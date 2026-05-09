#!/usr/bin/env python3
"""Backtest a strict pre-event model on one RoboMaster 2025 regional split."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backtest_2025_south import (
    BACKTEST_FIELDS,
    MATCH_FIELDS,
    MATCH_SOURCE_ID,
    MATCH_SOURCE_URL,
    PREDICTION_FIELDS,
    RATING_FIELDS,
    build_rating_rows,
    build_strength_profiles,
    decode_related_sheet,
    display_team,
    int_cell,
    predict_match,
    summarize_backtest,
    write_csv,
)


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"


@dataclass(frozen=True)
class RegionConfig:
    region: str
    slug: str
    feature_cutoff: str
    model_run_id: str
    backtest_id: str
    split_name: str
    markers: tuple[str, ...]
    min_rows: int = 80


REGION_CONFIGS = {
    "中部赛区": RegionConfig(
        region="中部赛区",
        slug="central",
        feature_cutoff="2025-05-20",
        model_run_id="rmuc_2025_central_pre_event_v1",
        backtest_id="backtest_2025_central_pre_event",
        split_name="2025_central_regional_pre_event_cutoff",
        markers=("中国科学技术大学", "RoboWalker", "西北工业大学", "冠军争夺战"),
    ),
}


def locate_region_rows(
    rows: dict[int, dict[int, Any]], config: RegionConfig
) -> tuple[int, int]:
    run_start: int | None = None
    previous_region: Any = None
    candidates: list[tuple[int, int]] = []

    for row_index in range(1, max(rows) + 2):
        region = rows.get(row_index, {}).get(2)
        if region != previous_region:
            if previous_region == config.region and run_start is not None:
                candidates.append((run_start, row_index - 1))
            run_start = row_index
            previous_region = region

    for start, end in candidates:
        row_text = "\n".join(
            " ".join(str(rows[row].get(col, "")) for col in range(3, 11))
            for row in range(start, end + 1)
        )
        if end - start + 1 >= config.min_rows and all(
            marker in row_text for marker in config.markers
        ):
            return start, end

    raise ValueError(f"could not locate 2025 {config.region} rows in Tencent sheet")


def extract_matches(config: RegionConfig) -> list[dict[str, str]]:
    rows = decode_related_sheet()
    start, end = locate_region_rows(rows, config)
    matches: list[dict[str, str]] = []

    for row_index in range(start, end + 1):
        row = rows[row_index]
        red_school = str(row.get(5) or "").strip()
        red_team = str(row.get(6) or "").strip()
        blue_school = str(row.get(7) or "").strip()
        blue_team = str(row.get(8) or "").strip()
        red_score = int_cell(row.get(9))
        blue_score = int_cell(row.get(10))
        team_a = display_team(red_school, red_team)
        team_b = display_team(blue_school, blue_team)

        if red_score == blue_score:
            continue

        winner = team_a if red_score > blue_score else team_b
        match_no = str(int_cell(row.get(3)))
        notes = (
            f"tencent_sheet_row={row_index};label_source_post_event=2025-06-05;"
            f"feature_cutoff={config.feature_cutoff};red_school={red_school};"
            f"red_team={red_team};blue_school={blue_school};blue_team={blue_team}"
        )
        matches.append(
            {
                "match_id": f"rmuc_2025_{config.slug}_{match_no.zfill(3)}",
                "year": "2025",
                "stage": "区域赛",
                "region": config.region,
                "round": str(row.get(4) or ""),
                "match_no": match_no,
                "team_a": team_a,
                "team_b": team_b,
                "winner": winner,
                "score_a": str(red_score),
                "score_b": str(blue_score),
                "source_url": MATCH_SOURCE_URL,
                "confidence": "0.78",
                "source_id": MATCH_SOURCE_ID,
                "notes": notes,
            }
        )
    return matches


def clean_prediction_rows(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in row.items() if not key.startswith("_")}
        for row in predictions
    ]


def top_rows(
    predictions: list[dict[str, Any]], correct_value: str, limit: int
) -> list[dict[str, Any]]:
    rows = [row for row in predictions if row["correct"] == correct_value]
    return sorted(rows, key=lambda row: float(row["confidence"]), reverse=True)[:limit]


def render_report(
    config: RegionConfig,
    matches: list[dict[str, str]],
    predictions: list[dict[str, Any]],
    summary: dict[str, str],
) -> str:
    high_conf = [row for row in predictions if float(row["confidence"]) >= 0.70]
    high_conf_errors = [row for row in high_conf if row["correct"] != "1"]
    upset_rows = sorted(
        predictions,
        key=lambda row: float(row["upset_risk_index"]),
        reverse=True,
    )[:8]

    lines = [
        f"# 2025 {config.region} 严格赛前特征回测",
        "",
        f"- 样本：{len(matches)} 场有明确胜负的逐场结果",
        f"- 特征截止日：{config.feature_cutoff}",
        f"- 准确率：{float(summary['accuracy']) * 100:.2f}%",
        f"- 高置信前 20% 准确率：{float(summary['accuracy_top_confidence_20pct']) * 100:.2f}%",
        f"- Brier：{summary['brier']}",
        f"- Log loss：{summary['log_loss']}",
        f"- 置信度 >= 70% 的错误率：{float(summary['high_confidence_error_rate']) * 100:.2f}%",
        f"- 置信度 >= 70% 样本数：{len(high_conf)}，其中错判 {len(high_conf_errors)} 场",
        "",
        "## 数据边界",
        "",
        "- 标签来自赛后逐场比分表，只用于回测判定。",
        "- 特征只使用 2023-2024 历史结果、2025 赛前完整形态/初始金币信号、2025 前技术奖项。",
        "- 不使用 2025 中部赛区本身或后续分区赛逐场结果作为特征。",
        "",
        "## 高置信错判",
        "",
    ]

    errors = top_rows(predictions, "0", 8)
    if errors:
        for row in errors:
            lines.append(
                "- "
                f"{row['team_a']} vs {row['team_b']}，预测 {row['predicted_winner']}，"
                f"实际 {row['actual_winner']}，置信度 {float(row['confidence']) * 100:.2f}%，"
                f"爆冷风险 {float(row['upset_risk_index']) * 100:.2f}%"
            )
    else:
        lines.append("- 无")

    lines.extend(["", "## 最高爆冷风险样本", ""])
    for row in upset_rows:
        lines.append(
            "- "
            f"{row['team_a']} vs {row['team_b']}，预测 {row['predicted_winner']}，"
            f"实际 {row['actual_winner']}，置信度 {float(row['confidence']) * 100:.2f}%，"
            f"爆冷风险 {float(row['upset_risk_index']) * 100:.2f}%"
        )

    return "\n".join(lines) + "\n"


def run_backtest(config: RegionConfig) -> dict[str, str]:
    matches = extract_matches(config)
    exact_profiles, school_profiles = build_strength_profiles()
    predictions = [
        predict_match(
            match,
            exact_profiles,
            school_profiles,
            model_run_id=config.model_run_id,
            feature_cutoff=config.feature_cutoff,
        )
        for match in matches
    ]
    rating_rows = build_rating_rows(
        matches,
        exact_profiles,
        school_profiles,
        model_run_id=config.model_run_id,
        feature_cutoff=config.feature_cutoff,
    )
    summary = summarize_backtest(
        predictions,
        backtest_id=config.backtest_id,
        model_run_id=config.model_run_id,
        split_name=config.split_name,
        feature_cutoff=config.feature_cutoff,
        strict_note="strict_no_2025_regional_match_results_features",
    )

    suffix = f"2025_{config.slug}"
    write_csv(f"match_results_{suffix}.csv", MATCH_FIELDS, matches)
    write_csv(f"model_predictions_{suffix}.csv", PREDICTION_FIELDS, clean_prediction_rows(predictions))
    write_csv(f"team_strength_ratings_{suffix}.csv", RATING_FIELDS, rating_rows)
    write_csv(f"model_backtests_{suffix}.csv", BACKTEST_FIELDS, [summary])

    REPORTS_DIR.mkdir(exist_ok=True)
    report = render_report(config, matches, predictions, summary)
    (REPORTS_DIR / f"2025_{config.slug}_backtest.md").write_text(report, encoding="utf-8")

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--region",
        required=True,
        choices=sorted(REGION_CONFIGS),
        help="2025 regional split to backtest",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = REGION_CONFIGS[args.region]
    summary = run_backtest(config)
    print(
        f"2025 {config.region} backtest: "
        f"n={summary['n_matches']} accuracy={summary['accuracy']} "
        f"top20={summary['accuracy_top_confidence_20pct']} "
        f"brier={summary['brier']} log_loss={summary['log_loss']}"
    )


if __name__ == "__main__":
    main()
