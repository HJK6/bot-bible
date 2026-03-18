#!/usr/bin/env python3
"""UserPromptSubmit hook — auto-register Claude Code and log user messages."""
import os
import sys
import json
import time
sys.path.insert(0, "/Users/YOUR_USERNAME/agent-dashboard/tracker/hooks")
from shared import ensure_registered, log_message, log_chat, update_task, is_tmux, needs_title, generate_title, set_title

def main():
    try:
        input_data = json.load(sys.stdin)
        ensure_registered()
        prompt = input_data.get("prompt", "")
        if prompt and not prompt.strip().startswith("<task-notification>"):
            # Truncate long prompts for the log
            short = prompt[:500] + ("..." if len(prompt) > 500 else "")
            log_message(f"User: {short}")
            update_task(f"Processing: {prompt[:100]}")
            # Log to chat so messages appear in the app Chat tab
            # Skip if orchestrator already logged this inbound message
            from shared import get_agent_id as _get_aid
            _flag = f"/tmp/orch_sent_{_get_aid()}"
            _skip = os.environ.get("ORCHESTRATOR_MANAGED")
            if not _skip and os.path.exists(_flag):
                try:
                    _age = time.time() - float(open(_flag).read().strip())
                    if _age < 30:
                        _skip = True
                    os.unlink(_flag)
                except Exception:
                    pass
            if not _skip:
                log_chat(short, direction="inbound", sender="user")
            # Generate a human-readable title on the first prompt
            if needs_title():
                title = generate_title(prompt)
                if title:
                    set_title(title)
        print(json.dumps({}))
    except Exception:
        print(json.dumps({}))
    sys.exit(0)

if __name__ == "__main__":
    main()
