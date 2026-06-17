# 节点状态机与区块载荷说明

[English](node-state-machine.md) | 简体中文

本文说明 ChainMon 节点运行时的状态模型，以及区块中实际携带的信息。当前实现没有暴露一个单独的 `NodeState` 枚举；节点状态是由主循环、对等节点心跳、共识区块状态和本地账本状态共同组成的。

## 运行组件

一个 ChainMon 节点就是一个 `monitor_client.py` 进程。它包含以下运行组件：

- `Blockchain`：本地 JSON 账本和 `pending_data` 待上链数据池。
- `SimpleConsensus`：leader 选择、区块提议缓存、投票和区块确认状态。
- `P2PNetwork`：配置里的对等节点列表，以及心跳推导出的在线/离线状态。
- `HardwareCollector`：本机 `psutil` 指标采集，以及可选的 IPMI/SDR/FRU 采集。
- Flask Web 服务：看板和 HTTP API。
- Flask P2P 服务：区块提议、投票、链同步、节点查询和健康检查接口。

## 节点生命周期

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

## 状态说明

| 状态 | 归属 | 含义 | 主要代码路径 |
| --- | --- | --- | --- |
| `INIT` | 进程 | 加载配置，初始化区块链、共识、网络、采集器和 IPMI 执行器。 | `MonitorClient.__init__` |
| `BOOTSTRAP_SERVICES` | 进程 | 启动 P2P 服务、Web 服务和对等节点心跳线程。 | `_start_background_threads()` |
| `INITIAL_CHAIN_SYNC` | 账本 | 等待 P2P 服务就绪后，尝试从对等节点拉取更长且有效的链。 | `start()`, `_sync_chain_from_peers()` |
| `COLLECTING` | 采集器 | 采集托管设备和本机资源指标，将 `ChainData` 放入 `pending_data`。 | `_collect_data_cycle()` |
| `REFRESH_ACTIVE_NODES` | 共识 | 根据本机和心跳在线的 peer 生成当前投票节点集合。 | `_update_active_consensus_nodes()` |
| `FOLLOWER_WAIT` | 共识 | 当前节点不是下一个区块 leader，不创建区块，但继续采集和同步。 | `is_my_turn()` 返回 `False` |
| `LEADER_READY` | 共识 | 当前节点是 leader，且存在待上链数据。 | `is_my_turn()` 返回 `True` |
| `BLOCK_PROPOSED` | 共识 | leader 用 `pending_data` 创建区块，放入 `pending_blocks`，广播区块提议，并给自己投同意票。 | `_create_and_propose_block()` |
| `WAITING_VOTES` | 共识 | 区块保持 `BlockStatus.PENDING`，直到在线投票节点的同意比例达到阈值。 | `vote_block()`, `_check_consensus()` |
| `CONFIRMED` | 账本 | 同意比例达到 `consensus_threshold`，区块通过校验后写入本地账本。 | `get_confirmed_block()`, `add_block()` |
| `REJECTED` | 共识 | 拒绝比例达到阈值，或提议在内存缓存中过期后被清理。 | `_check_consensus()`, `cleanup_old_pending()` |
| `PERIODIC_SYNC` | 账本 | 每隔 `sync_interval` 秒从在线 peer 拉取最长有效链。 | `_sync_chain_from_peers()` |
| `STOPPING` | 进程 | 停止主循环并保存本地账本。 | `stop()` |

## 对等节点状态

对等节点状态由 `P2PNetwork` 维护。

- peer 初始在本地内存中视为离线。
- 心跳线程定期访问配置中的 peer。
- 心跳成功时设置 `is_online = true`，并更新 `last_heartbeat`。
- 心跳失败时设置为离线。
- 共识通过 `set_active_nodes()` 只使用 `本机 + 在线 peer` 作为投票集合。

因此双节点部署中，如果对端短暂不可达，本机仍可基于当前在线视图继续出块，不会一直等待离线节点确认。

## Leader 选择

只要节点拥有相同的在线节点视图和链高度，leader 选择就是确定性的。

```text
voting_nodes = sorted(self_node_id + online_peer_ids)
leader_index = len(chain) % len(voting_nodes)
leader = voting_nodes[leader_index]
```

代码调用的是 `is_my_turn(len(self.blockchain.chain))`。由于 `len(chain)` 包含创世块，所以 leader 是基于当前本地链长度为下一个区块选择出来的。

## 区块提议状态

`SimpleConsensus` 在内存中维护区块提议：

```python
pending_blocks[block_hash] = {
    "block": block,
    "votes": [BlockVote, ...],
    "status": BlockStatus.PENDING,
    "proposer": node_id,
    "propose_time": timestamp,
}
```

`BlockStatus` 有三个值：

- `PENDING = 0`：已经提议，但还没有最终确认。
- `CONFIRMED = 1`：同意比例达到 `consensus_threshold`。
- `REJECTED = 2`：拒绝比例达到 `consensus_threshold`。

开发注意：`pending_blocks` 是内存里的提议缓存，不等同于账本。只有被 `Blockchain.add_block()` 写入的确认区块，才会持久化到 `data/ledger/chain.json`。

## 区块里带什么信息

区块模型位于 `blockchain/block.py`。

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

字段含义：

| 字段 | 含义 |
| --- | --- |
| `block_height` | 区块高度，自增。创世块高度为 `0`。 |
| `prev_block_hash` | 上一个区块的哈希，用于形成链式账本。 |
| `timestamp` | 区块打包时间，Unix 秒级时间戳。创世块当前固定为 `1`。 |
| `client_node_id` | 打包该区块的节点 ID，例如 `tc` 或 `ali`。 |
| `data_list` | 本区块包含的 `ChainData` 记录列表。 |
| `current_hash` | 当前区块计算得到的 SHA-256 哈希。 |
| `node_sign` | 预留的节点签名字段。当前为空，后续可接入真实签名。 |
| `nonce` | 预留的哈希随机数。当前主流程为 `0`，可选挖矿辅助函数会修改它。 |

当前哈希输入为：

```text
block_height + prev_block_hash + timestamp + data_list_json + node_sign + nonce
```

重要细节：当前代码中，`client_node_id` 会保存在区块里，但没有参与哈希计算；真正的监控和运维数据 `data_list` 会参与哈希计算。如果未来需要严格证明“哪个节点打包了该区块”，建议把 `client_node_id` 纳入哈希输入，并启用真实节点签名。

## `data_list` 里带什么信息

`data_list` 的每一项都是一个 `ChainData`：

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

字段含义：

| 字段 | 含义 |
| --- | --- |
| `data_type` | `ChainDataType` 中定义的整数类型。 |
| `device_ip` | 被维护设备标识。本机服务器使用稳定的节点 ID，例如 `tc` 或 `ali`。 |
| `content` | JSON 字符串，承载真实指标、FRU 详情或操作结果。 |
| `operate_user` | 数据产生者。自动采样为 `system`，IPMI 操作为操作账号。 |
| `timestamp` | 数据产生时间，Unix 秒级时间戳。 |
| `data_id` | 可选外部数据 ID。当前通常为空。 |

`ChainDataType` 取值：

| 值 | 名称 | 典型内容 |
| --- | --- | --- |
| `0` | `FRU_HARDWARE` | IPMI FRU 字段、目标 IP、采集时间和成功标记。 |
| `1` | `PERFORMANCE` | CPU、内存、磁盘、网络、温度、功耗、风扇和传感器数据。 |
| `2` | `IPMI_OPERATION` | 指令、执行状态、结果摘要和错误摘要。 |
| `3` | `NODE_HEARTBEAT` | 预留的节点心跳记录。当前主循环尚未主动写入。 |
| `4` | `CONFIG_CHANGE` | 预留的配置变更审计记录。当前主循环尚未主动写入。 |

## 性能指标载荷

本机服务器指标来自 `psutil`，也是当前看板的主要数据来源：

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

托管 IPMI 设备指标来自 `ipmitool sdr`，可能包含：

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

Web 看板会对这些格式做归一化。本机资源中 CPU 读取 `cpu_percent`，内存读取 `memory.percent`；IPMI 风格记录中 CPU 可读取 `cpu_usage`，内存可读取 `memory_usage`。

## 数据流总结

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

## 运维排查入口

可以通过以下接口观察节点状态：

- `GET /api/status`：进程状态、链状态、网络状态、托管设备数量。
- `GET /api/network/status`：peer 在线/离线详情。
- `GET /api/blockchain/info`：链高度、最新哈希、待上链数据数量、链有效性。
- `GET /api/blockchain/blocks?limit=20`：区块列表。
- `GET /api/blockchain/block/<height>`：完整区块内容，包括 `data_list`。
- `GET /api/server/metrics`：最新归一化服务器资源指标。
- `GET /api/server/metrics/history?limit=80`：按服务器分组的 CPU 和内存历史序列。

