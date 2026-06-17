"""
P2P网络模块
基于HTTP的极简节点间通信
负责区块广播、投票传播、链同步等网络操作
"""
import requests
import time
import logging
import threading
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class PeerNode:
    """对等节点信息"""
    node_id: str
    host: str
    port: int
    region: str
    last_heartbeat: int = 0
    is_online: bool = True

    def get_url(self, path: str = "") -> str:
        """获取节点完整URL"""
        return f"http://{self.host}:{self.port}{path}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "region": self.region,
            "last_heartbeat": self.last_heartbeat,
            "is_online": self.is_online
        }


class P2PNetwork:
    """
    P2P网络管理器
    负责节点发现、消息广播、区块同步等网络操作
    """

    def __init__(self, node_id: str, listen_port: int, peers_config: List[Dict[str, Any]]):
        """
        初始化P2P网络
        :param node_id: 当前节点ID
        :param listen_port: 当前节点监听端口
        :param peers_config: 节点白名单配置
        """
        self.node_id = node_id
        self.listen_port = listen_port
        self.peers: Dict[str, PeerNode] = {}
        
        # 从配置加载节点信息
        for p in peers_config:
            peer = PeerNode(
                node_id=p["node_id"],
                host=p["host"],
                port=p["port"],
                region=p.get("region", "unknown")
            )
            self.peers[peer.node_id] = peer
        
        # 移除自己（不把自己当对等节点）
        if self.node_id in self.peers:
            del self.peers[self.node_id]
        
        logger.info(f"P2P网络初始化完成，对等节点数: {len(self.peers)}")

    def get_peers(self) -> List[PeerNode]:
        """获取所有对等节点"""
        return list(self.peers.values())

    def get_online_peers(self) -> List[PeerNode]:
        """获取所有在线对等节点"""
        return [p for p in self.peers.values() if p.is_online]

    def update_peer_status(self, node_id: str, is_online: bool):
        """更新节点在线状态"""
        if node_id in self.peers:
            self.peers[node_id].is_online = is_online
            self.peers[node_id].last_heartbeat = int(time.time())

    def broadcast_block_proposal(self, block_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        广播区块提议给所有在线节点
        返回: {node_id: (success, response)} 字典
        """
        results = {}
        block_hash = block_data.get("current_hash", "unknown")
        
        logger.info(f"开始广播区块提议 {block_hash[:16]}... 给 {len(self.get_online_peers())} 个节点")
        
        for peer in self.get_online_peers():
            try:
                url = peer.get_url("/p2p/block/propose")
                resp = requests.post(url, json=block_data, timeout=10)
                if resp.status_code == 200:
                    results[peer.node_id] = (True, resp.json())
                else:
                    results[peer.node_id] = (False, f"HTTP {resp.status_code}")
            except Exception as e:
                logger.warning(f"广播区块到节点 {peer.node_id} 失败: {e}")
                results[peer.node_id] = (False, str(e))
                self.update_peer_status(peer.node_id, False)
        
        success_count = sum(1 for s, _ in results.values() if s)
        logger.info(f"区块广播完成，成功: {success_count}/{len(results)}")
        return results

    def broadcast_vote(self, block_hash: str, voter_id: str, is_approved: bool) -> Dict[str, Any]:
        """
        广播投票给所有在线节点
        """
        vote_data = {
            "block_hash": block_hash,
            "voter_id": voter_id,
            "is_approved": is_approved,
            "timestamp": int(time.time())
        }
        
        results = {}
        for peer in self.get_online_peers():
            try:
                url = peer.get_url("/p2p/block/vote")
                resp = requests.post(url, json=vote_data, timeout=10)
                if resp.status_code == 200:
                    results[peer.node_id] = (True, resp.json())
                else:
                    results[peer.node_id] = (False, f"HTTP {resp.status_code}")
            except Exception as e:
                logger.warning(f"广播投票到节点 {peer.node_id} 失败: {e}")
                results[peer.node_id] = (False, str(e))
        
        return results

    def request_chain_sync(self, peer_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        向指定节点请求区块链同步
        返回: 远程链的区块列表（字典格式），失败返回None
        """
        if peer_id not in self.peers:
            logger.error(f"节点 {peer_id} 不在对等节点列表中")
            return None
        
        peer = self.peers[peer_id]
        try:
            url = peer.get_url("/p2p/chain/sync")
            resp = requests.get(url, timeout=90)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("chain", [])
            else:
                logger.error(f"请求链同步失败: HTTP {resp.status_code}")
                return None
        except Exception as e:
            logger.error(f"请求链同步异常: {e}")
            return None

    def send_heartbeat(self, peer_id: str) -> bool:
        """
        向指定节点发送心跳
        """
        if peer_id not in self.peers:
            return False
        
        peer = self.peers[peer_id]
        try:
            url = peer.get_url("/p2p/heartbeat")
            data = {
                "node_id": self.node_id,
                "timestamp": int(time.time()),
                "status": "online"
            }
            resp = requests.post(url, json=data, timeout=5)
            is_online = resp.status_code == 200
            self.update_peer_status(peer_id, is_online)
            return is_online
        except Exception as e:
            logger.debug(f"发送心跳到 {peer_id} 失败: {e}")
            self.update_peer_status(peer_id, False)
            return False

    def broadcast_heartbeat(self):
        """向所有配置节点发送心跳，允许离线节点恢复为在线。"""
        for peer in self.get_peers():
            self.send_heartbeat(peer.node_id)

    def discover_peers(self) -> List[Dict[str, Any]]:
        """
        发现网络中的其他节点
        向已知节点请求其已知的节点列表
        """
        discovered = []
        for peer in self.get_online_peers():
            try:
                url = peer.get_url("/p2p/peers")
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    peer_list = resp.json().get("peers", [])
                    discovered.extend(peer_list)
            except Exception as e:
                logger.debug(f"从节点 {peer.node_id} 发现节点失败: {e}")
        
        return discovered

    def start_heartbeat_thread(self, interval: int = 30):
        """
        启动心跳线程（后台定期发送心跳）
        """
        def heartbeat_loop():
            while True:
                try:
                    self.broadcast_heartbeat()
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"心跳线程异常: {e}")
                    time.sleep(interval)
        
        t = threading.Thread(target=heartbeat_loop, daemon=True, name="heartbeat")
        t.start()
        logger.info(f"心跳线程已启动，间隔: {interval}秒")

    def get_network_status(self) -> Dict[str, Any]:
        """获取网络状态"""
        online = self.get_online_peers()
        return {
            "total_peers": len(self.peers),
            "online_peers": len(online),
            "offline_peers": len(self.peers) - len(online),
            "peers": [p.to_dict() for p in self.peers.values()]
        }
