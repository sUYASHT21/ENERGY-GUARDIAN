import { useState } from "react";
import type { HistoryPoint, Room } from "../api/types";
import { EnergyBarChart, Legend, RoomBarChart } from "../components/charts";
import { Card, Empty, ErrorBanner, SourceBadge, Spinner, cx, inputCls, type Tint } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { formatKwh, formatMoney } from "../lib/format";

const RANGES = [
  { key: "24h", label: "24 hours", hours: 24 },
  { key: "7d", label: "7 days", hours: 168 },
  { key: "30d", label: "30 days", hours: 720 },
] as const;

export default function History() {
  const [range, setRange] = useState<(typeof RANGES)[number]["key"]>("7d");
  const [roomId, setRoomId] = useState<string>("");
  const [showTable, setShowTable] = useState(false);
  const rooms = useApi<Room[]>("/rooms");
  const hist = useApi<{ series: HistoryPoint[]; currency: string; timezone: string; group: string }>(
    `/dashboard/history?range=${range}${roomId ? `&room_id=${roomId}` : ""}`, { refreshOn: ["summary"], throttleMs: 30000 });
  const hours = RANGES.find((r) => r.key === range)!.hours;
  const byRoom = useApi<{ room: string; energy_kwh: number; wasted_kwh: number; cost: number }[]>(`/dashboard/rooms?hours=${hours}`, { refreshOn: ["summary"], throttleMs: 30000 });

  const series = hist.data?.series ?? [];
  const tot = series.reduce((a, p) => ({ e: a.e + p.energy_kwh, w: a.w + p.wasted_kwh, c: a.c + p.cost, sim: a.sim + p.simulation_kwh, hw: a.hw + p.hardware_kwh + p.emulator_kwh }), { e: 0, w: 0, c: 0, sim: 0, hw: 0 });
  const cur = hist.data?.currency ?? "INR";
  const labelFmt = (p: string) => (hist.data?.group === "day" ? p.slice(5) : p.slice(11, 16));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="display text-[34px] text-ink sm:text-[44px]">Energy <em>history</em></h1>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-full bg-surface-2 p-1" role="group" aria-label="Time range">
            {RANGES.map((r) => (
              <button key={r.key} onClick={() => setRange(r.key)} aria-pressed={range === r.key}
                className={cx("rounded-full px-3.5 py-1 text-sm transition", range === r.key ? "bg-ink font-[480] text-surface" : "text-ink-2")}>{r.label}</button>
            ))}
          </div>
          <select className={cx(inputCls, "w-auto")} value={roomId} onChange={(e) => setRoomId(e.target.value)} aria-label="Room filter">
            <option value="">All rooms</option>
            {rooms.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </div>
      </div>
      <ErrorBanner error={hist.error} onRetry={hist.reload} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi tint="sky" label="Energy" value={formatKwh(tot.e)} />
        <Kpi tint="rose" label="Wasted (vacant rooms)" value={formatKwh(tot.w)} sub={tot.e ? `${((tot.w / tot.e) * 100).toFixed(1)}% of total` : undefined} />
        <Kpi tint="butter" label="Cost" value={formatMoney(tot.c, cur)} />
        <Kpi tint="lilac" label="Data source" value={<span className="flex flex-wrap gap-1">{tot.sim > 0 && <SourceBadge source="simulation" />}{tot.hw > 0 && <SourceBadge source="hardware" />}{tot.e === 0 && "—"}</span>}
          sub={tot.sim > 0 ? `${formatKwh(tot.sim)} simulated` : undefined} />
      </div>
      <Card title={hist.data?.group === "day" ? "Energy per day" : "Energy per hour"} subtitle={`Timezone ${hist.data?.timezone ?? ""}. Periods without telemetry show as zero.`}
        actions={<><Legend items={[{ color: "var(--series-1)", label: "Used (occupied)" }, { color: "var(--series-2)", label: "Wasted (vacant)" }]} />
          <button className="text-xs text-ink underline-offset-4 hover:underline" onClick={() => setShowTable(!showTable)}>{showTable ? "Hide table" : "Show table"}</button></>}>
        {!hist.data ? <Spinner /> : series.length === 0 ? <Empty>No data</Empty> : <EnergyBarChart series={series} currency={cur} labelFmt={labelFmt} height={300} />}
        {showTable && (
          <div className="mt-4 max-h-80 overflow-auto">
            <table className="w-full text-sm tabular">
              <thead className="sticky top-0 bg-surface text-left text-xs text-muted"><tr><th>Period</th><th>Energy</th><th>Wasted</th><th>Cost</th><th>Simulated</th><th>Hardware</th></tr></thead>
              <tbody>{series.map((p) => (
                <tr key={p.period} className="border-t border-line"><td className="py-1">{p.period}</td><td>{p.energy_kwh.toFixed(3)}</td><td>{p.wasted_kwh.toFixed(3)}</td><td>{p.cost.toFixed(2)}</td><td>{p.simulation_kwh.toFixed(3)}</td><td>{(p.hardware_kwh + p.emulator_kwh).toFixed(3)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Card>
      <Card title="Energy by room" subtitle={`Last ${RANGES.find((r) => r.key === range)!.label}`}
        actions={<Legend items={[{ color: "var(--series-1)", label: "Used (occupied)" }, { color: "var(--series-2)", label: "Wasted (vacant)" }]} />}>
        {!byRoom.data ? <Spinner /> : byRoom.data.length === 0 ? <Empty>No data</Empty> : <RoomBarChart rows={byRoom.data} />}
      </Card>
    </div>
  );
}

function Kpi({ label, value, sub, tint }: { label: string; value: React.ReactNode; sub?: string; tint: Tint }) {
  return (
    <div className={`rounded-3xl p-5 tint-${tint}`}>
      <div className="text-[13px] opacity-80">{label}</div>
      <div className="display mt-1 text-[28px] leading-tight">{value}</div>
      {sub && <div className="text-[12px] opacity-75">{sub}</div>}
    </div>
  );
}
