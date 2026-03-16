# Calendar

Read and create calendar events via Apple Calendar (AppleScript) and Google Calendar (Google API).

## Google Account Tokens

| Account | Token Path |
|---------|-----------|
| **YOUR_BOT_EMAIL** (Bartimaeus) | `~/.config/google/calendar_token.json` |
| **YOUR_USER_EMAIL** (User) | `~/.config/google/user_calendar_token.json` |
| **YOUR_USER_EMAIL_2** (User) | `~/.config/google/gujju_calendar_token.json` |

Use the appropriate token path depending on which account you need to act as.

## Apple Calendar — List Today's Events

```bash
osascript -e 'tell application "Calendar"
    set today to current date
    set time of today to 0
    set tomorrow to today + (1 * days)
    set output to ""
    repeat with cal in calendars
        set evts to (every event of cal whose start date >= today and start date < tomorrow)
        repeat with e in evts
            set output to output & (summary of e) & " | " & (start date of e as text) & " - " & (end date of e as text) & " | " & (name of cal) & linefeed
        end repeat
    end repeat
    return output
end tell'
```

## Apple Calendar — List Events for Next N Days

```bash
osascript -e 'tell application "Calendar"
    set today to current date
    set time of today to 0
    set endDate to today + (7 * days)
    set output to ""
    repeat with cal in calendars
        set evts to (every event of cal whose start date >= today and start date < endDate)
        repeat with e in evts
            set output to output & (summary of e) & " | " & (start date of e as text) & " - " & (end date of e as text) & " | " & (name of cal) & linefeed
        end repeat
    end repeat
    return output
end tell'
```

## Apple Calendar — Create an Event

```bash
osascript -e 'tell application "Calendar"
    tell calendar "Home"
        set startDate to (current date)
        set time of startDate to (14 * hours)
        set endDate to startDate + (1 * hours)
        make new event with properties {summary:"Meeting with Alice", start date:startDate, end date:endDate, location:"Coffee shop"}
    end tell
end tell'
```

## Apple Calendar — Create Event on Specific Date

```bash
osascript -e 'tell application "Calendar"
    tell calendar "Home"
        set startDate to date "February 15, 2026 at 2:00:00 PM"
        set endDate to date "February 15, 2026 at 3:00:00 PM"
        make new event with properties {summary:"Team Standup", start date:startDate, end date:endDate, description:"Weekly sync"}
    end tell
end tell'
```

## Apple Calendar — Create All-Day Event

```bash
osascript -e 'tell application "Calendar"
    tell calendar "Home"
        set startDate to date "March 1, 2026 12:00:00 AM"
        set endDate to date "March 2, 2026 12:00:00 AM"
        make new event with properties {summary:"Company Holiday", start date:startDate, end date:endDate, allday event:true}
    end tell
end tell'
```

## Apple Calendar — List Calendars

```bash
osascript -e 'tell application "Calendar"
    set output to ""
    repeat with cal in calendars
        set output to output & (name of cal) & " (" & (uid of cal) & ")" & linefeed
    end repeat
    return output
end tell'
```

## Apple Calendar — Delete Event by Title

```bash
osascript -e 'tell application "Calendar"
    repeat with cal in calendars
        set evts to (every event of cal whose summary is "Meeting with Alice")
        repeat with e in evts
            delete e
        end repeat
    end repeat
end tell'
```

## Apple Calendar — Search Events

```bash
osascript -e 'tell application "Calendar"
    set output to ""
    repeat with cal in calendars
        set evts to (every event of cal whose summary contains "standup")
        repeat with e in evts
            set output to output & (summary of e) & " | " & (start date of e as text) & " | " & (name of cal) & linefeed
        end repeat
    end repeat
    return output
end tell'
```

---

## Google Calendar — Python (Google API)

Requires `credentials.json` at `/Users/bartimaeus/.config/google/credentials.json` and token stored at `/Users/bartimaeus/.config/google/calendar_token.json`.

```python
import os
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDS_PATH = os.path.expanduser("~/.config/google/credentials.json")
TOKEN_PATH = os.path.expanduser("~/.config/google/calendar_token.json")

def get_calendar_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)

def list_events(days: int = 7, max_results: int = 20, calendar_id: str = "primary") -> list:
    service = get_calendar_service()
    now = datetime.now(timezone.utc).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    result = service.events().list(
        calendarId=calendar_id, timeMin=now, timeMax=end,
        maxResults=max_results, singleEvents=True, orderBy="startTime"
    ).execute()
    events = result.get("items", [])
    out = []
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date"))
        end_t = e["end"].get("dateTime", e["end"].get("date"))
        out.append({"id": e["id"], "summary": e.get("summary", "(no title)"),
                     "start": start, "end": end_t, "location": e.get("location"),
                     "description": e.get("description")})
    return out

def create_event(summary: str, start: str, end: str, description: str = None,
                 location: str = None, calendar_id: str = "primary", timezone: str = "America/Chicago") -> dict:
    """Create event. start/end as ISO strings like '2026-02-15T14:00:00'."""
    service = get_calendar_service()
    event = {
        "summary": summary,
        "start": {"dateTime": start, "timeZone": timezone},
        "end": {"dateTime": end, "timeZone": timezone},
    }
    if description:
        event["description"] = description
    if location:
        event["location"] = location
    return service.events().insert(calendarId=calendar_id, body=event).execute()

def create_allday_event(summary: str, date: str, end_date: str = None,
                        calendar_id: str = "primary") -> dict:
    """Create all-day event. date as 'YYYY-MM-DD'."""
    service = get_calendar_service()
    event = {
        "summary": summary,
        "start": {"date": date},
        "end": {"date": end_date or date},
    }
    return service.events().insert(calendarId=calendar_id, body=event).execute()

def delete_event(event_id: str, calendar_id: str = "primary"):
    service = get_calendar_service()
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

def list_calendars() -> list:
    service = get_calendar_service()
    result = service.calendarList().list().execute()
    return [{"id": c["id"], "summary": c["summary"]} for c in result.get("items", [])]
```

### Google Calendar Quick Examples

```python
# List next 7 days
for e in list_events(days=7):
    print(f"{e['start']} — {e['summary']}")

# Create event
create_event("Lunch with Bob", "2026-02-15T12:00:00", "2026-02-15T13:00:00",
             location="Torchy's Tacos")

# All-day event
create_allday_event("PTO Day", "2026-03-01", "2026-03-02")

# List calendars
for c in list_calendars():
    print(f"{c['summary']} ({c['id']})")

# Delete
delete_event("abc123eventid")
```

## Notes

- Apple Calendar must be open (launches silently in background)
- Calendar names are case-sensitive in AppleScript — list calendars first to get exact names
- Default timezone for Google Calendar is `America/Chicago` — change as needed
- Google Calendar `primary` is the user's default calendar
- First Google Calendar run opens a browser for OAuth — subsequent runs use the cached token
- All-day events in Google use `date` (YYYY-MM-DD), timed events use `dateTime` (ISO 8601)
- Required pip packages: `google-auth google-auth-oauthlib google-api-python-client`
