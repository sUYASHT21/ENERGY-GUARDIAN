/* WebSocket live-update channel. Holds the latest backend summary, a short live power
   series built from summaries, and per-message-type version counters that pages use to
   refetch exactly when relevant data changes. */
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { LivePoint, Summary } from "../api/types";

export type WsStatus = "connecting" | "open" | "closed";

interface LiveState {
  status: WsStatus;
  summary: Summary | null;
  livePoints: LivePoint[];
  versions: Record<string, number>;
  lastMessageAt: number | null;
}

const LiveContext = createContext<LiveState>({ status: "closed", summary: null, livePoints: [], versions: {}, lastMessageAt: null });
const MAX_POINTS = 240;

export function wsUrl(token: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws?token=${encodeURIComponent(token)}`;
}

export function LiveProvider({ token, children }: { token: string | null; children: ReactNode }) {
  const [state, setState] = useState<LiveState>({ status: "closed", summary: null, livePoints: [], versions: {}, lastMessageAt: null });
  const retry = useRef(0);

  useEffect(() => {
    if (!token) return;
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const connect = () => {
      setState((s) => ({ ...s, status: "connecting" }));
      ws = new WebSocket(wsUrl(token));
      ws.onopen = () => {
        retry.current = 0;
        setState((s) => ({ ...s, status: "open" }));
      };
      ws.onmessage = (ev) => {
        let msg: { type: string; data: unknown };
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        setState((s) => {
          const versions = { ...s.versions, [msg.type]: (s.versions[msg.type] ?? 0) + 1 };
          if (msg.type === "summary") {
            const summary = msg.data as Summary;
            const point = { ts: summary.generated_at, power_w: summary.live_power_w, sources: summary.data_sources_live };
            const livePoints = [...s.livePoints, point].slice(-MAX_POINTS);
            return { ...s, summary, livePoints, versions, lastMessageAt: Date.now() };
          }
          return { ...s, versions, lastMessageAt: Date.now() };
        });
      };
      ws.onclose = (ev) => {
        setState((s) => ({ ...s, status: "closed" }));
        if (stopped || ev.code === 4401) return;
        const delay = Math.min(15000, 1000 * 2 ** retry.current++);
        timer = setTimeout(connect, delay);
      };
      ws.onerror = () => ws?.close();
    };
    connect();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      ws?.close();
    };
  }, [token]);

  // HTTP fallback: while the socket is not open, poll the summary so indicators stay truthful.
  const status = state.status;
  useEffect(() => {
    if (!token || status === "open") return;
    let cancelled = false;
    const poll = async () => {
      try {
        const summary = await api<Summary>("/dashboard/summary");
        if (cancelled) return;
        setState((s) => ({
          ...s,
          summary,
          livePoints: [...s.livePoints, { ts: summary.generated_at, power_w: summary.live_power_w, sources: summary.data_sources_live }].slice(-MAX_POINTS),
          versions: { ...s.versions, summary: (s.versions.summary ?? 0) + 1 },
        }));
      } catch {
        /* keep last known state */
      }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [token, status]);

  return <LiveContext.Provider value={state}>{children}</LiveContext.Provider>;
}

export function useLive(): LiveState {
  return useContext(LiveContext);
}

/** Sum of version counters for the given message types — changes whenever one arrives. */
export function useLiveVersion(types: string[]): number {
  const { versions } = useLive();
  return types.reduce((acc, t) => acc + (versions[t] ?? 0), 0);
}
