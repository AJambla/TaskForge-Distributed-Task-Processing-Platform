# SECURITY.md — Security Specification

## Threat Model Summary

TaskForge accepts input from two categories of actor: authenticated developers submitting tasks (semi-trusted — they have an account, but their *inputs* are not trusted), and, indirectly, whatever a task payload references (an image URL, a webhook destination URL). The primary risks are therefore not "a stranger reaches the system" (the API requires auth) but "an authenticated user's task payload is used to attack the system, the workers, or third parties" — SSRF via webhook/image URLs, resource exhaustion via oversized or malicious inputs, and abuse of the platform as an attack proxy (e.g. using webhook delivery to port-scan internal infrastructure). Because task types are fixed and built-in (not arbitrary user code), the threat model is bounded to input-level attacks against known handlers, not arbitrary code execution.

## Authentication

- **Password security:** Passwords hashed with bcrypt (or argon2), never stored or logged in plaintext. Minimum length/complexity enforced at registration.
- **Sessions/JWT:** Short-lived access tokens (~15 min) plus a longer-lived, revocable refresh token (stored hashed server-side, checked on refresh). Access tokens are stateless; revocation happens via refresh-token invalidation, not access-token blacklisting, keeping the hot-path auth check fast.
- **API keys:** Generated as a high-entropy random value, stored only as a hash (SHA-256) in Postgres — matching the password-hashing principle of never storing the usable secret. Full key value shown to the user exactly once, at creation.
- **Token expiration:** Access tokens expire in ~15 minutes; refresh tokens in ~30 days, revocable at any time via `DELETE`-equivalent logout; API keys do not expire by default but are revocable.

## Authorization

- **RBAC:** Two roles — `user` and `admin`. `user` can manage only their own tasks/API keys; `admin` can view all tasks, all workers, and system-wide queue metrics.
- **Resource ownership:** Every task/API-key read or mutation endpoint checks `user_id` ownership server-side (never trusts a client-supplied user identifier); admins are explicitly exempted, not implicitly assumed.
- **Admin privileges:** Granted only via direct database update in MVP (no self-service admin promotion endpoint) — a deliberate, small piece of friction to prevent privilege-escalation bugs in a feature that has essentially one legitimate user (the project operator) at this project's scale.

## API Security

- **Input validation:** Every request body is validated against a Pydantic schema before touching the database or being queued; task `payload` is validated against a **per-task-type** schema (e.g. `image_resize` requires a well-formed URL and bounded width/height; `webhook_delivery` requires a well-formed URL and a bounded body size) — this is the first and most important control, since it's what stands between an attacker and the handler.
- **Rate limiting:** Per-API-key and per-user request limits (see API.md), enforced via Redis, protecting against both accidental client bugs (retry storms) and deliberate abuse.
- **Request size limits:** Body size capped at the ASGI server/reverse-proxy layer (e.g. a few hundred KB for task submission bodies) — task payloads reference external resources (URLs) rather than embedding large binary data directly, keeping this limit realistic.
- **CORS:** Restricted to the known dashboard origin(s) in production; permissive only in local development.
- **CSRF:** Not applicable to the API-key/JWT-bearer-token auth model used here (no cookie-based session auth), which sidesteps CSRF by design rather than requiring CSRF tokens.
- **Security headers:** Standard hardening headers (`X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security` in production) set at the API/reverse-proxy layer.

## Task Security (Primary Focus Area)

This is the most important section given TaskForge's nature — it processes externally referenced content on behalf of users.

- **Arbitrary code execution:** Not applicable — TaskForge has no user-uploaded-code or arbitrary-handler feature by design (see PRD.md Non-Goals); this eliminates the largest class of risk that a general task-execution platform would otherwise need to solve.
- **Malicious task payloads:** Mitigated at the validation layer — every payload is checked against a strict per-type schema before it is ever queued or reaches a handler; unknown fields are rejected rather than silently ignored (fail closed).
- **SSRF (Server-Side Request Forgery):** The `image_resize` (fetches a `source_url`) and `webhook_delivery` (POSTs to a target URL) handlers are the concrete SSRF risk. Mitigations implemented in `app/core/ssrf.py`:
  - Enforce `http` or `https` URL schemes only.
  - Resolve and validate the target hostname before connecting.
  - Reject private/link-local/loopback IP ranges (RFC 1918 `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), Carrier-Grade NAT (`100.64.0.0/10`), multicast (`224.0.0.0/4`), IPv6 loopback (`::1`), link-local (`fe80::/10`), and cloud metadata endpoints (`169.254.169.254`).
  - Disable automatic client redirects (`follow_redirects=False`) across all HTTP fetch handlers to prevent post-validation redirect bypasses.
  - Enforce connection timeouts and response-size caps.
- **Command injection:** Not applicable to the fixed handler set, since no handler shells out with user-controlled arguments; if this were ever added, the rule is: never build a shell command via string interpolation with task-payload data.
- **Container escape:** Workers run as an unprivileged, non-root user (`taskforge`) inside their container, with no unnecessary host mounts or capabilities — reduces the blast radius of a hypothetical handler-level vulnerability.
- **Resource exhaustion:** Every task execution runs under a per-task-type timeout (killed and marked `timeout` if exceeded) and, for the image-resize handler specifically, explicit memory/dimension caps (e.g. reject payloads requesting an output image above a defined pixel-count ceiling) to prevent a single task from exhausting a worker's memory.
- **Malicious dependencies:** Dependencies pinned and scanned in CI (see DEPLOYMENT.md § CI/CD "Security Scan" stage) using `pip-audit` and `npm audit`.

## Secrets

- **Environment variables:** Used for local development (`.env`, gitignored, `.env.example` committed as a template with no real values).
- **Secret manager:** In production, secrets (DB credentials, RabbitMQ credentials, JWT signing key) are provided via environment variables. The API and worker startup logic enforces non-default production secrets and fails fast if defaults are detected in production mode.
- **API keys:** Application-level API keys (for TaskForge's own users) are hashed at rest (SHA-256), with `last_used_at` updates debounced in Redis.
- **Database credentials:** Provided via the managed Postgres connection string, injected as an environment variable at deploy time, never hardcoded.

## Infrastructure

- **TLS:** Terminated at the reverse proxy / PaaS edge for all public traffic; internal service-to-service traffic uses private Docker networks.
- **Network isolation:** Postgres, Redis, and RabbitMQ are not exposed on public ports in production — reachable only from the API/worker services within the internal network.
- **Container permissions:** Containers run as non-root user (`taskforge`, uid 10001); no privileged containers; minimal base images.
- **Least privilege:** Database credentials used by the API/workers are scoped to only the tables/operations they need.
- **Storage security:** Resized images stored in designated `IMAGE_OUTPUT_DIR` with sanitized unique filenames (`uuid4.hex`).

## Database

- **SQL injection:** Mitigated structurally — all queries go through SQLAlchemy parameterized async queries, never raw string interpolation.
- **Access controls:** Application connects with dedicated application role; no direct end-user database access.
- **Encryption:** Encryption at rest and in transit via TLS-enabled database connections.

## Monitoring (Security-Relevant)

- **Audit logs:** Authentication events (login success/failure, API key creation/revocation) are logged with timestamp, user ID, and source IP to application logs.
- **Suspicious activity:** Repeated failed logins or API-key auth failures are visible in logs and rate-limited.
- **Failed authentication:** Logged distinctly from authorization failures (401 vs 403) to make brute-force attempts identifiable.
- **Abnormal task behavior:** Sudden spikes in submission rate are throttled by rate limiting; abnormal failure rates trigger Prometheus alert rules.

## Security Checklist

- [x] All task payloads validated against strict per-type schemas before queueing.
- [x] SSRF protections active on `image_resize` and `webhook_delivery` handlers (RFC 1918, CGNAT `100.64.0.0/10`, metadata blocking, `follow_redirects=False`).
- [x] Passwords (bcrypt) and API keys (SHA-256) stored only as hashes.
- [x] JWT access tokens short-lived (15 min); refresh tokens revocable with rotation on refresh.
- [x] Rate limiting enforced on task submission and auth endpoints with `Retry-After` headers.
- [x] Security response headers injected (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `HSTS` in production).
- [x] Postgres/Redis/RabbitMQ not publicly reachable in production configurations.
- [x] Containers run as non-root (`taskforge`) with no unnecessary capabilities.
- [x] Dependency scanning wired into CI (`pip-audit`, `npm audit`).
- [x] Secrets sourced from environment, fail-fast production checks against default secrets.
- [x] Task execution timeouts and memory caps enforced per task type.
