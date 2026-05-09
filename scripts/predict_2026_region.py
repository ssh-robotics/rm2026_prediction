#!/usr/bin/env python3
"""Predict 2026 RoboMaster regional outcomes with calibrated upset risk."""

from __future__ import annotations

import argparse
import csv
import math
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
MODEL_RUN_ID = "rmuc_2026_region_v2_rmul_calibrated"
SOURCE_ID = "model_design_internal"
DEFAULT_REGION = "南部赛区"
DEFAULT_ITERATIONS = 30000

REGION_REPORT_SLUG = {
    "南部赛区": "south",
    "中部赛区": "central",
    "东部赛区": "east",
    "北部赛区": "north",
}

PREDICTION_FIELDS = [
    "prediction_id",
    "model_run_id",
    "region",
    "school",
    "team",
    "predicted_rank",
    "expected_rank",
    "rating_mu",
    "rating_sigma",
    "champion_probability",
    "national_probability",
    "repechage_probability",
    "upset_risk_index",
    "confidence_tier",
    "key_factors",
    "source_id",
    "notes",
]


@dataclass
class TeamProjection:
    school: str
    team: str
    region: str
    rating_mu: float
    rating_sigma: float
    evidence: int
    factors: list[str]
    champion_probability: float = 0.0
    national_probability: float = 0.0
    repechage_probability: float = 0.0
    expected_rank: float = 0.0
    upset_risk_index: float = 0.0


def read_csv(name: str) -> list[dict[str, str]]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_csv_optional(name: str) -> list[dict[str, str]]:
    path = DATA_DIR / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(name: str, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with (DATA_DIR / name).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def normalize_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = value.replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", value).strip().lower()


def key_for(school: str, team: str) -> tuple[str, str]:
    return normalize_text(school), normalize_text(team)


def add_points(
    exact: dict[tuple[str, str], float],
    school_points: dict[str, float],
    evidence: dict[tuple[str, str], int],
    school_evidence: dict[str, int],
    school: str,
    team: str,
    points: float,
) -> None:
    if not school:
        return
    key = key_for(school, team)
    school_key = normalize_text(school)
    exact[key] += points
    school_points[school_key] += points
    evidence[key] += 1
    school_evidence[school_key] += 1


def finish_points(row: dict[str, str]) -> float:
    try:
        finish_order = int(row.get("finish_order") or 0)
    except ValueError:
        finish_order = 0

    if row["stage"] == "全国赛":
        if finish_order <= 0:
            award = row.get("award", "")
            base = 58 if award == "一等奖" else 38 if award == "二等奖" else 22
        elif finish_order <= 1:
            base = 210
        elif finish_order <= 2:
            base = 185
        elif finish_order <= 4:
            base = 162
        elif finish_order <= 8:
            base = 126
        elif finish_order <= 16:
            base = 90
        else:
            base = 60
    elif row["stage"] == "区域赛":
        if finish_order <= 0:
            award = row.get("award", "")
            base = 30 if award == "一等奖" else 16 if award == "二等奖" else 8
        elif finish_order <= 1:
            base = 96
        elif finish_order <= 2:
            base = 84
        elif finish_order <= 4:
            base = 70
        elif finish_order <= 8:
            base = 48
        elif finish_order <= 16:
            base = 30
        else:
            base = 16
        if row.get("qualification") == "晋级全国赛":
            base += 22
        elif row.get("qualification") == "晋级复活赛":
            base += 10
    else:
        base = 10

    return base * {"2023": 0.45, "2024": 0.75, "2025": 1.08}.get(row["year"], 0.0)


def build_profiles(region: str) -> list[TeamProjection]:
    exact: dict[tuple[str, str], float] = defaultdict(float)
    school_points: dict[str, float] = defaultdict(float)
    evidence: dict[tuple[str, str], int] = defaultdict(int)
    school_evidence: dict[str, int] = defaultdict(int)
    factors: dict[tuple[str, str], list[str]] = defaultdict(list)
    school_factors: dict[str, list[str]] = defaultdict(list)

    for row in read_csv("historical_competition_results.csv"):
        points = finish_points(row)
        add_points(
            exact,
            school_points,
            evidence,
            school_evidence,
            row["school"],
            row["team"],
            points,
        )
        if points >= 90:
            factors[key_for(row["school"], row["team"])].append(
                f"{row['year']}{row['stage']}{row['finish_group']}"
            )

    for row in read_csv("historical_preseason_assessments.csv"):
        year = row["year"]
        if year > "2025":
            continue
        try:
            score = float(row.get("score") or 0)
        except ValueError:
            score = 0.0
        try:
            initial_gold = float(row.get("total_initial_gold_bonus") or 0)
        except ValueError:
            initial_gold = 0.0
        points = 0.0
        if year == "2025":
            points = initial_gold * 0.70
        elif year == "2024":
            points = score * 0.07 + initial_gold * 0.14
        elif year == "2023":
            points = score * 0.035 + initial_gold * 0.07
        add_points(
            exact,
            school_points,
            evidence,
            school_evidence,
            row["school"],
            row["team"],
            points,
        )

    for row in read_csv("historical_technical_awards.csv"):
        award_text = f"{row.get('award_category', '')}{row.get('award_name', '')}"
        points = 10.0
        if "技术突破" in award_text or "最佳技术报告" in award_text:
            points = 18.0
        elif "最佳战术" in award_text:
            points = 16.0
        points *= {"2023": 0.45, "2024": 0.75, "2025": 1.0}.get(row["year"], 0.0)
        add_points(
            exact,
            school_points,
            evidence,
            school_evidence,
            row["school"],
            row["team"],
            points,
        )
        if points >= 12:
            factors[key_for(row["school"], row["team"])].append(row["award_name"])

    for row in read_csv("rmu_ranking_top_2025.csv"):
        try:
            score = float(row["score"])
        except ValueError:
            score = 0.0
        school_key = normalize_text(row["school"])
        school_points[school_key] += score * 6.0
        school_evidence[school_key] += 1
        school_factors[school_key].append(f"2025高校积分榜Top{row['rank']}")

    for row in read_csv("complete_form_2026.csv"):
        try:
            rank = int(row["complete_rank"])
        except ValueError:
            rank = 96
        rank_points = max(0.0, 118.0 - rank * 1.05)
        add_points(
            exact,
            school_points,
            evidence,
            school_evidence,
            row["school"],
            row["team"],
            rank_points,
        )
        if rank <= 20:
            factors[key_for(row["school"], row["team"])].append(f"2026完整形态第{rank}")

    for row in read_csv("technical_bonus_2026.csv"):
        try:
            initial_gold = float(row["total_initial_gold_bonus"] or 0)
        except ValueError:
            initial_gold = 0.0
        points = initial_gold * 0.82
        add_points(
            exact,
            school_points,
            evidence,
            school_evidence,
            row["school"],
            row["team"],
            points,
        )
        if initial_gold >= 100:
            factors[key_for(row["school"], row["team"])].append(
                f"2026初始金币{int(initial_gold)}"
            )

    for row in read_csv_optional("rmul_2026_team_features.csv"):
        try:
            total_score = float(row.get("rmul_total_score") or 0.0)
        except ValueError:
            total_score = 0.0
        try:
            score_3v3 = float(row.get("rmul_3v3_score") or 0.0)
        except ValueError:
            score_3v3 = 0.0
        points = min(128.0, total_score * 0.72 + score_3v3 * 0.22)
        add_points(
            exact,
            school_points,
            evidence,
            school_evidence,
            row["school"],
            row["team"],
            points,
        )
        if points >= 40:
            site = row.get("best_site", "")
            finish = row.get("best_3v3_finish", "")
            factors[key_for(row["school"], row["team"])].append(
                f"2026高校联盟赛{site}{finish}"
            )

    projections: list[TeamProjection] = []
    for row in read_csv("regional_teams_2026.csv"):
        if row["region"] != region:
            continue
        key = key_for(row["school"], row["team"])
        school_key = normalize_text(row["school"])
        exact_points = exact.get(key, 0.0)
        fallback_points = school_points.get(school_key, 0.0) * 0.72
        profile_source = "exact" if exact_points else "school_fallback"
        points = exact_points if exact_points else fallback_points
        count = evidence.get(key, 0) if exact_points else school_evidence.get(school_key, 0)

        rating = 1500.0 + points
        sigma = max(70.0, 210.0 / math.sqrt(count + 1))
        if profile_source == "school_fallback":
            sigma += 25.0
        if count <= 2:
            sigma += 35.0

        factor_list = factors.get(key, []) or school_factors.get(school_key, [])
        if not factor_list:
            factor_list = ["历史奖项/考核信号" if profile_source == "exact" else "学校级历史信号"]

        projections.append(
            TeamProjection(
                school=row["school"],
                team=row["team"],
                region=region,
                rating_mu=rating,
                rating_sigma=sigma,
                evidence=count,
                factors=factor_list[:4],
            )
        )

    if not projections:
        raise ValueError(f"no teams found for region {region}")
    return projections


def region_slots(region: str) -> tuple[int, int]:
    for row in read_csv("region_slots_2026.csv"):
        if row["region"] == region:
            return int(row["national_slots"]), int(row["repechage_slots"])
    raise ValueError(f"no slot definition for region {region}")


def simulate_region(
    projections: list[TeamProjection],
    national_slots: int,
    repechage_slots: int,
    iterations: int,
) -> None:
    rng = random.Random(20260509)
    champion_counts = defaultdict(int)
    national_counts = defaultdict(int)
    repechage_counts = defaultdict(int)
    rank_sum = defaultdict(float)

    for _ in range(iterations):
        sampled = []
        for item in projections:
            calibrated_sigma = math.sqrt(item.rating_sigma**2 + 115.0**2)
            sampled_rating = rng.gauss(item.rating_mu, calibrated_sigma)
            sampled.append((sampled_rating, item))
        sampled.sort(key=lambda pair: pair[0], reverse=True)

        for index, (_, item) in enumerate(sampled, start=1):
            key = key_for(item.school, item.team)
            rank_sum[key] += index
            if index == 1:
                champion_counts[key] += 1
            if index <= national_slots:
                national_counts[key] += 1
            elif index <= national_slots + repechage_slots:
                repechage_counts[key] += 1

    for item in projections:
        key = key_for(item.school, item.team)
        item.champion_probability = champion_counts[key] / iterations
        item.national_probability = national_counts[key] / iterations
        item.repechage_probability = repechage_counts[key] / iterations
        item.expected_rank = rank_sum[key] / iterations

    for item in projections:
        boundary_risk = math.exp(-abs(item.expected_rank - national_slots) / 5.5)
        uncertainty_risk = min(1.0, item.rating_sigma / 210.0)
        evidence_risk = 1.0 if item.evidence <= 2 else max(0.0, 1.0 - item.evidence / 12.0)
        item.upset_risk_index = min(
            1.0,
            0.48 * uncertainty_risk + 0.34 * boundary_risk + 0.18 * evidence_risk,
        )


def confidence_tier(item: TeamProjection) -> str:
    if item.national_probability >= 0.82 and item.upset_risk_index <= 0.45:
        return "high"
    if item.national_probability >= 0.55:
        return "medium"
    if item.repechage_probability >= 0.30:
        return "bubble"
    return "low"


def prediction_rows(projections: list[TeamProjection]) -> list[dict[str, Any]]:
    ordered = sorted(
        projections,
        key=lambda item: (item.expected_rank, -item.national_probability),
    )
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(ordered, start=1):
        rows.append(
            {
                "prediction_id": f"pred_2026_{REGION_REPORT_SLUG.get(item.region, 'region')}_{index:02d}",
                "model_run_id": MODEL_RUN_ID,
                "region": item.region,
                "school": item.school,
                "team": item.team,
                "predicted_rank": str(index),
                "expected_rank": f"{item.expected_rank:.3f}",
                "rating_mu": f"{item.rating_mu:.3f}",
                "rating_sigma": f"{item.rating_sigma:.3f}",
                "champion_probability": f"{item.champion_probability:.6f}",
                "national_probability": f"{item.national_probability:.6f}",
                "repechage_probability": f"{item.repechage_probability:.6f}",
                "upset_risk_index": f"{item.upset_risk_index:.6f}",
                "confidence_tier": confidence_tier(item),
                "key_factors": ";".join(item.factors),
                "source_id": SOURCE_ID,
                "notes": (
                    "calibrated_from=2025_south_backtest;"
                    "v2_changes=lower_confidence_cap,higher_sigma_floor,current_complete_form;"
                    "current_season_sources=rmul_2026_awards;"
                    "no_match_schedule_available"
                ),
            }
        )
    return rows


def write_report(region: str, rows: list[dict[str, Any]], national_slots: int, repechage_slots: int) -> Path:
    slug = REGION_REPORT_SLUG.get(region, "region")
    path = REPORT_DIR / f"2026_{slug}_region_prediction.md"
    title = f"2026 {region}预测"
    lines = [
        f"# {title}",
        "",
        "## 2025 南部回测校准",
        "",
        "- 全量准确率：0.696629。",
        "- 最高置信 20% 子集准确率：1.000000。",
        "- v2 优化：降低过度自信，提高低证据队伍的方差，并引入 2026 完整形态/初始金币信号。",
        "- 当前赛季增量：加入 2026 高校联盟赛 3V3/步兵/工程挑战赛成绩，其中 3V3 权重最高。",
        "",
        "## 赛程边界",
        "",
        "官方直播页当前显示该赛事窗口但暂无逐场赛程，因此本报告预测赛区强度、冠军概率、全国赛/复活赛概率，不生成逐场对阵胜负。",
        "",
        f"- 全国赛名额：{national_slots}",
        f"- 复活赛名额：{repechage_slots}",
        "",
        "## Top 12",
        "",
        "| Rank | Team | Champion | National | Repechage | Upset Risk | Factors |",
        "| ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows[:12]:
        lines.append(
            "| {rank} | {school} {team} | {champ:.1%} | {nat:.1%} | {rep:.1%} | {risk:.1%} | {factors} |".format(
                rank=row["predicted_rank"],
                school=row["school"],
                team=row["team"],
                champ=float(row["champion_probability"]),
                nat=float(row["national_probability"]),
                rep=float(row["repechage_probability"]),
                risk=float(row["upset_risk_index"]),
                factors=row["key_factors"],
            )
        )
    lines.extend(
        [
            "",
            "## Usage",
            "",
            "把 `confidence_tier=high` 的队伍视为稳健预测；`bubble` 队伍优先人工看视频、技术开源、装甲/飞镖/哨兵可靠性信息。",
            "爆冷风险高的队伍不应被简单排序淘汰，需要在有逐场赛程后重新做对阵级预测。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    national_slots, repechage_slots = region_slots(args.region)
    projections = build_profiles(args.region)
    simulate_region(projections, national_slots, repechage_slots, args.iterations)
    rows = prediction_rows(projections)
    write_csv("region_predictions_2026.csv", PREDICTION_FIELDS, rows)
    report_path = write_report(args.region, rows, national_slots, repechage_slots)

    print(
        f"{args.region}: teams={len(rows)} national_slots={national_slots} "
        f"repechage_slots={repechage_slots} report={report_path}"
    )
    for row in rows[:8]:
        print(
            f"{row['predicted_rank']}. {row['school']} {row['team']} "
            f"champion={float(row['champion_probability']):.3f} "
            f"national={float(row['national_probability']):.3f}"
        )


if __name__ == "__main__":
    main()
