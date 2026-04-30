# Guest Sessions

Guest sessions let a user pick up a real account state without committing to
email + password. They get the same access/refresh cookies as a normal user, the
same default inventory/loadout/wallet/notifications, and they can call every
authenticated endpoint that a normal user can — with one exception: **they
cannot change their username**. To rename, they must upgrade to a full account
(see [Upgrading to a real user](#upgrading-to-a-real-user)).

---

## Lifecycle

```
   POST /api/v1/users/guest                     POST /api/v1/users/guest/upgrade
        │                                                  │
        ▼                                                  ▼
  ┌───────────────┐    cookies           ┌────────────────────────────┐
  │ guest user    │  di_access           │ real user                  │
  │ is_guest=true │  di_refresh          │ is_guest=false             │
  │ expires_at=ts │  ────────────────►   │ expires_at=null            │
  └───────────────┘                      │ verification email queued  │
        │                                └────────────────────────────┘
        │ no upgrade before expires_at
        ▼
  cleaned up out-of-band (see "Cleanup")
```

Each guest user document carries:

| Field         | Type    | Notes                                                      |
|---------------|---------|------------------------------------------------------------|
| `is_guest`    | `bool`  | `true` for the lifetime of the guest                       |
| `expires_at`  | `int`   | Unix seconds (UTC). Set to now + `GUEST_USER_TTL_DAYS`     |
| `email`       | string  | Synthetic — `guest-<random>@guest.dead-and-injured.local`  |
| `username`    | string  | Synthetic — `guest-<random>` (locked until upgrade)        |
| `password`    | string  | Random 32-byte secret hashed with bcrypt; never returned   |
| `is_email_verified` | `bool` | `false`                                              |

The `password` is not knowable to the client; guest sessions are reconstructed
purely via the access/refresh cookies set by `POST /users/guest`.

---

## Configuration

| Env var               | Default | Meaning                                          |
|-----------------------|---------|--------------------------------------------------|
| `GUEST_USER_TTL_DAYS` | `7`     | Days until a guest's `expires_at` lapses.       |
| `ACCESS_TOKEN_TTL_DAYS`  | `10` | (Existing.) Per-token TTL — applies to guests.   |
| `REFRESH_TOKEN_TTL_DAYS` | `30` | (Existing.) Per-refresh-token TTL.               |

---

## Endpoints

### `POST /api/v1/users/guest`

Provision a brand-new guest user and return a session.

- **Auth:** none.
- **Rate limit:** 10/minute per client.
- **Request body:** none (empty JSON or no body accepted).
- **Side effects:**
  - Inserts a new `users` document with `is_guest=true`, `expires_at=now + GUEST_USER_TTL_DAYS·86400`.
  - Inserts default `inventory`, `loadouts`, `wallets`, and `notifications` documents (matching a normal signup).
  - Issues a fresh access + refresh token pair and sets them as `di_access` / `di_refresh` HTTP-only cookies on the response.
- **Response:** `201 Created`, `APIResponse[UserOut]`.

```json
{
  "success": true,
  "message": "Guest session created",
  "data": {
    "id": "...",
    "username": "guest-abcdef12",
    "email": "guest-...@guest.dead-and-injured.local",
    "is_guest": true,
    "expires_at": 1714435200,
    "is_email_verified": false,
    "date_created": 1713830400,
    "last_updated": 1713830400
  },
  "meta": {
    "is_guest": "true",
    "expires_at": 1714435200
  },
  "errors": []
}
```

After this call, the browser holds `di_access` + `di_refresh` cookies and can hit every authenticated endpoint that a normal user can.

### `POST /api/v1/users/guest/upgrade`

Convert the currently authenticated guest into a real user.

- **Auth:** required (`di_access` cookie or `Authorization: Bearer <token>`).
- **Rate limit:** 5/minute per client.
- **Request body:**

  ```json
  {
    "email": "real-user@example.com",
    "password": "Hunter12!",
    "username": "optional-new-username"
  }
  ```

  - `email` *(required)*: must not be in use by another account.
  - `password` *(required)*: ≥8 chars, must contain at least one letter and one digit.
  - `username` *(optional)*: 3–32 chars; if provided and different from the current synthetic username, must not already be taken. If omitted the synthetic guest username is preserved.

- **Behaviour:**
  - Refuses (`409 Conflict`) if the authenticated account is already a real user (`is_guest=false`).
  - Refuses (`409 Conflict`) if the email/username is owned by a different user.
  - Sets `is_guest=false`, `expires_at=null`, `is_email_verified=false` on the user.
  - Hashes the new password and stores it.
  - **Invalidates every prior token issued to the user** (`accessToken` + `refreshToken` rows are deleted), then issues a fresh pair so a leaked guest cookie cannot keep acting as the upgraded user.
  - Queues a verification email to the new address (uses the existing Resend pipeline). The response `meta.verification_email` is `"queued"` or `"delayed"` matching the email-broker outcome semantics used elsewhere.
- **Response:** `200 OK`, `APIResponse[UserOut]`. The response also resets `di_access` / `di_refresh` cookies.

```json
{
  "success": true,
  "message": "Account upgraded. Verification email on the way.",
  "data": {
    "id": "...",
    "username": "real-user",
    "email": "real-user@example.com",
    "is_guest": false,
    "expires_at": null,
    "is_email_verified": false
  },
  "meta": {
    "verification_email": "queued"
  },
  "errors": []
}
```

---

## What guests CAN do

Once authenticated with `di_access`, a guest user can call every endpoint that a normal user can, including but not limited to:

- `GET /users/me`, `PATCH /users/me` (except `username`, see below)
- `POST /users/me/profile-media`
- All game / matchmaking / inventory / wallet / leaderboard endpoints
- `POST /users/refresh`, `POST /users/logout`
- `DELETE /users/account`

The token authentication path is identical — there is no per-request "is the
user expired?" gate. Token TTLs apply uniformly. `expires_at` is only consulted
by the cleanup job (see below).

## What guests CANNOT do

### Renaming

`PATCH /users/me` rejects username changes for guests with `403 Forbidden`:

```json
{
  "success": false,
  "message": "Guest accounts cannot change usernames. Upgrade to a full account first.",
  "errors": [{ "code": "http_403", "message": "Guest accounts cannot change usernames. Upgrade to a full account first." }]
}
```

A guest must call `POST /users/guest/upgrade` first; the upgrade payload may itself include the desired final `username`. After upgrade, normal `PATCH /users/me` username updates are unblocked.

Other update fields (`avatar_url`, `bio`, `profile_media_*`) work for guests.

### Email verification

A guest's email is the synthetic `guest-...@guest.dead-and-injured.local`. Trying to "verify" it via `POST /users/verify-email/resend` will queue an email to that synthetic address that nobody can read. There is no UX value in calling that endpoint as a guest — upgrade first, then verify the real address.

---

## Upgrading to a real user

Client flow:

1. `POST /users/guest` once on app open if there are no auth cookies.
2. User plays normally with their guest session.
3. When the user wants to keep their progress / change handle / receive emails, surface a "Create account" form. The form must collect:
   - `email` (required)
   - `password` (required, ≥8 chars, letter + digit)
   - `username` (optional — empty means "keep my guest handle")
4. Send `POST /users/guest/upgrade` with the chosen body. Cookies are refreshed automatically.
5. (Optional) Surface "Verify your email" UX since `is_email_verified=false` after upgrade.

Server-side, the upgrade is a single transactional update — there is no partial state where a user is half-guest, half-real.

---

## Cleanup

There is no scheduled task in this repo that purges stale guests yet. To add one
(recommended in production), schedule a Celery beat job that runs daily and
performs the equivalent of:

```python
async def purge_expired_guests() -> int:
    cutoff = int(time.time())
    cursor = db.users.find({"is_guest": True, "expires_at": {"$lt": cutoff}}, {"_id": 1})
    user_ids = [str(doc["_id"]) async for doc in cursor]
    for user_id in user_ids:
        await delete_all_tokens_with_user_id(userId=user_id)
        await db.users.delete_one({"_id": ObjectId(user_id)})
        await db.inventory.delete_many({"user_id": user_id})
        await db.loadouts.delete_many({"user_id": user_id})
        await db.wallets.delete_many({"user_id": user_id})
        await db.notifications.delete_many({"user_id": user_id})
    return len(user_ids)
```

Until that job exists, expired guests stay in the database but their tokens
will naturally die at `ACCESS_TOKEN_TTL_DAYS` / `REFRESH_TOKEN_TTL_DAYS`,
locking them out from the API even if `expires_at` is in the past.

You can also add a Mongo TTL index on `users.expires_at` if you accept Mongo
deleting just the user row without cascading to inventory/wallet/etc.:

```js
db.users.createIndex({ expires_at: 1 }, { expireAfterSeconds: 0, partialFilterExpression: { is_guest: true } })
```

---

## Security notes

- The synthetic guest password is `secrets.token_urlsafe(32) + "Aa1"`. It satisfies the password complexity validator and is hashed with bcrypt before storage; the cleartext is discarded immediately.
- Guest users start with `is_email_verified=false`. Endpoints gated on `verify_token_email_verified` will refuse a guest. If you want guests on those endpoints, the gate needs to relax for `is_guest=true` users — review on a case-by-case basis.
- Upgrading rotates tokens. Any unrelated client still holding the guest cookies will be 401'd on the next call and must re-auth as the real user.
- The synthetic email is only displayed in `UserOut.email`. Don't log it through normal email pipelines — it routes to a domain we don't own (`guest.dead-and-injured.local`).

---

## Real-user-only operations

This is the canonical list of things the backend will refuse to do (or that
silently no-op) for a guest. Each entry names the endpoint, the reason it's
gated, and the failure shape so frontends can branch UX off the response.

### Hard blocks — server returns an error

These return non-2xx responses for guests. The frontend should pre-check
`user.is_guest === true` and surface an "Upgrade to a full account" CTA before
calling them.

| # | Endpoint | Method | Why it's blocked | Failure for guests |
|---|----------|--------|------------------|--------------------|
| 1 | `/api/v1/users/me` (`username` field) | `PATCH` | Username changes are guest-restricted by design — the only way for a guest to rename is to upgrade. | `403 Forbidden` — *"Guest accounts cannot change usernames. Upgrade to a full account first."* See `services/user_service.py:update_user_by_id`. |
| 2 | `/api/v1/games/matchmaking/queue` | `POST` | Gated by `verify_token_email_verified`. Guests have `is_email_verified=false`. | `403 Forbidden` — *"Email verification required."* See `api/v1/game.py` and `security/auth.py:verify_token_email_verified`. |
| 3 | `/api/v1/matches/multiplayer-round` *(and legacy `/api/v1/matchs/multiplayer-round`)* | `POST` | Same `verify_token_email_verified` gate. | `403 Forbidden` — *"Email verification required."* See `api/v1/match.py`. |

> Any future endpoint that adds `Depends(verify_token_email_verified)` automatically joins this list. Audit it with `grep -rn "verify_token_email_verified" api/`.

### Soft blocks — technically callable, but useless for a guest

These won't 4xx, but they have no useful effect because a guest's identity is
synthetic. The frontend should generally not surface them in the UI for guest
sessions.

| # | Endpoint | Method | What goes wrong |
|---|----------|--------|-----------------|
| 4 | `/api/v1/users/password-reset/request` | `POST` | Sends the reset email to the synthetic `guest-…@guest.dead-and-injured.local` address. The email is queued by Resend, then bounces or is silently dropped — the user can never click the link. |
| 5 | `/api/v1/users/password-reset/confirm` | `POST` | Requires a token from request (4) which the guest never receives. |
| 6 | `/api/v1/users/verify-email/resend` | `POST` | Same problem — the verification email goes to the synthetic address. |
| 7 | `/api/v1/users/verify-email` | `POST` | Requires a token from (6) which never arrives. (Even if it did flip `is_email_verified=true`, the account is still `is_guest=true`, so the username-change block remains.) |
| 8 | `/api/v1/users/login` | `POST` | The guest's cleartext password is `secrets.token_urlsafe(32) + "Aa1"`, generated server-side and discarded immediately. The client never had it, so password login is impossible. The only way back into a guest session is the existing cookies. |
| 9 | `/api/v1/users/google/start` → callback → exchange | mixed | If the user opens Google sign-in from a guest session, the callback matches the Google email *(which is real)* against the `users` collection. The synthetic guest email won't match, so a brand-new real user is created — the guest progress is **abandoned**. To merge, the guest must explicitly call `POST /users/guest/upgrade` *with the email they want* (matching their Google email is fine), then sign in with Google later if they want. |

### Operations that *do* work for guests

For completeness — the gating above is narrow. A guest with valid `di_access` cookies can call all of these without issue:

- `GET /users/me`, `PATCH /users/me` (every field except `username`)
- `POST /users/me/profile-media`
- `POST /users/refresh`, `POST /users/logout`, `DELETE /users/account`
- All read endpoints (`/users`, `/games/*`, `/leaderboard/*`, `/players/*`, `/scores/*`, `/secret/*`, `/app_features/*`)
- All friend / single-player game flows that use plain `verify_token`
- `POST /users/guest/upgrade` (this is the escape hatch into the real-user world)

### Quick frontend mapping

```ts
// Pseudocode for guarding real-user-only buttons in the UI.
function gateForRealUser(user: User, action: () => void) {
  if (user.is_guest) {
    showUpgradeModal({ continueAction: action }); // POST /users/guest/upgrade then run action
    return;
  }
  if (!user.is_email_verified) {
    showVerifyEmailModal();
    return;
  }
  action();
}
```

Apply that gate to: matchmaking queue join, multiplayer round submission, and
the "change username" affordance on the profile page.
