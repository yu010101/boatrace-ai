#!/bin/bash

# ── 2026-09-16 時刻ガード ──────────────────────────────────────────────
# launchd が JST から +16h ずれて発火していた(朝の予測が23:30=全レース終了後)。
# plist を StartInterval(30分毎) に変え、実行可否はここで JST 実時刻から判定する。
# 1日1回だけ本体を走らせる(マーカー)。TZ を明示するので launchd 側のTZ設定に依存しない。
JST_HM=$(TZ=Asia/Tokyo date +%H%M); JST_D=$(TZ=Asia/Tokyo date +%Y%m%d)
MARK="$HOME/.boatrace-ai/state/evening_${JST_D}.done"; mkdir -p "$HOME/.boatrace-ai/state"
if (( 10#$JST_HM < 2230 || 10#$JST_HM > 2329 )); then exit 0; fi
[[ -f "$MARK" ]] && exit 0
touch "$MARK"
# ──────────────────────────────────────────────────────────────────────

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
  # 2026-10-20 本人「無料記事だけ再開」
# [PAUSED 2026-10-28 GitHub Actions と二重公開になるため。公開は GH Actions boatrace.yml の1本]   boatrace publish results || echo "[WARN] results publish failed"
  echo "=== $(date) evening job end ==="
} >> "$LOG" 2>&1
