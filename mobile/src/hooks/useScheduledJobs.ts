import { useState, useCallback, useEffect, useRef } from 'react';
import { callApi } from '../services/api';
import { ScheduledJob, ScheduledJobsResponse } from '../types/agent';

const CATEGORY_ORDER: Record<string, number> = {
  Stocks: 0, Trading: 1, Land: 2, Aceable: 3, System: 4, Other: 5, Stale: 6,
};

export default function useScheduledJobs() {
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [syncedAt, setSyncedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const initialLoad = useRef(true);

  const fetch = useCallback(async () => {
    try {
      if (initialLoad.current) setLoading(true);
      const result = await callApi<ScheduledJobsResponse>('dashGetScheduledJobs');
      if (result?.jobs) {
        const sorted = [...result.jobs].sort((a, b) => {
          const catA = CATEGORY_ORDER[a.category] ?? 5;
          const catB = CATEGORY_ORDER[b.category] ?? 5;
          if (catA !== catB) return catA - catB;
          return a.tag.localeCompare(b.tag);
        });
        setJobs(sorted);
        setSyncedAt(result.synced_at);
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

  return { jobs, syncedAt, loading, error, refetch: fetch };
}
