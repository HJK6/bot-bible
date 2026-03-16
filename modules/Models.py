from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List


@dataclass
class AgentRecord:
    agent_id: str
    agent_type: str
    agent_name: str
    title: str
    status: str
    current_task: str
    started_at: str
    last_heartbeat: str
    ended_at: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    host: str = ""
    pid: int = 0
    ttl: int = 0
    interactive: bool = False


@dataclass
class AgentLog:
    agent_id: str
    timestamp: int
    level: str
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    ttl: int = 0


@dataclass
class AgentCommand:
    command_id: str
    command: str
    payload: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    created_at: str = ""
    ttl: int = 0


@dataclass
class AgentChatMessage:
    agent_id: str
    timestamp: int
    direction: str
    message: str
    sender: str = ""
    ttl: int = 0
