# Resume Agent Session

Resume a Claude Code session from an agent chat on the mobile app. Allows picking up where an orchestrator-spawned agent left off.

## Data Sources

| Source | Location | What it has |
|--------|----------|-------------|
| **AgentTracker** (DynamoDB) | Table `AgentTracker`, PK: `agent_id` | Agent metadata: title, goal, status, session_id |
| **AgentChat** (DynamoDB) | Table `AgentChat`, PK: `agent_id`, SK: `timestamp` | Chat messages (inbound/outbound) |
| **Session files** (local) | `~/.claude/orchestrator/sessions/<agent_id>.json` | session_id, goal, conversation_history |

## Step 1 — List Agents

```python
import boto3
dynamo = boto3.resource('dynamodb', region_name='us-east-1')
tracker = dynamo.Table('AgentTracker')

# All agents, newest first
resp = tracker.scan()
agents = sorted(resp['Items'], key=lambda x: x.get('last_heartbeat', ''), reverse=True)
for a in agents:
    print(f"{a['agent_id'][:8]}  {a.get('status','?'):10s}  {a.get('title','(no title)')}")
```

Or filter by status:
```python
from boto3.dynamodb.conditions import Key
resp = tracker.query(IndexName='StatusIndex', KeyConditionExpression=Key('status').eq('idle'))
```

## Step 2 — Get Chat History

```python
from boto3.dynamodb.conditions import Key
chat = dynamo.Table('AgentChat')
resp = chat.query(
    KeyConditionExpression=Key('agent_id').eq(AGENT_ID),
    ScanIndexForward=True  # chronological
)
for msg in resp['Items']:
    direction = 'USER' if msg['direction'] == 'inbound' else 'AGENT'
    print(f"[{direction}] {msg['message'][:200]}")
```

## Step 3 — Find Session ID

**Option A — Local session file** (preferred, has full conversation history):
```python
import json
with open(f'/Users/bartimaeus/.claude/orchestrator/sessions/{AGENT_ID}.json') as f:
    session = json.load(f)
session_id = session['session_id']          # Claude Code UUID
goal = session['goal']
history = session['conversation_history']    # [{role, content, timestamp}, ...]
```

**Option B — DynamoDB** (if local file missing):
```python
resp = tracker.get_item(Key={'agent_id': AGENT_ID})
agent = resp['Item']
session_id = agent.get('session_id', '')
goal = agent.get('goal', '')
```

## Step 4 — Resume the Session

### 4a. Direct resume (session_id exists and is recent)

```bash
claude --resume SESSION_ID -p "FOLLOW_UP_MESSAGE" --output-format stream-json --verbose
```

Or interactively:
```bash
claude --resume SESSION_ID
```

### 4b. Rebuild context (session_id stale or missing)

If `--resume` fails (session expired, context evicted), reconstruct from chat history:

```python
# Build a context prompt from the agent's history
lines = [f"You are resuming a previous agent session.\n\nOriginal goal: {goal}\n"]
lines.append("Previous conversation:")
for msg in history:  # from session file or AgentChat query
    role = "User" if msg.get('role') == 'user' or msg.get('direction') == 'inbound' else "Agent"
    content = msg.get('content') or msg.get('message', '')
    lines.append(f"\n{role}: {content}")
lines.append("\n\nContinue from where you left off. The user has a follow-up request:")
lines.append(FOLLOW_UP_MESSAGE)
context_prompt = "\n".join(lines)
```

Then start a fresh session with the reconstructed context:
```bash
claude -p "CONTEXT_PROMPT" --output-format stream-json --verbose
```

## Step 5 — Log Response Back to App

After completing work, write the response to AgentChat so it appears in the mobile app:

```python
import time
chat = dynamo.Table('AgentChat')
chat.put_item(Item={
    'agent_id': AGENT_ID,
    'timestamp': int(time.time() * 1000),
    'direction': 'outbound',
    'message': RESPONSE_TEXT[:5000],
    'sender': 'Bartimaeus',
    'ttl': int(time.time()) + (7 * 86400),
})
```

## Quick Resume Script

One-liner to find and resume the most recent idle agent:

```bash
# Find most recent idle agent's session_id from local files
py -c "
import json, glob, os
files = sorted(glob.glob(os.path.expanduser('~/.claude/orchestrator/sessions/*.json')), key=os.path.getmtime, reverse=True)
for f in files:
    d = json.load(open(f))
    sid = d.get('session_id','')
    print(f\"{d['agent_id'][:8]}  {d.get('title','?')[:50]}  session={sid[:8]}\")
" | head -10
```

Then resume:
```bash
claude --resume <SESSION_ID>
```

## Notes

- Session files persist across orchestrator restarts — they're the most reliable source for session_id
- Claude Code sessions expire after some time; if `--resume` fails, fall back to context rebuild (Step 4b)
- The orchestrator also stores `last_user_messages`, `last_agent_message`, `agent_summary` in AgentTracker — useful for context rebuild
- AgentChat messages have a 7-day TTL; older conversations are auto-deleted
- To avoid conflicts with a running orchestrator, check agent status is `idle` or `stopped` before resuming
- When resuming, update AgentTracker status to `running` and back to `idle`/`completed` when done
