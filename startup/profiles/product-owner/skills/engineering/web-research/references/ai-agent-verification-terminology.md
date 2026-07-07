# AI Agent Verification Loops & Maker-Checker Pattern — Terminology Reference

Source: Web research session (Jul 2026). All sources and URLs verified at time of retrieval.

## The Terminology Map

| Term | Where it dominates | Context |
|------|-------------------|---------|
| **Verifier** | Academic RL/RLVR literature | "generator-verifier" pairing; formal correctness check vs ground truth |
| **Critic** | Actor-critic RL lineage; multi-agent SE | Value judgment / qualitative assessment (AgentForge, CRADLE) |
| **Reviewer** | Multi-agent debate papers; medical/legal | Peer-review simulation (MARS, RadCouncil) |
| **Checker** | Industry blogs; finance/banking context | Maker-checker pattern; separation-of-duties |
| **Evaluator** | Anthropic's canonical taxonomy | "Evaluator-Optimizer" workflow |

**Canonical equivalence** (per Groneberg workshop):  
`maker-checker` = `evaluator-optimizer` (Anthropic) = `reflection` (Andrew Ng)

## Academic Papers

### Cannot Self-Correct
- **Title:** Large Language Models Cannot Self-Correct Reasoning Yet
- **URL:** https://arxiv.org/abs/2310.01798
- **Quote:** "In the context of reasoning, our research indicates that LLMs struggle to self-correct their responses without external feedback, and at times, their performance even degrades after self-correction."
- **Key finding:** Intrinsic self-correction fails without external signal. Foundation for the maker-checker pattern.

### Small LMs Need Strong Verifiers
- **Title:** Small Language Models Need Strong Verifiers to Self-Correct Reasoning
- **URL:** https://arxiv.org/abs/2404.17140
- **Quote:** "LLMs refine their solutions using self-generated critiques... notable performance gains when paired with a strong GPT-4-based verifier, though limitations are identified when using a weak self-verifier."
- **Key finding:** Separate/stronger verifier outperforms self-verification.

### Self-Refine
- **Title:** Self-Refine: Iterative Refinement with Self-Feedback
- **URL:** https://arxiv.org/abs/2303.17651
- **Quote:** "A single LLM [acts] as the generator, refiner, and feedback provider... improving by ~20% absolute on average."
- **Key finding:** Single-model self-refine can work on easier tasks (the optimistic counterpoint).

### RL Tango (Generator-Verifier Co-Training)
- **Title:** RL Tango: Reinforcing Generator and Verifier Together for Language Reasoning
- **URL:** https://arxiv.org/abs/2505.15034
- **Quote:** "An LLM generator serves as a policy guided by a verifier (reward model)... a generative, process-level LLM verifier, which is trained via RL and co-evolves with the generator."
- **Key finding:** Uses "verifier" as the canonical academic term. Both generator and verifier improve via co-training.

### PAG (Policy as Generative Verifier)
- **Title:** PAG: Multi-Turn Reinforced LLM Self-Correction with Policy as Generative Verifier
- **URL:** https://arxiv.org/abs/2506.10406
- **Quote:** "Empowers LLMs to self-correct by alternating between policy and verifier roles... a verify-then-revise workflow."
- **Key finding:** Roles are interchangeable within one model. Selective revision mechanism.

### SPOC (Spontaneous Self-Correction)
- **Title:** Boosting LLM Reasoning via Spontaneous Self-Correction
- **URL:** https://arxiv.org/abs/2506.06923
- **Quote:** "Assigns dual roles — solution proposer and verifier — to the same model... interleaved solutions and verifications in a single inference pass."
- **Key finding:** Multi-agent perspective with dual roles in one model.

### AgentForge (Critic Agent)
- **Title:** AgentForge: Execution-Grounded Multi-Agent LLM Framework for Autonomous Software Engineering
- **URL:** https://arxiv.org/abs/2604.13120
- **Quote:** "Planner, Coder, Tester, Debugger, and Critic agents coordinate through shared memory... execution-grounded verification as a first-class principle."
- **Key finding:** Uses "critic" for the checking role in a software engineering pipeline.

### CRADLE (Generator-Critic)
- **Title:** CRADLE: Conversational RTL Design Space Exploration with LLM-based Multi-Agent Systems
- **URL:** https://arxiv.org/abs/2508.08709
- **Quote:** "A generator-critic agent system targeting FPGA resource minimization."
- **Key finding:** Generator-critic framing for hardware design.

### MARS (Reviewer System)
- **Title:** MARS: toward more efficient multi-agent collaboration for LLM reasoning
- **URL:** https://arxiv.org/abs/2509.20502
- **Quote:** "An author agent generates... reviewer agents provide decisions and comments independently, and a meta-reviewer integrates the feedback."
- **Key finding:** Explicit "reviewer" + "meta-reviewer" hierarchy.

### Delayed Verification Destabilizes
- **Title:** Delayed Verification Destabilizes Multi-Agent LLM Belief
- **URL:** https://arxiv.org/abs/2606.27409
- **Quote:** "Multi-agent LLM systems often rely on verifier and critic agents to suppress hallucinations, but verification is delayed."
- **Key finding:** Uses both "verifier" and "critic" interchangeably. Formal model of verification delay.

### Asymmetric Actor-Critic
- **Title:** Asymmetric Actor-Critic for Multi-turn LLM Agents
- **URL:** https://arxiv.org/abs/2604.00304
- **Quote:** "A powerful proprietary LLM acts as the actor, while a smaller open-source critic provides runtime supervision... leverages a generation-verification asymmetry."
- **Key finding:** The checker can be a smaller model than the maker.

### Prover-Verifier (Scalable Oversight)
- **Title:** FindTheFlaws: Annotated Errors for Detecting Flawed Reasoning
- **URL:** https://arxiv.org/abs/2503.22989
- **Quote:** "Prover-verifier games, in which a capable 'prover' model generates solutions that must be verifiable by a less capable 'verifier'."
- **Key finding:** OpenAI's scalable-oversight game-theoretic framing.

### ExComm (Verification Loop)
- **Title:** ExComm: Exploration-Stage Communication for Error-Resilient Agentic Test-Time Scaling
- **URL:** https://arxiv.org/abs/2605.22102
- **Quote:** "Periodically audits agent belief states to detect such conflicts, resolves them through a dedicated tool-based verification loop."
- **Key finding:** Uses "verification loop" terminology for multi-agent error recovery.

### ChromaFlow (Verification Loops)
- **Title:** ChromaFlow: A Negative Ablation Study of Orchestration Overhead
- **URL:** https://arxiv.org/abs/2605.14102
- **Quote:** "Autonomous language-model agents increasingly combine planning, tool use, document processing, browsing, code execution, and verification loops."
- **Key finding:** Verification loops as a standard capability alongside planning and tool use.

## Industry Blog Posts

### Anthropic — "Building Effective Agents"
- **URL:** https://www.anthropic.com/research/building-effective-agents
- **Term:** Evaluator-Optimizer
- **Quote:** "In the evaluator-optimizer workflow, one LLM call generates a response while another provides evaluation and feedback in a loop."
- **Examples given:** Literary translation, complex search tasks.

### XYZBytes — "One Agent Writes, Another Agent Checks"
- **URL:** https://www.xyzbytes.com/blog/maker-checker-agents-verification-loops
- **Term:** Maker-Checker
- **Quote:** "An agent grading its own work is not a check. It is a confirmation ritual."
- **Three required properties:** Independent context, adversarial prompting, majority vote panel.

### Labyrinth Analytics — "The Maker-Checker Pattern"
- **URL:** https://labyrinthanalyticsconsulting.com/blog/maker-checker-pattern-ai-pipeline
- **Term:** Maker-Checker (deterministic maker, LLM checker)
- **Quote:** "The checker recomputes the answer using natural-language reasoning rather than the code path taken by the maker."
- **Unique angle:** Inverts the roles — deterministic code is maker, LLM is checker.

### Terry Li — "The Maker-Checker Trap"
- **URL:** https://terryli.hm/posts/the-maker-checker-trap/
- **Term:** Maker-Checker (critical perspective)
- **Quote:** "The maker-checker pattern, as typically implemented, optimises for the wrong thing. It optimises for the checker catching errors... The metric that actually matters is 'declining error rate over time'."
- **Key insight:** Without structured exception capture (the "why" behind corrections), the system doesn't compound.

### Groneberg Workshop — "Agentic AI Design Patterns"
- **URL:** https://jeffrey-groneberg.github.io/AI_Workshop_Agentic_Patterns/patterns/maker-checker/
- **Term:** Maker-Checker = Evaluator-Optimizer = Reflection
- **Quote:** "The maker-checker is a two-agent pattern where one agent produces output and another evaluates it, looping until quality criteria are met. This maps to the Evaluator-Optimizer pattern from Anthropic and the Reflection pattern from Andrew Ng."
- **Key insight:** The canonical equivalence mapping.

### WNS — "Agentic AI in Banking"
- **URL:** https://www.wns.com/perspectives/blogs/agentic-ai-in-banking-re-writing-the-maker-checker-rulebook
- **Term:** Maker-Checker (banking context)
- **Context:** Banking's separation-of-duties control pattern being mapped onto AI agents.

## Key Insights

1. **No single term dominates** the field. Academia leans "verifier/critic"; industry leans "checker/evaluator"; multi-agent papers use "reviewer."

2. **The critical distinction is internal vs. external verification.** Self-verification (same model) is empirically weaker than independent verifier (separate context + adversarial prompting).

3. **"Critic" vs. "verifier" nuance:** "Critic" implies qualitative judgment (actor-critic heritage); "verifier" implies correctness check against ground truth.

4. **The checker can be smaller.** Asymmetric Actor-Critic (arXiv:2604.00304) shows a smaller open-source critic can supervise a larger proprietary actor effectively.

5. **The feedback loop must compound.** Terry Li's trap: without structured exception capture, the checker corrects the same errors forever.

---

## Researcher & Founder Perspectives (Jul 2026)

### Andrej Karpathy — Verifiability Framework & Agent Loops

**Sources:**
- Sequoia AI Ascent 2026 talk transcript: https://sozai.app/transcript/andrej-karpathy-vibe-coding-agentic-engineering/
- Karpathy's Software 3.0 Playbook (analysis): https://philippdubach.com/posts/karpathys-software-3.0-playbook/
- LittleX Research deep dive: https://littlex.org/en/research/sequoia-karpathy-software3-20260502/

**Key quotes:**

> "Traditional computers can easily automate what you can specify in code, and this latest round of LLMs can easily automate what you can verify… The way frontier labs train these LLMs, these are giant reinforcement learning environments — they are given verification rewards."

> "You can outsource your thinking, but you can't outsource your understanding."

> "You're in charge of the taste, the engineering, the design, and that it makes sense, and that you're asking for the right things."

> "When you actually look at the code, sometimes I get a little bit of a heart attack, because it's not super amazing code… It's very bloaty, and there's a lot of copy-paste, and there's awkward abstractions that are brittle and — like, it works, but it's just really gross."

> "Vibe coding is about raising the floor for everyone… But agentic engineering is about preserving the quality bar of what existed before in professional software."

**Verifiability thesis:** Karpathy argues verification reward availability predicts what frontier models will excel at. Domains with verifiable outcomes (math, code) get the steepest RL-driven gains. Everything else stays "jagged." He sees human taste/judgment/verification as the lasting bottleneck — and the human's inability to absorb information fast enough as the binding constraint on how many agent loops one person can manage.

### Simon Willison — Agent Definition & Accountability

**Source:** https://simonwillison.net/2025/Sep/18/agents/

> "An LLM agent runs tools in a loop to achieve a goal."

> "If your agent strategy is to replace your human staff… you're going to end up sorely disappointed. That's because there's one key feature that remains unique to human staff: accountability."

**Key insight:** Willison's settled definition ("tools in a loop to achieve a goal") is now widely accepted among practitioners. He distinguishes this from the "agents as human replacements" definition common in business contexts, calling the latter "science fiction" because of the unbridgeable accountability gap.

### Harrison Chase (LangChain) — Reflection/Critique Agents

**Sources:**
- LangChain blog: https://www.langchain.com/blog/reflection-agents
- GitHub: https://github.com/langchain-ai/langgraph-reflection

> "Reflection is a prompting strategy used to improve the quality and success rate of agents and similar AI systems. It involves prompting an LLM to reflect on and critique its past actions."

**Three patterns:**
1. **Basic Reflection**: generator + reflector (teacher role-play)
2. **Reflexion**: actor explicitly critiques with citations/grounding in external data
3. **Language Agent Tree Search (LATS)**: explores multiple reasoning paths

**langgraph-reflection package:** Prebuilt graph with "main agent" + "critique agent". The critique agent returns a **user** message if critiques exist, or **no** messages when done. Supports LLM-as-a-Judge (evaluating on Accuracy, Completeness, Clarity, Helpfulness, Safety) and Code Validation via Pyright static analysis.

### Devin / Cognition — Self-Verify & Auto-Fix

**Sources:**
- Devin 2.2: https://cognition.com/blog/introducing-devin-2-2
- Devin Review: https://cognition.com/blog/devin-review

> "Devin doesn't just write code and hand it off. It plans, codes, reviews its own output, catches issues, and fixes them — all before you ever open the PR."

> "As code generation gets easier, code review is the new bottleneck… code review — not code generation — is now the bottleneck to shipping great products."

**Devin Review bug severity levels:** Red (probable bugs), Yellow (warnings), Gray (FYI/commentary).

**Key insight:** Cognition frames agent verification as two distinct problems: (1) self-verify during code generation (the "autofix" loop), and (2) AI-assisted code review of the output (Devin Review for humans). Their "Lazy LGTM problem" thesis — small PRs are easy to review, large ones aren't — is the business justification.

### SWE-agent / Mini-SWE-agent (Princeton/Stanford) — Minimalist Verification

**Source:** https://mini-swe-agent.com/latest/

> "Does not have any tools other than bash — it doesn't even use the tool-calling interface of the LMs."
> "Back then, we placed a lot of emphasis on tools and special interfaces… However, one year later, a lot of this is not needed at all."

**Approach:** No separate critic/verifier agent. Verification = execution result. The agent appends to a linear message history, executes bash commands via `subprocess.run`, and the exit code + output is the only feedback signal. Achieves >74% on SWE-bench verified in ~100 lines of Python.

**Key insight:** The minimalist counterpoint to architect-heavy multi-agent systems. Demonstrates that for well-scoped software engineering tasks, execution-based verification can replace LLM-based critics entirely.

### Matt Shumer — Validation & Orchestration

**Source:** https://shumer.dev/blog

> "The first coding model I can start, walk away from for hours, and come back to fully working software. Judgment under ambiguity + strong validation changes everything."
> — GPT-5.3-Codex review (Feb 2026)

**Key insight:** Shumer's emphasis on "judgment under ambiguity + strong validation" as the threshold for autonomous coding aligns with the verifiability thesis. His prompting guide emphasizes giving agents "right context, clear constraints, and the exact shape of the output you want."

### Flo Crivello (Lindy CEO) — Production Agent Evaluation

**Source:** https://flocrivello.com/ (personal blog), https://www.cognitiverevolution.ai/living-lindy-a-no-bs-conversation-on-ai-agents-with-flo-crivello/ (podcast)

**Key insight:** Crivello's public writing is business/strategy focused rather than technical verification patterns. As CEO of Lindy (enterprise AI agent platform), his perspective represents the production deployment viewpoint: agents need to actually deliver value to customers, and evaluation is ultimately about business outcomes rather than LLM judgment loops.

---

## Framework Terminology Comparison (Jul 2026)

| Framework | Review/Verification Role(s) | Architecture Pattern | How It Verifies |
|-----------|---------------------------|---------------------|-----------------|
| **LangGraph** | "critique agent", "reflector", "judge" | Two-agent reflection loop; Reflexion (actor + revisor) | LLM-as-a-Judge; Pyright static analysis; citation-grounded critique; external tool feedback |
| **AutoGen** (Microsoft) | "critic agent" | Two-agent teams (RoundRobinGroupChat); Reflection pattern | Critic evaluates primary agent's responses; LLM-based evaluation |
| **CrewAI** | "manager agent" | Hierarchical Process (manager delegates & validates) | Manager validates outcomes; sequential task execution with manager oversight |
| **Aider** | "Architect" + "Editor" (human as verifier) | Two-model: Architect (reasoning) → Editor (edits) | Human reviews the plan before editor runs; linting; edit format validation |
| **OpenHands** | No separate critic role | Single CodeActAgent (code as action) | Asks human for confirmation; execution feedback from bash/Python |
| **Devin** (Cognition) | "self-verify", "Devin Review Autofix" | Self-contained: plan → code → review → fix loop | AI bug detection (red/yellow/gray); computer-use testing; test suite execution |
| **SWE-agent** / **Mini-SWE-agent** | No separate critic role | Single agent with bash commands | Execution-based (bash exit code, test output); no LLM-as-judge |
| **Karpathy's approach** | Human as verifier; "self-check protocol" (CLAUDE.md) | Human-in-the-loop: taste + judgment + verification | CLAUDE.md self-check rules; human oversight of agent-generated code |

### Detailed Framework Terminology

#### LangGraph (LangChain)
- **Nodes:** "generation_node", "reflection_node" (basic pattern)
- **Reflexion:** "first_responder" (draft), "execute_tools", "revisor" (revise)
- **langgraph-reflection:** "main agent", "critique agent"
- **Judgment criteria:** Accuracy, Completeness, Clarity, Helpfulness, Safety
- **Source:** https://www.langchain.com/blog/reflection-agents

#### AutoGen (Microsoft)
- **Team types:** RoundRobinGroupChat, SelectorGroupChat, MagenticOneGroupChat, Swarm
- **Role:** "critic agent" (evaluates primary agent responses)
- **Pattern:** "Reflection pattern"
- **Source:** https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/teams.html

#### CrewAI
- **Process modes:** Sequential (default), Hierarchical
- **Role:** "manager agent" — coordinates, delegates, validates outcomes
- **Manager capabilities:** "Result Validation: The manager evaluates outcomes to ensure they meet the required standards"
- **Source:** https://docs.crewai.com/en/learn/hierarchical-process

#### Aider
- **Roles:** "Architect" (reasoning model), "Editor" (editing model)
- **Verification:** Human reviews the Architect's plan before the Editor acts
- **Source:** https://aider.chat/2024/09/26/architect.html

#### OpenHands
- **Agent type:** CodeActAgent (single agent)
- **Capabilities:** "Converse: Communicate with humans in natural language to ask for clarification, confirmation, etc."
- **Source:** https://docs.openhands.dev/openhands/usage/agents

#### Devin (Cognition)
- **Terminology:** "self-verify", "auto-fix", "Devin Review Autofix"
- **Bug severity:** Red (probable bugs), Yellow (warnings), Gray (FYI)
- **Source:** https://cognition.com/blog/introducing-devin-2-2

#### SWE-agent / Mini-SWE-agent
- **No critic role:** Minimalist approach — bash commands only, no tool-calling
- **Verification via execution:** `subprocess.run` result = ground truth
- **Source:** https://github.com/SWE-agent/mini-swe-agent

---

## Cross-Cutting Insights (added Jul 2026)

1. **Two schools of thought on verification:** Internal critics (LangGraph, AutoGen, Devin use LLM-as-judge) vs. execution-based (SWE-agent, mini-SWE-agent let test results/bash output be the ground truth).

2. **The human role is shifting.** Karpathy's "taste, judgment, engineering, design" and Aider's "plan review before code touches files" both position the human as the verifier of plans, not the executor.

3. **Verifiability predicts automation speed.** Karpathy's verifiability framework: what can be verified (math, code) gets automated fastest. Everything else stays "jagged."

4. **The minimalist challenge.** Mini-SWE-agent (74% SWE-bench, 100 lines, no critic) challenges the assumption that multi-agent review architectures are necessary for quality. Sometimes execution feedback is enough.

5. **Framework language is converging on few patterns:** "Critic/critique" (LangGraph, AutoGen), "Manager" (CrewAI), "Architect/Editor" (Aider), "Self-verify" (Devin). The most minimal frameworks (SWE-agent, OpenHands) skip the reviewer role entirely.
