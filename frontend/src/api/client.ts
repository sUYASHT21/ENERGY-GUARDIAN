export const API_BASE = "/api/v1";
const TOKEN_KEY = "seg_token";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(formatDetail(detail) || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

function formatDetail(detail: unknown): string {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => (typeof e === "object" && e && "msg" in e ? `${(e as { loc?: unknown[] }).loc?.slice(1).join(".") ?? ""} ${(e as { msg: string }).msg}`.trim() : String(e)))
      .join("; ");
  }
  return JSON.stringify(detail);
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session-only login */
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

export async function api<T>(path: string, options: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  });
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    if (res.status === 401 && onUnauthorized) onUnauthorized();
    const body = data as { detail?: unknown; errors?: unknown } | null;
    throw new ApiError(res.status, body?.errors ?? body?.detail ?? res.statusText);
  }
  return data as T;
}

export const post = <T>(path: string, body?: unknown) => api<T>(path, { method: "POST", body: body ?? {} });
export const put = <T>(path: string, body: unknown) => api<T>(path, { method: "PUT", body });
export const patch = <T>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body });
export const del = (path: string) => api<void>(path, { method: "DELETE" });
