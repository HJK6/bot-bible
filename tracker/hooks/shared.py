"""Shared DynamoDB helpers for Claude Code hooks. Lightweight — no threads, no heartbeat."""
import os
import re
import time
import socket
import hashlib
import subprocess
import boto3
from datetime import datetime, timezone
from decimal import Decimal

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_dynamo = None

def get_dynamo():
    global _dynamo
    if _dynamo is None:
        session = boto3.Session(region_name=AWS_REGION)
        _dynamo = session.resource("dynamodb")
    return _dynamo

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def now_ms():
    return int(time.time() * 1000)

def ttl_days(days):
    return int(time.time()) + (days * 86400)

def get_agent_id():
    """Deterministic agent_id based on tmux session name (stable across all processes in the session)."""
    tmux_info = _get_tmux_info()
    if tmux_info:
        session_name = tmux_info["tmux_session"]
        return hashlib.sha256(f"claude-code::tmux-{session_name}".encode()).hexdigest()[:36]
    # Fallback for non-tmux (shouldn't reach here due to guards)
    ppid = os.getppid()
    return hashlib.sha256(f"claude-code::pid-{ppid}".encode()).hexdigest()[:36]

def get_ppid():
    return os.getppid()

def _get_tmux_info():
    """Detect tmux environment and return metadata, or None if not in tmux."""
    if not os.environ.get("TMUX"):
        return None
    try:
        result = subprocess.run(
            ["/opt/homebrew/bin/tmux", "display-message", "-p",
             "#{session_name}|#{window_name}|#{window_index}"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode != 0:
            return None
        parts = result.stdout.strip().split("|")
        if len(parts) == 3:
            return {
                "tmux_session": parts[0],
                "tmux_window": parts[1],
                "tmux_index": int(parts[2]),
            }
    except Exception:
        pass
    return None

def is_tmux():
    """Check if current process is inside tmux."""
    return bool(os.environ.get("TMUX"))

def ensure_registered():
    """Register or reconnect this Claude Code instance. Only registers tmux sessions."""
    # Skip registration for non-tmux processes (headless -p calls, subagents, etc.)
    if not os.environ.get("TMUX"):
        return None

    dynamo = get_dynamo()
    table = dynamo.Table("AgentTracker")
    tmux = _get_tmux_info()
    in_tmux = tmux is not None

    agent_id = get_agent_id()
    ppid = get_ppid()
    now = now_iso()

    # For orchestrator-managed sessions, just update heartbeat on existing entry
    if tmux and tmux["tmux_session"].startswith("agent-"):
        try:
            table.update_item(
                Key={"agent_id": agent_id},
                UpdateExpression="SET last_heartbeat = :hb, pid = :p",
                ExpressionAttributeValues={":hb": now, ":p": ppid},
                ConditionExpression="attribute_exists(agent_id)",
            )
        except Exception:
            pass
        return agent_id

    try:
        resp = table.get_item(Key={"agent_id": agent_id})
        existing = resp.get("Item")
        if existing and existing.get("status") in ("running", "idle"):
            # Update heartbeat + tmux info
            expr = "SET last_heartbeat = :hb, #s = :s, #t = :ttl"
            values = {":hb": now, ":s": "running", ":ttl": ttl_days(7)}
            names = {"#s": "status", "#t": "ttl"}
            if tmux:
                expr += ", tmux_session = :ts, tmux_window = :tw, tmux_index = :ti, interactive = :i"
                values[":ts"] = tmux["tmux_session"]
                values[":tw"] = tmux["tmux_window"]
                values[":ti"] = tmux["tmux_index"]
                values[":i"] = True
            table.update_item(
                Key={"agent_id": agent_id},
                UpdateExpression=expr,
                ExpressionAttributeValues=values,
                ExpressionAttributeNames=names,
            )
            return agent_id
        # If stale/completed but process is still alive, re-register as running
        if existing and existing.get("status") in ("stale", "completed"):
            expr = "SET last_heartbeat = :hb, #s = :s, #t = :ttl, ended_at = :na"
            values = {":hb": now, ":s": "running", ":ttl": ttl_days(7), ":na": None}
            names = {"#s": "status", "#t": "ttl"}
            if tmux:
                expr += ", tmux_session = :ts, tmux_window = :tw, tmux_index = :ti, interactive = :i"
                values[":ts"] = tmux["tmux_session"]
                values[":tw"] = tmux["tmux_window"]
                values[":ti"] = tmux["tmux_index"]
                values[":i"] = True
            table.update_item(
                Key={"agent_id": agent_id},
                UpdateExpression=expr,
                ExpressionAttributeValues=values,
                ExpressionAttributeNames=names,
            )
            return agent_id
    except Exception:
        pass

    # Build title from tmux window name or PID
    if tmux:
        title = f"tmux:{tmux['tmux_session']}:{tmux['tmux_window']}"
    else:
        title = f"Claude Code (PID {ppid})"

    # New registration
    record = {
        "agent_id": agent_id,
        "agent_type": "claude-code",
        "agent_name": f"Claude Code (PID {ppid})",
        "title": title,
        "status": "running",
        "current_task": "",
        "goal": "",
        "started_at": now,
        "last_heartbeat": now,
        "metrics": {},
        "host": socket.gethostname(),
        "pid": ppid,
        "ttl": ttl_days(7),
        "interactive": in_tmux,
    }
    if tmux:
        record["tmux_session"] = tmux["tmux_session"]
        record["tmux_window"] = tmux["tmux_window"]
        record["tmux_index"] = tmux["tmux_index"]
    table.put_item(Item=record)
    return agent_id

def log_message(message, level="info", **metadata):
    """Write a log entry to AgentLogs. No-op if not in tmux."""
    if not os.environ.get("TMUX"):
        return
    dynamo = get_dynamo()
    table = dynamo.Table("AgentLogs")
    agent_id = get_agent_id()
    record = {
        "agent_id": agent_id,
        "timestamp": now_ms(),
        "level": level,
        "message": message,
        "metadata": _convert_floats(metadata) if metadata else {},
        "ttl": ttl_days(3),
    }
    table.put_item(Item=record)

def log_chat(message, direction="outbound", sender=""):
    """Write a chat message to AgentChat (visible in app Chat tab). No-op if not in tmux."""
    if not os.environ.get("TMUX"):
        return
    dynamo = get_dynamo()
    table = dynamo.Table("AgentChat")
    agent_id = get_agent_id()
    record = {
        "agent_id": agent_id,
        "timestamp": now_ms(),
        "direction": direction,
        "message": message,
        "sender": sender,
        "ttl": ttl_days(7),
    }
    table.put_item(Item=record)

def update_task(task):
    """Update current_task and heartbeat. No-op if not in tmux. Only updates existing items."""
    if not os.environ.get("TMUX"):
        return
    dynamo = get_dynamo()
    table = dynamo.Table("AgentTracker")
    agent_id = get_agent_id()
    try:
        table.update_item(
            Key={"agent_id": agent_id},
            UpdateExpression="SET last_heartbeat = :hb, current_task = :ct, #t = :ttl",
            ExpressionAttributeValues={
                ":hb": now_iso(),
                ":ct": task,
                ":ttl": ttl_days(7),
            },
            ExpressionAttributeNames={"#t": "ttl"},
            ConditionExpression="attribute_exists(agent_id)",
        )
    except Exception:
        pass

def mark_completed():
    """Mark this agent as completed. No-op if not in tmux."""
    if not os.environ.get("TMUX"):
        return
    dynamo = get_dynamo()
    table = dynamo.Table("AgentTracker")
    agent_id = get_agent_id()
    table.update_item(
        Key={"agent_id": agent_id},
        UpdateExpression="SET #s = :s, ended_at = :e, last_heartbeat = :hb",
        ExpressionAttributeValues={
            ":s": "completed",
            ":e": now_iso(),
            ":hb": now_iso(),
        },
        ExpressionAttributeNames={"#s": "status"},
    )

def generate_title(prompt):
    """Generate a short human-readable title from the first user prompt using Haiku via claude CLI."""
    try:
        # Strip TMUX and CLAUDECODE so the Haiku subprocess doesn't trigger hooks
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "TMUX", "TMUX_PANE")}
        result = subprocess.run(
            ["/Users/bartimaeus/.local/bin/claude", "-p", "--model", "haiku",
             f"Generate a very short title (3-5 words, no quotes, no punctuation) for a coding session about: {prompt[:300]}"],
            capture_output=True, text=True, timeout=15, env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            title = result.stdout.strip().strip('"\'.')
            # Strip markdown formatting that Haiku sometimes adds
            title = title.split('\n')[0]  # First line only
            title = re.sub(r'\*+', '', title)  # Remove bold/italic markers
            title = re.sub(r'^(Title|Summary|Session)\s*:\s*', '', title, flags=re.IGNORECASE)  # Remove prefixes
            title = title.strip(' "\'.:')
            if title:
                return title[:50]
    except Exception:
        pass
    return None


def set_title(title):
    """Update agent title in DynamoDB and rename tmux window."""
    if not os.environ.get("TMUX"):
        return
    dynamo = get_dynamo()
    table = dynamo.Table("AgentTracker")
    agent_id = get_agent_id()
    table.update_item(
        Key={"agent_id": agent_id},
        UpdateExpression="SET title = :t, last_heartbeat = :hb",
        ExpressionAttributeValues={":t": title, ":hb": now_iso()},
    )
    # Rename tmux window only (session name is immutable — used for agent_id)
    if os.environ.get("TMUX"):
        try:
            subprocess.run(
                ["/opt/homebrew/bin/tmux", "rename-window", title[:40]],
                capture_output=True, text=True, timeout=2,
            )
        except Exception:
            pass


def needs_title():
    """Check if this agent still has the default auto-generated title."""
    if not os.environ.get("TMUX"):
        return False
    dynamo = get_dynamo()
    table = dynamo.Table("AgentTracker")
    agent_id = get_agent_id()
    try:
        resp = table.get_item(Key={"agent_id": agent_id})
        item = resp.get("Item")
        if not item:
            return True
        title = item.get("title", "")
        return title.startswith("tmux:") or title.startswith("Claude Code")
    except Exception:
        return False


def _convert_floats(item):
    if isinstance(item, dict):
        return {k: _convert_floats(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [_convert_floats(i) for i in item]
    elif isinstance(item, float):
        return Decimal(str(item))
    return item
