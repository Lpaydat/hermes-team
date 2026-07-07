# Digest Format

The Telegram digest template. Load this when composing the Phase 5 message of the scout.

## Template

```
📡 AI Research Digest — YYYY-MM-DD (Weekday)

📊 Today: N items scouted | N notable | N signal tracked

🔬 QUEUED FOR DEEP RESEARCH:
1. **Title** — Why it matters (one line)
   🔗 link | 📋 kanban task filed
2. ...

📰 NOTABLE:
• Title — takeaway (link)
• ...

⚡ SIGNAL (tracked in DB):
• Title (link)
• Title (link)
• ...

💡 CONNECTION/GAP SPOTTED:
One paragraph on an interesting trend, contradiction, or under-explored
area noticed across today's sources.

---
🤖 Scouted by Research Agent | Wiki: ~/vault/ (curated knowledge only)
```

## Rules
- If the message exceeds 4096 chars (Telegram limit), split into two messages.
- Always include the 💡 section — even if minor, surface it.
- "🆕 New source:" and "🆕 Emerging:" lines go after SIGNAL if found.
- The 🔬 section is the key value-add — it tells the user what's worth their attention.
