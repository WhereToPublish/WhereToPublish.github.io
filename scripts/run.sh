#!/usr/bin/env bash
set -euo pipefail

# Extract data from various sources into data_extracted/
python3 ./scripts/update_extracted.py

# Merge all extracted data into data_merged/
python3 ./scripts/data_merge_dafnee.py

# Process merged data into data/ and build all_biology.csv
python3 ./scripts/data_process.py
