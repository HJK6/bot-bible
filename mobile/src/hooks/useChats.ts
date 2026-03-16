import { useState, useCallback, useEffect, useRef } from 'react';
import { callApi } from '../services/api';
import { Agent } from '../types/agent';

export interface ChatPreview {
  agent_id: string;
  title: string;
  lastMessage: string;
  lastTimestamp: number;
  status: string;
  unread?: boolean;
}

export default function useChats() {
  const [chats, setChats] = useState<ChatPreview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const initialLoad = useRef(true);

  const fetch = useCallback(async () => {
    try {
      if (initialLoad.current) setLoading(true);
      // Get agents from AgentTracker — each one has a chat
      const agents = await callApi<Agent[]>('dashGetAgents');
      if (agents) {
        const previews: ChatPreview[] = agents
          .filter((a) => a.interactive !== false)
          .map((a) => ({
            agent_id: a.agent_id,
            title: a.title || a.agent_name || a.agent_id.slice(0, 8),
            lastMessage: a.current_task || a.goal || '',
            lastTimestamp: a.last_heartbeat ? new Date(a.last_heartbeat).getTime() : 0,
            status: a.status,
          }))
          .sort((a, b) => b.lastTimestamp - a.lastTimestamp);
        setChats(previews);
      }
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
      initialLoad.current = false;
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { chats, loading, error, refetch: fetch };
}
