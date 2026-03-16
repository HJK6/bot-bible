#!/usr/bin/env python3
"""Stop hook — log assistant response to chat and update heartbeat."""
import sys
import json

sys.path.insert(0, "/Users/bartimaeus/agent-dashboard/tracker/hooks")
from shared import ensure_registered, log_message, log_chat, update_task

def is_tool_noise(text):
    """Detect concatenated tool-call orchestration text that shouldn't be logged to chat."""
    tool_patterns = ["Bash(", "Read(", "Edit(", "Write(", "Grep(", "Glob(", "Agent(", "Update("]
    hits = sum(1 for p in tool_patterns if p in text)
    if hits >= 2:
        return True
    # Concatenated words without spaces (e.g. "Letmefixtheroutetype")
    if len(text) > 100 and text.count(" ") < len(text) / 15:
        return True
    return False

def main():
    try:
        input_data = json.load(sys.stdin)
        ensure_registered()

        response = input_data.get("last_assistant_message", "")
        stop_reason = input_data.get("stop_reason", "")

        if response and not is_tool_noise(response):
            short = response[:2000] + ("..." if len(response) > 2000 else "")
            log_chat(short, direction="outbound", sender="claude")

        # Only mark completed if session is truly ending
        if stop_reason == "session_end":
            from shared import mark_completed
            mark_completed()

        print(json.dumps({}))
    except Exception:
        print(json.dumps({}))
    sys.exit(0)

if __name__ == "__main__":
    main()
