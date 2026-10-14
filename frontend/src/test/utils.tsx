import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { ToastProvider } from "../components/ui";
import { AuthProvider } from "../hooks/auth";

export type Handler = (url: string, init: RequestInit) => unknown | Promise<unknown>;

/** Install a fetch mock routing "METHOD /path" (path without /api/v1 and query) to handlers. */
export function mockApi(routes: Record<string, Handler | unknown>) {
  const calls: { method: string; url: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input).replace(/^\/api\/v1/, "");
    const method = (init.method ?? "GET").toUpperCase();
    const body = init.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, url, body });
    const path = url.split("?")[0];
    const key = Object.keys(routes).find((k) => {
      const [m, p] = k.split(" ");
      if (m !== method) return false;
      const re = new RegExp("^" + p.replace(/:\w+/g, "[^/]+") + "$");
      return re.test(path);
    });
    if (!key) return new Response(JSON.stringify({ detail: `no mock for ${method} ${url}` }), { status: 404 });
    const h = routes[key];
    const data = typeof h === "function" ? await (h as Handler)(url, init) : h;
    if (data instanceof Response) return data;
    return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  close() {}
  send() {}
}

export function mockWebSocket() {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
  return FakeWebSocket;
}

export function renderAt(ui: ReactElement, { path = "/", route = "/" } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ToastProvider>
        <AuthProvider>
          <Routes><Route path={path} element={ui} /></Routes>
        </AuthProvider>
      </ToastProvider>
    </MemoryRouter>,
  );
}

export const ADMIN = { id: 1, username: "admin", role: "admin", is_active: true };

export const SUMMARY = {
  generated_at: new Date().toISOString(), timezone: "Asia/Kolkata", currency: "INR",
  live_power_w: 4321, live_power_by_source: { simulation: 4321 }, energy_today_kwh: 12.5, energy_today_by_source: { simulation: 12.5 },
  cost_today: 100, wasted_today_kwh: 2.25, wasted_cost_today: 18, wasted_co2_today_kg: 1.6,
  estimated_savings: { label: "ESTIMATE — test", today_kwh: 1.2, today_cost: 9.6, today_co2_kg: 0.85, total_kwh: 3, total_cost: 24, total_co2_kg: 2.1, by_source: { simulation: 3 }, episodes: 2, active_episodes: 1 },
  carbon_today_kg: 8.9, carbon_factor_kg_per_kwh: 0.71, tariff_rate_now: 8,
  rooms: { total: 2, occupied: 1, vacant: 1, unknown: 0 }, appliances: { total: 3, on: 2, off: 1, unknown: 0 },
  devices: { total: 2, online: 2 }, alerts: { open: 1, unacknowledged: 1, by_severity: { warning: 1 } },
  data_sources_live: ["simulation"], simulation: { enabled: true, running: true }, automation_mode: "dry_run",
  real_switching_enabled: false, ml: { method: "isolation_forest", model_version: "if-v1-s42" },
};
