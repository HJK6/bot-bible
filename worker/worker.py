#!/Users/YOUR_USERNAME/task-worker/.venv/bin/python3.13
"""
Task Worker Bot
Polls the BotRequests SQS queue for tasks and dispatches them
to the appropriate repo's tasks/ folder.

Message format: {"repo": "land-bot", "task": "aggregateLandData", "data": {...}}

Usage:
    caffeinate -dims python3.13 worker.py
"""

import boto3
import json
import importlib
import inspect
import signal
import subprocess
import sys
import os
import time
import traceback
from datetime import datetime

CLAUDE_PATH = "/Users/YOUR_USERNAME/.local/bin/claude"

# Memory event logging
sys.path.insert(0, "/Users/YOUR_USERNAME/memory-system")
from memory_system.log import log_event as _log_event
def mem_log(category, summary, **kwargs):
    try: _log_event("task-worker", category, summary, **kwargs)
    except Exception: pass

QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/YOUR_AWS_ACCOUNT_ID/BotRequests"
DLQ_URL = "https://sqs.us-east-1.amazonaws.com/YOUR_AWS_ACCOUNT_ID/BotRequests-DLQ"
AWS_REGION = "us-east-1"

POLL_WAIT_SECONDS = 20  # SQS long polling
IDLE_SLEEP_SECONDS = 5
MAX_RECENT_TASKS = 20  # Keep last N tasks in metrics

class SimpleLogger:
    """Minimal logger matching land-bot's logger.log() interface."""
    def log(self, msg, level="INFO"):
        log(str(msg), level if isinstance(level, str) else "INFO")

_logger = SimpleLogger()

REPO_MAP = {
    "land-bot": "/Users/YOUR_USERNAME/land-bot",
    "memory-system": "/Users/YOUR_USERNAME/memory-system",
    "stocks": "/Users/YOUR_USERNAME/nse",
}

session = boto3.Session(region_name=AWS_REGION)
sqs = session.client("sqs")

# Task history for dashboard metrics
recent_tasks = []


def log(msg, level="INFO"):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)
    if tracker:
        try:
            tracker.log(msg, level=level.lower())
        except Exception:
            pass


def git_pull(repo_path):
    """Pull latest from the repo's current branch."""
    result = subprocess.run(
        ["git", "pull", "--ff-only"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        log(f"git pull warning: {result.stderr.strip()}", "WARNING")
    else:
        output = result.stdout.strip()
        if output and output != "Already up to date.":
            log(f"git pull: {output}")


def spawn_fix_agent(repo_name, task_name, error_trace):
    """Spawn a Claude agent to diagnose and fix a failed task."""
    repo_path = REPO_MAP.get(repo_name)
    if not repo_path:
        log("Cannot spawn fix agent: unknown repo", "WARNING")
        return False

    prompt = (
        f"A task failed in repo '{repo_name}' at {repo_path}. "
        f"Task: {task_name}\n\n"
        f"Error traceback:\n{error_trace}\n\n"
        f"Diagnose the root cause and fix the bug in the relevant source file(s). "
        f"Do NOT modify worker.py. Only fix files within {repo_path}. "
        f"Keep changes minimal — fix the bug, nothing else."
    )

    log(f"Spawning Claude fix agent for {repo_name}/{task_name}...")
    if tracker:
        tracker.update_task(f"Fix agent: {repo_name}/{task_name}")

    try:
        # Start in new process group so we can kill all children (e.g. tracker scripts)
        proc = subprocess.Popen(
            [CLAUDE_PATH, "-p", "--permission-mode", "bypassPermissions", prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=repo_path,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=5)
            log("Fix agent timed out after 180s", "WARNING")
            return False
        finally:
            # Kill entire process group to clean up orphaned children (tracker, etc.)
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

        output = stdout.strip() if stdout else ""
        if output:
            log_output = output if len(output) < 2000 else output[:2000] + "...[truncated]"
            log(f"Fix agent output:\n{log_output}")
        if proc.returncode == 0:
            log("Fix agent completed successfully")
            return True
        else:
            log(f"Fix agent exited with code {proc.returncode}", "WARNING")
            if stderr:
                log(f"Fix agent stderr: {stderr[:500]}", "WARNING")
            return False
    except Exception as e:
        log(f"Fix agent spawn error: {e}", "ERROR")
        return False


def requeue_task(repo_name, task_name, data):
    """Re-queue a task message back to SQS."""
    body = json.dumps({"repo": repo_name, "task": task_name, "data": data})
    sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=body)
    log(f"Re-queued task: {repo_name}/{task_name}")


def execute_task(repo_name, task_name, data):
    """Run a task from a repo's tasks/ folder."""
    repo_path = REPO_MAP.get(repo_name)
    if not repo_path:
        raise ValueError(f"Unknown repo: {repo_name}. Known repos: {list(REPO_MAP.keys())}")

    if not os.path.isdir(repo_path):
        raise FileNotFoundError(f"Repo path does not exist: {repo_path}")

    task_file = os.path.join(repo_path, "tasks", f"{task_name}.py")
    if not os.path.isfile(task_file):
        raise FileNotFoundError(f"Task file not found: {task_file}")

    # Pull latest
    git_pull(repo_path)

    # Add repo to sys.path so imports within the task (modules.*, scrapers.*, etc.) resolve
    if repo_path not in sys.path:
        sys.path.insert(0, repo_path)

    # Clear stale 'tasks' package if it points to a different repo
    if "tasks" in sys.modules:
        cached_tasks = sys.modules["tasks"]
        cached_path = getattr(cached_tasks, "__path__", [None])[0] if hasattr(cached_tasks, "__path__") else None
        expected_path = os.path.join(repo_path, "tasks")
        if cached_path and os.path.normpath(cached_path) != os.path.normpath(expected_path):
            # Remove stale tasks package and all its submodules
            stale_keys = [k for k in sys.modules if k == "tasks" or k.startswith("tasks.")]
            for k in stale_keys:
                del sys.modules[k]

    # Change to repo root so relative paths in tasks work
    original_cwd = os.getcwd()
    os.chdir(repo_path)

    try:
        # Import (or reimport) the task module
        module_name = f"tasks.{task_name}"
        if module_name in sys.modules:
            module = importlib.reload(sys.modules[module_name])
        else:
            module = importlib.import_module(module_name)

        if not hasattr(module, "run"):
            raise AttributeError(f"Task '{module_name}' has no run() function")

        # Check if run() expects a logger parameter (e.g. testTask)
        sig = inspect.signature(module.run)
        params = list(sig.parameters.keys())
        if len(params) >= 2 and "logger" in params:
            return module.run(data, _logger)
        else:
            return module.run(data)
    finally:
        os.chdir(original_cwd)


def poll_queue():
    """Receive one message from the queue."""
    response = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=POLL_WAIT_SECONDS,
        VisibilityTimeout=300,
    )
    messages = response.get("Messages", [])
    return messages[0] if messages else None


def delete_message(receipt_handle):
    sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt_handle)


def get_dlq_count():
    """Check how many messages are in the DLQ."""
    try:
        resp = sqs.get_queue_attributes(
            QueueUrl=DLQ_URL,
            AttributeNames=['ApproximateNumberOfMessages']
        )
        return int(resp['Attributes']['ApproximateNumberOfMessages'])
    except Exception:
        return -1


def update_dashboard(tasks_completed, tasks_failed):
    if not tracker:
        return
    tracker.update_metrics(
        tasks_completed=tasks_completed,
        tasks_failed=tasks_failed,
        recent_tasks=list(recent_tasks),
    )


def run():
    log("Task Worker started, polling BotRequests queue")
    tasks_completed = 0
    tasks_failed = 0

    if tracker:
        tracker.update_task("Idle — waiting for tasks")
        update_dashboard(tasks_completed, tasks_failed)

    while True:
        message = None
        body = {}
        repo = ""
        task = ""
        data = {}
        try:
            message = poll_queue()

            if not message:
                now = time.strftime("%H:%M:%S")
                log("No request found, will try again in 5s")
                if tracker:
                    tracker.update_task(f"Idle — no tasks in queue (checked {now})")
                time.sleep(5)
                continue

            body = json.loads(message["Body"])
            repo = body.get("repo", "")
            task = body.get("task", "")
            data = body.get("data", {})
            receipt_handle = message["ReceiptHandle"]

            if not repo or not task:
                log(f"Skipping malformed message (empty repo or task): {body}", "WARNING")
                delete_message(receipt_handle)
                continue

            task_label = f"{repo}/{task}"
            log(f"Received task: {task_label}")

            if tracker:
                tracker.update_task(f"Running: {task_label}")

            start_time = time.time()
            success = execute_task(repo, task, data)
            elapsed = round(time.time() - start_time, 1)

            if success is not False:
                delete_message(receipt_handle)
                tasks_completed += 1
                log(f"Task completed: {task_label} ({elapsed}s)")
                mem_log("success", f"Task completed: {task_label} ({elapsed}s)", tags=[repo, task])
                recent_tasks.insert(0, f"{task_label} ({elapsed}s)")
                if len(recent_tasks) > MAX_RECENT_TASKS:
                    recent_tasks.pop()
            else:
                tasks_failed += 1
                log(f"Task returned False: {task_label} ({elapsed}s)", "WARNING")
                mem_log("error", f"Task returned False: {task_label} ({elapsed}s)", tags=[repo, task])
                recent_tasks.insert(0, f"FAILED: {task_label}")
                if len(recent_tasks) > MAX_RECENT_TASKS:
                    recent_tasks.pop()

            update_dashboard(tasks_completed, tasks_failed)

        except json.JSONDecodeError as e:
            log(f"Invalid JSON in message body: {e}", "ERROR")
            if message:
                delete_message(message["ReceiptHandle"])
            tasks_failed += 1
            update_dashboard(tasks_completed, tasks_failed)

        except Exception as e:
            error_trace = traceback.format_exc()
            tasks_failed += 1
            log(f"Task error: {e}\n{error_trace}", "ERROR")
            mem_log("error", f"Task error: {repo}/{task} — {e}", tags=[repo, task], details=error_trace[:1000])
            update_dashboard(tasks_completed, tasks_failed)

            # Auto-fix: spawn Claude agent to fix the issue, then re-queue
            auto_fix_marker = body.get("_auto_fix_attempt", 0) if body else 0
            if repo and task and auto_fix_marker < 1:
                mem_log("task", f"Spawning fix agent for {repo}/{task}", tags=[repo, task, "auto-fix"])
                fixed = spawn_fix_agent(repo, task, error_trace)
                if fixed:
                    # Re-queue with retry marker so we don't loop forever
                    retry_data = dict(data) if data else {}
                    retry_body = {"repo": repo, "task": task, "data": retry_data, "_auto_fix_attempt": 1}
                    sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(retry_body))
                    log(f"Re-queued task after fix: {repo}/{task}")
                    # Delete the original — we just sent a fresh copy with the fix applied
                    if message:
                        delete_message(message["ReceiptHandle"])
                else:
                    log(f"Auto-fix failed for {repo}/{task} — leaving in queue for DLQ redrive", "WARNING")
                    dlq_count = get_dlq_count()
                    if dlq_count >= 0:
                        log(f"DLQ currently holds {dlq_count} message(s)", "WARNING")
                    # Do NOT delete — let visibility timeout expire so SQS counts the receive.
                    # After maxReceiveCount (3) receives without deletion, SQS moves to DLQ.
            elif auto_fix_marker >= 1:
                log(f"Task already had auto-fix attempt — leaving in queue for DLQ redrive: {repo}/{task}", "WARNING")
                dlq_count = get_dlq_count()
                if dlq_count >= 0:
                    log(f"DLQ currently holds {dlq_count} message(s)", "WARNING")
                # Do NOT delete — let SQS handle redrive to DLQ after maxReceiveCount

            time.sleep(IDLE_SLEEP_SECONDS)


# Dashboard tracker (optional — works without it)
tracker = None
try:
    sys.path.insert(0, "/Users/YOUR_USERNAME/agent-dashboard/tracker")
    from tracker import BotTracker
    tracker = BotTracker("task-worker", "Task Worker", title="Task Worker")
    print("[Tracker] Registered with dashboard")
except Exception as e:
    print(f"[Tracker] Dashboard tracking unavailable: {e}")


def _acquire_pidlock():
    """Ensure only one task-worker instance runs. Exit if another is alive."""
    pidfile = "/tmp/task_worker.pid"
    if os.path.exists(pidfile):
        try:
            old_pid = int(open(pidfile).read().strip())
            os.kill(old_pid, 0)
            print(f"[PID Lock] Task worker already running (PID {old_pid}), exiting.")
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            pass
        except PermissionError:
            print(f"[PID Lock] Process {old_pid} exists but not owned by us, exiting.")
            sys.exit(1)
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))


if __name__ == "__main__":
    _acquire_pidlock()
    try:
        run()
    except KeyboardInterrupt:
        log("Shutting down")
    finally:
        if tracker:
            tracker.complete("completed")
