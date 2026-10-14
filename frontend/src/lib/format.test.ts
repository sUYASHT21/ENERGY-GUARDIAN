import { describe, expect, it } from "vitest";
import { compact, formatKg, formatKwh, formatMoney, formatPower, humanize, timeAgo } from "./format";

describe("format helpers", () => {
  it("formats power with kW above 1000 W", () => {
    expect(formatPower(950)).toBe("950 W");
    expect(formatPower(1500)).toBe("1.50 kW");
    expect(formatPower(null)).toBe("—");
  });
  it("formats energy with adaptive precision", () => {
    expect(formatKwh(0.0456)).toBe("0.046 kWh");
    expect(formatKwh(12.345)).toBe("12.35 kWh");
    expect(formatKwh(371.44)).toBe("371.4 kWh");
  });
  it("formats money with currency symbol", () => {
    expect(formatMoney(2971.09, "INR")).toBe("₹2,971.09");
    expect(formatMoney(5, "USD")).toBe("$5.00");
    expect(formatMoney(5, "CHF")).toBe("CHF 5.00");
  });
  it("formats kg and compact numbers", () => {
    expect(formatKg(2.345)).toBe("2.35 kg");
    expect(formatKg(12.34)).toBe("12.3 kg");
    expect(compact(1500)).toBe("1.5K");
    expect(compact(25000)).toBe("25K");
    expect(compact(42)).toBe("42");
  });
  it("renders relative times", () => {
    const now = Date.parse("2026-01-01T12:00:00Z");
    expect(timeAgo(null)).toBe("never");
    expect(timeAgo("2026-01-01T11:59:58Z", now)).toBe("just now");
    expect(timeAgo("2026-01-01T11:59:30Z", now)).toBe("30s ago");
    expect(timeAgo("2026-01-01T11:50:00Z", now)).toBe("10 min ago");
    expect(timeAgo("2026-01-01T09:00:00Z", now)).toBe("3 h ago");
  });
  it("humanizes identifiers", () => {
    expect(humanize("vacant_room_waste")).toBe("Vacant room waste");
  });
});
