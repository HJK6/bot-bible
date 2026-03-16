import { useEffect, useRef, useCallback } from 'react';
import { AppState } from 'react-native';

interface Options {
  enabled?: boolean;
  intervalMs?: number;
}

export default function useAutoRefresh(
  fetchFn: () => void | Promise<void>,
  options: Options = {}
) {
  const { enabled = true, intervalMs = 5000 } = options;
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fetchRef = useRef(fetchFn);
  fetchRef.current = fetchFn;

  const start = useCallback(() => {
    if (intervalRef.current) return;
    intervalRef.current = setInterval(() => fetchRef.current(), intervalMs);
  }, [intervalMs]);

  const stop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (enabled) start();
    else stop();
    return stop;
  }, [enabled, start, stop]);

  // Pause when app is backgrounded, resume when foregrounded
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active' && enabled) {
        fetchRef.current();
        start();
      } else {
        stop();
      }
    });
    return () => sub.remove();
  }, [enabled, start, stop]);

  return { start, stop };
}
