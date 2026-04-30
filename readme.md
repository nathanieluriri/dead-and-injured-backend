# Dead & Injured — Backend

FastAPI service backing the Dead & Injured game. Async MongoDB via Motor, JWT-cookie auth, Celery + Redis for outbound email, slowapi for rate-limiting, Pydantic v2 schemas. The project layout was originally scaffolded by the in-house `fasterapi` CLI; the rest of this document covers operational concerns specific to this service.

---

## Layout

```
backend/
├── api/v1/                FastAPI routers (one file per resource)
├── core/                  config, db, cookies, rate-limit, background tasks
├── email_templates/       HTML email bodies
├── repositories/          Motor query helpers
├── schemas/               Pydantic models (Create / Out / Update / etc.)
├── security/              auth dependencies, JWT, password hashing
├── services/              business logic, called by routers
├── main.py                FastAPI app, exception handlers, router wiring
├── seed.py                bootstrap data
├── docker-compose.yml     Mongo + Redis + Celery worker
└── requirements.txt
```

---

## Run locally

```bash
pip install -r requirements.txt
docker compose up -d        # Mongo, Redis, worker
uvicorn main:app --reload   # API on :8000
```

Configuration is environment-driven; see [`core/config.py`](core/config.py) for the full list. Email delivery uses Resend via `RESEND_API_KEY`, with optional `RESEND_FROM_EMAIL` and `RESEND_FROM_NAME` overrides. At boot, the resolved non-secret settings (`ENV`, `COOKIE_SECURE`, `COOKIE_SAMESITE`, CORS origins, prefixes) are logged so misconfiguration shows up in the container logs instead of silently defaulting.

---

## Auth at a glance

- HS256 JWTs signed with one of N rotating secrets stored in Mongo (`db.secret_keys`); the `kid` header selects which one.
- Access + refresh tokens issued on signup / login, set as `HttpOnly` cookies. Cookie names are `di_access` and `di_refresh` by default.
- `verify_token` dependency rejects expired tokens with 401 and tampered/unknown-kid tokens with 403 — the distinction matters for the refresh flow.
- `verify_token_to_refresh` accepts an *expired* access token plus a valid refresh token and returns both, so the rotation endpoint can issue a new pair while invalidating the old.

The migration to **RS256 + a public JWKS endpoint** is tracked in [`../todo.md`](../todo.md). Until that lands, only the backend can verify tokens — the frontend middleware can only check cookie presence.

---

## CSRF posture

There is **no token-based CSRF**. Defense-in-depth comes from two layers:

1. **`SameSite` cookie attribute.** `lax` in development, forced to `strict` in production by [`core/config.py`](core/config.py). Browsers refuse to attach the cookie to a cross-site `POST`, `PATCH`, `PUT`, or `DELETE`.
2. **Finite CORS allowlist with `allow_credentials=True`.** Configured via `CORS_ORIGINS`; defaults to `http://localhost:3000,http://127.0.0.1:3000`. Browsers refuse to share the response with any origin outside that list, so a malicious page can fire the request but cannot read what comes back.

This is sufficient *only* while the following invariants hold. Breaking any one of them silently regresses CSRF protection and requires reintroducing tokens:

- **No state-changing `GET` routes.** `SameSite=lax` still attaches cookies to top-level cross-site `GET` navigations. Any handler that mutates state on `GET` is reachable cross-origin.
- **Tight CORS allowlist.** Wildcards (`*`) or echoing back arbitrary origins defeats the second layer. `allow_credentials` requires concrete origins.
- **Public-API browsers only.** Native mobile clients and server-to-server callers do not honor `SameSite`; if they ever share these cookies, add a CSRF token.

`/.well-known/jwks.json` (planned, see todo) is intentionally CORS-open and unauthenticated — it returns public keys.

---

## JWT secret rotation

Module-level `_secret_cache` in [`security/encrypting_jwt.py`](security/encrypting_jwt.py) loads the `SECRETID` document from Mongo once and reuses it for the lifetime of the process. The cache is **per-process**, so rotating `SECRETID` requires every web and Celery worker container to be restarted before the new keys take effect.

### Procedure

1. **Add the new key to the existing document.** Update the Mongo document at `db.secret_keys[ObjectId(SECRETID)]` to add a new `{kid: secret}` entry alongside the existing ones. Do *not* remove the old keys yet.
2. **Roll the deploy.** Restart every web container and every Celery worker. Until a process restarts, it continues signing and verifying with the keys it loaded at boot.
3. **Wait one access-token TTL.** Default 10 days. After this, no live access token is signed with the about-to-be-retired key.
4. **Wait one refresh-token TTL.** Default 30 days. After this, no live refresh-rotation can produce a token signed with the old key.
5. **Remove the old key from Mongo and roll once more.** Now the old `kid` is unknown and any straggler token signed with it is rejected as `TokenInvalidError`.

If the new key is *added* without removing the old one, no rolling restart is required for new sessions to remain valid — `decode_jwt_token` looks up by `kid` and accepts whichever key the token was signed with, as long as the cache contains it. The restart is only required for the issuer to *start using* the new key.

### Hot-rotation (optional follow-up)

If "wait for the next deploy" is too slow, two options exist:

- **SIGHUP handler** that calls `_secret_cache = None`. Send `kill -HUP <pid>` after updating Mongo and the next request reloads the cache.
- **Admin-only endpoint** that does the same. Easier to operate but requires its own auth, and you are using JWTs to authenticate the call that invalidates the JWT cache — bootstrap carefully.

Neither is implemented; the rolling restart is currently the only supported path.

---

## Email delivery

Outbound email is queued through Celery (`enqueue_email` in [`services/email_service.py`](services/email_service.py)). The function returns an `EmailDispatch` enum:

- `QUEUED` — handed off to the broker; a worker will deliver.
- `DELAYED` — broker unreachable. The failure is logged loudly and the caller surfaces a degraded UX (signup still succeeds, the response carries `meta.verification_email = "delayed"`, and the frontend renders a banner asking the user to request a new link).

There is currently **no outbox sweeper**, so `DELAYED` effectively means "lost." Adding a Celery beat job that periodically replays logged-but-undelivered emails is tracked in [`../todo.md`](../todo.md); without it, the degraded indicator is honest about the immediate failure but the eventual-consistency guarantee does not exist.

---

## Recovering an unverified account

If the verification email never arrives (broker outage, dropped message, user deleted it), the user must still be able to recover. The recovery loop is: log in → hit `POST /users/verify-email/resend` → receive a fresh token. For this to work, **`verify_token_email_verified` must gate gameplay only, never the recovery path itself.** Today (verified by grep) it gates exactly two routes: `POST /games/matchmaking/queue` and `POST /matches/multiplayer-round`. Login (`/users/login`), the session refresher (`/users/refresh`), `/users/me`, and `/users/verify-email/resend` all use plain `verify_token` and accept unverified accounts.

If you ever extend `verify_token_email_verified` to a route that an unverified user must reach during recovery, the loop breaks. Two fixes in priority order:

1. **Don't tighten the gate.** Verify the user is in fact recovering (not already past the gameplay paywall) and use plain `verify_token`.
2. **If the gate must apply,** add an unauthenticated `POST /users/verify-email/request` that takes an email, looks up the user, and queues a fresh token. Mirror `request_password_reset`'s shape exactly: rate-limited, returns the same envelope shape regardless of whether the email matches a real account, never leaks existence. Without enumeration safety, the endpoint is a free email-to-account oracle.

The frontend mounts a "Resend verification" button on the profile page (`frontend/src/components/profile/ResendVerificationButton.tsx`), shown only when `ProfilePageResponse.user.isEmailVerified` is `false`. That button POSTs to a Next.js proxy at `/api/auth/verify-email/resend`, which forwards the cookies to the backend route.

---

## Rate limiting

slowapi-backed, configured per-route with `@limiter.limit("N/minute")`. Hot endpoints:

- `/users/signup` — 5/min
- `/users/login` — 10/min
- `/users/password-reset/request`, `/password-reset/confirm` — 5/min each
- `/users/verify-email/resend` — 3/min
- `/users/me` (GET) — 60/min

Limits key off client IP via `slowapi.util.get_remote_address`. If the API ever sits behind a proxy without `X-Forwarded-For` rewriting, all traffic will appear to come from the same address and the limits will be effectively global — fix the proxy header config first, do not loosen the limits.

---

## Test plan

There is no automated test suite yet (tracked in [`../todo.md`](../todo.md)). Until pytest lands, run the manual smoke sequence below before any release. Treat each line as a checkbox.

### Auth
- [ ] **Signup happy path.** New email, new username → 201, cookies set, response carries `meta.verification_email = "queued"`, verification email arrives.
- [ ] **Signup rollback.** Kill MongoDB mid-flow (after the user insert, before token issuance — easiest to simulate by raising in `_create_email_verification`). Confirm `_rollback_signup` deletes from `users`, `inventory`, `loadouts`, `wallets`, `notifications`, and `email_verification_tokens`.
- [ ] **Signup with broker down.** Stop the Celery worker / Redis. Signup should still 201; response carries `meta.verification_email = "delayed"` and the user-facing message asks them to request a new link.
- [ ] **Login.** 200, cookies set, "new sign in" email queued.
- [ ] **Refresh.** Wait for access TTL, hit a protected route → 401. POST `/users/refresh` → 200, new pair issued, old access token rejected on next call.
- [ ] **Expired token returns 401.** Manually craft an expired token; protected route returns 401 (not 403).
- [ ] **Tampered token returns 403.** Flip a byte in the signature; protected route returns 403.
- [ ] **Password-reset magic link.** Request → email arrives → confirm with new password → all sessions invalidated, login with new password works.
- [ ] **Email-verification magic link.** Request → email arrives → POST `/users/verify-email` with the token → `is_email_verified` flips to `true`.
- [ ] **Resend verification.** `/users/verify-email/resend` while authenticated as an unverified user issues a new token; calling it on a verified account returns 409.

### Rate limits
- [ ] **Signup 6× in a minute.** 6th call returns 429 with the standard envelope.
- [ ] **Login 11× in a minute.** Same.
- [ ] **Password reset 6× in a minute.** Same.

### Other
- [ ] **`/secrets/me` for a fresh user.** Returns `[]`, not an error.
- [ ] **`COOKIE_SECURE=false` with `ENV=production`.** Process should crash at boot with `RuntimeError("COOKIE_SECURE must be true when ENV=production")` from [`core/config.py`](core/config.py).
- [ ] **CORS preflight.** OPTIONS from an allowed origin returns the matching `Access-Control-Allow-*`; from a disallowed origin returns no CORS headers and the browser blocks.

Append observations and dates to this file (or a sibling `smoke-log.md`) when running through the list.

---

## Deferred work

See [`../todo.md`](../todo.md) for the consolidated backlog. Highlights: RS256 + JWKS migration, pytest suite, Alembic-style migrations, ruff/mypy/pre-commit, and the email-outbox replay worker.
