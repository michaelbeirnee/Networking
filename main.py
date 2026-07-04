#!/usr/bin/env python3
"""
Columbia Alumni Finder
----------------------
Searches every company in the findjobs repo for Columbia University alumni
and their contact information, then writes results to a CSV.

Usage:
    python main.py                          # all sectors, all companies
    python main.py --sector pe              # private equity only
    python main.py --sector ib --limit 10  # first 10 IB firms
    python main.py --output contacts.csv   # custom output file

Sectors: ib | pe | vc | hedge | swe | all
"""

import argparse
import csv
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from companies import SECTOR_ALIASES, load_all_companies
from finder import APOLLO_API_KEY, HUNTER_API_KEY, SERPAPI_KEY, find_columbia_alumni

CSV_FIELDS = [
    "name", "title", "company", "sector",
    "email", "linkedin_url", "location",
    "graduation_year", "degree", "source", "found_at",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Find Columbia alumni at findjobs companies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--sector", choices=list(SECTOR_ALIASES), default="all",
                   help="Which sector to search (default: all)")
    p.add_argument("--limit", type=int, default=None, metavar="N",
                   help="Stop after N companies (useful for testing)")
    p.add_argument("--output", default="columbia_alumni.csv", metavar="FILE",
                   help="CSV output path (default: columbia_alumni.csv)")
    p.add_argument("--delay", type=float, default=2.0, metavar="SEC",
                   help="Seconds to wait between API calls (default: 2)")
    p.add_argument("--resume", action="store_true",
                   help="Skip companies already in the output file")
    return p.parse_args()


def _already_found(output_path: Path) -> set[str]:
    """Return set of company names already written to the output CSV."""
    if not output_path.exists():
        return set()
    with open(output_path, newline="") as f:
        reader = csv.DictReader(f)
        return {row["company"] for row in reader if "company" in row}


def _print_key_status() -> None:
    apollo = "✓" if APOLLO_API_KEY else "✗ (set APOLLO_API_KEY)"
    serp   = "✓" if SERPAPI_KEY    else "✗ (set SERPAPI_KEY)"
    hunter = "✓" if HUNTER_API_KEY else "✗ (set HUNTER_API_KEY)"
    print(f"  1. Apollo.io        : {apollo}")
    print(f"  2. SerpAPI (Google) : {serp}")
    print(f"  3. Hunter.io (email): {hunter}")


def main() -> None:
    args   = parse_args()
    output = Path(args.output)

    print("\nColumbia Alumni Finder")
    print("=" * 40)
    _print_key_status()
    print()

    print("Loading companies from findjobs…")
    companies = load_all_companies(sector=args.sector)
    print(f"  {len(companies)} companies loaded")

    done = set()
    if args.resume:
        done = _already_found(output)
        if done:
            print(f"  Resuming — skipping {len(done)} already-processed companies")
        companies = [c for c in companies if c.get("name") not in done]

    if args.limit:
        companies = companies[: args.limit]

    print(f"  Will search {len(companies)} companies\n")

    # Open CSV (append if resuming, else write fresh)
    mode = "a" if args.resume and output.exists() else "w"
    csv_file   = open(output, mode, newline="")
    csv_writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, extrasaction="ignore")
    if mode == "w":
        csv_writer.writeheader()

    total_found = 0
    try:
        for idx, company in enumerate(companies, 1):
            name    = company.get("name", "Unknown")
            website = company.get("website") or ""
            sector  = company.get("sector", "unknown")

            print(f"[{idx}/{len(companies)}] {name}")

            people = find_columbia_alumni(name, website, sector, delay=args.delay)

            if people:
                csv_writer.writerows(people)
                csv_file.flush()
                total_found += len(people)
                print(f"  → {len(people)} contact(s) saved")
            else:
                print("  → none found")

            # Don't hammer APIs between companies
            if idx < len(companies):
                time.sleep(args.delay)

    except KeyboardInterrupt:
        print("\n\nInterrupted — partial results saved.")
    finally:
        csv_file.close()

    print(f"\nDone. {total_found} total contact(s) written to {output}")
    if total_found:
        print(f"Open {output} in Excel / Numbers to review.\n")


if __name__ == "__main__":
    if sys.version_info < (3, 9):
        sys.exit("Python 3.9+ required.")
    main()
