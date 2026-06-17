# Node State Machine and Block Payload

[English](node-state-machine.md) | [Simplified Chinese](node-state-machine.zh-CN.md)

This document explains the runtime state model used by ChainMon nodes and the exact information carried by blocks. The current implementation does not expose a single `NodeState` enum. Instead, node status is composed from the monitor client loop, peer heartbeat status, consensus block status, and local ledger status.

## Runtime Components

A ChainMon node is one `monitor_client.py` process. It owns these runtime components:

- `Blockchain`: local JSON ledger and `pending_data` pool.
- `SimpleConsensus`: leader selection, block proposal cache, votes, and block confirmation status.
- `P2PNetwork`: configured peer list and heartbeat-derived online/offline status.
- `HardwareCollector`: local `psutil` metrics and optional IPMI/SDR/FRU collection.
- Flask Web server: dashboard and HTTP APIs.
- Flask P2P server: block proposal, vote, chain sync, peer query, and health endpoints.

## Node Lifecycle

```text
INIT
  |
  v
BOOTSTRAP_SERVICES
  |
  v
INITIAL_CHAIN_SYNC
  |
  v
COLLECTING
  |
  v
REFRESH_ACTIVE_NODES
  |
  +-------------------------+
  |                         |
  v                         v
FOLLOWER_WAIT          LEADER_READY
  |                         |
  |                         v
  |                    BLOCK_PROPOSED
  |                         |
  |                         v
  |                    WAITING_VOTES
  |                         |
  |              +----------+----------+
  |              |                     |
  |              v                     v
  |          CONFIRMED              REJECTED
  |              |                     |
  +--------------+---------------------+
                 |
                 v
             PERIODIC_SYNC
                 |
                 v
             COLLECTING
```

## State Descriptions

| State | Owner | Meaning | Main code path |
| --- | --- | --- | --- |
| `INIT` | process | Load config, create blockchain, consensus, network, collector, IPMI executor. | `MonitorClient.__init__` |
| `BOOTSTRAP_SERVICES` | process | Start P2P server, Web server, and peer heartbeat thread. | `_start_background_threads()` |
| `INITIAL_CHAIN_SYNC` | ledger | Wait briefly for P2P readiness, then try to pull a longer valid chain from peers. | `start()`, `_sync_chain_from_peers()` |
| `COLLECTING` | collector | Collect configured managed devices and local server metrics, then append `ChainData` into `pending_data`. | `_collect_data_cycle()` |
| `REFRESH_ACTIVE_NODES` | consensus | Build current voting set from self plus heartbeat-online peers. | `_update_active_consensus_nodes()` |
| `FOLLOWER_WAIT` | consensus | Current node is not the leader for the next block height. It keeps collecting data and syncing. | `is_my_turn()` returns `False` |
| `LEADER_READY` | consensus | Current node is leader and has `pending_data` to package. | `is_my_turn()` returns `True` |
| `BLOCK_PROPOSED` | consensus | Leader creates a block from `pending_data`, caches it in `pending_blocks`, broadcasts proposal, and votes for itself. | `_create_and_propose_block()` |
| `WAITING_VOTES` | consensus | Block remains in `BlockStatus.PENDING` until enough online voting nodes approve. | `vote_block()`, `_check_consensus()` |
| `CONFIRMED` | ledger | Approval rate reaches `consensus_threshold`; block is validated and appended to local ledger. | `get_confirmed_block()`, `add_block()` |
| `REJECTED` | consensus | Rejection rate reaches threshold or the pending proposal later expires from cache. | `_check_consensus()`, `cleanup_old_pending()` |
| `PERIODIC_SYNC` | ledger | Pull the longest valid chain from online peers every `sync_interval` seconds. | `_sync_chain_from_peers()` |
| `STOPPING` | process | Stop loop and persist the local ledger. | `stop()` |

## Peer Status

Peer status is maintained by `P2PNetwork`.

- A peer starts as offline in local memory.
- The heartbeat thread periodically calls each configured peer.
- Successful heartbeat marks the peer `is_online = true` and updates `last_heartbeat`.
- Failed heartbeat marks the peer offline.
- Consensus uses only `self + online peers` as the voting set through `set_active_nodes()`.

This is why a two-node deployment can still produce local blocks when the peer is temporarily unreachable: the voting set is reduced to the online view instead of waiting forever for an offline peer.

## Leader Selection

Leader selection is deterministic for all nodes that have the same active node view and chain height.

```text
voting_nodes = sorted(self_node_id + online_peer_ids)
leader_index = len(chain) % len(voting_nodes)
leader = voting_nodes[leader_index]
```

The code calls `is_my_turn(len(self.blockchain.chain))`. Because `len(chain)` includes the genesis block, the leader is selected for the next block using the current local chain length.

## Block Proposal Status

`SimpleConsensus` tracks block proposals in memory:

```python
pending_blocks[block_hash] = {
    "block": block,
    "votes": [BlockVote, ...],
    "status": BlockStatus.PENDING,
    "proposer": node_id,
    "propose_time": timestamp,
}
```

`BlockStatus` has three values:

- `PENDING = 0`: proposed but not finalized.
- `CONFIRMED = 1`: approval rate reached `consensus_threshold`.
- `REJECTED = 2`: rejection rate reached `consensus_threshold`.

Development note: `pending_blocks` is an in-memory proposal cache. It is not the same thing as the ledger. Only a confirmed block appended by `Blockchain.add_block()` is persisted into `data/ledger/chain.json`.

## What a Block Contains

The block model lives in `blockchain/block.py`.

```json
{
  "block_height": 12,
  "prev_block_hash": "previous block sha256",
  "timestamp": 1781680000,
  "client_node_id": "tc",
  "data_list": [],
  "current_hash": "current block sha256",
  "node_sign": "",
  "nonce": 0
}
```

Field meanings:

| Field | Meaning |
| --- | --- |
| `block_height` | Monotonic block height. Genesis block height is `0`. |
| `prev_block_hash` | Hash of the previous block. This links the ledger. |
| `timestamp` | Block packaging time, Unix timestamp in seconds. Genesis currently uses fixed timestamp `1`. |
| `client_node_id` | Node ID that packaged the block, such as `tc` or `ali`. |
| `data_list` | List of `ChainData` records included in this block. |
| `current_hash` | SHA-256 hash calculated by the block. |
| `node_sign` | Reserved signature field. It is currently empty unless future signing is added. |
| `nonce` | Reserved hash nonce. Current production flow uses `0`; optional mining helper can change it. |

Current hash input:

```text
block_height + prev_block_hash + timestamp + data_list_json + node_sign + nonce
```

Important: in the current code, `client_node_id` is stored in the block but is not part of the hash input. The actual monitored data inside `data_list` is part of the hash input. If strict block-proposer provenance is required, a future hardening step should include `client_node_id` in the hash input and add real node signatures.

## What `data_list` Contains

Each entry in `data_list` is a `ChainData` record:

```json
{
  "data_type": 1,
  "device_ip": "tc",
  "content": "{\"cpu_percent\": 21.5, \"memory\": {\"percent\": 63.2}}",
  "operate_user": "system",
  "timestamp": 1781680000,
  "data_id": ""
}
```

Field meanings:

| Field | Meaning |
| --- | --- |
| `data_type` | Integer enum from `ChainDataType`. |
| `device_ip` | Managed device identifier. For the local server this is the stable node ID, such as `tc` or `ali`. |
| `content` | JSON string carrying the actual metrics, FRU details, or operation result. |
| `operate_user` | Actor that produced the data. Automated samples use `system`; IPMI operations use the operator account. |
| `timestamp` | Data creation time, Unix timestamp in seconds. |
| `data_id` | Optional external data ID. Currently usually empty. |

`ChainDataType` values:

| Value | Name | Typical content |
| --- | --- | --- |
| `0` | `FRU_HARDWARE` | IPMI FRU fields, target IP, collection time, success flag. |
| `1` | `PERFORMANCE` | CPU, memory, disk, network, temperature, power, fan, and sensor data. |
| `2` | `IPMI_OPERATION` | Command, execution status, command result snippet, error snippet. |
| `3` | `NODE_HEARTBEAT` | Reserved for heartbeat records. Not actively written by the current main loop. |
| `4` | `CONFIG_CHANGE` | Reserved for config audit records. Not actively written by the current main loop. |

## Performance Payloads

Local server metrics use `psutil` and are currently the main dashboard source:

```json
{
  "cpu_percent": 18.2,
  "memory": {
    "total": 8335568896,
    "used": 4212346880,
    "percent": 50.5
  },
  "disk": {
    "/": {
      "total": 527371075584,
      "used": 103668916224,
      "percent": 19.66
    }
  },
  "net": {
    "bytes_sent": 123456,
    "bytes_recv": 654321
  },
  "temperature": {},
  "collect_time": 1781680000,
  "node_id": "tc",
  "node_name": "Tencent Cloud TC",
  "region": "cn-guangzhou"
}
```

Managed IPMI device metrics use `ipmitool sdr` and can include:

```json
{
  "cpu_usage": 0,
  "memory_usage": 0,
  "disk_io": {},
  "gpu_util": 0,
  "gpu_mem": 0,
  "temperature": {},
  "power": 0,
  "fan_speed": {},
  "sensors": [],
  "target_ip": "10.0.0.10",
  "collect_time": 1781680000,
  "success": true
}
```

The Web dashboard normalizes these formats. For local server resources, CPU comes from `cpu_percent` and memory comes from `memory.percent`. For IPMI-style records, CPU can come from `cpu_usage` and memory from `memory_usage`.

## Data Flow Summary

```text
collector
  -> ChainData
  -> blockchain.pending_data
  -> leader create_block()
  -> Block.data_list
  -> consensus.pending_blocks
  -> votes reach threshold
  -> blockchain.add_block()
  -> data/ledger/chain.json
  -> Web APIs read latest and historical metrics
```

## Operational Reading

Use these APIs to inspect node state:

- `GET /api/status`: process status, chain status, network status, managed device count.
- `GET /api/network/status`: peer online/offline details.
- `GET /api/blockchain/info`: chain height, latest hash, pending data count, validity.
- `GET /api/blockchain/blocks?limit=20`: block list.
- `GET /api/blockchain/block/<height>`: full block content including `data_list`.
- `GET /p2p/chain/info`: lightweight P2P chain height, latest hash, and validity metadata.
- `GET /p2p/chain/sync`: full P2P ledger payload for synchronization.
- `GET /api/server/metrics`: latest normalized server metrics.
- `GET /api/server/metrics/history?limit=80`: historical CPU and memory series by server.
