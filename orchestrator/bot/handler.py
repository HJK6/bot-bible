"""Bot-to-bot communication handler — processes incoming bot messages, sends outbound, manages sessions."""

import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from typing import Optional, Callable, List

import boto3

from .models import BotCommBot, BotCommSession, BotCommMessage, BotScope
from .storage import BotCommStorage

logger = logging.getLogger("orchestrator.bot")

# Fallback gap: only used if Claude classification fails
FALLBACK_GAP_MS = 24 * 60 * 60 * 1000

# Compact after this many messages
COMPACT_THRESHOLD = 20
COMPACT_KEEP_RECENT = 5

MEDIA_BUCKET = "YOUR_BOT_NAME-chat-media"
AWS_REGION = "us-east-1"

# SSM path for the shared HMAC secret used to sign outbound messages
HMAC_SECRET_SSM = "/YOUR_BOT_NAME/botcomm/secret"

_hmac_secret_cache = None


def _ulid() -> str:
    return f"{int(time.time() * 1000):013d}_{uuid.uuid4().hex[:8]}"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _format_gap(ms: int) -> str:
    """Convert milliseconds to human-readable time gap."""
    seconds = ms // 1000
    if seconds < 60:
        return f"{seconds} seconds ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def _get_hmac_secret() -> str:
    """Fetch HMAC signing secret from SSM (cached)."""
    global _hmac_secret_cache
    if _hmac_secret_cache is None:
        ssm = boto3.client("ssm", region_name=AWS_REGION)
        try:
            resp = ssm.get_parameter(Name=HMAC_SECRET_SSM, WithDecryption=True)
            _hmac_secret_cache = resp["Parameter"]["Value"]
        except Exception as e:
            logger.error(f"Failed to get HMAC secret: {e}")
            _hmac_secret_cache = ""
    return _hmac_secret_cache


def _sign_payload(payload_str: str) -> str:
    """Create HMAC-SHA256 signature of payload."""
    secret = _get_hmac_secret()
    if not secret:
        return ""
    return hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()


class BotHandler:
    """Processes bot-to-bot messages with session management and outbound delivery."""

    def __init__(self, notify_fn: Optional[Callable] = None):
        """
        Args:
            notify_fn: async callable(message, sender="BotComm") to push updates to mobile app
        """
        self.storage = BotCommStorage()
        self._notify_fn = notify_fn
        self._s3 = boto3.client("s3", region_name=AWS_REGION)

    async def handle_incoming(self, bot_id: str, message_type: str, message: str,
                              reply_to: str = "", attachments: list = None,
                              message_id: str = ""):
        """Main entry point for incoming bot messages.
        Called by orchestrator when SQS delivers a bot message.
        """
        attachments = attachments or []

        # 1. Look up bot
        bot = self.storage.get_bot(bot_id)
        if not bot:
            logger.warning(f"Unknown bot: {bot_id}")
            await self._notify(f"Message from unknown bot '{bot_id}': {message[:100]}")
            return

        if bot.status != "active":
            logger.warning(f"Suspended bot tried to communicate: {bot_id}")
            return

        logger.info(f"Bot message from {bot.name} ({bot_id}): [{message_type}] {message[:80]}")

        # 2. Resolve session
        session = self._resolve_session(bot, message)

        # 3. Store inbound message
        msg = BotCommMessage(
            session_id=session.session_id,
            message_id=message_id or _ulid(),
            bot_id=bot_id,
            direction="inbound",
            message_type=message_type,
            body=message,
            attachments=attachments,
            reply_to=reply_to,
            created_at=_now_ms(),
        )
        self.storage.put_message(msg)
        self.storage.update_session_activity(bot_id, session.session_id)

        # 4. Notify archon
        await self._notify(
            f"Bot [{bot.name}] ({message_type}): {message[:200]}",
            sender="BotComm",
        )

        # 5. Handle special message types
        if message_type == "capability_query":
            await self._handle_capability_query(bot, session, message)
        # chat, data_request, data_response — routed to orchestrator agent
        # The orchestrator will pick up the notification and route to an agent

        # 6. Check compaction
        session_fresh = self.storage.get_session(bot_id, session.session_id)
        if session_fresh and session_fresh.message_count > COMPACT_THRESHOLD:
            self._compact_session_sync(session)

    def _classify_session(self, bot: BotCommBot, session: BotCommSession,
                           gap_ms: int, new_message: str) -> Optional[str]:
        """Use Claude to classify whether a new message continues the existing session or starts a new one.

        Returns 'continue', 'new', or None on error.
        """
        # Gather context
        recent = self.storage.get_recent_messages(session.session_id, limit=5)
        summary = getattr(session, "summary", "") or ""
        gap_str = _format_gap(gap_ms)

        # Build conversation history snippet
        history_lines = []
        for msg in recent:
            direction = "Friend" if msg.direction == "inbound" else "YOUR_BOT_NAME"
            history_lines.append(f"{direction}: {msg.body[:300]}")
        history = "\n".join(history_lines) if history_lines else "(no recent messages)"

        prompt = f"""You are a session classifier for a bot-to-bot messaging system.
Given the conversation history and a new incoming message, decide: does this message CONTINUE the existing conversation, or START a brand new topic?

Consider:
- Topic continuity: does the new message relate to what was discussed?
- References: does it reference prior messages, use pronouns like "it"/"that", or follow up?
- Time gap is a signal but NOT a hard rule. A message after 12 hours can still continue a conversation if the topic matches. A message after 10 minutes can be a new topic.

Session summary: {summary if summary else '(none)'}

Recent messages:
{history}

Time since last message: {gap_str}

New message from friend bot: {new_message[:500]}

Reply with exactly one word: continue or new"""

        try:
            # Clean env to avoid nested session detection when called from within Claude Code
            clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            result = subprocess.run(
                ["claude", "-p", prompt, "--model", "claude-haiku-4-5-20251001", "--output-format", "text"],
                capture_output=True, text=True, timeout=15, env=clean_env,
            )
            if result.returncode != 0:
                logger.warning(f"Claude session classify failed (rc={result.returncode}): {result.stderr[:200]}")
                return None
            answer = result.stdout.strip().lower()
            if answer in ("continue", "new"):
                logger.info(f"Session classify for {bot.name}: {answer} (gap={gap_str})")
                return answer
            logger.warning(f"Unexpected classify response: {answer[:100]}")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("Session classify timed out")
            return None
        except Exception as e:
            logger.warning(f"Session classify error: {e}")
            return None

    def _resolve_session(self, bot: BotCommBot, message_text: str = "") -> BotCommSession:
        """Get or create a session for this bot, using AI classification when possible."""
        active = self.storage.get_active_session(bot.bot_id)

        if not active:
            # No active session — create new
            session = BotCommSession(
                bot_id=bot.bot_id,
                session_id=_ulid(),
                started_at=_now_ms(),
                last_message_at=_now_ms(),
                message_count=0,
                status="active",
            )
            self.storage.put_session(session)
            logger.info(f"New session for {bot.name} ({bot.bot_id}): {session.session_id}")
            return session

        gap_ms = _now_ms() - active.last_message_at

        # Use Claude to classify
        decision = self._classify_session(bot, active, gap_ms, message_text) if message_text else None

        if decision == "new":
            self.storage.close_session(active.bot_id, active.session_id)
            session = BotCommSession(
                bot_id=bot.bot_id,
                session_id=_ulid(),
                started_at=_now_ms(),
                last_message_at=_now_ms(),
                message_count=0,
                status="active",
            )
            self.storage.put_session(session)
            logger.info(f"New session (AI classified) for {bot.name} ({bot.bot_id}): {session.session_id}")
            return session

        if decision == "continue":
            return active

        # Fallback: classification unavailable — use 24h heuristic
        if gap_ms >= FALLBACK_GAP_MS:
            logger.info(f"Fallback: gap {_format_gap(gap_ms)} >= 24h, new session for {bot.name}")
            self.storage.close_session(active.bot_id, active.session_id)
            session = BotCommSession(
                bot_id=bot.bot_id,
                session_id=_ulid(),
                started_at=_now_ms(),
                last_message_at=_now_ms(),
                message_count=0,
                status="active",
            )
            self.storage.put_session(session)
            return session

        logger.info(f"Fallback: gap {_format_gap(gap_ms)} < 24h, continuing session for {bot.name}")
        return active

    async def _handle_capability_query(self, bot: BotCommBot, session: BotCommSession, query: str):
        """Respond to a capability query with YOUR_BOT_NAME's capabilities."""
        capabilities = [
            "weather — current conditions and forecasts via Open-Meteo",
            "sms — send/receive SMS via Twilio",
            "email — send/read email via Gmail API",
            "calendar — manage Google Calendar events",
            "contacts — macOS contacts lookup",
            "web_scraper — AI-guided web scraping and smart crawling",
            "dynamo — DynamoDB operations",
            "s3_data — share data via S3 presigned URLs",
            "scheduler — schedule one-time and recurring tasks",
            "voice_call — AI voice calls via Twilio + Bedrock",
            "memory — event logging with semantic search",
            "notes — Apple Notes read/create/search",
        ]

        response = f"YOUR_BOT_NAME capabilities:\n" + "\n".join(f"- {c}" for c in capabilities)

        await self.send_message(
            bot_id=bot.bot_id,
            message=response,
            message_type="capability_response",
            reply_to=session.session_id,
        )

    async def send_message(self, bot_id: str, message: str, message_type: str = "chat",
                           reply_to: str = "", attachments: list = None) -> bool:
        """Send a message to a friend bot via their webhook URL."""
        attachments = attachments or []

        bot = self.storage.get_bot(bot_id)
        if not bot:
            logger.error(f"Cannot send to unknown bot: {bot_id}")
            return False

        if not bot.webhook_url:
            logger.error(f"Bot {bot_id} has no webhook_url configured")
            return False

        # Resolve session for storing outbound
        session = self._resolve_session(bot, message)

        # Build payload
        payload = {
            "bot_id": "YOUR_BOT_NAME",
            "message_id": _ulid(),
            "message_type": message_type,
            "message": message,
            "reply_to": reply_to,
            "attachments": attachments,
            "timestamp": _now_ms(),
        }

        payload_str = json.dumps(payload, sort_keys=True)
        signature = _sign_payload(payload_str)
        payload["signature"] = signature

        # POST to friend bot's webhook
        try:
            req = urllib.request.Request(
                bot.webhook_url,
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-YOUR_BOT_NAME-Signature": signature,
                },
            )
            resp = urllib.request.urlopen(req, timeout=15)
            resp_body = resp.read().decode()
            logger.info(f"Sent to {bot.name} ({bot_id}): {message[:80]} -> {resp.status}")
        except Exception as e:
            logger.error(f"Failed to send to {bot.name} ({bot_id}): {e}")
            return False

        # Store outbound message
        msg = BotCommMessage(
            session_id=session.session_id,
            message_id=payload["message_id"],
            bot_id=bot_id,
            direction="outbound",
            message_type=message_type,
            body=message,
            attachments=attachments,
            reply_to=reply_to,
            created_at=_now_ms(),
        )
        self.storage.put_message(msg)
        self.storage.update_session_activity(bot_id, session.session_id)

        return True

    def generate_download_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned GET URL for downloading data from S3."""
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": MEDIA_BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )

    def generate_upload_url(self, bot_id: str, filename: str,
                            content_type: str = "application/json") -> dict:
        """Generate a presigned PUT URL for uploading data to S3."""
        key = f"bot-data/{bot_id}/{int(time.time())}_{filename}"
        upload_url = self._s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": MEDIA_BUCKET,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=300,
        )
        return {
            "upload_url": upload_url,
            "key": key,
            "object_url": f"https://{MEDIA_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{key}",
        }

    def _compact_session_sync(self, session: BotCommSession):
        """Compact older messages into a summary (synchronous)."""
        messages = self.storage.get_session_messages(session.session_id, limit=100)
        if len(messages) <= COMPACT_THRESHOLD:
            return

        to_summarize = messages[:-COMPACT_KEEP_RECENT]

        summary_parts = []
        for msg in to_summarize:
            direction = "Friend" if msg.direction == "inbound" else "YOUR_BOT_NAME"
            summary_parts.append(f"[{msg.message_type}] {direction}: {msg.body[:200]}")

        summary = f"Compacted {len(to_summarize)} messages. Topics: " + "; ".join(
            set(m.message_type for m in to_summarize)
        ) + f"\nMessages:\n" + "\n".join(summary_parts[:15])

        # Truncate if too long
        if len(summary) > 2000:
            summary = summary[:1997] + "..."

        self.storage.update_session_summary(session.bot_id, session.session_id, summary)
        message_ids = [msg.message_id for msg in to_summarize]
        self.storage.delete_messages(session.session_id, message_ids)
        logger.info(f"Compacted session {session.session_id}: {len(to_summarize)} messages")

    async def _notify(self, message: str, sender: str = "BotComm"):
        """Send notification to mobile app."""
        if self._notify_fn:
            try:
                await self._notify_fn(message, sender=sender)
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
