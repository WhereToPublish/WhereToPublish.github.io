"""download_sheets.py — Download all Google Sheet field tabs as CSVs using the Sheets API.

Replaces download_csv.sh. Downloads each field tab defined in sheets_client.SHEET_TAB_NAMES
to data_extracted/<slug>.csv, then writes data_extracted/.metadata.json with original row
counts and journal order — used by upload_sheets.py for safety validation before any upload.

Usage:
    python3 scripts/download_sheets.py [--credentials PATH]

Requires a Google service-account credentials file. Set GOOGLE_SERVICE_ACCOUNT_KEY or
place the key at ~/.config/wheretopublish/google_service_account.json.
"""

import argparse
import json
from pathlib import Path

import sheets_client

OUTPUT_DIR = Path("data_extracted")
METADATA_FILE = OUTPUT_DIR / ".metadata.json"
CONFIG_DIR = Path("config")


def extract_journal_order(rows: list[list[str]]) -> list[str]:
    """Return the ordered list of Journal values from downloaded rows (header excluded).

    The Journal column is located by name so column position changes are handled
    automatically. Rows without a Journal value are recorded as an empty string.

    Args:
        rows: All rows including the header row at index 0.

    Returns:
        Ordered list of Journal cell values (data rows only).
    """
    header = rows[0]
    assert "Journal" in header, (
        f"'Journal' column not found in header: {header}"
    )
    journal_idx = header.index("Journal")
    return [row[journal_idx].strip() if len(row) > journal_idx else "" for row in rows[1:]]


def download_country_formatting(service) -> None:
    """Download publisher\u2192country mappings from the 'variables' tab and save to config/country_formatting.json.

    Reads three publisher groups from the variables tab:
      - "main For-profit Publishers"         + the column immediately to its right
      - "main University Press Publishers"   + the column immediately to its right
      - "main non-profit Publishers"         + the column immediately to its right

    The country column is always pub_idx + 1, which avoids ambiguity when the
    "Publisher Country" header appears multiple times in the same row.

    Saves a nested JSON:
        {"for_profit": {...}, "university_press": {...}, "non_profit": {...}}

    Args:
        service: Authenticated Sheets API service (from sheets_client.get_sheets_service).
    """
    dest = CONFIG_DIR / "_variables_raw.csv"  # temp file, not kept
    rows = sheets_client.download_tab_as_csv(service, sheets_client.VARIABLES_TAB_NAME, dest)
    assert len(rows) >= 2, (
        f"Tab '{sheets_client.VARIABLES_TAB_NAME}' has fewer than 2 rows "
        f"(expected header + data), got {len(rows)}"
    )

    header = rows[0]

    def _build_dict(pub_col_name: str) -> dict[str, str]:
        """Build a publisher\u2192country dict using the column immediately right of pub_col_name."""
        assert pub_col_name in header, (
            f"Column '{pub_col_name}' not found in '{sheets_client.VARIABLES_TAB_NAME}' header: {header}"
        )
        pub_idx = header.index(pub_col_name)
        country_idx = pub_idx + 1
        assert country_idx < len(header), (
            f"No column to the right of '{pub_col_name}' (index {pub_idx}) in header: {header}"
        )
        result: dict[str, str] = {}
        for row in rows[1:]:
            pub = row[pub_idx].strip() if len(row) > pub_idx else ""
            country = row[country_idx].strip() if len(row) > country_idx else ""
            if pub and country:
                result[pub] = country
        return result

    for_profit = _build_dict("main For-profit Publishers")
    university_press = _build_dict("main University Press Publishers")
    non_profit = _build_dict("main non-profit Publishers")

    assert len(for_profit) >= 1, (
        f"For-profit publisher dict is empty after reading '{sheets_client.VARIABLES_TAB_NAME}' tab."
    )

    country_data = {
        "for_profit": for_profit,
        "university_press": university_press,
        "non_profit": non_profit,
    }

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CONFIG_DIR / "country_formatting.json"
    out_path.write_text(json.dumps(country_data, ensure_ascii=False, indent=2), encoding="utf-8")
    total = len(for_profit) + len(university_press) + len(non_profit)
    print(
        f"  Saved {total} publisher\u2192country entries to {out_path} "
        f"({len(for_profit)} for-profit, {len(university_press)} university press, {len(non_profit)} non-profit)"
    )

    # Remove temp raw CSV
    if dest.exists():
        dest.unlink()


def download_all_fields(credentials_path: Path | None = None) -> None:
    """Download all field tabs from the WhereToPublish spreadsheet to data_extracted/.

    Saves data_extracted/.metadata.json with original row counts and journal order
    for every slug so that upload_sheets.py can validate data integrity before upload.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    service = sheets_client.get_sheets_service(credentials_path=credentials_path, readonly=True)

    metadata: dict[str, dict] = {}
    print(f"Downloading {len(sheets_client.SHEET_TAB_NAMES)} field tabs from Google Sheets ...")
    for slug, tab_name in sheets_client.SHEET_TAB_NAMES.items():
        dest = OUTPUT_DIR / f"{slug}.csv"
        print(f"  [{slug}] '{tab_name}' → {dest}")
        rows = sheets_client.download_tab_as_csv(service, tab_name, dest)
        assert len(rows) >= 2, (
            f"Tab '{tab_name}' (slug: {slug}) has fewer than 2 rows — "
            f"expected at least a header row plus one data row, got {len(rows)}"
        )
        data_rows = len(rows) - 1
        journal_order = extract_journal_order(rows)
        assert len(journal_order) == data_rows
        metadata[slug] = {
            "data_rows": data_rows,
            "journal_order": journal_order,
        }
        print(f"    Saved {data_rows} data rows")

    METADATA_FILE.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nAll {len(sheets_client.SHEET_TAB_NAMES)} tabs downloaded to {OUTPUT_DIR}/")
    print(f"Metadata saved to {METADATA_FILE}")

    print(f"\nDownloading country formatting from '{sheets_client.VARIABLES_TAB_NAME}' tab ...")
    download_country_formatting(service)
    print("Country formatting download complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download all WhereToPublish Google Sheet field tabs as CSVs."
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=None,
        help=(
            "Path to service-account JSON key "
            "(default: GOOGLE_SERVICE_ACCOUNT_KEY env var or "
            "~/.config/wheretopublish/google_service_account.json)"
        ),
    )
    args = parser.parse_args()
    download_all_fields(credentials_path=args.credentials)


if __name__ == "__main__":
    main()
