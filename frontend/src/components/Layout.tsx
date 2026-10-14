import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  Activity, Bell, Brain, CalendarClock, Cpu, DoorOpen, FlaskConical, History, LayoutDashboard, LogOut, Menu,
  Moon, ScrollText, Settings, ShieldCheck, ShieldOff, Sun, TerminalSquare, X, Zap,
} from "lucide-react";
import { useAuth } from "../hooks/auth";
import { useLive } from "../hooks/live";
import { cx } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/rooms", label: "Rooms & appliances", icon: DoorOpen },
  { to: "/devices", label: "Devices", icon: Cpu },
  { to: "/history", label: "History", icon: History },
  { to: "/alerts", label: "Alerts", icon: Bell },
  { to: "/commands", label: "Commands", icon: TerminalSquare },
  { to: "/schedules", label: "Schedules", icon: CalendarClock },
  { to: "/ml", label: "ML model", icon: Brain },
  { to: "/simulation", label: "Simulation", icon: FlaskConical },
  { to: "/events", label: "Event log", icon: ScrollText },
  { to: "/settings", label: "Settings", icon: Settings },
];

type Theme = "system" | "light" | "dark";
function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return (localStorage.getItem("seg_theme") as Theme) || "system";
    } catch {
      return "system";
    }
  });
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("seg_theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  const cycle = () => setTheme((t) => (t === "system" ? "dark" : t === "dark" ? "light" : "system"));
  return [theme, cycle];
}

function Nav({ onNavigate, unacked }: { onNavigate?: () => void; unacked: number }) {
  return (
    <nav className="flex flex-col gap-0.5 p-2" aria-label="Main">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cx("flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm", isActive ? "bg-accent-wash font-semibold text-accent-ink" : "text-ink-2 hover:bg-surface-2")
          }
        >
          <Icon className="size-4" aria-hidden />
          <span className="flex-1">{label}</span>
          {to === "/alerts" && unacked > 0 && (
            <span className="rounded-full bg-critical px-1.5 text-[11px] font-semibold text-white" aria-label={`${unacked} unacknowledged alerts`}>{unacked}</span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const { summary, status } = useLive();
  const [open, setOpen] = useState(false);
  const [theme, cycleTheme] = useTheme();
  const unacked = summary?.alerts.unacknowledged ?? 0;
  const simLive = summary?.data_sources_live.includes("simulation") || summary?.simulation.running;

  return (
    <div className="flex min-h-screen bg-bg text-ink">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-surface lg:flex">
        <Brand />
        <div className="flex-1 overflow-y-auto"><Nav unacked={unacked} /></div>
        <UserBox name={user?.username} role={user?.role} onLogout={logout} />
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col bg-surface">
            <div className="flex items-center justify-between pr-2"><Brand /><button className="rounded p-2" onClick={() => setOpen(false)} aria-label="Close menu"><X className="size-5" /></button></div>
            <div className="flex-1 overflow-y-auto"><Nav unacked={unacked} onNavigate={() => setOpen(false)} /></div>
            <UserBox name={user?.username} role={user?.role} onLogout={logout} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex flex-wrap items-center gap-2 border-b border-line bg-surface/95 px-4 py-2 backdrop-blur">
          <button className="rounded p-1.5 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu className="size-5" /></button>
          <div className="flex flex-1 flex-wrap items-center gap-2 text-xs">
            {simLive && (
              <span className="inline-flex items-center gap-1 rounded-full bg-sim-wash px-2.5 py-1 font-semibold text-sim">
                <FlaskConical className="size-3.5" aria-hidden /> Simulation mode — data is synthetic
              </span>
            )}
            {summary && (
              <span className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2.5 py-1 font-medium text-ink-2">
                <Activity className="size-3.5" aria-hidden /> Automation: <b className="text-ink">{summary.automation_mode.replace("_", "-")}</b>
              </span>
            )}
            {summary && (summary.real_switching_enabled ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-critical/10 px-2.5 py-1 font-semibold text-critical-ink"><ShieldOff className="size-3.5" aria-hidden /> Real switching ENABLED</span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-good/10 px-2.5 py-1 font-medium text-good-ink"><ShieldCheck className="size-3.5" aria-hidden /> Hardware switching disabled</span>
            ))}
          </div>
          <span className="inline-flex items-center gap-1.5 text-xs text-ink-2" title="Live update connection">
            <span className={cx("size-2 rounded-full", status === "open" ? "bg-good" : status === "connecting" ? "bg-warning" : "bg-critical")} />
            {status === "open" ? "Live" : status === "connecting" ? "Connecting" : "Offline"}
          </span>
          <button onClick={cycleTheme} className="rounded-lg p-1.5 text-ink-2 hover:bg-surface-2" aria-label={`Theme: ${theme}`} title={`Theme: ${theme}`}>
            {theme === "dark" ? <Moon className="size-4" /> : theme === "light" ? <Sun className="size-4" /> : <Sun className="size-4 opacity-60" />}
          </button>
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2 px-4 py-4">
      <span className="grid size-8 place-items-center rounded-lg bg-accent text-white"><Zap className="size-4" aria-hidden /></span>
      <div className="leading-tight">
        <div className="text-sm font-semibold">Smart Energy Guardian</div>
        <div className="text-[11px] text-muted">AI-based IoT energy management</div>
      </div>
    </div>
  );
}

function UserBox({ name, role, onLogout }: { name?: string; role?: string; onLogout: () => void }) {
  return (
    <div className="flex items-center justify-between border-t border-line px-4 py-3 text-sm">
      <div className="leading-tight">
        <div className="font-medium">{name}</div>
        <div className="text-xs text-muted">{role}</div>
      </div>
      <button onClick={onLogout} className="rounded-lg p-1.5 text-ink-2 hover:bg-surface-2" aria-label="Log out" title="Log out"><LogOut className="size-4" /></button>
    </div>
  );
}
