# Codex CLI Ability

Use OpenAI's Codex CLI as a code-writing agent to reduce Claude model usage. Codex writes code, Opus reviews it.

## Setup

```
npm i -g @openai/codex
```

Authenticated via ChatGPT Plus subscription (`codex login`). Uses subscription quota — no extra API cost.
Default model is GPT-4o. Do NOT pass `-m o3` or `-m o4-mini` — those require a separate API key and will fail with ChatGPT auth.

## Usage Patterns

### 1. Non-interactive code writing (exec mode)

Use `codex exec` to run Codex headlessly — ideal for delegating implementation tasks from Claude.

```bash
codex exec -C /path/to/repo --full-auto "Implement feature X in file Y"
```

Key flags:
- `-C <dir>` — working directory (must be a git repo)
- `--full-auto` — auto-approve safe commands, sandbox writes to workspace
- `-s workspace-write` — allow writing files in workspace
- `-s read-only` — read-only sandbox (safer for exploration)
- `--skip-git-repo-check` — run outside a git repo
- `-o <file>` — write last agent message to a file
- `--json` — output events as JSONL (for programmatic parsing)

### 2. Code review

```bash
codex review --uncommitted                # review all uncommitted changes
codex review --base main                  # review changes vs main branch
codex review --commit abc123              # review a specific commit
codex review "Focus on security issues"   # custom review instructions
```

### 3. Interactive mode

```bash
codex -m o3 -C /path/to/repo "Build a REST API for user management"
```

Opens an interactive TUI session (not usable from within Claude — use `exec` instead).

## Cost-Saving Workflow

The primary purpose: **Codex writes, Opus reviews**. This saves Claude Opus/Sonnet tokens.

### From Claude (delegating to Codex)

```bash
# Have Codex implement something
codex exec -C /path/to/repo --full-auto \
  "Add pagination to the /api/leads endpoint. Use cursor-based pagination with a default page size of 50."

# Then Opus reviews the changes
git diff  # review in Claude context
```

### Note on models

With ChatGPT Plus auth, the default model (GPT-4o) is used. Model selection (`-m`) requires an API key and will fail with ChatGPT login. If we add an API key later, these models are available:

| Model | Best For | Notes |
|-------|----------|-------|
| `o4-mini` | Simple tasks, quick edits, bulk operations | Cheapest, fastest reasoning model |
| `o3` | Complex features, multi-file changes | Strong reasoning, mid cost |
| `gpt-4.1` | Exploration, Q&A, code explanation | Good general purpose, not a reasoning model |
| `gpt-4o` | General coding (default with ChatGPT auth) | Balanced speed/quality |
| `gpt-4.1-mini` | Light tasks, summarization | Cheaper than 4.1 |

### Workflow steps (from Claude)

1. **Plan** (Opus) — design the approach, define what to build
2. **Write** (Codex) — `codex exec` with clear instructions
3. **Review** (Opus) — read the diff, check quality and correctness
4. **Fix** (Codex) — if issues found, run another `codex exec` with fix instructions
5. **Final review** (Opus) — approve or iterate

## Output Capture

For programmatic use, capture Codex output:

```bash
# Save last message to file
codex exec -C /path/to/repo --full-auto \
  -o /tmp/codex_result.txt \
  "Explain the architecture of this project"

# JSONL event stream
codex exec --json --skip-git-repo-check "List all API endpoints" > /tmp/codex_events.jsonl
```

## JSONL Stuffing Pattern (Bulk Processing Hack)

Codex rate limits count **calls**, not tokens. Stuff many items into a single call using file I/O:

1. Write all items to `input.jsonl` (one JSON object per line)
2. Have codex read the file, process each row, and write results to `output.jsonl`
3. Each codex call = 1 rate limit hit regardless of row count

~2000 rows per call works well. With 150 calls/5hr limit, that's 300K items per window.

```bash
# Write input.jsonl with rows to process
# Then run codex with instructions to read input and write output
codex exec --skip-git-repo-check --full-auto \
  "Read input.jsonl, classify each row, write results to output.jsonl. \
   Input format: {id, field1, field2, ...}. \
   Output format: {id, result1, result2, ...}. \
   Process ALL rows. Write ALL results. No markdown — just the JSONL file. \
   Input file: /tmp/batch/input.jsonl \
   Output file: /tmp/batch/output.jsonl"
```

Key points:
- **Default model (GPT-4o)** works for classification/extraction tasks — no need for reasoning models
- `gpt-5.3-codex` is for coding tasks, not bulk text processing
- With ChatGPT Plus auth, only the default model works (no `-m` flag)
- Parallelize with 5+ concurrent calls for throughput (~10K items/min)

Example: `bulk_classify.py` in `/Users/bartimaeus/nse/` classifies 95K stock announcements this way.

## Notes

- Codex requires a git repo by default (use `--skip-git-repo-check` to bypass)
- `--full-auto` is safe — it sandboxes writes to the workspace directory only
- Codex can also use `--search` flag for live web search during tasks
- Interactive mode (`codex` without `exec`) opens a TUI — only useful in a real terminal, not from within Claude
- Session history is persisted and can be resumed with `codex resume`
