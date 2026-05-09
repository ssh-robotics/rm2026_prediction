import csv
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


class East2025BacktestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "backtest_2025_region.py"),
                "--region",
                "东部赛区",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    def read_csv(self, name: str) -> list[dict[str, str]]:
        with (DATA_DIR / name).open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_extracts_2025_east_decisive_matches(self) -> None:
        matches = self.read_csv("match_results_2025_east.csv")

        self.assertEqual(91, len(matches))
        self.assertEqual({"2025"}, {row["year"] for row in matches})
        self.assertEqual({"东部赛区"}, {row["region"] for row in matches})
        self.assertTrue(all(row["winner"] in {row["team_a"], row["team_b"]} for row in matches))
        self.assertEqual(
            {"rm_community_results_2015_2025"},
            {row["source_id"] for row in matches},
        )

    def test_predictions_keep_pre_event_cutoff_and_upset_fields(self) -> None:
        predictions = self.read_csv("model_predictions_2025_east.csv")

        self.assertEqual(91, len(predictions))
        self.assertEqual(
            {"rmuc_2025_east_pre_event_v1"},
            {row["model_run_id"] for row in predictions},
        )
        for row in predictions:
            self.assertEqual("2025-05-26", row["data_cutoff"])
            p_a = float(row["p_team_a_win"])
            p_b = float(row["p_team_b_win"])
            upset = float(row["upset_risk_index"])
            self.assertAlmostEqual(1.0, p_a + p_b, places=6)
            self.assertGreaterEqual(p_a, 0.0)
            self.assertLessEqual(p_a, 1.0)
            self.assertGreaterEqual(upset, 0.0)
            self.assertLessEqual(upset, 1.0)
            self.assertIn("historical_results_year<2025", row["notes"])
            self.assertIn("feature_cutoff=2025-05-26", row["notes"])

    def test_backtest_summary_is_recorded(self) -> None:
        backtests = self.read_csv("model_backtests_2025_east.csv")
        row = next(
            item
            for item in backtests
            if item["backtest_id"] == "backtest_2025_east_pre_event"
        )

        self.assertEqual("91", row["n_matches"])
        self.assertEqual("2025_east_regional_pre_event_cutoff", row["split_name"])
        self.assertGreaterEqual(float(row["coverage"]), 0.99)
        self.assertGreaterEqual(float(row["accuracy"]), 0.50)
        self.assertIn("label_source_post_event", row["notes"])
        self.assertIn("feature_cutoff=2025-05-26", row["notes"])

    def test_report_is_written(self) -> None:
        report = ROOT / "reports" / "2025_east_backtest.md"
        self.assertTrue(report.exists())
        text = report.read_text(encoding="utf-8")
        self.assertIn("2025 东部赛区", text)
        self.assertIn("严格赛前特征", text)

    def test_database_loads_east_backtest_tables(self) -> None:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_database.py")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        with sqlite3.connect(DATA_DIR / "robomaster_2026.db") as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertIn("match_results_2025_east", tables)
            self.assertIn("model_predictions_2025_east", tables)
            count = conn.execute(
                "SELECT COUNT(*) FROM model_predictions_2025_east"
            ).fetchone()[0]
            self.assertEqual(91, count)


if __name__ == "__main__":
    unittest.main()
