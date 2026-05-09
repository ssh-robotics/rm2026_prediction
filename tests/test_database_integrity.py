import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "robomaster_2026.db"


class DatabaseIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_database.py")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.conn = sqlite3.connect(DB_PATH)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.conn.close()

    def scalar(self, sql: str, params: tuple = ()) -> int:
        row = self.conn.execute(sql, params).fetchone()
        self.assertIsNotNone(row)
        return row[0]

    def test_prediction_tables_exist(self) -> None:
        expected = {
            "historical_competition_results",
            "historical_technical_awards",
            "historical_preseason_assessments",
            "prediction_feature_weights",
            "model_backtest_plan",
            "region_predictions_2026",
        }
        actual = {
            row[0]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        self.assertTrue(expected.issubset(actual))

    def test_historical_results_cover_three_years(self) -> None:
        years = {
            row[0]
            for row in self.conn.execute(
                "SELECT DISTINCT year FROM historical_competition_results"
            )
        }
        self.assertEqual({"2023", "2024", "2025"}, years)
        self.assertGreaterEqual(
            self.scalar("SELECT COUNT(*) FROM historical_competition_results"),
            90,
        )

    def test_preseason_assessments_cover_available_years(self) -> None:
        years = {
            row[0]
            for row in self.conn.execute(
                "SELECT DISTINCT year FROM historical_preseason_assessments"
            )
        }
        self.assertEqual({"2023", "2024", "2025", "2026"}, years)
        self.assertGreaterEqual(
            self.scalar("SELECT COUNT(*) FROM historical_preseason_assessments"),
            384,
        )

    def test_source_ids_resolve(self) -> None:
        tables = [
            "historical_competition_results",
            "historical_technical_awards",
            "historical_preseason_assessments",
            "prediction_feature_weights",
            "model_backtest_plan",
        ]
        for table in tables:
            with self.subTest(table=table):
                unresolved = self.scalar(
                    f"""
                    SELECT COUNT(*)
                    FROM {table} t
                    LEFT JOIN sources s ON t.source_id = s.source_id
                    WHERE t.source_id <> '' AND s.source_id IS NULL
                    """
                )
                self.assertEqual(0, unresolved)

    def test_team_history_features_align_with_2026_field(self) -> None:
        self.assertEqual(
            96,
            self.scalar("SELECT COUNT(*) FROM team_history_features_2026"),
        )
        row = self.conn.execute(
            """
            SELECT best_national_finish_order, national_top8_count, technical_award_count
            FROM team_history_features_2026
            WHERE school = ? AND team = ?
            """,
            ("上海交通大学", "交龙"),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual("1", row[0])
        self.assertGreaterEqual(int(row[1]), 1)
        self.assertGreaterEqual(int(row[2]), 1)


if __name__ == "__main__":
    unittest.main()
