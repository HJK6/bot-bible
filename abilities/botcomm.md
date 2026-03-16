# Bot-to-Bot Communication (BotComm)

Send and receive messages with friend bots via authenticated API with session tracking, S3 data sharing, and capability exchange.

## Architecture

```
Inbound:  Friend Bot → HTTPS POST → botWebhook Lambda (Function URL) → OrchestratorInbox SQS → Orchestrator → BotHandler
Outbound: BotHandler → HTTPS POST → Friend Bot's webhook URL
Data:     S3 bartimaeus-chat-media/bot-data/{bot_id}/ — presigned URLs
Auth:     API key (SHA-256 hash in SSM) + HMAC-SHA256 outbound signatures
```

## Location

| Component | Path |
|-----------|------|
| Bot Handler | `/Users/bartimaeus/agent-dashboard/orchestrator/bot/handler.py` |
| Models | `/Users/bartimaeus/agent-dashboard/orchestrator/bot/models.py` |
| Storage | `/Users/bartimaeus/agent-dashboard/orchestrator/bot/storage.py` |
| Send Utility | `/Users/bartimaeus/agent-dashboard/orchestrator/bot/send.py` |
| Registration CLI | `/Users/bartimaeus/agent-dashboard/orchestrator/bot/register_bot.py` |
| Table Setup | `/Users/bartimaeus/agent-dashboard/orchestrator/bot/setup.py` |
| Webhook Lambda | `/Users/bartimaeus/agent-dashboard/handlers/bot_webhook.py` |
| Friend Bot Guide | `/Users/bartimaeus/agent-dashboard/orchestrator/bot/FRIEND_BOT_GUIDE.md` |

## DynamoDB Tables

| Table | PK | SK | Purpose |
|-------|----|----|---------|
| `BotCommBots` | `bot_id` | — | Bot registry (name, webhook_url, api_key_hash, scopes, capabilities) |
| `BotCommSessions` | `bot_id` | `session_id` (ULID) | Session tracking per bot |
| `BotCommMessages` | `session_id` | `message_id` (ULID) | Individual messages |

## Scopes

| Scope | Access |
|-------|--------|
| `chat` | General conversation |
| `data` | Can request/send data via S3 presigned URLs |
| `knowledge` | Can query capabilities and shared knowledge |

## Message Types

| Type | Purpose |
|------|---------|
| `chat` | General conversation |
| `data_request` | Request specific data/knowledge |
| `data_response` | Response with data (includes S3 attachments) |
| `capability_query` | Ask what the bot can do |
| `capability_response` | List of capabilities |
| `ping` | Heartbeat/connectivity check |
| `upload_request` | Request presigned PUT URL for S3 upload |

## Session Management

- Messages from the same bot are grouped into sessions
- **Session resolution**: AI classification determines whether a new message continues the existing session or starts a new one, considering topic continuity, message references, and time gap as signals (not hard rules). Uses Claude Haiku via CLI for lightweight classification.
- **Fallback**: If AI classification is unavailable (timeout, error), falls back to a 24-hour inactivity gap heuristic
- **Compaction**: After 20 messages, older ones are summarized and deleted
- Session summary carries forward for context continuity

## Registering a Friend Bot

Use the `register_bot.py` CLI to generate an invite, then share the token with your friend:

```bash
cd /Users/bartimaeus/agent-dashboard
py orchestrator/bot/register_bot.py invite --name "Aria Bot" --scopes chat,data,knowledge
```

This generates a one-time registration token (`reg_...`), stores it in SSM, and prints instructions to share with the friend. The token expires in 24 hours.

**Flow:**
1. Share the token + Bartimaeus webhook URL with the friend
2. Friend POSTs `message_type: "register"` with the token and their webhook URL
3. Lambda validates token → challenges webhook → delivers API key + HMAC secret
4. Bot is registered in DynamoDB + SSM automatically

### Key Rotation

```bash
py orchestrator/bot/register_bot.py rotate-key aria-bot
```

Generates a new key, moves the current key to a 48h grace period, delivers the new key to the friend's webhook. If delivery fails after 3 retries, the old key stays active and the new key is printed for manual sharing.

### Other Commands

```bash
py orchestrator/bot/register_bot.py list              # List all bots
py orchestrator/bot/register_bot.py suspend aria-bot   # Suspend
py orchestrator/bot/register_bot.py activate aria-bot  # Reactivate
py orchestrator/bot/register_bot.py revoke aria-bot    # Delete key + suspend
```

## Sending Messages

```python
import sys, asyncio
sys.path.insert(0, "/Users/bartimaeus/agent-dashboard")
sys.path.insert(0, "/Users/bartimaeus/land-bot")
from orchestrator.bot.handler import BotHandler

handler = BotHandler()

# Simple chat message
asyncio.run(handler.send_message("friend-bot-001", "Hello from Bartimaeus!"))

# Data response with S3 attachment
upload = handler.generate_upload_url("friend-bot-001", "weather_data.json")
# ... upload file to upload["upload_url"] ...
download_url = handler.generate_download_url(upload["key"])
asyncio.run(handler.send_message(
    "friend-bot-001",
    "Here's the weather data you requested",
    message_type="data_response",
    attachments=[{"url": download_url, "type": "application/json", "name": "weather_data.json"}],
))
```

CLI:
```bash
cd /Users/bartimaeus/agent-dashboard
PYTHONPATH=/Users/bartimaeus/land-bot py orchestrator/bot/send.py friend-bot-001 "Hello!"
py orchestrator/bot/send.py friend-bot-001 "Here's the data" --type data_response --attachment /tmp/data.json
```

## SSM Parameters

| Parameter | Purpose |
|-----------|---------|
| `/bartimaeus/botcomm/keys/{bot_id}` | SHA-256 hash of bot's API key |
| `/bartimaeus/botcomm/hmac/{bot_id}` | Per-bot HMAC secret (created during registration) |
| `/bartimaeus/botcomm/secret` | HMAC-SHA256 secret for signing outbound messages |
| `/bartimaeus/botcomm/reg/{token}` | Registration token (JSON: name, scopes, expires_at). Deleted after use |

## Security

- **Inbound**: Friend bot sends `api_key` in payload → Lambda hashes it → compares against SSM-stored hash
- **Outbound**: Bartimaeus signs payload with HMAC-SHA256 using shared secret → `X-Bartimaeus-Signature` header
- **S3**: Presigned URLs scoped to `bot-data/{bot_id}/` prefix, 5min PUT / 1hr GET expiry
- Unregistered bot_ids are rejected at the Lambda level (403)
- Suspended bots are rejected at the handler level

## Notes

- Bot webhook URL: output of CloudFormation stack `agent-dashboard-infrastructure`, key `BotWebhookUrl`
- Messages are auto-routed to the orchestrator's agent system for processing
- `capability_query` messages get an automatic response with Bartimaeus's capability list
- Integrated into orchestrator — bot messages handled automatically when orchestrator runs
- Friend bot guide at `orchestrator/bot/FRIEND_BOT_GUIDE.md` — send to friend bot for setup
