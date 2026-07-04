"""Load company lists from the findjobs GitHub repo."""

import requests

_REPO_BASE = "https://raw.githubusercontent.com/michaelbeirnee/findjobs/main"

_SOURCES = {
    "investment_banking": "firms_data.json",
    "private_equity":     "pe_firms_data.json",
    "hedge_funds":        "hedge_funds_data.json",
    "venture_capital":    "vc_firms_data.json",
    "software":           "swe_firms_data.json",
}

SECTOR_ALIASES = {
    "ib":    "investment_banking",
    "pe":    "private_equity",
    "hedge": "hedge_funds",
    "vc":    "venture_capital",
    "swe":   "software",
    "all":   None,
}


def load_all_companies(sector: str = "all") -> list[dict]:
    """Return a flat list of company dicts, each with a 'sector' key added.

    sector: one of 'all', 'ib', 'pe', 'vc', 'hedge', 'swe'
    """
    canonical = SECTOR_ALIASES.get(sector, sector)
    sources = _SOURCES if canonical is None else {canonical: _SOURCES[canonical]}

    companies: list[dict] = []
    for sec, filename in sources.items():
        url = f"{_REPO_BASE}/{filename}"
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            for firm in r.json():
                firm["sector"] = sec
                companies.append(firm)
        except Exception as exc:
            print(f"[warn] Could not load {filename}: {exc}")

    return companies
