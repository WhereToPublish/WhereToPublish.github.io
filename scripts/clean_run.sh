#!/usr/bin/env bash
set -euo pipefail

rm -rf data_extracted/
rm -rf data_merged/
rm -rf data

sh ./scripts/download_extraction.sh
sh ./scripts/download_csv.sh
sh ./scripts/run.sh
