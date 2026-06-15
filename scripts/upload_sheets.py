"""upload_sheets.py — Upload enriched data and reports to Google Sheets.

Uploads:
  1. Enriched field CSVs to their corresponding Google Sheets tabs.
  2. The disagreement report (logs/disagreements.csv) to the "Disagreements" tab.
  3. The missing-publisher report (logs/missing_publisher_in_configs.csv) to
     the "Missing publishers" tab.

The Disagreements and Missing publishers tabs are recreated fresh on each run
(values cleared, then rewritten). The enriched field tabs are updated in-place
(values only — formatting, dropdowns, and data-validation rules are preserved).

In Disagreements, rows where column == "Publisher" get per-cell background
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

import argparse
import json
from pathlib import Path
import polars as pl
from libraries import FINAL_COLUMNS
import sheets_client

INPUT_DIR = Path("data_extracted")
METADATA_FILE = INPUT_DIR / ".metadata.json"
DISAGREEMENTS_PATH = Path("logs/disagreements.csv")
MISSING_PUBLISHERS_PATH = Path("logs/missing_publisher_in_configs.csv")

# Columns in the disagreement report whose values are ISSNs
ISSN_COLUMN_NAMES: frozenset[str] = frozenset({"e-ISSN", "p-ISSN"})

# Value columns in the disagreement report that may carry ISSN strings
DISAGREEMENT_VALUE_COLS: list[str] = [
    "dataset_value",
    "Scimago_value",
    "DOAJ_value",
    "OpenAPC_value",
]

DISAGREEMENT_REQUIRED_COLUMNS: list[str] = [
    "priority",
    "journal",
    "url",
    "publisher_type",
    "field",
    "column",
    "dataset_value",
    "Scimago_value",
    "DOAJ_value",
    "OpenAPC_value",
]

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

    Only rows whose 'column' field is an ISSN type (e-ISSN, p-ISSN) are transformed.
    All four value columns (dataset_value, Scimago_value, DOAJ_value, OpenAPC_value)
    are processed for those rows.

    Args:
        rows: List of rows including header at index 0. All values must be strings.

    Returns:
        New list of rows with ISSN values replaced by HYPERLINK formulas.
    """
    assert rows, "rows must not be empty"
    header = rows[0]
    assert "column" in header, f"Expected 'column' in header, got: {header}"

    col_idx = header.index("column")
    value_indices = [header.index(c) for c in DISAGREEMENT_VALUE_COLS if c in header]

    result: list[list[str]] = [header]
    for row in rows[1:]:
        col_name = row[col_idx] if col_idx < len(row) else ""
        if col_name in ISSN_COLUMN_NAMES:
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


def upload_rows_to_sheet(service, rows: list[list], tab_name: str, spreadsheet_id: str = sheets_client.SPREADSHEET_ID,
                         clear_before_write: bool = False, ) -> int:
    """Upload *rows* to a Google Sheets tab.

    Args:
        service: Authenticated Sheets API service with write scope.
        rows: List of lists including header row at index 0.
        tab_name: Exact name of the tab to write to.
        spreadsheet_id: Google Sheets spreadsheet ID.
        clear_before_write: If True, clear existing values in the tab before writing
                    new rows. Formatting and data-validation rules are preserved.

    Returns:
        Number of data rows uploaded (excluding header).
    """
    assert rows, f"rows must not be empty for tab '{tab_name}'"
    if clear_before_write:
        sheets_client.clear_tab_values(service, spreadsheet_id, tab_name)

    n_cols = len(rows[0])
    padded = [row + [""] * (n_cols - len(row)) for row in rows]
    sheets_client.write_rows(service, spreadsheet_id, tab_name, padded)
    data_rows = len(rows) - 1
    print(f"  Uploaded {data_rows} data rows to tab '{tab_name}'.")
    return data_rows


def build_disagreement_publisher_bg_overrides(rows: list[list[str]]) -> list[
    tuple[int, int, str]]:
    """Return per-cell background overrides for disagreement Publisher value cells.

    Only rows where column == 'Publisher' are considered. The value columns
    dataset_value/Scimago_value/DOAJ_value/OpenAPC_value are colored by publisher type.
    """
    assert rows and len(rows) >= 1, "rows must include a header"
    header = rows[0]
    value_cols = [c for c in DISAGREEMENT_VALUE_COLS if c in header]
    value_indices = [header.index(c) for c in value_cols]
    overrides: list[tuple[int, int, str]] = []
    for row_idx, row in enumerate(rows[1:], start=1):
        for col_idx in value_indices:
            value = row[col_idx].strip() if col_idx < len(row) else ""
            if value and value.startswith('#'):
                color_hex = value.split(';')[0]
                rows[row_idx][col_idx] = ";".join(value.split(';')[-1:]).strip()
            else:
                color_hex = REPORT_DEFAULT_BG_HEX
            overrides.append((row_idx, col_idx, color_hex))
    return overrides, rows


def load_disagreements_rows() -> list[list[str]]:
    """Load, sort, and format the disagreements report as rows ready for upload.
    Sorts by 'column' then 'journal'. Converts ISSN values to HYPERLINK formulas.
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

        print(f"  [{slug}] → '{tab_name}' ...")
        n_rows = upload_rows_to_sheet(service, reordered, tab_name)
        print(f"    {n_rows} data rows uploaded.")

    print(f"\nAll {len(sheets_client.SHEET_TAB_NAMES)} fields uploaded successfully.")


def upload_reports(service) -> None:
    """Upload the disagreement and missing-publisher reports to their dedicated tabs.

    Tabs are cleared then rewritten on each run (values only) so formatting and
    data-validation rules remain intact.
    """

    print("\nUploading disagreements report ...")
    disagreement_rows = load_disagreements_rows()
    disagreement_bg, disagreement_rows = build_disagreement_publisher_bg_overrides(disagreement_rows)
    upload_rows_to_sheet(service, disagreement_rows, "Disagreements", clear_before_write=True)
    print("Applying disagreement report background color formatting ...")
    sheets_client.apply_report_formatting(
        service=service, spreadsheet_id=sheets_client.SPREADSHEET_ID,
        tab_name="Disagreements", rows_count=len(disagreement_rows), cols_count=len(disagreement_rows[0]),
        bg_overrides=disagreement_bg)
    print("Uploading missing publishers report ...")
    missing_pub_rows = load_missing_publishers_rows()
    upload_rows_to_sheet(service, missing_pub_rows, "Missing publishers", clear_before_write=True)


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
