import { createContext, useCallback, useContext, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, CircleHelp, CircleSlash, Cpu, FlaskConical, Info, Loader2, OctagonAlert, Radio, X } from "lucide-react";
import type { Source } from "../api/types";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function Card({ title, subtitle, actions, children, className, bodyClass }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <section className={cx("rounded-xl border border-line bg-surface", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-2 border-b border-line px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx("p-4", bodyClass)}>{children}</div>
    </section>
  );
}

type Variant = "primary" | "secondary" | "danger" | "ghost";
export function Button({ variant = "secondary", busy, className, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant; busy?: boolean;
}) {
  const styles: Record<Variant, string> = {
    primary: "bg-accent text-white hover:opacity-90 border-transparent",
    secondary: "bg-surface text-ink border-line hover:bg-surface-2",
    danger: "bg-critical text-white border-transparent hover:opacity-90",
    ghost: "bg-transparent text-ink-2 border-transparent hover:bg-surface-2",
  };
  return (
    <button
      {...rest}
      disabled={rest.disabled || busy}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        styles[variant], className,
      )}
    >
      {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

/* Status always ships icon + label (never colour alone). */
export type Tone = "good" | "warning" | "serious" | "critical" | "neutral" | "info";
const TONE: Record<Tone, { cls: string; Icon: typeof Info }> = {
  good: { cls: "text-good-ink bg-good/10", Icon: CheckCircle2 },
  warning: { cls: "text-warning-ink bg-warning/15", Icon: AlertTriangle },
  serious: { cls: "text-ink bg-serious/20", Icon: AlertTriangle },
  critical: { cls: "text-critical-ink bg-critical/10", Icon: OctagonAlert },
  neutral: { cls: "text-ink-2 bg-surface-2", Icon: CircleHelp },
  info: { cls: "text-accent-ink bg-accent-wash", Icon: Info },
};

export function StatusPill({ tone, label, icon }: { tone: Tone; label: string; icon?: ReactNode }) {
  const { cls, Icon } = TONE[tone];
  return (
    <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium", cls)}>
      {icon ?? <Icon className="size-3.5" aria-hidden />}
      {label}
    </span>
  );
}

export function SourceBadge({ source, compact = false }: { source: Source | string | null | undefined; compact?: boolean }) {
  if (!source) return null;
  if (source === "simulation")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-sim-wash px-2 py-0.5 text-xs font-semibold text-sim" title="Synthetic data from the built-in simulator">
        <FlaskConical className="size-3.5" aria-hidden />{compact ? "SIM" : "Simulated"}
      </span>
    );
  if (source === "emulator")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-xs font-semibold text-ink-2" title="ESP32 protocol emulator — not a physical device">
        <Cpu className="size-3.5" aria-hidden />{compact ? "EMU" : "Emulated ESP32"}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-good/10 px-2 py-0.5 text-xs font-semibold text-good-ink" title="Reading reported by physical hardware">
      <Radio className="size-3.5" aria-hidden />{compact ? "HW" : "Hardware"}
    </span>
  );
}

export function occupancyTone(state: string): Tone {
  return state === "occupied" ? "info" : state === "vacant" ? "neutral" : "warning";
}

export function connectionTone(status: string): Tone {
  return status === "online" ? "good" : status === "offline" ? "critical" : "neutral";
}

export function severityTone(sev: string): Tone {
  return sev === "critical" ? "critical" : sev === "warning" ? "warning" : "info";
}

export function commandTone(status: string): Tone {
  switch (status) {
    case "acknowledged": return "good";
    case "failed": case "timeout": return "critical";
    case "blocked": return "serious";
    case "pending": case "sent": return "info";
    default: return "neutral";
  }
}

export function StatTile({ label, value, sub, footnote, icon, tone }: {
  label: string; value: ReactNode; sub?: ReactNode; footnote?: ReactNode; icon?: ReactNode; tone?: "estimate";
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-xl border border-line bg-surface p-4">
      <div className="flex items-start justify-between gap-2 text-xs font-medium leading-tight text-ink-2">
        <span>{label}</span>
        {icon && <span className="text-muted">{icon}</span>}
      </div>
      <div className="truncate text-2xl font-semibold tracking-tight text-ink">{value}</div>
      {sub && <div className="text-xs text-ink-2">{sub}</div>}
      {tone === "estimate" && <div className="text-[11px] font-medium uppercase tracking-wide text-muted">Estimate</div>}
      {footnote && <div className="text-[11px] text-muted">{footnote}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-4 text-sm text-muted" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label}…
    </div>
  );
}

export function ErrorBanner({ error, onRetry }: { error: Error | null; onRetry?: () => void }) {
  if (!error) return null;
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-critical/30 bg-critical/10 px-3 py-2 text-sm text-critical-ink">
      <span className="flex items-center gap-2"><OctagonAlert className="size-4" aria-hidden />{error.message}</span>
      {onRetry && <Button variant="ghost" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-dashed border-line px-4 py-6 text-sm text-muted">
      <CircleSlash className="size-4" aria-hidden />{children}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-ink-2">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
}

export const inputCls = "min-w-0 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent-wash";

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center" role="dialog" aria-modal="true" aria-label={title}>
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-line bg-surface shadow-xl">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-surface-2" aria-label="Close"><X className="size-4" /></button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

/* ---------- toasts ---------- */
interface Toast { id: number; tone: Tone; text: string }
const ToastCtx = createContext<(tone: Tone, text: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((tone: Tone, text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, tone, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(92vw,380px)] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto rounded-lg border border-line bg-surface px-3 py-2 text-sm shadow-lg">
            <StatusPill tone={t.tone} label={t.tone === "good" ? "Done" : t.tone === "critical" ? "Error" : "Notice"} />
            <p className="mt-1 text-ink">{t.text}</p>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}
