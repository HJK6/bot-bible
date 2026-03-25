"""DynamoDB storage layer for SMS system."""

import time
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Any

import boto3
from boto3.dynamodb.conditions import Key, Attr

from .models import SmsContact, SmsSession, SmsMessage, SmsExpense

logger = logging.getLogger("orchestrator.sms.storage")

AWS_REGION = "us-east-1"

# Table names
CONTACTS_TABLE = "BartSmsContacts"
SESSIONS_TABLE = "BartSmsSessions"
MESSAGES_TABLE = "BartSmsMessages"
EXPENSES_TABLE = "BartSmsExpenses"


def _convert_floats(item):
    """Recursively convert float → Decimal for DynamoDB."""
    if isinstance(item, dict):
        return {k: _convert_floats(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [_convert_floats(i) for i in item]
    elif isinstance(item, float):
        return Decimal(str(item))
    return item


def _convert_decimals(item):
    """Recursively convert Decimal → int/float from DynamoDB reads."""
    if isinstance(item, dict):
        return {k: _convert_decimals(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [_convert_decimals(i) for i in item]
    elif isinstance(item, Decimal):
        return int(item) if item == int(item) else float(item)
    return item


def _now_ms():
    return int(time.time() * 1000)


class SmsStorage:
    """DynamoDB CRUD for SMS tables."""

    def __init__(self):
        self._dynamo = boto3.resource("dynamodb", region_name=AWS_REGION)
        self.contacts = self._dynamo.Table(CONTACTS_TABLE)
        self.sessions = self._dynamo.Table(SESSIONS_TABLE)
        self.messages = self._dynamo.Table(MESSAGES_TABLE)
        self.expenses = self._dynamo.Table(EXPENSES_TABLE)

    # ── Contacts ──────────────────────────────────────────────────────

    def get_contact(self, phone: str) -> Optional[SmsContact]:
        """Get a contact by phone number."""
        try:
            resp = self.contacts.get_item(Key={"phone": phone})
            item = resp.get("Item")
            if not item:
                return None
            return SmsContact.from_dict(_convert_decimals(item))
        except Exception as e:
            logger.error(f"Failed to get contact {phone}: {e}")
            return None

    def put_contact(self, contact: SmsContact):
        """Create or update a contact."""
        contact.updated_at = _now_ms()
        if not contact.created_at:
            contact.created_at = _now_ms()
        self.contacts.put_item(Item=_convert_floats(contact.to_dict()))

    def get_all_contacts(self) -> List[SmsContact]:
        """Get all contacts."""
        try:
            resp = self.contacts.scan()
            return [SmsContact.from_dict(_convert_decimals(i)) for i in resp.get("Items", [])]
        except Exception as e:
            logger.error(f"Failed to scan contacts: {e}")
            return []

    def get_contacts_for_event(self, event_id: str) -> List[SmsContact]:
        """Get all contacts participating in an expense event."""
        try:
            resp = self.contacts.scan(
                FilterExpression=Attr("expense_events").contains(event_id)
            )
            return [SmsContact.from_dict(_convert_decimals(i)) for i in resp.get("Items", [])]
        except Exception as e:
            logger.error(f"Failed to get contacts for event {event_id}: {e}")
            return []

    # ── Sessions ──────────────────────────────────────────────────────

    def get_active_session(self, phone: str) -> Optional[SmsSession]:
        """Get the most recent active session for a phone number."""
        try:
            resp = self.sessions.query(
                KeyConditionExpression=Key("phone").eq(phone),
                ScanIndexForward=False,  # Most recent first
                Limit=1,
            )
            items = resp.get("Items", [])
            if not items:
                return None
            session = SmsSession.from_dict(_convert_decimals(items[0]))
            if session.status in ("active", "compacted"):
                return session
            return None
        except Exception as e:
            logger.error(f"Failed to get active session for {phone}: {e}")
            return None

    def get_session(self, phone: str, session_id: str) -> Optional[SmsSession]:
        """Get a specific session."""
        try:
            resp = self.sessions.get_item(Key={"phone": phone, "session_id": session_id})
            item = resp.get("Item")
            if not item:
                return None
            return SmsSession.from_dict(_convert_decimals(item))
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None

    def put_session(self, session: SmsSession):
        """Create or update a session."""
        self.sessions.put_item(Item=_convert_floats(session.to_dict()))

    def update_session_activity(self, phone: str, session_id: str):
        """Update last_message_at and increment message_count."""
        try:
            self.sessions.update_item(
                Key={"phone": phone, "session_id": session_id},
                UpdateExpression="SET last_message_at = :t, message_count = message_count + :one",
                ExpressionAttributeValues={
                    ":t": _now_ms(),
                    ":one": 1,
                },
            )
        except Exception as e:
            logger.error(f"Failed to update session activity: {e}")

    def update_session_summary(self, phone: str, session_id: str, summary: str):
        """Set the compacted summary for a session. Keeps status as 'active'."""
        try:
            self.sessions.update_item(
                Key={"phone": phone, "session_id": session_id},
                UpdateExpression="SET summary = :s",
                ExpressionAttributeValues={":s": summary},
            )
        except Exception as e:
            logger.error(f"Failed to update session summary: {e}")

    def close_session(self, phone: str, session_id: str):
        """Mark a session as closed."""
        try:
            self.sessions.update_item(
                Key={"phone": phone, "session_id": session_id},
                UpdateExpression="SET #st = :s",
                ExpressionAttributeValues={":s": "closed"},
                ExpressionAttributeNames={"#st": "status"},
            )
        except Exception as e:
            logger.error(f"Failed to close session: {e}")

    # ── Messages ──────────────────────────────────────────────────────

    def put_message(self, message: SmsMessage):
        """Store a message."""
        self.messages.put_item(Item=_convert_floats(message.to_dict()))

    def check_message_sid_exists(self, session_id: str, message_sid: str) -> bool:
        """Check if a message with this Twilio MessageSid already exists (dedup)."""
        if not message_sid:
            return False
        try:
            resp = self.messages.query(
                KeyConditionExpression=Key("session_id").eq(session_id),
                FilterExpression=Attr("message_sid").eq(message_sid),
                Limit=1,
            )
            return len(resp.get("Items", [])) > 0
        except Exception:
            return False

    def get_session_messages(self, session_id: str, limit: int = 50) -> List[SmsMessage]:
        """Get messages for a session, ordered by message_id (time-sortable)."""
        try:
            resp = self.messages.query(
                KeyConditionExpression=Key("session_id").eq(session_id),
                ScanIndexForward=True,
                Limit=limit,
            )
            return [SmsMessage.from_dict(_convert_decimals(i)) for i in resp.get("Items", [])]
        except Exception as e:
            logger.error(f"Failed to get messages for session {session_id}: {e}")
            return []

    def get_recent_messages(self, session_id: str, limit: int = 10) -> List[SmsMessage]:
        """Get the most recent N messages for a session."""
        try:
            resp = self.messages.query(
                KeyConditionExpression=Key("session_id").eq(session_id),
                ScanIndexForward=False,  # Most recent first
                Limit=limit,
            )
            items = resp.get("Items", [])
            messages = [SmsMessage.from_dict(_convert_decimals(i)) for i in items]
            messages.reverse()  # Put back in chronological order
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

    # ── Expenses ──────────────────────────────────────────────────────

    def put_expense(self, expense: SmsExpense):
        """Store an expense."""
        if not expense.created_at:
            expense.created_at = _now_ms()
        self.expenses.put_item(Item=_convert_floats(expense.to_dict()))

    def get_event_expenses(self, event_id: str) -> List[SmsExpense]:
        """Get all expenses for an event."""
        try:
            resp = self.expenses.query(
                KeyConditionExpression=Key("event_id").eq(event_id),
            )
            return [SmsExpense.from_dict(_convert_decimals(i)) for i in resp.get("Items", [])]
        except Exception as e:
            logger.error(f"Failed to get expenses for event {event_id}: {e}")
            return []

    def delete_expense(self, event_id: str, expense_id: str):
        """Delete a specific expense."""
        try:
            self.expenses.delete_item(Key={"event_id": event_id, "expense_id": expense_id})
        except Exception as e:
            logger.error(f"Failed to delete expense {expense_id}: {e}")
