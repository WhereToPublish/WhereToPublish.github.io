"""review_common.py — Shared review-tab schema and upload helpers.

Both review workflows of the project upload rows carrying a **Status** column
(`pending` / `approve` / `reject`) to a dedicated Google Sheet tab:

- the **deterministic disagreement report** computed on every pipeline run
  (logs/disagreements.csv → the `Disagreements` tab), and
- the **non-deterministic AI suggestions** of the journal-metadata-enrichment
  project (agent/output/Agent_suggestions.csv → the `Agent_suggestions` tab).

Both tabs share the same apply-row schema, so a single Google Apps Script can
process them: each row records the exact cell to change (`data_tab`,
`target_row`, `target_col`) plus the verification values (`journal`, `field`,
`current_value`), so the script never scans whole data tabs — it verifies the
target cell and performs a single-cell write.

Rows are uploaded with Status `pending`; a reviewer sets `approve` or `reject`,
and the Apps Script archives processed rows in `<tab>_processed` and deletes
them from the review tab.

This module is the single source of truth for the schema; it is imported both
by the WhereToPublish scripts and by the journal-metadata-enrichment project
(which already puts the parent `scripts/` directory on sys.path to import
`sheets_client`).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from libraries import FINAL_COLUMNS, norm_name
import sheets_client

# --------------------------------------------------------------------------
# Shared review-row schema
# --------------------------------------------------------------------------

STATUS_PENDING = "pending"
STATUS_APPROVE = "approve"
STATUS_REJECT = "reject"
REVIEW_STATUSES = [STATUS_PENDING, STATUS_APPROVE, STATUS_REJECT]

STATUS_COLUMN = "Status"

# Column names used by the Google Apps Script to apply an approved row.
# All of them (plus the Status column) must exist in every review tab.
# Values in these columns are kept raw (no colors / no HYPERLINK formulas).
STATUS_APPLY_COLUMNS = [
    "journal",
    "field",
    "current_value",
    "suggested_value",
    "suggestion_type",
    "data_tab",
    "target_row",
    "target_col",
]

# Suggestion types handled by the Apps Script.
SUGGESTION_TYPES = ["fill", "correct", "alt_name", "remove"]

# Review tabs of the spreadsheet.
DISAGREEMENTS_TAB = "Disagreements"
SUGGESTIONS_TAB = "Agent_suggestions"

# Full column order of the disagreement report (CSV and uploaded tab).
# Both review tabs (this one and Agent_suggestions) share the same leading
# columns (Status + apply-row schema + priority), tab-specific context
# columns (the external evidence plus a factual `reasoning` justifying the
# priority, as in the AI suggestions), and the shared target-cell columns
# (data_tab, target_row, target_col) last. `field` is the dataset column whose
# value conflicts with the external sources.
DISAGREEMENT_COLUMNS = [
    STATUS_COLUMN,
    "journal",
    "field",
    "current_value",
    "suggested_value",
    "suggestion_type",
    "priority",
    "url",
    "reasoning",
    "Scimago_value",
    "DOAJ_value",
    "OpenAPC_value",
    "data_tab",
    "target_row",
    "target_col",
]

# Data columns whose conflicts are reported (must all exist in FINAL_COLUMNS).
DISAGREEMENT_DATA_COLUMNS = [
    "Publisher",
    "Publisher type",
    "Business model",
    "e-ISSN",
    "p-ISSN",
    "APC Euros",
]

# Report columns parsed into per-cell background colors on upload
# ("#RRGGBB; value" prefixes produced by color_value).
DISAGREEMENT_VALUE_COLUMNS = [
    "current_value",
    "suggested_value",
    "Scimago_value",
    "DOAJ_value",
    "OpenAPC_value",
]

# Report columns whose ISSN values are hyperlinked to the ISSN portal on upload.
DISAGREEMENT_ISSN_LINK_COLUMNS = [
    "Scimago_value",
    "DOAJ_value",
    "OpenAPC_value",
]


# --------------------------------------------------------------------------
# Journal → sheet cell location
# --------------------------------------------------------------------------


def build_journal_location_index(data_extracted_dir: Path) -> dict[str, list[tuple[str, int]]]:
    """Index all journals of the data tabs for fast cell-location lookups.

    Reads each field CSV of *data_extracted_dir* (headers + data rows mirroring
    the corresponding Google Sheet tab) and maps the normalized journal name
    to every (tab_name, sheet_row) occurrence. The alternative journal name is
    indexed as a secondary key. sheet_row is the 1-based row number in the
    Google Sheet tab (header = row 1).

    Returns:
        Dict norm_name -> list of (tab_name, sheet_row), in tab order.
    """
    index: dict[str, list[tuple[str, int]]] = {}
    for slug, tab_name in sheets_client.SHEET_TAB_NAMES.items():
        csv_path = Path(data_extracted_dir) / f"{slug}.csv"
        if not csv_path.exists():
            print(f"WARNING: {csv_path} not found — journals of tab '{tab_name}' "
                  "are not indexed for review-row targets.")
            continue
        with open(csv_path, encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            if header is None or "Journal" not in header:
                print(f"WARNING: {csv_path} has no Journal column — skipped.")
                continue
            journal_idx = header.index("Journal")
            alt_idx = header.index("Alternative journal name") \
                if "Alternative journal name" in header else None
            for i, row in enumerate(reader):
                # Sheet row = header row (1) + data offset + 1
                sheet_row = i + 2
                keys = []
                if journal_idx < len(row) and row[journal_idx].strip():
                    keys.append(norm_name(row[journal_idx]))
                if alt_idx is not None and alt_idx < len(row) and row[alt_idx].strip():
                    keys.append(norm_name(row[alt_idx]))
                for key in keys:
                    index.setdefault(key, []).append((tab_name, sheet_row))
    return index


_LOCATION_CACHE: dict[Path, dict[str, list[tuple[str, int]]]] = {}


def locate_journal_cell(data_extracted_dir: Path, journal: str, field: str) -> dict[str, str]:
    """Return the review-row target columns for (journal, field) as strings.

    Looks up the journal in the data tabs (primary name first, then the
    alternative journal name) and the column of *field* in FINAL_COLUMNS.
    The cell is only *recorded* — the Apps Script re-verifies it before
    writing. When the journal is missing, ambiguous (found in more than one
    data tab), or the field is unknown, empty strings are returned so the
    Apps Script reports the row for manual handling.

    Returns:
        Dict with keys data_tab, target_row, target_col (all strings).
    """
    empty = {"data_tab": "", "target_row": "", "target_col": ""}
    if field not in FINAL_COLUMNS:
        print(f"WARNING: field '{field}' is not a data tab column; "
              f"review row for '{journal}' has no target cell.")
        return empty
    data_extracted_dir = Path(data_extracted_dir)
    if data_extracted_dir not in _LOCATION_CACHE:
        _LOCATION_CACHE[data_extracted_dir] = build_journal_location_index(data_extracted_dir)
    index = _LOCATION_CACHE[data_extracted_dir]

    key = norm_name(journal)
    matches = index.get(key, [])
    if not matches:
        print(f"WARNING: journal '{journal}' not found in any data tab; "
              "review row has no target cell.")
        return empty
    tabs = {tab for tab, _ in matches}
    if len(tabs) > 1:
        print(f"WARNING: journal '{journal}' found in multiple data tabs {sorted(tabs)}; "
              "review row has no target cell.")
        return empty
    tab, sheet_row = matches[0]
    return {
        "data_tab": tab,
        "target_row": str(sheet_row),
        "target_col": str(FINAL_COLUMNS.index(field) + 1),
    }


# --------------------------------------------------------------------------
# Shared review-tab upload
# --------------------------------------------------------------------------


def upload_review_tab(
    service: Any,
    spreadsheet_id: str,
    tab_name: str,
    rows: list[list],
    bg_overrides: list[tuple[int, int, str]] | None = None,
    status_validation: bool = True,
) -> int:
    """Replace the content of a review tab with *rows* (Status workflow tab).

    Ensures the tab exists, clears its values (formatting preserved), writes
    the new rows, applies report formatting (optionally with per-cell
    background overrides) and adds a Status dropdown validation.

    Args:
        service: Authenticated Sheets API service with write scope.
        spreadsheet_id: Spreadsheet ID.
        tab_name: Review tab name (created if missing).
        rows: Rows including header at index 0; the header must contain the
              Status column when status_validation is True.
        bg_overrides: Optional per-cell background overrides for
                      apply_report_formatting.
        status_validation: When True, add a pending/approve/reject dropdown
                           to the Status column.

    Returns:
        Number of data rows written (header excluded).
    """
    assert rows, f"rows must not be empty for review tab '{tab_name}'"
    sheets_client.get_or_create_tab(service, spreadsheet_id, tab_name)
    sheets_client.clear_tab_values(service, spreadsheet_id, tab_name)

    n_cols = len(rows[0])
    padded = [row + [""] * (n_cols - len(row)) for row in rows]
    sheets_client.write_rows(service, spreadsheet_id, tab_name, padded)

    if status_validation:
        assert STATUS_COLUMN in rows[0], (
            f"Review tab '{tab_name}' rows must carry a '{STATUS_COLUMN}' column."
        )
        status_col = rows[0].index(STATUS_COLUMN)
        sheets_client.apply_status_validation(
            service, spreadsheet_id, tab_name, column_index=status_col,
            options=REVIEW_STATUSES, rows_count=len(rows),
        )
    sheets_client.apply_report_formatting(
        service=service, spreadsheet_id=spreadsheet_id, tab_name=tab_name,
        rows_count=len(rows), cols_count=n_cols, bg_overrides=bg_overrides,
    )
    data_rows = len(rows) - 1
    print(f"  Uploaded {data_rows} data rows to review tab '{tab_name}'.")
    return data_rows
