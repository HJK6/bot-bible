#!/usr/bin/env python3
"""Tmux Session Manager - macOS desktop app"""

import subprocess
import os
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import threading

TMUX = "/opt/homebrew/bin/tmux"


def get_trashed_sessions():
    """Get trashed agent tmux session names from DynamoDB."""
    try:
        import boto3
        from boto3.dynamodb.conditions import Attr
        dynamo = boto3.resource("dynamodb", region_name="us-east-1")
        tracker = dynamo.Table("AgentTracker")
        response = tracker.scan(
            FilterExpression=Attr("status").eq("trashed"),
            ProjectionExpression="agent_id, tmux_session, title, trashed_at",
        )
        items = response.get("Items", [])
        while "LastEvaluatedKey" in response:
            response = tracker.scan(
                FilterExpression=Attr("status").eq("trashed"),
                ProjectionExpression="agent_id, tmux_session, title, trashed_at",
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))
        return items
    except Exception:
        return []


def restore_agent(agent_id):
    """Restore a trashed agent in DynamoDB."""
    try:
        import boto3
        dynamo = boto3.resource("dynamodb", region_name="us-east-1")
        tracker = dynamo.Table("AgentTracker")
        tracker.update_item(
            Key={"agent_id": agent_id},
            UpdateExpression="SET #s = :s, #h = :h REMOVE trashed_at, hidden_at",
            ExpressionAttributeValues={":s": "idle", ":h": False},
            ExpressionAttributeNames={"#s": "status", "#h": "hidden"},
        )
        return True
    except Exception:
        return False


def trash_agent_by_tmux(tmux_session_name):
    """Find the agent for a tmux session and trash it in DynamoDB. Returns True if trashed."""
    try:
        import boto3
        from boto3.dynamodb.conditions import Attr
        from datetime import timezone
        dynamo = boto3.resource("dynamodb", region_name="us-east-1")
        tracker = dynamo.Table("AgentTracker")
        response = tracker.scan(
            FilterExpression=Attr("tmux_session").eq(tmux_session_name),
            ProjectionExpression="agent_id",
        )
        items = response.get("Items", [])
        if not items:
            return False
        agent_id = items[0]["agent_id"]
        now = datetime.now(timezone.utc).isoformat()
        tracker.update_item(
            Key={"agent_id": agent_id},
            UpdateExpression="SET #s = :s, trashed_at = :t, #h = :h",
            ExpressionAttributeValues={":s": "trashed", ":t": now, ":h": True},
            ExpressionAttributeNames={"#s": "status", "#h": "hidden"},
        )
        return True
    except Exception:
        return False


class TmuxManager:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Tmux Sessions")
        self.root.geometry("520x520")
        self.root.resizable(True, True)
        self.root.configure(bg="#1e1e2e")
        self.trashed_agents = []
        self.show_trash = False

        # Style
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Title.TLabel", font=("SF Pro Display", 20, "bold"),
                        foreground="#cdd6f4", background="#1e1e2e")
        style.configure("Sub.TLabel", font=("SF Pro Text", 11),
                        foreground="#6c7086", background="#1e1e2e")
        style.configure("Empty.TLabel", font=("SF Pro Text", 13),
                        foreground="#585b70", background="#1e1e2e")

        style.configure("Session.TFrame", background="#313244", relief="flat")
        style.configure("SessionName.TLabel", font=("SF Mono", 14, "bold"),
                        foreground="#cdd6f4", background="#313244")
        style.configure("SessionInfo.TLabel", font=("SF Pro Text", 11),
                        foreground="#a6adc8", background="#313244")
        style.configure("Attached.TLabel", font=("SF Pro Text", 10, "bold"),
                        foreground="#a6e3a1", background="#313244")

        # Trashed session styles
        style.configure("TrashedName.TLabel", font=("SF Mono", 13),
                        foreground="#6c7086", background="#252535")
        style.configure("TrashedInfo.TLabel", font=("SF Pro Text", 10),
                        foreground="#585b70", background="#252535")
        style.configure("TrashHeader.TLabel", font=("SF Pro Text", 12, "bold"),
                        foreground="#6c7086", background="#1e1e2e")

        style.configure("Open.TButton", font=("SF Pro Text", 11, "bold"),
                        foreground="#1e1e2e", background="#89b4fa",
                        padding=(12, 6))
        style.map("Open.TButton",
                  background=[("active", "#74c7ec")])

        style.configure("Trash.TButton", font=("SF Pro Text", 11),
                        foreground="#1e1e2e", background="#f38ba8",
                        padding=(10, 6))
        style.map("Trash.TButton",
                  background=[("active", "#eba0ac")])

        style.configure("Refresh.TButton", font=("SF Pro Text", 11),
                        foreground="#cdd6f4", background="#45475a",
                        padding=(12, 6))
        style.map("Refresh.TButton",
                  background=[("active", "#585b70")])

        style.configure("New.TButton", font=("SF Pro Text", 11, "bold"),
                        foreground="#1e1e2e", background="#a6e3a1",
                        padding=(12, 6))
        style.map("New.TButton",
                  background=[("active", "#94e2d5")])

        style.configure("Restore.TButton", font=("SF Pro Text", 10),
                        foreground="#cdd6f4", background="#585b70",
                        padding=(8, 4))
        style.map("Restore.TButton",
                  background=[("active", "#6c7086")])

        # Header
        header = tk.Frame(self.root, bg="#1e1e2e")
        header.pack(fill="x", padx=20, pady=(18, 0))

        ttk.Label(header, text="Tmux Sessions", style="Title.TLabel").pack(side="left")

        btn_frame = tk.Frame(header, bg="#1e1e2e")
        btn_frame.pack(side="right")
        ttk.Button(btn_frame, text="+ New", style="New.TButton",
                   command=self.new_session).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="Refresh", style="Refresh.TButton",
                   command=self.refresh).pack(side="left")

        self.count_label = ttk.Label(self.root, text="", style="Sub.TLabel")
        self.count_label.pack(anchor="w", padx=22, pady=(2, 8))

        # Scrollable session list
        container = tk.Frame(self.root, bg="#1e1e2e")
        container.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.canvas = tk.Canvas(container, bg="#1e1e2e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg="#1e1e2e")

        self.scroll_frame.bind("<Configure>",
                               lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw", tags="frame")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig("frame", width=e.width))

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Mouse wheel scrolling
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self.refresh()
        self.root.after(5000, self.auto_refresh)
        self.root.mainloop()

    def get_sessions(self):
        result = subprocess.run(
            [TMUX, "list-sessions", "-F",
             "#{session_name}\t#{session_windows}\t#{session_attached}\t#{session_created}"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return []
        sessions = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            session_name = parts[0]
            created = datetime.fromtimestamp(int(parts[3]))
            # Get the first window's name as a human-readable title
            win_result = subprocess.run(
                [TMUX, "list-windows", "-t", session_name, "-F", "#{window_name}"],
                capture_output=True, text=True
            )
            window_name = ""
            if win_result.returncode == 0 and win_result.stdout.strip():
                window_name = win_result.stdout.strip().split("\n")[0]
            sessions.append({
                "name": session_name,
                "title": window_name if window_name and window_name != session_name else "",
                "windows": int(parts[1]),
                "attached": parts[2] == "1",
                "created": created.strftime("%b %d, %I:%M %p"),
            })
        return sessions

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        sessions = self.get_sessions()

        # Fetch trashed agents in background on first load, use cached after
        def fetch_and_render():
            self.trashed_agents = get_trashed_sessions()
            self.root.after(0, lambda: self._render_sessions(sessions))

        if not self.trashed_agents and not hasattr(self, '_trashed_fetched'):
            self._trashed_fetched = True
            threading.Thread(target=fetch_and_render, daemon=True).start()
            # Render immediately without trash data
            self._render_sessions(sessions)
        else:
            # Re-fetch trashed in background
            threading.Thread(target=lambda: setattr(self, 'trashed_agents', get_trashed_sessions()),
                           daemon=True).start()
            self._render_sessions(sessions)

    def _render_sessions(self, sessions):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        # Build set of trashed tmux session names
        trashed_names = {a.get("tmux_session", "") for a in self.trashed_agents if a.get("tmux_session")}

        # Split sessions into active and trashed
        active = [s for s in sessions if s["name"] not in trashed_names]
        trashed = [s for s in sessions if s["name"] in trashed_names]

        self.count_label.config(text=f"{len(active)} active session{'s' if len(active) != 1 else ''}")

        if not active:
            ttk.Label(self.scroll_frame, text="No tmux sessions running",
                      style="Empty.TLabel").pack(pady=60)
        else:
            for sess in active:
                self._render_session_card(sess)

        # Deleted section
        trash_count = len(trashed)
        if trash_count > 0 or self.show_trash:
            # Separator
            sep = tk.Frame(self.scroll_frame, bg="#45475a", height=1)
            sep.pack(fill="x", pady=(12, 0))

            # Clickable trash header
            trash_header = tk.Frame(self.scroll_frame, bg="#1e1e2e", cursor="hand2")
            trash_header.pack(fill="x", pady=(8, 4))

            arrow = "▼" if self.show_trash else "▶"
            label_text = f"{arrow}  Deleted ({trash_count})"
            header_label = ttk.Label(trash_header, text=label_text, style="TrashHeader.TLabel")
            header_label.pack(side="left", padx=4)

            trash_header.bind("<Button-1>", lambda e: self._toggle_trash(sessions))
            header_label.bind("<Button-1>", lambda e: self._toggle_trash(sessions))

            if self.show_trash:
                if not trashed:
                    ttk.Label(self.scroll_frame, text="Trash is empty",
                              style="Empty.TLabel").pack(pady=20)
                else:
                    for sess in trashed:
                        self._render_trashed_card(sess)

    def _render_session_card(self, sess):
        card = tk.Frame(self.scroll_frame, bg="#313244", padx=14, pady=10)
        card.pack(fill="x", pady=4)

        # Left side: name + info
        left = tk.Frame(card, bg="#313244")
        left.pack(side="left", fill="x", expand=True)

        name_row = tk.Frame(left, bg="#313244")
        name_row.pack(anchor="w")
        display_name = sess["title"] if sess["title"] else sess["name"]
        ttk.Label(name_row, text=display_name,
                  style="SessionName.TLabel").pack(side="left")
        if sess["attached"]:
            ttk.Label(name_row, text=" ● attached",
                      style="Attached.TLabel").pack(side="left", padx=(8, 0))

        info_parts = []
        if sess["title"]:
            info_parts.append(sess["name"])
        info_parts.append(f"{sess['windows']} window{'s' if sess['windows'] != 1 else ''}")
        info_parts.append(sess["created"])
        ttk.Label(left, text="  ·  ".join(info_parts),
                  style="SessionInfo.TLabel").pack(anchor="w", pady=(2, 0))

        # Right side: buttons
        right = tk.Frame(card, bg="#313244")
        right.pack(side="right")

        name = sess["name"]
        ttk.Button(right, text="Open", style="Open.TButton",
                   command=lambda n=name: self.open_session(n)).pack(side="left", padx=(0, 6))
        ttk.Button(right, text="Trash", style="Trash.TButton",
                   command=lambda n=name: self.trash_session(n)).pack(side="left")

    def _render_trashed_card(self, sess):
        # Find agent info for this tmux session
        agent = next((a for a in self.trashed_agents if a.get("tmux_session") == sess["name"]), None)

        card = tk.Frame(self.scroll_frame, bg="#252535", padx=14, pady=8)
        card.pack(fill="x", pady=2)

        left = tk.Frame(card, bg="#252535")
        left.pack(side="left", fill="x", expand=True)

        display_name = agent.get("title", "") if agent else ""
        if not display_name:
            display_name = sess["title"] if sess["title"] else sess["name"]
        ttk.Label(left, text=display_name, style="TrashedName.TLabel").pack(anchor="w")

        info_parts = [sess["name"]]
        if agent and agent.get("trashed_at"):
            try:
                dt = datetime.fromisoformat(agent["trashed_at"].replace("Z", "+00:00"))
                info_parts.append(f"deleted {dt.strftime('%b %d, %I:%M %p')}")
            except Exception:
                pass
        ttk.Label(left, text="  ·  ".join(info_parts),
                  style="TrashedInfo.TLabel").pack(anchor="w", pady=(2, 0))

        right = tk.Frame(card, bg="#252535")
        right.pack(side="right")

        agent_id = agent.get("agent_id", "") if agent else ""
        ttk.Button(right, text="Restore", style="Restore.TButton",
                   command=lambda aid=agent_id, n=sess["name"]: self._restore_session(aid, n)).pack(side="left", padx=(0, 6))
        ttk.Button(right, text="Kill", style="Trash.TButton",
                   command=lambda aid=agent_id, n=sess["name"]: self._permanently_delete(aid, n)).pack(side="left")

    def _toggle_trash(self, sessions):
        self.show_trash = not self.show_trash
        self._render_sessions(sessions)

    def _restore_session(self, agent_id, session_name):
        if not agent_id:
            messagebox.showwarning("Restore", "No agent ID found for this session.")
            return
        if messagebox.askyesno("Restore Session", f"Restore '{session_name}' from trash?"):
            def do_restore():
                success = restore_agent(agent_id)
                if success:
                    self.trashed_agents = [a for a in self.trashed_agents if a.get("agent_id") != agent_id]
                self.root.after(0, self.refresh)
                if not success:
                    self.root.after(0, lambda: messagebox.showerror("Restore Failed", "Could not restore agent."))

            threading.Thread(target=do_restore, daemon=True).start()

    def open_session(self, name):
        subprocess.Popen(["osascript", "-e", f'''
            tell application "Terminal"
                activate
                do script "{TMUX} attach -t {name}"
            end tell
        '''])

    def _permanently_delete(self, agent_id, session_name):
        if not messagebox.askyesno("Permanently Delete",
                                   f"Permanently delete '{session_name}'?\nThis kills the tmux session and removes all data."):
            return

        def do_delete():
            # Kill tmux session
            subprocess.run([TMUX, "kill-session", "-t", session_name], capture_output=True)
            # Nuke all DynamoDB data
            try:
                import boto3
                from boto3.dynamodb.conditions import Key
                dynamo = boto3.resource("dynamodb", region_name="us-east-1")
                tracker = dynamo.Table("AgentTracker")
                logs = dynamo.Table("AgentLogs")
                chat = dynamo.Table("AgentChat")
                tracker.delete_item(Key={"agent_id": agent_id})
                try:
                    log_resp = logs.query(KeyConditionExpression=Key("agent_id").eq(agent_id))
                    with logs.batch_writer() as batch:
                        for item in log_resp.get("Items", []):
                            batch.delete_item(Key={"agent_id": agent_id, "timestamp": item["timestamp"]})
                except Exception:
                    pass
                try:
                    chat_resp = chat.query(KeyConditionExpression=Key("agent_id").eq(agent_id))
                    with chat.batch_writer() as batch:
                        for item in chat_resp.get("Items", []):
                            batch.delete_item(Key={"agent_id": agent_id, "timestamp": item["timestamp"]})
                except Exception:
                    pass
            except Exception:
                pass
            self.trashed_agents = [a for a in self.trashed_agents if a.get("agent_id") != agent_id]
            self.root.after(0, self.refresh)

        threading.Thread(target=do_delete, daemon=True).start()

    def trash_session(self, name):
        if messagebox.askyesno("Trash Session", f"Move tmux session '{name}' to trash?"):
            def do_trash():
                trashed = trash_agent_by_tmux(name)
                if trashed:
                    # Refresh trashed agents cache so it shows in Deleted section
                    self.trashed_agents = get_trashed_sessions()
                else:
                    # No agent found in DynamoDB — just kill the tmux session directly
                    subprocess.run([TMUX, "kill-session", "-t", name])
                self.root.after(0, self.refresh)

            threading.Thread(target=do_trash, daemon=True).start()

    def new_session(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("New Session")
        dialog.geometry("300x130")
        dialog.configure(bg="#1e1e2e")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="Session name:", font=("SF Pro Text", 12),
                 fg="#cdd6f4", bg="#1e1e2e").pack(pady=(16, 6))

        entry = tk.Entry(dialog, font=("SF Mono", 13), bg="#313244", fg="#cdd6f4",
                         insertbackground="#cdd6f4", relief="flat", bd=8)
        entry.pack(fill="x", padx=20)
        entry.focus_set()

        def create(event=None):
            name = entry.get().strip()
            if not name:
                return
            dialog.destroy()
            subprocess.Popen(["osascript", "-e", f'''
                tell application "Terminal"
                    activate
                    do script "{TMUX} new-session -s {name}"
                end tell
            '''])
            self.root.after(1000, self.refresh)

        entry.bind("<Return>", create)
        ttk.Button(dialog, text="Create", style="Open.TButton",
                   command=create).pack(pady=10)

    def auto_refresh(self):
        self.refresh()
        self.root.after(5000, self.auto_refresh)


if __name__ == "__main__":
    TmuxManager()
