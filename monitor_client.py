#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全球分布式机房区块链监控管理系统 - 主客户端程序
集成区块链、共识、网络、数据采集、IPMI执行等所有模块
"""
import os
import sys
import json
import time
import logging
import signal
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client.config_loader import load_config, get_node_id, get_peers
from blockchain.block import Block, ChainData, ChainDataType, create_genesis_block
from blockchain.chain import Blockchain
from blockchain.consensus import SimpleConsensus
from blockchain.network import P2PNetwork
from client.collector import HardwareCollector
from client.ipmi_executor import IPMIExecutor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("MonitorClient")


class MonitorClient:
    """
    监控客户端主类
    集成所有功能模块，是系统的核心入口
    """

    def __init__(self, config_path: str = "config/node_config.yaml"):
        """初始化客户端"""
        self.config_path = config_path
        self.config = load_config(config_path)
        self.node_id = get_node_id(self.config)
        
        logger.info("=" * 60)
        logger.info("监控客户端启动 - 节点ID: %s", self.node_id)
        logger.info("=" * 60)
        
        # 初始化各模块
        self._init_modules()
        
        # 运行状态
        self.is_running = False
        self.stop_event = threading.Event()
        
        # 后台线程引用
        self.p2p_thread = None
        self.web_thread = None
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _init_modules(self):
        """初始化所有模块"""
        logger.info("开始初始化各模块...")
        
        # 1. 区块链模块
        ledger_path = self.config.get("blockchain", {}).get("ledger_path", "./data/ledger")
        self.blockchain = Blockchain(self.node_id, ledger_path)
        logger.info("区块链模块初始化完成，当前高度: %d", len(self.blockchain.chain) - 1)
        
        # 2. 共识模块
        peers_config = get_peers(self.config)
        consensus_threshold = self.config.get("blockchain", {}).get("consensus_threshold", 80)
        self.consensus = SimpleConsensus(self.node_id, peers_config, consensus_threshold)
        logger.info("共识模块初始化完成，节点白名单数: %d", len(peers_config))
        
        # 3. 网络模块
        listen_port = self.config.get("blockchain", {}).get("listen_port", 8080)
        self.network = P2PNetwork(self.node_id, listen_port, peers_config)
        logger.info("网络模块初始化完成，监听端口: %d", listen_port)
        
        # 4. 数据采集模块
        client_config = self.config.get("client", {})
        ipmi_user = client_config.get("ipmi_username", "admin")
        ipmi_pass = client_config.get("ipmi_password", "admin123")
        self.collector = HardwareCollector(ipmi_user, ipmi_pass)
        logger.info("数据采集模块初始化完成")
        
        # 5. IPMI执行模块
        whitelist = client_config.get("ipmi_whitelist", ["power", "chassis", "sensor", "fru"])
        self.ipmi_executor = IPMIExecutor(ipmi_user, ipmi_pass, whitelist)
        logger.info("IPMI执行模块初始化完成，白名单: %s", whitelist)
        
        # 6. 托管设备列表
        self.managed_devices = []
        
        logger.info("所有模块初始化完成！")

    def start(self):
        """启动客户端主循环"""
        self.is_running = True
        logger.info("客户端主循环启动...")
        
        # 启动后台线程
        self._start_background_threads()
        
        try:
            # 主循环：数据采集 + 区块创建
            while not self.stop_event.is_set():
                # 1. 采集数据
                self._collect_data_cycle()
                
                # 2. 检查是否需要创建区块
                if self.consensus.is_my_turn():
                    self._create_and_propose_block()
                
                # 3. 清理过期数据
                self.consensus.cleanup_old_pending(3600)
                
                # 等待下一个采集周期
                collect_interval = self.config.get("client", {}).get("collect_interval", 30)
                self.stop_event.wait(collect_interval)
                
        except KeyboardInterrupt:
            logger.info("收到中断信号，准备退出...")
        finally:
            self.stop()

    def _start_background_threads(self):
        """启动后台线程"""
        # 导入服务器模块
        from p2p_server import set_client as set_p2p_client, start_server_thread as start_p2p
        from web_server import set_client as set_web_client, start_server_thread as start_web
        
        # 设置全局客户端引用
        set_p2p_client(self)
        set_web_client(self)
        
        # 启动P2P服务器线程
        p2p_port = self.config.get("blockchain", {}).get("listen_port", 8080)
        self.p2p_thread = start_p2p(host="0.0.0.0", port=p2p_port)
        
        # 启动Web管理后台线程
        web_port = self.config.get("web", {}).get("port", 5000)
        self.web_thread = start_web(host="0.0.0.0", port=web_port)
        
        # 心跳线程（已在network模块中启动）
        # self.network.start_heartbeat_thread(30)
        
        logger.info("所有后台线程已启动")

    def _collect_data_cycle(self):
        """数据采集周期"""
        logger.debug("开始数据采集周期...")
        
        # 如果没有托管设备，尝试扫描
        if not self.managed_devices:
            self._scan_devices()
        
        # 采集每个设备的数据
        for device in self.managed_devices:
            device_ip = device.get("ip")
            if not device_ip:
                continue
            
            try:
                # 采集FRU信息（去重）
                fru_data = self.collector.collect_fru_info(device_ip)
                if fru_data.get("success") and self.collector.is_fru_changed(device_ip, fru_data):
                    chain_data = ChainData(
                        data_type=int(ChainDataType.FRU_HARDWARE),
                        device_ip=device_ip,
                        content=json.dumps(fru_data, ensure_ascii=False),
                        operate_user="system"
                    )
                    self.blockchain.add_data(chain_data)
                    logger.info("FRU数据已加入上链池: %s", device_ip)
                
                # 采集性能指标
                perf_data = self.collector.collect_performance_metrics(device_ip)
                if perf_data.get("success"):
                    chain_data = ChainData(
                        data_type=int(ChainDataType.PERFORMANCE),
                        device_ip=device_ip,
                        content=json.dumps(perf_data, ensure_ascii=False),
                        operate_user="system"
                    )
                    self.blockchain.add_data(chain_data)
                    
            except Exception as e:
                logger.error("采集设备 %s 数据失败: %s", device_ip, e)
        
        # 采集本地指标
        local_metrics = self.collector.collect_local_metrics()
        chain_data = ChainData(
            data_type=int(ChainDataType.PERFORMANCE),
            device_ip="localhost",
            content=json.dumps(local_metrics, ensure_ascii=False),
            operate_user="system"
        )
        self.blockchain.add_data(chain_data)
        
        logger.debug("数据采集周期完成，待上链数据: %d", len(self.blockchain.pending_data))

    def _scan_devices(self):
        """扫描机房内网设备（简化版）"""
        client_config = self.config.get("client", {})
        scan_subnets = client_config.get("scan_subnets", [])
        
        logger.info("扫描网络设备，网段: %s", scan_subnets)
        
        # 示例：添加一些测试设备
        example_devices = [
            {"ip": "10.0.1.100", "name": "server-1"},
            {"ip": "10.0.1.101", "name": "server-2"}
        ]
        
        self.managed_devices = example_devices
        logger.info("扫描完成，发现设备数: %d", len(self.managed_devices))

    def _create_and_propose_block(self):
        """创建并提议新区块"""
        # 检查是否有待上链数据
        if not self.blockchain.pending_data:
            logger.debug("无待上链数据，跳过区块创建")
            return None
        
        logger.info("创建新区块，待上链数据: %d 条", len(self.blockchain.pending_data))
        
        # 创建区块
        new_block = self.blockchain.create_block(self.node_id)
        
        # 提议区块（加入待确认列表）
        block_hash = self.consensus.propose_block(new_block)
        
        # 广播区块提议
        block_data = new_block.to_dict()
        broadcast_results = self.network.broadcast_block_proposal(block_data)
        
        # 自己先投票（同意）
        self.consensus.vote_block(block_hash, self.node_id, True)
        
        # 切换到下一个记账节点
        next_node = self.consensus.next_leader()
        logger.info("区块提议完成，下一记账节点: %s", next_node)
        
        return new_block

    def execute_ipmi_command(self, target_ip: str, command: str, 
                              operator: str = "web"):
        """
        执行IPMI命令（供Web后台调用）
        返回执行结果，并自动上链审计
        """
        logger.info("收到IPMI命令: %s - %s", target_ip, command[:50])
        
        # 执行命令
        cmd_record = self.ipmi_executor.execute_command(target_ip, command, operator)
        
        # 上链审计
        chain_data = ChainData(
            data_type=int(ChainDataType.IPMI_OPERATION),
            device_ip=target_ip,
            content=json.dumps({
                "command": command,
                "status": cmd_record.status,
                "result": cmd_record.result[:500] if cmd_record.result else "",
                "error": cmd_record.error[:500] if cmd_record.error else ""
            }, ensure_ascii=False),
            operate_user=operator
        )
        self.blockchain.add_data(chain_data)
        
        return {
            "command_id": cmd_record.command_id,
            "status": cmd_record.status,
            "result": cmd_record.result,
            "error": cmd_record.error
        }

    def get_status(self):
        """获取客户端完整状态"""
        return {
            "node_id": self.node_id,
            "is_running": self.is_running,
            "blockchain": self.blockchain.get_chain_info(),
            "network": self.network.get_network_status(),
            "managed_devices": len(self.managed_devices),
            "pending_ipmi_commands": len(self.ipmi_executor.command_history),
            "timestamp": datetime.now().isoformat()
        }

    def stop(self):
        """停止客户端"""
        logger.info("正在停止客户端...")
        self.is_running = False
        self.stop_event.set()
        
        # 保存区块链状态
        self.blockchain._save_chain()
        
        logger.info("客户端已停止")

    def _signal_handler(self, sig, frame):
        """信号处理器"""
        logger.info("收到信号: %s", sig)
        self.stop()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="区块链监控客户端")
    parser.add_argument("--config", default="config/node_config.yaml", 
                       help="配置文件路径")
    parser.add_argument("--init", action="store_true",
                       help="初始化配置并退出")
    
    args = parser.parse_args()
    
    if args.init:
        # 仅初始化配置
        load_config(args.config)
        print("配置文件已创建: %s" % args.config)
        print("请编辑配置文件后重新运行")
        return
    
    # 启动客户端
    client = MonitorClient(args.config)
    client.start()


if __name__ == "__main__":
    main()
