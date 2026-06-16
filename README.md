# ChainMon

> Chain + Monitor — 全球分布式机房极简联盟链监控管理系统

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Ubuntu%2020.04%2F22.04-orange.svg)](https://ubuntu.com/)

ChainMon 是基于 Python 自研轻量化联盟链的全球分布式机房监控系统，无代币、无挖矿、无复杂共识、无重型依赖。

通过在各机房部署 Ubuntu 专属本地服务客户端，实现服务器 FRU 硬件采集、性能指标监控、IPMI 远程指令管控，所有数据与运维操作上链存证、不可篡改、全程溯源。

## 当前版本：服务器资源维护视图

当前实现重点已经调整为“服务器资源信息维护”，联盟链作为采集数据和运维操作的审计底座。Web 首页优先展示所有维护服务器的 CPU 利用率、内存利用率和历史趋势，而不是优先展示区块浏览。

### 已实现能力

- 两台云服务器节点：`tc`（腾讯云）和 `ali`（阿里云）互为联盟链节点。
- 任意访问一个 Web 后台，都可以看到所有维护服务器的资源信息。
- 首页提供 CPU 利用率和内存利用率折线图，使用浏览器原生 Canvas，无外部 CDN 依赖。
- 本机资源采集使用节点 ID（如 `tc` / `ali`）作为设备标识，不再使用容易混淆的 `localhost`。
- 当对端短暂不可达时，本机仍可按在线节点集合完成本地记账，避免服务器指标卡在待确认状态。
- 清链后使用确定性创世块，方便两台节点从干净账本重新开始同步。

### 关键接口

```http
GET /api/server/metrics
```

返回每台维护服务器的最新 CPU、内存、磁盘、网络等摘要信息。当前 Web 首页主要使用 CPU 和内存字段。

```http
GET /api/server/metrics/history?limit=80
```

按服务器分组返回 CPU 利用率和内存利用率历史点，用于绘制折线图。

```http
GET /api/status
GET /api/blockchain/blocks?limit=20
```

用于健康检查、链状态检查和审计排障。

### 清空链上历史数据

如果需要清理旧链、移除历史 `localhost` 记录，可在每个节点上执行：

```bash
cd ~/ChainMon
pkill -f '[p]ython3 monitor_client.py' || true
mkdir -p backups/$(date +%Y%m%d%H%M%S)/data_ledger
cp -a data/ledger/. backups/$(date +%Y%m%d%H%M%S)/data_ledger/ 2>/dev/null || true
rm -f data/ledger/chain.json
setsid -f bash -lc 'source venv/bin/activate 2>/dev/null || true; exec python3 monitor_client.py >> logs/stdout.log 2>&1 < /dev/null'
```

两台节点都清空并重启后，会从新的短链重新采集 `tc` / `ali` 的资源数据。

### 2026-06-17 完整验收结果

本次已在 `srvlist.txt` 中两台云服务器完成部署、清链和验收：

- `http://43.156.165.206:5000`
  - 链有效：`true`
  - 对等节点在线：`1`
  - 待上链数据：`0`
  - 维护服务器：`tc`、`ali`
  - CPU/内存历史序列：两台服务器均有数据点
  - `localhost` 指标：已清除

- `http://8.152.4.161:5000`
  - 链有效：`true`
  - 对等节点在线：`1`
  - 待上链数据：`0`
  - 维护服务器：`tc`、`ali`
  - CPU/内存历史序列：两台服务器均有数据点
  - `localhost` 指标：已清除

本地测试：

```bash
python tests/test_blockchain.py
python tests/test_server_metrics.py
python -m py_compile monitor_client.py web_server.py p2p_server.py blockchain/block.py blockchain/chain.py blockchain/consensus.py blockchain/network.py client/collector.py client/config_loader.py client/crypto.py client/ipmi_executor.py
```

## 目录

- [项目简介](#项目简介)
- [系统架构](#系统架构)
- [一体化架构说明](#一体化架构说明)
- [联盟链同步机制](#联盟链同步机制)
- [最佳实践：跨区域部署示例](#最佳实践跨区域部署示例)
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

- 硬件静态信息采集（FRU完整硬件信息：CPU型号、内存、主板、序列号等）
- 设备动态指标采集（CPU、内存、磁盘IO、GPU、温度、功耗）
- 远程IPMI指令管控（开机、关机、重启、硬件参数查询）
- 全球分布式就近组网（就近采集、就近上报）
- 区块链可信溯源能力（所有数据、操作全上链存储）
- FRU敏感数据加密传输（AES-256-CBC + HMAC-SHA256）

## 系统架构

```
+———————————————————————————————————————————————————————————+
|                     应用层：可视化管理后台                   |
|           (设备状态查看、FRU详情加密、IPMI指令下发、        |
|            溯源查询、链可视化、审计日志)                     |
+———————————————————————————————————————————————————————————+
                           ↕ HTTP (Flask :5000)
+———————————————————————————————————————————————————————————+
|                核心层：极简私有联盟链网络                    |
|     (区块打包、链式哈希校验、决定性轮询共识、账本同步)       |
+———————————————————————————————————————————————————————————+
                           ↕ 本地调用
+———————————————————————————————————————————————————————————+
|             终端层：机房本地服务客户端（多节点）              |
|   (局域网扫描、IPMI数据采集、IPMI指令执行、本地缓存、       |
|    数据上链、AES加密)                                       |
+———————————————————————————————————————————————————————————+
```

### 架构分层

1. **终端层**：机房本地服务客户端，每个机房部署一套，独立完成组网、数据采集、指令执行、链上存证
2. **核心层**：极简私有联盟链网络，由所有客户端节点共同组成，提供分布式记账存证能力。共识基于 `chain_height % N` 决定性轮询，无需状态同步
3. **应用层**：Flask Web管理后台，数据展示、FRU加密查看、指令下发、溯源查询（浏览器原生 Web Crypto API，零外部 CDN 依赖）

## 一体化架构说明

**客户端与联盟链节点是同一个进程，不可分离。** 一个 `monitor_client.py` 进程同时承载了全部能力：

```
python3 monitor_client.py（单进程）
    │
    ├── 联盟链节点 ─────────── 区块链账本（Blockchain）
    │   ├── 共识模块（Consensus）── 决定性轮询记账（chain_height % N）
    │   ├── P2P服务器 ──────── 监听8080，接收/广播区块与投票
    │   └── 账本存储 ──────── 本地 chain.json 持久化
    │
    ├── 监控客户端 ─────────── 数据采集器（Collector）
    │   ├── FRU采集 ──────── ipmitool fru
    │   ├── 性能采集 ──────── ipmitool sensor + psutil
    │   ├── IPMI执行器 ────── ipmitool 指令白名单管控
    │   └── 加密模块 ──────── AES-256-CBC + HMAC-SHA256
    │
    └── Web管理后台 ──────── Flask服务器，监听5000
        ├── 仪表盘 ──────── 全局状态概览
        ├── 设备管理 ─────── FRU详情加密查看（Web Crypto API解密）
        ├── IPMI控制 ─────── 远程指令下发
        ├── 区块链浏览 ───── 链可视化、区块详情
        └── 审计日志 ─────── 链上数据查询与溯源
```

**这意味着：启动 `monitor_client.py` = 联盟链节点上线。** 进程启动后自动完成：

1. 初始化本地账本（加载历史链或创建创世区块）
2. 启动 P2P 服务器（监听 8080，等待其他节点连接）
3. 启动 Web 管理后台（监听 5000）
4. 从对等节点同步链数据（如果本地链落后则自动追赶）
5. 开始采集设备数据，按轮询顺序打包区块

**一个机房 = 一台服务器 = 一个 `monitor_client.py` 进程 = 一个联盟链节点。** 无需单独部署区块链服务。

## 联盟链同步机制

ChainMon 的联盟链同步分为两个层面：**共识同步**（区块实时确认）和**链同步**（账本追赶），两者配合确保全网数据一致。

### 一、共识同步：区块从提议到上链的完整流程

```
节点A（轮到记账）                    节点B                      节点C
    │                                   │                          │
    │  1. 采集本地数据                    │                          │
    │  2. 打包新区块                      │                          │
    │  3. 本地投票(同意)                  │                          │
    │                                    │                          │
    │─── POST /p2p/block/propose ───────>│                          │
    │─── POST /p2p/block/propose ──────────────────────────────────>│
    │                                    │                          │
    │                                    │ 4. 接收提议，投票(同意)    │
    │                                    │                          │ 4. 接收提议，投票(同意)
    │                                    │                          │
    │<── POST /p2p/block/vote (B同意) ──│                          │
    │<── POST /p2p/block/vote (B同意) ─────────────────────────────│
    │                                   │                          │
    │<── POST /p2p/block/vote (C同意) ──│                          │
    │<── POST /p2p/block/vote (C同意) ─────────────────────────────│
    │                                    │                          │
    │  5. 统计投票: 3/3=100%≥80%         │ 5. 统计投票: 3/3=100%    │ 5. 统计投票: 3/3=100%
    │  6. ✅ 区块确认，写入本地链          │ 6. ✅ 区块确认，写入链    │ 6. ✅ 区块确认，写入链
    │  7. 切换记账权给下一个节点           │                          │
```

**详细步骤：**

| 步骤 | 动作 | 说明 |
|------|------|------|
| 1 | 本地数据采集 | 节点采集本机房设备的FRU、性能、IPMI操作等数据，放入待上链池 |
| 2 | 打包新区块 | 轮询到的节点将待上链池数据打包成区块，计算SHA256哈希 |
| 3 | 本地投票 | 提议节点自己先投同意票，并广播投票给所有节点 |
| 4 | 广播区块提议 | 通过 POST `/p2p/block/propose` 发送给所有在线对等节点 |
| 5 | 对等节点接收投票 | 收到提议的节点校验哈希、签名后自动投同意票，并广播自己的投票 |
| 6 | 共识达成 | 各节点独立统计收到的投票，当同意票≥80%节点数时，区块状态变为CONFIRMED |
| 7 | 写入本地链 | 区块确认后，各节点独立将区块追加到本地链并持久化 |
| 8 | 轮询切换 | 记账权按 `chain_height % len(all_nodes)` 决定，传递到下一个节点 |

**关键设计：投票是广播的。** 每个节点投票后会将自己的投票广播给所有对等节点，确保每个节点都能独立统计到完整票数并独立确认区块。

### 二、决定性共识机制

ChainMon 采用 **决定性轮询共识**（Deterministic Round-Robin），不依赖节点间状态同步：

```
leader_index = chain_height % len(all_nodes)
```

- 每个节点基于**链当前高度**和**已知节点列表**独立计算本轮记账节点
- 无需网络同步或状态变量，多节点天然一致
- 单节点可独立出块（100% ≥ 80%阈值），网络中断不影响本地服务
- 轮询严格交替，保证各节点出块机会均等

### 三、链同步：新节点上线与落后节点追赶

当一个节点启动时、或者网络中断恢复后，本地区块链可能落后于全网最新状态。ChainMon 通过定期链同步机制自动追赶：

```
新节点启动                              已有节点A
    │                                       │
    │  1. 加载本地链（可能是创世区块）         │
    │  2. 启动P2P服务器                      │
    │  3. 等待3秒（服务器就绪）               │
    │                                       │
    │─── GET /p2p/chain/sync ──────────────>│
    │<── 返回完整链数据 ────────────────────│
    │                                       │
    │  4. 比较链高度：远程100 > 本地0          │
    │  5. 校验远程链哈希完整性                 │
    │  6. 校验与本地链的共同前缀               │
    │  7. ✅ 替换本地链，同步完成              │
    │                                       │
    │  （之后每60秒定期检查一次）               │
```

**链同步策略：**

| 场景 | 触发条件 | 同步行为 |
|------|----------|----------|
| 新节点首次上线 | 本地仅有创世区块 | 从任意在线节点拉取完整链 |
| 网络中断恢复 | 本地高度 < 远程高度 | 增量同步缺失的区块 |
| 正常运行 | 定期60秒检查 | 比对所有在线节点，若落后则同步最长链 |
| 链分叉 | 本地与远程链在共同高度哈希不同 | 拒绝同步，需人工介入 |

**同步安全校验：**

- 远程链必须通过完整性校验（所有区块的 prev_hash 链式关联正确）
- 远程链必须与本地链有共同前缀（防止分叉覆盖）
- 只有远程链**更长**时才替换本地链

### 四、心跳与节点状态管理

各节点之间通过定期心跳维护在线状态：

- 默认每30秒向所有对等节点发送心跳（POST `/p2p/heartbeat`）
- 心跳失败时标记对等节点为离线
- 离线节点不参与区块广播和投票
- 网络恢复后，心跳成功自动恢复在线状态

## 最佳实践：跨区域部署示例

以 **中国香港机房 + 美国机房** 为例，说明跨区域监控与同步的完整逻辑。

### 网络拓扑

```
                        ┌─────────────────────┐
                        │    公网 / 专线       │
                        │  (跨太平洋延迟~150ms) │
                        └─────────┬───────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
┌─────────┴──────────┐  ┌────────┴─────────┐  ┌─────────┴──────────┐
│  中国香港机房        │  │  美国机房         │  │  运维人员浏览器     │
│  hk-dc1             │  │  us-dc1           │  │                    │
│                     │  │                   │  │                    │
│  monitor_client.py  │  │  monitor_client.py│  │  http://hk:5000    │
│  ├─ P2P :8080       │  │  ├─ P2P :8080     │  │  或 http://us:5000 │
│  ├─ Web :5000       │  │  ├─ Web :5000     │  │                    │
│  ├─ 本地账本         │  │  ├─ 本地账本       │  │                    │
│  └─ 管理设备:        │  │  └─ 管理设备:      │  │                    │
│     10.0.1.100      │  │     10.0.2.100    │  │                    │
│     10.0.1.101      │  │     10.0.2.101    │  │                    │
│     10.0.1.102      │  │     10.0.2.102    │  │                    │
└─────────────────────┘  └───────────────────┘  └────────────────────┘
```

### 香港节点配置

```yaml
# config/node_config.yaml（香港节点 hk-dc1）
node:
  node_id: "hk-dc1"
  region: "hk"

blockchain:
  listen_port: 8080
  consensus_threshold: 80
  ledger_path: "./data/ledger"

client:
  ipmi_username: "admin"
  ipmi_password: "admin123"
  collect_interval: 30
  scan_subnets: ["10.0.1.0/24"]

web:
  port: 5000

# 对等节点白名单（写入美国节点信息）
peers:
  - node_id: "us-dc1"
    host: "203.0.113.10"    # 美国节点公网IP
    port: 8080
    region: "us"
```

### 美国节点配置

```yaml
# config/node_config.yaml（美国节点 us-dc1）
node:
  node_id: "us-dc1"
  region: "us"

blockchain:
  listen_port: 8080
  consensus_threshold: 80
  ledger_path: "./data/ledger"

client:
  ipmi_username: "admin"
  ipmi_password: "admin123"
  collect_interval: 30
  scan_subnets: ["10.0.2.0/24"]

web:
  port: 5000

# 对等节点白名单（写入香港节点信息）
peers:
  - node_id: "hk-dc1"
    host: "198.51.100.10"    # 香港节点公网IP
    port: 8080
    region: "hk"
```

### 跨区域数据流与同步逻辑

#### 场景1：日常监控数据上链（香港节点轮到记账）

```
时间线  香港节点 hk-dc1                              美国节点 us-dc1
──────  ──────────────                               ──────────────
T+0s    采集本机房10.0.1.x设备数据
        采集本机房10.0.1.x性能指标
        → 5条数据进入待上链池
        （chain_height % 2 = hk-dc1的索引 → 轮到记账）
        打包区块 Block#101
        本地投票: hk-dc1=同意
        广播投票给 us-dc1

T+0.3s  广播区块提议 ──── POST /p2p/block/propose ──> 接收区块提议
        （约150ms跨洋延迟）                            校验哈希通过
                                                      本地投票: us-dc1=同意
        <─── POST /p2p/block/vote ───────────────── 广播投票给 hk-dc1

T+0.5s  收到 us-dc1 投票: 同意                       收到 hk-dc1 投票: 同意
        统计: 2/2=100% ≥ 80%                          统计: 2/2=100% ≥ 80%
        ✅ 区块确认！写入本地链                        ✅ 区块确认！写入本地链

        香港机房设备数据现已在美国节点的链上可查 ✓
```

**关键点：** 只有结构化的小数据包（JSON格式设备指标）跨洋传输，**不传输原始日志或大量监控数据**，跨区网络压力极小。

#### 场景2：运维人员从Web后台远程执行IPMI指令

```
运维人员                    香港节点 hk-dc1                         美国节点 us-dc1
──────                      ──────────────                          ──────────────
访问 http://hk:5000
下发IPMI指令:
  目标: 10.0.2.100
  命令: power reset

                            Web后台接收指令
                            → 目标设备10.0.2.100
                              属于美国机房
                            → 转发指令到美国节点
                            ──── POST /api/ipmi/execute ──────────> 美国节点本地执行:
                                                                        ipmitool -H 10.0.2.100
                                                                        -U admin power reset
                            <──── 返回执行结果 ──────────────────── 执行完成

                            结果日志打包上链：
                            ChainData(type=IPMI_OPERATION,
                              device="10.0.2.100",
                              command="power reset",
                              operator="admin",
                              status="success")

                            轮到记账时，IPMI操作日志
                            随区块广播到美国节点
                            → 全网可溯源 ✓
```

#### 场景3：网络中断后的断点续传与链同步

```
时间线  香港节点 hk-dc1                              美国节点 us-dc1
──────  ──────────────                               ──────────────
T+0s    ...正常运行...                                ...正常运行...

T+300s  🌐 跨洋网络中断！
        → 心跳超时，标记 us-dc1 离线
        → 继续本地采集+缓存
        → 轮到自己记账时，独自打包+确认
          （单节点100%≥80%，区块仍可确认）
        → 区块暂存本地链

T+600s  🌐 网络恢复！
        → 心跳成功，us-dc1 恢复在线
        → 定期链同步检查：
          发现 us-dc1 高度 > 本地高度
          → 增量同步缺失区块

T+603s  同步完成，双节点链高度一致 ✓
        恢复正常共识流程
```

**断网期间的行为：**

| 角色 | 断网行为 | 恢复后行为 |
|------|----------|-----------|
| 本地采集 | 继续采集，数据进入待上链池 | 积压数据批量打包上链 |
| 区块打包 | 单节点可独立确认（100%≥80%） | 恢复多节点共识 |
| 心跳 | 标记对端离线 | 自动恢复在线状态 |
| 链同步 | 停止 | 自动增量同步缺失区块 |
| IPMI指令 | 本机房设备仍可操作 | 跨机房指令恢复转发 |

### 跨区域部署要点

1. **公网IP互通**：各机房节点必须通过公网IP（或专线）互相可达，P2P端口（默认8080）需开放防火墙
2. **延迟容忍**：共识过程仅需2-3次HTTP往返（区块广播+投票），150ms延迟下约0.5秒完成确认
3. **带宽极省**：仅传输结构化JSON数据（单条设备指标约200-500字节），不传输原始日志或监控图表
4. **数据就近**：设备数据在本地机房采集和缓存，仅上链的哈希摘要跨区传输
5. **独立可用**：即使跨区网络中断，各机房节点仍可独立运行，本地采集、本地记账、本地管控

## 核心特性

- **极简联盟链架构**：摒弃公链冗余能力，仅保留链式记账、哈希防篡改、分布式共识、账本同步核心能力
- **决定性轮询共识**：基于 `chain_height % N` 的确定性算法，无需状态同步，多节点天然一致
- **分布式就近部署**：各机房本地客户端独立组网、就近采集、就近执行，规避跨区网络延迟
- **全维度硬件监控**：支持 FRU 静态硬件信息（CPU型号/内存/主板/序列号）、温度/风扇/功耗/CPU/内存全指标采集
- **FRU加密传输**：AES-256-CBC + HMAC-SHA256 加密，前端 Web Crypto API 浏览器本地解密
- **零外部CDN依赖**：前端纯原生 JavaScript + Web Crypto API，无任何第三方CDN引用，在中国大陆网络环境稳定可用
- **可信IPMI运维**：标准化 ipmitool 指令下发与执行（白名单管控），所有运维操作自动上链审计
- **断网容错能力**：离线缓存、联网补传，单节点可独立出块，保证数据零丢失
- **无单点故障**：多节点分布式账本同步，去中心化组网
- **纯Ubuntu适配**：环境统一、依赖统一、部署简单

## 环境依赖

### 系统要求

- **操作系统**：Ubuntu 20.04 LTS 或 Ubuntu 22.04 LTS（仅支持Ubuntu）
- **Python版本**：Python 3.9+
- **硬件要求**：2核4G及以上（推荐4核8G）
- **网络要求**：各节点间 P2P 端口（默认8080）互通，Web端口（默认5000）对运维人员可达

### 系统工具依赖

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ipmitool openssh-client curl
```

### Python 依赖

```bash
pip install -r requirements.txt
```

| 包名 | 版本要求 | 用途 |
|------|----------|------|
| `flask` | >=2.3.0 | Web管理后台框架 |
| `flask-cors` | >=4.0.0 | CORS跨域支持 |
| `psutil` | >=5.9.0 | 系统性能采集（CPU/内存/磁盘/网络） |
| `requests` | >=2.31.0 | HTTP客户端（P2P节点间通信） |
| `pyyaml` | >=6.0 | YAML配置文件解析 |
| `cryptography` | >=41.0.0 | AES-256-CBC 加密/解密 |

> **注意**：Ubuntu 24.04 或系统中同时存在多个 Python 版本时，pip 可能拒绝安装到系统目录。可使用以下方式安装：
> ```bash
> pip install -r requirements.txt --break-system-packages
> # 或使用虚拟环境
> python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
> ```

## 快速部署

### 1. 克隆项目

```bash
git clone https://github.com/Dzy-HW-XD/ChainMon.git
cd ChainMon
```

### 2. 创建配置文件

```bash
# 复制配置模板并修改
cp config/config_template.yaml config/node_config.yaml
vim config/node_config.yaml
```

**关键配置项（必须修改）：**

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `node.node_id` | 节点唯一ID | `ali` / `tc` / `hk-dc1` |
| `node.region` | 机房区域 | `cn-hangzhou` / `cn-guangzhou` |
| `peers` | 其他节点信息 | 见配置说明 |
| `client.ipmi_username` | IPMI账号 | `admin` |
| `client.ipmi_password` | IPMI密码 | `admin123` |
| `web.username` | Web后台账号 | `admin` |
| `web.password` | Web后台密码 | `admin123` |

### 3. 安装依赖

```bash
# 方式一：虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 方式二：系统安装
pip install -r requirements.txt --break-system-packages
```

### 4. 创建运行时目录

```bash
mkdir -p data/ledger data/cache logs
```

### 5. 启动客户端

```bash
# 前台运行（测试/调试）
python3 monitor_client.py

# 后台运行（生产）
nohup python3 monitor_client.py > logs/monitor.log 2>&1 &

# 或使用 systemd（推荐）
sudo cp scripts/monitor.service /etc/systemd/system/
sudo systemctl enable monitor
sudo systemctl start monitor
```

### 6. 访问管理后台

浏览器打开：`http://服务器IP:5000`

默认账号：`admin / admin123`

### 部署验证

```bash
# 检查进程
ps aux | grep monitor_client

# 检查端口
ss -tlnp | grep -E '5000|8080'

# 检查API
curl http://localhost:5000/api/status

# 检查日志
tail -f logs/monitor.log
```

## 配置说明

配置文件位置：`config/node_config.yaml`

### 完整配置段

| 配置段 | 关键字段 | 说明 |
|--------|----------|------|
| `node` | `node_id`, `node_name`, `region`, `role` | 节点基础信息（机房标识） |
| `blockchain` | `listen_port`, `genesis_hash`, `block_interval`, `consensus_threshold`, `ledger_path`, `private_key_path` | 链网络参数 |
| `peers` | `node_id`, `host`, `port`, `region` 列表 | 联盟链节点白名单 |
| `client` | `scan_subnets`, `ipmi_username/password`, `collect_interval`, `batch_size`, `cache_path`, `ipmi_whitelist` | 客户端采集配置 |
| `devices` | `ip`, `name`, `type` 列表（可选） | 显式托管设备清单 |
| `database` | `sqlite_path`, `retention_days` | SQLite 存储路径和保留策略 |
| `web` | `port`, `debug`, `username`, `password` | Web 管理后台配置 |
| `logging` | `level`, `file_path`, `retention_days` | 日志级别和路径 |

### 配置详解

#### node（节点基础信息）

```yaml
node:
  node_id: "ali"              # 节点唯一ID（必需，用于共识轮询和链上标识）
  node_name: "阿里云-ALI节点"  # 节点显示名称
  region: "cn-hangzhou"       # 机房区域
  role: "client"              # 节点角色
```

#### blockchain（区块链参数）

```yaml
blockchain:
  listen_port: 8080           # P2P监听端口（需防火墙放行）
  block_interval: 30          # 出块间隔（秒）
  consensus_threshold: 80     # 共识阈值（百分比，≥80%确认）
  ledger_path: "./data/ledger"# 账本存储路径
  private_key_path: "./data/node_private.pem"  # 节点私钥路径
```

#### peers（节点白名单）

每个节点的 `peers` 中只写**其他**节点的信息，不写自己：

```yaml
peers:
  - node_id: "tc"
    host: "43.156.165.206"    # 对端公网IP
    port: 8080
    region: "cn-guangzhou"
```

#### devices（托管设备清单）

可选配置，显式指定该节点管理的设备列表：

```yaml
devices:
  - ip: "10.0.1.100"
    name: "核心交换机"
    type: "switch"
  - ip: "10.0.1.101"
    name: "GPU服务器-01"
    type: "server"
```

不配置时，系统自动从IPMI扫描发现设备。

#### IPMI白名单

```yaml
client:
  ipmi_whitelist:
    - "power"
    - "chassis"
    - "sensor"
    - "fru"
    - "sel"
    - "lan"
    - "user"
```

仅允许白名单中的关键词作为IPMI指令前缀，防止危险操作。

## 使用指南

### Web管理后台

访问 `http://服务器IP:5000` 进入管理后台，5个功能标签：

1. **Dashboard（仪表盘）**：节点状态、区块链信息、链可视化
2. **Devices（设备管理）**：托管设备列表、点击设备查看加密FRU详情（CPU型号、内存容量、主板信息等）
3. **Blockchain（区块链浏览）**：区块列表、区块详情、节点出块统计
4. **IPMI Control（IPMI控制）**：远程指令下发（开机/关机/重启/FRU查询/传感器/SEL日志）
5. **Audit Log（审计日志）**：链上数据查询（按类型/IP筛选）

### API接口

#### 获取系统状态

```bash
GET /api/status
```

返回示例：
```json
{
  "node_id": "ali",
  "is_running": true,
  "blockchain": {
    "chain_height": 68,
    "is_valid": true,
    "total_blocks": 69,
    "latest_block_hash": "1f7072d..."
  },
  "network": {
    "total_peers": 1,
    "online_peers": 1
  },
  "managed_devices": 1
}
```

#### 获取设备列表

```bash
GET /api/devices
```

#### 获取设备FRU详情（加密）

```bash
GET /api/device/{ip}/fru
```

返回 AES-256-CBC 加密的 FRU 数据，前端通过 Web Crypto API 自动解密。包含：
- `product_name` - 产品型号
- `serial` - 序列号
- `board` - 主板信息
- `chassis` - 机箱信息
- `cpu_info` - CPU型号/核心数
- `memory_info` - 内存容量
- `sensors_summary` - 传感器摘要（温度/风扇/功耗）

#### 获取加密密钥

```bash
GET /api/crypto/key
```

返回 Base64 编码的 AES-256 密钥（由 Web 管理员密码 SHA-256 派生）。

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

参数：
- `data_type`：0=FRU, 1=性能, 2=IPMI操作, 3=心跳
- `device_ip`：按设备IP筛选
- `limit`：返回条数（默认50）

## 开发指南

### 项目结构

```
ChainMon/
├── blockchain/              # 区块链核心模块
│   ├── __init__.py
│   ├── block.py           # 区块结构定义与哈希计算
│   ├── chain.py           # 区块链管理（添加、验证、查询、同步）
│   ├── consensus.py       # 决定性轮询共识（chain_height % N）
│   └── network.py         # P2P网络模块（节点通信、广播、心跳）
├── client/                # 客户端模块
│   ├── __init__.py
│   ├── collector.py       # 数据采集（FRU、性能指标）
│   ├── config_loader.py   # YAML配置加载/保存模块
│   ├── crypto.py          # AES-256-CBC加密 + HMAC-SHA256
│   └── ipmi_executor.py   # IPMI指令执行器（白名单管控）
├── config/                # 配置文件
│   ├── config_template.yaml  # 配置模板（含完整注释）
│   └── node_config.yaml     # 实际配置（不提交git）
├── data/                  # 数据目录（gitignore）
│   ├── ledger/            # 区块链账本
│   └── cache/             # 采集数据缓存
├── logs/                  # 日志目录（gitignore）
├── scripts/               # 部署脚本
│   ├── deploy.sh          # 一键部署脚本（Ubuntu）
│   └── monitor.service    # systemd 服务单元
├── tests/                 # 测试代码
│   └── test_blockchain.py  # 区块链核心逻辑单元测试
├── monitor_client.py      # 主客户端程序（入口，一体化进程）
├── p2p_server.py          # P2P网络服务器（区块提议/投票/心跳/链同步API）
├── web_server.py          # Web管理后台服务器（Flask + 内嵌前端）
├── requirements.txt       # Python依赖清单
├── README.md              # 项目文档（本文件）
├── LICENSE                # MIT License
└── .gitignore             # Git忽略规则
```

### 模块说明

| 模块 | 文件 | 职责 |
|------|------|------|
| 区块核心 | `blockchain/block.py` | Block 结构体、ChainData 结构体、SHA256哈希、创世区块 |
| 链管理 | `blockchain/chain.py` | 链追加、验证、查询、JSON持久化、链同步 |
| 共识 | `blockchain/consensus.py` | `is_my_turn(chain_height)` 决定性轮询、`get_current_leader()` |
| P2P网络 | `blockchain/network.py` | 节点发现、区块广播、投票广播、心跳、链同步请求 |
| 数据采集 | `client/collector.py` | FRU硬件信息、IPMI传感器、psutil本地性能 |
| IPMI执行 | `client/ipmi_executor.py` | ipmitool 指令白名单校验与执行 |
| 加密模块 | `client/crypto.py` | AES-256-CBC加密/解密、HMAC-SHA256校验 |
| 配置加载 | `client/config_loader.py` | YAML配置读取/保存/默认值 |
| 主进程 | `monitor_client.py` | 一体化入口，启动链节点+P2P服务器+Web后台+采集 |
| P2P API | `p2p_server.py` | Flask Blueprint: 区块提议/投票/心跳/链同步端点 |
| Web后台 | `web_server.py` | Flask应用: 管理界面HTML + REST API |

### 开发流程

1. **修改代码**：在对应模块中进行修改
2. **运行测试**：`python3 tests/test_blockchain.py`
3. **启动客户端**：`python3 monitor_client.py`
4. **查看日志**：`tail -f logs/monitor.log`

### 安全设计

- **FRU加密**：敏感硬件信息通过 AES-256-CBC 加密传输，密钥由管理员密码 SHA-256 派生
- **前端解密**：浏览器原生 Web Crypto API 解密，无需第三方加密库
- **零CDN依赖**：前端所有逻辑纯原生实现，不受 CDN 网络影响
- **IPMI白名单**：仅允许 `power/chassis/sensor/fru/sel/lan/user` 等安全指令前缀
- **IP转发**：IPMI指令自动转发到目标设备所在机房节点执行，跨机房操作可溯源
- **链上存证**：所有 IPMI 操作自动上链，操作人/时间/设备/结果不可篡改

## 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| 开发语言 | Python 3.9+ | 最简开发、生态成熟 |
| 区块链底层 | 自研极简联盟链 | 无第三方链依赖 |
| 共识机制 | 决定性轮询共识 | chain_height % N 算法 |
| 数据存储 | JSON文件 | 极简持久化，零配置 |
| 数据库 | SQLite | 设备和操作记录持久化 |
| 通信协议 | HTTP/REST | 成熟通用、调试简单 |
| 哈希算法 | SHA256 | 通用安全哈希 |
| 加密算法 | AES-256-CBC | FRU数据传输加密 |
| 前端加密 | Web Crypto API | 浏览器原生，零CDN |
| IPMI工具 | ipmitool | 系统原生、兼容性强 |
| Web框架 | Flask | 轻量级、易上手 |

## 路线图

### 一期（基础可用）✅

- [x] 最简区块链底层：区块结构、哈希校验、节点组网、决定性轮询共识
- [x] 本地客户端基础组网、心跳、账本同步能力
- [x] FRU硬件信息、CPU/内存基础指标采集与上链
- [x] IPMI查询/控制指令执行与日志上链
- [x] 投票广播与区块自动上链
- [x] 启动时链同步与定期链追赶
- [x] Web管理后台（仪表盘/设备管理/区块链浏览/IPMI控制/审计日志）
- [x] FRU加密传输（AES-256-CBC + Web Crypto API）
- [x] 零CDN依赖前端（纯原生JS + Web Crypto API）
- [x] 跨区域双节点部署验证（ALI + TC）

### 二期（功能完善）🔄

- [ ] GPU、磁盘IO、温度、功耗全维度指标采集
- [ ] IPMI设备启停、参数配置等管控指令全覆盖
- [ ] 权限校验、指令风控、异常重试机制
- [ ] 账本巡检、数据防篡改校验能力
- [ ] 设备告警与通知

### 三期（稳定商用）📋

- [ ] 网络断连容错、断点续传、数据缓存优化
- [ ] 多节点冗余（≥3节点）、故障自动切换
- [ ] 后台溯源审计、告警、数据统计功能
- [ ] 性能优化，适配大规模机房、大批量设备管控

## 常见问题

### Q: 客户端和联盟链节点是什么关系？

A: **一体化设计，不可分离。** 一个 `monitor_client.py` 进程同时是监控客户端和联盟链节点。启动客户端 = 联盟链节点上线，无需单独部署区块链服务。

### Q: 为什么只用Ubuntu？

A: 统一研发与运行环境标准，简化开发复杂度，聚焦业务能力。所有代码、测试、部署均基于Ubuntu。

### Q: 跨区网络延迟会影响监控吗？

A: 不会。设备数据在本地机房采集和缓存，仅结构化的上链数据（JSON，几百字节）跨区传输。150ms跨洋延迟下，区块共识约0.5秒完成。

### Q: 跨区网络中断怎么办？

A: 各节点独立运行，本地采集、本地记账（单节点100%≥80%阈值）。网络恢复后自动通过链同步机制追赶缺失区块，数据零丢失。

### Q: FRU数据如何加密？

A: 后端使用 AES-256-CBC 加密（密钥由Web管理员密码SHA-256派生），前端使用浏览器原生 Web Crypto API 在本地解密。数据传输全程加密，密钥不离开服务器。

### Q: 为什么前端页面在国内加载快？

A: 前端完全摒弃了外部 CDN 依赖（之前的 CryptoJS CDN 在中国大陆不稳定），所有 JS 逻辑（包括 AES 解密、图表绘制）均使用浏览器原生 API 实现。

### Q: 如何扩容新机房节点？

A: 1) 在新机房服务器上部署客户端；2) 更新所有节点的 `peers` 配置，加入新节点信息；3) 重启所有节点使配置生效。新节点启动后自动从已有节点同步完整链数据。

### Q: 数据安全性如何保证？

A: 1) 私有封闭联盟链，仅白名单节点可接入；2) 所有数据上链存证，链式哈希防篡改；3) IPMI指令白名单机制，防止危险操作；4) FRU数据 AES-256 加密传输。

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

- 项目主页：https://github.com/Dzy-HW-XD/ChainMon
- 问题反馈：https://github.com/Dzy-HW-XD/ChainMon/issues

---

**⚠️ 免责声明**：本项目仅供学习和研究使用，生产环境部署前请充分测试。因使用本项目造成的任何损失，作者概不负责。
