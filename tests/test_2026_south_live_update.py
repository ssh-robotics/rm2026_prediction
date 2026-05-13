import csv
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "robomaster_2026.db"


class SouthLiveUpdateTest(unittest.TestCase):
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

    def test_after16_live_tables_load(self) -> None:
        self.assertEqual(
            16,
            self.scalar("SELECT COUNT(*) FROM live_match_events_2026_south_after16"),
        )
        self.assertEqual(
            32,
            self.scalar("SELECT COUNT(*) FROM live_robot_key_stats_2026_south_after16"),
        )
        self.assertEqual(
            32,
            self.scalar("SELECT COUNT(*) FROM live_team_ratings_2026_south_after16"),
        )
        self.assertEqual(
            4,
            self.scalar("SELECT COUNT(*) FROM live_model_predictions_2026_south_after16"),
        )
        self.assertEqual(
            1,
            self.scalar("SELECT COUNT(*) FROM live_model_backtests_2026_south_after16"),
        )

    def test_after16_predictions_are_rolling_only(self) -> None:
        with (DATA_DIR / "live_model_predictions_2026_south_after16.csv").open(
            newline="", encoding="utf-8"
        ) as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(4, len(rows))
        self.assertEqual({row["status"] for row in rows}, {"rolling_after16"})
        self.assertEqual(
            {row["match_id"] for row in rows},
            {"30916", "30917", "30918", "30919"},
        )
        for row in rows:
            p_red = float(row["p_red_win"])
            p_blue = float(row["p_blue_win"])
            self.assertAlmostEqual(1.0, p_red + p_blue, places=3)
            self.assertTrue(row["predicted_winner"])

    def test_live_source_ids_resolve(self) -> None:
        tables = [
            "live_match_events_2026_south_after16",
            "live_robot_key_stats_2026_south_after16",
            "live_team_ratings_2026_south_after16",
            "live_model_predictions_2026_south_after16",
            "live_model_backtests_2026_south_after16",
        ]
        for table in tables:
            with self.subTest(table=table):
                self.assertEqual(
                    0,
                    self.scalar(
                        f"""
                        SELECT COUNT(*)
                        FROM {table} t
                        LEFT JOIN sources s ON t.source_id = s.source_id
                        WHERE t.source_id <> '' AND s.source_id IS NULL
                        """
                    ),
                )


if __name__ == "__main__":
    unittest.main()
