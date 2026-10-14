import { Pause, Play, RotateCcw, StepForward } from "lucide-react";
import { post } from "../api/client";
import type { SimulationStatus } from "../api/types";
import { Button, Card, Empty, ErrorBanner, Spinner, StatusPill, cx, inputCls, useToast } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useApi } from "../hooks/useApi";
import { humanize } from "../lib/format";

export default function Simulation() {
  const { can } = useAuth();
  const toast = useToast();
  const sim = useApi<SimulationStatus>("/simulation", { refreshOn: ["simulation"], intervalMs: 5000 });

  const call = async (path: string, body?: unknown, msg?: string) => {
    try { await post(path, body); if (msg) toast("good", msg); sim.reload(); } catch (e) { toast("critical", (e as Error).message); }
  };

  if (sim.error) return <ErrorBanner error={sim.error} onRetry={sim.reload} />;
  if (!sim.data) return <Spinner />;
  const s = sim.data;
  if (!s.enabled) return <Empty>Simulation is disabled on this server (SIMULATION_ENABLED=false).</Empty>;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="display text-[34px] text-ink sm:text-[44px]">Simulation <em>lab</em></h1>
          <p className="mt-2 max-w-3xl text-[16px] text-muted">
            Hardware-free demo. Each simulated controller behaves like an ESP32: it posts telemetry through the same ingestion pipeline and
            fetches/acknowledges commands through the same functions as the HTTP device API. All its data is labelled <b>Simulated</b>.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill tone={s.running ? "good" : "neutral"} label={s.running ? `Running · tick ${s.tick}` : "Stopped"} />
          {can("operator") && (s.running
            ? <Button onClick={() => call("/simulation/stop", undefined, "Simulation stopped")}><Pause className="size-4" />Stop</Button>
            : <Button variant="primary" onClick={() => call("/simulation/start", undefined, "Simulation started")}><Play className="size-4" />Start</Button>)}
          {can("operator") && !s.running && <Button onClick={() => call("/simulation/tick?steps=1")}><StepForward className="size-4" />Single tick</Button>}
          {can("operator") && <Button variant="ghost" onClick={() => call("/simulation/reset", undefined, "Scenarios reset")}><RotateCcw className="size-4" />Reset scenarios</Button>}
        </div>
      </div>

      <Card title="Scenario per room" subtitle={`Tick interval ${s.tick_seconds}s. Demo rooms use a 1-minute minimum vacancy so wastage is detected quickly.`}>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {s.rooms?.map((r) => (
            <div key={r.room_id} className="rounded-2xl border border-line p-3">
              <div className="font-medium">{r.room}</div>
              <select disabled={!can("operator")} className={cx(inputCls, "mt-2")} value={r.scenario} aria-label={`Scenario for ${r.room}`}
                onChange={(e) => call("/simulation/scenario", { room_id: r.room_id, scenario: e.target.value }, `${r.room}: ${humanize(e.target.value)}`)}>
                {Object.keys(s.scenarios ?? {}).map((k) => <option key={k} value={k}>{humanize(k)}</option>)}
              </select>
              <p className="mt-2 text-xs text-ink-2">{s.scenarios?.[r.scenario]}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Suggested demonstration">
        <ol className="list-decimal space-y-1.5 pl-5 text-sm text-ink-2">
          <li><b>Vacant-room wastage:</b> CR-102 starts in <i>vacant waste</i>. After ~1 min the dashboard shows waste alerts and dry-run commands (default mode records but sends nothing).</li>
          <li><b>Simulated shutdown:</b> in Settings switch automation to <i>auto</i>. Simulated OFF commands are sent, acknowledged by the virtual controller, appliances turn off, estimated savings start.</li>
          <li><b>Anomaly:</b> LAB-202 runs the <i>anomaly</i> scenario — the ML page shows flagged readings and an anomaly alert, but no shutdown (occupied room).</li>
          <li><b>Sensor failure:</b> set a room to <i>sensor failure</i> → occupancy becomes unknown, a critical alert appears and automation is blocked.</li>
          <li><b>Offline device:</b> <i>offline</i> → after 30 s the controller is offline, appliance states become unknown, automation suspended.</li>
          <li><b>Failed / timed-out commands:</b> <i>command failure</i> or <i>command timeout</i> in a room without an active schedule, with automation on <i>auto</i>.</li>
        </ol>
      </Card>
    </div>
  );
}
