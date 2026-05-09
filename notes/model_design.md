# Prediction Model Design

## Target

The practical target is not "80% accuracy on every match". RoboMaster has
frequent upsets, especially in close-rating matches, short BO formats, and
matches affected by robot reliability. The first defensible target is:

- Full match set: calibrated probabilities, low Brier score and log loss.
- High-confidence subset: reach 80%+ accuracy where model confidence and
  rating/feature gaps justify a prediction.
- Always report coverage together with accuracy, for example
  `accuracy@top_confidence_20pct` and `accuracy@p>=0.75`.

## Model Path

1. Elo baseline from match-level results.
2. Glicko or TrueSkill to represent uncertainty and cross-season inactivity.
3. Logistic regression calibration using rating difference plus team features.
4. XGBoost/LightGBM only after enough match-level results exist.

The likely first production model should be `Glicko + logistic calibration`.

## Current Feature Families

- Current-season 2026 signals:
  - region
  - complete-form rank
  - technical solution / project document grades
  - initial gold bonus
  - University League 3V3 / infantry / engineering challenge results
- Historical strength:
  - 2023-2025 national award group
  - 2023-2025 regional award group and advancement status
  - 2025 RoboMaster university ranking score
- Engineering strength:
  - 2023 and 2024 complete-form scores
  - 2025 complete-form initial gold bonus
  - robot competitive awards
  - tactical / technical report / annual breakthrough awards
- Future match-level features:
  - Glicko/Elo rating
  - recent win rate and score margin
  - opponent-adjusted win rate
  - stage/region/side effects

## Upset Modeling

Upsets should be modeled explicitly instead of discarded as noise.

The database table `upset_model_features` defines seven risk signals:

- `rating_uncertainty`: high Glicko RD or TrueSkill sigma.
- `rating_gap_small`: teams are close in rating.
- `technical_gap_small`: complete-form and initial-gold signals are close.
- `underdog_recent_momentum`: underdog has improving recent results.
- `favorite_recent_decline`: favorite has weakening recent signals.
- `low_match_count`: not enough match evidence.
- `stage_variance`: format and stage amplify variance.

In prediction output, upset risk should reduce confidence and widen probability
toward 50/50. It should not blindly flip the predicted winner.

Current implementation in `scripts/backtest_2025_south.py` uses:

- `close_rating`: exponential risk when two teams are close in pre-event rating.
- `uncertainty`: rating sigma/RD from sparse or indirect evidence.
- `data_confidence`: penalty when the two teams have few pre-cutoff signals.
- `stage_variance`: higher variance for Swiss/group rounds and qualification
  placement matches than for final medal matches.

The final probability is first produced by a logistic transform of rating
difference, then shrunk toward 50/50 according to `upset_risk_index`. The
favorite probability is also capped more aggressively when upset risk is high.

## Backtest Rules

- Use time splits only. No random split.
- A prediction can use only facts published before its `data_cutoff`.
- If two matches are on the same date and no order is known, update ratings
  only after all same-date predictions are scored.
- Record `accuracy`, `Brier`, `log_loss`, calibration buckets, and
  high-confidence error rate.

Planned splits are stored in `model_backtest_plan`.

## Match-Level Data Gap

The current database is strong for team priors but not yet enough for a real
winner model, because `match_results` is intentionally empty until逐场数据 is
verified.

Collection priority:

1. Official RoboMaster live schedule/result pages.
2. Official Bilibili replay titles for pairings.
3. Community result summaries for winner and score, marked with confidence.
4. OCR or manual review for key knockout matches and upset cases.

## 2025 South Regional Backtest

The first strict pre-event backtest uses 2025 South regional matches as labels
and only features available by `2025-05-15`, before the South event started.

- Test labels: 89 decisive South regional matches extracted from the
  2015-2025 community result sheet referenced by the RoboMaster forum post.
- Label source date: 2025-06-05, used only as post-event ground truth.
- Feature cutoff: 2025-05-15.
- Allowed features: 2023-2024 official historical results, 2023-2024 technical
  awards, 2023-2025 pre-event complete-form/initial-gold signals.
- Excluded features: 2025 South regional results, 2025 regional awards,
  2025 national awards, 2025 post-season technical awards.

Backtest result:

- Full coverage accuracy: `0.696629`.
- Top-confidence 20% accuracy: `1.000000`.
- Brier score: `0.214928`.
- Log loss: `0.623352`.

Interpretation: a full-field 80% target is not defensible yet under strict
pre-event information. The first realistic target is 80%+ on a declared
high-confidence subset while continuing to report full-field calibration and
upset-risk warnings.

## 2025 Central Regional Backtest

The second strict pre-event backtest uses 2025 Central regional matches as
labels and only features available by `2025-05-20`, before the Central event
started on 2025-05-21.

- Test labels: 88 decisive Central regional matches extracted from the same
  2015-2025 community result sheet.
- Label source date: 2025-06-05, used only as post-event ground truth.
- Feature cutoff: 2025-05-20.
- Allowed features: 2023-2024 official historical results, 2023-2024 technical
  awards, 2023-2025 pre-event complete-form/initial-gold signals.
- Excluded features: all 2025 regional match results, 2025 regional awards,
  2025 national awards, and 2025 post-season technical awards.

Backtest result:

- Full coverage accuracy: `0.670455`.
- Top-confidence 20% accuracy: `0.888889`.
- Brier score: `0.202366`.
- Log loss: `0.596793`.
- High-confidence error rate: `0.226415`.

Interpretation: Central exposes a different failure mode from South. The model
overrated several historically strong teams and underweighted 2025-season
breakout signals from 中国科学技术大学 RoboWalker and 南京航空航天大学金城学院 Born of Fire.
The next model iteration should add a current-season momentum/upgrade feature
instead of only widening generic upset risk.

## 2026 Region Prediction V2

The 2025 South backtest showed that the raw prior was too confident on some
historical favorites and too harsh on low-evidence improvers. The v2 regional
predictor therefore makes three changes before forecasting 2026 regional
outcomes:

- Fix missing-rank handling: national/regional award rows with empty exact
  order are no longer treated as champion-level results.
- Raise the minimum rating uncertainty and simulation noise, so rankings near
  the qualification boundary remain probabilistic.
- Add 2026 complete-form rank and initial-gold bonus as current-season signals.
- Add 2026 University League results as a current-season momentum signal:
  3V3 is weighted most heavily, infantry and engineering challenge results add
  smaller technical-width signals.

`scripts/predict_2026_region.py --region 南部赛区` writes
`data/region_predictions_2026.csv` and
`reports/2026_south_region_prediction.md`.
