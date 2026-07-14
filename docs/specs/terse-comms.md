# Spec: Terse Agent-to-Agent Reporting (caveman style layer)

Status: ready-for-agent · Owner: operator · Origin: 2026-07-10 caveman evaluation

## Problem Statement

Agent-to-agent messages in the loop are verbose. In a card-based system this cost compounds structurally: card bodies, completion reports, and findings comments are written once but **re-injected into every descendant session on every dispatch** (dev report → verifier → each probe → fix card → re-verify → tech-lead). Worse, parent-result injection truncates each field at a fixed size — a verbose probe report gets clipped before its parked orchestrator ever reads it, which is a correctness problem, not just a token bill. Meanwhile the prose that pads these reports carries no information the loop uses.

## Solution

Adopt the caveman skill (JuliusBrussee) as the **house reporting style for agent-to-agent messages**: terse, filler-free prose with technical content byte-exact — installed as a shared skill and wired into the loop's reporting doctrines. Compression applies to *reports* (completion summaries, findings prose, status comments, intercom chatter); it never applies to *specs* (contracts, ACs, worker mandates, SOULs), whose precision is what makes weak generators succeed. Structured fields are exempt entirely.

## User Stories

1. As the parked verifier, I want probe completion reports that fit untruncated inside parent-result injection, so that my synthesis reads whole verdicts, not clipped ones.
2. As the tech-lead, I want stamped verdicts and evidence digests I can read in one glance, so that acting on PASS/FAIL costs seconds.
3. As a developer agent, I want findings delivered as one-line-per-finding with exact locations and fixes, so that warm-resume fixes start immediately.
4. As any downstream agent, I want code, commands, paths, and error strings byte-exact in every report, so that terseness never corrupts evidence.
5. As the operator, I want structured fields (iteration headers, verdict metadata, AC-to-evidence maps) untouched by compression, so that dashboards and audits keep parsing.
6. As the operator, I want contracts and specs exempt from compression, so that generator success rates don't degrade (detailed specs are proven to be what makes weak models succeed).
7. As the operator, I want lower token burn per loop iteration, so that multi-iteration ventures cost less.
8. As a QA synthesizer, I want worker findings terse but evidence-complete, so that dedup and triage stay fast and lossless.
9. As any agent, I want compression to auto-relax for security warnings, irreversible-action confirmations, and ambiguity-risk sequences, so that safety-critical communication stays explicit.

## Implementation Decisions

- **Install the upstream caveman skill unmodified** into the shared skills location (its prompt is already tokenizer-aware: no invented abbreviations, no arrow glyphs, shortest-decisive-error-line, byte-exact code/errors, built-in Auto-Clarity relaxation). Do not fork; overlay.
- **Wire as a short overlay at the loop's reporting points** — the verifier doctrine's worker mandates and verdict-stamping section, the developer completion-report doctrine, and the QA synthesizer's report section: "report in caveman `full`; exemptions below." Intensity capped at `lite`/`full`; `ultra`/`wenyan` are excluded (instruction-following risk on weak models).
- **Hard exemptions (never compressed):** iteration headers (`REVIEW-ITERATION:` convention), verdict metadata JSON, AC-to-evidence mappings, pasted evidence blocks, contracts/ACs/mandates/SOULs, and anything the skill's own Auto-Clarity rules escalate.
- **Findings format:** adopt the one-line finding shape (location: severity: problem. fix.) for findings comments, keeping the existing header/counter conventions intact.
- **Compress reports, never specs** is the governing rule; it is stated in each overlay rather than centralized, so every affected doctrine is self-contained.
- **Do NOT adopt** the package's subagent presets (in-session subagents are the fragility the loop just removed) or its statusline/stats machinery.

## Testing Decisions

- **Seam: the kanban/beads state machine** — the existing drill pattern. A drill run with the overlay active must show: stamped verdict metadata parses identically (all required keys), iteration headers intact, evidence blocks byte-identical to their sources, and probe completion summaries under the injection truncation threshold.
- **A good test asserts survival of the structured contract, not prose length**: compression level is advisory; field integrity is binding.
- **Prior art:** the fix-loop drill assertions (stamped-verdict checks) extend directly — add field-integrity and summary-length assertions to the same waiters.

## Out of Scope

- Compressing memory files/SOULs/CLAUDE.md (the package offers this; deliberately not adopted now); MCP description-shrinking middleware; the package's subagents; changing what reports *contain* (only how prose is worded); human-facing documents.

## Further Notes

- Evidence for "compress reports, never specs": the drill series showed a fully-specified contract is what let even a weak generator produce correct 22-case output on the first attempt — spec precision is load-bearing; report prose is not.
- The injection-truncation cap that motivates this is a per-field platform constant on parent-result injection; terse summaries are the difference between a parked orchestrator reading a whole verdict and a clipped one.
