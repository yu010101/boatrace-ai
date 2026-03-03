#!/bin/bash
# 初回: ログディレクトリ作成 + ML訓練 + launchd登録
set -euo pipefail

PROJ_DIR=/Users/yu01/projects/boatrace-ai
LAUNCHD_SRC="$PROJ_DIR/scripts/launchd"
LAUNCHD_DST=~/Library/LaunchAgents
GUI_DOMAIN="gui/$(id -u)"

mkdir -p ~/.boatrace-ai/logs
cd "$PROJ_DIR"
source .venv/bin/activate

echo "=== MLモデル初回訓練 ==="
boatrace train --days 90

echo "=== 既存crontabからboatraceエントリ削除 ==="
if crontab -l 2>/dev/null | grep -q boatrace; then
  crontab -l 2>/dev/null | grep -v 'boatrace\|# Boatrace' | crontab -
  echo "crontab entries removed"
else
  echo "no boatrace crontab entries found"
fi

echo "=== launchd plistインストール ==="
PLISTS=(
  com.boatrace.ai.morning
  com.boatrace.ai.evening
  com.boatrace.ai.weekly-train
)

for label in "${PLISTS[@]}"; do
  # 既存サービスがあれば停止
  launchctl bootout "$GUI_DOMAIN/$label" 2>/dev/null || true
  # plistをコピー
  cp "$LAUNCHD_SRC/$label.plist" "$LAUNCHD_DST/"
  # サービス登録
  launchctl bootstrap "$GUI_DOMAIN" "$LAUNCHD_DST/$label.plist"
  echo "  registered: $label"
done

echo "=== 登録確認 ==="
launchctl list | grep boatrace

echo "=== セットアップ完了 ==="
