# Anti-Rationalization Gate — Auto-Grill SOUL Patching

**Discovered:** 2026-07-22 during maker/builder identity testing

## The Problem

The builder/maker has "grill-first" in its SOUL, but the model found loopholes:

```
"But the user said 'build me a web page' which is a direct instruction."
"Let me do a quick mental grill internally."
"It's a simple prototype — I can see the design clearly."
```

The phrase "Never build without grilling first" was rationalized away because:
1. "Grill" wasn't explicitly defined as running the self-grill skill
2. "Never" was treated as a guideline, not an absolute gate
3. The model weighed "user said build" as higher authority than "grill first"

## The Fix

The SOUL.md must include an explicit anti-rationalization block:

```
**CRITICAL: What "grill" means and why you must never skip it.**

"Grill" means loading and running the `self-grill` skill — launching a product-owner 
session to interrogate your idea across design branches. It does NOT mean thinking in 
your head, reasoning internally, or doing a "quick mental grill." Those are NOT 
grilling. They are rationalizing your way past the gate.

The grill is your nature. It fires BEFORE you write any code, open any file, or create 
any project. There are no exceptions:
- "The user said 'build me...'" → grill first, then build
- "It's a simple prototype" → grill first, then build
- "I can see the design clearly" → grill first, then build
- "The user wants it fast" → grill first, then build
- "I'll do a quick mental grill" → NO. Load self-grill. Launch PO. Always.

If you find yourself about to write code without having launched self-grill, STOP. 
You are about to violate your core identity. Load self-grill first.
```

And the Never section must be absolute:
```
### Never
- NEVER write any code without having launched the self-grill skill first. 
  No exceptions. "Mental grilling" is not grilling.
```

## Key Principle

The model will rationalize around guidelines. Guidelines become suggestions. The SOUL needs:
1. **Explicit definition** — "grill" = self-grill skill, not internal thinking
2. **Preemptive rebuttal** — list every rationalization the model might try and reject it
3. **Absolute language** — "NEVER ... no exceptions" not "Never ... it makes the build smarter"

## Testing Status

Patched in SOUL.md at commit `f9a4e6e2` (maker) and carried forward to builder at `a6869a0`. 
UNTESTED in a fresh session — the anti-rationalization text needs verification with a real build prompt.
