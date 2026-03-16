import { useState, useCallback, useEffect, useRef } from 'react';
import { callApi } from '../services/api';
import { Agent } from '../types/agent';

export default function useAgents() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const initialLoad = useRef(true);

  const fetch = useCallback(async () => {
    try {
      if (initialLoad.current) setLoading(true);
      const result = await callApi<Agent[]>('dashGetAgents');
      if (result) {
        const order: Record<string, number> = { running: 0, idle: 1, stale: 2, completed: 3, failed: 4 };
        const sorted = [...result].sort(
          (a, b) => (order[a.status] ?? 5) - (order[b.status] ?? 5)
        );
        setAgents(sorted);
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

  return { agents, loading, error, refetch: fetch };
}
