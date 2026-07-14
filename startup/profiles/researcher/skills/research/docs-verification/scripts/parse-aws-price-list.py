#!/usr/bin/env python3
"""
Parse the AWS Price List API (Bulk API) JSON to extract per-region pricing tiers.

The rendered pricing pages on aws.amazon.com/<service>/pricing/ carry their
pricing TABLES AS IMAGES — there is no text to grep. The Price List API publishes
the same data as machine-readable JSON with verbatim tier descriptions, updated
daily. This is the authoritative source.

Usage:
    # Download the index for a service (one-time, ~700KB for API Gateway)
    curl -sL "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<ServiceCode>/current/index.json" \
        -o /tmp/<service>_pricing.json

    # Then parse it (defaults: AmazonApiGateway, us-east-1, request-like products)
    python3 parse-aws-price-list.py /tmp/apigw_pricing.json
    python3 parse-aws-price-list.py /tmp/ec2_pricing.json --service AmazonEC2 --region us-west-2 --keyword "BoxUsage"
    python3 parse-aws-price-list.py /tmp/cf_pricing.json --service AmazonCloudFront --region us-east-1 --keyword "Requests"

Args:
    json_path       : path to the downloaded index.json (positional, required)
    --service, -s   : service code, informational only (default AmazonApiGateway)
    --region, -r    : regionCode filter (default us-east-1)
    --keyword, -k   : substring to filter usagetype/description/operation/productFamily.
                      For API Gateway request pricing use "Request".
                      Pass "" to disable the keyword filter and dump everything in the region.

Output:
    For each matching SKU: productFamily, usagetype, description, then every
    price tier (verbatim description string + per-unit USD + unit).
    Exits 0 on success, 1 if no products match.
"""
import argparse
import json
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json_path", help="path to downloaded Price List API index.json")
    ap.add_argument("-s", "--service", default="AmazonApiGateway",
                    help="service code (informational; default AmazonApiGateway)")
    ap.add_argument("-r", "--region", default="us-east-1",
                    help="regionCode filter (default us-east-1)")
    ap.add_argument("-k", "--keyword", default="Request",
                    help='substring filter on usagetype/description/operation/productFamily '
                         '(default "Request"; pass "" for no filter)')
    args = ap.parse_args()

    with open(args.json_path) as f:
        data = json.load(f)

    pub_date = data.get("publicationDate", "unknown")
    print(f"# Service: {args.service}")
    print(f"# Region:  {args.region}")
    print(f"# Price List publicationDate: {pub_date}")
    print(f"# Keyword filter: {args.keyword!r}" + ("" if args.keyword else " (disabled)"))
    print()

    products = data.get("products", {})
    terms = data.get("terms", {}).get("OnDemand", {})

    matches = []
    for pid, p in products.items():
        attrs = p.get("attributes", {})
        if attrs.get("regionCode") != args.region:
            continue
        ut = attrs.get("usagetype", "")
        desc = attrs.get("description", "")
        op = attrs.get("operation", "")
        pf = p.get("productFamily", "")
        if args.keyword and args.keyword.lower() not in (ut + desc + op + pf).lower():
            continue
        # Has at least one OnDemand price dimension
        if pid not in terms:
            continue
        matches.append((pid, pf, ut, desc, op))

    if not matches:
        print("No products matched. Try widening the keyword (--keyword '') or check the region/service.")
        # Helpful: show available usagetypes in this region for diagnosis
        uts = sorted({p.get("attributes", {}).get("usagetype", "")
                      for p in products.values()
                      if p.get("attributes", {}).get("regionCode") == args.region})
        print(f"\nAvailable usagetypes in {args.region}:")
        for u in uts:
            print(f"  {u}")
        sys.exit(1)

    matches.sort(key=lambda m: (m[2], m[1]))  # by usagetype, then family
    print(f"# {len(matches)} matching SKU(s)\n")

    for pid, pf, ut, desc, op in matches:
        print(f"=== {ut} ===")
        print(f"  productFamily: {pf}")
        print(f"  description:   {desc}")
        print(f"  operation:     {op}")
        ondemand = terms.get(pid, {})
        tier_n = 0
        for tid, td in ondemand.items():
            for pdid, pdv in td.get("priceDimensions", {}).items():
                tier_n += 1
                usd = pdv.get("pricePerUnit", {}).get("USD", "N/A")
                unit = pdv.get("unit", "")
                tdesc = pdv.get("description", "")
                print(f"  tier {tier_n}: {usd} USD / {unit}  —  {tdesc}")
        print()

    print(f"# Done. {len(matches)} SKU(s), publicationDate={pub_date}.")


if __name__ == "__main__":
    main()
