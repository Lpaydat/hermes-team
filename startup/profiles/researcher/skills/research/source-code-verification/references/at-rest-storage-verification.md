# At-rest storage verification (auth servers / token systems)

A recurring sub-class: "does framework X store secret-at-rest in plaintext or hashed/encrypted?" and "does it cache responses for idempotency?" This recipe covers how to answer that from source, including the migration-history pitfall that bites nearly every auth-server audit.

## The three artifacts you must read (in order)

Reading only the ORM/struct layer is insufficient — it describes in-memory shape, not the physical column. Read in this order:

1. **The SQL migration DDL** (`migrations/*.up.sql`, `src/main/resources/*.sql`) — the ground truth for what bytes land on disk. Column names and types (`TEXT`, `VARCHAR(255)`, `BLOB`, `BYTEA`) tell you plaintext vs opaque. The struct may hash/encrypt *before* binding to the column, and only the migration shows that.
2. **The ORM model / struct** (`models.py`, `entities/*.java`, Go struct with `db:"..."` tags) — confirms the column-to-field binding. A `TextField` / `string` field bound to a column named `token` is plaintext; a field bound to a column named `signature` or `token_hash` is a derived value.
3. **The token-generation function** (`GenerateRefreshToken`, `OAuth2RefreshTokenGenerator`, `crypto.SecureAlphanumeric`) — tells you whether the value is a raw random string (will be plaintext if stored) or a self-authenticating structured token (HMAC-signed, never persisted).

## The migration-history pitfall (THE one that bites)

**A codebase's current `main` branch can hold TWO eras of storage simultaneously.** When a project migrates from plaintext-at-rest to hashed/self-authenticating, the *current* migration set contains BOTH the old plaintext column definition AND the migration that supersedes it. And the application code often still supports both paths during rollout.

Worked example — **Supabase GoTrue** (`7e41f41bd`, 2026-07):
- `migrations/00_init_auth_schema.up.sql:36` defines `"token" varchar(255)` — **plaintext**, indexed directly.
- `migrations/20251007112900_add_session_refresh_token_columns.up.sql` adds `refresh_token_hmac_key text` + `refresh_token_counter bigint` — the v2 replacement.
- `internal/crypto/refresh_tokens.go:46` literally panics: `"crypto.RefreshToken is not meant to be saved in the database"` — explicit design: v2 token is stateless HMAC, never persisted.
- `internal/tokens/service.go` has a branch for legacy `*models.RefreshToken` (plaintext, DB-returned) AND `*crypto.RefreshToken` (re-minted HMAC).

**Lesson:** When auditing "what does X store at rest," always grep the FULL migration history (`ls migrations/`), not just the latest schema. If you see a token-related migration dated significantly after the initial schema, the storage model changed — report BOTH eras and flag which is deprecated. Reporting only the current `main` code (v2) would have missed that the design under review's plaintext-cache pattern *has a real precedent* in the deprecated v1 path.

## Auth-server grep batch

When verifying a token / OAuth server codebase, run these in ONE turn:

```
# Pass 1 — token storage columns and the plaintext/hash decision
pattern: "refresh.{0,20}(hash|sha256|sha-256|bcrypt|argon|plaintext|plain|encrypt|AEAD|cipher)"
# Pass 2 — rotation + reuse-detection machinery
pattern: "refresh.{0,5}(token)?.{0,15}(rotat|reuse)"
# Pass 3 — the refresh handler (where idempotency / caching would live)
pattern: "RefreshToken|refresh_token|createRefreshResponse|PopulateTokenEndpointResponse"
```

Pass 1 tells you the storage decision; pass 2 narrows to the rotation logic; pass 3 finds the handler where you check for response-caching vs re-mint.

## Self-authenticating (HMAC) token pattern — the strong design

The most secure pattern you'll encounter: the token is `base64(version || id || counter || HMAC-signature || checksum)`. The DB stores ONLY the HMAC **key** (and a counter), never the token. Verification is `HMAC(key, received_bytes) == received_signature`.

Recognizing it:
- A `TokenStrategy.RefreshTokenSignature(ctx, token)` method that returns a *substring* of the token (Fosite/Hydra pattern) — the signature IS the DB key.
- A `KeyCipher().Encrypt(ctx, session)` call on the session blob (Hydra `EncryptSessionData`) — optional AEAD on the non-token data.
- An explicit `panic("... not meant to be saved in the database")` on the token type (GoTrue v2).
- A DB column named `*_hmac_key` + a `*_counter` column, with NO `*_token` column.

When you see this, you can assert: **no plaintext token at rest** — only the signing key.

## Answering "does it cache responses for idempotency?"

A design-doc may cache the full `/refresh` JSON response (including the new plaintext token) for grace-window replay. To check whether a framework does the same:

1. Read the refresh handler's **response-population method** (e.g. `PopulateTokenEndpointResponse`, `create_refresh_response`, `createRefreshResponse`).
2. Does it call a **token generator** (`GenerateRefreshToken`, `OAuth2RefreshTokenGenerator.generate`, `crypto.RefreshToken.Encode`) on every call? → it **re-mints** (no cache).
3. Does it read a previously-stored response/token blob and return it verbatim? → it **caches/returns**.

As of 2026-07, **no major framework caches the full refresh response** for idempotency. The re-mint-on-replay pattern is universal among systems with grace windows (Auth0, Cognito, Hydra, GoTrue-v2). The one precedent for returning a stored plaintext token on grace replay (GoTrue v1) was deprecated in favor of re-minting.

## Framework-specific storage at a glance (verified 2026-07-12)

| Framework | Plaintext token at rest? | Lookup key | Replay idempotency |
|---|---|---|---|
| Ory Hydra | No — HMAC signature (SHA-512/384) is the PK | `signature` column | Re-mints fresh pair |
| Keycloak | No — refresh token is a signed JWT; reuse tracked by `reuse_id` claim in client session | JWT signature verification | Re-mints new JWTs |
| Supabase GoTrue v2 | No — HMAC key + counter only; token panics if persisted | HMAC verification | Re-mints same-counter token |
| Supabase GoTrue v1 (deprecated) | **Yes** — `token varchar(255)` | plaintext `token` column | Returns stored plaintext active token |
| Authentik | **Yes** — `TextField`, plaintext `token` lookup | plaintext `token` field | No grace window; revoked → error |
| Spring Authorization Server | **Yes** — `refresh_token_value` BLOB, plaintext `.equals()` | plaintext BLOB | No grace window; re-mints or reuses (`isReuseRefreshTokens`) |
| Django allauth | **Yes** — `token_secret TextField` (client-side; stores external provider tokens) | n/a | n/a (not an auth server) |
| Passport.js | No storage layer | n/a | n/a (client library) |

Closed-source vendors (Auth0, Cognito, Firebase) don't publish their DB schema; tag those findings `[ASSERTED-FROM-DOCS]` (inferred from documented re-mint behavior + JWT claims), vs `[VERIFIED-FROM-SOURCE]` for the open-source frameworks above.
