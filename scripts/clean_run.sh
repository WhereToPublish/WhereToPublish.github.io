#!/usr/bin/env bash
set -euo pipefail

rm -rf data_extracted/
rm -rf data_extraction/
rm -rf data

sh ./scripts/download_extraction.sh
python3 ./scripts/download_sheets.py

python3 ./scripts/update_extracted.py
python3 ./scripts/data_process.py
python3 ./scripts/APC_process.py
python3 ./scripts/upload_sheets.py
