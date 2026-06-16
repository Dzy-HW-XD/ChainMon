"""
区块结构定义与哈希计算
极简区块：仅包含核心字段，无冗余数据
"""
import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from enum import IntEnum


class ChainDataType(IntEnum):
    """链上数据类型"""
    FRU_HARDWARE = 0      # 硬件FRU数据
    PERFORMANCE = 1        # 性能指标
    IPMI_OPERATION = 2     # IPMI操作日志
    NODE_HEARTBEAT = 3    # 节点心跳
    CONFIG_CHANGE = 4      # 配置变更


@dataclass
class ChainData:
    """链上通用数据结构体"""
    data_type: int             # 数据类型（ChainDataType）
    device_ip: str             # 目标设备IP
    content: str               # 具体数据/指令内容（JSON字符串）
    operate_user: str          # 操作用户/后台账号
    timestamp: int = 0         # 数据产生时间戳
    data_id: str = ""          # 数据唯一ID（可选）

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = int(time.time())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChainData':
        return cls(**data)


@dataclass
class Block:
    """
    极简区块结构体
    仅保留运维系统必需核心字段，降低计算与存储压力
    """
    block_height: int                      # 区块高度（自增唯一）
    prev_block_hash: str                   # 上一区块哈希（链式关联核心）
    timestamp: int                         # 区块打包时间戳
    client_node_id: str                    # 上报机房本地客户端节点ID
    data_list: List[ChainData]            # 链上数据（监控数据/操作日志）
    current_hash: str = ""                # 当前区块哈希（计算字段）
    node_sign: str = ""                   # 节点签名（防伪造）
    nonce: int = 0                        # 随机数（用于哈希计算）

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = int(time.time())
        # 如果没有哈希，自动计算
        if not self.current_hash:
            self.current_hash = self.calculate_hash()
    
    def calculate_hash(self) -> str:
        """
        计算区块哈希
        哈希输入：block_height + prev_block_hash + timestamp + data_list_json + node_sign + nonce
        """
        # 构建哈希原始数据
        data_json = json.dumps(
            [d.to_dict() for d in self.data_list],
            ensure_ascii=False,
            sort_keys=True
        )
        raw = f"{self.block_height}{self.prev_block_hash}{self.timestamp}{data_json}{self.node_sign}{self.nonce}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()
    
    def recalculate_hash(self) -> str:
        """重新计算哈希（用于验证）"""
        self.current_hash = self.calculate_hash()
        return self.current_hash
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "block_height": self.block_height,
            "prev_block_hash": self.prev_block_hash,
            "timestamp": self.timestamp,
            "client_node_id": self.client_node_id,
            "data_list": [d.to_dict() for d in self.data_list],
            "current_hash": self.current_hash,
            "node_sign": self.node_sign,
            "nonce": self.nonce
        }
    
    def to_json(self) -> str:
        """序列化为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Block':
        """从字典反序列化"""
        data_list = [ChainData.from_dict(d) for d in data.get("data_list", [])]
        return cls(
            block_height=data["block_height"],
            prev_block_hash=data["prev_block_hash"],
            timestamp=data["timestamp"],
            client_node_id=data["client_node_id"],
            data_list=data_list,
            current_hash=data.get("current_hash", ""),
            node_sign=data.get("node_sign", ""),
            nonce=data.get("nonce", 0)
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Block':
        """从JSON字符串反序列化"""
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def validate_hash(self) -> bool:
        """验证区块哈希是否正确"""
        calculated = self.calculate_hash()
        return calculated == self.current_hash


def create_genesis_block(node_id: str) -> Block:
    """
    创建创世区块（第一个区块）
    创世区块的 prev_block_hash 为全0
    """
    genesis = Block(
        block_height=0,
        prev_block_hash="0" * 64,  # 64个0
        timestamp=1,
        client_node_id=node_id,
        data_list=[],
        nonce=0
    )
    genesis.current_hash = genesis.calculate_hash()
    return genesis


def mine_block(block: Block, difficulty: int = 0) -> Block:
    """
    简易挖矿（可选，用于增加区块生成难度）
    difficulty=0 表示不挖矿，直接返回
    difficulty>0 表示哈希前N位必须为0
    """
    if difficulty <= 0:
        block.current_hash = block.calculate_hash()
        return block
    
    target = "0" * difficulty
    while True:
        hash_val = block.calculate_hash()
        if hash_val.startswith(target):
            block.current_hash = hash_val
            break
        block.nonce += 1
    
    return block
