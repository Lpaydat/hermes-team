# JS/TS Backend Ecosystem Tool Comparison

Domain-specific methodology for "research the standard/must-have tools for a TypeScript/JavaScript backend" or "compare N libraries across the TS/JS backend ecosystem." Companion to `backend-ecosystem-comparison.md`, which covers Rust/Python/Go. This file covers TypeScript/JavaScript specifically — the distinct registry commands, the edge/Cloudflare Workers runtime dimension that Rust/Python/Go don't have, and the bundle-size-decides-on-edge pattern that is unique to the JS frontend+edge world.

## 1. The output shape: same scored table, edge column added

Deliverable shape is the same as `backend-ecosystem-comparison.md` §1 — one table per category with columns: tool, what it does, score (1–10), canonical?, alternatives, pros, cons — **plus one extra column that is critical in the JS/TS backend world: `Runtime fit`** (Node.js / Bun / Deno / Cloudflare Workers / edge-runtime). The single most decisive question in TS backend tool selection is "does it run on Cloudflare Workers / edge?" because the Workers runtime (V8 isolates + Web APIs) is a subset of Node and Bun. A tool that scores 9 for Node may be a 3 for Workers.

## 2. Registry data: npm commands

```sh
# Latest version + publish date for one package
curl -s "https://registry.npmjs.org/$pkg" | python3 -c "
import sys,json; d=json.load(sys.stdin)
l=d['dist-tags']['latest']; print(f'$pkg: latest={l}, published={d[\"time\"].get(l,\"?\")[:10]}')"

# Weekly download count — the canonical adoption signal
curl -s "https://api.npmjs.org/downloads/point/last-week/$pkg" | python3 -c "
import sys,json; d=json.load(sys.stdin); print(f'$pkg: weekly_dl={d[\"downloads\"]}')"
```

**Rate-limit caveat (verified 2026-08):** The npm downloads API (`api.npmjs.org/downloads`) will return errors (empty body / non-JSON) when called in a tight loop with no delay. Add `sleep 1` between calls, or batch a handful and retry the failures individually after a `sleep 3`. The `registry.npmjs.org` metadata endpoint (versions, dates) is more tolerant than the downloads endpoint. When a batch of download-count calls all fail, it's almost always transient — retry, don't abandon the data.

**Go comparison note:** Go has no download stats (module proxy gives version+timestamp only); use GitHub stars + `pushed_at` as the liveness proxy — see `backend-ecosystem-comparison.md` §6.3.

## 3. The decisive dimension: edge/Workers compatibility

Unlike Rust/Python/Go (where the runtime is a single given), TS/JS backends span multiple runtimes, and **the Workers runtime is the constraining one**. A tool that uses Node-specific APIs (`http`, `fs`, `net`, `Buffer` in non-standard ways, `process` globals) will NOT run on Cloudflare Workers, which exposes only Web-standard APIs (`fetch`, `Request`/`Response`, `crypto.subtle`, `Cache`, `FormData`, Web Streams).

| Runtime | APIs | Tool implications |
|---|---|---|
| **Cloudflare Workers** | Web-standard only (V8 isolates) | `ws` (Node `net`) ❌, `socket.io` ❌, `multer`/`formidable` (Node) ❌, `nodemailer` (Node) ❌. Use PartyKit/Durable Objects, native `Request.formData()`, Resend (fetch SDK). |
| **Node.js** | Full Node API | Everything works — the universal fallback. |
| **Bun** | Node API + Web APIs + Bun extensions | Most npm works; some native modules have edge cases. |
| **Deno** | Web-standard + npm: specifier | Increasingly npm-compatible; some packages still awkward. |

**Key pattern: if the deployment target is Cloudflare Workers/edge, filter every tool choice through "is it Web-standard API-based?" first.** Fetch-based SDKs (Resend, Drizzle's HTTP drivers, Better Auth) work on Workers; Node-bound libraries (Nodemailer, ws, multer) do not.

## 4. Interdependency tracking — TS-specific chains

| Pattern | Example | Impact |
|---|---|---|
| **Validation ↔ ORM coupling** | Drizzle ORM has native integrations for Zod, Valibot, TypeBox, ArkType, Effect/Schema — your validation choice and ORM choice share a codegen layer (`drizzle-zod`, `drizzle-valibot`, etc.) | Pick a validation lib Drizzle supports; the pair generates matching schemas from your DB schema |
| **Framework ↔ runtime lock-in** | Elysia is Bun-only; Express/Fastify are Node-only; Hono is runtime-agnostic (Workers/Deno/Bun/Node) | For multi-runtime or edge-first projects, Hono is the only major framework that spans all targets |
| **Realtime ↔ runtime lock-in** | Socket.io/ws are Node-only; PartyKit builds on Cloudflare Durable Objects | Edge realtime → PartyKit; Node realtime → ws; the two are not portable to each other |
| **Bundle size on edge** | Zod (~13KB min) vs Valibot (~1.3KB tree-shaken, "up to 95% smaller") | On Cloudflare Workers, bundle size = cold-start time; Valibot is the edge-optimized choice |
| **Auth architecture coupling** | Better Auth is an embedded TS library (cookie sessions) — runs in your Worker. Logto is a standalone OIDC IdP — any backend validates JWTs. See `auth-library-architecture.md`. | TS-only backend → Better Auth. Polyglot (TS + Rust/Go/Python) → Logto (OIDC, language-agnostic) |

## 5. Scoring rubric (same 1–10, edge context)

Reuse the rubric from `backend-ecosystem-comparison.md` §5, but **score the version in the context of the target runtime**. A tool that is canonical for Node (Express, score 7) may be non-viable for Workers (doesn't run there). State the runtime context in the recommendation:

- "Hono (score 9, edge-native)" not just "Hono (score 9)"
- "ws (score 8, Node-only)" — not "ws (score 8)" with the runtime left implicit

## 6. Verified findings (2026-08-08)

### Validation libraries
| Tool | Weekly downloads | Edge bundle | Score | Verdict |
|---|---|---|---|---|
| **Zod** | 251.7M | ~13KB (monolithic) | 9 | Ecosystem default (Drizzle, tRPC, Hono, React Hook Form all integrate). Best DX. |
| **Valibot** | 16.5M | ~1.3KB (tree-shakeable, "95% smaller than Zod") | 8 | The edge/Workers pick — same API ergonomics, Drizzle supports it. |
| **@sinclair/typebox** | 108.6M | ~20KB | 7 | JSON-Schema-native; bundled by Fastify. High downloads are transitive (Fastify). |
| **ArkType** | 1.36M | ~12KB | 5 | Rising, runtime-perf-focused, not production-proven at scale. |
| **@effect/schema** | 1.09M | ~30KB | 5 | Effect-ecosystem-coupled. |

### Backend frameworks
| Tool | Weekly downloads | Runtime fit | Score | Verdict |
|---|---|---|---|---|
| **Hono** | 56.6M | Workers/Deno/Bun/Node (all) | 9 | Edge-native, first-class Workers template, typed Bindings. The multi-runtime pick. |
| **Express** | 126.7M | Node only | 7 | Largest ecosystem; v5 async-friendly; **not edge-compatible**. |
| **Fastify** | 10.7M | Node only | 7 | Fastest Node framework; JSON-Schema-first; **not edge-compatible**. |
| **Elysia** | 813k | Bun only | 5 | Best type-safety on Bun; Bun-locked (no Workers/Node). |

### Realtime
| Tool | Weekly downloads | Runtime fit | Score | Verdict |
|---|---|---|---|---|
| **PartyKit** (partyserver pkg) | 1.5M | Cloudflare Durable Objects | 9 (edge) | Acquired by Cloudflare Apr 2024 — first-party. The edge realtime pick. |
| **ws** | 248.4M | Node only | 8 (Node) | Universal, lightweight raw WebSocket. 15x socket.io downloads. |
| **socket.io** | 16.9M | Node only | 6 | Rooms/namespaces/reconnect; heavy, Node-only, often unnecessary. |

### Email
| Tool | Weekly downloads | Runtime fit | Score | Verdict |
|---|---|---|---|---|
| **Resend** | 9.4M | All (fetch SDK, Workers-compatible) | 9 | API-first, React Email templating, edge-native. |
| **Nodemailer** | 19.2M | Node only | 7 | Self-hosted SMTP, legacy adoption. **Not edge-compatible.** |

### File upload
No single "standard" — depends on runtime + storage:
- **Edge (Workers/Hono):** native `await c.req.formData()` (Web-standard, no library) for small uploads; **presigned R2/S3 URLs** for large files (client uploads directly — server never handles bytes).
- **Node:** `multer` (Express, 20M/wk) or `formidable` (24M/wk).
- **Always prefer presigned URLs** for large uploads regardless of runtime — keeps the server lightweight.

### ORM: Drizzle (confirmed)
- Native support for Cloudflare D1, Durable Objects, Neon, Vercel Postgres, Supabase, PlanetScale, Turso, all major DBs.
- Native validation integrations: Zod, Valibot, TypeBox, ArkType, Effect/Schema.
- 18M weekly downloads, v1.0 (stable). The edge-first TS ORM.

### Testing: Vitest (confirmed)
- Hono's Workers docs recommend `@cloudflare/vitest-pool-workers` — so Vitest is the standard even for edge testing.

## 7. Pitfalls specific to TS/JS backend research

1. **npm download counts inflate via transitive dependencies.** TypeBox shows 108M/wk but most is Fastify bundling it — not direct adoption. Cross-check with a "who depends on this" check before scoring a library canonical based on downloads alone.

2. **The Workers runtime ≠ Node ≠ Bun.** Always state the target runtime. A recommendation like "use Express" is wrong without the "(Node-only)" caveat when the deployment target is edge. The Workers runtime (V8 isolates + Web APIs subset) silently breaks Node-specific packages at deploy time, not at install time.

3. **"Bundle size" is a first-class scoring axis on edge, not a micro-optimization.** On Cloudflare Workers, cold-start latency is proportional to bundle size. Zod's ~13KB vs Valibot's ~1.3KB is a 10x difference that shows up in real cold-start numbers. In Rust/Python/Go backend research this dimension doesn't exist — don't omit it here.

4. **Acquisitions change the "is it first-party?" answer.** PartyKit was acquired by Cloudflare (Apr 2024) — it's now a Cloudflare product. Resend, Vercel, Neon are venture-backed SaaS. When a tool's ownership changed, note the current owner + date — it affects long-term support risk. (This applies to open-core research too; see `open-core-product-research.md` §8.)

5. **The validation ↔ ORM coupling is bidirectional in TS.** In Python, pydantic is so dominant that FastAPI/SQLModel just assume it. In TS, the validation market is split (Zod/Valibot/TypeBox/ArkType/Effect), so the ORM (Drizzle) had to integrate with ALL of them. When recommending a validation lib for a TS backend, check the ORM's integration list first — it constrains the choice.
