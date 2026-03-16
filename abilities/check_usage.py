#!/usr/bin/env python3
"""Check Claude Code rate limit usage via tmux + /usage command.

Spawns a tmux session, runs claude's /usage command, parses the output,
optionally writes to DynamoDB for the mobile app.

Usage:
    py check_usage.py          # Print usage
    py check_usage.py --save   # Print + save to DynamoDB
"""
import subprocess
import time
import re
import json
import sys
from datetime import datetime, timezone


def collect_usage() -> dict:
    """Spawn tmux, run claude /usage, parse output, cleanup."""
    session = f"usage-check-{int(time.time())}"

    try:
        # Start tmux session with wide terminal
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session, "-x", "200", "-y", "50"],
            check=True,
        )
        # Launch claude
        subprocess.run(["tmux", "send-keys", "-t", session, "claude", "Enter"], check=True)

        # Wait for trust prompt or ready state
        for _ in range(15):
            time.sleep(1)
            output = _capture(session)
            if "Yes, I trust this folder" in output:
                subprocess.run(["tmux", "send-keys", "-t", session, "Enter"], check=True)
                time.sleep(3)
                break
            if "for shortcuts" in output:
                break

        # Send /usage
        subprocess.run(["tmux", "send-keys", "-t", session, "/usage", "Enter"], check=True)
        time.sleep(3)

        # Capture output
        output = _capture(session)

        # Exit claude
        subprocess.run(["tmux", "send-keys", "-t", session, "Escape", ""], check=True)
        time.sleep(1)
        subprocess.run(["tmux", "send-keys", "-t", session, "/exit", "Enter"], check=True)
        time.sleep(2)

        return _parse_usage(output)

    finally:
        # Cleanup
        subprocess.run(["tmux", "kill-session", "-t", session], capture_output=True)


def _capture(session: str) -> str:
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", session, "-p"],
        capture_output=True,
        text=True,
    )
    return result.stdout


def _parse_usage(output: str) -> dict:
    """Parse the /usage command output."""
    now = datetime.now(timezone.utc).isoformat()
    usage = {"last_refreshed": now}

    # Parse percentage bars: "███████▌                   15% used"
    pct_pattern = r"(\d+)%\s+used"
    pct_matches = re.findall(pct_pattern, output)

    # Parse reset times
    # "Resets 5am (America/Chicago)" or "Resets Mar 16 at 7pm (America/Chicago)"
    reset_pattern = r"Resets\s+(.+?)(?:\n|$)"
    reset_matches = re.findall(reset_pattern, output)

    # Map sections by order: session, week (all), week (sonnet)
    sections = ["session", "week_all", "week_sonnet"]
    for i, section in enumerate(sections):
        usage[section] = {
            "pct": int(pct_matches[i]) if i < len(pct_matches) else None,
            "resets": reset_matches[i].strip() if i < len(reset_matches) else None,
        }

    # Extra usage
    if "Extra usage not enabled" in output:
        usage["extra_usage"] = "not_enabled"
    elif "Extra usage" in output:
        usage["extra_usage"] = "enabled"

    return usage


def save_to_dynamo(usage: dict):
    """Write usage data to DynamoDB BotTracker."""
    import boto3
    from decimal import Decimal

    dynamo = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamo.Table("BotTracker")

    table.put_item(
        Item={
            "bot_id": "system:claude-usage",
            "bot_type": "system",
            "bot_name": "claude-usage",
            "title": "Claude Code Usage",
            "status": "system",
            "last_heartbeat": usage["last_refreshed"],
            "session_pct": Decimal(str(usage["session"]["pct"])) if usage["session"]["pct"] is not None else Decimal("0"),
            "session_resets": usage["session"].get("resets", ""),
            "week_all_pct": Decimal(str(usage["week_all"]["pct"])) if usage["week_all"]["pct"] is not None else Decimal("0"),
            "week_all_resets": usage["week_all"].get("resets", ""),
            "week_sonnet_pct": Decimal(str(usage["week_sonnet"]["pct"])) if usage["week_sonnet"]["pct"] is not None else Decimal("0"),
            "week_sonnet_resets": usage["week_sonnet"].get("resets", ""),
            "extra_usage": usage.get("extra_usage", "unknown"),
            "ttl": int(time.time()) + 86400,  # 24h TTL
        }
    )


def format_usage(usage: dict) -> str:
    """Pretty print usage."""
    def bar(pct):
        if pct is None:
            return "N/A"
        filled = pct // 5
        return f"[{'#' * filled}{'.' * (20 - filled)}] {pct}%"

    lines = [
        f"Session (5h):    {bar(usage['session']['pct'])}",
        f"  Resets: {usage['session'].get('resets', 'N/A')}",
        "",
        f"Week (all):      {bar(usage['week_all']['pct'])}",
        f"  Resets: {usage['week_all'].get('resets', 'N/A')}",
        "",
        f"Week (Sonnet):   {bar(usage['week_sonnet']['pct'])}",
        f"  Resets: {usage['week_sonnet'].get('resets', 'N/A')}",
        "",
        f"Extra usage: {usage.get('extra_usage', 'unknown')}",
        f"Last refreshed: {usage['last_refreshed']}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    usage = collect_usage()
    print(format_usage(usage))

    if "--save" in sys.argv:
        save_to_dynamo(usage)
        print("\nSaved to DynamoDB.")
