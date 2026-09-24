import { useEffect, useRef, useState } from "react";
import { Outlet, NavLink, Link, useLocation } from "react-router-dom";
import {
  Activity,
  BarChart3,
  ChevronUp,
  KeyRound,
  Layers,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  Search,
  Server,
  Settings,
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
  { to: "/app/queues", label: "Queues", icon: Layers },
  { to: "/app/workers", label: "Workers", icon: Server },
  { to: "/app/metrics", label: "Metrics", icon: BarChart3, admin: true },
  { to: "/app/activity", label: "Activity", icon: Activity },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const isAdmin = user?.role === "admin";
  const items = NAV.filter((n) => !n.admin || isAdmin);
  const footRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMenuOpen(false);
    setProfileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!profileOpen) return;
    const onDown = (e: MouseEvent) => {
      if (footRef.current && !footRef.current.contains(e.target as Node)) {
        setProfileOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [profileOpen]);

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

      <div className="sidenav__foot" ref={footRef}>
        {profileOpen && (
          <div className="profile-menu" role="menu">
            <Link to="/app/api-keys" className="profile-menu__item" role="menuitem">
              <KeyRound size={14} /> API Keys
            </Link>
            <Link to="/app/settings" className="profile-menu__item" role="menuitem">
              <Settings size={14} /> Settings
            </Link>
            <button className="profile-menu__item profile-menu__item--danger" role="menuitem" onClick={logout}>
              <LogOut size={14} /> Sign out
            </button>
          </div>
        )}
        <button
          className="sidenav__user sidenav__user--btn"
          onClick={() => setProfileOpen((o) => !o)}
          aria-haspopup="menu"
          aria-expanded={profileOpen}
        >
          <span className="sidenav__avatar" aria-hidden>
            {(user?.email || "?").slice(0, 1).toUpperCase()}
          </span>
          <span className="min-w-0 flex-1 text-left">
            <span className="sidenav__user-email truncate block">{user?.email || "Signed in"}</span>
            <span className="sidenav__user-role">{user?.role ?? "user"}</span>
          </span>
          <ChevronUp
            size={14}
            style={{
              color: "var(--subtle)",
              transition: "transform 0.2s var(--ease)",
              transform: profileOpen ? "rotate(180deg)" : undefined,
            }}
          />
        </button>
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
