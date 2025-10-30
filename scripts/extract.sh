#!/usr/bin/env bash
set -euo pipefail

# Download raw data into raw_data/
./scripts/download_csv.sh

# Generate list of journals to process (journals.txt) from raw_data
source /Users/tlatrille/Documents/venv/py312stats/bin/activate
python3 ./scripts/extract_list_journals.py

source /Users/tlatrille/Documents/venv/dafneeditor/bin/activate
python3 /Users/tlatrille/Documents/dafneeditor/manage.py extract_data_from_file /Users/tlatrille/Documents/WhereToPublish/data_extraction/journals.txt /Users/tlatrille/Documents/WhereToPublish/data_extraction

# Data extraction from raw_data to data_extracted/
source /Users/tlatrille/Documents/venv/py312stats/bin/activate
python3 ./scripts/data_extraction.py
