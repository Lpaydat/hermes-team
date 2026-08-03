# QA Workflow A/B/C/D/E Evolution — Lessons Learned

## Evolution chain

```
A (cron)     → B (engine, 1 card)   → C (engine, 7-card fan-out)
  → D (C + 6 gap fixes) → E (D + adaptive sizing + intermediate schemas)
```

Each version was A/B tested on identical fixture repos with 5+ subagent deep analysis.

## Key findings per dimension

### Card structure drives execution depth

The same 8-phase protocol in 1 card → QA skips 5 phases. In 7 cards → QA executes all 7. The template's card structure, not the protocol text in the body, determines what QA actually does.

### Adaptive sizing (E)

qa-receive computes `sizing: small|medium|large` from claim count and artifact type. Conditional edges route:
- small → qa-quick (1 card, ~30K tokens, 235s)
- non-small → 7-card fan-out (~110K tokens, 444s)

3× cheaper for small artifacts with same verdict quality. Caught a finding the 7-card version missed (single-session context advantage).

### Schema pitfalls (hit in production)

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Boolean in condition | `True == 'true'` → False | Use `"True"` or output strings |
| String-enum for boolean | `True` fails `{"type":"string","enum":["true"]}` | Use `{"type":"boolean"}` |
| Optional field in schema | `null` fails `{"type":"string"}` | Omit from properties |
| skill field on node | Not passed to card | skill_enforcer handles it |
| depends_on + explicit edges | Unreachable nodes error | Add explicit edges |
| Verdict vocabulary | `pass`/`clean` vs `PASS` | Schema enum enforces |

### Delta-first testing

QA must test CHANGED files first. Without explicit `git diff --name-only` instruction in the card body, QA over-invested in unchanged sibling files and under-tested the actual merge delta.

### Findings accountability

`findings_filed: <int>` in the output schema forces QA to count actual kanban cards created for findings. Without it, QA claims findings but doesn't file them.

### Inline evidence in verdict

The verdict card should cite ONE key piece of evidence per phase inline. Without this, the verdict is just counts — you need to open child cards to see any evidence.

### Cost-efficiency by artifact size

| Size | Best version | Cost | Quality |
|------|-------------|------|---------|
| Small (<10 claims) | E qa-quick | ~30K tokens | 6/10 evidence |
| Medium (10-20) | D/E fan-out | ~110K tokens | 9/10 evidence |
| Large (20+) | D/E fan-out + containers | ~200K+ tokens | 9/10 evidence |

## Remaining gaps (for F)

1. qa-quick evidence depth (6/10 → target 9/10)
2. Medium/large path untested with enforced schemas
3. No FAIL-path testing (all tests were PASS on trivial changes)
4. node_states.status not updated on dead-branch skip (engine bookkeeping)
