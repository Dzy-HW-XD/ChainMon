#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2P网络服务器
接收其他节点发来的区块提议、投票、心跳等P2P消息
"""
from flask import Flask, request, jsonify
import logging
import threading
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# 全局引用（由monitor_client设置）
_global_client = None


def set_client(client):
    """设置全局客户端引用"""
    global _global_client
    _global_client = client


def create_app() -> Flask:
    """创建Flask应用"""
    app = Flask(__name__)

    @app.route('/p2p/block/propose', methods=['POST'])
    def handle_block_propose():
        """处理区块提议"""
        if not _global_client:
            return jsonify({"error": "客户端未初始化"}), 500
        
        try:
            block_data = request.json
            from blockchain.block import Block
            block = Block.from_dict(block_data)
            
            # 接收区块提议
            success, reason = _global_client.consensus.receive_block_proposal(
                block, block_data.get("proposer_id", "unknown")
            )
            
            if success:
                # 自动投票同意（简化：收到提议自动同意）
                _global_client.consensus.vote_block(
                    block.current_hash, _global_client.node_id, True
                )
                return jsonify({"status": "accepted", "block_hash": block.current_hash})
            else:
                return jsonify({"status": "rejected", "reason": reason}), 400
                
        except Exception as e:
            logger.error("处理区块提议失败: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route('/p2p/block/vote', methods=['POST'])
    def handle_block_vote():
        """处理投票"""
        if not _global_client:
            return jsonify({"error": "客户端未初始化"}), 500
        
        try:
            vote_data = request.json
            block_hash = vote_data.get("block_hash")
            voter_id = vote_data.get("voter_id")
            is_approved = vote_data.get("is_approved", False)
            
            success = _global_client.consensus.vote_block(block_hash, voter_id, is_approved)
            
            if success:
                return jsonify({"status": "voted"})
            else:
                return jsonify({"status": "vote_failed"}), 400
                
        except Exception as e:
            logger.error("处理投票失败: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route('/p2p/chain/sync', methods=['GET'])
    def handle_chain_sync():
        """处理链同步请求"""
        if not _global_client:
            return jsonify({"error": "客户端未初始化"}), 500
        
        try:
            chain_data = [b.to_dict() for b in _global_client.blockchain.chain]
            return jsonify({
                "chain_height": len(chain_data) - 1,
                "chain": chain_data
            })
        except Exception as e:
            logger.error("处理链同步请求失败: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route('/p2p/heartbeat', methods=['POST'])
    def handle_heartbeat():
        """处理心跳"""
        try:
            data = request.json
            node_id = data.get("node_id")
            timestamp = data.get("timestamp")
            status = data.get("status", "online")
            
            if _global_client:
                _global_client.network.update_peer_status(
                    node_id, status == "online"
                )
            
            return jsonify({"status": "ok"})
        except Exception as e:
            logger.error("处理心跳失败: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route('/p2p/peers', methods=['GET'])
    def handle_get_peers():
        """获取节点列表"""
        if not _global_client:
            return jsonify({"peers": []})
        
        peers = []
        for p in _global_client.network.get_peers():
            peers.append(p.to_dict())
        return jsonify({"peers": peers})

    @app.route('/health', methods=['GET'])
    def health():
        """健康检查"""
        node_id = _global_client.node_id if _global_client else "unknown"
        return jsonify({"status": "ok", "node_id": node_id})

    return app


def run_server(host: str = "0.0.0.0", port: int = 8080):
    """运行P2P服务器"""
    app = create_app()
    app.run(host=host, port=port, debug=False, threaded=True)


def start_server_thread(host: str = "0.0.0.0", port: int = 8080) -> threading.Thread:
    """在后台线程中启动P2P服务器"""
    def run():
        run_server(host, port)
    
    t = threading.Thread(target=run, daemon=True, name="p2p-server")
    t.start()
    logger.info("P2P服务器线程已启动，监听: %s:%s", host, port)
    return t
