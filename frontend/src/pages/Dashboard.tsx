import { useMemo } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Bolt, Leaf, Plug, Trash2, Users } from "lucide-react";
import { post } from "../api/client";
import type { Alert, Device, HistoryPoint, LivePoint, OverviewRoom, Summary } from "../api/types";
import { EnergyBarChart, Legend, LivePowerChart } from "../components/charts";
import {
  Button, Card, Empty, ErrorBanner, SourceBadge, Spinner, StatTile, StatusPill, connectionTone, cx, occupancyTone,
  pillGhost, pillPrimary, severityTone, textLink, useToast, type Tint,
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
    <div className="flex flex-col gap-6">
      <section className="grid grid-cols-1 items-stretch gap-6 lg:grid-cols-12">
        <div className="flex flex-col justify-center lg:col-span-7">
          <div className="mb-3 flex flex-wrap items-center gap-2 text-[14px] text-tag">
            <span>Campus energy overview</span>
            {summary.data_sources_live.map((s) => <SourceBadge key={s} source={s} />)}
          </div>
          <h1 className="display text-[40px] text-ink sm:text-[56px] sm:leading-[1.08]">
            Energy that switches off <em>when the room does.</em>
          </h1>
          <p className="mt-4 max-w-xl text-[16px] leading-relaxed text-muted">
            {summary.rooms.occupied} of {summary.rooms.total} rooms occupied · {summary.appliances.on} appliances running ·
            tariff {formatMoney(summary.tariff_rate_now, cur)}/kWh · grid factor {summary.carbon_factor_kg_per_kwh} kg CO₂/kWh ·
            updated {timeAgo(summary.generated_at)}
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            <Link to="/alerts" className={pillPrimary}>Review alerts{summary.alerts.open ? ` (${summary.alerts.open})` : ""} <ArrowRight className="size-4" /></Link>
            <Link to="/simulation" className={pillGhost}>Run a scenario</Link>
          </div>
        </div>
        <Card variant="peach" className="lg:col-span-5" eyebrow="Estimated savings · today" bodyClass="px-6 pb-6 pt-1">
          <div className="display text-[56px] leading-none">{formatKwh(sav.today_kwh)}</div>
          <div className="mt-3 grid grid-cols-2 gap-3 text-[14px]">
            <div className="rounded-2xl bg-white/50 px-3 py-2 dark:bg-black/20"><div className="opacity-75">Cost avoided</div><div className="text-[18px] font-[500]">{formatMoney(sav.today_cost, cur)}</div></div>
            <div className="rounded-2xl bg-white/50 px-3 py-2 dark:bg-black/20"><div className="opacity-75">CO₂ avoided</div><div className="text-[18px] font-[500]">{formatKg(sav.today_co2_kg)}</div></div>
          </div>
          <p className="mt-3 text-[13px]">
            {sav.active_episodes} active · {sav.episodes} shutdown episodes · {formatKwh(sav.total_kwh)} all time{simSavings ? " · from simulated shutdowns" : ""}
          </p>
          <div className="mt-3 inline-flex rounded-full bg-white/50 px-2.5 py-0.5 text-[11px] font-[500] uppercase tracking-wide dark:bg-black/20">Estimate</div>
          <p className="mt-2 text-[12px] leading-snug opacity-80">{sav.label}</p>
        </Card>
      </section>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile tint="sky" label="Live power" icon={<Bolt className="size-4" />} value={formatPower(summary.live_power_w)}
          sub={`${summary.appliances.on} of ${summary.appliances.total} appliances on`} />
        <StatTile tint="butter" label="Energy today" icon={<Plug className="size-4" />} value={formatKwh(summary.energy_today_kwh)}
          sub={`${formatMoney(summary.cost_today, cur)} at configured tariff`} />
        <StatTile tint="rose" label="Wasted in vacant rooms" icon={<Trash2 className="size-4" />} value={formatKwh(summary.wasted_today_kwh)}
          sub={`${formatMoney(summary.wasted_cost_today, cur)} · ${formatKg(summary.wasted_co2_today_kg)} CO₂`}
          footnote="Measured: energy drawn while occupancy = vacant" />
        <StatTile tint="sage" label="Carbon emitted today" icon={<Leaf className="size-4" />} value={formatKg(summary.carbon_today_kg)}
          sub={`${formatKg(sav.total_co2_kg)} avoided all time (estimate)`} />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2" eyebrow="Live power" title="Total of all appliances with fresh readings" subtitle="Last 15 minutes"
          actions={<span className="display text-[40px] leading-none">{formatPower(summary.live_power_w)}</span>}>
          {points.length > 1 ? <LivePowerChart points={points} height={240} /> : <Empty>Waiting for telemetry…</Empty>}
        </Card>
        <Card variant="mist" eyebrow="System" title="Rooms, devices and alerts">
          <dl className="grid grid-cols-2 gap-2.5 text-sm">
            <Stat tint="sky" label="Rooms occupied" value={`${summary.rooms.occupied}/${summary.rooms.total}`} />
            <Stat tint={summary.rooms.unknown > 0 ? "butter" : "plain"} label="Occupancy unknown" value={summary.rooms.unknown} />
            <Stat tint={(summary.devices.offline ?? 0) > 0 ? "rose" : "sage"} label="Devices online" value={`${summary.devices.online ?? 0}/${summary.devices.total}`} />
            <Stat tint={summary.alerts.open > 0 ? "rose" : "plain"} label="Open alerts" value={summary.alerts.open} />
            <Stat tint="lilac" label="Anomaly detector" value={summary.ml.method === "isolation_forest" ? "Isolation Forest" : "Rule fallback"} />
            <Stat tint="plain" label="Model" value={summary.ml.model_version ?? "—"} />
          </dl>
        </Card>
      </div>

      <Card eyebrow="Rooms" title="Occupancy & appliances" subtitle="Live state from the decision engine" actions={<Link to="/rooms" className={textLink}>Manage rooms →</Link>}>
        {overview.error && <ErrorBanner error={overview.error} onRetry={overview.reload} />}
        {!overview.data ? <Spinner /> : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {overview.data.map((r) => <RoomTile key={r.id} room={r} />)}
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2" eyebrow="Last 24 hours" title="Energy by hour" subtitle="Stacked: energy used while occupied and energy drawn in vacant rooms"
          actions={<Legend items={[{ color: "var(--series-1)", label: "Used (occupied)" }, { color: "var(--series-2)", label: "Wasted (vacant)" }]} />}>
          {today.data ? <EnergyBarChart series={today.data.series} currency={today.data.currency} labelFmt={(p) => p.slice(11, 16)} /> : <Spinner />}
        </Card>
        <AlertsCard alerts={alerts.data} reload={alerts.reload} />
      </div>

      <Card eyebrow="Controllers" title="Device health" actions={<Link to="/devices" className={textLink}>All devices →</Link>}>
        {!devices.data ? <Spinner /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="text-left text-[13px] text-tag"><tr><th className="py-2 font-[450]">Device</th><th className="font-[450]">Type</th><th className="font-[450]">Status</th><th className="font-[450]">Sensor</th><th className="font-[450]">Health</th><th className="font-[450]">Last seen</th></tr></thead>
              <tbody>
                {devices.data.map((d) => (
                  <tr key={d.id} className="border-t border-line">
                    <td className="py-2.5 font-[480]">{d.name}</td>
                    <td><SourceBadge source={d.source} compact /></td>
                    <td><StatusPill tone={connectionTone(d.connection_status)} label={humanize(d.connection_status)} /></td>
                    <td><StatusPill tone={d.sensor_status === "fault" ? "critical" : d.sensor_status === "ok" ? "good" : "neutral"} label={d.sensor_status} /></td>
                    <td><HealthBar score={d.health.score} /></td>
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

function HealthBar({ score }: { score: number }) {
  const color = score >= 80 ? "var(--good)" : score >= 50 ? "var(--warning)" : "var(--critical)";
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-16 rounded-full bg-surface-2"><span className="block h-1.5 rounded-full" style={{ width: `${score}%`, background: color }} /></span>
      <span className="tabular text-[13px] text-ink-2">{score}</span>
    </span>
  );
}

function Stat({ label, value, tint }: { label: string; value: React.ReactNode; tint: Tint | "plain" }) {
  return (
    <div className={cx("rounded-2xl px-3.5 py-2.5", tint === "plain" ? "bg-surface text-ink" : `tint-${tint}`)}>
      <dt className="text-[12px] opacity-75">{label}</dt>
      <dd className="mt-0.5 truncate text-[15px] font-[500]">{value}</dd>
    </div>
  );
}

function RoomTile({ room }: { room: OverviewRoom }) {
  const vacantMin = room.vacant_since ? Math.round((Date.now() - new Date(room.vacant_since).getTime()) / 60000) : null;
  return (
    <Link to={`/rooms/${room.id}`} className={cx("block rounded-2xl p-4 transition hover:-translate-y-0.5 hover:shadow-float",
      room.occupancy_state === "occupied" ? "bg-[var(--t-sky)]/45" : room.occupancy_state === "vacant" ? "bg-surface-2" : "bg-[var(--t-butter)]/60")}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="display truncate text-[20px]">{room.name}</div>
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
          <li key={a.id} className={cx("inline-flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 text-xs",
            a.decision === "auto_shutdown" || a.decision === "recommend_shutdown" ? "ring-2 ring-serious" : "")}
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
    <Card eyebrow="Attention" title="Open alerts" actions={<Link to="/alerts" className={textLink}>View all →</Link>}>
      {!alerts ? <Spinner /> : alerts.length === 0 ? <Empty>No open alerts</Empty> : (
        <ul className="flex flex-col gap-2">
          {alerts.map((a) => (
            <li key={a.id} className="rounded-2xl bg-surface-2 p-3">
              <div className="flex items-start justify-between gap-2">
                <StatusPill tone={severityTone(a.severity)} label={humanize(a.alert_type)} />
                <span className="text-xs text-muted">{timeAgo(a.last_seen_at)}</span>
              </div>
              <p className="mt-1.5 text-sm font-[480]">{a.title}</p>
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
