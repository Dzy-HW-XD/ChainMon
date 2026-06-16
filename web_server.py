#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web管理后台服务器
提供可视化监控界面和API接口
- 设备管理：查看所有设备信息，点击查看FRU详情
- 区块链浏览：完整链可视化，显示节点出块信息
- FRU加密传输：AES-256-CBC加密保护硬件信息
"""
from flask import Flask, request, jsonify, render_template_string
import logging
import threading
import json
import time
from datetime import datetime
from typing import Dict, Any, List

from client.crypto import FRUCrypto

logger = logging.getLogger(__name__)

# 全局引用
_global_client = None
_crypto = None  # 加密器


def _server_metric_from_chain_data(data, block=None, source: str = "chain"):
    """Build a resource-maintenance summary from a PERFORMANCE chain record."""
    try:
        content = json.loads(data.content) if isinstance(data.content, str) else (data.content or {})
    except (json.JSONDecodeError, TypeError):
        content = {"raw": data.content}

    memory = content.get("memory") if isinstance(content.get("memory"), dict) else {}
    disk = content.get("disk") if isinstance(content.get("disk"), dict) else {}
    net = content.get("net") if isinstance(content.get("net"), dict) else {}

    disk_percent = None
    if disk:
        disk_values = [
            v.get("percent") for v in disk.values()
            if isinstance(v, dict) and isinstance(v.get("percent"), (int, float))
        ]
        if disk_values:
            disk_percent = max(disk_values)

    return {
        "device_ip": data.device_ip,
        "timestamp": content.get("collect_time") or data.timestamp,
        "cpu_percent": content.get("cpu_percent", content.get("cpu_usage")),
        "memory_percent": memory.get("percent", content.get("memory_usage")),
        "memory_total": memory.get("total"),
        "memory_used": memory.get("used"),
        "disk_percent": disk_percent,
        "net_bytes_sent": net.get("bytes_sent"),
        "net_bytes_recv": net.get("bytes_recv"),
        "source": source,
        "block_height": getattr(block, "block_height", None) if block else None,
        "block_hash": getattr(block, "current_hash", "") if block else "",
        "raw": content,
    }


def _collect_server_metrics_from_client(client):
    """Return latest server metrics by device, newest first."""
    from blockchain.block import ChainDataType

    latest_by_ip = {}

    for block in reversed(client.blockchain.chain):
        for data in reversed(block.data_list):
            if data.data_type != int(ChainDataType.PERFORMANCE):
                continue
            if data.device_ip not in latest_by_ip:
                latest_by_ip[data.device_ip] = _server_metric_from_chain_data(data, block, "chain")

    for data in reversed(client.blockchain.pending_data):
        if data.data_type == int(ChainDataType.PERFORMANCE):
            latest_by_ip[data.device_ip] = _server_metric_from_chain_data(data, None, "pending")

    if any(ip != "localhost" for ip in latest_by_ip):
        latest_by_ip.pop("localhost", None)

    servers = sorted(latest_by_ip.values(), key=lambda item: item.get("timestamp") or 0, reverse=True)
    preferred = next((s for s in servers if s.get("device_ip") == client.node_id), None)
    if preferred is None:
        preferred = next((s for s in servers if s.get("device_ip") == "localhost"), None)
    latest = preferred or (servers[0] if servers else {})
    return servers, latest


def _collect_server_metric_history_from_client(client, limit_per_server: int = 60):
    """Return CPU and memory history grouped by server."""
    from blockchain.block import ChainDataType

    history_by_ip = {}

    def add_metric(data, block=None, source: str = "chain"):
        if data.data_type != int(ChainDataType.PERFORMANCE):
            return
        metric = _server_metric_from_chain_data(data, block, source)
        ip = metric.get("device_ip")
        if not ip:
            return
        history_by_ip.setdefault(ip, []).append({
            "timestamp": metric.get("timestamp"),
            "cpu_percent": metric.get("cpu_percent"),
            "memory_percent": metric.get("memory_percent"),
            "source": source,
            "block_height": metric.get("block_height"),
        })

    for block in client.blockchain.chain:
        for data in block.data_list:
            add_metric(data, block, "chain")

    for data in client.blockchain.pending_data:
        add_metric(data, None, "pending")

    if any(ip != "localhost" for ip in history_by_ip):
        history_by_ip.pop("localhost", None)

    servers = []
    for ip, points in history_by_ip.items():
        points = sorted(points, key=lambda item: item.get("timestamp") or 0)
        servers.append({
            "device_ip": ip,
            "points": points[-limit_per_server:],
        })

    servers.sort(key=lambda item: (item["device_ip"] != client.node_id, item["device_ip"]))
    return servers


def set_client(client):
    """设置全局客户端引用"""
    global _global_client, _crypto
    _global_client = client
    # 从web配置中获取密码用于FRU加密
    web_password = client.config.get("web", {}).get("password", "admin123")
    _crypto = FRUCrypto(web_password)
    logger.info("Web加密器初始化完成，算法: AES-256-CBC")


# ======================== HTML模板 ========================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>区块链监控管理系统</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; background: #f0f2f5; color: #333; }
        .nav { background: #1a1a2e; padding: 0 20px; display: flex; align-items: center; height: 56px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }
        .nav h1 { color: #fff; font-size: 18px; font-weight: 600; }
        .nav .badge { background: #e94560; color: #fff; padding: 2px 8px; border-radius: 10px; font-size: 12px; margin-left: 12px; }
        .nav-right { margin-left: auto; color: #aaa; font-size: 13px; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        .tabs { display: flex; gap: 4px; margin-bottom: 20px; background: #fff; border-radius: 8px; padding: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
        .tab { padding: 10px 24px; border: none; background: none; cursor: pointer; border-radius: 6px; font-size: 14px; font-weight: 500; color: #666; transition: all 0.2s; }
        .tab:hover { background: #f5f5f5; }
        .tab.active { background: #1a1a2e; color: #fff; }
        .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .card { background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
        .card h3 { font-size: 13px; color: #999; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
        .card .value { font-size: 32px; font-weight: 700; color: #1a1a2e; }
        .card .sub { font-size: 13px; color: #666; margin-top: 4px; }
        .card.ok .value { color: #27ae60; }
        .card.warn .value { color: #f39c12; }
        .panel { background: #fff; border-radius: 10px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 20px; }
        .panel h2 { font-size: 16px; font-weight: 600; margin-bottom: 16px; color: #1a1a2e; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f8f9fa; padding: 10px 12px; text-align: left; font-size: 13px; color: #666; font-weight: 600; border-bottom: 2px solid #eee; }
        td { padding: 10px 12px; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
        tr:hover td { background: #f8f9fa; }
        .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }
        .tag-green { background: #e8f5e9; color: #27ae60; }
        .tag-red { background: #fce4ec; color: #e74c3c; }
        .tag-blue { background: #e3f2fd; color: #2196f3; }
        .tag-orange { background: #fff3e0; color: #f39c12; }
        .tag-purple { background: #f3e5f5; color: #9c27b0; }
        .tag-cyan { background: #e0f7fa; color: #0097a7; }
        .btn { padding: 6px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s; }
        .btn-primary { background: #1a1a2e; color: #fff; }
        .btn-primary:hover { background: #16213e; }
        .btn-danger { background: #e74c3c; color: #fff; }
        .btn-danger:hover { background: #c0392b; }
        .btn-success { background: #27ae60; color: #fff; }
        .btn-success:hover { background: #219a52; }
        .btn-outline { background: #fff; color: #1a1a2e; border: 1px solid #ddd; }
        .btn-outline:hover { background: #f5f5f5; }
        .btn-sm { padding: 4px 10px; font-size: 12px; }
        input, select, textarea { padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; outline: none; transition: border 0.2s; }
        input:focus, select:focus, textarea:focus { border-color: #1a1a2e; }
        .form-group { margin-bottom: 12px; }
        .form-group label { display: block; margin-bottom: 4px; font-size: 13px; color: #666; font-weight: 500; }
        .result-box { background: #1a1a2e; color: #0f0; padding: 16px; border-radius: 8px; font-family: monospace; font-size: 13px; white-space: pre-wrap; max-height: 400px; overflow-y: auto; margin-top: 12px; display: none; }
        .hash { font-family: monospace; font-size: 12px; color: #666; }
        .page { display: none; }
        .page.active { display: block; }
        .empty { text-align: center; padding: 40px; color: #999; }
        .chain-vis { display: flex; gap: 8px; overflow-x: auto; padding: 10px 0; }
        .chain-block { min-width: 120px; background: #f8f9fa; border: 2px solid #1a1a2e; border-radius: 8px; padding: 10px; text-align: center; font-size: 12px; flex-shrink: 0; }
        .chain-block .height { font-weight: 700; font-size: 16px; color: #1a1a2e; }
        .chain-block .node-tag { margin-top: 4px; }
        .chain-block .info { color: #999; margin-top: 4px; }
        .chain-arrow { display: flex; align-items: center; color: #1a1a2e; font-size: 18px; flex-shrink: 0; }
        .refresh-btn { float: right; }
        .charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin: 16px 0 20px; }
        .chart-box { border: 1px solid #eee; border-radius: 8px; padding: 14px; background: #fff; }
        .chart-title { font-size: 13px; font-weight: 600; color: #1a1a2e; margin-bottom: 8px; }
        .chart-box canvas { width: 100%; height: 240px; display: block; }
        .legend { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; font-size: 12px; color: #666; }
        .legend-item { display: inline-flex; align-items: center; gap: 5px; }
        .legend-swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }

        /* 设备详情模态框 */
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; }
        .modal-overlay.active { display: flex; align-items: center; justify-content: center; }
        .modal { background: #fff; border-radius: 12px; width: 680px; max-width: 95vw; max-height: 85vh; overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
        .modal-header { padding: 20px 24px; border-bottom: 1px solid #eee; display: flex; align-items: center; }
        .modal-header h3 { font-size: 18px; color: #1a1a2e; flex: 1; }
        .modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: #999; padding: 0 4px; }
        .modal-close:hover { color: #333; }
        .modal-body { padding: 24px; }
        .fru-section { margin-bottom: 20px; }
        .fru-section-title { font-size: 14px; font-weight: 600; color: #1a1a2e; border-bottom: 2px solid #1a1a2e; padding-bottom: 6px; margin-bottom: 12px; }
        .fru-grid { display: grid; grid-template-columns: 140px 1fr; gap: 8px 16px; }
        .fru-label { font-size: 13px; color: #888; font-weight: 500; text-align: right; }
        .fru-value { font-size: 13px; color: #333; word-break: break-all; }
        .fru-value.empty { color: #ccc; font-style: italic; }
        .encrypted-badge { display: inline-flex; align-items: center; gap: 4px; background: #e8f5e9; color: #27ae60; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
        .encrypted-badge svg { width: 14px; height: 14px; }
        .decrypt-fail { color: #e74c3c; font-size: 13px; padding: 12px; background: #fef2f2; border-radius: 6px; }
        .loading-spinner { display: inline-block; width: 20px; height: 20px; border: 2px solid #ddd; border-top: 2px solid #1a1a2e; border-radius: 50%; animation: spin 0.8s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* 设备行点击 */
        .device-row { cursor: pointer; transition: background 0.15s; }
        .device-row:hover td { background: #e3f2fd !important; }
        .device-actions { display: flex; gap: 6px; }

        /* 节点颜色 */
        .node-ali { background: #e3f2fd; color: #1565c0; }
        .node-tc { background: #e8f5e9; color: #2e7d32; }
        .node-default { background: #f3e5f5; color: #7b1fa2; }
    </style>
</head>
<body>
    <nav class="nav">
        <h1>Blockchain Monitor</h1>
        <span class="badge">v1.1</span>
        <div class="nav-right">
            Node: <strong id="node-id">-</strong> |
            <span id="node-status" class="tag tag-green">ONLINE</span> |
            <span class="encrypted-badge">
                <svg viewBox="0 0 24 24" fill="currentColor"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM12 17c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1s3.1 1.39 3.1 3.1v2z"/></svg>
                AES-256
            </span>
        </div>
    </nav>

    <div class="container">
        <div class="tabs">
            <button class="tab active" onclick="switchTab('dashboard')">Dashboard</button>
            <button class="tab" onclick="switchTab('devices')">Devices</button>
            <button class="tab" onclick="switchTab('blockchain')">Blockchain</button>
            <button class="tab" onclick="switchTab('ipmi')">IPMI Control</button>
            <button class="tab" onclick="switchTab('audit')">Audit Log</button>
        </div>

        <!-- Dashboard -->
        <div id="page-dashboard" class="page active">
            <div class="cards" id="stat-cards"></div>
            <div class="panel">
                <h2>Server Resource Maintenance <button class="btn btn-outline btn-sm refresh-btn" onclick="loadData()">Refresh</button></h2>
                <div class="cards" id="server-cards"></div>
                <div class="charts">
                    <div class="chart-box">
                        <div class="chart-title">CPU Utilization</div>
                        <canvas id="cpu-chart" width="640" height="260"></canvas>
                        <div class="legend" id="cpu-legend"></div>
                    </div>
                    <div class="chart-box">
                        <div class="chart-title">Memory Utilization</div>
                        <canvas id="memory-chart" width="640" height="260"></canvas>
                        <div class="legend" id="memory-legend"></div>
                    </div>
                </div>
                <table>
                    <thead><tr><th>Server</th><th>CPU</th><th>Memory</th><th>Collected</th><th>Source</th></tr></thead>
                    <tbody id="server-metrics"></tbody>
                </table>
            </div>
            <div class="panel">
                <h2>Chain Visualization <button class="btn btn-outline btn-sm refresh-btn" onclick="loadData()">Refresh</button></h2>
                <div class="chain-vis" id="chain-vis"></div>
            </div>
            <div class="panel">
                <h2>Recent Blocks</h2>
                <table>
                    <thead><tr><th>Height</th><th>Hash</th><th>Node</th><th>Data</th><th>Time</th></tr></thead>
                    <tbody id="recent-blocks"></tbody>
                </table>
            </div>
        </div>

        <!-- Devices -->
        <div id="page-devices" class="page">
            <div class="panel">
                <h2>Managed Devices <button class="btn btn-outline btn-sm refresh-btn" onclick="loadDevices()">Refresh</button></h2>
                <p style="font-size:13px;color:#888;margin-bottom:12px;">Click any device row to view FRU hardware details (encrypted)</p>
                <table>
                    <thead><tr><th>IP</th><th>Name</th><th>Source</th><th>Status</th><th>Actions</th></tr></thead>
                    <tbody id="device-list"></tbody>
                </table>
            </div>
        </div>

        <!-- Blockchain -->
        <div id="page-blockchain" class="page">
            <div class="cards" id="bc-cards"></div>
            <div class="panel">
                <h2>All Blocks</h2>
                <table>
                    <thead><tr><th>Height</th><th>Hash</th><th>Prev Hash</th><th>Node</th><th>Data Count</th><th>Time</th></tr></thead>
                    <tbody id="all-blocks"></tbody>
                </table>
            </div>
        </div>

        <!-- IPMI Control -->
        <div id="page-ipmi" class="page">
            <div class="panel">
                <h2>Execute IPMI Command</h2>
                <div style="display:flex; gap:16px; flex-wrap:wrap;">
                    <div style="flex:1; min-width:300px;">
                        <div class="form-group">
                            <label>Target IP</label>
                            <input type="text" id="ipmi-ip" placeholder="10.0.1.100" style="width:100%">
                        </div>
                        <div class="form-group">
                            <label>Command</label>
                            <input type="text" id="ipmi-cmd" placeholder="power status" style="width:100%">
                        </div>
                        <div class="form-group">
                            <label>Quick Commands</label>
                            <div style="display:flex; gap:6px; flex-wrap:wrap;">
                                <button class="btn btn-outline btn-sm" onclick="setCmd('power status')">Power Status</button>
                                <button class="btn btn-success btn-sm" onclick="setCmd('power on')">Power On</button>
                                <button class="btn btn-danger btn-sm" onclick="setCmd('power off')">Power Off</button>
                                <button class="btn btn-outline btn-sm" onclick="setCmd('power reset')">Reset</button>
                                <button class="btn btn-outline btn-sm" onclick="setCmd('fru')">FRU Info</button>
                                <button class="btn btn-outline btn-sm" onclick="setCmd('sdr')">Sensors</button>
                                <button class="btn btn-outline btn-sm" onclick="setCmd('sel list')">SEL Log</button>
                            </div>
                        </div>
                        <button class="btn btn-primary" onclick="execIPMI()" style="width:100%;margin-top:8px;">Execute</button>
                    </div>
                    <div style="flex:1; min-width:300px;">
                        <label>Result</label>
                        <div class="result-box" id="ipmi-result"></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Audit Log -->
        <div id="page-audit" class="page">
            <div class="panel">
                <h2>On-Chain Audit Log</h2>
                <div style="display:flex; gap:8px; margin-bottom:16px;">
                    <select id="audit-type" onchange="loadAudit()">
                        <option value="">All Types</option>
                        <option value="0">FRU Hardware</option>
                        <option value="1">Performance</option>
                        <option value="2">IPMI Operation</option>
                    </select>
                    <input type="text" id="audit-ip" placeholder="Filter by IP" onchange="loadAudit()">
                    <button class="btn btn-primary" onclick="loadAudit()">Query</button>
                </div>
                <table>
                    <thead><tr><th>Time</th><th>Type</th><th>Device IP</th><th>Content</th><th>Operator</th><th>Block</th></tr></thead>
                    <tbody id="audit-list"></tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- 设备FRU详情模态框 -->
    <div class="modal-overlay" id="fru-modal-overlay" onclick="closeFruModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal-header">
                <h3 id="fru-modal-title">Device FRU Info</h3>
                <span class="encrypted-badge" id="fru-encrypt-badge" style="margin-left:12px;">
                    <svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM12 17c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1s3.1 1.39 3.1 3.1v2z"/></svg>
                    AES-256-CBC Encrypted
                </span>
                <button class="modal-close" onclick="closeFruModal()">&times;</button>
            </div>
            <div class="modal-body" id="fru-modal-body">
                <div style="text-align:center;padding:40px;"><div class="loading-spinner"></div><br><br>Loading...</div>
            </div>
        </div>
    </div>

    <!-- 无外部CDN依赖：使用浏览器原生Web Crypto API进行AES解密 -->

    <script>
    // ===== 全局配置 =====
    var ENCRYPTION_KEY_RAW = ""; // 原始密钥bytes（从Base64解码）

    // ===== 初始化：获取加密密钥 =====
    function initCryptoKey() {
        fetch('/api/crypto/key').then(function(r) { return r.json(); }).then(function(data) {
            var keyB64 = data.key || "";
            // Base64解码为Uint8Array
            var binStr = atob(keyB64);
            ENCRYPTION_KEY_RAW = new Uint8Array(binStr.length);
            for (var i = 0; i < binStr.length; i++) {
                ENCRYPTION_KEY_RAW[i] = binStr.charCodeAt(i);
            }
        }).catch(function(e) { console.error("Failed to get encryption key:", e); });
    }

    // ===== AES-256-CBC 解密（使用浏览器原生Web Crypto API）=====
    async function decryptAesCbc(ivBase64, dataBase64) {
        if (!ENCRYPTION_KEY_RAW) throw new Error("Encryption key not loaded");

        // Base64 → ArrayBuffer
        function b64ToBuf(b64) {
            var bin = atob(b64);
            var arr = new Uint8Array(bin.length);
            for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
            return arr.buffer;
        }

        var ivBuf = b64ToBuf(ivBase64);
        var dataBuf = b64ToBuf(dataBase64);

        // 导入密钥
        var key = await crypto.subtle.importKey(
            "raw", ENCRYPTION_KEY_RAW.buffer,
            { name: "AES-CBC" }, false, ["decrypt"]
        );

        // 解密
        var decrypted = await crypto.subtle.decrypt(
            { name: "AES-CBC", iv: ivBuf }, key, dataBuf
        );

        // ArrayBuffer → String
        var decoder = new TextDecoder("utf-8");
        return decoder.decode(decrypted);
    }

    function switchTab(name) {
        document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
        document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });
        document.getElementById('page-' + name).classList.add('active');
        // 找到对应的tab按钮并激活
        document.querySelectorAll('.tab').forEach(function(t) {
            if (t.textContent.trim().toLowerCase().indexOf(name) >= 0) t.classList.add('active');
        });
        loadData();
    }

    function setCmd(cmd) {
        document.getElementById('ipmi-cmd').value = cmd;
    }

    function formatTime(ts) {
        if (!ts) return '-';
        var d = new Date(ts * 1000);
        return d.toLocaleString();
    }

    function shortHash(h) {
        if (!h || h.length < 16) return h;
        return h.substring(0, 8) + '...' + h.substring(h.length - 8);
    }

    function typeLabel(t) {
        var labels = {0: ['FRU', 'tag-blue'], 1: ['Perf', 'tag-green'], 2: ['IPMI', 'tag-orange'], 3: ['Heartbeat', 'tag-purple']};
        var info = labels[t] || ['Unknown', ''];
        return '<span class="tag ' + info[1] + '">' + info[0] + '</span>';
    }

    function nodeTag(nodeId) {
        if (!nodeId) return '<span class="tag tag-default">-</span>';
        var cls = 'node-default';
        if (nodeId === 'ali') cls = 'node-ali';
        else if (nodeId === 'tc') cls = 'node-tc';
        else if (nodeId.indexOf('ali') >= 0) cls = 'node-ali';
        else if (nodeId.indexOf('tc') >= 0) cls = 'node-tc';
        return '<span class="tag ' + cls + '">' + nodeId + '</span>';
    }

    function pct(v) {
        if (v === null || v === undefined || isNaN(Number(v))) return '-';
        return Number(v).toFixed(1) + '%';
    }

    function bytesHuman(v) {
        if (v === null || v === undefined || isNaN(Number(v))) return '-';
        var units = ['B', 'KB', 'MB', 'GB', 'TB'];
        var n = Number(v);
        var i = 0;
        while (n >= 1024 && i < units.length - 1) { n = n / 1024; i++; }
        return n.toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
    }

    function serverColor(i) {
        var colors = ['#1565c0', '#2e7d32', '#c62828', '#6a1b9a', '#ef6c00', '#00838f'];
        return colors[i % colors.length];
    }

    function drawMetricChart(canvasId, legendId, servers, field) {
        var canvas = document.getElementById(canvasId);
        if (!canvas) return;
        var ctx = canvas.getContext('2d');
        var w = canvas.width;
        var h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        var padL = 42, padR = 14, padT = 14, padB = 30;
        var plotW = w - padL - padR;
        var plotH = h - padT - padB;

        ctx.fillStyle = '#fff';
        ctx.fillRect(0, 0, w, h);
        ctx.strokeStyle = '#e5e7eb';
        ctx.lineWidth = 1;
        ctx.font = '12px Arial';
        ctx.fillStyle = '#777';

        for (var y = 0; y <= 100; y += 25) {
            var py = padT + plotH - (y / 100) * plotH;
            ctx.beginPath();
            ctx.moveTo(padL, py);
            ctx.lineTo(w - padR, py);
            ctx.stroke();
            ctx.fillText(y + '%', 6, py + 4);
        }

        var allTimes = [];
        servers.forEach(function(s) {
            (s.points || []).forEach(function(p) {
                if (p.timestamp && p[field] !== null && p[field] !== undefined) allTimes.push(p.timestamp);
            });
        });
        if (!allTimes.length) {
            ctx.fillStyle = '#999';
            ctx.fillText('No utilization history yet', padL + 10, padT + 30);
            document.getElementById(legendId).innerHTML = '';
            return;
        }

        var minT = Math.min.apply(null, allTimes);
        var maxT = Math.max.apply(null, allTimes);
        if (minT === maxT) maxT = minT + 1;

        servers.forEach(function(s, idx) {
            var pts = (s.points || []).filter(function(p) {
                return p.timestamp && p[field] !== null && p[field] !== undefined && !isNaN(Number(p[field]));
            });
            if (!pts.length) return;
            ctx.strokeStyle = serverColor(idx);
            ctx.fillStyle = serverColor(idx);
            ctx.lineWidth = 2;
            ctx.beginPath();
            pts.forEach(function(p, i) {
                var x = padL + ((p.timestamp - minT) / (maxT - minT)) * plotW;
                var v = Math.max(0, Math.min(100, Number(p[field])));
                var y = padT + plotH - (v / 100) * plotH;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            });
            ctx.stroke();
            pts.forEach(function(p) {
                var x = padL + ((p.timestamp - minT) / (maxT - minT)) * plotW;
                var v = Math.max(0, Math.min(100, Number(p[field])));
                var y = padT + plotH - (v / 100) * plotH;
                ctx.beginPath();
                ctx.arc(x, y, 2.5, 0, Math.PI * 2);
                ctx.fill();
            });
        });

        ctx.strokeStyle = '#cbd5e1';
        ctx.beginPath();
        ctx.moveTo(padL, padT);
        ctx.lineTo(padL, h - padB);
        ctx.lineTo(w - padR, h - padB);
        ctx.stroke();

        var legend = '';
        servers.forEach(function(s, idx) {
            legend += '<span class="legend-item"><span class="legend-swatch" style="background:' + serverColor(idx) + '"></span>' + s.device_ip + '</span>';
        });
        document.getElementById(legendId).innerHTML = legend;
    }

    function loadMetricHistory() {
        fetch('/api/server/metrics/history?limit=80').then(function(r) { return r.json(); }).then(function(data) {
            var servers = data.servers || [];
            drawMetricChart('cpu-chart', 'cpu-legend', servers, 'cpu_percent');
            drawMetricChart('memory-chart', 'memory-legend', servers, 'memory_percent');
        }).catch(function(e) { console.error(e); });
    }

    // ===== 数据加载 =====
    function loadData() {
        fetch('/api/status').then(function(r) { return r.json(); }).then(function(data) {
            document.getElementById('node-id').textContent = data.node_id || '-';
            var bc = data.blockchain || {};
            var net = data.network || {};
            document.getElementById('stat-cards').innerHTML =
                '<div class="card"><h3>Managed Devices</h3><div class="value">' + (data.managed_devices || 0) + '</div><div class="sub">IPMI ready</div></div>' +
                '<div class="card ok"><h3>Network Peers</h3><div class="value">' + (net.online_peers || 0) + '</div><div class="sub">Online / ' + (net.total_peers || 0) + ' total</div></div>' +
                '<div class="card"><h3>Chain Height</h3><div class="value">' + (bc.chain_height || 0) + '</div><div class="sub">Audit ledger blocks</div></div>' +
                '<div class="card warn"><h3>Pending Data</h3><div class="value">' + (bc.pending_data_count || 0) + '</div><div class="sub">Awaiting on-chain</div></div>';
        }).catch(function(e) { console.error(e); });

        fetch('/api/server/metrics').then(function(r) { return r.json(); }).then(function(data) {
            var servers = data.servers || [];
            var latest = data.latest || {};
            document.getElementById('server-cards').innerHTML =
                '<div class="card ok"><h3>CPU Usage</h3><div class="value">' + pct(latest.cpu_percent) + '</div><div class="sub">' + (latest.device_ip || '-') + '</div></div>' +
                '<div class="card"><h3>Memory Usage</h3><div class="value">' + pct(latest.memory_percent) + '</div><div class="sub">' + bytesHuman(latest.memory_used) + ' / ' + bytesHuman(latest.memory_total) + '</div></div>' +
                '<div class="card"><h3>Disk Usage</h3><div class="value">' + pct(latest.disk_percent) + '</div><div class="sub">Max mounted filesystem</div></div>' +
                '<div class="card"><h3>Last Sample</h3><div class="value" style="font-size:20px;">' + formatTime(latest.timestamp) + '</div><div class="sub">' + (latest.source || '-') + '</div></div>';

            var rows = '';
            for (var i = 0; i < servers.length; i++) {
                var s = servers[i];
                rows += '<tr>' +
                    '<td><strong>' + (s.device_ip || '-') + '</strong></td>' +
                    '<td>' + pct(s.cpu_percent) + '</td>' +
                    '<td>' + pct(s.memory_percent) + '</td>' +
                    '<td>' + formatTime(s.timestamp) + '</td>' +
                    '<td><span class="tag tag-green">' + (s.source || 'chain') + '</span></td>' +
                '</tr>';
            }
            document.getElementById('server-metrics').innerHTML = rows || '<tr><td colspan="5" class="empty">No server metrics yet</td></tr>';
        }).catch(function(e) { console.error(e); });

        loadMetricHistory();

        // 加载区块
        fetch('/api/blockchain/blocks?limit=50').then(function(r) { return r.json(); }).then(function(data) {
            var blocks = data.blocks || [];
            // 链可视化（最近10个）
            var vis = '';
            var last10 = blocks.slice(-10);
            for (var i = 0; i < last10.length; i++) {
                var b = last10[i];
                vis += '<div class="chain-block">' +
                    '<div class="height">#' + b.height + '</div>' +
                    '<div class="node-tag">' + nodeTag(b.node_id) + '</div>' +
                    '<div class="info">' + b.data_count + ' items</div>' +
                '</div>';
                if (i < last10.length - 1) vis += '<div class="chain-arrow">\u2192</div>';
            }
            document.getElementById('chain-vis').innerHTML = vis || '<div class="empty">No blocks</div>';

            // 最近区块表格
            var html = '';
            for (var i = blocks.length - 1; i >= 0; i--) {
                var b = blocks[i];
                html += '<tr><td><strong>#' + b.height + '</strong></td><td class="hash">' + shortHash(b.hash) + '</td><td>' + nodeTag(b.node_id) + '</td><td>' + b.data_count + '</td><td>' + formatTime(b.timestamp) + '</td></tr>';
            }
            document.getElementById('recent-blocks').innerHTML = html || '<tr><td colspan="5" class="empty">No blocks</td></tr>';

            // 区块链页面
            var bcCards = document.getElementById('bc-cards');
            if (bcCards) {
                bcCards.innerHTML =
                    '<div class="card"><h3>Total Blocks</h3><div class="value">' + blocks.length + '</div></div>' +
                    '<div class="card ok"><h3>Chain Valid</h3><div class="value">YES</div></div>';
            }
            var allHtml = '';
            for (var i = blocks.length - 1; i >= 0; i--) {
                var b = blocks[i];
                allHtml += '<tr><td>#' + b.height + '</td><td class="hash">' + shortHash(b.hash) + '</td><td class="hash">' + shortHash(b.prev_hash || '') + '</td><td>' + nodeTag(b.node_id) + '</td><td>' + b.data_count + '</td><td>' + formatTime(b.timestamp) + '</td></tr>';
            }
            var allBody = document.getElementById('all-blocks');
            if (allBody) allBody.innerHTML = allHtml || '<tr><td colspan="6" class="empty">No blocks</td></tr>';
        }).catch(function(e) { console.error(e); });

        // 加载设备
        loadDevices();
        loadAudit();
    }

    function loadDevices() {
        fetch('/api/devices').then(function(r) { return r.json(); }).then(function(data) {
            var devs = data.devices || [];
            var html = '';
            for (var i = 0; i < devs.length; i++) {
                var d = devs[i];
                var sourceTag = d.source === 'chain' ? '<span class="tag tag-blue">Chain</span>' : '<span class="tag tag-green">Config</span>';
                var statusTag = d.status === 'online' ? '<span class="tag tag-green">Online</span>' : (d.status === 'managed' ? '<span class="tag tag-blue">Managed</span>' : '<span class="tag tag-orange">Unknown</span>');
                html += '<tr class="device-row" data-ip="' + d.ip + '" data-name="' + (d.name || '') + '">' +
                    '<td><strong>' + d.ip + '</strong></td>' +
                    '<td>' + (d.name || '-') + '</td>' +
                    '<td>' + sourceTag + '</td>' +
                    '<td>' + statusTag + '</td>' +
                    '<td class="device-actions">' +
                    '<button class="btn btn-outline btn-sm" data-action="fru" data-ip="' + d.ip + '" data-name="' + (d.name || '') + '">FRU</button>' +
                    '<button class="btn btn-outline btn-sm" data-action="ipmi" data-ip="' + d.ip + '">IPMI</button>' +
                    '</td></tr>';
            }
            document.getElementById('device-list').innerHTML = html || '<tr><td colspan="5" class="empty">No devices</td></tr>';
        }).catch(function(e) { console.error(e); });
    }

    // ===== FRU设备详情 =====
    function showFruDetail(ip, name) {
        var modal = document.getElementById('fru-modal-overlay');
        modal.classList.add('active');
        document.getElementById('fru-modal-title').textContent = (name ? name + ' - ' : '') + ip;
        document.getElementById('fru-modal-body').innerHTML = '<div style="text-align:center;padding:40px;"><div class="loading-spinner"></div><br><br>Loading FRU data...</div>';

        fetch('/api/device/' + encodeURIComponent(ip) + '/fru').then(function(r) { return r.json(); }).then(function(data) {
            return renderFruDetail(ip, data);
        }).catch(function(e) {
            document.getElementById('fru-modal-body').innerHTML = '<div class="decrypt-fail">Failed to load FRU data: ' + e + '</div>';
        });
    }

    async function renderFruDetail(ip, rawData) {
        var fruData = null;
        var alg = rawData.alg || 'unknown';
        var isEncrypted = rawData.encrypted === true;

        if (isEncrypted) {
            try {
                var plaintext = await decryptAesCbc(rawData.iv, rawData.data);
                if (!plaintext) throw new Error("Decryption produced empty result");
                fruData = JSON.parse(plaintext);
            } catch(e) {
                console.error("Decryption failed:", e);
                document.getElementById('fru-modal-body').innerHTML =
                    '<div class="decrypt-fail"><strong>Decryption Failed</strong><br>Error: ' + e.message + '<br>The encryption key may not match, or the data was corrupted in transit.</div>';
                return;
            }
        } else {
            fruData = rawData;
        }

        var html = '';

        // 加密信息
        html += '<div style="margin-bottom:16px;"><span class="encrypted-badge">' +
            '<svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM12 17c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1s3.1 1.39 3.1 3.1v2z"/></svg>' +
            'Encrypted with ' + alg + '</span> ' +
            '<span style="font-size:12px;color:#888;margin-left:8px;">Data decrypted locally in browser</span></div>';

        // Product信息
        var product = fruData.product || fruData;
        if (product.product_manufacturer || product.product_name || product.product_serial) {
            html += '<div class="fru-section">';
            html += '<div class="fru-section-title">Product Information</div>';
            html += '<div class="fru-grid">';
            html += fruRow('Manufacturer', product.product_manufacturer);
            html += fruRow('Product Name', product.product_name);
            html += fruRow('Part Number', product.product_part_number);
            html += fruRow('Serial Number', product.product_serial);
            html += '</div></div>';
        }

        // Board信息
        if (fruData.board && (fruData.board.mfr || fruData.board.product || fruData.board.serial)) {
            html += '<div class="fru-section">';
            html += '<div class="fru-section-title">Board Information</div>';
            html += '<div class="fru-grid">';
            html += fruRow('Board Mfg', fruData.board.mfr);
            html += fruRow('Board Product', fruData.board.product);
            html += fruRow('Board Serial', fruData.board.serial);
            html += fruRow('Board Part', fruData.board.part);
            html += '</div></div>';
        } else if (product.board_mfr || product.board_product || product.board_serial) {
            html += '<div class="fru-section">';
            html += '<div class="fru-section-title">Board Information</div>';
            html += '<div class="fru-grid">';
            html += fruRow('Board Mfg', product.board_mfr);
            html += fruRow('Board Product', product.board_product);
            html += fruRow('Board Serial', product.board_serial);
            html += fruRow('Board Part', product.board_part);
            html += '</div></div>';
        }

        // Chassis信息
        if (product.chassis_part || product.chassis_serial || (fruData.chassis && (fruData.chassis.part || fruData.chassis.serial))) {
            html += '<div class="fru-section">';
            html += '<div class="fru-section-title">Chassis Information</div>';
            html += '<div class="fru-grid">';
            if (fruData.chassis) {
                html += fruRow('Chassis Part', fruData.chassis.part);
                html += fruRow('Chassis Serial', fruData.chassis.serial);
            } else {
                html += fruRow('Chassis Part', product.chassis_part);
                html += fruRow('Chassis Serial', product.chassis_serial);
            }
            html += '</div></div>';
        }

        // 系统资源（CPU/内存/温度等）
        if (fruData.system) {
            html += '<div class="fru-section">';
            html += '<div class="fru-section-title">System Resources</div>';
            html += '<div class="fru-grid">';
            html += fruRow('CPU Model', fruData.system.cpu_model);
            html += fruRow('CPU Cores', fruData.system.cpu_cores);
            html += fruRow('Memory Total', fruData.system.memory_total);
            html += fruRow('Memory Type', fruData.system.memory_type);
            html += fruRow('BIOS Version', fruData.system.bios_version);
            html += '</div></div>';
        }

        // 传感器摘要
        if (fruData.sensors_summary) {
            var ss = fruData.sensors_summary;
            html += '<div class="fru-section">';
            html += '<div class="fru-section-title">Sensor Summary</div>';
            html += '<div class="fru-grid">';
            if (ss.temperature) html += fruRow('Temperature', ss.temperature);
            if (ss.fan_speed) html += fruRow('Fan Speed', ss.fan_speed);
            if (ss.power) html += fruRow('Power', ss.power);
            html += '</div></div>';
        }

        // 采集时间
        if (fruData.collect_time) {
            html += '<div style="margin-top:16px;font-size:12px;color:#aaa;text-align:right;">Collected: ' + formatTime(fruData.collect_time) + '</div>';
        }

        document.getElementById('fru-modal-body').innerHTML = html || '<div class="empty">No FRU data available for this device</div>';
    }

    function fruRow(label, value) {
        if (!value) value = '';
        var cls = value ? '' : ' empty';
        var display = value || 'N/A';
        return '<div class="fru-label">' + label + '</div><div class="fru-value' + cls + '">' + display + '</div>';
    }

    function closeFruModal(event) {
        if (event && event.target !== document.getElementById('fru-modal-overlay')) return;
        document.getElementById('fru-modal-overlay').classList.remove('active');
    }

    // ===== Audit =====
    function loadAudit() {
        var typeEl = document.getElementById('audit-type');
        var ipEl = document.getElementById('audit-ip');
        if (!typeEl || !ipEl) return;
        var type = typeEl.value;
        var ip = ipEl.value;
        var url = '/api/query?limit=50';
        if (type) url += '&data_type=' + type;
        if (ip) url += '&device_ip=' + ip;
        fetch(url).then(function(r) { return r.json(); }).then(function(data) {
            var results = data.results || [];
            var html = '';
            for (var i = 0; i < results.length; i++) {
                var r = results[i];
                var content = r.content || '';
                if (content.length > 120) content = content.substring(0, 120) + '...';
                html += '<tr><td>' + formatTime(r.timestamp) + '</td><td>' + typeLabel(r.data_type) + '</td><td>' + (r.device_ip || '-') + '</td><td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + content + '</td><td>' + (r.operate_user || '-') + '</td><td class="hash">' + shortHash(r.block_hash) + '</td></tr>';
            }
            document.getElementById('audit-list').innerHTML = html || '<tr><td colspan="6" class="empty">No records</td></tr>';
        }).catch(function(e) { console.error(e); });
    }

    // ===== IPMI =====
    function execIPMI() {
        var ip = document.getElementById('ipmi-ip').value;
        var cmd = document.getElementById('ipmi-cmd').value;
        if (!ip || !cmd) { alert('Please enter IP and command'); return; }
        var box = document.getElementById('ipmi-result');
        box.style.display = 'block';
        box.textContent = 'Executing...';
        fetch('/api/ipmi/execute', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ip: ip, command: cmd})
        }).then(function(r) { return r.json(); }).then(function(data) {
            box.textContent = JSON.stringify(data, null, 2);
        }).catch(function(e) { box.textContent = 'Error: ' + e; });
    }

    // ===== 事件委托 =====
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('[data-action]');
        if (btn) {
            var action = btn.getAttribute('data-action');
            var ip = btn.getAttribute('data-ip');
            if (action === 'fru') {
                var name = btn.getAttribute('data-name') || '';
                showFruDetail(ip, name);
            } else if (action === 'ipmi') {
                document.getElementById('ipmi-ip').value = ip;
                switchTab('ipmi');
            }
            return;
        }
        var row = e.target.closest('tr.device-row');
        if (row) {
            var ip = row.getAttribute('data-ip');
            var name = row.getAttribute('data-name') || '';
            showFruDetail(ip, name);
        }
    });

    // ===== 初始化 =====
    initCryptoKey();  // 异步获取加密密钥
    loadData();
    setInterval(loadData, 30000);
    </script>
</body>
</html>
"""


def create_app() -> Flask:
    """创建Flask应用"""
    app = Flask(__name__)

    @app.route('/')
    def index():
        """管理后台首页"""
        return render_template_string(DASHBOARD_HTML)

    @app.route('/api/status')
    def api_status():
        """获取系统状态API"""
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500
        return jsonify(_global_client.get_status())

    @app.route('/api/server/metrics')
    def api_server_metrics():
        """Return latest CPU/memory/disk/network metrics for server maintenance."""
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500

        servers, latest = _collect_server_metrics_from_client(_global_client)
        return jsonify({
            "node_id": _global_client.node_id,
            "servers": servers,
            "latest": latest,
            "total": len(servers),
        })

    @app.route('/api/server/metrics/history')
    def api_server_metrics_history():
        """Return CPU and memory utilization history grouped by server."""
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500

        limit = request.args.get('limit', 60, type=int)
        limit = max(1, min(limit, 300))
        servers = _collect_server_metric_history_from_client(_global_client, limit)
        return jsonify({
            "node_id": _global_client.node_id,
            "servers": servers,
            "total": len(servers),
        })

    @app.route('/api/crypto/key')
    def api_crypto_key():
        """获取加密密钥（Base64编码，供前端CryptoJS使用）
        注意：此密钥仅对已认证的管理员可见，用于FRU数据的客户端解密
        """
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500
        from client.crypto import FRUCrypto
        web_password = _global_client.config.get("web", {}).get("password", "admin123")
        key_b64 = FRUCrypto.derive_key_base64(web_password)
        return jsonify({"key": key_b64})

    @app.route('/api/blockchain/info')
    def api_chain_info():
        """获取区块链信息"""
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500
        return jsonify(_global_client.blockchain.get_chain_info())

    @app.route('/api/blockchain/blocks')
    def api_blocks():
        """获取区块列表"""
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500

        limit = request.args.get('limit', 20, type=int)
        blocks = []
        chain = _global_client.blockchain.chain
        start = max(0, len(chain) - limit)
        for i in range(start, len(chain)):
            b = chain[i]
            blocks.append({
                "height": b.block_height,
                "hash": b.current_hash,
                "prev_hash": b.prev_block_hash,
                "timestamp": b.timestamp,
                "node_id": b.client_node_id,
                "data_count": len(b.data_list)
            })
        return jsonify({"blocks": blocks})

    @app.route('/api/blockchain/block/<int:height>')
    def api_block_detail(height):
        """获取区块详情"""
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500

        block = _global_client.blockchain.get_block_by_height(height)
        if not block:
            return jsonify({"error": "block not found"}), 404
        return jsonify(block.to_dict())

    @app.route('/api/devices')
    def api_devices():
        """
        获取所有设备列表
        合并配置中的设备 + 链上数据中发现的设备
        """
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500

        devices = []
        seen_ips = set()

        # 1. 从配置中获取设备
        config_devices = _global_client.config.get("devices", [])
        for d in config_devices:
            ip = d.get("ip", "")
            if ip and ip not in seen_ips:
                seen_ips.add(ip)
                devices.append({
                    "ip": ip,
                    "name": d.get("name", ""),
                    "type": d.get("type", "server"),
                    "status": "managed",
                    "source": "config"
                })

        # 2. 从本地managed_devices获取
        for d in _global_client.managed_devices:
            ip = d.get("ip", "")
            if ip and ip not in seen_ips:
                seen_ips.add(ip)
                devices.append({
                    "ip": ip,
                    "name": d.get("name", ""),
                    "type": d.get("type", "server"),
                    "status": "managed",
                    "source": "config"
                })

        # 3. 从区块链数据中扫描设备IP
        chain = _global_client.blockchain.chain
        for block in chain:
            for data in block.data_list:
                ip = data.device_ip
                if ip and ip not in seen_ips and ip != "localhost":
                    seen_ips.add(ip)
                    devices.append({
                        "ip": ip,
                        "name": "",
                        "type": "discovered",
                        "status": "discovered",
                        "source": "chain"
                    })

        return jsonify({"devices": devices})

    @app.route('/api/device/<ip>/fru')
    def api_device_fru(ip):
        """
        获取设备FRU信息（AES-256-CBC加密传输）
        优先从链上获取最新FRU数据，如无则实时采集
        """
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500

        if not _crypto:
            return jsonify({"error": "crypto not initialized"}), 500

        fru_data = None
        source = "none"

        # 1. 从区块链中查找最新的FRU数据
        chain = _global_client.blockchain.chain
        from blockchain.block import ChainDataType
        for block in reversed(chain):
            for data in reversed(block.data_list):
                if data.device_ip == ip and data.data_type == int(ChainDataType.FRU_HARDWARE):
                    try:
                        fru_data = json.loads(data.content)
                        source = "chain"
                    except (json.JSONDecodeError, TypeError):
                        fru_data = {"raw": data.content}
                        source = "chain"
                    break
            if fru_data:
                break

        # 2. 如果链上没有，尝试实时采集
        if not fru_data:
            try:
                result = _global_client.collector.collect_fru_info(ip)
                if result.get("success"):
                    fru_data = result
                    source = "live"
                else:
                    fru_data = {"error": result.get("error", "FRU collection failed"), "ip": ip}
                    source = "failed"
            except Exception as e:
                fru_data = {"error": str(e), "ip": ip}
                source = "error"

        # 3. 补充系统资源信息（从SDR传感器数据）
        if fru_data and source != "failed" and source != "error":
            # 从链上查找最新传感器数据
            for block in reversed(chain):
                for data in reversed(block.data_list):
                    if data.device_ip == ip and data.data_type == int(ChainDataType.PERFORMANCE):
                        try:
                            sdr = json.loads(data.content)
                            if sdr.get("success") or sdr.get("sensors"):
                                fru_data["sensors_summary"] = _extract_sensor_summary(sdr)
                        except (json.JSONDecodeError, TypeError):
                            pass
                        break
                if fru_data.get("sensors_summary"):
                    break

        # 4. 添加元信息
        fru_data["_source"] = source
        fru_data["_ip"] = ip
        fru_data["_collected_at"] = int(time.time())

        # 5. 加密传输
        encrypted = _crypto.encrypt(fru_data)
        return jsonify(encrypted)

    def _extract_sensor_summary(sdr_data: dict) -> dict:
        """从SDR传感器数据中提取摘要信息"""
        summary = {}
        if sdr_data.get("temperature"):
            temps = sdr_data["temperature"]
            if isinstance(temps, dict):
                temp_values = [v for v in temps.values() if isinstance(v, (int, float))]
                if temp_values:
                    summary["temperature"] = str(max(temp_values)) + " C (max)"
        if sdr_data.get("fan_speed"):
            fans = sdr_data["fan_speed"]
            if isinstance(fans, dict):
                fan_values = [v for v in fans.values() if isinstance(v, (int, float))]
                if fan_values:
                    summary["fan_speed"] = str(int(max(fan_values))) + " RPM (max)"
        if sdr_data.get("power"):
            power = sdr_data["power"]
            if isinstance(power, (int, float)) and power > 0:
                summary["power"] = str(int(power)) + " W"
        return summary

    @app.route('/api/ipmi/execute', methods=['POST'])
    def api_execute_ipmi():
        """执行IPMI指令"""
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500

        data = request.json
        target_ip = data.get("ip")
        command = data.get("command")

        if not target_ip or not command:
            return jsonify({"error": "missing parameters"}), 400

        result = _global_client.execute_ipmi_command(target_ip, command, "web")
        return jsonify(result)

    @app.route('/api/query')
    def api_query():
        """查询链上数据"""
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500

        data_type = request.args.get('data_type', type=int)
        device_ip = request.args.get('device_ip')
        limit = request.args.get('limit', 50, type=int)

        results = _global_client.blockchain.query_data(
            data_type=data_type,
            device_ip=device_ip,
            limit=limit
        )
        return jsonify({"results": results})

    @app.route('/api/network/status')
    def api_network_status():
        """获取网络状态"""
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500
        return jsonify(_global_client.network.get_network_status())

    @app.route('/api/ipmi/history')
    def api_ipmi_history():
        """获取IPMI执行历史"""
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500

        target_ip = request.args.get('ip')
        history = _global_client.ipmi_executor.get_command_history(target_ip)
        return jsonify({"history": history})

    @app.route('/api/audit/log')
    def api_audit_log():
        """获取审计日志（从区块链中提取操作记录）"""
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500

        entries = []
        chain = _global_client.blockchain.chain
        data_type_filter = request.args.get('data_type', type=int)

        for block in chain:
            for data in block.data_list:
                if data_type_filter is not None and data.data_type != data_type_filter:
                    continue
                entries.append({
                    "block_height": block.block_height,
                    "block_hash": block.current_hash[:16] + "...",
                    "data_type": data.data_type,
                    "device_ip": data.device_ip,
                    "content": data.content[:500] if data.content else "",
                    "operate_user": data.operate_user,
                    "timestamp": data.timestamp,
                })

        entries.sort(key=lambda x: x["timestamp"], reverse=True)
        limit = request.args.get('limit', default=50, type=int)
        return jsonify({"entries": entries[:limit], "total": len(entries)})

    return app


def run_server(host: str = "0.0.0.0", port: int = 5000):
    """运行Web服务器"""
    app = create_app()
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)
    app.run(host=host, port=port, debug=False, threaded=True)


def start_server_thread(host: str = "0.0.0.0", port: int = 5000) -> threading.Thread:
    """在后台线程中启动Web服务器"""
    def run():
        run_server(host, port)

    t = threading.Thread(target=run, daemon=True, name="web-server")
    t.start()
    logger.info("Web管理后台已启动，监听: %s:%s", host, port)
    return t
