# Agent-Security / Repo-Intake Scanning Landscape (captured 2026-07-25)

Reusable competitive landscape for any venture dossier on AI-coding-agent
security, repo-intake scanning, MCP-server scanning, or prompt-injection
defense. Re-verify GitHub star counts and any tool's existence before citing
in a fresh dossier — this field moves fast. Captured during a copycat-feasibility
study of the "Pre-Flight Repo Security Scan (azt-style)" idea.

## The reference product (copycat target)

**agent-zero-trust (azt)** — `github.com/ralfyishere/agent-zero-trust`
- **What it does:** deterministic, offline, single-file (stdlib-only) repo
  intake scanner. Inventories 14+ file classes that can influence an AI coding
  agent (CLAUDE.md, .mcp.json, hooks, .envrc, folderOpen tasks, lifecycle
  scripts, README, CI workflows) and flags injection / execution / exfil
  patterns. Publishes its own false-negative ledger.
- **GitHub (2026-07-25):** 4 stars, 0 forks, 2 open issues, 81 KB, MIT.
- **Show HN (item 48834271):** 1 point.
- **Design choices worth noting:** (1) no-LLM core (bootstrap-paradox argument:
  a scanner vulnerable to the attack it screens is worse than nothing);
  (2) published false-negative ledger (`corpus/misses/`, asserted undetected
  in CI); (3) disclosed its own day-one gate bypass in SECURITY.md.

## Directly comparable OSS tools (HN Algolia sweep, ~6-month window)

Each has a verified HN item ID. All are free / OSS / MIT unless noted.

| Tool | HN item | Pts | What it scans | Distinguishing note |
|------|---------|-----|---------------|---------------------|
| agent-zero-trust (azt) | [48834271](https://news.ycombinator.com/item?id=48834271) | 1 | Repo instruction environment (pre-agent intake) | Reference product; deterministic, stdlib-only |
| Aguara | [47088895](https://news.ycombinator.com/item?id=47088895) | 1 | AI agent skills + MCP servers (Go, AST-based) | 138 rules/15 cats; **scans 31k+ public skills**, public dashboard (watch.aguarascan.com) — the data-asset play |
| Driftcop | [44843841](https://news.ycombinator.com/item?id=44843841) | 4 | MCP "rug pull" / version drift | Sigstore transparency logs; detects tool changes since last approval |
| MCP Security Suite (Mighty) | [44904974](https://news.ycombinator.com/item?id=44904974) | 36 | MCP tool code (prompt injection, exfil, tool shadowing) | Cited Defcon 100% exploit rate; "traditional scanners catch <15%" [vendor-reported] |
| mcp-scan (Invariant/Snyk) | cited in azt README | — | Installed agent/MCP/skill components | The "other side" of the trust boundary from azt; now Snyk Agent Scan |
| Golf Scanner (YC X25) | [47296417](https://news.ycombinator.com/item?id=47296417) | 3 | Discovers every configured MCP server across IDEs | YC-backed; single Go binary |
| Aidevshield | [47270193](https://news.ycombinator.com/item?id=47270193) | 1 | Cursor/Copilot/Cline configs | NPM-audit framing for AI coding tool workflows |
| ClawCare | [47177594](https://news.ycombinator.com/item?id=47177594) | 1 | AI agent skills (scan + runtime guard) | |
| ContextGuard | [45655180](https://news.ycombinator.com/item?id=45655180) | 1 | MCP servers (runtime monitoring) | |
| SkillScan (chitacloud) | [47088895 comment](https://news.ycombinator.com/item?id=47088895) | — | Skills via HTTP API | Agents call it before loading a skill |
| Beelzebub | [45158776](https://news.ycombinator.com/item?id=45158776) | 8 | MCP "canary tools" (honeypot tripwires) | Runtime detection, not static scan; cited the Nx npm AI-assisted supply-chain attack |

## Key framing concept: the "lethal trifecta"

Simon Willison's framework (private data + untrusted content + exfiltration
vector = reliable data theft). The canonical HN threads:
- "My Lethal Trifecta talk" — [44846922](https://news.ycombinator.com/item?id=44846922) (430 pts)
- Original essay — [44289295](https://news.ycombinator.com/item?id=44289295)
- Supabase MCP example — [44493868](https://news.ycombinator.com/item?id=44493868)
- The Economist coverage — [45387155](https://news.ycombinator.com/item?id=45387155)

## Documented incidents / attack vectors (verified this session)

- **MCP mass-forking supply-chain attack** — [47428217](https://news.ycombinator.com/item?id=47428217): org "iflow-mcp" forks hundreds of MCP servers, republishes under @iflow-mcp npm/PyPI scope; familiar name, third-party-controlled code.
- **HTML-comment / hidden-text injection** — [47041889](https://news.ycombinator.com/item?id=47041889): zero-width Unicode (U+200B–U+200F, U+FEFF), bidi overrides, CSS hiding — invisible rendered, visible to model.
- **MCP "rug pull"** — [44843841](https://news.ycombinator.com/item?id=44843841): benign tool auto-updates to malicious.
- **Agent runtime opacity** — [47498251](https://news.ycombinator.com/item?id=47498251): no visibility into what agents read/spawn; [46041660](https://news.ycombinator.com/item?id=46041660) Codex reads ~/.ssh outside CWD.
- **Defcon 100% exploit rate** — [44904974](https://news.ycombinator.com/item?id=44904974) [vendor-reported, unverified].
- **jqwik protestware (May 2026)** — [48319968](https://news.ycombinator.com/item?id=48319968) (67 pts; Ars Technica coverage): maintainer added undisclosed instructions into the jqwik Java property-testing library telling AI coding agents to *delete app output*. Discussion continued at "Protestware for coding agents" [48315440](https://news.ycombinator.com/item?id=48315440) (83 pts). This is the textbook pre-flight-scan use-case: a trusted-looking, widely-used OSS repo contained instructions specifically meant to manipulate the agent.
- **Cursor one-line prompt attack (2025)** — [44768119](https://news.ycombinator.com/item?id=44768119) (CyberScoop coverage): a single prompt-injection line morphed Cursor's agent "into a local shell" with remote-code privileges.
- **Codex linked to malicious NPM** — [48392884](https://news.ycombinator.com/item?id=48392884): "OpenAI Codex tool linked to malicious NPM supply chain attack."

## Copycat-feasibility read

- **10+ comparable OSS tools launched in ~6 months** → saturated field.
- **Reference product flopped** (1 HN point, 4 stars) → no demonstrated demand
  for the *intake-scanner* wedge specifically.
- **Defensible venture ≠ another scanner.** The scanner is a weekend build
  (azt: one stdlib-only file). The moat candidates are: (a) a continuously-
  curated advisory database of agent-supply-chain threats ("GHSA for agent
  instruction surfaces"), (b) drift/provenance verification (the azt gap —
  Driftcop owns part of it), (c) vendor-neutral cross-agent positioning, (d)
  enterprise compliance wrapper (SOC2-aligned intake gate with signed logs).
- **Platform risk:** Snyk already has Agent Scan; Anthropic/GitHub/Cursor may
  bundle intake scanning natively → standalone window may be short.

## Paid incumbent pricing + encroachment (live-verified 2026-07-25)

The OSS landscape above is the long tail. The *paid* incumbents — Snyk,
Socket.dev, GitHub Advanced Security — are the real competitive ceiling for
any standalone agent-security product. Pricing verified live on the vendor
pages this date.

| Vendor | Tiers (verified live) | Unit | Source |
|--------|----------------------|------|--------|
| **Snyk** | Free $0; Team **$25/mo**; Ignite **$1,260/yr**; Enterprise (contact) | per contributing dev/mo | snyk.io/plans |
| **Socket.dev** | Free $0; Team **$25/mo**; Business **$50/mo**; Enterprise (custom) | per dev/mo | socket.dev/pricing |
| **GitHub Advanced Security** | Secret Protection **$19/mo**; Code Security **$30/mo** | per active committer/mo | github.com/security/advanced-security |

**Market-clearing price band: $19–$50 per developer/month.** A new
agent-security product must land within or just below this band. Below $19
reads as "not serious"; above $50 invites replacement by bundled incumbents.

**Encroachment signals (the real window-closer):**
- **Snyk "Evo Agent Security"** is a top-nav product (marked "New" on
  snyk.io) — described as "Secure coding agents, AI-generated code, and AI
  applications." A public incumbent has already staked the territory.
- **Socket.dev Business tier ($50/dev/mo) explicitly lists "Scan GitHub
  Actions and AI models."** Socket has crossed from dependency scanning into
  agent/CI scanning territory.

Both were detected by reading the incumbents' *product navigation and
pricing-tier feature lists*, not just their price tables. See the
"Encroachment detection" technique in the parent SKILL.md.

## AI-coding-agent adoption (for ICP sizing / WHY NOW)

Mass adoption is confirmed via revenue + HN engagement signals:

- **Cursor (Anysphere):** $100M ARR (Oct 2024) → $300M ARR (May 2025) →
  **>$500M ARR at $9.9B valuation** (Jun 2025). Sources: HN 43111746,
  43856745, 44203123 (TechCrunch).
- **Claude Code:** Highest sustained HN engagement of any dev tool 2025–2026.
  Launch thread HN 43163011 (2,127 pts / 963 comments); steganography thread
  HN 48734373 (2,445 pts / 750 comments); ~15 threads over 1,000 pts.
- **OpenAI Codex:** Autonomous deployments (Forbes, HN 47811847); on AWS
  (HN 47937388); in Linear (HN 46152258).

## Prior-art URLs cited by the reference product (NOT independently verified)

The azt README cites these as prior art. Flag for re-verification in any future
dossier — do not cite as live-confirmed without fetching:
- "Mozilla: indirect prompt injection in AI coding agents" (helpnetsecurity.com)
- "Microsoft: securing CI/CD in an agentic world (Claude Code Action case)" (microsoft.com security blog)
- "Cloud Security Alliance: Claude Code GitHub Action prompt-injection note" (labs.cloudsecurityalliance.org)
