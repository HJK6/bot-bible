#!/usr/bin/env python3
"""Notification hook — log Claude's responses to app chat."""
import sys
import json

sys.path.insert(0, "/Users/bartimaeus/agent-dashboard/tracker/hooks")
from shared import ensure_registered, log_chat

def main():
    try:
        input_data = json.load(sys.stdin)
        ensure_registered()
        message = input_data.get("message", "")
        if message and not message.strip().startswith("<task-notification>") and "waiting for your input" not in message.lower():
            short = message[:2000] + ("..." if len(message) > 2000 else "")
            log_chat(short, direction="outbound", sender="claude")
        print(json.dumps({}))
    except Exception:
        print(json.dumps({}))
    sys.exit(0)

if __name__ == "__main__":
    main()
