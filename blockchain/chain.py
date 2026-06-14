"""
区块链管理模块
负责区块的添加、验证、查询等核心链操作
"""
import os
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .block import Block, ChainData, ChainDataType, create_genesis_block

logger = logging.getLogger(__name__)


class Blockchain:
    """
    极简区块链管理类
    管理区块的添加、验证、查询等操作
    """

    def __init__(self, node_id: str, ledger_path: str = "./data/ledger"):
        self.node_id = node_id
        self.ledger_path = ledger_path
        self.chain: List[Block] = []
        self.pending_data: List[ChainData] = []  # 待上链数据池
        
        # 确保账本目录存在
        os.makedirs(ledger_path, exist_ok=True)
        
        # 加载或创建链
        self._load_chain()

    def _load_chain(self):
        """从磁盘加载区块链"""
        chain_file = os.path.join(self.ledger_path, "chain.json")
        if os.path.exists(chain_file):
            try:
                with open(chain_file, 'r', encoding='utf-8') as f:
                    chain_data = json.load(f)
                self.chain = [Block.from_dict(b) for b in chain_data]
                logger.info(f"区块链加载成功，当前高度: {len(self.chain) - 1}")
                # 验证链的完整性
                if not self.is_chain_valid():
                    logger.error("区块链完整性校验失败！")
                    # 可以选择回滚或尝试修复
            except Exception as e:
                logger.error(f"加载区块链失败: {e}，创建新链")
                self._create_new_chain()
        else:
            self._create_new_chain()

    def _create_new_chain(self):
        """创建新的区块链（创世区块）"""
        genesis = create_genesis_block(self.node_id)
        self.chain = [genesis]
        self._save_chain()
        logger.info(f"创世区块已创建，哈希: {genesis.current_hash[:16]}...")

    def _save_chain(self):
        """保存区块链到磁盘"""
        chain_file = os.path.join(self.ledger_path, "chain.json")
        try:
            chain_data = [b.to_dict() for b in self.chain]
            with open(chain_file, 'w', encoding='utf-8') as f:
                json.dump(chain_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存区块链失败: {e}")

    def get_latest_block(self) -> Block:
        """获取最新区块"""
        return self.chain[-1]

    def get_block_by_height(self, height: int) -> Optional[Block]:
        """根据高度获取区块"""
        if 0 <= height < len(self.chain):
            return self.chain[height]
        return None

    def get_block_by_hash(self, block_hash: str) -> Optional[Block]:
        """根据哈希获取区块"""
        for block in self.chain:
            if block.current_hash == block_hash:
                return block
        return None

    def add_data(self, data: ChainData) -> bool:
        """
        添加数据到待上链池
        数据会暂时存放在 pending_data 中，等待打包成区块
        """
        self.pending_data.append(data)
        logger.debug(f"数据已加入待上链池，当前池大小: {len(self.pending_data)}")
        return True

    def add_data_batch(self, data_list: List[ChainData]) -> int:
        """批量添加数据到待上链池，返回成功数量"""
        count = 0
        for data in data_list:
            if self.add_data(data):
                count += 1
        return count

    def create_block(self, node_id: str) -> Block:
        """
        创建新区块
        将 pending_data 中的数据打包成新区块
        """
        latest_block = self.get_latest_block()
        
        new_block = Block(
            block_height=latest_block.block_height + 1,
            prev_block_hash=latest_block.current_hash,
            timestamp=int(datetime.now().timestamp()),
            client_node_id=node_id,
            data_list=self.pending_data.copy(),  # 复制当前待上链数据
            nonce=0
        )
        
        # 计算哈希
        new_block.current_hash = new_block.calculate_hash()
        
        # 清空待上链池
        self.pending_data.clear()
        
        logger.info(f"新区块已创建，高度: {new_block.block_height}, "
                   f"数据条数: {len(new_block.data_list)}, "
                   f"哈希: {new_block.current_hash[:16]}...")
        
        return new_block

    def add_block(self, block: Block) -> Tuple[bool, str]:
        """
        添加区块到链中
        返回: (是否成功, 错误信息)
        """
        # 验证区块
        is_valid, error_msg = self._validate_block(block)
        if not is_valid:
            return False, error_msg
        
        # 添加到链中
        self.chain.append(block)
        
        # 保存链
        self._save_chain()
        
        logger.info(f"区块已上链，高度: {block.block_height}, "
                   f"节点: {block.client_node_id}, "
                   f"哈希: {block.current_hash[:16]}...")
        
        return True, ""

    def _validate_block(self, block: Block) -> Tuple[bool, str]:
        """验证区块的合法性"""
        # 检查区块高度是否连续
        latest = self.get_latest_block()
        if block.block_height != latest.block_height + 1:
            return False, f"区块高度不连续: 期望 {latest.block_height + 1}, 实际 {block.block_height}"
        
        # 检查前一区块哈希是否正确
        if block.prev_block_hash != latest.current_hash:
            return False, f"前一区块哈希不匹配"
        
        # 检查区块哈希是否正确
        if not block.validate_hash():
            return False, f"区块哈希验证失败"
        
        # 检查区块哈希是否为空
        if not block.current_hash:
            return False, f"区块哈希为空"
        
        return True, ""

    def is_chain_valid(self) -> bool:
        """
        验证整个区块链的完整性
        遍历所有区块，检查哈希链接是否正确
        """
        if len(self.chain) == 0:
            return True
        
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]
            
            # 检查当前区块的 prev_hash 是否等于前一个区块的 hash
            if current.prev_block_hash != previous.current_hash:
                logger.error(f"区块 {i} 的前哈希不匹配")
                return False
            
            # 检查当前区块的哈希是否正确
            if not current.validate_hash():
                logger.error(f"区块 {i} 的哈希验证失败")
                return False
        
        return True

    def get_chain_info(self) -> Dict[str, Any]:
        """获取区块链信息"""
        return {
            "node_id": self.node_id,
            "chain_height": len(self.chain) - 1,
            "total_blocks": len(self.chain),
            "latest_block_hash": self.get_latest_block().current_hash if self.chain else "",
            "pending_data_count": len(self.pending_data),
            "is_valid": self.is_chain_valid(),
            "ledger_path": self.ledger_path
        }

    def query_data(self, data_type: Optional[int] = None,
                   device_ip: Optional[str] = None,
                   start_time: Optional[int] = None,
                   end_time: Optional[int] = None,
                   limit: int = 100) -> List[Dict[str, Any]]:
        """
        查询链上数据
        支持按数据类型、设备IP、时间范围过滤
        """
        results = []
        
        # 从最新区块开始往前查询
        for block in reversed(self.chain):
            if len(results) >= limit:
                break
            
            for data in block.data_list:
                if len(results) >= limit:
                    break
                
                # 过滤条件
                if data_type is not None and data.data_type != data_type:
                    continue
                if device_ip is not None and data.device_ip != device_ip:
                    continue
                if start_time is not None and data.timestamp < start_time:
                    continue
                if end_time is not None and data.timestamp > end_time:
                    continue
                
                results.append({
                    "block_height": block.block_height,
                    "block_hash": block.current_hash,
                    "timestamp": data.timestamp,
                    "data_type": data.data_type,
                    "device_ip": data.device_ip,
                    "content": data.content,
                    "operate_user": data.operate_user
                })
        
        return results

    def sync_chain(self, remote_chain: List[Block]) -> Tuple[bool, str]:
        """
        同步远程区块链
        如果远程链更长且有效，则替换本地链
        """
        if len(remote_chain) <= len(self.chain):
            return False, "远程链不比本地链长"
        
        # 验证远程链的完整性
        temp_blockchain = Blockchain.__new__(Blockchain)
        temp_blockchain.chain = remote_chain
        temp_blockchain.node_id = self.node_id
        if not temp_blockchain.is_chain_valid():
            return False, "远程链完整性验证失败"
        
        # 检查远程链是否与本地链有共同前缀
        common_height = min(len(self.chain), len(remote_chain)) - 1
        if self.chain[common_height].current_hash != remote_chain[common_height].current_hash:
            return False, "远程链与本地链分叉，无法同步"
        
        # 替换本地链
        self.chain = remote_chain
        self._save_chain()
        
        logger.info(f"区块链同步成功，新高度: {len(self.chain) - 1}")
        return True, "同步成功"
