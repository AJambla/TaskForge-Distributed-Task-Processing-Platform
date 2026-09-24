import { useEffect, useState } from "react";
import { Outlet, NavLink, Link, useLocation } from "react-router-dom";
import {
  Activity,
  BarChart3,
  KeyRound,
  Layers,
  LayoutDashboard,
  ListChecks,
  Menu,
  Search,
  Server,
  X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { LogoMark } from "./ui/Logo";
import CommandPalette from "./CommandPalette";
import type { ComponentType } from "react";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ size?: number | string }>;
  admin?: boolean;
  count?: string;
}

const NAV: NavItem[] = [
  { to: "/app/overview", label: "Overview", icon: LayoutDashboard },
  { to: "/app/tasks", label: "Tasks", icon: ListChecks },
  { to: "/app/queues", label: "Queues", icon: Layers, admin: true },
  { to: "/app/workers", label: "Workers", icon: Server, admin: true },
  { to: "/app/metrics", label: "Metrics", icon: BarChart3, admin: true },
  { to: "/app/api-keys", label: "API Keys", icon: KeyRound },
  { to: "/app/activity", label: "Activity", icon: Activity },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const isAdmin = user?.role === "admin";
  const items = NAV.filter((n) => !n.admin || isAdmin);

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const sidebar = (
    <>
      <div className="sidenav__brand">
        <Link to="/app/overview" aria-label="TaskForge console" className="logo-link inline-flex items-center gap-2.5">
          <LogoMark width={26} />
          <span className="text-[16px] font-semibold tracking-[-0.03em]">TaskForge</span>
        </Link>
        <button
          className="icon-btn sidenav__close"
          onClick={() => setMenuOpen(false)}
          aria-label="Close menu"
        >
          <X size={16} />
        </button>
      </div>

      <div className="sidenav__search">
        <button className="search-trigger" onClick={() => setPaletteOpen(true)}>
          <Search size={14} />
          <span>Search…</span>
          <kbd className="search-trigger__kbd">Ctrl K</kbd>
        </button>
      </div>

      <nav className="sidenav__nav" aria-label="Console">
        {items.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => `sidenav__link ${isActive ? "is-active" : ""}`}
          >
            <link.icon size={16} />
            {link.label}
          </NavLink>
        ))}
      </nav>

      <div className="sidenav__foot">
        <div className="sidenav__user">
          <span className="sidenav__avatar" aria-hidden>
            {(user?.email || "?").slice(0, 1).toUpperCase()}
          </span>
          <span className="min-w-0">
            <span className="sidenav__user-email truncate block">{user?.email || "Signed in"}</span>
            <span className="sidenav__user-role">{user?.role ?? "user"}</span>
          </span>
        </div>
        <div className="sidenav__foot-links">
          <button className="sidenav__signout" onClick={logout}>
            Sign out
          </button>
        </div>
      </div>
    </>
  );

  return (
    <div className="console">
      {/* Desktop sidebar */}
      <aside className="sidenav hidden lg:flex">{sidebar}</aside>

      {/* Mobile sidebar overlay */}
      {menuOpen && (
        <div className="sidenav-overlay" role="presentation" onMouseDown={(e) => {
          if (e.target === e.currentTarget) setMenuOpen(false);
        }}>
          <aside className="sidenav sidenav--mobile flex">{sidebar}</aside>
        </div>
      )}

      <div className="console__body">
        <header className="console__topbar lg:hidden">
          <button className="burger" aria-label="Open menu" onClick={() => setMenuOpen(true)}>
            <Menu size={20} />
          </button>
          <Link to="/app/overview" className="logo-link inline-flex items-center gap-2">
            <LogoMark width={22} />
            <span className="text-[15px] font-semibold tracking-[-0.03em]">TaskForge</span>
          </Link>
          <button
            className="icon-btn ml-auto"
            aria-label="Search"
            onClick={() => setPaletteOpen(true)}
          >
            <Search size={16} />
          </button>
        </header>

        <main className="console__main">
          <Outlet />
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
