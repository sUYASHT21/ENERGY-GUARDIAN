import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { patch, post } from "../api/client";
import type { Room } from "../api/types";
import { Button, Card, ErrorBanner, Field, Modal, SourceBadge, Spinner, StatusPill, inputCls, occupancyTone, useToast } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useApi } from "../hooks/useApi";
import { humanize, timeAgo } from "../lib/format";

export const ROOM_TYPES = ["classroom", "laboratory", "hostel", "office", "other"];

export default function Rooms() {
  const { can } = useAuth();
  const rooms = useApi<Room[]>("/rooms", { refreshOn: ["room"] });
  const [creating, setCreating] = useState(false);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="display text-[34px] text-ink sm:text-[44px]">Rooms <em>&amp; appliances</em></h1>
        {can("operator") && <Button variant="primary" onClick={() => setCreating(true)}><Plus className="size-4" />Add room</Button>}
      </div>
      <ErrorBanner error={rooms.error} onRetry={rooms.reload} />
      {!rooms.data ? <Spinner /> : (
        <Card bodyClass="p-0">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="text-left text-[13px] text-tag">
                <tr><th className="px-4 py-2">Room</th><th>Type</th><th>Building</th><th>Occupancy</th><th>Min. vacancy</th><th>Automation</th><th>Updated</th></tr>
              </thead>
              <tbody>
                {rooms.data.map((r) => (
                  <tr key={r.id} className="border-t border-line hover:bg-surface-2">
                    <td className="px-4 py-2.5"><Link className="font-medium text-ink underline-offset-4 hover:underline" to={`/rooms/${r.id}`}>{r.name}</Link></td>
                    <td>{humanize(r.room_type)}</td>
                    <td className="text-ink-2">{r.building || "—"}{r.floor ? ` · floor ${r.floor}` : ""}</td>
                    <td><span className="inline-flex items-center gap-1.5"><StatusPill tone={occupancyTone(r.occupancy_state)} label={humanize(r.occupancy_state)} />{r.occupancy_source && <SourceBadge source={r.occupancy_source} compact />}</span></td>
                    <td className="tabular">{r.min_vacancy_minutes} min</td>
                    <td>{r.manual_override ? <StatusPill tone="warning" label="Manual override" /> : r.auto_control_enabled ? <StatusPill tone="good" label="Enabled" /> : <StatusPill tone="neutral" label="Disabled" />}</td>
                    <td className="text-ink-2">{timeAgo(r.occupancy_updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {creating && <RoomForm onClose={() => setCreating(false)} onSaved={() => { setCreating(false); rooms.reload(); }} />}
    </div>
  );
}

export function RoomForm({ room, onClose, onSaved }: { room?: Room; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({
    name: room?.name ?? "", room_type: room?.room_type ?? "classroom", building: room?.building ?? "", floor: room?.floor ?? 0,
    capacity: room?.capacity ?? 30, min_vacancy_minutes: room?.min_vacancy_minutes ?? 10, auto_control_enabled: room?.auto_control_enabled ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (room) await patch(`/rooms/${room.id}`, form);
      else await post("/rooms", form);
      toast("good", room ? "Room updated" : "Room created");
      onSaved();
    } catch (err) {
      setError(err as Error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={room ? `Edit ${room.name}` : "Add room"} onClose={onClose}>
      <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2"><Field label="Name"><input required maxLength={100} className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field></div>
        <Field label="Type"><select className={inputCls} value={form.room_type} onChange={(e) => setForm({ ...form, room_type: e.target.value })}>{ROOM_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}</select></Field>
        <Field label="Building"><input className={inputCls} value={form.building} onChange={(e) => setForm({ ...form, building: e.target.value })} /></Field>
        <Field label="Floor"><input type="number" className={inputCls} value={form.floor} onChange={(e) => setForm({ ...form, floor: Number(e.target.value) })} /></Field>
        <Field label="Capacity"><input type="number" min={0} className={inputCls} value={form.capacity} onChange={(e) => setForm({ ...form, capacity: Number(e.target.value) })} /></Field>
        <Field label="Minimum vacancy before action (min)" hint="Protects against brief absences / PIR false negatives">
          <input type="number" min={0.5} max={240} step={0.5} className={inputCls} value={form.min_vacancy_minutes} onChange={(e) => setForm({ ...form, min_vacancy_minutes: Number(e.target.value) })} />
        </Field>
        <label className="flex items-center gap-2 self-end pb-2 text-sm"><input type="checkbox" checked={form.auto_control_enabled} onChange={(e) => setForm({ ...form, auto_control_enabled: e.target.checked })} />Automation enabled for this room</label>
        <div className="sm:col-span-2"><ErrorBanner error={error} /></div>
        <div className="flex justify-end gap-2 sm:col-span-2"><Button type="button" onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} type="submit">Save</Button></div>
      </form>
    </Modal>
  );
}
