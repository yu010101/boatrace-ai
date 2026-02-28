"""CLI entry point using Click."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

import click

from boatrace_ai.data.client import fetch_programs, fetch_results, filter_programs
from boatrace_ai.data.constants import STADIUMS
from boatrace_ai.display.formatter import (
    console,
    display_accuracy_records,
    display_error,
    display_prediction,
    display_progress,
    display_results_saved,
    display_stats,
)
from boatrace_ai.prediction.engine import predict_race
from boatrace_ai.storage.database import (
    check_accuracy,
    get_stats,
    init_db,
    save_prediction,
    save_result,
)

VALID_STADIUMS = click.IntRange(1, 24)
VALID_RACES = click.IntRange(1, 12)


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
def predict_today(stadium: int | None, dry_run: bool) -> None:
    """本日の全レース（または指定場）を予測"""
    asyncio.run(_predict_today(stadium, dry_run))


async def _predict_today(stadium: int | None, dry_run: bool) -> None:
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
    console.print(f"\n[bold]予測対象: {total} レース[/bold]")

    if dry_run:
        for race in races:
            s = STADIUMS.get(race.race_stadium_number, "?")
            console.print(f"  {s} {race.race_number}R {race.race_subtitle}")
        return

    for i, race in enumerate(races, 1):
        s = STADIUMS.get(race.race_stadium_number, "?")
        display_progress(i, total, f"{s} {race.race_number}R 予測中...")

        try:
            prediction = await predict_race(race)
            display_prediction(race, prediction)
            save_prediction(
                race.race_date,
                race.race_stadium_number,
                race.race_number,
                prediction,
            )
        except Exception as e:
            display_error(f"{s} {race.race_number}R の予測に失敗: {e}")


@predict.command("race")
@click.option("--stadium", "-s", type=VALID_STADIUMS, required=True, help="競艇場番号 (1-24)")
@click.option("--race", "-r", "race_num", type=VALID_RACES, required=True, help="レース番号 (1-12)")
@click.option("--date", "-d", "date_str", default=None, help="日付 (YYYY-MM-DD)")
def predict_race_cmd(stadium: int, race_num: int, date_str: str | None) -> None:
    """単一レースを予測"""
    asyncio.run(_predict_single(stadium, race_num, date_str))


async def _predict_single(stadium: int, race_num: int, date_str: str | None) -> None:
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
        with console.status("[bold green]AIが予測中..."):
            prediction = await predict_race(race)
        display_prediction(race, prediction)
        save_prediction(
            race.race_date,
            race.race_stadium_number,
            race.race_number,
            prediction,
        )
    except Exception as e:
        display_error(f"予測に失敗: {e}")


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


# ── stats ─────────────────────────────────────────────────


@cli.command("stats")
def stats_cmd() -> None:
    """精度レポートを表示"""
    stats = get_stats()
    display_stats(stats)


if __name__ == "__main__":
    cli()
