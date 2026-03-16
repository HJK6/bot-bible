import { useState, useCallback, useEffect, useRef } from 'react';
import { callApi } from '../services/api';
import { Bot } from '../types/agent';

export default function useBots() {
  const [bots, setBots] = useState<Bot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const initialLoad = useRef(true);

  const fetch = useCallback(async () => {
    try {
      if (initialLoad.current) setLoading(true);
      const result = await callApi<Bot[]>('dashGetBots');
      if (result) {
        // Always-on bots (orchestrator, task-worker) go to the bottom
        const ALWAYS_ON = new Set(['telegram-bot', 'task-worker']);
        const sorted = [...result].sort((a, b) => {
          const aAlwaysOn = ALWAYS_ON.has(a.bot_type) ? 1 : 0;
          const bAlwaysOn = ALWAYS_ON.has(b.bot_type) ? 1 : 0;
          if (aAlwaysOn !== bAlwaysOn) return aAlwaysOn - bAlwaysOn;
          const order: Record<string, number> = { running: 0, stale: 1, completed: 2 };
          return (order[a.status] ?? 3) - (order[b.status] ?? 3);
        });
        setBots(sorted);
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

  return { bots, loading, error, refetch: fetch };
}
