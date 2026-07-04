"""
Multi-method Columbia alumni finder.

Priority chain per company:
  1. Apollo.io  — people search with school filter
                  (best: name + title + email + LinkedIn)
  2. SerpAPI    — Google search via serpapi.com (site:linkedin.com/in)
                  (free 100 searches/month; needs SERPAPI_KEY)
  3. Hunter.io  — domain email enrichment for step-2 hits
                  (free 25 searches/month; needs HUNTER_API_KEY)

Set API keys in a .env file (see .env.example).
"""

import os
import re
import time
import urllib.parse
from datetime import datetime

import requests

# ── Keys (populated by main.py via dotenv) ───────────────────────────────────
APOLLO_API_KEY  = os.getenv("APOLLO_API_KEY",  "")
HUNTER_API_KEY  = os.getenv("HUNTER_API_KEY",  "")
SERPAPI_KEY     = os.getenv("SERPAPI_KEY",      "")

# kept for backwards compat but no longer used
GOOGLE_API_KEY  = os.getenv("GOOGLE_API_KEY",  "")
GOOGLE_CSE_ID   = os.getenv("GOOGLE_CSE_ID",   "")

_COLUMBIA_TERMS = {
    "columbia university", "columbia business school",
    "columbia college", "columbia engineering", "columbia seas",
    "school of general studies", "columbia law",
}


# ── Public entry point ────────────────────────────────────────────────────────

def find_columbia_alumni(company_name: str, website: str, sector: str,
                         delay: float = 2.0) -> list:
    """Return list of normalised contact dicts for Columbia alumni at company."""

    # Method 1 ── Apollo.io
    if APOLLO_API_KEY:
        people, status = _apollo_search(company_name)
        if people is not None:
            _log("Apollo", len(people), status)
            return [_normalise(p, company_name, sector, "apollo") for p in people]
        _log("Apollo", 0, status)

    time.sleep(delay)

    # Method 2 ── SerpAPI → LinkedIn profiles
    serp_people, s_status = _serp_search(company_name)
    _log("SerpAPI", len(serp_people or []), s_status)

    if not serp_people:
        return []

    # Method 3 ── Hunter.io email enrichment for SerpAPI hits
    email_map: dict = {}
    if HUNTER_API_KEY and website:
        time.sleep(delay)
        emails, h_status = _hunter_domain(website)
        _log("Hunter", len(emails or []), h_status)
        if emails:
            email_map = _build_email_map(emails)

    results = []
    for person in serp_people:
        if email_map:
            person["email"] = _match_email(person["name"], email_map)
        results.append(_normalise(person, company_name, sector,
                                  "serp+hunter" if email_map else "serp"))
    return results


# ── Method 1: Apollo.io ───────────────────────────────────────────────────────

def _apollo_search(company_name: str) -> tuple:
    url = "https://api.apollo.io/v1/people/search"
    headers = {
        "X-Api-Key": APOLLO_API_KEY,
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
    }
    payload = {
        "q_organization_name": company_name,
        "page": 1,
        "per_page": 25,
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=20)
    except requests.RequestException as exc:
        return None, f"network_error: {exc}"

    if r.status_code == 401:
        return None, "unauthorized"
    if r.status_code == 429:
        return None, "rate_limited"
    if r.status_code != 200:
        return None, f"http_{r.status_code}"

    raw = r.json().get("people", [])
    people = []
    for p in raw:
        edu = p.get("education") or []
        # Filter client-side in case Apollo returns non-Columbia people
        if edu and not _is_columbia_alumnus(edu):
            continue
        grad_year, degree = _parse_education(edu)
        people.append({
            "name":            f"{p.get('first_name','')} {p.get('last_name','')}".strip(),
            "title":           p.get("title", ""),
            "email":           p.get("email", ""),
            "linkedin_url":    p.get("linkedin_url", ""),
            "location":        p.get("city", ""),
            "graduation_year": grad_year,
            "degree":          degree,
        })
    return people, "ok"


# ── Method 2: SerpAPI → LinkedIn ─────────────────────────────────────────────

def _serp_search(company_name: str) -> tuple:
    if not SERPAPI_KEY:
        return None, "no_key"

    query = f'site:linkedin.com/in "Columbia University" "{company_name}"'
    params = {
        "api_key": SERPAPI_KEY,
        "engine":  "google",
        "q":       query,
        "num":     10,
    }
    try:
        r = requests.get("https://serpapi.com/search", params=params, timeout=25)
    except requests.RequestException as exc:
        return None, f"network_error: {exc}"

    if r.status_code == 401:
        return None, "unauthorized"
    if r.status_code == 429:
        return None, "rate_limited"
    if r.status_code != 200:
        return None, f"http_{r.status_code}"

    items = r.json().get("organic_results", [])
    people = []
    for item in items:
        link    = item.get("link", "")
        title   = item.get("title", "")
        snippet = item.get("snippet", "")

        li_url = _extract_linkedin_url(link)
        if not li_url:
            continue

        people.append({
            "name":            _name_from_title(title),
            "title":           _job_from_snippet(snippet),
            "email":           "",
            "linkedin_url":    li_url,
            "location":        "",
            "graduation_year": "",
            "degree":          "",
        })
    return people, "ok"


# ── Method 3: Hunter.io email enrichment ─────────────────────────────────────

def _hunter_domain(website: str) -> tuple:
    domain = _extract_domain(website)
    if not domain:
        return None, "no_domain"

    try:
        r = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": HUNTER_API_KEY, "limit": 10},
            timeout=15,
        )
    except requests.RequestException as exc:
        return None, f"network_error: {exc}"

    if r.status_code == 401:
        return None, "unauthorized"
    if r.status_code == 429:
        return None, "rate_limited"
    if r.status_code != 200:
        return None, f"http_{r.status_code}"

    emails = r.json().get("data", {}).get("emails", [])
    return emails, "ok"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise(p: dict, company: str, sector: str, source: str) -> dict:
    return {
        "name":            p.get("name", ""),
        "title":           p.get("title", ""),
        "company":         company,
        "sector":          sector,
        "email":           p.get("email", ""),
        "linkedin_url":    p.get("linkedin_url", ""),
        "location":        p.get("location", ""),
        "graduation_year": p.get("graduation_year", ""),
        "degree":          p.get("degree", ""),
        "source":          source,
        "found_at":        datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _is_columbia_alumnus(edu_list: list) -> bool:
    return any(
        any(term in (e.get("school", {}).get("name", "")).lower()
            for term in _COLUMBIA_TERMS)
        for e in edu_list
    )


def _parse_education(edu_list: list) -> tuple:
    for e in edu_list:
        school_name = (e.get("school") or {}).get("name", "")
        if any(t in school_name.lower() for t in _COLUMBIA_TERMS):
            end  = e.get("end_date") or ""
            year = re.search(r"\d{4}", end)
            return (year.group(0) if year else ""), (e.get("degree") or "")
    return "", ""


def _extract_domain(website: str) -> str:
    if not website:
        return ""
    m = re.search(r"(?:https?://)?(?:www\.)?([^/\s]+)", website)
    return m.group(1) if m else ""


def _extract_linkedin_url(url: str) -> str:
    m = re.search(r"(https?://(?:www\.)?linkedin\.com/in/[^\s&?\"']+)", url)
    return m.group(1) if m else ""


def _name_from_title(title: str) -> str:
    # Google result titles: "John Smith - VP at Goldman Sachs | LinkedIn"
    parts = re.split(r"\s*[-|–]\s*", title)
    name  = parts[0].strip()
    name  = re.sub(r"\s*\|\s*LinkedIn.*$", "", name, flags=re.IGNORECASE)
    return name


def _job_from_snippet(snippet: str) -> str:
    snippet = snippet.strip()
    if len(snippet) <= 120:
        return snippet
    cut = snippet.rfind(" ", 0, 120)
    return snippet[: cut if cut > 60 else 120]


def _build_email_map(hunter_emails: list) -> dict:
    """Map 'firstname lastname' → email (lowercase keys)."""
    m: dict = {}
    for e in hunter_emails:
        fn   = (e.get("first_name") or "").strip().lower()
        ln   = (e.get("last_name")  or "").strip().lower()
        addr = e.get("value", "")
        if fn and ln and addr:
            m[f"{fn} {ln}"] = addr
            m[fn] = addr      # first-name-only fallback
    return m


def _match_email(name: str, email_map: dict) -> str:
    key   = name.strip().lower()
    first = key.split()[0] if key.split() else ""
    return email_map.get(key) or email_map.get(first, "")


def _log(method: str, count: int, status: str) -> None:
    if status in ("ok", "ok_empty"):
        if count:
            print(f"    [{method}] {count} hit(s)")
    else:
        print(f"    [{method}] {status}")
