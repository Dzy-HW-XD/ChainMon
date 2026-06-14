# ChainMon

> Chain + Monitor — 全球分布式机房极简联盟链监控管理系统

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Ubuntu%2020.04%2F22.04-orange.svg)](https://ubuntu.com/)

ChainMon 是基于 Python 自研轻量化联盟链的全球分布式机房监控系统，无代币、无挖矿、无复杂共识、无重型依赖。

通过在各机房部署 Ubuntu 专属本地服务客户端，实现服务器 FRU 硬件采集、性能指标监控、IPMI 远程指令管控，所有数据与运维操作上链存证、不可篡改、全程溯源。

## 目录

- [项目简介](#项目简介)
- [系统架构](#系统架构)
- [核心特性](#核心特性)
- [环境依赖](#环境依赖)
- [快速部署](#快速部署)
- [配置说明](#配置说明)
- [使用指南](#使用指南)
- [API文档](#api文档)
- [开发指南](#开发指南)
- [许可证](#许可证)

## 项目简介

传统中心化运维管控平台依赖中心服务器，极易出现跨区卡顿、单点宕机、运维操作无记录、设备数据可篡改、权责无法追溯等问题。

本系统摒弃复杂公链架构、无需挖矿、无需代币，采用最简联盟链区块链技术，在各机房部署专属本地服务客户端，实现：

- 硬件静态信息采集（FRU完整硬件信息）
- 设备动态指标采集（CPU、内存、磁盘IO、GPU、温度、功耗）
- 远程IPMI指令管控（开机、关机、重启、硬件参数查询）
- 全球分布式就近组网（就近采集、就近上报）
- 区块链可信溯源能力（所有数据、操作全上链存储）

## 系统架构

```
+———————————————————————————————+
|                    应用层：可视化管理后台                        |
|          (设备状态查看、IPMI指令下发、溯源查询、告警)           |
+———————————————————————————————+
                        ↓
+———————————————————————————————+
|                  核心层：极简私有联盟链网络                    |
|    (区块打包、链式哈希校验、PBFT简化共识、分布式账本同步)      |
+———————————————————————————————+
                        ↓
+———————————————————————————————+
|            终端层：机房本地服务客户端（多节点）                |
|  (局域网扫描、数据采集、IPMI执行、本地缓存、数据上链)         |
+———————————————————————————————+
```

### 架构分层

1. **终端层**：机房本地服务客户端，每个机房部署一套，独立完成组网、数据采集、指令执行、链上存证
2. **核心层**：极简私有联盟链网络，由所有客户端节点共同组成，提供分布式记账存证能力
3. **应用层**：可视化管理后台，数据展示、指令下发、溯源查询

## 核心特性

- **极简联盟链架构**：摒弃公链冗余能力，仅保留链式记账、哈希防篡改、分布式共识、账本同步核心能力
- **分布式就近部署**：各机房本地客户端独立组网、就近采集、就近执行，规避跨区网络延迟
- **全维度硬件监控**：支持 FRU 静态硬件信息、CPU/内存/磁盘IO/GPU/温度/功耗全指标采集
- **可信IPMI运维**：标准化 ipmitool 指令下发与执行，所有运维操作自动上链审计
- **断网容错能力**：离线缓存、联网补传，保证数据零丢失
- **无单点故障**：多节点分布式账本同步，去中心化组网
- **纯Ubuntu适配**：环境统一、依赖统一、部署简单

## 环境依赖

### 系统要求

- **操作系统**：Ubuntu 20.04 LTS 或 Ubuntu 22.04 LTS（仅支持Ubuntu）
- **Python版本**：Python 3.9+
- **硬件要求**：2核4G及以上（推荐4核8G）

### 基础依赖

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ipmitool openssh-client curl
```

### Python依赖

```bash
pip install -r requirements.txt
```

主要依赖包：
- `flask` - Web框架
- `psutil` - 系统性能采集
- `requests` - HTTP客户端
- `pyyaml` - YAML配置文件解析
- `sqlalchemy` - 数据库ORM（可选）

## 快速部署

### 1. 克隆项目

```bash
git clone https://github.com/yourusername/ChainMon.git
cd ChainMon
```

### 2. 初始化配置

```bash
# 创建默认配置文件
python3 monitor_client.py --init

# 编辑配置文件
vim config/node_config.yaml
```

### 3. 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. 启动客户端

```bash
# 前台运行（测试）
python3 monitor_client.py

# 后台运行（生产）
nohup python3 monitor_client.py > logs/monitor.log 2>&1 &

# 或使用 systemd（推荐）
sudo cp scripts/monitor.service /etc/systemd/system/
sudo systemctl enable monitor
sudo systemctl start monitor
```

### 5. 访问管理后台

浏览器打开：`http://服务器IP:5000`

默认账号：`admin / admin123`

## 配置说明

配置文件位置：`config/node_config.yaml`

### 核心配置项

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `node.node_id` | 节点唯一ID（机房标识） | `default-node` |
| `node.region` | 机房区域 | `cn-beijing` |
| `blockchain.listen_port` | 区块链P2P监听端口 | `8080` |
| `blockchain.consensus_threshold` | 共识阈值（百分比） | `80` |
| `peers` | 节点白名单（其他节点信息） | `[]` |
| `client.ipmi_username` | IPMI默认用户名 | `admin` |
| `client.collect_interval` | 数据采集间隔（秒） | `30` |
| `web.port` | Web管理后台端口 | `5000` |

### 节点白名单配置示例

```yaml
peers:
  - node_id: "bj-dc1"
    host: "10.0.1.10"
    port: 8080
    region: "cn-beijing"
  - node_id: "sh-dc2"
    host: "10.0.2.10"
    port: 8080
    region: "cn-shanghai"
```

## 使用指南

### Web管理后台

访问 `http://服务器IP:5000` 进入管理后台，功能包括：

1. **仪表盘**：查看节点状态、区块链信息、网络设备列表
2. **设备管理**：查看托管设备列表、设备详情
3. **IPMI操作**：下发IPMI指令（开机、关机、重启、查询等）
4. **区块链浏览**：查看区块列表、区块详情、链上数据
5. **审计日志**：查看所有上链的操作记录

### API接口

#### 获取系统状态

```bash
GET /api/status
```

#### 执行IPMI指令

```bash
POST /api/ipmi/execute
Content-Type: application/json

{
  "ip": "10.0.1.100",
  "command": "power status"
}
```

#### 查询链上数据

```bash
GET /api/query?data_type=0&device_ip=10.0.1.100&limit=50
```

#### 查看区块列表

```bash
GET /api/blockchain/blocks?limit=20
```

## 开发指南

### 项目结构

```
ChainMon/
├── blockchain/              # 区块链核心模块
│   ├── __init__.py
│   ├── block.py           # 区块结构定义与哈希计算
│   ├── chain.py           # 区块链管理（添加、验证、查询）
│   ├── consensus.py       # 极简共识机制（轮询+确认）
│   └── network.py        # P2P网络模块（节点通信）
├── client/                # 客户端模块
│   ├── __init__.py
│   ├── collector.py      # 数据采集（FRU、性能指标）
│   ├── ipmi_executor.py # IPMI指令执行器
│   └── config_loader.py  # 配置加载模块
├── web/                   # Web管理后台（可选）
├── config/                # 配置文件
│   ├── config_template.yaml  # 配置模板
│   └── node_config.yaml     # 实际配置（不提交）
├── data/                  # 数据目录（gitignore）
├── logs/                  # 日志目录（gitignore）
├── scripts/               # 部署脚本
├── tests/                 # 测试代码
├── monitor_client.py      # 主客户端程序（入口）
├── p2p_server.py         # P2P网络服务器
├── web_server.py          # Web管理后台服务器
├── requirements.txt      # Python依赖
├── README.md             # 项目文档
└── .gitignore            # Git忽略文件
```

### 开发流程

1. **修改代码**：在对应模块中进行修改
2. **运行测试**：`python3 -m pytest tests/`
3. **启动客户端**：`python3 monitor_client.py`
4. **查看日志**：`tail -f logs/monitor.log`

### 添加新功能

1. 在相应模块中添加代码
2. 更新API接口（如需要）
3. 更新Web界面（如需要）
4. 添加测试用例
5. 更新文档

## 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| 开发语言 | Python 3.9+ | 最简开发、生态成熟 |
| 区块链底层 | 自研极简联盟链 | 无第三方链依赖 |
| 数据存储 | SQLite3 | 极简嵌入式数据库 |
| 通信协议 | HTTP/REST | 成熟通用、调试简单 |
| 哈希算法 | SHA256 | 通用安全哈希 |
| IPMI工具 | ipmitool | 系统原生、兼容性强 |
| Web框架 | Flask | 轻量级、易上手 |

## 路线图

### 一期（基础可用）✅

- [x] 最简区块链底层：区块结构、哈希校验、节点组网、基础共识
- [x] 本地客户端基础组网、心跳、账本同步能力
- [x] FRU硬件信息、CPU/内存基础指标采集与上链
- [x] 简单IPMI查询指令执行与日志上链

### 二期（功能完善）🔄

- [ ] GPU、磁盘IO、温度、功耗全维度指标采集
- [ ] IPMI设备启停、参数配置等管控指令全覆盖
- [ ] 权限校验、指令风控、异常重试机制
- [ ] 账本巡检、数据防篡改校验能力

### 三期（稳定商用）📋

- [ ] 网络断连容错、断点续传、数据缓存优化
- [ ] 多节点冗余、故障自动切换
- [ ] 后台溯源审计、告警、数据统计功能
- [ ] 性能优化，适配大规模机房、大批量设备管控

## 常见问题

### Q: 为什么只用Ubuntu？

A: 统一研发与运行环境标准，简化开发复杂度，聚焦业务能力。所有代码、测试、部署均基于Ubuntu。

### Q: 是否需要显卡？

A: 不需要。系统轻量化设计，普通CPU服务器即可运行。

### Q: 如何扩容新机房节点？

A: 1) 在新机房服务器上部署客户端；2) 更新所有节点的`peers`配置，加入新节点信息；3) 重启所有节点使配置生效。

### Q: 数据安全性如何保证？

A: 1) 私有封闭联盟链，仅白名单节点可接入；2) 所有数据上链存证，链式哈希防篡改；3) IPMI指令白名单机制，防止危险操作。

## 贡献指南

欢迎提交Issue和Pull Request！

1. Fork本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开Pull Request

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

## 联系方式

- 项目主页：https://github.com/yourusername/ChainMon
- 问题反馈：https://github.com/yourusername/ChainMon/issues
- 邮件联系：your-email@example.com

---

**⚠️ 免责声明**：本项目仅供学习和研究使用，生产环境部署前请充分测试。因使用本项目造成的任何损失，作者概不负责。
