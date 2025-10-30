#!/usr/bin/env bash
set -euo pipefail

# Merge all extracted data into data_merged/
python3 ./scripts/data_merge_dafnee.py

# Process merged data into data/ and build all_biology.csv
python3 ./scripts/data_process.py
