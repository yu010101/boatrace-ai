#!/bin/bash
# 朝: 予測 → 推奨度記事(dry-run) → ツイート(skip)
cd /Users/yu01/projects/boatrace-ai
source .venv/bin/activate
set -o pipefail

LOG=~/.boatrace-ai/logs/morning_$(date +%Y%m%d).log
mkdir -p ~/.boatrace-ai/logs

{
  echo "=== $(date) morning job start ==="
  boatrace predict today --mode ml
  boatrace publish grades --dry-run
  echo "=== $(date) morning job end ==="
} >> "$LOG" 2>&1
