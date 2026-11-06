"""upload_sheets.py — Upload enriched data and reports to Google Sheets.

Uploads:
  1. Enriched field CSVs to their corresponding Google Sheets tabs.
  2. The disagreement report (logs/disagreements.csv) to the "Disagreements"
     review tab of the shared Status workflow (pending / approve / reject).
     'Low' priority rows are filtered out just before upload when more than
     NON_LOW_MAX_ROWS higher-priority rows exist, so the tab shows the
     meaningful backlog; the CSV keeps the full report.
  3. The missing-publisher report (logs/missing_publisher_in_configs.csv) to
     the "Missing publishers" tab (informational, no Status column).

The Disagreements and Missing publishers tabs are recreated fresh on each run
(values cleared, then rewritten); the review/report-tab formatting and the
Status dropdown are re-applied on upload. The enriched field tabs are updated
in-place (values only — formatting, dropdowns, and data-validation rules are
preserved). Approved Disagreements rows are applied to the data tabs by the
Google Apps Script (see apps_script/GOOGLE_APP_SCRIPT.md and apps_script/ApplyReviewedChanges.gs
at the repository root), never by these scripts.

In Disagreements, rows where field == "Publisher" get per-cell background
 colors in publisher value columns based on publisher type:
 For-profit (FBE7E7), Non-profit (EEF5EB), University Press (E9F2FA), Other (F4EDE1).

Safety checks for enriched field uploads (all hard failures — upload aborted if any fails):
  1. data_extracted/.metadata.json must exist (created by download_sheets.py).
  2. Each CSV must have at least MIN_DATA_ROWS data rows.
  3. Each CSV row count must exactly match the original row count recorded at download time.
  4. The Journal column order must exactly match the order recorded at download time.

Usage:
    python3 scripts/upload_sheets.py [--credentials PATH]

Requires a Google service-account credentials file with write (Editor) access.
Set GOOGLE_SERVICE_ACCOUNT_KEY or place the key at
~/.config/wheretopublish/google_service_account.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import polars as pl
from libraries import FINAL_COLUMNS
import review_common
import sheets_client

INPUT_DIR = Path("data_extracted")
METADATA_FILE = INPUT_DIR / ".metadata.json"
DISAGREEMENTS_PATH = Path("logs/disagreements.csv")
MISSING_PUBLISHERS_PATH = Path("logs/missing_publisher_in_configs.csv")

# Columns in the disagreement report whose values are ISSNs
ISSN_COLUMN_NAMES: frozenset[str] = frozenset({"e-ISSN", "p-ISSN"})

# Review-tab column order comes from review_common.DISAGREEMENT_COLUMNS.
DISAGREEMENT_REQUIRED_COLUMNS: list[str] = review_common.DISAGREEMENT_COLUMNS

# Disagreement report columns hyperlinked to the ISSN portal on upload.
# current_value / suggested_value must stay raw: the Apps Script compares and
# writes them verbatim, and a HYPERLINK formula would break that.
DISAGREEMENT_ISSN_LINK_COLUMNS: list[str] = review_common.DISAGREEMENT_ISSN_LINK_COLUMNS

# Disagreement report columns that may carry "#RRGGBB; value" publisher colors.
DISAGREEMENT_VALUE_COLS: list[str] = review_common.DISAGREEMENT_VALUE_COLUMNS

MISSING_PUBLISHERS_REQUIRED_COLUMNS: list[str] = [
    "journal",
    "publisher",
    "country",
    "publisher_type",
]

REPORT_DEFAULT_BG_HEX = "FFFFFF"


def issn_hyperlink(issn: str) -> str:
    """Return a Google Sheets HYPERLINK formula pointing to the ISSN portal for *issn*.

    If *issn* is empty, returns it unchanged.
    """
    if not issn:
        return issn
    url = f"https://portal.issn.org/search?search={issn}"
    return f'=HYPERLINK("{url}";"{issn}")'


def apply_issn_hyperlinks(rows: list[list[str]]) -> list[list[str]]:
    """Convert ISSN values in disagreement-report rows to clickable HYPERLINK formulas.

    Only rows whose 'field' is an ISSN type (e-ISSN, p-ISSN) are transformed.
    Only the external source value columns are processed — the Status and
    apply columns (current_value, suggested_value) keep raw values because the
    Apps Script verifies and writes them verbatim.

    Args:
        rows: List of rows including header at index 0. All values must be strings.

    Returns:
        New list of rows with ISSN values replaced by HYPERLINK formulas.
    """
    assert rows, "rows must not be empty"
    header = rows[0]
    assert "field" in header, f"Expected 'field' in header, got: {header}"

    field_idx = header.index("field")
    value_indices = [header.index(c) for c in DISAGREEMENT_ISSN_LINK_COLUMNS if c in header]

    result: list[list[str]] = [header]
    for row in rows[1:]:
        field_name = row[field_idx] if field_idx < len(row) else ""
        if field_name in ISSN_COLUMN_NAMES:
            row = list(row)  # copy so we don't mutate the original
            for idx in value_indices:
                if idx < len(row) and row[idx]:
                    row[idx] = issn_hyperlink(row[idx])
        result.append(row)
    return result


def df_to_rows(df: pl.DataFrame) -> list[list[str]]:
    """Convert a Polars DataFrame to a list of string rows with header at index 0."""
    header = df.columns
    data = [[str(v) if v is not None else "" for v in row] for row in df.rows()]
    return [header] + data


def reorder_columns(rows: list[list[str]], column_order: list[str]) -> list[list[str]]:
    """Return rows with columns reordered to match *column_order*.

    Columns absent from the CSV are skipped; columns in the CSV but not in
    *column_order* are dropped. Missing cells within a row are returned as empty strings.
    """
    header = rows[0]
    col_idx: dict[str, int] = {col: i for i, col in enumerate(header)}
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
        first_div = next(
            (i for i, (o, c) in enumerate(zip(original_order, current_order)) if o != c),
            min(len(original_order), len(current_order)),
        )
        assert False, (
            f"[{slug}] Journal order mismatch — the enriched CSV has a different row order "
            "than the original download. Upload aborted to avoid breaking sheet formatting.\n"
            f"  First divergence at row {first_div + 1}: "
            f"original={original_order[first_div]!r}, current={current_order[first_div]!r}"
        )


def upload_rows_to_sheet(service, rows: list[list], tab_name: str, spreadsheet_id: str = sheets_client.SPREADSHEET_ID, ) -> int:
    """Upload *rows* to a Google Sheets tab in place (no clearing).

    Args:
        service: Authenticated Sheets API service with write scope.
        rows: List of lists including header row at index 0.
        tab_name: Exact name of the tab to write to.
        spreadsheet_id: Google Sheets spreadsheet ID.

    Returns:
        Number of data rows uploaded (excluding header).
    """
    assert rows, f"rows must not be empty for tab '{tab_name}'"
    n_cols = len(rows[0])
    padded = [row + [""] * (n_cols - len(row)) for row in rows]
    sheets_client.write_rows(service, spreadsheet_id, tab_name, padded)
    data_rows = len(rows) - 1
    print(f"  Uploaded {data_rows} data rows to tab '{tab_name}'.")
    return data_rows


def split_color_prefix(value: str) -> tuple[str | None, str]:
    """Split a '#RRGGBB; value' color-coded report value.

    Returns (hex_color or None, display_value). Only the leading color prefix
    is removed — the value itself may legitimately contain semicolons (e.g.
    multi-society publisher names).
    """
    value = value.strip()
    if value.startswith("#") and ";" in value:
        color, _, rest = value.partition(";")
        return color, rest.strip()
    return None, value


def build_disagreement_publisher_bg_overrides(rows: list[list[str]]) -> tuple[
    list[tuple[int, int, str]], list[list[str]]]:
    """Return per-cell background overrides for disagreement value cells.

    Only rows where field == 'Publisher' are considered. The value columns in
    DISAGREEMENT_VALUE_COLS carry '#RRGGBB; value' prefixes encoding the
    publisher-type color of each value; the prefix is turned into a background
    override and stripped from the displayed value.
    """
    assert rows and len(rows) >= 1, "rows must include a header"
    header = rows[0]
    value_cols = [c for c in DISAGREEMENT_VALUE_COLS if c in header]
    value_indices = [header.index(c) for c in value_cols]
    overrides: list[tuple[int, int, str]] = []
    for row_idx, row in enumerate(rows[1:], start=1):
        for col_idx in value_indices:
            value = row[col_idx].strip() if col_idx < len(row) else ""
            color_hex, display_value = split_color_prefix(value)
            if color_hex is None:
                color_hex = REPORT_DEFAULT_BG_HEX
            if col_idx < len(row):
                row[col_idx] = display_value
            overrides.append((row_idx, col_idx, color_hex))
    return overrides, rows


def load_disagreements_rows() -> list[list[str]]:
    """Load the disagreements report as rows ready for the review-tab upload.

    The CSV (written by update_extracted.py) already follows the shared
    review-row schema and sort order; ISSN source values are hyperlinked to
    the ISSN portal for display.

    Returns:
        List of rows including header at index 0.
    """
    assert DISAGREEMENTS_PATH.exists(), f"Disagreements file not found: {DISAGREEMENTS_PATH}"
    df = pl.read_csv(DISAGREEMENTS_PATH, infer_schema_length=0)
    missing = [c for c in DISAGREEMENT_REQUIRED_COLUMNS if c not in df.columns]
    assert not missing, f"Missing disagreement columns in {DISAGREEMENTS_PATH}: {missing}"
    df = df.select(DISAGREEMENT_REQUIRED_COLUMNS)
    rows = df_to_rows(df)
    return apply_issn_hyperlinks(rows)


def load_missing_publishers_rows() -> list[list[str]]:
    """Load and sort the missing-publisher report as rows ready for upload.
    Sorts by 'publisher' then 'journal'.
    Returns:
        List of rows including header at index 0.
    """
    assert MISSING_PUBLISHERS_PATH.exists(), f"Missing publishers file not found: {MISSING_PUBLISHERS_PATH}"
    df = pl.read_csv(MISSING_PUBLISHERS_PATH, infer_schema_length=0)
    missing = [c for c in MISSING_PUBLISHERS_REQUIRED_COLUMNS if c not in df.columns]
    assert not missing, f"Missing missing-publisher columns in {MISSING_PUBLISHERS_PATH}: {missing}"
    df = df.select(MISSING_PUBLISHERS_REQUIRED_COLUMNS)
    df = df.sort(["publisher", "journal"])
    return df_to_rows(df)


def upload_all_fields(service, metadata: dict) -> None:
    """Upload all enriched field CSVs to their corresponding Google Sheets tabs.

    Updates values in-place; existing cell formatting, data-validation rules,
    and dropdown menus in each tab are preserved.
    """
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
        reordered = reorder_columns(rows, FINAL_COLUMNS)
        assert reordered[0] == FINAL_COLUMNS, (
            f"[{slug}] CSV columns {rows[0]} do not match the expected sheet columns {FINAL_COLUMNS}. "
            "Upload aborted to avoid shifting columns in the sheet."
        )
        print(f"  [{slug}] → '{tab_name}' ...")
        n_rows = upload_rows_to_sheet(service, reordered, tab_name)
        print(f"    {n_rows} data rows uploaded.")

    print(f"\nAll {len(sheets_client.SHEET_TAB_NAMES)} fields uploaded successfully.")


LOW_PRIORITY = "low"
# When more than this many non-low disagreement rows exist, 'low' priority rows
# are kept out of the upload so the review tab shows the meaningful backlog only.
NON_LOW_MAX_ROWS = 10


def is_low_priority_row(row: list[str], priority_idx: int) -> bool:
    return len(row) > priority_idx and row[priority_idx].strip().lower() == LOW_PRIORITY


def filter_low_priority_rows(rows: list[list[str]]) -> list[list[str]]:
    """Drop 'Low' priority rows when the higher-priority backlog is large.

    The full report stays in logs/disagreements.csv; the filter applies just
    before the tab upload. With more than NON_LOW_MAX_ROWS rows that are not of
    low priority, the 'Low' rows are skipped; otherwise everything is uploaded.
    """
    header = rows[0]
    priority_idx = header.index("priority")
    non_low_count = sum(1 for row in rows[1:] if not is_low_priority_row(row, priority_idx))
    if non_low_count <= NON_LOW_MAX_ROWS:
        return rows
    filtered = [row for row in rows[1:] if not is_low_priority_row(row, priority_idx)]
    print(f"  Skipping {len(rows) - 1 - len(filtered)} 'Low' priority rows "
          f"({non_low_count} higher-priority rows exceed {NON_LOW_MAX_ROWS}).")
    return [header] + filtered


def upload_reports(service) -> None:
    """Upload the disagreement and missing-publisher reports to their tabs.

    Both report tabs are cleared then rewritten (values only — formatting and
    data-validation preserved). The Disagreements tab is a review tab of the
    shared Status workflow: rows go up as `pending`, the Google Apps Script
    applies approved changes cell-by-cell and archives processed rows; 'Low'
    priority rows are filtered out when the higher-priority backlog is large
    (see filter_low_priority_rows). The missing-publisher report is
    informational only (no Status column).
    """
    print("\nUploading disagreements report ...")
    disagreement_rows = filter_low_priority_rows(load_disagreements_rows())
    disagreement_bg, disagreement_rows = build_disagreement_publisher_bg_overrides(disagreement_rows)
    review_common.upload_review_tab(
        service=service, spreadsheet_id=sheets_client.SPREADSHEET_ID,
        tab_name=review_common.DISAGREEMENTS_TAB, rows=disagreement_rows,
        bg_overrides=disagreement_bg,
    )
    print("Uploading missing publishers report ...")
    missing_pub_rows = load_missing_publishers_rows()
    review_common.upload_review_tab(
        service=service, spreadsheet_id=sheets_client.SPREADSHEET_ID,
        tab_name="Missing publishers", rows=missing_pub_rows,
        status_validation=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Upload enriched field CSVs and pipeline reports to Google Sheets. "
            "Enriched-data tabs are updated in-place; report tabs (Disagreements, "
            "Missing publishers) are cleared and rewritten while keeping formatting."
        )
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

    assert METADATA_FILE.exists(), (
        f"Metadata file not found: {METADATA_FILE}\n"
        "Run download_sheets.py first to create it."
    )
    metadata: dict[str, dict] = json.loads(METADATA_FILE.read_text(encoding="utf-8"))

    service = sheets_client.get_sheets_service(credentials_path=args.credentials, readonly=False)
    upload_all_fields(service, metadata)
    upload_reports(service)


if __name__ == "__main__":
    main()
