"""sheets_client.py — Shared Google Sheets API helper for the journal-metadata-enrichment project.

Provides authenticated access to the WhereToPublish spreadsheet using a service account.
Credentials are resolved from the GOOGLE_SERVICE_ACCOUNT_KEY environment variable or the
default path ~/.config/wheretopublish/google_service_account.json.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

SPREADSHEET_ID = "1PRXViyQlo5ZMjpCJ_XpcHfsnZEJmmdCiXjnkazMyua8"

# Name of the auxiliary tab containing configuration variables (country, publisher mappings, etc.)
VARIABLES_TAB_NAME = "variables"

# Minimum number of data rows (excluding header) required before any upload is allowed.
MIN_DATA_ROWS = 15

DEFAULT_CREDENTIALS_PATH = Path(
    os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_KEY",
        os.path.expanduser("~/.config/wheretopublish/google_service_account.json"),
    )
)

# Map field slugs (used by CLI/gap_analysis) to Google Sheets tab names
SHEET_TAB_NAMES: dict[str, str] = {
    "generalist": "Generalist",
    "anatomy_physiology": "Anatomy & Physiology",
    "cancer": "Cancer",
    "development": "Development",
    "ecology_evolution": "Ecology & Evolution",
    "genetics_genomics": "Genetics & Genomics",
    "immunology": "Immunology",
    "molecular_cellular_biology": "Molecular & Cellular Biology",
    "neurosciences": "Neurosciences",
    "plants": "Plants",
}

# Scopes ─ use readonly when only downloading; use full when uploading too
_SCOPE_READONLY = "https://www.googleapis.com/auth/spreadsheets.readonly"
_SCOPE_READWRITE = "https://www.googleapis.com/auth/spreadsheets"


def get_sheets_service(credentials_path: Path | None = None, readonly: bool = True) -> Any:
    """Return an authenticated Google Sheets API v4 service resource.

    Args:
        credentials_path: Path to the service-account JSON key file.
            Defaults to DEFAULT_CREDENTIALS_PATH.
        readonly: When True, requests only the spreadsheets.readonly scope.
            Set False when the caller needs write access (e.g. upload_suggestions).
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds_path = credentials_path or DEFAULT_CREDENTIALS_PATH
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google service-account credentials not found: {creds_path}\n"
            "Set GOOGLE_SERVICE_ACCOUNT_KEY or place the key at the default path."
        )

    scope = _SCOPE_READONLY if readonly else _SCOPE_READWRITE
    creds = service_account.Credentials.from_service_account_file(
        str(creds_path),
        scopes=[scope],
    )
    return build("sheets", "v4", credentials=creds)


def download_tab_as_csv(service: Any, tab_name: str,
                        dest_path: Path, spreadsheet_id: str = SPREADSHEET_ID) -> list[list[str]]:
    """Download a single tab from the spreadsheet and write it as a CSV file.

    Args:
        service: Authenticated Sheets API service (from get_sheets_service).
        tab_name: The exact name of the tab as shown in Google Sheets.
        dest_path: Local path where the CSV file will be written.
        spreadsheet_id: Google Sheets spreadsheet ID (default: WhereToPublish).

    Returns:
        The rows as a list-of-lists (including the header row).
    """
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=tab_name,
            valueRenderOption="FORMATTED_VALUE",
            dateTimeRenderOption="FORMATTED_STRING",
        )
        .execute()
    )
    rows: list[list[str]] = result.get("values", [])

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerows(rows)

    return rows


def write_rows(service: Any, spreadsheet_id: str, tab_name: str, rows: list[list[Any]],
               value_input_option: str = "USER_ENTERED") -> None:
    """Write a list of rows to a tab starting at A1."""
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{tab_name}!A1",
        valueInputOption=value_input_option,
        body={"values": rows},
    ).execute()


def read_csv_as_rows(csv_path: Path) -> list[list[str]]:
    """Read a CSV file and return its contents as a list-of-lists (including header row).

    Empty trailing cells on each row are preserved so that the row length matches the
    header length (Google Sheets uses the header width to size the update range).

    Args:
        csv_path: Path to the CSV file.

    Returns:
        List of rows, each row being a list of string cell values.
    """
    with open(csv_path, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    assert len(rows) >= 2, f"CSV at {csv_path} has fewer than 2 rows (header + data); got {len(rows)}"
    return rows


def recreate_sheet_tab(service: Any, spreadsheet_id: str, tab_name: str) -> None:
    """Delete a sheet tab if it exists, then create a fresh one with the same name.

    Used for report tabs (Disagreements, Missing publishers) that should be
    completely replaced on each run rather than updated in-place.

    Args:
        service: Authenticated Sheets API service with write scope.
        spreadsheet_id: Google Sheets spreadsheet ID.
        tab_name: Exact name of the tab to recreate.
    """
    spreadsheet_meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing = {s["properties"]["title"]: s["properties"]["sheetId"] for s in spreadsheet_meta["sheets"]}
    requests: list[dict] = []
    if tab_name in existing:
        requests.append({"deleteSheet": {"sheetId": existing[tab_name]}})
    requests.append({"addSheet": {"properties": {"title": tab_name}}})
    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}, ).execute()
    print(f"  Recreated sheet tab '{tab_name}'.")


def get_sheet_properties(service: Any, spreadsheet_id: str, tab_name: str) -> dict[str, int]:
    """Return basic properties for *tab_name*: sheetId, rowCount, and columnCount."""
    spreadsheet_meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    matching = [s["properties"] for s in spreadsheet_meta["sheets"] if s["properties"]["title"] == tab_name]
    assert len(matching) == 1, f"Expected one sheet named '{tab_name}', found {len(matching)}"
    props = matching[0]
    grid = props.get("gridProperties", {})
    return {
        "sheetId": int(props["sheetId"]),
        "rowCount": int(grid.get("rowCount", 0)),
        "columnCount": int(grid.get("columnCount", 0)),
    }


def clear_tab_values(service: Any, spreadsheet_id: str, tab_name: str) -> None:
    """Clear all cell values in a tab while preserving formatting and validation."""
    service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=tab_name, body={}, ).execute()


def chunked_batch_update(service: Any, spreadsheet_id: str, requests: list[dict], chunk_size: int = 500) -> None:
    """Send batchUpdate requests in chunks to avoid API limits."""
    assert chunk_size > 0, f"chunk_size must be > 0, got {chunk_size}"
    if not requests:
        return
    for start in range(0, len(requests), chunk_size):
        chunk = requests[start:start + chunk_size]
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": chunk}, ).execute()


def rgb_from_hex(hex_color: str) -> dict[str, float]:
    """Convert hex color like 'FBE7E7' or '#FBE7E7' to Sheets RGB floats."""
    value = hex_color.strip().lstrip("#")
    assert len(value) == 6, f"Hex color must be 6 chars, got '{hex_color}'"
    r = int(value[0:2], 16) / 255.0
    g = int(value[2:4], 16) / 255.0
    b = int(value[4:6], 16) / 255.0
    return {"red": r, "green": g, "blue": b}


def apply_report_formatting(service: Any, spreadsheet_id: str, tab_name: str, rows_count: int, cols_count: int,
                            bg_overrides: list[tuple[int, int, str]] | None = None, ) -> None:
    """Apply deterministic formatting to a rectangular report range.

    Applies base text formatting to all cells, bold+grey header row style, white
    default data-cell backgrounds, and optional per-cell background overrides.

    Args:
        rows_count: Number of table rows written (including header row).
        cols_count: Number of table columns written.
        bg_overrides: List of (row_idx, col_idx, hex_color) for per-cell background overrides.
                      Indices are 0-based and relative to the table range starting at A1.
    """
    assert rows_count >= 1, f"rows_count must be >= 1, got {rows_count}"
    assert cols_count >= 1, f"cols_count must be >= 1, got {cols_count}"

    props = get_sheet_properties(service, spreadsheet_id, tab_name)
    sheet_id = props["sheetId"]

    requests: list[dict] = []
    for row_idx, col_idx, color_hex in bg_overrides:
        assert row_idx >= 1, f"Override row index must be >= 1 (data rows only), got {row_idx}"
        assert row_idx < rows_count, f"Override row out of bounds: {row_idx} >= {rows_count}"
        assert col_idx >= 0, f"Override col index must be >= 0, got {col_idx}"
        assert col_idx < cols_count, f"Override col out of bounds: {col_idx} >= {cols_count}"
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_idx,
                        "endRowIndex": row_idx + 1,
                        "startColumnIndex": col_idx,
                        "endColumnIndex": col_idx + 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": rgb_from_hex(color_hex),
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor",
                }
            }
        )

    chunked_batch_update(service, spreadsheet_id, requests)
