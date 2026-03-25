"""Main SMS handler — processes incoming SMS, manages sessions, routes by scope, replies."""

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
from typing import Optional, Callable, Awaitable

from .models import SmsContact, SmsSession, SmsMessage, Scope
from .storage import SmsStorage
from .expenses import ExpenseTracker
from .altum_analytics import handle_altum_analytics

logger = logging.getLogger("orchestrator.sms")

# Add land-bot for SMS sending
sys.path.insert(0, "/Users/YOUR_USERNAME/land-bot")

CLAUDE_CMD = "/Users/YOUR_USERNAME/.local/bin/claude"
# Clean env to avoid nested Claude Code session detection
_CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

# Session gap: 4 hours of inactivity = new session
SESSION_GAP_MS = 4 * 60 * 60 * 1000

# Compact after this many messages in a session
COMPACT_THRESHOLD = 20
COMPACT_KEEP_RECENT = 5

# Bartimaeus Twilio number
TWILIO_NUMBER = "+16094733678"

# Archon phone (Vamshi)
ARCHON_PHONE = "+18179078815"


def _ulid() -> str:
    import uuid
    return f"{int(time.time()*1000):013d}_{uuid.uuid4().hex[:8]}"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _send_sms(to_number: str, body: str) -> bool:
    """Send SMS via Twilio (land-bot HttpsSms)."""
    try:
        from modules.HttpsSms import send_sms
        result = send_sms(to_number, body, from_number=TWILIO_NUMBER)
        logger.info(f"SMS sent to {to_number}: {body[:60]}...")
        return True
    except Exception as e:
        logger.error(f"Failed to send SMS to {to_number}: {e}")
        return False


def _call_claude(prompt: str, timeout: int = 60) -> Optional[str]:
    """Call claude -p as a subprocess (no tmux needed)."""
    try:
        result = subprocess.run(
            [CLAUDE_CMD, "-p", "--model", "haiku"],
            input=prompt, capture_output=True, text=True,
            timeout=timeout, env=_CLEAN_ENV,
        )
        output = result.stdout.strip()
        return output if output else None
    except subprocess.TimeoutExpired:
        logger.error("Claude call timed out")
        return None
    except Exception as e:
        logger.error(f"Claude call failed: {e}")
        return None


async def _async_claude(prompt: str, timeout: int = 30) -> Optional[str]:
    """Non-blocking claude -p call via thread executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _call_claude, prompt, timeout)


class SmsHandler:
    """Processes incoming SMS messages with session management, scopes, and AI replies."""

    def __init__(self, notify_fn: Optional[Callable] = None):
        """
        Args:
            notify_fn: async callable(message, sender="SMS") to push updates to mobile app
        """
        self.storage = SmsStorage()
        self.expenses = ExpenseTracker(self.storage)
        self._notify_fn = notify_fn

    async def handle_incoming(self, from_phone: str, body: str, message_sid: str = "", to_phone: str = ""):
        """Main entry point for incoming SMS messages.
        Called by orchestrator when SQS delivers an SMS.
        """
        body = body.strip()
        if not body:
            return

        logger.info(f"SMS from {from_phone}: {body[:80]}")

        # 1. Look up contact
        contact = self.storage.get_contact(from_phone)

        # 2. No contact or no scopes → silent (log + notify archon)
        if not contact or not contact.scopes:
            name = contact.name if contact else from_phone
            await self._notify(f"SMS from unknown/unscoped {name} ({from_phone}): {body}")
            logger.info(f"No scopes for {from_phone}, ignoring")
            return

        # 3. Determine session (new or existing)
        session = self._resolve_session(contact)

        # 4. Dedup check — SQS standard queues can deliver duplicates
        if message_sid and self.storage.check_message_sid_exists(session.session_id, message_sid):
            logger.info(f"Duplicate message_sid {message_sid}, skipping")
            return

        # 5. Store inbound message
        msg = SmsMessage(
            session_id=session.session_id,
            message_id=_ulid(),
            phone=from_phone,
            direction="inbound",
            body=body,
            message_sid=message_sid,
            created_at=_now_ms(),
        )
        self.storage.put_message(msg)
        self.storage.update_session_activity(session.phone, session.session_id)

        # 6. Notify archon (always, for visibility)
        await self._notify(f"SMS from {contact.name} ({from_phone}): {body}", sender="SMS")

        # 7. Process based on scopes
        reply = await self._process_message(contact, session, body)

        # 8. Send reply if generated — only store if delivery succeeds
        if reply:
            sent = _send_sms(from_phone, reply)
            if sent:
                out_msg = SmsMessage(
                    session_id=session.session_id,
                    message_id=_ulid(),
                    phone=TWILIO_NUMBER,
                    direction="outbound",
                    body=reply,
                    created_at=_now_ms(),
                )
                self.storage.put_message(out_msg)
                self.storage.update_session_activity(session.phone, session.session_id)

        # 9. Check if compaction needed
        session_fresh = self.storage.get_session(session.phone, session.session_id)
        if session_fresh and session_fresh.message_count > COMPACT_THRESHOLD:
            await self._compact_session(session)

    def _resolve_session(self, contact: SmsContact) -> SmsSession:
        """Get or create a session for this contact."""
        active = self.storage.get_active_session(contact.phone)

        if active:
            age = _now_ms() - active.last_message_at
            if age < SESSION_GAP_MS:
                return active
            # Too old — close it and start new
            self.storage.close_session(active.phone, active.session_id)

        # Create new session
        session = SmsSession(
            phone=contact.phone,
            session_id=_ulid(),
            started_at=_now_ms(),
            last_message_at=_now_ms(),
            message_count=0,
            status="active",
        )
        self.storage.put_session(session)
        logger.info(f"New session for {contact.name} ({contact.phone}): {session.session_id}")
        return session

    async def _process_message(self, contact: SmsContact, session: SmsSession, body: str) -> Optional[str]:
        """Route message processing based on contact scopes. Returns reply text or None."""

        # Archon gets full AI processing
        if Scope.ARCHON in contact.scopes:
            return await self._handle_archon(contact, session, body)

        # Expense tracker scope
        if Scope.EXPENSE_TRACKER in contact.scopes:
            return await self._handle_expense_tracker(contact, session, body)

        # Altum analytics scope
        if Scope.ALTUM_ANALYTICS in contact.scopes:
            return await self._handle_altum_analytics(contact, session, body)

        # Chat scope — basic conversational replies
        if Scope.CHAT in contact.scopes:
            return await self._handle_chat(contact, session, body)

        return None

    # ── Archon Scope ──────────────────────────────────────────────────

    async def _handle_archon(self, contact: SmsContact, session: SmsSession, body: str) -> Optional[str]:
        """Handle messages from archon (full access)."""
        body_lower = body.lower().strip()

        # Admin commands (pass original body to preserve case)
        if body.strip().startswith("/"):
            return self._handle_admin_command(body.strip(), contact)

        # Expense queries FIRST (before expense logging to avoid "balance $50" → expense)
        if any(w in body_lower for w in ["balance", "owe", "summary", "expenses", "settle", "totals"]):
            if contact.expense_events:
                event_id = contact.expense_events[0]
                return self.expenses.get_expense_summary(event_id)

        # Then check if it's an expense
        if contact.expense_events:
            expense_data = self.expenses.parse_expense_simple(body)
            if expense_data and expense_data["amount"] > 0:
                event_id = contact.expense_events[0]
                expense = self.expenses.log_expense(
                    event_id=event_id,
                    payer_phone=contact.phone,
                    payer_name=contact.name,
                    **expense_data,
                )
                total = self.expenses.get_total_spent(event_id)
                return f"Logged: ${expense.amount:.2f} for {expense.description}. Event total: ${total:.2f}"

        # General AI reply with full context
        return await self._ai_reply(contact, session, body, scope=Scope.ARCHON)

    def _handle_admin_command(self, body: str, contact: SmsContact) -> str:
        """Handle slash commands from archon."""
        parts = body.split()
        cmd = parts[0].lower()

        if cmd == "/contacts":
            contacts = self.storage.get_all_contacts()
            lines = ["Contacts:"]
            for c in contacts:
                scopes = ", ".join(c.scopes) if c.scopes else "none"
                lines.append(f"  {c.name}: {c.phone} [{scopes}]")
            return "\n".join(lines)

        elif cmd == "/addscope" and len(parts) >= 3:
            phone = parts[1]
            scope = parts[2].lower()
            target = self.storage.get_contact(phone)
            if target:
                if scope not in target.scopes:
                    target.scopes.append(scope)
                    self.storage.put_contact(target)
                return f"Added scope '{scope}' to {target.name}"
            return f"Contact {phone} not found"

        elif cmd == "/rmscope" and len(parts) >= 3:
            phone = parts[1]
            scope = parts[2].lower()
            target = self.storage.get_contact(phone)
            if target and scope in target.scopes:
                target.scopes.remove(scope)
                self.storage.put_contact(target)
                return f"Removed scope '{scope}' from {target.name}"
            return f"Contact {phone} not found or doesn't have scope"

        elif cmd == "/addcontact" and len(parts) >= 3:
            # /addcontact +1234567890 Name Here (preserve original case for name)
            phone = parts[1]
            name = " ".join(parts[2:])
            existing = self.storage.get_contact(phone)
            if existing:
                return f"Contact already exists: {existing.name}"
            new_contact = SmsContact(
                phone=phone,
                name=name,
                scopes=[],
                created_at=_now_ms(),
            )
            self.storage.put_contact(new_contact)
            return f"Added contact: {name} ({phone})"

        elif cmd == "/addevent" and len(parts) >= 3:
            phone = parts[1]
            event_id = parts[2]
            target = self.storage.get_contact(phone)
            if target:
                if event_id not in target.expense_events:
                    target.expense_events.append(event_id)
                    self.storage.put_contact(target)
                return f"Added {target.name} to event '{event_id}'"
            return f"Contact {phone} not found"

        elif cmd == "/expenses":
            event_id = parts[1] if len(parts) > 1 else "bachelor_party"
            return self.expenses.get_expense_summary(event_id)

        elif cmd == "/settle":
            event_id = parts[1] if len(parts) > 1 else "bachelor_party"
            balances = self.expenses.get_balances(event_id)
            settlements = self.expenses.calculate_settlements(balances)
            if not settlements:
                return "All settled up!"
            lines = ["Settlement plan:"]
            for debtor, creditor, amount in settlements:
                lines.append(f"  {debtor} -> {creditor}: ${amount:.2f}")
            return "\n".join(lines)

        elif cmd == "/help":
            return (
                "Commands:\n"
                "/contacts - list all contacts\n"
                "/addcontact +phone Name\n"
                "/addscope +phone scope\n"
                "/rmscope +phone scope\n"
                "/addevent +phone event_id\n"
                "/expenses [event_id]\n"
                "/settle [event_id]\n"
                "/help"
            )

        return f"Unknown command: {cmd}. Try /help"

    # ── Expense Tracker Scope ─────────────────────────────────────────

    async def _handle_expense_tracker(self, contact: SmsContact, session: SmsSession, body: str) -> Optional[str]:
        """Handle messages from expense_tracker scoped contacts.
        All parsing done by AI — handles expenses, clarifications, done signals, and edge cases.
        """
        if not contact.expense_events:
            return "You're not part of any expense events."

        event_id = contact.expense_events[0]

        # Build conversation context
        recent_messages = self.storage.get_recent_messages(session.session_id, limit=8)
        conversation_context = ""
        for msg in recent_messages[:-1]:
            role = contact.name if msg.direction == "inbound" else "YOUR_BOT_NAME"
            conversation_context += f"{role}: {msg.body}\n"

        # Get their current expense stats
        all_expenses = self.storage.get_event_expenses(event_id)
        their_count = sum(1 for e in all_expenses if e.payer_phone == contact.phone)
        their_total = sum(e.amount for e in all_expenses if e.payer_phone == contact.phone)

        participants = self.storage.get_contacts_for_event(event_id)
        participant_names = [c.name for c in participants]
        name_to_phone = {}
        for c in participants:
            name_to_phone[c.name.lower()] = c.phone
            first = c.name.split()[0].lower() if c.name else ""
            if first:
                name_to_phone[first] = c.phone

        prompt = f"""You are Bartimaeus, a bot collecting group expenses via SMS from a bachelor party trip to Big Sky, Montana (Wed Feb 26 - Tue Mar 3, 2026). The trip days: Wed=Feb 25, Thu=Feb 26, Fri=Feb 27, Sat=Feb 28, Sun=Mar 1, Mon=Mar 2, Tue=Mar 3.

You are talking to: {contact.name}
All participants: {', '.join(participant_names)}
{contact.name}'s logged expenses so far: {their_count} expense(s), ${their_total:.2f} total

Previous conversation:
{conversation_context}
{contact.name}: {body}

Analyze the LATEST message and respond with ONLY a JSON object (no markdown, no explanation):
{{
  "intent": "expense" | "done" | "query" | "clarification_answer" | "other",
  "expense": {{
    "description": "item description",
    "amount": 123.45,
    "date": "Thursday",
    "split_among": []
  }},
  "reply": "your SMS reply to send back"
}}

Rules:
- "intent" = "expense" if they're reporting an expense (has item + amount). Log it and ask "Any more expenses?"
- "intent" = "done" if they're saying they have no (more) expenses — e.g. "no", "nothing", "that's all", "I didn't pay for anything", "$0", "nope", etc.
- "intent" = "query" if they're asking about balances/totals/who owes what
- "intent" = "clarification_answer" if they're answering a follow-up question you asked (e.g. providing a missing date or amount)
- "intent" = "other" for anything else
- For "expense": fill in description, amount (number, no $), date (day name like "Thursday" is fine), split_among (list of names if not everyone, empty [] = split among all)
- For "done": reply should thank them. If they logged expenses, mention the count and total. If none, say no worries.
- For "query": reply with a brief summary of their expenses
- If expense is missing date or amount, set intent to "other" and ask for the missing info in your reply
- Keep replies SHORT (under 160 chars). Friendly but concise.
- If they mention multiple expenses in one message, extract just the first one and mention you'll get the rest after
- IMPORTANT: If they're joking around, trolling, or sending silly/rude messages, roast them back with humor. Be witty and playful — these are close friends at a bachelor party. Match their energy. Then steer back to expenses.
- Don't be overly formal or robotic. Talk like a friend in the group chat."""

        result = await _async_claude(prompt)
        if not result:
            return f"Sorry {contact.name}, I had trouble processing that. Try something like: Dinner $50 Thursday"

        # Parse AI response
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if not json_match:
            return f"Sorry {contact.name}, I had trouble processing that. Try something like: Dinner $50 Thursday"

        try:
            parsed = json.loads(json_match.group())
        except json.JSONDecodeError:
            return f"Sorry {contact.name}, I had trouble processing that. Try something like: Dinner $50 Thursday"

        intent = parsed.get("intent", "other")

        # Log expense if AI found one
        if intent in ("expense", "clarification_answer"):
            exp_data = parsed.get("expense", {})
            amount = float(exp_data.get("amount", 0))
            if amount > 0:
                split_phones = []
                for name in exp_data.get("split_among", []):
                    phone = name_to_phone.get(name.lower())
                    if phone:
                        split_phones.append(phone)

                self.expenses.log_expense(
                    event_id=event_id,
                    payer_phone=contact.phone,
                    payer_name=contact.name,
                    description=exp_data.get("description", ""),
                    amount=amount,
                    expense_date=exp_data.get("date", ""),
                    split_among=split_phones,
                )

        # Return AI's reply
        return parsed.get("reply", f"Sorry {contact.name}, I had trouble with that. Try: Dinner $50 Thursday")

    async def _parse_expense_async(self, body, contact, event_id, participants):
        """Non-blocking AI expense parsing."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.expenses.parse_expense_text,
            body, contact.phone, contact.name, event_id, participants,
        )

    # ── Altum Analytics Scope ─────────────────────────────────────────

    async def _handle_altum_analytics(self, contact: SmsContact, session: SmsSession, body: str) -> Optional[str]:
        """Handle messages from altum_analytics scoped contacts — CRM reporting."""
        # Build conversation context for multi-turn queries
        recent_messages = self.storage.get_recent_messages(session.session_id, limit=6)
        context_parts = []
        for msg in recent_messages[:-1]:
            role = contact.name if msg.direction == "inbound" else "YOUR_BOT_NAME"
            context_parts.append(f"{role}: {msg.body}")
        conversation_context = "\n".join(context_parts)

        # Look up contact's email from Agents table by name match
        contact_email = None
        try:
            from modules.Dynamo import Table
            from modules.Config import AGENTS_TABLE
            agents = Table(AGENTS_TABLE).scan()
            contact_name_lower = contact.name.lower()
            for agent in agents:
                agent_name = agent.get("name", "").lower()
                if contact_name_lower in agent_name or agent_name in contact_name_lower:
                    contact_email = agent.get("email", "")
                    break
        except Exception as e:
            logger.warning(f"Failed to look up agent email for {contact.name}: {e}")
        if not contact_email:
            contact_email = "sofianalire@gmail.com"  # fallback

        return await handle_altum_analytics(
            contact_name=contact.name,
            contact_email=contact_email,
            body=body,
            conversation_context=conversation_context,
        )

    # ── Chat Scope ────────────────────────────────────────────────────

    async def _handle_chat(self, contact: SmsContact, session: SmsSession, body: str) -> Optional[str]:
        """Handle messages from chat scoped contacts — simple AI conversation."""
        return await self._ai_reply(contact, session, body, scope=Scope.CHAT)

    # ── AI Reply ──────────────────────────────────────────────────────

    async def _ai_reply(self, contact: SmsContact, session: SmsSession, body: str, scope: str) -> Optional[str]:
        """Generate an AI reply using Ollama, with session context. Non-blocking."""
        # Build conversation context
        recent_messages = self.storage.get_recent_messages(session.session_id, limit=10)
        session_data = self.storage.get_session(session.phone, session.session_id)

        context_parts = []
        if session_data and session_data.summary:
            context_parts.append(f"Previous conversation summary: {session_data.summary}")

        for msg in recent_messages[:-1]:  # Exclude the message we're replying to (it was just stored)
            role = "User" if msg.direction == "inbound" else "YOUR_BOT_NAME"
            context_parts.append(f"{role}: {msg.body}")

        conversation = "\n".join(context_parts)

        scope_instructions = {
            Scope.ARCHON: "You have full access. You can help with anything the user asks.",
            Scope.CHAT: "You can have casual conversation. Keep it friendly and brief.",
        }

        prompt = f"""You are Bartimaeus, a helpful AI assistant communicating via SMS. Keep replies SHORT (under 160 chars when possible, max 320 chars). Be concise but friendly.

Contact: {contact.name}
Scope: {scope}
{scope_instructions.get(scope, '')}

{f"Conversation context:{chr(10)}{conversation}" if conversation else ""}

User message: {body}

Reply concisely:"""

        reply = await _async_claude(prompt)

        if not reply:
            return None

        # Clean up the reply
        reply = reply.strip('"').strip()
        if not reply:
            return None

        # Enforce max SMS length
        if len(reply) > 480:
            reply = reply[:477] + "..."

        return reply

    # ── Session Compaction ────────────────────────────────────────────

    async def _compact_session(self, session: SmsSession):
        """Compact older messages in a session into a summary. Non-blocking."""
        messages = self.storage.get_session_messages(session.session_id, limit=100)
        if len(messages) <= COMPACT_THRESHOLD:
            return

        # Keep the most recent messages, summarize the rest
        to_summarize = messages[:-COMPACT_KEEP_RECENT]

        # Build text to summarize
        summary_text = []
        for msg in to_summarize:
            role = "User" if msg.direction == "inbound" else "Bot"
            summary_text.append(f"{role}: {msg.body}")

        existing_session = self.storage.get_session(session.phone, session.session_id)
        existing_summary = existing_session.summary if existing_session else ""

        prompt = f"""Summarize this SMS conversation concisely (max 200 words). Capture key facts, decisions, and any expense amounts.

{f"Previous summary: {existing_summary}" if existing_summary else ""}

Messages to summarize:
{chr(10).join(summary_text)}

Summary:"""

        summary = await _async_claude(prompt)

        if summary:
            # Update session with summary (keep status as active)
            self.storage.update_session_summary(session.phone, session.session_id, summary)

            # Delete old messages
            message_ids = [msg.message_id for msg in to_summarize]
            self.storage.delete_messages(session.session_id, message_ids)

            logger.info(f"Compacted session {session.session_id}: {len(to_summarize)} messages -> summary")

    # ── Notification Helper ───────────────────────────────────────────

    async def _notify(self, message: str, sender: str = "SMS"):
        """Send notification to mobile app."""
        if self._notify_fn:
            try:
                await self._notify_fn(message, sender=sender)
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
