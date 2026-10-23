import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import api, { setToken } from "./api.js";

const AuthContext = createContext(null);
const USER_KEY = "onboardiq_user";

function loadUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(loadUser);

  const logout = useCallback(() => {
    setToken(null);
    try {
      localStorage.removeItem(USER_KEY);
    } catch {
      /* ignore */
    }
    setUser(null);
  }, []);

  const login = useCallback(async (username, password, role) => {
    const { data } = await api.post("/auth/login", { username, password, role });
    setToken(data.access_token);
    try {
      localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    } catch {
      /* ignore */
    }
    setUser(data.user);
    return data.user;
  }, []);

  useEffect(() => {
    window.addEventListener("onboardiq:logout", logout);
    return () => window.removeEventListener("onboardiq:logout", logout);
  }, [logout]);

  const hasRole = (...roles) => !!user && roles.some((r) => user.roles.includes(r));
  return <AuthContext.Provider value={{ user, login, logout, hasRole }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);

export function homeFor(user) {
  if (!user) return "/login";
  if (user.roles.includes("KYC_OFFICER")) return "/review";
  if (user.roles.includes("COMPLIANCE_OFFICER")) return "/checker";
  return "/my";
}

/** Route guard: must be logged in and hold one of the roles (the server enforces this too). */
export function RequireRole({ roles, children }) {
  const { user, hasRole } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !hasRole(...roles)) return <p className="error">Your role cannot open this page.</p>;
  return children;
}
