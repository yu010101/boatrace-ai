#!/usr/bin/env python3
"""boatrace-ai autoresearch experiment runner.

Usage:
    python experiment.py --name "num_leaves_63"
    python experiment.py --name "lr_0.03" --tune
    python experiment.py --name "days_180" --days 180
    python experiment.py --list
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "autoresearch"
RESULTS_FILE = RESULTS_DIR / "results.jsonl"
MODEL_META = Path.home() / ".boatrace-ai" / "model.meta.json"


def run_train(days: int = 90, val_days: int = 14, tune: bool = False, tune_trials: int = 50) -> tuple[bool, str]:
    cmd = ["uv", "run", "boatrace", "train", "--days", str(days), "--val-days", str(val_days)]
    if tune:
        cmd.extend(["--tune", "--tune-trials", str(tune_trials)])
    print(f">>> {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    return result.returncode == 0, result.stdout + result.stderr


def parse_model_meta() -> dict:
    if not MODEL_META.exists():
        return {}
    with open(MODEL_META) as f:
        return json.load(f)


def log_result(name: str, metrics: dict, params: dict, duration: float, notes: str = ""):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(),
        "experiment": name,
        "params_changed": params,
        "metrics": metrics,
        "duration_sec": round(duration, 1),
        "notes": notes,
    }
    with open(RESULTS_FILE, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"\n✓ Logged to {RESULTS_FILE}")


def print_results_table():
    if not RESULTS_FILE.exists():
        print("No experiments yet.")
        return
    records = []
    with open(RESULTS_FILE) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    if not records:
        print("No experiments yet.")
        return

    print(f"\n{'='*90}")
    print(f"{'Experiment':<25} {'hit_1st':>8} {'hit_top2':>9} {'brier':>7} {'ece':>6} {'Time':>6}")
    print(f"{'='*90}")
    for r in records:
        m = r.get("metrics", {})
        print(
            f"{r['experiment']:<25} "
            f"{m.get('hit_1st_rate', '-'):>8} "
            f"{m.get('hit_top2_rate', '-'):>9} "
            f"{m.get('brier_score', '-'):>7} "
            f"{m.get('ece', '-'):>6} "
            f"{r.get('duration_sec', '-'):>5}s"
        )
    print(f"{'='*90}")
    print(f"Total: {len(records)} experiments")


def main():
    parser = argparse.ArgumentParser(description="boatrace-ai autoresearch experiment runner")
    parser.add_argument("--name", type=str, help="Experiment name")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--val-days", type=int, default=14)
    parser.add_argument("--tune", action="store_true")
    parser.add_argument("--tune-trials", type=int, default=50)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--notes", type=str, default="")
    args = parser.parse_args()

    if args.list:
        print_results_table()
        return

    if not args.name:
        print("Error: --name required")
        sys.exit(1)

    start = time.time()
    print(f"\n{'='*60}")
    print(f"  Experiment: {args.name}")
    print(f"  Days: {args.days}, Val: {args.val_days}, Tune: {args.tune}")
    print(f"{'='*60}\n")

    success, output = run_train(args.days, args.val_days, args.tune, args.tune_trials)
    if not success:
        print(f"✗ Training failed:\n{output}")
        sys.exit(1)

    print("✓ Training complete")
    meta = parse_model_meta()
    metrics = meta.get("val_metrics", meta.get("metrics", {}))
    print(f"  Metrics: {json.dumps(metrics, indent=2)}")

    duration = time.time() - start
    params = {"days": args.days, "val_days": args.val_days, "tune": args.tune}
    log_result(args.name, metrics, params, duration, args.notes)
    print_results_table()


if __name__ == "__main__":
    main()
