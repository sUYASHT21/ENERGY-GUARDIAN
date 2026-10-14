import { useState, type FormEvent } from "react";
import { Trash2 } from "lucide-react";
import { del, patch, post } from "../api/client";
import type { Room, Schedule } from "../api/types";
import { Button, Card, Empty, ErrorBanner, Field, Spinner, inputCls, useToast } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useApi } from "../hooks/useApi";
import { DAYS } from "../lib/format";

export default function Schedules() {
  const { can } = useAuth();
  const toast = useToast();
  const rooms = useApi<Room[]>("/rooms");
  const schedules = useApi<Schedule[]>("/schedules");
  const [form, setForm] = useState({ room_id: 0, days: [0, 1, 2, 3, 4] as number[], start_time: "09:00", end_time: "11:00", label: "" });
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const roomId = form.room_id || rooms.data?.[0]?.id || 0;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      for (const d of form.days) {
        await post("/schedules", { room_id: roomId, day_of_week: d, start_time: form.start_time, end_time: form.end_time, label: form.label });
      }
      toast("good", `${form.days.length} schedule entr${form.days.length === 1 ? "y" : "ies"} added`);
      schedules.reload();
    } catch (err) { setError(err as Error); } finally { setBusy(false); }
  };
  const toggle = async (s: Schedule) => { try { await patch(`/schedules/${s.id}`, { enabled: !s.enabled }); schedules.reload(); } catch (e) { toast("critical", (e as Error).message); } };
  const remove = async (s: Schedule) => { try { await del(`/schedules/${s.id}`); schedules.reload(); } catch (e) { toast("critical", (e as Error).message); } };

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold">Schedules</h1>
        <p className="text-sm text-ink-2">During a scheduled session (and the grace period before it) automatic shutdown is blocked; only recommendations are raised. Times are in the configured local timezone.</p>
      </div>
      {can("operator") && (
        <Card title="Add session">
          <form onSubmit={submit} className="grid grid-cols-1 items-end gap-3 md:grid-cols-6">
            <Field label="Room"><select className={inputCls} value={roomId} onChange={(e) => setForm({ ...form, room_id: Number(e.target.value) })}>
              {rooms.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></Field>
            <div className="md:col-span-2">
              <span className="text-sm font-medium text-ink-2">Days</span>
              <div className="mt-1 flex flex-wrap gap-1">
                {DAYS.map((d, i) => (
                  <label key={d} className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-line px-2 py-1 text-xs">
                    <input type="checkbox" checked={form.days.includes(i)} onChange={(e) => setForm({ ...form, days: e.target.checked ? [...form.days, i] : form.days.filter((x) => x !== i) })} />{d}
                  </label>
                ))}
              </div>
            </div>
            <Field label="Start"><input type="time" required className={inputCls} value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} /></Field>
            <Field label="End"><input type="time" required className={inputCls} value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} /></Field>
            <Field label="Label"><input className={inputCls} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="Lecture" /></Field>
            <div className="md:col-span-6 flex items-center justify-between gap-2"><ErrorBanner error={error} /><Button variant="primary" busy={busy} disabled={!form.days.length || !roomId} type="submit">Add</Button></div>
          </form>
        </Card>
      )}
      <ErrorBanner error={schedules.error} onRetry={schedules.reload} />
      {!schedules.data || !rooms.data ? <Spinner /> : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {rooms.data.map((r) => {
            const list = schedules.data!.filter((s) => s.room_id === r.id);
            return (
              <Card key={r.id} title={r.name}>
                {list.length === 0 ? <Empty>No scheduled sessions</Empty> : (
                  <ul className="flex flex-col divide-y divide-[var(--border)] text-sm">
                    {list.map((s) => (
                      <li key={s.id} className="flex items-center justify-between gap-2 py-1.5">
                        <span className={s.enabled ? "" : "text-muted line-through"}><b className="inline-block w-10">{DAYS[s.day_of_week]}</b>{s.start_time}–{s.end_time} {s.label && <span className="text-ink-2">· {s.label}</span>}</span>
                        {can("operator") && (
                          <span className="flex gap-1">
                            <Button variant="ghost" className="px-2 py-0.5 text-xs" onClick={() => toggle(s)}>{s.enabled ? "Disable" : "Enable"}</Button>
                            <Button variant="ghost" className="px-2 py-0.5 text-xs" onClick={() => remove(s)} aria-label="Delete schedule"><Trash2 className="size-3.5" /></Button>
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
