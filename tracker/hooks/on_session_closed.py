#!/usr/bin/env python3
"""Tmux session-closed hook — mark dead sessions as completed+hidden in AgentTracker."""
import boto3
import subprocess

TMUX = "/opt/homebrew/bin/tmux"
AWS_REGION = "us-east-1"


def main():
    dynamo = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = dynamo.Table("AgentTracker")

    # Get all live tmux session names
    try:
        result = subprocess.run(
            [TMUX, "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=5,
        )
        live_sessions = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
    except Exception:
        return  # can't determine live sessions, bail

    # Scan AgentTracker for active entries with tmux sessions
    resp = table.scan()
    for item in resp.get("Items", []):
        status = item.get("status", "")
        if status in ("completed",):
            continue
        tmux_session = item.get("tmux_session", "")
        if not tmux_session:
            continue
        if tmux_session not in live_sessions:
            table.update_item(
                Key={"agent_id": item["agent_id"]},
                UpdateExpression="SET #s = :s, #h = :h",
                ExpressionAttributeValues={":s": "completed", ":h": True},
                ExpressionAttributeNames={"#s": "status", "#h": "hidden"},
            )


if __name__ == "__main__":
    main()
