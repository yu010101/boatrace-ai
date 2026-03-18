# 設計書: 記事品質改善 v2

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/boatrace_ai/storage/database.py` | 的中レースの予測データ取得関数追加、決まり手統計取得関数追加 |
| `src/boatrace_ai/publish/article.py` | 施策1〜4の全変更 |
| `src/boatrace_ai/publish/eyecatch.py` | グラフ画像生成関数追加 |
| `src/boatrace_ai/cli.py` | publish resultsにグラフ画像パス渡し |
| `tests/test_article.py` | 新規テスト追加 |

## 施策1: 的中レースの「なぜ」深掘り

### データフロー
```
accuracy_log (hit_trifecta=1)
  → predictions (analysis, confidence)
  → results (technique_number)
  → _build_hit_analysis(record, prediction, result) → HTML
```

### database.py 新関数
```python
def get_prediction_for_race(race_date, stadium_number, race_number) -> dict | None:
    """predictions + results を JOIN して1レース分のデータ取得"""
```

### article.py 新関数
```python
def _build_hit_analysis(record: dict, prediction: dict | None, result: dict | None) -> str:
    """的中レースに2〜4文の根拠テキストを生成"""
    # - prediction.analysis から1文抜粋
    # - prediction.confidence → 信頼度%
    # - result.technique_number → 決まり手
    # - record.trifecta_payout → 払戻額
```

### _build_accuracy_html 変更
- ハイライトセクションの各的中レースに根拠テキストを追加
- 上位3本のみ深掘り（残りは現行通り）

## 施策2: 累計実績グラフ画像

### eyecatch.py 新関数
```python
async def generate_stats_chart(
    accuracy_trend: list[dict],
    roi_trend: list[dict],
) -> Path | None:
    """30日分の的中率+ROIグラフをHTML→PNG生成"""
```

### HTMLグラフ仕様
- 800x400px PNG
- CSSのみ（JSライブラリ不使用）で棒グラフ+折れ線を表現
- 棒: 日別ROI（%）— COLOR_ACCENT
- 線: 日別1着的中率 — COLOR_HIT
- ブランドカラー準拠

### 記事への組み込み
- cli.py の _publish_results でグラフ生成 → note_client.upload_image → HTML内に<img>埋め込み
- _build_accuracy_html に chart_url 引数追加

## 施策3: 結果記事の文字数増加

### 新セクション: 「本日の傾向分析」
_build_accuracy_html に追加（ハイライトの後）:

```python
def _build_daily_trends(records: list[dict], results_data: list[dict]) -> str:
    """場ごとの傾向分析セクション"""
    # - 1着的中率が高い/低い場
    # - 決まり手分布（逃げ○本、差し○本、まくり○本）
    # - インコース勝率（1号艇が1着の割合）
```

### database.py 新関数
```python
def get_results_for_date(race_date: str) -> list[dict]:
    """当日の全結果(technique_number, actual_order含む)を取得"""
```

## 施策4: タイトルバリエーション

### generate_accuracy_report 変更
タイトル選択ロジック:
```python
# 条件1: 高額払戻（万舟 = ¥10,000+）がある
if max_payout >= 10000:
    title = f"万舟的中！競艇AI予想 結果｜{venue_str}..."

# 条件2: 3連単的中が多い（5本以上）
elif tri_hits >= 5:
    title = f"3連単{tri_hits}本的中！競艇AI予想..."

# 条件3: 1着的中率が50%超え
elif hit_1st_pct >= 50:
    title = f"的中率{hit_1st_pct}%！競艇AI予想..."

# デフォルト: 現行フォーマット
else:
    title = f"競艇AI予想 結果｜{venue_str}..."
```
