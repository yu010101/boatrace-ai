# Boatrace AI

AI（Claude API + LightGBM）を使ったボートレース予想システム。
ML予測 → 推奨度スコアリング → note.com有料記事 → X自動投稿の一気通貫パイプライン。

## アカウント

| プラットフォーム | ユーザー名 | URL |
|-----------------|-----------|-----|
| note | suiri_ai | https://note.com/suiri_ai |
| X (Twitter) | @suiri_ai | https://x.com/suiri_ai |

## セットアップ

```bash
cd ~/projects/boatrace-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# ML機能を使う場合
pip install -e ".[ml]"

# X連携を使う場合
pip install -e ".[social]"

# note.com投稿を使う場合
pip install -e ".[publish]"
```

`.env` を作成:

```bash
cp .env.example .env
# ANTHROPIC_API_KEY を設定（必須）
# NOTE_EMAIL / NOTE_PASSWORD（note.com投稿時）
# TWITTER_API_KEY 等（X投稿時）
```

## コマンド一覧

### 予測

```bash
# 本日の全レース予測（ML+自動グレーディング+仮想ベット保存）
boatrace predict today
boatrace predict today --stadium 1          # 特定場のみ
boatrace predict today --mode ml            # MLモード指定
boatrace predict today --dry-run            # 出走表だけ確認

# 単一レース予測
boatrace predict race --stadium 1 --race 3
boatrace predict race -s 1 -r 3 -d 2026-03-02 --mode ml
```

### MLモデル訓練

```bash
boatrace train                  # 過去90日のデータで訓練
boatrace train --days 180       # 過去180日
boatrace train --val-days 21    # 検証データ21日分
```

### 結果取得・比較

```bash
boatrace results fetch              # 本日の結果を取得
boatrace results fetch 2026-03-01   # 指定日の結果
boatrace results check              # 予測と結果を比較（+仮想ベット自動照合）
boatrace stats                      # 精度レポート
```

### 回収率トラッキング

```bash
boatrace roi today              # 本日の回収率
boatrace roi check              # 未照合の仮想ベットを結果と照合
boatrace roi summary            # 直近30日の回収率サマリー
boatrace roi summary --days 90  # 直近90日
```

### note.com 記事投稿

```bash
# アカウント管理
boatrace note login             # ログイン（セッション取得）
boatrace note status            # ログイン状態確認

# 記事投稿
boatrace publish today                  # 全レースを有料記事で投稿
boatrace publish today --free           # 無料記事として投稿
boatrace publish today --dry-run        # プレビューのみ
boatrace publish race -s 1 -r 3        # 単一レース記事
boatrace publish grades                 # 推奨度ランク一覧（無料記事）
boatrace publish grades --dry-run       # プレビュー
boatrace publish premium                # Sランクのみ一覧
boatrace publish results                # 前日の的中レポート（+回収率）
boatrace publish results 2026-03-01     # 指定日のレポート
```

### X (Twitter) 投稿

```bash
boatrace tweet morning              # 朝の推奨レースツイート
boatrace tweet morning --dry-run    # プレビューのみ
boatrace tweet hit                  # 的中ツイート（全的中ベット）
boatrace tweet hit --dry-run
boatrace tweet daily                # 日次サマリーツイート
boatrace tweet daily --dry-run
```

## 運用フロー

```bash
# ── 朝（予測 → 記事 → ツイート） ──
boatrace predict today --mode ml
boatrace publish grades             # 無料: 全レース推奨度一覧
boatrace tweet morning              # X: 推奨レース告知

# ── 夜（結果 → 回収率 → ツイート → レポート） ──
boatrace results fetch
boatrace results check              # 精度判定 + 仮想ベット照合
boatrace roi summary
boatrace tweet hit                  # X: 的中報告
boatrace tweet daily                # X: 日次成績サマリー
boatrace publish results            # note: 的中レポート+回収率
```

## 推奨度ランク

| ランク | 条件 | 意味 |
|--------|------|------|
| S | p1 >= 40% かつ top2 >= 55% | 高確信（有料で売る） |
| A | p1 >= 30% かつ top2 >= 45% | 有力候補あり |
| B | p1 >= 20% | 予測可能 |
| C | それ以外 | 混戦（見送り推奨） |

## 競艇場番号

| 番号 | 場 | 番号 | 場 | 番号 | 場 |
|------|------|------|------|------|------|
| 1 | 桐生 | 9 | 津 | 17 | 宮島 |
| 2 | 戸田 | 10 | 三国 | 18 | 徳山 |
| 3 | 江戸川 | 11 | びわこ | 19 | 下関 |
| 4 | 平和島 | 12 | 住之江 | 20 | 若松 |
| 5 | 多摩川 | 13 | 尼崎 | 21 | 芦屋 |
| 6 | 浜名湖 | 14 | 鳴門 | 22 | 福岡 |
| 7 | 蒲郡 | 15 | 丸亀 | 23 | 唐津 |
| 8 | 常滑 | 16 | 児島 | 24 | 大村 |

## テスト

```bash
pytest tests/ -v
```

## データソース

[Boatrace Open API](https://github.com/BoatraceOpenAPI)（非公式、MIT License）
