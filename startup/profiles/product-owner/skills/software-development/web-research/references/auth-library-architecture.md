# Auth Library Architecture Types — the decisive axis for compatibility

When comparing auth libraries for compatibility across backend languages, the single most important fact about each library is its **architecture coupling type**. This determines whether the library can work in a given language at all, before you look at features or SDK quality.

## The three architecture types

### 1. Embedded SDK library (language-locked)
The auth logic runs **inside your application process** as a library in a specific language. Sessions are validated in-process, no separate auth server required.

- **Coupling:** Tight. Works only in the library's native language. Non-native backends need a sidecar service in the native language.
- **Token model:** Typically opaque session tokens (random IDs) validated via DB lookup, or signed cookies — **not** standard JWTs by default.
- **Examples:** Better Auth (TypeScript-only), Auth.js (NextAuth) (TypeScript-only), Lucia (deprecated, was TS-only).

**Key verification question:** "Does the library require running in-process in language X?" If yes → any non-X backend needs a sidecar.

### 2. Standalone protocol server / IdP (language-agnostic)
The auth logic runs in a **separate server process** that speaks a standard protocol (OIDC, OAuth 2.1, SAML). Your backend — in any language — validates tokens using standard libraries.

- **Coupling:** None to the backend language. The frontend uses a provider-specific SDK for login flows, but the backend validates tokens with any JWT/OIDC library.
- **Token model:** Standard OIDC JWTs. Validated offline via JWKS discovery (`/.well-known/openid-configuration`). No SDK needed on the backend.
- **Examples:** Logto (OIDC/OAuth 2.1), Keycloak (OIDC), Auth0 (OIDC), Ory (Ory IdP), Zitadel (OIDC).

**Key verification question:** "Does it speak OIDC/OAuth 2.0 as an identity provider?" If yes → any backend language works via standard JWT validation.

### 3. Core server + Backend SDK (SDK-language-only)
A hybrid: a separate Core server handles auth logic and DB, but session **verification** happens in a backend SDK that must run in your application process. The SDK speaks a proprietary protocol to the Core.

- **Coupling:** SDK-dependent. Works only in languages that have a backend SDK. The Core is language-agnostic, but you can't use the Core directly for session verification without the SDK.
- **Token model:** Proprietary session token format. Verification requires the SDK (which may call the Core or verify locally).
- **Examples:** SuperTokens (Core in Java + SDKs for Node/Python/Go/.NET, no Rust), Appwrite (separate server + SDKs).

**Key verification question:** "Is there a backend SDK for my language?" If no SDK → not viable without reverse-engineering the token format.

## Compatibility matrix template

For any (backend-language × frontend-type) pair, the architecture type determines the answer:

| Architecture type | Backend in native language | Backend in other language |
|---|---|---|
| Embedded SDK | ✅ Native | ❌ Needs sidecar in native language |
| Standalone protocol | ✅ Standard JWT validation | ✅ Standard JWT validation |
| Core + SDK | ✅ Native SDK | ❌ If no SDK for that language |

**Logto (standalone protocol) is the only architecture type that works with ALL backend languages natively** — this is why it's the default recommendation for polyglot stacks (especially Rust, which lacks SDKs for most embedded/SDK-based auth libraries).

## Session findings (verified 2026-08-07)

### Better Auth — Type 1 (embedded TS library)
- **Source:** "Better Auth is a framework-agnostic authentication (and authorization) framework for **TypeScript**." — [README](https://github.com/better-auth/better-auth)
- **Session model:** "Better Auth manages session using a **traditional cookie-based session management**." — [session-management.mdx](https://github.com/better-auth/better-auth/blob/main/docs/content/docs/concepts/session-management.mdx)
- **Optional JWT cookie cache:** Supports `strategy: "jwt"` (HS256) for external system compatibility, but it's a *cache* with revocation caveats — not the authoritative session mechanism.
- **Rust backend:** Needs a TS sidecar. Rust calls `GET /api/auth/get-session` HTTP endpoint or validates the JWT cache (with revocation gaps).
- **Expo plugin:** Requires a TS backend — `@better-auth/expo` has `better-auth: workspace:^` as a peerDependency, and the README says "Ensure you have a Better Auth backend set up."

### Logto — Type 2 (standalone OIDC IdP)
- **Source:** "Full support for **OIDC, OAuth 2.1, and SAML**" — [README](https://github.com/logto-io/logto)
- **Architecture:** Separate Docker/Node server. Issues standard OIDC JWTs. Any backend validates via JWKS.
- **Rust backend:** ✅ Validate with `jsonwebtoken` crate. No SDK needed.
- **Python backend:** ✅ Validate with `pyjwt` / `authlib`.

### SuperTokens — Type 3 (Core + SDK)
- **Source:** "Three building blocks: 1) Frontend SDK, 2) Backend SDK, 3) SuperTokens Core" — [supertokens-core README](https://github.com/supertokens/supertokens-core)
- **Session verification:** "The most frequent auth-related operation is session verification — this happens **within the backend SDK (node, python, Go)** without contacting the Java core."
- **Backend SDKs:** Node.js, Python (Flask/Django), Go, ASP.NET. **No Rust SDK** (confirmed via GitHub search: `org:supertokens+rust` → 0 results).
- **Rust backend:** ❌ Not viable without reverse-engineering the token format.

## How to classify an auth library quickly

1. **Check the README/intro docs** — does it say "for TypeScript" / "for Python" / language-specific? → Type 1.
2. **Check for OIDC/OAuth provider capability** — does it mention OIDC, OAuth 2.0/2.1, SAML, or "identity provider"? → Type 2.
3. **Check for a separate Core/server component + SDK list** — does it describe a Core server and list backend SDKs by language? → Type 3.
4. **Verify SDK coverage** — `curl "https://api.github.com/orgs/<vendor>/repos?per_page=100"` and filter for SDK-shaped names. Use `search/repositories?q=org:<vendor>+<language>` to confirm absence (0 results = decisive).
5. **Check peerDependencies** — `curl "https://raw.githubusercontent.com/<vendor>/<repo>/main/packages/<plugin>/package.json"` and inspect `peerDependencies` to determine if a plugin requires the core server.
