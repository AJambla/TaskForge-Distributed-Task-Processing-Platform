import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { LogoMark } from "../../components/ui/Logo";
import { Button } from "../../components/ui/Button";
import Field, { Spinner } from "../../components/ui/Field";
import { Eye, EyeOff } from "lucide-react";

const d = (s: string) => ({ "--d": s } as React.CSSProperties);

const STRENGTH = [
  { label: "Weak", color: "#b91c1c" },
  { label: "Fair", color: "#c2410c" },
  { label: "Good", color: "#b45309" },
  { label: "Strong", color: "#067647" },
];

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const passwordStrength = (pwd: string) => {
    let score = 0;
    if (pwd.length >= 8) score++;
    if (/[A-Z]/.test(pwd)) score++;
    if (/[a-z]/.test(pwd)) score++;
    if (/[0-9]/.test(pwd)) score++;
    return score;
  };

  const strength = passwordStrength(password);
  const strengthInfo = STRENGTH[Math.max(0, strength - 1)];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    setLoading(true);

    try {
      await register({ email, password });
      setSuccess(true);
      setTimeout(() => navigate("/login"), 1500);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: { message?: string } } } };
      setError(
        axiosErr.response?.data?.error?.message || "Registration failed. Please try again."
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
            Already registered?{" "}
            <Link to="/login" className="font-medium" style={{ color: "var(--brand)" }}>
              Sign in
            </Link>
          </div>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-[420px]">
          <div className="wipe" style={d("0.05s")}>
            <span className="badge">
              Start orchestrating
            </span>
            <h1
              className="mt-5 font-semibold"
              style={{ fontSize: 34, letterSpacing: "-0.035em", lineHeight: 1.15 }}
            >
              Create your account.
            </h1>
            <p className="mt-2 text-sm" style={{ color: "var(--subtle)" }}>
              Get your queues, workers and metrics in one console.
            </p>
          </div>

          <div className="panel mt-8 rise" style={{ ...d("0.18s"), padding: 28 }}>
            {success ? (
              <div className="py-8 text-center">
                <span className="chip chip--succeeded mx-auto" style={{ padding: "10px 16px" }}>
                  Account created
                </span>
                <p className="mt-4 text-sm" style={{ color: "var(--subtle)" }}>
                  Redirecting to sign in…
                </p>
                <div className="mt-6 flex justify-center">
                  <Spinner size={22} />
                </div>
              </div>
            ) : (
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

                <Field
                  label="Password"
                  hint={
                    password ? (
                      <div className="flex items-center gap-3">
                        <span className="flex flex-1 gap-1" aria-hidden>
                          {[1, 2, 3, 4].map((i) => (
                            <span
                              key={i}
                              className="h-[3px] flex-1"
                              style={{
                                background: i <= strength ? strengthInfo.color : "var(--line)",
                              }}
                            />
                          ))}
                        </span>
                        <span style={{ color: strengthInfo.color }}>{strengthInfo.label}</span>
                      </div>
                    ) : null
                  }
                >
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="field__input pr-11"
                      placeholder="••••••••"
                      required
                      minLength={8}
                      autoComplete="new-password"
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

                <Field label="Confirm password">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="field__input"
                    placeholder="••••••••"
                    required
                    autoComplete="new-password"
                  />
                </Field>

                <Button
                  type="submit"
                  variant="nav"
                  withIcon
                  disabled={loading}
                  className="btn--block"
                >
                  {loading ? "Creating account…" : "Create account"}
                </Button>
              </form>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
