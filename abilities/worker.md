# Task Worker Bot

SQS-driven task runner that polls the BartimaeusRequests queue and dispatches tasks to repo-specific task files.

## Location

Repo: `/Users/bartimaeus/task-worker/`

## How to Start

```bash
cd /Users/bartimaeus/task-worker
caffeinate -dims python3 worker.py > /tmp/task_worker.log 2>&1 &
```

## How It Works

1. Long-polls `BartimaeusRequests` SQS queue (20s intervals)
2. Receives messages with format: `{"repo": "land-bot", "task": "taskName", "data": {...}}`
3. Maps repo name to local path, `git pull --ff-only` to get latest code
4. Imports `tasks/{taskName}.py` from the repo and calls `run(data)`
5. Deletes message from queue on success; leaves it for retry on failure

## SQS Queue

- **Queue**: `BartimaeusRequests`
- **URL**: `https://sqs.us-east-1.amazonaws.com/YOUR_AWS_ACCOUNT_ID/BartimaeusRequests`
- **Visibility timeout**: 300s (5 min per task before retry)

## Sending Tasks

```bash
aws sqs send-message \
  --queue-url "https://sqs.us-east-1.amazonaws.com/YOUR_AWS_ACCOUNT_ID/BartimaeusRequests" \
  --message-body '{"repo": "land-bot", "task": "testTask", "data": {"test": true}}' \
  --region us-east-1
```

Or from Python:
```python
import boto3, json
sqs = boto3.client("sqs", region_name="us-east-1")
sqs.send_message(
    QueueUrl="https://sqs.us-east-1.amazonaws.com/YOUR_AWS_ACCOUNT_ID/BartimaeusRequests",
    MessageBody=json.dumps({"repo": "land-bot", "task": "aggregatePropertyData", "data": {"account_id": "123", "county": "DALLAS"}})
)
```

## Supported Repos

| Repo | Local Path | Available Tasks |
|------|-----------|-----------------|
| `land-bot` | `/Users/bartimaeus/land-bot` | `testTask`, `aggregatePropertyData`, `refreshPropertyData`, `hydrate_skiptrace_data`, `scrape_preforeclosures`, `scrape_taxsales` |

To add a new repo, add it to `REPO_MAP` in `worker.py`.

## Task File Contract

Each task file in `tasks/` must export a `run()` function:

```python
# Standard signature
def run(task_data: dict) -> bool:
    # Return True on success, False to leave in queue for retry

# Alternative (testTask pattern)
def run(data, logger):
    # logger has .log(msg, level) method
```

The worker auto-detects which signature to use.

## Dashboard Tracking

Registers with the agent dashboard as `task-worker`. Tracks:
- `tasks_completed` — total count
- `tasks_failed` — total count
- `recent_tasks` — list of last 20 completed tasks with timing

## Monitoring

```bash
tail -f /tmp/task_worker.log
```

Or check the agent dashboard: http://agent-dashboard-frontend.s3-website-us-east-1.amazonaws.com

## Key Behaviors

- **Git pull before each task** — always runs latest code from the repo
- **Auto-retry** — failed tasks stay in queue and are retried after visibility timeout (5 min)
- **Malformed messages** — invalid JSON is deleted from queue to prevent blocking
- **Graceful shutdown** — Ctrl+C stops polling and marks tracker as completed
