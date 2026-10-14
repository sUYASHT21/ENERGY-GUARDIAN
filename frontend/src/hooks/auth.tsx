import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getToken, post, setToken, setUnauthorizedHandler } from "../api/client";
import type { Role, User } from "../api/types";

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  can: (role: Role) => boolean;
}

const RANK: Record<Role, number> = { viewer: 0, operator: 1, admin: 2 };
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(getToken());
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(!!getToken());

  const logout = useCallback(() => {
    setToken(null);
    setTok(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    api<User>("/auth/me")
      .then((u) => !cancelled && setUser(u))
      .catch(() => !cancelled && logout())
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [token, logout]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await post<{ access_token: string; user: User }>("/auth/login", { username, password });
    setToken(res.access_token);
    setTok(res.access_token);
    setUser(res.user);
  }, []);

  const can = useCallback((role: Role) => !!user && RANK[user.role] >= RANK[role], [user]);

  const value = useMemo(() => ({ user, token, loading, login, logout, can }), [user, token, loading, login, logout, can]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
