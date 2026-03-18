# Altum Realty — Land Investment CRM

Land acquisition CRM with county scrapers, skip-trace pipeline, DynamoDB storage, and SQS task dispatch.

**Repo**: `/Users/YOUR_USERNAME/land-bot/`
**Run scripts**: `PYTHONPATH=. python3 scripts/<script>.py` (from repo root)
**Run tests**: `PYTHONPATH=. python3 -c "from tests.<module> import <fn>; <fn>()"`

---

## County Scrapers

9 counties, each at `scrapers/<county>/scraper.py`. Every scraper exposes:

- `scrape_data(account_id, seed_data=None, foreclosure_data=None)` → `ScrapedLotData | None`
- `refresh_data(existing_property)` → `Property | None`

| County | TRW/Seed Data | Notes |
|--------|--------------|-------|
| **Bexar** | No | CAD → Tax Office → LatLong |
| **Collin** | No | CAD (eSearch token) → Tax Office (geographic_id) |
| **Dallas** | Required (DallasTrwRecord) | Supports `foreclosure_data` dict |
| **Denton** | No | Tax Office → CAD, checks delinquency |
| **Ellis** | Required (EllisTrwRecord w/ CAN) | Tax → CAD, checks delinquency |
| **Harris** | No | HCAD + optional tax office |
| **Kaufman** | Required (KaufmanTrwRecord) | Tax → CAD, Google Maps fallback |
| **Tarrant** | Optional (TarrantTrwRecord) | Cookie-based tax office |
| **Travis** | No | Strips leading zeros from account_id |

Scrapers are called dynamically by tasks:
```python
import importlib
module = importlib.import_module(f"scrapers.{county.lower()}.scraper")
result = module.scrape_data(account_id, seed_data=seed_data)
```

---

## SQS Tasks

Tasks live in `tasks/`. Each has `run(task_data: dict) -> bool`. Dispatched via the **BotRequests** SQS queue.

### Message Format

```json
{
    "repo": "land-bot",
    "task": "<task_module_name>",
    "data": { ... }
}
```

### aggregatePropertyData

Scrapes a property + owner, writes to DynamoDB.

```json
{
    "repo": "land-bot",
    "task": "aggregatePropertyData",
    "data": {
        "account_id": "R000012345",
        "county": "DALLAS",
        "seed_data": { "category_code": "..." },
        "foreclosure_data": {
            "lien_amount": 50000.0,
            "appraised_amount": 100000.0,
            "equity": 50000.0,
            "foreclosure_notice": "...",
            "foreclosure_type": "...",
            "auction_date": "03/03/2026"
        }
    }
}
```

### refreshPropertyData

Re-scrapes an existing property to update data.

```json
{
    "repo": "land-bot",
    "task": "refreshPropertyData",
    "data": {
        "account_id": "R000012345",
        "county": "DALLAS"
    }
}
```

### scrape_preforeclosures

Fetches preforeclosure data from 64cents, filters by lien ratio, sends each property as `aggregatePropertyData` to the queue.

```json
{
    "repo": "land-bot",
    "task": "scrape_preforeclosures",
    "data": {
        "county": "DALLAS",
        "auction_date": "03/03/2026"
    }
}
```

### hydrate_skiptrace_data

Merges skip-trace results (phones, relatives, associates) into an existing owner, updates PhoneMapping, sets status to COLD.

```json
{
    "repo": "land-bot",
    "task": "hydrate_skiptrace_data",
    "data": {
        "owner_id": "abc123...",
        "skiptrace_data": {
            "phones": [{"number": "2145551234", "phone_type": "mobile", "last_seen": "2025-01"}],
            "relatives": [{"first_name": "Jane", "last_name": "Doe", "phones": [...]}],
            "associates": [{"first_name": "John", "last_name": "Smith", "phones": [...]}]
        }
    }
}
```

### testTask

Simple test task for verifying the worker pipeline.

```json
{
    "repo": "land-bot",
    "task": "testTask",
    "data": { "message": "hello" }
}
```

---

## Skip Matrix Pipeline

Skip-trace uses CSV batch files. Pipeline: generate CSV → send to skip-trace service → parse results → hydrate owners.

All files in `scrapers/skiptrace/`.

### Step 1: Generate Input CSV

```bash
PYTHONPATH=. python3 scrapers/skiptrace/generate_skip_matrix_input.py \
    --from-owners --counties DENTON,TRAVIS,COLLIN --status NEW
```

- Reads from Leads or Owners table (`--from-owners` flag)
- Filter by `--counties` (comma-separated uppercase) and `--status`
- Filter by specific owners with `--owner-ids-file path`
- Output: `skip_matrix_raw_name_input.csv`
- Columns: owner_id, Name, Mailing Street/City/State/Zip, Property Account ID, Property Street/City/State/Zip, Property County, Latitude, Longitude

### Step 2: Parse Names (split First/Last)

```bash
PYTHONPATH=. python3 scrapers/skiptrace/generate_skip_matrix_input.py --parsed
```

- Reads raw CSV, splits Name → First Name + Last Name
- Handles splits on `&`, `%`, `C/O`, `CO`
- First segment: "Last First" format; after `%` or `C/O`: "First Last" format
- Strips "Et Al", "Etal", "Et A"
- Output: `skip_matrix_parsed_name_input.csv`
- Columns: owner_id, First Name, Last Name, Mailing Street/City/State/Zip, Property Street/City/State/Zip

### Step 3: Clean/Validate Addresses

```bash
PYTHONPATH=. python3 scrapers/skiptrace/clean_skip_matrix.py [csv_path]
PYTHONPATH=. python3 scrapers/skiptrace/clean_skip_matrix.py [csv_path] --list-fixable
```

- `review_addresses(csv_path)` — finds address errors (not found, city-is-street, no street type, etc.)
- `list_fixable_properties(csv_path)` — shows fixable issues with before/after from Google Maps API

### Step 4: Parse Results

```python
from scrapers.skiptrace.parser import parse_skip_matrix_csv
records = parse_skip_matrix_csv("skip_results.csv")
# Returns list of SkipMatrixRecord objects
```

Result CSV columns: Owner ID, First/Last Name, Property/Mailing Address, Bankruptcy info, Subject phones 1-5, emails 1-5, IP addresses, Relatives 1-5 (with phones/emails), Associates 1-5 (with phones/emails).

### Step 5: Hydrate Owners

Send each parsed result to the queue as `hydrate_skiptrace_data` task, or call `update_owners.py` directly.

---

## Twilio Voice / Call Logging

### Call Flow
- **Outbound**: `start_voice_call()` in `modules/TwilioVoiceApi.py` generates TwiML, records with `record="record-from-answer-dual"`, callback → `on_call_complete()`
- **Inbound**: `incoming_voice_call` Lambda routes to agent, failed Dial → voicemail recording
- **Recording callback**: `on_call_complete()` downloads audio → S3 (`{owner_id}/recordings/{call_id}.wav`), stores in `owner.call_logs` via `add_call_record()`
- **Voicemails**: Stored in separate `Voicemails` table (not in owner.call_logs)

### Call Log Entry (in Owner.call_logs array)
Fields: `owner_id`, `call_id`, `call_sid`, `after_call_summary`, `agent_email`, `call_duration`, `recording_sid`, `recording_key`, `recording_bucket`, `recording_duration`, `from_number`, `to_number`, `timestamp`, `transcript_bucket`, `transcript_key`

### After-Call Summary
- `add_after_call_summary()` in `modules/OwnerDetails.py` — attaches summary to matching call_log entry
- If no call_log exists (unanswered call, no recording), creates a minimal entry with available data
- Always creates a note: `"Call made to {phone}: {summary}"`
- Auto-updates status: "wrong number" → DEAD, "reached owner"/"scheduled follow-up"/"not interested" → CONTACT MADE, "transferred to manager" → WARM

### Key Tables
- `CallTracking` — temporary (1hr TTL), stores call_sid + child_call_sid for active calls
- `PhoneMapping` — maps phone → owner_id, used to resolve inbound callers

### Deploy
```bash
cd /Users/YOUR_USERNAME/land-bot
make update_handlers PYTHON=python3   # Build handlers.zip, upload to S3, update CloudFormation
```

---

## Refresh / Re-aggregation Processes

Data changes trigger cascading refreshes across related tables. Keep these in mind when modifying data.

### Phone Number Added → Refresh PhoneMapping

When a new phone number is added to an owner (e.g. via skip-trace or manual entry), the **PhoneMapping** table must be updated. Each phone maps to a list of `associated_contacts` (owner_id + name). This is how inbound calls are matched to owners.

- `hydrate_skiptrace_data` handles this automatically — it iterates all phones (owner, relatives, associates) and calls `_add_owner_to_phone_mapping()` for each
- If adding phones manually, ensure PhoneMapping is updated too

### Property Updated → Re-aggregate Owner

When property data changes (tax data, land value, estimated value, flags), the **owner record must be re-aggregated** since owner totals are computed from their properties:

- `total_amount_due` — sum of all property tax amounts
- `total_land_value` — sum of all property land values
- `total_estimated_value` — sum of all property estimated values
- `owner_flags` / `property_flags` — recomputed from current data

### Bulk Re-aggregation (after pricing, comps update, etc.)

After bulk operations like a pricing run or comps refresh, **all affected owners need re-aggregation**. This means:

1. Identify affected properties (by county, status, or filter)
2. Group by owner_id
3. Re-read all properties for each owner
4. Recompute totals and flags
5. Write updated owners back

This can be dispatched as batch `refreshPropertyData` tasks to the SQS queue, or run as a script that iterates owners directly.

---

## Tests

Tests in `tests/`. Invoke from repo root:

```bash
PYTHONPATH=. python3 -c "from tests.<module> import <fn>; <fn>()"
```

| Module | Key Functions |
|--------|--------------|
| `tests.cache` | `test_refresh_all()`, `test_load_all()`, `test_query_properties()`, `test_query_owners()` |
| `tests.models` | `run_all()` — round-trip tests for all dataclasses |
| `tests.tasks` | `runAggregateDallasDataFromFiltered()` |
| `tests.owner` | `get_all_owners()`, `get_all_owners_as_dicts()` |
| `tests.reports` | `test_email_agent_activity_report()` |
| `tests.latlong` | `test_call_google_maps_api()` |
| `tests.scrapers.<county>` | County-specific scraper tests (bexar, collin, dallas, denton, ellis, harris, kaufman, tarrant, travis) |
| `tests.scrapers.skiptrace` | Skip-trace tests |
| `tests.scrapers.mls` | MLS scraper tests |
| `tests.scrapers.georeference` | Zoning georeference tests |

---

## Key Modules

| Module | Purpose |
|--------|---------|
| `modules.Config` | Table names, constants, queue URLs |
| `modules.Dynamo` | `Table(name)` — get, write, delete, filter, query_index, batch ops |
| `modules.Cache` | Local DynamoDB cache — `Cache.load_all()`, `Cache.properties`, `Cache.owners`, etc. |
| `modules.Models` | All dataclasses: Property, Owner, Comparable, Lead, PhoneMapping, etc. |
| `modules.WebManager` | `DriverManager` — Selenium + undetected-chromedriver |
| `modules.AddressParser` | `parse_address(addr)` → ParsedAddress, `get_city(addr)` |
| `modules.LatLong` | `call_google_maps_api(address)` → lat/long |
| `modules.SQS` | `get_sqs()` → boto3 SQS client |
| `modules.Log` | `logger.log(msg, LogType)` |

## DynamoDB Tables

| Table | Key | GSIs |
|-------|-----|------|
| Properties | account_id (HASH) + county (RANGE) | — |
| Owners | owner_id (HASH) | AssigneeIndex, PhoneIndex, StatusIndex |
| Leads | owner_id (HASH) | AssigneeIndex, PhoneIndex, StatusIndex |
| Comparables | mls_id (HASH) | CountyIndex |
| ComparablesLookup | account_id (HASH) + county (RANGE) | — |
| Voicemails | call_id (HASH) | — |
| PhoneMapping | phone (HASH) | — |
| Agents | email (HASH) | — |
| LeadConversations | conversation_id (HASH) | TwilioPhoneLeadPhoneIndex, OwnerIdLastUpdatedIndex, LeadPhoneIndex |
| LeadTextMessages | conversation_id (HASH) + message_id (RANGE) | — |
