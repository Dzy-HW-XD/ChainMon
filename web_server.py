#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web管理后台服务器
提供可视化监控界面和API接口
"""
from flask import Flask, request, jsonify, render_template_string
import logging
import threading
import time
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# 全局引用
_global_client = None


def set_client(client):
    """设置全局客户端引用"""
    global _global_client
    _global_client = client


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
        .chain-block { min-width: 100px; background: #f8f9fa; border: 2px solid #1a1a2e; border-radius: 8px; padding: 10px; text-align: center; font-size: 12px; flex-shrink: 0; }
        .chain-block .height { font-weight: 700; font-size: 16px; color: #1a1a2e; }
        .chain-block .info { color: #999; margin-top: 4px; }
        .chain-arrow { display: flex; align-items: center; color: #1a1a2e; font-size: 18px; flex-shrink: 0; }
        .refresh-btn { float: right; }
    </style>
</head>
<body>
    <nav class="nav">
        <h1>Blockchain Monitor</h1>
        <span class="badge">v1.0</span>
        <div class="nav-right">
            Node: <strong id="node-id">-</strong> | 
            <span id="node-status" class="tag tag-green">ONLINE</span>
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
                <h2>Managed Devices</h2>
                <table>
                    <thead><tr><th>IP</th><th>Name</th><th>Status</th><th>Actions</th></tr></thead>
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

    <script>
    function switchTab(name) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.getElementById('page-' + name).classList.add('active');
        event.target.classList.add('active');
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

    function loadData() {
        fetch('/api/status').then(r => r.json()).then(data => {
            document.getElementById('node-id').textContent = data.node_id || '-';
            // Stat cards
            var bc = data.blockchain || {};
            var net = data.network || {};
            document.getElementById('stat-cards').innerHTML =
                '<div class="card"><h3>Chain Height</h3><div class="value">' + (bc.chain_height || 0) + '</div><div class="sub">Total: ' + (bc.total_blocks || 0) + ' blocks</div></div>' +
                '<div class="card ok"><h3>Network Peers</h3><div class="value">' + (net.online_peers || 0) + '</div><div class="sub">Online / ' + (net.total_peers || 0) + ' total</div></div>' +
                '<div class="card"><h3>Managed Devices</h3><div class="value">' + (data.managed_devices || 0) + '</div><div class="sub">IPMI ready</div></div>' +
                '<div class="card warn"><h3>Pending Data</h3><div class="value">' + (bc.pending_data_count || 0) + '</div><div class="sub">Awaiting on-chain</div></div>';
        }).catch(e => console.error(e));

        // Load blocks
        fetch('/api/blockchain/blocks?limit=20').then(r => r.json()).then(data => {
            var blocks = data.blocks || [];
            // Chain visualization (last 10)
            var vis = '';
            var last10 = blocks.slice(-10);
            for (var i = 0; i < last10.length; i++) {
                var b = last10[i];
                vis += '<div class="chain-block"><div class="height">#' + b.height + '</div><div class="info">' + b.data_count + ' items</div></div>';
                if (i < last10.length - 1) vis += '<div class="chain-arrow">\u2192</div>';
            }
            document.getElementById('chain-vis').innerHTML = vis || '<div class="empty">No blocks</div>';

            // Recent blocks table
            var html = '';
            for (var i = blocks.length - 1; i >= 0; i--) {
                var b = blocks[i];
                html += '<tr><td><strong>#' + b.height + '</strong></td><td class="hash">' + shortHash(b.hash) + '</td><td>' + (b.node_id || '-') + '</td><td>' + b.data_count + '</td><td>' + formatTime(b.timestamp) + '</td></tr>';
            }
            document.getElementById('recent-blocks').innerHTML = html || '<tr><td colspan="5" class="empty">No blocks</td></tr>';

            // All blocks page
            var bcCards = document.getElementById('bc-cards');
            if (bcCards) {
                bcCards.innerHTML =
                    '<div class="card"><h3>Total Blocks</h3><div class="value">' + blocks.length + '</div></div>' +
                    '<div class="card ok"><h3>Chain Valid</h3><div class="value">YES</div></div>';
            }
            var allHtml = '';
            for (var i = blocks.length - 1; i >= 0; i--) {
                var b = blocks[i];
                allHtml += '<tr><td>#' + b.height + '</td><td class="hash">' + shortHash(b.hash) + '</td><td class="hash">' + shortHash(b.prev_hash || '') + '</td><td>' + (b.node_id || '-') + '</td><td>' + b.data_count + '</td><td>' + formatTime(b.timestamp) + '</td></tr>';
            }
            var allBody = document.getElementById('all-blocks');
            if (allBody) allBody.innerHTML = allHtml || '<tr><td colspan="6" class="empty">No blocks</td></tr>';
        }).catch(e => console.error(e));

        // Load devices
        fetch('/api/devices').then(r => r.json()).then(data => {
            var devs = data.devices || [];
            var html = '';
            for (var d of devs) {
                html += '<tr><td><strong>' + d.ip + '</strong></td><td>' + (d.name || '-') + '</td><td><span class="tag tag-blue">Managed</span></td><td><button class="btn btn-outline btn-sm" onclick="document.getElementById(\\'ipmi-ip\\').value=\\'' + d.ip + '\\';switchTab(\\'ipmi\\')">IPMI</button></td></tr>';
            }
            document.getElementById('device-list').innerHTML = html || '<tr><td colspan="4" class="empty">No devices</td></tr>';
        }).catch(e => console.error(e));

        loadAudit();
    }

    function loadAudit() {
        var type = document.getElementById('audit-type').value;
        var ip = document.getElementById('audit-ip').value;
        var url = '/api/query?limit=50';
        if (type) url += '&data_type=' + type;
        if (ip) url += '&device_ip=' + ip;
        fetch(url).then(r => r.json()).then(data => {
            var results = data.results || [];
            var html = '';
            for (var r of results) {
                var content = r.content || '';
                if (content.length > 120) content = content.substring(0, 120) + '...';
                html += '<tr><td>' + formatTime(r.timestamp) + '</td><td>' + typeLabel(r.data_type) + '</td><td>' + (r.device_ip || '-') + '</td><td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + content + '</td><td>' + (r.operate_user || '-') + '</td><td class="hash">' + shortHash(r.block_hash) + '</td></tr>';
            }
            document.getElementById('audit-list').innerHTML = html || '<tr><td colspan="6" class="empty">No records</td></tr>';
        }).catch(e => console.error(e));
    }

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
        }).then(r => r.json()).then(data => {
            box.textContent = JSON.stringify(data, null, 2);
        }).catch(e => { box.textContent = 'Error: ' + e; });
    }

    // Initial load
    loadData();
    // Auto refresh every 30s
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
        """获取设备列表"""
        if not _global_client:
            return jsonify({"error": "client not initialized"}), 500
        
        devices = []
        for d in _global_client.managed_devices:
            devices.append({
                "ip": d.get("ip"),
                "name": d.get("name", ""),
                "status": "managed"
            })
        return jsonify({"devices": devices})

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

        # 从区块链中提取所有包含操作数据的记录
        entries = []
        chain = _global_client.blockchain.chain
        data_type_filter = request.args.get('data_type', type=int)

        for block in chain:
            for data in block.data_list:
                # 如果指定了data_type过滤
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

        # 按时间倒序
        entries.sort(key=lambda x: x["timestamp"], reverse=True)
        limit = request.args.get('limit', default=50, type=int)
        return jsonify({"entries": entries[:limit], "total": len(entries)})

    return app


def run_server(host: str = "0.0.0.0", port: int = 5000):
    """运行Web服务器"""
    app = create_app()
    # 抑制Flask默认日志
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
