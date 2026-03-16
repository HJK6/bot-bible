"""Data models for SMS system. Uses DataclassBase from land-bot."""

import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

sys.path.insert(0, "/Users/bartimaeus/land-bot")
from modules.Models import DataclassBase


# -- Scopes ----------------------------------------------------------------

class Scope:
    """Known scope constants."""
    ARCHON = "archon"             # Full access — admin/owner
    EXPENSE_TRACKER = "expense_tracker"  # Can log expenses, check balances
    ALTUM_ANALYTICS = "altum_analytics"  # Altum Realty reporting — queries CRM data
    CHAT = "chat"                 # General chat only


# -- Contacts --------------------------------------------------------------

@dataclass
class SmsContact(DataclassBase):
    """BartSmsContacts table. PK: phone (E.164, e.g. '+1XXXXXXXXXX')."""

    phone: str = ""               # E.164 format
    name: str = ""                # Display name
    scopes: List[str] = field(default_factory=list)  # e.g. ["archon"] or ["expense_tracker"]
    expense_events: List[str] = field(default_factory=list)  # event IDs this contact participates in
    created_at: int = 0           # Epoch ms
    updated_at: int = 0           # Epoch ms


# -- Sessions --------------------------------------------------------------

@dataclass
class SmsSession(DataclassBase):
    """BartSmsSessions table. PK: phone, SK: session_id.
    A session groups related messages within a time window.
    After SESSION_GAP_HOURS of inactivity, a new session starts."""

    phone: str = ""               # E.164 format
    session_id: str = ""          # ULID
    started_at: int = 0           # Epoch ms
    last_message_at: int = 0      # Epoch ms
    message_count: int = 0
    summary: str = ""             # Compacted summary of older messages
    status: str = "active"        # active | compacted | closed


# -- Messages --------------------------------------------------------------

@dataclass
class SmsMessage(DataclassBase):
    """BartSmsMessages table. PK: session_id, SK: message_id (ULID-style string).
    Individual messages within a session."""

    session_id: str = ""
    message_id: str = ""          # ULID-style: "{timestamp_ms}_{uuid8}" — sort key
    phone: str = ""               # Sender phone (E.164)
    direction: str = ""           # "inbound" | "outbound"
    body: str = ""
    message_sid: str = ""         # Twilio MessageSid (for dedup)
    created_at: int = 0           # Epoch ms (informational)


# -- Expenses --------------------------------------------------------------

@dataclass
class SmsExpenseItem(DataclassBase):
    """A line item within an expense."""
    description: str = ""
    amount: float = 0.0
    for_person: str = ""          # Phone of person this item is for (empty = shared)


@dataclass
class SmsExpense(DataclassBase):
    """BartSmsExpenses table. PK: event_id, SK: expense_id.
    Tracks individual expenses within an event (e.g. bachelor_party)."""

    event_id: str = ""            # e.g. "bachelor_party"
    expense_id: str = ""          # ULID
    payer_phone: str = ""         # Who paid (E.164)
    payer_name: str = ""          # Display name of payer
    description: str = ""         # e.g. "Dinner at XYZ"
    amount: float = 0.0           # Total amount
    expense_date: str = ""        # Date of expense, e.g. "Feb 26" or "2026-02-26"
    items: List[SmsExpenseItem] = field(default_factory=list)  # Itemized breakdown
    split_among: List[str] = field(default_factory=list)  # Phones to split among (empty = all participants)
    split_type: str = "equal"     # equal | itemized | custom
    created_at: int = 0           # Epoch ms
    note: str = ""                # Any additional note
