# Autoresearch Program: boatrace-ai

## Overview

boatrace-ai はボートレース（競艇）のAI予測システム。LightGBM LambdaRank で6艇をランキングし、的中率・ROIを最大化する。

## The Single File to Edit

**`src/boatrace_ai/ml/training.py`** — モデルのハイパーパラメータ、学習設定を制御するメインファイル。

変更可能な箇所:
- `LGBM_PARAMS` dict（num_leaves, learning_rate, feature_fraction 等）
- `N_ESTIMATORS`, `EARLY_STOPPING_ROUNDS`
- `OPTUNA_N_TRIALS`, `OPTUNA_TIMEOUT`
- `time_series_split()` ロジック
- `build_dataset()` のデータ変換
- `_evaluate()` 評価ロジック

上級: **`src/boatrace_ai/ml/features.py`** で特徴量を追加・削除可能（現在35特徴量）。

## How to Run an Experiment

```bash
# 基本実験（5分以内）
uv run boatrace train --days 90 --val-days 14

# Optuna チューニング付き（10分）
uv run boatrace train --days 90 --val-days 14 --tune --tune-trials 50

# バックテスト
uv run boatrace roi summary --days 30
```

## How to Evaluate

モデルメタデータ: `~/.boatrace-ai/model.meta.json`

### Primary Metrics
| Metric | 意味 | 目標 |
|--------|------|------|
| `hit_1st_rate` | 1着的中率 | 高いほど良い（ランダム≈17%） |
| `hit_top2_rate` | 上位2予測に1着が含まれる率 | 高いほど良い |

### Secondary Metrics
| Metric | 意味 | 制約 |
|--------|------|------|
| `brier_score` | 確率キャリブレーション | <0.25 |
| `ece` | Expected Calibration Error | <0.10 |

### Business Metrics
| Metric | 意味 | 目標 |
|--------|------|------|
| ROI | 回収率（EV/Kelly方式） | >1.0 |

## Experiment Ideas

### 1. ハイパーパラメータ
```python
num_leaves: [15, 31, 63, 127]
learning_rate: [0.01, 0.03, 0.05, 0.1]
feature_fraction: [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
bagging_fraction: [0.5, 0.7, 0.8, 0.9]
min_child_samples: [5, 10, 20, 50, 100]
reg_alpha: [0, 0.01, 0.1, 1.0, 10.0]
reg_lambda: [0, 0.01, 0.1, 1.0, 10.0]
```

### 2. 学習データ期間
```
--days 30 / 60 / 90 / 180 / 365
```

### 3. 特徴量エンジニアリング（features.py）
- 特徴量重要度分析→下位削除
- 新特徴量案:
  - 選手の直近N走ローリング勝率
  - モーター使用日数（慣らし具合）
  - 風速・波高（水面コンディション）
  - 展示タイム差（直前情報）
  - 1号艇絶対優位度（会場別）

### 4. オッズブレンド比率
- 現行: 70% ML + 30% オッズ
- 試す: 50/50, 80/20, 90/10, 100/0

### 5. キャリブレーション
- IsotonicRegression（現行）
- Platt Scaling
- Temperature Scaling

### 6. EV/Kelly パラメータ
- `EV_MIN`: 0.05, 0.10, 0.15, 0.20
- `EV_KELLY_FRACTION`: 0.10, 0.25, 0.50

## Constraints

1. **LambdaRank objective を維持**
2. **時系列分割を維持**（未来データリーク防止）
3. **固定グループサイズ6** を前提としたコードを壊さない
4. **NDCG@1,3** 評価指標を維持
5. **カテゴリカル特徴量**: stadium_number, grade_number, branch_number

## Workflow

1. `program.md` を読む
2. `training.py` の現在のパラメータを確認
3. 仮説を立てる
4. `training.py` を1箇所だけ変更
5. `python experiment.py --name "experiment_name"` 実行
6. 結果確認→次の仮説
7. 繰り返す
