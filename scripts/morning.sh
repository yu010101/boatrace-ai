#!/bin/bash

# ── 2026-09-16 時刻ガード ──────────────────────────────────────────────
# launchd が JST から +16h ずれて発火していた(朝の予測が23:30=全レース終了後)。
# plist を StartInterval(30分毎) に変え、実行可否はここで JST 実時刻から判定する。
# 1日1回だけ本体を走らせる(マーカー)。TZ を明示するので launchd 側のTZ設定に依存しない。
JST_HM=$(TZ=Asia/Tokyo date +%H%M); JST_D=$(TZ=Asia/Tokyo date +%Y%m%d)
MARK="$HOME/.boatrace-ai/state/morning_${JST_D}.done"; mkdir -p "$HOME/.boatrace-ai/state"
if (( 10#$JST_HM < 830 || 10#$JST_HM > 929 )); then exit 0; fi
[[ -f "$MARK" ]] && exit 0
touch "$MARK"
# ──────────────────────────────────────────────────────────────────────

# 朝: 予測 → 推奨度記事(無料publish) → 有料Sランク記事(¥980 publish)
cd /Users/apple/projects/boatrace-ai
source .venv/bin/activate
set -o pipefail

LOG=~/.boatrace-ai/logs/morning_$(date +%Y%m%d).log
mkdir -p ~/.boatrace-ai/logs

{
  echo "=== $(date) morning job start ==="
  boatrace predict today --mode ml
# [PAUSED 2026-09-16 ユーザー指示: 外部投稿を停止]   boatrace publish grades || echo "[WARN] grades publish failed (may be already-published today)"
# [PAUSED 2026-09-16 ユーザー指示: 外部投稿を停止]   boatrace publish premium || echo "[WARN] premium publish failed (may be already-published today)"
  echo "=== $(date) morning job end ==="
} >> "$LOG" 2>&1
