#!/usr/bin/env python3
"""
tmux watcher — polls AgentCommands for messages targeting tmux Claude sessions
and delivers them via `tmux send-keys`.

Run alongside tmux: python3 tmux_watcher.py &
Stops automatically when no tmux claude sessions remain.
"""
import os
import sys
import time
import json
import subprocess
import logging
import boto3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [tmux-watcher] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
POLL_INTERVAL = 3  # seconds
TMUX = "/opt/homebrew/bin/tmux"


def get_dynamo():
    return boto3.resource("dynamodb", region_name=AWS_REGION)


def get_tmux_agents(dynamo):
    """Get all running/idle claude-code agents that have tmux metadata."""
    table = dynamo.Table("AgentTracker")
    resp = table.scan()
    agents = []
    for item in resp.get("Items", []):
        if (
            item.get("status") in ("running", "idle", "stale")
            and item.get("tmux_session")
            and not item.get("hidden")
        ):
            agents.append(item)
    return agents


def get_pending_commands(dynamo):
    """Get pending commands from AgentCommands."""
    table = dynamo.Table("AgentCommands")
    resp = table.scan()
    return [
        c for c in resp.get("Items", [])
        if c.get("status") == "pending"
        and c.get("command") == "send_message"
    ]


def mark_command_done(dynamo, command_id):
    """Mark a command as completed."""
    table = dynamo.Table("AgentCommands")
    table.update_item(
        Key={"command_id": command_id},
        UpdateExpression="SET #s = :s, completed_at = :t",
        ExpressionAttributeValues={
            ":s": "completed",
            ":t": int(time.time()),
        },
        ExpressionAttributeNames={"#s": "status"},
    )


def deliver_to_tmux(session_name, window_index, message):
    """Send a message to a tmux pane via send-keys."""
    target = f"{session_name}:{window_index}"
    try:
        # Send literal text, then Enter key separately
        subprocess.run(
            [TMUX, "send-keys", "-t", target, "-l", message],
            capture_output=True, text=True, timeout=5,
        )
        subprocess.run(
            [TMUX, "send-keys", "-t", target, "Enter"],
            capture_output=True, text=True, timeout=5,
        )
        log.info(f"Delivered to {target}: {message[:80]}...")
        return True
    except Exception as e:
        log.error(f"Failed to deliver to {target}: {e}")
        return False


def log_chat_inbound(dynamo, agent_id, message):
    """Log the inbound message to AgentChat so it shows in the app."""
    table = dynamo.Table("AgentChat")
    table.put_item(Item={
        "agent_id": agent_id,
        "timestamp": int(time.time() * 1000),
        "direction": "inbound",
        "message": message,
        "sender": "mobile",
        "ttl": int(time.time()) + (7 * 86400),
    })


def tmux_session_exists():
    """Check if the claude tmux session still exists."""
    try:
        result = subprocess.run(
            [TMUX, "has-session", "-t", "claude"],
            capture_output=True, timeout=2,
        )
        return result.returncode == 0
    except Exception:
        return False


def main():
    log.info("Starting tmux watcher")
    dynamo = get_dynamo()

    while True:
        try:
            # Stop if no tmux claude session
            if not tmux_session_exists():
                log.info("No claude tmux session found, exiting")
                break

            # Get tmux agents and pending commands
            agents = get_tmux_agents(dynamo)
            if not agents:
                time.sleep(POLL_INTERVAL)
                continue

            agent_map = {a["agent_id"]: a for a in agents}
            commands = get_pending_commands(dynamo)

            for cmd in commands:
                payload = cmd.get("payload", {})
                target_agent_id = payload.get("agent_id", "")
                message = payload.get("message", "")

                if not message or target_agent_id not in agent_map:
                    continue

                agent = agent_map[target_agent_id]
                session_name = agent["tmux_session"]
                window_index = agent.get("tmux_index", 0)

                # Log inbound message to chat
                log_chat_inbound(dynamo, target_agent_id, message)

                # Deliver to tmux pane
                if deliver_to_tmux(session_name, window_index, message):
                    mark_command_done(dynamo, cmd["command_id"])

        except Exception as e:
            log.error(f"Error in poll loop: {e}")

        time.sleep(POLL_INTERVAL)

    log.info("tmux watcher stopped")


if __name__ == "__main__":
    main()
