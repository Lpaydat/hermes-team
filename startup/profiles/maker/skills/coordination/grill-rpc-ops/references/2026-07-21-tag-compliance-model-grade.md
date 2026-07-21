# Tag Compliance & Model Grade Findings

## The core problem

The grill RPC protocol requires PO to output structured tags (`<Q>`, `<LOCK>`, `<DONE>`). The `-z` launch prompt instructs PO to use them. In practice:

| Model | `<Q>` compliance | `<LOCK>` compliance | `<DONE>` compliance |
|-------|------------------|---------------------|---------------------|
| glm-5.2 (zai) | ~50% | 0% | ~30% (early surrender) |
| deepseek-v4-flash | untested | untested | untested |

## Why tags fail

1. **Skill context > prompt context.** When tag instructions are in the `-z` prompt, they compete with the loaded skill's conversational style. The `grilling` skill says "ask one question at a time" — natural prose. Tags are unnatural on top of that.

2. **grill-rpc skill (v0.5) moves tags to system context.** This should improve compliance but hasn't been E2E tested yet.

3. **Lower-grade models ignore format instructions under high token load.** When PO is reasoning through complex design questions, output format is the first thing it drops.

## Design principle: the orchestrator handles structure, not PO

All v0.5 design decisions flow from this principle:

- **Decisions:** Builder writes `Lock D{n}: ...` in their answer → answer.sh extracts (not PO)
- **Questions:** answer.sh tries `<Q>` first, falls back to last-paragraph-with-`?` (not PO)
- **State:** answer.sh auto-updates _state.md decision counts (not PO)
- **Branch transitions:** Orchestrator edits _state.md (not PO)

PO's ONLY job is to grill — ask questions, push back, find gaps. Everything structural is handled by the wrapper.

## v0.5 fallback chain

```
<Q> tag present?     → clean extraction (preferred)
       ↓ no
Last paragraph has ? → paragraph extraction (fallback)  
       ↓ no
Dump to stderr       → manual reading (last resort)
```

This chain ensures the grill continues regardless of PO's output format compliance.
