import { useState } from "react";
import { Link } from "react-router-dom";
import { post } from "../api/client";
import type { Alert, Command, Room } from "../api/types";
import { Button, Card, Empty, ErrorBanner, SourceBadge, Spinner, StatusPill, cx, inputCls, severityTone, useToast } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useApi } from "../hooks/useApi";
import { formatDateTime, humanize, timeAgo } from "../lib/format";

const TYPES = ["", "vacant_room_waste", "anomaly", "sensor_failure", "device_offline", "stale_data", "command_failed", "command_timeout"];

export default function Alerts() {
  const { can } = useAuth();
  const toast = useToast();
  const [status, setStatus] = useState<"open" | "resolved" | "all">("open");
  const [type, setType] = useState("");
  const alerts = useApi<Alert[]>(`/alerts?status=${status}&limit=200${type ? `&alert_type=${type}` : ""}`, { refreshOn: ["alert"] });
  const rooms = useApi<Room[]>("/rooms");
  const roomName = (id: number | null) => rooms.data?.find((r) => r.id === id)?.name;

  const act = async (a: Alert, action: "acknowledge" | "resolve") => {
    try {
      const note = action === "resolve" ? prompt("Resolution note (optional)") ?? undefined : undefined;
      await post(`/alerts/${a.id}/${action}`, action === "resolve" ? { note } : undefined);
      toast("good", `Alert ${action === "resolve" ? "resolved" : "acknowledged"}`);
      alerts.reload();
    } catch (e) { toast("critical", (e as Error).message); }
  };
  const apply = async (a: Alert) => {
    if (!a.appliance_id || !confirm(`Send OFF to the appliance of alert "${a.title}"? It goes through the same safety gate.`)) return;
    try {
      const c = await post<Command>("/commands", { appliance_id: a.appliance_id, action: "off", reason: `applied recommendation of alert #${a.id}` });
      toast(c.status === "blocked" ? "critical" : "good", c.status === "blocked" ? `Blocked: ${c.error}` : `Command ${c.status} (${c.mode})`);
    } catch (e) { toast("critical", (e as Error).message); }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Alerts</h1>
        <div className="flex flex-wrap gap-2">
          <div className="inline-flex rounded-lg border border-line bg-surface p-0.5" role="group" aria-label="Status filter">
            {(["open", "resolved", "all"] as const).map((s) => (
              <button key={s} onClick={() => setStatus(s)} aria-pressed={status === s} className={cx("rounded-md px-3 py-1 text-sm", status === s ? "bg-accent-wash font-semibold text-accent-ink" : "text-ink-2")}>{humanize(s)}</button>
            ))}
          </div>
          <select className={cx(inputCls, "w-auto")} value={type} onChange={(e) => setType(e.target.value)} aria-label="Alert type">
            {TYPES.map((t) => <option key={t} value={t}>{t ? humanize(t) : "All types"}</option>)}
          </select>
        </div>
      </div>
      <ErrorBanner error={alerts.error} onRetry={alerts.reload} />
      {!alerts.data ? <Spinner /> : alerts.data.length === 0 ? <Empty>No alerts match the filter</Empty> : (
        <div className="flex flex-col gap-2">
          {alerts.data.map((a) => {
            const decision = (a.details?.decision ?? null) as { summary?: string; blockers?: string[] } | null;
            return (
              <Card key={a.id} bodyClass="p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusPill tone={severityTone(a.severity)} label={a.severity} />
                    <span className="text-xs font-medium uppercase tracking-wide text-muted">{humanize(a.alert_type)}</span>
                    {a.source && <SourceBadge source={a.source} compact />}
                    {a.resolved && <StatusPill tone="good" label="Resolved" />}
                  </div>
                  <span className="text-xs text-muted" title={formatDateTime(a.created_at)}>first {timeAgo(a.created_at)} · last {timeAgo(a.last_seen_at)} · {a.occurrences}×</span>
                </div>
                <h3 className="mt-1.5 font-medium">{a.title}</h3>
                {a.message && <p className="text-sm text-ink-2">{a.message}</p>}
                {decision?.blockers && decision.blockers.length > 0 && (
                  <p className="mt-1 text-xs text-ink-2">Automatic action blocked by: {decision.blockers.map(humanize).join(", ")}</p>
                )}
                {a.recommendation && <p className="mt-1 text-sm"><span className="font-medium">Recommendation:</span> {a.recommendation}</p>}
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-ink-2">
                  {a.room_id && <Link className="text-accent-ink hover:underline" to={`/rooms/${a.room_id}`}>{roomName(a.room_id) ?? `Room ${a.room_id}`}</Link>}
                  {a.acknowledged && <span>Acknowledged by {a.acknowledged_by} {timeAgo(a.acknowledged_at)}</span>}
                  {a.resolved && a.resolution_note && <span>· {a.resolution_note}</span>}
                </div>
                {can("operator") && !a.resolved && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {!a.acknowledged && <Button className="px-2 py-1 text-xs" onClick={() => act(a, "acknowledge")}>Acknowledge</Button>}
                    <Button className="px-2 py-1 text-xs" variant="ghost" onClick={() => act(a, "resolve")}>Resolve</Button>
                    {a.alert_type === "vacant_room_waste" && a.appliance_id && <Button className="px-2 py-1 text-xs" variant="primary" onClick={() => apply(a)}>Apply recommendation</Button>}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
