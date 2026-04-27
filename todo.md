# Backend TODO

Tracks gaps and corrections needed so the FastAPI backend supports the
existing frontend (`/play`, `/game`, `/puzzles`, `/learn`, `/practice`,
`/social`, `/profile`).

---

## A. Critical Corrections (existing endpoints)

- [ ] **Protect Secrets endpoint** — `api/v1/secret.py` exposes all secrets without auth. Restrict to admin or remove the public list route entirely (game answers leak).
- [ ] **Protect Scores / Players / Leaderboard list routes** — currently no JWT (`api/v1/scores.py`, `api/v1/players.py`, `api/v1/leaderboard.py`). At minimum require auth on `/me`-style reads; rate-limit anonymous leaderboard.
- [ ] **Fix scoring logic in `services/match_service.py`** — when one player wins, the loser is also recorded as `MatchResult.win` (lines ~72, ~100, ~133). Loser must be `MatchResult.loss`.
- [ ] **Enforce turn alternation** — same player can submit two guesses in a row. Validate `last_match.player_id != current_player_id` before accepting a guess (`services/match_service.py:52-114`).
- [ ] **Fix typos in route paths** (breaking change — coordinate with frontend):
  - `/api/v1/matchs` → `/api/v1/matches`
  - `/api/v1/scoress` → `/api/v1/scores`
  - `POST /api/v1/users/refesh` → `/api/v1/users/refresh`
- [ ] **CORS** — `main.py` uses `allow_origins=["*"]`. Replace with explicit Next.js origin list (`http://localhost:3000`, prod domain) and `allow_credentials=True` for cookie auth.
- [ ] **Game expiry job** — status `expired` is defined but never set. Add a periodic task (or lazy check on read) to expire stale `waiting`/`started` games.
- [ ] **Wire email service** — `services/email_service.py` exists but is never called. Hook into signup (verification) and login (new-signin alert).

## B. Missing Auth Features

- [ ] `POST /api/v1/users/verify-email` — confirm signup token.
- [ ] `POST /api/v1/users/password-reset/request` and `/confirm` — uses existing OTP template.
- [ ] `POST /api/v1/users/logout` — invalidate access + refresh tokens server-side.
- [ ] `PATCH /api/v1/users/me` — update username, avatar, bio (Profile page edit button).

## C. Missing Game Modes

- [ ] **Single-player vs Bot** (`/play/bot`) — `GameType.SinglePlayer` exists in schema but no endpoint. Need:
  - `POST /api/v1/games/single` → creates bot game, server generates secret
  - `POST /api/v1/games/single/{id}/guess` → returns dead/injured (server-authoritative)
- [ ] **Local pass-and-play** (`/play/local`) — accept two secrets from one client; no auth on opponent guesses.
- [ ] **Friend challenge** (`/play/friend`) — see Social section.
- [ ] **Server-authoritative secret generation** — currently the frontend calls `generateSecret()` in `lib/game.ts`. Move to backend; never send secret to client until game ends.
- [ ] **Server-authoritative guess evaluation** — frontend's `evaluateGuess()` must be replaced by an API call. Backend already does this in `Player` (schemas/imports.py:64-95) — expose it for single-player.

## D. Daily Puzzles (`/puzzles` page)

- [ ] `GET /api/v1/puzzles/daily` — today's puzzle (deterministic per-day seed).
- [ ] `GET /api/v1/puzzles?difficulty=&limit=` — puzzle catalog.
- [ ] `POST /api/v1/puzzles/{id}/attempt` — submit guess, returns dead/injured.
- [ ] `GET /api/v1/puzzles/me/progress` — solved set, weekly progress, puzzle rating, streak.
- [ ] New collection: `puzzles`, `puzzle_attempts`.

## E. Learn / Curriculum (`/learn` page)

- [ ] `GET /api/v1/curriculum` — chapters + lesson list + per-user status (done/current/locked).
- [ ] `GET /api/v1/curriculum/{chapterId}/lessons/{lessonId}` — lesson content.
- [ ] `POST /api/v1/curriculum/{chapterId}/lessons/{lessonId}/complete`.
- [ ] New collection: `curriculum` (static seed) + `curriculum_progress` (per user).

## F. Practice Modes (`/practice` page)

- [ ] `POST /api/v1/practice/session` — body: `{ length, allow_duplicates, unlimited_attempts, hints_enabled, powerup_test }`. Returns session id + secret-less game.
- [ ] `POST /api/v1/practice/session/{id}/guess` — returns dead/injured + optional hint.
- [ ] Practice sessions should NOT affect rating or leaderboard.

## G. Power-ups & Inventory (`/profile`, in-game)

- [ ] `GET /api/v1/users/me/inventory` — list owned power-ups with counts (15 ids defined in `frontend/src/lib/powerups.ts`).
- [ ] `POST /api/v1/users/me/loadout` — save equipped loadout (max N slots).
- [ ] `POST /api/v1/matches/{id}/powerup` — consume a power-up mid-game; server applies effect.
- [ ] New collections: `inventory`, `loadouts`. Seed initial counts on signup.

## H. Social / Friends (`/social` page)

- [ ] `GET /api/v1/friends` — friends list with online status.
- [ ] `POST /api/v1/friends/request` — by username.
- [ ] `POST /api/v1/friends/request/{id}/accept` and `/reject`.
- [ ] `DELETE /api/v1/friends/{id}`.
- [ ] `POST /api/v1/friends/{id}/challenge` — creates a private game and notifies friend.
- [ ] Online presence: heartbeat endpoint or WS pings.
- [ ] New collections: `friendships`, `friend_requests`, `presence`.

## I. Profile & Stats (`/profile` page)

- [ ] `GET /api/v1/users/me/profile` — aggregate: rating, tier, join date, bio, avatar.
- [ ] `GET /api/v1/users/me/stats` — wins, losses, win-rate, average dead/injured, streak, coins.
- [ ] `GET /api/v1/users/me/matches?limit=&offset=` — recent match history with opponent + result + rating delta.
- [ ] `GET /api/v1/users/me/achievements` — unlocked badges.

## J. Leaderboard (`/social` Leaderboard tab, `/play` rating strip)

- [ ] Add a leaderboard *computation* service — current code only has CRUD on a `leaderboards` collection but nothing populates it. Recompute on match completion (or scheduled).
- [ ] `GET /api/v1/leaderboard/global?limit=&offset=` — paginated ranked list.
- [ ] `GET /api/v1/leaderboard/me` — current user's rank + neighbours.
- [ ] Implement an Elo (or Glicko) rating update on game completion.

## K. Realtime (multiplayer)

- [ ] Replace polling with **SSE** or **WebSocket** for match state changes (TODO already present at `api/v1/game.py:109`).
- [ ] Endpoint suggestion: `GET /api/v1/matches/{id}/stream` (SSE) emitting `guess`, `turn`, `end` events.

## L. Hardening

- [ ] Rate-limit auth + guess endpoints (slowapi or similar).
- [ ] Input validation on all guess payloads (length, digit range, duplicates rule per game).
- [ ] Structured error responses using existing `APIResponse` wrapper consistently.
- [ ] Add `/healthz` and `/readyz` for the Next.js host to probe.

---

**Priority order for Next.js integration MVP:** A (corrections) → B (auth) → C (single-player + server-authoritative scoring) → I (profile/stats) → J (leaderboard compute) → H (friends) → D/E/F/G → K (realtime).
