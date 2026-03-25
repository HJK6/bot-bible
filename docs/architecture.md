# System Architecture

## Message Flow

### Telegram -> Agent
```
Telegram -> Lambda (webhook.py) -> SQS (OrchestratorInbox)
                                        |
                        Orchestrator._poll_sqs()
                                |
                    _route_message(text)  [AI + keyword matching]
                                |
                    _start_agent() or _send_to_agent()
                                |
                    _create_agent_tmux() -> tmux new-session
                                |
                    claude --dangerously-skip-permissions
                                |
                    _send_prompt_and_monitor() -> parse output -> Telegram reply
```

### SMS -> Handler
```
Twilio -> Lambda (sms_webhook.py) -> SQS -> Orchestrator
                                            |
                        sms_handler.handle_incoming()
                                |
                    Resolve contact + scope (ARCHON/EXPENSE/CHAT)
                                |
                    Claude tmux agent processes message
                                |
                    _send_sms(reply) via Twilio
```

### Gmail -> Handler
```
Gmail -> Lambda (gmail_webhook.py) -> SQS -> Orchestrator
                                              |
                        gmail_handler.handle_incoming()
                                |
                    Process email + route to agent
```

### Bot-to-Bot Communication
```
Friend Bot -> Lambda (bot_webhook.py, HMAC-signed) -> SQS -> Orchestrator
                                                            |
                                        bot_handler.handle_incoming()
                                                |
                                    AI session classification
                                                |
                                    Spawn ephemeral agent for reply
                                                |
                                    bot_handler.send_message() -> HMAC POST
```

### Task Worker
```
Producer (scraper/Lambda/orchestrator) -> SQS (BotRequests)
                                            |
                                    worker.poll_queue()
                                            |
                                    git pull -> import tasks.{name} -> run(data)
                                            |
                            Success: delete message
                            Failure: spawn Claude fix agent -> re-queue
                            2nd failure: -> DLQ
```

## Agent Lifecycle (tmux)

```
1. Orchestrator._start_agent(goal)
   -> Generate session name: agent-{SHA256(goal)[:8]}
   -> Derive agent_id: SHA256("claude-code::tmux-{session_name}")[:36]
   -> Register in AgentTracker (DynamoDB) directly
   -> _create_agent_tmux() -> tmux new-session with ORCHESTRATOR_MANAGED=1
   -> claude --dangerously-skip-permissions (or --resume {session_id})

2. Claude Code starts, detects $TMUX
   -> on_prompt.py hook fires
   -> shared.ensure_registered() updates heartbeat
   -> Agent ID matches via deterministic hash

3. During execution:
   -> on_tool.py logs each tool use
   -> tmux_watcher.py delivers queued commands via send-keys
   -> Heartbeat thread updates last_heartbeat every 30s
   -> Orchestrator monitors output via _send_prompt_and_monitor()

4. Completion:
   -> on_stop.py marks status=completed
   -> on_session_closed.py (tmux hook) marks hidden=True
   -> TTL cleans up after 7 days

5. Trash/Restore:
   -> Stop agent: moves to trash (tmux session kept alive for 48h)
   -> Restore: re-registers in DynamoDB, reattaches tmux session
```

## Summoning Room (Command Center)

The Summoning Room is an Electron app that provides a visual interface for managing tmux agent sessions. It does NOT replace tmux -- it wraps it.

```
Summoning Room (Electron)
    |
    +--> PtyManager (node-pty)
    |       Attaches to tmux sessions via: tmux attach-session -t {name}
    |       4 concurrent PTY slots
    |       Renders via xterm.js in renderer process
    |
    +--> API Server (~/.tmux/cmdcenter/server.py, port 7777)
    |       Lists tmux sessions + enriches with DynamoDB agent metadata
    |       CRUD: trash, restore, rename agents
    |       iTerm2 integration via AppleScript (single + quad-view)
    |
    +--> Slot State Persistence (.slot-state.json)
            Remembers which sessions were in which slots across restarts
```

### iTerm2 Integration

The API server exposes iTerm2 AppleScript functions:
- `open_session_in_iterm(session_name)` -- opens a single tmux session in a new iTerm2 tab
- `open_quad_in_iterm(session_names)` -- opens 4 sessions in a 2x2 iTerm2 split layout

## DynamoDB Schema

### Agent Tables
| Table | PK | SK | TTL | Purpose |
|-------|----|----|-----|---------|
| AgentTracker | agent_id | -- | 7d | Active agent metadata + heartbeat |
| AgentLogs | agent_id | timestamp | 3d | Execution logs |
| AgentChat | agent_id | timestamp | 7d | Conversation messages |
| AgentCommands | command_id | -- | 1d | Queued commands for delivery |
| BotTracker | bot_id | -- | 7d | Long-running bot status |

### Communication Tables
| Table | PK | SK | Purpose |
|-------|----|----|---------|
| BotCommBots | bot_id | -- | Registered friend bots |
| BotCommSessions | bot_id | session_id | Bot conversation sessions |
| BotCommMessages | session_id | message_id | Individual messages |
| BotSmsContacts | phone | -- | SMS contact directory |
| BotSmsSessions | phone | session_id | SMS conversation sessions |
| BotSmsMessages | session_id | message_id | SMS messages |
| BotSmsExpenses | event_id | expense_id | Expense entries |

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
| dashGetMemory | memory.py | Query memory events |
| dashGetOutput | output.py | Get output content |
| dashGetStocks | stocks.py | Stock data endpoints |
| dashGetProjects | projects.py | Project tracking endpoints |

## Message Routing Intelligence

The orchestrator routes incoming messages to the right agent:

1. **Explicit prefix**: `a1b2c3d4 do this` -> exact agent_id match
2. **Bracket notation**: `[Agent Name] do this` -> name match
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
Same session always gets same ID -- enables recovery and continuity.

### Recipe-Based Scraping
1. First scrape: AI-guided (WebScraper with Claude deciding actions)
2. Save successful run as deterministic recipe (JSON)
3. Future scrapes: Replay recipe -> AI fallback only on failure
4. Recipes include fallback CSS selectors for resilience
