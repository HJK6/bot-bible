#!/usr/bin/env python3
"""YOUR_BOT_NAME morning briefing — weekday 9 AM analysis of queue health and call days."""

import boto3
import boto3.dynamodb.conditions
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict

CONFIG_PATH = Path.home() / ".config" / "YOUR_BOT_NAME" / "heartbeat.json"
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

NEXT_SCOUT_LEAD_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/YOUR_AWS_ACCOUNT_ID/NextScoutLead"
NEXT_ENVOY_LEAD_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/YOUR_AWS_ACCOUNT_ID/NextEnvoyLead"

DEFAULT_CONFIG = {
    "times": ["9:00"],
    "days": "weekdays",
    "enabled": True,
}


def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
    return DEFAULT_CONFIG


def should_fire(now: datetime, config: dict) -> bool:
    """Check if current time matches configured schedule."""
    times = config.get("times", DEFAULT_CONFIG["times"])
    days = config.get("days", "weekdays")

    # Check day of week (0=Monday, 6=Sunday)
    weekday = now.weekday()
    if days == "weekdays" and weekday >= 5:
        return False
    elif days == "weekends" and weekday < 5:
        return False

    h, m = now.hour, now.minute
    for pattern in times:
        if ":" not in pattern:
            continue
        ph, pm = pattern.split(":", 1)

        if ph == "*":
            hour_match = True
        elif ph.startswith("*/"):
            step = int(ph[2:])
            hour_match = (h % step == 0)
        else:
            hour_match = (h == int(ph))

        if pm == "*":
            min_match = True
        elif pm.startswith("*/"):
            step = int(pm[2:])
            min_match = (m % step == 0)
        else:
            min_match = (m == int(pm))

        if hour_match and min_match:
            return True

    return False


def check_lambda_ran():
    """Check if populateNextBestLeadQueue Lambda ran successfully today."""
    logs_client = boto3.client('logs', region_name='us-east-1')
    log_group = '/aws/lambda/populateNextBestLeadQueue'

    # Lambda runs at cron(0 12 * * ? *) = 12:00 PM UTC daily (~6-7 AM local)
    now_utc = datetime.now(timezone.utc)
    start_time = int((now_utc - timedelta(hours=6)).timestamp() * 1000)
    end_time = int(now_utc.timestamp() * 1000)

    try:
        response = logs_client.filter_log_events(
            logGroupName=log_group,
            startTime=start_time,
            endTime=end_time,
            filterPattern='REPORT RequestId',
            limit=5,
        )
        events = response.get('events', [])
        if not events:
            return False, "No invocations found in last 6 hours"

        last_msg = events[-1].get('message', '')
        # Parse duration and errors from REPORT line
        if 'Error' in last_msg or 'Timeout' in last_msg:
            return False, f"Ran with errors"

        # Extract duration if available
        duration = ""
        if 'Duration:' in last_msg:
            try:
                dur_part = last_msg.split('Duration:')[1].split('ms')[0].strip()
                dur_sec = round(float(dur_part) / 1000, 1)
                duration = f" in {dur_sec}s"
            except (ValueError, IndexError):
                pass

        ts = events[-1].get('timestamp', 0)
        run_time = datetime.fromtimestamp(ts / 1000).strftime('%I:%M %p')
        return True, f"Ran at {run_time}{duration}"

    except Exception as e:
        return False, f"Could not check logs: {e}"


def get_queue_counts():
    """Get approximate message counts for lead queues."""
    sqs = boto3.client('sqs', region_name='us-east-1')
    counts = {}
    for name, url in [("Scout", NEXT_SCOUT_LEAD_QUEUE_URL), ("Envoy", NEXT_ENVOY_LEAD_QUEUE_URL)]:
        try:
            response = sqs.get_queue_attributes(
                QueueUrl=url,
                AttributeNames=["ApproximateNumberOfMessages"]
            )
            counts[name] = int(response["Attributes"]["ApproximateNumberOfMessages"])
        except Exception as e:
            counts[name] = f"Error: {e}"
    return counts


def get_call_days_report():
    """Generate call days distribution for COLD leads."""
    dynamo = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamo.Table('Leads')

    items = []
    scan_kwargs = {
        'ProjectionExpression': '#s, #o, #c, #sk',
        'ExpressionAttributeNames': {
            '#s': 'status', '#o': 'owner_id', '#c': 'call_logs', '#sk': 'sk'
        },
    }

    while True:
        response = table.scan(**scan_kwargs)
        items.extend(response.get('Items', []))
        if 'LastEvaluatedKey' not in response:
            break
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']

    items = [i for i in items if i.get('sk') == 'PROFILE']
    items = [i for i in items if not (i.get('owner_id') and 'test' in str(i.get('owner_id')).lower())]
    items = [i for i in items if (i.get('status') or '').strip() != 'DEPRECATED']
    cold_leads = [i for i in items if (i.get('status') or '').strip() == 'COLD']

    call_days_dist = defaultdict(int)
    for owner in cold_leads:
        call_logs = owner.get('call_logs', []) or []
        if not call_logs:
            call_days_dist[0] += 1
            continue
        call_dates = set()
        for log in call_logs:
            if not isinstance(log, dict):
                continue
            ts = log.get('timestamp')
            if ts is not None:
                try:
                    call_dates.add(datetime.fromtimestamp(float(ts)).date())
                except (ValueError, TypeError):
                    pass
        call_days_dist[len(call_dates) if call_dates else 0] += 1

    return len(cold_leads), call_days_dist


def send_push_notification(title, body):
    """Send push notification via Expo Push API."""
    from boto3.dynamodb.conditions import Attr
    dynamo = boto3.resource('dynamodb', region_name='us-east-1')
    tokens_table = dynamo.Table('PushTokens')

    try:
        response = tokens_table.scan(FilterExpression=Attr("active").eq(True))
        tokens = response.get("Items", [])
        if not tokens:
            print("No active push tokens found")
            return

        truncated_body = body[:200] + "..." if len(body) > 200 else body

        messages = []
        for token_record in tokens:
            push_token = token_record.get("push_token", "")
            if not push_token:
                continue
            messages.append({
                "to": push_token,
                "title": title,
                "body": truncated_body,
                "sound": "default",
                "data": {
                    "agent_id": "system",
                    "agent_title": "System",
                },
                "badge": 1,
            })

        if not messages:
            return

        data = json.dumps(messages).encode("utf-8")
        req = urllib.request.Request(
            EXPO_PUSH_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print(f"Push notification sent: {result}")
    except Exception as e:
        print(f"Failed to send push notification: {e}")


def send_update(message):
    """Write to AgentChat table AND send push notification."""
    dynamo = boto3.resource('dynamodb', region_name='us-east-1')
    dynamo.Table('AgentChat').put_item(Item={
        'agent_id': 'system',
        'timestamp': int(time.time() * 1000),
        'direction': 'outbound',
        'message': message,
        'sender': 'YOUR_BOT_NAME',
        'ttl': int(time.time()) + (7 * 86400),
    })
    send_push_notification("[System]", message)
    print(f"Update sent: {message[:100]}...")


def run_morning_briefing():
    """Generate and send the morning briefing."""
    parts = []
    now = datetime.now()
    parts.append(f"Morning Briefing — {now.strftime('%A, %b %d')}")
    parts.append("")

    # 1. Populate queues lambda status
    success, status = check_lambda_ran()
    icon = "OK" if success else "WARN"
    parts.append(f"[{icon}] Populate Queues: {status}")

    # 2. Queue counts
    counts = get_queue_counts()
    parts.append("")
    parts.append("Lead Queues:")
    for name, count in counts.items():
        parts.append(f"  {name}: {count} leads")

    # 3. Call days report
    total_cold, dist = get_call_days_report()
    parts.append("")
    parts.append(f"Call Days ({total_cold} COLD leads):")
    for d in sorted(dist.keys()):
        label = 'Never called' if d == 0 else f'{d} day(s)'
        parts.append(f"  {label}: {dist[d]}")

    message = "\n".join(parts)
    send_update(message)


def main():
    config = load_config()

    if not config.get("enabled", True):
        return

    now = datetime.now()

    if should_fire(now, config):
        run_morning_briefing()


if __name__ == "__main__":
    main()
