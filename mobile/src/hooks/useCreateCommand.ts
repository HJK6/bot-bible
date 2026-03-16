import { useState, useCallback } from 'react';
import { callApi } from '../services/api';

export default function useCreateCommand() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createCommand = useCallback(async (command: string, payload: Record<string, any> = {}) => {
    try {
      setLoading(true);
      setError(null);
      const result = await callApi('dashCreateCommand', { command, payload });
      return result;
    } catch (e: any) {
      setError(e.message);
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);

  return { createCommand, loading, error };
}
