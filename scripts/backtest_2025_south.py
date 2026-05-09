#!/usr/bin/env python3
"""Backtest a pre-event RoboMaster 2025 South regional win model."""

from __future__ import annotations

import base64
import csv
import json
import math
import re
import zlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RELATED_SHEET_JSON = DATA_DIR / "tencent_get_sheet_bb08j6_all.json"
FEATURE_CUTOFF = "2025-05-15"
MODEL_RUN_ID = "rmuc_2025_south_pre_event_v1"
BACKTEST_ID = "backtest_2025_south_pre_event"
MATCH_SOURCE_ID = "rm_community_results_2015_2025"
MODEL_SOURCE_ID = "model_design_internal"
MATCH_SOURCE_URL = "https://bbs.robomaster.com/article/25006"


MATCH_FIELDS = [
    "match_id",
    "year",
    "stage",
    "region",
    "round",
    "match_no",
    "team_a",
    "team_b",
    "winner",
    "score_a",
    "score_b",
    "source_url",
    "confidence",
    "source_id",
    "notes",
]

PREDICTION_FIELDS = [
    "prediction_id",
    "model_run_id",
    "match_id",
    "prediction_created_at",
    "data_cutoff",
    "team_a",
    "team_b",
    "p_team_a_win",
    "p_team_b_win",
    "predicted_winner",
    "confidence",
    "upset_risk_index",
    "actual_winner",
    "correct",
    "source_id",
    "notes",
]

RATING_FIELDS = [
    "rating_id",
    "rating_system",
    "rating_version",
    "school",
    "team",
    "as_of_date",
    "rating_mu",
    "rating_sigma",
    "rating_rd",
    "games_played",
    "source_id",
    "notes",
]

BACKTEST_FIELDS = [
    "backtest_id",
    "model_run_id",
    "split_name",
    "n_matches",
    "coverage",
    "accuracy",
    "accuracy_top_confidence_20pct",
    "brier",
    "log_loss",
    "high_confidence_error_rate",
    "source_id",
    "notes",
]


@dataclass
class CellField:
    field: int
    wire: int
    value: int | None
    data: bytes | None


@dataclass
class StrengthProfile:
    rating: float
    sigma: float
    rd: float
    evidence: int
    source: str


def read_varint(buf: bytes, index: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        byte = buf[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, index
        shift += 7


def parse_fields(buf: bytes) -> list[CellField]:
    fields: list[CellField] = []
    index = 0
    while index < len(buf):
        key, index = read_varint(buf, index)
        field = key >> 3
        wire = key & 7
        if wire == 0:
            value, index = read_varint(buf, index)
            fields.append(CellField(field, wire, value, None))
        elif wire == 1:
            fields.append(CellField(field, wire, None, buf[index : index + 8]))
            index += 8
        elif wire == 2:
            length, index = read_varint(buf, index)
            fields.append(CellField(field, wire, length, buf[index : index + length]))
            index += length
        elif wire == 5:
            fields.append(CellField(field, wire, None, buf[index : index + 4]))
            index += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
    return fields


def decode_related_sheet(path: Path = RELATED_SHEET_JSON) -> dict[int, dict[int, Any]]:
    payload_json = json.loads(path.read_text(encoding="utf-8"))
    encoded = payload_json["data"]["initialAttributedText"]["text"][0]["related_sheet"]
    decompressed = zlib.decompress(base64.b64decode(encoded))

    root = parse_fields(decompressed)[0].data
    if root is None:
        raise ValueError("related_sheet root is empty")
    inner = parse_fields(root)
    large_sheet_blob = inner[-1].data
    if large_sheet_blob is None:
        raise ValueError("related_sheet payload is empty")
    sheet_fields = parse_fields(parse_fields(large_sheet_blob)[1].data or b"")

    string_blob = next(item.data for item in sheet_fields if item.field == 5 and item.data)
    strings = decode_string_table(string_blob)
    rows: dict[int, dict[int, Any]] = defaultdict(dict)

    for item in sheet_fields:
        if item.field != 6 or item.data is None:
            continue
        row = 0
        col = 0
        value: Any = None
        for sub in parse_fields(item.data):
            if sub.field == 1 and sub.wire == 0:
                row = int(sub.value or 0)
            elif sub.field == 2 and sub.wire == 0:
                col = int(sub.value or 0)
            elif sub.field == 3 and sub.wire == 2 and sub.data is not None:
                value = decode_cell_value(sub.data, strings)
        rows[row][col] = value

    return rows


def decode_string_table(blob: bytes) -> list[str]:
    strings: list[str] = []
    for item in parse_fields(blob):
        if item.field != 1 or item.data is None:
            continue
        text = ""
        for sub in parse_fields(item.data):
            if sub.field == 1 and sub.wire == 2 and sub.data is not None:
                text = sub.data.decode("utf-8", "replace")
        strings.append(text)
    return strings


def decode_cell_value(blob: bytes, strings: list[str]) -> Any:
    value_type: int | None = None
    raw_value: int | None = None
    for item in parse_fields(blob):
        if item.field == 1 and item.wire == 0:
            value_type = item.value
        elif item.field == 2 and item.wire == 2 and item.data is not None:
            nested = parse_fields(item.data)
            if nested and nested[0].wire == 0:
                raw_value = nested[0].value

    if value_type == 4:
        if raw_value is None:
            return ""
        return strings[raw_value] if raw_value < len(strings) else ""
    return raw_value


def normalize_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = value.replace("（", "(").replace("）", ")")
    value = re.sub(r"\s+", "", value)
    return value.strip().lower()


def display_team(school: str, team: str) -> str:
    return f"{school} {team}".strip()


def int_cell(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(value)


def locate_2025_south_rows(rows: dict[int, dict[int, Any]]) -> tuple[int, int]:
    run_start: int | None = None
    previous_region: Any = None
    candidates: list[tuple[int, int]] = []

    max_row = max(rows)
    for row_index in range(1, max_row + 2):
        region = rows.get(row_index, {}).get(2)
        if region != previous_region:
            if previous_region == "南部赛区" and run_start is not None:
                candidates.append((run_start, row_index - 1))
            run_start = row_index
            previous_region = region

    for start, end in candidates:
        row_text = "\n".join(
            " ".join(str(rows[row].get(col, "")) for col in range(3, 11))
            for row in range(start, end + 1)
        )
        has_2025_final = "冠军争夺战" in row_text and "华南农业大学" in row_text and "华南理工大学" in row_text
        has_2025_field = "中国石油大学（华东）" in row_text and "太原理工大学" in row_text
        if has_2025_final and has_2025_field and end - start + 1 >= 80:
            return start, end

    raise ValueError("could not locate 2025 South regional rows in Tencent sheet")


def extract_2025_south_matches() -> list[dict[str, str]]:
    rows = decode_related_sheet()
    start, end = locate_2025_south_rows(rows)
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
        match_id = f"rmuc_2025_south_{match_no.zfill(3)}"
        notes = (
            f"tencent_sheet_row={row_index};label_source_post_event=2025-06-05;"
            f"feature_cutoff={FEATURE_CUTOFF};red_school={red_school};red_team={red_team};"
            f"blue_school={blue_school};blue_team={blue_team}"
        )
        matches.append(
            {
                "match_id": match_id,
                "year": "2025",
                "stage": "区域赛",
                "region": "南部赛区",
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


def read_csv(name: str) -> list[dict[str, str]]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(name: str, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with (DATA_DIR / name).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def add_strength(
    exact: dict[tuple[str, str], float],
    school: dict[str, float],
    evidence: dict[tuple[str, str], int],
    school_evidence: dict[str, int],
    raw_school: str,
    raw_team: str,
    points: float,
) -> None:
    if not raw_school:
        return
    school_key = normalize_text(raw_school)
    team_key = normalize_text(raw_team)
    key = (school_key, team_key)
    exact[key] += points
    school[school_key] += points
    evidence[key] += 1
    school_evidence[school_key] += 1


def finish_points(row: dict[str, str]) -> float:
    stage = row["stage"]
    try:
        order = int(row["finish_order"] or 0)
    except ValueError:
        order = 0

    if stage == "全国赛":
        if order <= 0:
            base = 35
        elif order <= 1:
            base = 185
        elif order <= 2:
            base = 165
        elif order <= 4:
            base = 145
        elif order <= 8:
            base = 115
        elif order <= 16:
            base = 82
        else:
            base = 58
    elif stage == "区域赛":
        if order <= 0:
            base = 18
        elif order <= 1:
            base = 92
        elif order <= 2:
            base = 80
        elif order <= 4:
            base = 66
        elif order <= 8:
            base = 45
        else:
            base = 28
        if row.get("qualification") == "晋级全国赛":
            base += 18
        elif row.get("qualification") == "晋级复活赛":
            base += 8
    else:
        base = 12

    year_weight = {"2023": 0.65, "2024": 1.0}.get(row["year"], 0.0)
    return base * year_weight


def build_strength_profiles() -> tuple[dict[tuple[str, str], StrengthProfile], dict[str, StrengthProfile]]:
    exact: dict[tuple[str, str], float] = defaultdict(float)
    school: dict[str, float] = defaultdict(float)
    evidence: dict[tuple[str, str], int] = defaultdict(int)
    school_evidence: dict[str, int] = defaultdict(int)

    for row in read_csv("historical_competition_results.csv"):
        if row["year"] >= "2025":
            continue
        add_strength(
            exact,
            school,
            evidence,
            school_evidence,
            row["school"],
            row["team"],
            finish_points(row),
        )

    for row in read_csv("historical_preseason_assessments.csv"):
        year = row["year"]
        if year > "2025":
            continue
        try:
            rank = int(row.get("rank") or 0)
        except ValueError:
            rank = 0
        try:
            score = float(row.get("score") or 0)
        except ValueError:
            score = 0.0
        try:
            initial_gold = float(row.get("total_initial_gold_bonus") or 0)
        except ValueError:
            initial_gold = 0.0

        if year == "2025":
            rank_bonus = 0.0
            if "official_sequence_not_score_rank" not in row.get("notes", ""):
                rank_bonus = max(0.0, 36.0 - rank * 0.28)
            points = initial_gold * 0.95 + rank_bonus
        elif year == "2024":
            points = score * 0.10 + initial_gold * 0.20 + max(0.0, 24.0 - rank * 0.18)
        elif year == "2023":
            points = score * 0.055 + initial_gold * 0.10
        else:
            points = 0.0

        add_strength(
            exact,
            school,
            evidence,
            school_evidence,
            row["school"],
            row["team"],
            points,
        )

    for row in read_csv("historical_technical_awards.csv"):
        if row["year"] >= "2025":
            continue
        award_text = f"{row.get('award_category', '')}{row.get('award_name', '')}"
        points = 14.0
        if "技术突破" in award_text or "最佳技术报告" in award_text:
            points = 22.0
        elif "最佳战术" in award_text:
            points = 18.0
        if row["year"] == "2023":
            points *= 0.65
        add_strength(
            exact,
            school,
            evidence,
            school_evidence,
            row["school"],
            row["team"],
            points,
        )

    exact_profiles: dict[tuple[str, str], StrengthProfile] = {}
    for key, points in exact.items():
        count = evidence[key]
        exact_profiles[key] = make_profile(points, count, "exact")

    school_profiles: dict[str, StrengthProfile] = {}
    for key, points in school.items():
        count = school_evidence[key]
        school_profiles[key] = make_profile(points * 0.88, count, "school_fallback")

    return exact_profiles, school_profiles


def make_profile(points: float, evidence_count: int, source: str) -> StrengthProfile:
    rating = 1500.0 + points
    sigma = max(45.0, 165.0 / math.sqrt(evidence_count + 1))
    rd = max(60.0, 260.0 / math.sqrt(evidence_count + 1))
    return StrengthProfile(rating, sigma, rd, evidence_count, source)


def lookup_profile(
    team_display: str,
    exact_profiles: dict[tuple[str, str], StrengthProfile],
    school_profiles: dict[str, StrengthProfile],
) -> tuple[StrengthProfile, str, str]:
    parts = team_display.split(" ", 1)
    raw_school = parts[0]
    raw_team = parts[1] if len(parts) > 1 else ""
    key = (normalize_text(raw_school), normalize_text(raw_team))

    if key in exact_profiles:
        return exact_profiles[key], raw_school, raw_team

    school_key = normalize_text(raw_school)
    if school_key in school_profiles:
        return school_profiles[school_key], raw_school, raw_team

    return StrengthProfile(1500.0, 150.0, 240.0, 0, "missing_default"), raw_school, raw_team


def sigmoid(value: float) -> float:
    value = max(-35.0, min(35.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def stage_variance(round_name: str) -> float:
    if "第" in round_name and "轮" in round_name:
        return 0.72
    if "16进8" in round_name or "8进4" in round_name:
        return 0.45
    if "名额争夺" in round_name:
        return 0.55
    if "半决赛" in round_name:
        return 0.34
    if "冠军" in round_name or "季军" in round_name:
        return 0.25
    return 0.5


def predict_match(
    match: dict[str, str],
    exact_profiles: dict[tuple[str, str], StrengthProfile],
    school_profiles: dict[str, StrengthProfile],
    model_run_id: str = MODEL_RUN_ID,
    feature_cutoff: str = FEATURE_CUTOFF,
) -> dict[str, Any]:
    profile_a, school_a, team_a = lookup_profile(match["team_a"], exact_profiles, school_profiles)
    profile_b, school_b, team_b = lookup_profile(match["team_b"], exact_profiles, school_profiles)

    rating_diff = profile_a.rating - profile_b.rating
    raw_probability = sigmoid(rating_diff / 92.0)
    evidence_total = profile_a.evidence + profile_b.evidence
    data_confidence = min(1.0, evidence_total / 14.0)
    uncertainty = min(1.0, (profile_a.sigma + profile_b.sigma) / 300.0)
    close_rating = math.exp(-abs(rating_diff) / 105.0)
    stage_risk = stage_variance(match["round"])
    upset_risk = min(
        1.0,
        max(
            0.0,
            0.38 * close_rating
            + 0.26 * uncertainty
            + 0.22 * (1.0 - data_confidence)
            + 0.14 * stage_risk,
        ),
    )

    shrink = 0.08 + 0.33 * upset_risk
    probability = 0.5 + (raw_probability - 0.5) * (1.0 - shrink)
    max_confidence = 0.93 - 0.18 * upset_risk
    probability = min(max_confidence, max(1.0 - max_confidence, probability))

    predicted_winner = match["team_a"] if probability >= 0.5 else match["team_b"]
    actual_winner = match["winner"]
    y = 1.0 if actual_winner == match["team_a"] else 0.0
    p = min(1.0 - 1e-6, max(1e-6, probability))
    confidence = max(probability, 1.0 - probability)

    notes = (
        f"feature_cutoff={feature_cutoff};historical_results_year<2025;"
        "preseason_year<=2025_pre_cutoff;technical_awards_year<2025;"
        f"rating_diff={rating_diff:.3f};"
        f"team_a_profile={profile_a.source};team_b_profile={profile_b.source};"
        f"team_a_evidence={profile_a.evidence};team_b_evidence={profile_b.evidence};"
        f"team_a_school={school_a};team_a_team={team_a};"
        f"team_b_school={school_b};team_b_team={team_b}"
    )

    return {
        "prediction_id": f"pred_{match['match_id']}",
        "model_run_id": model_run_id,
        "match_id": match["match_id"],
        "prediction_created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_cutoff": feature_cutoff,
        "team_a": match["team_a"],
        "team_b": match["team_b"],
        "p_team_a_win": f"{probability:.6f}",
        "p_team_b_win": f"{1.0 - probability:.6f}",
        "predicted_winner": predicted_winner,
        "confidence": f"{confidence:.6f}",
        "upset_risk_index": f"{upset_risk:.6f}",
        "actual_winner": actual_winner,
        "correct": "1" if predicted_winner == actual_winner else "0",
        "source_id": MODEL_SOURCE_ID,
        "notes": notes,
        "_brier": (p - y) ** 2,
        "_log_loss": -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p)),
    }


def build_rating_rows(
    matches: list[dict[str, str]],
    exact_profiles: dict[tuple[str, str], StrengthProfile],
    school_profiles: dict[str, StrengthProfile],
    model_run_id: str = MODEL_RUN_ID,
    feature_cutoff: str = FEATURE_CUTOFF,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rating_rows: list[dict[str, Any]] = []

    for match in matches:
        for team_display in (match["team_a"], match["team_b"]):
            if team_display in seen:
                continue
            seen.add(team_display)
            profile, school, team = lookup_profile(team_display, exact_profiles, school_profiles)
            rating_rows.append(
                {
                    "rating_id": f"rating_{model_run_id}_{len(rating_rows) + 1:03d}",
                    "rating_system": "pre_event_prior_with_upset_risk",
                    "rating_version": "v1",
                    "school": school,
                    "team": team,
                    "as_of_date": feature_cutoff,
                    "rating_mu": f"{profile.rating:.3f}",
                    "rating_sigma": f"{profile.sigma:.3f}",
                    "rating_rd": f"{profile.rd:.3f}",
                    "games_played": str(profile.evidence),
                    "source_id": MODEL_SOURCE_ID,
                    "notes": (
                        f"profile_source={profile.source};"
                        "feature_sources=historical_results_year<2025,"
                        "preseason_year<=2025_pre_cutoff,technical_awards_year<2025"
                    ),
                }
            )
    return rating_rows


def summarize_backtest(
    predictions: list[dict[str, Any]],
    backtest_id: str = BACKTEST_ID,
    model_run_id: str = MODEL_RUN_ID,
    split_name: str = "2025_south_regional_pre_event_cutoff",
    feature_cutoff: str = FEATURE_CUTOFF,
    strict_note: str = "strict_no_2025_south_or_later_features",
) -> dict[str, str]:
    n = len(predictions)
    correct = sum(int(row["correct"]) for row in predictions)
    ordered = sorted(predictions, key=lambda row: float(row["confidence"]), reverse=True)
    top_n = max(1, math.ceil(n * 0.20))
    top_correct = sum(int(row["correct"]) for row in ordered[:top_n])
    high_conf = [row for row in predictions if float(row["confidence"]) >= 0.70]
    high_conf_errors = (
        sum(1 for row in high_conf if row["correct"] != "1") / len(high_conf)
        if high_conf
        else 0.0
    )

    return {
        "backtest_id": backtest_id,
        "model_run_id": model_run_id,
        "split_name": split_name,
        "n_matches": str(n),
        "coverage": "1.000000",
        "accuracy": f"{correct / n:.6f}",
        "accuracy_top_confidence_20pct": f"{top_correct / top_n:.6f}",
        "brier": f"{sum(row['_brier'] for row in predictions) / n:.6f}",
        "log_loss": f"{sum(row['_log_loss'] for row in predictions) / n:.6f}",
        "high_confidence_error_rate": f"{high_conf_errors:.6f}",
        "source_id": MODEL_SOURCE_ID,
        "notes": (
            f"feature_cutoff={feature_cutoff};label_source_post_event=2025-06-05;"
            f"{strict_note};community_labels_confidence=0.78"
        ),
    }


def main() -> None:
    matches = extract_2025_south_matches()
    exact_profiles, school_profiles = build_strength_profiles()
    predictions = [
        predict_match(match, exact_profiles, school_profiles) for match in matches
    ]
    clean_predictions = [
        {key: value for key, value in row.items() if not key.startswith("_")}
        for row in predictions
    ]
    rating_rows = build_rating_rows(matches, exact_profiles, school_profiles)
    backtest_rows = [summarize_backtest(predictions)]

    write_csv("match_results.csv", MATCH_FIELDS, matches)
    write_csv("model_predictions.csv", PREDICTION_FIELDS, clean_predictions)
    write_csv("team_strength_ratings.csv", RATING_FIELDS, rating_rows)
    write_csv("model_backtests.csv", BACKTEST_FIELDS, backtest_rows)

    summary = backtest_rows[0]
    print(
        "2025 South backtest: "
        f"n={summary['n_matches']} accuracy={summary['accuracy']} "
        f"top20={summary['accuracy_top_confidence_20pct']} "
        f"brier={summary['brier']} log_loss={summary['log_loss']}"
    )


if __name__ == "__main__":
    main()
