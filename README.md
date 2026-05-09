# RoboMaster Super 2026 Prediction

Workspace for forecasting match outcomes in the 2026 RoboMaster Super Confrontation.

## Structure

- `data/` - raw and cleaned team, match, ranking, and map data
- `notes/` - assumptions, scouting notes, and data-source notes
- `models/` - scripts or notebooks for rating and prediction models
- `reports/` - generated prediction summaries and match previews
- `scripts/` - local build and maintenance scripts

## Current Database

Build or refresh the derived CSV files and SQLite database:

```bash
python3 scripts/prepare_historical_data.py
python3 scripts/backtest_2025_south.py
python3 scripts/backtest_2025_region.py --region 中部赛区
python3 scripts/predict_2026_region.py --region 南部赛区
python3 scripts/build_database.py
```

Run integrity checks:

```bash
python3 -m unittest tests.test_database_integrity tests.test_2025_south_backtest tests.test_2025_central_backtest tests.test_2026_region_prediction
```

Main database:

`data/robomaster_2026.db`

High-signal view:

```sql
SELECT *
FROM team_history_features_2026
ORDER BY CAST(total_initial_gold_bonus AS INTEGER) DESC,
         CAST(complete_rank AS INTEGER);
```

Key modeling notes are in `notes/model_design.md`. Match-level backtest reports:

- `reports/2025_south_backtest.md`: 89 South regional labels with strict
  `2025-05-15` feature cutoff.
- `reports/2025_central_backtest.md`: 88 Central regional labels with strict
  `2025-05-20` feature cutoff.

The first 2026 region forecast is `reports/2026_south_region_prediction.md`.
It uses the calibrated v2 model and writes `data/region_predictions_2026.csv`.

## Suggested Workflow

1. Record confirmed teams and schedule in `data/`.
2. Track each team's recent form, robot configuration, penalties, and map-side performance in `notes/`.
3. Start with a transparent baseline model before adding complex features.
4. Save each prediction report in `reports/` with the date and data cutoff.
