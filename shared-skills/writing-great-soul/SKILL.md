---
name: writing-great-soul
description: Reference for writing and editing SOUL.md charter files — the vocabulary and principles that keep identity lean and separate procedures into skills.
disable-model-invocation: true
---

A SOUL.md is a **charter** — it declares what an agent _is_, the domain it _owns_, and the boundaries it _keeps_. It is read into context every turn, shaping every interaction regardless of relevance.

A skill wrangles determinism through _process_; a charter through _stance_ — the durable posture, leaving steps to skills.

**Sediment** and **no-op** are borrowed from the `writing-great-skills` glossary, where richer definitions live. Other bolded terms are coined here.

## The line test

Sort each line into one of three buckets:

- _Who I am_ (role, ownership, boundaries, stance) → **keep**.
- _What I do_ (procedure, steps, workflow) → **move to a skill**.
- _What someone else does_ (a teammate's responsibilities) → **route via the team-coordination layer**.

The line between the first two is the line between a charter and an SOP. When a charter inlines a procedure, it becomes a stale **Duplication** — the agent follows the stale copy instead of loading the authoritative one. (For borderline cases — handoff vs. roster, stance vs. rule — the sections below resolve them.)

Two further questions close the remaining gaps:

- **Could this line become stale without me noticing?** If yes, it is a procedure or a roster — move it to a skill or the team-coordination layer. Identity does not drift; procedures do.
- **Is there a skill that already defines this procedure?** If yes, the charter line is a stale duplicate — replace it with an index entry pointing to that skill. If no, author the skill first, then point to it.

## What a charter contains

1. **Role** — one sentence: what this agent _is_ and is _for_.
2. **Ownership** — the domain and boundaries this agent owns.
3. **Handoffs** — what this agent routes outward, stated as its own action ("I route design questions to the architect", "I escalate findings to the owner").
4. **Stance** — a few durable principles that affect decisions. A _posture_, expressed in positive terms.
5. **Skill index** — skill names and trigger conditions only. Present whenever the agent has skills. Each entry is a **context pointer**: it says _when_ to reach for a skill, not _how_ it works.

## The index vs the procedure

The diagnostic: **if a reader could follow the entry without loading the skill, it is a procedure.**

```
Borderline (trim back):
- `code-review` — when reviewing a PR: check the traits, run tests, then comment on standards
- `research` — when answering a question: gather sources, cross-reference, cite

True pointer (keep):
- `code-review` — when reviewing a PR
- `research` — when answering a question against primary sources
```

## Stance

A charter's principles should be few and durable. If you find yourself writing many micro-rules, the underlying principle is missing — find it and collapse.

The test: do the rules share a single underlying concern? Replace them with the principle. If they map to different concerns, keep them separate — each must be stance-level (affects judgment), not protocol-level (affects mechanics).

```
Rules (collapse):
- Always cite the source for each claim
- Link every factual assertion
- Tag every statement with confidence level

Principle (keep):
- Every claim carries its evidence — source, link, confidence.
```

## Failure modes

- **Inlining** — a procedure, step list, or code snippet inside the charter (a hierarchy violation that causes **Duplication**). Cure: move to a skill; leave an index entry.
- **Roster rot** — teammate roster duplicated across identity files. Cure: each charter states only its own ownership.
- **Rule list** — micro-rules that fight each other. Cure: collapse to the underlying principle.
- **Decorative persona** — personality traits with no behavioral effect ("be witty", "love a good metaphor"). If a trait does not shape an output or decision, it is noise. Cure: omit it, or fold it into Stance with a behavioral anchor ("plain-spoken, direct" → affects tone of every response).
- **Compliance dump** — access-control rules, secret-handling procedures, or audit requirements pasted into the charter. These are configuration, not identity — they belong in access-policy files or config. Cure: move to the appropriate config layer; keep only the stance-level security principle (e.g., "treat secrets as untrusted by default").
- **Sediment** — stale lines that settle because adding feels safe. Cure: keep only what shapes current behaviour.
- **No-op** — a line the agent obeys by default. Cure: omit it.

## When you edit a SOUL.md

1. Apply the line test to every sentence — each sentence lands in a bucket.
2. Move procedures to skills, leaving index entries — every "what I do" line has a skill. Moving a procedure may mean authoring a skill, not just linking one.
3. Collapse rule lists to principles — each principle covers a distinct concern.
4. Route rosters to the team-coordination layer, remove sediment, no-ops, decorative persona, and compliance dumps — the charter names only its own role and boundaries.
5. Verify the skill index points to skills that exist — every entry resolves.
