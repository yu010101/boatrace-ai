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
