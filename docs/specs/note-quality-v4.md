# 設計: note記事品質 v4

## 変更ファイル
- `src/boatrace_ai/publish/article.py` — 主要変更
- `src/boatrace_ai/data/constants.py` — 決まり手テキスト確認
- `tests/test_article.py` — テスト追加

## D1: タイトル感情フック強化

### 現状
- accuracy記事: 万舟/3連単N本/的中率N%/デフォルト の4パターン（実装済み）
- grades記事: 的中率あり/なし の2パターン
- track_record/membership: 固定タイトル

### 変更
grades記事のタイトルにSランク数とフックを追加:

```python
# 現行 (line ~972)
title = f"競艇AI予想｜{venue_str}全{num_venues}場【全レース1着予測無料】{date_short}"

# v4: Sランク数を強調
s_count = len([g for g in grades if g.get("grade") == "S"])
if s_count >= 5:
    title = f"Sランク{s_count}レース！競艇AI予想｜{venue_str}全{num_venues}場【1着予測無料】{date_short}"
elif s_count >= 1:
    title = f"競艇AI予想｜{venue_str}全{num_venues}場 Sランク{s_count}レース【1着予測無料】{date_short}"
```

midday記事のタイトルにも午前成績を反映（既に実装済み — 確認のみ）。

track_record記事のタイトルに直近成績を追加:
```python
# 現行
title = "競艇AI実績｜直近30日の的中率・ROI推移【全データ公開】"

# v4: 直近成績を動的に
if stats.get("hit_1st_pct", 0) >= 50:
    title = f"的中率{stats['hit_1st_pct']}%！競艇AI実績｜直近30日の全データ公開"
elif stats.get("total_races", 0) > 0:
    title = f"競艇AI実績｜{stats['total_races']}レース分析の的中率・ROI推移【全データ公開】"
```

## B2: グレード別 視覚マーカー

### 現状
grades記事のグレードセクションヘッダー:
```
推奨度Sランク（高確信）— 5レース
```
各レースには `◎○△` の予測順位マーカーが既にある（predictions使用時）。

### 変更
セクションヘッダーにグレードマーカーを追加:

```python
# line ~1079
label = {
    "S": f"◎ 推奨度Sランク（高確信）— {len(rank_grades)}レース",
    "A": f"○ 推奨度Aランク（有力）— {len(rank_grades)}レース",
    "B": f"△ 推奨度Bランク（予測可能）— {len(rank_grades)}レース",
    "C": f"✕ 推奨度Cランク（見送り推奨）— {len(rank_grades)}レース",
}[rank]
```

accuracy結果記事のグレード別集計にもマーカー:
```python
# グレード別成績表示に ◎○△✕ を付与
grade_marker = {"S": "◎", "A": "○", "B": "△", "C": "✕"}.get(grade, "")
```

## D3: ハッシュタグ最適化

### 現状
```python
_HASHTAGS_BY_TYPE = {
    "prediction": ["競艇予想", "ボートレース予想", "AI予測", ...],
    "results": ["競艇結果", "ボートレース結果", "的中", ...],
    ...
}
```
場名は追加されるが、動的タグ（万舟、高配当等）は未対応。

### 変更
`_build_hashtags()` に動的タグ用のkwargsを追加:

```python
def _build_hashtags(
    race: RaceProgram | None = None,
    *,
    venue_names: list[str] | None = None,
    article_type: str | None = None,
    dynamic_tags: list[str] | None = None,  # NEW
) -> list[str]:
    ...
    # 動的タグを先頭付近に挿入（固定タグの後、場名の前）
    if dynamic_tags:
        tags.extend(dynamic_tags)
    ...
```

呼び出し側で条件付きタグを生成:
```python
# accuracy記事
dynamic = []
if max_payout >= 10000:
    dynamic.append("万舟")
if hit_tri >= 5:
    dynamic.append("3連単的中")
if roi_pct >= 100:
    dynamic.append("回収率100超")

# grades記事
dynamic = []
s_count = len([g for g in grades if g.get("grade") == "S"])
if s_count >= 5:
    dynamic.append("Sランク多数")
dynamic.append("無料予想")
```

## A2: レースドラマ描写

### 現状
`_build_hit_analysis()` (line 446) が的中理由を生成するが、
決まり手のテキスト表現のみで展開描写がない。

### 変更
`_build_hit_analysis()` を拡張し、決まり手ベースの展開描写テンプレートを追加:

```python
_RACE_DRAMA: dict[str, str] = {
    "逃げ": "{boat}号艇がスタートから主導権を握り、そのまま逃げ切り。",
    "差し": "{boat}号艇が内を巧みに突いて差し切る好レース。",
    "まくり": "{boat}号艇が豪快にまくり、外から一気に先頭へ。",
    "まくり差し": "{boat}号艇がまくり差しで鮮やかに抜け出す展開。",
    "抜き": "{boat}号艇が2周目以降に抜き去る逆転劇。",
    "恵まれ": "先行艇の転覆で{boat}号艇が恵まれて1着。波乱の結末。",
}
```

`_build_hit_analysis()` 内で結果の決まり手テキストを使用:
```python
if result and result.get("winning_technique"):
    tech_name = TECHNIQUES.get(result["winning_technique"], "")
    drama = _RACE_DRAMA.get(tech_name, "")
    if drama:
        sentences.append(drama.format(boat=result.get("first_place", "?")))
```

## C4: メンバーシップ実績数値

### 現状
`generate_membership_article()` のstatsは渡されるが、
具体的な「先月の3連単N本的中」のような訴求がない。

### 変更
メンバー特典セクションの後に実績セクションを追加:

```python
# 実績ベースの訴求
if stats.get("total_races", 0) > 0:
    parts.append("<h3>◆ 直近の実績</h3>")
    perf_items = []
    if stats.get("hit_trifecta_count", 0) > 0:
        perf_items.append(
            f"<li>直近30日の3連単的中 … <strong>{stats['hit_trifecta_count']}本</strong></li>"
        )
    if stats.get("hit_1st_pct", 0) > 0:
        perf_items.append(
            f"<li>1着的中率 … <strong>{stats['hit_1st_pct']}%</strong></li>"
        )
    if stats.get("total_races", 0) > 0:
        perf_items.append(
            f"<li>分析レース数 … <strong>{stats['total_races']:,}レース</strong></li>"
        )
    if perf_items:
        parts.append(f"<ul>{''.join(perf_items)}</ul>")
    parts.append(
        "<p>これらの全レース詳細予測をメンバーシップで毎日お届けします。</p>"
    )
```

## A4: 翌日プレビュー

### 現状
結果記事の末尾にCTA（「明日のSランク予測は朝7:30公開」）はあるが、
具体的な注目場/理由がない。

### 変更
accuracy記事の末尾CTAの前に翌日注目セクションを追加。
ただし翌日のプログラムデータは記事生成時点では未取得の場合が多い。

**シンプルアプローチ**: 当日の成績が良かった場をベースに「明日も注目」:
```python
def _build_tomorrow_preview(records: list[AccuracyRecord]) -> str:
    """Build tomorrow preview based on today's hot venues."""
    # 当日の場別成績を集計
    venue_stats = defaultdict(lambda: {"total": 0, "hit": 0})
    for r in records:
        venue = STADIUMS.get(r["stadium_number"], "")
        venue_stats[venue]["total"] += 1
        if r["hit_1st"]:
            venue_stats[venue]["hit"] += 1

    # 的中率上位3場を「明日も注目」として紹介
    sorted_venues = sorted(
        venue_stats.items(),
        key=lambda x: x[1]["hit"] / max(x[1]["total"], 1),
        reverse=True,
    )[:3]

    if not sorted_venues:
        return ""

    parts = ["<h3>◆ 明日の注目</h3>"]
    items = []
    for venue, st in sorted_venues:
        rate = round(st["hit"] / max(st["total"], 1) * 100)
        items.append(f"<li>{venue} … 本日{rate}%的中、好調継続に期待</li>")
    parts.append(f"<ul>{''.join(items)}</ul>")
    return "\n".join(parts)
```

## テスト計画

| テスト対象 | テスト内容 | 件数 |
|-----------|-----------|------|
| D1 タイトル | Sランク数別タイトル、track_record動的タイトル | 4 |
| B2 マーカー | グレードヘッダーに◎○△✕含む | 4 |
| D3 ハッシュタグ | 万舟時の動的タグ、場名タグ | 3 |
| A2 ドラマ | 決まり手別テンプレート展開 | 4 |
| C4 実績 | membership記事に3連単N本/的中率表示 | 2 |
| A4 プレビュー | 好調場が翌日注目に表示 | 2 |
| **合計** | | **19** |
