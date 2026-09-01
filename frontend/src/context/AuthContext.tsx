import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import { type User, type LoginCredentials, type RegisterCredentials, type LoginResponse } from "../types";
import client from "../api/client";

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (credentials: RegisterCredentials) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) {
      const decoded = decodeJwt(token);
      if (decoded) {
        setUser({ id: decoded.sub, email: decoded.email || "", role: decoded.role });
        setIsAuthenticated(true);
      }
    }
  }, []);

  const decodeJwt = (token: string): { sub: string; role: string; email?: string } | null => {
    try {
      const payload = token.split(".")[1];
      if (!payload) return null;
      const decoded = JSON.parse(atob(payload));
      return decoded;
    } catch {
      return null;
    }
  };

  const login = async (credentials: LoginCredentials) => {
    const response = await client.post<LoginResponse>("/auth/login", credentials);
    const { access_token, refresh_token, expires_in } = response.data;
    localStorage.setItem("access_token", access_token);
    localStorage.setItem("refresh_token", refresh_token);
    localStorage.setItem("access_expires_in", String(expires_in));
    const decoded = decodeJwt(access_token);
    if (decoded) {
      setUser({ id: decoded.sub, email: credentials.email, role: decoded.role });
      setIsAuthenticated(true);
    }
  };

  const register = async (credentials: RegisterCredentials) => {
    await client.post("/auth/register", credentials);
  };

  const logout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("access_expires_in");
    setUser(null);
    setIsAuthenticated(false);
  };

  return (
    <AuthContext.Provider value={{ user, isAuthenticated, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
