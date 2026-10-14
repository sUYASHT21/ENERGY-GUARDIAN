const CURRENCY_SYMBOL: Record<string, string> = { INR: "₹", USD: "$", EUR: "€", GBP: "£" };

export function currencySymbol(code: string): string {
  return CURRENCY_SYMBOL[code] ?? `${code} `;
}

export function formatPower(watts: number | null | undefined): string {
  if (watts == null || Number.isNaN(watts)) return "—";
  if (Math.abs(watts) >= 1000) return `${(watts / 1000).toFixed(2)} kW`;
  return `${watts.toFixed(0)} W`;
}

export function formatKwh(kwh: number | null | undefined, digits?: number): string {
  if (kwh == null || Number.isNaN(kwh)) return "—";
  const d = digits ?? (Math.abs(kwh) < 1 ? 3 : Math.abs(kwh) < 100 ? 2 : 1);
  return `${kwh.toFixed(d)} kWh`;
}

export function formatMoney(amount: number | null | undefined, currency = "INR"): string {
  if (amount == null || Number.isNaN(amount)) return "—";
  return `${currencySymbol(currency)}${amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatKg(kg: number | null | undefined): string {
  if (kg == null || Number.isNaN(kg)) return "—";
  return kg < 10 ? `${kg.toFixed(2)} kg` : `${kg.toFixed(1)} kg`;
}

export function compact(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(Math.abs(n) >= 10_000 ? 0 : 1)}K`;
  return `${Math.round(n)}`;
}

export function timeAgo(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ago`;
  return `${Math.floor(h / 24)} d ago`;
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function humanize(s: string): string {
  return s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
