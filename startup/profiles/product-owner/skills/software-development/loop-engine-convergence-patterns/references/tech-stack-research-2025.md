# Tech Stack Research — Final Decisions (verified August 2026)

All decisions user-confirmed. Data verified via primary sources (GitHub API, official docs, npm registry, live benchmarks, crate.io, PyPI).

## Languages (user-confirmed priorities)

1. **Rust** — top priority, prefer for everything possible including WASM. Best compiler for AI-generated code.
2. **Python** — prototyping, internal tools, quick builds, AI/ML
3. **TypeScript** — frontend only (React, React Native, Svelte/SvelteKit)
4. **Go** — when Go has a clear ecosystem advantage or tooling edge

Only these 4 languages.

## Tech-preferences.json: current counts

- **111 tools** across 45 categories
- **59 toolkits** (composable groups)
- **23 recipes** (project types)
- All references validated, no duplicates, all broken references caught

## Auth (OSS-first) — DECIDED

**Primary: Better Auth** (MIT, TypeScript-native, self-hosted, unlimited, first-class Expo plugin, passkey/SSO/OIDC).
- Architecture: run auth in TS service, validate JWTs in Python (PyJWT) / Rust (jsonwebtoken).
- **Alternative: Logto** (Apache 2.0, standalone OIDC server, native TS + Python SDKs, Expo support).
- **Python-specific: SuperTokens** (native Python/FastAPI SDK).
- Lucia is DEPRECATED (March 2025). Better Auth is its successor.
- No single auth covers TS + Python + Rust natively. **Logto is the only auth that works with ALL backends** (OIDC JWT — language-agnostic).

**Compatibility matrix:**

| Backend | Better Auth | Logto | SuperTokens |
|---------|-------------|-------|-------------|
| Rust/axum | ⚠ TS sidecar | ✅ OIDC JWT | ❌ No Rust SDK |
| Python/FastAPI | ⚠ TS sidecar | ✅ OIDC JWT | ✅ Native SDK |
| TypeScript | ✅ Native | ✅ Native | ✅ Native |

## ORM — DECIDED: Drizzle

Schema definition IS the type system — no codegen step, no drift, no live DB needed. Single source of truth.

**Drizzle compatibility:**

| Database | Drizzle? |
|----------|----------|
| PostgreSQL, SQLite, MySQL, Neon, Supabase, Cloudflare D1 | ✅ Yes |
| MongoDB, Qdrant, SurrealDB, Redis, all graph DBs | ❌ No — use native drivers |

Benchmarks (run live): Kysely is 4-7x faster at query building but both sub-100µs (DB round-trip dominates). Drizzle wins on type generation (no codegen) and migration tooling (drizzle-kit).

## Linting — DECIDED

- **Rust:** clippy + rustfmt (built-in)
- **Python:** ruff (replaces flake8+black+isort)
- **TypeScript:** **Biome** chosen (Rust-based, 25x faster than ESLint+Prettier, single tool)
- **Go:** golangci-lint + gofmt (built-in)

## Graph Databases — ALL INCLUDED, different use cases

| DB | License | Use case |
|----|---------|----------|
| **GraphQLite** | OSS | Embedded SQLite + Cypher (client-side, local-first, mobile). 97.7% openCypher conformance. Built-in PageRank, Louvain, Dijkstra. |
| **SurrealDB** | BSL 1.1→Apache 2030 | Multi-model (document+graph+vector+kv). Runs embedded (like SQLite), in WASM/browser, or server. SurrealQL. |
| **Neo4j CE** | GPLv3 | Most mature, Cypher, GDS library. CE = single instance, no clustering. GPLv3 SaaS-safe (not AGPL). |
| **Memgraph** | BSL 1.1→Apache 2030 | In-memory, sub-ms multi-hop, GraphRAG. Cypher. RAM-bounded. |
| **FalkorDB** | SSPL-1.0 | GraphBLAS sparse matrix, Redis-compatible. Rust. Ultra-low-latency. |
| **Dgraph** | Apache 2.0 | Native GraphQL API generation, distributed. Safest license. Go. |
| **ArangoDB** | BSL 1.1 | Multi-model (graph+doc+kv). AQL query language. |

**License reality:** "Prefer OSS" means free to use without subscription, not strictly OSI-approved. BSL 1.1 and SSPL allow free production use — restriction is only on reselling as hosted DBaaS.

## Charts — MULTIPLE BY USE CASE

| Use case | Pick | Bundle | Why |
|----------|------|--------|-----|
| General (bar/line/pie) | **Chart.js** | 68KB gzip | Canvas (fast), framework-agnostic, free |
| Power/complex | **Apache ECharts** | 332KB | 100+ chart types, canvas/WebGL, real-time |
| Financial/trading | **Lightweight Charts** | 45KB | Candlestick, professional trading |
| Real-time streaming | **uPlot** | 22KB | Fastest canvas, millions of points |
| Scientific/3D | Plotly.js | 1.36MB | Heavy but 40+ types, 3D |
| React custom | Visx | varies | Low-level D3 + React |
| Graph/network (Obsidian-style) | **Cytoscape.js** | 300KB | What Obsidian actually uses |
| Node editor / flow diagrams | **React Flow** | 24KB | Interactive node-based UIs |
| Geo/maps | deck.gl | large | Large-scale geospatial |

Recharts is 8/10 — popular (shadcn/ui wraps it) but heavy (148KB SVG-based). Chart.js beats it on size and performance.

## Animation — MULTIPLE BY USE CASE

| Tool | Bundle | Best for | Framework |
|------|--------|----------|-----------|
| **Motion** (Framer Motion) | 34KB | React micro-interactions, layout animations, gestures | React-only |
| **anime.js** | 17KB | Cross-framework, SVG morphing, complex timelines | Agnostic |
| **GSAP** | 30KB | Professional timelines, ScrollTrigger, banner ads | Agnostic (premium plugins) |
| **Auto-Animate** | 2KB | Drop-in list animations | React + Svelte + Vue |

Dead: Motion One (merged into `motion` package). Stitches (archived Feb 2025).

## Media Players

| Tool | Bundle | Best for |
|------|--------|----------|
| **Vidstack** | 15KB | Modern, framework-agnostic, HLS/DASH, React/Svelte/Vue |
| **Media Chrome** | 12KB | Headless web components for custom video UIs |
| Video.js | 120KB | Legacy standard, huge plugin ecosystem |

## Validation by Language

| Language | Tool | Score | Notes |
|----------|------|-------|-------|
| TypeScript | **Zod** (primary) + **Valibot** (edge) | 9/10 | Valibot 95% smaller for CF Workers |
| Rust | **serde** (structural) + **validator** crate (semantic) | 10/10 | No single "Zod equivalent" — use both |
| Python | **pydantic v2** | 10/10 | FastAPI depends on it — enough |
| Go | **go-playground/validator** | 8/10 | Closest to canonical |

## TypeScript Backend (new)

| Category | Tool | Score | Notes |
|----------|------|-------|-------|
| Framework | **Hono** | 9/10 | Edge-native, CF Workers first-class. Only TS framework that works on edge+Node+Bun+Deno |
| Runtime | CF Workers (V8 isolates) | 9/10 | Not Node/Bun — own runtime |
| Realtime | **PartyKit** | 8/10 | CF Workers websocket scaling |
| Email | **Resend** | 9/10 | Best DX for transactional email |

Express/Fastify are Node-only and don't work on CF Workers.

## Rust Backend Canonical Crates

| Tool | Category | Canonical? | Notes |
|------|----------|-----------|-------|
| serde + serde_json | Serialization | YES — no alternative | Entire ecosystem depends on it |
| tokio | Async runtime | YES — no alternative | axum hard-depends on it |
| reqwest | HTTP client | YES | Built on hyper/tokio |
| anyhow | Error handling (apps) | YES | For application crates |
| thiserror | Error handling (libs) | YES | For library crates |
| clap | CLI parsing | YES | Feature-rich, derive macros |
| tracing | Logging/tracing | YES | Libraries use log facade, apps use tracing |
| sqlx | Async DB (Postgres) | YES | Pairs natively with axum |
| rusqlite | Embedded SQLite | YES | For local-first apps |

## Python Backend Canonical Packages

| Tool | Category | Canonical? |
|------|----------|-----------|
| pydantic v2 | Data validation | YES — FastAPI built on it |
| httpx | HTTP client | YES — FastAPI TestClient base |
| uvicorn | ASGI server | YES |
| pydantic-settings | Config/env | YES — supersedes python-dotenv |
| SQLAlchemy 2.0 + alembic | ORM + migrations | YES |
| pytest-asyncio | Async testing | YES |

## Go Backend

| Tool | Category | Notes |
|------|----------|-------|
| net/http (1.22+) | HTTP router | Stdlib now sufficient — no framework needed |
| sqlc | DB codegen | Type-safe SQL, no ORM overhead |
| viper | Config | Full config management |

## Frontend State/Data (React)

| Layer | Pick | Notes |
|-------|------|-------|
| Client state | **Zustand** | Simplest+scalable, shadcn-friendly |
| Server state | **TanStack Query** | Don't put server data in Zustand |
| Routing | **React Router v7** | TanStack Router for max type-safety |
| Forms | **React Hook Form + Zod** | shadcn/ui Form IS built on RHF |
| Tables | **TanStack Table** | Headless, all frameworks, pairs with shadcn/ui |
| Toasts | **Sonner** | shadcn/ui wraps Sonner |

Cross-tool: TanStack Query + Zustand = gold-standard server/client state split. shadcn/ui Form component imports react-hook-form — confirmed from source.

## Svelte Frontend

| Layer | Pick | Notes |
|-------|------|-------|
| State | Svelte 5 Runes (`$state`) | Native, 2025 default |
| Server state | SvelteKit `load` | Native |
| Routing | SvelteKit built-in | No decision needed |
| Forms | **sveltekit-superforms + Zod** | De facto standard |
| Toasts | **svelte-sonner** | Sonner port |

## React Native

| Layer | Pick | Notes |
|-------|------|-------|
| Routing | **Expo Router** | File-based, typed, future of RN nav |
| UI | gluestack v5 (shadcn-pattern on NativeWind) | |

## Styling Utilities

cva + clsx + tailwind-merge = the standard combo. **shadcn/ui uses these internally** (confirmed from source code). Chart component wraps Recharts. Toast wraps Sonner. Table is plain styled HTML.

## API Protocols

| Project type | Best protocol | Why |
|---|---|---|
| TS frontend + TS backend | tRPC | Zero codegen, types end-to-end |
| Public API / heterogeneous | REST + OpenAPI | Universal, cacheable, FastAPI native |
| Many clients, different data | GraphQL | Real operational tax |
| Internal services / streaming | gRPC / Connect | Contracts, polyglot, low latency |
| Long-running / async | Temporal / Inngest | Different layer, complements query protocol |

## UI Libraries (Tailwind-aligned)

| Framework | #1 | #2 |
|---|---|---|
| React web | **shadcn/ui** (Radix + Tailwind, copy-paste) | Radix Primitives (headless) |
| React Native | **gluestack v5** (shadcn-pattern on NativeWind) | React Native Reusables |
| Svelte | **shadcn-svelte** (bits-ui + Tailwind) | Skeleton v3 |

## Databases — FULL LIST (18 entries)

PostgreSQL, Neon, SQLite, Supabase, Pocketbase, MongoDB, Qdrant, sqlite-vec, SurrealDB, Dgraph, Neo4j, Memgraph, FalkorDB, GraphQLite, ArangoDB, Cloudflare D1, sqlx (Rust), rusqlite (Rust embedded)

## Additional Tools

- **Tailwind CSS** — foundation for all UI libraries
- **Redis** — caching, pub/sub, rate limiting
- **RabbitMQ** — message broker
- **BullMQ** — TypeScript job queue on Redis
- **Stripe** — payments
- **Cloudflare Queues** — edge message queues
- **Vercel AI SDK + Mastra** — TS AI framework
- **rust-genai** — Rust LLM client
- **pydantic-ai / LangGraph** — Python AI framework
- **Temporal** — durable workflows
- **Inngest** — TS-first durable workflows
- **pi coding agent SDK** — agent SDK

## AI/LLM

- Always prioritize **OpenAI-compatible** providers for portability
- Vector: sqlite-vec (embedded), Qdrant (scale)
- Graph: GraphQLite (embedded), full graph DB list for server-side

## Hosting

- **Cloudflare** — always preferred for serverless (Workers, Pages, D1, Queues, R2)
