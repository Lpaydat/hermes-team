# Dossier Delegation & Fact-Verification Patterns

Lessons from building and verifying the first dossier (LeadPilot, 2026-07-23).

## Delegation-extract-write fallback

Rich 13-section dossiers with web research can exhaust subagent tool-call limits before writing the file. The complete content is always preserved in the delegation summary at `~/.hermes-teams/startup/profiles/builder/cache/delegation/subagent-summary-*.txt`.

**Pattern:**
1. Delegate research to subagent with `role='leaf'`, clear output path, and existing signal data.
2. If subagent completes and writes the file → done.
3. If subagent hits tool-call limit → read the summary file, extract dossier content (starts at `# <Idea Name> (Dossier)` heading, ends before `Honest research limitations` footer), write locally.

With `delegation.max_iterations: 999` this is less common, but config changes only apply on next engine restart — subagents launched in the current session use the old limit. Always check the summary file.

## Pricing-page confusion pitfall (verified by independent fact-checker)

Researchers confuse adjacent dollar amounts on competitor pricing pages. Real example: Podium's pricing page shows "$96K additional monthly revenue" in a customer testimonial. The researcher recorded this as "$96/mo entry tier" and marked it "verified from pricing page." Actual entry price: $399/mo.

**Rule:** Always verify whether a dollar amount appears in a plan name/feature column or in a testimonial quote. Cross-check against the plan name in the page's JSON data. Add-on prices (e.g., "$49/mo payroll add-on") are NOT plan entry prices.

## Independent fact-verification outcomes (LeadPilot, first run)

- 20/26 claims VERIFIED (all Reddit/HN URLs real, all quotes exact word-for-word, all competitor financials correct)
- 3 claims DISPUTED (Podium pricing $96→$399, Podium valuation $1.5B→$3B, Thryv entry $49→$244)
- 3 claims UNVERIFIABLE (SBA stats blocked, $2,340 ROI no traceable URL, "58% after hours" is anecdotal Reddit not research)

The corrected data strengthened the thesis (Podium at $399/mo makes the $99-299 price point even more competitive). ~82% verification rate on first run.
