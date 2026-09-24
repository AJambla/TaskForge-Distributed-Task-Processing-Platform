import { Outlet, NavLink, Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { LogoMark } from "./ui/Logo";
import { Button } from "./ui/Button";

const NAV = [
  { to: "/app/tasks", label: "Tasks" },
  { to: "/app/workers", label: "Workers" },
  { to: "/app/metrics", label: "Metrics" },
  { to: "/app/api-keys", label: "API Keys" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  return (
    <div className="app-shell flex min-h-screen flex-col">
      <header className="appbar">
        <div className="mx-auto flex h-16 max-w-[1180px] items-center gap-8 px-4 sm:px-6 lg:px-8">
          <Link to="/app" aria-label="TaskForge console" className="logo-link inline-flex items-center gap-2.5">
            <LogoMark width={28} />
            <span className="text-[17px] font-semibold tracking-[-0.03em]">TaskForge</span>
          </Link>

          <nav className="hidden items-center gap-7 md:flex" aria-label="Console">
            {NAV.map((link, i) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  `navlink link-in ${isActive ? "is-active" : ""}`
                }
                style={{ "--d": `${0.02 + i * 0.06}s` } as React.CSSProperties}
              >
                {link.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto hidden items-center gap-4 md:flex">
            {user?.email && (
              <span className="mono text-xs" style={{ color: "var(--subtle)" }}>
                {user.email}
              </span>
            )}
            <Button variant="nav" size="sm" withIcon onClick={handleLogout}>
              Sign out
            </Button>
          </div>

          <button
            className="burger md:hidden"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            aria-controls="app-menu"
            onClick={() => setMenuOpen((o) => !o)}
          >
            <span />
            <span />
            <span />
          </button>
        </div>

        {menuOpen && (
          <nav
            id="app-menu"
            className="flex flex-col gap-1 border-t md:hidden"
            style={{ borderColor: "var(--line)", background: "#fff", padding: "12px 16px 16px" }}
            aria-label="Console mobile"
          >
            {NAV.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  `navlink block px-2 py-3 ${isActive ? "is-active" : ""}`
                }
              >
                {link.label}
              </NavLink>
            ))}
            <div className="pt-3">
              <Button variant="nav" size="sm" withIcon onClick={handleLogout}>
                Sign out
              </Button>
            </div>
          </nav>
        )}
      </header>

      <main className="mx-auto w-full max-w-[1180px] flex-1 px-4 py-8 sm:px-6 md:py-10 lg:px-8">
        <Outlet />
      </main>

      <footer
        className="border-t"
        style={{ borderColor: "var(--line)", background: "rgba(255,255,255,0.6)" }}
      >
        <div
          className="mx-auto flex max-w-[1180px] items-center justify-between px-4 py-4 text-xs sm:px-6 lg:px-8"
          style={{ color: "var(--subtle)" }}
        >
          <span>TaskForge — Task Orchestration</span>
          <Link to="/" className="navlink !text-xs">
            Landing
          </Link>
        </div>
      </footer>
    </div>
  );
}
