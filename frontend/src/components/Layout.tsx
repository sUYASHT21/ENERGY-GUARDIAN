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
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, tint: "tint-peach", group: "Monitor" },
  { to: "/rooms", label: "Rooms & appliances", icon: DoorOpen, tint: "tint-sky", group: "Monitor" },
  { to: "/alerts", label: "Alerts", icon: Bell, tint: "tint-rose", group: "Monitor" },
  { to: "/history", label: "History", icon: History, tint: "tint-butter", group: "Monitor" },
  { to: "/devices", label: "Devices", icon: Cpu, tint: "tint-sage", group: "Operate" },
  { to: "/commands", label: "Commands", icon: TerminalSquare, tint: "tint-lilac", group: "Operate" },
  { to: "/schedules", label: "Schedules", icon: CalendarClock, tint: "tint-sky", group: "Operate" },
  { to: "/ml", label: "ML model", icon: Brain, tint: "tint-lilac", group: "Intelligence" },
  { to: "/simulation", label: "Simulation", icon: FlaskConical, tint: "tint-peach", group: "Intelligence" },
  { to: "/events", label: "Event log", icon: ScrollText, tint: "tint-butter", group: "System" },
  { to: "/settings", label: "Settings", icon: Settings, tint: "tint-sage", group: "System" },
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
  const groups = [...new Set(NAV.map((n) => n.group))];
  return (
    <nav className="flex flex-col gap-4 px-3 py-2" aria-label="Main">
      {groups.map((g) => (
        <div key={g}>
          <div className="px-3 pb-1.5 text-[12px] text-tag">{g}</div>
          <div className="flex flex-col gap-0.5">
            {NAV.filter((n) => n.group === g).map(({ to, label, icon: Icon, end, tint }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cx("group flex items-center gap-2.5 rounded-full py-1.5 pl-1.5 pr-3 text-[14px] transition",
                    isActive ? "bg-ink font-[480] text-surface" : "text-ink-2 hover:bg-surface-2")
                }
              >
                <span className={cx("grid size-7 place-items-center rounded-full", tint)}><Icon className="size-3.5" aria-hidden /></span>
                <span className="flex-1">{label}</span>
                {to === "/alerts" && unacked > 0 && (
                  <span className="rounded-full bg-critical px-1.5 text-[11px] font-semibold text-white" aria-label={`${unacked} unacknowledged alerts`}>{unacked}</span>
                )}
              </NavLink>
            ))}
          </div>
        </div>
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
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-line bg-surface lg:flex">
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
        <header className="sticky top-0 z-30 flex flex-wrap items-center gap-2 bg-bg/85 px-4 py-3 backdrop-blur md:px-8">
          <button className="rounded p-1.5 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu className="size-5" /></button>
          <div className="flex flex-1 flex-wrap items-center gap-2 text-xs">
            {simLive && (
              <span className="inline-flex items-center gap-1 rounded-full tint-lilac px-3 py-1 font-[500]">
                <FlaskConical className="size-3.5" aria-hidden /> Simulation mode — data is synthetic
              </span>
            )}
            {summary && (
              <span className="inline-flex items-center gap-1 rounded-full tint-sky px-3 py-1 font-[450]">
                <Activity className="size-3.5" aria-hidden /> Automation: <b className="font-[600]">{summary.automation_mode.replace("_", "-")}</b>
              </span>
            )}
            {summary && (summary.real_switching_enabled ? (
              <span className="inline-flex items-center gap-1 rounded-full tint-rose px-3 py-1 font-[600]"><ShieldOff className="size-3.5" aria-hidden /> Real switching ENABLED</span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full tint-sage px-3 py-1 font-[450]"><ShieldCheck className="size-3.5" aria-hidden /> Hardware switching disabled</span>
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
        <main className="mx-auto w-full max-w-[1320px] flex-1 px-4 pb-16 pt-4 md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-5 py-5">
      <span className="grid size-9 place-items-center rounded-full tint-peach"><Zap className="size-4" aria-hidden /></span>
      <div className="leading-tight">
        <div className="display text-[19px] tracking-[-0.01em]">Energy <em>Guardian</em></div>
        <div className="text-[12px] text-tag">AI-based IoT energy management</div>
      </div>
    </div>
  );
}

function UserBox({ name, role, onLogout }: { name?: string; role?: string; onLogout: () => void }) {
  return (
    <div className="m-3 flex items-center justify-between rounded-2xl bg-surface-2 px-3 py-2.5 text-sm">
      <div className="flex items-center gap-2.5 leading-tight">
        <span className="grid size-9 place-items-center rounded-full tint-sky text-[13px] font-[600] uppercase">{name?.slice(0, 2)}</span>
        <div>
        <div className="font-[480]">{name}</div>
        <div className="text-xs text-muted">{role}</div>
        </div>
      </div>
      <button onClick={onLogout} className="rounded-lg p-1.5 text-ink-2 hover:bg-surface-2" aria-label="Log out" title="Log out"><LogOut className="size-4" /></button>
    </div>
  );
}
