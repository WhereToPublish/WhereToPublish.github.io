"""upload_sheets.py — Upload enriched data_extracted CSVs back to Google Sheets.

Uploads the enriched data for every field slug defined in sheets_client.SHEET_TAB_NAMES
to the corresponding Google Sheets tab.

Safety checks (all are hard failures — the upload is aborted if any check fails):
  1. data_extracted/.metadata.json must exist (created by download_sheets.py).
  2. Each CSV must have at least MIN_DATA_ROWS data rows.
  3. Each CSV row count must exactly match the original row count recorded at download time.
  4. The Journal column order must exactly match the order recorded at download time.

Only cell values are written (spreadsheets.values.update with USER_ENTERED).
Cell formatting, data-validation rules, and dropdown menus are untouched.

Usage:
    python3 scripts/upload_sheets.py [--credentials PATH]

Requires a Google service-account credentials file with write (Editor) access.
Set GOOGLE_SERVICE_ACCOUNT_KEY or place the key at
~/.config/wheretopublish/google_service_account.json.
"""

import argparse
import json
from pathlib import Path

import sheets_client

INPUT_DIR = Path("data_extracted")
METADATA_FILE = INPUT_DIR / ".metadata.json"

# Desired column order for the uploaded tables.
# Columns not present in a CSV are silently skipped.
UPLOAD_COLUMN_ORDER: list[str] = [
    "Journal's MAIN field",
    "Field",
    "Journal",
    "Website",
    "Publisher type",
    "Publisher",
    "Institution",
    "Institution type",
    "Country",
    "Business model",
    "Alternative journal name",
    "APC Euros",
    "Scimago Rank",
    "Scimago Quartile",
    "H index",
    "PCI partner",
    "e-ISSN",
    "p-ISSN",
    "ISSN-L",
]


def reorder_columns(rows: list[list[str]], column_order: list[str]) -> list[list[str]]:
    """Return rows with columns reordered to match column_order.

    Columns absent from the CSV are skipped; columns in the CSV but not in
    column_order are dropped.  Missing cells within a row are returned as empty
    strings.
    """
    header = rows[0]
    col_idx: dict[str, int] = {col: i for i, col in enumerate(header)}
    # Only keep columns that actually exist in the header
    new_header = [col for col in column_order if col in col_idx]
    indices = [col_idx[col] for col in new_header]
    result: list[list[str]] = [new_header]
    for row in rows[1:]:
        result.append([row[i] if i < len(row) else "" for i in indices])
    return result


def read_journal_order(rows: list[list[str]]) -> list[str]:
    """Return the ordered list of Journal values from CSV rows (header excluded).

    Locates the Journal column by name in the header row.
    """
    header = rows[0]
    assert "Journal" in header, f"'Journal' column not found in CSV header: {header}"
    journal_idx = header.index("Journal")
    return [row[journal_idx].strip() if len(row) > journal_idx else "" for row in rows[1:]]


def validate_before_upload(slug: str, rows: list[list[str]], meta: dict) -> None:
    """Assert that the enriched CSV is safe to upload to Google Sheets.

    Checks:
    - Minimum data-row threshold (sheets_client.MIN_DATA_ROWS).
    - Row count matches the original count recorded at download time.
    - Journal column order is identical to the order recorded at download time.

    Args:
        slug: Field slug (e.g. "genetics_genomics").
        rows: All rows from the enriched CSV, header at index 0.
        meta: Metadata dict for this slug from .metadata.json.
    """
    data_rows = len(rows) - 1  # exclude header
    original_rows = meta["data_rows"]
    original_order = meta["journal_order"]

    assert data_rows >= sheets_client.MIN_DATA_ROWS, (
        f"[{slug}] Only {data_rows} data rows found — minimum is {sheets_client.MIN_DATA_ROWS}. "
        "Something is wrong; aborting upload."
    )
    assert data_rows == original_rows, (
        f"[{slug}] Row count mismatch: enriched CSV has {data_rows} data rows but "
        f"the original download had {original_rows}. "
        "Upload aborted to avoid breaking sheet formatting."
    )

    current_order = read_journal_order(rows)
    if current_order != original_order:
        # Find first diverging position for a useful error message
        first_div = next(
            (i for i, (o, c) in enumerate(zip(original_order, current_order)) if o != c),
            min(len(original_order), len(current_order)),  # lengths differ
        )
        assert False, (
            f"[{slug}] Journal order mismatch — the enriched CSV has a different row order "
            "than the original download. Upload aborted to avoid breaking sheet formatting.\n"
            f"  First divergence at row {first_div + 1}: "
            f"original={original_order[first_div]!r}, current={current_order[first_div]!r}"
        )


def upload_all_fields(credentials_path: Path | None = None) -> None:
    """Upload all enriched field CSVs to their corresponding Google Sheets tabs."""
    assert METADATA_FILE.exists(), (
        f"Metadata file not found: {METADATA_FILE}\n"
        "Run download_sheets.py first to create it."
    )
    metadata: dict[str, dict] = json.loads(METADATA_FILE.read_text(encoding="utf-8"))

    service = sheets_client.get_sheets_service(credentials_path=credentials_path, readonly=False)

    print(f"Uploading enriched data for {len(sheets_client.SHEET_TAB_NAMES)} fields ...")
    for slug, tab_name in sheets_client.SHEET_TAB_NAMES.items():
        csv_path = INPUT_DIR / f"{slug}.csv"
        assert csv_path.exists(), (
            f"Enriched CSV not found: {csv_path}\n"
            "Run the full pipeline (download_sheets.py + update_extracted.py) first."
        )
        assert slug in metadata, (
            f"Slug '{slug}' not found in metadata {METADATA_FILE}. "
            "Re-run download_sheets.py to regenerate the metadata."
        )

        rows = sheets_client.read_csv_as_rows(csv_path)
        validate_before_upload(slug, rows, metadata[slug])

        reordered = reorder_columns(rows, UPLOAD_COLUMN_ORDER)
        n_cols = len(reordered[0])
        padded = [row + [""] * (n_cols - len(row)) for row in reordered]

        print(f"  [{slug}] → '{tab_name}' ...")
        sheets_client.write_rows(service, sheets_client.SPREADSHEET_ID, tab_name, padded)
        n_rows = len(reordered) - 1
        print(f"    {n_rows} data rows uploaded.")

    print(f"\nAll {len(sheets_client.SHEET_TAB_NAMES)} fields uploaded successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload all enriched field CSVs to their Google Sheets tabs."
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
    upload_all_fields(credentials_path=args.credentials)


if __name__ == "__main__":
    main()
