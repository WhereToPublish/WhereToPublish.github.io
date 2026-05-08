# DONE

## Google Sheets API Integration — May 2026

### What was done

Replaced the wget-based `download_csv.sh` with a proper Google Sheets API
integration for both downloading and uploading journal data.

#### Download

- **`scripts/download_sheets.py`** (new): Downloads all 10 field tabs from
  the WhereToPublish Google Sheet to `data_extracted/` using the Sheets API
  v4. Replaces `scripts/download_csv.sh`.

#### Upload

- **`scripts/upload_sheets.py`** (new): Uploads the enriched
  `data_extracted/genetics_genomics.csv` to the **"Test_upload"** tab in
  Google Sheets for validation. Only cell values are written — formatting,
  dropdowns, and data-validation rules in the sheet are untouched.

#### Shared client

- **`scripts/sheets_client.py`** (refactored):
  - Added `TEST_UPLOAD_TAB = "Test_upload"` constant.
  - Added `read_csv_as_rows()` helper with assertion on minimum row count.
  - Added `upload_tab_from_csv()` with tab-existence assertion.
  - Removed unused `load_suggestion_keys_from_tabs()` function (contained try/except; had no callers).
  - Removed unused `import io`.

#### CLI helper

- **`scripts/fetch_sheet.py`** (refactored): Removed all try/except blocks;
  errors now propagate naturally. Default output path updated from
  `agent/output/raw_genetics_genomics.csv` to `data_extracted/genetics_genomics.csv`.

#### Entry points updated

| File | Change |
|------|--------|
| `scripts/run.sh` | `download_csv.sh` → `download_sheets.py`; added `upload_sheets.py` |
| `scripts/clean_run.sh` | Same substitutions |
| `scripts/update_branch_data.sh` | `download_csv.sh` → `download_sheets.py` |
| `.github/workflows/extract-data.yml` | Added "Setup Google Sheets credentials" step (writes `GOOGLE_SHEETS_KEY_JSON` secret to `/tmp/gsa_key.json`, exports `GOOGLE_SERVICE_ACCOUNT_KEY`) |

#### Dependencies

- **`requirements.txt`**: Added `google-api-python-client>=2.0` and `google-auth>=2.0`.

#### Documentation

- **`API_SETUP.md`** (new): Step-by-step guide for GCP project creation,
  enabling the Sheets API, service account setup, key download, sharing the
  spreadsheet, local credential configuration, and GitHub Actions secret setup.
- **`README.md`**: Updated pipeline section, Key Scripts table, and local
  development instructions.

### Test results

- `python3 scripts/download_sheets.py` — downloaded all 10 tabs (175–519 rows
  each) successfully.
- Full pipeline `bash scripts/run.sh` — completed without errors.
- `python3 scripts/upload_sheets.py` — uploaded 110 data rows to "Test_upload"
  tab. Awaiting manual confirmation that formatting/dropdowns are intact.

### Next steps (after Test_upload validation)

Once the upload to "Test_upload" is confirmed correct:
1. Update `upload_sheets.py` to upload each field's enriched CSV to its
   corresponding real tab (using `SHEET_TAB_NAMES`).
2. Remove `TEST_FIELD_SLUG` hardcoding and loop over all field slugs.
