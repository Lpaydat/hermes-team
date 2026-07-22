# Fact-Verification (Phase 3.5)

Every dossier must be fact-verified by an **independent** subagent before grilling. The model that wrote the dossier cannot verify it — that's echo, not verification.

## How to verify

Dispatch `delegate_task` with `role='leaf'`:

```
Fact-verify the dossier at [path]. You did NOT write this dossier.
Every claim is false until you verify it independently.

Check:
1. SOURCE URLS — does each URL load and say what's claimed?
2. COMPETITOR DATA — revenue, pricing, employees — check original sources
3. MARKET STATISTICS — SBA numbers, engagement metrics, attribution
4. QUOTES — are they real and accurate (not paraphrased or invented)?
5. SCORING — does the evidence cited actually support the sub-scores?

Output VERIFIED / DISPUTED / UNVERIFIABLE for each claim with evidence.
Write report to [path]-verification.md.
Verdict: PASS (>=90% verified), CONDITIONAL (70-89%), FAIL (<70% or critical claim disproven).
Do NOT fabricate verification.
```

## Verification outcomes

- **PASS** → proceed to grill
- **CONDITIONAL** → fix disputed claims in the dossier, note unverifiable ones, then proceed
- **FAIL** → fix the dossier or re-research. If a critical claim is fabricated, kill the DOSSIER (not the idea)

Report template: `~/vault/ventures/templates/fact-verification-template.md`

## What the verifier catches (real examples, LeadPilot 2026-07-23)

1. **Podium pricing: $96/mo claimed → actual $399/mo** — researcher confused "$96K customer revenue" testimonial with pricing
2. **Podium valuation: $1.5B claimed → actual $3B** (Wikipedia)
3. **Podium plan names: "Core, Grow" → actual "Core, Pro, Signature"**
4. **Thryv entry price: $49/mo claimed → actual $244/mo** ($49 is a payroll add-on)

Lesson: researchers confuse adjacent numbers on pages. Independent verification catches these.
