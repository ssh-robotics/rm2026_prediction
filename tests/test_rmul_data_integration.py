import csv
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


class RMULDataIntegrationTest(unittest.TestCase):
    def test_parses_2026_rmul_awards_and_team_features(self) -> None:
        from scripts.prepare_historical_data import (
            build_rmul_team_features,
            parse_rmul_awards_html,
        )

        awards = parse_rmul_awards_html(DATA_DIR / "raw_rmul_2026_awards_official.html")
        features = build_rmul_team_features(awards)

        self.assertGreaterEqual(len(awards), 300)
        contests = {row["contest"] for row in awards}
        self.assertIn("3V3对抗赛", contests)
        self.assertIn("步兵对抗赛", contests)
        self.assertIn("工程挑战赛", contests)
        self.assertTrue(
            any(
                row["contest"] == "3V3对抗赛"
                and row["site"] == "上海站"
                and row["finish_group"] == "冠军"
                and row["school"] == "武汉工程大学"
                and row["team"] == "Nautilus"
                for row in awards
            )
        )

        nautilus = next(
            row
            for row in features
            if row["school"] == "武汉工程大学" and row["team"] == "Nautilus"
        )
        self.assertGreater(float(nautilus["rmul_total_score"]), 70.0)
        self.assertGreater(float(nautilus["rmul_3v3_score"]), 70.0)
        self.assertEqual("上海站", nautilus["best_site"])
        self.assertEqual("冠军", nautilus["best_3v3_finish"])
        self.assertIn("rmul_2026_awards", nautilus["source_id"])

    def test_prepare_writes_rmul_tables(self) -> None:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "prepare_historical_data.py")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        with (DATA_DIR / "rmul_2026_team_features.csv").open(
            newline="", encoding="utf-8"
        ) as f:
            features = list(csv.DictReader(f))

        self.assertGreaterEqual(len(features), 300)
        self.assertTrue(
            any(
                row["school"] == "中国科学技术大学"
                and row["team"] == "RoboWalker"
                and float(row["rmul_total_score"]) > 70.0
                for row in features
            )
        )

    def test_2026_prediction_uses_rmul_current_season_factor(self) -> None:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "prepare_historical_data.py")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "predict_2026_region.py"),
                "--region",
                "南部赛区",
                "--iterations",
                "1000",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        with (DATA_DIR / "region_predictions_2026.csv").open(
            newline="", encoding="utf-8"
        ) as f:
            rows = list(csv.DictReader(f))

        row = next(
            item
            for item in rows
            if item["school"] == "武汉工程大学" and item["team"] == "Nautilus"
        )
        self.assertIn("2026高校联盟赛", row["key_factors"])
        self.assertIn("rmul_2026_awards", row["notes"])


if __name__ == "__main__":
    unittest.main()
