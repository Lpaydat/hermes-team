---
name: cloud-cost-research
description: Research and compare real cloud-provider pricing (AWS, GCP) for architecture/cost decisions. Use the official pricing APIs (AWS Price List JSON bulk-offer files, GCP billing catalog) instead of scraping marketing pricing pages — those pages render pricing tables client-side and yield empty DOMs under static extraction.
---

# Cloud cost research

Use when the task is to compare, verify, or model cloud service costs (compute instances, managed DBs, storage, I/O) for an architecture decision, RFP, or cost table. This is NOT for "what is X" lookups that a single web page answers.

## Core principle: pull from the pricing API, not the marketing page

AWS and GCP marketing pricing pages (`aws.amazon.com/<service>/pricing/`, `cloud.google.com/<service>/pricing`) render their price **tables via JavaScript widgets** that require region/tab interaction. A static fetch or DOM scrape returns descriptive prose but **empty pricing tables** (verified 2026-07-12 on the RDS + Aurora pricing pages: `document.querySelectorAll('table').length === 0` even after clicking expand headers). Vision analysis of the page also frequently fails or isn't available.

The reliable structured source is the provider's **pricing catalog API**.

## AWS — Price List (Bulk API)

Official docs: https://docs.aws.amazon.com/pricing/latest/userguide/price-list-api.html

**URL pattern (regional offer file, GET):**
```
https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<ServiceCode>/current/<region>/index.json
```
- `<ServiceCode>` examples: `AmazonRDS`, `AmazonEC2`, `AmazonAurora`, `AmazonDynamoDB`
- `<region>` e.g. `us-east-1`. (Note: the bare `.../current/index.json` is the ~496MB global file — prefer the regional file, ~25MB for RDS.)
- `curl -s 'https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/us-east-1/index.json' -o /tmp/rds.json`
- These are plain HTTP GETs — no auth, no signing. A POST to that host 403s.

**GOTCHAS (all verified 2026-07-12 against AmazonRDS us-east-1):**
1. The RDS instance `productFamily` value is literally **`"Database Instance"`** — NOT `"DB Instance"` (which is what the docs and pricing page call them). Filtering on `"DB Instance"` returns **zero** products. `Aurora` storage is `productFamily: "Database Storage"`; provisioned IOPS is `"Provisioned IOPS"`.
2. The price is at **`terms.OnDemand[<sku>][<termId>].priceDimensions[<rateId>].pricePerUnit.USD`** — and the USD value is a **STRING** (`"0.1780000000"`), not a float. There is no `price` key; it's `pricePerUnit`. The hourly dimension has `unit: "Hrs"`.
3. vCPU and memory are **directly in the product `attributes`** (`attributes.vcpu`, `attributes.memory` e.g. `"32 GiB"`) — no need to maintain a side table of instance specs.
4. Reserved Instance terms live in `terms.Reserved`; filter by `termAttributes.LeaseContractLength` (`"1yr"`/`"3yr"`) and `termAttributes.PurchaseOption` (`"No Upfront"`/`"Partial Upfront"`/`"All Upfront"`).
5. **Aurora Serverless v2 does NOT appear as an `Hrs` unit** — its `ServerlessV2` products return `None` for the hourly lookup. Aurora Serverless v2 is priced **per ACU-hour**. Find the ACU rate in the **pricing page worked examples** (the `/rds/aurora/pricing/` prose), not the Price List `Hrs` field. As of 2026-07-12: **$0.12/ACU-hour (Aurora Standard)**, **$0.156/ACU-hour (I/O-Optimized)**, 0.5 ACU granularity, billed per second, min 0.5 ACU.
6. Dedupe by `(usagetype, instanceType, deploymentOption)` — the same logical price appears under several SKUs (e.g. Aurora IO-optimized vs Standard variants).

**Use the reusable extractor:** `scripts/aws_pricing_extract.py` — parameterized by service/region/engine, bakes in all six gotchas above. Run it; don't hand-parse from scratch each time.

## AWS — instance + storage units to model

For a managed-Postgres cost table you need: instance $/hour (×730 for monthly), storage $/GB-month, and I/O (Aurora charges $/million requests on Standard, $0 on I/O-Optimized; RDS gp3/io2 charges per provisioned IOPS-month). Single-AZ vs Multi-AZ roughly doubles instance + storage cost.

## GCP — Cloud Billing Catalog API

`https://cloudbilling.googleapis.com/v1/services` → list services → `services/<id>/skus`. Requires an API key / service account (auth required, unlike AWS). For a one-off, the Cloud SQL pricing page text is more scrapable than AWS's, but still prefer the SKU API for structured data.

## Managed-DB multi-tenancy cost modeling (critical insight)

A frequent question: does **database-per-tenant** require N paid instances? **No.** Both RDS and Aurora (and Cloud SQL) allow **multiple logical databases on a single instance/cluster** — you pay for ONE instance and N databases share its storage/compute. The cost lever for DB-per-tenant is NOT instance count; it is:

1. **`max_connections`** — PostgreSQL on RDS defaults to `LEAST({DBInstanceClassMemory/9531392}, 5000)` (≈ RAM_bytes/9.5MB, capped 5000). Aurora Serverless v2 scales connections with ACUs (thousands). DB-per-tenant + a pooler that opens ≥1 backend conn per tenant DB means tenant count is bounded by this number.
2. **Account quotas** — RDS default **40 DB instances / region** and **40 DB clusters / region** (adjustable via Service Quotas). These bound the *true* database-per-tenant-on-separate-instances model, not the shared-instance model.
3. **PgBouncer config** — `default_pool_size` is **per user/database pair** (default 20); `max_db_connections` is **per database** (default 0/unlimited). For DB-per-tenant you configure one `[databases]` entry per tenant; total backend connections ≈ tenants × pool_size. Transaction-mode pooling (`pool_mode = transaction`) collapses this drastically but breaks session-level features.
4. **Storage overhead** — DB-per-tenant + schema-per-tenant duplicate per-database/per-schema catalog objects (system catalogs, `template1` overhead, per-tenant indexes) vs shared-DB's single set of shared indexes. Roughly constant per-DB overhead (~8–30MB for a near-empty Postgres DB) × N.

## Workflow

1. Identify the service codes and the dimensions to model (instance, storage, I/O, connections).
2. `curl` the regional offer JSON; run `scripts/aws_pricing_extract.py` with the right filters.
3. For Aurora Serverless / per-unit services not in `Hrs`, read the worked examples on the pricing page for the unit rate.
4. Cross-check any `max_connections` / quota claims against the official limits doc (`docs.aws.amazon.com/.../CHAP_Limits.html`) and PgBouncer config (`pgbouncer.org/config.html`).
5. Record the actual numbers + source URL + access date in a `references/<topic>.md` so future sessions don't re-fetch. Pricing pages change; the access date is mandatory.

## Pitfalls

- **Scraping the pricing page → empty tables.** Don't. Use the Price List API.
- **Filtering on `"DB Instance"`.** The real value is `"Database Instance"`.
- **Reading `price.USD`.** It's `pricePerUnit.USD` and it's a string.
- **Expecting Aurora Serverless in the `Hrs` unit.** It's per-ACU-hour; get it from the page examples.
- **Forgetting the access date.** Cloud prices change; an undated number is useless as evidence.
- **Confusing "database-per-tenant" with "instance-per-tenant."** They are different cost regimes. Multiple DBs per instance is the cheap path; N instances is only forced by hard isolation/compliance, not by the model itself.

## Support files

- `scripts/aws_pricing_extract.py` — reusable AWS Price List extractor (service/region/engine filters, handles all gotchas above).
- `references/aws-rds-postgres-pricing.md` — condensed pricing knowledge bank for AWS managed Postgres (RDS + Aurora Serverless v2 + storage + multi-tenancy cost factors), captured 2026-07-12.
