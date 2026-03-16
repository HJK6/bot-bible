export interface Agent {
  agent_id: string;
  agent_type: "claude-agent" | "aceable-bot" | "telegram-bot" | string;
  agent_name: string;
  title: string;
  goal: string;
  status: "running" | "idle" | "completed" | "failed" | "stale" | "trashed" | string;
  current_task: string;
  started_at: string;
  last_heartbeat: string;
  ended_at: string | null;
  metrics: Record<string, any>;
  host: string;
  pid: number;
  interactive?: boolean;
  tmux_session?: string;
  tmux_window?: string;
  tmux_index?: number;
}

export interface Bot {
  bot_id: string;
  bot_type: string;
  bot_name: string;
  title: string;
  status: "running" | "stale" | "completed" | string;
  current_task: string;
  started_at: string;
  last_heartbeat: string;
  metrics: Record<string, any>;
  host: string;
  pid: number;
}

export interface AgentLog {
  agent_id: string;
  timestamp: number;
  level: "info" | "warning" | "error";
  message: string;
  metadata: Record<string, any>;
}

export interface AgentChatMessage {
  agent_id: string;
  timestamp: number;
  direction: "inbound" | "outbound";
  message: string;
  sender: string;
  image_url?: string;
}

export interface AgentChatMessageOptimistic extends AgentChatMessage {
  optimistic?: boolean;
  pending?: boolean;
  image_url?: string;
}

export interface ScheduledJob {
  tag: string;
  type: "one-time" | "recurring";
  active: boolean;
  stale: boolean;
  time: string;
  days: string;
  category: string;
  command: string;
  last_run: string | null;
}

export interface Project {
  project_id: string;
  name: string;
  description: string;
  status: "active" | "paused" | "archived";
  category: string;
  tech_stack: string[];
  repo_path: string;
  recent_activity: string[];
  updated_at: string;
  created_at: string;
}

export interface ScheduledJobsResponse {
  synced_at: string;
  host: string;
  total: number;
  active: number;
  jobs: ScheduledJob[];
}
