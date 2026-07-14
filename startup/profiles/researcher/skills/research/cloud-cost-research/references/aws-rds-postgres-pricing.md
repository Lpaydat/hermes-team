# AWS Managed PostgreSQL — pricing & multi-tenancy cost factors

Condensed knowledge bank captured **2026-07-12** from primary AWS sources.
Cloud prices change — re-verify the $ figures before quoting in a fresh
artifact. The structural facts (productFamily values, price-field paths,
max_connections formula, quotas, PgBouncer semantics) are stable.

## Primary sources (all accessed 2026-07-12)
- **AWS Price List API (official JSON):** `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/us-east-1/index.json` (regional offer file, ~25MB, public HTTP GET, no auth).
- **Aurora pricing page (worked examples = the source for ACU rates):** https://aws.amazon.com/rds/aurora/pricing/
- **RDS quotas & limits doc:** https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Limits.html
- **PgBouncer config reference:** https://www.pgbouncer.org/config.html

## RDS for PostgreSQL — instance pricing (us-east-1, On-Demand, Single-AZ)

| Instance | vCPU | RAM | $/hr (OD) | $/mo (OD, ×730) | 1yr RI No-Upfront $/hr | $/mo (RI) |
|---|---|---|---|---|---|---|
| db.t3.micro | 2 | 1G | $0.0180 | $13 | $0.0129 | $9 |
| db.t3.small | 2 | 2G | $0.0360 | $26 | $0.0258 | $19 |
| db.t3.medium | 2 | 4G | $0.0720 | $53 | $0.0517 | $38 |
| db.t3.large | 2 | 8G | $0.1450 | $106 | $0.1034 | $75 |
| db.t4g.large | 2 | 8G | $0.1290 | $94 | $0.0930 | $68 |
| db.m5.large | 2 | 8G | $0.1780 | $130 | $0.1140 | $83 |
| db.m5.xlarge | 4 | 16G | $0.3560 | $260 | $0.2280 | $166 |
| db.m5.2xlarge | 8 | 32G | $0.7120 | $520 | $0.4560 | $333 |
| db.m5.4xlarge | 16 | 64G | $1.4240 | $1,040 | $0.9121 | $666 |
| db.r5.large | 2 | 16G | $0.2500 | $182 | $0.1444 | $105 |
| db.r5.xlarge | 4 | 32G | $0.5000 | $365 | $0.2888 | $211 |
| db.r5.2xlarge | 8 | 64G | $1.0000 | $730 | $0.5775 | $422 |
| db.r5.4xlarge | 16 | 128G | $2.0000 | $1,460 | $1.1550 | $843 |
| db.r5.8xlarge | 32 | 256G | $4.0000 | $2,920 | $2.3100 | $1,686 |
| db.m6i.large | 2 | 8G | $0.1780 | $130 | $0.1140 | $83 |
| db.r6i.large | 2 | 16G | $0.2500 | $182 | $0.1444 | $105 |

Multi-AZ (one standby) ≈ 2× the instance $/hr. (t3/t4g are burstable; "Unlimited mode" charges $0.075/vCPU-hr beyond baseline.)

## RDS storage pricing (us-east-1, Single-AZ)
- **gp3 (General Purpose SSD):** $0.115/GB-month + $0.02/provisioned-IOPS-month (baseline 3000 IOPS included).
- **gp2:** $0.115/GB-month (IOPS scale with size).
- **io1:** $0.125/GB-month + $0.10/IOPS-month.
- **io2:** $0.125/GB-month + $0.10/IOPS-month.
- **Magnetic (legacy):** $0.10/GB-month.
Multi-AZ doubles storage cost. RDS storage 20 GiB → 64 TiB; gp3 3k–256k IOPS.

## Aurora (PostgreSQL-compatible) pricing (us-east-1)

**Provisioned instances** (sample, Single-AZ):
| Instance | $/hr |
|---|---|
| db.r6g.large | $0.260 |
| db.r6i.large | $0.290 |
| db.r5.large | $0.290 |
| db.r5.2xlarge | $1.160 |
| db.t3.medium | $0.082 |

**Serverless v2** (NOT in the `Hrs` unit — read from pricing-page worked examples):
- **Aurora Standard:** **$0.12 / ACU-hour** + $0.10/GB-month storage + **$0.20 / million I/O requests**.
- **Aurora I/O-Optimized:** **$0.156 / ACU-hour** + $0.225/GB-month storage + **$0 I/O**.
- 1 ACU ≈ 2 GiB RAM + corresponding CPU. Granularity 0.5 ACU, billed per second, min 0.5 ACU, can scale to 0 ACU (idle). Max 256 ACUs/cluster.
- Switching threshold: I/O-Optimized wins if I/O spend > 25% of total Aurora spend (up to 40% savings).

## The critical multi-tenancy insight: DB-per-tenant ≠ N instances

**Multiple logical databases run on a single instance/cluster.** You pay for ONE instance; N tenant databases share its compute + storage. Database-per-tenant does NOT force N paid instances. The cost levers are connection count and account quotas, not instance count.

### PostgreSQL `max_connections` on RDS (the hard ceiling for shared-instance DB-per-tenant)
- Default parameter-group formula: **`LEAST({DBInstanceClassMemory/9531392}, 5000)`** — ≈ RAM_bytes ÷ 9.5 MB, capped at 5,000. Range 6–262,143.
- Worked examples (default formula):
  - db.t3.medium (4GB) → ~400 max connections
  - db.m5.large (8GB) → ~800
  - db.r5.large (16GB) → ~1,600
  - db.r5.2xlarge (64GB) → ~6,500 → but capped at 5,000
- Raise by editing the parameter group (to max 262,143), but each connection ≈ 10 MB RAM → memory-bound.
- **Aurora Serverless v2** scales connections with ACUs and can handle thousands; better fit if tenant count × per-tenant-pool is large.

### Account quotas (per region; all adjustable via Service Quotas)
- **DB instances: 40** (ap-south-1: 20). Adjustable.
- **DB clusters: 40.** Adjustable. (This bounds the *true* instance-per-tenant model — you must request a quota increase long before 1,000 instances.)
- There is **no documented hard limit on the number of logical databases per instance** — it is bounded in practice by `max_connections`, catalog/catalog-bloat memory, and `shared_buffers`. 1,000 databases on one well-sized instance is operationally feasible.

### PgBouncer semantics for DB-per-tenant
- Configure one `[databases]` entry per tenant database. Backend connection pool is **per (user, database) pair**.
- `default_pool_size` (default **20**) — max server connections per user/database pair.
- `max_db_connections` (default **0** = unlimited) — cap per database regardless of user.
- `max_client_conn` (default unlimited) — total client connections PgBouncer will accept; may need OS `ulimit -n` bump.
- `pool_mode = transaction` collapses N tenants' backends into a small shared pool but **breaks** session features (advisory locks, temp tables, `SET`, prepared statements that span transactions). For a financial ledger app that likely uses transactions + session features, prefer `pool_mode = session` or `transaction` only if the app is pooler-clean.
- Total backend connections ≈ tenants × `default_pool_size`. At 1,000 tenants × 20 = 20,000 — far above a single instance's `max_connections`. Mitigate with smaller per-tenant pool size (e.g. 2–5) or sharded PgBouncer.

## Storage overhead per tenancy model (structural, not vendor-priced)
- **Shared-DB (tenant_id):** one set of tables/indexes; indexes span all tenants. Best index utilization; tenant-agnostic page sharing. Lowest overhead.
- **Schema-per-tenant:** N copies of every table + index definition in `pg_class`/`pg_depend`; catalog bloat grows linearly with tenant count. `VACUUM`/`ANALYZE` runs per schema. Moderate overhead, plus heavier planning cost.
- **Database-per-tenant:** each DB has its own catalog (copied from `template1`), pg_authids, autovacuum workers, connection overhead. A near-empty Postgres DB ≈ 8–30 MB of catalog overhead → ×1,000 ≈ 8–30 GB of pure overhead before any tenant data. Shared buffers get spread across N catalogs → lower cache hit ratio per tenant unless instance RAM is scaled.

## What to verify on next use
- Re-pull the regional offer JSON (prices refresh ~daily) for any $ figure.
- Re-check the Aurora Serverless ACU rate against the current pricing-page worked example.
- RDS DB-instance quota may have been raised since capture.
