# PO Grill Quality — 2026-07-23 E2E Observations

## Context
First full E2E test of the self-grill flow with glm-5.2 acting as PO.
Two grills observed in detail: LeadPilot (14 decisions, 5 branches, ~50 min)
and WhatsApp Shared Inbox (still in progress at time of capture).

## What PO did well

### Evidence verification
PO does NOT accept dossier claims at face value. It demands sourcing:
- "Where did the 58% after-hours stat come from? Show me the thread."
- "You claim $2,340 from 187 texts but can't show a live URL. Is that acceptable evidence?"

### Math checking
PO caught a factor-of-10 error in WhatsApp pricing:
- Founder claimed: 2,000 convos × $0.10 = $20 (wrong)
- PO corrected: 2,000 × $0.10 = $200 → negative margin
- This was a grill-ending finding if not corrected

### Live competitor research
PO scraped the Shopify App Store live during the grill:
- Found 941 WhatsApp apps (founder claimed category was empty)
- Scraped Zoko's live listing, disproved 5 founder claims in a table
- Verified pricing, features, review counts — all cited with live data

### Pushing past hedging
When founder hedged ("we'll try multiple channels"), PO pushed:
- "Not 'we'll try multiple things' — what is THE channel? Name it specifically."
- "If the answer is 'manual outbound to 500 founders,' say that."
- Refused to accept vague answers as decisions

### Multiple-question batching
PO sometimes asks 3-5 questions in a single turn (Q3, Q4, Q5). The builder
can answer all in one answer.sh call — efficient for throughput.

## Patterns that slow the grill

### API timeouts on long answers
glm-5.2 sometimes times out processing a long multi-decision answer (400s+).
The builder needs to retry with `hermes --resume`. This costs ~5-10 min per occurrence.

### Question extraction failures
answer.sh fails to extract PO's question ~30% of the time (PO doesn't use `<Q>` tags
consistently). Builder falls back to reading the grill state file or kanban comments
to find the question text manually.

## Decision density benchmark

LeadPilot grill: 14 decisions across 5 branches in ~50 minutes.
- Branch 1 (statistical-evidence): 1 decision, 1 question
- Branch 2 (willingness-to-pay): 1 decision, 2 questions
- Branch 3 (customer-acquisition): 4 decisions, 5 questions
- Branch 4 (technical-feasibility): 4 decisions, 3 questions
- Branch 5 (prototype-scope): 4 decisions, 2 questions

Average: ~3.5 min per decision. Expect 10-20 decisions for a well-prepared dossier.
