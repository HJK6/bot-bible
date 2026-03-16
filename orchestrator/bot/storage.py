"""DynamoDB storage layer for bot-to-bot communication."""

import time
import logging
from decimal import Decimal
from typing import List, Optional

import boto3
from boto3.dynamodb.conditions import Key

from .models import BotCommBot, BotCommSession, BotCommMessage

logger = logging.getLogger("orchestrator.bot.storage")

AWS_REGION = "us-east-1"

# Table names
BOTS_TABLE = "BotCommBots"
SESSIONS_TABLE = "BotCommSessions"
MESSAGES_TABLE = "BotCommMessages"


def _convert_floats(item):
    """Recursively convert float -> Decimal for DynamoDB."""
    if isinstance(item, dict):
        return {k: _convert_floats(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [_convert_floats(i) for i in item]
    elif isinstance(item, float):
        return Decimal(str(item))
    return item


def _convert_decimals(item):
    """Recursively convert Decimal -> int/float from DynamoDB reads."""
    if isinstance(item, dict):
        return {k: _convert_decimals(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [_convert_decimals(i) for i in item]
    elif isinstance(item, Decimal):
        return int(item) if item == int(item) else float(item)
    return item


def _now_ms():
    return int(time.time() * 1000)


class BotCommStorage:
    """DynamoDB CRUD for BotComm tables."""

    def __init__(self):
        self._dynamo = boto3.resource("dynamodb", region_name=AWS_REGION)
        self.bots = self._dynamo.Table(BOTS_TABLE)
        self.sessions = self._dynamo.Table(SESSIONS_TABLE)
        self.messages = self._dynamo.Table(MESSAGES_TABLE)

    # -- Bots ---------------------------------------------------------------

    def get_bot(self, bot_id: str) -> Optional[BotCommBot]:
        """Get a bot by ID."""
        try:
            resp = self.bots.get_item(Key={"bot_id": bot_id})
            item = resp.get("Item")
            if not item:
                return None
            return BotCommBot.from_dict(_convert_decimals(item))
        except Exception as e:
            logger.error(f"Failed to get bot {bot_id}: {e}")
            return None

    def put_bot(self, bot: BotCommBot):
        """Create or update a bot."""
        bot.updated_at = _now_ms()
        if not bot.created_at:
            bot.created_at = _now_ms()
        self.bots.put_item(Item=_convert_floats(bot.to_dict()))

    def get_all_bots(self) -> List[BotCommBot]:
        """Get all registered bots."""
        try:
            resp = self.bots.scan()
            return [BotCommBot.from_dict(_convert_decimals(i)) for i in resp.get("Items", [])]
        except Exception as e:
            logger.error(f"Failed to scan bots: {e}")
            return []

    # -- Sessions -----------------------------------------------------------

    def get_active_session(self, bot_id: str) -> Optional[BotCommSession]:
        """Get the most recent active session for a bot."""
        try:
            resp = self.sessions.query(
                KeyConditionExpression=Key("bot_id").eq(bot_id),
                ScanIndexForward=False,
                Limit=1,
            )
            items = resp.get("Items", [])
            if not items:
                return None
            session = BotCommSession.from_dict(_convert_decimals(items[0]))
            if session.status in ("active", "compacted"):
                return session
            return None
        except Exception as e:
            logger.error(f"Failed to get active session for {bot_id}: {e}")
            return None

    def get_session(self, bot_id: str, session_id: str) -> Optional[BotCommSession]:
        """Get a specific session."""
        try:
            resp = self.sessions.get_item(Key={"bot_id": bot_id, "session_id": session_id})
            item = resp.get("Item")
            if not item:
                return None
            return BotCommSession.from_dict(_convert_decimals(item))
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None

    def get_latest_session(self, bot_id: str) -> Optional[BotCommSession]:
        """Get the most recent session for a bot."""
        try:
            resp = self.sessions.query(
                KeyConditionExpression=Key("bot_id").eq(bot_id),
                ScanIndexForward=False,
                Limit=1,
            )
            items = resp.get("Items", [])
            if not items:
                return None
            return BotCommSession.from_dict(_convert_decimals(items[0]))
        except Exception as e:
            logger.error(f"Failed to get latest session for {bot_id}: {e}")
            return None

    def put_session(self, session: BotCommSession):
        """Create or update a session."""
        self.sessions.put_item(Item=_convert_floats(session.to_dict()))

    def update_session_activity(self, bot_id: str, session_id: str):
        """Update last_message_at and increment message_count."""
        try:
            self.sessions.update_item(
                Key={"bot_id": bot_id, "session_id": session_id},
                UpdateExpression="SET last_message_at = :t, message_count = message_count + :one",
                ExpressionAttributeValues={
                    ":t": _now_ms(),
                    ":one": 1,
                },
            )
        except Exception as e:
            logger.error(f"Failed to update session activity: {e}")

    def update_session_summary(self, bot_id: str, session_id: str, summary: str):
        """Set the compacted summary for a session."""
        try:
            self.sessions.update_item(
                Key={"bot_id": bot_id, "session_id": session_id},
                UpdateExpression="SET summary = :s",
                ExpressionAttributeValues={":s": summary},
            )
        except Exception as e:
            logger.error(f"Failed to update session summary: {e}")

    def close_session(self, bot_id: str, session_id: str):
        """Mark a session as closed."""
        try:
            self.sessions.update_item(
                Key={"bot_id": bot_id, "session_id": session_id},
                UpdateExpression="SET #st = :s",
                ExpressionAttributeValues={":s": "closed"},
                ExpressionAttributeNames={"#st": "status"},
            )
        except Exception as e:
            logger.error(f"Failed to close session: {e}")

    # -- Messages -----------------------------------------------------------

    def put_message(self, message: BotCommMessage):
        """Store a message."""
        self.messages.put_item(Item=_convert_floats(message.to_dict()))

    def get_session_messages(self, session_id: str, limit: int = 50) -> List[BotCommMessage]:
        """Get messages for a session, ordered by message_id (time-sortable)."""
        try:
            resp = self.messages.query(
                KeyConditionExpression=Key("session_id").eq(session_id),
                ScanIndexForward=True,
                Limit=limit,
            )
            return [BotCommMessage.from_dict(_convert_decimals(i)) for i in resp.get("Items", [])]
        except Exception as e:
            logger.error(f"Failed to get messages for session {session_id}: {e}")
            return []

    def get_recent_messages(self, session_id: str, limit: int = 10) -> List[BotCommMessage]:
        """Get the most recent N messages for a session."""
        try:
            resp = self.messages.query(
                KeyConditionExpression=Key("session_id").eq(session_id),
                ScanIndexForward=False,
                Limit=limit,
            )
            items = resp.get("Items", [])
            messages = [BotCommMessage.from_dict(_convert_decimals(i)) for i in items]
            messages.reverse()
            return messages
        except Exception as e:
            logger.error(f"Failed to get recent messages: {e}")
            return []

    def delete_messages(self, session_id: str, message_ids: List[str]):
        """Delete specific messages by session_id + message_id pairs."""
        try:
            with self.messages.batch_writer() as batch:
                for mid in message_ids:
                    batch.delete_item(Key={"session_id": session_id, "message_id": mid})
        except Exception as e:
            logger.error(f"Failed to delete messages: {e}")
