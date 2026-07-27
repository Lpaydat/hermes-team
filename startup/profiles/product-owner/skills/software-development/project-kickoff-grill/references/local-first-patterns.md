# Local-First Patterns for Multi-Device Apps

19 concrete architecture patterns for multi-device local-first applications. Use these during grilling to challenge architecture decisions with real failure modes.

## Sync patterns

- **Hybrid sync** — don't force everything through a single sync engine. Read-heavy data (catalog) can cache-and-poll while write-heavy data (orders) uses realtime sync. Mixing strategies per data type prevents a single sync failure from blocking all operations.
- **Opt-in realtime collaboration** — realtime sync is opt-in per entity, not global. A POS terminal doesn't need to see another terminal's order in realtime — it needs its own orders to persist reliably. Reserve realtime for entities where collaboration is the actual workflow (shared inventory counts).
- **Append-only ledger** — money operations are append-only. Never UPDATE a balance; always INSERT an adjustment. Reconciliation computes the sum. This makes sync conflicts recoverable (last-write-wins on an append is a missed entry, not a corrupted balance).
- **Delta polling** — instead of syncing everything, poll for deltas since last-seen timestamp. Reduces bandwidth on flaky connections. Pair with a rolling sync window (don't keep deltas forever — GC after N days).
- **Rolling sync window** — keep only N days of delta history. Older deltas are assumed reconciled. Prevents the sync log from growing unbounded.
- **Optimistic concurrency control** — each entity carries a version number. On sync, if the server version is newer, reject the local write and force conflict resolution. Never silently merge.

## Money safety patterns

- **Customer-level debt balance** — debt lives at the customer level, not the order level. A partial payment reduces the customer's total debt, not a specific order's. FIFO allocation (oldest debt first) is a policy choice, not a structural constraint.
- **Debt allocation (FIFO + smallest-first)** — when applying a partial payment, allocate to oldest debt first (FIFO), then smallest balance first (to clear whole orders). Document the chosen policy in the spec — the verifier checks this.
- **Money offline fallback** — when the sync server is down, money operations must still work locally. Receipts print with a local sequence number. When sync resumes, reconcile by sequence. Never block a sale because the server is unreachable.
- **Price rounding** — VAT-inclusive prices can produce fractional units at wholesale quantities. Specify rounding mode (banker's rounding, not half-up) and where it applies (per-line, per-order). The old model's `price_per_unit` may not expose this.
- **Dual pricing (wholesale/retail)** — a single `price_per_unit` field often hides a dual-price reality. Wholesale default + retail nullable is common. Ask the owner, don't assume.

## Operational patterns

- **Soft lock for closing** — when a terminal is closing its shift, set a soft lock on its orders. Other terminals can still read but get a "being reconciled" badge. Lock auto-expires after N minutes to prevent stuck states.
- **Business day rollover** — define when a "day" ends for reporting purposes. Is it midnight? Last sale before close? The first sale after a gap? This affects daily totals, debt aging, and inventory snapshots.
- **Three-state sync badges** — every entity shows one of three states: synced (green), pending (yellow), conflict (red). Never just "saved" — the user must know whether their data is safe.
- **Auto-lock with PIN** — terminals auto-lock after N minutes of inactivity. PIN to unlock, not password (faster for counter staff). Override available for admin.
- **Timestamp receipt ID** — receipt IDs are timestamp-based (YYYYMMDDHHMMSS + terminal ID), not sequential integers. Prevents collisions across offline terminals and makes receipt chronological order deterministic.
- **Order item snapshot immutability** — when an order is placed, snapshot the product name and price INTO the order item. Never reference the live product record. If the product price changes later, old receipts still show what was actually charged.
- **VAT toggle trap** — if the system has a "VAT inclusive" toggle, make sure toggling it doesn't silently change stored prices. The toggle affects DISPLAY only; storage is always one canonical form.
- **Backup/DR** — define what happens on total device failure. Is there a nightly export? Can another terminal import it? How recent is the last backup? The owner must know the RPO (recovery point objective) — "you lose at most N hours of data."
- **Printer reconnection (cold-start limitation)** — if the BT printer disconnects mid-shift, reconnection should be automatic. But the first receipt after reconnection may fail silently (cold start). Print a test receipt on reconnect to verify.
