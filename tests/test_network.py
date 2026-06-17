#!/usr/bin/env python3
"""Tests for P2P network state handling."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blockchain.network import P2PNetwork


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def test_heartbeat_recovers_offline_peer():
    network = P2PNetwork("tc", 8080, [
        {"node_id": "ali", "host": "203.0.113.10", "port": 8080, "region": "cn-hangzhou"}
    ])
    network.update_peer_status("ali", False)

    assert network.get_online_peers() == []

    with patch("blockchain.network.requests.post", return_value=FakeResponse(200)) as mocked_post:
        network.broadcast_heartbeat()

    assert mocked_post.called
    assert network.peers["ali"].is_online is True
    assert network.peers["ali"].last_heartbeat > 0


def test_heartbeat_marks_peer_offline_on_failure():
    network = P2PNetwork("tc", 8080, [
        {"node_id": "ali", "host": "203.0.113.10", "port": 8080, "region": "cn-hangzhou"}
    ])

    with patch("blockchain.network.requests.post", side_effect=TimeoutError("timeout")):
        network.broadcast_heartbeat()

    assert network.peers["ali"].is_online is False
    assert network.peers["ali"].last_heartbeat > 0


if __name__ == "__main__":
    test_heartbeat_recovers_offline_peer()
    test_heartbeat_marks_peer_offline_on_failure()
    print("network tests passed")
