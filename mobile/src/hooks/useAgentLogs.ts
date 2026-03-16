import { useState, useCallback, useEffect } from 'react';
import { callApi } from '../services/api';
import { AgentLog } from '../types/agent';

export default function useAgentLogs(agentId: string) {
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!agentId) return;
    try {
      setLoading(true);
      const result = await callApi<AgentLog[]>('dashGetAgentLogs', {
        agent_id: agentId,
        limit: 500,
      });
      if (result) {
        setLogs(result);
      }
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { logs, loading, error, refetch: fetch };
}
