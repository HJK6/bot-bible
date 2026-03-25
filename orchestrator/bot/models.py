"""Data models for bot-to-bot communication. Uses DataclassBase from land-bot."""

import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

sys.path.insert(0, "/Users/YOUR_USERNAME/land-bot")
from modules.Models import DataclassBase


# ── Scopes ────────────────────────────────────────────────────────────

class BotScope:
    """Permission scopes for friend bots."""
    CHAT = "chat"              # General conversation
    DATA = "data"              # Can request/send data via S3
    KNOWLEDGE = "knowledge"    # Can query capabilities and knowledge


# ── Bot Registry ──────────────────────────────────────────────────────

@dataclass
class BotCommBot(DataclassBase):
    """BotCommBots table. PK: bot_id.
    Registry of known friend bots that can communicate with Bartimaeus."""

    bot_id: str = ""              # Unique identifier (e.g. "aria-bot")
    name: str = ""                # Display name
    webhook_url: str = ""         # Friend bot's inbound webhook URL
    api_key_hash: str = ""        # SHA-256 hash of the bot's API key
    capabilities: List[str] = field(default_factory=list)  # What the bot can do
    scopes: List[str] = field(default_factory=list)        # Permissions granted
    status: str = "active"        # active | suspended
    previous_api_key_hash: str = ""  # For key rotation grace period
    key_rotated_at: int = 0       # When current key was issued (epoch ms)
    key_grace_until: int = 0      # Previous key valid until (epoch ms)
    created_at: int = 0           # Epoch ms
    updated_at: int = 0           # Epoch ms


# ── Sessions ──────────────────────────────────────────────────────────

@dataclass
class BotCommSession(DataclassBase):
    """BotCommSessions table. PK: bot_id, SK: session_id.
    Groups related messages within a time window.
    After SESSION_GAP_HOURS of inactivity, a new session starts."""

    bot_id: str = ""              # Which bot
    session_id: str = ""          # ULID (time-sortable)
    started_at: int = 0           # Epoch ms
    last_message_at: int = 0      # Epoch ms
    message_count: int = 0
    summary: str = ""             # Compacted summary of older messages
    status: str = "active"        # active | compacted | closed


# ── Messages ──────────────────────────────────────────────────────────

@dataclass
class BotCommMessage(DataclassBase):
    """BotCommMessages table. PK: session_id, SK: message_id.
    Individual messages within a session."""

    session_id: str = ""
    message_id: str = ""          # ULID-style: "{timestamp_ms}_{uuid8}"
    bot_id: str = ""              # Which bot
    direction: str = ""           # "inbound" | "outbound"
    message_type: str = "chat"    # chat | data_request | data_response | capability_query | capability_response | ping
    body: str = ""                # Message text
    attachments: List[dict] = field(default_factory=list)  # [{url, type, name, size_bytes}]
    reply_to: str = ""            # Optional parent message_id
    created_at: int = 0           # Epoch ms
