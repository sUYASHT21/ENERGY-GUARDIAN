import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { ADMIN, SUMMARY, mockApi, mockWebSocket, renderAt } from "../test/utils";
import Alerts from "./Alerts";
import { mergeLivePoints } from "./Dashboard";
import RoomDetail from "./RoomDetail";
import Settings from "./Settings";

beforeEach(() => {
  localStorage.clear();
  mockWebSocket();
  window.history.pushState({}, "", "/");
});
afterEach(() => vi.unstubAllGlobals());

const decision = (overrides = {}) => ({
  appliance_id: 5, action: "recommend_shutdown", data_ok: true, waste_detected: true, execution_mode: null,
  summary: "Wastage detected; automatic shutdown blocked by policy (no_active_schedule)",
  checks: [
    { name: "power_data_fresh", category: "data", passed: true, detail: "last reading 2s ago (limit 45s)" },
    { name: "room_vacant", category: "waste", passed: true, detail: "room occupancy 'vacant'" },
    { name: "no_active_schedule", category: "safety", passed: false, detail: "scheduled session active: Lecture" },
  ],
  blockers: ["no_active_schedule"], notes: [], evaluated_at: new Date().toISOString(), ...overrides,
});

const ROOM_DETAIL = {
  room: { id: 2, name: "CR-102 Seminar Room", room_type: "classroom", building: "A", floor: 1, capacity: 30, auto_control_enabled: true,
    min_vacancy_minutes: 1, manual_override: false, override_until: null, override_reason: "", occupancy_state: "vacant",
    occupancy_updated_at: new Date().toISOString(), vacant_since: new Date().toISOString(), people_count: 0, occupancy_source: "simulation" },
  appliances: [{ id: 5, name: "Split AC", appliance_type: "ac", room_id: 2, device_id: 2, relay_channel: 3, rated_power_w: 1200,
    standby_threshold_w: 36, essential: false, auto_off_allowed: true, manual_override: false, state: "on", last_power_w: 1100,
    last_voltage_v: 230, last_current_a: 5, last_reading_at: new Date().toISOString(), last_source: "simulation",
    last_anomaly_score: -0.05, anomaly_streak: -3, decision: decision() }],
  devices: [{ id: 2, name: "Sim node CR-102", kind: "simulated", connection_status: "online", sensor_status: "ok" }],
  schedules: [],
};

describe("login and dashboard", () => {
  it("logs in and renders backend summary values", async () => {
    const { calls } = mockApi({
      "POST /auth/login": { access_token: "tok", user: ADMIN, expires_in_minutes: 60 },
      "GET /auth/me": ADMIN,
      "GET /dashboard/summary": SUMMARY,
      "GET /dashboard/live-power": [],
      "GET /dashboard/overview": [],
      "GET /dashboard/history": { series: [], currency: "INR" },
      "GET /alerts": [],
      "GET /devices": [],
    });
    render(<App />);
    await userEvent.type(await screen.findByLabelText("Password"), "guardian-demo");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Campus energy overview")).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/auth/login")?.body).toEqual({ username: "admin", password: "guardian-demo" });
    expect(localStorage.getItem("seg_token")).toBe("tok");
    expect((await screen.findAllByText("4.32 kW")).length).toBeGreaterThan(0);
    expect(screen.getByText("12.50 kWh")).toBeInTheDocument();
    expect(screen.getByText("Simulation mode — data is synthetic")).toBeInTheDocument();
    expect(screen.getByText("Hardware switching disabled")).toBeInTheDocument();
    expect(screen.getAllByText("Estimate").length).toBe(3);
  });

  it("shows an error for wrong credentials", async () => {
    mockApi({ "POST /auth/login": () => new Response(JSON.stringify({ detail: "invalid username or password" }), { status: 401 }) });
    render(<App />);
    await userEvent.type(await screen.findByLabelText("Password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid username or password");
  });
});

describe("room detail", () => {
  beforeEach(() => localStorage.setItem("seg_token", "tok"));

  it("explains the decision with every check", async () => {
    mockApi({ "GET /auth/me": ADMIN, "GET /rooms/:id": ROOM_DETAIL, "GET /dashboard/live-power": [], "GET /commands": [] });
    renderAt(<RoomDetail />, { path: "/rooms/:id", route: "/rooms/2" });
    expect(await screen.findByText("Split AC")).toBeInTheDocument();
    expect(screen.getByText("Shutdown recommended")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /show decision checks for split ac/i }));
    expect(screen.getByText(/scheduled session active: Lecture/)).toBeInTheDocument();
    expect(screen.getByText(/automatic shutdown blocked by policy/)).toBeInTheDocument();
    expect(screen.getAllByLabelText("failed")).toHaveLength(1);
  });

  it("sends a manual OFF command and reports a blocked result", async () => {
    const { calls } = mockApi({
      "GET /auth/me": ADMIN, "GET /rooms/:id": ROOM_DETAIL, "GET /dashboard/live-power": [], "GET /commands": [],
      "POST /commands": { id: 9, status: "blocked", action: "off", mode: "dry_run", error: "controller is offline; device status unavailable" },
    });
    renderAt(<RoomDetail />, { path: "/rooms/:id", route: "/rooms/2" });
    await screen.findByText("Split AC");
    await waitFor(() => expect(screen.getByRole("button", { name: /^Off$/ })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /^Off$/ }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url === "/commands")).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ appliance_id: 5, action: "off", dry_run: false });
    expect(await screen.findByText(/Blocked: controller is offline/)).toBeInTheDocument();
  });
});

describe("alerts", () => {
  beforeEach(() => localStorage.setItem("seg_token", "tok"));
  it("acknowledges an alert through the API", async () => {
    const alert = { id: 7, alert_type: "anomaly", severity: "warning", title: "Abnormal consumption: Test benches", message: "power 2.3x rated",
      room_id: 4, appliance_id: 12, device_id: 4, source: "simulation", details: {}, recommendation: "Inspect the appliance.",
      created_at: new Date().toISOString(), last_seen_at: new Date().toISOString(), occurrences: 3, acknowledged: false,
      acknowledged_by: null, acknowledged_at: null, resolved: false, resolved_at: null, resolution_note: null };
    const { calls } = mockApi({ "GET /auth/me": ADMIN, "GET /alerts": [alert], "GET /rooms": [], "POST /alerts/:id/acknowledge": { ...alert, acknowledged: true } });
    renderAt(<Alerts />);
    expect(await screen.findByText("Abnormal consumption: Test benches")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Acknowledge" })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url === "/alerts/7/acknowledge")).toBe(true));
  });
});

describe("settings", () => {
  beforeEach(() => localStorage.setItem("seg_token", "tok"));
  it("shows real switching as environment-locked and saves only changed fields", async () => {
    const runtime = { automation_mode: "dry_run", currency: "INR", tariff_flat_rate: 8, tariff_tou_enabled: false, tariff_tou_periods: [],
      carbon_factor_kg_per_kwh: 0.71, timezone: "Asia/Kolkata", default_min_vacancy_minutes: 10, schedule_grace_minutes: 10,
      manual_on_cooldown_minutes: 15, anomaly_persistence: 2, savings_cap_hours: 8, auto_command_cooldown_minutes: 5 };
    const env = { app_env: "development", real_switching_enabled: false, simulation_enabled: true, command_timeout_seconds: 20,
      device_offline_seconds: 30, telemetry_stale_seconds: 45, max_integration_gap_seconds: 300, using_insecure_defaults: false };
    const { calls } = mockApi({ "GET /auth/me": ADMIN, "GET /settings": { runtime, environment: env },
      "PUT /settings": (_u: string, init: RequestInit) => ({ runtime: { ...runtime, ...JSON.parse(String(init.body)) }, environment: env }) });
    renderAt(<Settings />);
    expect(await screen.findByText("Environment (read-only)")).toBeInTheDocument();
    expect(screen.getByText("Disabled")).toBeInTheDocument();
    const rate = screen.getByLabelText("Flat rate per kWh");
    await userEvent.clear(rate);
    await userEvent.type(rate, "9.5");
    await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ tariff_flat_rate: 9.5 });
  });
});

describe("live point merging", () => {
  it("sorts, de-duplicates near-identical timestamps and caps length", () => {
    const pts = mergeLivePoints(
      [{ ts: "2026-01-01T00:00:10Z", power_w: 2 }, { ts: "2026-01-01T00:00:00Z", power_w: 1 }],
      [{ ts: "2026-01-01T00:00:10.500Z", power_w: 3 }, { ts: "2026-01-01T00:00:20Z", power_w: 4 }],
    );
    expect(pts.map((p) => p.power_w)).toEqual([1, 2, 4]);
  });
});
