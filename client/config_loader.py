"""
配置加载模块
从YAML文件加载系统配置
"""
import os
import yaml
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "node": {
        "node_id": "default-node",
        "node_name": "默认机房节点",
        "region": "cn-beijing",
        "role": "server",
        "mode": "server"
    },
    "blockchain": {
        "listen_port": 8080,
        "genesis_hash": "",
        "block_interval": 30,
        "consensus_threshold": 80,
        "ledger_path": "./data/ledger"
    },
    "peers": [],
    "agent": {
        "upstream": "",
        "upstreams": [],
        "token": "",
        "push_interval": 30,
        "task_poll_interval": 30
    },
    "client": {
        "scan_subnets": ["10.0.1.0/24"],
        "ipmi_username": "admin",
        "ipmi_password": "admin123",
        "collect_interval": 30,
        "batch_size": 50,
        "cache_path": "./data/cache",
        "ipmi_whitelist": ["power", "chassis", "sensor", "fru", "sel", "lan", "user"]
    },
    "database": {
        "sqlite_path": "./data/monitor.db",
        "retention_days": 90
    },
    "web": {
        "port": 5000,
        "debug": False,
        "username": "admin",
        "password": "admin123"
    },
    "logging": {
        "level": "INFO",
        "file_path": "./logs/monitor.log",
        "retention_days": 30
    }
}


def load_config(config_path: str = "config/node_config.yaml") -> Dict[str, Any]:
    """
    加载配置文件
    如果配置文件不存在，创建默认配置
    """
    if not os.path.exists(config_path):
        logger.warning(f"配置文件不存在: {config_path}，创建默认配置")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(DEFAULT_CONFIG, f, allow_unicode=True, default_flow_style=False)
        return DEFAULT_CONFIG
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info(f"配置文件加载成功: {config_path}")
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}，使用默认配置")
        return DEFAULT_CONFIG


def save_config(config: Dict[str, Any], config_path: str = "config/node_config.yaml") -> None:
    """保存配置到文件"""
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
    logger.info(f"配置已保存: {config_path}")


def get_node_id(config: Dict[str, Any]) -> str:
    """从配置中获取节点ID"""
    return config.get("node", {}).get("node_id", "unknown")


def get_peers(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从配置中获取节点白名单"""
    return config.get("peers", [])
