import { useState, type FormEvent } from "react";
import { ArrowRight, Bolt, Leaf, ShieldCheck, Users, Zap } from "lucide-react";
import { Button, ErrorBanner, Field, inputCls } from "../components/ui";
import { useAuth } from "../hooks/auth";

/* Editorial hero: serif headline on warm paper, floating product fragments around it,
   the sign-in form as a floating artifact. Fragments are illustrative (labelled "preview"). */
export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
    } catch (err) {
      setError(err as Error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg">
      <header className="mx-auto flex max-w-[1200px] items-center justify-between px-5 py-5">
        <div className="flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-full tint-peach"><Zap className="size-4" aria-hidden /></span>
          <span className="display text-[20px]">Energy <em>Guardian</em></span>
        </div>
        <span className="hidden text-[14px] text-tag sm:inline">Classrooms · Laboratories · Hostels</span>
      </header>

      <main className="mx-auto grid max-w-[1200px] grid-cols-1 items-center gap-10 px-5 pb-16 pt-6 lg:grid-cols-12 lg:pt-12">
        <section className="relative lg:col-span-7">
          <div className="mb-4 text-[14px] text-tag">AI-based IoT energy management</div>
          <h1 className="display text-[44px] leading-[1.08] text-ink sm:text-[64px] lg:text-[76px]">
            Lights off <em>when the room</em> empties out.
          </h1>
          <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-muted">
            Occupancy sensors, live power metering, schedules and an Isolation Forest model work together to find wasted
            electricity — and switch it off only when every safety check agrees.
          </p>

          <div className="relative mt-10 hidden h-[230px] sm:block" aria-hidden>
            <div className="absolute left-0 top-2 w-[230px] rotate-[-2deg] rounded-[20px] bg-surface p-4 shadow-float">
              <div className="flex items-center justify-between text-[13px] text-muted"><span>Live power</span><Bolt className="size-4" /></div>
              <div className="mt-1 text-[22px] font-[500]">9.31 kW</div>
              <svg viewBox="0 0 200 50" className="mt-2 h-12 w-full"><path d="M0 38 C25 30 40 34 60 26 S100 12 120 22 160 30 200 8" fill="none" stroke="var(--line-live)" strokeWidth="2" /></svg>
            </div>
            <div className="absolute left-[250px] top-12 w-[220px] rotate-[1.5deg] rounded-3xl tint-sage p-4">
              <div className="flex items-center gap-1.5 text-[13px]"><Leaf className="size-4" /> CO₂ avoided</div>
              <div className="display mt-1 text-[30px] leading-none">2.4 kg</div>
              <div className="mt-1 text-[12px] opacity-80">estimate · simulated shutdowns</div>
            </div>
            <div className="absolute left-[60px] top-[150px] flex items-center gap-3 rounded-full bg-surface py-2 pl-2 pr-4 shadow-float">
              <span className="grid size-8 place-items-center rounded-full tint-sky"><Users className="size-4" /></span>
              <span className="text-[13px]">CR-102 vacant 12 min · <b className="font-[500]">AC off</b></span>
            </div>
            <div className="absolute left-[360px] top-[160px] flex items-center gap-2 rounded-full tint-lilac px-3 py-1.5 text-[12px]">
              <ShieldCheck className="size-3.5" /> 18 safety checks passed
            </div>
            <span className="absolute -bottom-2 left-0 text-[11px] text-tag">Preview — your live data appears after sign-in</span>
          </div>
        </section>

        <section className="lg:col-span-5">
          <form onSubmit={submit} className="rounded-[20px] bg-surface p-7 shadow-float">
            <h2 className="display text-[30px]">Sign <em>in</em></h2>
            <p className="mt-1 text-[14px] text-muted">to the energy management console</p>
            <div className="mt-6 flex flex-col gap-4">
              <Field label="Username"><input className={inputCls} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></Field>
              <Field label="Password"><input className={inputCls} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
              <ErrorBanner error={error} />
              <Button variant="primary" type="submit" busy={busy} className="py-2.5 text-[15px]">Sign in <ArrowRight className="size-4" /></Button>
              <p className="rounded-2xl bg-surface-2 px-3.5 py-2.5 text-[13px] text-ink-2">
                Local demo default: <code>admin</code> / <code>guardian-demo</code> — change it with <code>ADMIN_PASSWORD</code>.
              </p>
            </div>
          </form>
        </section>
      </main>
    </div>
  );
}
