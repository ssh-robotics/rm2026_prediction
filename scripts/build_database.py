#!/usr/bin/env python3
"""Build the local RoboMaster prediction SQLite database from CSV tables."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "robomaster_2026.db"

TABLES = [
    "sources",
    "region_slots_2026",
    "regional_teams_2026",
    "complete_form_2026",
    "technical_bonus_2026",
    "rmu_ranking_top_2025",
    "rmuc_2025_national_top4",
    "rmuc_2025_regional_awards",
    "historical_competition_results",
    "historical_technical_awards",
    "historical_preseason_assessments",
    "prediction_feature_weights",
    "model_backtest_plan",
    "match_data_sources",
    "upset_model_features",
    "match_results",
    "team_strength_ratings",
    "model_predictions",
    "model_backtests",
    "region_predictions_2026",
]

OPTIONAL_TABLES = [
    "match_results_2025_central",
    "team_strength_ratings_2025_central",
    "model_predictions_2025_central",
    "model_backtests_2025_central",
]


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def load_csv(conn: sqlite3.Connection, table: str) -> int:
    path = DATA_DIR / f"{table}.csv"
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header")

        columns = reader.fieldnames
        conn.execute(f"DROP TABLE IF EXISTS {quote_ident(table)}")
        column_sql = ", ".join(f"{quote_ident(col)} TEXT" for col in columns)
        conn.execute(f"CREATE TABLE {quote_ident(table)} ({column_sql})")

        placeholders = ", ".join("?" for _ in columns)
        insert_sql = (
            f"INSERT INTO {quote_ident(table)} "
            f"({', '.join(quote_ident(col) for col in columns)}) "
            f"VALUES ({placeholders})"
        )
        rows = [[row[col] for col in columns] for row in reader]
        conn.executemany(insert_sql, rows)
        return len(rows)


def create_views(conn: sqlite3.Connection) -> None:
    conn.execute("DROP VIEW IF EXISTS team_fact_2026")
    conn.execute(
        """
        CREATE VIEW team_fact_2026 AS
        SELECT
            r.school,
            r.team,
            r.region,
            c.complete_rank,
            b.technical_solution_grade,
            b.technical_solution_bonus,
            b.project_doc_grade,
            b.project_doc_bonus,
            b.total_initial_gold_bonus,
            rk.rank AS university_rank_2025,
            rk.score AS university_score_2025
        FROM regional_teams_2026 r
        LEFT JOIN complete_form_2026 c
            ON r.school = c.school AND r.team = c.team
        LEFT JOIN technical_bonus_2026 b
            ON r.school = b.school AND r.team = b.team
        LEFT JOIN rmu_ranking_top_2025 rk
            ON r.school = rk.school
        """
    )

    conn.execute("DROP VIEW IF EXISTS team_history_features_2026")
    conn.execute(
        """
        CREATE VIEW team_history_features_2026 AS
        WITH national AS (
            SELECT
                school,
                team,
                CAST(MIN(
                    CASE
                        WHEN stage = '全国赛' AND finish_order <> ''
                        THEN CAST(finish_order AS INTEGER)
                    END
                ) AS TEXT) AS best_national_finish_order,
                SUM(
                    CASE
                        WHEN stage = '全国赛'
                            AND finish_order <> ''
                            AND CAST(finish_order AS INTEGER) <= 4
                        THEN 1 ELSE 0
                    END
                ) AS national_top4_count,
                SUM(
                    CASE
                        WHEN stage = '全国赛'
                            AND finish_order <> ''
                            AND CAST(finish_order AS INTEGER) <= 8
                        THEN 1 ELSE 0
                    END
                ) AS national_top8_count,
                COUNT(DISTINCT CASE WHEN stage = '全国赛' THEN year END)
                    AS national_award_years
            FROM historical_competition_results
            GROUP BY school, team
        ),
        regional AS (
            SELECT
                school,
                team,
                SUM(CASE WHEN qualification = '晋级全国赛' THEN 1 ELSE 0 END)
                    AS regional_national_advancement_count,
                SUM(CASE WHEN qualification = '晋级复活赛' THEN 1 ELSE 0 END)
                    AS regional_repechage_advancement_count,
                SUM(
                    CASE
                        WHEN stage = '区域赛'
                            AND finish_order <> ''
                            AND CAST(finish_order AS INTEGER) <= 4
                        THEN 1 ELSE 0
                    END
                ) AS regional_top4_count,
                MIN(
                    CASE
                        WHEN stage = '区域赛' AND finish_order <> ''
                        THEN CAST(finish_order AS INTEGER)
                    END
                ) AS best_regional_finish_order
            FROM historical_competition_results
            GROUP BY school, team
        ),
        technical AS (
            SELECT
                school,
                team,
                COUNT(*) AS technical_award_count,
                SUM(CASE WHEN award = '一等奖' THEN 1 ELSE 0 END)
                    AS technical_first_prize_count
            FROM historical_technical_awards
            GROUP BY school, team
        ),
        preseason AS (
            SELECT
                school,
                team,
                MIN(
                    CASE
                        WHEN year = '2023' AND rank <> ''
                        THEN CAST(rank AS INTEGER)
                    END
                ) AS complete_rank_2023,
                MAX(
                    CASE
                        WHEN year = '2023' AND score <> ''
                        THEN CAST(score AS REAL)
                    END
                ) AS complete_score_2023
            FROM historical_preseason_assessments
            GROUP BY school, team
        )
        SELECT
            tf.school,
            tf.team,
            tf.region,
            tf.complete_rank,
            tf.total_initial_gold_bonus,
            tf.university_rank_2025,
            tf.university_score_2025,
            COALESCE(n.best_national_finish_order, '') AS best_national_finish_order,
            COALESCE(n.national_top4_count, 0) AS national_top4_count,
            COALESCE(n.national_top8_count, 0) AS national_top8_count,
            COALESCE(n.national_award_years, 0) AS national_award_years,
            COALESCE(r.regional_national_advancement_count, 0)
                AS regional_national_advancement_count,
            COALESCE(r.regional_repechage_advancement_count, 0)
                AS regional_repechage_advancement_count,
            COALESCE(r.regional_top4_count, 0) AS regional_top4_count,
            COALESCE(CAST(r.best_regional_finish_order AS TEXT), '')
                AS best_regional_finish_order,
            COALESCE(t.technical_award_count, 0) AS technical_award_count,
            COALESCE(t.technical_first_prize_count, 0)
                AS technical_first_prize_count,
            COALESCE(CAST(p.complete_rank_2023 AS TEXT), '')
                AS complete_rank_2023,
            COALESCE(CAST(p.complete_score_2023 AS TEXT), '')
                AS complete_score_2023
        FROM team_fact_2026 tf
        LEFT JOIN national n
            ON tf.school = n.school AND tf.team = n.team
        LEFT JOIN regional r
            ON tf.school = r.school AND tf.team = r.team
        LEFT JOIN technical t
            ON tf.school = t.school AND tf.team = t.team
        LEFT JOIN preseason p
            ON tf.school = p.school AND tf.team = p.team
        """
    )


def create_indexes(conn: sqlite3.Connection) -> None:
    existing_tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    school_team_tables = [
        "regional_teams_2026",
        "complete_form_2026",
        "technical_bonus_2026",
        "rmuc_2025_regional_awards",
        "historical_competition_results",
        "historical_technical_awards",
        "historical_preseason_assessments",
        "team_strength_ratings",
        "team_strength_ratings_2025_central",
    ]
    for table in school_team_tables:
        if table not in existing_tables:
            continue
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_school_team "
            f"ON {quote_ident(table)} (school, team)"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_rmu_ranking_top_2025_school "
        "ON rmu_ranking_top_2025 (school)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sources_source_id "
        "ON sources (source_id)"
    )


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=DELETE")
        counts = {table: load_csv(conn, table) for table in TABLES}
        for table in OPTIONAL_TABLES:
            if (DATA_DIR / f"{table}.csv").exists():
                counts[table] = load_csv(conn, table)
        create_indexes(conn)
        create_views(conn)
        conn.commit()

    for table, count in counts.items():
        print(f"{table}: {count} rows")
    print(f"database: {DB_PATH}")


if __name__ == "__main__":
    main()
