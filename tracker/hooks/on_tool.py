#!/usr/bin/env python3
"""PostToolUse hook — log tool executions to dashboard."""
import sys
import json

sys.path.insert(0, "/Users/bartimaeus/agent-dashboard/tracker/hooks")
from shared import ensure_registered, log_message, update_task

def main():
    try:
        input_data = json.load(sys.stdin)
        ensure_registered()

        tool = input_data.get("tool_name", "unknown")
        tool_input = input_data.get("tool_input", {})

        # Build a human-readable summary
        if tool == "Bash":
            cmd = tool_input.get("command", "")[:200]
            desc = tool_input.get("description", "")
            summary = desc if desc else cmd
            log_message(f"Bash: {summary}", tool=tool)
        elif tool in ("Read", "Glob", "Grep"):
            path = tool_input.get("file_path", "") or tool_input.get("pattern", "") or tool_input.get("path", "")
            log_message(f"{tool}: {path}", tool=tool)
        elif tool in ("Edit", "Write"):
            path = tool_input.get("file_path", "")
            log_message(f"{tool}: {path}", tool=tool)
        elif tool == "Task":
            desc = tool_input.get("description", "")
            log_message(f"Subagent: {desc}", tool=tool)
        elif tool == "WebFetch":
            url = tool_input.get("url", "")
            log_message(f"WebFetch: {url}", tool=tool)
        elif tool == "WebSearch":
            query = tool_input.get("query", "")
            log_message(f"WebSearch: {query}", tool=tool)
        else:
            log_message(f"{tool}", tool=tool)

        update_task(f"Using {tool}")
        print(json.dumps({}))
    except Exception:
        print(json.dumps({}))
    sys.exit(0)

if __name__ == "__main__":
    main()
