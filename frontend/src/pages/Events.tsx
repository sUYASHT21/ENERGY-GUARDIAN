import { useState } from "react";
import type { EventItem } from "../api/types";
import { Card, Empty, ErrorBanner, Spinner, StatusPill, cx, inputCls } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { formatDateTime } from "../lib/format";

const CATEGORIES = ["", "alert", "command", "device", "occupancy", "override", "config", "settings", "simulation", "ml", "auth", "savings", "telemetry", "system"];

export default function Events() {
  const [category, setCategory] = useState("");
  const events = useApi<EventItem[]>(`/events?limit=300${category ? `&category=${category}` : ""}`, { refreshOn: ["event"], throttleMs: 3000 });
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Event log</h1>
          <p className="text-sm text-ink-2">Persistent audit trail of system activity, configuration changes and operator actions.</p>
        </div>
        <select className={cx(inputCls, "w-auto")} value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
          {CATEGORIES.map((c) => <option key={c} value={c}>{c || "All categories"}</option>)}
        </select>
      </div>
      <ErrorBanner error={events.error} onRetry={events.reload} />
      {!events.data ? <Spinner /> : events.data.length === 0 ? <Empty>No events</Empty> : (
        <Card bodyClass="p-0">
          <ul className="divide-y divide-[var(--border)]">
            {events.data.map((e) => (
              <li key={e.id} className="flex flex-wrap items-start gap-3 px-4 py-2 text-sm">
                <span className="w-32 shrink-0 tabular text-xs text-muted">{formatDateTime(e.ts)}</span>
                <span className="w-24 shrink-0"><StatusPill tone={e.level === "warning" ? "warning" : e.level === "error" ? "critical" : "neutral"} label={e.category} /></span>
                <span className="min-w-0 flex-1">{e.message}</span>
                {e.actor && <span className="text-xs text-ink-2">by {e.actor}</span>}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
