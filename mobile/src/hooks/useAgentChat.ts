import { useState, useCallback, useEffect } from 'react';
import { callApi } from '../services/api';
import { AgentChatMessage } from '../types/agent';

export default function useAgentChat(agentId: string) {
  const [messages, setMessages] = useState<AgentChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!agentId) return;
    try {
      setLoading(true);
      const result = await callApi<AgentChatMessage[]>('dashGetAgentChat', {
        agent_id: agentId,
        limit: 100,
      });
      console.log(`[useAgentChat] ${agentId.slice(0,8)}: got ${Array.isArray(result) ? result.length : typeof result} messages`);
      // API returns newest first, reverse for chronological order
      const sorted = Array.isArray(result) ? [...result].reverse() : [];
      setMessages(sorted);
      setError(null);
    } catch (e: any) {
      console.error(`[useAgentChat] ${agentId.slice(0,8)}: error`, e.message);
      setMessages([]);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { messages, loading, error, refetch: fetch };
}
