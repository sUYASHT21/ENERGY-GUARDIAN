import { useEffect, useState } from "react";
import { Lock, Plus, Trash2 } from "lucide-react";
import { put } from "../api/client";
import type { RuntimeSettings, SettingsResponse } from "../api/types";
import { Button, Card, ErrorBanner, Field, Spinner, StatusPill, inputCls, useToast } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useApi } from "../hooks/useApi";

const MODES: { value: RuntimeSettings["automation_mode"]; label: string; help: string }[] = [
  { value: "recommend", label: "Recommend only", help: "Raise alerts with recommendations; never issue commands." },
  { value: "dry_run", label: "Dry-run (default)", help: "Record the shutdown the engine would perform; nothing is sent." },
  { value: "auto", label: "Automatic", help: "Send commands to simulated/emulated devices. Hardware additionally needs REAL_SWITCHING_ENABLED and per-device validation." },
];

export default function Settings() {
  const { can } = useAuth();
  const toast = useToast();
  const res = useApi<SettingsResponse>("/settings", { refreshOn: ["settings"] });
  const [form, setForm] = useState<RuntimeSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => { if (res.data) setForm(res.data.runtime); }, [res.data]);

  if (res.error) return <ErrorBanner error={res.error} onRetry={res.reload} />;
  if (!res.data || !form) return <Spinner />;
  const env = res.data.environment;
  const admin = can("admin");
  const num = (k: keyof RuntimeSettings) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: Number(e.target.value) });

  const save = async () => {
    setBusy(true);
    setError(null);
    const changed = Object.fromEntries(Object.entries(form).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(res.data!.runtime[k as keyof RuntimeSettings])));
    try {
      if (Object.keys(changed).length === 0) return toast("info", "Nothing changed");
      if (changed.automation_mode === "auto" && !confirm("Switch automation to AUTOMATIC? Simulated/emulated devices will receive real commands from the engine.")) return;
      await put("/settings", changed);
      toast("good", "Settings saved");
      res.reload();
    } catch (e) { setError(e as Error); } finally { setBusy(false); }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Settings</h1>
        {admin ? <Button variant="primary" busy={busy} onClick={save}>Save changes</Button> : <StatusPill tone="neutral" label="Read-only (admin required)" icon={<Lock className="size-3.5" />} />}
      </div>
      <ErrorBanner error={error} />
      {env.using_insecure_defaults && <ErrorBanner error={new Error("Server is using default SECRET_KEY / ADMIN_PASSWORD. Set them in .env before any real deployment.")} />}

      <fieldset disabled={!admin} className="contents">
        <Card title="Automation mode">
          <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
            {MODES.map((m) => (
              <label key={m.value} className={`cursor-pointer rounded-lg border p-3 text-sm ${form.automation_mode === m.value ? "border-accent bg-accent-wash" : "border-line"}`}>
                <span className="flex items-center gap-2 font-medium"><input type="radio" name="mode" checked={form.automation_mode === m.value} onChange={() => setForm({ ...form, automation_mode: m.value })} />{m.label}</span>
                <span className="mt-1 block text-xs text-ink-2">{m.help}</span>
              </label>
            ))}
          </div>
        </Card>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Card title="Tariff & carbon" subtitle="Used for cost and CO₂ figures (all savings are labelled as estimates)">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Currency (ISO code)"><input className={inputCls} maxLength={8} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></Field>
              <Field label="Flat rate per kWh"><input type="number" step={0.01} min={0} className={inputCls} value={form.tariff_flat_rate} onChange={num("tariff_flat_rate")} /></Field>
              <Field label="Grid emission factor (kg CO₂/kWh)" hint="Default ≈ Indian grid average; use your region's published factor"><input type="number" step={0.01} min={0} className={inputCls} value={form.carbon_factor_kg_per_kwh} onChange={num("carbon_factor_kg_per_kwh")} /></Field>
              <Field label="Timezone (IANA)"><input className={inputCls} value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} /></Field>
            </div>
            <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={form.tariff_tou_enabled} onChange={(e) => setForm({ ...form, tariff_tou_enabled: e.target.checked })} />Time-of-use tariff</label>
            {form.tariff_tou_enabled && (
              <div className="mt-2 flex flex-col gap-2">
                {form.tariff_tou_periods.map((p, i) => (
                  <div key={i} className="grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-2">
                    <input aria-label="Period name" className={inputCls} value={p.name} onChange={(e) => setForm({ ...form, tariff_tou_periods: form.tariff_tou_periods.map((x, j) => j === i ? { ...x, name: e.target.value } : x) })} />
                    <input aria-label="Start" type="time" className={inputCls} value={p.start} onChange={(e) => setForm({ ...form, tariff_tou_periods: form.tariff_tou_periods.map((x, j) => j === i ? { ...x, start: e.target.value } : x) })} />
                    <input aria-label="End" type="time" className={inputCls} value={p.end} onChange={(e) => setForm({ ...form, tariff_tou_periods: form.tariff_tou_periods.map((x, j) => j === i ? { ...x, end: e.target.value } : x) })} />
                    <input aria-label="Rate" type="number" step={0.01} className={`${inputCls} w-24`} value={p.rate} onChange={(e) => setForm({ ...form, tariff_tou_periods: form.tariff_tou_periods.map((x, j) => j === i ? { ...x, rate: Number(e.target.value) } : x) })} />
                    <Button variant="ghost" onClick={() => setForm({ ...form, tariff_tou_periods: form.tariff_tou_periods.filter((_, j) => j !== i) })} aria-label="Remove period"><Trash2 className="size-4" /></Button>
                  </div>
                ))}
                <Button className="self-start" onClick={() => setForm({ ...form, tariff_tou_periods: [...form.tariff_tou_periods, { name: "Peak", start: "18:00", end: "22:00", rate: form.tariff_flat_rate }] })}><Plus className="size-4" />Add period</Button>
              </div>
            )}
          </Card>

          <Card title="Decision engine thresholds">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Default min. vacancy for new rooms (min)"><input type="number" step={0.5} min={0.5} className={inputCls} value={form.default_min_vacancy_minutes} onChange={num("default_min_vacancy_minutes")} /></Field>
              <Field label="Schedule grace period (min)" hint="Block auto-off this long before a session"><input type="number" min={0} className={inputCls} value={form.schedule_grace_minutes} onChange={num("schedule_grace_minutes")} /></Field>
              <Field label="Respect manual switch-on for (min)"><input type="number" min={0} className={inputCls} value={form.manual_on_cooldown_minutes} onChange={num("manual_on_cooldown_minutes")} /></Field>
              <Field label="Automatic command cooldown (min)"><input type="number" min={0} className={inputCls} value={form.auto_command_cooldown_minutes} onChange={num("auto_command_cooldown_minutes")} /></Field>
              <Field label="Anomaly persistence (readings)" hint="Consecutive flagged readings before an alert"><input type="number" min={1} max={20} className={inputCls} value={form.anomaly_persistence} onChange={num("anomaly_persistence")} /></Field>
              <Field label="Savings estimate cap (hours)"><input type="number" min={0.5} max={24} step={0.5} className={inputCls} value={form.savings_cap_hours} onChange={num("savings_cap_hours")} /></Field>
            </div>
          </Card>
        </div>
      </fieldset>

      <Card title="Environment (read-only)" subtitle="Changed only through environment variables and a restart — never through the UI">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
          <Row k="Environment" v={env.app_env} />
          <Row k="Real hardware switching" v={env.real_switching_enabled ? <StatusPill tone="critical" label="ENABLED" /> : <StatusPill tone="good" label="Disabled" />} />
          <Row k="Simulation" v={env.simulation_enabled ? "enabled" : "disabled"} />
          <Row k="Command timeout" v={`${env.command_timeout_seconds} s`} />
          <Row k="Device offline after" v={`${env.device_offline_seconds} s`} />
          <Row k="Telemetry stale after" v={`${env.telemetry_stale_seconds} s`} />
          <Row k="Max integration gap" v={`${env.max_integration_gap_seconds} s`} />
        </dl>
      </Card>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="flex items-center justify-between gap-2 border-b border-line py-1"><dt className="text-ink-2">{k}</dt><dd className="font-medium">{v}</dd></div>;
}
