import { useState, useCallback, useEffect } from 'react';
import { callApi } from '../services/api';
import { AgentChatMessage } from '../types/agent';

export default function useUpdates() {
  const [updates, setUpdates] = useState<AgentChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    try {
      setLoading(true);
      const result = await callApi<AgentChatMessage[]>('dashGetAgentChat', {
        agent_id: 'system',
        limit: 50,
      });
      // API returns newest first — keep that order for the feed
      const sorted = Array.isArray(result) ? result : [];
      setUpdates(sorted);
      setError(null);
    } catch (e: any) {
      setUpdates([]);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { updates, loading, error, refetch: fetch };
}
