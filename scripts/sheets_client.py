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
    "generalist":                  "Generalists",
    "anatomy_physiology":          "Anatomy & Physiology",
    "cancer":                      "Cancer",
    "development":                 "Development",
    "ecology_evolution":           "Ecology & Evolution",
    "genetics_genomics":           "Genetics & Genomics",
    "immunology":                  "Immunology",
    "molecular_cellular_biology":  "Molecular & Cellular Biology",
    "neurosciences":               "Neurosciences",
    "plants":                      "Plants",
}

# Scopes ─ use readonly when only downloading; use full when uploading too
_SCOPE_READONLY = "https://www.googleapis.com/auth/spreadsheets.readonly"
_SCOPE_READWRITE = "https://www.googleapis.com/auth/spreadsheets"


def get_sheets_service(
    credentials_path: Path | None = None,
    readonly: bool = True,
) -> Any:
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


def download_tab_as_csv(
    service: Any,
    tab_name: str,
    dest_path: Path,
    spreadsheet_id: str = SPREADSHEET_ID,
) -> list[list[str]]:
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


def write_rows(
    service: Any,
    spreadsheet_id: str,
    tab_name: str,
    rows: list[list[Any]],
    value_input_option: str = "USER_ENTERED",
) -> None:
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


def upload_tab_from_csv(
    service: Any,
    csv_path: Path,
    tab_name: str,
    spreadsheet_id: str = SPREADSHEET_ID,
) -> int:
    """Upload CSV data to a Google Sheets tab (values only — formatting is untouched).

    Writes all rows from the CSV starting at A1 of the target tab.  Only cell
    values are updated; existing cell formatting, data-validation rules, and
    dropdown menus in the sheet are preserved because we use spreadsheets.values.update
    (not batchUpdate with format requests).

    Args:
        service: Authenticated Sheets API service with write scope.
        csv_path: Path to the enriched CSV file to upload.
        tab_name: Exact name of the Google Sheets tab to write to.
        spreadsheet_id: Google Sheets spreadsheet ID (default: WhereToPublish).

    Returns:
        Number of data rows written (excluding header).
    """
    rows = read_csv_as_rows(csv_path)
    n_cols = len(rows[0])
    # Pad every row to the header width so the update range covers all columns
    padded_rows = [row + [""] * (n_cols - len(row)) for row in rows]

    # Validate tab exists in the spreadsheet
    spreadsheet_meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing_titles = {s["properties"]["title"] for s in spreadsheet_meta["sheets"]}
    assert tab_name in existing_titles, (
        f"Tab '{tab_name}' not found in spreadsheet {spreadsheet_id}. "
        f"Available tabs: {sorted(existing_titles)}"
    )

    write_rows(service, spreadsheet_id, tab_name, padded_rows, value_input_option="USER_ENTERED")
    data_rows = len(rows) - 1  # exclude header
    print(f"  Uploaded {data_rows} data rows to tab '{tab_name}' (spreadsheet {spreadsheet_id})")
    return data_rows
