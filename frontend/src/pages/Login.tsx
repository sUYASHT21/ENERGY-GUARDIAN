import { useState, type FormEvent } from "react";
import { Zap } from "lucide-react";
import { Button, ErrorBanner, Field, inputCls } from "../components/ui";
import { useAuth } from "../hooks/auth";

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
    <div className="grid min-h-screen place-items-center bg-bg p-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-xl border border-line bg-surface p-6 shadow-sm">
        <div className="mb-5 flex items-center gap-2">
          <span className="grid size-9 place-items-center rounded-lg bg-accent text-white"><Zap className="size-5" aria-hidden /></span>
          <div>
            <h1 className="font-semibold">Smart Energy Guardian</h1>
            <p className="text-xs text-muted">Sign in to the energy management console</p>
          </div>
        </div>
        <div className="flex flex-col gap-3">
          <Field label="Username"><input className={inputCls} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></Field>
          <Field label="Password"><input className={inputCls} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
          <ErrorBanner error={error} />
          <Button variant="primary" type="submit" busy={busy}>Sign in</Button>
          <p className="text-xs text-muted">Local demo default: <code>admin</code> / <code>guardian-demo</code> (change via <code>ADMIN_PASSWORD</code>).</p>
        </div>
      </form>
    </div>
  );
}
