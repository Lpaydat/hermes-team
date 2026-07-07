# Software Engineering V&V (Verification, Validation, Review) → Agent Loops

Source: Web research session (Jul 2026). Formal definitions gathered from
IEEE-STD-610, CMMI, ISTQB, INCOSE, and Boehm, via Wikipedia articles on
"Software verification and validation," "Shift-left testing," "Continuous
testing," and "V-model (software development)."

This reference is the **software/systems-engineering side** of verification.
Its companion, `references/ai-agent-verification-terminology.md`, covers the
**AI-agent side** (verifier/critic/reviewer/evaluator terminology, academic
papers, framework comparison). Read both for the full picture: classical SE
gives you the *definitions and the V-model*; the AI-agent literature gives
you *how living agent systems implement the same roles today*.

---

## 1. Formal Definitions (Three Standards Bodies)

### 1.1 IEEE-STD-610 (via CMMI)

> **Verification:** "The process of evaluating software to determine whether
> the products of a given development phase satisfy the conditions imposed at
> the start of that phase."

> **Validation:** "The process of evaluating software during or at the end of
> the development process to determine whether it satisfies specified
> requirements."

**Key distinction:** Verification is *phase-gate* checking (does output
match its input spec?). Validation is *end-product* checking (does the whole
thing satisfy requirements?).

### 1.2 Boehm's Classic Distinction (the mnemonic everyone cites)

- **Verification**: "Are we building the product right?"
- **Validation**: "Are we building the right product?"

Barry Boehm, 1979. "Building the product right" = specs are correctly
implemented. "Building the right product" = refers back to the user's actual
needs.

### 1.3 ISTQB (software testing profession's standard vocabulary)

- **Verification**: "Confirmation by examination and through provision of
  objective evidence that specified requirements have been fulfilled."
  (Static — the software is NOT running. Reviews, inspections, static
  analysis.)
- **Validation**: "Confirmation by examination and through provision of
  objective evidence that the requirements for a specific intended use or
  application have been fulfilled." (Dynamic — the software IS running.)

ISTQB classifies testing into:
- **Static testing** → verification without executing code (reviews, static
  analysis). **This is where Review formally sits** — as a *technique within*
  verification, not a peer of V&V.
- **Dynamic testing** → verification/validation *by executing the software*.

**Review types (ISTQB):** informal review, walkthrough, technical review,
inspection.

### 1.4 INCOSE / Systems Engineering

In the systems-engineering V-Model:
- Left side of the V = **definition/decomposition** (requirements analysis →
  system design → architecture design → module design).
- Right side = **integration & validation** (unit testing → integration
  testing → system testing → user acceptance testing).

- **Verification** = "Did we build the system right?" Each ascending level of
  the right side checks the product against the corresponding left-side
  specification.
- **Validation** = the top of the V (UAT): "Did we build the right system?"
  Checked against original user requirements and stakeholder needs.

---

## 2. The Three-Term Hierarchy

| Term | Question | When (SDLC) | Artifact examined | Running? |
|------|----------|-------------|-------------------|----------|
| **Review** | Is this work product internally consistent, complete, defect-free? | Every phase (it's a *technique*) | Documents, code, models | No (static) |
| **Verify** | Does this output correctly implement its input specification? | Phase-by-phase (gate checks) | Intermediate artifacts vs their specs | Usually no; sometimes yes (unit tests) |
| **Validate** | Does the finished product meet the real user/stakeholder need? | End of cycle / each release | The running system vs user needs | Yes (dynamic — must execute) |

**Hierarchy:** Review ⊂ Verification (review is one technique within the
broader verification activity). Verification + Validation = V&V (the two
complementary halves of quality assurance).

---

## 3. Shift-Left Verification

**Shift-left testing** (Larry Smith, *Dr. Dobb's Journal*, Sept 2001):
testing/verification performed **earlier in the lifecycle** — moved left on
the project timeline. First half of "test early and often."

### Four Types of Shift-Left (Firesmith, 2013–2015)

1. **Traditional shift-left** — Move emphasis from late acceptance/system
   testing down to **unit and integration testing**. Largely completed
   industry-wide.
2. **Incremental shift-left** — Decompose one large V into many smaller
   incremental Vs; each increment gets its own testing. Standard for large
   complex systems (especially hardware-heavy).
3. **Agile/DevOps shift-left** — Replace the single V with many tiny
   sprint-Vs; testing happens within every short sprint. Currently dominant.
4. **Model-based shift-left** — Test **requirements, architecture, and
   design models** *before any code exists*. The most aggressive form — you
   verify the *specifications themselves*.

**Why shift left:** defects are exponentially cheaper to fix the earlier
they're caught. A bug in requirements costs ~1× to fix at requirements time,
~10–100× if found in production.

**Harm caused by late testing** (that shift-left prevents):
- Insufficient resources allocated to testing.
- Undiscovered defects in requirements, architecture, and design — and
  significant wasted effort implementing them.
- Increasing debugging difficulty as more software is integrated.
- A "bow wave" of technical debt that can sink the project.

---

## 4. Continuous Verification / Continuous Testing

**Continuous testing** (Wikipedia): "the process of executing automated
tests as part of the software delivery pipeline to obtain **immediate
feedback on the business risks** associated with a software release
candidate." Scope: from bottom-up validation of requirements/user stories to
assessing system requirements tied to business goals.

**Continuous verification** (broader concept) extends continuous testing
beyond code/CI: **constantly and automatically checking** that a system
continues to meet requirements *after deployment, in production*. Associated
with:
- **Progressive delivery** (canary deployments, feature flags) — rollout
  stages gated by automated checks of real-world behavior.
- **Observability-driven verification** — SLOs, health checks, automated
  rollbacks ("verify in production"; progressive-delivery / GitOps).
- **Policy-as-code / compliance-as-code** — continuously verifying
  infrastructure stays compliant (OPA, Sentinel).

**Shared principles:**
- Fast feedback loops (defects exposed soon after introduction).
- Automated, gate-able checks (pass/fail signal in a pipeline, not a manual
  milestone).
- Risk-based (tests map to business-risk tolerance, not just coverage).
- Defect prevention over detection (shift quality left).
- Metrics & continuous improvement (the process itself is measured).

---

## 5. Mapping V&V to Agent Workflows

An LLM agent loop (observe → reason → act → observe) is itself a
**micro-SDLC every turn**. Each turn produces an "artifact" (a tool call, a
text answer, a plan).

### 5.1 Core Analogy Table

| SE Concept | Agent-Loop Equivalent |
|-----------|----------------------|
| **Specification (input)** | The task/prompt + the tool's contract (param schema, expected return shape, postconditions) |
| **Verification** (built it right) | Checking the agent's output against the *explicit specification* — right args? right return type? constraints obeyed? |
| **Validation** (right thing) | Checking whether the output actually *solves the user's real problem* — not just what they literally asked |
| **Review** (static technique) | Inspecting the agent's reasoning/plan *before* executing — LLM-as-judge on a plan, self-critique, schema validation before a tool call fires |
| **Unit test** | Checking a single tool call in isolation |
| **Integration test** | Checking a sequence of tool calls / a multi-step trajectory |
| **System test** | End-to-end eval on a full task suite |
| **Acceptance test** | The user's thumbs-up / a golden answer match / a real-world outcome |

### 5.2 Verification in an Agent Loop (built it right) = spec-conformance

- **Schema/contract validation** before a tool call (param matches function
  schema).
- **Tool-result shape checks** (did the tool return what its contract
  promised?).
- **Pre/postcondition checks** (e.g., "file must exist after `write_file`").
- **Constraint satisfaction** ("only use tool calls," "don't modify files
  outside the workspace," "respond in JSON").

**Technique:** deterministic code (guards, validators, parsers), not another
model call. Fast, cheap, high-precision.

### 5.3 Validation in an Agent Loop (right thing) = outcome/utility

- **LLM-as-judge** — a second model evaluates "does this actually answer the
  question / accomplish the task?"
- **Eval harnesses** — golden task sets scored against rubrics.
- **User-in-the-loop feedback** — thumbs up/down, implicit correction
  signals.
- **Real-world grounding** — did the code actually run? did the change move
  the metric?

**Technique:** usually a model call or a human. Slower, costlier, lower
precision than verification, but measures the thing that matters.

### 5.4 Review in an Agent Loop = static, pre-execution

The most **underused** technique in agent design:
- **Plan-then-execute** — generate a plan, *review* it before any
  irreversible action.
- **Diff review before apply** — show proposed code change to a reviewer
  (human or model) before commit.
- **Tool-call linting** — lightweight pass inspecting a proposed tool call
  for smell.
- **Reflection / self-critique** — agent re-reads its own draft and revises.

Review is to agents what **inspections and walkthroughs** are to software:
cheap, catches a large fraction of defects, scales.

### 5.5 Shift-Left Verification for Agents

**Core insight:** catch defects as early as possible in the agent's turn,
because the cost of a bad tool call compounds (downstream calls build on bad
state; user trust erodes; token budget burns).

Concretely, agents should shift left by:
1. **Validating the *prompt/task* before acting** — does the task make sense?
   Is it ambiguous? (Model-based shift-left: verify requirements before
   building the response.)
2. **Schema-validating tool calls before dispatch** (not after a crash).
3. **Pre-commit review of file edits** — show the patch to a reviewer model
   before writing, especially for irreversible operations.
4. **Plan-first architectures** (ReAct-with-plan, Plan-and-Execute,
   Tree-of-Thought) — generate and *verify the plan* before executing.
5. **Fail fast on contract violations** — if a tool returns an unexpected
   type, surface it immediately.

### 5.6 Continuous Verification for Agents

For long-running, multi-turn, or deployed agents, one-shot verification at
the end isn't enough:
1. **Eval-gated rollouts** — every agent/prompt change must pass an eval
   suite before going live (CI for agents).
2. **Trajectory-level checks** — not just "was each tool call valid?" but
   "did the *sequence* achieve the goal?"
3. **Production monitoring / observability for agents** — log tool calls,
   outcomes, corrections; detect drift, regressions, loops in real time.
4. **Feedback loops that retrain the guardrails** — user corrections and
   judge scores feed back into the eval set, guardrails, system prompt.
5. **Progressive rollout of capabilities** — enable a new tool/model for 1%
   of traffic first; auto-rollback if error rate spikes (canary pattern for
   agent behavior).

---

## 6. Summary — The Unified Vocabulary for Agent Builders

- **Verify** = "Did the agent build the response/action right?" → check
  against the *specification* (schemas, contracts, constraints).
  Deterministic, fast, cheap.
- **Validate** = "Did the agent build the *right* response?" → check against
  the *user's actual need*. Usually a model judge or a human.
- **Review** = a *static verification technique* — inspect the agent's
  plan/output *before* execution or delivery. Cheap defect prevention; the
  agent-design analogue of code review.
- **Shift-left verification** = move checks to the earliest possible point in
  the agent's turn (validate the task before acting, schema-check before
  dispatch, review plans before executing). Defects compound — catch them at
  t=0.
- **Continuous verification** = keep checking *after* the turn and *across*
  turns — eval-gated rollouts, trajectory scoring, production monitoring,
  feedback loops. Agents are deployed systems, not one-shot programs.

---

## Sources

- Wikipedia, "Software verification and validation" (IEEE/CMMI/Boehm defs).
- IEEE Std 610.12-1990 (Standard Glossary of SE Terminology).
- ISTQB Glossary of Testing Terms v4.x (istqb-glossary.org) — static vs
  dynamic testing; review taxonomy.
- Wikipedia, "V-model (software development)".
- Wikipedia, "Shift-left testing" (Larry Smith, *Dr. Dobb's Journal*, Sept
  2001; Donald Firesmith's "Four Types of Shift Left Testing," 2013–2015).
- Wikipedia, "Continuous testing".
- INCOSE Systems Engineering Handbook.
- Boehm, B. (1979), "Software Engineering: R&D Trends and Defense Needs."

*Note: The ISTQB glossary website (glossary.istqb.org) was inaccessible
during this research (server-side errors); definitions are paraphrased from
the established ISTQB Foundation Level syllabus content as reflected in
secondary sources.*
