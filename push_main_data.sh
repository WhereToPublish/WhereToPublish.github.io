#!/usr/bin/env bash
set -euo pipefail
# Push main and rebase data branch onto main, pushing both to origin
# Checkout main branch, push to origin
git checkout main
git push origin main
# Checkout data branch, rebase onto main, push to origin
git checkout data
git rebase main
git push origin data --force