# Local-First Architecture Patterns

Design patterns for multi-device local-first apps, surfaced during the CRR POS v2 migration grill (2026-07-26) and subsequent design-council + owner review sessions. These are concrete solutions to problems that emerge when you move from server-first to local-first with 2-5 devices.

## 1. Hybrid sync: realtime for collaboration, polling for the rest

**Problem:** Polling every 3-5 seconds is fine for slow-changing data (product catalog, customer list, settings) but creates a collaboration gap for active operations (two staff adding items to the same order simultaneously).

**Solution:** Two sync modes:
- **Polling** (every 3-5s) for: products, customers, settings, order metadata, historical data
- **Realtime subscription** (SSE/WebSocket) for: items on a currently-active order, when multiple devices are collaborating

PocketBase has realtime subscriptions built in. The active order's items stream updates to all subscribed devices in ~200ms on LAN.

## 2. Opt-in realtime collaboration (presence + join)

**Problem:** Pure realtime for all orders wastes resources when most orders are single-device. Pure local-first breaks the "I can see what others have already added" collaboration need.

**Solution:** Explicit opt-in to realtime per order via presence detection:

1. Staff A opens Order 001 → pushes a presence signal ("I'm on Order 001") to the server, works in local mode
2. Staff B opens Order 001 → checks server → sees Staff A present → UI shows "Join Staff A" button
3. Staff B clicks Join → both devices subscribe to realtime updates for Order 001
4. Items added by either appear on both within ~200ms
5. When someone leaves (navigates away), they unsubscribe. If A leaves, B drops back to solo mode with a visible toast: "Staff A left — switched to solo mode"

**Known race condition:** If two devices open the same order within ~200ms (before either's presence signal lands), both go solo. Unlikely in real workflows (people join when they SEE someone else is busy, not within 200ms). Fallback: on sync, duplicate line items for the same product display grouped ("cooking oil × 3" + "cooking oil × 3" → shown as "cooking oil × 6"), with separate underlying records for audit.

**Degradation:** If realtime breaks (Pi down, WiFi drop), devices keep recording independently against local IndexedDB. On reconnect, sync merges everything. The presence system degrades gracefully — no presence checks means solo mode, which always works.

## 3. Append-only ledger for money and debt

**Problem:** Last-write-wins sync corrupts mutable balances. Device A records a 500 baht payment, Device B records a 300 baht charge. One silently overwrites the other. Money lost.

**Solution:** All financial state is an immutable log. `ledger_entries` records are NEVER updated or deleted — only appended.

```
{customer_id, order_id, entry_type: "charge"|"payment"|"void", amount, note, created_by, created_at, device_id}
```

- **Customer balance** is always `SUM(charges) - SUM(payments) - SUM(voids)`, derived on read, never stored as a mutable field.
- **Two concurrent entries** (payment + charge) both survive sync. No conflict possible.
- **A correction** is a new entry with `entry_type: "void"` referencing the original, not a deletion.
- **The ledger IS the audit trail.**

## 4. Customer-level debt balance (not order-level allocation)

**Problem:** Customer owes debt from multiple orders. When they make a payment, should staff allocate it to specific orders?

**Decision:** Customer-level balance. Staff sees "A owes 650 total," records a 400 payment, balance becomes 250. The payment isn't tied to a specific order — it reduces the customer's total. The original charge entries preserve which orders created the debt (for audit), but payment is always customer-level.

**Rationale:** Retail debt runs on trust and personal relationships. The customer owes the STORE, not specific orders. Order-level allocation adds cashier friction for no real benefit at small scale. This matches real Thai retail (เขียนบัญชี / "book account") workflows.

## 5. Soft lock for closing/payment

**Problem:** Two devices both try to close the same order and receive payment simultaneously. Total is computed wrong, money is collected twice, accounting breaks.

**Solution:** Only one device can close an order at a time. Acquire a soft lock: `locked_by: device_id`, `locked_at: timestamp`. Other devices see "closing on [device name]" and wait. Lock auto-expires after 10 minutes (crashed device doesn't permanently lock the order).

This is separate from the realtime collaboration pattern (which is about ADDING items). Closing is always single-device exclusive.

## 6. The VAT toggle trap

**Problem:** User asks for "an optional toggle to enable tax receipts (ใบกำกับภาษี)." A simple toggle is dangerous — Thai tax law requires sequential, gap-free tax invoice numbers. An accidental toggle-on burns a sequence number and creates an unexplained gap.

**Solution (if tax receipts are needed):**
- Design the schema for VAT from day one: prices stored VAT-inclusive (Thai retail standard), `tax_rate` field in store settings (default 7%)
- The toggle is owner-only, one-way, and irreversible without a recorded reason. Once `tax_enabled: true`, it stays on. Turning off requires owner auth + written justification in the audit trail.
- Tax invoice numbers are a SEPARATE counter from order numbers. They only start counting when the feature is enabled, and only increment when a receipt is explicitly printed as a tax invoice.
- **Cheaper insurance if VAT isn't needed yet:** store prices VAT-inclusive anyway (free), leave empty tax fields in the schema. Future VAT addition requires no price restructuring.

## 7. Printer reconnection state machine

**Problem:** Bluetooth printer goes out of range. App holds a dead GATT connection. Must restart app to reconnect (the exact bug in the old crr-pos).

**Solution:**
```
CONNECTED → (connection lost) → DISCONNECTED → (auto-retry every 5s) → CONNECTED | DISCONNECTED
```
- Listen for `gattserverdisconnected` (Bluetooth) or network error (WiFi ESC/POS)
- On disconnect: mark printer status as "disconnected," show badge in UI, queue print jobs
- Auto-retry connection every 5 seconds when disconnected
- No app restart required, ever
- **Prefer WiFi/network printers** if possible — no persistent connection to lose, multiple devices share one printer, range issues eliminated

**Platform limitation (discovered during design-council, 2026-07-26):** `navigator.bluetooth.getDevices()` (auto-reconnect without user gesture on cold-start) is behind experimental Chrome flag `#enable-experimental-web-platform-features`. Stock Android Chrome won't have it. **Accept one-tap-per-session for cold-start reconnect** — in-session auto-reconnect (disconnect→reconnect without page reload) works fully. After a PWA reload, staff taps "Connect printer" once. This is a massive improvement over the old restart-required behavior.

**WiFi ESC/POS infeasibility:** Browsers cannot do raw TCP (`net.Dial` to port 9100). "WiFi printer via fetch to IP:port" is impossible. If WiFi printing is needed, a **Pi proxy** is required — the Pi makes the TCP connection to the printer, the browser sends print data to the Pi via HTTP.

## 8. Backup and disaster recovery

**Problem:** The sync server (Raspberry Pi) is a single piece of hardware. SD cards corrupt, hardware fails, power surges happen. When it dies, all devices lose their sync target and divergence begins.

**Solution:** Layered backup strategy:
- **Daily encrypted backup to cloud** (e.g. Backblaze B2 at ~$0.005/GB) — automated cron job copies the SQLite file. Design council escalated to **hourly** for money-touching systems.
- **Second USB drive on the Pi** — local redundant copy, encrypted
- **Cold spare Pi** — have a second Pi ready for hardware swap
- **Devices must run a full business day without the server** — the local IndexedDB sync queue must be durable enough to hold a day of transactions
- **Recovery procedure:** fix/replace Pi → restore SQLite from backup → devices sync pending changes up. No data lost because devices held everything locally.

**Design principle:** The server is the sync target, NOT the source of truth during an outage. Each device's local DB is independently valid. The server reconciles — it doesn't own.

## 9. Optimistic concurrency control for money operations

**Problem:** Local-first means a device might make a money decision (debt payment, order close) based on stale data. Two devices could both close the same order with different amounts.

**Solution:** Pre-commit validation gate — money operations pull the freshest server state right before committing:

1. Open customer debt page → pull latest ledger from server immediately (not stale local data)
2. Staff selects orders, enters amount
3. Before submit → check server: "has anything changed for this customer since I loaded?"
4. If nothing changed → submit with confidence
5. If something changed → pull latest, recompute, show staff the updated state, require re-confirmation

This eliminates stale-data money decisions whenever the server is reachable. The allocation is always made against the freshest state at the exact moment of commitment.

## 10. Three-state sync badges for money operations

**Problem:** Staff and owner need to know instantly whether a sale has been reconciled with the server, or if it's still local-only.

**Solution:** Every money-bearing record has a visible `sync_status`:
- 🟢 **synced** — server has it, fully reconciled, validated
- 🟡 **pending** — local only, written during offline, waiting for server sync. Warning toast on creation: "Saved locally — will sync when server is back."
- 🔴 **conflict** — two conflicting versions exist (e.g. two offline devices closed the same order with different amounts). Surfaces to owner for manual resolution.

Background sync retries every few seconds. On success: badge turns green. On conflict: badge turns red.

**Design principle:** Non-money operations (ringing items, searching products) are pure local-first and don't need badges. Only money operations carry the three-state badge. This cleanly separates "works offline" from "needs validation."

## 11. Money operations with offline fallback (pending state)

**Problem:** Full offline support for money operations conflicts with the pre-commit validation gate (pattern 9). You can't validate against a server you can't reach. But the store network may be unstable.

**Solution:** Money operations try server validation first, fall back to local save with `sync_status: pending`:
- **Server reachable:** pre-submit validation → atomic commit → `synced` (green badge)
- **Server unreachable:** save locally → `pending` (amber badge) → background retry → `synced` on success
- **Conflict (two offline closes):** `conflict` (red badge) → owner resolves

The customer walks away happy either way. Staff and owner always know exactly which sales haven't been reconciled. The pending state + paper receipt is the floor — the sale isn't lost even if the device crashes.

## 12. Auto-lock with PIN for shared devices

**Problem:** Staff accounts are new. A cashier finishes their shift, forgets to log out. Next morning, another cashier picks up the device and is still logged in as the wrong person. Every sale is attributed incorrectly.

**Solution:** Auto-lock after inactivity (default 30 min), with PIN re-entry (not full username/password):
- Lock screen shows "Device locked — last user: [name]"
- Staff enters 6-digit PIN to resume as themselves, or taps "switch user" for full login
- PIN is quick to enter at the counter — not a friction point
- **Owner role does NOT auto-logout** — remote sessions persist until explicit logout. BUT destructive operations (deactivate device, change settings, delete user) require re-auth even for owner.
- **PIN security:** bcrypt-hashed (never plaintext), cached locally in Dexie for offline unlock, rate-limited (5 wrong → 5min lockout)

## 13. Order item snapshot immutability

**Problem:** Staff closes Order 001 with "Cooking Oil × 3 @ 80 baht." Two months later, the product price changes to 90 baht. If the order receipt derives the price from live product data, it now shows 90 baht — a historical lie.

**Solution:** `order_items` stores `product_name`, `unit`, and `price_per_unit` as **snapshots at time of sale**. These fields are NEVER derived from live product data after the order closes. The product can be renamed, repriced, or deactivated — closed orders remain immutable snapshots.

**Companion rule — deactivate, never delete:** Products are only ever deactivated (status: inactive), never permanently deleted. Deactivation hides them from ordering/search but all historical orders remain fully readable. Deletion risks orphaned order items pointing to a nonexistent product.

**Grill check:** Verify the old system's `OrderItem` model uses snapshot fields vs optional fields that fall back to live product data. If fields are optional (`productName?`), the UI likely fetches live data in some paths — that's the bug.

## 14. Timestamp-based receipt identification

**Problem:** Sequential receipt numbers require server coordination (to avoid collisions across offline devices). This conflicts with offline money operations if you want receipts to work fully offline.

**Solution:** Use the order's `closed_at` timestamp as the receipt identifier. No sequential counter, no server coordination, no offline collision risk. A receipt is uniquely identified by when it was closed. Simple, local-first, works offline.

**When NOT to use this:** If the store requires legally compliant tax invoices (ใบกำกับภาษี) with sequential, gap-free numbering, timestamps don't satisfy the requirement. Use server-assigned sequential numbers and accept that receipt finalization requires connectivity. But for a simple บิลเงินสด (cash bill), timestamps are sufficient and simpler.

## 15. Delta polling (check updated_at, pull only changes)

**Problem:** Polling every N seconds by fetching the full catalog is wasteful when changes are infrequent. For a product catalog with hundreds of records, fetching all of them every 10 seconds is bandwidth overkill.

**Solution:** Delta polling protocol:
1. Device sends one lightweight request: "my latest local `updated_at` is X"
2. Server checks: "do I have any records newer than X?"
3. If yes → server returns ONLY the changed records (delta)
4. Device merges delta into local IndexedDB
5. If device has local-only changes → push them in the same cycle

A quiet catalog (no changes) costs one tiny timestamp check every poll cycle. A price update propagates within one poll interval. Bandwidth is proportional to changes, not catalog size. Works for products, customers, and any collection with an `updated_at` field.

## 16. Time-boxed local sync (rolling window)

**Problem:** A new device joins the store. First login tries to sync 3 years of order history into IndexedDB. Hundreds of megabytes, device stuck loading while cashier waits. But daily operations only need recent orders.

**Solution:** Time-boxed sync with a rolling window:
- **Always sync locally:** all active products, all customers, all store settings, all ledger entries (or last 12 months)
- **Time-boxed:** orders from last N months (e.g. 3 months) sync to local Dexie
- **Server-queryable:** older orders are searchable from the device via a server query, but NOT stored locally
- **Auto-sliding window:** old records age out of local Dexie as time passes, but remain in the server DB permanently

The trade-off: searching for an order older than the window requires a network round-trip to the server. But that's a rare operation — the daily flow never touches old data.

**Grill check:** Ask the user "how far back does a device need order history locally?" and "how important is searching old orders from the device vs an owner-only report?" The answer determines the window size.

## 17. Business day rollover

**Problem:** "Today's sales" reports using calendar midnight as the cutoff misattribute sales near store close. A sale at 3:10 PM on a store that closes at 3 PM shouldn't count as "today" if the drawer was already counted.

**Solution:** Configurable business day boundaries:
- `business_day_start` and `business_day_end` in store settings (e.g. "04:00" and "15:00")
- "Today's sales" = sales between business_day_start and business_day_end on this calendar day
- Sales after close count toward the NEXT business day's report
- Matches how the cash drawer actually works — counting the drawer at close IS the end of the day

This is a settings decision, not a schema decision. The order records keep absolute timestamps; the report query applies the business-day window.

## 18. Dual pricing (wholesale default + retail)

**Problem:** Many retail stores have two prices per product — wholesale and retail (small-buy). Not every product has both. The cashier needs to quickly select which price applies when adding to an order.

**Solution:**
- Products have `price_wholesale` (always set — this is the DEFAULT) and `price_retail` (nullable — null means single-price wholesale item)
- Add drawer defaults to wholesale. A toggle button switches to retail.
- **Clear visual marker** (color/tag) shows which price is currently active — prevents accidental wrong-price charges.
- Single-price products (no retail price) skip the toggle entirely — the fast path stays fast.
- `order_items` gains `price_type: "wholesale" | "retail"` to record which price was used, plus the snapshotted `price_per_unit`.
- **No manual price overrides** — the cashier selects wholesale or retail but cannot enter a custom amount. Server-side validation at commit gate: `price_per_unit` must equal EITHER `price_wholesale` OR `price_retail` from the product record.

**Owner insight (CRR POS v2):** 80% of sales are wholesale. Defaulting to wholesale makes the fast path the common path. The toggle is only for the 20% walk-in retail customers. Cashier judgment handles edge cases (longtime customer getting wholesale on small quantity) — no quantity threshold enforcement needed.

## 19. Debt allocation strategies (FIFO + smallest-first)

**Problem:** When a customer owes debt across multiple orders and makes a partial payment, how should the system allocate it? FIFO (oldest first) is standard, but some stores prefer clearing smaller debts first to reduce the number of outstanding orders.

**Solution:** Offer TWO strategies, staff-selectable per payment:
1. **FIFO** — clear oldest debts first (standard)
2. **Smallest-first** — clear smaller debts first (reduces order count)

Staff selects which orders to pay (checkboxes), picks the strategy, sees the allocation breakdown before confirming. The system allocates across ONLY the selected orders.

**Offline behavior:** Debt payments work offline (saved as `pending`). On sync, the server re-runs the selected strategy with current debt amounts and overwrites `resolved_debts` authoritatively. If two payments collide (rare — 1 counter, 1 person), the second re-allocates against whatever's left. Total balance is always correct; per-order breakdown may shift.

**Owner insight (CRR POS v2):** "This should not be much issue as we have only 1 counter and most of the time, it's only me or single staff responsible for debt payment." — The concurrency risk that the design council flagged as CATASTROPHIC (concurrent payments producing wrong per-order allocation) doesn't apply at this store's scale. The owner's domain knowledge overrides the theoretical risk.

## When these patterns apply

These patterns are relevant for ANY local-first multi-device application, not just POS. The key trigger is: "multiple devices write to local state and sync to a shared server." If that's the architecture, these patterns apply regardless of domain.
