import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, ChevronDown, ChevronRight, Hand, Pencil, Plus, Power, PowerOff, Trash2, XCircle } from "lucide-react";
import { del, patch, post } from "../api/client";
import type { Appliance, Command, Decision, Device, RoomDetail as RoomDetailT } from "../api/types";
import { LivePowerChart } from "../components/charts";
import {
  Button, Card, Empty, ErrorBanner, Field, Modal, SourceBadge, Spinner, StatusPill, commandTone, connectionTone, cx, inputCls,
  occupancyTone, useToast,
} from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useApi } from "../hooks/useApi";
import { DAYS, formatDateTime, formatPower, humanize, timeAgo } from "../lib/format";
import { RoomForm } from "./Rooms";

export const APPLIANCE_TYPES = ["light", "fan", "ac", "projector", "computer", "lab_equipment", "heater", "refrigerator", "server", "emergency_light", "other"];

export default function RoomDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { can } = useAuth();
  const toast = useToast();
  const detail = useApi<RoomDetailT>(`/rooms/${id}`, { refreshOn: ["summary", "command", "room"], throttleMs: 3000 });
  const power = useApi<{ ts: string; power_w: number }[]>(`/dashboard/live-power?minutes=15&room_id=${id}`, { refreshOn: ["summary"], throttleMs: 10000 });
  const [editing, setEditing] = useState(false);
  const [addingAppliance, setAddingAppliance] = useState(false);
  const [editAppliance, setEditAppliance] = useState<Appliance | null>(null);

  if (detail.error) return <ErrorBanner error={detail.error} onRetry={detail.reload} />;
  if (!detail.data) return <Spinner />;
  const { room, appliances, devices, schedules } = detail.data;

  const override = async (enabled: boolean) => {
    const minutes = enabled ? Number(prompt("Override duration in minutes (empty = until disabled)", "60") || 0) || null : null;
    try {
      await post(`/rooms/${room.id}/override`, { enabled, minutes, reason: enabled ? "set from dashboard" : "" });
      toast("good", enabled ? "Manual override enabled — automation will not switch this room" : "Override disabled");
      detail.reload();
    } catch (e) { toast("critical", (e as Error).message); }
  };
  const remove = async () => {
    if (!confirm(`Delete ${room.name} and all its appliances and schedules?`)) return;
    try { await del(`/rooms/${room.id}`); toast("good", "Room deleted"); nav("/rooms"); } catch (e) { toast("critical", (e as Error).message); }
  };

  return (
    <div className="flex flex-col gap-4">
      <Link to="/rooms" className="inline-flex items-center gap-1 text-sm text-ink-2 hover:text-ink"><ArrowLeft className="size-4" />All rooms</Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{room.name}</h1>
          <p className="text-sm text-ink-2">{humanize(room.room_type)} · {room.building || "no building"} · capacity {room.capacity} · min. vacancy {room.min_vacancy_minutes} min</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusPill tone={occupancyTone(room.occupancy_state)} label={`${humanize(room.occupancy_state)}${room.people_count ? ` · ${room.people_count} people` : ""}`} />
            {room.occupancy_source && <SourceBadge source={room.occupancy_source} />}
            {room.vacant_since && <span className="text-xs text-ink-2">vacant since {formatDateTime(room.vacant_since)}</span>}
            {room.manual_override && <StatusPill tone="warning" label={`Manual override${room.override_until ? ` until ${formatDateTime(room.override_until)}` : ""}`} icon={<Hand className="size-3.5" />} />}
            {!room.auto_control_enabled && <StatusPill tone="neutral" label="Automation disabled" />}
          </div>
        </div>
        {can("operator") && (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => override(!room.manual_override)}><Hand className="size-4" />{room.manual_override ? "End override" : "Manual override"}</Button>
            <Button onClick={() => setEditing(true)}><Pencil className="size-4" />Edit</Button>
            <Button variant="ghost" onClick={remove} aria-label="Delete room"><Trash2 className="size-4" /></Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Room power — last 15 min">
          {power.data && power.data.length > 1 ? <LivePowerChart points={power.data} height={180} /> : <Empty>No recent telemetry</Empty>}
        </Card>
        <Card title="Controllers & schedule">
          <ul className="flex flex-col gap-1.5 text-sm">
            {devices.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-2">
                <span className="font-medium">{d.name}</span>
                <span className="flex gap-1"><StatusPill tone={connectionTone(d.connection_status)} label={d.connection_status} /><StatusPill tone={d.sensor_status === "fault" ? "critical" : d.sensor_status === "ok" ? "good" : "neutral"} label={`sensor ${d.sensor_status}`} /></span>
              </li>
            ))}
            {devices.length === 0 && <li className="text-muted">No controller assigned</li>}
          </ul>
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted">Scheduled sessions</h3>
          <ul className="mt-1 text-sm text-ink-2">
            {schedules.length === 0 && <li>None — <Link className="text-accent-ink hover:underline" to="/schedules">add schedules</Link></li>}
            {schedules.map((s) => <li key={s.id}>{DAYS[s.day_of_week]} {s.start_time}–{s.end_time} {s.label && `· ${s.label}`}{!s.enabled && " (disabled)"}</li>)}
          </ul>
        </Card>
      </div>

      <Card title="Appliances" subtitle="Each row shows the latest deterministic decision and every check behind it"
        actions={can("operator") && <Button onClick={() => setAddingAppliance(true)}><Plus className="size-4" />Add appliance</Button>}>
        {appliances.length === 0 ? <Empty>No appliances yet</Empty> : (
          <div className="flex flex-col gap-3">
            {appliances.map((a) => <ApplianceRow key={a.id} a={a} onChanged={detail.reload} onEdit={() => setEditAppliance(a)} />)}
          </div>
        )}
      </Card>

      {editing && <RoomForm room={room} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); detail.reload(); }} />}
      {(addingAppliance || editAppliance) && (
        <ApplianceForm roomId={room.id} appliance={editAppliance ?? undefined}
          onClose={() => { setAddingAppliance(false); setEditAppliance(null); }}
          onSaved={() => { setAddingAppliance(false); setEditAppliance(null); detail.reload(); }} />
      )}
    </div>
  );
}

function decisionPill(d: Decision) {
  if (d.action === "auto_shutdown") return <StatusPill tone="serious" label={d.execution_mode === "dry_run" ? "Dry-run shutdown" : `Auto shutdown (${d.execution_mode})`} />;
  if (d.action === "recommend_shutdown") return <StatusPill tone="warning" label="Shutdown recommended" />;
  if (!d.data_ok) return <StatusPill tone="warning" label="Insufficient data" />;
  return <StatusPill tone="good" label="No wastage" />;
}

function ApplianceRow({ a, onChanged, onEdit }: { a: Appliance & { decision: Decision }; onChanged: () => void; onEdit: () => void }) {
  const { can, user } = useAuth();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const send = async (action: "on" | "off", dryRun = false) => {
    let confirmEssential = false;
    if (action === "off" && a.essential) {
      if (user?.role !== "admin") return toast("critical", "Essential loads can only be switched off by an admin");
      if (!confirm(`${a.name} is marked ESSENTIAL. Switch it off anyway?`)) return;
      confirmEssential = true;
    }
    setBusy(action + (dryRun ? "-dry" : ""));
    try {
      const c = await post<Command>("/commands", { appliance_id: a.id, action, dry_run: dryRun, confirm_essential: confirmEssential });
      toast(c.status === "blocked" ? "critical" : "good", c.status === "blocked" ? `Blocked: ${c.error}` : `Command ${c.action.toUpperCase()} ${c.status} (${c.mode})`);
      onChanged();
    } catch (e) { toast("critical", (e as Error).message); } finally { setBusy(null); }
  };
  const toggleOverride = async () => {
    try { await patch(`/appliances/${a.id}`, { manual_override: !a.manual_override }); onChanged(); } catch (e) { toast("critical", (e as Error).message); }
  };

  const d = a.decision;
  const groups: [string, string][] = [["data", "Data quality"], ["waste", "Wastage"], ["safety", "Safety policy"], ["mode", "Mode / hardware gate"]];
  return (
    <div className="rounded-lg border border-line">
      <div className="flex flex-wrap items-center gap-3 p-3">
        <button onClick={() => setOpen(!open)} className="rounded p-1 text-muted hover:bg-surface-2" aria-expanded={open} aria-label={`Show decision checks for ${a.name}`}>
          {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        </button>
        <div className="min-w-[180px] flex-1">
          <div className="flex flex-wrap items-center gap-2 font-medium">
            {a.name}
            {a.essential && <StatusPill tone="info" label="Essential" />}
            {!a.auto_off_allowed && <StatusPill tone="neutral" label="Manual only" />}
            {a.manual_override && <StatusPill tone="warning" label="Override" />}
            {a.anomaly_streak >= 2 && <StatusPill tone="critical" label="Anomaly" />}
          </div>
          <div className="text-xs text-muted">{humanize(a.appliance_type)} · ch {a.relay_channel} · rated {formatPower(a.rated_power_w)} · reading {timeAgo(a.last_reading_at)}</div>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <StatusPill tone={a.state === "on" ? "good" : a.state === "off" ? "neutral" : "warning"} label={a.state.toUpperCase()} />
          <span className="tabular w-20 text-right font-semibold">{formatPower(a.last_power_w)}</span>
          {a.last_source && <SourceBadge source={a.last_source} compact />}
        </div>
        <div className="flex items-center gap-2">{decisionPill(d)}</div>
        {can("operator") && (
          <div className="flex flex-wrap gap-1.5">
            <Button className="px-2 py-1 text-xs" busy={busy === "on"} onClick={() => send("on")}><Power className="size-3.5" />On</Button>
            <Button className="px-2 py-1 text-xs" busy={busy === "off"} onClick={() => send("off")}><PowerOff className="size-3.5" />Off</Button>
            <Button className="px-2 py-1 text-xs" variant="ghost" busy={busy === "off-dry"} onClick={() => send("off", true)} title="Record what would happen without sending anything">Dry-run off</Button>
            <Button className="px-2 py-1 text-xs" variant="ghost" onClick={toggleOverride}>{a.manual_override ? "Clear override" : "Override"}</Button>
            <Button className="px-2 py-1 text-xs" variant="ghost" onClick={onEdit} aria-label={`Edit ${a.name}`}><Pencil className="size-3.5" /></Button>
          </div>
        )}
      </div>
      {open && (
        <div className="border-t border-line bg-surface-2/50 p-3 text-sm">
          <p className="font-medium">{d.summary}</p>
          {d.notes.map((n) => <p key={n} className="mt-1 text-xs text-ink-2">{n}</p>)}
          <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            {groups.map(([cat, label]) => {
              const checks = d.checks.filter((c) => c.category === cat);
              if (!checks.length) return null;
              return (
                <div key={cat}>
                  <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{label}</h4>
                  <ul className="flex flex-col gap-1">
                    {checks.map((c) => (
                      <li key={c.name} className="flex items-start gap-1.5 text-xs">
                        {c.passed ? <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-good-ink" aria-label="passed" /> : <XCircle className="mt-0.5 size-3.5 shrink-0 text-critical-ink" aria-label="failed" />}
                        <span><span className="font-medium text-ink">{humanize(c.name)}</span> <span className="text-ink-2">— {c.detail}</span></span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
          <RecentCommands applianceId={a.id} />
        </div>
      )}
    </div>
  );
}

function RecentCommands({ applianceId }: { applianceId: number }) {
  const cmds = useApi<Command[]>(`/commands?appliance_id=${applianceId}&limit=5`, { refreshOn: ["command"] });
  if (!cmds.data?.length) return null;
  return (
    <div className="mt-3">
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Recent commands</h4>
      <ul className="flex flex-col gap-1 text-xs">
        {cmds.data.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-2">
            <StatusPill tone={commandTone(c.status)} label={c.status} />
            <span className="font-medium">{c.action.toUpperCase()}</span>
            <span className="text-ink-2">{c.origin} · {c.mode} · {formatDateTime(c.created_at)}</span>
            {c.error && <span className="text-critical-ink">{c.error}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ApplianceForm({ roomId, appliance, onClose, onSaved }: { roomId: number; appliance?: Appliance; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const devices = useApi<Device[]>("/devices");
  const [form, setForm] = useState({
    name: appliance?.name ?? "", appliance_type: appliance?.appliance_type ?? "light", room_id: roomId,
    device_id: appliance?.device_id ?? (null as number | null), relay_channel: appliance?.relay_channel ?? 0,
    rated_power_w: appliance?.rated_power_w ?? 100, standby_threshold_w: appliance?.standby_threshold_w ?? 5,
    essential: appliance?.essential ?? false, auto_off_allowed: appliance?.auto_off_allowed ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (appliance) await patch(`/appliances/${appliance.id}`, form);
      else await post("/appliances", form);
      toast("good", appliance ? "Appliance updated" : "Appliance added");
      onSaved();
    } catch (err) { setError(err as Error); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!appliance || !confirm(`Delete ${appliance.name}?`)) return;
    try { await del(`/appliances/${appliance.id}`); onSaved(); } catch (err) { setError(err as Error); }
  };
  const roomDevices = (devices.data ?? []).filter((d) => d.room_id === roomId || d.room_id === null);
  return (
    <Modal title={appliance ? `Edit ${appliance.name}` : "Add appliance"} onClose={onClose}>
      <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2"><Field label="Name"><input required className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field></div>
        <Field label="Type"><select className={inputCls} value={form.appliance_type} onChange={(e) => setForm({ ...form, appliance_type: e.target.value })}>{APPLIANCE_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}</select></Field>
        <Field label="Controller"><select className={inputCls} value={form.device_id ?? ""} onChange={(e) => setForm({ ...form, device_id: e.target.value ? Number(e.target.value) : null })}>
          <option value="">None</option>{roomDevices.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.kind})</option>)}</select></Field>
        <Field label="Relay channel"><input type="number" min={0} max={63} className={inputCls} value={form.relay_channel} onChange={(e) => setForm({ ...form, relay_channel: Number(e.target.value) })} /></Field>
        <Field label="Rated power (W)"><input type="number" min={1} className={inputCls} value={form.rated_power_w} onChange={(e) => setForm({ ...form, rated_power_w: Number(e.target.value) })} /></Field>
        <Field label="Standby threshold (W)" hint="Power above this counts as running"><input type="number" min={0} className={inputCls} value={form.standby_threshold_w} onChange={(e) => setForm({ ...form, standby_threshold_w: Number(e.target.value) })} /></Field>
        <div className="flex flex-col gap-2 pt-5 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={form.essential} onChange={(e) => setForm({ ...form, essential: e.target.checked })} />Essential load (never auto-off)</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={form.auto_off_allowed} onChange={(e) => setForm({ ...form, auto_off_allowed: e.target.checked })} />Automatic off allowed</label>
        </div>
        <div className="sm:col-span-2"><ErrorBanner error={error} /></div>
        <div className={cx("flex gap-2 sm:col-span-2", appliance ? "justify-between" : "justify-end")}>
          {appliance && <Button type="button" variant="ghost" onClick={remove}><Trash2 className="size-4" />Delete</Button>}
          <div className="flex gap-2"><Button type="button" onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} type="submit">Save</Button></div>
        </div>
      </form>
    </Modal>
  );
}
