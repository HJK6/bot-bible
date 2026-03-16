# Email

Send and read email via Apple Mail (AppleScript) and Gmail (Google API).

## Google Account Tokens

| Account | Token Path |
|---------|-----------|
| **YOUR_BOT_EMAIL** (Bartimaeus) | `~/.config/google/gmail_token.json` |
| **YOUR_USER_EMAIL** (User) | `~/.config/google/user_gmail_token.json` |
| **YOUR_USER_EMAIL_2** (User) | `~/.config/google/gujju_gmail_token.json` |

Use the appropriate token path depending on which account you need to act as.

## Apple Mail — Send Email

```bash
osascript -e 'tell application "Mail"
    set newMsg to make new outgoing message with properties {subject:"Test from Bartimaeus", content:"Hello from the agent!", visible:false}
    tell newMsg
        make new to recipient at end of to recipients with properties {address:"recipient@example.com"}
    end tell
    send newMsg
end tell'
```

## Apple Mail — Send with CC/BCC

```bash
osascript -e 'tell application "Mail"
    set newMsg to make new outgoing message with properties {subject:"Meeting Update", content:"See you Thursday.", visible:false}
    tell newMsg
        make new to recipient at end of to recipients with properties {address:"alice@example.com"}
        make new cc recipient at end of cc recipients with properties {address:"bob@example.com"}
        make new bcc recipient at end of bcc recipients with properties {address:"secret@example.com"}
    end tell
    send newMsg
end tell'
```

## Apple Mail — Send to Contact by Name

```bash
# Step 1: Resolve email from Contacts
EMAIL=$(osascript -e 'tell application "Contacts"
    set thePerson to first person whose name is "John Smith"
    get value of first email of thePerson
end tell')

# Step 2: Send
osascript -e "tell application \"Mail\"
    set newMsg to make new outgoing message with properties {subject:\"Hello\", content:\"Message body here.\", visible:false}
    tell newMsg
        make new to recipient at end of to recipients with properties {address:\"${EMAIL}\"}
    end tell
    send newMsg
end tell"
```

## Apple Mail — Read Recent Inbox Messages

```bash
osascript -e 'tell application "Mail"
    set inboxMsgs to messages of inbox
    set output to ""
    repeat with i from 1 to (count of inboxMsgs)
        if i > 20 then exit repeat
        set msg to item i of inboxMsgs
        set output to output & "From: " & (sender of msg) & " | Subject: " & (subject of msg) & " | Date: " & (date received of msg as text) & linefeed
    end repeat
    return output
end tell'
```

## Apple Mail — Read a Specific Message Body

```bash
osascript -e 'tell application "Mail"
    set msg to first message of inbox whose subject contains "Invoice"
    return (content of msg)
end tell'
```

## Apple Mail — Search Messages

```bash
osascript -e 'tell application "Mail"
    set results to (messages of inbox whose sender contains "amazon")
    set output to ""
    repeat with msg in results
        set output to output & (subject of msg) & " | " & (date received of msg as text) & linefeed
    end repeat
    return output
end tell'
```

## Apple Mail — List Mailboxes

```bash
osascript -e 'tell application "Mail"
    set output to ""
    repeat with acct in accounts
        set acctName to name of acct
        repeat with mb in mailboxes of acct
            set output to output & acctName & "/" & (name of mb) & linefeed
        end repeat
    end repeat
    return output
end tell'
```

## Apple Mail — Count Unread

```bash
osascript -e 'tell application "Mail" to return unread count of inbox'
```

---

## Gmail — Python (Google API)

Requires `credentials.json` at `/Users/bartimaeus/.config/google/credentials.json` and token stored at `/Users/bartimaeus/.config/google/gmail_token.json`.

```python
import os, base64
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CREDS_PATH = os.path.expanduser("~/.config/google/credentials.json")
TOKEN_PATH = os.path.expanduser("~/.config/google/gmail_token.json")

def get_gmail_service():
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
    return build("gmail", "v1", credentials=creds)

def send_email(to: str, subject: str, body: str):
    service = get_gmail_service()
    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()

def list_messages(query: str = "is:inbox", max_results: int = 10) -> list:
    service = get_gmail_service()
    results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = results.get("messages", [])
    out = []
    for m in messages:
        msg = service.users().messages().get(userId="me", id=m["id"], format="metadata",
              metadataHeaders=["From", "Subject", "Date"]).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        out.append({"id": m["id"], "from": headers.get("From"), "subject": headers.get("Subject"),
                     "date": headers.get("Date"), "snippet": msg.get("snippet")})
    return out

def read_message(msg_id: str) -> dict:
    service = get_gmail_service()
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    # Extract plain text body
    body = ""
    parts = msg["payload"].get("parts", [])
    if parts:
        for part in parts:
            if part["mimeType"] == "text/plain":
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode()
                break
    elif msg["payload"].get("body", {}).get("data"):
        body = base64.urlsafe_b64decode(msg["payload"]["body"]["data"]).decode()
    return {"from": headers.get("From"), "to": headers.get("To"), "subject": headers.get("Subject"),
            "date": headers.get("Date"), "body": body}
```

### Gmail Quick Examples

```python
# Send
send_email("alice@example.com", "Hello", "Message body here.")

# List recent inbox
for m in list_messages("is:inbox is:unread", max_results=5):
    print(f"{m['from']} — {m['subject']}")

# Read full message
msg = read_message("18e1a2b3c4d5e6f7")
print(msg["body"])

# Search
for m in list_messages("from:amazon subject:order", max_results=10):
    print(m["snippet"])
```

## Notes

- Apple Mail must be configured with at least one account and signed in
- Apple Mail sends from the default account unless specified
- Gmail API requires OAuth consent screen setup (see Google setup below)
- Gmail `query` uses the same syntax as the Gmail search box
- First Gmail run opens a browser for OAuth — subsequent runs use the cached token
- Required pip packages: `google-auth google-auth-oauthlib google-api-python-client`
