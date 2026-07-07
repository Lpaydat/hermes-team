# Generator-Verifier Pattern — Research Findings (Jul 2026)

## Terminology across fields

All of these describe the same core pattern (Groneberg: "maker-checker = evaluator-optimizer = reflection"):

| Term | Source | Context |
|------|--------|---------|
| **Verifier** | Academic papers (6 of 11 surveyed) | Generator-verifier, RLVR, scalable oversight |
| **Critic** | Actor-critic heritage, LangGraph, AutoGen | Multi-agent SE papers |
| **Reviewer** | Multi-agent debate, medical AI (MARS) | Peer review simulation |
| **Checker** | Banking/finance industry blogs | Maker-checker pattern |
| **Evaluator** | Anthropic canonical guide | Evaluator-optimizer pattern |
| **Reflector** | Andrew Ng | Reflection pattern |

**Consensus**: "Verifier" is the most recognized cross-domain term. Use it.

## Key academic papers

| Paper | Term | Key finding |
|-------|------|-------------|
| "LLMs Cannot Self-Correct Reasoning Yet" (Huang et al.) | self-correction | Same-model self-correction is structurally weak without external signal |
| "Self-Refine" (Madaan et al.) | generator/refiner | Iterative refinement with feedback loop |
| "RL Tango" | generator-verifier | RL-trained verifier improves generator |
| "FindTheFlaws" | prover-verifier | Adversarial verification catches more bugs |
| "Delayed Verification Destabilizes" | verifier + critic | Timing of verification matters — earlier is better |

## Framework terminology

| Framework | Review role name | Pattern |
|-----------|-----------------|---------|
| LangGraph | Critique agent, reflector, judge | Two-agent reflection loop; LLM-as-a-Judge |
| AutoGen | Critic agent | Two-agent team (reflection) |
| CrewAI | Manager agent | Hierarchical (manager delegates & validates) |
| Aider | Architect → Editor | Plan review before code; human as verifier |
| OpenHands | No critic role | Single CodeActAgent, human confirmation |
| Devin/Cognition | "self-verify", "autofix" | Plan → code → review → fix loop |
| SWE-agent | No critic role | Bash execution = ground truth |

## V&V formal definitions (IEEE/ISTQB)

| Term | Question | SE definition | Agent equivalent |
|------|----------|---------------|-----------------|
| **Verify** | "Did we build it right?" | Products of a phase satisfy conditions imposed at start | Run tests, check contract items, lint — deterministic, fast |
| **Validate** | "Did we build the right thing?" | Software satisfies specified requirements at end of process | LLM-as-judge, eval harness, user feedback — outcome-based |
| **Review** | (subset of verification) | Static testing technique — no code execution | Diff review, plan review — most underused technique |

**ISTQB insight**: "Review" is a *technique within static testing* (a verification activity), NOT a peer of V&V. This means "reviewer" as a role name is technically too narrow — the profile does both static review AND dynamic verification.

## Prominent voices

- **Karpathy**: "You can outsource your thinking, but you can't outsource your understanding" — verifiability as the map of what automates next
- **Simon Willison**: "An LLM agent runs tools in a loop to achieve a goal" — accountability gap prevents agents from being human replacements
- **Harrison Chase** (LangGraph): "main agent + critique agent" — three patterns (Basic Reflection, Reflexion, LATS)
- **Devin/Cognition**: "Plans, codes, reviews its own output, catches issues, and fixes them — all before you ever open the PR"

## Critical distinction: self-verification vs independent verification

Self-verification (same model, same context) is structurally weaker than independent verification (separate context, adversarial prompting). This is why role separation matters — the verifier MUST be a different agent instance with clean context, not the generator reviewing its own work.
