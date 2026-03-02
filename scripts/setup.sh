#!/bin/bash
# 初回: ログディレクトリ作成 + ML訓練 + cron登録
mkdir -p ~/.boatrace-ai/logs
cd /Users/yu01/projects/boatrace-ai
source .venv/bin/activate

echo "=== MLモデル初回訓練 ==="
boatrace train --days 90

echo "=== crontab 登録 ==="
# 既存crontabを保持しつつ追加
(crontab -l 2>/dev/null; cat <<'CRON'

# Boatrace AI daily automation
30 7  * * * /Users/yu01/projects/boatrace-ai/scripts/morning.sh
30 21 * * * /Users/yu01/projects/boatrace-ai/scripts/evening.sh
0  3  * * 0 /Users/yu01/projects/boatrace-ai/scripts/weekly_train.sh
CRON
) | crontab -

echo "=== 登録確認 ==="
crontab -l | grep boatrace

echo "=== セットアップ完了 ==="
