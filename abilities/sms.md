# SMS

Send and receive text messages via Twilio with session management, contact scopes, and expense tracking.

## Architecture

```
Inbound: Twilio → smsWebhook Lambda → OrchestratorInbox SQS → Orchestrator → SmsHandler
Outbound: SmsHandler → land-bot HttpsSms → Twilio REST API
Storage: DynamoDB (contacts, sessions, messages, expenses)
AI: Ollama (qwen2.5:14b) for conversation and expense parsing
```

## Location

| Component | Path |
|-----------|------|
| SMS Handler | `/Users/bartimaeus/agent-dashboard/orchestrator/sms/handler.py` |
| Models | `/Users/bartimaeus/agent-dashboard/orchestrator/sms/models.py` |
| Storage | `/Users/bartimaeus/agent-dashboard/orchestrator/sms/storage.py` |
| Expenses | `/Users/bartimaeus/agent-dashboard/orchestrator/sms/expenses.py` |
| Table Setup | `/Users/bartimaeus/agent-dashboard/orchestrator/sms/setup.py` |
| Twilio Send | `/Users/bartimaeus/land-bot/modules/HttpsSms.py` |
| Webhook Lambda | `/Users/bartimaeus/agent-dashboard/handlers/sms_webhook.py` |

## DynamoDB Tables

| Table | PK | SK | Purpose |
|-------|----|----|---------|
| `BartSmsContacts` | `phone` (E.164) | — | Contact registry with scopes |
| `BartSmsSessions` | `phone` | `session_id` (ULID) | Session tracking per contact |
| `BartSmsMessages` | `session_id` | `message_id` (ULID) | Individual messages |
| `BartSmsExpenses` | `event_id` | `expense_id` (ULID) | Expense records per event |

## Scopes

| Scope | Access |
|-------|--------|
| `archon` | Full access — admin commands, AI chat, expense tracking |
| `expense_tracker` | Log expenses, check balances, view summaries |
| `chat` | Casual AI conversation only |
| (none) | No reply — message logged, archon notified |

## Session Management

- Messages from the same contact are grouped into sessions
- **Session gap**: 4 hours of inactivity starts a new session
- **Compaction**: After 20 messages, older ones are summarized by AI and deleted
- Session summary carries forward for context continuity

## Sending SMS

```python
import sys
sys.path.insert(0, "/Users/bartimaeus/land-bot")
from modules.HttpsSms import send_sms

send_sms("+1XXXXXXXXXX", "Hello from Bartimaeus")
send_sms("+1XXXXXXXXXX", "Hello", from_number="+19725128295")
```

## Admin Commands (Archon via SMS)

| Command | Description |
|---------|-------------|
| `/contacts` | List all contacts with scopes |
| `/addcontact +phone Name` | Add new contact |
| `/addscope +phone scope` | Grant scope to contact |
| `/rmscope +phone scope` | Remove scope from contact |
| `/addevent +phone event_id` | Add contact to expense event |
| `/expenses [event_id]` | View expense summary |
| `/settle [event_id]` | View settlement plan |
| `/help` | List commands |

## Expense Tracking

Contacts with `expense_tracker` scope can text expenses:
- `nachos $15` — logs $15 for nachos, split among all event participants
- `I paid $50 for dinner` — same
- `Split lift tickets with Rahul $340` — AI parses split participants
- `balance` / `settle` — view balances and settlement plan

Archon can also send itemized receipts (AI-parsed).

## Config

- `TWILIO_ACCOUNT_SID` = `YOUR_TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN` = configured in Config.py
- `TWILIO_SMS_NUMBER` = `+1XXXXXXXXXX` (Bartimaeus number)
- Archon phone: `+1XXXXXXXXXX`

## Notes

- Phone numbers must be E.164 format: `+1` followed by 10 digits
- SMS body limit: 160 chars per segment, auto-concatenated for longer
- AI replies kept under 320 chars for SMS friendliness
- Unknown/unscoped contacts get no reply but archon is notified
- Ollama must be running for AI features (expense parsing, chat replies)
- Integrated into orchestrator — SMS handled automatically when orchestrator runs
