import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { LogoMark } from "../../components/ui/Logo";
import { Button } from "../../components/ui/Button";
import Field from "../../components/ui/Field";
import { Eye, EyeOff } from "lucide-react";

const d = (s: string) => ({ "--d": s } as React.CSSProperties);

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await login({ email, password });
      navigate("/app/tasks");
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: { message?: string } } } };
      setError(
        axiosErr.response?.data?.error?.message || "Invalid email or password"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-shell flex min-h-screen flex-col">
      <header className="appbar">
        <div className="mx-auto flex h-16 w-full max-w-[1180px] items-center px-4 sm:px-6 lg:px-8">
          <Link to="/" className="logo-link inline-flex items-center gap-2.5" aria-label="TaskForge home">
            <LogoMark width={28} />
            <span className="text-[17px] font-semibold tracking-[-0.03em]">TaskForge</span>
          </Link>
          <div className="ml-auto text-sm" style={{ color: "var(--subtle)" }}>
            New here?{" "}
            <Link to="/register" className="font-medium" style={{ color: "var(--brand)" }}>
              Create an account
            </Link>
          </div>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-[420px]">
          <div className="wipe" style={d("0.05s")}>
            <span className="badge">
              Console access
            </span>
            <h1
              className="mt-5 font-semibold"
              style={{ fontSize: 34, letterSpacing: "-0.035em", lineHeight: 1.15 }}
            >
              Welcome back.
            </h1>
            <p className="mt-2 text-sm" style={{ color: "var(--subtle)" }}>
              Sign in to your TaskForge workspace.
            </p>
          </div>

          <div className="panel mt-8 p-6 rise" style={{ ...d("0.18s"), padding: 28 }}>
            <form onSubmit={handleSubmit} className="space-y-5">
              {error && (
                <div
                  className="chip chip--failed w-full"
                  style={{ padding: "12px 14px", display: "flex", whiteSpace: "normal" }}
                  role="alert"
                >
                  {error}
                </div>
              )}

              <Field label="Email">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="field__input"
                  placeholder="you@example.com"
                  required
                  autoComplete="email"
                />
              </Field>

              <Field label="Password">
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="field__input pr-11"
                    placeholder="••••••••"
                    required
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((s) => !s)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    className="absolute right-3 top-1/2 -translate-y-1/2"
                    style={{ color: "var(--subtle)" }}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </Field>

              <Button
                type="submit"
                variant="nav"
                withIcon
                disabled={loading}
                className="btn--block"
              >
                {loading ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </div>

          <p className="mt-6 text-center text-sm" style={{ color: "var(--subtle)" }}>
            By continuing you agree to run{" "}
            <span style={{ color: "var(--text)" }}>every job with a plan</span>.
          </p>
        </div>
      </main>
    </div>
  );
}
