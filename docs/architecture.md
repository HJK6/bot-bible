# System Architecture

## Message Flow

### Telegram → Agent
```
Telegram → Lambda (webhook.py) → SQS (OrchestratorInbox)
                                        ↓
                        Orchestrator._poll_sqs()
                                ↓
                    _route_message(text)  [AI + keyword matching]
                                ↓
                    _start_agent() or _send_to_agent()
                                ↓
                    subprocess: claude -p --output-format stream-json
                                ↓
                    Parse stream → send reply to Telegram
```

### SMS → Handler
```
Twilio → Lambda (sms_webhook.py) → SQS → Orchestrator
                                            ↓
                        sms_handler.handle_incoming()
                                ↓
                    Resolve contact + scope (ARCHON/EXPENSE/CHAT)
                                ↓
                    Claude tmux agent processes message
                                ↓
                    _send_sms(reply) via Twilio
```

### Bot-to-Bot Communication
```
Friend Bot → Lambda (bot_webhook.py, HMAC-signed) → SQS → Orchestrator
                                                            ↓
                                        bot_handler.handle_incoming()
                                                ↓
                                    AI session classification
                                                ↓
                                    Spawn ephemeral agent for reply
                                                ↓
                                    bot_handler.send_message() → HMAC POST
```

### Task Worker
```
Producer (scraper/Lambda/orchestrator) → SQS (BartimaeusRequests)
                                            ↓
                                    worker.poll_queue()
                                            ↓
                                    git pull → import tasks.{name} → run(data)
                                            ↓
                            Success: delete message
                            Failure: spawn Claude fix agent → re-queue
                            2nd failure: → DLQ
```

## Agent Lifecycle (tmux)

```
1. Orchestrator._start_agent(goal)
   → Create tmux session: agent-{hash[:8]}
   → Register in AgentTracker (DynamoDB)
   → tmux send-keys: "claude -p --dangerously-skip-permissions ..."

2. Claude Code starts, detects $TMUX
   → on_prompt.py hook fires
   → shared.ensure_registered() updates heartbeat
   → Agent ID = SHA256("claude-code::tmux-{session_name}")[:36]

3. During execution:
   → on_tool.py logs each tool use
   → tmux_watcher.py delivers queued commands via send-keys
   → Heartbeat thread updates last_heartbeat every 30s

4. Completion:
   → on_stop.py marks status=completed
   → on_session_closed.py (tmux hook) marks hidden=True
   → TTL cleans up after 7 days
```

## DynamoDB Schema

### Agent Tables
| Table | PK | SK | TTL | Purpose |
|-------|----|----|-----|---------|
| AgentTracker | agent_id | — | 7d | Active agent metadata + heartbeat |
| AgentLogs | agent_id | timestamp | 3d | Execution logs |
| AgentChat | agent_id | timestamp | 7d | Conversation messages |
| AgentCommands | command_id | — | 1d | Queued commands for delivery |
| BotTracker | bot_id | — | 7d | Long-running bot status |

### Communication Tables
| Table | PK | SK | Purpose |
|-------|----|----|---------|
| BotCommBots | bot_id | — | Registered friend bots |
| BotCommSessions | bot_id | session_id | Bot conversation sessions |
| BotCommMessages | session_id | message_id | Individual messages |
| BartSmsContacts | phone | — | SMS contact directory |
| BartSmsSessions | phone | session_id | SMS conversation sessions |
| BartSmsMessages | session_id | message_id | SMS messages |
| BartSmsExpenses | event_id | expense_id | Expense entries |

## API Endpoints

All endpoints go through API Gateway with Cognito authorization:

| Endpoint | Handler | Purpose |
|----------|---------|---------|
| dashGetAgents | tracker.py | List all agents (filters hidden) |
| dashGetBots | tracker.py | List bots (auto-reaps stale) |
| dashGetAgentLogs | tracker.py | Query logs for agent |
| dashGetAgentChat | tracker.py | Query chat + presign S3 URLs |
| dashCreateCommand | tracker.py | Send command to agent |
| dashUpdateAgent | tracker.py | Update agent metadata |
| dashGetUploadUrl | media.py | Get S3 presigned upload URL |
| dashRegisterPushToken | tracker.py | Register Expo push token |

## Message Routing Intelligence

The orchestrator routes incoming messages to the right agent:

1. **Explicit prefix**: `a1b2c3d4 do this` → exact agent_id match
2. **Bracket notation**: `[Agent Name] do this` → name match
3. **AI classification**: Claude Haiku decides if message continues existing agent or needs new one
4. **Keyword scoring**: Overlap between message words and agent's goal/history (fallback)

## Key Patterns

### DataclassBase
All data models inherit from `DataclassBase` which provides `from_dict()`, `to_dict()`, `from_json()`, `to_json()`. Never use plain `@dataclass`.

### AgentTracker Context Manager
```python
with AgentTracker("bot-type", "Bot Name") as tracker:
    tracker.update_task("Processing")
    tracker.update_metrics(items=10)
    tracker.log("Done")
# Auto-completes or marks failed on exception
```

### Deterministic Agent IDs
```python
agent_id = hashlib.sha256(f"claude-code::tmux-{session_name}".encode()).hexdigest()[:36]
```
Same session always gets same ID — enables recovery and continuity.

### Recipe-Based Scraping
1. First scrape: AI-guided (WebScraper with Claude deciding actions)
2. Save successful run as deterministic recipe (JSON)
3. Future scrapes: Replay recipe → AI fallback only on failure
4. Recipes include fallback CSS selectors for resilience
