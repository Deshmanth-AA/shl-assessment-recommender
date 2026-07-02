"""
Fetches the full SHL product catalog JSON and filters it down to
Individual Test Solutions (excludes pre-packaged Job Solutions).

Run this once, locally or in your deploy pipeline, on a machine with
normal internet access:

    python scrape_catalog.py

It writes data/catalog.json, which app/catalog.py loads at startup.

Why the filter is name/heuristic-based:
SHL's public catalog JSON (the export used here) does not carry an
explicit "Individual Test Solution" vs "Job Solution" field. On the
live site those live under two different catalogue tabs. Empirically,
packaged Job Solutions are consistently named "<Role> Solution"
(e.g. "Entry Level Cashier Solution", "Customer Service Phone Solution",
"Entry Level Sales Solution") and bundle multiple test types (you'll
see e.g. ["Competencies", "Personality & Behavior"] together with a
role-based name, no single instrument name). Individual Test Solutions
are named after the instrument itself (e.g. "Core Java (Advanced Level)
(New)", "OPQ32r", "Verify G+"). We filter on the naming convention below.
If you have access to the live catalogue's tab structure, replace
`is_job_solution()` with a direct field check for more precision.
"""
import json
import re
import sys
import urllib.request

CATALOG_URL = "https://tcp-us-prod-rnd.shl.com/voiceRater/shl-ai-hiring/shl_product_catalog.json"
OUT_PATH = "data/catalog.json"

JOB_SOLUTION_PATTERNS = [
    r"\bSolution\b",           # "Entry Level Cashier Solution"
    r"\bSolutions\b",
]


def is_job_solution(entry: dict) -> bool:
    name = entry.get("name", "")
    for pat in JOB_SOLUTION_PATTERNS:
        if re.search(pat, name, flags=re.IGNORECASE):
            return True
    return False


def fetch_catalog(url: str = CATALOG_URL) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    return _parse_lenient(raw)


def _parse_lenient(raw: str) -> list:
    """The upstream export has occasional literal control characters
    (raw newlines/tabs) inside string values instead of escaped \\n / \\t,
    which trips Python's strict JSON parser. Try strict=False first
    (stdlib's built-in tolerance for this exact case); if that still
    fails, strip stray control chars from inside string literals and
    retry."""
    try:
        return json.loads(raw, strict=False)
    except json.JSONDecodeError:
        pass

    cleaned = []
    in_string = False
    escape = False
    for ch in raw:
        if in_string:
            if escape:
                cleaned.append(ch)
                escape = False
                continue
            if ch == "\\":
                cleaned.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = False
                cleaned.append(ch)
                continue
            if ord(ch) < 0x20:
                if ch in ("\n", "\r", "\t"):
                    cleaned.append(" ")
                continue
            cleaned.append(ch)
        else:
            if ch == '"':
                in_string = True
            cleaned.append(ch)
    return json.loads("".join(cleaned))


def normalize(entry: dict) -> dict:
    """Keep only the fields the agent actually needs, normalize test_type."""
    keys = entry.get("keys", []) or []
    # SHL's public site uses short letter codes for test type facets.
    # Map the descriptive "keys" bucket names to the closest single-letter
    # code used on shl.com (A=Ability, B=Biodata/SJT, C=Competencies,
    # D=Development, E=Assessment Exercises, K=Knowledge&Skills,
    # P=Personality&Behavior, S=Simulations). We keep the first match as
    # the primary type but retain the full list too.
    code_map = {
        "Ability & Aptitude": "A",
        "Biodata & Situational Judgment": "B",
        "Competencies": "C",
        "Development & 360": "D",
        "Assessment Exercises": "E",
        "Knowledge & Skills": "K",
        "Personality & Behavior": "P",
        "Simulations": "S",
    }
    codes = [code_map.get(k, k) for k in keys]
    return {
        "id": entry.get("entity_id"),
        "name": entry.get("name", "").strip(),
        "url": entry.get("link", "").strip(),
        "description": (entry.get("description") or "").strip(),
        "job_levels": entry.get("job_levels", []) or [],
        "languages": entry.get("languages", []) or [],
        "duration": entry.get("duration", "") or "",
        "remote": entry.get("remote", ""),
        "adaptive": entry.get("adaptive", ""),
        "test_types": codes,
        "keys": keys,
    }


def main():
    print(f"Fetching catalog from {CATALOG_URL} ...")
    try:
        raw_entries = fetch_catalog()
    except Exception as e:
        print(f"ERROR: could not fetch catalog ({e}).")
        print("If you're behind a restricted network, download the JSON")
        print("manually and point --local at the file instead.")
        sys.exit(1)

    print(f"Fetched {len(raw_entries)} total catalog entries.")

    individual = [e for e in raw_entries if not is_job_solution(e)]
    excluded = len(raw_entries) - len(individual)
    print(f"Excluded {excluded} entries matching Job Solution naming pattern.")
    print(f"Keeping {len(individual)} Individual Test Solutions.")

    normalized = [normalize(e) for e in individual if e.get("link")]

    with open(OUT_PATH, "w") as f:
        json.dump(normalized, f, indent=2)
    print(f"Wrote {len(normalized)} entries to {OUT_PATH}")


if __name__ == "__main__":
    main()