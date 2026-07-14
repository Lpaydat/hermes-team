# OAuth2/OIDC refresh-token rotation — provider data models + stateless verdict

Condensed findings from verifying refresh-token rotation claims against Auth0, Okta, and AWS Cognito docs (2026-07). Use this to short-circuit re-research on auth-architecture questions. **Re-verify against live docs before relying on a number** — provider behavior shifts; this is a starting map, not a frozen spec.

---

## Q1: Provider-by-provider

### Auth0 — token families + reuse detection, opaque-ID storage

**Sources:**
- [Refresh Token Rotation](https://auth0.com/docs/secure/tokens/refresh-tokens/refresh-token-rotation)
- [Management API: Get Refresh Token](https://auth0.com/docs/api/management/v2/refresh-tokens/get-refresh-token) ← data model
- [Online Refresh Tokens](https://auth0.com/docs/secure/tokens/refresh-tokens/online-refresh-tokens/online-refresh-tokens)

- **Reuse detection via token families: YES.** Verbatim: *"the most recently issued refresh token is also immediately invalidated when a previously-used refresh token is sent to the authorization server. This prevents any refresh tokens in the same token family (all refresh tokens descending from the original refresh token issued for the client) from being used."*
- **Stored value: opaque `id`, not the raw token.** The API is keyed by `GET /api/v2/refresh-tokens/{id}`.
- **Per-token server-side record** (from the Get endpoint response schema):
  - `id`, `user_id`, `created_at`, `idle_expires_at`, `expires_at`
  - `device { initial_ip, initial_asn, initial_user_agent, last_ip, last_asn, last_user_agent }`
  - `client_id`, `session_id`
  - `rotating` (boolean), `resource_servers[]`, `refresh_token_metadata{}`, `last_exchanged_at`
- **Conforms to OAuth 2.0 BCP** (explicitly stated).
- **Reuse events are logged** (`ferrt` / failed-exchange family) — surfaceable via log streaming.
- ⚠️ *Whether a hash of the raw token is also stored for lookup is not documented — cannot confirm from primary source.*

### Okta — reuse detection + grace period, chain invalidation

**Source:** [Refresh access tokens and rotate refresh tokens](https://developer.okta.com/docs/guides/refresh-tokens/main/)

- **Reuse detection: YES.** Verbatim: *"If a previously used refresh token is used again with the token request, the authorization server automatically detects the attempted reuse of the refresh token. As a result, Okta immediately invalidates the most recently issued refresh token and all access tokens issued since the user authenticated."*
- **Grace period: 0–60s, default 30.** *"After the refresh token is rotated, the previous token remains valid for the configured amount of time to allow clients to get the new token."*
- **System Log events:** `app.oauth2.as.token.detect_reuse` (custom auth servers), `app.oauth2.token.detect_reuse` (org auth server).
- **Config:** `refresh_token: { rotation_type: "ROTATE" | "STATIC", leeway: <0-60> }` under `settings.oauthClient`.
- **Default per app type:** SPAs default to ROTATE; mobile/web default to STATIC.
- ⚠️ **Stored value (raw vs hash vs id): NOT documented in public guide.** Behavior proves server-side state exists; exact representation not confirmed.

### AWS Cognito — rotation optional (OFF by default); NO reuse detection, NO family revocation

**Sources** (re-verified 2026-07-12 against live pages):
- [Refresh tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-refresh-token.html) — §Refresh token rotation, §Things to know, §Enable refresh token rotation (API)
- [Ending user sessions with token revocation](https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html) — §RevokeToken operation, §Revocation endpoint, §Things to know
- Negative evidence: full-text grep of all Cognito devguide token/revocation/security pages for "reuse" / "family" / "chain" / "theft" = **zero matches.**

> Note: old task URLs like `…/amazon-cognito-user-pools-using-the-sdk-token-handling.html` now 302-redirect to the guide root. Find current pages via the sitemap (`/cognito/latest/developerguide/sitemap.xml`) and download-then-strip — see `doc-extraction-recipes.md` § "Deep-link redirect wall."

- **Rotation: YES but OFF by default**, optional per app-client. Config: `RefreshTokenRotation: { Feature: "ENABLED", RetryGracePeriodSeconds: <0-60> }`. *"With refresh token rotation, your client can invalidate the original refresh token and issue a new refresh token with each token refresh."* The new token is valid for the *remaining duration of the original* token (lifetime does not extend). Security best practice to enable.
- **Reuse detection: NO.** No documented mechanism detects reuse of a rotated-out token and cascades to siblings. This is the single most important Cognito finding and the most common misread — `origin_jti` looks like a family id but is **not** documented as a family-revocation key.
- **Family-based revocation: NO — revocation is per-refresh-token and explicitly does NOT cascade.** Verbatim from the revocation page: *"When you revoke a refresh token, all access tokens that were previously issued by that refresh token become invalid. **The other refresh tokens issued to the user are not affected.**"* And: *"RevokeToken revokes all access tokens for a given refresh token… This operation **doesn't affect any of the user's other refresh tokens** or the ID- and access-token children of those other refresh tokens."* (Cascade reaches only the ACCESS/ID tokens minted *from that refresh token*, never sibling refresh tokens.)
- **Server-side jti tracking — CONFIRMED (but not used for family revocation).** Verbatim: *"After you enable refresh token rotation, new claims are added in JSON web tokens from your user pool. The `origin_jti` and `jti` claims are added to access and ID tokens."* `jti` = unique per-token ID; `origin_jti` = the originating token's jti. These enable per-token revocation, NOT reuse-detection-driven family revocation.
- **Grace period: `RetryGracePeriodSeconds`, up to 60s.** *"To allow for retries for a brief duration, you can also configure a grace period for the original refresh token of up to 60 seconds."* Semantics = **delay before the old token is revoked** (not "suspend breach detection," since there is no breach detection to suspend). Contrast Auth0 `leeway` which explicitly suspends detection for the immediately-previous token.
- **APIs:** `GetTokensFromRefreshToken` (required for rotation mode). `REFRESH_TOKEN_AUTH` flow is **incompatible** with rotation — must disable it when enabling rotation.
- **Global sign-out:** `GlobalSignOut` (user-authorized) / `AdminUserGlobalSignOut` (admin, IAM-authorized) revoke ALL a user's refresh, ID, and access tokens.
- ⚠️ **JWT revocation caveat:** *"revoked tokens will still be valid if they are verified using any JWT library that verifies the signature and expiration of the token."* Classic stateless-access-token revocation gap — revocation only bites if the resource server calls Cognito or checks a revocation list.
- ⚠️ *Whether the raw token or a hash is stored beyond the jti: not documented.*

### Firebase Auth — per-user revocation timestamp, NO token-family reuse detection documented

**Source:** [Manage User Sessions](https://firebase.google.com/docs/auth/admin/manage-sessions)

- **Format: refresh token is NOT a JWT** (the ID token IS a JWT). Verbatim: *"exchanged for a **Firebase ID token (a JWT) and refresh token**"* — refresh token described separately, never called a JWT.
- **Revocation model: per-user `tokensValidAfterTime` timestamp** (not per-token). `revokeRefreshTokens(uid)` sets a timestamp; any token issued before it is rejected. Verbatim: *"Because Firebase ID tokens are **stateless JWTs**, you can determine a token has been revoked only by requesting the token's status from the Firebase Authentication backend. For this reason, performing this check on your server is an expensive operation, requiring an extra network round trip."*
- **Reuse detection via token families: NOT DOCUMENTED.** Firebase does not advertise rotation + reuse detection like Auth0/Okta/Cognito. Its model is revocation-on-demand (admin-initiated or password-reset-triggered), not automatic theft detection.
- **Refresh tokens expire on:** user deletion, user disable, or major account change (password/email update).
- ⚠️ *Whether Google's internal implementation has any silent reuse detection beyond the documented timestamp model: not publicly documented.*

### Keycloak — reuse detection via `revokeRefreshToken`; ⚠️ critical crash-after-commit false-positive bug

**Sources:**
- [Keycloak Server Admin: Sessions](https://www.keycloak.org/docs/latest/server_admin/) — §Offline Session Idle / Max
- [Keycloak issue #49213](https://github.com/keycloak/keycloak/issues/49213) — "Refresh token reuse counter not reverted on transaction rollback, causing permanent session revocation on transient DB failures" (open, May 2026, team/core-protocols, help wanted)
- [Keycloak issue #26434](https://github.com/keycloak/keycloak/issues/26434) — doc enhancement for the "revoke refresh token" feature
- [Keycloak issue #16422](https://github.com/keycloak/keycloak/issues/16422) — per-client rotation config (realm-only currently)

- **Rotation + reuse detection: YES, realm-level setting `revokeRefreshToken=true`.** When enabled, the old refresh token is invalidated on use. `refreshTokenMaxReuse` (default 0) bounds how many times a token may be reused before the session is revoked. This is a *reuse-counter* model, not Auth0's family-cascade model — the counter tracks presentations of the same token.
- **Grace window: NONE documented.** No leeway/overlap-period equivalent. Instead, Keycloak adds an idle-timeout extension window on offline sessions (*"Keycloak adds a window of time to the idle timeout before the session invalidation takes effect"*) — but this is a session-expiry grace, not a replay-tolerance grace for rotation.
- **⚠️ CRITICAL BUG (#49213, production-confirmed):** The per-session reuse counter is incremented in-memory **before** the transaction commits and is **not reverted on rollback** (a `TODO` comment in source since 2017). A transient DB failure (e.g. Postgres failover setting `default_transaction_read_only = on`) that rolls back the request *after* the counter advanced leaves the counter permanently elevated. The next refresh exceeds `refreshTokenMaxReuse` and **permanently revokes the session** with `invalid_grant: Maximum allowed refresh token reuse exceeded`.
- **Real-world impact (verbatim from #49213):** During a Patroni failover window on a production OpenShift cluster, *"684 external-partner offline-refresh-token sessions (738 distinct client IDs) crossed `refreshTokenMaxReuse=1` within 1–2 retries and were **permanently revoked**. **678 of 684 (99.1%)** were revoked through this counter-advancement path."* Recovery required manual out-of-band token reissuance.
- **Why this is the canonical crash-after-commit false-positive evidence:** It is the only primary source documenting the *rate* of false-positive revocations (99.1% of revocations in a real incident were caused by the commit/rollback race, not by actual theft). The proposed fix (defer the counter increment via `enlistAfterCompletion`) mirrors the correct CAS/transactional pattern.
- ⚠️ Realm-level only — no per-client rotation config (issue #16422, open). The `SuppressRefreshTokenRotationExecutor` client policy can disable rotation for specific clients.

### Firebase Auth — NO rotation, NO reuse detection (verified 2026-07-12)

**Sources:**
- [Manage User Sessions](https://firebase.google.com/docs/auth/admin/manage-sessions) — §Revoke refresh tokens, §Detect ID token revocation, §Advanced Security
- [Verify ID Tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens) — §ID Token Payload Claims

- **Rotation: NONE.** No documented feature issues a new refresh token on each refresh or rotates refresh tokens. *"Firebase Authentication sessions are long lived… the refresh token can be used to retrieve new ID tokens. Firebase ID tokens are short lived and last for an hour."* Refresh tokens expire **only** when: user deleted / user disabled / *"a major account change is detected for the user. This includes events like password or email address updates."* Refreshing an ID token does NOT rotate or invalidate the refresh token.
- **Reuse detection: NONE.** The refresh token is a reusable credential — replaying it simply mints more ID tokens; no reuse event triggers revocation. Theft detection is explicitly **delegated to the application**: *"A common security mechanism for detecting token theft is to keep track of request IP address origins… you might revoke a user's token if you detect that the user's IP address suddenly changed geolocation."* Firebase provides NO built-in detector.
- **Server-side state: per-user `tokensValidAfterTime` watermark** (NOT a per-token or per-family record). Revocation = `getAuth().revokeRefreshTokens(uid)`, which advances this single timestamp. The ID token carries `auth_time`; a token is revoked iff its `auth_time` < the user's watermark. One watermark per user, keyed by `uid`.
- **Revocation triggers:** explicit admin `revokeRefreshTokens(uid)`; automatic on user delete/disable; automatic on password reset (*"Password resets also revoke a user's existing tokens; however, the Firebase Authentication backend handles the revocation automatically"*).
- **Grace/concurrency: N/A** — no rotation ⇒ no replay race, and refresh tokens are reusable so concurrent refreshes are normal operation.
- **Cost caveat:** *"Because Firebase ID tokens are stateless JWTs, you can determine a token has been revoked only by requesting the token's status from the Firebase Authentication backend… an expensive operation, requiring an extra network round trip."* Revocation is not enforceable by local JWT verification alone.

---

## Q0: What does the OAuth 2.0 Security BCP (RFC 9700) mandate? — the foundational authority

**Source:** [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.txt) — "Best Current Practice for OAuth 2.0 Security," BCP 240, January 2025. Updates RFCs 6749/6750/6819. The `draft-ietf-oauth-security-topics` draft *became* RFC 9700; draft-28 is substantively identical on refresh-token content.

### Rotation + reuse detection are BCP-mandated for public clients

- **§2.2.2 (Refresh Tokens):** *"Refresh tokens for public clients MUST be sender-constrained or use refresh token rotation as described in Section 4.14."*
- **§4.14.2 (Recommendations):** *"Authorization servers MUST utilize one of these methods to detect refresh token replay by malicious actors for public clients: Sender-constrained refresh tokens … / Refresh token rotation."* — rotation is one of two mandated methods.
- **Rotation definition (§4.14.2):** *"the authorization server issues a new refresh token with every access token refresh response. The previous refresh token is invalidated, but information about the relationship is retained by the authorization server."*

### Reuse detection semantics (§4.14.2)

*"If a refresh token is compromised and subsequently used by both the attacker and the legitimate client, one of them will present an invalidated refresh token, which will inform the authorization server of the breach. The authorization server cannot determine which party submitted the invalid refresh token, but it will revoke the active refresh token. This stops the attack at the cost of forcing the legitimate client to obtain a fresh authorization grant."*

**Key points (all from §4.14.2):**
- Server MUST retain relationship state between invalidated and successor tokens (*"information about the relationship is retained"*).
- On reuse detection, server MUST revoke the active (current) refresh token — not just reject the stale one.
- Server CANNOT identify attacker vs. legitimate client — recovery is always "revoke + force re-auth."
- Implementation note: the grant/family may be encoded in the token itself, but integrity MUST be protected (e.g., signatures).

### The access-token revocation window problem — BCP answer is NOT "use RFC 7009"

- **§4.14 (opening):** refresh tokens *"allow the authorization server to issue access tokens with a short lifetime and reduced scope, thus reducing the potential impact of access token leakage."*
- **§2.2.1 (Access Tokens):** *"Authorization and resource servers SHOULD use mechanisms for sender-constraining access tokens, such as mutual TLS for OAuth 2.0 [RFC8705] or OAuth 2.0 Demonstrating Proof of Possession (DPoP) [RFC9449] … to prevent misuse of stolen and leaked access tokens."*
- **§4.10:** admits sender-constraining may be infeasible (*"Architecture and performance reasons may prevent the use of these measures"*), and offers NO revocation-based fallback.

### ⚠️ RFC 9700 does NOT cite RFC 7009 (Token Revocation) anywhere

Full-text grep of RFC 9700 for "7009" / "Token Revocation" / "RFC 7009" = **zero matches** (normative refs, informative refs, body text). The BCP's refresh-token strategy is built on **rotation + reuse detection + sender-constraining + short access-token lifetimes**, not on RFC 7009 revocation. RFC 7009 §5 (Security Considerations) corroborates this gap:
- *"If the authorization server does not support access token revocation, access tokens will not be immediately invalidated when the corresponding refresh token is revoked."*
- *"This specification in general does not intend to provide countermeasures against token theft and abuse."*

### Normative-force cheat sheet (all from RFC 9700 unless noted)

| Control | Level | § |
|---|---|---|
| Rotation OR sender-constrain (public clients) | MUST | 9700 §2.2.2 |
| Reuse detection (public clients) | MUST | 9700 §4.14.2 |
| Retain relationship state | required (by rotation definition) | 9700 §4.14.2 |
| Revoke active token on reuse | MUST | 9700 §4.14.2 |
| Identify attacker vs legit | CANNOT | 9700 §4.14.2 |
| Sender-constrain access tokens | SHOULD | 9700 §2.2.1 |
| RT inactivity expiry | SHOULD (no fixed value) | 9700 §4.14.2 |
| Auto-revoke on logout/pw change | MAY | 9700 §4.14.2 |
| RT risk-assessment issuance | MUST | 9700 §4.14.2 |
| RT scope/audience binding | MUST | 9700 §4.14.2 |
| RT TLS + storage confidentiality | MUST | 6749 §10.4 |
| RFC 7009 immediate AT invalidation | NOT guaranteed | 7009 §5 |
| RFC 7009 as theft countermeasure | explicitly disclaimed | 7009 §5 |

This BCP evidence is the spec-level foundation; the provider evidence below (Q1–Q5) shows how production systems implement it.

---

## Q2: Can rotation be truly stateless? — NO.

### The logic (why reuse detection mandates storage)

Reuse detection requires answering *"has this token been presented before?"* A self-contained JWT cannot answer this — the client could tamper with any "used" claim, and signature validation alone can't mark a token consumed. Therefore:

- **Rotation alone** (issue new token, stop accepting old) *could* be stateless: sign each refresh JWT with an expiry, accept any valid signature. Provides **zero theft detection.**
- **Reuse detection** requires marking a token consumed → a server-side store keyed by token id/jti/hash. Non-optional.
- **Family revocation** requires tracking the chain → a `family_id` / `origin_jti` per token.

**Minimal viable state for rotation + reuse detection:** `{ token_id/jti, family_id/origin_jti, used/revoked_flag }` per token. You cannot go below this.

### What production systems store (confirmed)

| Provider | Per-token server-side state | Keyed by | Reuse-detection scope |
|----------|-----------------------------|----------|----------------------|
| Auth0 | Full record (id, user, session, device, timestamps, rotating flag, metadata) | opaque `id` | **Family** — reuse revokes the family + grant |
| Okta | Implied by chain-invalidation + detect_reuse log events | undocumented | **Family** — reuse invalidates newest token + all ATs since auth |
| Cognito | `jti` + `origin_jti` + revocation status | `jti` | **None** — no reuse detection; revoking one RT does NOT affect siblings |
| Keycloak | Per-session reuse counter (`refreshTokenMaxReuse`) + session record | session id / token | **Session** — reuse beyond counter revokes the session (⚠️ counter advances on rollback, see #49213) |
| Firebase | Per-user `tokensValidAfterTime` watermark (NOT per-token) | `uid` | **None** — no rotation, no reuse detection |

**Only Auth0, Okta, and Keycloak implement reuse-detection-driven revocation.** Cognito has rotation + jti tracking but NO family/session cascade (the most commonly misread case — `origin_jti` resembles a family id yet is not used for family revocation). Firebase has no rotation at all. **No surveyed production system implements rotation + reuse detection with zero server-side per-token state** — but the *shape* of that state ranges from a single per-user timestamp (Firebase) to a full per-token record (Auth0).

### Verdict (citable)

> Fully-stateless refresh-token rotation with reuse detection is **not possible**. Rotation alone can be stateless; the security value (reuse/family detection) fundamentally requires server-side per-token state.

### Implication for architecture constraints

A common design brief tension (seen in the dc-val-auth council): *"signature-only refresh JWT validation, no lookup"* + *"rotation with reuse detection"* are **directly contradictory.** You must look up the token's jti/id to detect reuse. Resolution that keeps p99 low: a lightweight Redis/dictionary store keyed by `jti` (`GET` is sub-ms, easily inside a <200ms p99 budget). The "stateless" goal can still hold for **access JWTs** (signature-only, short exp); the stateful requirement applies only to the refresh path.

---

## Q4: Admin revocation vs signature-only refresh JWT — signature-only is INCOMPATIBLE with revocation

**Core tension:** A refresh JWT validated by signature+exp alone cannot be distinguished from a valid-but-revoked token, because the signature stays valid and exp hasn't passed. Admin "revoke user" (stop FUTURE refreshes) is therefore impossible without a server-side check on the /refresh path.

### RFC authority

- **RFC 7009 §2.1** (Token Revocation): *"The invalidation takes place immediately, and the token cannot be used again after the revocation."* — implies the server MUST check on subsequent use.
- **RFC 7009 §3** (Implementation Note) names the trade-off explicitly: self-contained (JWT) tokens allow stateless authorization, but *"some (currently non-standardized) backend interaction between the authorization server and the resource server may be used when **immediate** access token revocation is desired."* The alternative escape valve: *"issue **short-lived** access tokens, which can be refreshed at any time using the corresponding refresh tokens."*

### What production systems do (all require a store)

| Provider | Checks a store on /refresh? | What's stored | Verbatim evidence |
|----------|------------------------------|---------------|-------------------|
| **Auth0** | YES | Per-token record keyed by opaque `id`; grant-level revocation cascades to all tokens in the grant | *"The API invalidates the token. The invalidation takes place immediately, and the token cannot be used again after the revocation."* ([Revoke Refresh Tokens](https://auth0.com/docs/secure/tokens/refresh-tokens/revoke-refresh-tokens)) |
| **Okta** | YES | **Blocklist/denylist** (Okta's own word) | *"The authorization server validates the refresh token, checking its validity, expiration, **and whether it has been revoked**."* + *"After the token is revoked, it's **added to a blocklist or denylist** maintained by the authorization server."* ([Token lifecycle](https://developer.okta.com/docs/concepts/token-lifecycles/)) |
| **Cognito** | YES | `jti`/`origin_jti` claims tracked server-side; `EnableTokenRevocation` flag | *"Revoked tokens will still be valid if they are verified using any JWT library that verifies the signature and expiration of the token."* (i.e. Cognito admits signature+exp alone is insufficient) ([Revoking tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html)) |
| **Firebase** | YES | Per-user `tokensValidAfterTime` timestamp | *"Because Firebase ID tokens are **stateless JWTs**, you can determine a token has been revoked only by requesting the token's status from the Firebase Authentication backend."* ([Manage User Sessions](https://firebase.google.com/docs/auth/admin/manage-sessions)) |

### Verdict

> **Signature-only refresh JWT validation is incompatible with admin revocation (R3-class requirements).** Every surveyed production system maintains server-side state and consults it on /refresh. The brief's non-goal ("no per-token allowlist or blocklist") cannot coexist with admin revocation. Minimum viable: a per-user `tokensValidAfterTime` timestamp (Firebase pattern — one row per user, reject if refresh token's `iat` < timestamp) OR a per-token/ family blocklist (Auth0/Okta pattern). The access-token path can remain signature-only (15-min exp is the "short-lived" window RFC 7009 §3 describes).

---

## Q5: Replay race under reuse detection — grace/leeway window is MANDATORY for R2-class requirements

**Core problem:** Reuse detection revokes the token family when a *previously-used* refresh token is re-presented. But legitimate replays happen (network retries, concurrent requests, slow networks). Without a grace window, a legitimate replay kills the user's session and forces re-auth.

### RFC authority

- **RFC 9700 §4.14** (OAuth 2.0 Security BCP): Under rotation, *"The authorization server cannot determine which party submitted the invalid refresh token, but it will revoke the active refresh token. This stops the attack at the cost of **forcing the legitimate client to obtain a fresh authorization grant**."* The BCP does NOT specify a grace period or idempotency mechanism — it accepts session death as the cost.
- **RFC 6749 §10.4**: *"The previous refresh token is **invalidated but retained** by the authorization server."* — retention is the mechanism that enables reuse detection.

### Grace-period comparison (the replay-race fix)

| Provider | Has grace/leeway? | Default | Range | Idempotent within window? | Source |
|----------|-------------------|---------|-------|---------------------------|--------|
| **Auth0** | YES ("Rotation Overlap Period" / `leeway`) | **DISABLED (0s)** | configurable in seconds | YES — old token re-exchanged returns new pair; only the *immediately previous* token accepted, not the second-to-last | [Configure Refresh Token Rotation](https://auth0.com/docs/secure/tokens/refresh-tokens/configure-refresh-token-rotation) |
| **Okta** | YES ("Grace period for token rotation") | **30s** | 0–60s | YES — *"the previous token remains valid for the configured amount of time"* | [Refresh access tokens](https://developer.okta.com/docs/guides/refresh-tokens/main/) |
| **Cognito** | YES ("Refresh token rotation grace period") | (configurable) | up to 60s | YES — *"To allow for retries for a brief duration, you can also configure a grace period for the original refresh token"* | [Refresh tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-refresh-token.html) |
| **Keycloak** | **NO grace window for replay** (only an offline-session idle-timeout extension, which is a different concept) | — | — | NO — reuse counter (`refreshTokenMaxReuse`) tolerates N replays but there is no time-bounded idempotent window | [Server Admin](https://www.keycloak.org/docs/latest/server_admin/) + [#49213](https://github.com/keycloak/keycloak/issues/49213) |
| **Firebase** | N/A — no rotation/reuse detection documented | — | — | — | re-verify |

### Critical caveat: Auth0 ships with leeway DISABLED

Auth0's grace window is off by default (`leeway` parameter not set). Out-of-the-box, Auth0 will kill a legitimate user's session on any replay — including innocent network retries. This is a configuration landmine: teams enabling rotation must explicitly set `leeway` to get replay tolerance.

### Recommended pattern

1. **Grace/leeway window (mandatory):** Allow the immediately-previous token to be exchanged within a short window (10–30s recommended, matching Okta default). Must return the SAME new token pair (idempotent), not a divergent pair — otherwise concurrent requests strand one client.
2. **Client-side single-flight:** Complementary, not a substitute — mobile clients on unreliable networks can't guarantee it.
3. **Idempotency key:** No surveyed provider documents this explicitly; the grace window effectively provides it.

### Verdict

> **Reuse-detection-based family revocation is NOT safe for unreliable networks without a grace period.** R2-class requirements ("system must function if a refresh is replayed") require a grace/leeway window to be compatible with reuse detection. All three rotation-capable providers (Auth0, Okta, Cognito) implement it — but Auth0 ships it disabled by default. The grace window introduces a small (≤60s) window where a stolen token can be used alongside the legitimate one — an explicit security/UX trade-off the architecture must own.

---

## Q6: JWT vs opaque FORMAT for refresh tokens — does the format matter if you need state anyway?

**Question:** Should refresh tokens be JWTs or opaque tokens? (Distinct from Q2's statelessness question — this asks whether the *format itself* offers any benefit given that server-side state is required regardless.)

### RFC 6749 §1.5 — "usually opaque to the client" (closest thing to format guidance)

The core spec describes the refresh token as a string that is **"usually opaque to the client"** — notably using the hedging "usually," not a mandate. The token is defined as "an identifier used to retrieve the authorization information," implying a server-side lookup. Contrast with §1.4 (access tokens), which explicitly offers *both* formats: *"The token may denote an identifier used to retrieve the authorization information **or may self-contain the authorization information** in a verifiable manner."* §1.5 does NOT extend this self-contained option to refresh tokens.

### RFC 6819 §3.1 — the handle-vs-assertion framework (the decisive evidence)

The OAuth threat model defines two token-content representations and explicitly names the revocation trade-off:

- **Handle (opaque):** *"Handles enable simple revocation and do not require cryptographic mechanisms to protect token content from being modified."*
- **Assertion (self-contained/JWT):** *"Assertions can typically be directly validated and used by a resource server without interactions with the authorization server. This results in better performance and scalability in deployments where the issuing and consuming entities reside on different systems. **Implementing token revocation is more difficult with assertions than with handles.**"*

**Key insight:** The self-contained benefit (no server lookup) exists for *resource servers* — but refresh tokens are *"never sent to resource servers"* (RFC 6749 §1.5). The self-contained property's beneficiary does not exist in the refresh-token path.

### RFC 9068 §1 — the JWT token profile is access-token-only

RFC 9068 (the canonical JWT token profile) scopes itself explicitly: *"This specification defines a profile for issuing OAuth 2.0 **access tokens** in JSON Web Token (JWT) format."* There is **no equivalent RFC defining a JWT profile for refresh tokens.** The spec ecosystem has standardized JWTs for access tokens (where the no-lookup benefit applies to resource servers) but has not done so for refresh tokens (where it doesn't).

### RFC 9700 §4.14.2 implementation note — the one place JWT-like formats are permitted for refresh tokens

The BCP implementation note permits encoding grant information into the refresh token via signatures — but frames it as a **lookup optimization, not a stateless-validation mechanism:**

> *"The grant to which a refresh token belongs may be encoded into the refresh token itself. This can enable an authorization server to efficiently determine the grant to which a refresh token belongs, and by extension, all refresh tokens that need to be revoked. Authorization servers MUST ensure the integrity of the refresh token value in this case, for example, using signatures."*

The server still must look up the grant record (for rotation state, reuse detection, revocation). The signature protects the integrity of the encoded `grant_id`; it does not eliminate the DB lookup. This is the **only** residual benefit of a signed refresh token: using the embedded `grant_id` as a lookup key.

### Vendor format confirmations — all surveyed vendors use opaque/non-JWT refresh tokens

| Provider | Refresh token format | Evidence |
|----------|---------------------|----------|
| **Auth0** | Opaque | *"Do not rely on token structure: Treat ORTs as opaque strings. Don't parse or rely on any internal structure—this may change."* ([Online Refresh Tokens](https://auth0.com/docs/secure/tokens/refresh-tokens/online-refresh-tokens/online-refresh-tokens)) |
| **AWS Cognito** | Opaque (jti/origin_jti in access/ID tokens, NOT in refresh token) | *"The `origin_jti` and `jti` claims are added to **access and ID tokens**."* The JWT tracking metadata lives in the access/ID tokens, not the refresh token. ([Refresh tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-refresh-token.html)) |
| **Firebase** | Not a JWT (ID token IS a JWT) | *"exchanged for a **Firebase ID token (a JWT) and refresh token**"* — refresh token described separately, never called a JWT. ([Manage User Sessions](https://firebase.google.com/docs/auth/admin/manage-sessions)) |
| **Okta** | Not documented as JWT | *"**Access and ID tokens are JSON web tokens**"* — refresh token described as *"a special token"* without the JWT label. ([Refresh access tokens](https://developer.okta.com/docs/guides/refresh-tokens/main/)) |
| **Google** | Not documented as JWT | Refresh token returned as separate field; never described as a JWT in OAuth docs. |

### Verdict

> **A JWT refresh token offers no meaningful benefit over an opaque token, given that server-side state is required regardless (rotation, reuse detection, revocation — see Q2, Q4).** The self-contained property's beneficiary (resource servers) does not exist in the refresh-token path. The only residual benefit is using an embedded `grant_id` as a lookup key (per RFC 9700 §4.14.2), a minor optimization an opaque token also achieves by indexing. All surveyed production vendors use opaque/non-JWT refresh tokens. RFC 6819 §3.1 explicitly warns that *"revocation is more difficult with assertions than with handles."* The spec ecosystem (RFC 9068) has standardized JWTs for access tokens only.

---

## Q7: Crash-recovery vs theft disambiguation — the false-positive reuse-alarm problem

**The problem:** A legitimate client crashes *after* the server commits a token rotation (CAS `UPDATE` succeeds), then retries >grace later. The server sees the old (retired) token → reuse detection fires → family revoked → force-logout. This is a **false positive**: a crash, not theft. Distinct from Q5 (which covers the *within-grace* replay race); Q7 covers the *post-grace* crash-recovery case. The question: what mitigations exist, and what is the industry state-of-the-art?

### Q7a: The RFCs state the problem is unsolvable by the server alone

- **RFC 6819 §5.2.2.3** (verbatim): *"Since the authorization server cannot determine whether the attacker or the legitimate client is trying to access, in case of such an access attempt the valid refresh token and the access authorization associated with it are both revoked."*
- **RFC 9700 §4.14.2** (verbatim): *"The authorization server cannot determine which party submitted the invalid refresh token, but it will revoke the active refresh token."*
- **Implication:** The spec framework treats all post-grace replays as theft. There is **no RFC-level guidance for distinguishing crash-recovery from theft.** The server cannot tell them apart by design.

### Q7b: RFC 6819 §5.2.2.3 "clustered environments" caveat — does NOT address client crash-recovery

A common misread. The caveat is about **server-side distributed coordination**, not client crashes:

- Verbatim: *"Note: This measure may cause problems in clustered environments, since usage of the currently valid refresh token must be ensured. In such an environment, other measures might be more appropriate."*
- **"Clustered environments" = a multi-node authorization server** keeping a consistent view of which token is "current" (a distributed-state-coherence / distributed-CAS problem).
- **"usage of the currently valid refresh token must be ensured" = the server cluster must agree on which token is valid** — a consistency concern across AS nodes, not a client-retry concern.
- It is a **Note** (informational), not a normative MUST/SHOULD.
- **The client-crash-after-commit false-positive is a different problem this caveat does not cover.** Do not cite §5.2.2.3 as RFC guidance for crash-recovery; it addresses server clustering.

### Q7c: Two-tier detection (soft-alarm + revoke-on-second-replay) — NO documented production precedent

The proposed pattern: replay inside grace = idempotent; replay outside grace but inside absolute-TTL = soft alarm (log only); revoke only on the SECOND replay outside grace.

- **No surveyed vendor implements "revoke only on second replay."** Auth0/Okta/Cognito/Keycloak all do immediate family/session revoke on the first post-grace replay.
- **It is a novel innovation.** If proposed in a design doc, it requires a custom threat model. The security cost: a real attacker who steals a token gets TWO replays before the family is revoked, roughly doubling the theft-detection window.
- **Closest precedent:** Keycloak's `refreshTokenMaxReuse` counter *allows* N replays before revoking (configurable, default 0) — but this is a reuse-*tolerance* threshold, not a soft-alarm/log-only tier. And as #49213 shows, it produces false positives when the counter advances on rollback.

### Q7d: Client idempotency keys for refresh — standardized generically, NOT applied by any auth framework

- **The standard:** [draft-ietf-httpapi-idempotency-key-header-07](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/) (Oct 2025, HTTPAPI WG, expires April 2026). §2.6: "First time → process normally; Duplicate (retry after completion) → return cached result; Concurrent (retry before completion) → conflict error." §5 Security: mandates a **composite key** (client + idempotency-key) to prevent cross-client data leaks.
- **Canonical production pattern:** Stripe — *"Stripe's idempotency works by saving the resulting status code and body of the first request… Subsequent requests with the same key return the same result."* Keys auto-prune after 24h. ([Stripe Idempotent Requests](https://docs.stripe.com/api/idempotent_requests))
- **Does any auth framework use idempotency keys for refresh? NO.** Auth0, Cognito, Okta, Keycloak, Firebase, Ory, Supertokens — none document an idempotency-key mechanism on the `/token` (refresh) endpoint. The IETF draft is generic for POST/PATCH APIs (payment creation, etc.), not OAuth refresh.
- **Does it help with crash recovery?** *If* the client persists the idempotency key across the crash and retries with the same key, the server returns the cached (already-committed) new token pair, bypassing reuse detection entirely. **But** if the client crashes hard and retries from a saved token without the key, it looks identical to theft. So idempotency keys help *only when the client participates* — they do not solve the problem for a client that lost its in-flight request state.
- **Verdict for design docs:** Idempotency keys are the cleanest *technical* fix but are **unproven in production auth** and require client-side key persistence. Reasonable as future hardening; not a substitute for a grace window.

### Q7e: False-positive rates — only Keycloak documents one (and it's severe)

No vendor publishes an FP rate *by design*. The only primary-source FP data point is Keycloak issue #49213:

| Vendor | Documents FP rate? | Grace window | Notes |
|---|---|---|---|
| **Auth0** | No | `leeway` (disabled by default) | Immediate family revoke outside leeway |
| **Okta** | No | 30s default (0–60s) | Explicitly acknowledges UX impact of reuse detection on poor networks |
| **Cognito** | N/A (no reuse detection) | `RetryGracePeriodSeconds` ≤60s | No false-positive *class* — it doesn't revoke on reuse |
| **Keycloak** | **YES (99.1%)** | None | 678/684 revocations in a real incident were false positives from the commit/rollback race (#49213) |
| **Firebase** | N/A | N/A | No rotation |

**Key takeaway for design docs:** The crash-after-commit false-positive is a *real, severe, production-documented* problem (Keycloak 99.1%). A design that claims reuse detection is "safe" without addressing this scenario is contradicted by the strongest available primary source. The correct framing: the server genuinely cannot distinguish crash from theft (RFC 6819/9700), so the architecture must choose a mitigation (grace window — the industry default; idempotency keys — unproven; two-tier detection — novel) and own the security/UX trade-off explicitly.

### Q7f: Academic guidance

arXiv search for "refresh token security" returns nothing on rotation/reuse-detection design (OAuth security analysis lives in IETF RFCs and USENIX-style protocol-attack papers, not rotation-design research). The RFCs (6819 §5.2.2.3, 9700 §4.14.2) are the authoritative guidance, and they treat the disambiguation as unsolvable by the server. RFC 6819 §5.2.2.5 (Device Identification) is the only RFC-level *heuristic* hint — binding to device identifiers (IMEI, OS-specific) to "detect token theft from a particular device" — but this is a soft signal, not deterministic.
