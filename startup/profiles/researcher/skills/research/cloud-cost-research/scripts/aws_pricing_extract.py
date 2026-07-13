#!/usr/bin/env python3
"""
AWS Price List (Bulk API) extractor for managed-service cost research.

Pulls the regional offer JSON for a service/region and prints a clean table of
instance-type + storage pricing. Built from hard-won gotchas found 2026-07-12;
see SKILL.md "GOTCHAS" section for why each filter is shaped this way.

Usage:
    python3 aws_pricing_extract.py --service AmazonRDS --region us-east-1 \
        --engine PostgreSQL --out /tmp/rds_prices.txt

The regional offer file (~25MB for RDS) is cached at /tmp/aws_<svc>_<region>.json
and re-used on subsequent runs; pass --refresh to force re-download.

Requires: requests (or fall back to urllib). No AWS credentials needed —
pricing.us-east-1.amazonaws.com is public, plain HTTP GET.
"""
import argparse, json, re, sys, urllib.request
from collections import defaultdict


def fetch_offer(service: str, region: str, refresh: bool, cache: str) -> dict:
    import os
    if refresh or not os.path.exists(cache):
        url = f"https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{service}/current/{region}/index.json"
        print(f"Downloading {url} ...", file=sys.stderr)
        urllib.request.urlretrieve(url, cache)
    with open(cache) as f:
        return json.load(f)


def hourly(terms: dict, sku: str) -> tuple:
    """Return ($/hr_OnDemand, description) for a SKU. Reads pricePerUnit.USD (a STRING)."""
    for _tid, term in terms.get("OnDemand", {}).get(sku, {}).items():
        for _rid, dim in term.get("priceDimensions", {}).items():
            if dim.get("unit") == "Hrs":
                ppu = dim.get("pricePerUnit", {})
                if "USD" in ppu:
                    return float(ppu["USD"]), dim.get("description", "")
    return None, None


def reserved_hourly(terms: dict, sku: str, lease="1yr", purchase="No Upfront") -> float:
    for _tid, term in terms.get("Reserved", {}).get(sku, {}).items():
        ta = term.get("termAttributes", {})
        if ta.get("LeaseContractLength") != lease or ta.get("PurchaseOption") != purchase:
            continue
        for _rid, dim in term.get("priceDimensions", {}).items():
            if dim.get("unit") == "Hrs":
                ppu = dim.get("pricePerUnit", {})
                if "USD" in ppu:
                    return float(ppu["USD"])
    return None


def parse_mem(s: str) -> float:
    m = re.match(r"([\d.]+)", s or "")
    return float(m.group(1)) if m else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--service", default="AmazonRDS", help="AWS service code, e.g. AmazonRDS, AmazonEC2")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--engine", default="PostgreSQL", help="databaseEngine filter, e.g. PostgreSQL, Aurora PostgreSQL")
    ap.add_argument("--out", help="write the table to this path as well as stdout")
    ap.add_argument("--refresh", action="store_true", help="re-download the offer file")
    ap.add_argument("--cache", help="override cache path")
    ap.add_argument("--families", default="t3,t4g,m5,m6i,r5,r6i,r6g,c6i",
                    help="comma instance-family prefixes to include (regex: db.(fam).)")
    args = ap.parse_args()

    cache = args.cache or f"/tmp/aws_{args.service}_{args.region}.json"
    data = fetch_offer(args.service, args.region, args.refresh, cache)
    products, terms = data.get("products", {}), data.get("terms", {})

    # GOTCHA: RDS instances use productFamily "Database Instance", NOT "DB Instance".
    fam_re = re.compile(r"\.(" + "|".join(args.families.split(",")) + r")\.")

    instances = defaultdict(lambda: {"vcpu": "?", "mem": 0, "sa": None, "sa_ri": None, "ma": None})
    for sku, prod in products.items():
        if not isinstance(prod, dict) or prod.get("productFamily") != "Database Instance":
            continue
        a = prod.get("attributes", {})
        if a.get("databaseEngine") != args.engine:
            continue
        it = a.get("instanceType", "")
        if not fam_re.search(it):
            continue
        dep = a.get("deploymentOption", "")
        h, _ = hourly(terms, sku)
        if dep == "Single-AZ":
            instances[it]["sa"] = h
            instances[it]["sa_ri"] = reserved_hourly(terms, sku)
        elif dep == "Multi-AZ":
            instances[it]["ma"] = h
        instances[it]["vcpu"] = a.get("vcpu", "?")
        instances[it]["mem"] = parse_mem(a.get("memory"))

    lines = [
        f"{args.engine} on {args.service} — On-Demand, {args.region} (accessed via AWS Price List API)",
        f"{'Instance':22} | {'vCPU':>4} | {'RAM':>5} | {'SA $/hr':>9} | {'1yr RI NoUp':>11} | {'MA $/hr':>9} | {'SA $/mo':>8}",
        "-" * 95,
    ]
    for it in sorted(instances):
        d = instances[it]
        if not d["sa"]:
            continue
        lines.append(
            f"{it:22} | {str(d['vcpu']):>4} | {d['mem']:>4.0f}G | "
            f"${d['sa']:.4f}    | ${d['sa_ri']:.4f}      | ${d['ma']:.4f}    | ${d['sa']*730:,.0f}"
            if d["sa_ri"]
            else f"{it:22} | {str(d['vcpu']):>4} | {d['mem']:>4.0f}G | ${d['sa']:.4f}    | {'-':>11} | ${d['ma']:.4f}    | ${d['sa']*730:,.0f}"
        )
    out = "\n".join(lines)
    print(out)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out + "\n")


if __name__ == "__main__":
    main()
