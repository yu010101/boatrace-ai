#!/bin/bash
# 夜: 結果取得 → 照合 → 回収率 → 結果レポート publish
cd /Users/apple/projects/boatrace-ai
source .venv/bin/activate
set -o pipefail

LOG=~/.boatrace-ai/logs/evening_$(date +%Y%m%d).log
mkdir -p ~/.boatrace-ai/logs

{
  echo "=== $(date) evening job start ==="
  boatrace results fetch
  boatrace results check
  boatrace roi check
  boatrace roi today
  boatrace publish results || echo "[WARN] results publish failed"
  echo "=== $(date) evening job end ==="
} >> "$LOG" 2>&1
