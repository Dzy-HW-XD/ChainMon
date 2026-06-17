#!/usr/bin/env python3
"""Tests for outbound agent ingestion APIs."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_server
from monitor_client import MonitorClient


def test_agent_register_heartbeat_and_metrics():
    client_obj = MonitorClient.__new__(MonitorClient)
    client_obj.node_id = "server-ali"
    client_obj.node_mode = "server"
    client_obj.config = {"agent": {"token": "secret"}, "web": {"password": "admin123"}}
    client_obj.agent_registry = {}

    class FakeBlockchain:
        def __init__(self):
            self.pending_data = []

        def add_data(self, data):
            self.pending_data.append(data)
            return True

    client_obj.blockchain = FakeBlockchain()

    web_server.set_client(client_obj)
    app = web_server.create_app()
    test_client = app.test_client()
    headers = {"X-Agent-Token": "secret"}

    resp = test_client.post("/api/agent/register", json={
        "node_id": "tc",
        "node_name": "Tencent Agent",
        "region": "cn-guangzhou",
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["agent"]["node_id"] == "tc"

    resp = test_client.post("/api/agent/heartbeat", json={
        "node_id": "tc",
        "region": "cn-guangzhou",
    }, headers=headers)
    assert resp.status_code == 200

    resp = test_client.post("/api/agent/metrics", json={
        "node_id": "tc",
        "node_name": "Tencent Agent",
        "region": "cn-guangzhou",
        "metrics": [{
            "device_ip": "tc",
            "cpu_percent": 12.3,
            "memory": {"percent": 45.6},
            "collect_time": 100,
        }],
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["accepted"] == 1
    assert len(client_obj.blockchain.pending_data) == 2
    assert client_obj.blockchain.pending_data[-1].device_ip == "tc"


def test_agent_token_required_when_configured():
    client_obj = MonitorClient.__new__(MonitorClient)
    client_obj.node_id = "server-ali"
    client_obj.config = {"agent": {"token": "secret"}, "web": {"password": "admin123"}}
    client_obj.agent_registry = {}
    web_server.set_client(client_obj)
    app = web_server.create_app()

    resp = app.test_client().post("/api/agent/register", json={"node_id": "tc"})
    assert resp.status_code == 401


if __name__ == "__main__":
    test_agent_register_heartbeat_and_metrics()
    test_agent_token_required_when_configured()
    print("agent api tests passed")
