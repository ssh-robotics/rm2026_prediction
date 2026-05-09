# Data Dictionary

## Core Tables

- `sources`: provenance for every imported dataset.
- `region_slots_2026`: national and repechage advancement slots by 2026 region.
- `regional_teams_2026`: official 96-team 2026 regional participant list.
- `complete_form_2026`: official 2026 complete-form video display rank.
- `technical_bonus_2026`: official 2026 technical solution and project document grades with initial gold bonus.
- `rmu_ranking_top_2025`: top of the official university score/rank chart as of August 2025.
- `rmuc_2025_national_top4`: 2025 national top four.
- `rmuc_2025_regional_awards`: 2025 regional award and advancement results for high-signal teams.
- `historical_competition_results`: normalized 2023-2025 national, regional, and invitational award/advancement rows.
- `historical_technical_awards`: normalized robot competitive, tactical, technical report, and annual breakthrough awards.
- `historical_preseason_assessments`: 2023/2024 complete-form scores, 2025 complete-form initial-gold signals, and 2026 complete-form ranks.
- `rmul_2026_awards`: official 2026 University League 3V3, infantry, and engineering challenge award rows.
- `rmul_2026_team_features`: team-level current-season features derived from `rmul_2026_awards`.
- `prediction_feature_weights`: baseline feature priors for the first transparent model.
- `model_backtest_plan`: time-based backtest splits and metrics.
- `match_data_sources`: candidate sources for match-level pairings, scores, and winners.
- `upset_model_features`: explicit upset-risk feature definitions.
- `match_results`: verified 2025 South regional match-level fact table used by
  the first strict backtest.
- `match_results_2025_central`: verified 2025 Central regional match-level fact
  table used by the second strict backtest.
- `team_strength_ratings`, `model_predictions`, `model_backtests`: 2025 South
  model output tables.
- `team_strength_ratings_2025_central`, `model_predictions_2025_central`,
  `model_backtests_2025_central`: 2025 Central model output tables.

## SQLite View

- `team_fact_2026`: joins 2026 regional teams with complete-form rank, initial gold bonus, 2025 university ranking, and 2026 University League features where available.
- `team_history_features_2026`: joins 2026 teams to historical national/regional/technical/preseason features and current-season University League features.

## Data Rules

- Official sources are stored as facts; predictions should be written to separate model or report outputs.
- Team names are preserved as published, including spaces and Chinese punctuation.
- Missing ranking fields mean the school was outside the currently imported top slice, not necessarily unranked.
- Grouped finishes such as 八强、十六强、三十二强 are not internally ordered unless the official source publishes an exact rank.
- Upset risk is modeled as uncertainty and confidence adjustment, not as a reason to rewrite historical facts.
