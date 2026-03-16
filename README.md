# Bot Bible

Everything a new Claude Code instance needs to stand up the Bartimaeus agent infrastructure from scratch.

## Architecture Overview

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│  Telegram    │───▶│  Lambda      │───▶│  SQS             │
│  (User)      │    │  Webhook     │    │  OrchestratorInbox│
└─────────────┘    └──────────────┘    └────────┬──────────┘
                                                │
┌─────────────┐    ┌──────────────┐    ┌────────▼──────────┐
│  Mobile App  │───▶│  API Gateway │    │   Orchestrator    │
│  (Expo)      │    │  + Cognito   │    │   (Local Daemon)  │
└─────────────┘    └──────────────┘    └────────┬──────────┘
                                                │
                          ┌─────────────────────┼─────────────────────┐
                          │                     │                     │
                   ┌──────▼──────┐    ┌────────▼────────┐   ┌───────▼──────┐
                   │ Claude Code  │    │  Task Worker    │   │  SMS/Bot     │
                   │ (tmux agent) │    │  (SQS poller)  │   │  Handlers    │
                   └──────────────┘    └─────────────────┘   └──────────────┘
                          │
                   ┌──────▼──────┐
                   │  Tracker    │──▶ DynamoDB (AgentTracker, AgentLogs, AgentChat)
                   │  + Hooks    │
                   └─────────────┘
```

### Components

| Component | Directory | Description |
|-----------|-----------|-------------|
| **Orchestrator** | `orchestrator/` | Local daemon — manages Claude agents in tmux, routes Telegram/SMS/bot messages |
| **Handlers** | `handlers/` | AWS Lambda functions — webhooks (Telegram, SMS, Bot, Voice), API endpoints |
| **Modules** | `modules/` | Shared AWS utilities — DynamoDB wrapper, config, models |
| **Tracker** | `tracker/` | Agent tracking SDK + Claude Code hooks for session lifecycle |
| **Mobile App** | `mobile/` | Expo (React Native) app — iOS/Android/Web dashboard |
| **Worker** | `worker/` | SQS task worker — executes repo tasks with auto-fix |
| **Infrastructure** | `infrastructure/` | CloudFormation (SAM) templates + deploy scripts |
| **Bin Scripts** | `bin/` | CLI tools — scheduler, session manager, bootstrap, sync, creds |
| **Claude Config** | `claude-config/` | Settings, hooks config, tmux config templates |
| **Abilities** | `abilities/` | Loadable context docs for integrations (30+ capabilities) |
| **Shared** | `shared/` | DataclassBase models, web scraper, smart crawler, RPA |

---

## Quick Start

### Prerequisites

- macOS (Apple Silicon recommended)
- Python 3.11+
- Node.js 20+
- AWS CLI configured (`aws configure`)
- Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`)
- tmux installed (`brew install tmux`)
- Expo CLI (`npm install -g expo-cli`)

### 1. Deploy AWS Infrastructure

```bash
cd infrastructure/
make build_template        # Merge CloudFormation fragments
make build_handlers        # Zip Lambda handlers
make upload_handlers       # Upload to S3
make deploy_stack          # Create/update CloudFormation stack
```

### 2. Configure Claude Code

```bash
# Copy settings template
cp claude-config/settings.json.template ~/.claude/settings.json
# Copy tmux config
cp claude-config/tmux.conf ~/.tmux.conf
# Edit settings to update hook paths
```

### 3. Start the Orchestrator

```bash
cd orchestrator/
pip install -r requirements.txt
python orchestrator.py
```

### 4. Start the Task Worker

```bash
cd worker/
python worker.py
```

### 5. Deploy the Mobile App

```bash
cd mobile/
npm install
cp .env.example .env      # Fill in your values
npx expo start             # Development
npx expo export --platform web  # Web build
```

---

## Things You MUST Update

After cloning, prompt the user for these values and update accordingly:

### AWS & Infrastructure
| What | Where | Example |
|------|-------|---------|
| AWS Account ID | `infrastructure/templates/fragments/*.yaml`, `worker/worker.py` | `123456789012` |
| AWS Region | `modules/Config.py`, `orchestrator/orchestrator.py` | `us-east-1` |
| S3 Code Bucket | `infrastructure/Makefile` | `my-deployment-assets` |
| S3 Frontend Bucket | `infrastructure/Makefile`, deploy scripts | `my-dashboard-frontend` |
| S3 Media Bucket | `modules/Config.py` | `my-chat-media` |
| ACM Certificate ARN | `infrastructure/templates/fragments/cdn.yaml` | `arn:aws:acm:...` |
| Domain Name | `infrastructure/templates/fragments/cdn.yaml` | `yourdomain.com` |

### Authentication
| What | Where | Example |
|------|-------|---------|
| Cognito User Pool ID | `infrastructure/templates/fragments/api.yaml`, `mobile/src/services/auth.ts` | `us-east-1_XXXXXXXXX` |
| Cognito Client ID | `mobile/src/services/auth.ts` | (from CloudFormation output) |
| API Gateway URL | `mobile/.env` | `https://xxxxx.execute-api.us-east-1.amazonaws.com/prod` |

### Telegram
| What | Where | Example |
|------|-------|---------|
| Telegram Bot Token | `orchestrator/orchestrator.py` (or env var) | `123456:ABC-DEF...` |
| Telegram Chat ID | Orchestrator config | Your Telegram user ID |

### Twilio (SMS/Voice)
| What | Where | Example |
|------|-------|---------|
| Twilio Phone Number | `orchestrator/sms/handler.py` | `+1XXXXXXXXXX` |
| Twilio Account SID | SSM parameter store | `ACXXXXXXX` |
| Twilio Auth Token | SSM parameter store | (secret) |

### Expo (Mobile App)
| What | Where | Example |
|------|-------|---------|
| EAS Project ID | `mobile/app.json` | UUID from `eas init` |
| Bundle Identifier | `mobile/app.json` | `com.yourorg.dashboard` |

### Claude Code Hooks
| What | Where | Example |
|------|-------|---------|
| Hook script paths | `claude-config/settings.json.template` | Update to your repo locations |
| Python venv path | `claude-config/settings.json.template` | `~/.venvs/global/bin/python` |

### Credentials (SSM Parameter Store)
| What | SSM Path | Notes |
|------|----------|-------|
| BotComm Secret | `/bartimaeus/botcomm/secret` | HMAC signing key for bot-to-bot auth |
| Porkbun API Key | `/bartimaeus/creds/porkbun` | DNS management |
| Google OAuth | `~/.config/google/credentials.json` | Gmail + Calendar API |

---

## CloudFormation Resources

The SAM template (`infrastructure/templates/`) deploys:

### DynamoDB Tables
| Table | Purpose | TTL |
|-------|---------|-----|
| AgentTracker | Active agent sessions | 7 days |
| AgentLogs | Agent execution logs | 3 days |
| AgentChat | Conversation history | 7 days |
| AgentCommands | Pending commands for agents | 1 day |
| BotTracker | Long-running bot status | 7 days |
| BotCommBots | Registered friend bots | - |
| BotCommSessions | Bot-to-bot conversation sessions | - |
| BotCommMessages | Bot-to-bot messages | - |
| MemoryEvents | Event memory system | - |
| PushTokens | Expo push notification tokens | - |
| BusinessExpenses | Expense tracking | - |

### Lambda Functions
- Telegram webhook → SQS
- SMS webhook (Twilio) → SQS
- Bot webhook (HMAC-signed) → SQS
- Voice webhook → SQS
- Dashboard API (tracker, media, memory, output, stocks, projects)

### Other Resources
- API Gateway + Cognito authorizer
- SQS queue (OrchestratorInbox) — 24h retention, 30s visibility
- S3 buckets (media, expense receipts)
- CloudFront distribution + S3 origin
- EventBridge daily summary cron
- IAM execution role (DynamoDB, S3, SQS, SSM, Bedrock, Logs)

---

## Memory System Structure

See [docs/memory-structure.md](docs/memory-structure.md) for the complete memory system design.

The Claude Code memory lives at `~/.claude/projects/<project-hash>/memory/` and uses a hierarchical markdown structure:

```
memory/
├── MEMORY.md              # Index file (always loaded into context)
├── config/                # Environment, preferences, credentials
├── codebase/              # Per-repo architecture notes
├── operations/            # Deploy procedures, fixes, RPA
├── domain/                # Business domain knowledge
├── trading/               # Trading strategies
├── project/               # Active batch/project tracking
└── personal/              # Contacts, family, todos
```

Each memory file uses frontmatter:
```markdown
---
name: descriptive-name
description: one-line summary for relevance matching
type: user | feedback | project | reference
---

Content here...
```

---

## Tmux Session Management

The orchestrator manages Claude agents as tmux windows:

```bash
# List all Claude sessions
claude-sessions list

# Attach to a session
claude-sessions attach

# Start a new Claude session
claude-sessions new

# Start the tmux watcher (delivers commands to sessions)
claude-sessions watcher
```

Agent IDs are deterministic: `SHA256("claude-code::tmux-{session_name}")[:36]`

This means the same session always gets the same agent_id, enabling:
- Session recovery after crash
- Cross-process communication via DynamoDB
- Dashboard tracking continuity

---

## Hook System

Claude Code hooks track agent lifecycle in DynamoDB:

| Hook | Event | What It Does |
|------|-------|-------------|
| `on_prompt.py` | UserPromptSubmit | Register/reconnect session, generate title |
| `on_tool.py` | PostToolUse | Log tool usage |
| `on_stop.py` | Stop | Mark agent as completed |
| `on_notification.py` | Notification | Log notifications |
| `on_session_closed.py` | tmux session-closed | Mark dead sessions as completed+hidden |
| `tmux_watcher.py` | Polling daemon | Deliver queued commands to tmux sessions |

---

## Scheduler

Launchd-based job scheduling:

```bash
# One-time job
bin/schedule once "+2h" "python my_script.py" --tag my-job

# Recurring job
bin/schedule recurring "09:00 weekdays" "python daily_task.py" --tag daily-task

# List all jobs
bin/schedule-list
```

Jobs are managed via macOS LaunchAgents (`~/Library/LaunchAgents/com.bartimaeus.schedule.*.plist`).

---

## Backup & Restore

```bash
# Sync config to S3
bin/bart-sync push

# Restore config from S3
bin/bart-sync pull

# Backup credentials to SSM
bin/bart-sync backup-creds

# Full fresh-Mac bootstrap
bin/bart-bootstrap
```

---

## License

Private repository. All rights reserved.
