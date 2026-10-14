export type Role = "viewer" | "operator" | "admin";
export type Source = "simulation" | "emulator" | "hardware";
export type Occupancy = "occupied" | "vacant" | "unknown";

export interface User {
  id: number;
  username: string;
  role: Role;
  is_active: boolean;
}

export interface Summary {
  generated_at: string;
  timezone: string;
  currency: string;
  live_power_w: number;
  live_power_by_source: Record<string, number>;
  energy_today_kwh: number;
  energy_today_by_source: Record<string, number>;
  cost_today: number;
  wasted_today_kwh: number;
  wasted_cost_today: number;
  wasted_co2_today_kg: number;
  estimated_savings: {
    label: string;
    today_kwh: number;
    today_cost: number;
    today_co2_kg: number;
    total_kwh: number;
    total_cost: number;
    total_co2_kg: number;
    by_source: Record<string, number>;
    episodes: number;
    active_episodes: number;
  };
  carbon_today_kg: number;
  carbon_factor_kg_per_kwh: number;
  tariff_rate_now: number;
  rooms: { total: number; occupied: number; vacant: number; unknown: number };
  appliances: { total: number; on: number; off: number; unknown: number };
  devices: Record<string, number> & { total: number };
  alerts: { open: number; unacknowledged: number; by_severity: Record<string, number> };
  data_sources_live: Source[];
  simulation: { enabled: boolean; running: boolean };
  automation_mode: "recommend" | "dry_run" | "auto";
  real_switching_enabled: boolean;
  ml: { method: string; model_version: string | null };
}

export interface Room {
  id: number;
  name: string;
  room_type: string;
  building: string;
  floor: number;
  capacity: number;
  auto_control_enabled: boolean;
  min_vacancy_minutes: number;
  manual_override: boolean;
  override_until: string | null;
  override_reason: string;
  occupancy_state: Occupancy;
  occupancy_updated_at: string | null;
  vacant_since: string | null;
  people_count: number | null;
  occupancy_source: Source | null;
}

export interface Check {
  name: string;
  category: "data" | "waste" | "safety" | "mode";
  passed: boolean;
  detail: string;
}

export interface Decision {
  appliance_id: number;
  action: "none" | "recommend_shutdown" | "auto_shutdown";
  data_ok: boolean;
  waste_detected: boolean;
  execution_mode: string | null;
  summary: string;
  checks: Check[];
  blockers: string[];
  notes: string[];
  evaluated_at: string;
}

export interface Appliance {
  id: number;
  name: string;
  appliance_type: string;
  room_id: number;
  device_id: number | null;
  relay_channel: number;
  rated_power_w: number;
  standby_threshold_w: number;
  essential: boolean;
  auto_off_allowed: boolean;
  manual_override: boolean;
  state: "on" | "off" | "unknown";
  last_power_w: number | null;
  last_voltage_v: number | null;
  last_current_a: number | null;
  last_reading_at: string | null;
  last_source: Source | null;
  last_anomaly_score: number | null;
  anomaly_streak: number;
  decision?: Decision;
}

export interface Schedule {
  id: number;
  room_id: number;
  day_of_week: number;
  start_time: string;
  end_time: string;
  label: string;
  enabled: boolean;
}

export interface RoomDetail {
  room: Room;
  appliances: (Appliance & { decision: Decision })[];
  devices: { id: number; name: string; kind: string; connection_status: string; sensor_status: string }[];
  schedules: Schedule[];
}

export interface Device {
  id: number;
  uid: string;
  name: string;
  kind: "simulated" | "emulator" | "esp32";
  source: Source;
  room_id: number | null;
  has_occupancy_sensor: boolean;
  control_validated: boolean;
  connection_status: "online" | "offline" | "never_seen";
  last_seen_at: string | null;
  firmware_version: string | null;
  ip_address: string | null;
  rssi_dbm: number | null;
  uptime_s: number | null;
  free_heap: number | null;
  sensor_status: string;
  error_count: number;
  health: { score: number; issues: string[] };
  appliance_count: number;
}

export interface Alert {
  id: number;
  alert_type: string;
  severity: "info" | "warning" | "critical";
  title: string;
  message: string;
  room_id: number | null;
  appliance_id: number | null;
  device_id: number | null;
  source: Source | null;
  details: Record<string, unknown>;
  recommendation: string | null;
  created_at: string;
  last_seen_at: string;
  occurrences: number;
  acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved: boolean;
  resolved_at: string | null;
  resolution_note: string | null;
}

export interface Command {
  id: number;
  appliance_id: number;
  device_id: number | null;
  action: "on" | "off";
  mode: string;
  status: "pending" | "sent" | "acknowledged" | "failed" | "timeout" | "dry_run" | "blocked";
  origin: "automation" | "manual";
  requested_by: string;
  reason: string;
  decision: Partial<Decision>;
  created_at: string;
  sent_at: string | null;
  expires_at: string | null;
  completed_at: string | null;
  result_relay_on: boolean | null;
  error: string | null;
}

export interface EventItem {
  id: number;
  ts: string;
  level: string;
  category: string;
  message: string;
  actor: string | null;
  room_id: number | null;
  appliance_id: number | null;
  device_id: number | null;
}

export interface HistoryPoint {
  period: string;
  energy_kwh: number;
  wasted_kwh: number;
  cost: number;
  simulation_kwh: number;
  emulator_kwh: number;
  hardware_kwh: number;
}

export interface OverviewRoom {
  id: number;
  name: string;
  room_type: string;
  occupancy_state: Occupancy;
  people_count: number | null;
  vacant_since: string | null;
  occupancy_source: Source | null;
  manual_override: boolean;
  power_w: number;
  appliances: {
    id: number;
    name: string;
    type: string;
    state: "on" | "off" | "unknown";
    power_w: number | null;
    essential: boolean;
    source: Source | null;
    anomaly: boolean;
    decision: Decision["action"] | null;
  }[];
  devices: { id: number; name: string; kind: string; connection_status: string; sensor_status: string }[];
}

export interface RuntimeSettings {
  automation_mode: "recommend" | "dry_run" | "auto";
  currency: string;
  tariff_flat_rate: number;
  tariff_tou_enabled: boolean;
  tariff_tou_periods: { name: string; start: string; end: string; rate: number }[];
  carbon_factor_kg_per_kwh: number;
  timezone: string;
  default_min_vacancy_minutes: number;
  schedule_grace_minutes: number;
  manual_on_cooldown_minutes: number;
  anomaly_persistence: number;
  savings_cap_hours: number;
  auto_command_cooldown_minutes: number;
}

export interface SettingsResponse {
  runtime: RuntimeSettings;
  environment: {
    app_env: string;
    real_switching_enabled: boolean;
    simulation_enabled: boolean;
    command_timeout_seconds: number;
    device_offline_seconds: number;
    telemetry_stale_seconds: number;
    max_integration_gap_seconds: number;
    using_insecure_defaults: boolean;
  };
}

export interface ModelRecord {
  id: number;
  version: string;
  algorithm: string;
  trained_at: string;
  data_source: string;
  n_train: number;
  n_test: number;
  params: Record<string, unknown>;
  metrics: {
    precision: number;
    recall: number;
    f1: number;
    roc_auc: number;
    false_positive_rate: number;
    confusion_matrix: { tn: number; fp: number; fn: number; tp: number };
    recall_by_anomaly_kind: Record<string, number>;
    n_test: number;
    n_test_anomalies: number;
    evaluated_on: string;
  };
  active: boolean;
}

export interface MLStatus {
  method: string;
  model_version: string | null;
  last_error: string | null;
  active_model: ModelRecord | null;
  models: ModelRecord[];
  last_hour: { readings_scored: number; flagged: number };
  disclaimer: string;
  safety_note: string;
}

export interface ScorePoint {
  ts: string;
  appliance_id: number;
  appliance: string | null;
  score: number;
  is_anomaly: boolean;
  method: string;
  power_w: number;
  source: Source;
}

export interface SimulationStatus {
  enabled: boolean;
  running: boolean;
  tick?: number;
  tick_seconds?: number;
  scenarios?: Record<string, string>;
  rooms?: { room_id: number; room: string; scenario: string }[];
}

export interface LivePoint {
  ts: string;
  power_w: number;
  sources?: string[];
}
