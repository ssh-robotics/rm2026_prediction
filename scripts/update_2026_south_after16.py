#!/usr/bin/env python3
"""Build live rolling outputs after the first 16 South regional matches."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"

MODEL_RUN_ID = "rmuc_2026_south_after16_live_v1"
SOURCE_ID = "official_live_schedule_json"
EVENT = "RMUC 2026超级对抗赛"
ZONE = "南部赛区"
DATE_CST = "2026-05-13"

SCHEDULE_PATH = DATA_DIR / "live_schedule.json"
GROUP_RANK_PATH = DATA_DIR / "live_group_rank_info.json"
ROBOT_DATA_PATH = DATA_DIR / "live_robot_data.json"
PRE_PREDICTIONS_PATH = DATA_DIR / "model_predictions_2026_south_day1.csv"
REGION_RATINGS_PATH = DATA_DIR / "region_predictions_2026.csv"

LIVE_MATCH_EVENTS_PATH = DATA_DIR / "live_match_events_2026_south_after16.csv"
LIVE_ROBOT_STATS_PATH = DATA_DIR / "live_robot_key_stats_2026_south_after16.csv"
LIVE_TEAM_RATINGS_PATH = DATA_DIR / "live_team_ratings_2026_south_after16.csv"
LIVE_PREDICTIONS_PATH = DATA_DIR / "live_model_predictions_2026_south_after16.csv"
LIVE_BACKTEST_PATH = DATA_DIR / "live_model_backtests_2026_south_after16.csv"
REPORT_PATH = REPORT_DIR / "2026_south_after16_live_update.md"

TZ_CST = timezone(timedelta(hours=8))


@dataclass
class Rating:
    school: str
    team: str
    pre_mu: float
    sigma: float
    pre_rank: int
    event_upset_risk: float


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def team_display(school: str, team: str) -> str:
    return f"{school} {team}".strip()


def parse_team(player: dict[str, Any]) -> tuple[str, str, str]:
    team = player.get("team") or {}
    return team.get("id", ""), team.get("collegeName", ""), team.get("name", "")


def format_time_cst(iso_time: str) -> str:
    dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00")).astimezone(TZ_CST)
    return dt.strftime("%Y-%m-%d %H:%M")


def sigmoid(value: float) -> float:
    value = max(-35.0, min(35.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def stage_variance(match_status: str = "GROUP") -> float:
    return 0.72 if match_status == "GROUP" else 0.55


def calibrated_probability(
    rating_a: float,
    rating_b: float,
    sigma_a: float,
    sigma_b: float,
    risk_a: float,
    risk_b: float,
) -> tuple[float, float]:
    rating_diff = rating_a - rating_b
    raw_probability = sigmoid(rating_diff / 92.0)
    uncertainty = min(1.0, (sigma_a + sigma_b) / 300.0)
    close_rating = math.exp(-abs(rating_diff) / 105.0)
    event_risk = (risk_a + risk_b) / 2.0
    upset_risk = min(
        1.0,
        max(
            0.0,
            0.36 * close_rating
            + 0.22 * uncertainty
            + 0.22 * event_risk
            + 0.20 * stage_variance(),
        ),
    )
    shrink = 0.08 + 0.33 * upset_risk
    probability = 0.5 + (raw_probability - 0.5) * (1.0 - shrink)
    max_confidence = 0.93 - 0.18 * upset_risk
    probability = min(max_confidence, max(1.0 - max_confidence, probability))
    return probability, upset_risk


def load_ratings() -> dict[tuple[str, str], Rating]:
    ratings: dict[tuple[str, str], Rating] = {}
    for row in load_csv(REGION_RATINGS_PATH):
        if row["region"] != ZONE:
            continue
        key = (row["school"], row["team"])
        ratings[key] = Rating(
            school=row["school"],
            team=row["team"],
            pre_mu=float(row["rating_mu"]),
            sigma=float(row["rating_sigma"]),
            pre_rank=int(row["predicted_rank"]),
            event_upset_risk=float(row["upset_risk_index"]),
        )
    return ratings


def load_pre_predictions() -> dict[str, dict[str, str]]:
    return {row["match_id"]: row for row in load_csv(PRE_PREDICTIONS_PATH)}


def load_south_matches() -> tuple[dict[str, str], list[dict[str, Any]]]:
    obj = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))["data"]
    zone = next(z for z in obj["event"]["zones"]["nodes"] if z["name"] == ZONE)
    groups = {group["id"]: group["name"] for group in zone["groups"]["nodes"]}
    matches: list[dict[str, Any]] = []
    for match in zone["groupMatches"]["nodes"]:
        if not match.get("planStartedAt"):
            continue
        if not format_time_cst(match["planStartedAt"]).startswith(DATE_CST):
            continue
        red_player = (match.get("redSide") or {}).get("player")
        blue_player = (match.get("blueSide") or {}).get("player")
        if not red_player or not blue_player:
            continue
        red_id, red_school, red_team = parse_team(red_player)
        blue_id, blue_school, blue_team = parse_team(blue_player)
        matches.append(
            {
                "match_id": match["id"],
                "order_number": int(match["orderNumber"]),
                "time": format_time_cst(match["planStartedAt"]),
                "group": groups.get(match["groupId"], ""),
                "status": match["status"],
                "result": match["result"],
                "red_id": red_id,
                "red_school": red_school,
                "red_team": red_team,
                "blue_id": blue_id,
                "blue_school": blue_school,
                "blue_team": blue_team,
                "red_display": team_display(red_school, red_team),
                "blue_display": team_display(blue_school, blue_team),
                "red_game_wins": int(match["redSideWinGameCount"]),
                "blue_game_wins": int(match["blueSideWinGameCount"]),
            }
        )
    return groups, sorted(matches, key=lambda row: row["order_number"])


def item_value(items: list[dict[str, Any]], name: str) -> Any:
    for item in items:
        if item.get("itemName") == name:
            return item.get("itemValue")
    return ""


def load_group_stats() -> dict[tuple[str, str], dict[str, Any]]:
    obj = json.loads(GROUP_RANK_PATH.read_text(encoding="utf-8"))
    stats: dict[tuple[str, str], dict[str, Any]] = {}
    for zone in obj["zones"]:
        if zone["zoneName"] != ZONE:
            continue
        for group in zone["groups"]:
            for rank_index, items in enumerate(group["groupPlayers"], start=1):
                team_info = item_value(items, "战队")
                if not isinstance(team_info, dict):
                    continue
                school = team_info.get("collegeName", "")
                team = team_info.get("teamName", "")
                wdl = str(item_value(items, "胜/平/负"))
                wins, draws, losses = [int(part) for part in wdl.split("/")]
                stats[(school, team)] = {
                    "group": group["groupName"].replace("组", ""),
                    "official_rank": rank_index,
                    "wdl": wdl,
                    "wins": wins,
                    "draws": draws,
                    "losses": losses,
                    "opponent_score": float(item_value(items, "对手分") or 0),
                    "avg_base_hp_diff": float(item_value(items, "时均总基地净胜血量") or 0),
                    "avg_team_damage": float(item_value(items, "时均全队总伤害血量") or 0),
                }
    return stats


def zscores(values: dict[tuple[str, str], float]) -> dict[tuple[str, str], float]:
    if not values:
        return {}
    vals = list(values.values())
    center = mean(vals)
    spread = pstdev(vals) or 1.0
    return {key: (value - center) / spread for key, value in values.items()}


def load_robot_stats() -> dict[tuple[str, str], dict[str, Any]]:
    obj = json.loads(ROBOT_DATA_PATH.read_text(encoding="utf-8"))
    zone = next(z for z in obj["zones"] if z["zoneName"] == ZONE)
    raw: dict[tuple[str, str], dict[str, Any]] = {}
    metric_for_signal: dict[str, dict[tuple[str, str], float]] = defaultdict(dict)

    for team in zone["teams"]:
        key = (team["collegeName"], team["name"])
        robots = team.get("robots") or []
        infantry = [r for r in robots if r.get("type") == "Infantry"]
        heroes = [r for r in robots if r.get("type") == "Hero"]
        combat_damage = sum(float(r.get("gkDamage") or 0.0) for r in robots)
        combat_hurt = sum(float(r.get("eagHurt") or 0.0) for r in robots)
        kills = sum(float(r.get("gKillCount") or 0.0) for r in robots)
        avg_small_hit = mean([float(r.get("eaSmallHitRate") or 0.0) for r in robots]) if robots else 0.0
        infantry_small_hit = (
            mean([float(r.get("eaSmallHitRate") or 0.0) for r in infantry])
            if infantry
            else 0.0
        )
        hero_big_hit = (
            mean([float(r.get("eaBigHitRate") or 0.0) for r in heroes])
            if heroes
            else 0.0
        )
        hero_kills = sum(float(r.get("gKillCount") or 0.0) for r in heroes)
        engineer_econ = sum(
            float(r.get("eaExchangeEcon") or 0.0)
            + float(r.get("eaAssembleEcon") or 0.0)
            + float(r.get("avgMineDiff") or 0.0)
            for r in robots
        )
        dart_hits = sum(
            float(r.get(metric) or 0.0)
            for r in robots
            for metric in (
                "etDartOutpostCnt",
                "etDartFixedCnt",
                "etDartRDFixCnt",
                "etDartRDMoveCnt",
                "etDartEndMoveCnt",
            )
        )
        radar_signal = sum(
            float(r.get("eaRadarDebuffDmg") or 0.0)
            + float(r.get("eaRadarMarkerTime") or 0.0) / 10.0
            + float(r.get("eaRadarParseSuccCnt") or 0.0) * 10.0
            for r in robots
        )
        raw[key] = {
            "team_id": team["id"],
            "school": team["collegeName"],
            "team": team["name"],
            "combat_damage": combat_damage,
            "combat_hurt_metric": combat_hurt,
            "kills": kills,
            "avg_small_hit_rate": avg_small_hit,
            "infantry_small_hit_rate": infantry_small_hit,
            "hero_big_hit_rate": hero_big_hit,
            "hero_kills": hero_kills,
            "engineer_econ": engineer_econ,
            "dart_hits": dart_hits,
            "radar_signal": radar_signal,
        }
        metric_for_signal["combat_damage"][key] = combat_damage
        metric_for_signal["combat_hurt_metric"][key] = combat_hurt
        metric_for_signal["kills"][key] = kills
        metric_for_signal["avg_small_hit_rate"][key] = avg_small_hit
        metric_for_signal["engineer_econ"][key] = engineer_econ
        metric_for_signal["dart_hits"][key] = dart_hits
        metric_for_signal["radar_signal"][key] = radar_signal

    z = {name: zscores(values) for name, values in metric_for_signal.items()}
    for key, row in raw.items():
        row["robot_signal_score"] = (
            0.26 * z["combat_damage"][key]
            + 0.20 * z["combat_hurt_metric"][key]
            + 0.18 * z["kills"][key]
            + 0.14 * z["avg_small_hit_rate"][key]
            + 0.12 * z["engineer_econ"][key]
            + 0.06 * z["dart_hits"][key]
            + 0.04 * z["radar_signal"][key]
        )
    ranks = sorted(raw, key=lambda key: raw[key]["robot_signal_score"], reverse=True)
    for index, key in enumerate(ranks, start=1):
        raw[key]["robot_signal_rank"] = index
    return raw


def evaluate_completed_matches(
    matches: list[dict[str, Any]],
    ratings: dict[tuple[str, str], Rating],
    pre_predictions: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], float], dict[str, float]]:
    events: list[dict[str, Any]] = []
    match_deltas: dict[tuple[str, str], float] = defaultdict(float)
    brier_sum = 0.0
    log_loss_sum = 0.0
    scored_predictions: list[dict[str, Any]] = []

    for match in matches:
        if match["status"] != "DONE" or match["order_number"] > 16:
            continue
        winner_side = "red" if match["result"] == "RED" else "blue"
        winner = match["red_display"] if winner_side == "red" else match["blue_display"]
        pre = pre_predictions[match["match_id"]]
        correct = pre["predicted_winner"] == winner
        p_red = float(pre["p_red_win"])
        actual_red = 1.0 if winner_side == "red" else 0.0
        brier_sum += (p_red - actual_red) ** 2
        p = min(1.0 - 1e-6, max(1e-6, p_red))
        log_loss_sum += -(actual_red * math.log(p) + (1.0 - actual_red) * math.log(1.0 - p))
        scored_predictions.append({**pre, "correct": correct})

        margin = abs(match["red_game_wins"] - match["blue_game_wins"])
        margin_factor = 1.0 + 0.2 * max(0, margin - 1)
        delta = 85.0 * (actual_red - p_red) * margin_factor
        red_key = (match["red_school"], match["red_team"])
        blue_key = (match["blue_school"], match["blue_team"])
        match_deltas[red_key] += delta
        match_deltas[blue_key] -= delta

        events.append(
            {
                "match_id": match["match_id"],
                "event": EVENT,
                "zone": ZONE,
                "match_time_cst": match["time"],
                "group_name": match["group"],
                "red_team": match["red_display"],
                "blue_team": match["blue_display"],
                "red_game_wins": match["red_game_wins"],
                "blue_game_wins": match["blue_game_wins"],
                "winner": winner,
                "pre_predicted_winner": pre["predicted_winner"],
                "pre_confidence": pre["confidence"],
                "pre_upset_risk_index": pre["upset_risk_index"],
                "correct": "1" if correct else "0",
                "source_id": SOURCE_ID,
                "notes": (
                    f"official_result={match['result']};"
                    f"pre_p_red={p_red:.3f};live_rating_delta={delta:.3f}"
                ),
            }
        )

    n = len(scored_predictions)
    accuracy = sum(1 for row in scored_predictions if row["correct"]) / n
    top_n = max(1, round(n * 0.2))
    top_rows = sorted(scored_predictions, key=lambda row: float(row["confidence"]), reverse=True)[:top_n]
    high_conf_rows = [row for row in scored_predictions if float(row["confidence"]) >= 0.75]
    metrics = {
        "n_matches": n,
        "accuracy": accuracy,
        "accuracy_top_confidence_20pct": sum(1 for row in top_rows if row["correct"]) / top_n,
        "brier": brier_sum / n,
        "log_loss": log_loss_sum / n,
        "high_confidence_error_rate": (
            sum(1 for row in high_conf_rows if not row["correct"]) / len(high_conf_rows)
            if high_conf_rows
            else 0.0
        ),
        "high_confidence_count": len(high_conf_rows),
    }
    return events, match_deltas, metrics


def build_live_ratings(
    ratings: dict[tuple[str, str], Rating],
    group_stats: dict[tuple[str, str], dict[str, Any]],
    robot_stats: dict[tuple[str, str], dict[str, Any]],
    match_deltas: dict[tuple[str, str], float],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], float], dict[tuple[str, str], float]]:
    rows: list[dict[str, Any]] = []
    live_mu: dict[tuple[str, str], float] = {}
    live_sigma: dict[tuple[str, str], float] = {}

    for key, rating in ratings.items():
        group = group_stats.get(key, {})
        robot = robot_stats.get(key, {})
        official_rank = int(group.get("official_rank", 16))
        group_delta = (8.5 - official_rank) * 2.5
        group_delta += 2.5 * float(group.get("avg_base_hp_diff", 0.0))
        group_delta += 0.9 * float(group.get("avg_team_damage", 0.0))
        group_delta = max(-55.0, min(65.0, group_delta))
        robot_delta = max(-25.0, min(30.0, 16.0 * float(robot.get("robot_signal_score", 0.0))))
        match_delta = match_deltas.get(key, 0.0)
        live_rating = rating.pre_mu + match_delta + group_delta + robot_delta
        sigma = max(55.0, rating.sigma * 0.92 if key in group_stats else rating.sigma)
        live_mu[key] = live_rating
        live_sigma[key] = sigma
        rows.append(
            {
                "rating_id": f"rating_{MODEL_RUN_ID}_{len(rows) + 1:03d}",
                "model_run_id": MODEL_RUN_ID,
                "school": key[0],
                "team": key[1],
                "group_name": group.get("group", ""),
                "pre_rating_mu": f"{rating.pre_mu:.3f}",
                "live_rating_mu": f"{live_rating:.3f}",
                "delta_match_result": f"{match_delta:.3f}",
                "delta_group_rank": f"{group_delta:.3f}",
                "delta_robot_signal": f"{robot_delta:.3f}",
                "rating_sigma": f"{sigma:.3f}",
                "official_group_rank": group.get("official_rank", ""),
                "group_wdl": group.get("wdl", ""),
                "source_id": SOURCE_ID,
                "notes": (
                    "live_after_first_16_matches;"
                    "update=pre_rating+match_delta+group_rank_delta+robot_signal_delta"
                ),
            }
        )
    rows.sort(key=lambda row: float(row["live_rating_mu"]), reverse=True)
    return rows, live_mu, live_sigma


def build_robot_rows(
    robot_stats: dict[tuple[str, str], dict[str, Any]],
    group_stats: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, robot in sorted(
        robot_stats.items(), key=lambda item: item[1]["robot_signal_score"], reverse=True
    ):
        group = group_stats.get(key, {})
        rows.append(
            {
                "team_id": robot["team_id"],
                "school": key[0],
                "team": key[1],
                "group_name": group.get("group", ""),
                "official_group_rank": group.get("official_rank", ""),
                "group_wdl": group.get("wdl", ""),
                "group_wins": group.get("wins", ""),
                "group_losses": group.get("losses", ""),
                "opponent_score": group.get("opponent_score", ""),
                "avg_base_hp_diff": group.get("avg_base_hp_diff", ""),
                "avg_team_damage": group.get("avg_team_damage", ""),
                "robot_signal_score": f"{robot['robot_signal_score']:.6f}",
                "robot_signal_rank": robot["robot_signal_rank"],
                "combat_damage": f"{robot['combat_damage']:.3f}",
                "combat_hurt_metric": f"{robot['combat_hurt_metric']:.3f}",
                "kills": f"{robot['kills']:.3f}",
                "avg_small_hit_rate": f"{robot['avg_small_hit_rate']:.3f}",
                "infantry_small_hit_rate": f"{robot['infantry_small_hit_rate']:.3f}",
                "hero_big_hit_rate": f"{robot['hero_big_hit_rate']:.3f}",
                "hero_kills": f"{robot['hero_kills']:.3f}",
                "engineer_econ": f"{robot['engineer_econ']:.3f}",
                "dart_hits": f"{robot['dart_hits']:.3f}",
                "radar_signal": f"{robot['radar_signal']:.3f}",
                "source_id": "official_live_robot_data_json",
                "notes": "robot_signal_score=zscore_weighted_combat_econ_dart_radar",
            }
        )
    return rows


def build_rolling_predictions(
    matches: list[dict[str, Any]],
    ratings: dict[tuple[str, str], Rating],
    live_mu: dict[tuple[str, str], float],
    live_sigma: dict[tuple[str, str], float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for match in matches:
        if match["status"] == "DONE" or match["order_number"] <= 16:
            continue
        red_key = (match["red_school"], match["red_team"])
        blue_key = (match["blue_school"], match["blue_team"])
        red_rating = ratings[red_key]
        blue_rating = ratings[blue_key]
        p_red, upset = calibrated_probability(
            live_mu[red_key],
            live_mu[blue_key],
            live_sigma[red_key],
            live_sigma[blue_key],
            red_rating.event_upset_risk,
            blue_rating.event_upset_risk,
        )
        p_blue = 1.0 - p_red
        predicted_winner = match["red_display"] if p_red >= 0.5 else match["blue_display"]
        confidence = max(p_red, p_blue)
        rows.append(
            {
                "prediction_id": f"pred_{MODEL_RUN_ID}_{match['match_id']}",
                "model_run_id": MODEL_RUN_ID,
                "match_id": match["match_id"],
                "prediction_created_at": created_at,
                "data_cutoff": "2026-05-13T18:30:00+08:00",
                "event": EVENT,
                "zone": ZONE,
                "match_time_cst": match["time"],
                "group_name": match["group"],
                "red_team": match["red_display"],
                "blue_team": match["blue_display"],
                "p_red_win": f"{p_red:.6f}",
                "p_blue_win": f"{p_blue:.6f}",
                "predicted_winner": predicted_winner,
                "confidence": f"{confidence:.6f}",
                "upset_risk_index": f"{upset:.6f}",
                "status": "rolling_after16",
                "source_id": SOURCE_ID,
                "notes": (
                    f"pre_red_mu={red_rating.pre_mu:.3f};live_red_mu={live_mu[red_key]:.3f};"
                    f"pre_blue_mu={blue_rating.pre_mu:.3f};live_blue_mu={live_mu[blue_key]:.3f};"
                    "uses_completed_matches_30900_30915_only"
                ),
            }
        )
    return rows


def write_report(
    events: list[dict[str, Any]],
    robot_rows: list[dict[str, Any]],
    rating_rows: list[dict[str, Any]],
    prediction_rows: list[dict[str, Any]],
    metrics: dict[str, float],
) -> None:
    misses = [row for row in events if row["correct"] == "0"]
    top_robot = robot_rows[:8]
    top_ratings = rating_rows[:12]
    lines = [
        "# 2026 南部赛区前 16 场赛后滚动更新",
        "",
        "数据时间：2026-05-13 前 16 场结束后",
        f"模型：`{MODEL_RUN_ID}`",
        "",
        "## 赛前预测复盘",
        "",
        f"- 前 16 场命中：{sum(1 for row in events if row['correct'] == '1')}/{len(events)}。",
        f"- 全量准确率：{metrics['accuracy']:.6f}。",
        f"- 最高置信 20% 准确率：{metrics['accuracy_top_confidence_20pct']:.6f}。",
        f"- Brier：{metrics['brier']:.6f}。",
        f"- Log loss：{metrics['log_loss']:.6f}。",
        f"- 置信度 >= 0.75 的错误率：{metrics['high_confidence_error_rate']:.6f}。",
        "",
        "主要失误来自历史强先验在第一轮集中失手，说明 Day 1 需要快速放大赛中信息权重。",
        "",
        "## 预测错误",
        "",
        "| 时间 | 对阵 | 赛前预测 | 实际胜方 | 赛前置信 |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for row in misses:
        lines.append(
            f"| {row['match_time_cst'][11:]} | {row['red_team']} vs {row['blue_team']} | "
            f"{row['pre_predicted_winner']} | {row['winner']} | {float(row['pre_confidence']) * 100:.1f}% |"
        )
    lines.extend(
        [
            "",
            "## 机器人关键数据 Top 8",
            "",
            "| Rank | 队伍 | 机器人信号 | 总伤害 | 总击杀 | 小弹丸命中率 | 工程经济 | 雷达信号 |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in top_robot:
        lines.append(
            f"| {row['robot_signal_rank']} | {row['school']} {row['team']} | "
            f"{float(row['robot_signal_score']):.3f} | {float(row['combat_damage']):.1f} | "
            f"{float(row['kills']):.1f} | {float(row['avg_small_hit_rate']):.1f} | "
            f"{float(row['engineer_econ']):.1f} | {float(row['radar_signal']):.1f} |"
        )
    lines.extend(
        [
            "",
            "## 滚动评级 Top 12",
            "",
            "| Rank | 队伍 | 赛前 rating | 滚动 rating | 结果修正 | 排名/血量/伤害修正 | 机器人修正 |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for index, row in enumerate(top_ratings, start=1):
        lines.append(
            f"| {index} | {row['school']} {row['team']} | {float(row['pre_rating_mu']):.1f} | "
            f"{float(row['live_rating_mu']):.1f} | {float(row['delta_match_result']):+.1f} | "
            f"{float(row['delta_group_rank']):+.1f} | {float(row['delta_robot_signal']):+.1f} |"
        )
    lines.extend(
        [
            "",
            "## 后续 4 场滚动预测",
            "",
            "| 时间 | 对阵 | 预测胜方 | 胜率 | 爆冷风险 |",
            "| --- | --- | --- | ---: | ---: |",
        ]
    )
    for row in prediction_rows:
        lines.append(
            f"| {row['match_time_cst'][11:]} | {row['red_team']} vs {row['blue_team']} | "
            f"{row['predicted_winner']} | {float(row['confidence']) * 100:.1f}% | "
            f"{float(row['upset_risk_index']) * 100:.1f}% |"
        )
    lines.extend(
        [
            "",
            "## 调整原则",
            "",
            "- 严格赛前预测不回写，保留为 `model_predictions_2026_south_day1.csv`。",
            "- live 模型只使用 30900-30915 已完赛结果和官方机器人/小组统计。",
            "- 第一轮高置信失误较多，因此本轮滚动权重高于赛前估计，但仍保留历史 rating 作为底座。",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ratings = load_ratings()
    pre_predictions = load_pre_predictions()
    _, matches = load_south_matches()
    group_stats = load_group_stats()
    robot_stats = load_robot_stats()
    events, match_deltas, metrics = evaluate_completed_matches(matches, ratings, pre_predictions)
    robot_rows = build_robot_rows(robot_stats, group_stats)
    rating_rows, live_mu, live_sigma = build_live_ratings(
        ratings, group_stats, robot_stats, match_deltas
    )
    prediction_rows = build_rolling_predictions(matches, ratings, live_mu, live_sigma)

    write_csv(
        LIVE_MATCH_EVENTS_PATH,
        [
            "match_id",
            "event",
            "zone",
            "match_time_cst",
            "group_name",
            "red_team",
            "blue_team",
            "red_game_wins",
            "blue_game_wins",
            "winner",
            "pre_predicted_winner",
            "pre_confidence",
            "pre_upset_risk_index",
            "correct",
            "source_id",
            "notes",
        ],
        events,
    )
    write_csv(
        LIVE_ROBOT_STATS_PATH,
        [
            "team_id",
            "school",
            "team",
            "group_name",
            "official_group_rank",
            "group_wdl",
            "group_wins",
            "group_losses",
            "opponent_score",
            "avg_base_hp_diff",
            "avg_team_damage",
            "robot_signal_score",
            "robot_signal_rank",
            "combat_damage",
            "combat_hurt_metric",
            "kills",
            "avg_small_hit_rate",
            "infantry_small_hit_rate",
            "hero_big_hit_rate",
            "hero_kills",
            "engineer_econ",
            "dart_hits",
            "radar_signal",
            "source_id",
            "notes",
        ],
        robot_rows,
    )
    write_csv(
        LIVE_TEAM_RATINGS_PATH,
        [
            "rating_id",
            "model_run_id",
            "school",
            "team",
            "group_name",
            "pre_rating_mu",
            "live_rating_mu",
            "delta_match_result",
            "delta_group_rank",
            "delta_robot_signal",
            "rating_sigma",
            "official_group_rank",
            "group_wdl",
            "source_id",
            "notes",
        ],
        rating_rows,
    )
    write_csv(
        LIVE_PREDICTIONS_PATH,
        [
            "prediction_id",
            "model_run_id",
            "match_id",
            "prediction_created_at",
            "data_cutoff",
            "event",
            "zone",
            "match_time_cst",
            "group_name",
            "red_team",
            "blue_team",
            "p_red_win",
            "p_blue_win",
            "predicted_winner",
            "confidence",
            "upset_risk_index",
            "status",
            "source_id",
            "notes",
        ],
        prediction_rows,
    )
    write_csv(
        LIVE_BACKTEST_PATH,
        [
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
        ],
        [
            {
                "backtest_id": "backtest_2026_south_day1_after16_pre_match",
                "model_run_id": "rmuc_2026_south_day1_pre_match_v1",
                "split_name": "2026_south_day1_first_16_pre_match",
                "n_matches": int(metrics["n_matches"]),
                "coverage": "1.000000",
                "accuracy": f"{metrics['accuracy']:.6f}",
                "accuracy_top_confidence_20pct": f"{metrics['accuracy_top_confidence_20pct']:.6f}",
                "brier": f"{metrics['brier']:.6f}",
                "log_loss": f"{metrics['log_loss']:.6f}",
                "high_confidence_error_rate": f"{metrics['high_confidence_error_rate']:.6f}",
                "source_id": SOURCE_ID,
                "notes": (
                    "evaluated_after_first_16_matches;"
                    f"high_confidence_count={int(metrics['high_confidence_count'])}"
                ),
            }
        ],
    )
    write_report(events, robot_rows, rating_rows, prediction_rows, metrics)
    print(f"events={len(events)}")
    print(f"robot_stats={len(robot_rows)}")
    print(f"ratings={len(rating_rows)}")
    print(f"rolling_predictions={len(prediction_rows)}")
    print(f"accuracy={metrics['accuracy']:.6f}")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
