# RoboMaster Model V3 And Live Rolling Design

## Goal

Improve the current RoboMaster prediction system in two connected layers:

1. Build a stricter pre-event `v3` model that reduces overconfident misses in
   2025 South and Central regional backtests.
2. Add a live rolling predictor that updates team ratings after each completed
   match and uses the updated state to predict later matches in the same event.

The system must keep pre-event and live predictions separate so backtests stay
honest and data leakage is visible.

## Scope

### In Scope

- Add a combined 2025 South + Central backtest report and CSV output.
- Add `v3` feature logic for current-season momentum and breakout teams.
- Add rating update state for live rolling predictions.
- Add a CLI flow that can:
  - initialize event ratings before the first match,
  - predict the next known match or all remaining known matches,
  - ingest one finished match result,
  - update ratings immediately after ingestion,
  - write updated prediction/rating tables.
- Add tests that prove pre-event backtests do not use event results as features,
  while live rolling mode can use already-completed matches.

### Out Of Scope

- Video OCR.
- Automatic live web scraping.
- XGBoost/LightGBM.
- Guaranteeing 80% full-field accuracy.

## Model A: Pre-Event V3

The `v3` pre-event model keeps the current transparent rating approach but adds
explicit current-season momentum:

- `breakout_boost`: for teams with strong 2025 pre-event complete-form,
  initial-gold, technical-solution, or project-document signals but weak older
  historical records.
- `breakout_risk`: raises uncertainty for breakout candidates so they can upset
  favorites without becoming overconfident favorites too quickly.
- `favorite_vs_breakout_cap`: lowers the confidence cap when a historically
  strong favorite faces a high-breakout-risk team.
- `current_signal_score`: normalized score from same-season pre-event signals.

V3 should optimize calibration first:

- lower Brier score,
- lower log loss,
- lower high-confidence error rate,
- preserve or improve top-confidence 20% accuracy.

Full accuracy is still reported but is not the only target.

## Model B: Live Rolling Predictor

Live rolling mode starts from the same pre-event rating snapshot as `v3`.
After each finished match, the match result is appended to a live event log and
the two teams' ratings are updated before predicting later matches.

The rating update should be conservative:

- Higher K/update weight for knockout matches than low-stakes group matches.
- Higher update weight for decisive score margins.
- Lower update weight for low-confidence or disputed source results.
- Rating uncertainty decreases slightly after each observed match.
- Unexpected wins increase the winner more than expected wins.

The predictor must never use future matches during a live replay or live event.
For historical simulation, it processes rows strictly by `match_no` or
`match_order`.

## Data Flow

1. Pre-event build reads historical facts and pre-event assessments.
2. `v3` writes pre-event ratings and pre-event predictions.
3. Live rolling mode copies the pre-event ratings into a live state table.
4. Before a match, live mode predicts from the current live state.
5. After the match, live mode ingests winner and score.
6. The live rating updater writes post-match ratings.
7. Remaining predictions use the updated ratings.

## Tables And Files

New or extended outputs:

- `data/model_predictions_2025_combined_v3.csv`
- `data/model_backtests_2025_combined_v3.csv`
- `data/team_strength_ratings_2025_v3.csv`
- `data/live_match_events.csv`
- `data/live_team_ratings.csv`
- `data/live_model_predictions.csv`
- `reports/2025_combined_v3_backtest.md`

The SQLite build should load these tables when present.

## CLI Design

Suggested commands:

```bash
python3 scripts/backtest_2025_v3.py
python3 scripts/live_rolling_predict.py init --region 中部赛区 --event 2025_central_replay
python3 scripts/live_rolling_predict.py predict --event 2025_central_replay
python3 scripts/live_rolling_predict.py ingest --event 2025_central_replay --match-id rmuc_2025_central_001
python3 scripts/live_rolling_predict.py replay --event 2025_central_replay
```

For initial implementation, `replay` can use the historical Central/South CSVs
to simulate live mode and measure how much rolling updates improve later-match
accuracy.

## Testing

Required tests:

- `v3` combined backtest has 177 matches from South + Central.
- `v3` writes accuracy, top-confidence 20%, Brier, log loss, and
  high-confidence error rate.
- Pre-event predictions include notes proving the feature cutoff and no 2025
  event-result leakage.
- Live replay predictions before match `N` can use matches `< N` but not `N`
  or later.
- Live replay produces a separate metrics row from strict pre-event backtest.
- Database build loads new optional v3/live tables.

## Success Criteria

Minimum acceptable outcome:

- Combined strict pre-event backtest runs end-to-end.
- Live replay runs end-to-end on at least 2025 Central.
- Existing South/Central/2026 tests continue passing.
- High-confidence error rate does not regress versus current v1 on the combined
  South + Central sample.

Preferred outcome:

- Combined Brier and log loss improve.
- Central high-confidence misses involving breakout teams are reduced.
- Live rolling replay improves later-stage match accuracy compared with strict
  pre-event-only predictions.

## Risks

- The current sample is small, so hand-tuned boosts can overfit.
- Community match labels have lower reliability than official live data.
- Rolling predictions can look better simply because later matches include more
  information; reports must label them as live/rolling, not strict pre-event.

## Self-Review

- No placeholder requirements remain.
- Pre-event and live rolling modes are separated to avoid leakage.
- The first implementation is small enough for one plan: shared feature/rating
  utilities, v3 combined backtest, live replay, database/test integration.
