#!/usr/bin/env bash
set -euo pipefail
rm -rf zenodo
mkdir -p zenodo
# Create a zip archive of the data folder containing only csv files (not starting with APC_)
zip -r zenodo/data.zip data -i "*.csv" -x "data/APC_*.csv"
# Create a zip archive of the data_extracted folder containing only csv files
zip -r zenodo/data_extracted.zip data_extracted -i "*.csv"