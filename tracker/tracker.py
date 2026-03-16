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
import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal

# AWS Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

AGENT_TRACKER_TABLE = "AgentTracker"
AGENT_LOGS_TABLE = "AgentLogs"
AGENT_CHAT_TABLE = "AgentChat"
BOT_TRACKER_TABLE = "BotTracker"

TTL_AGENT_DAYS = 7
TTL_LOGS_DAYS = 3
TTL_CHAT_DAYS = 7


def _get_dynamo():
    session = boto3.Session(region_name=AWS_REGION)
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
    def __init__(self, agent_type: str, agent_name: str, title: str = None, agent_id: str = None, interactive: bool = False, heartbeat: bool = False):
        self.agent_type = agent_type
        self.agent_name = agent_name
        self.title = title or agent_name
        self.current_task = ""
        self.goal = ""
        self.metrics = {}
        self.interactive = interactive
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._heartbeat_thread = None

        self._dynamo = _get_dynamo()
        self._tracker_table = self._dynamo.Table(AGENT_TRACKER_TABLE)
        self._logs_table = self._dynamo.Table(AGENT_LOGS_TABLE)
        self._chat_table = self._dynamo.Table(AGENT_CHAT_TABLE)

        # Use explicit agent_id if provided (for session recovery), else deterministic hash
        if agent_id:
            self.agent_id = agent_id
        else:
            import hashlib
            self.agent_id = hashlib.sha256(f"{agent_type}::{agent_name}".encode()).hexdigest()[:36]

        self._register()
        if heartbeat:
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
                    UpdateExpression="SET last_heartbeat = :hb, pid = :pid, #s = :s, #t = :ttl, interactive = :inter",
                    ExpressionAttributeValues={
                        ":hb": now,
                        ":pid": os.getpid(),
                        ":s": "running",
                        ":ttl": _ttl_seconds(TTL_AGENT_DAYS),
                        ":inter": self.interactive,
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
            "interactive": self.interactive,
        })
        # DynamoDB doesn't accept None values in top-level attributes for some operations
        record = {k: v for k, v in record.items() if v is not None}
        self._tracker_table.put_item(Item=record)
        self.log(f"Agent registered: {self.agent_name} ({self.agent_type})")

    def update_task(self, task_description: str):
        with self._lock:
            self.current_task = task_description
        try:
            self._tracker_table.update_item(
                Key={"agent_id": self.agent_id},
                UpdateExpression="SET current_task = :ct, last_heartbeat = :hb, #t = :ttl",
                ExpressionAttributeValues={":ct": task_description, ":hb": _now_iso(), ":ttl": _ttl_seconds(TTL_AGENT_DAYS)},
                ExpressionAttributeNames={"#t": "ttl"},
                ConditionExpression="attribute_exists(agent_id)",
            )
        except Exception:
            pass

    def update_metrics(self, **kwargs):
        with self._lock:
            self.metrics.update(kwargs)
        try:
            expr = "SET last_heartbeat = :hb, #t = :ttl, #m = :m"
            vals = {":hb": _now_iso(), ":ttl": _ttl_seconds(TTL_AGENT_DAYS), ":m": _convert_floats(self.metrics)}
            self._tracker_table.update_item(
                Key={"agent_id": self.agent_id},
                UpdateExpression=expr,
                ExpressionAttributeValues=vals,
                ExpressionAttributeNames={"#t": "ttl", "#m": "metrics"},
                ConditionExpression="attribute_exists(agent_id)",
            )
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
                ConditionExpression="attribute_exists(agent_id)",
            )
            self.log(f"Agent {status}: {self.agent_name}", level="info")
        except Exception as e:
            print(f"[Tracker] Deregister error: {e}")

    def get_log_handler(self, level=logging.INFO):
        """Return a logging.Handler that forwards log messages to DynamoDB."""
        handler = _DynamoLogHandler(self)
        handler.setLevel(level)
        return handler

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        status = "failed" if exc_type else "completed"
        self.complete(status)
        return False


class BotTracker:
    """Tracker for long-running bots (orchestrator, task-worker, scrapers).
    Writes to BotTracker table. No chat support — bots don't have conversations."""

    def __init__(self, bot_type: str, bot_name: str, title: str = None):
        self.bot_type = bot_type
        self.bot_name = bot_name
        self.title = title or bot_name
        self.current_task = ""
        self.metrics = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._heartbeat_thread = None

        self._dynamo = _get_dynamo()
        self._tracker_table = self._dynamo.Table(BOT_TRACKER_TABLE)
        self._logs_table = self._dynamo.Table(AGENT_LOGS_TABLE)

        # Deterministic bot_id from type::name
        import hashlib
        self.bot_id = hashlib.sha256(f"{bot_type}::{bot_name}".encode()).hexdigest()[:36]

        self._register()

    def _register(self):
        now = _now_iso()
        try:
            resp = self._tracker_table.get_item(Key={"bot_id": self.bot_id})
            existing = resp.get("Item")
            if existing and existing.get("status") == "running":
                self._tracker_table.update_item(
                    Key={"bot_id": self.bot_id},
                    UpdateExpression="SET last_heartbeat = :hb, pid = :pid, #s = :s, #t = :ttl",
                    ExpressionAttributeValues={
                        ":hb": now, ":pid": os.getpid(),
                        ":s": "running", ":ttl": _ttl_seconds(TTL_AGENT_DAYS),
                    },
                    ExpressionAttributeNames={"#s": "status", "#t": "ttl"},
                )
                self.metrics = existing.get("metrics", {}) or {}
                self.log(f"Bot reconnected: {self.bot_name} ({self.bot_type})")
                return
        except Exception:
            pass

        record = _convert_floats({
            "bot_id": self.bot_id,
            "bot_type": self.bot_type,
            "bot_name": self.bot_name,
            "title": self.title,
            "status": "running",
            "current_task": "",
            "started_at": now,
            "last_heartbeat": now,
            "metrics": {},
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "ttl": _ttl_seconds(TTL_AGENT_DAYS),
        })
        self._tracker_table.put_item(Item=record)
        self.log(f"Bot registered: {self.bot_name} ({self.bot_type})")

    def update_task(self, task_description: str):
        with self._lock:
            self.current_task = task_description
        try:
            self._tracker_table.update_item(
                Key={"bot_id": self.bot_id},
                UpdateExpression="SET current_task = :ct, last_heartbeat = :hb, #t = :ttl",
                ExpressionAttributeValues={":ct": task_description, ":hb": _now_iso(), ":ttl": _ttl_seconds(TTL_AGENT_DAYS)},
                ExpressionAttributeNames={"#t": "ttl"},
                ConditionExpression="attribute_exists(bot_id)",
            )
        except Exception:
            pass

    def update_metrics(self, **kwargs):
        with self._lock:
            self.metrics.update(kwargs)
        try:
            expr = "SET last_heartbeat = :hb, #t = :ttl, #m = :m"
            vals = {":hb": _now_iso(), ":ttl": _ttl_seconds(TTL_AGENT_DAYS), ":m": _convert_floats(self.metrics)}
            self._tracker_table.update_item(
                Key={"bot_id": self.bot_id},
                UpdateExpression=expr,
                ExpressionAttributeValues=vals,
                ExpressionAttributeNames={"#t": "ttl", "#m": "metrics"},
                ConditionExpression="attribute_exists(bot_id)",
            )
        except Exception:
            pass

    def log(self, message: str, level: str = "info", **metadata):
        try:
            record = _convert_floats({
                "agent_id": self.bot_id,
                "timestamp": _now_ms(),
                "level": level,
                "message": message,
                "metadata": metadata if metadata else {},
                "ttl": _ttl_seconds(TTL_LOGS_DAYS),
            })
            self._logs_table.put_item(Item=record)
        except Exception as e:
            print(f"[BotTracker] Log error: {e}")

    def complete(self, status: str = "completed"):
        self._stop_event.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
        try:
            self._tracker_table.update_item(
                Key={"bot_id": self.bot_id},
                UpdateExpression="SET #s = :s, ended_at = :e, last_heartbeat = :hb",
                ExpressionAttributeValues={":s": status, ":e": _now_iso(), ":hb": _now_iso()},
                ExpressionAttributeNames={"#s": "status"},
                ConditionExpression="attribute_exists(bot_id)",
            )
            self.log(f"Bot {status}: {self.bot_name}", level="info")
        except Exception as e:
            print(f"[BotTracker] Deregister error: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.complete("failed" if exc_type else "completed")
        return False


_LEVEL_MAP = {
    logging.DEBUG: "info",
    logging.INFO: "info",
    logging.WARNING: "warning",
    logging.ERROR: "error",
    logging.CRITICAL: "error",
}


class _DynamoLogHandler(logging.Handler):
    """Python logging handler that writes to DynamoDB AgentLogs via AgentTracker."""

    def __init__(self, tracker: AgentTracker):
        super().__init__()
        self._tracker = tracker

    def emit(self, record: logging.LogRecord):
        try:
            level = _LEVEL_MAP.get(record.levelno, "info")
            self._tracker.log(record.getMessage(), level=level)
        except Exception:
            self.handleError(record)
