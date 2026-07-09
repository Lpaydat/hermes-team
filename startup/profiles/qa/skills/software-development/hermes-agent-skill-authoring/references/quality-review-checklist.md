# Quality Review Checklist — run before committing a skill

Use after YAML validation (Workflow Step 4) and before commit (Step 6). Read every file you wrote — this checklist, the SKILL.md, and every reference file — sentence by sentence. A grep does not substitute for reading.

## Negation

For each file, scan for steering by prohibition: "do not", "don't", "never", "no X", "not Y".

For each hit, ask: is this a hard guardrail on a behavior that cannot be phrased positively?
- **Yes** (e.g. "install profile-scoped, never globally") → keep it, but pair with the positive target.
- **No** → rewrite as the positive target behavior. "Don't test until it's listening" → "Poll until it's listening, then test." "You are NOT running the test suite" → "Write a real consumer script that imports and uses the library."

## Duplication

Check whether the skill restates material already provided every turn by:
- **The SOUL.md** — identity, stance, hard rules. If the SOUL says "you are a skeptical empiricist who never fixes bugs," the skill should not re-explain this.
- **Another loaded skill** — if a build detection table exists in the main SKILL.md, a reference file should point to it, not duplicate it.
- **The universal categories in the parent skill** — if the main SKILL.md has a 10-item edge case list, a type-specific reference's edge case table should contain ONLY cases beyond those 10, with a pointer saying so.

## No-op prose

For each sentence, ask: does this change the agent's behavior versus its default? If deleted, would the agent do anything differently?

Common no-ops:
- Generic advice: "Be thorough", "Push boundaries", "This is where real bugs live"
- Identity restatement: "You are a skeptical empiricist" (the SOUL said this)
- Obvious consequences: "Always clean up — lingering processes cause port conflicts"
- Restating a step's completion criterion in a "Verification Checklist" section

Delete no-ops rather than polishing them.

## Leading word check

Does the skill have a compact concept (a pretrained word) that anchors behavior across all its sections? The word should appear in the description (for invocation) and throughout the body (for execution).

If the skill revolves around an idea but doesn't name it with a single word, find one. Example: "testable assertion" → "claim", with claims getting "verdicts" (proven/disproven/untested).

## Description check

- Starts with "Use when..." or a trigger phrase
- Lists trigger branches, not identity or internal structure
- Does not enumerate sub-topics that the dispatch table already covers
- Under 1024 chars (hard limit)
- Front-loads the leading word

## Reference file check

For each `references/*.md`:
- "Confirm it's alive" / "Evidence" sections contain only type-specific items, not generic restatements of the parent skill's universal tables
- Edge case tables say "beyond the universal categories" and contain only type-specific cases
- No "if X fails, that's a finding" no-ops (the parent skill's step criteria already say this)
- No build table duplication with the parent skill

## Completion

- [ ] Every file read sentence by sentence (not grepped)
- [ ] All negations resolved or justified as hard guardrails
- [ ] No duplication with SOUL, other skills, or within the skill's own files
- [ ] No no-op prose remaining
- [ ] Leading word present in description and throughout body
- [ ] Description is trigger-focused, under 1024 chars
- [ ] Reference files contain only type-specific material
