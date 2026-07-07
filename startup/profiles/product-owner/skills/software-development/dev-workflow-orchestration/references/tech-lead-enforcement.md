# Tech-Lead Enforcement: Forcing Kanban-Native Flow

## The problem

Tech-lead's `loops-engineering` skill says to prefer the pi harness over `delegate_task`, but for quick single-file tasks tech-lead defaults to `delegate_task` (in-session subagent). This means:

1. The verifier profile is NEVER invoked (no kanban card assigned to verifier)
2. The failure-fix loop never triggers (same-model generation + verification)
3. The adversarial-review skill is never loaded
4. All verifier skill improvements go untested

**The user's core principle (Jul 2026)**: *"only SOUL not work from my experience. llm is suck and always cheat + take shortcut. we need to stripe tools from its hand instead"* — SOUL rules, skill patches, and card body language are **suggestions**. Tool access is **enforcement**. An LLM cannot use a tool it doesn't have. When a role keeps shortcutting around your architecture, the answer is always: remove the tool, don't add more prose.

## What does NOT work (proven in Tests 1-8)

| Strategy | Result |
|----------|--------|
| **Card body language** ("Use pi harness", "Do NOT use delegate_task") | ❌ Ignored — tech-lead treats instructions as suggestions |
| **Loops-engineering skill patches** (3 patches: "prefer pi", "PREFERRED", "MANDATORY") | ❌ Ignored — LLM takes the shortcut when it's available |
| **SOUL rules** ("NEVER write code") | ❌ Ignored — SOUL is a suggestion, not enforcement |
| **Complexity thresholds in the skill** | ❌ Unreliable — LLM judges task as "small" regardless |

**Test 8 (Jul 2026)**: Card body said "Use `pi --provider zai --model GLM-4.6`". Tech-lead ignored it and used `delegate_task` (GLM 5.2). Verifier never invoked. Test INCONCLUSIVE.

## What DOES work: toolset restriction (proven in Test 9)

**Strip the tools from tech-lead's hands.** LLMs cannot use tools they don't have. This is deterministic enforcement — no interpretation, no judgment, no shortcutting.

### Required toolset changes

```
hermes -p tech-lead tools disable delegation     # Forces pi/kanban-native flow
hermes -p tech-lead tools disable code_execution  # Prevents direct coding
hermes -p tech-lead tools disable file            # Prevents write_file/read_file
hermes -p tech-lead tools disable browser
hermes -p tech-lead tools disable vision
hermes -p tech-lead tools disable image_gen
hermes -p tech-lead tools disable tts
hermes -p tech-lead tools disable computer_use
hermes -p tech-lead tools disable clarify
hermes -p tech-lead tools disable cronjob
hermes -p tech-lead tools disable web
```

**Result**: tech-lead has ONLY terminal, skills, todo, memory, session_search, kanban. No `delegate_task`, no `write_file`, no `code_execution`.

### What tech-lead retains

| Tool | Why it's needed |
|------|----------------|
| `terminal` | Run bd, git, pytest, pi harness invocation |
| `skills` | Load loops-engineering doctrine |
| `todo` | Task tracking |
| `memory` | Persistent notes |
| `session_search` | Cross-session context |
| `kanban_*` | Create dev/verifier cards — the orchestration surface |

### Critical: gateway restart required

Toolset changes take effect ONLY on the next gateway restart. The running gateway process keeps the old toolset until restarted:

```bash
# Must run from OUTSIDE the gateway process:
hermes gateway stop --profile tech-lead
hermes gateway start --profile tech-lead
```

### Test 9 proof (Jul 2026)

After disabling `delegation` + `file` + `code_execution`:
1. Tech-lead tried codex (failed — infra), claude (failed — SSL), opencode (failed)
2. Fell back to `pi --provider zai --model glm-4.5-air` ← **THE HARNESS**
3. pi wrote code (inimerge.py + 23 tests)
4. Tech-lead ran adversarial probes — found AC5 defect (comment preservation)
5. Caught rubber-stamp test — generator's test only asserted keys, not comment survival
6. Re-delegated to pi with fix instructions — pi implemented custom `_extract_comments()`
7. Second probe confirmed all 11 ACs pass

The fix loop triggered naturally — exactly the generator-verifier dynamic the architecture was designed for.

## RESOLVED: harness-direct removed, kanban-native forced (Test 10b, Jul 2026)

**The gap is closed.** After removing harness-direct from loops-engineering entirely AND removing the `claude` binary (symlink deleted from fnm node-versions bin dir), tech-lead created its first kanban-native developer + verifier cards.

### What changed in loops-engineering

1. **Execute phase rewritten**: "You are the PLANNER. You NEVER write code and NEVER invoke a coding harness yourself." Kanban-native is the ONLY flow — create developer card, then verifier card.
2. **Validate phase rewritten**: "You don't validate; the verifier does." Tech-lead monitors verifier output only.
3. **Harness choices documented**: pi (GLM-4.5-air) is the default. Claude Code and zz/zlaude explicitly listed as alternatives. `cc` (original Claude) is disabled.

### What changed at the binary level

The `claude` symlink was deleted from the fnm node-versions bin directory:
```bash
rm -f ~/.local/share/fnm/node-versions/v24.18.0/installation/bin/claude
```
This prevents `claude` from resolving in PATH. `zz`/`zlaude` (Z.AI GLM wrappers) still work because they call the binary directly, not via the symlink.

**Rationale**: Claude Code's Anthropic models one-shot clean code, defeating the failure-fix loop test. The generator needs to produce bugs for the verifier to catch.

**Important distinction (user clarification, Jul 2026)**: `zz`/`zlaude` (Claude Code wrapper using Z.AI GLM backend) is ALLOWED — it routes through Z.AI's GLM models, not Anthropic's. Only `cc`/`claude` (original Claude with Anthropic models) is blocked. The wrapper `zz` calls the binary directly via a different path, so deleting the `claude` symlink doesn't affect it.

### Test 10b proof (Jul 2026) — FIRST FULL 3-ROLE PIPELINE

After all changes:
1. ✅ Tech-lead created developer card (`t_3bae40d0`) assigned to `developer`
2. ✅ Tech-lead created verifier card (`t_d788bd4c`) assigned to `verifier` as child
3. ✅ Developer profile picked up card, loaded developer-loop skill
4. ✅ Developer invoked `pi --provider zai --model glm-4.5-air` (weak model)
5. ✅ Developer completed with trace ledger + AC-to-evidence mapping (19 tests)
6. ✅ Verifier profile auto-promoted, loaded adversarial-review v4.0.0
7. ✅ Verifier ran 18 independent trace-blind probes
8. ✅ Verifier verdict: PASS — 37 green total (19 dev + 18 verifier)
9. ✅ Bead closed, all profiles completed correctly

**This is the first time ALL 3 profiles worked together in the full kanban-native pipeline.**

After dispatching a card, verify tech-lead used the correct flow:

```bash
# Check if developer/verifier cards were created
hermes kanban --board startup list --assignee developer 2>&1
hermes kanban --board startup list --assignee verifier 2>&1

# Check if pi harness was invoked (not delegate_task)
hermes kanban --board startup log <tech-lead-card-id> 2>&1 | grep -E 'pi --|delegate_task'
# If "pi --" appears → harness was used ✅
# If only "delegate_task" appears → shortcut was taken ❌ (shouldn't happen if toolset restricted)

# Verify tech-lead toolset is correct
hermes -p tech-lead tools list 2>&1 | grep 'enabled'
# Should show: terminal, skills, todo, memory, session_search (and kanban via config)
```

## Removing deepseek fallback

All profiles should have `fallback_model: []` in config.yaml. The deepseek fallback caused silent model switching when Z.AI had transient connection errors — tasks would succeed on deepseek but with different quality characteristics than expected. Verified Jul 2026: remove from ALL profiles (product-owner, developer, verifier, tech-lead).
