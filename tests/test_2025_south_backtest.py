import csv
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


class South2025BacktestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "backtest_2025_south.py")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    def read_csv(self, name: str) -> list[dict[str, str]]:
        with (DATA_DIR / name).open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_extracts_2025_south_decisive_matches(self) -> None:
        matches = self.read_csv("match_results.csv")
        south = [row for row in matches if row["year"] == "2025" and row["region"] == "南部赛区"]

        self.assertEqual(89, len(south))
        self.assertTrue(all(row["winner"] in {row["team_a"], row["team_b"]} for row in south))
        self.assertEqual(
            {"rm_community_results_2015_2025"},
            {row["source_id"] for row in south},
        )

    def test_predictions_keep_pre_event_cutoff_and_upset_fields(self) -> None:
        predictions = self.read_csv("model_predictions.csv")
        south_predictions = [
            row
            for row in predictions
            if row["model_run_id"] == "rmuc_2025_south_pre_event_v1"
        ]

        self.assertEqual(89, len(south_predictions))
        for row in south_predictions:
            self.assertEqual("2025-05-15", row["data_cutoff"])
            p_a = float(row["p_team_a_win"])
            p_b = float(row["p_team_b_win"])
            upset = float(row["upset_risk_index"])
            self.assertAlmostEqual(1.0, p_a + p_b, places=6)
            self.assertGreaterEqual(p_a, 0.0)
            self.assertLessEqual(p_a, 1.0)
            self.assertGreaterEqual(upset, 0.0)
            self.assertLessEqual(upset, 1.0)
            self.assertIn("historical_results_year<2025", row["notes"])
            self.assertIn("feature_cutoff=2025-05-15", row["notes"])

    def test_backtest_summary_is_recorded(self) -> None:
        backtests = self.read_csv("model_backtests.csv")
        row = next(
            item
            for item in backtests
            if item["backtest_id"] == "backtest_2025_south_pre_event"
        )

        self.assertEqual("89", row["n_matches"])
        self.assertEqual("2025_south_regional_pre_event_cutoff", row["split_name"])
        self.assertGreaterEqual(float(row["coverage"]), 0.99)
        self.assertGreaterEqual(float(row["accuracy"]), 0.50)
        self.assertIn("label_source_post_event", row["notes"])
        self.assertIn("feature_cutoff=2025-05-15", row["notes"])


if __name__ == "__main__":
    unittest.main()
