#!/usr/bin/env bash
set -euo pipefail
mkdir -p logs
sh ./scripts/download_csv.sh > logs/download_csv.log 2>&1

python3 ./scripts/update_extracted.py > logs/update_extracted.log 2>&1
python3 ./scripts/data_process.py > logs/data_process.log 2>&1