import { useState, useCallback, useEffect, useRef } from 'react';
import { callApi } from '../services/api';
import { Project } from '../types/agent';

export default function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const initialLoad = useRef(true);

  const fetch = useCallback(async () => {
    try {
      if (initialLoad.current) setLoading(true);
      const result = await callApi<Project[]>('dashGetProjects');
      if (result) {
        setProjects(result);
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

  return { projects, loading, error, refetch: fetch };
}
