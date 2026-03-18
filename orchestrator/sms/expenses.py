"""Expense tracking and splitting for SMS system."""

import logging
import os
import subprocess
import tempfile
import time
import re
import json
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .models import SmsExpense, SmsExpenseItem, SmsContact, Scope
from .storage import SmsStorage

logger = logging.getLogger("orchestrator.sms.expenses")

CLAUDE_CMD = "/Users/YOUR_USERNAME/.local/bin/claude"
TMUX_CMD = "/opt/homebrew/bin/tmux"


def _ulid() -> str:
    """Generate a simple time-sortable unique ID."""
    import uuid
    return f"{int(time.time()*1000):013d}_{uuid.uuid4().hex[:8]}"


class ExpenseTracker:
    """Manages expense tracking for events like bachelor party."""

    def __init__(self, storage: SmsStorage):
        self.storage = storage

    def log_expense(
        self,
        event_id: str,
        payer_phone: str,
        payer_name: str,
        description: str,
        amount: float,
        items: Optional[List[SmsExpenseItem]] = None,
        split_among: Optional[List[str]] = None,
        split_type: str = "equal",
        expense_date: str = "",
        note: str = "",
    ) -> SmsExpense:
        """Log a new expense."""
        expense = SmsExpense(
            event_id=event_id,
            expense_id=_ulid(),
            payer_phone=payer_phone,
            payer_name=payer_name,
            description=description,
            amount=amount,
            expense_date=expense_date,
            items=items or [],
            split_among=split_among or [],
            split_type=split_type,
            created_at=int(time.time() * 1000),
            note=note,
        )
        self.storage.put_expense(expense)
        logger.info(f"Logged expense: {payer_name} paid ${amount:.2f} for '{description}' in {event_id}")
        return expense

    def get_balances(self, event_id: str) -> Dict[str, float]:
        """Calculate net balances for all participants in an event.
        Positive = owed money (paid more than share), Negative = owes money.
        """
        expenses = self.storage.get_event_expenses(event_id)
        participants = self.storage.get_contacts_for_event(event_id)
        all_phones = [c.phone for c in participants]
        phone_to_name = {c.phone: c.name for c in participants}

        if not all_phones:
            return {}

        # Track how much each person paid and how much they owe
        paid = defaultdict(float)     # phone -> total paid
        owes = defaultdict(float)     # phone -> total owed

        for exp in expenses:
            paid[exp.payer_phone] += exp.amount

            if exp.split_type == "itemized" and exp.items:
                # Itemized: each item assigned to a person
                assigned_total = 0.0
                for item in exp.items:
                    if item.for_person:
                        owes[item.for_person] += item.amount
                        assigned_total += item.amount
                # Any remainder split equally among split_among or all
                remainder = exp.amount - assigned_total
                if remainder > 0:
                    split_group = exp.split_among if exp.split_among else all_phones
                    per_person = remainder / len(split_group)
                    for phone in split_group:
                        owes[phone] += per_person
            else:
                # Equal split
                split_group = exp.split_among if exp.split_among else all_phones
                per_person = exp.amount / len(split_group)
                for phone in split_group:
                    owes[phone] += per_person

        # Net balance: positive means they are owed, negative means they owe
        balances = {}
        for phone in all_phones:
            net = paid.get(phone, 0) - owes.get(phone, 0)
            name = phone_to_name.get(phone, phone)
            balances[name] = round(net, 2)

        return balances

    def get_total_spent(self, event_id: str) -> float:
        """Get total amount spent for an event."""
        expenses = self.storage.get_event_expenses(event_id)
        return sum(exp.amount for exp in expenses)

    def get_expense_summary(self, event_id: str) -> str:
        """Generate a human-readable expense summary."""
        expenses = self.storage.get_event_expenses(event_id)
        if not expenses:
            return "No expenses logged yet."

        total = sum(exp.amount for exp in expenses)
        balances = self.get_balances(event_id)

        lines = [f"Total: ${total:.2f} across {len(expenses)} expense(s)"]
        lines.append("")

        # Recent expenses (last 5)
        recent = sorted(expenses, key=lambda e: e.created_at, reverse=True)[:5]
        lines.append("Recent:")
        for exp in recent:
            lines.append(f"  {exp.payer_name}: ${exp.amount:.2f} - {exp.description}")

        lines.append("")
        lines.append("Balances:")
        for name, bal in sorted(balances.items(), key=lambda x: x[1], reverse=True):
            if bal >= 0:
                lines.append(f"  {name}: +${bal:.2f}")
            else:
                lines.append(f"  {name}: -${abs(bal):.2f}")

        # Settlement suggestions
        settlements = self.calculate_settlements(balances)
        if settlements:
            lines.append("")
            lines.append("To settle:")
            for debtor, creditor, amount in settlements:
                lines.append(f"  {debtor} -> {creditor}: ${amount:.2f}")

        return "\n".join(lines)

    def get_person_summary(self, event_id: str, phone: str) -> str:
        """Get expense summary for a specific person."""
        expenses = self.storage.get_event_expenses(event_id)
        participants = self.storage.get_contacts_for_event(event_id)
        phone_to_name = {c.phone: c.name for c in participants}
        name = phone_to_name.get(phone, phone)

        their_expenses = [e for e in expenses if e.payer_phone == phone]
        total_paid = sum(e.amount for e in their_expenses)

        balances = self.get_balances(event_id)
        balance = balances.get(name, 0)

        lines = [f"{name}'s expenses:"]
        lines.append(f"  Total paid: ${total_paid:.2f}")
        if balance >= 0:
            lines.append(f"  Owed back: ${balance:.2f}")
        else:
            lines.append(f"  Owes: ${abs(balance):.2f}")

        if their_expenses:
            lines.append("  Items:")
            for exp in their_expenses:
                lines.append(f"    ${exp.amount:.2f} - {exp.description}")

        return "\n".join(lines)

    def calculate_settlements(self, balances: Dict[str, float]) -> List[Tuple[str, str, float]]:
        """Calculate minimum transactions to settle all debts."""
        debtors = []  # (name, amount_owed)
        creditors = []  # (name, amount_owed_to_them)

        for name, bal in balances.items():
            if bal < -0.01:
                debtors.append([name, abs(bal)])
            elif bal > 0.01:
                creditors.append([name, bal])

        # Sort for greedy matching
        debtors.sort(key=lambda x: x[1], reverse=True)
        creditors.sort(key=lambda x: x[1], reverse=True)

        settlements = []
        i, j = 0, 0
        while i < len(debtors) and j < len(creditors):
            amount = min(debtors[i][1], creditors[j][1])
            if amount > 0.01:
                settlements.append((debtors[i][0], creditors[j][0], round(amount, 2)))
            debtors[i][1] -= amount
            creditors[j][1] -= amount
            if debtors[i][1] < 0.01:
                i += 1
            if creditors[j][1] < 0.01:
                j += 1

        return settlements

    def parse_expense_text(self, text: str, sender_phone: str, sender_name: str, event_id: str, participants: List[SmsContact]) -> Optional[Dict]:
        """Use AI to parse an expense from natural language text.
        Returns dict with: description, amount, split_among, items, or None if not an expense.
        """
        phone_to_name = {c.phone: c.name for c in participants}
        name_to_phone = {c.name.lower(): c.phone for c in participants}
        # Also map first names
        for c in participants:
            first = c.name.split()[0].lower() if c.name else ""
            if first and first not in name_to_phone:
                name_to_phone[first] = c.phone

        participant_names = [c.name for c in participants]

        prompt = f"""Parse this text message as an expense report. The sender is {sender_name}.
Event participants: {', '.join(participant_names)}

Message: "{text}"

If this is an expense, respond with ONLY a JSON object (no markdown, no explanation):
{{
  "is_expense": true,
  "description": "brief description",
  "amount": 12.50,
  "payer": "{sender_name}",
  "split_among": ["name1", "name2"],
  "items": [{{"description": "item", "amount": 5.00, "for_person": "name"}}],
  "split_type": "equal"
}}

Rules:
- "split_among" defaults to ALL participants if not specified
- "items" is for itemized receipts, empty list [] if not itemized
- "split_type" is "equal" unless items are assigned to specific people (then "itemized")
- Amount should be a number (no $)
- If the message says "for me and X", split_among should be [sender, X]
- If the message is NOT an expense, respond: {{"is_expense": false}}"""

        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, prefix='claude_exp_') as pf:
                pf.write(prompt)
                prompt_file = pf.name

            out_file = prompt_file + '.out'
            session_name = f"claude_exp_{os.getpid()}_{int(time.time()*1000)}"

            cmd = f'cat "{prompt_file}" | {CLAUDE_CMD} -p --model haiku > "{out_file}" 2>&1; {TMUX_CMD} wait-for -S {session_name}'
            subprocess.run([TMUX_CMD, "new-session", "-d", "-s", session_name, cmd], timeout=5)
            subprocess.run([TMUX_CMD, "wait-for", session_name], timeout=30)

            response_text = ""
            if os.path.exists(out_file):
                with open(out_file) as f:
                    response_text = f.read().strip()
                os.unlink(out_file)
            os.unlink(prompt_file)
            if not response_text:
                return None

            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                return None

            result = json.loads(json_match.group())
            if not result.get("is_expense"):
                return None

            # Resolve names to phone numbers
            split_phones = []
            for name in result.get("split_among", []):
                phone = name_to_phone.get(name.lower())
                if phone:
                    split_phones.append(phone)

            items = []
            for item_data in result.get("items", []):
                for_person_phone = ""
                if item_data.get("for_person"):
                    for_person_phone = name_to_phone.get(item_data["for_person"].lower(), "")
                items.append(SmsExpenseItem(
                    description=item_data.get("description", ""),
                    amount=float(item_data.get("amount", 0)),
                    for_person=for_person_phone,
                ))

            return {
                "description": result.get("description", ""),
                "amount": float(result.get("amount", 0)),
                "split_among": split_phones,
                "items": items,
                "split_type": result.get("split_type", "equal"),
            }

        except Exception as e:
            logger.error(f"Failed to parse expense text: {e}")
            return None

    def parse_expense_simple(self, text: str) -> Optional[Dict]:
        """Quick regex-based expense parsing for simple messages like 'nachos $15' or 'I paid $50 for dinner'."""
        text_lower = text.lower().strip()

        # Pattern 1: "$amount for description" — e.g. "$50 for dinner"
        match = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)\s+(?:for\s+)?(.+)", text_lower)
        if match:
            amount_str, desc = match.groups()
            desc = desc.strip().rstrip(".-,")
            try:
                amount = float(amount_str)
                if amount > 0 and desc:
                    return {"description": desc, "amount": amount, "split_among": [], "items": [], "split_type": "equal"}
            except ValueError:
                pass

        # Pattern 2: "I paid/got/bought description $amount" — e.g. "I got nachos $15"
        match = re.search(r"(?:i\s+(?:got|paid|bought|spent|had)\s+)(.+?)\s*\$\s*(\d+(?:\.\d{1,2})?)", text_lower)
        if match:
            desc, amount_str = match.groups()
            desc = desc.strip().rstrip(".-,")
            try:
                amount = float(amount_str)
                if amount > 0 and desc:
                    return {"description": desc, "amount": amount, "split_among": [], "items": [], "split_type": "equal"}
            except ValueError:
                pass

        # Pattern 3: "description $amount" — e.g. "nachos $15"
        match = re.search(r"^([^$]+?)\s*\$\s*(\d+(?:\.\d{1,2})?)$", text_lower)
        if match:
            desc, amount_str = match.groups()
            desc = desc.strip().rstrip(".-,")
            try:
                amount = float(amount_str)
                if amount > 0 and desc:
                    return {"description": desc, "amount": amount, "split_among": [], "items": [], "split_type": "equal"}
            except ValueError:
                pass

        return None
