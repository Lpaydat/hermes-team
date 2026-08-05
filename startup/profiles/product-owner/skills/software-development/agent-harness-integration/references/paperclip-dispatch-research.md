# Paperclip Dispatch Architecture — Condensed Research

Source: https://github.com/paperclipai/paperclip (cloned to /tmp/paperclip)
Researched: 2026-08-05

## Adapter System (14 built-in types)

```
acpx_local, claude_local, codex_local, cursor, cursor_cloud,
gemini_local, grok_local, hermes_gateway, hermes_local,
openclaw_gateway, opencode_local, pi_local, process, http
```

File: `server/src/adapters/builtin-adapter-types.ts`

Each adapter:
- `adapterType` — string slug (e.g. "hermes_gateway")
- `adapterConfig` — adapter-specific settings
- `agentDefaultsPayload` — secrets/env/config

External adapters loaded as npm packages via `server/src/routes/adapters.ts`.
Registry: `server/src/adapters/registry.js`.

## Hermes Adapter Modes

**hermes_local** — Paperclip spawns `hermes` CLI on same host.
File: `server/src/adapters/` + `ui/src/adapters/hermes-local/`

**hermes_gateway** — Paperclip calls an already-running Hermes API server.
- Config: `apiBaseUrl` (e.g. http://127.0.0.1:8642), `apiKey` (matches API_SERVER_KEY)
- Hermes setup: `API_SERVER_ENABLED=true`, `API_SERVER_KEY=<secret>`, `hermes gateway run --replace --accept-hooks`
- Health check: `GET /api/health`
- Start run: `POST /api/v1/runs`
File: `server/src/adapters/hermes-gateway-doc.ts`

## Heartbeat Model (the "if it can receive a heartbeat, it's hired" pattern)

NOT a simple liveness ping. The heartbeat is the RUN lifecycle:

```
heartbeat interval fires → agent wakes → checks for work →
  if work: runs, produces evidence →
  if no work: skips →
  classifies liveness state
```

### Liveness States (run-liveness.ts)

| State | Meaning | Detection |
|-------|---------|-----------|
| `runnable` | Agent made real progress | Evidence: comments created, files changed, tests run |
| `plan_only` | Agent only talked about doing | Regex: "I'll check", "let me inspect", "next step is" |
| `manager_review` | Agent needs human approval | Regex: "requires approval", "security-sensitive", "production deploy" |
| `blocked_external` | Agent is stuck | Regex: "blocked by", "waiting on credentials/access" |
| `unknown` | Can't classify | Fallback |

### Evidence Signals (RunLivenessEvidenceInput)

```typescript
{
  issueCommentsCreated: number,
  documentRevisionsCreated: number,
  planDocumentRevisionsCreated: number,
  workProductsCreated: number,
  workspaceOperationsCreated: number,
  activityEventsCreated: number,
  toolOrActionEventsCreated: number,
  latestEvidenceAt: Date | null,
}
```

### Regex Classifiers (from run-liveness.ts)

```typescript
PLANNING_ONLY_RE = /\b(?:i(?:'ll| will| am going to|'m going to)|let me|i need to|next(?:,| i will| i'll)?|my next step is|the next step is)\s+(?:first\s+)?(?:inspect|check|review|look|investigate|analy[sz]e|open|read|start|begin|work on|implement|fix|test|update|create|add)\b/i

NEXT_STEPS_RE = /^\s*(?:next steps?|plan)\s*:/im

BLOCKER_RE = /\b(?:blocked|can't proceed|cannot proceed|unable to proceed|waiting on|need(?:s|ed)? .{0,80}\b(?:approval|access|credential|credentials|secret|api key|token|input|clarification)|requires? .{0,80}\b(?:approval|access|credential|credentials|secret|api key|token|input|clarification))\b/i

MANAGER_REVIEW_RE = /\b(?:manager review|human review|manual review|security review|escalate|production deploy|deploy(?:ing)? to production|deploy(?:ing)? to prod|prod deploy|production access|rotate .{0,40}\b(?:secret|key|token)|delete .{0,40}\bproduction|security-sensitive|credentialed operation|budget-sensitive|cost approval|spend approval)\b/i

RUNNABLE_RE = /\b(?:(?:run|rerun|execute)\s+(?:pnpm|npm|yarn|bun|vitest|jest|pytest|cargo|go test|curl|tests?|typecheck|build|lint|package|verification)|(?:inspect|check|review|look|investigate|analy[sz]e|open|read|start|begin|continue|implement|fix|test|update|create|add|write|verify|validate|report)\b)/i
```

## Task Watchdog System

File: `server/src/services/task-watchdogs.ts`

Issue-level watchdogs that monitor subtrees of issues. A watchdog can:
- Snooze (defer evaluation until a time)
- Continue (agent is productive, keep going)
- Dismiss as false positive

Grace window: 15 seconds after issue creation before first evaluation (prevents false positives from assignment race).

## Runtime Config

File: `ui/src/lib/new-agent-runtime-config.ts`

```typescript
{
  heartbeat: {
    enabled: boolean,
    intervalSec: number,
    wakeOnDemand: true,
    skipTimerWhenNoActionableWork: true,
    cooldownSec: 10,
    maxConcurrentRuns: number,
  },
  modelProfiles: {
    cheap: { enabled: boolean, adapterConfig: { model: string } },
  },
}
```

## Key Takeaways for ngin

1. The adapter pattern (trait in Rust) is the right abstraction — Paperclip validates this with 14 types.
2. Heartbeat is more than TTL — it includes productivity classification from agent output.
3. The regex classifiers are a starting point — they can be improved with structured evidence signals.
4. `maxConcurrentRuns` per agent is native (not a bolt-on).
5. Watchdog snooze/dismiss pattern is useful for preventing false-positive kill decisions.
