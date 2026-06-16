"""
极简共识机制模块
采用固定节点轮询记账（Round-Robin）+ 简易确认机制
适配私有联盟链场景，零挖矿、零能耗
"""
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import IntEnum

logger = logging.getLogger(__name__)


class BlockStatus(IntEnum):
    """区块状态"""
    PENDING = 0      # 待确认
    CONFIRMED = 1    # 已确认
    REJECTED = 2     # 已拒绝


@dataclass
class BlockVote:
    """区块投票/确认记录"""
    block_hash: str
    voter_node_id: str
    vote_time: int
    is_approved: bool
    signature: str = ""


class SimpleConsensus:
    """
    极简共识管理器
    - 轮询记账：节点按顺序轮流创建区块
    - 确认机制：区块创建后广播，超过阈值(80%)节点确认后正式上链
    """

    def __init__(self, node_id: str, peers: List[Dict[str, Any]], 
                 consensus_threshold: int = 80):
        """
        初始化共识管理器
        :param node_id: 当前节点ID
        :param peers: 节点白名单列表 [{"node_id": "", "host": "", "port": 0, ...}]
        :param consensus_threshold: 共识阈值（百分比）
        """
        self.node_id = node_id
        self.peers = peers  # 节点白名单
        self.consensus_threshold = consensus_threshold
        
        # 当前轮询指针（下一个应该创建区块的节点索引）
        self.current_leader_index = 0
        
        # 待确认区块缓存 {block_hash: {"block": Block, "votes": [BlockVote], "status": BlockStatus}}
        self.pending_blocks: Dict[str, Dict] = {}
        
        # 已确认的区块哈希集合（用于快速去重）
        self.confirmed_block_hashes: set = set()

    def get_peer_nodes(self) -> List[str]:
        """获取所有对等节点ID列表"""
        return [p["node_id"] for p in self.peers]

    def get_peer_info(self, node_id: str) -> Optional[Dict[str, Any]]:
        """根据节点ID获取节点信息"""
        for p in self.peers:
            if p["node_id"] == node_id:
                return p
        return None

    def _get_all_nodes(self) -> List[str]:
        """
        获取包含自身在内的所有节点ID列表（按字母排序保证所有节点视图一致）
        """
        peer_ids = [p["node_id"] for p in self.peers]
        all_nodes = sorted(set([self.node_id] + peer_ids))
        return all_nodes

    def is_my_turn(self, chain_height: int = 0) -> bool:
        """
        判断当前节点是否应该创建下一个区块
        决定性轮询：基于当前链高度决定leader，所有节点结果一致
        chain_height % len(all_nodes) 决定下一个出块节点
        """
        all_nodes = self._get_all_nodes()

        if len(all_nodes) == 1:
            return True  # 只有自己，直接返回True

        # 找到当前节点在排序列表中的索引
        try:
            my_index = all_nodes.index(self.node_id)
        except ValueError:
            logger.warning(f"当前节点 {self.node_id} 不在节点列表中")
            return True  # 保险起见允许出块

        # 基于链高度的决定性轮询
        # 链高度N → 下一个区块高度N+1 → leader = all_nodes[(N+1) % len(all_nodes)]
        # 但更直观：当前高度N → leader = all_nodes[N % len(all_nodes)]
        # 例如：height=0(ali创世), height=1(tc出块), height=2(ali出块)
        leader_index = chain_height % len(all_nodes)
        return my_index == leader_index

    def get_current_leader(self, chain_height: int = 0) -> str:
        """获取当前应该出块的节点ID"""
        all_nodes = self._get_all_nodes()
        if not all_nodes:
            return self.node_id
        leader_index = chain_height % len(all_nodes)
        return all_nodes[leader_index]

    def next_leader(self) -> str:
        """
        切换到下一个记账节点
        返回下一个记账节点的ID
        """
        all_nodes = self._get_all_nodes()
        if len(all_nodes) == 0:
            return self.node_id
        
        self.current_leader_index = (self.current_leader_index + 1) % len(all_nodes)
        next_node = all_nodes[self.current_leader_index]
        logger.debug(f"记账权转移至: {next_node} (index={self.current_leader_index})")
        return next_node

    def propose_block(self, block: 'Block') -> str:
        """
        提议一个新区块（当前节点创建区块后调用）
        将区块加入待确认列表
        返回区块哈希
        """
        block_hash = block.current_hash
        
        self.pending_blocks[block_hash] = {
            "block": block,
            "votes": [],
            "status": BlockStatus.PENDING,
            "proposer": self.node_id,
            "propose_time": int(time.time())
        }
        
        logger.info(f"区块提议已提交，哈希: {block_hash[:16]}..., 提议者: {self.node_id}")
        return block_hash

    def receive_block_proposal(self, block: 'Block', proposer_id: str) -> Tuple[bool, str]:
        """
        接收其他节点发来的区块提议
        返回: (是否接受, 原因)
        """
        block_hash = block.current_hash
        
        # 检查区块是否已经确认过（防重放）
        if block_hash in self.confirmed_block_hashes:
            return False, "区块已确认，忽略"
        
        # 检查区块哈希是否正确
        if not block.validate_hash():
            return False, "区块哈希验证失败"
        
        # 接受区块提议
        self.pending_blocks[block_hash] = {
            "block": block,
            "votes": [],
            "status": BlockStatus.PENDING,
            "proposer": proposer_id,
            "propose_time": int(time.time())
        }
        
        logger.info(f"收到区块提议，哈希: {block_hash[:16]}..., 提议者: {proposer_id}")
        return True, "接受"

    def vote_block(self, block_hash: str, voter_id: str, is_approved: bool) -> bool:
        """
        对区块进行投票/确认
        返回: 是否投票成功
        """
        if block_hash not in self.pending_blocks:
            logger.warning(f"区块 {block_hash[:16]}... 不在待确认列表中")
            return False
        
        pending = self.pending_blocks[block_hash]
        
        # 检查是否已经投过票
        for v in pending["votes"]:
            if v.voter_node_id == voter_id:
                logger.warning(f"节点 {voter_id} 已经对区块 {block_hash[:16]}... 投过票")
                return False
        
        # 添加投票记录
        vote = BlockVote(
            block_hash=block_hash,
            voter_node_id=voter_id,
            vote_time=int(time.time()),
            is_approved=is_approved
        )
        pending["votes"].append(vote)
        
        logger.info(f"节点 {voter_id} 对区块 {block_hash[:16]}... "
                   f"投票: {'同意' if is_approved else '拒绝'}")
        
        # 检查是否达到共识阈值
        self._check_consensus(block_hash)
        
        return True

    def _check_consensus(self, block_hash: str):
        """
        检查区块是否达到共识阈值
        如果达到，将区块状态改为已确认
        """
        if block_hash not in self.pending_blocks:
            return
        
        pending = self.pending_blocks[block_hash]
        
        if pending["status"] != BlockStatus.PENDING:
            return  # 已经处理过了
        
        # 统计同意票数
        all_nodes = self._get_all_nodes()
        total_nodes = len(all_nodes)  # 含自身的总节点数
        approve_votes = sum(1 for v in pending["votes"] if v.is_approved)
        
        if total_nodes == 0:
            approval_rate = 100
        else:
            approval_rate = (approve_votes / total_nodes) * 100
        
        logger.debug(f"区块 {block_hash[:16]}...  consensus检查: "
                   f"同意={approve_votes}/{total_nodes}, 通过率={approval_rate:.1f}%")
        
        # 检查是否达到阈值
        if approval_rate >= self.consensus_threshold:
            pending["status"] = BlockStatus.CONFIRMED
            self.confirmed_block_hashes.add(block_hash)
            logger.info(f"区块 {block_hash[:16]}... 已达到共识阈值，正式确认！")
        elif total_nodes > 0 and (total_nodes - approve_votes) / total_nodes * 100 >= self.consensus_threshold:
            # 超过阈值的人反对，拒绝区块
            pending["status"] = BlockStatus.REJECTED
            logger.warning(f"区块 {block_hash[:16]}... 已被拒绝")

    def get_confirmed_block(self, block_hash: str) -> Optional['Block']:
        """
        获取已确认的区块
        返回: 区块对象，如果未确认则返回None
        """
        if block_hash not in self.pending_blocks:
            return None
        
        pending = self.pending_blocks[block_hash]
        if pending["status"] == BlockStatus.CONFIRMED:
            return pending["block"]
        
        return None

    def get_pending_blocks(self) -> List[Dict[str, Any]]:
        """获取所有待确认的区块信息"""
        result = []
        for block_hash, pending in self.pending_blocks.items():
            result.append({
                "block_hash": block_hash,
                "status": pending["status"].value,
                "proposer": pending["proposer"],
                "vote_count": len(pending["votes"]),
                "propose_time": pending["propose_time"]
            })
        return result

    def cleanup_old_pending(self, max_age_seconds: int = 3600):
        """
        清理过期的待确认区块
        """
        current_time = int(time.time())
        to_remove = []
        
        for block_hash, pending in self.pending_blocks.items():
            age = current_time - pending["propose_time"]
            if age > max_age_seconds and pending["status"] == BlockStatus.PENDING:
                to_remove.append(block_hash)
        
        for block_hash in to_remove:
            del self.pending_blocks[block_hash]
            logger.info(f"清理过期待确认区块: {block_hash[:16]}...")

    def update_peers(self, new_peers: List[Dict[str, Any]]):
        """更新节点白名单"""
        self.peers = new_peers
        logger.info(f"节点白名单已更新，当前节点数: {len(self.peers)}")
