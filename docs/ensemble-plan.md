# BoatraceAI アンサンブル設計案

## Level 0 (Base Models)
1. **LightGBM LambdaRank** (現行) — raw scores
2. **MLP Classifier** (新規) — sklearn or PyTorch
   - Input: 40次元特徴量 (展示タイム追加後)
   - Hidden: [128, 64, 32], Dropout 0.3
   - Output: 6-class softmax

## Level 1 (Meta-Learner)
- Logistic Regression
- Input: 12次元 (6 scores × 2 models)
- 5-fold time-series CV

## 実装ステップ
1. `src/boatrace_ai/ml/nn_model.py` — MLP wrapper
2. `training.py` にstacking追加
3. `model.py` predict統合
