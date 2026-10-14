import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useLiveVersion } from "./live";

interface Options {
  /** WebSocket message types that should trigger a (throttled) refetch */
  refreshOn?: string[];
  /** Fallback polling interval when the socket is quiet (ms) */
  intervalMs?: number;
  /** Minimum time between live-triggered refetches (ms) */
  throttleMs?: number;
  enabled?: boolean;
}

export function useApi<T>(path: string | null, { refreshOn = [], intervalMs, throttleMs = 2000, enabled = true }: Options = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path && enabled);
  const lastFetch = useRef(0);
  const version = useLiveVersion(refreshOn);

  const load = useCallback(async () => {
    if (!path || !enabled) return;
    lastFetch.current = Date.now();
    try {
      const res = await api<T>(path);
      setData(res);
      setError(null);
    } catch (e) {
      setError(e as Error);
    } finally {
      setLoading(false);
    }
  }, [path, enabled]);

  useEffect(() => {
    setLoading(!!path && enabled);
    load();
  }, [load, path, enabled]);

  // Live-triggered refetch, throttled: a burst of messages within the window causes one request
  // at the window boundary (the wait shrinks as time passes, so a steady stream cannot starve it).
  useEffect(() => {
    if (!version) return;
    const wait = Math.max(0, throttleMs - (Date.now() - lastFetch.current));
    const t = setTimeout(load, wait);
    return () => clearTimeout(t);
  }, [version, load, throttleMs]);

  useEffect(() => {
    if (!intervalMs) return;
    const id = setInterval(load, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, load]);

  return { data, error, loading, reload: load, setData };
}
