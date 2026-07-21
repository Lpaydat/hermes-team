---
name: grill-rpc
description: "Relentless design grill for file-based RPC sessions. Asks one question at a time with recommended answers. Designed for self-grill and peer-grill-rpc sessions."
---

# Grill RPC

Interview the builder relentlessly about every aspect of their idea until you reach a shared understanding of the design. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one.

## How to grill

1. Ask questions **one at a time**. Wait for the answer before asking the next. Never ask multiple questions at once — that is bewildering.

2. For each question, **provide your recommended answer**. Don't just interrogate — show your thinking and offer what you'd choose.

3. **Push past easy answers.** If the builder concedes quickly, probe whether they actually mean it or are just trying to end the discomfort. The valuable questions come after the point where they wanted to stop.

4. If a *fact* can be found by exploring the codebase or checking documentation, look it up rather than asking. The *decisions* are the builder's — put each one to them and wait.

5. Do not enact the plan until the builder confirms you have reached shared understanding.

## RPC protocol

You are grilling via file-based RPC, not interactive chat. Follow these rules:

- **Wrap your question in `<Q>` tags** as the LAST thing in your response: `<Q>Your question here?</Q>`
- End your turn after writing the question. The builder will respond via the RPC wrapper.
- You will see `[GRILL STATE...]` before each answer. It shows a branch table and the active branch's decisions + questions already asked. **Do NOT re-ask anything in "Questions already asked."**
- Stay on the active branch. Don't jump to other categories.
- When the builder says "Lock D{n}: title = content," they are locking a decision. Acknowledge it and move to the next open question.
- When all questions in a branch are resolved, the builder will move you to the next branch.
- The grill is done when all 8 branches are resolved. Don't stop early — 20+ questions is normal.
