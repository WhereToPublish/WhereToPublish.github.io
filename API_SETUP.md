# Google Sheets API — Setup Guide

This document explains how to set up Google Sheets API credentials so that the
WhereToPublish data pipeline can download and upload data automatically.

---

## Overview

The pipeline authenticates with Google Sheets using a **service account** — a
non-human Google identity that can be granted access to specific spreadsheets.
The credentials are stored as a JSON key file and are never committed to the
repository.

---

## 1. Create a Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/).
2. Click **Select a project → New Project**.
3. Give it a name (e.g. `wheretopublish`) and click **Create**.

---

## 2. Enable the Google Sheets API

1. In the Cloud Console, open **APIs & Services → Library**.
2. Search for **"Google Sheets API"** and click **Enable**.

---

## 3. Create a Service Account

1. Go to **APIs & Services → Credentials**.
2. Click **Create Credentials → Service Account**.
3. Name it (e.g. `wheretopublish-bot`) and click **Create and Continue**.
4. Skip the optional role and user access steps — click **Done**.

---

## 4. Download the JSON Key

1. In the Credentials page, click the service account you just created.
2. Go to the **Keys** tab → **Add Key → Create new key**.
3. Choose **JSON** and click **Create**. The key file downloads automatically.
4. Rename it to `google_service_account.json` and keep it safe — treat it like a
   password.

---

## 5. Share the Spreadsheet with the Service Account

The service account has an email address like:
```
wheretopublish-bot@your-project-id.iam.gserviceaccount.com
```

1. Open the [WhereToPublish Google Sheet](https://docs.google.com/spreadsheets/d/1PRXViyQlo5ZMjpCJ_XpcHfsnZEJmmdCiXjnkazMyua8).
2. Click **Share** (top-right).
3. Paste the service account email and set the permission to **Editor**
   (required for upload; Reader is sufficient for download-only).
4. Click **Share**.

---

## 6. Local Setup

Place the key file at the default path so the scripts find it automatically:

```bash
mkdir -p ~/.config/wheretopublish
mv ~/Downloads/google_service_account.json ~/.config/wheretopublish/google_service_account.json
chmod 600 ~/.config/wheretopublish/google_service_account.json
```

Alternatively, point to it via the environment variable:

```bash
export GOOGLE_SERVICE_ACCOUNT_KEY=/path/to/your/google_service_account.json
```

### Test the setup

```bash
# Download all 10 field tabs
python3 scripts/download_sheets.py

# Upload genetics_genomics enriched data to Test_upload (after running the pipeline)
python3 scripts/upload_sheets.py
```

Or run the full pipeline:

```bash
bash scripts/run.sh
```

### Single-field download (CLI helper)

```bash
# Download one specific field tab
python3 scripts/fetch_sheet.py --field genetics_genomics --output data_extracted/genetics_genomics.csv
```

---

## 7. GitHub Actions Setup

The GitHub Actions workflow (`extract-data.yml`) reads the key from a repository
secret named **`GOOGLE_SHEETS_KEY_JSON`**.

### Add the secret

1. In the GitHub repository, go to **Settings → Secrets and variables → Actions**.
2. Click **New repository secret**.
3. Name: `GOOGLE_SHEETS_KEY_JSON`
4. Value: paste the **entire contents** of `google_service_account.json` (the
   raw JSON object, not a file path).
5. Click **Add secret**.

The workflow step that uses it:

```yaml
- name: Setup Google Sheets credentials
  env:
    GOOGLE_SHEETS_KEY_JSON: ${{ secrets.GOOGLE_SHEETS_KEY_JSON }}
  run: |
    echo "$GOOGLE_SHEETS_KEY_JSON" > /tmp/gsa_key.json
    echo "GOOGLE_SERVICE_ACCOUNT_KEY=/tmp/gsa_key.json" >> $GITHUB_ENV
```

This writes the JSON to a temporary file and sets `GOOGLE_SERVICE_ACCOUNT_KEY`
for all subsequent steps. The file is discarded when the runner exits.

---

## Security Notes

- **Never commit** `google_service_account.json` to the repository.
- The `.gitignore` should exclude `*.json` credential files.
- The service account has **Editor** access only to the specific spreadsheet you
  shared it with — it cannot access other Drive files.
- For read-only workflows (download only), you can grant **Viewer** access
  instead of Editor.

---

## Credential Resolution Order

The scripts resolve credentials in this order:

1. `--credentials PATH` CLI argument (if provided)
2. `GOOGLE_SERVICE_ACCOUNT_KEY` environment variable
3. `~/.config/wheretopublish/google_service_account.json` (default path)

If none of these exist, the script will raise a `FileNotFoundError` with a clear
message.
