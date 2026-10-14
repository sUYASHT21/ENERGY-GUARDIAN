import type { ReactNode } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { HistoryPoint, LivePoint, ScorePoint } from "../api/types";
import { compact, formatKwh, formatMoney, formatPower } from "../lib/format";

const S1 = "var(--series-1)";
const S2 = "var(--series-2)";

/* Shared tooltip shell: text uses ink tokens; identity comes from the swatch beside it. */
function TipBox({ title, rows }: { title: string; rows: { color?: string; label: string; value: string }[] }) {
  return (
    <div className="rounded-2xl bg-surface px-3.5 py-2.5 text-xs shadow-pop">
      <div className="mb-1 font-medium text-ink">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2 text-ink-2">
          {r.color && <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: r.color }} />}
          <span className="flex-1">{r.label}</span>
          <span className="tabular font-medium text-ink">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

export function Legend({ items }: { items: { color: string; label: string; dashed?: boolean }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs text-ink-2">
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5">
          {i.dashed ? (
            <span className="inline-block w-4 border-t-2 border-dashed" style={{ borderColor: i.color }} />
          ) : (
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: i.color }} />
          )}
          {i.label}
        </span>
      ))}
    </div>
  );
}

function ChartFrame({ height, children, label }: { height: number; children: ReactNode; label: string }) {
  return (
    <div style={{ height }} className="w-full" role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height="100%">{children as React.ReactElement}</ResponsiveContainer>
    </div>
  );
}

const hhmm = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

const LIVE = "var(--line-live)";

export function LivePowerChart({ points, height = 220, gradientId = "liveWash" }: { points: LivePoint[]; height?: number; gradientId?: string }) {
  const data = points.map((p) => ({ t: new Date(p.ts).getTime(), power: p.power_w, ts: p.ts }));
  return (
    <ChartFrame height={height} label="Total live power over the last minutes">
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" style={{ stopColor: "var(--wash-live)", stopOpacity: 0.75 }} />
            <stop offset="100%" style={{ stopColor: "var(--wash-live)", stopOpacity: 0.05 }} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t) => hhmm(new Date(t).toISOString())} minTickGap={40} />
        <YAxis tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)} kW` : `${v} W`)} width={56} />
        <Tooltip
          cursor={{ strokeWidth: 1 }}
          content={({ active, payload }) =>
            active && payload?.length ? (
              <TipBox title={new Date(payload[0].payload.t).toLocaleTimeString()} rows={[{ color: LIVE, label: "Total power", value: formatPower(payload[0].payload.power) }]} />
            ) : null
          }
        />
        <Area type="monotone" dataKey="power" stroke={LIVE} strokeWidth={2} fill={`url(#${gradientId})`} isAnimationActive={false} dot={false} activeDot={{ r: 4, fill: LIVE, stroke: "var(--surface)", strokeWidth: 2 }} />
      </AreaChart>
    </ChartFrame>
  );
}

/** Stacked: energy used while occupied (blue) + energy consumed in vacant rooms (orange). */
export function EnergyBarChart({ series, currency, height = 260, labelFmt }: {
  series: HistoryPoint[]; currency: string; height?: number; labelFmt: (p: string) => string;
}) {
  const data = series.map((p) => ({ ...p, used: Math.max(p.energy_kwh - p.wasted_kwh, 0), label: labelFmt(p.period) }));
  return (
    <ChartFrame height={height} label="Energy consumption, split into useful and wasted energy">
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap="20%">
        <CartesianGrid vertical={false} />
        <XAxis dataKey="label" minTickGap={12} />
        <YAxis tickFormatter={(v) => (v >= 10 ? compact(v) : v.toFixed(1))} width={40} />
        <Tooltip
          cursor={{ fill: "var(--surface-2)" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload as HistoryPoint & { used: number; label: string };
            const rows = [
              { color: S1, label: "Used (occupied)", value: formatKwh(p.used) },
              { color: S2, label: "Wasted (vacant)", value: formatKwh(p.wasted_kwh) },
              { label: "Cost", value: formatMoney(p.cost, currency) },
            ];
            if (p.simulation_kwh > 0) rows.push({ label: "of which simulated", value: formatKwh(p.simulation_kwh) });
            if (p.hardware_kwh > 0) rows.push({ label: "of which hardware", value: formatKwh(p.hardware_kwh) });
            return <TipBox title={p.label} rows={rows} />;
          }}
        />
        <Bar dataKey="used" stackId="e" fill={S1} maxBarSize={24} stroke="var(--surface)" strokeWidth={1} isAnimationActive={false} />
        <Bar dataKey="wasted_kwh" stackId="e" fill={S2} maxBarSize={24} radius={[4, 4, 0, 0]} stroke="var(--surface)" strokeWidth={1} isAnimationActive={false} />
      </BarChart>
    </ChartFrame>
  );
}

export function RoomBarChart({ rows, height }: { rows: { room: string; energy_kwh: number; wasted_kwh: number }[]; height?: number }) {
  const data = rows.map((r) => ({ ...r, used: Math.max(r.energy_kwh - r.wasted_kwh, 0) }));
  return (
    <ChartFrame height={height ?? Math.max(160, data.length * 44)} label="Energy by room">
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 4 }}>
        <CartesianGrid horizontal={false} />
        <XAxis type="number" tickFormatter={(v) => (v >= 10 ? compact(v) : v.toFixed(1))} />
        <YAxis type="category" dataKey="room" width={150} tick={{ fontSize: 11 }} />
        <Tooltip
          cursor={{ fill: "var(--surface-2)" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload as { room: string; used: number; wasted_kwh: number; energy_kwh: number };
            return <TipBox title={p.room} rows={[
              { color: S1, label: "Used (occupied)", value: formatKwh(p.used) },
              { color: S2, label: "Wasted (vacant)", value: formatKwh(p.wasted_kwh) },
              { label: "Total", value: formatKwh(p.energy_kwh) },
            ]} />;
          }}
        />
        <Bar dataKey="used" stackId="r" fill={S1} maxBarSize={24} stroke="var(--surface)" strokeWidth={1} isAnimationActive={false} />
        <Bar dataKey="wasted_kwh" stackId="r" fill={S2} maxBarSize={24} radius={[0, 4, 4, 0]} stroke="var(--surface)" strokeWidth={1} isAnimationActive={false} />
      </BarChart>
    </ChartFrame>
  );
}

/** Anomaly score over time for one appliance; scores above 0 are flagged by the model. */
export function ScoreChart({ points, height = 220 }: { points: ScorePoint[]; height?: number }) {
  const data = points.map((p) => ({ t: new Date(p.ts).getTime(), score: p.score, flagged: p.is_anomaly, power: p.power_w }));
  return (
    <ChartFrame height={height} label="Anomaly score over time">
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t) => hhmm(new Date(t).toISOString())} minTickGap={40} />
        <YAxis width={44} tickFormatter={(v) => v.toFixed(2)} />
        <ReferenceLine y={0} stroke="var(--critical)" strokeDasharray="4 4" />
        <Tooltip
          content={({ active, payload }) =>
            active && payload?.length ? (
              <TipBox title={new Date(payload[0].payload.t).toLocaleTimeString()} rows={[
                { color: S1, label: "Anomaly score", value: (payload[0].payload.score as number).toFixed(3) },
                { label: "Flagged", value: payload[0].payload.flagged ? "yes" : "no" },
                { label: "Power", value: formatPower(payload[0].payload.power) },
              ]} />
            ) : null
          }
        />
        <Line type="monotone" dataKey="score" stroke={S1} strokeWidth={2} isAnimationActive={false}
          dot={(props: { cx?: number; cy?: number; payload?: { flagged: boolean }; index?: number }) =>
            props.payload?.flagged && props.cx != null && props.cy != null ? (
              <circle key={props.index} cx={props.cx} cy={props.cy} r={4} fill="var(--critical)" stroke="var(--surface)" strokeWidth={2} />
            ) : <g key={props.index} />
          }
        />
      </LineChart>
    </ChartFrame>
  );
}
