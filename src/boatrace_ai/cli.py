"""CLI entry point using Click."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta

import click

from boatrace_ai import config
from boatrace_ai.data.client import fetch_programs, fetch_results, filter_programs
from boatrace_ai.data.constants import STADIUMS
from boatrace_ai.display.formatter import (
    console,
    display_accuracy_preview,
    display_accuracy_records,
    display_article_preview,
    display_error,
    display_grade_summary,
    display_note_status,
    display_prediction,
    display_progress,
    display_publish_progress,
    display_publish_result,
    display_publish_summary,
    display_race_grade,
    display_results_saved,
    display_roi,
    display_stats,
    display_training_progress,
    display_training_result,
    display_virtual_bets,
)
from boatrace_ai.prediction.engine import predict_race, predict_race_auto
from boatrace_ai.publish.article import (
    _build_accuracy_markdown,
    _build_hit_analysis,
    _build_markdown,
    generate_accuracy_report,
    generate_article,
    generate_grade_summary_article,
    generate_membership_article,
    generate_midday_report,
    generate_track_record_article,
)
from boatrace_ai.publish.note_client import NoteClient
from boatrace_ai.scoring.grader import grade_race
from boatrace_ai.storage.database import (
    check_accuracy,
    get_accuracy_for_date,
    get_accuracy_trend,
    get_grades_for_date,
    get_latest_article,
    get_prediction_for_race,
    get_predictions_for_date,
    get_results_for_date,
    get_roi_daily,
    get_roi_stats,
    get_roi_trend,
    get_stats,
    init_db,
    save_prediction,
    save_published_article,
    save_race_grade,
    save_race_odds,
    save_result,
    save_virtual_bets,
)
from boatrace_ai.tracking.roi import check_virtual_bets

log = logging.getLogger(__name__)

VALID_STADIUMS = click.IntRange(1, 24)
VALID_RACES = click.IntRange(1, 12)
VALID_MODES = click.Choice(["auto", "ml", "claude", "hybrid"])


def _parse_date(date_str: str | None) -> date | None:
    if date_str is None:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise click.BadParameter(f"日付の形式が不正です: '{date_str}' (正しい形式: YYYY-MM-DD)")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _try_grade_and_save(race, prediction, mode: str, odds_data=None) -> str | None:
    """Try to grade a race and save virtual bets. Returns grade string or None."""
    if mode not in ("ml", "auto"):
        return None
    if not config.MODEL_PATH.exists():
        return None

    try:
        from boatrace_ai.ml.model import get_last_ev_bets, predict_race_ml_with_probs

        _, ordered_probs = predict_race_ml_with_probs(race, odds_data=odds_data)
        grade_result = grade_race(ordered_probs)
        save_race_grade(
            race.race_date,
            race.race_stadium_number,
            race.race_number,
            grade_result.grade.value,
            grade_result.top1_prob,
            grade_result.top2_prob,
            grade_result.top3_prob,
            grade_result.reason,
        )
        display_race_grade(grade_result)

        # Save virtual bets — only for allowed grades (default: S, A)
        allowed_grades = [g.strip() for g in config.BET_GRADES.split(",")]
        if grade_result.grade.value in allowed_grades:
            ev_bets = get_last_ev_bets(race)
            if ev_bets:
                # Filter to high-ROI bet types: 単勝 and 2連単 only
                filtered = [b for b in ev_bets if b.bet_type in ("単勝", "2連単")]
                if filtered:
                    save_virtual_bets(
                        race.race_date,
                        race.race_stadium_number,
                        race.race_number,
                        [b.to_bet_string() for b in filtered],
                        grade=grade_result.grade.value,
                        bet_amounts=[b.bet_amount for b in filtered],
                        model_probs=[b.model_prob for b in filtered],
                        market_odds=[b.market_odds for b in filtered],
                        evs=[b.ev for b in filtered],
                    )
            elif prediction.recommended_bets:
                # Legacy: filter to 単勝/2連単 only
                filtered_bets = [
                    b for b in prediction.recommended_bets
                    if b.startswith("単勝") or b.startswith("2連単")
                ]
                if filtered_bets:
                    save_virtual_bets(
                        race.race_date,
                        race.race_stadium_number,
                        race.race_number,
                        filtered_bets,
                        grade=grade_result.grade.value,
                    )
        else:
            # Consume ev_bets cache even if not saving
            get_last_ev_bets(race)

        return grade_result.grade.value
    except Exception as e:
        logging.getLogger(__name__).debug("Grading failed: %s", e)
        return None


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="詳細ログを表示")
def cli(verbose: bool) -> None:
    """ボートレースAI予想システム"""
    _setup_logging(verbose)
    init_db()


# ── predict ───────────────────────────────────────────────


@cli.group()
def predict() -> None:
    """レース予測"""
    pass


@predict.command("today")
@click.option("--stadium", "-s", type=VALID_STADIUMS, default=None, help="競艇場番号で絞り込み (1-24)")
@click.option("--dry-run", is_flag=True, help="APIを呼ばず出走表のみ表示")
@click.option("--mode", "-m", type=VALID_MODES, default="auto", help="予測モード (auto|ml|claude|hybrid)")
def predict_today(stadium: int | None, dry_run: bool, mode: str) -> None:
    """本日の全レース（または指定場）を予測"""
    asyncio.run(_predict_today(stadium, dry_run, mode))


async def _fetch_odds_safe(race):
    """Fetch odds for a race, returning None on failure (graceful degradation)."""
    if os.environ.get("BOATRACE_SKIP_ODDS"):
        return None
    try:
        from boatrace_ai.data.odds import fetch_odds

        import json

        odds = await fetch_odds(race.race_number, race.race_stadium_number, race.race_date)
        if odds is not None:
            # Cache to DB
            odds_dict = {
                "win": odds.win,
                "exacta": odds.exacta,
                "quinella": odds.quinella,
                "trifecta": odds.trifecta,
                "trio": odds.trio,
                "fetched_at": odds.fetched_at,
            }
            save_race_odds(
                race.race_date,
                race.race_stadium_number,
                race.race_number,
                json.dumps(odds_dict, ensure_ascii=False),
                odds.fetched_at,
            )
            ev_count = len(odds.win) + len(odds.exacta) + len(odds.trifecta)
            logging.getLogger(__name__).info(
                "Odds fetched: stadium=%d race=%d (%d entries)",
                race.race_stadium_number, race.race_number, ev_count,
            )
        return odds
    except Exception as e:
        logging.getLogger(__name__).warning("Odds fetch failed for %dR: %s", race.race_number, e)
        return None


async def _predict_today(stadium: int | None, dry_run: bool, mode: str = "auto") -> None:
    try:
        with console.status("[bold green]出走表を取得中..."):
            programs = await fetch_programs()
    except Exception as e:
        display_error(f"出走表の取得に失敗: {e}")
        return

    races = filter_programs(programs, stadium_number=stadium)
    if not races:
        label = STADIUMS.get(stadium, str(stadium)) if stadium else "本日"
        display_error(f"{label}のレースが見つかりません。")
        return

    total = len(races)
    mode_label = f"モード: {mode}"
    console.print(f"\n[bold]予測対象: {total} レース ({mode_label})[/bold]")

    if dry_run:
        for race in races:
            s = STADIUMS.get(race.race_stadium_number, "?")
            console.print(f"  {s} {race.race_number}R {race.race_subtitle}")
        return

    # Validate feature count before running predictions
    if mode in ("ml", "auto") and config.MODEL_PATH.exists():
        try:
            from boatrace_ai.ml.features import FEATURE_NAMES
            from boatrace_ai.ml.model import load_model

            model = load_model()
            model_n_features = model.num_feature()
            code_n_features = len(FEATURE_NAMES)
            if model_n_features != code_n_features:
                display_error(
                    f"特徴量数の不一致: モデルは {model_n_features} 特徴量で学習されましたが、"
                    f"現在のコードは {code_n_features} 特徴量を生成します。\n"
                    f"'boatrace train' を実行してモデルを再学習してください。"
                )
                return
        except FileNotFoundError:
            pass  # Model not found — will be handled later in prediction flow
        except Exception as e:
            display_error(f"モデルの特徴量チェックに失敗: {e}")
            return

    for i, race in enumerate(races, 1):
        s = STADIUMS.get(race.race_stadium_number, "?")
        display_progress(i, total, f"{s} {race.race_number}R 予測中...")

        # Fetch odds for EV-based betting
        odds_data = None
        if mode in ("ml", "auto") and config.MODEL_PATH.exists():
            odds_data = await _fetch_odds_safe(race)

        try:
            prediction = await predict_race_auto(race, mode=mode, odds_data=odds_data)
            display_prediction(race, prediction)
            save_prediction(
                race.race_date,
                race.race_stadium_number,
                race.race_number,
                prediction,
            )
            _try_grade_and_save(race, prediction, mode, odds_data=odds_data)
        except Exception as e:
            display_error(f"{s} {race.race_number}R の予測に失敗: {e}")


@predict.command("race")
@click.option("--stadium", "-s", type=VALID_STADIUMS, required=True, help="競艇場番号 (1-24)")
@click.option("--race", "-r", "race_num", type=VALID_RACES, required=True, help="レース番号 (1-12)")
@click.option("--date", "-d", "date_str", default=None, help="日付 (YYYY-MM-DD)")
@click.option("--mode", "-m", type=VALID_MODES, default="auto", help="予測モード (auto|ml|claude|hybrid)")
def predict_race_cmd(stadium: int, race_num: int, date_str: str | None, mode: str) -> None:
    """単一レースを予測"""
    asyncio.run(_predict_single(stadium, race_num, date_str, mode))


async def _predict_single(stadium: int, race_num: int, date_str: str | None, mode: str = "auto") -> None:
    d = _parse_date(date_str)
    try:
        with console.status("[bold green]出走表を取得中..."):
            programs = await fetch_programs(d)
    except Exception as e:
        display_error(f"出走表の取得に失敗: {e}")
        return

    races = filter_programs(programs, stadium_number=stadium, race_number=race_num)
    if not races:
        s = STADIUMS.get(stadium, str(stadium))
        display_error(f"{s} {race_num}R が見つかりません。")
        return

    race = races[0]
    try:
        # Fetch odds for EV-based betting
        odds_data = None
        if mode in ("ml", "auto") and config.MODEL_PATH.exists():
            odds_data = await _fetch_odds_safe(race)

        status_label = "MLが予測中..." if mode in ("ml", "auto") and config.MODEL_PATH.exists() else "AIが予測中..."
        with console.status(f"[bold green]{status_label}"):
            prediction = await predict_race_auto(race, mode=mode, odds_data=odds_data)
        display_prediction(race, prediction)
        save_prediction(
            race.race_date,
            race.race_stadium_number,
            race.race_number,
            prediction,
        )
        _try_grade_and_save(race, prediction, mode, odds_data=odds_data)
    except Exception as e:
        display_error(f"予測に失敗: {e}")


# ── train ─────────────────────────────────────────────────


@cli.command("train")
@click.option("--days", "-d", default=365, type=click.IntRange(7, 730), help="訓練データ日数 (default: 365)")
@click.option("--val-days", default=14, type=click.IntRange(1, 90), help="バリデーション日数 (default: 14)")
@click.option("--tune/--no-tune", default=True, help="Optunaでハイパーパラメータを最適化 (default: on)")
@click.option("--tune-trials", default=50, type=click.IntRange(10, 200), help="Optuna試行回数 (default: 50)")
def train_cmd(days: int, val_days: int, tune: bool, tune_trials: int) -> None:
    """MLモデルを訓練"""
    asyncio.run(_train(days, val_days, tune, tune_trials))


async def _train(days: int, val_days: int, tune: bool = True, tune_trials: int = 50) -> None:
    try:
        from boatrace_ai.ml.training import (
            build_dataset,
            collect_training_data,
            time_series_split,
            train_model,
            tune_hyperparams,
        )
    except ImportError as e:
        display_error(str(e))
        return

    console.print(f"\n[bold]ML モデル訓練開始[/bold]")
    console.print(f"  データ期間: 過去 {days} 日 / バリデーション: {val_days} 日")
    if tune:
        console.print(f"  Optuna HPO: {tune_trials} trials\n")
    else:
        console.print()

    # Step 1: Collect data
    try:
        with console.status("[bold green]過去データを収集中..."):
            paired = await collect_training_data(
                days=days,
                progress_callback=display_training_progress,
            )
    except Exception as e:
        display_error(f"データ収集に失敗: {e}")
        return

    if not paired:
        display_error("訓練データが見つかりません。")
        return

    console.print(f"  [green]収集完了: {len(paired)} レース[/green]")

    # Step 2: Time series split
    train_pairs, val_pairs = time_series_split(paired, val_days=val_days)
    if not val_pairs:
        display_error(f"バリデーションデータが不足しています（{val_days}日分のデータが必要）。")
        return

    console.print(f"  訓練: {len(train_pairs)} レース / 検証: {len(val_pairs)} レース")

    # Step 3: Build datasets
    with console.status("[bold green]特徴量を抽出中..."):
        X_train, y_train, groups_train = build_dataset(train_pairs)
        X_val, y_val, groups_val = build_dataset(val_pairs)

    console.print(f"  特徴量抽出完了: 訓練 {len(X_train)} 行 / 検証 {len(X_val)} 行")

    # Step 3.5: Optuna HPO
    best_params = None
    if tune:
        try:
            with console.status(f"[bold green]Optuna HPO ({tune_trials} trials)..."):
                best_params = tune_hyperparams(
                    X_train, y_train, X_val, y_val,
                    groups_train, groups_val,
                    n_trials=tune_trials,
                )
            console.print(f"  [green]HPO完了[/green]: num_leaves={best_params.get('num_leaves')}, "
                          f"lr={best_params.get('learning_rate', 0):.4f}")
        except Exception as e:
            console.print(f"  [yellow]HPO失敗（デフォルトパラメータで続行）: {e}[/yellow]")

    # Step 4: Train
    try:
        with console.status("[bold green]LightGBM LambdaRank 訓練中..."):
            meta = train_model(
                X_train, y_train, X_val, y_val,
                groups_train, groups_val,
                params=best_params,
            )
    except Exception as e:
        display_error(f"訓練に失敗: {e}")
        return

    display_training_result(meta)
    console.print(f"\n  モデル: {config.MODEL_PATH}")
    console.print(f"  メタデータ: {config.MODEL_META_PATH}")


# ── results ───────────────────────────────────────────────


@cli.group()
def results() -> None:
    """結果の取得・比較"""
    pass


@results.command("fetch")
@click.argument("date_str", default=None, required=False)
def results_fetch(date_str: str | None) -> None:
    """結果を取得して保存 (引数: YYYY-MM-DD、省略で本日)"""
    asyncio.run(_results_fetch(date_str))


async def _results_fetch(date_str: str | None) -> None:
    d = _parse_date(date_str)
    label = date_str or "本日"

    try:
        with console.status(f"[bold green]{label}の結果を取得中..."):
            resp = await fetch_results(d)
    except Exception as e:
        display_error(f"結果の取得に失敗: {e}")
        return

    count = 0
    for result in resp.results:
        has_results = any(b.racer_place_number is not None for b in result.boats)
        if has_results:
            save_result(result.race_date, result)
            count += 1

    display_results_saved(count, label)


@results.command("check")
def results_check() -> None:
    """予測と結果を比較"""
    records = check_accuracy()
    display_accuracy_records(records)
    if records:
        hit_1st = sum(1 for r in records if r["hit_1st"])
        hit_tri = sum(1 for r in records if r["hit_trifecta"])
        total = len(records)
        console.print(
            f"\n  [bold]今回の比較: {total}R | 1着的中: {hit_1st} ({hit_1st/total:.0%}) | 3連単的中: {hit_tri} ({hit_tri/total:.0%})[/bold]"
        )

    # Auto-check virtual bets
    checked = check_virtual_bets()
    if checked:
        hit_count = sum(1 for b in checked if b["is_hit"] == 1)
        console.print(f"\n  [bold]仮想ベット照合: {len(checked)}件 (的中: {hit_count}件)[/bold]")


# ── stats ─────────────────────────────────────────────────


@cli.command("stats")
def stats_cmd() -> None:
    """精度レポートを表示"""
    stats = get_stats()
    display_stats(stats)


# ── roi ──────────────────────────────────────────────────


@cli.group()
def roi() -> None:
    """回収率トラッキング"""
    pass


@roi.command("today")
def roi_today() -> None:
    """本日の回収率を表示"""
    today_str = date.today().isoformat()
    summary = get_roi_daily(today_str)
    display_roi(summary)


@roi.command("check")
@click.argument("date_str", default=None, required=False)
def roi_check(date_str: str | None) -> None:
    """仮想ベットを結果と照合 (引数: YYYY-MM-DD、省略で全未照合)"""
    checked = check_virtual_bets()
    display_virtual_bets(checked)

    if checked:
        hit_count = sum(1 for b in checked if b.get("is_hit") == 1)
        total_payout = sum(b.get("payout", 0) for b in checked)
        total_invested = sum(b.get("bet_amount", 1000) for b in checked)
        console.print(
            f"\n  [bold]照合完了: {len(checked)}件 / 的中: {hit_count}件"
            f" / 投資: ¥{total_invested:,} / 払戻: ¥{total_payout:,}[/bold]"
        )


@roi.command("summary")
@click.option("--days", "-d", default=30, type=click.IntRange(1, 365), help="集計日数 (default: 30)")
def roi_summary(days: int) -> None:
    """直近N日の回収率サマリー"""
    start = (date.today() - timedelta(days=days)).isoformat()
    summary = get_roi_stats(start)
    console.print(f"\n[bold]直近 {days} 日間の回収率[/bold]")
    display_roi(summary)


# ── tweet ────────────────────────────────────────────────


@cli.group()
def tweet() -> None:
    """X (Twitter) 投稿"""
    pass


@tweet.command("morning")
@click.argument("date_str", default=None, required=False)
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
def tweet_morning(date_str: str | None, dry_run: bool) -> None:
    """朝の推奨レースツイート"""
    target_str = date_str or date.today().isoformat()

    from boatrace_ai.social.templates import build_morning_tweet
    from boatrace_ai.social.twitter import post_tweet_with_link_reply

    grades = get_grades_for_date(target_str)
    s_rank = [g for g in grades if g["grade"] == "S"]

    # note_url for self-reply
    article = get_latest_article("grades")
    note_url = article["note_url"] if article and article.get("race_date") == target_str else ""

    tweet_text = build_morning_tweet(target_str, s_rank, note_url=note_url)
    console.print(f"\n[bold]ツイート内容:[/bold]\n{tweet_text}\n")
    if note_url:
        console.print(f"[dim]self-reply: {note_url}[/dim]\n")

    if dry_run:
        console.print("[yellow]--dry-run: 投稿をスキップしました[/yellow]")
        return

    try:
        if note_url:
            main_id, reply_id = post_tweet_with_link_reply(
                tweet_text,
                f"全レース予測はこちら\n{note_url}",
                tweet_type="morning", race_date=target_str, dry_run=False,
            )
            if main_id:
                console.print(f"[green]投稿成功 (id={main_id}, reply={reply_id})[/green]")
            else:
                console.print("[yellow]既に投稿済み、またはスキップされました[/yellow]")
        else:
            from boatrace_ai.social.twitter import post_tweet
            tweet_id = post_tweet(
                tweet_text, tweet_type="morning", race_date=target_str, dry_run=False,
            )
            if tweet_id:
                console.print(f"[green]投稿成功 (id={tweet_id})[/green]")
            else:
                console.print("[yellow]既に投稿済み、またはスキップされました[/yellow]")
    except Exception as e:
        display_error(f"ツイート投稿に失敗: {e}")


@tweet.command("hit")
@click.argument("date_str", default=None, required=False)
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
def tweet_hit(date_str: str | None, dry_run: bool) -> None:
    """的中ツイート（当日の的中ベットすべて）"""
    target_str = date_str or date.today().isoformat()

    from boatrace_ai.social.templates import build_hit_tweet
    from boatrace_ai.social.twitter import post_tweet
    from boatrace_ai.storage.database import get_roi_daily as _get_daily

    daily = _get_daily(target_str)
    if daily["total_bets"] == 0:
        display_error("照合済みベットがありません。先に roi check を実行してください。")
        return

    # Get hit bets from DB
    from boatrace_ai.storage.database import _get_connection

    conn = _get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM virtual_bets
               WHERE race_date = ? AND is_hit = 1""",
            (target_str,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        console.print("[yellow]本日の的中ベットはありません。[/yellow]")
        return

    for row in rows:
        tweet_text = build_hit_tweet(
            target_str,
            row["stadium_number"],
            row["race_number"],
            row["bet_type"],
            row["combination"],
            row["payout"],
            grade=row.get("grade", ""),
        )
        console.print(f"\n[bold]ツイート内容:[/bold]\n{tweet_text}\n")

        if dry_run:
            console.print("[yellow]--dry-run: 投稿をスキップ[/yellow]")
            continue

        try:
            tweet_id = post_tweet(
                tweet_text,
                tweet_type="hit",
                race_date=target_str,
                stadium_number=row["stadium_number"],
                race_number=row["race_number"],
                dry_run=False,
            )
            if tweet_id:
                console.print(f"[green]投稿成功 (id={tweet_id})[/green]")
        except Exception as e:
            display_error(f"ツイート投稿に失敗: {e}")


@tweet.command("daily")
@click.argument("date_str", default=None, required=False)
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
def tweet_daily(date_str: str | None, dry_run: bool) -> None:
    """日次サマリーツイート"""
    target_str = date_str or date.today().isoformat()

    from boatrace_ai.social.templates import build_daily_tweet
    from boatrace_ai.social.twitter import post_tweet_with_link_reply

    daily = get_roi_daily(target_str)
    if daily["total_bets"] == 0:
        display_error("本日のベットデータがありません。")
        return

    # note_url for self-reply
    article = get_latest_article("results")
    note_url = article["note_url"] if article and article.get("race_date") == target_str else ""

    tweet_text = build_daily_tweet(
        target_str,
        daily["total_bets"],
        daily["hit_count"],
        daily["roi"],
        note_url=note_url,
    )
    console.print(f"\n[bold]ツイート内容:[/bold]\n{tweet_text}\n")
    if note_url:
        console.print(f"[dim]self-reply: {note_url}[/dim]\n")

    if dry_run:
        console.print("[yellow]--dry-run: 投稿をスキップしました[/yellow]")
        return

    try:
        if note_url:
            main_id, reply_id = post_tweet_with_link_reply(
                tweet_text,
                f"全結果レポートはこちら\n{note_url}",
                tweet_type="daily", race_date=target_str, dry_run=False,
            )
            if main_id:
                console.print(f"[green]投稿成功 (id={main_id}, reply={reply_id})[/green]")
            else:
                console.print("[yellow]既に投稿済み、またはスキップされました[/yellow]")
        else:
            from boatrace_ai.social.twitter import post_tweet
            tweet_id = post_tweet(
                tweet_text, tweet_type="daily", race_date=target_str, dry_run=False,
            )
            if tweet_id:
                console.print(f"[green]投稿成功 (id={tweet_id})[/green]")
            else:
                console.print("[yellow]既に投稿済み、またはスキップされました[/yellow]")
    except Exception as e:
        display_error(f"ツイート投稿に失敗: {e}")


# ── note ──────────────────────────────────────────────────


@cli.group()
def note() -> None:
    """note.com アカウント管理"""
    pass


@note.command("login")
def note_login() -> None:
    """note.com にログイン（セッションcookie取得）"""
    asyncio.run(_note_login())


async def _note_login() -> None:
    try:
        client = NoteClient()
        with console.status("[bold green]note.com にログイン中..."):
            await client.login()
        console.print("[bold green]✓ note.com へのログインに成功しました[/bold green]")
    except Exception as e:
        display_error(f"note.com ログインに失敗: {e}")


@note.command("status")
def note_status() -> None:
    """note.com ログイン状態を確認"""
    asyncio.run(_note_status())


async def _note_status() -> None:
    client = NoteClient()
    status = await client.get_status()
    display_note_status(status)


# ── publish ───────────────────────────────────────────────


@cli.group()
def publish() -> None:
    """記事を note.com に投稿"""
    pass


@publish.command("today")
@click.option("--stadium", "-s", type=VALID_STADIUMS, default=None, help="競艇場番号で絞り込み (1-24)")
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
@click.option("--free", is_flag=True, help="無料記事として投稿（payタグ除去、price=0）")
@click.option("--mode", "-m", type=VALID_MODES, default="auto", help="予測モード (auto|ml|claude|hybrid)")
def publish_today(stadium: int | None, dry_run: bool, free: bool, mode: str) -> None:
    """本日の全レース: 予測→記事→note投稿"""
    asyncio.run(_publish_today(stadium, dry_run, free, mode))


async def _publish_today(
    stadium: int | None, dry_run: bool, free: bool = False, mode: str = "auto"
) -> None:
    # Fetch programs
    try:
        with console.status("[bold green]出走表を取得中..."):
            programs = await fetch_programs()
    except Exception as e:
        display_error(f"出走表の取得に失敗: {e}")
        return

    races = filter_programs(programs, stadium_number=stadium)
    if not races:
        label = STADIUMS.get(stadium, str(stadium)) if stadium else "本日"
        display_error(f"{label}のレースが見つかりません。")
        return

    total = len(races)
    mode_label = "無料" if free else "有料"
    console.print(f"\n[bold]投稿対象: {total} レース（{mode_label} / {mode}モード）[/bold]")

    # Prepare note client (unless dry-run)
    note_client: NoteClient | None = None
    if not dry_run:
        try:
            note_client = NoteClient()
            with console.status("[bold green]note.com ログイン確認中..."):
                await note_client.ensure_logged_in()
        except Exception as e:
            display_error(f"note.com ログインに失敗: {e}")
            return

    success = 0
    failed = 0

    for i, race in enumerate(races, 1):
        s = STADIUMS.get(race.race_stadium_number, "?")
        label = f"{s} {race.race_number}R"

        # Predict (with odds for EV-based betting)
        display_progress(i, total, f"{label} 予測中...")
        odds_data = None
        if mode in ("ml", "auto") and config.MODEL_PATH.exists():
            odds_data = await _fetch_odds_safe(race)
        try:
            prediction = await predict_race_auto(race, mode=mode, odds_data=odds_data)
            save_prediction(
                race.race_date,
                race.race_stadium_number,
                race.race_number,
                prediction,
            )
            grade_str = _try_grade_and_save(race, prediction, mode, odds_data=odds_data)
        except Exception as e:
            display_error(f"{label} の予測に失敗: {e}")
            failed += 1
            continue

        # Generate article (with grade if available)
        title, html_body, hashtags = generate_article(
            race, prediction, free=free, grade=grade_str,
        )

        if dry_run:
            md_text = _build_markdown(race, prediction, free=free, grade=grade_str)
            display_article_preview(title, md_text)
            success += 1
            continue

        # Publish
        display_publish_progress(i, total, title)
        price = 0 if free else config.NOTE_ARTICLE_PRICE
        try:
            result = await note_client.create_and_publish(
                title, html_body, price=price, hashtags=hashtags,
                eyecatch_title=title, article_type="prediction",
            )
            url = result.get("note_url", "")
            display_publish_result(title, url, price)
            success += 1
        except Exception as e:
            display_error(f"{label} の投稿に失敗: {e}")
            failed += 1

        # Rate limiting interval between posts
        if i < total and not dry_run:
            await asyncio.sleep(config.NOTE_PUBLISH_INTERVAL)

    display_publish_summary(success, failed, total)


@publish.command("race")
@click.option("--stadium", "-s", type=VALID_STADIUMS, required=True, help="競艇場番号 (1-24)")
@click.option("--race", "-r", "race_num", type=VALID_RACES, required=True, help="レース番号 (1-12)")
@click.option("--date", "-d", "date_str", default=None, help="日付 (YYYY-MM-DD)")
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
@click.option("--mode", "-m", type=VALID_MODES, default="auto", help="予測モード (auto|ml|claude|hybrid)")
def publish_race(stadium: int, race_num: int, date_str: str | None, dry_run: bool, mode: str) -> None:
    """単一レースを記事化してnote投稿"""
    asyncio.run(_publish_race(stadium, race_num, date_str, dry_run, mode))


async def _publish_race(stadium: int, race_num: int, date_str: str | None, dry_run: bool, mode: str = "auto") -> None:
    d = _parse_date(date_str)

    try:
        with console.status("[bold green]出走表を取得中..."):
            programs = await fetch_programs(d)
    except Exception as e:
        display_error(f"出走表の取得に失敗: {e}")
        return

    races = filter_programs(programs, stadium_number=stadium, race_number=race_num)
    if not races:
        s = STADIUMS.get(stadium, str(stadium))
        display_error(f"{s} {race_num}R が見つかりません。")
        return

    race = races[0]

    # Fetch odds for EV-based betting
    odds_data = None
    if mode in ("ml", "auto") and config.MODEL_PATH.exists():
        odds_data = await _fetch_odds_safe(race)

    # Predict
    try:
        with console.status("[bold green]AIが予測中..."):
            prediction = await predict_race_auto(race, mode=mode, odds_data=odds_data)
        display_prediction(race, prediction)
        save_prediction(
            race.race_date,
            race.race_stadium_number,
            race.race_number,
            prediction,
        )
        grade_str = _try_grade_and_save(race, prediction, mode, odds_data=odds_data)
    except Exception as e:
        display_error(f"予測に失敗: {e}")
        return

    # Generate article
    title, html_body, hashtags = generate_article(
        race, prediction, grade=grade_str,
    )

    if dry_run:
        md_text = _build_markdown(race, prediction, grade=grade_str)
        display_article_preview(title, md_text)
        return

    # Publish
    try:
        note_client = NoteClient()
        with console.status("[bold green]note.com にログイン確認中..."):
            await note_client.ensure_logged_in()
        with console.status("[bold green]記事を投稿中..."):
            result = await note_client.create_and_publish(
                title, html_body, hashtags=hashtags,
                eyecatch_title=title, article_type="prediction",
            )
        url = result.get("note_url", "")
        display_publish_result(title, url, config.NOTE_ARTICLE_PRICE)
    except Exception as e:
        display_error(f"投稿に失敗: {e}")


@publish.command("results")
@click.argument("date_str", default=None, required=False)
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
def publish_results(date_str: str | None, dry_run: bool) -> None:
    """的中レポートを生成してnote投稿 (引数: YYYY-MM-DD、省略で前日)"""
    asyncio.run(_publish_results(date_str, dry_run))


async def _publish_results(date_str: str | None, dry_run: bool) -> None:
    if date_str is None:
        target = date.today() - timedelta(days=1)
        target_str = target.isoformat()
    else:
        d = _parse_date(date_str)
        target_str = d.isoformat() if d else date_str

    # Step 1: Fetch results for the date
    try:
        with console.status(f"[bold green]{target_str}の結果を取得中..."):
            resp = await fetch_results(_parse_date(target_str))
    except Exception as e:
        display_error(f"結果の取得に失敗: {e}")
        return

    count = 0
    for result in resp.results:
        has_results = any(b.racer_place_number is not None for b in result.boats)
        if has_results:
            save_result(result.race_date, result)
            count += 1

    if count == 0:
        display_error(f"{target_str}の結果が見つかりません。")
        return

    display_results_saved(count, target_str)

    # Step 2: Update accuracy_log
    with console.status("[bold green]的中判定中..."):
        check_accuracy()

    # Step 3: Get accuracy data for the date
    records = get_accuracy_for_date(target_str)
    if not records:
        display_error(f"{target_str}の予測データが見つかりません（予測→結果の突合がゼロ件）。")
        return

    # Step 4: Get cumulative stats + ROI
    stats = get_stats()
    roi_stats = get_roi_daily(target_str)

    # Step 4.5: Get results data (used for hit analysis + daily trends)
    results_data = get_results_for_date(target_str)

    # Step 4.6: Build hit analyses for trifecta hits
    hit_analyses: dict[tuple[int, int], str] = {}
    tri_hits = [r for r in records if r["hit_trifecta"]]
    top_hits = sorted(tri_hits, key=lambda x: x.get("trifecta_payout", 0), reverse=True)[:3]
    for r in top_hits:
        pred = get_prediction_for_race(target_str, r["stadium_number"], r["race_number"])
        res_data = None
        for rd in results_data:
            if rd["stadium_number"] == r["stadium_number"] and rd["race_number"] == r["race_number"]:
                res_data = rd
                break
        analysis_text = _build_hit_analysis(r, pred, res_data)
        if analysis_text:
            hit_analyses[(r["stadium_number"], r["race_number"])] = analysis_text

    # Step 5: Generate report (with ROI + related links + new data)
    related_links = _get_related_links("grades", "track_record", "midday")

    # Step 5.5: Get trend data for chart/text display
    accuracy_trend = get_accuracy_trend(30)
    roi_trend = get_roi_trend(30)
    chart_url = None

    if dry_run:
        title, html_body, hashtags = generate_accuracy_report(
            target_str, records, stats, roi_stats=roi_stats,
            related_links=related_links,
            hit_analyses=hit_analyses, results_data=results_data,
            accuracy_trend=accuracy_trend, roi_trend=roi_trend,
        )
        md_text = _build_accuracy_markdown(target_str, records, stats, roi_stats=roi_stats)
        display_accuracy_preview(title, md_text)
        return

    # Step 6: Publish to note.com
    try:
        note_client = NoteClient()
        with console.status("[bold green]note.com にログイン確認中..."):
            await note_client.ensure_logged_in()

        # Try chart image upload (fallback to text-based trend in article)
        try:
            from boatrace_ai.publish.eyecatch import generate_stats_chart

            chart_path = await generate_stats_chart(accuracy_trend, roi_trend)
            if chart_path:
                chart_url = await note_client.upload_image(chart_path)
        except Exception as e:
            log.warning("グラフ画像の生成/アップロードに失敗（テキスト推移で代替）: %s", e)

        title, html_body, hashtags = generate_accuracy_report(
            target_str, records, stats, roi_stats=roi_stats,
            related_links=related_links,
            chart_url=chart_url, hit_analyses=hit_analyses, results_data=results_data,
            accuracy_trend=accuracy_trend, roi_trend=roi_trend,
        )

        with console.status("[bold green]的中レポートを投稿中..."):
            result = await note_client.create_and_publish(
                title, html_body, price=0, hashtags=hashtags,
                eyecatch_title=title, article_type="results",
            )
        url = result.get("note_url", "")
        display_publish_result(title, url, 0)
        if url:
            save_published_article(target_str, "results", url, title)
    except Exception as e:
        display_error(f"投稿に失敗: {e}")


@publish.command("grades")
@click.argument("date_str", default=None, required=False)
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
def publish_grades(date_str: str | None, dry_run: bool) -> None:
    """推奨度ランク一覧を無料記事として投稿"""
    target_str = date_str or date.today().isoformat()

    grades = get_grades_for_date(target_str)
    if not grades:
        display_error(f"{target_str}の推奨度データがありません。先に predict today を実行してください。")
        return

    display_grade_summary(grades)

    # Load predictions to show ◎○△ in the free article
    predictions_map: dict[tuple[int, int], list[int]] = {}
    preds = get_predictions_for_date(target_str)
    for p in preds:
        try:
            order = json.loads(p["predicted_order"]) if isinstance(p["predicted_order"], str) else p["predicted_order"]
            predictions_map[(p["stadium_number"], p["race_number"])] = order
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    stats = get_stats()
    related_links = _get_related_links("results", "track_record", "midday")
    title, html_body, hashtags = generate_grade_summary_article(
        target_str, grades, stats=stats, predictions=predictions_map,
        related_links=related_links,
    )

    if dry_run:
        display_article_preview(title, html_body)
        return

    asyncio.run(_publish_grades_note(title, html_body, hashtags))


async def _publish_grades_note(title: str, html_body: str, hashtags: list[str]) -> None:
    try:
        note_client = NoteClient()
        with console.status("[bold green]note.com にログイン確認中..."):
            await note_client.ensure_logged_in()
        with console.status("[bold green]推奨度記事を投稿中..."):
            result = await note_client.create_and_publish(
                title, html_body, price=0, hashtags=hashtags,
                eyecatch_title=title, article_type="grades",
            )
        url = result.get("note_url", "")
        display_publish_result(title, url, 0)
        if url:
            save_published_article(date.today().isoformat(), "grades", url, title)
    except Exception as e:
        display_error(f"投稿に失敗: {e}")


@publish.command("premium")
@click.argument("date_str", default=None, required=False)
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
def publish_premium(date_str: str | None, dry_run: bool) -> None:
    """Sランクのみの有料記事を自動投稿"""
    asyncio.run(_publish_premium(date_str, dry_run))


async def _publish_premium(date_str: str | None, dry_run: bool) -> None:
    target_str = date_str or date.today().isoformat()

    grades = get_grades_for_date(target_str)
    s_grades = [g for g in grades if g["grade"] == "S"]

    if not s_grades:
        display_error(f"{target_str}のSランクレースがありません。")
        return

    # Fetch programs for S-rank races
    try:
        d = _parse_date(target_str)
        with console.status("[bold green]出走表を取得中..."):
            programs = await fetch_programs(d)
    except Exception as e:
        display_error(f"出走表の取得に失敗: {e}")
        return

    # Match S-rank grades to programs
    s_keys = {(g["stadium_number"], g["race_number"]) for g in s_grades}
    races = [
        r for r in programs.programs
        if (r.race_stadium_number, r.race_number) in s_keys
    ]

    if not races:
        display_error("Sランクに対応するレースが見つかりません。")
        return

    total = len(races)
    console.print(f"\n[bold]Sランク有料記事: {total} レース（¥{config.NOTE_ARTICLE_PRICE}）[/bold]")

    # Prepare note client
    note_client: NoteClient | None = None
    if not dry_run:
        try:
            note_client = NoteClient()
            with console.status("[bold green]note.com ログイン確認中..."):
                await note_client.ensure_logged_in()
        except Exception as e:
            display_error(f"note.com ログインに失敗: {e}")
            return

    success = 0
    failed = 0

    # Open shared browser for batch publishing (reused across all articles)
    if note_client is not None:
        await note_client.open_browser()

    try:
        for i, race in enumerate(races, 1):
            s = STADIUMS.get(race.race_stadium_number, "?")
            label = f"{s} {race.race_number}R"

            display_progress(i, total, f"{label} 予測中...")
            odds_data = None
            if config.MODEL_PATH.exists():
                odds_data = await _fetch_odds_safe(race)
            try:
                prediction = await predict_race_auto(race, mode="ml", odds_data=odds_data)
            except Exception as e:
                display_error(f"{label} の予測に失敗: {e}")
                failed += 1
                continue

            title, html_body, hashtags = generate_article(
                race, prediction, grade="S",
            )

            if dry_run:
                md_text = _build_markdown(race, prediction, grade="S")
                display_article_preview(title, md_text)
                success += 1
                continue

            display_publish_progress(i, total, title)
            try:
                result = await note_client.create_and_publish(
                    title, html_body, price=config.NOTE_ARTICLE_PRICE, hashtags=hashtags,
                    eyecatch_title=title, article_type="prediction",
                )
                url = result.get("note_url", "")
                display_publish_result(title, url, config.NOTE_ARTICLE_PRICE)
                success += 1
            except Exception as e:
                display_error(f"{label} の投稿に失敗: {e}")
                failed += 1

            if i < total:
                await asyncio.sleep(config.NOTE_PUBLISH_INTERVAL)
    finally:
        if note_client is not None:
            await note_client.close_browser()

    display_publish_summary(success, failed, total)


@publish.command("track-record")
@click.option("--days", "-d", default=30, type=click.IntRange(7, 90), help="集計日数 (default: 30)")
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
def publish_track_record(days: int, dry_run: bool) -> None:
    """週次実績レポートを生成してnote投稿"""
    asyncio.run(_publish_track_record(days, dry_run))


def _get_related_links(*article_types: str) -> dict[str, dict]:
    """Fetch latest published articles for cross-linking."""
    links: dict[str, dict] = {}
    for t in article_types:
        article = get_latest_article(t)
        if article:
            links[t] = {"note_url": article["note_url"], "title": article["title"]}
    return links


async def _publish_track_record(days: int, dry_run: bool) -> None:
    accuracy_trend = get_accuracy_trend(days)
    roi_trend = get_roi_trend(days)
    stats = get_stats()

    if not accuracy_trend:
        display_error("実績データがありません。")
        return

    related_links = _get_related_links("grades", "results", "midday")
    title, html_body, hashtags = generate_track_record_article(
        accuracy_trend, roi_trend, stats, related_links=related_links,
    )

    if dry_run:
        console.print(f"\n[bold]タイトル:[/bold] {title}")
        console.print(html_body)
        return

    try:
        note_client = NoteClient()
        with console.status("[bold green]note.com にログイン確認中..."):
            await note_client.ensure_logged_in()
        with console.status("[bold green]実績レポートを投稿中..."):
            result = await note_client.create_and_publish(
                title, html_body, price=0, hashtags=hashtags,
                eyecatch_title=title, article_type="track_record",
            )
        url = result.get("note_url", "")
        display_publish_result(title, url, 0)
        if url:
            save_published_article(date.today().isoformat(), "track_record", url, title)
    except Exception as e:
        display_error(f"投稿に失敗: {e}")


@publish.command("midday")
@click.argument("date_str", default=None, required=False)
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
def publish_midday(date_str: str | None, dry_run: bool) -> None:
    """午前の中間速報を生成してnote投稿"""
    asyncio.run(_publish_midday(date_str, dry_run))


async def _publish_midday(date_str: str | None, dry_run: bool) -> None:
    target_str = date_str or date.today().isoformat()

    # Fetch & save results so far
    try:
        with console.status(f"[bold green]{target_str}の結果を取得中..."):
            resp = await fetch_results(_parse_date(target_str))
    except Exception as e:
        display_error(f"結果の取得に失敗: {e}")
        return

    count = 0
    for result in resp.results:
        has_results = any(b.racer_place_number is not None for b in result.boats)
        if has_results:
            save_result(result.race_date, result)
            count += 1

    if count == 0:
        display_error(f"{target_str}の結果がまだありません。")
        return

    display_results_saved(count, target_str)

    # Update accuracy
    with console.status("[bold green]的中判定中..."):
        check_accuracy()

    records = get_accuracy_for_date(target_str)
    if not records:
        display_error(f"{target_str}の午前データがありません。")
        return

    related_links = _get_related_links("grades", "results", "track_record")
    title, html_body, hashtags = generate_midday_report(
        target_str, records, related_links=related_links,
    )

    if dry_run:
        console.print(f"\n[bold]タイトル:[/bold] {title}")
        console.print(html_body)
        return

    try:
        note_client = NoteClient()
        with console.status("[bold green]note.com にログイン確認中..."):
            await note_client.ensure_logged_in()
        with console.status("[bold green]中間速報を投稿中..."):
            result = await note_client.create_and_publish(
                title, html_body, price=0, hashtags=hashtags,
                eyecatch_title=title, article_type="midday",
            )
        url = result.get("note_url", "")
        display_publish_result(title, url, 0)
        if url:
            save_published_article(target_str, "midday", url, title)
    except Exception as e:
        display_error(f"投稿に失敗: {e}")


@publish.command("membership")
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
def publish_membership(dry_run: bool) -> None:
    """メンバーシップ紹介記事を生成してnote投稿"""
    asyncio.run(_publish_membership(dry_run))


async def _publish_membership(dry_run: bool) -> None:
    stats = get_stats()
    related_links = _get_related_links("grades", "results", "track_record")
    title, html_body, hashtags = generate_membership_article(
        stats, related_links=related_links,
    )

    if dry_run:
        console.print(f"\n[bold]タイトル:[/bold] {title}")
        console.print(html_body)
        return

    try:
        note_client = NoteClient()
        with console.status("[bold green]note.com にログイン確認中..."):
            await note_client.ensure_logged_in()
        with console.status("[bold green]メンバーシップ記事を投稿中..."):
            result = await note_client.create_and_publish(
                title, html_body, price=0, hashtags=hashtags,
                eyecatch_title=title, article_type="membership",
            )
        url = result.get("note_url", "")
        display_publish_result(title, url, 0)
        if url:
            save_published_article(date.today().isoformat(), "membership", url, title)
    except Exception as e:
        display_error(f"投稿に失敗: {e}")


@tweet.command("midday")
@click.argument("date_str", default=None, required=False)
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
def tweet_midday(date_str: str | None, dry_run: bool) -> None:
    """午前の中間速報ツイート"""
    target_str = date_str or date.today().isoformat()

    from boatrace_ai.social.templates import build_midday_tweet
    from boatrace_ai.social.twitter import post_tweet_with_link_reply

    records = get_accuracy_for_date(target_str)
    if not records:
        display_error("午前のデータがありません。先に publish midday を実行してください。")
        return

    total = len(records)
    hit_1st = sum(1 for r in records if r["hit_1st"])
    hit_tri = sum(1 for r in records if r["hit_trifecta"])

    # note_url for self-reply
    article = get_latest_article("midday")
    note_url = article["note_url"] if article and article.get("race_date") == target_str else ""

    tweet_text = build_midday_tweet(target_str, total, hit_1st, hit_tri, note_url=note_url)
    console.print(f"\n[bold]ツイート内容:[/bold]\n{tweet_text}\n")
    if note_url:
        console.print(f"[dim]self-reply: {note_url}[/dim]\n")

    if dry_run:
        console.print("[yellow]--dry-run: 投稿をスキップしました[/yellow]")
        return

    try:
        if note_url:
            main_id, reply_id = post_tweet_with_link_reply(
                tweet_text,
                f"午前の詳細はこちら\n{note_url}",
                tweet_type="midday", race_date=target_str, dry_run=False,
            )
            if main_id:
                console.print(f"[green]投稿成功 (id={main_id}, reply={reply_id})[/green]")
            else:
                console.print("[yellow]既に投稿済み、またはスキップされました[/yellow]")
        else:
            from boatrace_ai.social.twitter import post_tweet
            tweet_id = post_tweet(
                tweet_text, tweet_type="midday", race_date=target_str, dry_run=False,
            )
            if tweet_id:
                console.print(f"[green]投稿成功 (id={tweet_id})[/green]")
            else:
                console.print("[yellow]既に投稿済み、またはスキップされました[/yellow]")
    except Exception as e:
        display_error(f"ツイート投稿に失敗: {e}")


# ── engage ───────────────────────────────────────────────


@cli.group()
def engage() -> None:
    """X エンゲージメント（引用RT・リプライ・いいね）"""
    pass


@engage.command("scan")
@click.option("--target", "-t", default=None, help="特定のハンドル名でフィルタ")
def engage_scan(target: str | None) -> None:
    """ターゲットの最新投稿をスキャン"""
    from boatrace_ai.social.engagement import scan_targets

    with console.status("[bold green]ターゲット投稿をスキャン中..."):
        results = scan_targets(target_handle=target)

    if not results:
        console.print("[yellow]競艇関連のツイートが見つかりませんでした[/yellow]")
        return

    for data in results:
        console.print(f"\n[bold]@{data['handle']}[/bold] ({data['name']}) [優先度{data['priority']}]")
        for tweet in data["tweets"]:
            metrics = tweet.get("metrics", {})
            likes = metrics.get("like_count", 0)
            rts = metrics.get("retweet_count", 0)
            text_preview = tweet["text"][:80].replace("\n", " ")
            console.print(f"  [{tweet['id']}] {text_preview}... (♥{likes} RT{rts})")


@engage.command("quote")
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
def engage_quote(dry_run: bool) -> None:
    """引用RT候補を表示・実行"""
    from boatrace_ai.social.engagement import (
        can_quote,
        pick_quote_template,
        scan_targets,
    )
    from boatrace_ai.social.twitter import quote_repost

    race_date = date.today().isoformat()

    if not can_quote(race_date):
        console.print("[yellow]本日の引用RT上限に達しています[/yellow]")
        return

    results = scan_targets()
    if not results:
        console.print("[yellow]引用RT候補が見つかりませんでした[/yellow]")
        return

    from boatrace_ai.storage.database import save_engagement_log

    for data in results:
        handle = data["handle"]
        if not can_quote(race_date, handle):
            continue
        if not data["tweets"]:
            continue

        tweet = data["tweets"][0]
        text = pick_quote_template()
        console.print(f"\n[bold]引用RT:[/bold] @{handle} の [{tweet['id']}]")
        console.print(f"  テンプレート: {text}")

        if dry_run:
            console.print("  [yellow]--dry-run: スキップ[/yellow]")
            continue

        our_id = quote_repost(tweet["id"], text, race_date)
        if our_id:
            save_engagement_log(
                "quote", handle, race_date,
                target_tweet_id=tweet["id"],
                our_tweet_id=our_id,
                tweet_text=text,
            )
            console.print(f"  [green]投稿成功 (id={our_id})[/green]")
        else:
            console.print("  [red]投稿に失敗しました[/red]")


@engage.command("reply")
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
def engage_reply(dry_run: bool) -> None:
    """リプライ候補を表示・実行"""
    from boatrace_ai.social.engagement import (
        can_reply,
        pick_reply_template,
        scan_targets,
    )
    from boatrace_ai.social.twitter import reply_to_tweet

    race_date = date.today().isoformat()

    if not can_reply(race_date):
        console.print("[yellow]本日のリプライ上限に達しています[/yellow]")
        return

    results = scan_targets()
    if not results:
        console.print("[yellow]リプライ候補が見つかりませんでした[/yellow]")
        return

    from boatrace_ai.storage.database import save_engagement_log

    for data in results:
        handle = data["handle"]
        if not can_reply(race_date):
            break
        if not data["tweets"]:
            continue

        tweet = data["tweets"][0]
        text = pick_reply_template()
        console.print(f"\n[bold]リプライ:[/bold] @{handle} の [{tweet['id']}]")
        console.print(f"  テンプレート: {text}")

        if dry_run:
            console.print("  [yellow]--dry-run: スキップ[/yellow]")
            continue

        reply_id = reply_to_tweet(tweet["id"], text, dry_run=False)
        if reply_id:
            save_engagement_log(
                "reply", handle, race_date,
                target_tweet_id=tweet["id"],
                our_tweet_id=reply_id,
                tweet_text=text,
            )
            console.print(f"  [green]投稿成功 (id={reply_id})[/green]")
        else:
            console.print("  [red]投稿に失敗しました[/red]")


@engage.command("auto")
@click.option("--timing", "-t", type=click.Choice(["morning", "evening"]), required=True, help="タイミング")
@click.option("--dry-run", is_flag=True, help="投稿せずプレビューのみ表示")
def engage_auto(timing: str, dry_run: bool) -> None:
    """自動エンゲージメント実行"""
    from boatrace_ai.social.engagement import execute_engagement

    console.print(f"\n[bold]自動エンゲージメント ({timing})[/bold]")

    if dry_run:
        console.print("[yellow]--dry-run モード[/yellow]")

    try:
        summary = execute_engagement(timing=timing, dry_run=dry_run)
        console.print(f"\n[bold]結果:[/bold]")
        console.print(f"  引用RT: {summary['quotes']}")
        console.print(f"  リプライ: {summary['replies']}")
        console.print(f"  いいね: {summary['likes']}")
        console.print(f"  スキップ: {summary['skipped']}")
    except Exception as e:
        display_error(f"エンゲージメント実行に失敗: {e}")


@engage.command("stats")
@click.argument("date_str", default=None, required=False)
def engage_stats(date_str: str | None) -> None:
    """エンゲージメント統計"""
    from boatrace_ai.social.engagement import get_engagement_stats

    target_date = date_str or date.today().isoformat()
    stats = get_engagement_stats(target_date)

    console.print(f"\n[bold]エンゲージメント統計 ({stats['date']})[/bold]")
    limits = stats["limits"]
    console.print(f"  引用RT: {stats['quotes']}/{limits['max_quotes']}")
    console.print(f"  リプライ: {stats['replies']}/{limits['max_replies']}")
    console.print(f"  いいね: {stats['likes']}/{limits['max_likes']}")


# ── backtest ─────────────────────────────────────────────


@cli.command("backtest")
@click.option("--days", "-d", default=30, type=click.IntRange(1, 365), help="バックテスト日数 (default: 30)")
@click.option("--min-ev", default=0.20, type=float, help="最小EV閾値 (default: 0.20)")
@click.option("--kelly", default=0.25, type=float, help="Kelly fraction (default: 0.25)")
def backtest_cmd(days: int, min_ev: float, kelly: float) -> None:
    """EV戦略のバックテスト（過去データで新旧ROI比較）"""
    from boatrace_ai.ml.backtest import run_backtest

    start = (date.today() - timedelta(days=days)).isoformat()
    results = run_backtest(start_date=start, min_ev=min_ev, kelly_fraction=kelly)

    console.print(f"\n[bold]バックテスト結果 (過去{days}日)[/bold]\n")

    console.print(f"[bold]旧戦略（確信度ベース・固定¥1,000）[/bold]")
    old = results["old"]
    console.print(f"  ベット数: {old['total_bets']}")
    console.print(f"  投資額: ¥{old['total_invested']:,}")
    console.print(f"  払戻額: ¥{old['total_payout']:,}")
    console.print(f"  損益: ¥{old['profit']:,}")
    old_roi_pct = old['roi'] * 100
    roi_color = "green" if old['roi'] >= 1.0 else "red"
    console.print(f"  ROI: [{roi_color}]{old_roi_pct:.1f}%[/{roi_color}]")

    console.print(f"\n[bold]新戦略（EV > {min_ev:.0%} + Kelly {kelly:.0%}）[/bold]")
    new = results["new"]
    console.print(f"  ベット数: {new['total_bets']}")
    console.print(f"  投資額: ¥{new['total_invested']:,}")
    console.print(f"  払戻額: ¥{new['total_payout']:,}")
    console.print(f"  損益: ¥{new['profit']:,}")
    new_roi_pct = new['roi'] * 100
    roi_color = "green" if new['roi'] >= 1.0 else "red"
    console.print(f"  ROI: [{roi_color}]{new_roi_pct:.1f}%[/{roi_color}]")

    improvement = new_roi_pct - old_roi_pct
    imp_color = "green" if improvement > 0 else "red"
    console.print(f"\n  [bold]改善: [{imp_color}]{improvement:+.1f}pp[/{imp_color}][/bold]")

    if new['roi'] >= 1.0:
        console.print("\n  [bold green]Go/No-go: GO — 新戦略は損益分岐点以上です[/bold green]")
    else:
        console.print("\n  [bold yellow]Go/No-go: CAUTION — ROI < 100%、パラメータ調整を検討してください[/bold yellow]")


if __name__ == "__main__":
    cli()
