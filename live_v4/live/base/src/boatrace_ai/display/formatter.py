"""Rich-based display formatting for predictions, results, and stats."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from boatrace_ai.data.constants import GRADES, RACER_CLASSES, STADIUMS
from boatrace_ai.data.models import PredictionResult, RaceProgram

console = Console()

# ボートカラー
BOAT_COLORS: dict[int, str] = {
    1: "bright_white",
    2: "black",
    3: "bright_red",
    4: "bright_blue",
    5: "bright_yellow",
    6: "bright_green",
}


def _boat_label(num: int) -> Text:
    color = BOAT_COLORS.get(num, "white")
    return Text(f" {num} ", style=f"bold {color} on dark_red" if num == 3 else f"bold {color}")


def display_prediction(race: RaceProgram, prediction: PredictionResult) -> None:
    """Display a single race prediction with Rich formatting."""
    stadium = STADIUMS.get(race.race_stadium_number, f"場{race.race_stadium_number}")
    grade = GRADES.get(race.race_grade_number, "")

    # Header
    title = f"{stadium} {race.race_number}R {grade} {race.race_subtitle}"
    console.print()
    console.rule(f"[bold cyan]{title}[/bold cyan]")
    console.print(f"  [dim]{race.race_title} | 締切: {race.race_closed_at}[/dim]")

    # Boat table
    table = Table(show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("枠", justify="center", width=3)
    table.add_column("選手名", width=10)
    table.add_column("級別", justify="center", width=4)
    table.add_column("全国勝率", justify="right", width=8)
    table.add_column("当地勝率", justify="right", width=8)
    table.add_column("ST平均", justify="right", width=6)
    table.add_column("モ2連率", justify="right", width=8)

    for b in race.boats:
        cls = RACER_CLASSES.get(b.racer_class_number, "?")
        cls_style = "bold red" if cls == "A1" else "bold yellow" if cls == "A2" else ""
        table.add_row(
            str(b.racer_boat_number),
            b.racer_name,
            Text(cls, style=cls_style),
            f"{b.racer_national_top_1_percent:.1f}%",
            f"{b.racer_local_top_1_percent:.1f}%",
            f"{b.racer_average_start_timing:.2f}" if b.racer_average_start_timing is not None else "-",
            f"{b.racer_assigned_motor_top_2_percent:.1f}%",
        )

    console.print(table)

    # Prediction
    order_str = " → ".join(str(n) for n in prediction.predicted_order)
    confidence_pct = prediction.confidence * 100
    conf_color = "green" if confidence_pct >= 60 else "yellow" if confidence_pct >= 40 else "red"

    console.print(
        Panel(
            f"[bold]予測着順:[/bold] {order_str}\n"
            f"[bold]信頼度:[/bold] [{conf_color}]{confidence_pct:.0f}%[/{conf_color}]\n"
            f"[bold]推奨買い目:[/bold] {', '.join(prediction.recommended_bets)}\n"
            f"\n[dim]{prediction.analysis}[/dim]",
            title="[bold magenta]AI予測[/bold magenta]",
            border_style="magenta",
        )
    )


def display_accuracy_records(records: list[dict]) -> None:
    """Display accuracy comparison between predictions and results."""
    if not records:
        console.print("[yellow]比較可能なレースがありません。[/yellow]")
        return

    table = Table(title="予測 vs 結果", show_header=True, header_style="bold")
    table.add_column("日付", width=10)
    table.add_column("場", width=6)
    table.add_column("R", justify="center", width=3)
    table.add_column("予測1着", justify="center", width=8)
    table.add_column("実際1着", justify="center", width=8)
    table.add_column("的中", justify="center", width=4)
    table.add_column("予測3連単", justify="center", width=10)
    table.add_column("実際3連単", justify="center", width=10)
    table.add_column("的中", justify="center", width=4)

    for r in records:
        stadium = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
        hit_1st = "[green]○[/green]" if r["hit_1st"] else "[red]×[/red]"
        hit_tri = "[green]○[/green]" if r["hit_trifecta"] else "[red]×[/red]"
        table.add_row(
            r["race_date"],
            stadium,
            str(r["race_number"]),
            str(r["predicted_1st"]),
            str(r["actual_1st"]),
            hit_1st,
            r["predicted_trifecta"],
            r["actual_trifecta"],
            hit_tri,
        )

    console.print(table)


def display_stats(stats: dict) -> None:
    """Display accuracy statistics."""
    total = stats["total_races"]
    if total == 0:
        console.print("[yellow]統計データがありません。まず予測→結果取得→比較を行ってください。[/yellow]")
        return

    table = Table(title="精度レポート", show_header=True, header_style="bold")
    table.add_column("指標", width=20)
    table.add_column("値", justify="right", width=15)

    table.add_row("総レース数", str(total))
    table.add_row("1着的中数", f"{stats['hit_1st']} / {total}")
    table.add_row("1着的中率", f"{stats['hit_1st_rate']:.1%}")
    table.add_row("3連単的中数", f"{stats['hit_trifecta']} / {total}")
    table.add_row("3連単的中率", f"{stats['hit_trifecta_rate']:.1%}")

    console.print()
    console.print(table)


def display_results_saved(count: int, date_str: str) -> None:
    """Display confirmation of saved results."""
    console.print(f"[green]{date_str} の結果を {count} レース保存しました。[/green]")


def display_error(message: str) -> None:
    """Display an error message."""
    console.print(f"[bold red]エラー:[/bold red] {message}")


def display_progress(current: int, total: int, label: str) -> None:
    """Display progress info."""
    console.print(f"  [{current}/{total}] {label}", highlight=False)


def display_publish_progress(current: int, total: int, title: str) -> None:
    """Display article publishing progress."""
    console.print(f"  [{current}/{total}] 投稿中: {title}", highlight=False)


def display_publish_result(title: str, url: str, price: int) -> None:
    """Display successful article publication."""
    console.print(
        Panel(
            f"[bold]{title}[/bold]\n"
            f"URL: [link={url}]{url}[/link]\n"
            f"価格: ¥{price:,}",
            title="[bold green]投稿成功[/bold green]",
            border_style="green",
        )
    )


def display_publish_summary(success: int, failed: int, total: int) -> None:
    """Display publishing summary after batch operation."""
    table = Table(title="投稿サマリー", show_header=True, header_style="bold")
    table.add_column("項目", width=15)
    table.add_column("数", justify="right", width=10)

    table.add_row("対象レース", str(total))
    table.add_row("投稿成功", f"[green]{success}[/green]")
    if failed:
        table.add_row("投稿失敗", f"[red]{failed}[/red]")
    else:
        table.add_row("投稿失敗", "0")

    console.print()
    console.print(table)


def display_note_status(status: dict) -> None:
    """Display note.com login status."""
    if status["logged_in"]:
        console.print("[bold green]✓ note.com にログイン済み[/bold green]")
    else:
        if status["session_exists"]:
            console.print("[bold yellow]△ セッションファイルは存在しますが、有効期限切れです[/bold yellow]")
        else:
            console.print("[bold red]✗ 未ログイン[/bold red]")
    console.print(f"  セッションファイル: {status['session_path']}")


def display_article_preview(title: str, md_text: str) -> None:
    """Display article preview in terminal."""
    console.print(
        Panel(
            md_text,
            title=f"[bold cyan]プレビュー: {title}[/bold cyan]",
            border_style="cyan",
        )
    )


def display_training_progress(collected: int, total_days: int) -> None:
    """Display training data collection progress."""
    console.print(f"  データ収集完了: {collected} レース / {total_days} 日分")


def display_training_result(meta: dict) -> None:
    """Display training result with accuracy metrics."""
    table = Table(title="訓練結果", show_header=True, header_style="bold")
    table.add_column("項目", width=20)
    table.add_column("値", justify="right", width=20)

    table.add_row("訓練日", meta.get("trained_at", "-"))
    table.add_row("訓練レース数", str(meta.get("train_races", 0)))
    table.add_row("検証レース数", str(meta.get("val_races", 0)))
    table.add_row("ベストイテレーション", str(meta.get("best_iteration", "-")))

    metrics = meta.get("metrics", {})
    if metrics:
        logloss = metrics.get("logloss", "-")
        table.add_row("LogLoss", str(logloss))

        hit_1st = metrics.get("hit_1st_rate", 0)
        hit_1st_pct = f"{hit_1st:.1%}" if isinstance(hit_1st, float) else str(hit_1st)
        hit_color = "green" if isinstance(hit_1st, float) and hit_1st >= 0.25 else "yellow"
        table.add_row("1着的中率 (検証)", f"[{hit_color}]{hit_1st_pct}[/{hit_color}]")

        hit_top2 = metrics.get("hit_top2_rate", 0)
        hit_top2_pct = f"{hit_top2:.1%}" if isinstance(hit_top2, float) else str(hit_top2)
        table.add_row("Top2的中率 (検証)", hit_top2_pct)

    console.print()
    console.print(table)
    console.print(
        Panel(
            f"[bold green]モデル保存完了[/bold green]",
            border_style="green",
        )
    )


GRADE_STYLES: dict[str, str] = {
    "S": "bold bright_yellow",   # gold
    "A": "bold green",
    "B": "bold yellow",
    "C": "dim",
}


def display_race_grade(grade_result) -> None:
    """Display a single race grade result."""
    style = GRADE_STYLES.get(grade_result.grade.value, "")
    console.print(
        f"  [{style}]推奨度: {grade_result.grade.value}[/{style}]"
        f"  (p1={grade_result.top1_prob:.0%}, top2={grade_result.top2_prob:.0%},"
        f" top3={grade_result.top3_prob:.0%})"
    )
    console.print(f"  [dim]{grade_result.reason}[/dim]")


def display_grade_summary(grades: list[dict]) -> None:
    """Display a table of all race grades for a day."""
    if not grades:
        console.print("[yellow]推奨度データがありません。[/yellow]")
        return

    table = Table(title="推奨度一覧", show_header=True, header_style="bold")
    table.add_column("日付", width=10)
    table.add_column("場", width=6)
    table.add_column("R", justify="center", width=3)
    table.add_column("推奨度", justify="center", width=6)
    table.add_column("p1", justify="right", width=6)
    table.add_column("top2", justify="right", width=6)
    table.add_column("top3", justify="right", width=6)
    table.add_column("根拠", width=30)

    for g in grades:
        style = GRADE_STYLES.get(g["grade"], "")
        stadium = STADIUMS.get(g["stadium_number"], str(g["stadium_number"]))
        table.add_row(
            g["race_date"],
            stadium,
            str(g["race_number"]),
            Text(g["grade"], style=style),
            f"{g['top1_prob']:.0%}",
            f"{g['top2_prob']:.0%}",
            f"{g['top3_prob']:.0%}",
            g.get("reason", ""),
        )

    console.print()
    console.print(table)

    # Summary counts
    s_count = sum(1 for g in grades if g["grade"] == "S")
    a_count = sum(1 for g in grades if g["grade"] == "A")
    b_count = sum(1 for g in grades if g["grade"] == "B")
    c_count = sum(1 for g in grades if g["grade"] == "C")
    console.print(
        f"  S: {s_count} / A: {a_count} / B: {b_count} / C: {c_count}"
        f"  (計 {len(grades)} レース)"
    )


def display_roi(summary: dict) -> None:
    """Display ROI summary stats."""
    table = Table(title="回収率サマリー", show_header=True, header_style="bold")
    table.add_column("項目", width=20)
    table.add_column("値", justify="right", width=15)

    table.add_row("総ベット数", str(summary["total_bets"]))
    table.add_row("投資額", f"¥{summary['total_invested']:,}")
    table.add_row("払戻額", f"¥{summary['total_payout']:,}")

    profit = summary["profit"]
    profit_color = "green" if profit >= 0 else "red"
    table.add_row("損益", f"[{profit_color}]¥{profit:+,}[/{profit_color}]")

    roi = summary["roi"]
    roi_color = "green" if roi >= 1.0 else "red"
    table.add_row("回収率", f"[{roi_color}]{roi:.0%}[/{roi_color}]")

    table.add_row("的中数", str(summary["hit_count"]))
    table.add_row("的中率", f"{summary['hit_rate']:.1%}")

    console.print()
    console.print(table)


def display_virtual_bets(bets: list[dict]) -> None:
    """Display virtual bet results."""
    if not bets:
        console.print("[yellow]未照合の仮想ベットはありません。[/yellow]")
        return

    table = Table(title="仮想ベット照合結果", show_header=True, header_style="bold")
    table.add_column("日付", width=10)
    table.add_column("場", width=6)
    table.add_column("R", justify="center", width=3)
    table.add_column("賭式", width=6)
    table.add_column("組合せ", width=10)
    table.add_column("推奨度", justify="center", width=6)
    table.add_column("結果", justify="center", width=6)
    table.add_column("配当", justify="right", width=10)

    for b in bets:
        stadium = STADIUMS.get(b.get("stadium_number", 0), "?")
        is_hit = b.get("is_hit")
        if is_hit == 1:
            result = "[green]的中[/green]"
        elif is_hit == 0:
            result = "[red]不的中[/red]"
        else:
            result = "[dim]未判定[/dim]"

        payout = b.get("payout", 0)
        payout_str = f"¥{payout:,}" if payout > 0 else "-"

        grade_style = GRADE_STYLES.get(b.get("grade", ""), "")
        grade_text = Text(b.get("grade", ""), style=grade_style)

        table.add_row(
            b.get("race_date", ""),
            stadium,
            str(b.get("race_number", "")),
            b.get("bet_type", ""),
            b.get("combination", ""),
            grade_text,
            result,
            payout_str,
        )

    console.print()
    console.print(table)


def display_accuracy_preview(title: str, md_text: str) -> None:
    """Display accuracy report preview in terminal."""
    console.print(
        Panel(
            md_text,
            title=f"[bold yellow]的中レポート: {title}[/bold yellow]",
            border_style="yellow",
        )
    )
