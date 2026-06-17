# ChainMon

> Lightweight server-resource monitoring with an auditable private chain.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Ubuntu%2020.04%2F22.04-orange.svg)](https://ubuntu.com/)

English | [Chinese](README.zh-CN.md)

ChainMon is a lightweight monitoring system for small multi-site server fleets. Each site runs one `monitor_client.py` process that collects local server resource metrics, exposes a Web dashboard, participates in a private audit chain, and synchronizes records with peer nodes.

The project is intentionally simple: no token, no mining, no public-chain dependency, and no heavyweight database requirement. The chain is used as an audit ledger for resource samples and operations; the primary product experience is the server maintenance dashboard.

## Features

- Server resource dashboard focused on CPU and memory utilization.
- CPU and memory trend charts rendered with native browser Canvas.
- Any node's Web UI can display all synchronized managed servers.
- Local server metrics are identified by node ID, such as `tc` or `ali`, instead of ambiguous `localhost`.
- Private chain audit ledger for resource samples and IPMI operations.
- Deterministic round-robin block creation with online-node-aware confirmation.
- P2P ledger synchronization between configured nodes.
- Optional IPMI command execution with whitelist protection.
- FRU detail encryption using AES-256-CBC and browser-native Web Crypto APIs.
- Zero external frontend CDN dependency.

## Architecture

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

One deployment node is one process:

```bash
python3 monitor_client.py
```

That single process starts:

- the monitor collector;
- the P2P API server on the configured chain port, default `8080`;
- the Web dashboard on the configured Web port, default `5000`;
- the local JSON ledger under `data/ledger/`.

## Project Structure

```text
ChainMon/
|-- blockchain/
|   |-- block.py          # Block and ChainData models
|   |-- chain.py          # JSON ledger management and query logic
|   |-- consensus.py      # Round-robin consensus and voting
|   `-- network.py        # Peer node communication
|-- client/
|   |-- collector.py      # psutil and IPMI data collection
|   |-- config_loader.py  # YAML config loading
|   |-- crypto.py         # FRU encryption helpers
|   `-- ipmi_executor.py  # Whitelisted IPMI command execution
|-- config/
|   `-- config_template.yaml
|-- docs/
|   |-- node-state-machine.md
|   `-- node-state-machine.zh-CN.md
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

## Requirements

- Ubuntu 20.04 or Ubuntu 22.04
- Python 3.9+
- Network access between peer nodes on the P2P port, default `8080`
- Operator access to the Web port, default `5000`
- Optional: `ipmitool` for physical server BMC/IPMI collection and control

Install system packages:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ipmitool openssh-client curl
```

Install Python packages:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Quick Start

Create a node config:

```bash
cp config/config_template.yaml config/node_config.yaml
vim config/node_config.yaml
```

Create runtime directories:

```bash
mkdir -p data/ledger data/cache logs
```

Start the service in the foreground:

```bash
source venv/bin/activate
python3 monitor_client.py
```

Start in the background:

```bash
source venv/bin/activate
nohup python3 monitor_client.py > logs/stdout.log 2>&1 &
```

Open the dashboard:

```text
http://<server-ip>:5000
```

## Configuration

The runtime config lives at:

```text
config/node_config.yaml
```

Minimal two-node example for node `tc`:

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

Notes:

- `node.node_id` must be unique across the private network.
- Each node's `peers` should list the other nodes, not itself.
- Empty `scan_subnets` means ChainMon monitors the node server itself through `psutil`.
- Explicit `devices` entries are for managed IPMI/BMC devices.

## Development Notes

- [Node state machine and block payload](docs/node-state-machine.md) explains the current implicit node lifecycle, peer online/offline view, consensus proposal states, and the exact fields carried by each block.

## Web Dashboard

The dashboard is served by `web_server.py` and currently includes:

- resource summary cards;
- CPU utilization trend chart;
- memory utilization trend chart;
- managed server/device table;
- blockchain audit view;
- IPMI command panel;
- audit log query.

The resource charts are drawn with browser-native Canvas and do not require Chart.js, ECharts, or any external CDN.

## API

### System Status

```http
GET /api/status
```

Returns node status, chain height, chain validity, peer status, pending data count, and managed device count.

### Latest Server Metrics

```http
GET /api/server/metrics
```

Returns the latest resource record for each managed server.

### Server Metric History

```http
GET /api/server/metrics/history?limit=80
```

Returns CPU and memory history grouped by server.

### Devices

```http
GET /api/devices
GET /api/device/{ip}/fru
```

`/api/device/{ip}/fru` returns encrypted FRU information when available.

### IPMI

```http
POST /api/ipmi/execute
Content-Type: application/json

{
  "ip": "10.0.1.100",
  "command": "power status"
}
```

Commands are checked against `client.ipmi_whitelist`.

### Audit Query

```http
GET /api/query?data_type=1&device_ip=tc&limit=50
GET /api/audit/log
```

Data types:

| Value | Type |
| --- | --- |
| `0` | FRU hardware |
| `1` | Performance metrics |
| `2` | IPMI operation |
| `3` | Node heartbeat |
| `4` | Config change |

### P2P

```http
GET  /health
GET  /p2p/chain/sync
POST /p2p/block/propose
POST /p2p/block/vote
POST /p2p/heartbeat
```

These endpoints are used by nodes internally.

## Ledger and Consensus

ChainMon stores the private audit ledger as JSON under `data/ledger/chain.json`.

The consensus model is intentionally lightweight:

- block leaders are selected by deterministic round-robin;
- each proposed block receives votes from currently active nodes;
- if only the local node is active, local collection can still be confirmed;
- when peers recover, chain synchronization pulls the longer valid chain.

The chain is not a cryptocurrency system. It is an audit ledger for operational records.

## Operational Tasks

### Check Service

```bash
ps aux | grep '[p]ython3 monitor_client.py'
ss -tlnp | grep -E '5000|8080'
curl http://localhost:5000/api/status
curl http://localhost:5000/api/server/metrics
curl 'http://localhost:5000/api/server/metrics/history?limit=20'
```

### Reset Local Ledger

Use this only when you intentionally want to discard the local audit history.

```bash
cd ~/ChainMon
pkill -f '[p]ython3 monitor_client.py' || true
stamp=$(date +%Y%m%d%H%M%S)
mkdir -p "backups/$stamp/data_ledger"
cp -a data/ledger/. "backups/$stamp/data_ledger/" 2>/dev/null || true
rm -f data/ledger/chain.json
setsid -f bash -lc 'source venv/bin/activate 2>/dev/null || true; exec python3 monitor_client.py >> logs/stdout.log 2>&1 < /dev/null'
```

For a multi-node clean reset, stop all nodes, back up and remove `data/ledger/chain.json` on every node, then start all nodes again.

## Best Practices

- Use stable, meaningful `node.node_id` values, such as a site code or datacenter code. Do not use `localhost` as a managed server identity in production.
- Keep every node's `peers` list consistent and do not include the local node in its own peer list.
- Run all nodes with NTP or another time synchronization service so chart timelines and audit records remain readable.
- Back up `data/ledger/` before clearing or migrating a node. Treat the ledger as audit evidence.
- Keep `collect_interval` conservative for small cloud instances. A 30 second interval is a reasonable default for CPU and memory trends.
- Expose port `8080` only to trusted peer nodes. Expose port `5000` only to trusted operators or behind a VPN/reverse proxy.
- Rotate Web passwords and IPMI credentials before using the project outside a lab environment.
- Keep `ipmi_whitelist` narrow. Avoid adding destructive commands unless operator authentication and authorization are in place.
- Use systemd or another process supervisor for long-running deployments instead of ad hoc shell sessions.
- Validate a deployment with `/api/status`, `/api/server/metrics`, `/api/server/metrics/history`, and `/health` after every config change.

## Testing

Run local tests:

```bash
python tests/test_blockchain.py
python tests/test_server_metrics.py
python -m py_compile monitor_client.py web_server.py p2p_server.py blockchain/block.py blockchain/chain.py blockchain/consensus.py blockchain/network.py client/collector.py client/config_loader.py client/crypto.py client/ipmi_executor.py
```

Run a public API smoke test against deployed nodes:

```bash
curl http://<node-ip>:5000/api/status
curl http://<node-ip>:5000/api/server/metrics
curl 'http://<node-ip>:5000/api/server/metrics/history?limit=20'
curl http://<node-ip>:8080/health
```

## Security Notes

- Do not commit runtime secrets such as `token.txt`, SSH credentials, private keys, or production configs.
- `config/node_config.yaml`, `data/`, `logs/`, `*.pem`, and `*.key` are ignored by `.gitignore`.
- Use firewall rules or security groups to limit Web and P2P exposure.
- IPMI commands are whitelist-checked, but production deployments should still add authentication and operator authorization before allowing destructive actions.
- The current Web authentication model is intentionally simple and should be strengthened before commercial production use.

## Roadmap

- Authentication and role-based access control.
- Alerting for CPU, memory, disk, and peer status.
- More robust peer discovery and reconnect behavior.
- Historical retention policies and ledger compaction.
- Optional database backend for query acceleration.
- Broader hardware telemetry, including disk IO, temperature, fan, power, and GPU metrics.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
