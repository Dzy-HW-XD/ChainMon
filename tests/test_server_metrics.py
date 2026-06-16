#!/usr/bin/env python3
"""Tests for server resource maintenance metric aggregation."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blockchain.block import Block, ChainData, ChainDataType
from web_server import _collect_server_metrics_from_client, _collect_server_metric_history_from_client


class FakeBlockchain:
    def __init__(self, chain, pending_data=None):
        self.chain = chain
        self.pending_data = pending_data or []


class FakeClient:
    def __init__(self, chain, pending_data=None):
        self.node_id = "test-node"
        self.blockchain = FakeBlockchain(chain, pending_data)


def test_collect_server_metrics_uses_localhost_only_when_no_named_servers():
    local = ChainData(
        data_type=int(ChainDataType.PERFORMANCE),
        device_ip="localhost",
        content=json.dumps({
            "cpu_percent": 12.5,
            "memory": {"total": 1000, "used": 400, "percent": 40.0},
            "disk": {
                "/": {"total": 1000, "used": 700, "percent": 70.0},
                "/data": {"total": 1000, "used": 300, "percent": 30.0},
            },
            "net": {"bytes_sent": 1234, "bytes_recv": 5678},
            "collect_time": 100,
        }),
        operate_user="system",
        timestamp=90,
    )
    block = Block(
        block_height=1,
        prev_block_hash="0" * 64,
        timestamp=120,
        client_node_id="test-node",
        data_list=[local],
    )

    servers, latest = _collect_server_metrics_from_client(FakeClient([block]))

    assert len(servers) == 1
    assert latest["device_ip"] == "localhost"
    assert latest["cpu_percent"] == 12.5
    assert latest["memory_percent"] == 40.0
    assert latest["disk_percent"] == 70.0
    assert latest["net_bytes_recv"] == 5678


def test_collect_server_metrics_filters_legacy_localhost_when_named_servers_exist():
    legacy = ChainData(
        data_type=int(ChainDataType.PERFORMANCE),
        device_ip="localhost",
        content=json.dumps({"cpu_percent": 10, "memory": {"percent": 20}, "collect_time": 100}),
        operate_user="system",
    )
    current = ChainData(
        data_type=int(ChainDataType.PERFORMANCE),
        device_ip="test-node",
        content=json.dumps({"cpu_percent": 30, "memory": {"percent": 40}, "collect_time": 120}),
        operate_user="system",
    )
    block = Block(
        block_height=1,
        prev_block_hash="0" * 64,
        timestamp=120,
        client_node_id="test-node",
        data_list=[legacy, current],
    )

    servers, latest = _collect_server_metrics_from_client(FakeClient([block]))

    assert [s["device_ip"] for s in servers] == ["test-node"]
    assert latest["device_ip"] == "test-node"


def test_collect_server_metrics_pending_overrides_chain():
    old = ChainData(
        data_type=int(ChainDataType.PERFORMANCE),
        device_ip="localhost",
        content=json.dumps({"cpu_percent": 10, "collect_time": 100}),
        operate_user="system",
    )
    pending = ChainData(
        data_type=int(ChainDataType.PERFORMANCE),
        device_ip="localhost",
        content=json.dumps({"cpu_percent": 90, "collect_time": 200}),
        operate_user="system",
    )
    block = Block(
        block_height=1,
        prev_block_hash="0" * 64,
        timestamp=100,
        client_node_id="test-node",
        data_list=[old],
    )

    servers, latest = _collect_server_metrics_from_client(FakeClient([block], [pending]))

    assert len(servers) == 1
    assert latest["cpu_percent"] == 90
    assert latest["source"] == "pending"


def test_collect_server_metrics_prefers_current_node_id():
    local_legacy = ChainData(
        data_type=int(ChainDataType.PERFORMANCE),
        device_ip="localhost",
        content=json.dumps({"cpu_percent": 10, "collect_time": 100}),
        operate_user="system",
    )
    current_node = ChainData(
        data_type=int(ChainDataType.PERFORMANCE),
        device_ip="test-node",
        content=json.dumps({"cpu_percent": 20, "collect_time": 90}),
        operate_user="system",
    )
    block = Block(
        block_height=1,
        prev_block_hash="0" * 64,
        timestamp=100,
        client_node_id="test-node",
        data_list=[local_legacy, current_node],
    )

    servers, latest = _collect_server_metrics_from_client(FakeClient([block]))

    assert len(servers) == 1
    assert latest["device_ip"] == "test-node"
    assert latest["cpu_percent"] == 20


def test_collect_server_metric_history_groups_cpu_and_memory():
    points = []
    for i in range(3):
        points.append(ChainData(
            data_type=int(ChainDataType.PERFORMANCE),
            device_ip="test-node",
            content=json.dumps({
                "cpu_percent": 10 + i,
                "memory": {"percent": 50 + i},
                "collect_time": 100 + i,
            }),
            operate_user="system",
        ))
    points.append(ChainData(
        data_type=int(ChainDataType.PERFORMANCE),
        device_ip="other-node",
        content=json.dumps({
            "cpu_percent": 30,
            "memory": {"percent": 60},
            "collect_time": 103,
        }),
        operate_user="system",
    ))
    block = Block(
        block_height=1,
        prev_block_hash="0" * 64,
        timestamp=120,
        client_node_id="test-node",
        data_list=points,
    )

    history = _collect_server_metric_history_from_client(FakeClient([block]), limit_per_server=2)

    assert [s["device_ip"] for s in history] == ["test-node", "other-node"]
    assert len(history[0]["points"]) == 2
    assert history[0]["points"][-1]["cpu_percent"] == 12
    assert history[0]["points"][-1]["memory_percent"] == 52


if __name__ == "__main__":
    test_collect_server_metrics_uses_localhost_only_when_no_named_servers()
    test_collect_server_metrics_filters_legacy_localhost_when_named_servers_exist()
    test_collect_server_metrics_pending_overrides_chain()
    test_collect_server_metrics_prefers_current_node_id()
    test_collect_server_metric_history_groups_cpu_and_memory()
    print("server metrics tests passed")
