#!/bin/bash
# 週次: モデル再訓練 + ログクリーンアップ
cd /Users/yu01/projects/boatrace-ai
source .venv/bin/activate

LOG_DIR=~/.boatrace-ai/logs
LOG="$LOG_DIR/train_$(date +%Y%m%d).log"
mkdir -p "$LOG_DIR"

{
  echo "=== $(date) weekly train start ==="
  boatrace train --days 90
  echo "=== $(date) weekly train end ==="

  echo "=== $(date) log cleanup ==="
  # 30日超のdate付きログを削除
  find "$LOG_DIR" -name '*_20[0-9][0-9][0-9][0-9][0-9][0-9].log' -mtime +30 -delete -print
  # launchd stdout/stderrログを truncate
  for f in "$LOG_DIR"/launchd_*.log; do
    [ -f "$f" ] && : > "$f"
  done
  echo "log cleanup done"
} >> "$LOG" 2>&1
