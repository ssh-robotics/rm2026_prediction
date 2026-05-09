import csv
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


class Region2026PredictionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "predict_2026_region.py"),
                "--region",
                "南部赛区",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    def read_csv(self, name: str) -> list[dict[str, str]]:
        with (DATA_DIR / name).open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_outputs_all_south_teams_with_probabilities(self) -> None:
        rows = self.read_csv("region_predictions_2026.csv")
        south_rows = [row for row in rows if row["region"] == "南部赛区"]

        self.assertEqual(32, len(south_rows))
        self.assertEqual("1", south_rows[0]["predicted_rank"])
        self.assertGreater(float(south_rows[0]["champion_probability"]), 0.0)
        for row in south_rows:
            national = float(row["national_probability"])
            repechage = float(row["repechage_probability"])
            upset = float(row["upset_risk_index"])
            self.assertGreaterEqual(national, 0.0)
            self.assertLessEqual(national, 1.0)
            self.assertGreaterEqual(repechage, 0.0)
            self.assertLessEqual(repechage, 1.0)
            self.assertGreaterEqual(upset, 0.0)
            self.assertLessEqual(upset, 1.0)
            self.assertIn("calibrated_from=2025_south_backtest", row["notes"])

    def test_expected_slots_are_calibrated(self) -> None:
        rows = self.read_csv("region_predictions_2026.csv")
        south_rows = [row for row in rows if row["region"] == "南部赛区"]

        national_sum = sum(float(row["national_probability"]) for row in south_rows)
        repechage_sum = sum(float(row["repechage_probability"]) for row in south_rows)

        self.assertAlmostEqual(10.0, national_sum, delta=0.02)
        self.assertAlmostEqual(6.0, repechage_sum, delta=0.02)

    def test_report_is_written(self) -> None:
        report = ROOT / "reports" / "2026_south_region_prediction.md"

        self.assertTrue(report.exists())
        text = report.read_text(encoding="utf-8")
        self.assertIn("2026 南部赛区预测", text)
        self.assertIn("2025 南部回测校准", text)
        self.assertIn("暂无逐场赛程", text)


if __name__ == "__main__":
    unittest.main()
