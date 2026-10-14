import { createContext, useCallback, useContext, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, CircleHelp, CircleSlash, Cpu, FlaskConical, Info, Loader2, OctagonAlert, Radio, X } from "lucide-react";
import type { Source } from "../api/types";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export type CardVariant = "float" | "mist" | "peach" | "plain";

/* "float" = white product artifact with a whisper shadow (charts, data); "mist" = flat neutral
   card; "peach" = the editorial accent (use sparingly); "plain" = hairline only. */
export function Card({ title, subtitle, actions, children, className, bodyClass, variant = "float", eyebrow }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string;
  variant?: CardVariant; eyebrow?: ReactNode;
}) {
  const skin: Record<CardVariant, string> = {
    float: "bg-surface shadow-float rounded-[20px]",
    mist: "bg-surface-2 rounded-3xl",
    peach: "bg-peach text-sienna rounded-3xl",
    plain: "bg-surface border border-line rounded-3xl",
  };
  return (
    <section className={cx("min-w-0", skin[variant], className)}>
      {(title || actions || eyebrow) && (
        <header className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5">
          <div className="min-w-0">
            {eyebrow && <div className={cx("mb-1 text-[13px]", variant === "peach" ? "text-sienna/80" : "text-tag")}>{eyebrow}</div>}
            {title && <h2 className={cx("text-[17px] font-[480] tracking-[-0.01em]", variant === "peach" ? "text-sienna" : "text-ink")}>{title}</h2>}
            {subtitle && <p className={cx("mt-0.5 text-[13px]", variant === "peach" ? "text-sienna/80" : "text-muted")}>{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx("p-5", bodyClass)}>{children}</div>
    </section>
  );
}

/* Editorial page header: ghost category tag, serif headline (weight 400) with an optional
   italic phrase, slate subhead, actions on the right. */
export function PageHeader({ eyebrow, title, italic, subtitle, actions }: {
  eyebrow?: ReactNode; title: ReactNode; italic?: ReactNode; subtitle?: ReactNode; actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 pb-2">
      <div className="min-w-0 max-w-3xl">
        {eyebrow && <div className="mb-2 text-[14px] text-tag">{eyebrow}</div>}
        <h1 className="display text-[34px] text-ink sm:text-[44px]">
          {title}{italic && <> <em>{italic}</em></>}
        </h1>
        {subtitle && <p className="mt-2 text-[16px] leading-relaxed text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/* Link styles for anchors that should look like the pill pair / the arrow text link. */
export const pillPrimary = "inline-flex items-center gap-1.5 rounded-full border border-ink bg-ink px-5 py-2 text-[15px] font-[450] text-surface transition hover:opacity-85";
export const pillGhost = "inline-flex items-center gap-1.5 rounded-full border border-ink/80 px-5 py-2 text-[15px] font-[450] text-ink transition hover:bg-surface-2";
export const textLink = "text-[14px] text-ink hover:underline underline-offset-4";

type Variant = "primary" | "secondary" | "danger" | "ghost";
/* Pill buttons: filled ink primary, ghost (ink hairline) secondary — the DESIGN.md pair. */
export function Button({ variant = "secondary", busy, className, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant; busy?: boolean;
}) {
  const styles: Record<Variant, string> = {
    primary: "bg-ink text-surface border-ink hover:opacity-85",
    secondary: "bg-transparent text-ink border-ink/80 hover:bg-surface-2",
    danger: "bg-critical text-white border-critical hover:opacity-90",
    ghost: "bg-transparent text-ink-2 border-transparent hover:bg-surface-2",
  };
  return (
    <button
      {...rest}
      disabled={rest.disabled || busy}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-full border px-4 py-1.5 text-[14px] font-[450] transition disabled:cursor-not-allowed disabled:opacity-45",
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
  good: { cls: "tint-sage", Icon: CheckCircle2 },
  warning: { cls: "tint-butter", Icon: AlertTriangle },
  serious: { cls: "tint-peach", Icon: AlertTriangle },
  critical: { cls: "tint-rose", Icon: OctagonAlert },
  neutral: { cls: "bg-surface-2 text-ink-2", Icon: CircleHelp },
  info: { cls: "tint-sky", Icon: Info },
};

export function StatusPill({ tone, label, icon }: { tone: Tone; label: string; icon?: ReactNode }) {
  const { cls, Icon } = TONE[tone];
  return (
    <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-[500]", cls)}>
      {icon ?? <Icon className="size-3.5" aria-hidden />}
      {label}
    </span>
  );
}

export function SourceBadge({ source, compact = false }: { source: Source | string | null | undefined; compact?: boolean }) {
  if (!source) return null;
  if (source === "simulation")
    return (
      <span className="inline-flex items-center gap-1 rounded-full tint-lilac px-2.5 py-0.5 text-xs font-[500]" title="Synthetic data from the built-in simulator">
        <FlaskConical className="size-3.5" aria-hidden />{compact ? "SIM" : "Simulated"}
      </span>
    );
  if (source === "emulator")
    return (
      <span className="inline-flex items-center gap-1 rounded-full tint-butter px-2.5 py-0.5 text-xs font-[500]" title="ESP32 protocol emulator — not a physical device">
        <Cpu className="size-3.5" aria-hidden />{compact ? "EMU" : "Emulated ESP32"}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full tint-sage px-2.5 py-0.5 text-xs font-[500]" title="Reading reported by physical hardware">
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

export type Tint = "peach" | "sky" | "sage" | "butter" | "rose" | "lilac";

/* Colour-tinted metric tile: tint surface + same-hue ink (text never wears a series colour). */
export function StatTile({ label, value, sub, footnote, icon, tone, tint = "sky" }: {
  label: string; value: ReactNode; sub?: ReactNode; footnote?: ReactNode; icon?: ReactNode; tone?: "estimate"; tint?: Tint;
}) {
  return (
    <div className={cx("flex min-w-0 flex-col gap-1.5 rounded-3xl p-5", `tint-${tint}`)}>
      <div className="flex items-start justify-between gap-2 text-[13px] font-[450] leading-tight opacity-85">
        <span>{label}</span>
        {icon && <span className="grid size-8 shrink-0 place-items-center rounded-full bg-white/55 dark:bg-black/20">{icon}</span>}
      </div>
      <div className="display truncate text-[34px] leading-none">{value}</div>
      {sub && <div className="text-[13px] opacity-85">{sub}</div>}
      {tone === "estimate" && (
        <div className="mt-0.5 inline-flex w-fit rounded-full bg-white/55 px-2 py-0.5 text-[11px] font-[500] uppercase tracking-wide dark:bg-black/20">Estimate</div>
      )}
      {footnote && <div className="text-[12px] opacity-75">{footnote}</div>}
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
    <div role="alert" className="flex items-center justify-between gap-3 rounded-2xl tint-rose px-4 py-2.5 text-sm">
      <span className="flex items-center gap-2"><OctagonAlert className="size-4" aria-hidden />{error.message}</span>
      {onRetry && <Button variant="ghost" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-2 rounded-2xl bg-surface-2 px-4 py-6 text-sm text-muted">
      <CircleSlash className="size-4" aria-hidden />{children}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-[13px] font-[450] text-ink-2">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
}

export const inputCls = "min-w-0 rounded-2xl border border-line bg-surface px-3.5 py-2 text-sm text-ink outline-none transition focus:border-ink/60 focus:ring-4 focus:ring-[var(--t-sky)]";

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center" role="dialog" aria-modal="true" aria-label={title}>
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl bg-surface shadow-pop">
        <div className="flex items-center justify-between px-6 pt-5">
          <h2 className="display text-[26px]">{title}</h2>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-surface-2" aria-label="Close"><X className="size-4" /></button>
        </div>
        <div className="p-6">{children}</div>
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
          <div key={t.id} className="pointer-events-auto rounded-2xl bg-surface px-4 py-3 text-sm shadow-pop">
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
