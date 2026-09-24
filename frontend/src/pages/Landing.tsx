import { useState } from "react";
import { Link } from "react-router-dom";
import { LogoMark } from "../components/ui/Logo";
import { ButtonLink } from "../components/ui/Button";

const BG_VIDEO =
  "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260808_075824_7c8a2ef3-826c-43ca-81a1-162429faa306.mp4";

const LINKS = ["Platform", "Workers", "Reliability", "Pricing"];

const d = (s: string) => ({ "--d": s } as React.CSSProperties);

export default function Landing() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="landing">
      <div className="landing__bg">
        <video className="bg-video" autoPlay muted loop playsInline>
          <source src={BG_VIDEO} type="video/mp4" />
        </video>
      </div>

      <header className="landing__nav">
        <nav className="glass-bar landing__nav-links" aria-label="Primary">
          {LINKS.map((label, i) => (
            <a
              key={label}
              href="#"
              className="navlink link-in"
              style={d(`${0.02 + i * 0.06}s`)}
            >
              {label}
            </a>
          ))}
        </nav>

        <Link to="/" className="landing__logo" aria-label="TaskForge">
          <LogoMark width={36} />
        </Link>

        <div className="landing__cta">
          <ButtonLink to="/login" variant="nav" withIcon delay={0.16} className="wipe-r">
            Launch Console
          </ButtonLink>
        </div>

        <button
          className="burger landing__burger link-in"
          style={d("0.16s")}
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          aria-controls="landing-menu"
          onClick={() => setMenuOpen((o) => !o)}
        >
          <span />
          <span />
          <span />
        </button>
      </header>

      <div
        id="landing-menu"
        className={`landing__mobile ${menuOpen ? "is-open" : ""}`}
        hidden={!menuOpen}
      >
        {LINKS.map((label) => (
          <a key={label} href="#" className="mobile-link" onClick={() => setMenuOpen(false)}>
            {label}
          </a>
        ))}
        <ButtonLink to="/login" variant="nav" withIcon>
          Launch Console
        </ButtonLink>
      </div>

      <main className="landing__hero">
        <span className="badge wipe" style={d("0.18s")}>
          <span className="badge__sq" aria-hidden />
          Task Orchestration for Engineering Teams
        </span>

        <h1 className="hl" style={{ marginTop: "clamp(22px, 2.8vw, 36px)" }}>
          <span className="hl__mask">
            <span className="hl__rise" style={d("0.26s")}>
              Every background job
            </span>
          </span>
          <span className="hl__mask">
            <span className="hl__rise hl__nowrap" style={d("0.4s")}>
              <span className="hl__muted">starts with a </span>
              <span className="accent" data-text="reliable queue.">
                reliable queue.
              </span>
            </span>
          </span>
        </h1>

        <div className="landing__actions">
          <ButtonLink to="/login" variant="light" withIcon delay={0.56} className="wipe">
            Launch Console
          </ButtonLink>
          <ButtonLink to="/login" variant="ghost" delay={0.66} className="wipe">
            See TaskForge in Action
          </ButtonLink>
        </div>
      </main>

      <p className="landing__lede">
        <span className="hl__rise" style={d("0.78s")}>
          TaskForge continuously routes, retries and supervises your workloads across
          elastic worker pools — predicting failure risk, surfacing dead letters early,
          and recommending the highest-impact actions for your team.
        </span>
      </p>
    </div>
  );
}
