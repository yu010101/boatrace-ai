# 記事品質改善 v2（競合分析に基づく改善）

## 完了済み（v1）
- [x] Phase 1: アイキャッチ画像設定（Playwright CDP方式）
- [x] Phase 2: 記事コンテンツのブラッシュアップ（コピー、ハッシュタグ、払戻金額）

## 進行中（v2）

### 施策1: 的中レースの「なぜ」深掘り
- [ ] database.py: get_prediction_for_race() 追加
- [ ] database.py: get_results_for_date() 追加
- [ ] article.py: _build_hit_analysis() 追加
- [ ] article.py: _build_accuracy_html にハイライト根拠追加

### 施策2: 累計実績グラフ画像
- [ ] eyecatch.py: generate_stats_chart() 追加
- [ ] cli.py: グラフ生成→アップロード→記事埋め込み
- [ ] article.py: _build_accuracy_html に chart_url 引数追加

### 施策3: 結果記事の文字数増加
- [ ] article.py: _build_daily_trends() 追加
- [ ] article.py: _build_accuracy_html に傾向セクション追加

### 施策4: タイトルバリエーション
- [ ] article.py: generate_accuracy_report のタイトルロジック変更

### 仕上げ
- [ ] テスト追加・全テストパス
- [ ] コミット・プッシュ・動作確認
