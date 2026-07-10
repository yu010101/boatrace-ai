# Boatrace AI Competitive Analysis

**Date:** 2026-03-05

---

## 1. GitHub Open-Source Landscape (Boatrace/Kyotei)

### Top Boatrace-Related Repos by Stars

| Repo | Stars | Language | Last Updated | Category | Description |
|------|-------|----------|-------------|----------|-------------|
| [cstenmt/boatrace](https://github.com/cstenmt/boatrace) | 22 | C | 2026-02 | Data Download | Bulk CSV download from official boatrace.jp data download page |
| [hmasdev/pyjpboatrace](https://github.com/hmasdev/pyjpboatrace) | 14 | Python | 2026-02 | Library (Scraping + Auto-bet) | PyPI package for scraping race data and automated betting via Selenium |
| [griCe14807/boatrace](https://github.com/griCe14807/boatrace) | 14 | Jupyter Notebook | 2026-01 | Prediction + Auto-bet | Full pipeline: DB creation, data analysis, auto-voting |
| [takobouzu/BOAT_RACE_DB](https://github.com/takobouzu/BOAT_RACE_DB) | 11 | Python | 2025-02 | Database Builder | Scrapes boatrace.jp into SQLite DB, runs on Raspberry Pi |
| [BoatraceOpenAPI/programs](https://github.com/BoatraceOpenAPI/programs) | 7 | PHP | 2026-03 | Open API | Unofficial JSON API for race programs via GitHub Pages, 30-min updates |
| [BoatraceOpenAPI/results](https://github.com/BoatraceOpenAPI/results) | 3 | PHP | 2026-03 | Open API | Unofficial JSON API for race results |
| [GINK03/boatrace-prediction](https://github.com/GINK03/boatrace-prediction) | 2 | Jupyter Notebook | 2022-08 | Prediction | Analysis notebooks |
| [k0kishima/blue_magic](https://github.com/k0kishima/blue_magic) | 1 | Ruby | 2025-04 | Full System (Prediction + Auto-bet) | End-to-end: prediction, simulation, auto-voting via Teleboat; evolved to metaboatrace org |

### Notable Projects (Low Stars but Interesting)

| Repo | Stars | Language | Last Updated | Notes |
|------|-------|----------|-------------|-------|
| [metaboatrace/*](https://github.com/metaboatrace) | 0 | Python/TS/HCL | 2026-02 | Organization evolved from blue_magic. Modular: models, scrapers, crawlers, SNS, infra (Terraform) |
| [a0082489/boatrace-prediction-app](https://github.com/a0082489/boatrace-prediction-app) | 0 | Python | 2025-08 | Flask app with mobile responsive design, covers all 24 venues |
| [tsukasaI/boatrace-ai](https://github.com/tsukasaI/boatrace-ai) | 0 | Rust | 2026-01 | Rare Rust-based boatrace AI |
| [minna-boat-ai/minna_boatrace_ai](https://github.com/minna-boat-ai/minna_boatrace_ai) | 0 | Python | 2025-12 | Community/team project |
| [debuchikun0611-svg/boatrace-ai](https://github.com/debuchikun0611-svg/boatrace-ai) | 0 | Python | 2026-03 | "Competition-style AI prediction app" |

### Key Observations - GitHub Boatrace

1. **Extremely low star counts**: The highest-starred boatrace-specific repo has only 22 stars (and that is a data downloader, not prediction)
2. **No dominant open-source prediction project exists**: The space is fragmented with dozens of small personal projects
3. **Most repos are data infrastructure**: Scrapers, downloaders, DB builders -- not prediction models
4. **No repo publishes verified ROI or backtesting results** openly
5. **No repo has a polished web UI** (except a0082489's Flask app)
6. **No repo integrates with note.com, X (Twitter), or content publishing** (unique to our project)
7. **The metaboatrace organization** is the most architecturally mature (modular repos, Terraform infra) but has 0 stars

---

## 2. Indirect Competitors: Keiba/Horse Racing AI (for comparison)

| Repo | Stars | Language | Description |
|------|-------|----------|-------------|
| [stockedge/netkeiba-scraper](https://github.com/stockedge/netkeiba-scraper) | 113 | Scala | Scrapes netkeiba.com for prediction features |
| [dominicplouffe/HorseRacingPrediction](https://github.com/dominicplouffe/HorseRacingPrediction) | 179 | Python | SVR algorithm for horse racing (English) |
| [codeworks-data/mvp-horse-racing-prediction](https://github.com/codeworks-data/mvp-horse-racing-prediction) | 62 | Jupyter | HK horse racing ML prediction |
| [Christy-Lo/Horse-Racing-Prediction](https://github.com/Christy-Lo/Horse-Racing-Prediction) | 35 | Jupyter | Random Forest, $40K profit in 3000 races from 10K+ records |
| [ryutoro-galois/keiba-predictor](https://github.com/ryutoro-galois/keiba-predictor) | 15 | HTML | Auto-generates weekly prediction reports |
| [KHTTakuya/KeibaPrediction](https://github.com/KHTTakuya/KeibaPrediction) | 12 | Python | Horse racing prediction program |
| [kmycode/kmy-keiba](https://github.com/kmycode/kmy-keiba) | 9 | C# | Desktop app for viewing keiba data |

### Key Observation
Horse racing AI repos get **5-10x more stars** than boatrace repos (179 vs 22 max). This indicates boatrace AI is a much less saturated niche with far less competition.

---

## 3. Commercial Boatrace AI Prediction Services

### Major Services

| Service | URL | Type | Pricing | Key Features | Reported Performance |
|---------|-----|------|---------|-------------|---------------------|
| **AI Shisu** | [ai-shisu.com](https://www.ai-shisu.com/) | Web | Free | Multi-sport (keiba, keirin, boatrace), AI-based numerical indexing | 50,000+ monthly users; creator won 4-consecutive regional horse racing prediction championships |
| **Umekichi AI** | [umepyon.com](https://umepyon.com/) | Web | Free | Covers all ticket types (trifecta, exacta, etc.), daily updates, 24 venues, player ability indices | Not publicly tracked |
| **Poseidon** | [poseidon-boatrace.net](https://poseidon-boatrace.net/) | Web | Free | "Poseidon Index" based on 1M+ historical races, odds analysis | Independent tests found ROI below 100% |
| **BOATERS** | [boaters-boatrace.com](https://boaters-boatrace.com/) | Web | Unknown | 4 AI models (hit-focused, balanced, high-odds, filtering), pre-race predictions | "Currently measuring" (no published results) |
| **boat-race.jp** | [boat-race.jp](https://boat-race.jp/) | Web | Free | Factors: racer ability, lane position, motor performance. Publishes per-prediction P&L | Tracks daily P&L (e.g., +4,680 yen on sample) |
| **Biwako Official AI** | [ai.boatrace-biwako.jp](https://ai.boatrace-biwako.jp/top) | Web (Official) | Free | Official venue-sponsored AI. Racer metrics, motor/boat data, environmental factors | **Hit rate 31.5%, ROI 77.9%** (2025/2-2026/2) |
| **Nikkan Sports AI** | [nikkansports.raceyosou.jp](https://nikkansports.raceyosou.jp/) | App/Web | Freemium | Published by major sports newspaper, learns from race data daily | Hit rate 25%, ROI 102.8% (recent) |

### Mobile Apps

| App | Platform | Downloads | Key Feature |
|-----|----------|-----------|-------------|
| **Ichigeki-kun** (一撃くん) | Android/iOS | N/A (released late 2024) | Specialized for high-payout (ana) predictions |
| **Kyotei AI Yosou** (競艇AI予想) | iOS | 10,000+ since 2020 | General-purpose AI predictions |
| **Kyotei nara High Class** | Android | 50,000+ | Claims 47% hit rate |
| **Nikkan AI Yosou** | iOS | N/A | Nikkan Sports paper's official multi-sport prediction app |

### Key Observations - Commercial

1. **Most commercial services are free** (ad-supported or lead-gen for premium tipster services)
2. **Official venue AI (Biwako) achieves 31.5% hit rate with 77.9% ROI** -- this is the most transparent benchmark. It shows that even official AI loses money long-term
3. **Nikkan Sports AI barely breaks even** at 102.8% ROI -- most honest and credible benchmark
4. **Affiliate/review sites inflate results dramatically** (claiming 237-324% ROI from dubiously-measured periods)
5. **No commercial service publishes code, model architecture, or methodology** openly
6. **No service integrates with note.com or X for content publishing**

---

## 4. ML Approaches Used in the Wild

| Approach | Used By | Notes |
|----------|---------|-------|
| **LightGBM** | HYBRID BOAT MASTER, PC-KYOTEI tutorials, multiple bloggers | Most popular approach. Gradient boosting on tabular race features |
| **Random Forest** | Various research projects | Feature importance assessment for player-motor combinations |
| **Neural Networks (Keras/TF)** | Research papers, HYBRID BOAT MASTER (combined with LightGBM) | ~57% accuracy on test races |
| **Rank Learning (Learning-to-Rank)** | note.com blogger (1-year project) | Predicts relative ordering rather than absolute outcomes |
| **Multiple Regression** | satolog.org blogger | Simplest approach, called "AI" loosely |
| **Logistic Regression** | Various | Win probability estimation baseline |
| **PCA + Clustering** | Research (Grokipedia) | 152 features reduced to 66 via PCA; K-means/Ward clustering for race condition segmentation |
| **Reinforcement Learning** | Research (Fitted Q Iteration) | Betting strategy optimization (not outcome prediction) |
| **Contextual Bandits** | Research (Thompson Sampling) | Adaptive prediction adjustment |

### Common Features Used

- Player win rates (overall, by course/lane, recent form)
- Motor performance metrics (2-ren rate, 3-ren rate)
- Boat performance metrics
- Start timing (ST) averages
- Exhibition times
- Lane/course position (1-6)
- Weather and wind conditions
- Venue-specific statistics
- Player rank (A1, A2, B1, B2)
- Historical head-to-head matchups

### Reported Accuracy Ranges

| Bet Type | Typical AI Accuracy | Notes |
|----------|-------------------|-------|
| Win (単勝) | 40-60% | Course 1 boats achieve ~55% win rate baseline |
| Top-3 finish | 60-70% in favorable conditions | Drops significantly in mixed fields |
| Trifecta (3連単) | 10-20% | Extremely hard; 120 possible outcomes |
| Controlled simulations | 82-91% | Not representative of real-world performance |

---

## 5. Data Infrastructure Ecosystem

| Resource | Type | Notes |
|----------|------|-------|
| [boatrace.jp official data](https://www.boatrace.jp/owpc/pc/extra/data/download.html) | Official Download | LZH-compressed CSV files: player data, results, programs |
| [BoatraceOpenAPI](https://github.com/BoatraceOpenAPI) | Unofficial JSON API | Programs, results, previews via GitHub Pages; 30-min refresh |
| [BoatraceCSV](https://github.com/BoatraceCSV) | Data Repo | Pre-processed CSV data on GitHub Pages |
| [pyjpboatrace](https://pypi.org/project/pyjpboatrace/) | PyPI Package | Scraping + auto-betting library |
| [BOAT_RACE_DB](https://github.com/takobouzu/BOAT_RACE_DB) | SQLite Builder | Complete DB schema from official site scraping |
| [PC-KYOTEI Database](https://pc-kyotei.com/) | Commercial DB | Paid database service with tutorial content |

---

## 6. Competitive Positioning Summary

### What No One Does (Opportunities)

1. **Content publishing integration**: No competitor publishes predictions to note.com or X/Twitter programmatically
2. **Transparent ML pipeline**: No open-source project publishes end-to-end ML code WITH backtesting results
3. **ROI tracking dashboard**: No open-source project tracks and displays ROI over time publicly
4. **Modern web UI**: No open-source project has a polished, mobile-friendly dashboard
5. **Multi-model ensemble**: Most use single model; few combine approaches
6. **Real-time odds-adjusted betting**: Most predict outcomes but don't factor in live odds for value betting

### Our Competitive Advantages (boatrace-ai)

1. **Integrated publishing pipeline**: note.com + X integration is unique in the entire landscape
2. **Modern tech stack**: Python ML + proper project structure with tests
3. **Content monetization angle**: No competitor monetizes through content platforms
4. **End-to-end system**: Prediction + publishing + social media is a unique value chain

### Threats

1. **Official AI (Biwako)** sets a credibility benchmark that is hard to beat transparently
2. **Nikkan Sports** has massive brand trust and data access
3. **AI Shisu** has 50K+ monthly users as the free prediction leader
4. **Data access is commoditized**: Many scrapers and APIs exist; data is not a moat
5. **Model performance ceiling**: Even the best models struggle with trifecta prediction (~20% max)

### Market Size Indicators

- Boatrace annual sales: ~2.4 trillion yen (2024), largest of Japan's public betting sports
- ~80% of purchases are online post-COVID
- Growing interest in AI-assisted betting (proliferation of services since 2020)
- Niche but passionate audience willing to pay for an edge

---

## 7. Recommended Strategy

1. **Focus on content value, not just prediction accuracy**: The market for "accurate prediction" is crowded and hard to differentiate. Publishing insightful analysis to note.com creates unique value
2. **Be transparent about ROI**: Publish tracked results honestly. Most competitors hide behind cherry-picked results. Transparency builds trust
3. **Target the "hobbyist builder" audience**: People who want to understand the AI, not just get tips. note.com articles explaining methodology attract this audience
4. **Use ensemble methods**: Combine LightGBM (most proven) with odds analysis for value betting
5. **Build a brand on X**: No competitor has strong X presence with daily AI predictions + commentary
