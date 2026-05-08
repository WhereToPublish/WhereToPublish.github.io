"""fetch_sheet.py — Download a single Google Sheet tab as CSV using the Sheets API.

Usage:
    python3 fetch_sheet.py [--field FIELD] [--output OUTPUT_PATH] [--credentials PATH]

By default downloads the Genetics & Genomics tab to data_extracted/genetics_genomics.csv.

Requires a Google service-account credentials file. Set GOOGLE_SERVICE_ACCOUNT_KEY or
place the key at ~/.config/wheretopublish/google_service_account.json.
"""

import argparse
from pathlib import Path

import sheets_client


def main() -> None:
    default_output = str(Path("data_extracted") / "genetics_genomics.csv")

    parser = argparse.ArgumentParser(description="Download a WhereToPublish Google Sheet tab as CSV.")
    parser.add_argument(
        "--field",
        choices=list(sheets_client.SHEET_TAB_NAMES.keys()),
        default="genetics_genomics",
        help=f"Field slug to download (default: genetics_genomics). Available: {list(sheets_client.SHEET_TAB_NAMES.keys())}",
    )
    parser.add_argument(
        "--output",
        default=default_output,
        help=f"Output CSV path (default: {default_output})",
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=None,
        help="Path to service-account JSON key (default: GOOGLE_SERVICE_ACCOUNT_KEY env var or ~/.config/wheretopublish/google_service_account.json)",
    )
    args = parser.parse_args()

    tab_name = sheets_client.SHEET_TAB_NAMES[args.field]
    dest = Path(args.output)

    print(f"Downloading tab '{tab_name}' via Sheets API ...")
    service = sheets_client.get_sheets_service(credentials_path=args.credentials, readonly=True)
    rows = sheets_client.download_tab_as_csv(service, tab_name, dest)

    print(f"  Saved {len(rows)} rows to {dest}")
    assert len(rows) >= 2, f"Downloaded tab '{tab_name}' has fewer than 2 rows — expected header + data"
    print(f"  Header: {','.join(rows[0])[:120]}")


if __name__ == "__main__":
    main()
