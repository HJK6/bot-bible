# Claude Code Memory System

The memory system gives Claude Code persistent, file-based knowledge across conversations. It lives at `~/.claude/projects/<project-hash>/memory/`.

## How It Works

1. **MEMORY.md** — The index file. Always loaded into conversation context (first 200 lines). Contains only links to memory files with brief descriptions. Never put actual memory content here.

2. **Memory files** — Individual `.md` files organized by topic. Each has YAML frontmatter for metadata. Loaded on-demand when relevant.

3. **contacts.json** — Flat JSON file with contact entries. Searchable by name/phone/email.

## Directory Structure

```
memory/
├── MEMORY.md                     # Index (always in context, max 200 lines)
├── contacts.json                 # Contact directory
│
├── config/                       # System configuration
│   ├── environment.md            # AWS region, Python version, venv paths
│   ├── preferences.md            # User communication preferences
│   ├── model_usage.md            # Which Claude models for what tasks
│   ├── coding_standards.md       # Code style rules (DataclassBase, etc.)
│   └── credentials.md            # Where credentials live (not the creds themselves)
│
├── codebase/                     # Per-repo architecture notes
│   ├── agent_dashboard.md        # Backend — Lambda, orchestrator, tracker
│   ├── dashboard.md              # Mobile app — Expo, routing, hooks
│   ├── telegram_bot.md           # Bot code, abilities, scraper
│   ├── task_worker.md            # SQS worker, task dispatch
│   ├── land_bot.md               # CRM, scrapers, DynamoDB
│   ├── land_sales_portal.md      # React CRM frontend
│   ├── memory_system.md          # Memory events + FAISS
│   ├── aceable.md                # Course automation
│   ├── stocks.md                 # BSE/NSE pipeline
│   └── 0dte_trading.md           # IBKR trading system
│
├── operations/                   # How to do things
│   ├── deploys.md                # Deploy commands for all repos
│   ├── lambda_architecture.md    # Cold start optimization
│   ├── fixes.md                  # Known issues and fixes
│   ├── rpa.md                    # Screen automation setup
│   ├── altum_testing.md          # Test infrastructure
│   └── mobile_app_upgrade.md     # App upgrade procedures
│
├── domain/                       # Business knowledge
│   ├── altum_realty.md            # Land CRM team, statuses, pipeline
│   ├── altum_reports.md           # On-demand report types
│   ├── skip_matrix_process.md    # CSV generation pipeline
│   ├── data_quality.md           # Skip trace quality issues
│   ├── monthly_foreclosures.md   # Monthly scraping process
│   ├── mls_scraper.md            # MLS Matrix scraper
│   ├── tax_delinquent_mls.md     # Tax x MLS cross-reference
│   ├── foreclosures_com.md       # Foreclosure.com scraper
│   └── foreclosures/             # Per-state foreclosure processes
│       ├── colorado.md
│       ├── florida.md
│       ├── florida_scrapers.md
│       ├── fl_miami_dade.md
│       ├── fl_broward.md
│       ├── fl_hillsborough.md
│       ├── fl_orange.md
│       ├── fl_duval.md
│       ├── georgia.md
│       └── texas.md
│
├── trading/                      # Trading strategies
│   ├── indian_stock_analysis.md  # Buy signal analysis
│   ├── indian_daytrading.md      # Day trading system
│   └── strategies/
│       ├── fo_overnight.md       # F&O overnight
│       ├── midcap_swing.md       # Mid/small cap swing
│       └── silent_shock.md       # Silent volume shock
│
├── project/                      # Active project tracking
│   ├── foreclosure_batches.md    # Batch index
│   ├── batch_2026_02_mock.md
│   ├── batch_2026_02_tax_delinquent.md
│   ├── batch_2026_03_ab.md
│   └── batch_2026_03_c.md
│
└── personal/                     # Personal info
    ├── family.md
    ├── friends.md
    ├── bachelors_party.md
    ├── cousins_trip.md
    ├── todo.md
    └── compute_results.md
```

## Memory File Format

Every memory file uses this template:

```markdown
---
name: descriptive-name
description: One-line description used to decide relevance in future conversations
type: user | feedback | project | reference
---

Content goes here. For feedback/project types, structure as:

**Rule/Fact**: The main thing to remember.

**Why**: The motivation or incident that led to this.

**How to apply**: When and where this should influence behavior.
```

## Memory Types

### `user` — Who the user is
Information about the user's role, goals, expertise, preferences. Helps tailor responses.

**Example**: "User is a senior full-stack engineer. Deep Go expertise, new to React."

### `feedback` — Corrections and guidance
Things the user has corrected. Most important type — prevents repeating mistakes.

**Example**: "Don't mock the database in integration tests. Why: mocked tests passed but prod migration failed."

### `project` — Active work context
Ongoing initiatives, deadlines, batch tracking. Decays fast — include why so future sessions can judge relevance.

**Example**: "Merge freeze begins 2026-03-05 for mobile release cut."

### `reference` — External pointers
Where to find information in external systems (Linear, Slack, Grafana, etc.).

**Example**: "Pipeline bugs tracked in Linear project INGEST."

## MEMORY.md Format

The index file should be a slim table of contents:

```markdown
# Memory

## Quick Reference
- **Config**: `config/environment.md` · `config/preferences.md`
- **Contacts**: `contacts.json`

## Topic Files — read on demand

### Codebase (`codebase/`)
| Topic | File | When to load |
|-------|------|-------------|
| Agent Dashboard | `codebase/agent_dashboard.md` | Backend work |
| Mobile App | `codebase/dashboard.md` | Mobile/web work |
```

### Key Rules

1. **MEMORY.md is an index, not a memory** — only links and brief descriptions
2. **Max 200 lines** — lines after 200 are truncated from context
3. **Organize by topic**, not chronologically
4. **No duplicates** — check for existing memory before writing new
5. **Keep descriptions specific** — they're used for relevance matching
6. **Convert relative dates** — "Thursday" → "2026-03-05"
7. **Update or remove** outdated memories

### What NOT to Store

- Code patterns derivable from reading the codebase
- Git history (use `git log`)
- Fix recipes (the fix is in the code)
- Anything in CLAUDE.md files
- Ephemeral task state (use tasks/plans instead)

## Bootstrap for New Instance

To set up memory for a new Claude Code instance:

1. Create the memory directory:
   ```bash
   mkdir -p ~/.claude/projects/<project-hash>/memory/{config,codebase,operations,domain,project,personal}
   ```

2. Start with `MEMORY.md` index and `config/` files:
   - `config/environment.md` — AWS region, Python paths, venv locations
   - `config/preferences.md` — Communication style, response format
   - `config/credentials.md` — Where credentials are stored (not the values)

3. Add codebase files as you work with each repo

4. Memory builds naturally through conversation — Claude saves memories when it learns something relevant

## Sync

Memory files sync to S3 via `bot-sync`:
```bash
bot-sync push    # Upload changed memory files
bot-sync pull    # Download changes
```

This enables memory portability across machines.
