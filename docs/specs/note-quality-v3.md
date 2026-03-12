# 設計書: note記事品質 価値最大化 v3

## 変更対象ファイル
- `src/boatrace_ai/publish/article.py` — 主要変更（全施策）
- `src/boatrace_ai/storage/database.py` — 運用日数取得関数追加
- `tests/test_article.py` — テスト追加

## 施策別設計

---

### A1: 冒頭「今日の一言」— 感情フック

**対象関数**: `_build_accuracy_html()`, `generate_midday_report()`

新規関数 `_build_opening_hook()` を追加:

```python
def _build_opening_hook(
    hit_1st_pct: int, hit_tri: int, total: int,
    max_payout: int = 0, roi_pct: int = 0,
) -> str:
    """Generate emotional opening line based on today's results."""
```

ロジック:
- 3連単5本以上 + ROI>=100%: 「本日は攻守ともに好調。AIの精度が光る一日でした。」
- 3連単5本以上 + ROI<100%: 「3連単Nレース的中！回収率は課題が残りますが、的中力は健在です。」
- 万舟あり(max_payout>=10000): 「万舟的中！大穴を捉えたAIの分析力が際立ちます。」
- 1着的中率50%超: 「1着的中率N%と安定した一日。堅い予測が光りました。」
- 1着的中率40%未満: 「本日は苦戦。波乱含みの展開にAIも対応しきれませんでした。率直に振り返ります。」
- それ以外: 「本日の予測結果をまとめました。良かった点・課題の両面をレポートします。」

配置: `<h2>` 直後の `<p>` として挿入

---

### A3: 「今日の敗因」セクション

**対象関数**: `_build_accuracy_html()`

新規関数 `_build_loss_analysis()` を追加:

```python
def _build_loss_analysis(
    records: list[AccuracyRecord],
    results_data: list[dict] | None,
) -> str:
    """Analyze loss patterns when overall results are weak."""
```

表示条件: 1着的中率 < 45% のとき

分析項目:
1. 荒れた場の特定（1号艇1着率が全体平均より低い場）
2. 予測外し連続区間（ワースト場の的中率）
3. 結論（「明日は〇〇を改善ポイントとしてモデルが学習します」）

配置: 傾向分析セクションの直後

---

### B1: Unicode装飾セクション区切り

**変更箇所**: `_build_accuracy_html()`, grades記事, midday, track_record

現在: `<hr>` のみ
変更後: `<hr>` は残しつつ、主要セクション見出しに装飾を追加

```python
# h2見出しの装飾例
"<h2>━━ 3連単的中ハイライト ━━</h2>"
"<h2>━━ 本日の傾向分析 ━━</h2>"

# h3見出しの装飾例
"<h3>◆ 的中レース一覧（場別）</h3>"
"<h3>◆ 累計実績</h3>"
"<h3>◆ 明日の予測について</h3>"
```

---

### B3: 擬似テーブル化

**対象セクション**:
1. 累計実績 `_build_track_record()` — 現在1行のp → ul/li構造化
2. 日別実績（track_record記事） — p羅列 → ul/li + 視覚揃え
3. 関連記事 `_build_related_articles()` — プレーンURL → 装飾付きリンク

変更例（累計実績）:
```html
<!-- Before -->
<p><strong>総予測: 513レース | 1着的中率: 58% | 3連単的中率: 8%</strong></p>

<!-- After -->
<h3>◆ 累計実績</h3>
<ul>
  <li>総予測レース … <strong>513レース</strong></li>
  <li>1着的中率 …… <strong>58%</strong></li>
  <li>3連単的中率 … <strong>8%</strong></li>
  <li>連続運用 ……… <strong>31日目</strong></li>
</ul>
```

変更例（関連記事）:
```html
<!-- Before -->
<p>本日の全レース予測 → https://note.com/suiri_ai/n/xxx</p>

<!-- After -->
<ul>
  <li>◇ 本日の全レース予測 → https://note.com/suiri_ai/n/xxx</li>
  <li>◇ 過去30日の実績推移 → https://note.com/suiri_ai/n/yyy</li>
</ul>
```

---

### C1: 冒頭フォローCTA

**対象**: 全記事タイプの冒頭（h2直後）

```html
<p><strong>◎ フォローすると毎朝7:30にAI予測が届きます</strong></p>
```

grades記事のみ上部に配置（最も流入が多い記事のため）。
results/midday/track_record は末尾CTA（C2）のみ。

---

### C2: 末尾CTA「明日のSランク予測」

**対象**: results記事、midday記事の末尾

現在の「明日の予測について」セクションを強化:

```html
<h3>◆ 明日の予測について</h3>
<p><strong>明日も朝7:30に全場のAI予測を無料公開します。</strong></p>
<p>フォローしておくと、朝イチでSランクレースをチェックできます。
予測→結果→検証を<strong>365日毎日</strong>自動で回し続けるAI予想です。</p>
```

---

### E1: 「水理AIとは」信頼性数値化

**変更箇所**: `ABOUT_SUIRI_AI` 定数 → `_build_about_section()` 関数化

DB から動的に取得する値:
- 累計分析レース数（`stats["total_races"]`）
- 連続運用日数（新規: `get_operation_days()` from database.py）

```python
def get_operation_days() -> int:
    """Get number of days since first prediction."""
    # SELECT julianday('now') - julianday(MIN(race_date)) FROM predictions
```

出力例:
```html
<h3>◆ 水理AIとは</h3>
<p>ボートレース全場・全レースを毎朝自動分析するAI予測サービスです。
LightGBMと独自の特徴量エンジニアリングにより、選手・モーター・コース・展示データを
総合的にスコアリング。</p>
<ul>
  <li>累計分析 … <strong>15,000レース以上</strong></li>
  <li>連続運用 … <strong>31日目</strong>（毎日365日自動運用）</li>
  <li>全履歴公開 … <strong>勝ちも負けも改ざんなく公開</strong></li>
</ul>
<p>予測だけでなく「結果が正しかったか」まで毎日証明するAI予想です。</p>
```

---

## 関数変更一覧

| 関数 | 変更内容 |
|------|---------|
| `_build_opening_hook()` | **新規** — 感情フック生成 |
| `_build_loss_analysis()` | **新規** — 敗因分析 |
| `_build_about_section()` | **新規** — 動的な水理AI紹介 |
| `get_operation_days()` | **新規** (database.py) — 運用日数 |
| `_build_accuracy_html()` | A1挿入, A3挿入, B1装飾, C2末尾CTA |
| `_build_track_record()` | B3擬似テーブル化 |
| `_build_related_articles()` | B3装飾付きリンク |
| `_build_daily_trends()` | B1装飾 |
| `_build_trend_text()` | B1装飾 |
| `generate_grades_article()` | C1冒頭CTA, B1装飾, E1動的about |
| `generate_midday_report()` | B1装飾, C2末尾CTA, E1動的about |
| `generate_track_record_article()` | B1装飾, B3擬似テーブル, E1動的about |
| `generate_membership_article()` | B1装飾, E1動的about |
| `ABOUT_SUIRI_AI` | 定数→`_build_about_section(stats)`関数に移行 |
