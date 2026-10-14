import { useState, type FormEvent } from "react";
import { KeyRound, Plus, ShieldCheck } from "lucide-react";
import { patch, post } from "../api/client";
import type { Device, Room } from "../api/types";
import { Button, Card, ErrorBanner, Field, Modal, SourceBadge, Spinner, StatusPill, connectionTone, inputCls, useToast } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useApi } from "../hooks/useApi";
import { humanize, timeAgo } from "../lib/format";

export default function Devices() {
  const { can } = useAuth();
  const toast = useToast();
  const devices = useApi<Device[]>("/devices", { refreshOn: ["device", "summary"], throttleMs: 4000 });
  const rooms = useApi<Room[]>("/rooms");
  const [creating, setCreating] = useState(false);
  const [issuedKey, setIssuedKey] = useState<{ uid: string; key: string } | null>(null);
  const roomName = (id: number | null) => rooms.data?.find((r) => r.id === id)?.name ?? "—";

  const validate = async (d: Device) => {
    const msg = d.control_validated
      ? `Revoke control validation for ${d.name}? Hardware commands will be blocked.`
      : `Mark ${d.name} as independently validated for relay control?\n\nOnly do this after wiring, relay ratings and fail-safe behaviour were checked on site. Real switching additionally requires REAL_SWITCHING_ENABLED=true on the server.`;
    if (!confirm(msg)) return;
    try { await patch(`/devices/${d.id}`, { control_validated: !d.control_validated }); devices.reload(); } catch (e) { toast("critical", (e as Error).message); }
  };
  const rotate = async (d: Device) => {
    if (!confirm(`Rotate the API key of ${d.name}? The device must be re-flashed with the new key.`)) return;
    try { const r = await post<{ api_key: string }>(`/devices/${d.id}/rotate-key`); setIssuedKey({ uid: d.uid, key: r.api_key }); } catch (e) { toast("critical", (e as Error).message); }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="display text-[34px] text-ink sm:text-[44px]">Devices <em>&amp; controllers</em></h1>
          <p className="mt-2 text-[16px] text-muted">ESP32 controllers, emulators and simulated nodes. See docs/HARDWARE.md for the HTTP protocol.</p>
        </div>
        {can("admin") && <Button variant="primary" onClick={() => setCreating(true)}><Plus className="size-4" />Register device</Button>}
      </div>
      <ErrorBanner error={devices.error} onRetry={devices.reload} />
      {!devices.data ? <Spinner /> : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {devices.data.map((d) => (
            <Card key={d.id} title={d.name} subtitle={<span className="font-mono">{d.uid}</span>} actions={<SourceBadge source={d.source} />}>
              <div className="flex flex-wrap gap-1.5">
                <StatusPill tone={connectionTone(d.connection_status)} label={humanize(d.connection_status)} />
                <StatusPill tone={d.sensor_status === "fault" ? "critical" : d.sensor_status === "ok" ? "good" : "neutral"} label={`Occupancy sensor: ${d.sensor_status}`} />
                {d.kind === "esp32" && (d.control_validated ? <StatusPill tone="good" label="Control validated" /> : <StatusPill tone="neutral" label="Control not validated" />)}
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <dt className="text-muted">Room</dt><dd>{roomName(d.room_id)}</dd>
                <dt className="text-muted">Health</dt><dd className="tabular">{d.health.score}/100 {d.health.issues.length > 0 && <span className="text-ink-2">({d.health.issues.join(", ")})</span>}</dd>
                <dt className="text-muted">Last seen</dt><dd>{timeAgo(d.last_seen_at)}</dd>
                <dt className="text-muted">Firmware</dt><dd>{d.firmware_version ?? "—"}</dd>
                <dt className="text-muted">Wi-Fi RSSI</dt><dd>{d.rssi_dbm != null ? `${d.rssi_dbm} dBm` : "—"}</dd>
                <dt className="text-muted">Uptime</dt><dd>{d.uptime_s != null ? `${Math.round(d.uptime_s / 60)} min` : "—"}</dd>
                <dt className="text-muted">Free heap</dt><dd>{d.free_heap != null ? `${Math.round(d.free_heap / 1024)} KiB` : "—"}</dd>
                <dt className="text-muted">Appliances</dt><dd>{d.appliance_count}</dd>
                <dt className="text-muted">Errors</dt><dd>{d.error_count}</dd>
              </dl>
              {can("admin") && d.kind !== "simulated" && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {d.kind === "esp32" && <Button className="px-2 py-1 text-xs" onClick={() => validate(d)}><ShieldCheck className="size-3.5" />{d.control_validated ? "Revoke validation" : "Mark validated"}</Button>}
                  <Button className="px-2 py-1 text-xs" variant="ghost" onClick={() => rotate(d)}><KeyRound className="size-3.5" />Rotate key</Button>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
      {creating && <DeviceForm rooms={rooms.data ?? []} onClose={() => setCreating(false)} onCreated={(uid, key) => { setCreating(false); setIssuedKey({ uid, key }); devices.reload(); }} />}
      {issuedKey && (
        <Modal title="Device API key" onClose={() => setIssuedKey(null)}>
          <p className="mt-2 text-[16px] text-muted">This key is shown <b>once</b>. Put it in the firmware's <code>config.h</code> (or pass it to the emulator). Only a hash is stored on the server.</p>
          <dl className="mt-3 space-y-2 text-sm">
            <div><dt className="text-xs text-muted">X-Device-Id</dt><dd className="font-mono">{issuedKey.uid}</dd></div>
            <div><dt className="text-xs text-muted">X-Device-Key</dt><dd className="break-all rounded bg-surface-2 p-2 font-mono">{issuedKey.key}</dd></div>
          </dl>
          <div className="mt-3 flex justify-end gap-2">
            <Button onClick={() => navigator.clipboard?.writeText(issuedKey.key)}>Copy key</Button>
            <Button variant="primary" onClick={() => setIssuedKey(null)}>Done</Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function DeviceForm({ rooms, onClose, onCreated }: { rooms: Room[]; onClose: () => void; onCreated: (uid: string, key: string) => void }) {
  const [form, setForm] = useState<{ uid: string; name: string; kind: string; room_id: number | null; has_occupancy_sensor: boolean }>({ uid: "", name: "", kind: "esp32", room_id: rooms[0]?.id ?? null, has_occupancy_sensor: true });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await post<{ api_key: string; device: Device }>("/devices", form);
      onCreated(r.device.uid, r.api_key);
    } catch (err) { setError(err as Error); } finally { setBusy(false); }
  };
  return (
    <Modal title="Register device" onClose={onClose}>
      <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Device id (uid)" hint="Letters, digits, - _ . :"><input required pattern="[A-Za-z0-9_.:\-]{3,64}" className={inputCls} value={form.uid} onChange={(e) => setForm({ ...form, uid: e.target.value })} placeholder="esp32-lab301" /></Field>
        <Field label="Name"><input required className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Kind" hint="Emulator = protocol test client, labelled separately from hardware">
          <select className={inputCls} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            <option value="esp32">ESP32 hardware</option><option value="emulator">ESP32 emulator</option>
          </select>
        </Field>
        <Field label="Room"><select className={inputCls} value={form.room_id ?? ""} onChange={(e) => setForm({ ...form, room_id: e.target.value ? Number(e.target.value) : null })}>
          <option value="">Unassigned</option>{rooms.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></Field>
        <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={form.has_occupancy_sensor} onChange={(e) => setForm({ ...form, has_occupancy_sensor: e.target.checked })} />Has occupancy sensor (reports room occupancy)</label>
        <div className="sm:col-span-2"><ErrorBanner error={error} /></div>
        <div className="flex justify-end gap-2 sm:col-span-2"><Button type="button" onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} type="submit">Register</Button></div>
      </form>
    </Modal>
  );
}
