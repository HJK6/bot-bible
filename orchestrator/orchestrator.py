"""
Agent Orchestrator
Local daemon that manages Claude agents, handles Telegram, and processes dashboard commands.
Features smart message routing to existing agents based on context/topic matching.
Persistent sessions via Claude Code --resume flag with local session storage.

Usage: python3 orchestrator.py
"""

import asyncio
import hashlib
import os
import re
import sys
import json
import random
import signal
import subprocess
import threading
import time
import uuid
import logging
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from collections import defaultdict
from pathlib import Path

# Add parent dir so we can import tracker
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tracker.tracker import BotTracker
from sms.handler import SmsHandler
from bot.handler import BotHandler

import boto3
from boto3.dynamodb.conditions import Attr, Key
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Config ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OWNER_CHAT_ID = int(os.environ.get("OWNER_CHAT_ID", "5697607361"))

AWS_REGION = "us-east-1"

AGENT_COMMANDS_TABLE = "AgentCommands"
AGENT_TRACKER_TABLE = "AgentTracker"
AGENT_LOGS_TABLE = "AgentLogs"
AGENT_CHAT_TABLE = "AgentChat"
PUSH_TOKENS_TABLE = "PushTokens"

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

COMMAND_POLL_INTERVAL = 5  # seconds
CLAUDE_WORKING_DIR = "/Users/YOUR_USERNAME"
CLAUDE_CMD = ["claude", "-p", "--dangerously-skip-permissions", "--output-format", "stream-json", "--verbose"]

# AI routing via Claude Code CLI (Max subscription)
CLAUDE_ROUTE_CMD = ["claude", "-p", "--model", "claude-haiku-4-5-20251001", "--output-format", "text"]
CLAUDE_ROUTE_TIMEOUT = 15  # seconds
# Clean env to avoid nested session detection
_CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

# tmux-based agent sessions
TMUX = "/opt/homebrew/bin/tmux"
AGENT_LOG_DIR = "/tmp/agent-logs"
os.makedirs(AGENT_LOG_DIR, exist_ok=True)
# Regex to strip ANSI escape codes from terminal output
ANSI_RE = re.compile(r'\x1b\[[\?0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[^[\]].?|\r')

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "orchestrator.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("orchestrator")

# --- AWS Session ---
session = boto3.Session(region_name=AWS_REGION)
dynamo = session.resource("dynamodb")
commands_table = dynamo.Table(AGENT_COMMANDS_TABLE)
tracker_table = dynamo.Table(AGENT_TRACKER_TABLE)
logs_table = dynamo.Table(AGENT_LOGS_TABLE)
chat_table = dynamo.Table(AGENT_CHAT_TABLE)
push_tokens_table = dynamo.Table(PUSH_TOKENS_TABLE)

ORCHESTRATOR_QUEUE_URL = os.environ.get(
    "ORCHESTRATOR_QUEUE_URL",
    f"https://sqs.{AWS_REGION}.amazonaws.com/841672795586/OrchestratorInbox"
)
sqs_client = session.client("sqs")


def _convert_floats(item):
    """Convert float values to Decimal for DynamoDB."""
    if isinstance(item, dict):
        return {k: _convert_floats(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [_convert_floats(i) for i in item]
    elif isinstance(item, float):
        return Decimal(str(item))
    else:
        return item


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _now_ms():
    return int(time.time() * 1000)


def _ttl_seconds(days):
    return int(time.time()) + (days * 86400)


def _extract_keywords(text):
    """Extract meaningful keywords from text for topic matching."""
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "it", "its", "this", "that",
        "these", "those", "i", "me", "my", "we", "our", "you", "your", "he",
        "she", "they", "them", "his", "her", "their", "what", "which", "who",
        "whom", "where", "when", "how", "why", "if", "then", "else", "but",
        "and", "or", "not", "no", "yes", "so", "to", "of", "in", "on", "at",
        "by", "for", "with", "from", "up", "out", "off", "about", "into",
        "over", "after", "before", "just", "now", "also", "very", "too",
        "here", "there", "all", "any", "some", "each", "much", "many", "more",
        "most", "other", "than", "ok", "okay", "sure", "thanks", "please",
        "hey", "hi", "hello", "yeah", "yep", "nope", "right", "got", "get",
        "make", "let", "go", "see", "look", "take", "come", "give", "tell",
        "keep", "put", "run", "set", "try", "ask", "need", "use", "want",
        "know", "think", "like", "still", "already", "yet",
    }
    words = re.findall(r'[a-zA-Z0-9_./\-]+', text.lower())
    return set(w for w in words if len(w) > 2 and w not in stop_words)


class ManagedAgent:
    """A Claude agent conversation thread managed by the orchestrator."""

    def __init__(self, agent_id: str, goal: str, title: str, tracker=None):
        self.agent_id = agent_id
        self.goal = goal
        self.title = title
        self.tracker = tracker
        self.process = None  # Current subprocess, if running
        self.conversation_history = []  # List of {"role": "user"/"agent", "content": str, "timestamp": str}
        self.last_agent_message = ""
        self.agent_summary = ""
        self._output_buffer = ""
        self._running_task = None  # asyncio.Task for the current subprocess reader
        self.session_id = None  # Claude Code session UUID for --resume
        self.current_task = ""
        self.is_idle = False  # True when session exists but no process running
        self.source = "telegram"  # Origin: "telegram", "sms", or "bot"
        self.source_bot_id = None  # For bot-sourced agents: the bot_id to reply to
        self.tmux_session = None  # tmux session name for interactive visibility
        self._log_file = None  # pipe-pane log file path
        self._log_pos_before_prompt = 0  # log file position before sending a prompt

    def _update_dynamo(self, expression, values, names=None):
        """Update this agent's AgentTracker entry."""
        try:
            kwargs = {
                "Key": {"agent_id": self.agent_id},
                "UpdateExpression": expression,
                "ExpressionAttributeValues": values,
            }
            if names:
                kwargs["ExpressionAttributeNames"] = names
            tracker_table.update_item(**kwargs)
        except Exception:
            pass

    @property
    def last_user_messages(self):
        """Get last 3 user messages."""
        user_msgs = [m["content"] for m in self.conversation_history if m["role"] == "user"]
        return user_msgs[-3:]

    @property
    def is_busy(self):
        """True if a Claude process is currently running for this agent."""
        if self.tmux_session:
            return not self.is_idle and self._running_task and not self._running_task.done()
        return self.process is not None and self.process.poll() is None

    @property
    def state(self):
        """Return agent state: 'busy', 'idle', or 'stopped'."""
        if self.tmux_session:
            return "idle" if self.is_idle else "busy"
        if self.process is not None and self.process.poll() is None:
            return "busy"
        if self.session_id:
            return "idle"
        return "stopped"


class MessageQueue:
    """Queue outgoing Telegram messages with agent-aware batching.

    Rules:
    - Messages from the SAME agent can be sent without waiting for reply.
    - When switching to a DIFFERENT agent's messages, wait for user reply first
      (unless timed out).
    - Each message is tagged with [agent_title].
    - Tracks which agent sent the last message for reply routing.
    """

    def __init__(self):
        self._queue = asyncio.Queue()
        self._last_sending_agent = None  # agent_id of last message sent
        self._waiting_for_reply = False
        self._reply_event = asyncio.Event()
        self._reply_text = None
        self._lock = asyncio.Lock()

    async def enqueue(self, agent_id: str, agent_title: str, message: str):
        """Add a message to the outgoing queue."""
        await self._queue.put((agent_id, agent_title, message))

    async def process_queue(self, send_fn):
        """Main loop: process queued messages respecting agent-switching rules."""
        while True:
            agent_id, agent_title, message = await self._queue.get()

            # If switching agents and we sent a message before, wait for reply
            if (self._last_sending_agent is not None
                    and self._last_sending_agent != agent_id
                    and self._waiting_for_reply):
                try:
                    await asyncio.wait_for(self._reply_event.wait(), timeout=120)
                except asyncio.TimeoutError:
                    logger.debug("Timeout waiting for reply before agent switch, proceeding")
                self._reply_event.clear()
                self._waiting_for_reply = False

            tagged = f"[{agent_title}]\n{message}"
            await send_fn(tagged)

            self._last_sending_agent = agent_id
            self._waiting_for_reply = True
            self._reply_event.clear()

            self._queue.task_done()

    def get_last_sending_agent(self):
        """Return the agent_id that sent the most recent message."""
        return self._last_sending_agent

    def notify_reply(self, reply_text: str):
        """Called when user sends a reply. Unblocks any pending agent switch wait."""
        self._reply_text = reply_text
        self._waiting_for_reply = False
        self._reply_event.set()


class Orchestrator:
    def __init__(self):
        self.managed_agents = {}  # agent_id -> ManagedAgent
        self.message_queue = MessageQueue()
        self.self_tracker = None  # tracker for the orchestrator itself
        self._running = True
        self._app = None  # telegram app
        self._total_agents_started = 0
        self.sms_handler = None  # initialized in start() after send_update is available
        self.bot_handler = None  # initialized in start() after send_update is available

    # ========================
    # Lifecycle
    # ========================

    async def start(self):
        """Start the orchestrator."""
        logger.info("Starting orchestrator...")

        # Register self as a bot (uses BotTracker table, not AgentTracker)
        self.self_tracker = BotTracker("telegram-bot", "Orchestrator")
        self.self_tracker.update_task("Running - managing agents")

        # Clean up any leftover session files from previous recovery system
        sessions_dir = os.path.expanduser("~/.claude/orchestrator/sessions")
        if os.path.exists(sessions_dir):
            import shutil
            shutil.rmtree(sessions_dir, ignore_errors=True)

        # Load telegram bot token from env file
        env_path = "/Users/YOUR_USERNAME/telegram-claude-bot/.env"
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        os.environ[key.strip()] = val.strip()

        token = os.environ.get("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
        if not token:
            logger.error("No TELEGRAM_BOT_TOKEN found")
            return

        # Setup Telegram bot (for sending only — messages arrive via SQS)
        self._app = Application.builder().token(token).build()

        # Initialize SMS handler
        try:
            self.sms_handler = SmsHandler(notify_fn=self.send_update)
            logger.info("SMS handler initialized")
        except Exception as e:
            logger.error(f"Failed to initialize SMS handler: {e}")

        # Initialize Bot-to-Bot handler
        try:
            self.bot_handler = BotHandler(notify_fn=self.send_update)
            logger.info("Bot handler initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Bot handler: {e}")

        # Start background tasks
        asyncio.create_task(self._poll_commands())
        asyncio.create_task(self._monitor_agents())
        asyncio.create_task(self.message_queue.process_queue(self._send_telegram))

        # Initialize Telegram bot for sending (no polling — messages come via SQS)
        await self._app.initialize()
        await self._app.start()
        # NOTE: Not starting updater.start_polling() — messages arrive via SQS webhook

        # Start SQS polling for incoming messages
        asyncio.create_task(self._poll_sqs())

        # Clean up stale Ghost OS MCP processes from previous runs
        import subprocess as _sp
        try:
            _sp.run(["pkill", "-f", "ghost mcp"], capture_output=True, timeout=5)
        except Exception:
            pass

        logger.info("Orchestrator started. Waiting for commands...")
        self.self_tracker.log("Orchestrator started")

        recovered = len(self.managed_agents)
        if recovered:
            logger.info(f"Recovered {recovered} agent session(s) from previous run")
            self.self_tracker.log(f"Recovered {recovered} agent session(s)")

        # Send startup update to mobile app
        startup_msg = "Orchestrator started"
        if recovered:
            startup_msg += f" ({recovered} agent session(s) recovered)"
        await self.send_update(startup_msg)

        # Keep running
        try:
            while self._running:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Clean shutdown — save sessions, kill running processes, but preserve idle agents."""
        logger.info("Shutting down orchestrator...")
        self._running = False

        # Save all sessions and kill running processes (but don't delete session files)
        for agent_id, agent in list(self.managed_agents.items()):
            # Kill running process if any
            if agent.process and agent.process.poll() is None:
                agent.process.terminate()
                try:
                    agent.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    agent.process.kill()
                agent.process = None

            agent._update_dynamo("SET #s = :s", {":s": "idle"}, {"#s": "status"})

        self.managed_agents.clear()

        # Stop telegram
        if self._app:
            try:
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down telegram: {e}")

        # Deregister self
        if self.self_tracker:
            self.self_tracker.complete("completed")

        logger.info("Orchestrator shut down")

    async def _send_telegram(self, message: str):
        """Send a message to the owner on Telegram. DISABLED — app chat is primary channel."""
        logger.debug(f"Telegram send skipped (disabled): {message[:80]}")

    async def _send_direct(self, message: str):
        """Send a message directly without going through the queue."""
        await self._send_telegram(message)

    async def _send_push_notification(self, agent_title: str, message: str, agent_id: str = ""):
        """Send push notification via Expo Push API to all registered devices."""
        try:
            response = push_tokens_table.scan(
                FilterExpression=Attr("active").eq(True)
            )
            tokens = response.get("Items", [])
            if not tokens:
                return

            body = message[:200] + "..." if len(message) > 200 else message

            messages = []
            for token_record in tokens:
                push_token = token_record.get("push_token", "")
                if not push_token:
                    continue
                messages.append({
                    "to": push_token,
                    "title": f"[{agent_title}]",
                    "body": body,
                    "sound": "default",
                    "data": {
                        "agent_id": agent_id,
                        "agent_title": agent_title,
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
                logger.debug(f"Push notification sent: {result}")

        except Exception as e:
            logger.error(f"Failed to send push notification: {e}")

    # ========================
    # Session Persistence
    # ========================

    def _persist_session_id(self, agent: ManagedAgent):
        """Save session_id to DynamoDB."""
        try:
            tracker_table.update_item(
                Key={"agent_id": agent.agent_id},
                UpdateExpression="SET session_id = :sid",
                ExpressionAttributeValues={":sid": agent.session_id},
            )
        except Exception as e:
            logger.error(f"Failed to persist session_id for {agent.agent_id[:8]}: {e}")

    # ========================
    # Telegram Command Handlers
    # ========================

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Agent Orchestrator running.\n\n"
            "Send me a task to start a new Claude agent.\n"
            "Messages are auto-routed to the right agent.\n\n"
            "/status - see running agents\n"
            "/agents - list all agents with IDs\n"
            "/reset - stop all agents"
        )

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        agents = [m for m in self.managed_agents.values()]
        if not agents:
            await update.message.reply_text("No agents currently active.")
            return

        lines = ["Active agents:"]
        for m in agents:
            state = m.state
            task = m.current_task or "idle"
            lines.append(f"  [{m.title}] ({state})")
            lines.append(f"    Task: {task}")
            lines.append(f"    Goal: {m.goal[:80]}{'...' if len(m.goal) > 80 else ''}")
            lines.append(f"    Messages: {len(m.conversation_history)}")
            if m.session_id:
                lines.append(f"    Session: {m.session_id[:8]}...")
        await update.message.reply_text("\n".join(lines))

    async def _cmd_agents(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        agents = list(self.managed_agents.values())
        if not agents:
            await update.message.reply_text("No agents active.")
            return

        lines = ["Agents (use ID prefix to direct messages):"]
        for m in agents:
            lines.append(f"  {m.agent_id[:8]} [{m.title}] - {m.state}")
        await update.message.reply_text("\n".join(lines))

    async def _cmd_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        count = len(self.managed_agents)
        for agent_id in list(self.managed_agents.keys()):
            await self._stop_agent(agent_id)
        await update.message.reply_text(f"Stopped {count} agent(s). All cleared.")

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages with smart routing."""
        if not update.message or not update.message.text:
            return
        if update.message.chat_id != OWNER_CHAT_ID:
            return

        text = update.message.text.strip()
        if not text:
            return

        # Notify the message queue that a reply has been received
        self.message_queue.notify_reply(text)

        # Route the message
        target_agent_id = await self._route_message(text)

        if target_agent_id:
            agent = self.managed_agents.get(target_agent_id)
            if agent:
                logger.info(f"Routing message to agent [{agent.title}] ({agent.agent_id[:8]})")
                await update.message.reply_text(f"-> [{agent.title}]")
                await self._send_to_agent(target_agent_id, text)
            else:
                # Agent was in DynamoDB but not locally managed; start fresh
                logger.info(f"Agent {target_agent_id[:8]} not locally managed, starting new")
                await self._start_new_agent_with_message(text, update)
        else:
            await self._start_new_agent_with_message(text, update)

    async def _start_new_agent_with_message(self, text: str, update: Update):
        """Start a new agent from a user message."""
        agent_id = await self._start_agent(text)
        if agent_id:
            agent = self.managed_agents.get(agent_id)
            title = agent.title if agent else agent_id[:8]
            await update.message.reply_text(f"New agent [{title}] started.")
        else:
            await update.message.reply_text("Failed to start agent.")

    # ========================
    # SQS Inbox Polling
    # ========================

    async def _poll_sqs(self):
        """Poll the OrchestratorInbox SQS queue for incoming messages."""
        while self._running:
            try:
                response = await asyncio.to_thread(
                    sqs_client.receive_message,
                    QueueUrl=ORCHESTRATOR_QUEUE_URL,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=5,
                    MessageAttributeNames=["All"],
                )
                messages = response.get("Messages", [])
                for msg in messages:
                    body = json.loads(msg["Body"])
                    source = body.get("source", "unknown")
                    text = body.get("text", "")

                    if source == "telegram" and text:
                        await self._handle_sqs_message(text)
                    elif source == "sms" and text:
                        from_number = body.get("from", "unknown")
                        to_number = body.get("to", "")
                        message_sid = body.get("message_sid", "")
                        logger.info(f"SMS from {from_number}: {text[:80]}")
                        if self.sms_handler:
                            try:
                                await self.sms_handler.handle_incoming(
                                    from_phone=from_number,
                                    body=text,
                                    message_sid=message_sid,
                                    to_phone=to_number,
                                )
                            except Exception as e:
                                logger.error(f"SMS handler error: {e}")
                                await self.send_update(f"SMS from {from_number}: {text}", sender="SMS")
                        else:
                            await self.send_update(f"SMS from {from_number}: {text}", sender="SMS")
                    elif source == "bot":
                        bot_id = body.get("bot_id", "unknown")
                        message_type = body.get("message_type", "chat")
                        bot_message = body.get("message", "")
                        logger.info(f"Bot message from {bot_id}: [{message_type}] {bot_message[:80]}")
                        if self.bot_handler:
                            try:
                                await self.bot_handler.handle_incoming(
                                    bot_id=bot_id,
                                    message_type=message_type,
                                    message=bot_message,
                                    reply_to=body.get("reply_to", ""),
                                    attachments=body.get("attachments", []),
                                    message_id=body.get("message_id", ""),
                                )
                            except Exception as e:
                                logger.error(f"Bot handler error: {e}")
                                await self.send_update(f"Bot [{bot_id}]: {bot_message[:200]}", sender="BotComm")
                        else:
                            await self.send_update(f"Bot [{bot_id}]: {bot_message[:200]}", sender="BotComm")
                        # Route bot messages to agent — agent decides whether to reply
                        if bot_message and message_type in ("chat", "data_request", "data_response", "capability_response"):
                            agent_text = f"[BotComm from {bot_id}] ({message_type}): {bot_message}"
                            await self._handle_bot_agent_message(bot_id, agent_text)
                    elif source == "gmail":
                        history_id = body.get("history_id", 0)
                        email_addr = body.get("email", "unknown")
                        if email_addr != "YOUR_EMAIL":
                            logger.debug(f"Ignoring Gmail notification for {email_addr}")
                        else:
                            logger.info(f"Gmail notification: {email_addr} historyId={history_id}")
                            await self._handle_gmail_notification(email_addr, history_id)

                    # Delete message from queue
                    await asyncio.to_thread(
                        sqs_client.delete_message,
                        QueueUrl=ORCHESTRATOR_QUEUE_URL,
                        ReceiptHandle=msg["ReceiptHandle"],
                    )
            except Exception as e:
                logger.error(f"SQS poll error: {e}")
                await asyncio.sleep(5)

    async def _handle_bot_agent_message(self, bot_id: str, text: str):
        """Handle a bot message inline with a lightweight claude -p call.
        No agent/chat/tmux session is created — just generates a reply and sends it.
        """
        # Build context from bot handler's session data
        context_lines = [text, "", "---", f"You are YOUR_BOT_NAME. Reply to this BotComm message from bot '{bot_id}'."]

        if self.bot_handler:
            try:
                bot = self.bot_handler.storage.get_bot(bot_id)
                if bot:
                    context_lines.append(f"Bot name: {bot.name}, capabilities: {bot.capabilities}")
                    session = self.bot_handler.storage.get_latest_session(bot_id)
                    if session:
                        recent = self.bot_handler.storage.get_recent_messages(session.session_id, limit=5)
                        if recent:
                            context_lines.append("\nRecent conversation:")
                            for msg in recent:
                                who = bot.name if msg.direction == "inbound" else "YOUR_BOT_NAME"
                                context_lines.append(f"  {who}: {msg.body[:300]}")
                        if getattr(session, "summary", ""):
                            context_lines.append(f"\nSession summary: {session.summary}")
            except Exception as e:
                logger.warning(f"Failed to build bot context: {e}")

        context_lines.append("\nFirst, decide if this message needs a reply. Do NOT reply if:")
        context_lines.append("- The message is just an acknowledgment (ok, got it, thanks, sounds good, bye, etc.)")
        context_lines.append("- The message is confirming receipt of something you sent")
        context_lines.append("- The message is a farewell/sign-off")
        context_lines.append("- The message contains credentials/keys being delivered (just store them)")
        context_lines.append("- Replying would just create a back-and-forth loop with no substance")
        context_lines.append("\nDO reply if:")
        context_lines.append("- The bot is asking a question")
        context_lines.append("- The bot is requesting action or data")
        context_lines.append("- The bot is introducing itself for the first time")
        context_lines.append("- The message contains important information that needs acknowledgment")
        context_lines.append("\nIf no reply is needed, output exactly: [NO_REPLY]")
        context_lines.append("If a reply is needed, just write your response directly.")
        context_lines.append("Keep replies concise.")

        full_prompt = "\n".join(context_lines)
        logger.info(f"Generating inline bot reply for {bot_id}")

        try:
            clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            result = await asyncio.to_thread(
                lambda: subprocess.run(
                    ["claude", "-p", full_prompt, "--model", "claude-haiku-4-5-20251001", "--output-format", "text"],
                    capture_output=True, text=True, timeout=30, env=clean_env,
                )
            )
            if result.returncode != 0:
                logger.error(f"Bot reply generation failed (rc={result.returncode}): {result.stderr[:200]}")
                return

            reply = result.stdout.strip()
            if not reply:
                logger.info(f"Empty reply for bot {bot_id}, skipping")
                return

            if "[NO_REPLY]" in reply:
                logger.info(f"Bot reply: no reply needed for {bot_id}")
                return

            # Send the reply
            if self.bot_handler:
                sent = await self.bot_handler.send_message(bot_id, reply[:4000], message_type="chat")
                if sent:
                    logger.info(f"Bot reply sent to {bot_id}: {reply[:80]}")
                    await self.send_update(f"Replied to bot [{bot_id}]: {reply[:200]}", sender="BotComm")
                else:
                    logger.error(f"Failed to send bot reply to {bot_id}")
        except subprocess.TimeoutExpired:
            logger.error(f"Bot reply generation timed out for {bot_id}")
        except Exception as e:
            logger.error(f"Bot reply generation error for {bot_id}: {e}")

    _gmail_last_history_id: int = 0  # Track last processed historyId
    _gmail_notified_ids: set = set()  # Track message IDs we've already notified about

    async def _handle_gmail_notification(self, email_address: str, history_id: int):
        """Fetch new email details via history API and send a push notification."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            token_path = os.path.expanduser("~/.config/google/gmail_token.json")
            creds = Credentials.from_authorized_user_file(
                token_path, ["https://www.googleapis.com/auth/gmail.modify"]
            )
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, "w") as f:
                    f.write(creds.to_json())

            service = build("gmail", "v1", credentials=creds)

            # Use history API if we have a previous historyId, otherwise just get latest
            new_msg_ids = []
            if self._gmail_last_history_id:
                try:
                    history = await asyncio.to_thread(
                        lambda: service.users().history().list(
                            userId="me",
                            startHistoryId=self._gmail_last_history_id,
                            historyTypes=["messageAdded"],
                            labelId="INBOX",
                        ).execute()
                    )
                    for record in history.get("history", []):
                        for added in record.get("messagesAdded", []):
                            msg_id = added["message"]["id"]
                            labels = added["message"].get("labelIds", [])
                            if "INBOX" in labels and msg_id not in self._gmail_notified_ids:
                                new_msg_ids.append(msg_id)
                except Exception:
                    # historyId too old or invalid — fall back to listing
                    pass

            # Fallback: if no history results, check latest unread
            if not new_msg_ids and not self._gmail_last_history_id:
                results = await asyncio.to_thread(
                    lambda: service.users().messages().list(
                        userId="me", labelIds=["INBOX", "UNREAD"], maxResults=1
                    ).execute()
                )
                for m in results.get("messages", []):
                    if m["id"] not in self._gmail_notified_ids:
                        new_msg_ids.append(m["id"])

            self._gmail_last_history_id = history_id

            if not new_msg_ids:
                logger.debug(f"Gmail: no new inbox messages (historyId={history_id})")
                return

            # Fetch details and notify for each new message
            for msg_id in new_msg_ids:
                msg = await asyncio.to_thread(
                    lambda mid=msg_id: service.users().messages().get(
                        userId="me", id=mid, format="metadata",
                        metadataHeaders=["From", "Subject"],
                    ).execute()
                )

                headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
                sender = headers.get("from", "Unknown")
                subject = headers.get("subject", "(no subject)")

                # Clean sender: "Name <email>" → "Name"
                if "<" in sender:
                    sender = sender.split("<")[0].strip().strip('"')

                notification = f"New email from {sender}: {subject}"
                logger.info(f"Gmail: {notification}")
                await self.send_update(notification, sender="Gmail")
                self._gmail_notified_ids.add(msg_id)

            # Keep the set from growing unbounded
            if len(self._gmail_notified_ids) > 100:
                self._gmail_notified_ids = set(list(self._gmail_notified_ids)[-50:])

        except Exception as e:
            logger.error(f"Gmail notification handler error: {e}")
            await self.send_update("New email received", sender="Gmail")

    async def _handle_sqs_message(self, text: str, source: str = "telegram", source_bot_id: str = None):
        """Process an incoming message from SQS (originally from Telegram or other sources)."""
        text = text.strip()
        if not text:
            return

        # Notify the message queue that a reply has been received
        self.message_queue.notify_reply(text)

        # Handle commands
        if text.startswith("/"):
            await self._handle_sqs_command(text)
            return

        # Route the message (same logic as _handle_message)
        target_agent_id = await self._route_message(text)

        def _tag_agent(agent):
            """Tag agent with source info for reply routing."""
            if source != "telegram":
                agent.source = source
                agent.source_bot_id = source_bot_id

        if target_agent_id:
            agent = self.managed_agents.get(target_agent_id)
            if agent:
                logger.info(f"Routing message to agent [{agent.title}] ({agent.agent_id[:8]})")
                _tag_agent(agent)
                await self._send_direct(f"-> [{agent.title}]")
                await self._send_to_agent(target_agent_id, text)
            else:
                logger.info(f"Agent {target_agent_id[:8]} not locally managed, starting new")
                agent_id = await self._start_agent(text)
                if agent_id:
                    agent = self.managed_agents.get(agent_id)
                    if agent:
                        _tag_agent(agent)
                    title = agent.title if agent else agent_id[:8]
                    await self._send_direct(f"New agent [{title}] started.")
        else:
            agent_id = await self._start_agent(text)
            if agent_id:
                agent = self.managed_agents.get(agent_id)
                if agent:
                    _tag_agent(agent)
                title = agent.title if agent else agent_id[:8]
                await self._send_direct(f"New agent [{title}] started.")
            else:
                await self._send_direct("Failed to start agent.")

    async def _handle_sqs_command(self, text: str):
        """Handle slash commands received via SQS."""
        cmd = text.split()[0].lower()

        if cmd == "/start":
            await self._send_direct(
                "Agent Orchestrator running.\n\n"
                "Send me a task to start a new Claude agent.\n"
                "Messages are auto-routed to the right agent.\n\n"
                "/status - see running agents\n"
                "/agents - list all agents with IDs\n"
                "/reset - stop all agents"
            )
        elif cmd == "/status":
            agents = list(self.managed_agents.values())
            if not agents:
                await self._send_direct("No agents currently active.")
                return
            lines = ["Active agents:"]
            for m in agents:
                state = m.state
                task = m.current_task or "idle"
                lines.append(f"  [{m.title}] ({state})")
                lines.append(f"    Task: {task}")
                lines.append(f"    Goal: {m.goal[:80]}{'...' if len(m.goal) > 80 else ''}")
                lines.append(f"    Messages: {len(m.conversation_history)}")
                if m.session_id:
                    lines.append(f"    Session: {m.session_id[:8]}...")
            await self._send_direct("\n".join(lines))
        elif cmd == "/agents":
            agents = list(self.managed_agents.values())
            if not agents:
                await self._send_direct("No agents active.")
                return
            lines = ["Agents (use ID prefix to direct messages):"]
            for m in agents:
                lines.append(f"  {m.agent_id[:8]} [{m.title}] - {m.state}")
            await self._send_direct("\n".join(lines))
        elif cmd == "/reset":
            count = len(self.managed_agents)
            for agent_id in list(self.managed_agents.keys()):
                await self._stop_agent(agent_id)
            await self._send_direct(f"Stopped {count} agent(s). All cleared.")

    # ========================
    # Smart Message Routing
    # ========================

    async def _route_message(self, text: str) -> str:
        """Determine which agent (if any) a message should be routed to.

        Returns agent_id to route to, or None to spawn a new agent.
        """
        text_lower = text.lower().strip()

        # Check for explicit "new agent" requests
        new_agent_patterns = [
            "start a new", "new agent", "new task", "create agent",
            "spawn agent", "start agent", "begin a new", "fresh agent",
        ]
        for pat in new_agent_patterns:
            if text_lower.startswith(pat):
                return None

        running_agents = [
            a for a in self.managed_agents.values()
        ]

        if not running_agents:
            return None

        # 1. Check if message starts with an agent ID prefix (e.g. "a1b2c3d4 do this")
        for agent in running_agents:
            prefix = agent.agent_id[:8]
            if text_lower.startswith(prefix):
                return agent.agent_id

        # 2. Check if message starts with agent title in brackets (e.g. "[My Agent] do this")
        bracket_match = re.match(r'^\[([^\]]+)\]', text)
        if bracket_match:
            target_title = bracket_match.group(1).lower()
            for agent in running_agents:
                if agent.title.lower() == target_title or target_title in agent.title.lower():
                    return agent.agent_id

        # 3. Check if message mentions agent title directly
        for agent in running_agents:
            title_lower = agent.title.lower()
            # Only match if the title is reasonably specific (> 5 chars)
            if len(title_lower) > 5 and title_lower in text_lower:
                return agent.agent_id

        # 4. If only one agent is active, check follow-up heuristic first
        if len(running_agents) == 1:
            agent = running_agents[0]
            if self._looks_like_followup(text, agent):
                return agent.agent_id

        # 5. AI routing via Claude Haiku (works for both single and multiple agents)
        ai_result = await self._ai_route_message(text, running_agents)
        if ai_result == "new":
            return None
        if ai_result and ai_result in self.managed_agents:
            return ai_result

        # 6. Fallback: keyword scoring
        best_agent_id = None
        best_score = 0

        msg_keywords = _extract_keywords(text)
        if not msg_keywords:
            last_sender = self.message_queue.get_last_sending_agent()
            if last_sender and last_sender in self.managed_agents:
                return last_sender
            return None

        for agent in running_agents:
            score = self._compute_relevance_score(text, msg_keywords, agent)
            if score > best_score:
                best_score = score
                best_agent_id = agent.agent_id

        if best_score >= 2:
            return best_agent_id

        return None

    async def _ai_route_message(self, text: str, agents: list) -> str:
        """Use Claude Haiku to determine which agent a message should be routed to.
        Returns agent_id, 'new', or None (on failure).
        """
        if not agents:
            return None

        agent_descriptions = []
        for i, agent in enumerate(agents):
            desc = f"Agent {i+1}: [{agent.title}]"
            desc += f"\n  Goal: {agent.goal[:150]}"
            if agent.agent_summary:
                desc += f"\n  Status: {agent.agent_summary[:100]}"
            recent_user = agent.last_user_messages[-1] if agent.last_user_messages else ""
            if recent_user:
                desc += f"\n  Last user message: {recent_user[:100]}"
            desc += f"\n  State: {agent.state}"
            agent_descriptions.append(desc)

        prompt = f"""You are a message router. Given a user message and a list of active agents, decide which agent the message should go to.

Active agents:
{chr(10).join(agent_descriptions)}

User message: "{text}"

Reply with ONLY the agent number (e.g. "1", "2") or "new" if this message is a brand new task that none of the existing agents are working on. Do not explain."""

        try:
            loop = asyncio.get_event_loop()

            def _call_claude():
                try:
                    result = subprocess.run(
                        CLAUDE_ROUTE_CMD + [prompt],
                        capture_output=True, text=True,
                        timeout=CLAUDE_ROUTE_TIMEOUT, env=_CLEAN_ENV,
                    )
                    if result.returncode == 0:
                        return result.stdout.strip()
                    logger.warning(f"Claude routing failed (rc={result.returncode}): {result.stderr[:200]}")
                    return None
                except subprocess.TimeoutExpired:
                    logger.warning("Claude routing timed out")
                    return None
                except Exception as e:
                    logger.warning(f"Claude routing failed: {e}")
                    return None

            response_text = await loop.run_in_executor(None, _call_claude)

            if not response_text:
                return None

            response_clean = response_text.strip().lower()

            if "new" in response_clean:
                logger.info(f"AI router: new agent for message: {text[:50]}")
                return "new"

            numbers = re.findall(r'\d+', response_clean)
            if numbers:
                idx = int(numbers[0]) - 1  # 1-indexed to 0-indexed
                if 0 <= idx < len(agents):
                    chosen = agents[idx]
                    logger.info(f"AI router chose [{chosen.title}] for: {text[:50]}")
                    return chosen.agent_id

            logger.warning(f"AI router unparseable: {response_text}")
            return None

        except Exception as e:
            logger.error(f"AI routing error: {e}")
            return None

    def _looks_like_followup(self, text: str, agent: ManagedAgent) -> bool:
        """Heuristic: does this message look like a follow-up to an existing agent?"""
        text_lower = text.lower()

        quick_replies = [
            "yes", "no", "ok", "okay", "sure", "do it", "go ahead", "proceed",
            "continue", "stop", "cancel", "abort", "looks good", "perfect",
            "thanks", "thank you", "great", "nice", "cool", "done", "next",
            "try again", "retry", "redo", "why", "how", "what happened",
            "show me", "explain", "more details", "elaborate",
        ]
        for reply in quick_replies:
            if text_lower == reply or text_lower.startswith(reply + " ") or text_lower.startswith(reply + ","):
                return True

        msg_keywords = _extract_keywords(text)
        agent_keywords = set()
        agent_keywords.update(_extract_keywords(agent.goal))
        agent_keywords.update(_extract_keywords(agent.agent_summary))
        agent_keywords.update(_extract_keywords(agent.last_agent_message[:500]))
        for um in agent.last_user_messages:
            agent_keywords.update(_extract_keywords(um))

        if msg_keywords and agent_keywords:
            overlap = msg_keywords & agent_keywords
            if len(overlap) / len(msg_keywords) > 0.3:
                return True

        return False

    def _compute_relevance_score(self, text: str, msg_keywords: set, agent: ManagedAgent) -> int:
        """Compute a relevance score for routing a message to a specific agent."""
        score = 0

        goal_kw = _extract_keywords(agent.goal)
        summary_kw = _extract_keywords(agent.agent_summary)
        last_msg_kw = _extract_keywords(agent.last_agent_message[:500])
        user_msg_kw = set()
        for um in agent.last_user_messages:
            user_msg_kw.update(_extract_keywords(um))

        goal_overlap = msg_keywords & goal_kw
        score += len(goal_overlap) * 3

        summary_overlap = msg_keywords & summary_kw
        score += len(summary_overlap) * 2

        conv_overlap = msg_keywords & (last_msg_kw | user_msg_kw)
        score += len(conv_overlap) * 1

        if self.message_queue.get_last_sending_agent() == agent.agent_id:
            score += 2

        if agent.is_busy:
            score += 1

        return score

    # ========================
    # Agent Conversation Management
    # ========================

    ACK_MESSAGES = [
        "A task of substance. I'll get to work and return with results.",
        "This requires a touch of magic. Working...",
        "Consider it done... shortly.",
        "Understood. Allow me a moment.",
        "On it. I'll surface when there's something to show.",
        "A worthy request. Give me a moment.",
        "Leave it with me.",
        "Working. I'll report back soon.",
        "I hear you. Let me see what I can conjure.",
        "Acknowledged. The wheels are turning.",
    ]

    def _generate_ack(self) -> str:
        """Pick a random djinni-personality acknowledgment message."""
        return random.choice(self.ACK_MESSAGES)

    async def _deliver_to_tmux(self, agent_id: str, message: str, skip_log: bool = False) -> bool:
        """Deliver a message to a tmux Claude session not managed by the orchestrator."""
        try:
            dynamo = boto3.resource("dynamodb", region_name="us-east-1")
            table = dynamo.Table("AgentTracker")
            resp = table.get_item(Key={"agent_id": agent_id})
            agent = resp.get("Item")
            if not agent or not agent.get("tmux_session"):
                return False
            session_name = agent["tmux_session"]
            window_index = agent.get("tmux_index", 0)
            target = f"{session_name}:{window_index}"
            # Retry with backoff — tmux send-keys can timeout if the pane is busy
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    subprocess.run(
                        ["/opt/homebrew/bin/tmux", "send-keys", "-t", target, "-l", message],
                        capture_output=True, text=True, timeout=10,
                    )
                    result = subprocess.run(
                        ["/opt/homebrew/bin/tmux", "send-keys", "-t", target, "Enter"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode == 0:
                        if not skip_log:
                            self._log_chat(agent_id, message, direction="inbound", sender="mobile")
                        logger.info(f"Delivered to tmux {target}: {message[:80]}")
                        return True
                    else:
                        logger.error(f"tmux send-keys failed: {result.stderr}")
                        return False
                except subprocess.TimeoutExpired:
                    if attempt < max_retries - 1:
                        wait = (attempt + 1) * 5  # 5s, 10s
                        logger.warning(f"tmux send-keys timeout (attempt {attempt + 1}/{max_retries}), retrying in {wait}s...")
                        await asyncio.sleep(wait)
                    else:
                        raise
        except Exception as e:
            logger.error(f"tmux delivery error: {e}")
            return False

    async def _rehydrate_agent(self, agent_id: str):
        """Rehydrate an agent from DynamoDB/tmux into managed_agents.

        After an orchestrator restart, managed_agents is empty but tmux sessions
        and DynamoDB entries still exist. This rebuilds the ManagedAgent so that
        _send_to_agent (with response monitoring) can be used instead of the
        fire-and-forget _deliver_to_tmux.
        """
        try:
            resp = tracker_table.get_item(Key={"agent_id": agent_id})
            item = resp.get("Item")
            if not item:
                return

            session_name = item.get("tmux_session")
            if not session_name:
                return

            # Verify the tmux session actually exists
            result = subprocess.run(
                [TMUX, "has-session", "-t", session_name],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                logger.warning(f"Rehydrate {agent_id[:8]}: tmux session {session_name} not found")
                return

            agent = ManagedAgent(
                agent_id=agent_id,
                goal=item.get("goal", ""),
                title=item.get("title", "Agent"),
            )
            agent.tmux_session = session_name
            agent.session_id = item.get("session_id", "")
            agent.agent_summary = item.get("agent_summary", "")
            agent.last_agent_message = item.get("last_agent_message", "")
            agent.is_idle = True  # Assume idle since we don't know current state
            agent.source = item.get("source", "telegram")
            agent.source_bot_id = item.get("source_bot_id")

            # Rebuild minimal conversation history from DynamoDB
            last_msgs = item.get("last_user_messages", [])
            for msg in last_msgs:
                agent.conversation_history.append({
                    "role": "user",
                    "content": msg,
                    "timestamp": _now_iso(),
                })

            # Set up pipe-pane log file
            log_file = os.path.join(AGENT_LOG_DIR, f"{agent_id[:8]}.log")
            # Re-enable pipe-pane in case it was lost
            subprocess.run(
                [TMUX, "pipe-pane", "-t", session_name, "-o", f"cat >> {log_file}"],
                capture_output=True, text=True, timeout=5,
            )
            agent._log_file = log_file

            self.managed_agents[agent_id] = agent
            logger.info(f"Rehydrated agent [{agent.title}] ({agent_id[:8]}) from DynamoDB/tmux")
        except Exception as e:
            logger.error(f"Failed to rehydrate agent {agent_id[:8]}: {e}")

    async def _download_image_for_agent(self, image_url: str) -> str:
        """Download an image from S3 URL to a local temp file for Claude to read."""
        import re as _re
        import uuid as _uuid

        filename = f"user_image_{_uuid.uuid4().hex[:8]}.jpg"
        local_path = f"/tmp/{filename}"
        loop = asyncio.get_event_loop()

        # Parse S3 URL to extract bucket and key
        s3_match = _re.match(r"https://(.+?)\.s3\.(.+?)\.amazonaws\.com/(.+)", image_url)
        if s3_match:
            bucket = s3_match.group(1)
            key = s3_match.group(3)
            def _download_s3():
                import boto3
                s3 = boto3.client("s3", region_name="us-east-1")
                s3.download_file(bucket, key, local_path)
            await loop.run_in_executor(None, _download_s3)
        else:
            # Fallback for non-S3 URLs
            import urllib.request
            await loop.run_in_executor(None, lambda: urllib.request.urlretrieve(image_url, local_path))

        logger.info(f"Downloaded image to {local_path}")
        return local_path

    async def _send_to_agent(self, agent_id: str, user_message: str, skip_log: bool = False):
        """Send a user message to an existing agent."""
        agent = self.managed_agents.get(agent_id)
        if not agent:
            logger.error(f"Agent {agent_id[:8]} not found")
            return

        if agent.is_busy:
            # Queue message - it will be sent once the current process finishes
            agent.conversation_history.append({
                "role": "user",
                "content": user_message,
                "timestamp": _now_iso(),
            })
            self._persist_routing_fields(agent)

            if not skip_log:
                self._log_chat(agent_id, user_message, direction="inbound", sender="user")
            logger.info(f"Agent {agent_id[:8]} is busy, message queued in conversation history")
            await self._send_direct(f"[{agent.title}] Agent is busy processing. Your message has been queued.")
            return

        # Add user message to conversation history
        agent.conversation_history.append({
            "role": "user",
            "content": user_message,
            "timestamp": _now_iso(),
        })
        self._persist_routing_fields(agent)
        if not skip_log:
            self._log_chat(agent_id, user_message, direction="inbound", sender="user")

        # Send immediate ack so user doesn't stare at a loading indicator
        ack = self._generate_ack()
        self._log_chat(agent_id, ack, direction="outbound", sender=agent.title)

        if agent.tmux_session:
            # Send via tmux interactive session
            agent.is_idle = False
            agent.current_task = "Running Claude session"
            try:
                tracker_table.update_item(
                    Key={"agent_id": agent.agent_id},
                    UpdateExpression="SET #s = :s",
                    ExpressionAttributeValues={":s": "running"},
                    ExpressionAttributeNames={"#s": "status"},
                )
            except Exception:
                pass
            agent._running_task = asyncio.create_task(
                self._send_prompt_and_monitor(agent, user_message)
            )
        elif agent.session_id:
            # No tmux session but has session_id — create tmux with --resume
            self._create_agent_tmux(agent, initial_prompt=user_message)
        else:
            # No tmux, no session — create fresh tmux session
            self._create_agent_tmux(agent, initial_prompt=user_message)

    def _build_context_prompt(self, agent: ManagedAgent) -> str:
        """Build a prompt that includes the agent's goal and conversation history.
        Used only for first invocation or when --resume fails.
        """
        parts = []

        parts.append(f"You are working on this task: {agent.goal}")
        parts.append("")

        if agent.agent_summary:
            parts.append(f"Summary of progress so far: {agent.agent_summary}")
            parts.append("")

        recent = agent.conversation_history[-20:]
        if len(recent) > 1:
            parts.append("Conversation history:")
            for msg in recent[:-1]:
                role = "User" if msg["role"] == "user" else "Agent"
                parts.append(f"{role}: {msg['content']}")
            parts.append("")

        latest_msg = agent.conversation_history[-1]["content"] if agent.conversation_history else ""
        parts.append(f"User: {latest_msg}")
        parts.append("")
        parts.append("Continue working on this task. Respond to the user's latest message.")

        return "\n".join(parts)

    # NOTE: _run_claude_for_agent and _read_agent_output_json removed.
    # Agents now run interactively in tmux sessions (see _create_agent_tmux).

    # ========================
    # tmux Agent Session Management
    # ========================

    def _create_agent_tmux(self, agent: ManagedAgent, initial_prompt: str = None, session_name: str = None):
        """Create a tmux session with interactive Claude for an agent."""
        if not session_name:
            session_name = f"agent-{agent.agent_id[:8]}"

        # Check if session already exists
        result = subprocess.run(
            [TMUX, "has-session", "-t", session_name],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            agent.tmux_session = session_name
            log_file = os.path.join(AGENT_LOG_DIR, f"{agent.agent_id[:8]}.log")
            agent._log_file = log_file
            logger.info(f"tmux session {session_name} already exists")
            if initial_prompt:
                agent.is_idle = False
                agent._running_task = asyncio.create_task(
                    self._send_prompt_and_monitor(agent, initial_prompt)
                )
            return

        # Build claude command
        if agent.session_id:
            cmd = f"claude --resume {agent.session_id} --dangerously-skip-permissions"
        else:
            cmd = "claude --dangerously-skip-permissions"

        try:
            # Create tmux session with interactive Claude
            # Set ORCHESTRATOR_MANAGED env var so hooks know not to double-log inbound messages
            managed_cmd = f"ORCHESTRATOR_MANAGED=1 {cmd}"
            subprocess.run(
                [TMUX, "new-session", "-d", "-s", session_name, "-x", "200", "-y", "50", managed_cmd],
                capture_output=True, text=True, timeout=10,
                cwd=CLAUDE_WORKING_DIR,
            )

            # Set window name to human-readable title
            if agent.title:
                subprocess.run(
                    [TMUX, "rename-window", "-t", session_name, agent.title[:40]],
                    capture_output=True, text=True, timeout=5,
                )

            # Set up pipe-pane for output capture
            log_file = os.path.join(AGENT_LOG_DIR, f"{agent.agent_id[:8]}.log")
            subprocess.run(
                [TMUX, "pipe-pane", "-t", session_name, "-o", f"cat >> {log_file}"],
                capture_output=True, text=True, timeout=5,
            )

            agent.tmux_session = session_name
            agent._log_file = log_file
            agent.is_idle = False
            agent.current_task = "Running Claude session"

            # Store in DynamoDB
            try:
                tracker_table.update_item(
                    Key={"agent_id": agent.agent_id},
                    UpdateExpression="SET tmux_session = :ts, #s = :s",
                    ExpressionAttributeValues={":ts": session_name, ":s": "running"},
                    ExpressionAttributeNames={"#s": "status"},
                )
            except Exception:
                pass

            logger.info(f"Created tmux session {session_name} for agent [{agent.title}]")

            # Send initial prompt and start monitoring
            if initial_prompt:
                agent._running_task = asyncio.create_task(
                    self._send_prompt_and_monitor(agent, initial_prompt, is_initial=True)
                )
            else:
                # Just monitor for idle (e.g., --resume recovery)
                agent._running_task = asyncio.create_task(
                    self._monitor_tmux_agent(agent)
                )

        except Exception as e:
            logger.error(f"Failed to create tmux session for {agent.agent_id[:8]}: {e}")

    def _rename_tmux_window(self, agent: ManagedAgent, title: str):
        """Rename the tmux window to show a human-readable title (session name stays immutable)."""
        session = agent.tmux_session
        if not session or not title:
            return
        try:
            result = subprocess.run(
                [TMUX, "rename-window", "-t", session, title[:40]],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                logger.info(f"Renamed tmux window for {session} -> {title[:40]}")
            else:
                logger.warning(f"Failed to rename tmux window: {result.stderr}")
        except Exception as e:
            logger.error(f"Failed to rename tmux window: {e}")

    def _kill_tmux_session(self, agent: ManagedAgent):
        """Kill the tmux session for an agent."""
        session_name = agent.tmux_session
        if not session_name:
            return
        try:
            subprocess.run(
                [TMUX, "kill-session", "-t", session_name],
                capture_output=True, text=True, timeout=5,
            )
            agent.tmux_session = None
            logger.info(f"Killed tmux session {session_name}")
        except Exception as e:
            logger.error(f"Failed to kill tmux session {session_name}: {e}")

    def _tmux_capture_pane(self, session_name: str) -> str:
        """Capture the current visible content of a tmux pane."""
        try:
            result = subprocess.run(
                [TMUX, "capture-pane", "-t", session_name, "-p", "-J", "-S", "-500"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            pass
        return ""

    def _tmux_session_alive(self, session_name: str) -> bool:
        """Check if a tmux session still exists."""
        try:
            result = subprocess.run(
                [TMUX, "has-session", "-t", session_name],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """Strip ANSI escape codes from terminal output."""
        return ANSI_RE.sub('', text)

    def _detect_claude_idle(self, pane_content: str) -> bool:
        """Check if Claude Code is waiting for input (showing the prompt).

        Claude Code may render UI elements below the ❯ prompt (separator lines,
        'bypass permissions' hint, etc.), so we check the last several lines.
        We look for a STANDALONE ❯ (empty prompt, no text after it) to avoid
        false positives from '❯ [Pasted text...]' input lines.
        """
        lines = [l for l in pane_content.strip().split('\n') if l.strip()]
        if not lines:
            return False
        # Check last 5 lines for a standalone prompt (❯ with nothing after it)
        for line in lines[-5:]:
            cleaned = self._strip_ansi(line).strip()
            # Standalone prompt: just ❯ with nothing meaningful after it
            if cleaned == '❯' or cleaned == '>':
                return True
            # ❯ followed only by whitespace
            if cleaned.startswith('❯') and not cleaned[1:].strip():
                return True
        return False

    async def _tmux_send_text(self, session: str, text: str):
        """Send text to a tmux session using load-buffer + paste-buffer for reliability."""
        tmp_path = f"/tmp/tmux-prompt-{session}.txt"
        loop = asyncio.get_event_loop()

        def _send():
            with open(tmp_path, 'w') as f:
                f.write(text)
            subprocess.run(
                [TMUX, "load-buffer", tmp_path],
                capture_output=True, text=True, timeout=5,
            )
            subprocess.run(
                [TMUX, "paste-buffer", "-t", session],
                capture_output=True, text=True, timeout=5,
            )
            # Brief delay to let Claude Code process the pasted text before Enter
            import time
            time.sleep(0.5)
            subprocess.run(
                [TMUX, "send-keys", "-t", session, "Enter"],
                capture_output=True, text=True, timeout=5,
            )
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        await loop.run_in_executor(None, _send)

    def _log_agent_start_failure(self, agent: ManagedAgent):
        """Log a failure message to chat when the agent's tmux session dies on startup."""
        fail_msg = "Agent failed to start — Claude session exited unexpectedly. Please try again."
        self._log_chat(agent.agent_id, fail_msg, direction="outbound", sender="system")
        agent.is_idle = True
        agent.current_task = "Failed to start"
        try:
            tracker_table.update_item(
                Key={"agent_id": agent.agent_id},
                UpdateExpression="SET #s = :s, current_task = :ct",
                ExpressionAttributeValues={":s": "failed", ":ct": "Failed to start"},
                ExpressionAttributeNames={"#s": "status"},
            )
        except Exception:
            pass
        logger.error(f"Agent {agent.agent_id[:8]} failed to start after retry")

    async def _send_prompt_and_monitor(self, agent: ManagedAgent, prompt: str, is_initial: bool = False, _retry: int = 0):
        """Send a prompt to the tmux Claude session and monitor for response."""
        session = agent.tmux_session
        if not session:
            return

        if is_initial:
            # Wait for Claude to initialize — handle trust prompt if it appears
            init_ok = False
            for _ in range(30):
                await asyncio.sleep(1)
                if not self._tmux_session_alive(session):
                    logger.warning(f"tmux session {session} died during init for agent {agent.agent_id[:8]}")
                    break
                pane = self._tmux_capture_pane(session)
                if "Yes, I trust this folder" in pane:
                    # Auto-accept the workspace trust prompt
                    subprocess.run(
                        [TMUX, "send-keys", "-t", session, "Enter"],
                        capture_output=True, text=True, timeout=5,
                    )
                    logger.info(f"Auto-accepted trust prompt for agent {agent.agent_id[:8]}")
                    await asyncio.sleep(2)
                    continue
                if self._detect_claude_idle(pane):
                    init_ok = True
                    break
            else:
                logger.warning(f"Claude init timeout for agent {agent.agent_id[:8]}, sending prompt anyway")
                init_ok = True  # timeout but session alive — try sending anyway

            # If session died during init, retry once by recreating tmux session
            if not init_ok and not self._tmux_session_alive(session):
                if _retry < 1:
                    logger.info(f"Retrying tmux session for agent {agent.agent_id[:8]} (attempt {_retry + 1})")
                    new_session = f"agent-{hashlib.sha256(agent.goal.encode()).hexdigest()[:8]}-r"
                    cmd = "claude --dangerously-skip-permissions"
                    try:
                        managed_cmd = f"ORCHESTRATOR_MANAGED=1 {cmd}"
                        subprocess.run(
                            [TMUX, "new-session", "-d", "-s", new_session, "-x", "200", "-y", "50", managed_cmd],
                            capture_output=True, text=True, timeout=10,
                            cwd=CLAUDE_WORKING_DIR,
                        )
                        agent.tmux_session = new_session
                        log_file = os.path.join(AGENT_LOG_DIR, f"{agent.agent_id[:8]}.log")
                        subprocess.run(
                            [TMUX, "pipe-pane", "-t", new_session, "-o", f"cat >> {log_file}"],
                            capture_output=True, text=True, timeout=5,
                        )
                        agent._log_file = log_file
                        logger.info(f"Recreated tmux session {new_session} for agent {agent.agent_id[:8]}")
                        await self._send_prompt_and_monitor(agent, prompt, is_initial=True, _retry=_retry + 1)
                    except Exception as e:
                        logger.error(f"Retry tmux creation failed for {agent.agent_id[:8]}: {e}")
                        self._log_agent_start_failure(agent)
                    return
                else:
                    self._log_agent_start_failure(agent)
                    return

        # Record log file position before sending
        log_file = agent._log_file
        if log_file and os.path.exists(log_file):
            agent._log_pos_before_prompt = os.path.getsize(log_file)
        else:
            agent._log_pos_before_prompt = 0

        # Send the prompt
        await self._tmux_send_text(session, prompt)
        logger.info(f"Sent prompt to tmux {session}: {prompt[:80]}")

        # Monitor for completion
        await self._monitor_tmux_agent(agent, prompt=prompt)

    async def _monitor_tmux_agent(self, agent: ManagedAgent, prompt: str = ""):
        """Monitor a tmux Claude session until it finishes processing."""
        session = agent.tmux_session
        if not session:
            return

        idle_count = 0
        max_wait = 600  # 10 minutes
        poll_interval = 3
        # Give Claude time to start processing before checking idle
        await asyncio.sleep(5)

        for _ in range(max_wait // poll_interval):
            await asyncio.sleep(poll_interval)

            if not self._tmux_session_alive(session):
                logger.warning(f"tmux session {session} died for agent {agent.agent_id[:8]}")
                agent.tmux_session = None
                break

            pane = self._tmux_capture_pane(session)
            if self._detect_claude_idle(pane):
                idle_count += 1
                if idle_count >= 2:  # Confirm idle for 2 consecutive polls
                    break
            else:
                idle_count = 0

        # Detect if session died (no tmux_session means it died in the loop above)
        session_died = agent.tmux_session is None

        # Extract response text (pass prompt so it can be stripped from capture)
        response_text = self._extract_tmux_response(agent, prompt=prompt)

        # Update agent state
        if response_text.strip():
            agent.last_agent_message = response_text[-2000:]
            summary_lines = response_text.strip().split("\n")[-3:]
            agent.agent_summary = " ".join(summary_lines)[:200]
            agent.conversation_history.append({
                "role": "agent",
                "content": agent.last_agent_message,
                "timestamp": _now_iso(),
            })
        elif session_died:
            # Session died with no response — log failure so user sees it in chat
            fail_msg = "Claude session crashed before responding. Send another message to retry."
            self._log_chat(agent.agent_id, fail_msg, direction="outbound", sender="system")
            logger.warning(f"Agent {agent.agent_id[:8]} session died with no response")

        agent.is_idle = True
        agent.current_task = "Idle - waiting for input"

        # Update DynamoDB status
        status = "failed" if (session_died and not response_text.strip()) else "idle"
        try:
            tracker_table.update_item(
                Key={"agent_id": agent.agent_id},
                UpdateExpression="SET #s = :s",
                ExpressionAttributeValues={":s": status},
                ExpressionAttributeNames={"#s": "status"},
            )
        except Exception:
            pass

        # Try to capture session_id from Claude's local storage
        self._try_capture_session_id(agent)

        # Refresh title/goal from DynamoDB (may have been updated by summarizer)
        self._refresh_agent_meta(agent)

        # Persist state
        self._persist_routing_fields(agent)

        if response_text.strip():
            self._log_chat(agent.agent_id, agent.last_agent_message, direction="outbound", sender=agent.title)

        logger.info(f"Agent [{agent.title}] ({agent.agent_id[:8]}) finished, now idle")

        # Route response to source
        if response_text.strip():
            result_preview = response_text[-3000:]
            if agent.source == "bot" and agent.source_bot_id and self.bot_handler:
                # Agent outputs [NO_REPLY] when no response is needed
                if "[NO_REPLY]" in result_preview:
                    logger.info(f"Bot agent decided no reply needed for {agent.source_bot_id}")
                else:
                    try:
                        sent = await self.bot_handler.send_message(
                            agent.source_bot_id,
                            result_preview[:4000],
                            message_type="chat",
                        )
                        if sent:
                            logger.info(f"Bot reply sent to {agent.source_bot_id}")
                        else:
                            logger.error(f"Failed to send bot reply to {agent.source_bot_id}")
                    except Exception as e:
                        logger.error(f"Error sending bot reply: {e}")
                    summary = result_preview[:200].replace("\n", " ")
                    await self.send_update(
                        f"Replied to bot [{agent.source_bot_id}]: {summary}",
                        sender="BotComm",
                    )
            else:
                await self.message_queue.enqueue(agent.agent_id, agent.title, result_preview)
                await self._send_push_notification(agent.title, result_preview, agent_id=agent.agent_id)

        # Check for pending user messages that arrived while busy
        # Only re-process if a NEW user message was appended after the prompt we just processed
        if agent.conversation_history and agent.conversation_history[-1]["role"] == "user":
            last_user_msg = agent.conversation_history[-1]
            last_user_content = last_user_msg.get("content", "")
            # Compare against the prompt we just sent — if it's the same, it's not a new message
            if last_user_content != prompt:
                logger.info(f"Agent [{agent.title}] has pending user message, processing it now")
                agent.is_idle = False
                agent._running_task = asyncio.create_task(
                    self._send_prompt_and_monitor(agent, last_user_content)
                )
            else:
                logger.debug(f"Agent [{agent.title}] last user message is the prompt we just processed, skipping")

    # UI-only characters (never appear in Claude's text output)
    # NOTE: ⏺ is NOT here — Claude Code uses ⏺ to prefix its actual text output
    _CC_UI_CHARS = set('⏵⎿─│╭╰╮╯┌└┐┘├┤┬┴┼━═┃●◐◑◒◓⠋⠙⠹⠸⠼⠴✓✗↳▸▹▐▛▜▌▝▘▀▄█▊▋▍▎▏░▒▓')
    _CC_UI_KEYWORDS = (
        'bypass permissions', 'auto-accept', 'shift+tab', 'Esc to cancel',
        'Enter to confirm', 'ClaudeCode', 'Claude Code',
        'ClaudeMax', 'Claude Max', 'Yes, I trust',
    )
    _CC_TOOL_NAMES = ('Bash', 'Read', 'Edit', 'Write', 'Glob', 'Grep', 'Agent',
                      'Skill', 'WebFetch', 'WebSearch', 'TaskCreate', 'TaskUpdate',
                      'TaskGet', 'TaskOutput', 'NotebookEdit', 'CronCreate',
                      'ToolSearch', 'AskUserQuestion')

    def _classify_line(self, stripped: str) -> str:
        """Classify a tmux line: 'text' (keep), 'ui' (discard), or 'empty' (discard).

        Claude Code renders output as:
          ⏺ actual response text    ← text output (KEEP, strip ⏺ prefix)
          ⏺ Bash  cat foo.txt       ← tool call header (DISCARD)
          ⎿ tool output             ← tool output (DISCARD)
          ─────────────             ← separator (DISCARD)
          ⏵⏵ bypass permissions...  ← UI chrome (DISCARD)
          ▐▛███▜▌ Claude Code...    ← banner (DISCARD)
        """
        if not stripped:
            return 'empty'

        # ⏺ lines: could be text output OR tool call header
        if stripped.startswith('⏺'):
            after = stripped[1:].strip()
            if not after:
                return 'ui'  # bare ⏺ with nothing after it
            # Check if it's a tool call header: "⏺ ToolName  args" or "⏺ ToolName"
            for tn in self._CC_TOOL_NAMES:
                if after == tn or after.startswith(tn + ' ') or after.startswith(tn + '\t') or after.startswith(tn + '('):
                    return 'ui'
            # Otherwise it's Claude's text output
            return 'text'

        # Lines starting with other UI symbols
        if stripped[0] in self._CC_UI_CHARS:
            return 'ui'

        # Purely decorative lines
        if all(c in '─━═│┃┌┐└┘╭╮╰╯├┤┬┴┼ ▐▛▜▌▝▘▀▄█▊▋▍▎▏░▒▓▪' for c in stripped):
            return 'ui'

        # Tool use headers without ⏺ prefix
        for tn in self._CC_TOOL_NAMES:
            if stripped.startswith(tn + ' ') or stripped == tn:
                return 'ui'

        # Banner / UI keywords
        for kw in self._CC_UI_KEYWORDS:
            if kw in stripped:
                return 'ui'

        # Everything else is prompt text (pasted user input) or other non-response content.
        # In Claude Code, actual response text is ALWAYS ⏺-prefixed.
        return 'prompt'

    def _clean_text_line(self, line: str) -> str:
        """Strip Claude Code ⏺ prefix from text output lines."""
        stripped = line.strip()
        if stripped.startswith('⏺'):
            # Remove the ⏺ and leading whitespace after it
            return stripped[1:].strip()
        return line

    def _strip_prompt_from_response(self, text: str, prompt: str) -> str:
        """Remove the original prompt text that leaks into tmux capture."""
        if not prompt or not text:
            return text
        # The prompt appears at the start of the captured block (typed via send-keys).
        # Try to find and remove it. Use first 80 chars of prompt as anchor.
        prompt_clean = prompt.strip()
        # Try exact match first
        if text.startswith(prompt_clean):
            return text[len(prompt_clean):].strip()
        # Try matching first significant line of prompt (tmux may word-wrap)
        prompt_first_line = prompt_clean.split('\n')[0].strip()[:80]
        if len(prompt_first_line) > 20:
            idx = text.find(prompt_first_line)
            if idx >= 0 and idx < 100:  # Near the start
                # Find where prompt content ends — look for a big gap after prompt lines
                prompt_lines = prompt_clean.split('\n')
                # Remove all lines that match prompt lines from the beginning
                text_lines = text.split('\n')
                prompt_set = set(l.strip() for l in prompt_lines if l.strip())
                skip_until = 0
                for i, line in enumerate(text_lines):
                    if line.strip() in prompt_set or not line.strip():
                        skip_until = i + 1
                    else:
                        break
                if skip_until > 0:
                    return '\n'.join(text_lines[skip_until:]).strip()
        return text

    def _extract_response_from_lines(self, lines: list, prompt: str = "") -> str:
        """Core extraction: find Claude's text response between ❯ prompts, filtering UI."""
        # Collect ALL response blocks between ❯ prompts
        response_blocks = []
        current_block = []
        in_response = False
        in_text_block = False  # Track if we're inside a ⏺ text output block

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('❯'):
                if current_block:
                    response_blocks.append(current_block)
                current_block = []
                in_response = True
                in_text_block = False
                continue
            if in_response:
                kind = self._classify_line(stripped)
                if kind == 'text':
                    # Start or continue a text block
                    in_text_block = True
                    current_block.append(self._clean_text_line(line))
                elif kind == 'prompt' and in_text_block:
                    # Continuation line inside a ⏺ text block.
                    # Claude Code renders multi-line output where only the
                    # first line has the ⏺ prefix; subsequent lines are plain
                    # text (sometimes indented, sometimes not — especially
                    # after -J joins wrapped lines).  Keep them all.
                    current_block.append(stripped)
                elif kind == 'empty' and in_text_block:
                    # Blank line inside a text block (e.g. paragraph break)
                    current_block.append('')
                else:
                    # UI line or non-continuation prompt → end of text block
                    in_text_block = False

        if current_block:
            response_blocks.append(current_block)

        if not response_blocks:
            return ""

        # Use the LAST non-empty response block (most recent interaction)
        for block in reversed(response_blocks):
            raw = '\n'.join(block).strip()
            cleaned = self._strip_prompt_from_response(raw, prompt)
            if cleaned:
                return cleaned

        return ""

    def _extract_tmux_response(self, agent: ManagedAgent, prompt: str = "") -> str:
        """Extract Claude's response from the tmux pane (clean rendered text, no ANSI junk)."""
        if not agent.tmux_session:
            return ""

        pane = self._tmux_capture_pane(agent.tmux_session)
        if not pane:
            return ""

        pane = self._strip_ansi(pane)
        lines = pane.split('\n')
        text = self._extract_response_from_lines(lines, prompt)

        # Fallback: if extraction produced nothing useful, try the pipe-pane log
        if not text or len(text) < 10:
            text = self._extract_from_pipe_log(agent, prompt) or text

        return text if text else ""

    def _extract_from_pipe_log(self, agent: ManagedAgent, prompt: str = "") -> str:
        """Fallback: extract response from the pipe-pane log file."""
        log_file = getattr(agent, '_log_file', None)
        if not log_file or not os.path.exists(log_file):
            return ""
        try:
            # Only read from position recorded before the prompt was sent
            start_pos = getattr(agent, '_log_pos_before_prompt', 0)
            with open(log_file, 'r', errors='replace') as f:
                if start_pos:
                    f.seek(start_pos)
                raw = f.read()
            raw = self._strip_ansi(raw)
            lines = raw.split('\n')
            return self._extract_response_from_lines(lines, prompt)
        except Exception:
            return ""

    def _try_capture_session_id(self, agent: ManagedAgent):
        """Try to find the Claude session ID from local session storage."""
        if agent.session_id:
            return

        # Claude Code stores sessions under ~/.claude/projects/<project>/.sessions/
        sessions_dir = os.path.expanduser("~/.claude/projects/-Users-YOUR_USERNAME/.sessions")
        if not os.path.exists(sessions_dir):
            return

        try:
            # Find the most recently modified session file
            files = []
            for f in os.listdir(sessions_dir):
                if f.endswith('.json'):
                    fpath = os.path.join(sessions_dir, f)
                    files.append((f, os.path.getmtime(fpath)))
            files.sort(key=lambda x: x[1], reverse=True)

            if files:
                newest = files[0][0].replace('.json', '')
                agent.session_id = newest
                self._persist_session_id(agent)
                logger.info(f"Captured session_id {newest[:8]} for agent {agent.agent_id[:8]}")
        except Exception as e:
            logger.warning(f"Failed to capture session_id: {e}")

    def _persist_routing_fields(self, agent: ManagedAgent):
        """Update the routing context fields in DynamoDB for this agent."""
        try:
            expr = (
                "SET last_user_messages = :lum, last_agent_message = :lam, "
                "agent_summary = :asumm, agent_goal = :agoal, session_id = :sid"
            )
            vals = _convert_floats({
                ":lum": agent.last_user_messages[-3:] if agent.last_user_messages else [],
                ":lam": (agent.last_agent_message or "")[:2000],
                ":asumm": (agent.agent_summary or "")[:500],
                ":agoal": agent.goal[:1000],
                ":sid": agent.session_id or "",
            })
            tracker_table.update_item(
                Key={"agent_id": agent.agent_id},
                UpdateExpression=expr,
                ExpressionAttributeValues=vals,
            )
        except Exception as e:
            logger.error(f"Failed to persist routing fields for {agent.agent_id[:8]}: {e}")

    def _refresh_agent_meta(self, agent: ManagedAgent):
        """Read back title/goal from DynamoDB in case they were updated by the summarizer."""
        try:
            resp = tracker_table.get_item(
                Key={"agent_id": agent.agent_id},
                ProjectionExpression="title, goal",
            )
            item = resp.get("Item", {})
            new_title = item.get("title")
            new_goal = item.get("goal")
            if new_title and new_title != agent.title:
                logger.info(f"Agent title updated: [{agent.title}] -> [{new_title}]")
                agent.title = new_title
            if new_goal and new_goal != agent.goal:
                agent.goal = new_goal
        except Exception as e:
            logger.warning(f"Failed to refresh agent meta for {agent.agent_id[:8]}: {e}")

    async def send_update(self, message: str, sender: str = "YOUR_BOT_NAME"):
        """Send a system update visible in the Updates tab of the mobile app."""
        self._log_chat("system", message, direction="outbound", sender=sender)
        await self._send_push_notification("System", message, agent_id="system")
        logger.info(f"System update sent: {message[:80]}")

    def _log_chat(self, agent_id: str, message: str, direction: str = "outbound", sender: str = "", image_url: str = ""):
        """Log a chat message to the AgentChat DynamoDB table."""
        try:
            record = _convert_floats({
                "agent_id": agent_id,
                "timestamp": _now_ms(),
                "direction": direction,
                "message": message[:5000],
                "sender": sender,
                "ttl": _ttl_seconds(7),
            })
            if image_url:
                record["image_url"] = image_url
            chat_table.put_item(Item=record)
        except Exception as e:
            logger.error(f"Failed to log chat: {e}")

    # ========================
    # Agent Lifecycle
    # ========================

    @staticmethod
    def _truncate_title(goal: str) -> str:
        """Generate a temporary truncated title from a goal string."""
        first_line = goal.split('\n')[0]
        short = first_line[:40].strip()
        if len(first_line) > 40:
            space_idx = short.rfind(" ")
            if space_idx > 20:
                short = short[:space_idx]
            short += "..."
        return short

    async def _summarize_title_goal(self, agent: 'ManagedAgent'):
        """Use Claude Haiku to generate a short title and goal from the user's prompt, then update DynamoDB."""
        prompt_text = agent.goal[:500]
        prompt = f"""Given this user request to an AI agent, generate a short title and goal.

User request: "{prompt_text}"

Reply in EXACTLY this format (two lines, no extra text):
TITLE: <3-6 word summary>
GOAL: <1-2 sentence description of what needs to be done>"""

        try:
            loop = asyncio.get_event_loop()

            def _call_claude():
                try:
                    result = subprocess.run(
                        CLAUDE_ROUTE_CMD + [prompt],
                        capture_output=True, text=True,
                        timeout=CLAUDE_ROUTE_TIMEOUT, env=_CLEAN_ENV,
                    )
                    if result.returncode == 0:
                        return result.stdout.strip()
                    logger.warning(f"Claude summarize failed (rc={result.returncode}): {result.stderr[:200]}")
                    return None
                except subprocess.TimeoutExpired:
                    logger.warning("Claude summarize timed out")
                    return None
                except Exception as e:
                    logger.warning(f"Claude summarize failed: {e}")
                    return None

            response_text = await loop.run_in_executor(None, _call_claude)

            if not response_text:
                return

            # Parse TITLE: and GOAL: lines
            title = None
            goal = None
            for line in response_text.split("\n"):
                line = line.strip()
                if line.upper().startswith("TITLE:"):
                    title = line[6:].strip().strip('"')
                elif line.upper().startswith("GOAL:"):
                    goal = line[5:].strip().strip('"')

            if title:
                agent.title = title
                agent._update_dynamo("SET title = :t", {":t": title})
                if agent.tmux_session:
                    self._rename_tmux_window(agent, title)
                logger.info(f"Agent [{agent.agent_id[:8]}] title summarized: {title}")

            if goal:
                agent.goal = goal
                agent._update_dynamo("SET goal = :g", {":g": goal})
                logger.info(f"Agent [{agent.agent_id[:8]}] goal summarized: {goal}")

        except Exception as e:
            logger.warning(f"Failed to summarize title/goal for {agent.agent_id[:8]}: {e}")

    async def _start_agent(self, goal: str) -> str:
        """Start a new Claude agent with the given goal. Returns agent_id."""
        short_title = self._truncate_title(goal)

        # Generate session name and derive agent_id using same scheme as hooks
        session_name = f"agent-{hashlib.sha256(goal.encode()).hexdigest()[:8]}"
        agent_id = hashlib.sha256(f"claude-code::tmux-{session_name}".encode()).hexdigest()[:36]

        # Register in AgentTracker directly (no SDK — hooks will find this entry and update heartbeat)
        now = _now_iso()
        try:
            tracker_table.put_item(Item={
                "agent_id": agent_id,
                "agent_type": "claude-code",
                "agent_name": f"agent ({session_name})",
                "title": short_title,
                "goal": goal[:500],
                "status": "running",
                "current_task": "Starting Claude session",
                "started_at": now,
                "last_heartbeat": now,
                "tmux_session": session_name,
                "interactive": True,
                "ttl": Decimal(str(int(time.time()) + 7 * 86400)),
            })
        except Exception as e:
            logger.error(f"Failed to register agent: {e}")

        agent = ManagedAgent(
            agent_id=agent_id,
            goal=goal,
            title=short_title,
            tracker=None,
        )

        # Add the initial user message
        agent.conversation_history.append({
            "role": "user",
            "content": goal,
            "timestamp": now,
        })

        self.managed_agents[agent_id] = agent
        self._total_agents_started += 1

        # Persist initial state
        self._persist_routing_fields(agent)
        self._log_chat(agent_id, goal, direction="inbound", sender="user")

        # Send immediate ack so user doesn't stare at a loading indicator
        ack = self._generate_ack()
        self._log_chat(agent_id, ack, direction="outbound", sender=short_title)

        # Summarize title/goal in background via Claude Haiku (non-blocking)
        asyncio.create_task(self._summarize_title_goal(agent))

        # Create tmux session with interactive Claude and send the initial prompt
        self._create_agent_tmux(agent, initial_prompt=goal, session_name=session_name)

        logger.info(f"Started agent [{short_title}] ({agent_id[:8]})")

        return agent_id

    async def _stop_agent(self, agent_id: str):
        """Stop a managed agent and move to trash (reaped after 48h by cleanup).

        Tmux session is kept alive so the agent can be restored within 48h.
        """
        agent = self.managed_agents.get(agent_id)

        if not agent:
            # Not orchestrator-managed — just trash the DynamoDB entry (keep tmux alive)
            self._trash_agent(agent_id)
            return

        # Kill running process if any
        if agent.process and agent.process.poll() is None:
            agent.process.terminate()
            try:
                agent.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                agent.process.kill()

        # Cancel the output reader task
        if agent._running_task and not agent._running_task.done():
            agent._running_task.cancel()

        # Don't kill tmux — keep it alive for potential restore within 48h

        # Move to trash (reaped after 48h by cleanup)
        self._trash_agent(agent_id)

        title = agent.title
        del self.managed_agents[agent_id]
        logger.info(f"Stopped agent [{title}] ({agent_id[:8]})")

    def _trash_agent(self, agent_id: str):
        """Mark agent as trashed. Data will be reaped after 48h by claude-cleanup."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            tracker_table.update_item(
                Key={"agent_id": agent_id},
                UpdateExpression="SET #s = :s, trashed_at = :t, #h = :h",
                ExpressionAttributeValues={
                    ":s": "trashed",
                    ":t": now,
                    ":h": True,
                },
                ExpressionAttributeNames={
                    "#s": "status",
                    "#h": "hidden",
                },
            )
            logger.info(f"Trashed agent {agent_id[:8]}")
        except Exception as e:
            logger.error(f"Failed to trash agent {agent_id[:8]}: {e}")

    def _nuke_agent_data(self, agent_id: str):
        """Delete tracker, logs, and chat records for an agent from DynamoDB."""
        try:
            tracker_table.delete_item(Key={"agent_id": agent_id})
        except Exception:
            pass
        try:
            log_resp = logs_table.query(
                KeyConditionExpression=Key("agent_id").eq(agent_id)
            )
            for item in log_resp.get("Items", []):
                logs_table.delete_item(Key={
                    "agent_id": agent_id,
                    "timestamp": item["timestamp"],
                })
        except Exception:
            pass
        try:
            chat_resp = chat_table.query(
                KeyConditionExpression=Key("agent_id").eq(agent_id)
            )
            for item in chat_resp.get("Items", []):
                chat_table.delete_item(Key={
                    "agent_id": agent_id,
                    "timestamp": item["timestamp"],
                })
        except Exception:
            pass

    # ========================
    # Bot Restart
    # ========================

    RESTART_COMMANDS = {
        "task-worker": [
            sys.executable, os.path.expanduser("~/task-worker/worker.py")
        ],
        "telegram-bot": [
            sys.executable, os.path.join(os.path.dirname(__file__), "orchestrator.py")
        ],
    }

    async def _restart_bot(self, bot_type: str):
        """Restart a system bot (task-worker or orchestrator itself)."""
        if bot_type not in self.RESTART_COMMANDS:
            logger.warning(f"Unknown bot_type for restart: {bot_type}")
            return

        launch_cmd = self.RESTART_COMMANDS[bot_type]
        logger.info(f"Restarting bot: {bot_type}")

        if bot_type == "task-worker":
            # Kill existing task-worker process
            pidfile = "/tmp/task_worker.pid"
            try:
                if os.path.exists(pidfile):
                    old_pid = int(open(pidfile).read().strip())
                    os.kill(old_pid, signal.SIGTERM)
                    logger.info(f"Sent SIGTERM to task-worker PID {old_pid}")
                    await asyncio.sleep(2)
            except (ProcessLookupError, ValueError):
                pass
            except Exception as e:
                logger.error(f"Error killing task-worker: {e}")

            # Spawn new task-worker
            log_path = "/tmp/task_worker.log"
            with open(log_path, "a") as log_file:
                proc = subprocess.Popen(
                    launch_cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            logger.info(f"Spawned new task-worker PID {proc.pid}")
            self.self_tracker.log(f"Restarted task-worker (PID {proc.pid})")

        elif bot_type == "telegram-bot":
            # Self-restart: spawn replacement, then shut down
            logger.info("Orchestrator self-restart initiated")
            self.self_tracker.log("Orchestrator restarting...")

            # Clear pidlock so new process can start
            pidfile = "/tmp/orchestrator.pid"
            if os.path.exists(pidfile):
                os.remove(pidfile)

            # Spawn new orchestrator
            log_path = os.path.join(os.path.dirname(__file__), "orchestrator.log")
            with open(log_path, "a") as log_file:
                subprocess.Popen(
                    launch_cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            logger.info("Spawned replacement orchestrator, shutting down current instance")

            # Shut down gracefully
            await self.shutdown()

    # ========================
    # Dashboard Command Polling
    # ========================

    async def _poll_commands(self):
        """Poll DynamoDB AgentCommands for commands from the dashboard."""
        while self._running:
            try:
                response = commands_table.scan(
                    FilterExpression=Attr("status").eq("pending")
                )
                commands = response.get("Items", [])

                for cmd in sorted(commands, key=lambda c: c.get("created_at", "")):
                    await self._process_command(cmd)
            except Exception as e:
                logger.error(f"Command poll error: {e}")

            await asyncio.sleep(COMMAND_POLL_INTERVAL)

    async def _process_command(self, cmd):
        """Process a single dashboard command."""
        command_id = cmd["command_id"]
        command = cmd["command"]
        payload = cmd.get("payload", {})

        logger.info(f"Processing command: {command} ({command_id[:8]})")

        # Mark as processing
        try:
            commands_table.update_item(
                Key={"command_id": command_id},
                UpdateExpression="SET #s = :s",
                ExpressionAttributeValues={":s": "processing"},
                ExpressionAttributeNames={"#s": "status"},
            )
        except Exception as e:
            logger.error(f"Failed to mark command as processing: {e}")

        try:
            if command == "start_agent":
                prompt = payload.get("prompt", "")
                if prompt:
                    agent_id = await self._start_agent(prompt)
                    logger.info(f"Started agent from dashboard: {agent_id[:8] if agent_id else 'FAILED'}")

            elif command == "stop_agent":
                agent_id = payload.get("agent_id", "")
                if agent_id:
                    await self._stop_agent(agent_id)

            elif command == "delete_agent":
                agent_id = payload.get("agent_id", "")
                if agent_id:
                    await self._stop_agent(agent_id)

            elif command == "restart_bot":
                bot_type = payload.get("bot_type", "")
                await self._restart_bot(bot_type)

            elif command == "send_message":
                agent_id = payload.get("agent_id", "")
                message = payload.get("message", "")
                image_url = payload.get("image_url", "")

                # Build the prompt for Claude (includes image path)
                agent_prompt = message
                if image_url:
                    try:
                        local_image_path = await self._download_image_for_agent(image_url)
                        image_note = f"\n\n[User attached an image. View it at: {local_image_path}]"
                        agent_prompt = (message + image_note) if message else f"[User sent an image. View it at: {local_image_path}]"
                    except Exception as e:
                        logger.error(f"Failed to download image: {e}")
                        if not message:
                            agent_prompt = f"[User sent an image but download failed: {image_url}]"

                # Log the original message (not the modified one) with image_url for the app
                if agent_id and (message or image_url):
                    display_msg = message or "(image)"
                    self._log_chat(agent_id, display_msg, direction="inbound", sender="mobile", image_url=image_url)

                    # Signal the hook to skip logging (prevents double inbound messages)
                    flag_path = f"/tmp/orch_sent_{agent_id}"
                    with open(flag_path, "w") as f:
                        f.write(str(time.time()))

                    # Send the enriched prompt (with image path) to the agent
                    prompt_to_send = agent_prompt or message
                    if agent_id not in self.managed_agents:
                        # Try to rehydrate from DynamoDB/tmux so we get response monitoring
                        await self._rehydrate_agent(agent_id)
                    if agent_id in self.managed_agents:
                        await self._send_to_agent(agent_id, prompt_to_send, skip_log=True)
                    else:
                        delivered = await self._deliver_to_tmux(agent_id, prompt_to_send, skip_log=True)
                        if not delivered:
                            logger.warning(f"Cannot send message: agent {agent_id[:8]} not managed locally or via tmux")

            # Mark command as completed
            commands_table.update_item(
                Key={"command_id": command_id},
                UpdateExpression="SET #s = :s",
                ExpressionAttributeValues={":s": "completed"},
                ExpressionAttributeNames={"#s": "status"},
            )
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            try:
                commands_table.update_item(
                    Key={"command_id": command_id},
                    UpdateExpression="SET #s = :s",
                    ExpressionAttributeValues={":s": "failed"},
                    ExpressionAttributeNames={"#s": "status"},
                )
            except Exception:
                pass

    # ========================
    # Agent Monitoring
    # ========================

    async def _monitor_agents(self):
        """Monitor managed agents, update metrics, clean up stale ones."""
        last_reap = 0
        while self._running:
            try:
                for agent_id, agent in list(self.managed_agents.items()):
                    # Clean up dead subprocess (legacy)
                    if agent.process and agent.process.poll() is not None:
                        agent.process = None
                    # Remove dead tmux sessions from in-memory state
                    if agent.tmux_session and not self._tmux_session_alive(agent.tmux_session):
                        logger.warning(f"tmux session {agent.tmux_session} died for agent {agent_id[:8]}")
                        agent.tmux_session = None
                        agent.is_idle = True

                if self.self_tracker:
                    active = len(self.managed_agents)
                    busy = sum(1 for a in self.managed_agents.values() if a.is_busy)
                    idle = sum(1 for a in self.managed_agents.values() if a.state == "idle")
                    self.self_tracker.update_metrics(
                        managed_agents=active,
                        busy_agents=busy,
                        idle_agents=idle,
                        total_started=self._total_agents_started,
                    )

            except Exception as e:
                logger.error(f"Monitor error: {e}")

            await asyncio.sleep(10)


async def main():
    orchestrator = Orchestrator()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(orchestrator.shutdown()))

    await orchestrator.start()


def _acquire_pidlock():
    """Ensure only one orchestrator instance runs. Exit if another is alive."""
    pidfile = "/tmp/orchestrator.pid"
    if os.path.exists(pidfile):
        try:
            old_pid = int(open(pidfile).read().strip())
            os.kill(old_pid, 0)
            print(f"[PID Lock] Orchestrator already running (PID {old_pid}), exiting.")
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
    asyncio.run(main())
