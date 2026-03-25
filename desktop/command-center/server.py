#!/usr/bin/env python3
"""Command Center — web dashboard for tmux session management.

Integrates with DynamoDB AgentTracker for agent titles, trash/restore,
matching the Tmux Sessions desktop app functionality.
"""

import json
import re
import subprocess
import os
import signal
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from datetime import datetime, timezone

PORT = 7777
TMUX = "/opt/homebrew/bin/tmux"

# ── DynamoDB helpers (matches Tmux Sessions app) ────────────────────────

_dynamo = None

def get_dynamo():
    global _dynamo
    if _dynamo is None:
        import boto3
        _dynamo = boto3.resource("dynamodb", region_name="us-east-1")
    return _dynamo


def get_agent_by_tmux(tmux_session_name):
    try:
        from boto3.dynamodb.conditions import Attr
        tracker = get_dynamo().Table("AgentTracker")
        resp = tracker.scan(
            FilterExpression=Attr("tmux_session").eq(tmux_session_name),
            ProjectionExpression="agent_id, title, agent_name, #s",
            ExpressionAttributeNames={"#s": "status"},
        )
        items = resp.get("Items", [])
        return items[0] if items else None
    except Exception:
        return None


def get_all_agents_by_tmux(session_names):
    """Batch lookup: return {tmux_session_name: agent_dict}."""
    result = {}
    try:
        from boto3.dynamodb.conditions import Attr
        tracker = get_dynamo().Table("AgentTracker")
        # Scan for all non-trashed agents that have a tmux_session
        resp = tracker.scan(
            FilterExpression=Attr("status").ne("trashed") & Attr("tmux_session").exists(),
            ProjectionExpression="agent_id, title, agent_name, tmux_session, #s",
            ExpressionAttributeNames={"#s": "status"},
        )
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp = tracker.scan(
                FilterExpression=Attr("status").ne("trashed") & Attr("tmux_session").exists(),
                ProjectionExpression="agent_id, title, agent_name, tmux_session, #s",
                ExpressionAttributeNames={"#s": "status"},
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            items.extend(resp.get("Items", []))
        for item in items:
            ts = item.get("tmux_session", "")
            if ts in session_names:
                result[ts] = item
    except Exception:
        pass
    return result


def rename_agent(agent_id, new_title):
    try:
        tracker = get_dynamo().Table("AgentTracker")
        tracker.update_item(
            Key={"agent_id": agent_id},
            UpdateExpression="SET title = :t",
            ExpressionAttributeValues={":t": new_title},
        )
        return True
    except Exception:
        return False


def trash_agent_by_tmux(tmux_session_name):
    try:
        from boto3.dynamodb.conditions import Attr
        tracker = get_dynamo().Table("AgentTracker")
        resp = tracker.scan(
            FilterExpression=Attr("tmux_session").eq(tmux_session_name),
            ProjectionExpression="agent_id",
        )
        items = resp.get("Items", [])
        if not items:
            return False
        now = datetime.now(timezone.utc).isoformat()
        tracker.update_item(
            Key={"agent_id": items[0]["agent_id"]},
            UpdateExpression="SET #s = :s, trashed_at = :t, #h = :h",
            ExpressionAttributeValues={":s": "trashed", ":t": now, ":h": True},
            ExpressionAttributeNames={"#s": "status", "#h": "hidden"},
        )
        return True
    except Exception:
        return False


def get_trashed_sessions():
    try:
        from boto3.dynamodb.conditions import Attr
        tracker = get_dynamo().Table("AgentTracker")
        resp = tracker.scan(
            FilterExpression=Attr("status").eq("trashed"),
            ProjectionExpression="agent_id, tmux_session, title, trashed_at",
        )
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp = tracker.scan(
                FilterExpression=Attr("status").eq("trashed"),
                ProjectionExpression="agent_id, tmux_session, title, trashed_at",
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            items.extend(resp.get("Items", []))
        return items
    except Exception:
        return []


def restore_agent(agent_id):
    try:
        tracker = get_dynamo().Table("AgentTracker")
        tracker.update_item(
            Key={"agent_id": agent_id},
            UpdateExpression="SET #s = :s, #h = :h REMOVE trashed_at, hidden_at",
            ExpressionAttributeValues={":s": "idle", ":h": False},
            ExpressionAttributeNames={"#s": "status", "#h": "hidden"},
        )
        return True
    except Exception:
        return False


# ── Tmux helpers ────────────────────────────────────────────────────────

def tmux(*args):
    try:
        r = subprocess.run([TMUX] + list(args), capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception as e:
        return str(e)


_title_cache = {}  # {tmux_session_name: generated_title}


def _summarize_title(msg, session_name=None):
    """Use Claude Code CLI (haiku) to generate a short title from a user prompt."""
    if session_name and session_name in _title_cache:
        return _title_cache[session_name]
    import json as _json
    try:
        r = subprocess.run(
            [os.path.join(os.environ["HOME"], ".local/bin/claude"),
             "-p", f"Summarize into a concise 3-6 word title (no quotes, no markdown, no bold): '{msg[:200]}'",
             "--output-format", "json", "--no-session-persistence", "--model", "haiku"],
            capture_output=True, text=True, timeout=15,
            stdin=subprocess.DEVNULL,
        )
        if r.returncode == 0 and r.stdout.strip():
            data = _json.loads(r.stdout)
            title = data.get("result", "").strip().strip("*\"'")
            if title and len(title) < 60:
                if session_name:
                    _title_cache[session_name] = title
                return title
    except Exception:
        pass
    # Fallback: simple truncation
    clean = msg.strip()
    if len(clean) <= 45:
        result = clean[0].upper() + clean[1:] if clean else clean
    else:
        truncated = clean[:45].rsplit(" ", 1)[0]
        result = truncated.rstrip(".,;:- ") + "..."
    if session_name:
        _title_cache[session_name] = result
    return result


def sanitize_tmux_name(title):
    """Make a title safe for use as a tmux session name."""
    # Replace dots, colons, and other problematic chars with hyphens
    name = re.sub(r'[.:!@#$%^&*()\[\]{}/\\|<>"\';,?`~\s]+', '-', title)
    # Collapse multiple hyphens, strip leading/trailing
    name = re.sub(r'-+', '-', name).strip('-')
    return name[:60] if name else ""


def sync_tmux_names(session_names, agents):
    """Rename tmux sessions to match their DynamoDB titles.

    Updates the AgentTracker tmux_session field when renamed.
    Returns updated session_names set and name mapping {old: new}.
    """
    renames = {}
    for old_name in list(session_names):
        agent = agents.get(old_name)
        if not agent:
            continue
        title = agent.get("title", "")
        if not title:
            continue
        new_name = sanitize_tmux_name(title)
        if not new_name or new_name == old_name:
            continue
        # Check if target name already exists
        existing = tmux("has-session", "-t", new_name)
        # has-session returns empty on success, error message on failure
        check = subprocess.run([TMUX, "has-session", "-t", new_name],
                               capture_output=True, text=True)
        if check.returncode == 0:
            # Name collision — skip
            continue
        # Rename the tmux session
        result = subprocess.run([TMUX, "rename-session", "-t", old_name, new_name],
                                capture_output=True, text=True)
        if result.returncode == 0:
            renames[old_name] = new_name
            # Update DynamoDB to track the new tmux session name
            try:
                tracker = get_dynamo().Table("AgentTracker")
                tracker.update_item(
                    Key={"agent_id": agent["agent_id"]},
                    UpdateExpression="SET tmux_session = :ts",
                    ExpressionAttributeValues={":ts": new_name},
                )
            except Exception:
                pass
    return renames


def get_sessions():
    raw = tmux("list-sessions", "-F",
               "#{session_name}|#{session_attached}|#{session_created}|#{session_windows}|#{session_activity}")
    if not raw:
        return []

    session_names = set()
    raw_sessions = []
    for line in raw.strip().split("\n"):
        parts = line.split("|")
        if len(parts) < 5:
            continue
        name = parts[0]
        if name in ("cmdcenter", "quad-view"):
            continue
        session_names.add(name)
        raw_sessions.append(parts)

    # Batch lookup agent titles from DynamoDB
    agents = get_all_agents_by_tmux(session_names)

    # Sync: rename tmux sessions to match DynamoDB titles
    renames = sync_tmux_names(session_names, agents)
    if renames:
        # Update raw_sessions with new names and refresh agents map
        for i, parts in enumerate(raw_sessions):
            if parts[0] in renames:
                raw_sessions[i] = [renames[parts[0]]] + parts[1:]
        session_names = {renames.get(n, n) for n in session_names}
        agents = get_all_agents_by_tmux(session_names)

    # Also get trashed session names to separate them
    trashed_agents = get_trashed_sessions()
    trashed_tmux = {a.get("tmux_session", "") for a in trashed_agents if a.get("tmux_session")}

    # Dedup: when sync_tmux_names renames an agent-* session, the orchestrator may
    # have already spawned a second tmux session with the same agent-* prefix.
    # Hide orphaned agent-* sessions that have no AgentTracker entry when a
    # renamed session (with an entry) was created within 30 seconds.
    renamed_times = []
    for parts in raw_sessions:
        name = parts[0]
        if not name.startswith("agent-") and agents.get(name):
            renamed_times.append(int(parts[2]))

    sessions = []
    trashed = []
    for parts in raw_sessions:
        name = parts[0]

        # Skip orphaned agent-* sessions (no DB entry, created near a renamed session)
        if name.startswith("agent-") and not agents.get(name):
            created = int(parts[2])
            if any(abs(created - rt) < 30 for rt in renamed_times):
                continue

        if name.startswith("claude-"):
            stype = "claude"
        elif name.startswith("agent-"):
            stype = "agent"
        else:
            stype = "other"

        # Agent title from DynamoDB
        agent = agents.get(name)
        agent_title = agent.get("title", "") if agent else ""
        agent_id = agent.get("agent_id", "") if agent else ""

        # Clean up legacy "tmux:session:window" titles — extract the readable last part
        if agent_title.startswith("tmux:"):
            parts_t = agent_title.split(":")
            readable = parts_t[-1].strip() if len(parts_t) > 1 else ""
            if readable and not re.match(r'^[\d.]+$', readable):
                agent_title = readable
            else:
                agent_title = ""  # fall through to window name fallback

        # Reject version-only titles (e.g. "2.1.81")
        if agent_title and re.match(r'^[\d.\s]+$', agent_title.strip()):
            agent_title = ""

        # Fallback: window name
        if not agent_title:
            win_out = tmux("list-windows", "-t", name, "-F", "#{window_name}")
            if win_out:
                wname = win_out.split("\n")[0]
                if wname != name and wname not in ('zsh', 'bash', 'fish') and not re.match(r'^\d+[\d.]*$', wname):
                    agent_title = wname

        # Fallback: extract first user message from Claude Code pane as topic
        if not agent_title:
            # Return cached title immediately if available
            if name in _title_cache:
                agent_title = _title_cache[name]
            else:
                try:
                    pane_text = tmux("capture-pane", "-t", name, "-p", "-J", "-S", "-200")
                    for pline in pane_text.split("\n"):
                        stripped = pline.strip()
                        if stripped.startswith("❯") or stripped.startswith(">"):
                            msg = re.sub(r'^[❯>]\s*', '', stripped).strip()
                            if msg and len(msg) > 3 and not re.match(r'^[\d\s.]+$', msg):
                                # Generate title async; use truncated version for now
                                short = msg[:45].rsplit(" ", 1)[0].rstrip(".,;:- ")
                                agent_title = short + ("..." if len(msg) > 45 else "")
                                # Fire background thread to generate AI title
                                _msg, _name = msg, name
                                threading.Thread(
                                    target=_summarize_title,
                                    args=(_msg,),
                                    kwargs={"session_name": _name},
                                    daemon=True,
                                ).start()
                                break
                except Exception:
                    pass

        # Final fallback: clean up the session name itself
        if not agent_title:
            clean = re.sub(r'^(tmux-)+', '', name)
            clean = re.sub(r'^claude-\d+(-\d+)?-?', '', clean)
            clean = re.sub(r'-\d+-\d+-\d+$', '', clean)
            clean = clean.replace('-', ' ').strip()
            # Reject if it's just numbers/dots (version strings like "2 1 81")
            if clean and not re.match(r'^[\d\s.]+$', clean):
                agent_title = clean

        # Preview: last non-empty line
        preview = ""
        try:
            cap = tmux("capture-pane", "-t", name, "-p", "-J", "-S", "-3")
            lines = [l.strip() for l in cap.split("\n") if l.strip()]
            preview = lines[-1][:120] if lines else ""
        except Exception:
            pass

        entry = {
            "name": name,
            "title": agent_title,
            "display_name": agent_title or (name.replace('-', ' ') if not re.match(r'^[\d\s.-]+$', name) else "Claude Session"),
            "type": stype,
            "attached": parts[1] == "1",
            "created": int(parts[2]),
            "created_fmt": datetime.fromtimestamp(int(parts[2])).strftime("%b %d %H:%M"),
            "windows": int(parts[3]),
            "last_activity": int(parts[4]),
            "preview": preview,
            "agent_id": agent_id,
        }

        if name in trashed_tmux:
            # Find trashed_at time
            ta = next((a for a in trashed_agents if a.get("tmux_session") == name), None)
            entry["trashed_at"] = ta.get("trashed_at", "") if ta else ""
            entry["agent_id"] = ta.get("agent_id", entry["agent_id"]) if ta else entry["agent_id"]
            trashed.append(entry)
        else:
            sessions.append(entry)

    sessions.sort(key=lambda s: s["created"], reverse=True)
    trashed.sort(key=lambda s: s["created"], reverse=True)
    return {"active": sessions, "trashed": trashed}


def get_usage():
    """Get Claude Code usage from BotTracker DynamoDB table."""
    try:
        from decimal import Decimal
        tracker = get_dynamo().Table("BotTracker")
        item = tracker.get_item(Key={"bot_id": "system:claude-usage"}).get("Item")
        if not item:
            return {"status": "no_data"}
        # Convert Decimals for JSON serialization
        result = {}
        for k, v in item.items():
            if isinstance(v, Decimal):
                result[k] = int(v) if v == int(v) else float(v)
            else:
                result[k] = v
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


def open_session_in_iterm(session_name):
    script = f'''
    tell application "iTerm"
        activate
        tell current window
            create tab with default profile command "/opt/homebrew/bin/tmux attach-session -t '{session_name}'"
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", script], capture_output=True)


def open_quad_in_iterm(session_names):
    if not session_names:
        return
    tmux("kill-session", "-t", "quad-view")
    tmux("new-session", "-d", "-s", "quad-view",
         f"{TMUX} attach-session -t '{session_names[0]}' -r")
    for s in session_names[1:4]:
        tmux("split-window", "-t", "quad-view",
             f"{TMUX} attach-session -t '{s}' -r")
    tmux("select-layout", "-t", "quad-view", "tiled")
    script = '''
    tell application "iTerm"
        activate
        create window with default profile command "/opt/homebrew/bin/tmux attach-session -t quad-view"
    end tell
    '''
    subprocess.run(["osascript", "-e", script], capture_output=True)


# ── HTTP Handler ────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def respond_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def respond_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/sessions":
            self.respond_json(get_sessions())
        elif path == "/api/usage":
            self.respond_json(get_usage())
        elif path == "/":
            self.respond_html(DASHBOARD_HTML)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        content_len = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_len)) if content_len else {}

        if path == "/api/open":
            name = body.get("session")
            if name:
                open_session_in_iterm(name)
                self.respond_json({"ok": True})
            else:
                self.respond_json({"error": "no session"}, 400)

        elif path == "/api/quad":
            sessions = body.get("sessions", [])
            if not sessions:
                data = get_sessions()
                sessions = [s["name"] for s in data["active"] if s["type"] in ("claude", "agent")][:4]
            open_quad_in_iterm(sessions)
            self.respond_json({"ok": True})

        elif path == "/api/trash":
            name = body.get("session")
            if name:
                trashed = trash_agent_by_tmux(name)
                if not trashed:
                    tmux("kill-session", "-t", name)
                self.respond_json({"ok": True, "dynamo_trashed": trashed})
            else:
                self.respond_json({"error": "no session"}, 400)

        elif path == "/api/kill":
            name = body.get("session")
            agent_id = body.get("agent_id", "")
            if name:
                tmux("kill-session", "-t", name)
                # Also nuke DynamoDB data
                if agent_id:
                    try:
                        dynamo = get_dynamo()
                        from boto3.dynamodb.conditions import Key
                        dynamo.Table("AgentTracker").delete_item(Key={"agent_id": agent_id})
                        for tbl_name in ("AgentLogs", "AgentChat"):
                            try:
                                tbl = dynamo.Table(tbl_name)
                                resp = tbl.query(KeyConditionExpression=Key("agent_id").eq(agent_id))
                                with tbl.batch_writer() as batch:
                                    for item in resp.get("Items", []):
                                        batch.delete_item(Key={"agent_id": agent_id, "timestamp": item["timestamp"]})
                            except Exception:
                                pass
                    except Exception:
                        pass
                self.respond_json({"ok": True})
            else:
                self.respond_json({"error": "no session"}, 400)

        elif path == "/api/restore":
            agent_id = body.get("agent_id")
            if agent_id:
                ok = restore_agent(agent_id)
                self.respond_json({"ok": ok})
            else:
                self.respond_json({"error": "no agent_id"}, 400)

        elif path == "/api/rename":
            session = body.get("session")
            new_title = body.get("new_name")
            if session and new_title:
                # Update DynamoDB title
                agent = get_agent_by_tmux(session)
                if agent:
                    rename_agent(agent["agent_id"], new_title)
                # Also rename the tmux session to match
                new_tmux_name = sanitize_tmux_name(new_title)
                if new_tmux_name and new_tmux_name != session:
                    check = subprocess.run([TMUX, "has-session", "-t", new_tmux_name],
                                           capture_output=True, text=True)
                    if check.returncode != 0:  # name not taken
                        subprocess.run([TMUX, "rename-session", "-t", session, new_tmux_name],
                                       capture_output=True, text=True)
                        # Update DynamoDB tmux_session field
                        if agent:
                            try:
                                tracker = get_dynamo().Table("AgentTracker")
                                tracker.update_item(
                                    Key={"agent_id": agent["agent_id"]},
                                    UpdateExpression="SET tmux_session = :ts",
                                    ExpressionAttributeValues={":ts": new_tmux_name},
                                )
                            except Exception:
                                pass
                self.respond_json({"ok": True})
            else:
                self.respond_json({"error": "missing params"}, 400)

        elif path == "/api/new":
            name = body.get("name", "")
            if name:
                tmux("new-session", "-d", "-s", name)
            else:
                tmux("new-session", "-d")
            self.respond_json({"ok": True})

        elif path == "/api/cleanup":
            killed = []
            data = get_sessions()
            for s in data["active"]:
                if s["attached"]:
                    continue
                pane_pid = tmux("list-panes", "-t", s["name"], "-F", "#{pane_pid}")
                if pane_pid:
                    r = subprocess.run(["pgrep", "-P", pane_pid.split("\n")[0]],
                                       capture_output=True, text=True)
                    if not r.stdout.strip():
                        trash_agent_by_tmux(s["name"])
                        tmux("kill-session", "-t", s["name"])
                        killed.append(s["display_name"])
            self.respond_json({"ok": True, "killed": killed})

        else:
            self.send_response(404)
            self.end_headers()


# ── Dashboard HTML ──────────────────────────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Command Center</title>
<style>
  :root {
    --bg: #1a1b26;
    --bg2: #24283b;
    --bg3: #292e42;
    --bg-trash: #1e1e2e;
    --fg: #a9b1d6;
    --fg-dim: #565f89;
    --blue: #7aa2f7;
    --green: #9ece6a;
    --red: #f7768e;
    --yellow: #e0af68;
    --purple: #bb9af7;
    --cyan: #7dcfff;
    --border: #3b4261;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--fg);
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    min-height: 100vh;
  }

  .header {
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    padding: 20px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .header h1 { font-size: 20px; font-weight: 700; color: var(--blue); letter-spacing: 1px; }

  .header-stats { display: flex; gap: 20px; font-size: 13px; color: var(--fg-dim); }
  .header-stats .stat-val { color: var(--fg); font-weight: 600; }

  .toolbar {
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    padding: 12px 32px;
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }

  .btn {
    padding: 8px 16px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--bg3);
    color: var(--fg);
    font-family: inherit;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .btn:hover { border-color: var(--blue); color: #fff; }
  .btn:active { transform: scale(0.97); }
  .btn-blue { background: var(--blue); color: var(--bg); border-color: var(--blue); }
  .btn-blue:hover { background: #8ab4ff; color: var(--bg); }
  .btn-green { background: var(--green); color: var(--bg); border-color: var(--green); }
  .btn-green:hover { background: #b2e080; color: var(--bg); }
  .btn-red { background: transparent; border-color: var(--red); color: var(--red); }
  .btn-red:hover { background: var(--red); color: var(--bg); }
  .btn-yellow { background: var(--yellow); color: var(--bg); border-color: var(--yellow); }
  .btn-yellow:hover { background: #ecc080; color: var(--bg); }
  .btn-purple { background: transparent; border-color: var(--purple); color: var(--purple); }
  .btn-purple:hover { background: var(--purple); color: var(--bg); }
  .btn-sm { padding: 5px 10px; font-size: 12px; }

  .content { padding: 24px 32px; }

  .session-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
    gap: 14px;
  }

  .session-card {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 18px;
    transition: all 0.15s;
    position: relative;
  }
  .session-card:hover { border-color: var(--blue); }
  .session-card.selected { border-color: var(--yellow); box-shadow: 0 0 0 1px var(--yellow); }

  .session-card .top-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 4px;
    padding-right: 28px;
  }

  .session-display-name { font-weight: 700; font-size: 15px; color: #fff; }

  .session-badge {
    font-size: 10px;
    padding: 2px 7px;
    border-radius: 4px;
    font-weight: 600;
    text-transform: uppercase;
    flex-shrink: 0;
  }
  .badge-claude { background: rgba(122,162,247,0.2); color: var(--blue); }
  .badge-agent { background: rgba(187,154,247,0.2); color: var(--purple); }
  .badge-other { background: rgba(125,207,255,0.2); color: var(--cyan); }

  .session-id {
    font-size: 11px;
    color: var(--fg-dim);
    margin-bottom: 6px;
  }

  .session-meta {
    font-size: 12px;
    color: var(--fg-dim);
    margin-bottom: 10px;
    display: flex;
    gap: 14px;
  }

  .status-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 4px;
    vertical-align: middle;
  }
  .dot-attached { background: var(--green); }
  .dot-detached { background: var(--red); }

  .session-preview {
    font-size: 11px;
    color: var(--fg-dim);
    background: var(--bg);
    padding: 6px 10px;
    border-radius: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 10px;
  }

  .session-actions { display: flex; gap: 6px; flex-wrap: wrap; }

  .select-checkbox {
    position: absolute;
    top: 16px;
    right: 16px;
    width: 18px; height: 18px;
    accent-color: var(--yellow);
    cursor: pointer;
  }

  /* Trash section */
  .trash-section {
    margin-top: 32px;
    border-top: 1px solid var(--border);
    padding-top: 16px;
  }

  .trash-header {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
    padding: 8px 0;
    user-select: none;
  }
  .trash-header:hover .trash-label { color: var(--fg); }
  .trash-label { font-size: 14px; font-weight: 600; color: var(--fg-dim); transition: color 0.15s; }
  .trash-arrow { color: var(--fg-dim); font-size: 12px; }
  .trash-count {
    font-size: 11px;
    background: var(--bg3);
    color: var(--fg-dim);
    padding: 1px 8px;
    border-radius: 10px;
  }

  .trash-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
    gap: 10px;
    margin-top: 12px;
  }

  .trash-card {
    background: var(--bg-trash);
    border: 1px solid #2a2a3a;
    border-radius: 8px;
    padding: 12px 16px;
    opacity: 0.7;
    transition: opacity 0.15s;
  }
  .trash-card:hover { opacity: 1; border-color: var(--border); }
  .trash-card .session-display-name { color: var(--fg-dim); font-size: 14px; }

  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 20px;
    color: var(--fg);
    font-size: 13px;
    z-index: 100;
    animation: fadeIn 0.2s;
    transition: opacity 0.3s;
  }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } }

  .modal-overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.6);
    display: flex; align-items: center; justify-content: center;
    z-index: 200;
  }
  .modal {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 24px;
    min-width: 360px;
  }
  .modal h3 { color: var(--blue); margin-bottom: 16px; font-size: 16px; }
  .modal input {
    width: 100%;
    padding: 8px 12px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--fg);
    font-family: inherit;
    font-size: 14px;
    margin-bottom: 14px;
  }
  .modal input:focus { outline: none; border-color: var(--blue); }
  .modal-actions { display: flex; gap: 8px; justify-content: flex-end; }

  .empty-state { text-align: center; padding: 60px 20px; color: var(--fg-dim); }
  .empty-state h2 { color: var(--fg); margin-bottom: 8px; }
</style>
</head>
<body>

<div class="header">
  <h1>COMMAND CENTER</h1>
  <div class="header-stats">
    <span>Sessions: <span class="stat-val" id="total-count">0</span></span>
    <span>Attached: <span class="stat-val" id="attached-count">0</span></span>
    <span>Claude: <span class="stat-val" id="claude-count">0</span></span>
    <span>Agent: <span class="stat-val" id="agent-count">0</span></span>
  </div>
</div>

<div class="toolbar">
  <button class="btn btn-blue" onclick="quadSelected()">Quad View Selected</button>
  <button class="btn btn-green" onclick="quadRecent()">Quad View (Recent 4)</button>
  <button class="btn" onclick="openAll()">Open All Selected</button>
  <button class="btn" onclick="selectAll()">Select All</button>
  <button class="btn" onclick="selectNone()">Select None</button>
  <div style="flex:1"></div>
  <button class="btn btn-yellow" onclick="showNewModal()">+ New Session</button>
  <button class="btn btn-red" onclick="cleanupDead()">Cleanup Dead</button>
  <button class="btn" onclick="refresh()">Refresh</button>
</div>

<div class="content">
  <div class="session-grid" id="grid"></div>
  <div id="trash-section"></div>
</div>

<div id="modal-container"></div>
<div id="toast-container"></div>

<script>
let data = { active: [], trashed: [] };
let selected = new Set();
let showTrash = false;

async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  return r.json();
}

function toast(msg, duration = 2500) {
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, duration);
}

function showModal(html) {
  document.getElementById('modal-container').innerHTML =
    '<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal">' + html + '</div></div>';
}
function closeModal() { document.getElementById('modal-container').innerHTML = ''; }

async function refresh() {
  data = await api('GET', '/api/sessions');
  render();
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function renderCard(s) {
  const hasTitle = s.title && s.title !== s.name;
  return '<div class="session-card ' + (selected.has(s.name) ? 'selected' : '') + '">' +
    '<input type="checkbox" class="select-checkbox" ' +
      (selected.has(s.name) ? 'checked' : '') +
      ' onchange="toggleSelect(\'' + s.name + '\', this.checked)">' +
    '<div class="top-row">' +
      '<span class="session-display-name">' + escHtml(s.display_name) + '</span>' +
      '<span class="session-badge badge-' + s.type + '">' + s.type + '</span>' +
    '</div>' +
    (hasTitle ? '<div class="session-id">' + escHtml(s.name) + '</div>' : '') +
    '<div class="session-meta">' +
      '<span><span class="status-dot ' + (s.attached ? 'dot-attached' : 'dot-detached') + '"></span>' +
        (s.attached ? 'Attached' : 'Detached') + '</span>' +
      '<span>' + s.created_fmt + '</span>' +
      '<span>' + s.windows + 'W</span>' +
    '</div>' +
    (s.preview ? '<div class="session-preview">' + escHtml(s.preview) + '</div>' : '') +
    '<div class="session-actions">' +
      '<button class="btn btn-sm btn-blue" onclick="openSession(\'' + s.name + '\')">Open</button>' +
      '<button class="btn btn-sm" onclick="showRenameModal(\'' + s.name + '\', \'' + escHtml(s.display_name).replace(/'/g, "\\'") + '\')">Rename</button>' +
      '<button class="btn btn-sm btn-red" onclick="trashSession(\'' + s.name + '\')">Trash</button>' +
    '</div>' +
  '</div>';
}

function render() {
  const active = data.active || [];
  const trashed = data.trashed || [];
  const grid = document.getElementById('grid');
  const trashEl = document.getElementById('trash-section');

  document.getElementById('total-count').textContent = active.length;
  document.getElementById('attached-count').textContent = active.filter(s => s.attached).length;
  document.getElementById('claude-count').textContent = active.filter(s => s.type === 'claude').length;
  document.getElementById('agent-count').textContent = active.filter(s => s.type === 'agent').length;

  if (active.length === 0) {
    grid.innerHTML = '<div class="empty-state"><h2>No active sessions</h2><p>Create a new session to get started.</p></div>';
  } else {
    grid.innerHTML = active.map(renderCard).join('');
  }

  // Trash section
  if (trashed.length > 0) {
    let html = '<div class="trash-section">' +
      '<div class="trash-header" onclick="toggleTrash()">' +
        '<span class="trash-arrow">' + (showTrash ? '&#9660;' : '&#9654;') + '</span>' +
        '<span class="trash-label">Deleted</span>' +
        '<span class="trash-count">' + trashed.length + '</span>' +
      '</div>';
    if (showTrash) {
      html += '<div class="trash-grid">' + trashed.map(s => {
        const hasTitle = s.title && s.title !== s.name;
        return '<div class="trash-card">' +
          '<div class="top-row" style="padding-right:0">' +
            '<span class="session-display-name">' + escHtml(s.display_name) + '</span>' +
            '<span class="session-badge badge-' + s.type + '">' + s.type + '</span>' +
          '</div>' +
          (hasTitle ? '<div class="session-id">' + escHtml(s.name) + '</div>' : '') +
          '<div class="session-meta">' +
            '<span>' + s.created_fmt + '</span>' +
            (s.trashed_at ? '<span>Deleted ' + s.trashed_at.split('T')[0] + '</span>' : '') +
          '</div>' +
          '<div class="session-actions" style="margin-top:8px">' +
            '<button class="btn btn-sm btn-purple" onclick="restoreSession(\'' + (s.agent_id || '') + '\')">Restore</button>' +
            '<button class="btn btn-sm btn-red" onclick="killSession(\'' + s.name + '\', \'' + (s.agent_id || '') + '\')">Delete Forever</button>' +
          '</div>' +
        '</div>';
      }).join('') + '</div>';
    }
    html += '</div>';
    trashEl.innerHTML = html;
  } else {
    trashEl.innerHTML = '';
  }
}

function toggleTrash() { showTrash = !showTrash; render(); }
function toggleSelect(name, checked) { if (checked) selected.add(name); else selected.delete(name); render(); }
function selectAll() { data.active.forEach(s => selected.add(s.name)); render(); }
function selectNone() { selected.clear(); render(); }

async function openSession(name) {
  await api('POST', '/api/open', { session: name });
  toast('Opened in iTerm2');
}

async function trashSession(name) {
  if (!confirm('Move "' + name + '" to trash?')) return;
  await api('POST', '/api/trash', { session: name });
  selected.delete(name);
  toast('Moved to trash');
  refresh();
}

async function killSession(name, agentId) {
  if (!confirm('Permanently delete "' + name + '"? This removes all data.')) return;
  await api('POST', '/api/kill', { session: name, agent_id: agentId });
  toast('Permanently deleted');
  refresh();
}

async function restoreSession(agentId) {
  if (!agentId) { toast('No agent ID to restore'); return; }
  await api('POST', '/api/restore', { agent_id: agentId });
  toast('Restored');
  refresh();
}

async function quadSelected() {
  const sel = [...selected];
  if (sel.length === 0) { toast('Select sessions first'); return; }
  if (sel.length > 4) { toast('Max 4 for quad view'); return; }
  await api('POST', '/api/quad', { sessions: sel });
  toast('Quad view opened');
}

async function quadRecent() {
  await api('POST', '/api/quad', {});
  toast('Quad view: 4 most recent');
}

async function openAll() {
  for (const name of selected) await api('POST', '/api/open', { session: name });
  toast('Opened ' + selected.size + ' sessions');
}

async function cleanupDead() {
  const r = await api('POST', '/api/cleanup');
  toast(r.killed?.length ? 'Cleaned: ' + r.killed.join(', ') : 'No dead sessions');
  refresh();
}

function showNewModal() {
  showModal(
    '<h3>New Session</h3>' +
    '<input id="new-name" placeholder="Session name (optional)" autofocus onkeydown="if(event.key===\'Enter\')createNew()">' +
    '<div class="modal-actions">' +
      '<button class="btn" onclick="closeModal()">Cancel</button>' +
      '<button class="btn btn-blue" onclick="createNew()">Create</button>' +
    '</div>'
  );
  setTimeout(() => document.getElementById('new-name')?.focus(), 100);
}

async function createNew() {
  const name = document.getElementById('new-name').value.trim();
  await api('POST', '/api/new', { name });
  closeModal();
  toast(name ? 'Created: ' + name : 'Created new session');
  refresh();
}

function showRenameModal(sessName, currentTitle) {
  showModal(
    '<h3>Rename Session</h3>' +
    '<p style="font-size:12px;color:var(--fg-dim);margin-bottom:12px">tmux: ' + escHtml(sessName) + '</p>' +
    '<input id="rename-input" value="' + escHtml(currentTitle) + '" autofocus onkeydown="if(event.key===\'Enter\')doRename(\'' + sessName + '\')">' +
    '<div class="modal-actions">' +
      '<button class="btn" onclick="closeModal()">Cancel</button>' +
      '<button class="btn btn-blue" onclick="doRename(\'' + sessName + '\')">Rename</button>' +
    '</div>'
  );
  setTimeout(() => { const el = document.getElementById('rename-input'); el?.focus(); el?.select(); }, 100);
}

async function doRename(sessName) {
  const newName = document.getElementById('rename-input').value.trim();
  if (!newName) { closeModal(); return; }
  await api('POST', '/api/rename', { session: sessName, new_name: newName });
  closeModal();
  toast('Renamed');
  refresh();
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    pidfile = os.path.expanduser("~/.tmux/cmdcenter/server.pid")
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))

    def cleanup(sig, frame):
        try: os.unlink(pidfile)
        except: pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Command Center running at http://localhost:{PORT}")
    server.serve_forever()
