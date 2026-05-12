"""Classify ISSNs from the Scimago dataset as print (p), electronic (e), or linking (l).

Uses the ISSN Portal JSON-LD API (no external library required).
Results are cached in config/ISSN_type.csv. Already-cached ISSNs are skipped.

Cache format: one row per ISSN; the "Type" column holds a semicolon-joined set of
type codes sorted by TYPE_ORDER, e.g. "p;l", "e;l", "e", "p".

Usage (from repo root):
    python scripts/Scimago_ISSN_type.py [--limit N]

Options:
    --limit N    Process at most N new ISSNs per run (default: unlimited).
                 Use for incremental runs; re-run until all ISSNs are classified.
                 The full Scimago dataset contains ~50k ISSNs; first run is slow.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import polars as pl
from libraries import format_issn, load_csv


SCIMAGO_FILE = os.path.join("data_extraction", "scimagojr.csv.gz")
ISSN_TYPE_FILE = os.path.join("config", "ISSN_type.csv")
ISSN_PORTAL_BASE = "https://portal.issn.org/resource/ISSN"
RATE_LIMIT_DELAY = 0.0  # seconds between API calls
SAVE_INTERVAL = 100  # flush cache to disk every N newly classified ISSNs

# Mapping from ISSN Portal medium values to type codes
MEDIUM_TO_TYPE = {
    "medium:Print": "p",
    "medium:Online": "e",
}

# Sort order for type codes within a combined type string (e before p before l)
TYPE_ORDER = {"e": 0, "p": 1, "l": 2}


class PassthroughHTTPErrorProcessor(urllib.request.HTTPErrorProcessor):
    """Return the response object for all HTTP status codes instead of raising.

    This allows the caller to inspect response.status without try/except.
    """

    def http_response(self, request, response):
        return response

    https_response = http_response


OPENER = urllib.request.build_opener(PassthroughHTTPErrorProcessor())


def query_issn_portal(issn: str) -> dict | None:
    """Fetch JSON-LD data for an ISSN from the ISSN Portal.

    Returns the parsed dict, or None if the ISSN was not found (HTTP 404).
    Asserts on unexpected HTTP status codes so unexpected failures are visible.
    """
    url = f"{ISSN_PORTAL_BASE}/{issn}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/ld+json",
            "User-Agent": "WhereToPublish/1.0 (mailto:contact@wheretopublish.github.io)",
        },
    )
    # urllib.error.URLError (timeout, connection reset, DNS failure) has no non-try/except solution.
    try:
        response = OPENER.open(req, timeout=15)
    except urllib.error.URLError as exc:
        print(f"WARNING: network error for ISSN {issn}: {exc}", file=sys.stderr)
        return None
    if response.status in (400, 404):
        # 404 = ISSN not registered; 400 = ISSN fails portal validation (bad checksum etc.)
        return None
    assert response.status == 200, (
        f"Unexpected HTTP {response.status} for ISSN {issn} at {url}"
    )
    return json.loads(response.read())


def classify_issn(issn: str) -> list[str]:
    """Return type codes for the given ISSN.

    Possible types: 'p' (print), 'e' (electronic), 'l' (linking ISSN).
    An ISSN can have both a medium type ('p' or 'e') and the 'l' type.
    Returns [] if the ISSN is not found or has an unrecognised format.
    """
    data = query_issn_portal(issn)
    if data is None:
        print(f"WARNING: ISSN {issn} not found in ISSN Portal", file=sys.stderr)
        return []

    medium = data.get("format")
    if medium not in MEDIUM_TO_TYPE:
        print(
            f"WARNING: ISSN {issn} has unrecognised format {medium!r}, skipping",
            file=sys.stderr,
        )
        return []

    types = [MEDIUM_TO_TYPE[medium]]

    # If this ISSN is the linking ISSN for its journal, add 'l'
    issn_l_value = data.get("identifiedBy", {}).get("#ISSN-L", {}).get("value")
    if issn_l_value == issn:
        types.append("l")

    return types


def load_issn_cache() -> dict[str, str]:
    """Return a dict mapping ISSN → combined type string for all ISSNs in ISSN_TYPE_FILE.

    The combined type string is a semicolon-joined set of type codes sorted by TYPE_ORDER,
    e.g. "p;l", "e;l", "e", "p".
    """
    if not os.path.exists(ISSN_TYPE_FILE):
        return {}
    df = pl.read_csv(ISSN_TYPE_FILE)
    assert list(df.columns) == ["ISSN", "Type"], (
        f"Unexpected columns in {ISSN_TYPE_FILE}: {df.columns}"
    )
    assert df["ISSN"].n_unique() == df.height, (
        f"ISSN_TYPE_FILE has duplicate ISSNs: {df.height} rows, {df['ISSN'].n_unique()} unique"
    )
    # Validate type codes
    valid_codes = set(TYPE_ORDER.keys())
    for row in df.iter_rows(named=True):
        codes = set(row["Type"].split(";"))
        assert codes <= valid_codes, (
            f"ISSN {row['ISSN']} has unexpected type codes: {codes - valid_codes}"
        )
    return dict(zip(df["ISSN"].to_list(), df["Type"].to_list()))


def save_issn_cache(new_rows: list[dict]) -> None:
    """Append new_rows to ISSN_TYPE_FILE (one unique row per ISSN), sorted by ISSN.

    Each entry in new_rows must have 'ISSN' and 'Type' keys, where 'Type' is a
    semicolon-joined combined type string (e.g. "p;l"). No ISSN in new_rows may
    already exist in the cache.
    """
    assert new_rows, "save_issn_cache called with empty new_rows"
    assert all("ISSN" in r and "Type" in r for r in new_rows), (
        "Each entry in new_rows must have 'ISSN' and 'Type' keys"
    )

    existing_cache = load_issn_cache()  # dict[ISSN → Type]
    for r in new_rows:
        assert r["ISSN"] not in existing_cache, (
            f"BUG: ISSN {r['ISSN']} already in cache; should not be in new_rows"
        )

    # Merge: combine existing and new into one dict, then write sorted
    combined_cache = {**existing_cache, **{r["ISSN"]: r["Type"] for r in new_rows}}
    combined = (
        pl.DataFrame({"ISSN": list(combined_cache.keys()), "Type": list(combined_cache.values())})
        .sort("ISSN")
    )

    assert list(combined.columns) == ["ISSN", "Type"], (
        f"Column mismatch after merge: {combined.columns}"
    )
    assert combined["ISSN"].n_unique() == combined.height, (
        f"BUG: duplicates after merge: {combined.height} rows, {combined['ISSN'].n_unique()} unique"
    )

    combined.write_csv(ISSN_TYPE_FILE)


# ─── Scimago ISSN Extraction ──────────────────────────────────────────────────


def extract_scimago_issns() -> set[str]:
    """Extract and normalise all unique ISSNs from the Scimago dataset."""
    df = load_csv(SCIMAGO_FILE, separator=";")
    assert "Issn" in df.columns, f"'Issn' column not found in {SCIMAGO_FILE}"

    issns: set[str] = set()
    for raw_cell in df["Issn"].to_list():
        if raw_cell is None:
            continue
        for part in str(raw_cell).split(","):
            formatted = format_issn(part.strip())
            if formatted is not None:
                issns.add(formatted)

    assert len(issns) > 0, f"No valid ISSNs extracted from {SCIMAGO_FILE}"
    return issns


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Classify Scimago ISSNs as print (p), electronic (e), or linking (l) "
            "using the ISSN Portal API. Results are cached in config/ISSN_type.csv."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process at most N new ISSNs per run (for incremental runs).",
    )
    args = parser.parse_args()

    scimago_issns = extract_scimago_issns()
    cached_issns = set(load_issn_cache().keys())
    new_issns = sorted(scimago_issns - cached_issns)

    print(f"Scimago ISSNs total : {len(scimago_issns)}")
    print(f"Already cached      : {len(cached_issns)}")
    print(f"To classify         : {len(new_issns)}")

    if not new_issns:
        print("Nothing to do.")
        return

    if args.limit is not None:
        new_issns = new_issns[: args.limit]
        print(f"Processing first {len(new_issns)} (--limit applied)")

    batch: list[dict] = []  # accumulates rows since the last save
    total_rows_written = 0
    classified = 0
    skipped = 0

    for i, issn in enumerate(new_issns, 1):
        types = classify_issn(issn)
        if types:
            combined_type = ";".join(sorted(types, key=lambda t: TYPE_ORDER.get(t, 99)))
            batch.append({"ISSN": issn, "Type": combined_type})
            classified += 1
        else:
            skipped += 1

        # Flush to disk every SAVE_INTERVAL ISSNs so progress survives a crash
        if classified % SAVE_INTERVAL == 0 and batch:
            save_issn_cache(batch)
            total_rows_written += len(batch)
            batch = []

        if i % 100 == 0 or i == len(new_issns):
            print(f"  {i}/{len(new_issns)} processed  "
                  f"(classified: {classified}, skipped: {skipped}) …")

        time.sleep(RATE_LIMIT_DELAY)

    # Final flush for any remaining rows
    if batch:
        save_issn_cache(batch)
        total_rows_written += len(batch)

    print(f"\nDone. Classified: {classified}  |  Skipped (not found): {skipped}")
    print(f"config/ISSN_type.csv updated with {total_rows_written} new rows.")


if __name__ == "__main__":
    main()
