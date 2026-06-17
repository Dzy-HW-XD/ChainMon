# Server/Agent State Machine and Block Payload

[English](node-state-machine.md) | [Simplified Chinese](node-state-machine.zh-CN.md)

ChainMon now uses a split runtime model:

- `monitor_client.py` is the public **server** runtime.
- `agent_client.py` is the outbound **agent** runtime.

VPN/private agents do not participate in P2P consensus and do not create blocks. They collect metrics and push them to the public server. The server owns the ledger and block creation.

## Server State Machine

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

| State | Meaning |
| --- | --- |
| `INIT` | Load server config, ledger, consensus, optional public P2P network, collector helpers, and agent registry. |
| `START_WEB_AND_OPTIONAL_P2P` | Start Web dashboard and agent APIs on `web.port`; start optional P2P server on `blockchain.listen_port`. |
| `WAIT_FOR_AGENT_DATA` | Server waits for outbound agents to register, heartbeat, or push metrics. |
| `RECEIVE_AGENT_PAYLOAD` | `/api/agent/metrics`, `/api/agent/heartbeat`, or task result endpoint receives data. |
| `PENDING_DATA` | The server converts incoming payloads into `ChainData` and appends them to `blockchain.pending_data`. |
| `CREATE_BLOCK` | Main loop packages pending records with `Blockchain.create_block()`. |
| `LOCAL_CONFIRM` | Single-server deployments confirm locally. Multi-public-server deployments may use the optional P2P voting path. |
| `APPEND_LEDGER` | Confirmed block is validated and persisted to `data/ledger/chain.json`. |

## Agent State Machine

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

| State | Meaning |
| --- | --- |
| `INIT` | Load `config/agent_config.yaml`, upstream server URL, optional token, collector settings, and local devices. |
| `REGISTER` | `POST /api/agent/register` to the public server. |
| `HEARTBEAT` | `POST /api/agent/heartbeat`; the server records agent liveness and can audit it on-chain. |
| `COLLECT_LOCAL_METRICS` | Collect local CPU, memory, disk, network, and optional IPMI device metrics. |
| `PUSH_METRICS` | `POST /api/agent/metrics`; server stores the records in `pending_data`. |
| `POLL_TASKS` | `GET /api/agent/tasks`; task execution is reserved for the next iteration. |
| `SLEEP` | Wait for `client.collect_interval`, then repeat. |

## What a Block Contains

The block model is defined in `blockchain/block.py`:

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

`data_list` contains `ChainData` records:

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

Data types:

| Value | Name | Used for |
| --- | --- | --- |
| `0` | `FRU_HARDWARE` | Optional hardware FRU records. |
| `1` | `PERFORMANCE` | Agent CPU, memory, disk, network, and sensor metrics. |
| `2` | `IPMI_OPERATION` | Task or IPMI operation result audit. |
| `3` | `NODE_HEARTBEAT` | Agent heartbeat audit. |
| `4` | `CONFIG_CHANGE` | Reserved config-change audit. |

## Block Hash Input

The current hash input is:

```text
block_height + prev_block_hash + timestamp + data_list_json + node_sign + nonce
```

`data_list` is protected by the block hash. `client_node_id` is stored as block metadata but is not currently part of the hash input. A future production hardening step should include `client_node_id` and real node signatures in the hash input.

## Operational APIs

Server APIs:

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

Optional public-server P2P APIs:

```http
GET  /health
GET  /p2p/chain/info
GET  /p2p/chain/sync
POST /p2p/block/propose
POST /p2p/block/vote
POST /p2p/heartbeat
```
