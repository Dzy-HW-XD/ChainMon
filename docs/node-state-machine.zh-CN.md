# 服务端/Agent 状态机与区块载荷

[English](node-state-machine.md) | 简体中文

ChainMon 当前采用分离运行模型：

- `monitor_client.py` 是公网 **Server 服务端**。
- `agent_client.py` 是出站 **Agent 采集端**。

VPN/内网 Agent 不参与 P2P 共识，也不创建区块。Agent 只负责采集并主动上报；服务端负责账本和出块。

## 服务端状态机

```text
INIT
  -> START_WEB_AND_OPTIONAL_P2P
  -> WAIT_FOR_AGENT_DATA
  -> RECEIVE_AGENT_PAYLOAD
  -> PENDING_DATA
  -> CREATE_BLOCK
  -> LOCAL_CONFIRM
  -> APPEND_LEDGER
  -> WAIT_FOR_AGENT_DATA
```

| 状态 | 含义 |
| --- | --- |
| `INIT` | 加载服务端配置、账本、共识、可选公网 P2P 网络、采集辅助模块和 Agent 注册表。 |
| `START_WEB_AND_OPTIONAL_P2P` | 启动 Web 看板和 Agent API；可选启动 P2P 服务。 |
| `WAIT_FOR_AGENT_DATA` | 等待 Agent 注册、心跳或推送指标。 |
| `RECEIVE_AGENT_PAYLOAD` | `/api/agent/metrics`、`/api/agent/heartbeat` 或任务结果接口收到数据。 |
| `PENDING_DATA` | 服务端把收到的数据转换为 `ChainData`，放入 `blockchain.pending_data`。 |
| `CREATE_BLOCK` | 主循环调用 `Blockchain.create_block()` 打包 pending 数据。 |
| `LOCAL_CONFIRM` | 单服务端部署时本地确认；多个公网服务端时可走保留的 P2P 投票路径。 |
| `APPEND_LEDGER` | 区块校验通过后写入 `data/ledger/chain.json`。 |

## Agent 状态机

```text
INIT
  -> REGISTER
  -> HEARTBEAT
  -> COLLECT_LOCAL_METRICS
  -> PUSH_METRICS
  -> POLL_TASKS
  -> SLEEP
  -> HEARTBEAT
```

| 状态 | 含义 |
| --- | --- |
| `INIT` | 加载 `config/agent_config.yaml`、公网服务端地址、可选 token、采集配置和本地设备。 |
| `REGISTER` | 调用 `POST /api/agent/register` 注册到公网服务端。 |
| `HEARTBEAT` | 调用 `POST /api/agent/heartbeat`，服务端记录 Agent 在线状态并可审计上链。 |
| `COLLECT_LOCAL_METRICS` | 采集本机 CPU、内存、磁盘、网络和可选 IPMI 设备指标。 |
| `PUSH_METRICS` | 调用 `POST /api/agent/metrics`，服务端把记录写入 pending 数据池。 |
| `POLL_TASKS` | 调用 `GET /api/agent/tasks`；任务执行留给下一轮迭代。 |
| `SLEEP` | 等待 `client.collect_interval` 后重复。 |

## 区块里带什么

区块模型位于 `blockchain/block.py`：

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

```json
{
  "data_type": 1,
  "device_ip": "tc",
  "content": "{\"cpu_percent\": 1.0, \"memory\": {\"percent\": 48.1}}",
  "operate_user": "agent",
  "timestamp": 1781700000,
  "data_id": ""
}
```

数据类型：

| 值 | 名称 | 用途 |
| --- | --- | --- |
| `0` | `FRU_HARDWARE` | 可选硬件 FRU 记录。 |
| `1` | `PERFORMANCE` | Agent 上报的 CPU、内存、磁盘、网络和传感器指标。 |
| `2` | `IPMI_OPERATION` | 任务或 IPMI 操作结果审计。 |
| `3` | `NODE_HEARTBEAT` | Agent 心跳审计。 |
| `4` | `CONFIG_CHANGE` | 预留配置变更审计。 |

## 区块哈希输入

当前哈希输入为：

```text
block_height + prev_block_hash + timestamp + data_list_json + node_sign + nonce
```

`data_list` 会被区块哈希保护。`client_node_id` 当前作为区块元数据保存，但尚未参与哈希计算。生产强化时建议把 `client_node_id` 和真实节点签名纳入哈希输入。

## 运维接口

服务端接口：

```http
GET  /api/status
GET  /api/server/metrics
GET  /api/server/metrics/history?limit=80
GET  /api/blockchain/info
GET  /api/blockchain/blocks?limit=20
POST /api/agent/register
POST /api/agent/heartbeat
POST /api/agent/metrics
GET  /api/agent/tasks?node_id=tc
POST /api/agent/tasks/{task_id}/result
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
