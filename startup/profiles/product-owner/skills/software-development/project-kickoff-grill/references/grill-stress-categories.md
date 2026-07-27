# Grill Stress Categories

The checklist for adversarial grilling during project kickoff (Step 2 of project-kickoff). Every architecture decision must be challenged against these categories. The goal is to find the concrete scenario where the decision breaks — before it's baked into a spec.

These categories are derived from real gaps surfaced during the CRR POS v2 migration session (2026-07-26), where the PO skipped grilling and wrote a spec from discussion alone. The holes below are exactly what slipped through.

## 1. Single points of failure

**Question:** What happens when X dies? (Where X is each critical piece of infrastructure.)

**Examples:**
- Server hardware dies (Raspberry Pi, VPS, etc.) — what's the recovery procedure? How recent is the last backup? Can devices keep operating independently, and for how long before divergence makes reconciliation painful?
- Storage media fails (SD card, USB SSD) — is the database on the same media as the OS? If so, a disk failure takes down both.
- Network infrastructure (store router, switch) — does the app degrade gracefully when LAN is down? When internet is down?

**Failure mode if untested:** The system works perfectly until the day it doesn't, and then the store can't operate and there's no recovery plan.

## 2. Data loss under concurrency

**Question:** What happens when two devices modify the same record simultaneously?

**Examples:**
- Two cashiers edit the same product's price at the same time — which wins? Is the other change lost silently?
- Two devices record a payment and a charge against the same customer's debt — does last-write-wins silently overwrite one?
- Device A closes an order while Device B is still adding items to it — what happens on sync?

**Failure mode if untested:** Silent data corruption. Money disappears or duplicates with no error message, no audit trail.

**Known fix pattern:** Append-only ledger for anything money-related. The balance is derived (SUM of entries), never stored as a mutable field. Two concurrent entries both survive sync — no conflict.

**Known decision pattern — debt tracking:** If the system tracks customer debt, use **customer-level balance** (not order-level allocation). Staff sees "Customer A owes 650 total" and records a payment against the total. The original charge entries preserve which orders created the debt (for audit), but payment is always customer-level. This avoids cashier friction — retail debt runs on trust, and order-level allocation adds complexity for no real benefit at small scale. See `references/local-first-patterns.md` for the full pattern.

## 3. Money safety

**Question:** Can a sync conflict corrupt a balance? Can a failed transaction leave a partial state? Is money calculated correctly?

**Examples:**
- Debt balance stored as a mutable number — two devices both read 1000, one subtracts 500 (payment), one adds 300 (charge). Last-write-wins overwrites one. Result: 500 baht silently lost.
- Order total computed and stored — if items are added by Device B after Device A computed the total, the stored total is wrong.
- Cash drawer reconciliation — if the app crashes mid-sale, is the half-completed order recoverable or abandoned?
- **Per-line rounding silently overcharges** — old `OrderItem.total_price` uses `math.ceil(price * amount)` per line. Three items @ 25.50 each: per-line rounding gives 78, per-total rounding gives 77. The customer pays 1 baht more than either alternative. Over hundreds of transactions this is real money. Always check how rounding is applied — per-line vs per-total — and whether prices have decimals at all. If prices are already round (end in 0 or 5), rounding never triggers and it's moot.

**Failure mode if untested:** Financial discrepancies that are discovered weeks later during reconciliation, with no way to trace the cause. Or silent over/undercharging that erodes trust when customers notice.

**Known fix pattern:** Append-only ledger for anything money-related. The balance is derived (SUM of entries), never stored as a mutable field. Two concurrent entries both survive sync — no conflict.

## 4. Compliance and legal requirements

**Question:** Does the system meet legal/tax/regulatory requirements for this jurisdiction?

**Examples:**
- Thailand: Does the store need to issue ใบกำกับภาษี (tax invoices)? If so, does the schema support VAT calculation?
- Receipt numbering — are sequential, gap-free receipt numbers legally required? If so, how are they generated in a distributed offline-first system (where devices can't coordinate sequence numbers)?
- Data retention — are there legal requirements for how long sales records must be kept?

**Failure mode if untested:** The system works for daily operations but can't be used for tax filing, or requires manual re-entry of data into a compliant system.

## 5. Offline and degraded operation

**Question:** How long can devices operate without the server? What breaks first?

**Examples:**
- Pi dies at 9am Monday — can the store run all day on local-only? What about a week?
- Internet is down but LAN is up — does sync between devices still work (Pi is local)? Or does sync depend on internet?
- A device was offline for 3 days, comes back online — does it sync cleanly, or does the accumulated queue cause issues?

**Failure mode if untested:** The "offline-first" claim is untested beyond a few minutes. Real outages last hours or days.

## 6. Physical workflow edge cases

**Question:** What happens in the messy reality of a retail counter?

**Examples:**
- Hardware barcode scanner types into whatever field has focus — cashier is typing a customer name, scans a product, barcode text lands in the name field. How is this prevented? (Common fix: a dedicated hidden scanner-listener that captures input only when a specific mode is active.)
- Receipt printer goes out of Bluetooth range — does the app require a restart to reconnect? (The old crr-pos had exactly this bug.)
- Customer wants to split payment (part cash, part debt) — does the schema support multiple payment methods per order?
- Multiple staff share one device — how does shift handoff work? Does the first staff member log out, or does the device stay logged in as one person?

**Barcode scanning workflow (camera-based):**
- **Where does the scan button live?** If the camera opens per-item and closes after each scan, it's too slow for a pile of 15 items. Fix: continuous scan mode (camera stays open, each detected barcode adds the product, tap done to close).
- **Quantity entry vs continuous scan:** In continuous mode, scanning the same barcode twice within 2 seconds increments the existing line item (handles "I have 5 identical items, scan the same one 5 times"). For manual quantity entry, show a drawer (product name + unit + amount field) — the old crr-pos `OrderItemForm` component is the reference pattern.
- **Single vs multiple barcode matches:** If a barcode maps to exactly 1 product → add immediately (continuous) or open drawer (manual). If it maps to multiple products → show product list, pick one, then proceed.
- **Unbarcoded items:** In Thai retail/grocery, many items are loose goods (rice by kg, produce by pile) with no manufacturer barcode. The camera scanner is a nice-to-have for the minority of barcoded items; manual search + quantity is the primary input method. Don't over-invest in barcode UX if most products are unbarcoded.

**Multi-device collaboration (especially for local-first):** The single hardest pattern in local-first. Ask: "can two devices work on the same order simultaneously?" If yes, you need a concrete sync model for it — not "last-write-wins," which silently loses items. Options:
- **Append-only adds** (multiple devices add items independently, items are separate records that group in UI display) — simplest, works if devices only ADD
- **Opt-in realtime collaboration** (presence detection + explicit join button + realtime subscription for that order) — best UX, requires server reachable for collaboration. See `references/local-first-patterns.md` for the full pattern.
- **Soft lock** (one device at a time acquires a lock on the order) — simplest to implement, prevents concurrent edits entirely
Ask: "does the workflow involve only adding items, or also editing quantities, receiving money, and closing?" The answer determines which pattern fits.

**Failure mode if untested:** The system works in clean demos but creates daily friction in real use. Staff develops workarounds that bypass the system's controls.

## 7. Inventory and stock reality

**Question:** Does the system model the actual inventory workflow, or just pricing?

**Examples:**
- Does selling a product decrement a stock count? Or is this purely price-lookup-and-ring?
- Is there a stock-take / stock-adjustment workflow for when physical count doesn't match system count?
- How are damaged/expired goods recorded?
- Can a product be sold if the system shows zero stock? (For a store with loose items like produce, stock might not be unit-counted.)

**Decision pattern — defer stock counts:** If the old system has no stock quantity field (just name/price/unit), the store has operated without stock tracking. Don't add it unless the owner explicitly identifies stockouts/reorder pain. Adding stock counts to a local-first multi-device system roughly doubles sync complexity (concurrent decrements race). Better to defer to a later version as a deliberate feature.

**Failure mode if untested:** Either over-engineered (forcing stock counts on items sold by weight/piece with no real inventory tracking) or under-engineered (no stock awareness at all, leading to overselling or no reorder signals).

## 8. Debt and credit workflows

**Question:** If the system tracks customer debt, how does credit actually work at the counter — not in theory, but in the real daily flow?

**Examples:**
- **Partial payment at close** — customer has a 1200 baht order, pays 1000, owes 200. Does the system create a debt entry for the shortfall automatically? (It should.)
- **Standalone payment** — customer walks in later with 200 baht, no new order, just paying off debt. Is there a separate entry path for this?
- **FIFO allocation** — customer owes from 3 different orders (200+300+150=650), pays 400. Does the system clear oldest-first? Does the allocation freeze at payment time, or recompute when late-syncing orders appear?
- **Debt query** — can the owner get a list of all customers with outstanding balances instantly?
- **Multiple payment methods per order** — can a single order mix cash + debt (partial payment at close)? This is the norm in trust-based Thai retail (เขียนบัญชี), not an edge case.

**Stress test — late-syncing debt:** Staff A processes a 400 payment at 2:00 PM, allocating against Orders 001 and 005 (the only ones visible on their device). Device 2's Order 012 charge (150) syncs at 2:05 PM. The allocation must NOT retroactively recompute — the staff-customer agreement was "400 clears these specific orders." Late orders are simply additional debt. Fix: use optimistic concurrency control (pattern 9 in local-first-patterns.md) to pull freshest state before committing, but accept that allocation freezes at commit time.

**Decision pattern — customer-level balance:** Use customer-level balance, not order-level allocation, as the PRIMARY model. Staff sees total owed, records payment against total. The charge entries preserve order linkage for audit. Order-level FIFO allocation is a UI convenience for the debt page (select orders to pay off), not the underlying data model. See `references/local-first-patterns.md` §4.

**Failure mode if untested:** Debt records that don't match reality, allocations that shift retroactively and confuse staff, or money operations that corrupt under sync conflicts.

## How to use this checklist

1. For each architecture decision made in Step 1 (Discuss), run through all 8 categories.
2. For each category, ask: "does this decision survive this scenario?" If you're not sure, it's a grill question.
3. Present each challenge one at a time with a concrete failure scenario and your recommended answer.
4. Record the resolution. Decisions that held go into the spec. Decisions that changed go into the spec. Open questions go to the architect card.

## 9. Pricing model reality

**Question:** Does the old system's single price field hide a multi-price reality?

**Examples:**
- The old model has `price_per_unit` — but does the store actually have different prices for different customer types (wholesale vs retail, member vs non-member, bulk vs single)?
- Are discounts given informally (cashier adjusts price manually) or systematically (stored in the system)?
- Does the store's pricing have volume thresholds (buy 10+ = cheaper)?

**Decision pattern — dual pricing:** If the store has wholesale + retail, model both explicitly: `price_wholesale` (default) + `price_retail` (nullable). The cashier toggles which applies at add time. Never allow arbitrary manual price entry (fraud vector) — only system-defined prices. Record which price was used on the order item snapshot.

**Failure mode if untested:** You build a single-price system and the store can't use it without manual workarounds (writing different prices by hand, or the cashier mentally adjusting). The old system's single price field doesn't mean there's only one price — it might mean the second price was managed outside the system entirely (notebook, memory, handwritten). Ask the owner: "do all customers pay the same price for the same product?"

## Category index

1. Single points of failure
2. Data loss under concurrency
3. Money safety
4. Compliance and legal requirements
5. Offline and degraded operation
6. Physical workflow edge cases
7. Inventory and stock reality
8. Debt and credit workflows
