# 项目记忆 - 区块链监控管理系统

## 项目概述
全球分布式机房区块链监控管理系统，基于Python自研极简联盟链。
- 仅适配 Ubuntu 20.04/22.04
- 技术栈：Python3.9+ / SQLite / Flask / SHA256 / ipmitool
- 测试服务器：8.152.4.161 (root/Dzy980708?)

## 项目结构
```
blockchain/  - 区块链核心 (block.py, chain.py, consensus.py, network.py)
client/      - 客户端模块 (collector.py, ipmi_executor.py, config_loader.py)
config/      - 配置文件 (config_template.yaml)
scripts/     - 部署脚本 (deploy.sh, monitor.service)
tests/       - 测试代码 (test_blockchain.py)
monitor_client.py - 主入口
p2p_server.py     - P2P网络服务器
web_server.py     - Web管理后台
```

## 核心设计决策
- 极简联盟链：仅区块打包+链式哈希+轮询共识+分布式账本
- PBFT简化版共识：轮询记账+80%阈值确认
- 客户端即链节点：单Python程序集成所有能力
- 业务与链解耦：客户端处理业务，链仅存证溯源
- IPMI白名单机制：仅允许安全指令执行
