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


def _extract_journal_order(rows: list[list[str]]) -> list[str]:
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
        journal_order = _extract_journal_order(rows)
        assert len(journal_order) == data_rows
        metadata[slug] = {
            "data_rows": data_rows,
            "journal_order": journal_order,
        }
        print(f"    Saved {data_rows} data rows")

    METADATA_FILE.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nAll {len(sheets_client.SHEET_TAB_NAMES)} tabs downloaded to {OUTPUT_DIR}/")
    print(f"Metadata saved to {METADATA_FILE}")


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
