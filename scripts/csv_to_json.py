#!/usr/bin/env python3
"""Convert columbia_alumni.csv into docs/data.json for the static site."""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "columbia_alumni.csv")
DST = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/data.json")


def main() -> None:
    people = []
    if SRC.exists():
        with open(SRC, newline="") as f:
            people = list(csv.DictReader(f))

    DST.parent.mkdir(parents=True, exist_ok=True)
    with open(DST, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(people),
            "people": people,
        }, f, indent=2)

    print(f"Wrote {len(people)} people to {DST}")


if __name__ == "__main__":
    main()
