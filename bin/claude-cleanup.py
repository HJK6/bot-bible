#!/usr/bin/env python3
"""Daily cleanup for Claude Code sessions and DynamoDB agent entries.

Deletes:
- ~/.claude/session-env/<id>/     (older than 1 day)
- ~/.claude/debug/<file>          (older than 1 day)
- ~/.claude/todos/<file>          (older than 1 day)
- ~/.claude/file-history/<id>/    (older than 1 day)
- ~/.claude/tasks/<id>/           (older than 1 day)
- ~/.claude/plans/<file>          (older than 1 day)
- DynamoDB AgentTracker entries   (heartbeat > 1 day, not running)
- DynamoDB AgentLogs entries      (timestamp > 1 day)
- Trashed agents                  (trashed_at > 48 hours — full data purge)

Scheduled via: ~/bin/schedule recurring "04:00 daily" "~/.venvs/global/bin/python ~/bin/claude-cleanup.py" --tag claude-cleanup
"""

import os
import shutil
import time
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [cleanup] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

CLAUDE_DIR = Path.home() / ".claude"
AGE_SECONDS = 86400  # 1 day
TRASH_AGE_SECONDS = 86400 * 2  # 48 hours


def clean_old_files(directory: Path, age_seconds: int = AGE_SECONDS) -> int:
    """Delete files older than age_seconds in a directory. Returns count deleted."""
    if not directory.exists():
        return 0
    cutoff = time.time() - age_seconds
    deleted = 0
    for item in directory.iterdir():
        try:
            mtime = item.stat().st_mtime
            if mtime < cutoff:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                deleted += 1
        except Exception as e:
            log.warning(f"Failed to delete {item}: {e}")
    return deleted


def clean_dynamo_agent_tracker() -> int:
    """Delete non-running AgentTracker entries.

    Removes:
    - All 'completed', 'failed', 'stale' entries
    - All 'idle' claude-agent entries (orchestrator keeps heartbeats fresh, but
      these are finished conversations that should not stay visible in the app)
    - Any entry with heartbeat > 1 day that isn't 'running'
    Keeps:
    - All 'running' entries (active processes)
    - 'idle' non-claude-agent entries (bots like stock-scraper, ibkr-collector)
    """
    try:
        import boto3
        dynamo = boto3.resource("dynamodb", region_name="us-east-1")
        tracker = dynamo.Table("AgentTracker")

        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=AGE_SECONDS)).isoformat()

        items = []
        response = tracker.scan()
        items.extend(response["Items"])
        while "LastEvaluatedKey" in response:
            response = tracker.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response["Items"])

        to_delete = []
        for i in items:
            status = i.get("status", "")
            agent_type = i.get("agent_type", "")
            hb = i.get("last_heartbeat", "")

            # Always keep running agents
            if status == "running":
                continue
            # Skip trashed agents — handled by reap_trashed_agents with 48h grace period
            if status == "trashed":
                continue
            # Delete idle claude-agents (finished conversations kept alive by orchestrator)
            if status == "idle" and agent_type == "claude-agent":
                to_delete.append(i)
            # Delete completed/failed/stale
            elif status in ("completed", "failed", "stale"):
                to_delete.append(i)
            # Delete anything with old heartbeat
            elif hb and hb < cutoff:
                to_delete.append(i)

        deleted = 0
        with tracker.batch_writer() as batch:
            for item in to_delete:
                batch.delete_item(Key={"agent_id": item["agent_id"]})
                deleted += 1

        return deleted
    except Exception as e:
        log.warning(f"AgentTracker cleanup failed: {e}")
        return 0


def clean_dynamo_agent_logs() -> int:
    """Delete AgentLogs entries older than 1 day."""
    try:
        import boto3
        dynamo = boto3.resource("dynamodb", region_name="us-east-1")
        logs = dynamo.Table("AgentLogs")

        cutoff_ms = int((time.time() - AGE_SECONDS) * 1000)

        items = []
        response = logs.scan()
        items.extend(response["Items"])
        while "LastEvaluatedKey" in response:
            response = logs.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response["Items"])

        old = [i for i in items if int(i.get("timestamp", 0)) < cutoff_ms]

        deleted = 0
        with logs.batch_writer() as batch:
            for item in old:
                batch.delete_item(
                    Key={"agent_id": item["agent_id"], "timestamp": item["timestamp"]}
                )
                deleted += 1

        return deleted
    except Exception as e:
        log.warning(f"AgentLogs cleanup failed: {e}")
        return 0


def reap_trashed_agents() -> int:
    """Permanently delete agents that have been in trash for 48+ hours.

    Kills the tmux session (kept alive for restore) and removes the AgentTracker
    entry plus all associated AgentLogs and AgentChat records.
    """
    try:
        import subprocess
        import boto3
        from boto3.dynamodb.conditions import Key, Attr
        dynamo = boto3.resource("dynamodb", region_name="us-east-1")
        tracker = dynamo.Table("AgentTracker")
        logs = dynamo.Table("AgentLogs")
        chat = dynamo.Table("AgentChat")

        TMUX = "/opt/homebrew/bin/tmux"
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=TRASH_AGE_SECONDS)).isoformat()

        # Find all trashed agents older than 48h
        response = tracker.scan(
            FilterExpression=Attr("status").eq("trashed") & Attr("trashed_at").lt(cutoff)
        )
        items = response["Items"]
        while "LastEvaluatedKey" in response:
            response = tracker.scan(
                FilterExpression=Attr("status").eq("trashed") & Attr("trashed_at").lt(cutoff),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response["Items"])

        reaped = 0
        for item in items:
            agent_id = item["agent_id"]
            # Kill tmux session if still alive
            tmux_session = item.get("tmux_session", "")
            if tmux_session:
                try:
                    subprocess.run(
                        [TMUX, "kill-session", "-t", tmux_session],
                        capture_output=True, text=True, timeout=5,
                    )
                    log.info(f"  Killed tmux session {tmux_session} for agent {agent_id[:8]}")
                except Exception:
                    pass
            # Delete logs
            try:
                log_resp = logs.query(KeyConditionExpression=Key("agent_id").eq(agent_id))
                with logs.batch_writer() as batch:
                    for log_item in log_resp.get("Items", []):
                        batch.delete_item(Key={"agent_id": agent_id, "timestamp": log_item["timestamp"]})
            except Exception:
                pass
            # Delete chat
            try:
                chat_resp = chat.query(KeyConditionExpression=Key("agent_id").eq(agent_id))
                with chat.batch_writer() as batch:
                    for chat_item in chat_resp.get("Items", []):
                        batch.delete_item(Key={"agent_id": agent_id, "timestamp": chat_item["timestamp"]})
            except Exception:
                pass
            # Delete tracker entry
            try:
                tracker.delete_item(Key={"agent_id": agent_id})
            except Exception:
                pass
            reaped += 1
            log.info(f"  Reaped trashed agent {agent_id[:8]} (trashed at {item.get('trashed_at', '?')})")

        return reaped
    except Exception as e:
        log.warning(f"Trashed agent reaper failed: {e}")
        return 0


def main():
    log.info("Starting Claude Code cleanup...")

    results = {}
    for name in ["session-env", "debug", "todos", "file-history", "tasks", "plans"]:
        d = CLAUDE_DIR / name
        count = clean_old_files(d)
        results[name] = count
        if count:
            log.info(f"  {name}: deleted {count} old items")

    tracker_count = clean_dynamo_agent_tracker()
    if tracker_count:
        log.info(f"  AgentTracker: deleted {tracker_count} old entries")
    results["AgentTracker"] = tracker_count

    logs_count = clean_dynamo_agent_logs()
    if logs_count:
        log.info(f"  AgentLogs: deleted {logs_count} old entries")
    results["AgentLogs"] = logs_count

    reaped_count = reap_trashed_agents()
    if reaped_count:
        log.info(f"  TrashedAgents: reaped {reaped_count} agents")
    results["TrashedAgents"] = reaped_count

    total = sum(results.values())
    if total:
        log.info(f"Cleanup complete: {total} total items removed")
    else:
        log.info("Cleanup complete: nothing to remove")


if __name__ == "__main__":
    main()
