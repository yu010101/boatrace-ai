"""りん（競艇データバンク｜AI予想の答え合わせ）の毎日の無料記事。朝=今日の1着予想、夜=前日の答え合わせ。

2026-10-21 本人「水理はもうりんにリブランディングしてるので、アイキャッチとか図解とか文字装飾とか変えて」。
型は 10/16 の見本（~/tasks/kyotei-db-20261015/drafts/note_brand/answer_example_visual.md）:
冒頭に数字 → 図 → 全件の内訳 → りんの一言 → 条件。当たりだけを抜き出さない、外れの原因を作らない、
太字は結論だけ、「水理AI」は使わない、りんは AI を名乗らない。
2026-10-21 本人「あおっていいよ」: タイトル・冒頭は煽ってよい（勝負レース・的中を前に）。約束（必ず・儲かる）と事実と違う数字は書かない。
タイトルに「AI」を入れない（note 競艇254記事で「AI」入りのスキ平均 6、無し 48。facts/note_buy_20261021）。
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from boatrace_ai.data.constants import STADIUMS

INTRO_URL = "https://note.com/rinboatrace/n/na643e88f5eb1"
GRADE_LABELS = {"S": "S", "A": "A", "B": "B", "C": "C"}
GRADE_RULES = (
    "推奨度は、本命が1着になる見込みの高さで分けています。"
    "S＝本命40%以上かつ上位2艇の合計55%以上、A＝本命30%以上かつ上位2艇45%以上、B＝本命20%以上、C＝それ以外。"
    "見込みは過去のレースから計算した値で、的中や払戻を約束するものではありません。"
)
PICKS_N = 3
CLOSING = "<p>りん「アタシの答え合わせは、ここまで！ 買うか買わないかは…アンタが決めてね。」</p><p>舟券は20歳以上、余裕資金の範囲で。購入はご自身で判断してください。</p>"


def _date_short(d: str) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}"


def _date_jp(d: str) -> str:
    return f"{int(d[0:4])}年{int(d[5:7])}月{int(d[8:10])}日"


def _venues(nums: list[int]) -> list[str]:
    return [STADIUMS.get(n, str(n)) for n in sorted(set(nums))]


def _figure(img: tuple[str, int, int] | None, caption: str) -> str:
    """note の本文の画像。img は (note の画像URL, 幅, 高さ)。無ければ何も出さない"""
    if not img:
        return ""
    url, width, height = img
    fid = uuid.uuid4().hex[:8]
    h = round(620 * height / width)
    return f'<figure name="{fid}" id="{fid}"><img src="{url}" alt="{caption}" width="620" height="{h}"><figcaption>{caption}</figcaption></figure>'


def _jst_hm(utc: str) -> str:
    """DB の created_at（UTC の "YYYY-MM-DD HH:MM:SS"）を日本時間の "HH:MM" にする"""
    from datetime import datetime, timedelta
    try:
        return (datetime.strptime(utc[:19], "%Y-%m-%d %H:%M:%S") + timedelta(hours=9)).strftime("%H:%M")
    except ValueError:
        return ""


def _deadline_note(excluded: dict | None, n: int) -> str:
    if excluded is None:
        return "予想を保存した時刻と締切の照合ができませんでした。締切後に保存した予想が混ざっている可能性があります"
    if not excluded.get("races") and not excluded.get("bets"):
        return f"数えたのは、締切より前に保存した予想{n}レースです（締切後に保存したものはありませんでした）"
    return f"数えたのは、締切より前に保存した予想{n}レースです。締切後に保存された予想{excluded.get('races', 0)}レースと仮想購入{excluded.get('bets', 0)}点は数えていません"


def _yen(n: int) -> str:
    return f"{n:,}円"


def _signed(n: int) -> str:
    return ("−" if n < 0 else "+") + _yen(abs(n))


def picks(grades: list[dict], predictions: dict[tuple[int, int], list[int]], close: dict | None = None, n: int = PICKS_N) -> list[dict]:
    """勝負レース: 推奨度Sのうち本命の見込みが高い順、1場1レースまで。朝と夜で同じ選び方をする（夜の記事で結果を確かめる）"""
    out, used = [], set()
    for g in sorted([g for g in grades if g["grade"] == "S"], key=lambda g: (-g["top1_prob"], g["stadium_number"], g["race_number"])):
        if g["stadium_number"] in used:
            continue
        k = (g["stadium_number"], g["race_number"])
        order = predictions.get(k) or []
        c = (close or {}).get(k)
        out.append({"st": g["stadium_number"], "venue": STADIUMS.get(g["stadium_number"], str(g["stadium_number"])), "race": g["race_number"],
                    "order": order[:3], "pct": round(g["top1_prob"] * 100), "close": c.strftime("%H:%M") if c else ""})
        used.add(g["stadium_number"])
        if len(out) >= n:
            break
    return out


def grade_hit_rows(grades: list[dict], records: list[dict]) -> list[tuple[str, int, int]]:
    """推奨度ごとに、本命（予想1着）が実際の1着だった数とレース数。予想と結果がそろったレースだけ"""
    grade_of = {(g["stadium_number"], g["race_number"]): g["grade"] for g in grades}
    hit: dict[str, int] = defaultdict(int)
    n: dict[str, int] = defaultdict(int)
    for r in records:
        g = grade_of.get((r["stadium_number"], r["race_number"]))
        if not g:
            continue
        n[g] += 1
        hit[g] += 1 if r["hit_1st"] else 0
    return [(f"推奨度{g}", hit[g], n[g]) for g in ("S", "A", "B", "C") if n[g]]


def results_cover_spec(race_date: str, records: list[dict], roi: dict) -> dict:
    """夜の記事の見出し画像に載せる文言（rin_visuals.cover_html に渡す）"""
    hit1 = sum(1 for r in records if r["hit_1st"])
    inv, pay = roi.get("total_invested", 0), roi.get("total_payout", 0)
    return {
        "tag": "りんの答え合わせ",
        "headline": [f"本命{hit1}/{len(records)}レース的中！", "でも、収支は？"],
        "amount_html": f"{inv:,}円 → <strong class=\"teal\">{pay:,}円</strong>" if inv else f"<strong class=\"teal\">{hit1}/{len(records)}</strong>",
        "sub": [f"{_date_jp(race_date)}の全{len(records)}レース", f"仮想購入{roi.get('total_bets', 0)}点の合計" if inv else "仮想購入なし"],
        "foot": f"{race_date.replace('-', '.')} ／ 実際に買った舟券ではありません",
    }


def grades_cover_spec(race_date: str, grades: list[dict], top: list[dict], yesterday_line: str = "") -> dict:
    """朝の記事の見出し画像に載せる文言。top は picks() の結果"""
    first = top[0] if top else None
    return {
        "tag": f"{_date_short(race_date)} りんの勝負レース",
        "headline": ["今日の勝負レースは", "この3つ！" if len(top) >= 3 else f"この{len(top)}つ！"],
        "amount_html": f"{first['venue']}{first['race']}R 本命{(first['order'] or ['?'])[0]}号艇 <strong class=\"teal\">{first['pct']}%</strong>" if first else "",
        "sub": [yesterday_line or f"全{len(grades)}レースの本命つき", "夜に、当たりも外れも答え合わせ"],
        "foot": f"{race_date.replace('-', '.')} ／ %は1着になる見込み。舟券は20歳以上で",
    }


def generate_rin_results_article(
    race_date: str,
    records: list[dict],
    roi: dict,
    grades: list[dict],
    images: dict[str, tuple[str, int, int]] | None = None,
    excluded: dict | None = None,
    morning_picks: list[dict] | None = None,
) -> tuple[str, str, list[str]]:
    """夜（前日分）の答え合わせ記事。morning_picks は朝の記事と同じ picks()。records・roi は締切前に保存したものだけを渡す。excluded={"races","bets"}（照合できなかったら None）。images: cover/money/grades の note 画像URL（無ければ図なしで出す）"""
    images = images or {}
    n = len(records)
    hit1 = sum(1 for r in records if r["hit_1st"])
    tri = sorted([r for r in records if r["hit_trifecta"]], key=lambda r: (r["stadium_number"], r["race_number"]))
    inv, pay, bets = roi.get("total_invested", 0), roi.get("total_payout", 0), roi.get("total_bets", 0)
    net = pay - inv
    venues = _venues([r["stadium_number"] for r in records])

    title = f"{_date_short(race_date)}の答え合わせ｜本命{hit1}/{n}的中・3連単{len(tri)}本ズバリ【競艇予想】" if tri else f"{_date_short(race_date)}の答え合わせ｜本命{hit1}/{n}的中【競艇予想】"

    p: list[str] = []
    p.append(f"<p>{_date_jp(race_date)}、{'・'.join(venues[:3])}{'など' if len(venues) > 3 else ''}全{len(venues)}場{n}レースの答え合わせです。朝に出した1着予想と、実際の結果を並べます。</p>")
    lead = f"本命が1着だったのは{n}レース中{hit1}レース（{round(hit1 / n * 100) if n else 0}%）。"
    if inv:
        lead += f"仮想購入は{bets}点で{_yen(inv)}、払戻は{_yen(pay)}、差引{_signed(net)}でした。"
    p.append(f"<p><strong>{lead}</strong></p>")
    if inv and net >= 0:
        p.append("<p>りん「やったー！ …でもね、たまたまの日もあるから、明日も見ててね。」</p>")
    elif inv:
        p.append("<p>りん「うぅ…払戻は購入額より少なかったよ。全部出すって決めてるから、ちゃんと見せるね。」</p>")

    if morning_picks:
        rec_of = {(r["stadium_number"], r["race_number"]): r for r in records}
        p.append("<h2>朝の勝負レース3選、結果は？</h2>")
        rows = []
        for pk in morning_picks:
            r = rec_of.get((pk["st"], pk["race"]))
            res = "数えていません（締切後の保存・結果なし）" if not r else (f"<strong>的中！</strong> 結果 {r['actual_trifecta']}" if r["hit_1st"] else f"外れ… 結果 {r['actual_trifecta']}")
            rows.append(f"<li>{pk['venue']} {pk['race']}R　本命{(pk['order'] or ['?'])[0]}号艇（見込み{pk['pct']}%）→ {res}</li>")
        p.append("<ul>" + "".join(rows) + "</ul>")
    p.append(_figure(images.get("ledger"), "今月の答え合わせ帳（本命の的中率）"))

    if inv:
        p.append("<h2>この日のお金</h2>")
        p.append(_figure(images.get("money"), f"仮想購入{_yen(inv)}、仮想払戻{_yen(pay)}、差引{_signed(net)}"))
        p.append(f"<p>当たった買い目も外れた買い目も、全{bets}点を足した数字です。的中は{roi.get('hit_count', 0)}点でした。</p>")

    p.append("<h2>推奨度ごとの答え合わせ</h2>")
    rows = grade_hit_rows(grades, records)
    p.append(_figure(images.get("grades"), "推奨度ごとの、本命が1着だった数とレース数"))
    if rows:
        p.append("<ul>" + "".join(f"<li>{label}: {h}/{c}レース（{round(h / c * 100)}%）</li>" for label, h, c in rows) + "</ul>")
    p.append("<p>推奨度が高いほど本命が1着になりやすいかは、1日分では決められません。日を重ねて見ていきます。</p>")

    p.append(f"<h2>3連単が予想どおりだったレース（{len(tri)}本）</h2>")
    if tri:
        p.append("<ul>" + "".join(
            f"<li>{STADIUMS.get(r['stadium_number'], r['stadium_number'])} {r['race_number']}R　{r['actual_trifecta']}　払戻 {_yen(int(r.get('trifecta_payout') or 0))}（100円あたり）</li>" for r in tri
        ) + "</ul>")
        p.append("<p>選んだレースではなく、一致したものを全部載せています。</p>")
    else:
        p.append("<p>この日は、3連単の予想が結果と一致したレースはありませんでした。</p>")

    miss = defaultdict(int)
    for r in records:
        if not r["hit_1st"]:
            miss[STADIUMS.get(r["stadium_number"], r["stadium_number"])] += 1
    p.append(f"<h2>本命が1着にならなかったレース（{n - hit1}レース）</h2>")
    p.append("<p>" + "、".join(f"{k} {v}" for k, v in miss.items()) + "</p>")
    p.append("<p>外れた理由は、この記録だけでは分かりません。展開や風のせいだったと、後から話を作ることはしません。</p>")

    p.append("<h2>この記事の数字について</h2>")
    p.append(
        "<ul><li>仮想購入は、決まった条件で買ったことにして計算したもので、実際に買った舟券ではありません</li>"
        + f"<li>{_deadline_note(excluded, len(records))}</li>"
        + f"<li>{GRADE_RULES}</li></ul>"
    )
    p.append(CLOSING)
    p.append(f'<p>このnoteについて：<a href="{INTRO_URL}">りんと、当たりも外れも答え合わせ。競艇データバンクを始めます</a></p>')
    hashtags = ["競艇", "ボートレース", "競艇予想", "ボートレース予想", "答え合わせ", "競艇データバンク", *venues[:3]]
    return title, "\n".join(x for x in p if x), hashtags


def yesterday_line(yesterday: dict | None) -> str:
    """「昨日は本命83/144的中」。結果がそろっていなければ空"""
    if not yesterday or not yesterday.get("records"):
        return ""
    recs = yesterday["records"]
    return f"昨日は本命{sum(1 for r in recs if r['hit_1st'])}/{len(recs)}的中"


def generate_rin_grades_article(
    race_date: str,
    grades: list[dict],
    predictions: dict[tuple[int, int], list[int]],
    yesterday: dict | None = None,
    images: dict[str, tuple[str, int, int]] | None = None,
    excluded: dict | None = None,
    top: list[dict] | None = None,
) -> tuple[str, str, list[str]]:
    """朝（当日分）の予想記事。top は picks()（締切時刻つき）。yesterday: {"date", "records", "roi"}"""
    images = images or {}
    top = top if top is not None else picks(grades, predictions)
    venues = _venues([g["stadium_number"] for g in grades])
    counts = {k: sum(1 for g in grades if g["grade"] == k) for k in ("S", "A", "B", "C")}
    made = sorted(g.get("created_at") or "" for g in grades)
    yl = yesterday_line(yesterday)
    head = "・".join(f"{t['venue']}{t['race']}R" for t in top[:2])
    title = f"{_date_short(race_date)}【勝負レース{len(top)}選】{head}" + (f"｜{yl}" if yl else f"｜全{len(grades)}レースの本命つき") + "【競艇予想】"

    p: list[str] = []
    if top:
        names = "・".join(f"{t['venue']}{t['race']}R" for t in top)
        p.append(f"<p><strong>今日の勝負レースは{names}！</strong>全{len(venues)}場{len(grades)}レースの中から、本命が1着になる見込みがいちばん高いレースを選びました。</p>")
    p.append("<p>りん「今日の勝負レースはこの3つ！ 夜に、当たりも外れも答え合わせするからね。」</p>" if len(top) >= 3 else "<p>りん「今日の勝負レースはこれ！ 夜に、当たりも外れも答え合わせするからね。」</p>")

    if top:
        p.append(f"<h2>今日の勝負レース{len(top)}選</h2>")
        p.append(_figure(images.get("picks"), "今日の勝負レース（本命・対抗・3着候補と、本命が1着になる見込み）"))
        items = []
        for t in top:
            o = t["order"]
            marks = " ".join(f"{m}{b}" for m, b in zip(["◎", "○", "△"], o))
            items.append(f"<li><strong>{t['venue']} {t['race']}R</strong>{'（締切 ' + t['close'] + '）' if t['close'] else ''}　{marks}　本命が1着になる見込み <strong>{t['pct']}%</strong></li>")
        p.append("<ul>" + "".join(items) + "</ul>")
        p.append("<p>見込みが高くても外れることはあります。今夜の答え合わせで、この3レースの結果も出します。</p>")

    if yesterday and yesterday.get("records"):
        recs, roi = yesterday["records"], yesterday.get("roi") or {}
        n, h = len(recs), sum(1 for r in recs if r["hit_1st"])
        p.append(f"<h2>昨日（{_date_short(yesterday['date'])}）の答え合わせ</h2>")
        line = f"朝の時点で結果がそろった{n}レースのうち、本命が1着だったのは{h}レース（{round(h / n * 100) if n else 0}%）。"
        if roi.get("total_invested"):
            line += f"仮想購入{_yen(roi['total_invested'])}に対して払戻{_yen(roi['total_payout'])}、差引{_signed(roi['total_payout'] - roi['total_invested'])}。"
        p.append(f"<p><strong>{line}</strong></p>")
        p.append(_figure(images.get("ledger"), "今月の答え合わせ帳（本命の的中率）"))
        p.append("<p>全レースがそろった内訳は、今夜の答え合わせの記事に載せます。</p>")

    p.append("<h2>全レースの本命</h2>")
    p.append("<p>場ごとに、レース番号・推奨度・◎本命 ○対抗 △3着候補・本命が1着になる見込みの順です。推奨度Sは"
             f"{counts['S']}レース、Aは{counts['A']}レース。</p>")
    by_venue: dict[int, list[dict]] = defaultdict(list)
    for g in grades:
        by_venue[g["stadium_number"]].append(g)
    for num in sorted(by_venue):
        p.append(f"<h3>{STADIUMS.get(num, num)}</h3>")
        items = []
        for g in sorted(by_venue[num], key=lambda g: g["race_number"]):
            order = predictions.get((num, g["race_number"])) or []
            marks = " ".join(f"{m}{b}" for m, b in zip(["◎", "○", "△"], order[:3]))
            items.append(f"<li>{g['race_number']}R［{g['grade']}］{marks}　{round(g['top1_prob'] * 100)}%</li>")
        p.append("<ul>" + "".join(items) + "</ul>")

    p.append("<h2>この記事の数字について</h2>")
    p.append(
        "<ul>"
        + f"<li>{GRADE_RULES}</li>"
        + (f"<li>予想を保存した時刻: {_jst_hm(made[0])}〜{_jst_hm(made[-1])}（日本時間）</li>" if made and _jst_hm(made[0]) else "")
        + (f"<li>保存した時点で締切を過ぎていた{excluded['races']}レースは、一覧にも夜の答え合わせにも入れていません</li>" if excluded and excluded.get("races") else "")
        + ("<li>締切との照合ができなかったため、締切後に保存した予想が混ざっている可能性があります</li>" if excluded is None else "")
        + "<li>仮想購入は、決まった条件で買ったことにして計算したもので、実際に買った舟券ではありません</li></ul>"
    )
    p.append(CLOSING)
    p.append(f'<p>このnoteについて：<a href="{INTRO_URL}">りんと、当たりも外れも答え合わせ。競艇データバンクを始めます</a></p>')
    hashtags = ["競艇", "ボートレース", "競艇予想", "ボートレース予想", "勝負レース", "競艇データバンク", *venues[:3]]
    return title, "\n".join(x for x in p if x), hashtags


# ── 2026-10-28 本人「旧型を全部新型で作り直す」: 旧 article.py の5種類（Sランク個別・午前の結果速報・高配当速報・実績・週間）をりんの型にする ──
# 型は朝夜の記事と同じ（冒頭に数字 → 図 → 全件の内訳 → りんの一言 → 条件）。題名に「AI」を入れない・「水理AI」を使わない・
# 予想の文章（LLM の analysis）は載せない（外れの原因や根拠の話を作らないため）。当たりだけを抜き出さない（高配当速報もその日の全体と並べる）。

RACER_CLASS = {1: "A1", 2: "A2", 3: "B1", 4: "B2"}


def race_cover_spec(race_date: str, venue: str, race_no: int, order: list[int], pct: int) -> dict:
    return {
        "tag": f"{_date_short(race_date)} りんの勝負レース",
        "headline": [f"{venue} {race_no}R", "本命はこの艇！"],
        "amount_html": f"本命{order[0] if order else '?'}号艇 <strong class=\"teal\">{pct}%</strong>",
        "sub": ["全6艇のデータつき", "夜に、当たりも外れも答え合わせ"],
        "foot": f"{race_date.replace('-', '.')} ／ %は1着になる見込み。舟券は20歳以上で",
    }


def generate_rin_race_article(race, prediction, grade: dict, close: str = "", free: bool = True) -> tuple[str, str, list[str]]:
    """推奨度Sの1レースの記事（旧【Sランク】個別予想）。pct は朝の記事と同じ「本命が1着になる見込み」（grades.top1_prob）"""
    venue = STADIUMS.get(race.race_stadium_number, str(race.race_stadium_number))
    order = list(prediction.predicted_order)
    pct = round(grade["top1_prob"] * 100)
    boat_of = {b.racer_boat_number: b for b in race.boats}
    name = lambda n: boat_of[n].racer_name if n in boat_of else "?"  # noqa: E731
    title = f"{_date_short(race.race_date)} {venue}{race.race_number}R【勝負レース】本命{order[0]}号艇・見込み{pct}%｜全6艇のデータつき【競艇予想】"

    p: list[str] = []
    p.append(f"<p><strong>{venue} {race.race_number}Rの本命は{order[0]}号艇（{name(order[0])}）。1着になる見込みは{pct}%です。</strong>"
             f"推奨度Sのレースから、見込みの高い順に選んだ1つです。</p>")
    p.append("<p>りん「このレース、アタシは本命を信じてる！ でも外れることもあるから、夜の答え合わせも見てね。」</p>")
    p.append("<h2>りんの予想</h2>")
    marks = " ".join(f"{m}{b}" for m, b in zip(["◎", "○", "△"], order[:3]))
    p.append("<ul>"
             f"<li><strong>{venue} {race.race_number}R</strong>{'（締切 ' + close + '）' if close else ''}　{marks}</li>"
             + "".join(f"<li>{m}{b}号艇　{name(b)}</li>" for m, b in zip(["◎ 本命 ", "○ 対抗 ", "△ 3着候補 "], order[:3]))
             + f"<li>本命が1着になる見込み <strong>{pct}%</strong></li></ul>")
    if prediction.recommended_bets:
        p.append("<h2>買い目の候補</h2>")
        p.append("<ul>" + "".join(f"<li>{b}</li>" for b in prediction.recommended_bets) + "</ul>")
        p.append("<p>候補は予想の並びから作ったもので、的中や払戻を約束するものではありません。</p>")
    if not free:
        p.append("<p>ここから先は、全6艇のデータと6着までの予想です。</p><pay>")
    p.append("<h2>全6艇のデータ</h2>")
    p.append("<p>号艇・選手・級別、全国勝率・当地勝率・平均スタート・モーター2連率・ボート2連率の順です。</p>")
    rows = []
    for b in sorted(race.boats, key=lambda b: b.racer_boat_number):
        st = f"{b.racer_average_start_timing:.2f}" if b.racer_average_start_timing is not None else "—"
        rows.append(f"<li><strong>{b.racer_boat_number}号艇 {b.racer_name}</strong>（{RACER_CLASS.get(b.racer_class_number, '?')}）　"
                    f"全国{b.racer_national_top_1_percent:.2f}・当地{b.racer_local_top_1_percent:.2f}・ST{st}・"
                    f"モーター{b.racer_assigned_motor_top_2_percent:.1f}%・ボート{b.racer_assigned_boat_top_2_percent:.1f}%</li>")
    p.append("<ul>" + "".join(rows) + "</ul>")
    p.append("<h2>6着までの予想</h2>")
    p.append(f"<p>{' → '.join(str(n) for n in order)}</p>")
    p.append("<h2>この記事の数字について</h2>")
    p.append(f"<ul><li>{GRADE_RULES}</li><li>選手とモーターの数字は、番組表（出走表）に載っている値です</li></ul>")
    p.append(CLOSING)
    p.append(f'<p>このnoteについて：<a href="{INTRO_URL}">りんと、当たりも外れも答え合わせ。競艇データバンクを始めます</a></p>')
    hashtags = ["競艇", "ボートレース", "競艇予想", "ボートレース予想", "勝負レース", "競艇データバンク", venue]
    return title, "\n".join(x for x in p if x), hashtags


def midday_cover_spec(race_date: str, records: list[dict]) -> dict:
    h = sum(1 for r in records if r["hit_1st"])
    return {
        "tag": f"{_date_short(race_date)} りんの途中経過",
        "headline": ["午前の答え合わせ！", f"本命{h}/{len(records)}レース的中"],
        "amount_html": f"<strong class=\"teal\">{round(h / len(records) * 100) if records else 0}%</strong>",
        "sub": [f"結果が出た{len(records)}レース", "夜に、全レースで答え合わせ"],
        "foot": f"{race_date.replace('-', '.')} ／ 締切前に保存した予想だけ",
    }


def generate_rin_midday_article(race_date: str, records: list[dict], grades: list[dict],
                                images: dict | None = None, excluded: dict | None = None,
                                morning_picks: list[dict] | None = None) -> tuple[str, str, list[str]]:
    """昼の途中経過（旧「午前の結果速報」）。records は結果が出たレースのうち締切前に保存した予想だけ"""
    images = images or {}
    n, h = len(records), sum(1 for r in records if r["hit_1st"])
    tri = sorted([r for r in records if r["hit_trifecta"]], key=lambda r: (r["stadium_number"], r["race_number"]))
    venues = _venues([r["stadium_number"] for r in records])
    title = f"{_date_short(race_date)}午前の答え合わせ｜本命{h}/{n}的中" + (f"・3連単{len(tri)}本ズバリ" if tri else "") + "【競艇予想】"

    p: list[str] = []
    p.append(f"<p><strong>結果が出た{n}レースのうち、本命が1着だったのは{h}レース（{round(h / n * 100) if n else 0}%）。</strong>"
             f"{'・'.join(venues[:3])}{'など' if len(venues) > 3 else ''}、ここまでの途中経過です。</p>")
    p.append("<p>りん「午前はここまで！ 残りのレースも、夜の答え合わせで全部出すね。」</p>")
    if morning_picks:
        rec_of = {(r["stadium_number"], r["race_number"]): r for r in records}
        p.append("<h2>朝の勝負レース、ここまでの結果</h2>")
        rows = []
        for pk in morning_picks:
            r = rec_of.get((pk["st"], pk["race"]))
            res = "まだ結果が出ていません" if not r else (f"<strong>的中！</strong> 結果 {r['actual_trifecta']}" if r["hit_1st"] else f"外れ… 結果 {r['actual_trifecta']}")
            rows.append(f"<li>{pk['venue']} {pk['race']}R　本命{(pk['order'] or ['?'])[0]}号艇（見込み{pk['pct']}%）→ {res}</li>")
        p.append("<ul>" + "".join(rows) + "</ul>")
    p.append("<h2>推奨度ごとの途中経過</h2>")
    p.append(_figure(images.get("grades"), "推奨度ごとの、本命が1着だった数とレース数（ここまで）"))
    gr = grade_hit_rows(grades, records)
    if gr:
        p.append("<ul>" + "".join(f"<li>{label}: {hh}/{c}レース（{round(hh / c * 100)}%）</li>" for label, hh, c in gr) + "</ul>")
    p.append(f"<h2>3連単が予想どおりだったレース（{len(tri)}本）</h2>")
    if tri:
        p.append("<ul>" + "".join(f"<li>{STADIUMS.get(r['stadium_number'], r['stadium_number'])} {r['race_number']}R　{r['actual_trifecta']}　払戻 {_yen(int(r.get('trifecta_payout') or 0))}（100円あたり）</li>" for r in tri) + "</ul>")
    else:
        p.append("<p>ここまで、3連単の予想が結果と一致したレースはありません。</p>")
    miss = defaultdict(int)
    for r in records:
        if not r["hit_1st"]:
            miss[STADIUMS.get(r["stadium_number"], r["stadium_number"])] += 1
    if miss:
        p.append(f"<h2>本命が1着にならなかったレース（{n - h}レース）</h2>")
        p.append("<p>" + "、".join(f"{k} {v}" for k, v in miss.items()) + "</p>")
    p.append("<h2>この記事の数字について</h2>")
    p.append(f"<ul><li>{_deadline_note(excluded, n)}</li><li>この記事を作った時点で結果が出ていたレースだけです。1日の数字は夜の答え合わせで出します</li><li>{GRADE_RULES}</li></ul>")
    p.append(CLOSING)
    p.append(f'<p>このnoteについて：<a href="{INTRO_URL}">りんと、当たりも外れも答え合わせ。競艇データバンクを始めます</a></p>')
    return title, "\n".join(x for x in p if x), ["競艇", "ボートレース", "競艇予想", "答え合わせ", "競艇データバンク", *venues[:3]]


def hit_cover_spec(race_date: str, best: dict, records: list[dict]) -> dict:
    venue = STADIUMS.get(best["stadium_number"], str(best["stadium_number"]))
    return {
        "tag": f"{_date_short(race_date)} りんの答え合わせ",
        "headline": [f"{venue} {best['race_number']}R", "3連単が予想どおり！"],
        "amount_html": f"払戻 <strong class=\"teal\">{int(best['trifecta_payout']):,}円</strong>",
        "sub": [f"この日の3連単一致は{sum(1 for r in records if r['hit_trifecta'])}本", f"本命は{len(records)}レース中{sum(1 for r in records if r['hit_1st'])}的中"],
        "foot": f"{race_date.replace('-', '.')} ／ 100円あたりの払戻。実際に買った舟券ではありません",
    }


def generate_rin_hit_article(race_date: str, best: dict, records: list[dict], images: dict | None = None,
                             excluded: dict | None = None) -> tuple[str, str, list[str]]:
    """高配当の速報（旧 hit-flash）。当たりだけを抜き出さないよう、その日の全体の数字と一致した3連単の全部を並べる"""
    images = images or {}
    venue = STADIUMS.get(best["stadium_number"], str(best["stadium_number"]))
    n, h = len(records), sum(1 for r in records if r["hit_1st"])
    tri = sorted([r for r in records if r["hit_trifecta"]], key=lambda r: -int(r.get("trifecta_payout") or 0))
    pay = int(best["trifecta_payout"])
    title = f"{_date_short(race_date)} {venue}{best['race_number']}R 3連単{pay:,}円が予想どおり｜その日の答え合わせつき【競艇予想】"
    p: list[str] = []
    p.append(f"<p><strong>{_date_jp(race_date)}の{venue} {best['race_number']}R、3連単{best['actual_trifecta']}が予想どおりで、払戻は100円あたり{_yen(pay)}でした。</strong>"
             f"この日いちばん払戻が大きかった一致です。</p>")
    p.append("<p>りん「やったー！ …でもね、この日ぜんぶが当たったわけじゃないよ。全体も見てね。」</p>")
    p.append("<h2>この日の全体</h2>")
    p.append(f"<p><strong>本命が1着だったのは{n}レース中{h}レース（{round(h / n * 100) if n else 0}%）。3連単の予想が結果と一致したのは{len(tri)}本です。</strong></p>")
    p.append(_figure(images.get("ledger"), "今月の答え合わせ帳（本命の的中率）"))
    p.append(f"<h2>3連単が予想どおりだったレース（{len(tri)}本・払戻の大きい順）</h2>")
    p.append("<ul>" + "".join(f"<li>{STADIUMS.get(r['stadium_number'], r['stadium_number'])} {r['race_number']}R　{r['actual_trifecta']}　払戻 {_yen(int(r.get('trifecta_payout') or 0))}</li>" for r in tri) + "</ul>")
    p.append("<p>一致したものを全部載せています。払戻の大きい一致がこの先も続くかは、1日分では分かりません。</p>")
    p.append("<h2>この記事の数字について</h2>")
    p.append(f"<ul><li>払戻は100円あたりの公式の金額で、実際に買った舟券ではありません</li><li>{_deadline_note(excluded, n)}</li></ul>")
    p.append(CLOSING)
    p.append(f'<p>このnoteについて：<a href="{INTRO_URL}">りんと、当たりも外れも答え合わせ。競艇データバンクを始めます</a></p>')
    return title, "\n".join(x for x in p if x), ["競艇", "ボートレース", "競艇予想", "答え合わせ", "競艇データバンク", venue]


def span_cover_spec(days: list[dict], label: str) -> dict:
    n, h = sum(d["n"] for d in days), sum(d["hit"] for d in days)
    return {
        "tag": f"りんの答え合わせ帳 {label}",
        "headline": [label, f"本命{h:,}/{n:,}的中"],
        "amount_html": f"<strong class=\"teal\">{round(h / n * 100) if n else 0}%</strong>",
        "sub": ["当たりも外れも、仮想購入の収支も全部", "締切前に保存した予想だけ"],
        "foot": f"{days[0]['date'].replace('-', '.')}〜{days[-1]['date'].replace('-', '.')} ／ 実際に買った舟券ではありません" if days else "",
    }


def generate_rin_span_article(days: list[dict], label: str, images: dict | None = None, paid: bool = False) -> tuple[str, str, list[str]]:
    """期間のまとめ（旧 実績レポート・週間レポート）。days は古い順の {date, hit, n, tri, inv, pay, dropped_races, dropped_bets}（締切前に保存したものだけ）"""
    images = images or {}
    n, h = sum(d["n"] for d in days), sum(d["hit"] for d in days)
    tri = sum(d["tri"] for d in days)
    inv, pay = sum(d["inv"] for d in days), sum(d["pay"] for d in days)
    title = f"{label}の答え合わせ｜本命{h:,}/{n:,}的中（{round(h / n * 100) if n else 0}%）・3連単{tri}本【競艇予想】"
    p: list[str] = []
    p.append(f"<p><strong>{label}（{_date_short(days[0]['date'])}〜{_date_short(days[-1]['date'])}・{len(days)}日）で、本命が1着だったのは{n:,}レース中{h:,}レース（{round(h / n * 100) if n else 0}%）。"
             f"3連単の予想が結果と一致したのは{tri}本でした。</strong></p>")
    if inv:
        p.append(f"<p><strong>仮想購入は{_yen(inv)}、払戻は{_yen(pay)}、差引{_signed(pay - inv)}。</strong></p>")
    p.append("<p>りん「いい日も悪い日も、ぜんぶ並べるね。1日だけ見て決めないでね。」</p>" if not inv or pay >= inv
             else "<p>りん「うぅ…この期間は払戻が購入額より少なかったよ。隠さず全部見せるね。」</p>")
    p.append("<h2>日ごとの本命の的中率</h2>")
    p.append(_figure(images.get("ledger"), f"{label}の答え合わせ帳（本命の的中率）"))
    if paid:
        p.append("<p>ここから先は、日ごとの内訳です。</p><pay>")
    p.append("<h2>日ごとの内訳</h2>")
    p.append("<ul>" + "".join(
        f"<li>{_date_short(d['date'])}　本命{d['hit']}/{d['n']}（{round(d['hit'] / d['n'] * 100) if d['n'] else 0}%）・3連単{d['tri']}本"
        + (f"・仮想購入{_yen(d['inv'])}→払戻{_yen(d['pay'])}（{_signed(d['pay'] - d['inv'])}）" if d["inv"] else "") + "</li>" for d in days) + "</ul>")
    dr, db = sum(d.get("dropped_races", 0) for d in days), sum(d.get("dropped_bets", 0) for d in days)
    p.append("<h2>この記事の数字について</h2>")
    p.append("<ul><li>数えたのは、締切より前に保存した予想と仮想購入だけです"
             + (f"（締切後に保存された予想{dr}レースと仮想購入{db}点は数えていません）" if dr or db else "") + "</li>"
             + "<li>締切との照合ができなかった日は、この記事に入れていません</li>"
             + "<li>仮想購入は、決まった条件で買ったことにして計算したもので、実際に買った舟券ではありません</li>"
             + f"<li>{GRADE_RULES}</li></ul>")
    p.append(CLOSING)
    p.append(f'<p>このnoteについて：<a href="{INTRO_URL}">りんと、当たりも外れも答え合わせ。競艇データバンクを始めます</a></p>')
    return title, "\n".join(x for x in p if x), ["競艇", "ボートレース", "競艇予想", "答え合わせ", "競艇データバンク"]


# ── 2026-10-29 本人「事実の判断材料の記事を足す」: 場ごとの1号艇の勝ちやすさ（週1回・予想の上乗せが示せるまでの間の中身）──
# 予想の上乗せは示せていない（同じ3,039レースで本命1着 53.5%・毎回1号艇 52.6%）。だから「勝てる」とは書かず、公式の結果を数えた事実だけを出す。

def venue_rows(results: list[dict]) -> list[dict]:
    """results は {stadium_number, first(1着の艇), trifecta_payout}。中止・結果なしは渡さない。場ごとの1号艇の1着率と3連単の払戻の中央値"""
    by: dict[int, list[dict]] = defaultdict(list)
    for r in results:
        by[r["stadium_number"]].append(r)
    out = []
    for st, rs in by.items():
        pays = sorted(int(r["trifecta_payout"]) for r in rs if r.get("trifecta_payout"))
        mid = pays[len(pays) // 2] if pays else 0
        out.append({"st": st, "venue": STADIUMS.get(st, str(st)), "n": len(rs), "boat1": sum(1 for r in rs if r["first"] == 1), "median_tri": mid})
    return sorted(out, key=lambda v: (-v["boat1"] / v["n"], v["st"]))


def venue_cover_spec(rows: list[dict], label: str) -> dict:
    n, w = sum(v["n"] for v in rows), sum(v["boat1"] for v in rows)
    hi, lo = rows[0], rows[-1]
    return {
        "tag": f"りんのデータ帳 {label}",
        "headline": ["1号艇がいちばん勝つ場、", "いちばん負ける場"],
        "amount_html": f"{hi['venue']} <strong class=\"teal\">{round(hi['boat1'] / hi['n'] * 100)}%</strong> ／ {lo['venue']} {round(lo['boat1'] / lo['n'] * 100)}%",
        "sub": [f"全{len(rows)}場{n:,}レースの平均は{round(w / n * 100)}%", "公式の結果を全部数えました"],
        "foot": f"{label} ／ 中止・結果なしのレースは数えていません",
    }


def generate_rin_venue_article(rows: list[dict], label: str, images: dict | None = None) -> tuple[str, str, list[str]]:
    """場ごとの1号艇の1着率と荒れやすさ。rows は venue_rows() の戻り値（1着率の高い順）"""
    images = images or {}
    n, w = sum(v["n"] for v in rows), sum(v["boat1"] for v in rows)
    avg = round(w / n * 100) if n else 0
    hi, lo = rows[0], rows[-1]
    pct = lambda v: round(v["boat1"] / v["n"] * 100)  # noqa: E731
    title = f"1号艇がいちばん勝つ場は{hi['venue']}（{pct(hi)}%）、負ける場は{lo['venue']}（{pct(lo)}%）｜{label}の全{n:,}レース【競艇予想】"
    p: list[str] = []
    p.append(f"<p><strong>{label}の全{len(rows)}場{n:,}レースで、1号艇が1着になったのは{w:,}レース（{avg}%）。"
             f"いちばん高いのは{hi['venue']}の{pct(hi)}%、いちばん低いのは{lo['venue']}の{pct(lo)}%でした。</strong></p>")
    p.append(f"<p>りん「同じ1号艇でも、場によってこんなに違うんだよ。{lo['venue']}で1号艇を本命にするときは、ちょっと考えてね。」</p>")
    p.append("<h2>場ごとの1号艇の1着率</h2>")
    p.append(_figure(images.get("venues"), "場ごとの、1号艇が1着になった数とレース数"))
    p.append("<p>1着率の高い順です。（　）の中は3連単の払戻の中央値（100円あたり）で、高い場ほど荒れやすいと読めます。</p>")
    p.append("<ul>" + "".join(f"<li><strong>{v['venue']}</strong>　1号艇 {v['boat1']}/{v['n']}レース（{pct(v)}%）　3連単の中央値 {_yen(v['median_tri'])}</li>" for v in rows) + "</ul>")
    p.append("<h2>この数字の使い方</h2>")
    p.append(f"<p>全場の平均{avg}%より低い場では、1号艇を本命にした舟券が外れやすかった、ということです。"
             "朝の勝負レースで本命が1号艇でも、その場の1着率と並べて見てください。</p>")
    p.append("<p>これは過去の結果を数えたもので、これからのレースの結果を約束するものではありません。風・水面・選手の組み合わせで、1日の中でも変わります。</p>")
    p.append("<h2>この記事の数字について</h2>")
    p.append(f"<ul><li>数えたのは{label}に結果が出たレースです。中止・順延・結果が出ていないレースは入れていません</li>"
             "<li>1着と3連単の払戻は、ボートレースの公式の結果（Boatrace Open API）から取っています</li>"
             "<li>3連単の中央値は、その場のレースを払戻の小さい順に並べたときの真ん中の値です</li></ul>")
    p.append(CLOSING)
    p.append(f'<p>このnoteについて：<a href="{INTRO_URL}">りんと、当たりも外れも答え合わせ。競艇データバンクを始めます</a></p>')
    return title, "\n".join(x for x in p if x), ["競艇", "ボートレース", "競艇予想", "競艇データ", "競艇データバンク", hi["venue"], lo["venue"]]
