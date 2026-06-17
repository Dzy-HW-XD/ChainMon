#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Outbound ChainMon agent.

The agent runs inside a VPN or private network, collects local resource metrics,
and pushes them to one or more public ChainMon server endpoints. It does not
open Web/P2P ports and does not maintain a local ledger.
"""
import argparse
import json
import logging
import os
import signal
import sys
import time
from typing import Any, Dict, List

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client.collector import HardwareCollector
from client.config_loader import get_node_id, load_config


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("AgentClient")


class AgentClient:
    """Collect local/private metrics and push them to a public server."""

    def __init__(self, config_path: str = "config/agent_config.yaml"):
        self.config_path = config_path
        self.config = load_config(config_path)
        self.node_id = get_node_id(self.config)
        self.node_name = self.config.get("node", {}).get("node_name", self.node_id)
        self.region = self.config.get("node", {}).get("region", "")
        self.agent_config = self.config.get("agent", {})
        self.endpoints = [e.rstrip("/") for e in self.agent_config.get("upstreams", [])]
        if not self.endpoints:
            single = self.agent_config.get("upstream")
            if single:
                self.endpoints = [single.rstrip("/")]
        if not self.endpoints:
            raise ValueError("agent.upstream or agent.upstreams is required")

        client_config = self.config.get("client", {})
        self.collect_interval = int(client_config.get("collect_interval", self.agent_config.get("push_interval", 30)))
        self.task_poll_interval = int(self.agent_config.get("task_poll_interval", 30))
        self.token = self.agent_config.get("token", "")
        self.collector = HardwareCollector(
            client_config.get("ipmi_username", "admin"),
            client_config.get("ipmi_password", "admin123"),
        )
        self.devices = self.config.get("devices", [])
        self.last_hardware_push = 0
        self.hardware_push_interval = int(self.agent_config.get("hardware_push_interval", 3600))
        self.stop_requested = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-Agent-Token"] = self.token
        return headers

    def _agent_payload(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "region": self.region,
            "mode": "agent",
            "capabilities": ["metrics", "tasks"],
        }

    def _post(self, path: str, payload: Dict[str, Any]) -> bool:
        ok = False
        for endpoint in self.endpoints:
            url = endpoint + path
            try:
                resp = requests.post(url, json=payload, headers=self._headers(), timeout=15)
                if 200 <= resp.status_code < 300:
                    ok = True
                    logger.debug("POST %s ok: %s", url, resp.text[:200])
                else:
                    logger.warning("POST %s failed: HTTP %s %s", url, resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("POST %s failed: %s", url, e)
        return ok

    def _get(self, path: str) -> List[Dict[str, Any]]:
        for endpoint in self.endpoints:
            url = endpoint + path
            try:
                resp = requests.get(url, headers=self._headers(), timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("tasks", [])
                logger.warning("GET %s failed: HTTP %s %s", url, resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("GET %s failed: %s", url, e)
        return []

    def register(self):
        self._post("/api/agent/register", self._agent_payload())

    def heartbeat(self):
        self._post("/api/agent/heartbeat", self._agent_payload())

    def collect_metrics(self) -> List[Dict[str, Any]]:
        metrics = []
        local_metrics = self.collector.collect_local_metrics()
        local_metrics["node_id"] = self.node_id
        local_metrics["device_ip"] = self.node_id
        local_metrics["node_name"] = self.node_name
        local_metrics["region"] = self.region
        metrics.append(local_metrics)

        for device in self.devices:
            device_ip = device.get("ip")
            if not device_ip or device.get("local") or device_ip in (self.node_id, "localhost"):
                continue
            perf = self.collector.collect_performance_metrics(device_ip)
            if perf.get("success"):
                perf["device_ip"] = device_ip
                perf["device_name"] = device.get("name", device_ip)
                perf["agent_node_id"] = self.node_id
                metrics.append(perf)
        return metrics

    def collect_hardware_assets(self, force: bool = False) -> List[Dict[str, Any]]:
        now = time.time()
        if not force and self.last_hardware_push and now - self.last_hardware_push < self.hardware_push_interval:
            return []
        asset = self.collector.collect_local_hardware_asset()
        asset["node_id"] = self.node_id
        asset["device_ip"] = self.node_id
        asset["node_name"] = self.node_name
        asset["region"] = self.region
        self.last_hardware_push = now
        return [asset]

    def push_metrics(self) -> bool:
        payload = self._agent_payload()
        payload["metrics"] = self.collect_metrics()
        hardware_assets = self.collect_hardware_assets(force=self.last_hardware_push == 0)
        if hardware_assets:
            payload["hardware_assets"] = hardware_assets
        ok = self._post("/api/agent/metrics", payload)
        if ok:
            logger.info(
                "pushed %d metric record(s), %d hardware asset record(s)",
                len(payload["metrics"]),
                len(payload.get("hardware_assets", [])),
            )
        return ok

    def poll_tasks(self):
        tasks = self._get(f"/api/agent/tasks?node_id={self.node_id}")
        if tasks:
            logger.info("received %d task(s); task execution is reserved for the next iteration", len(tasks))

    def run(self, once: bool = False):
        logger.info("agent started: node_id=%s upstreams=%s", self.node_id, self.endpoints)
        self.register()
        last_heartbeat = 0
        last_task_poll = 0
        while not self.stop_requested:
            now = time.time()
            if now - last_heartbeat >= max(30, self.collect_interval):
                self.heartbeat()
                last_heartbeat = now
            self.push_metrics()
            if now - last_task_poll >= self.task_poll_interval:
                self.poll_tasks()
                last_task_poll = now
            if once:
                break
            time.sleep(self.collect_interval)

    def _signal_handler(self, sig, frame):
        logger.info("received signal: %s", sig)
        self.stop_requested = True


def main():
    parser = argparse.ArgumentParser(description="ChainMon outbound agent")
    parser.add_argument("--config", default="config/agent_config.yaml", help="agent config path")
    parser.add_argument("--once", action="store_true", help="collect and push once, then exit")
    args = parser.parse_args()
    AgentClient(args.config).run(once=args.once)


if __name__ == "__main__":
    main()
