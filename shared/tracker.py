"""
Agent Tracker SDK
Standalone module for bots/agents to register and report status to DynamoDB.
Usage:
    from tracker import AgentTracker
    with AgentTracker("aceable-bot", "Aceable Course Runner") as tracker:
        tracker.update_task("Logging in")
        tracker.log("Starting login flow")
        tracker.update_metrics(pages_completed=5)
"""

import boto3
import uuid
import time
import socket
import os
import threading
from datetime import datetime, timezone
from decimal import Decimal

# AWS Configuration - defaults, can override via env
AWS_ACCESS_KEY = os.environ.get("TRACKER_AWS_ACCESS_KEY", "YOUR_AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.environ.get("TRACKER_AWS_SECRET_KEY", "YOUR_AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("TRACKER_AWS_REGION", "us-east-1")

AGENT_TRACKER_TABLE = "AgentTracker"
AGENT_LOGS_TABLE = "AgentLogs"
AGENT_CHAT_TABLE = "AgentChat"

HEARTBEAT_INTERVAL = 30  # seconds
TTL_AGENT_DAYS = 7
TTL_LOGS_DAYS = 3
TTL_CHAT_DAYS = 7


def _get_dynamo():
    session = boto3.Session(
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION,
    )
    return session.resource("dynamodb")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _now_ms():
    return int(time.time() * 1000)


def _ttl_seconds(days):
    return int(time.time()) + (days * 86400)


def _convert_floats(item):
    if isinstance(item, dict):
        return {k: _convert_floats(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [_convert_floats(i) for i in item]
    elif isinstance(item, float):
        return Decimal(str(item))
    else:
        return item


class AgentTracker:
    def __init__(self, agent_type: str, agent_name: str, title: str = None):
        self.agent_type = agent_type
        self.agent_name = agent_name
        self.title = title or agent_name
        self.current_task = ""
        self.goal = ""
        self.metrics = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._heartbeat_thread = None

        self._dynamo = _get_dynamo()
        self._tracker_table = self._dynamo.Table(AGENT_TRACKER_TABLE)
        self._logs_table = self._dynamo.Table(AGENT_LOGS_TABLE)
        self._chat_table = self._dynamo.Table(AGENT_CHAT_TABLE)

        # Deterministic agent_id from type+name so re-registration reuses the same entry
        import hashlib
        self.agent_id = hashlib.sha256(f"{agent_type}::{agent_name}".encode()).hexdigest()[:36]

        self._register()
        self._start_heartbeat()

    def _register(self):
        now = _now_iso()
        # Check if this agent already exists and is running
        try:
            resp = self._tracker_table.get_item(Key={"agent_id": self.agent_id})
            existing = resp.get("Item")
            if existing and existing.get("status") == "running":
                # Reuse existing — just update heartbeat and pid
                self._tracker_table.update_item(
                    Key={"agent_id": self.agent_id},
                    UpdateExpression="SET last_heartbeat = :hb, pid = :pid, #s = :s, #t = :ttl",
                    ExpressionAttributeValues={
                        ":hb": now,
                        ":pid": os.getpid(),
                        ":s": "running",
                        ":ttl": _ttl_seconds(TTL_AGENT_DAYS),
                    },
                    ExpressionAttributeNames={"#s": "status", "#t": "ttl"},
                )
                # Restore metrics from existing record
                self.metrics = existing.get("metrics", {}) or {}
                self.log(f"Agent reconnected: {self.agent_name} ({self.agent_type})")
                return
        except Exception:
            pass

        record = _convert_floats({
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "agent_name": self.agent_name,
            "title": self.title,
            "status": "running",
            "current_task": "",
            "goal": "",
            "started_at": now,
            "last_heartbeat": now,
            "ended_at": None,
            "metrics": {},
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "ttl": _ttl_seconds(TTL_AGENT_DAYS),
        })
        # DynamoDB doesn't accept None values in top-level attributes for some operations
        record = {k: v for k, v in record.items() if v is not None}
        self._tracker_table.put_item(Item=record)
        self.log(f"Agent registered: {self.agent_name} ({self.agent_type})")

    def _start_heartbeat(self):
        def _heartbeat_loop():
            while not self._stop_event.wait(HEARTBEAT_INTERVAL):
                try:
                    self._send_heartbeat()
                except Exception as e:
                    print(f"[Tracker] Heartbeat error: {e}")

        self._heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _send_heartbeat(self):
        with self._lock:
            expr = "SET last_heartbeat = :hb, current_task = :ct, #t = :ttl"
            vals = {
                ":hb": _now_iso(),
                ":ct": self.current_task,
                ":ttl": _ttl_seconds(TTL_AGENT_DAYS),
            }
            names = {"#t": "ttl"}

            if self.metrics:
                expr += ", #m = :m"
                vals[":m"] = _convert_floats(self.metrics)
                names["#m"] = "metrics"

            self._tracker_table.update_item(
                Key={"agent_id": self.agent_id},
                UpdateExpression=expr,
                ExpressionAttributeValues=vals,
                ExpressionAttributeNames=names,
            )

    def update_task(self, task_description: str):
        with self._lock:
            self.current_task = task_description
        # Immediately send heartbeat with new task
        try:
            self._send_heartbeat()
        except Exception:
            pass

    def update_metrics(self, **kwargs):
        with self._lock:
            self.metrics.update(kwargs)
        try:
            self._send_heartbeat()
        except Exception:
            pass

    def set_title(self, title: str):
        self.title = title
        try:
            self._tracker_table.update_item(
                Key={"agent_id": self.agent_id},
                UpdateExpression="SET title = :t",
                ExpressionAttributeValues={":t": title},
            )
        except Exception as e:
            print(f"[Tracker] Set title error: {e}")

    def set_goal(self, goal: str):
        self.goal = goal
        try:
            self._tracker_table.update_item(
                Key={"agent_id": self.agent_id},
                UpdateExpression="SET goal = :g",
                ExpressionAttributeValues={":g": goal},
            )
        except Exception as e:
            print(f"[Tracker] Set goal error: {e}")

    def log(self, message: str, level: str = "info", **metadata):
        try:
            record = _convert_floats({
                "agent_id": self.agent_id,
                "timestamp": _now_ms(),
                "level": level,
                "message": message,
                "metadata": metadata if metadata else {},
                "ttl": _ttl_seconds(TTL_LOGS_DAYS),
            })
            self._logs_table.put_item(Item=record)
        except Exception as e:
            print(f"[Tracker] Log error: {e}")

    def log_chat(self, message: str, direction: str = "outbound", sender: str = ""):
        try:
            record = _convert_floats({
                "agent_id": self.agent_id,
                "timestamp": _now_ms(),
                "direction": direction,
                "message": message,
                "sender": sender or self.title,
                "ttl": _ttl_seconds(TTL_CHAT_DAYS),
            })
            self._chat_table.put_item(Item=record)
        except Exception as e:
            print(f"[Tracker] Chat log error: {e}")

    def complete(self, status: str = "completed"):
        self._stop_event.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)

        try:
            self._tracker_table.update_item(
                Key={"agent_id": self.agent_id},
                UpdateExpression="SET #s = :s, ended_at = :e, last_heartbeat = :hb",
                ExpressionAttributeValues={
                    ":s": status,
                    ":e": _now_iso(),
                    ":hb": _now_iso(),
                },
                ExpressionAttributeNames={"#s": "status"},
            )
            self.log(f"Agent {status}: {self.agent_name}", level="info")
        except Exception as e:
            print(f"[Tracker] Deregister error: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        status = "failed" if exc_type else "completed"
        self.complete(status)
        return False
