import { useState } from "react";
import { Brain, ShieldAlert } from "lucide-react";
import { post } from "../api/client";
import type { Appliance, MLStatus, ModelRecord, ScorePoint } from "../api/types";
import { ScoreChart } from "../components/charts";
import { Button, Card, Empty, ErrorBanner, Field, SourceBadge, Spinner, StatusPill, cx, inputCls, useToast } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useApi } from "../hooks/useApi";
import { formatDateTime, formatPower, formatTime, humanize } from "../lib/format";

export default function ML() {
  const { can } = useAuth();
  const toast = useToast();
  const status = useApi<MLStatus>("/ml/status", { refreshOn: ["summary"], throttleMs: 15000 });
  const apps = useApi<Appliance[]>("/appliances");
  const [applianceId, setApplianceId] = useState<string>("");
  const flagged = useApi<ScorePoint[]>("/ml/scores?only_anomalies=true&minutes=60&limit=50", { refreshOn: ["summary"], throttleMs: 5000 });
  // Default to the most recently flagged appliance so the chart is useful on first load.
  const selectedId = applianceId || (flagged.data?.length ? String(flagged.data[flagged.data.length - 1].appliance_id) : "");
  const scores = useApi<ScorePoint[]>(selectedId ? `/ml/scores?appliance_id=${selectedId}&minutes=30` : null, { refreshOn: ["summary"], throttleMs: 5000 });
  const [params, setParams] = useState({ seed: 42, n_estimators: 200, contamination: 0.04 });
  const [busy, setBusy] = useState(false);

  const train = async () => {
    setBusy(true);
    try {
      const m = await post<ModelRecord>("/ml/train", params);
      toast("good", `Trained ${m.version}: F1 ${m.metrics.f1.toFixed(3)} on synthetic test data`);
      status.reload();
    } catch (e) { toast("critical", (e as Error).message); } finally { setBusy(false); }
  };
  const activate = async (id: number) => {
    try { await post(`/ml/models/${id}/activate`); status.reload(); } catch (e) { toast("critical", (e as Error).message); }
  };

  if (status.error) return <ErrorBanner error={status.error} onRetry={status.reload} />;
  if (!status.data) return <Spinner />;
  const s = status.data;
  const m = s.active_model?.metrics;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="display text-[34px] text-ink sm:text-[44px]">Anomaly <em>detection</em></h1>
        <p className="mt-2 text-[16px] text-muted">scikit-learn Isolation Forest on electrical features (power ratio, step change, voltage deviation, power factor, relay/power mismatch), with a transparent rule-based fallback.</p>
      </div>
      <div className="flex flex-col gap-2 rounded-3xl tint-butter p-4 text-sm">
        <p className="flex items-start gap-2"><ShieldAlert className="mt-0.5 size-4 shrink-0 text-warning-ink" aria-hidden /><span><b>Synthetic evaluation.</b> {s.disclaimer}</span></p>
        <p className="pl-6 text-ink-2">{s.safety_note}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card title="Model status" actions={<StatusPill tone={s.method === "isolation_forest" ? "good" : "warning"} label={s.method === "isolation_forest" ? "Isolation Forest active" : "Rule-based fallback"} icon={<Brain className="size-3.5" />} />}>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
            <dt className="text-muted">Version</dt><dd className="font-mono text-xs">{s.model_version ?? "—"}</dd>
            <dt className="text-muted">Trained</dt><dd>{formatDateTime(s.active_model?.trained_at)}</dd>
            <dt className="text-muted">Train / test rows</dt><dd className="tabular">{s.active_model ? `${s.active_model.n_train} / ${s.active_model.n_test}` : "—"}</dd>
            <dt className="text-muted">Training data</dt><dd className="text-xs">{s.active_model?.data_source ?? "—"}</dd>
            <dt className="text-muted">Scored (last hour)</dt><dd className="tabular">{s.last_hour.readings_scored}</dd>
            <dt className="text-muted">Flagged (last hour)</dt><dd className="tabular">{s.last_hour.flagged}</dd>
          </dl>
          {s.last_error && <p className="mt-2 text-xs text-critical-ink">Load error: {s.last_error}</p>}
        </Card>

        <Card title="Evaluation metrics" subtitle={m ? `Held-out synthetic test set: ${m.n_test} readings, ${m.n_test_anomalies} labelled anomalies` : undefined}>
          {!m ? <Empty>No trained model — rules are in use</Empty> : (
            <>
              <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4 xl:grid-cols-2">
                {([["Precision", m.precision, "sky"], ["Recall", m.recall, "sage"], ["F1", m.f1, "lilac"], ["ROC-AUC", m.roc_auc, "butter"]] as const).map(([k, v, t]) => (
                  <div key={k} className={`rounded-2xl p-3 tint-${t}`}><div className="text-xs opacity-80">{k}</div><div className="display text-[24px] leading-tight tabular">{v.toFixed(3)}</div></div>
                ))}
              </div>
              <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-muted">Confusion matrix</h3>
              <table className="mt-1 w-full text-center text-sm tabular" aria-label="Confusion matrix">
                <thead><tr className="text-xs text-muted"><th></th><th>Predicted normal</th><th>Predicted anomaly</th></tr></thead>
                <tbody>
                  <tr><th className="text-left text-xs text-muted">Actual normal</th><td>{m.confusion_matrix.tn}</td><td>{m.confusion_matrix.fp}</td></tr>
                  <tr><th className="text-left text-xs text-muted">Actual anomaly</th><td>{m.confusion_matrix.fn}</td><td>{m.confusion_matrix.tp}</td></tr>
                </tbody>
              </table>
              <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-muted">Recall by anomaly type</h3>
              <ul className="mt-1 flex flex-col gap-1 text-sm">
                {Object.entries(m.recall_by_anomaly_kind).map(([k, v]) => (
                  <li key={k} className="flex items-center gap-2">
                    <span className="w-36 text-ink-2">{humanize(k)}</span>
                    <span className="h-2 flex-1 rounded-full bg-[var(--t-sky)]"><span className="block h-2 rounded-full bg-[var(--series-1)]" style={{ width: `${v * 100}%` }} /></span>
                    <span className="w-12 text-right tabular">{(v * 100).toFixed(0)}%</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>

        <Card title="Train a new model" subtitle="Generates fresh synthetic data, trains, evaluates and activates">
          {can("admin") ? (
            <div className="flex flex-col gap-3">
              <Field label="Random seed" hint="Same seed ⇒ identical data, model and metrics"><input type="number" min={0} className={inputCls} value={params.seed} onChange={(e) => setParams({ ...params, seed: Number(e.target.value) })} /></Field>
              <Field label="Trees (n_estimators)"><input type="number" min={10} max={1000} className={inputCls} value={params.n_estimators} onChange={(e) => setParams({ ...params, n_estimators: Number(e.target.value) })} /></Field>
              <Field label="Contamination" hint="Expected anomaly share; sets the decision threshold"><input type="number" step={0.005} min={0.001} max={0.5} className={inputCls} value={params.contamination} onChange={(e) => setParams({ ...params, contamination: Number(e.target.value) })} /></Field>
              <Button variant="primary" busy={busy} onClick={train}>Train & activate</Button>
            </div>
          ) : <Empty>Admins only</Empty>}
        </Card>
      </div>

      <Card title="Anomaly scores" subtitle="Score > 0 is flagged by the model (red markers). An alert needs consecutive flagged readings."
        actions={<select className={cx(inputCls, "w-auto")} value={selectedId} onChange={(e) => setApplianceId(e.target.value)} aria-label="Appliance">
          <option value="">Choose appliance…</option>{apps.data?.map((a) => <option key={a.id} value={a.id}>{a.name} (#{a.id})</option>)}</select>}>
        {!selectedId ? <Empty>Select an appliance to plot its recent scores</Empty> : !scores.data ? <Spinner /> : scores.data.length < 2 ? <Empty>Not enough recent readings</Empty> : <ScoreChart points={scores.data} />}
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Recently flagged readings (last hour)">
          {!flagged.data ? <Spinner /> : flagged.data.length === 0 ? <Empty>No flagged readings</Empty> : (
            <div className="max-h-72 overflow-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-surface text-left text-xs text-muted"><tr><th>Time</th><th>Appliance</th><th>Power</th><th>Score</th><th>Source</th></tr></thead>
                <tbody>{flagged.data.slice().reverse().map((p, i) => (
                  <tr key={i} className="border-t border-line"><td className="tabular py-1">{formatTime(p.ts)}</td><td>{p.appliance}</td><td className="tabular">{formatPower(p.power_w)}</td><td className="tabular">{p.score.toFixed(3)}</td><td><SourceBadge source={p.source} compact /></td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="Model registry">
          <ul className="flex flex-col divide-y divide-[var(--border)] text-sm">
            {s.models.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span><span className="font-mono text-xs">{r.version}</span> <span className="text-ink-2">· F1 {r.metrics.f1.toFixed(3)} · AUC {r.metrics.roc_auc.toFixed(3)} · {formatDateTime(r.trained_at)}</span></span>
                {r.active ? <StatusPill tone="good" label="Active" /> : can("admin") && <Button className="px-2 py-1 text-xs" onClick={() => activate(r.id)}>Activate</Button>}
              </li>
            ))}
            {s.models.length === 0 && <li className="py-2 text-muted">No models trained yet</li>}
          </ul>
        </Card>
      </div>
    </div>
  );
}
