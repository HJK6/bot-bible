# Bot Startup Guide

Help a friend set up their own bot infrastructure modeled after YOUR_BOT_NAME. Covers CloudFormation, orchestrator, mobile app, memory system, tmux, and CLAUDE.md identity.

## Playbook Location

- **S3**: `s3://YOUR_BOT_NAME-chat-media/bot-data/matt-bot/tars_playbook.md`
- **Local copy**: `/tmp/tars_playbook.md` (ephemeral)
- Generate a fresh presigned URL when sharing:
  ```python
  import boto3
  s3 = boto3.client('s3', region_name='us-east-1')
  url = s3.generate_presigned_url('get_object', Params={'Bucket': 'YOUR_BOT_NAME-chat-media', 'Key': 'bot-data/matt-bot/tars_playbook.md'}, ExpiresIn=604800)
  ```

## What the Playbook Covers

1. **CloudFormation stack** — DynamoDB tables (AgentTracker, BotTracker, AgentLogs, AgentChat, AgentCommands, MemoryEvents, PushTokens, BotComm tables), SQS (OrchestratorInbox), Lambda functions (dashboard CRUD + webhooks), Cognito user pool, S3 + CloudFront, API Gateway
2. **Orchestrator daemon** — asyncio SQS poller, tmux session management, Claude Code subprocess spawning with `--resume`, ManagedAgent/MessageQueue classes, tracker SDK
3. **Mobile app** — Expo React Native, Amplify + Cognito auth, push notifications, chat interface, agent management
4. **Memory system** — DynamoDB MemoryEvents, FAISS embeddings, daily summaries
5. **tmux config** — mouse, 50k scrollback, session-closed hook for AgentTracker cleanup
6. **CLAUDE.md** — bot identity, owner info, abilities system, model usage rules
7. **BotComm** — registration with YOUR_BOT_NAME, send/poll scripts

## How to Use

1. Register the new bot via BotComm: `py orchestrator/bot/register_bot.py invite --name "Bot Name" --scopes chat,data,knowledge`
2. Generate a presigned URL for the playbook (see above)
3. Text the friend the URL — they paste the playbook contents into their Claude Code
4. The playbook tells their bot to replace `TARS` / `YOUR_BOT_NAME` with their chosen name
5. Once their bot deploys infra and messages back via BotComm, they're connected

## Registered Friend Bots

| Bot ID | Name | Owner | Status |
|--------|------|-------|--------|
| matt-bot | TARS | Matt Costantino | active |
| yeluru-claude-main | yeluru_claude_bot | Sai Yeluru | active |

## Future Improvements

- Upload a generic version of the playbook (without TARS-specific naming) to S3 at `bot-data/templates/bot_startup_playbook.md`
- Auto-generate personalized playbooks per bot name
- Include Telegram bot setup instructions (BotFather token, webhook)
