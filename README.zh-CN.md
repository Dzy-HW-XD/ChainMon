# ChainMon

> 公网审计链服务端 + VPN/内网出站 Agent 的服务器资源维护系统。

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/)

[English](README.md) | 简体中文

ChainMon 当前重塑为服务端和 Agent 分离部署：

- **Server 服务端**：部署在公网，提供 Web 看板、Agent 接入 API、审计账本和出块逻辑。
- **Agent 采集端**：部署在 VPN 或内网，只主动访问公网服务端，采集本机资源和可选 IPMI 设备指标。

公网服务端不需要主动访问 VPN 内机器；VPN 内 Agent 只需要能访问公网服务端即可。

## 架构

```text
公网
+--------------------------------------------------+
| ChainMon Server                                  |
| Web Dashboard + Agent API + JSON Audit Chain     |
| 示例：ali / 8.152.4.161                           |
+------------------------^-------------------------+
                         |
                         | Agent 主动 HTTP/HTTPS 上报
          +--------------+--------------+
          |                             |
+---------+----------+       +----------+---------+
| Agent: ali         |       | Agent: tc           |
| 本机 psutil/IPMI   |       | 本机 psutil/IPMI    |
| 主动推送指标       |       | 主动推送指标        |
+--------------------+       +---------------------+
```

## 功能

- 公网 Web 看板展示所有 Agent 上报的维护服务器。
- CPU 和内存趋势图使用浏览器原生 Canvas 绘制。
- 区块列表可以直接打开详情，查看完整区块头和 `data_list` 载荷。
- Agent 不开放 Web/P2P 端口。
- 服务端通过 `POST /api/agent/metrics` 接收指标并写入审计链。
- 服务端记录 Agent 心跳和任务结果审计。
- P2P 代码保留给未来多个公网 Server 组成联盟链使用，不再作为 VPN Agent 主路径。
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
|   |-- crypto.py
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
  node_name: "Ali Public Chain Server"
  region: "cn-hangzhou"
  mode: "server"

blockchain:
  listen_port: 8080
  consensus_threshold: 80
  ledger_path: "./data/ledger"

peers: []

agent:
  token: ""

web:
  port: 5000
  username: "admin"
  password: "admin123"
```

启动服务端：

```bash
python3 monitor_client.py --config config/node_config.yaml
```

访问：

```text
http://<公网服务端IP>:5000
```

## Agent 部署

复制 Agent 配置：

```bash
cp config/agent_config.example.yaml config/agent_config.yaml
vim config/agent_config.yaml
```

`tc` Agent 示例：

```yaml
node:
  node_id: "tc"
  node_name: "Tencent VPN Agent"
  region: "cn-guangzhou"
  mode: "agent"

agent:
  upstream: "http://8.152.4.161:5000"
  token: ""
  push_interval: 30
  task_poll_interval: 30

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

## Agent 接口

Agent 主动调用公网服务端：

```http
POST /api/agent/register
POST /api/agent/heartbeat
POST /api/agent/metrics
GET  /api/agent/tasks?node_id=tc
POST /api/agent/tasks/{task_id}/result
```

如果服务端配置了 `agent.token`，Agent 需要发送：

```http
X-Agent-Token: <token>
```

## 看板接口

```http
GET /api/status
GET /api/server/metrics
GET /api/server/metrics/history?limit=80
GET /api/blockchain/info
GET /api/blockchain/blocks?limit=20
GET /api/blockchain/block/{height}
```

可选公网服务端 P2P 接口：

```http
GET  /health
GET  /p2p/chain/info
GET  /p2p/chain/sync
POST /p2p/block/propose
POST /p2p/block/vote
POST /p2p/heartbeat
```

## 联盟链出块逻辑

ChainMon 使用轻量私有审计链。

1. Agent 将指标或任务结果推送到服务端。
2. 服务端将每条数据转换为 `ChainData`，放入 `blockchain.pending_data`。
3. 服务端主循环检查当前节点是否拥有出块权。
4. 单公网服务端部署时，服务端永远是出块节点。
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
| `0` | FRU 硬件信息 |
| `1` | 性能指标 |
| `2` | IPMI/任务操作结果 |
| `3` | Agent 心跳 |
| `4` | 配置变更 |

当前区块哈希覆盖 `block_height`、`prev_block_hash`、`timestamp`、`data_list`、`node_sign` 和 `nonce`。

## Best Practice / 最佳实践

- ChainMon Server 放在公网云服务器，前面建议加 HTTPS。
- VPN/内网机器只运行 Agent，保持出站访问模式。
- 不要把 BMC/IPMI 网络暴露到公网。
- 使用稳定的 `node.node_id`，例如 `tc`、`ali`、`vpn-a`。
- 生产环境启用 `agent.token`，后续建议升级为每 Agent 独立签名。
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
