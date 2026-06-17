# ChainMon

> 带私有审计链的轻量级服务器资源监控系统。

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Ubuntu%2020.04%2F22.04-orange.svg)](https://ubuntu.com/)

[English](README.md) | 简体中文

ChainMon 面向小规模、多机房或多云服务器场景。每个站点运行一个 `monitor_client.py` 进程，负责采集本机服务器资源指标、提供 Web 管理界面、参与私有审计链，并与其他节点同步记录。

项目刻意保持轻量：无代币、无挖矿、无公链依赖，也不强依赖重型数据库。链的作用是保存资源采样和运维操作的审计记录；主要产品体验是服务器维护看板。

## 功能特性

- 以服务器 CPU 和内存利用率为核心的资源维护看板。
- 使用浏览器原生 Canvas 绘制 CPU 和内存趋势图。
- 任意访问一个节点的 Web 后台，都可以看到已同步的所有维护服务器。
- 本机资源指标使用节点 ID 标识，例如 `tc` 或 `ali`，避免使用含义不清的 `localhost`。
- 使用私有审计链保存资源采样和 IPMI 操作记录。
- 确定性轮询出块，并按当前在线节点集合进行确认。
- 节点之间通过 P2P 接口同步账本。
- 可选 IPMI 指令执行，并带白名单保护。
- FRU 详情使用 AES-256-CBC 加密，前端使用浏览器原生 Web Crypto API 解密。
- 前端无外部 CDN 依赖。

## 架构

```text
+-------------------------------+
| Web Dashboard                  |
| Flask API + embedded frontend  |
| CPU/memory charts, devices,    |
| audit query, IPMI actions      |
+---------------+---------------+
                |
                | local process calls
+---------------v---------------+
| Monitor Client                 |
| psutil metrics, optional IPMI  |
| pending audit data pool        |
+---------------+---------------+
                |
                | packaged into blocks
+---------------v---------------+
| Private Audit Chain            |
| JSON ledger, SHA-256 hashes,   |
| round-robin leader selection   |
+---------------+---------------+
                |
                | HTTP P2P
+---------------v---------------+
| Peer Nodes                     |
| block proposal, vote, sync     |
+-------------------------------+
```

一个部署节点就是一个进程：

```bash
python3 monitor_client.py
```

该进程会同时启动：

- 资源采集器；
- P2P API 服务，默认端口 `8080`；
- Web 管理后台，默认端口 `5000`；
- 位于 `data/ledger/` 下的本地 JSON 账本。

## 项目结构

```text
ChainMon/
|-- blockchain/
|   |-- block.py          # Block 和 ChainData 数据模型
|   |-- chain.py          # JSON 账本管理和查询逻辑
|   |-- consensus.py      # 轮询共识和投票
|   `-- network.py        # 对等节点通信
|-- client/
|   |-- collector.py      # psutil 和 IPMI 数据采集
|   |-- config_loader.py  # YAML 配置加载
|   |-- crypto.py         # FRU 加密工具
|   `-- ipmi_executor.py  # 白名单 IPMI 指令执行
|-- config/
|   `-- config_template.yaml
|-- scripts/
|   |-- deploy.sh
|   `-- monitor.service
|-- tests/
|   |-- test_blockchain.py
|   `-- test_server_metrics.py
|-- monitor_client.py
|-- p2p_server.py
|-- web_server.py
`-- requirements.txt
```

## 环境要求

- Ubuntu 20.04 或 Ubuntu 22.04
- Python 3.9+
- 节点之间的 P2P 端口互通，默认 `8080`
- 运维人员可访问 Web 端口，默认 `5000`
- 可选：物理服务器 BMC/IPMI 采集和控制需要 `ipmitool`

安装系统依赖：

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ipmitool openssh-client curl
```

安装 Python 依赖：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 快速开始

创建节点配置：

```bash
cp config/config_template.yaml config/node_config.yaml
vim config/node_config.yaml
```

创建运行目录：

```bash
mkdir -p data/ledger data/cache logs
```

前台启动：

```bash
source venv/bin/activate
python3 monitor_client.py
```

后台启动：

```bash
source venv/bin/activate
nohup python3 monitor_client.py > logs/stdout.log 2>&1 &
```

打开 Web 后台：

```text
http://<server-ip>:5000
```

## 配置说明

运行配置文件位于：

```text
config/node_config.yaml
```

双节点中 `tc` 节点的最小配置示例：

```yaml
node:
  node_id: "tc"
  node_name: "Tencent Cloud TC"
  region: "cn-guangzhou"
  role: "client"

blockchain:
  listen_port: 8080
  block_interval: 30
  consensus_threshold: 80
  ledger_path: "./data/ledger"
  private_key_path: "./data/node_private.pem"

peers:
  - node_id: "ali"
    host: "<ali-public-ip>"
    port: 8080
    region: "cn-hangzhou"

client:
  scan_subnets: []
  ipmi_username: "admin"
  ipmi_password: "admin123"
  collect_interval: 30
  cache_path: "./data/cache"
  ipmi_whitelist:
    - "power"
    - "chassis"
    - "sensor"
    - "fru"
    - "sel"
    - "lan"
    - "user"

devices: []

web:
  port: 5000
  debug: false
  username: "admin"
  password: "admin123"
```

配置要点：

- `node.node_id` 必须在私有网络内唯一。
- 每个节点的 `peers` 只写其他节点，不写自己。
- `scan_subnets` 为空时，ChainMon 使用 `psutil` 监控节点服务器自身。
- `devices` 用于显式配置需要托管的 IPMI/BMC 设备。

## Web 后台

Web 后台由 `web_server.py` 提供，目前包含：

- 资源概览卡片；
- CPU 利用率趋势图；
- 内存利用率趋势图；
- 维护服务器/设备列表；
- 区块链审计视图；
- IPMI 指令面板；
- 审计日志查询。

资源趋势图使用浏览器原生 Canvas 绘制，不需要 Chart.js、ECharts 或外部 CDN。

## API

### 系统状态

```http
GET /api/status
```

返回节点状态、链高度、链有效性、对等节点状态、待上链数据数量和托管设备数量。

### 最新服务器指标

```http
GET /api/server/metrics
```

返回每台维护服务器的最新资源记录。

### 服务器指标历史

```http
GET /api/server/metrics/history?limit=80
```

按服务器分组返回 CPU 和内存历史点。

### 设备接口

```http
GET /api/devices
GET /api/device/{ip}/fru
```

`/api/device/{ip}/fru` 在可用时返回加密后的 FRU 信息。

### IPMI

```http
POST /api/ipmi/execute
Content-Type: application/json

{
  "ip": "10.0.1.100",
  "command": "power status"
}
```

指令会经过 `client.ipmi_whitelist` 白名单校验。

### 审计查询

```http
GET /api/query?data_type=1&device_ip=tc&limit=50
GET /api/audit/log
```

数据类型：

| 值 | 类型 |
| --- | --- |
| `0` | FRU 硬件信息 |
| `1` | 性能指标 |
| `2` | IPMI 操作 |
| `3` | 节点心跳 |
| `4` | 配置变更 |

### P2P

```http
GET  /health
GET  /p2p/chain/sync
POST /p2p/block/propose
POST /p2p/block/vote
POST /p2p/heartbeat
```

这些接口供节点内部通信使用。

## 账本与共识

ChainMon 将私有审计账本保存为 JSON 文件：

```text
data/ledger/chain.json
```

共识模型保持轻量：

- 使用确定性轮询选择出块节点；
- 区块提议后由当前活跃节点投票；
- 只有本机在线时，本机采集仍可确认上链；
- 节点恢复后，通过链同步拉取更长的有效链。

这条链不是加密货币系统，而是运维审计账本。

## 运维操作

### 检查服务

```bash
ps aux | grep '[p]ython3 monitor_client.py'
ss -tlnp | grep -E '5000|8080'
curl http://localhost:5000/api/status
curl http://localhost:5000/api/server/metrics
curl 'http://localhost:5000/api/server/metrics/history?limit=20'
```

### 重置本地账本

仅在明确需要丢弃本地审计历史时使用。

```bash
cd ~/ChainMon
pkill -f '[p]ython3 monitor_client.py' || true
stamp=$(date +%Y%m%d%H%M%S)
mkdir -p "backups/$stamp/data_ledger"
cp -a data/ledger/. "backups/$stamp/data_ledger/" 2>/dev/null || true
rm -f data/ledger/chain.json
setsid -f bash -lc 'source venv/bin/activate 2>/dev/null || true; exec python3 monitor_client.py >> logs/stdout.log 2>&1 < /dev/null'
```

如果需要多节点干净重置，应先停止所有节点，备份并删除每个节点的 `data/ledger/chain.json`，再统一启动。

## 最佳实践

- 使用稳定且有意义的 `node.node_id`，例如机房编号、云厂商编号或站点编号。生产环境不要使用 `localhost` 作为服务器身份。
- 保持所有节点的 `peers` 配置一致，并且不要把本节点写进自己的 `peers`。
- 所有节点应启用 NTP 或其他时间同步服务，避免趋势图时间轴和审计记录难以阅读。
- 清理、迁移或重建节点前先备份 `data/ledger/`，把账本视为审计证据。
- 小规格云服务器建议保持保守采集频率，CPU/内存趋势使用 30 秒采集间隔通常足够。
- `8080` 端口只开放给可信节点，`5000` 端口只开放给可信运维人员，最好放在 VPN 或反向代理后面。
- 在实验环境之外使用前，应轮换 Web 密码和 IPMI 凭据。
- 保持 `ipmi_whitelist` 尽量窄；如果没有认证和授权机制，不要加入高风险破坏性命令。
- 长期部署建议使用 systemd 或其他进程守护工具，不建议依赖临时 shell 会话。
- 每次修改配置后，使用 `/api/status`、`/api/server/metrics`、`/api/server/metrics/history` 和 `/health` 验证部署状态。

## 测试

运行本地测试：

```bash
python tests/test_blockchain.py
python tests/test_server_metrics.py
python -m py_compile monitor_client.py web_server.py p2p_server.py blockchain/block.py blockchain/chain.py blockchain/consensus.py blockchain/network.py client/collector.py client/config_loader.py client/crypto.py client/ipmi_executor.py
```

对已部署节点运行 API 冒烟测试：

```bash
curl http://<node-ip>:5000/api/status
curl http://<node-ip>:5000/api/server/metrics
curl 'http://<node-ip>:5000/api/server/metrics/history?limit=20'
curl http://<node-ip>:8080/health
```

## 安全说明

- 不要提交 `token.txt`、SSH 凭据、私钥、生产配置等运行时敏感信息。
- `.gitignore` 已忽略 `config/node_config.yaml`、`data/`、`logs/`、`*.pem` 和 `*.key`。
- 使用防火墙或安全组限制 Web 和 P2P 端口暴露范围。
- IPMI 指令虽然经过白名单校验，但生产环境仍应增加认证、授权和操作审计。
- 当前 Web 鉴权模型较简单，商业化或生产使用前应增强权限控制。

## 路线图

- 认证和基于角色的访问控制。
- CPU、内存、磁盘和节点状态告警。
- 更稳健的节点发现和断线重连。
- 历史数据保留策略和账本压缩。
- 可选数据库后端，用于提升查询性能。
- 更完整的硬件遥测，包括磁盘 IO、温度、风扇、功耗和 GPU 指标。

## 许可证

本项目使用 MIT License。详见 [LICENSE](LICENSE)。
