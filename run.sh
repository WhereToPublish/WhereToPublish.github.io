#!/usr/bin/env bash
set -euo pipefail

# Generate merged datasets in data_merged/
python3 ./scripts/data_merge_extraction.py

# Process merged data into data/ and build all_biology.csv
python3 ./scripts/data_process.py
