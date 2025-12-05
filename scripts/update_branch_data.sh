#!/usr/bin/env bash
set -euo pipefail

# Push main and rebase data branch onto main, pushing both to origin
# Checkout main branch, push to origin
git checkout main
git push origin main
git reset --hard

# Checkout data branch, rebase onto main, amend last commit to include data and data_extraction folders, push to origin
git checkout data
git rebase main
git reset --soft HEAD~1

# You might neet to run `download_extraction.sh` if you don't have the data_extraction files yet
# sh ./scripts/download_extraction.sh
#
# Update data: download csv files and process them
sh ./scripts/run.sh

# Add data, data_extraction and data_extracted folders to the last commit and force push to origin
git add data/
git add data_extracted/
git add data_extraction/
git commit -m "Extract data from DOAJ, OpenAPC, Scimago and update data files"
git push origin data --force

# Checkout main branch again
git checkout main
git checkout data -- data/
git checkout data -- data_extracted/
git checkout data -- data_extraction/
git reset