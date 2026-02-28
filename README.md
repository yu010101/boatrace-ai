# Boatrace AI

AI（Claude API）を使ったボートレース予想システム。

## セットアップ

```bash
cd ~/projects/boatrace-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`.env` を作成:

```bash
cp .env.example .env
# ANTHROPIC_API_KEY を設定
```

## 使い方

```bash
# 本日の全レース予測
boatrace predict today

# 特定の場のみ
boatrace predict today --stadium 1

# 出走表だけ確認（API呼ばない）
boatrace predict today --dry-run

# 単一レース予測
boatrace predict race --stadium 1 --race 1

# 結果を取得・保存
boatrace results fetch 2026-02-27

# 予測と結果を比較
boatrace results check

# 精度レポート
boatrace stats

# 詳細ログ
boatrace -v predict today --stadium 1
```

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
