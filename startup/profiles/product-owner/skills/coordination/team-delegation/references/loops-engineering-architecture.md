# Loops Engineering — Architecture & Role Separation

The core principle: **three roles, three context windows, three profiles.** Mixing them
is the sycophancy trap — an agent grading its own work. This file documents the correct
architecture and the crash recovery model.

## Role Summary

| Role | Profile | Does | Never Does | Model |
|------|---------|------|------------|-------|
| **Planner** | `tech-lead` | Contracts work, writes specs, creates kanban cards, reads traces, iterates | Writes code, grades code | GLM 5.2 |
| **Generator** | `developer` | Invokes coding harness (`pi`/`zz`), runs mechanical gates (tests/lint), captures trace | Grades quality, merges, touches contract | GLM 5.2 (governs) → harness model writes code |
| **Verifier** | `verifier` (was `reviewer`) | Executes tests independently, adversarial verification, `/review` static analysis on diff vs contract + bead criteria, merges on pass / creates fix card on fail | Writes code, touches contract | GLM 5.2 |

## The Harness

The harness (`pi` or `zz`) is a **vendor coding agent** that the developer profile wraps as a
subprocess tool. It writes code in an isolated worktree and returns a JSON envelope with
`session_id`, `cost`, and `transcript`. The harness uses its **own model** (separate from the
developer's GLM 5.2 governance model).

- `pi` (v0.80.3) — supports `--provider zai --model glm-4.5-air` (or openrouter, google, etc.)
- `zz`/`zlaude` (Claude Code v2.1.200) — uses Z.AI's Anthropic-compatible endpoint

### `pi` — verified invocation recipe (battle-tested Jul 2026)

```bash
# First attempt (cold start):
timeout --signal=TERM --kill-after=30 <wall_secs> \
  pi --provider zai --model glm-4.5-air \
    -p "<prompt or 'Read PRD.md in this directory'>" \
    --tools read,write,edit,bash,grep,find,ls \
    --mode json

# Fix attempt (warm resume — harness keeps prior memory):
timeout --signal=TERM --kill-after=30 <wall_secs> \
  pi --provider zai --model glm-4.5-air \
    --session <session_id_from_first_attempt> \
    -p "Read FIXES.md. Apply all review findings..." \
    --mode json
```

**Flags that DO NOT EXIST in pi** (the `developer-loop` skill lists them — they are WRONG):
- `--auto-test` → does not exist. Use `--tools` to include `bash` and instruct the harness to run tests in the prompt.
- `--max-turns` → does not exist (only Claude Code has this). **The wall-clock `timeout` wrapper IS the only cap for pi.**

**Session directory for warm resume**: pi stores sessions at `~/.pi/agent/sessions/<cwd-encoded>/`,
NOT `~/.pi/sessions/`. The `--session-dir` flag is NOT needed — pi resolves by cwd automatically.
Run the resume from the **same directory** the original session started in.

**Z.AI provider quirk**: requesting `glm-4.5-air` may get silently routed to `glm-4.7` (visible
in the JSON envelope's `responseModel` field). This is upstream aliasing — check the envelope.

**Built-in pi tools** (for `--tools` allowlist): `read`, `write`, `edit`, `bash`, `grep`, `find`, `ls`.
`grep` and `find` are off by default — include them explicitly when needed.

### Why the harness uses a different (weaker) model

The whole point of role separation is that the Generator is a "dumb" code writer. The Planner
and Verifier are "smart" (GLM 5.2). If the Generator were also GLM 5.2, the verifier (also
GLM 5.2) would be reviewing its own cognitive twin — the adversarial stance weakens. Using a
different model as the Generator ensures genuine independence and produces bugs the verifier
can actually catch, which exercises the failure-fix loop.

## Card Flow (the loop state machine)

```
tech-lead creates dev card (with contract_ref, evals_cmd, acceptance criteria)
  → developer claims card
    → developer invokes harness in worktree (pi/zz with budget caps)
      → harness writes code
    → developer runs mechanical gates (evals_cmd, tests, lint)
    → developer captures trace to ~/vault/traces/<board>/<chain-root>/attempt-N.jsonl
    → developer completes with AC-to-evidence mapping + structured report
  → verifier auto-promotes, claims verification card
    → verifier EXECUTES tests independently (step 1 — dynamic verification)
    → verifier runs /review on diff vs contract.md + bead criteria (step 2 — static analysis)
    → verifier adversarial probing (step 3 — find bugs tests missed)
    → verifier verify-findings pass (step 4 — reproduce every finding)
    → verifier AC CHECKLIST GATE (step 5 — prover-verifier: re-verify each AC with own probe)
    → PASS: verifier merges to main (step 7)
    → FAIL: verifier creates fix card for developer (with findings + resume session_id)
      → developer warm-resumes harness (pi --session <id> / claude -p -r <id>)
      → gates re-run → verifier re-verifies
      → iteration ≥ 3: verifier blocks own card, escalates to tech-lead
```

## Crash Recovery Model

Every role can crash. Recovery depends on **where state lives**:

| Crash Level | State Location | Recovery Mechanism |
|-------------|---------------|-------------------|
| **Harness crash** (pi/zz dies) | Harness session file (`~/.pi/agent/sessions/<cwd-encoded>/` for pi) | Developer warm-resumes: `pi --session <id>` (no `--session-dir` needed — pi resolves by cwd). Run from the **same directory** the session started in. |
| **Developer crash** (Hermes process dies) | Kanban card (status=running, claim lock expires after `dispatch_stale_timeout_seconds`, default 4h) | Dispatcher reclaims → re-dispatches card → new developer reads comment thread + resume harness session from prior metadata |
| **Verifier crash** | Kanban card (status=running) | Same as developer — reclaim + re-dispatch. Verifier re-reads the dev card's completion report + REVIEW-ITERATION comments |
| **Tech-lead crash** | Kanban card + trace ledger | Re-dispatch reads prior comments + trace (`~/vault/traces/`) to continue iteration |

**Key invariant**: The kanban card + trace ledger ARE the state. A process can die, lose its
session, and a fresh process picks up by reading only these.

## Workspace Architecture

- **Project repo (main branch)** — reviewer merges here
- **Kanban worktree (per card)** — `wt/<feature>` branch, isolated. Use `workspace_kind="worktree"`
  for project-linked cards, or `workspace_kind="dir"` with explicit stable path for multi-phase builds.
- **Trace ledger** — `~/vault/traces/<board>/<chain-root-id>/attempt-N.jsonl`. Keyed by the ORIGINAL
  card id so all fix iterations share one directory. The worktree dies; the ledger survives.
- **Kanban board** — shared SQLite DB for all task state, comments, handoffs.

### ⚠️ Workspace continuity (battle-tested)

`scratch` workspaces (the default) are cleaned up after completion/archive. For any multi-phase
build where a later phase needs an earlier phase's files:
- Use `workspace_kind="dir"` pointing to a **stable project directory** outside the kanban
  workspace tree (e.g. `~/projects/my-app/`)
- Never rely on a `scratch` workspace persisting after completion

## Inference Server for Local Models

| Option | Best For | Notes |
|--------|----------|-------|
| **Ollama** | Local dev (recommended) | `pacman -S ollama`, OpenAI-compatible API on `:11434`, auto GPU offload, GGUF format. `pi` uses via `--provider openai --endpoint localhost:11434` |
| **llama.cpp** | Specific quantization needs | `llama-server` for OpenAI-compatible endpoint |
| **vLLM** | Production serving | Overkill for single-user local dev |
| **OpenRouter** | Cloud models, zero install | Gemma 4 26B A4B available (free tier). Uncomment `OPENROUTER_API_KEY` in `.env` |

## Model Discovery Lesson (Jul 2026)

Do NOT assume your knowledge of available models is current. When the user says a model exists
(e.g. "Gemma 4"), **search for it** rather than dismissing:
```bash
# Check OpenRouter's cached model metadata
python3 -c "import json; d=json.load(open('~/.hermes/cache/openrouter_model_metadata.json')); [print(k) for k in d if 'gemma' in k.lower()]"
```
The OpenRouter cache is updated by Hermes at runtime and reflects models that actually exist now,
regardless of when your training data was cut off.

## The Mistake That Produced This File

During Jul 2026 battle-testing, the product-owner agent assigned all build tasks to `tech-lead`
directly. Tech-lead wrote code using its own Hermes tools (write_file, terminal, patch) — it
never delegated to `developer`, and no harness was ever invoked. All "battle tests" only tested
the kanban dispatch mechanism, NOT the loops-engineering architecture. The results were:

1. Tech-lead (Planner) = Generator = same agent → no independent generation
2. Reviewer reviewed GLM 5.2 code generated by GLM 5.2 → no model independence
3. No trace ledger, no structured completion reports, no harness session IDs
4. No failure-fix loop triggered (GLM 5.2 is too strong for the test specs)
5. The entire harness delegation path (`developer` profile + `pi`/`zz`) was untested

**Don't repeat this.** When testing loops engineering, assign build cards to `developer`, not
`tech-lead`. The developer profile's SOUL explicitly says: "The harness writes the code — you
govern the invocation."

## The Verifier Rename (Jul 2026)

The `reviewer` profile was renamed to `verifier` based on academic research:

- **Academic**: 6 of 11 surveyed papers use "verifier" (generator-verifier pattern)
- **ISTQB**: "Review" is a *subset* of verification (static only). The profile does BOTH static review (`/review` skill) AND dynamic verification (runs tests), so "verifier" is more accurate
- **Industry**: Anthropic uses "evaluator-optimizer", LangGraph uses "critic", banking uses "maker-checker" — all describe the same pattern

The `/review` skill (mattpocock) is a **tool** the verifier uses within step 2 of its 8-step protocol, not a role name. It checks git diffs along Standards + Spec axes against `contract.md` and bead acceptance criteria (NOT the PRD — too high-level for per-slice review).

### The AC checklist gate (step 5 — prover-verifier pattern)

The verifier's most important gate. The bead acceptance criteria (PO-written `- [ ]` checkbox items) are the **product contract**. The prover-verifier pattern requires BOTH developer and verifier to engage with each AC:

- **Developer provides proof** (in completion report): maps each AC to a test + output — a **claim**
- **Verifier re-verifies each**: writes its OWN probe (not the developer's test), executes independently — the **fact**
- If developer claims "AC met" but verifier's independent probe fails → **Critical finding**

This catches the classic generator cheat: tests weakened or gamed to pass (visible in the diff). The developer's proof is a claim; the verifier's execution is the fact.

See `dev-workflow-orchestration/references/generator-verifier-research.md` for the full research findings.
