# Collection Log

## 2026-05-09

Collected the first structured RoboMaster 2026 prediction database from public sources.

Primary official sources:

- RoboMaster 2026 RMUC introduction and schedule
- 2026 regional participant list
- 2026 complete-form assessment list
- 2026 technical solution / project document initial gold bonus table
- 2026 midterm and rule-test announcements as indexed sources
- 2025 university ranking top slice
- 2025 regional awards and national top four as historical priors

Current limitations:

- Match-by-match results are not yet imported.
- Full 2025 ranking table is only partially imported.
- Pilot-test details are indexed as a source but not yet normalized into team-level counts.
- Social media scouting, robot configuration notes, and livestream observations remain to be collected separately.

Expanded the database with near-three-year historical priors:

- 2023 official national and regional awards from RoboMaster XLSX attachments.
- 2024 official national and regional award tables.
- 2025 official national and regional award tables.
- 2023/2024 complete-form scores and initial-gold signals.
- 2025 complete-form pass list and initial-gold signals.
- 2023-2025 technical, tactical, robot competitive, and annual breakthrough award signals where available.
- Candidate match-level sources for later winner/score ingestion.

Modeling notes:

- The current database supports team-strength priors and 2026 scouting features.
- It does not yet support a fully trained match winner model, because verified match-level winner/score rows are still missing.
- Upsets are tracked as explicit risk factors in `upset_model_features`; high upset risk should reduce confidence rather than blindly flip predictions.
