# Memory System

Event-based memory with DynamoDB storage and local FAISS vector search. Log events as they happen, then query with natural language to recall past context.

## Location

Source: `/Users/bartimaeus/memory-system/memory_system/`
DynamoDB table: `MemoryEvents`
Local FAISS index: `/Users/bartimaeus/memory-system/local/faiss/`
Daily summaries: `/Users/bartimaeus/memory-system/local/daily/`

## Setup

```python
import sys
sys.path.insert(0, "/Users/bartimaeus/memory-system")

from memory_system import Memory
```

Requires:
- `faiss-cpu` installed (`pip install --user faiss-cpu`)
- Ollama running at localhost:11434 with `nomic-embed-text` model
- AWS credentials (hardcoded defaults in store.py, or set `MEMORY_AWS_ACCESS_KEY`, `MEMORY_AWS_SECRET_KEY`)
- `MemoryEvents` DynamoDB table deployed

## Quick Log (Preferred for Scripts)

Use `log_event` for lightweight, fire-and-forget event logging. No FAISS overhead — writes directly to DynamoDB. Embedding is always attempted; if Ollama is down, the event is queued locally (`local/pending_embeddings.jsonl`) and flushed automatically when Ollama is back (or during daily summary).

```python
import sys
sys.path.insert(0, "/Users/bartimaeus/memory-system")
from memory_system.log import log_event

# One-liner — logs to DynamoDB, embeds via Ollama (queues if down)
log_event("land-bot", "scrape", "Scraped 142 properties from Harris County",
          tags=["harris", "tax-sale"])

log_event("aceable-bot", "error", "Login failed — captcha detected",
          details="Traceback...", tags=["captcha"])

log_event("nse-pipeline", "success", "BSE pipeline complete: 3186 stocks scraped, CSV emailed",
          tags=["bse", "pipeline", "daily"])
```

All instrumented scripts use a `mem_log` wrapper that silently catches exceptions:
```python
sys.path.insert(0, "/Users/bartimaeus/memory-system")
from memory_system.log import log_event as _log_event
def mem_log(category, summary, **kwargs):
    try: _log_event("my-bot", category, summary, **kwargs)
    except Exception: pass
```

**Use `log_event` in all scripts/bots.** Every meaningful operation should log:
- Errors and failures (category: `error`)
- Successful completions (category: `success`)
- Scraper/pipeline results with counts (category: `scrape`)
- Reports generated/sent (category: `report`)
- Features deployed (category: `deploy`)
- Process outcomes (category: `task`)
- Fixes applied (category: `fix`)

## Memory Class API

### Log Events (Full — with FAISS update)

```python
mem = Memory()

# Log an event (embeds, writes to DynamoDB, updates local FAISS)
event = mem.log_event(
    source="aceable-bot",          # which bot/system
    category="error",              # error, success, fix, scrape, deploy, task, info, report
    summary="Login failed — captcha detected on sign-in page",
    details="Full traceback or longer context here...",
    tags=["aceable", "captcha", "login"],
    resolved=False,
)
print(event.event_id)  # "evt_a1b2c3d4e5f6"
```

### Query (Semantic Search)

```python
results = mem.query("aceable login problems", top_k=5)
for r in results:
    print(f"[{r.score:.3f}] [{r.event.source}] {r.event.summary}")
    if r.event.resolved:
        print(f"  Resolved: {r.event.resolution}")
```

### Resolve Events

```python
mem.resolve_event("evt_a1b2c3d4e5f6", "Added retry with exponential backoff")
```

### Get Events by Date

```python
events = mem.get_events_by_date("2026-02-09")
for e in events:
    print(f"[{e.category}] {e.summary}")
```

### Rebuild Index

```python
# Pull all events from DynamoDB and rebuild local FAISS index
count = mem.rebuild_index()
print(f"Indexed {count} events")
```

### Properties

| Property | Description |
|----------|-------------|
| `mem.event_count` | Number of events in local FAISS index |

## Event Categories

| Category | Use For |
|----------|---------|
| `error` | Failures, exceptions, crashes |
| `success` | Completed tasks, milestones |
| `fix` | Bug fixes, patches applied |
| `scrape` | Scraper runs, data collection |
| `deploy` | Deployments, infrastructure changes |
| `task` | SQS task execution results |
| `report` | Reports generated, data exports, emails sent |
| `info` | General notes, observations |
| `daily-summary` | Auto-generated daily summaries |

## MemoryEvent Fields

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | str | Unique ID (`evt_xxxxxxxxxxxx`) |
| `timestamp` | str | ISO 8601 UTC |
| `timestamp_ms` | int | Epoch milliseconds |
| `source` | str | Bot/system name |
| `category` | str | Event category |
| `summary` | str | Short description (embedded for search) |
| `details` | str | Full context, tracebacks, etc. |
| `tags` | list | Searchable tags |
| `resolved` | bool | Whether the event has been resolved |
| `resolution` | str | How it was resolved |
| `date` | str | YYYY-MM-DD |

## Daily Summary Generation

Via SQS task or direct call:

```python
from memory_system.daily_summary import generate_daily_summary

# Generate for yesterday (default)
summary = generate_daily_summary()

# Generate for specific date
summary = generate_daily_summary("2026-02-09")
```

Via SQS (through task-worker):
```json
{"repo": "memory-system", "task": "generate_daily_summary", "data": {"date": "2026-02-09"}}
```

## Chat Audit (End-of-Day Backfill)

The daily summary task automatically audits AgentChat messages before generating the summary. It uses a local LLM to extract operational events from chat conversations and backfills any that weren't explicitly logged.

Run manually:
```bash
cd /Users/bartimaeus/memory-system
PYTHONPATH=. ~/.venvs/global/bin/python tasks/audit_chats.py 2026-03-13
```

Via SQS:
```json
{"repo": "memory-system", "task": "audit_chats", "data": {"date": "2026-03-13"}}
```

The audit is a safety net — scripts should still call `log_event` directly for accurate, detailed logging. The audit catches events that slipped through.

## Architecture

```
Write path (lightweight):
  log_event() → write to DynamoDB (embed best-effort via Ollama)

Write path (full):
  Memory.log_event() → embed via Ollama → write to DynamoDB + update local FAISS

Query path:
  query() → embed query → FAISS similarity search → return ranked events

Startup:
  Memory() → load local FAISS index (or rebuild from DynamoDB if empty)

Daily pipeline (runs at 12:01 AM CT):
  1. audit_chats → scan AgentChat → LLM extract events → backfill MemoryEvents
  2. generate_daily_summary → query DateIndex GSI → summarize with Ollama → store
```

## Notes

- Embeddings use `nomic-embed-text` (768 dimensions) via Ollama
- FAISS uses cosine similarity (IndexFlatIP with L2 normalization)
- Embeddings stored in DynamoDB as binary — no re-embedding needed on index rebuild
- TTL set to 365 days by default
- DynamoDB PK: `source#category`, SK: `timestamp#event_id`
- GSI `DateIndex`: PK: `date_key`, SK: `timestamp_ms`

---

# Personal Facts

Persistent personal facts with semantic search and optional image attachments. Unlike events (temporal, auto-expire), facts persist forever and are updatable.

## Setup

```python
import sys
sys.path.insert(0, "/Users/bartimaeus/memory-system")

from memory_system import Facts
```

Requires same dependencies as Memory (faiss-cpu, Ollama, AWS credentials), plus:
- `PersonalFacts` DynamoDB table
- `bartimaeus-personal-facts` S3 bucket (for image storage, SSE-S3 encrypted)

## Facts Class API

### Remember (Store a Fact)

```python
facts = Facts()

# Text-only fact
f = facts.remember(
    fact="Cat's prescription is in the top drawer of the closet",
    category="health",
    tags=["cat", "medication"],
)
print(f.fact_id)  # "fact_a1b2c3d4e5f6"

# Fact with image attachment
f = facts.remember(
    fact="Driver's license — Texas DL, Class C, expires 08/2028",
    category="identity",
    tags=["drivers-license", "ID", "texas"],
    image_path="/tmp/dl_photo.jpg",
    image_description="Front of Texas driver's license, Class C, issued 2020, expires 2028",
)
```

### Recall (Semantic Search)

```python
results = facts.recall("where is the cat's prescription?", top_k=5)
for r in results:
    print(f"[{r.score:.3f}] {r.fact.fact}")

# Filter by category
results = facts.recall("medical records", category="health")
```

### Update a Fact

```python
facts.update("fact_abc123", fact="Cat's prescription moved to bathroom cabinet")

# Update multiple fields
facts.update("fact_abc123", fact="New text", tags=["new", "tags"], category="home")
```

### Forget (Soft-Delete)

```python
facts.forget("fact_abc123")
# Record stays in DynamoDB (recoverable), removed from FAISS
```

### List Facts

```python
# All active facts
all_facts = facts.list_facts()

# By category
health = facts.list_facts(category="health")

# Include forgotten facts
all_incl_inactive = facts.list_facts(include_inactive=True)
```

### Get Image URL

```python
url = facts.get_image_url("fact_abc123")  # presigned S3 URL, 1-hour expiry
url = facts.get_image_url("fact_abc123", expiry=7200)  # 2 hours
# Returns None if fact has no image
```

### Other Methods

```python
pf = facts.get_fact("fact_abc123")       # Get single fact by ID
count = facts.rebuild_index()             # Rebuild FAISS from DynamoDB
print(facts.fact_count)                   # Number of active facts in FAISS
```

## PersonalFact Fields

| Field | Type | Description |
|-------|------|-------------|
| `fact_id` | str | Unique ID (`fact_xxxxxxxxxxxx`) |
| `created_at` | str | ISO 8601 UTC |
| `updated_at` | str | ISO 8601 UTC |
| `fact` | str | The core fact text |
| `category` | str | Free-form grouping (health, home, identity, finance, etc.) |
| `tags` | list | Searchable tags |
| `image_key` | str | S3 key (empty if no image) |
| `image_description` | str | Image description (embedded for search) |
| `active` | bool | False = soft-deleted / forgotten |

## Architecture

```
Store path:
  remember() → embed fact+tags+description → upload image to S3 (if any)
            → write to DynamoDB + update local FAISS

Search path:
  recall() → embed query → FAISS similarity search → return ranked facts

Image path:
  remember(image_path=...) → S3 upload (encrypted) → store S3 key in DynamoDB
  get_image_url() → presigned S3 GET URL (1hr default)

DynamoDB: PersonalFacts table, PK: fact_id, GSI CategoryIndex (category + updated_at)
S3: bartimaeus-personal-facts bucket (SSE-S3, versioned, no expiry)
FAISS: local/faiss/facts_index.faiss + facts_metadata.json (separate from events index)
```
