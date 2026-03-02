#!/bin/bash
# 週次: モデル再訓練
cd /Users/yu01/projects/boatrace-ai
source .venv/bin/activate

LOG=~/.boatrace-ai/logs/train_$(date +%Y%m%d).log
mkdir -p ~/.boatrace-ai/logs

{
  echo "=== $(date) weekly train start ==="
  boatrace train --days 90
  echo "=== $(date) weekly train end ==="
} >> "$LOG" 2>&1
