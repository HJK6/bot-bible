import { useState, useCallback, useEffect, useRef } from 'react';
import { callApi } from '../services/api';

export interface UsageData {
  session_pct: number;
  session_resets: string;
  week_all_pct: number;
  week_all_resets: string;
  week_sonnet_pct: number;
  week_sonnet_resets: string;
  extra_usage: string;
  last_heartbeat: string;
}

export default function useUsage() {
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const initialLoad = useRef(true);

  const fetch = useCallback(async () => {
    try {
      if (initialLoad.current) setLoading(true);
      const result = await callApi<any>('dashGetUsage');
      if (result && result.status !== 'no_data') {
        setUsage(result as UsageData);
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

  return { usage, loading, error, refetch: fetch };
}
