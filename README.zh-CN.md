# ChainMon

> 公网审计链服务端 + 出站 Agent 的服务器资源维护系统。

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/)

[English](README.md) | 简体中文

ChainMon 当前采用服务端和 Agent 分离部署：

- **Server 服务端**：部署在公网或统一入口网络，提供 Web 看板、Agent 接入 API、JSON 审计账本和出块逻辑。
- **Agent 采集端**：部署在公网、VPN 或内网机器上，只主动访问服务端，采集本机资源和可选 IPMI/BMC 设备指标，然后推送到服务端。

服务端不需要主动访问 VPN/内网机器。Agent 只需要具备访问服务端 HTTP/HTTPS 地址的出站能力。

## 架构

```text
公网 / 统一入口网络
+--------------------------------------------------+
| ChainMon Server                                  |
| Web Dashboard + Agent API + JSON Audit Chain     |
| 示例入口：https://chainmon.example.com            |
+------------------------^-------------------------+
                         |
                         | Agent 主动 HTTPS 上报
          +--------------+--------------+
          |                             |
+---------+----------+       +----------+---------+
| Agent: ali         |       | Agent: tc           |
| 本机 psutil/资产   |       | 本机 psutil/资产    |
| 主动推送指标       |       | 主动推送指标        |
+--------------------+       +---------------------+
```

## 功能

- 公网 Web 看板展示所有 Agent 上报的维护服务器。
- CPU 利用率和内存利用率使用浏览器原生 Canvas 绘制折线图。
- Device 详情展示 Agent 在 OS 下采集的基础硬件资产，例如 CPU 型号、内存大小/模块、硬盘厂商/型号/容量。
- 区块列表可以直接打开详情，查看完整区块头和 `data_list` 载荷。
- Dashboard 的 Recent Blocks 固定展示最近 50 个区块；Blockchain 页面展示全部区块，每页 50 个。
- Agent 不开放 Web/P2P 端口。
- 服务端通过 `POST /api/agent/metrics` 接收指标并写入审计链。
- 服务端记录 Agent 心跳和任务结果审计。
- P2P 代码保留给未来多个公网 Server 组成联盟链使用。
- 无公链、无代币、无挖矿、无重型数据库依赖。

## 项目结构

```text
ChainMon/
|-- agent_client.py              # 出站 Agent
|-- monitor_client.py            # 公网服务端运行入口
|-- web_server.py                # Web 看板和 Agent API
|-- p2p_server.py                # 可选公网服务端 P2P 接口
|-- blockchain/
|   |-- block.py                 # Block 和 ChainData 模型
|   |-- chain.py                 # JSON 账本管理
|   |-- consensus.py             # 轻量确认逻辑
|   `-- network.py               # 可选公网 P2P 工具
|-- client/
|   |-- collector.py             # psutil 和 IPMI 采集
|   |-- config_loader.py
|   |-- crypto.py                # 硬件资产 AES 加密辅助
|   `-- ipmi_executor.py
|-- config/
|   |-- config_template.yaml     # 服务端配置模板
|   `-- agent_config.example.yaml
|-- docs/
|   |-- node-state-machine.md
|   `-- node-state-machine.zh-CN.md
`-- tests/
    |-- test_agent_api.py
    |-- test_blockchain.py
    |-- test_network.py
    `-- test_server_metrics.py
```

## 服务端部署

复制服务端配置：

```bash
cp config/config_template.yaml config/node_config.yaml
vim config/node_config.yaml
```

最小服务端配置：

```yaml
node:
  node_id: "server-ali"
  node_name: "Public ChainMon Server"
  region: "cn-hangzhou"
  mode: "server"

blockchain:
  listen_port: 8080
  consensus_threshold: 80
  ledger_path: "./data/ledger"

peers: []

agent:
  token: "replace-with-a-long-random-agent-token"

web:
  port: 5000
  username: "admin"
  password: "replace-with-a-long-random-web-password"
```

启动服务端：

```bash
python3 monitor_client.py --config config/node_config.yaml
```

访问入口：

```text
https://chainmon.example.com
```

## Agent 部署

复制 Agent 配置：

```bash
cp config/agent_config.example.yaml config/agent_config.yaml
vim config/agent_config.yaml
```

Agent 配置示例：

```yaml
node:
  node_id: "tc"
  node_name: "Tencent VPN Agent"
  region: "cn-guangzhou"
  mode: "agent"

agent:
  upstream: "https://chainmon.example.com"
  token: "replace-with-the-server-agent-token"
  push_interval: 30
  task_poll_interval: 30
  hardware_push_interval: 3600

client:
  collect_interval: 30

devices: []
```

启动 Agent：

```bash
python3 agent_client.py --config config/agent_config.yaml
```

单次验证：

```bash
python3 agent_client.py --config config/agent_config.yaml --once
```

## Key 配置说明

ChainMon 当前有两类密钥：

- `agent.token`：Agent 调用服务端时使用的共享令牌，通过 `X-Agent-Token` 请求头发送。
- `web.password`：Web 管理密码，同时也是硬件资产 AES 密钥的派生来源。服务端使用 `SHA-256(web.password)` 得到 AES key。

生产环境必须把默认值替换成长随机值，并且不要提交到 Git。建议在服务端前面加 HTTPS。浏览器侧硬件资产解密依赖 Web Crypto API，这个 API 只在 HTTPS 或 localhost 等安全上下文可用。如果使用普通 HTTP 访问公网地址，Web 会自动回退为服务端解密。

## Agent 接口

Agent 主动调用服务端：

```http
POST /api/agent/register
POST /api/agent/heartbeat
POST /api/agent/metrics
GET  /api/agent/tasks?node_id=tc
POST /api/agent/tasks/{task_id}/result
```

## 看板接口

```http
GET /api/status
GET /api/server/metrics
GET /api/server/metrics/history?limit=80
GET /api/blockchain/info
GET /api/blockchain/blocks?limit=20
GET /api/blockchain/block/{height}
GET /api/device/{id}/fru          # 兼容路径，返回加密硬件资产详情
GET /api/device/{id}/fru?plain=1  # 服务端解密后的硬件资产详情
```

## 联盟链出块逻辑

ChainMon 使用轻量私有审计链。

1. Agent 将指标、心跳或任务结果推送到服务端。
2. 服务端把每条数据转换为 `ChainData`，放入 `blockchain.pending_data`。
3. 服务端主循环检查当前节点是否拥有出块权。
4. 单公网服务端部署时，服务端始终是出块节点。
5. 服务端调用 `Blockchain.create_block()`，把 pending 数据打包成新区块。
6. 新区块进入本地共识提议。
7. 服务端给自己的区块投同意票。
8. 单活跃投票节点下，同意率立即达到阈值。
9. 区块通过校验后写入 `data/ledger/chain.json`。

区块字段：

```json
{
  "block_height": 12,
  "prev_block_hash": "previous block hash",
  "timestamp": 1781700000,
  "client_node_id": "server-ali",
  "data_list": [],
  "current_hash": "current block hash",
  "node_sign": "",
  "nonce": 0
}
```

`data_list` 中是 `ChainData`：

| 类型 | 含义 |
| --- | --- |
| `0` | OS 采集的硬件资产信息 |
| `1` | 性能指标 |
| `2` | IPMI/任务操作结果 |
| `3` | Agent 心跳 |
| `4` | 配置变更 |

当前区块哈希覆盖 `block_height`、`prev_block_hash`、`timestamp`、`data_list`、`node_sign` 和 `nonce`。

## Best Practice / 最佳实践

- ChainMon Server 前面建议统一加 HTTPS。
- VPN/内网机器只运行 Agent，保持出站访问模式。
- 不要把 BMC/IPMI 网络暴露到公网。
- 不要把真实公网 IP、token、密码、BMC 凭据提交到 Git。
- 使用稳定的 `node.node_id`，例如 `tc`、`ali`、`vpn-a`。
- 生产环境启用 `agent.token`，后续建议升级为每 Agent 独立凭据或签名。
- IPMI 密码只保存在 Agent 本地。
- 定期备份 `data/ledger/chain.json`。
- 服务端和 Agent 都建议使用 systemd 或 supervisor 托管。

## 测试

```bash
python tests/test_blockchain.py
python tests/test_server_metrics.py
python tests/test_network.py
python tests/test_agent_api.py
python -m py_compile monitor_client.py agent_client.py web_server.py p2p_server.py blockchain/block.py blockchain/chain.py blockchain/consensus.py blockchain/network.py client/collector.py client/config_loader.py client/crypto.py client/ipmi_executor.py
```
