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
git push origin data --force

# Checkout main branch again
git checkout main
git checkout data -- data/
git checkout data -- data_extracted/
git checkout data -- data_extraction/
git reset