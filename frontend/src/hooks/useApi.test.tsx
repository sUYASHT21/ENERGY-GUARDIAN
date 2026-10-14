import { act, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useApi } from "./useApi";

const versions = { current: 0 };
vi.mock("./live", () => ({ useLiveVersion: () => versions.current }));

function Probe() {
  const { data } = useApi<{ n: number }>("/thing", { refreshOn: ["command"], throttleMs: 1000 });
  return <div>value:{data?.n ?? "-"}</div>;
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useApi live refresh", () => {
  it("keeps refetching on live messages under StrictMode (regression)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ n: ++n }), { status: 200 })));
    versions.current = 3; // messages already received before the page mounted
    const { rerender } = render(<StrictMode><Probe /></StrictMode>);
    await screen.findByText(/value:\d/);
    const before = n;
    for (let i = 0; i < 3; i++) {
      versions.current += 1;
      rerender(<StrictMode><Probe /></StrictMode>);
      await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    }
    expect(n).toBeGreaterThanOrEqual(before + 3);
    expect(screen.getByText(`value:${n}`)).toBeInTheDocument();
  });
});
