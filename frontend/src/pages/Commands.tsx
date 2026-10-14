import { useState } from "react";
import type { Appliance, Command } from "../api/types";
import { Card, Empty, ErrorBanner, Spinner, StatusPill, commandTone, cx, inputCls } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { formatTime } from "../lib/format";

const STATUSES = ["", "pending", "sent", "acknowledged", "failed", "timeout", "dry_run", "blocked"];

export default function Commands() {
  const [status, setStatus] = useState("");
  const cmds = useApi<Command[]>(`/commands?limit=200${status ? `&status=${status}` : ""}`, { refreshOn: ["command"] });
  const apps = useApi<Appliance[]>("/appliances");
  const name = (id: number) => apps.data?.find((a) => a.id === id)?.name ?? `#${id}`;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Command log</h1>
          <p className="text-sm text-ink-2">Every command — manual or automatic — with its safety-gate result, delivery and acknowledgement.</p>
        </div>
        <select className={cx(inputCls, "w-auto")} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
          {STATUSES.map((s) => <option key={s} value={s}>{s || "All statuses"}</option>)}
        </select>
      </div>
      <ErrorBanner error={cmds.error} onRetry={cmds.reload} />
      {!cmds.data ? <Spinner /> : cmds.data.length === 0 ? <Empty>No commands yet</Empty> : (
        <Card bodyClass="p-0">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <thead className="bg-surface-2 text-left text-xs text-ink-2">
                <tr><th className="px-3 py-2">#</th><th>Appliance</th><th>Action</th><th>Status</th><th>Mode</th><th>Origin</th><th>Created</th><th>Sent</th><th>Completed</th><th>Reason / error</th></tr>
              </thead>
              <tbody>
                {cmds.data.map((c) => (
                  <tr key={c.id} className="border-t border-line align-top">
                    <td className="tabular px-3 py-2 text-muted">{c.id}</td>
                    <td className="font-medium">{name(c.appliance_id)}</td>
                    <td className="font-semibold">{c.action.toUpperCase()}</td>
                    <td><StatusPill tone={commandTone(c.status)} label={c.status.replace("_", "-")} /></td>
                    <td>{c.mode.replace("_", "-")}</td>
                    <td className="text-ink-2">{c.origin}{c.origin === "manual" && ` · ${c.requested_by}`}</td>
                    <td className="tabular text-ink-2">{formatTime(c.created_at)}</td>
                    <td className="tabular text-ink-2">{formatTime(c.sent_at)}</td>
                    <td className="tabular text-ink-2">{formatTime(c.completed_at)}</td>
                    <td className="max-w-[320px] text-xs">{c.error ? <span className="text-critical-ink">{c.error}</span> : <span className="text-ink-2">{c.reason}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
