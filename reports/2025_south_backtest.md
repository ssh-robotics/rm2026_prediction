# 2025 South Regional Backtest

This report evaluates the first RoboMaster win/loss prediction model on the
2025 South regional event.

## Data Boundary

- Feature cutoff: `2025-05-15`, before the 2025 South regional event.
- Test label source: `rm_community_results_2015_2025`, published after the
  event and used only as ground truth.
- Excluded from features: any 2025 South result, 2025 regional award, 2025
  national result, or later technical award.

## Model

The model builds a pre-event team rating from official 2023-2024 results,
technical awards, and 2025 complete-form initial-gold signals. It then maps
rating difference to a win probability and applies an `upset_risk_index` that
shrinks overconfident favorites toward 50/50 when the match has sparse data,
close ratings, high uncertainty, or high-variance stages.

## Result

| Metric | Value |
| --- | ---: |
| Matches | 89 |
| Coverage | 1.000000 |
| Full accuracy | 0.696629 |
| Top-confidence 20% accuracy | 1.000000 |
| Brier score | 0.214928 |
| Log loss | 0.623352 |
| High-confidence error rate | 0.285714 |

## Interpretation

The strict pre-event full-field model does not reach 80% accuracy. The
high-confidence subset does, which supports treating 80% as a coverage-aware
target instead of a promise for every match. Upsets are represented explicitly
through risk and probability calibration, so low-confidence matches can be
flagged instead of forced into deterministic calls.
