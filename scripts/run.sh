#!/usr/bin/env bash
set -euo pipefail

sh ./scripts/download_csv.sh

python3 ./scripts/update_extracted.py
python3 ./scripts/data_process.py