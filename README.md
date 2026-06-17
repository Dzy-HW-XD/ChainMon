# ChainMon

> Public audit-chain server plus outbound VPN/private-network agents for server resource maintenance.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/)

English | [简体中文](README.zh-CN.md)

ChainMon is now organized as a split deployment:

- **Server**: a public ChainMon node that exposes the Web dashboard, receives agent data, stores the audit ledger, and creates blocks.
- **Agent**: an outbound-only collector running inside a VPN/private network. It collects local server resources and optional IPMI device metrics, then pushes them to the public server.

The server does not need inbound access to VPN/private machines. Agents only need outbound HTTP/HTTPS access to the public server.

## Architecture

```text
Public Internet
+--------------------------------------------------+
| ChainMon Server                                  |
| Web Dashboard + Agent API + JSON Audit Chain     |
| Example: ali / 8.152.4.161                       |
+------------------------^-------------------------+
                         |
                         | outbound HTTP/HTTPS
          +--------------+--------------+
          |                             |
+---------+----------+       +----------+---------+
| Agent: ali         |       | Agent: tc           |
| local psutil/IPMI  |       | local psutil/IPMI   |
| push metrics       |       | push metrics        |
+--------------------+       +---------------------+
```

## Features

- Public dashboard shows all maintained servers reported by agents.
- CPU and memory trend charts rendered with browser-native Canvas.
- Block list entries can be opened to inspect the full block header and `data_list` payload.
- Agents do not open Web or P2P ports.
- Server receives `POST /api/agent/metrics` and writes records to the audit chain.
- Server records agent heartbeat and task-result audit records.
- Optional P2P code is retained only for future multi-server public consortium deployment.
- No public-chain, token, mining, or heavyweight database dependency.

## Project Structure

```text
ChainMon/
|-- agent_client.py              # Outbound VPN/private-network agent
|-- monitor_client.py            # Public ChainMon server runtime
|-- web_server.py                # Web dashboard and agent APIs
|-- p2p_server.py                # Optional public-server P2P endpoints
|-- blockchain/
|   |-- block.py                 # Block and ChainData models
|   |-- chain.py                 # JSON ledger management
|   |-- consensus.py             # Lightweight block confirmation
|   `-- network.py               # Optional public P2P helpers
|-- client/
|   |-- collector.py             # psutil and IPMI collection
|   |-- config_loader.py
|   |-- crypto.py
|   `-- ipmi_executor.py
|-- config/
|   |-- config_template.yaml     # Server config template
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

## Server Deployment

Copy the server config:

```bash
cp config/config_template.yaml config/node_config.yaml
vim config/node_config.yaml
```

Minimal public server config:

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

Start the server:

```bash
python3 monitor_client.py --config config/node_config.yaml
```

Open:

```text
http://<public-server-ip>:5000
```

## Agent Deployment

Copy the agent config:

```bash
cp config/agent_config.example.yaml config/agent_config.yaml
vim config/agent_config.yaml
```

Example for the `tc` agent:

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

Start the agent:

```bash
python3 agent_client.py --config config/agent_config.yaml
```

Run once for validation:

```bash
python3 agent_client.py --config config/agent_config.yaml --once
```

## Agent APIs

Agents call these public server APIs:

```http
POST /api/agent/register
POST /api/agent/heartbeat
POST /api/agent/metrics
GET  /api/agent/tasks?node_id=tc
POST /api/agent/tasks/{task_id}/result
```

If `agent.token` is configured on the server, agents must send:

```http
X-Agent-Token: <token>
```

## Dashboard APIs

```http
GET /api/status
GET /api/server/metrics
GET /api/server/metrics/history?limit=80
GET /api/blockchain/info
GET /api/blockchain/blocks?limit=20
GET /api/blockchain/block/{height}
```

Optional public-server P2P endpoints:

```http
GET  /health
GET  /p2p/chain/info
GET  /p2p/chain/sync
POST /p2p/block/propose
POST /p2p/block/vote
POST /p2p/heartbeat
```

## Block Creation Logic

ChainMon uses a lightweight private audit chain.

1. Agents push metrics or task results to the server.
2. The server converts each payload into `ChainData` and appends it to `blockchain.pending_data`.
3. On each loop, the server checks whether it is the current block creator.
4. In the common single-server deployment, the server is always the creator.
5. The server packages all pending records into one block with `Blockchain.create_block()`.
6. The block is proposed to the local consensus module.
7. The server votes for its own block.
8. With one active voting node, approval reaches the configured threshold immediately.
9. The block is validated and appended to `data/ledger/chain.json`.

Block fields:

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

`data_list` carries `ChainData` records:

| Type | Meaning |
| --- | --- |
| `0` | FRU hardware data |
| `1` | Performance metrics |
| `2` | IPMI/task operation result |
| `3` | Agent heartbeat |
| `4` | Config change |

The hash currently covers `block_height`, `prev_block_hash`, `timestamp`, `data_list`, `node_sign`, and `nonce`.

## Best Practices

- Put the ChainMon server on a public cloud host with HTTPS in front of it.
- Keep VPN/private machines as outbound-only agents.
- Do not expose BMC/IPMI networks to the public Internet.
- Use stable `node.node_id` values such as `tc`, `ali`, `vpn-a`.
- Enable `agent.token` or upgrade to per-agent signatures before production use.
- Keep IPMI credentials only on the agent side.
- Back up `data/ledger/chain.json`.
- Use systemd or another supervisor for both server and agent processes.

## Tests

```bash
python tests/test_blockchain.py
python tests/test_server_metrics.py
python tests/test_network.py
python tests/test_agent_api.py
python -m py_compile monitor_client.py agent_client.py web_server.py p2p_server.py blockchain/block.py blockchain/chain.py blockchain/consensus.py blockchain/network.py client/collector.py client/config_loader.py client/crypto.py client/ipmi_executor.py
```
