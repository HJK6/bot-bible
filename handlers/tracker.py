import json
import uuid
import time
from datetime import datetime, timezone
from modules.Dynamo import Table
from modules.Config import AGENT_TRACKER_TABLE, AGENT_LOGS_TABLE, AGENT_COMMANDS_TABLE, AGENT_CHAT_TABLE, PUSH_TOKENS_TABLE, BOT_TRACKER_TABLE
from handlers.apigw import apigw_adapter

@apigw_adapter
def getAgentsHandler(event, context):
    """Get all agents. Only hidden (user-deleted) and incomplete entries are filtered out."""
    table = Table(AGENT_TRACKER_TABLE)
    agents = table.get_all()

    # Filter out hidden (user-deleted) and incomplete/ghost entries
    agents = [a for a in agents if not a.get("hidden") and a.get("title")]
    agents.sort(key=lambda a: a.get("started_at", ""), reverse=True)
    return agents


@apigw_adapter
def getBotsHandler(event, context):
    """Get all bots from BotTracker table. Auto-reaps stale bots that stopped heartbeating."""
    table = Table(BOT_TRACKER_TABLE)
    bots = table.get_all()

    now = datetime.now(timezone.utc)
    stale_threshold = 30 * 60  # 30 minutes without heartbeat = stale
    always_on_types = {"telegram-bot", "task-worker"}  # orchestrator, task worker
    always_on_names = {"announcements poller"}  # stock poller - always running
    result = []

    for b in bots:
        if b.get("bot_type") == "system":
            continue
        if b.get("status") != "running" or not b.get("title"):
            continue
        # Check heartbeat staleness
        hb = b.get("last_heartbeat", "")
        if hb and b.get("bot_type", "") not in always_on_types and b.get("bot_name", "").lower() not in always_on_names:
            try:
                hb_time = datetime.fromisoformat(hb.replace("Z", "+00:00"))
                if hb_time.tzinfo is None:
                    hb_time = hb_time.replace(tzinfo=timezone.utc)
                age = (now - hb_time).total_seconds()
                if age > stale_threshold:
                    # Auto-reap: mark as completed
                    table.updateItem(
                        {"bot_id": b["bot_id"]},
                        "SET #s = :s, ended_at = :e",
                        {":s": "stale", ":e": now.isoformat()},
                        {"#s": "status"},
                    )
                    continue
            except (ValueError, TypeError):
                pass
        result.append(b)

    result.sort(key=lambda b: b.get("started_at", ""), reverse=True)
    return result


@apigw_adapter
def getScheduledJobsHandler(event, context):
    """Get scheduled jobs synced from the local machine."""
    import boto3
    s3 = boto3.client("s3", region_name="us-east-1")
    try:
        obj = s3.get_object(Bucket="altum-deployment-assets", Key="schedule/jobs.json")
        data = json.loads(obj["Body"].read())
        return data
    except s3.exceptions.NoSuchKey:
        return {"jobs": [], "synced_at": None}


@apigw_adapter
def getAgentLogsHandler(event, context):
    """Get logs for an agent."""
    agent_id = event.get("agent_id", "")
    limit = event.get("limit", 100)

    table = Table(AGENT_LOGS_TABLE)
    logs = table.query_pk("agent_id", agent_id, scan_forward=False, limit=limit)
    return logs


@apigw_adapter
def getAgentChatHandler(event, context):
    """Get chat messages for an agent."""
    import re
    import boto3

    agent_id = event.get("agent_id", "")
    limit = event.get("limit", 50)

    table = Table(AGENT_CHAT_TABLE)
    messages = table.query_pk("agent_id", agent_id, scan_forward=False, limit=limit)

    # Generate presigned URLs for any image_url fields (S3 objects are private)
    s3_client = None
    for msg in messages:
        image_url = msg.get("image_url", "")
        if not image_url:
            continue
        s3_match = re.match(r"https://(.+?)\.s3\.(.+?)\.amazonaws\.com/(.+)", image_url)
        if s3_match:
            if not s3_client:
                s3_client = boto3.client("s3", region_name="us-east-1")
            bucket = s3_match.group(1)
            key = s3_match.group(3)
            try:
                msg["image_url"] = s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket, "Key": key},
                    ExpiresIn=3600,
                )
            except Exception:
                pass  # keep original URL as fallback

    return messages


@apigw_adapter
def createCommandHandler(event, context):
    """Create a command for the orchestrator to pick up."""
    command = event.get("command", "")
    payload = event.get("payload", {})

    table = Table(AGENT_COMMANDS_TABLE)
    command_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    ttl = int(time.time()) + 86400  # 1 day

    record = {
        "command_id": command_id,
        "command": command,
        "payload": payload,
        "status": "pending",
        "created_at": now,
        "ttl": ttl,
    }
    table.write(record)
    return {"status": "success", "command_id": command_id}


@apigw_adapter
def updateAgentHandler(event, context):
    """Update agent fields (title, agent_name, goal, etc)."""
    agent_id = event.get("agent_id", "")

    expr_parts = []
    expr_values = {}
    expr_names = {}

    if "title" in event:
        expr_parts.append("#t = :t")
        expr_values[":t"] = event["title"]
        expr_names["#t"] = "title"

    if "agent_name" in event:
        expr_parts.append("agent_name = :n")
        expr_values[":n"] = event["agent_name"]

    if "goal" in event:
        expr_parts.append("goal = :g")
        expr_values[":g"] = event["goal"]

    if not expr_parts:
        return {"status": "error", "message": "No fields to update"}

    table = Table(AGENT_TRACKER_TABLE)
    table.updateItem(
        {"agent_id": agent_id},
        "SET " + ", ".join(expr_parts),
        expr_values,
        expr_names if expr_names else None,
    )
    return {"status": "success"}


@apigw_adapter
def deleteAgentHandler(event, context):
    """Delete an agent — hides from dashboard and sends stop command to kill tmux session."""
    agent_id = event.get("agent_id", "")

    tracker_table = Table(AGENT_TRACKER_TABLE)
    tracker_table.updateItem(
        {"agent_id": agent_id},
        "SET #h = :h, hidden_at = :t",
        {":h": True, ":t": datetime.now(timezone.utc).isoformat()},
        {"#h": "hidden"},
    )

    # Send stop command so orchestrator kills the tmux session
    commands_table = Table(AGENT_COMMANDS_TABLE)
    commands_table.write({
        "command_id": str(uuid.uuid4()),
        "command": "delete_agent",
        "payload": {"agent_id": agent_id},
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ttl": int(time.time()) + 86400,
    })

    return {"status": "success"}


@apigw_adapter
def getTrashedAgentsHandler(event, context):
    """Get trashed (soft-deleted) agents for the trash view."""
    table = Table(AGENT_TRACKER_TABLE)
    agents = table.filter("status", "trashed")
    agents = [a for a in agents if a.get("title")]
    agents.sort(key=lambda a: a.get("trashed_at", ""), reverse=True)
    return agents


@apigw_adapter
def restoreAgentHandler(event, context):
    """Restore a trashed agent back to the active list."""
    agent_id = event.get("agent_id", "")
    if not agent_id:
        return {"code": 400, "status": "error", "message": "Missing agent_id"}

    table = Table(AGENT_TRACKER_TABLE)
    table.updateItem(
        {"agent_id": agent_id},
        "SET #s = :s, #h = :h REMOVE trashed_at, hidden_at",
        {":s": "idle", ":h": False},
        {"#s": "status", "#h": "hidden"},
    )
    return {"status": "success"}


@apigw_adapter
def getCommandsHandler(event, context):
    """Get pending commands (for orchestrator polling)."""
    table = Table(AGENT_COMMANDS_TABLE)
    commands = table.filter("status", "pending")
    commands.sort(key=lambda c: c.get("created_at", ""))
    return commands


@apigw_adapter
def registerPushTokenHandler(event, context):
    """Register a device push token for notifications."""
    push_token = event.get("push_token", "")
    platform = event.get("platform", "ios")
    device_name = event.get("device_name", "")

    if not push_token:
        return {"code": 400, "status": "error", "message": "Missing push_token"}

    table = Table(PUSH_TOKENS_TABLE)
    now = datetime.now(timezone.utc).isoformat()

    record = {
        "push_token": push_token,
        "platform": platform,
        "device_name": device_name,
        "registered_at": now,
        "active": True,
        "ttl": int(time.time()) + 86400 * 90,  # 90 days
    }
    table.write(record)
    return {"status": "success"}


@apigw_adapter
def getUsageHandler(event, context):
    """Get Claude Code usage data from BotTracker."""
    table = Table(BOT_TRACKER_TABLE)
    try:
        item = table.table.get_item(Key={"bot_id": "system:claude-usage"}).get("Item")
        if not item:
            return {"status": "no_data"}
        # Convert Decimals to int for JSON
        for key in ("session_pct", "week_all_pct", "week_sonnet_pct"):
            if key in item:
                item[key] = int(item[key])
        return item
    except Exception as e:
        return {"code": 500, "status": "error", "message": str(e)}
