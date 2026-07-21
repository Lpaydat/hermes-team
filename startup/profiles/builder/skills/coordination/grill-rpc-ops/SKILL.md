---
name: grill-rpc-ops
description: "Operational playbook for running grill RPC sessions (builder↔PO design interviews via file-based RPC). Covers timeout management, session-key capture, and recovery from PO behavioral glitches. Load when running or debugging a self-grill or peer-grill-rpc session."
version: 1.0.0
metadata:
  hermes:
    tags: [coordination, grill, rpc, debugging, operations]
    category: coordination
---

# Grill RPC Ops — running grill sessions that don't fall over

The grill skills (`self-grill`, `peer-grill-rpc`) define the architecture. This skill covers what actually happens when you run a full grill end-to-end: the timeouts you need, the session-key capture step that's missing from the skills, and the PO behavioral glitches you'll hit every session.

Load this BEFORE launching a grill. The architecture skills tell you what to build; this tells you how to operate it without losing turns to preventable failures.

## Pre-flight checklist

Before launching PO, prepare:

1. **State dir:** `/tmp/grill-<slug>/` with `answer.sh` copied in and chmod +x
2. **Clear old state:** `rm -f SESSION.key DONE.flag SUMMARY.md CONTEXT.md` (no QUESTION.md — questions live in PO's output now)
3. **Timeout plan:** Every `answer.sh` call will run in background mode with timeout=900. Foreground terminal maxes at 600s — not enough for some turns.

## The session-key capture step (MISSING from the grill skills)

**This is the #1 cause of silent grill degradation.** PO cannot reliably self-report its hermes session key. It writes `SESSION_ID: 1` (a made-up number) instead of the real key (`20260721_060823_6334fd`). Every `answer.sh` call then resumes a non-existent session, creating a fresh disconnected PO session with zero accumulated context.

**Fix (do this immediately after launching PO):**

```bash
# Launch PO (writes Q1, exits)
HERMES_GRILL_STATE_DIR="$STATE_DIR" hermes -p product-owner \
  --skills grill-with-docs \
  -z "Grill prompt here..." --cli

# Capture the real session key from the most recent CLI session
hermes -p product-owner sessions list | head -2
# Output: ...cli    20260721_060823_6334fd

# Write it to SESSION.key
echo "20260721_060823_6334fd" > "$STATE_DIR/SESSION.key"
```

The patched `answer.sh` (in `shared-skills/self-grill/scripts/answer.sh`) reads SESSION.key before resuming PO.

## Per-turn operation pattern

Each answer-to-PO cycle uses `<Q>` tag extraction — no more QUESTION.md file:

```
1. PO wraps question in <Q>...</Q> tags. answer.sh extracts the inner text.
2. Compose answer (reason as a real builder would)
3. Launch answer.sh in background:
   terminal(background=true, command="answer.sh '...' 2>&1",
            notify_on_complete=true, timeout=900)
4. Poll: process(action="wait", session_id=..., timeout=60)
   - Repeat wait calls until status=exited
5. answer.sh stdout = the extracted question (clean, no PO reasoning).
   - Empty stdout + DONE.flag exists → session complete.
   - answer.sh stderr warning → PO forgot <Q> tags, read raw output from stderr.
```

**Never use 120s timeout** — PO takes 60-200s per turn and 120s kills it mid-response.

## PO behavioral glitches and recovery

### Missing `<Q>` tags (was inline-question glitch, ~40% of turns)

PO sometimes forgets to wrap its question in `<Q>...</Q>` tags. answer.sh prints a warning to stderr and exits 1. The raw output goes to stderr too.

**Recovery:** Read the question from stderr manually. Include in your next answer:
```
"Wrap your next question in <Q> tags so I get the clean version."
```

### Re-asking resolved decisions (~1-2 times per session)

PO re-opens a decision already locked in CONTEXT.md. In testing, D5 was asked twice and D2 was re-asked.

**Recovery:** Do NOT re-answer from scratch. Push back firmly:
```
"Already answered — see D5. Stop re-asking resolved questions.
Lock D5 and ask something genuinely open."
```
Reference the locked decision ID and demand PO move forward.

### Early surrender (anti-surrender failure)

PO declares the grill done after 1-2 questions, says "green light, ship it." This is the grill not working, not the design being resolved.

**Recovery:** Resume PO and say:
```
"No — you're surrendering. The grill says 50+ questions is normal
and you stopped after one. Push through to the next real question."
```

## Provider performance notes

PO uses `glm-5.2` via `zai` provider (product-owner default). Turn times vary wildly:
- **Fast session**: launch ~20s, resume ~60-200s. 8 questions in 45 min.
- **Slow session**: resume >12 min without finishing. Provider congestion suspected.

If a resume takes >10 min, kill and retry — it's a provider issue, not a skill issue. Consider switching PO to a faster provider (deepseek) for speed.

## Answering with --file for long answers

Multi-paragraph answers with template examples should use the `--file` flag to avoid shell escaping issues:

```bash
/tmp/grill-<slug>/answer.sh --file /dev/stdin << 'ANSWER'
Your multi-paragraph answer here...
With quotes, $variables, and backticks safely.
ANSWER
```

## Expected depth

A productive grill session reaches 8-15 questions per PO session and locks 10-14 decisions. PO should:
- Find contradictions in locked decisions (and force revisions)
- Verify technical claims against live data
- Push past the builder's first concession
- Cover: product form, user, data pipeline, edge cases, deployment, sharing, rate limiting

If PO is asking shallow questions or repeating resolved ground, the session may have lost context (check SESSION.key) or needs a fresh launch (outer loop).

## Next migration: graph_* as state store (replaces CONTEXT.md)

CONTEXT.md bloats — 14 decisions produced a 12KB file. The graph_* tools (already in PO's context_graph toolset) solve this structurally:

| Grill concept | Graph tool |
|---------------|------------|
| Grill anchor (open=in progress) | `graph_add_node(type="root", title="grill-{slug}")` |
| Lock a decision | `graph_add_node(type="decision", title="D5: Generation", content="deterministic templates", topics=["grill-{slug}"])` |
| Open a question | `graph_add_node(type="fact", title="Q3: What voice?", content="", topics=["grill-{slug}"])` |
| Resolve a question | `graph_resolve_node(node_id, content="Deadpan-absurdist")` |
| Done check (empty=complete) | `graph_remaining()` — returns ALL open decision/fact nodes |
| Export at end | `graph_pull(topic="grill-{slug}")` → write SUMMARY.md |
| Focused context | `graph_context(node_id)` — node + 1-hop neighbors |
| Link decisions | `graph_add_edge(source_id, target_id, "supersedes")` |

Key advantage: `graph_remaining()` returns ONLY open items — no resolved clutter. A fresh PO session sees what's left without parsing a giant file. Done-check becomes mechanical (empty list = done) instead of PO's subjective DONE.flag.

When migrating: PO prompt changes from "write CONTEXT.md" to "use graph_add_node / graph_resolve_node". Orchestrator checks `graph_remaining()` instead of DONE.flag. No new tools needed — raw graph_* covers it.

## Related skills

- `self-grill` — the user-invoked launcher (shared, global, pinned). Defines the two-loop architecture.
- `peer-grill-rpc` — the detailed architecture reference (builder profile, pinned). Covers the RPC design, anti-surrender rule, and launch recipes.
- `multi-agent-test-isolation` — clean-slate setup for testing cross-agent interactions (pinned).
