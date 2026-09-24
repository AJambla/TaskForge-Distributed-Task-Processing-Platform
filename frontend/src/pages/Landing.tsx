import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  Code2,
  CalendarClock,
  Zap,
  Fingerprint,
  KeyRound,
  Layers,
  Server,
  Activity,
  Gauge,
  History,
  RefreshCw,
  Archive,
  Ban,
  BarChart3,
} from "lucide-react";
import { LogoMark } from "../components/ui/Logo";
import { ButtonLink } from "../components/ui/Button";
import StatusPill from "../components/ui/StatusPill";

const BG_VIDEO =
  "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260808_075824_7c8a2ef3-826c-43ca-81a1-162429faa306.mp4";

const LINKS = [
  { label: "Platform", href: "#platform" },
  { label: "Workers", href: "#workers" },
  { label: "Reliability", href: "#reliability" },
];

const d = (s: string) => ({ "--d": s } as React.CSSProperties);

function onHashClick(e: React.MouseEvent<HTMLAnchorElement>) {
  const href = e.currentTarget.getAttribute("href") || "";
  if (!href.startsWith("#")) return;
  const target = document.querySelector(href);
  if (!target) return;
  e.preventDefault();
  target.scrollIntoView({
    behavior: document.visibilityState === "hidden" ? "auto" : "smooth",
  });
  history.replaceState(null, "", href);
}

function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          io.disconnect();
        }
      },
      { threshold: 0.12 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`reveal ${inView ? "is-in" : ""} ${className}`}
      style={d(`${delay}s`)}
    >
      {children}
    </div>
  );
}

interface Feature {
  icon: ReactNode;
  title: string;
  body: string;
}

function FeatureGrid({ features }: { features: Feature[] }) {
  return (
    <div className="feature-grid">
      {features.map((f, i) => (
        <Reveal key={f.title} delay={i * 0.06} className="feature">
          <span className="feature__icon">{f.icon}</span>
          <h3 className="feature__title">{f.title}</h3>
          <p className="feature__body">{f.body}</p>
        </Reveal>
      ))}
    </div>
  );
}

const PLATFORM_FEATURES: Feature[] = [
  {
    icon: <Code2 size={18} />,
    title: "Submit via REST API",
    body: "POST tasks to a versioned API with JWT or API-key auth. Email, image-resize and webhook jobs ship as first-class task types.",
  },
  {
    icon: <CalendarClock size={18} />,
    title: "Schedule & recur",
    body: "Run now or later with run_at, or attach recurrence rules for periodic jobs — without cron sprawl on your servers.",
  },
  {
    icon: <Zap size={18} />,
    title: "Priority lanes",
    body: "Latency-sensitive work gets a higher priority so it is picked up before the backlog ahead of it.",
  },
  {
    icon: <Fingerprint size={18} />,
    title: "Idempotency keys",
    body: "Safe retries at the API boundary: duplicate submissions with the same key collapse into a single task.",
  },
  {
    icon: <KeyRound size={18} />,
    title: "API keys",
    body: "Programmatic keys with visible prefixes, last-used tracking and one-click revocation from the console.",
  },
  {
    icon: <Layers size={18} />,
    title: "Queues per task type",
    body: "Main, retry and dead-letter queues keep every workload isolated — one noisy type never starves the others.",
  },
];

const WORKER_FEATURES: Feature[] = [
  {
    icon: <Server size={18} />,
    title: "Self-registering pool",
    body: "Workers announce themselves with hostname and concurrency limits on boot. Scale the fleet, the console follows.",
  },
  {
    icon: <Activity size={18} />,
    title: "Live heartbeats",
    body: "Status refreshes every 5 seconds. A silent worker flips to offline automatically — no page needed to notice.",
  },
  {
    icon: <Gauge size={18} />,
    title: "Load visibility",
    body: "Current vs max concurrency per worker, with processed and failed counters, so hot-spots surface before they hurt.",
  },
  {
    icon: <History size={18} />,
    title: "Attempt attribution",
    body: "Every execution attempt is recorded against its worker with outcome, timing and error detail for post-mortems.",
  },
];

const RELIABILITY_FEATURES: Feature[] = [
  {
    icon: <RefreshCw size={18} />,
    title: "Bounded retries with backoff",
    body: "Configurable max attempts per task. Retrying work waits in a dedicated retry queue instead of hammering your services.",
  },
  {
    icon: <Archive size={18} />,
    title: "Dead-letter queue",
    body: "Poison messages are parked in a broker DLQ rather than hot-looping workers — inspect them and redrive when ready.",
  },
  {
    icon: <Ban size={18} />,
    title: "Cancellation",
    body: "Stop queued or retrying tasks from the console before they ever reach a worker.",
  },
  {
    icon: <BarChart3 size={18} />,
    title: "Queue metrics",
    body: "Throughput per minute, pickup and execution latency, and per-type queue depth — live in the metrics dashboard.",
  },
];

export default function Landing() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <>
      <div className="landing" id="top">
        <div className="landing__bg">
          <video className="bg-video" autoPlay muted loop playsInline>
            <source src={BG_VIDEO} type="video/mp4" />
          </video>
        </div>

        <header className="landing__nav">
          <nav className="glass-bar landing__nav-links" aria-label="Primary">
            {LINKS.map((link, i) => (
              <a
                key={link.label}
                href={link.href}
                onClick={onHashClick}
                className="navlink link-in"
                style={d(`${0.02 + i * 0.06}s`)}
              >
                {link.label}
              </a>
            ))}
          </nav>

          <Link to="/" className="landing__logo" aria-label="TaskForge">
            <LogoMark width={36} />
          </Link>

          <div className="landing__cta" />

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
          {LINKS.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="mobile-link"
              onClick={(e) => {
                onHashClick(e);
                setMenuOpen(false);
              }}
            >
              {link.label}
            </a>
          ))}
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

      {/* ---------- Platform ---------- */}
      <section id="platform" className="section">
        <div className="section__inner">
          <Reveal>
            <span className="section__eyebrow">Platform</span>
            <h2 className="section__title">
              One queue for <span className="hl__muted">every background job.</span>
            </h2>
            <p className="section__lede">
              Submit work through the API or the console. TaskForge routes each job to the
              right queue, tracks every attempt, and hands you the levers — priority,
              scheduling, idempotency — when it matters.
            </p>
          </Reveal>
          <FeatureGrid features={PLATFORM_FEATURES} />
        </div>
      </section>

      {/* ---------- Workers ---------- */}
      <section id="workers" className="section section--alt">
        <div className="section__inner">
          <Reveal>
            <span className="section__eyebrow">Workers</span>
            <h2 className="section__title">
              A worker pool <span className="hl__muted">you can actually see.</span>
            </h2>
            <p className="section__lede">
              Workers register themselves, beat like a heart, and report their load. The
              console keeps every number live — and every attempt is attributed back to
              the worker that ran it.
            </p>
          </Reveal>
          <FeatureGrid features={WORKER_FEATURES} />
          <Reveal delay={0.1}>
            <div className="pipeline" aria-label="Task lifecycle">
              <StatusPill status="queued" />
              <span className="pipeline__arrow">→</span>
              <StatusPill status="running" />
              <span className="pipeline__arrow">→</span>
              <StatusPill status="succeeded" />
              <span className="pipeline__arrow">/</span>
              <StatusPill status="failed" />
              <span className="pipeline__arrow">→</span>
              <StatusPill status="retrying" />
              <span className="pipeline__arrow">→</span>
              <StatusPill status="dead_letter" />
              <span className="pipeline__arrow">·</span>
              <StatusPill status="cancelled" />
            </div>
          </Reveal>
        </div>
      </section>

      {/* ---------- Reliability ---------- */}
      <section id="reliability" className="section">
        <div className="section__inner">
          <Reveal>
            <span className="section__eyebrow">Reliability</span>
            <h2 className="section__title">
              Failure is <span className="hl__muted">a plan, not a surprise.</span>
            </h2>
            <p className="section__lede">
              Retries are bounded, backoff is automatic, and poison messages go to a
              dead-letter queue instead of melting your workers. Then the metrics tell you
              what happened before your users do.
            </p>
          </Reveal>
          <FeatureGrid features={RELIABILITY_FEATURES} />
        </div>
      </section>

      {/* ---------- CTA band ---------- */}
      <section className="cta-band">
        <div className="cta-band__inner">
          <Reveal>
            <h2 className="cta-band__title">
              Ready to give every job <em>a reliable queue?</em>
            </h2>
          </Reveal>
          <Reveal delay={0.1}>
            <ButtonLink to="/login" variant="light" withIcon>
              Launch Console
            </ButtonLink>
          </Reveal>
        </div>
      </section>

      {/* ---------- Footer ---------- */}
      <footer className="site-footer">
        <div className="site-footer__inner">
          <div className="site-footer__top">
            <div>
              <Link to="/" className="logo-link inline-flex items-center gap-2.5" aria-label="TaskForge home">
                <LogoMark width={28} />
                <span className="text-[16px] font-semibold tracking-[-0.03em]">TaskForge</span>
              </Link>
              <p className="site-footer__blurb">
                Task orchestration for engineering teams — queues, workers, retries and
                live metrics in one console, with a REST API for everything else.
              </p>
            </div>
            <div>
              <h3>Product</h3>
              <ul>
                {LINKS.map((link) => (
                  <li key={link.label}>
                    <a href={link.href} onClick={onHashClick}>
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3>Console</h3>
              <ul>
                <li>
                  <Link to="/login">Sign in</Link>
                </li>
                <li>
                  <Link to="/register">Create account</Link>
                </li>
              </ul>
            </div>
            <div>
              <h3>Task types</h3>
              <ul>
                <li>
                  <a href="#platform" onClick={onHashClick}>
                    Email sending
                  </a>
                </li>
                <li>
                  <a href="#platform" onClick={onHashClick}>
                    Image resizing
                  </a>
                </li>
                <li>
                  <a href="#platform" onClick={onHashClick}>
                    Webhook delivery
                  </a>
                </li>
              </ul>
            </div>
          </div>
          <div className="site-footer__bottom">
            <span>© 2026 TaskForge. Built for engineering teams.</span>
            <a href="#top" className="navlink !text-xs" onClick={onHashClick}>
              Back to top ↑
            </a>
          </div>
        </div>
      </footer>
    </>
  );
}
