#!/usr/bin/env bash
set -euo pipefail

rm -rf data_extracted/
rm -rf data_extraction/
rm -rf data

sh ./scripts/download_extraction.sh
sh ./scripts/download_csv.sh

python3 ./scripts/update_extracted.py
python3 ./scripts/data_process.py
