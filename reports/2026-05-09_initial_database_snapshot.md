# Initial Database Snapshot

Data cutoff: 2026-05-09

## Imported Tables

- `sources`: 11 source records
- `region_slots_2026`: 3 regional slot records
- `regional_teams_2026`: 96 regional participant records
- `complete_form_2026`: 96 complete-form assessment records
- `technical_bonus_2026`: 96 initial-gold bonus records
- `rmu_ranking_top_2025`: 16 university ranking records
- `rmuc_2025_national_top4`: 4 national-result records
- `rmuc_2025_regional_awards`: 44 historical regional-result records

## Regional Structure

- 南部赛区: 32 teams, 10 national slots, 6 repechage slots
- 东部赛区: 32 teams, 8 national slots, 6 repechage slots
- 北部赛区: 32 teams, 10 national slots, 4 repechage slots

## Current Highest-Bonus Teams

Initial gold bonus is not a direct strength rating, but it is a useful pre-match technical assessment signal.

- 同济大学 SuperPower: +200, complete-form rank 18
- 中南大学 FYT: +200, complete-form rank 21
- 浙江大学 Hello World: +200, complete-form rank 42
- 中国石油大学（华东）RPS: +175, complete-form rank 10
- 北京理工大学 追梦: +175, complete-form rank 11
- 西安交通大学 笃行: +150, complete-form rank 1
- 哈尔滨工业大学（威海）HERO: +150, complete-form rank 28
- 大连理工大学 凌BUG: +150, complete-form rank 41

## Next Collection Targets

- Normalize pilot-test results into team-level pass counts.
- Import full university ranking table rather than the current top-16 slice.
- Add match-by-match regional schedules and results once public.
- Add livestream/scouting notes in a separate non-fact table.

