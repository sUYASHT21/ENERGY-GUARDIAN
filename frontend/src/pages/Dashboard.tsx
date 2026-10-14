import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Bolt, Coins, Leaf, PiggyBank, Plug, Trash2, Users } from "lucide-react";
import { post } from "../api/client";
import type { Alert, Device, HistoryPoint, LivePoint, OverviewRoom, Summary } from "../api/types";
import { EnergyBarChart, Legend, LivePowerChart } from "../components/charts";
import {
  Button, Card, Empty, ErrorBanner, SourceBadge, Spinner, StatTile, StatusPill, connectionTone, cx, occupancyTone,
  severityTone, useToast,
} from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useLive } from "../hooks/live";
import { useApi } from "../hooks/useApi";
import { formatKg, formatKwh, formatMoney, formatPower, humanize, timeAgo } from "../lib/format";

export function mergeLivePoints(initial: LivePoint[], live: LivePoint[]): LivePoint[] {
  const all = [...initial, ...live].sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
  const out: LivePoint[] = [];
  for (const p of all) {
    const last = out[out.length - 1];
    if (last && Math.abs(new Date(p.ts).getTime() - new Date(last.ts).getTime()) < 2000) continue;
    out.push(p);
  }
  return out.slice(-300);
}

export default function Dashboard() {
  const live = useLive();
  const polled = useApi<Summary>("/dashboard/summary", { enabled: !live.summary });
  const summary = live.summary ?? polled.data;
  const initialLive = useApi<LivePoint[]>("/dashboard/live-power?minutes=15");
  const overview = useApi<OverviewRoom[]>("/dashboard/overview", { refreshOn: ["summary", "room", "command"], throttleMs: 3000 });
  const today = useApi<{ series: HistoryPoint[]; currency: string }>("/dashboard/history?range=24h", { refreshOn: ["summary"], throttleMs: 30000 });
  const alerts = useApi<Alert[]>("/alerts?status=open&limit=6", { refreshOn: ["alert"] });
  const devices = useApi<Device[]>("/devices", { refreshOn: ["device", "summary"], throttleMs: 5000 });

  const points = useMemo(() => mergeLivePoints(initialLive.data ?? [], live.livePoints), [initialLive.data, live.livePoints]);

  if (!summary) return polled.error ? <ErrorBanner error={polled.error} onRetry={polled.reload} /> : <Spinner label="Loading dashboard" />;
  const cur = summary.currency;
  const sav = summary.estimated_savings;
  const simSavings = (sav.by_source.simulation ?? 0) > 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Campus energy overview</h1>
          <p className="text-sm text-ink-2">
            Updated {timeAgo(summary.generated_at)} · tariff {formatMoney(summary.tariff_rate_now, cur)}/kWh · grid factor {summary.carbon_factor_kg_per_kwh} kg CO₂/kWh
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">{summary.data_sources_live.map((s) => <SourceBadge key={s} source={s} />)}</div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <StatTile label="Live power" icon={<Bolt className="size-4" />} value={formatPower(summary.live_power_w)}
          sub={`${summary.appliances.on} of ${summary.appliances.total} appliances on`} />
        <StatTile label="Energy today" icon={<Plug className="size-4" />} value={formatKwh(summary.energy_today_kwh)}
          sub={`${formatMoney(summary.cost_today, cur)} at configured tariff`} />
        <StatTile label="Wasted in vacant rooms" icon={<Trash2 className="size-4" />} value={formatKwh(summary.wasted_today_kwh)}
          sub={`${formatMoney(summary.wasted_cost_today, cur)} · ${formatKg(summary.wasted_co2_today_kg)} CO₂`}
          footnote="Measured: energy drawn while occupancy = vacant" />
        <StatTile label="Estimated savings today" icon={<PiggyBank className="size-4" />} value={formatKwh(sav.today_kwh)} tone="estimate"
          sub={`${sav.active_episodes} active · ${sav.episodes} shutdown episodes`} footnote={simSavings ? "From simulated shutdowns" : undefined} />
        <StatTile label="Estimated cost savings" icon={<Coins className="size-4" />} value={formatMoney(sav.today_cost, cur)} tone="estimate"
          sub={`${formatMoney(sav.total_cost, cur)} all time`} />
        <StatTile label="Estimated CO₂ avoided" icon={<Leaf className="size-4" />} value={formatKg(sav.today_co2_kg)} tone="estimate"
          sub={`${formatKg(sav.total_co2_kg)} all time · ${formatKg(summary.carbon_today_kg)} emitted today`} />
      </div>
      <p className="-mt-1 text-xs text-muted">{sav.label}</p>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Live power" subtitle="Total of all appliances with fresh readings · last 15 min"
          actions={<span className="text-3xl font-semibold tracking-tight">{formatPower(summary.live_power_w)}</span>}>
          {points.length > 1 ? <LivePowerChart points={points} /> : <Empty>Waiting for telemetry…</Empty>}
        </Card>
        <Card title="Status" subtitle="Rooms, devices and alerts">
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <Stat label="Rooms occupied" value={`${summary.rooms.occupied}/${summary.rooms.total}`} />
            <Stat label="Occupancy unknown" value={summary.rooms.unknown} warn={summary.rooms.unknown > 0} />
            <Stat label="Devices online" value={`${summary.devices.online ?? 0}/${summary.devices.total}`} warn={(summary.devices.offline ?? 0) > 0} />
            <Stat label="Open alerts" value={summary.alerts.open} warn={summary.alerts.open > 0} />
            <Stat label="Anomaly detector" value={summary.ml.method === "isolation_forest" ? "Isolation Forest" : "Rule fallback"} />
            <Stat label="Model" value={summary.ml.model_version ?? "—"} />
          </dl>
        </Card>
      </div>

      <Card title="Room occupancy & appliances" subtitle="Live state from the decision engine" actions={<Link to="/rooms" className="text-sm text-accent-ink hover:underline">Manage rooms</Link>}>
        {overview.error && <ErrorBanner error={overview.error} onRetry={overview.reload} />}
        {!overview.data ? <Spinner /> : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {overview.data.map((r) => <RoomTile key={r.id} room={r} />)}
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Energy by hour — last 24 h" subtitle="Stacked: energy used while occupied and energy drawn in vacant rooms"
          actions={<Legend items={[{ color: "var(--series-1)", label: "Used (occupied)" }, { color: "var(--series-2)", label: "Wasted (vacant)" }]} />}>
          {today.data ? <EnergyBarChart series={today.data.series} currency={today.data.currency} labelFmt={(p) => p.slice(11, 16)} /> : <Spinner />}
        </Card>
        <AlertsCard alerts={alerts.data} reload={alerts.reload} />
      </div>

      <Card title="Device health" subtitle="Controllers reporting telemetry" actions={<Link to="/devices" className="text-sm text-accent-ink hover:underline">All devices</Link>}>
        {!devices.data ? <Spinner /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="text-left text-xs text-muted"><tr><th className="py-1.5">Device</th><th>Type</th><th>Status</th><th>Sensor</th><th>Health</th><th>Last seen</th></tr></thead>
              <tbody>
                {devices.data.map((d) => (
                  <tr key={d.id} className="border-t border-line">
                    <td className="py-2 font-medium">{d.name}</td>
                    <td><SourceBadge source={d.source} compact /></td>
                    <td><StatusPill tone={connectionTone(d.connection_status)} label={humanize(d.connection_status)} /></td>
                    <td><StatusPill tone={d.sensor_status === "fault" ? "critical" : d.sensor_status === "ok" ? "good" : "neutral"} label={d.sensor_status} /></td>
                    <td className="tabular">{d.health.score}/100</td>
                    <td className="text-ink-2">{timeAgo(d.last_seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function Stat({ label, value, warn }: { label: string; value: React.ReactNode; warn?: boolean }) {
  return (
    <div className="rounded-lg bg-surface-2 px-3 py-2">
      <dt className="text-xs text-ink-2">{label}</dt>
      <dd className={cx("mt-0.5 truncate font-semibold", warn ? "text-critical-ink" : "text-ink")}>{value}</dd>
    </div>
  );
}

function RoomTile({ room }: { room: OverviewRoom }) {
  const vacantMin = room.vacant_since ? Math.round((Date.now() - new Date(room.vacant_since).getTime()) / 60000) : null;
  return (
    <Link to={`/rooms/${room.id}`} className="block rounded-lg border border-line p-3 transition hover:border-accent">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-medium">{room.name}</div>
          <div className="text-xs text-muted">{humanize(room.room_type)} · {formatPower(room.power_w)}</div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <StatusPill tone={occupancyTone(room.occupancy_state)} label={humanize(room.occupancy_state)} icon={<Users className="size-3.5" />} />
          {room.occupancy_source && <SourceBadge source={room.occupancy_source} compact />}
        </div>
      </div>
      <div className="mt-1 text-xs text-ink-2">
        {room.occupancy_state === "occupied" && room.people_count != null && `${room.people_count} people detected`}
        {room.occupancy_state === "vacant" && vacantMin != null && `Vacant for ${vacantMin} min`}
        {room.occupancy_state === "unknown" && "Occupancy unknown — automation blocked"}
        {room.manual_override && " · manual override"}
      </div>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {room.appliances.map((a) => (
          <li key={a.id} className={cx("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs",
            a.decision === "auto_shutdown" || a.decision === "recommend_shutdown" ? "border-serious" : "border-line")}
            title={`${a.name}: ${a.state}${a.power_w != null ? `, ${formatPower(a.power_w)}` : ""}${a.decision && a.decision !== "none" ? ` — ${humanize(a.decision)}` : ""}`}>
            <span className={cx("size-2 rounded-full", a.state === "on" ? "bg-good" : a.state === "off" ? "bg-[var(--axis)]" : "bg-warning")} aria-hidden />
            <span className="text-ink">{a.name}</span>
            <span className="text-muted">{a.state === "unknown" ? "?" : a.state}</span>
            {a.anomaly && <span className="font-semibold text-critical-ink">⚠ anomaly</span>}
            {a.essential && <span className="text-muted">· essential</span>}
          </li>
        ))}
      </ul>
    </Link>
  );
}

function AlertsCard({ alerts, reload }: { alerts: Alert[] | null; reload: () => void }) {
  const { can } = useAuth();
  const toast = useToast();
  const ack = async (id: number) => {
    try {
      await post(`/alerts/${id}/acknowledge`);
      toast("good", "Alert acknowledged");
      reload();
    } catch (e) {
      toast("critical", (e as Error).message);
    }
  };
  return (
    <Card title="Open alerts" actions={<Link to="/alerts" className="text-sm text-accent-ink hover:underline">View all</Link>}>
      {!alerts ? <Spinner /> : alerts.length === 0 ? <Empty>No open alerts</Empty> : (
        <ul className="flex flex-col gap-2">
          {alerts.map((a) => (
            <li key={a.id} className="rounded-lg border border-line p-2.5">
              <div className="flex items-start justify-between gap-2">
                <StatusPill tone={severityTone(a.severity)} label={humanize(a.alert_type)} />
                <span className="text-xs text-muted">{timeAgo(a.last_seen_at)}</span>
              </div>
              <p className="mt-1 text-sm font-medium">{a.title}</p>
              {a.recommendation && <p className="text-xs text-ink-2">{a.recommendation}</p>}
              <div className="mt-1.5 flex items-center gap-2">
                {a.acknowledged ? <span className="text-xs text-muted">Acknowledged by {a.acknowledged_by}</span>
                  : can("operator") && <Button className="px-2 py-1 text-xs" onClick={() => ack(a.id)}>Acknowledge</Button>}
                {a.source && <SourceBadge source={a.source} compact />}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
