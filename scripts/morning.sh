#!/bin/bash
# 朝: 予測 → 推奨度記事(無料publish) → 有料Sランク記事(¥980 publish)
cd /Users/apple/projects/boatrace-ai
source .venv/bin/activate
set -o pipefail

LOG=~/.boatrace-ai/logs/morning_$(date +%Y%m%d).log
mkdir -p ~/.boatrace-ai/logs

{
  echo "=== $(date) morning job start ==="
  boatrace predict today --mode ml
  boatrace publish grades || echo "[WARN] grades publish failed (may be already-published today)"
  boatrace publish premium || echo "[WARN] premium publish failed (may be already-published today)"
  echo "=== $(date) morning job end ==="
} >> "$LOG" 2>&1
