#!/usr/bin/env python3
"""Offline, reproducible lottery combination generator.

This tool does not fetch live rules, predict results, or buy tickets. It only
generates combinations within a user-supplied budget and reports base odds.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

DEFAULT_RESERVATION_URL = "https://lottery-quant-reservations.lee226520.chatgpt.site"

@dataclass(frozen=True)
class Game:
    code: str
    name: str
    price: Decimal
    jackpot_space: int | None
    pick_line: Callable[[random.Random], Any]
    formatter: Callable[[Any], str]
    event_label: str


def choose_unique(rng: random.Random, start: int, end: int, count: int) -> tuple[int, ...]:
    return tuple(sorted(rng.sample(range(start, end + 1), count)))


def score_set(values: tuple[int, ...], upper: int) -> float:
    """Mild anti-pattern score; it is not a probability model."""
    ordered = sorted(values)
    score = 0.0
    low = sum(value <= min(31, upper) for value in ordered)
    score += max(0, len(ordered) - low) * 0.35
    score -= sum(b - a == 1 for a, b in zip(ordered, ordered[1:])) * 1.15
    endings = [value % 10 for value in ordered]
    score -= (len(endings) - len(set(endings))) * 0.35
    if len(ordered) >= 4 and ordered[-1] - ordered[0] == len(ordered) - 1:
        score -= 1.5
    if len(set(value % 2 for value in ordered)) == 1:
        score -= 0.25
    return score


def anti_crowd_pick(
    rng: random.Random,
    sampler: Callable[[random.Random], Any],
    scorer: Callable[[Any], float],
    seen: set[str],
    formatter: Callable[[Any], str],
) -> Any:
    best = None
    best_score = float("-inf")
    for _ in range(96):
        candidate = sampler(rng)
        rendered = formatter(candidate)
        if rendered in seen:
            continue
        candidate_score = scorer(candidate)
        if candidate_score > best_score:
            best, best_score = candidate, candidate_score
    if best is None:
        for _ in range(1000):
            candidate = sampler(rng)
            if formatter(candidate) not in seen:
                return candidate
        raise RuntimeError("Could not generate a distinct combination")
    return best


def fmt_numbers(values: tuple[int, ...], width: int = 2) -> str:
    return " ".join(f"{value:0{width}d}" for value in values)


def fmt_ssq(line: tuple[tuple[int, ...], int]) -> str:
    reds, blue = line
    return f"红：{fmt_numbers(reds)} | 蓝：{blue:02d}"


def fmt_dlt(line: tuple[tuple[int, ...], tuple[int, ...]]) -> str:
    front, back = line
    return f"前：{fmt_numbers(front)} | 后：{fmt_numbers(back)}"


def fmt_7lc(line: tuple[int, ...]) -> str:
    return f"基本号：{fmt_numbers(line)}"


def make_games(kl8_count: int) -> dict[str, Game]:
    def ssq_sampler(rng: random.Random):
        return choose_unique(rng, 1, 33, 6), rng.randint(1, 16)

    def dlt_sampler(rng: random.Random):
        return choose_unique(rng, 1, 35, 5), choose_unique(rng, 1, 12, 2)

    def seven_lottery_sampler(rng: random.Random):
        return choose_unique(rng, 1, 30, 7)

    def kl8_sampler(rng: random.Random):
        return choose_unique(rng, 1, 80, kl8_count)

    def digit_sampler(width: int):
        def sample(rng: random.Random):
            return tuple(rng.randint(0, 9) for _ in range(width))

        return sample

    def seven_star_sampler(rng: random.Random):
        return tuple(rng.randint(0, 9) for _ in range(6)) + (rng.randint(0, 14),)

    return {
        "ssq": Game("ssq", "双色球", Decimal("2"), 17721088, ssq_sampler, fmt_ssq, "一等奖"),
        "dlt": Game("dlt", "超级大乐透", Decimal("2"), 21425712, dlt_sampler, fmt_dlt, "一等奖"),
        "7lc": Game("7lc", "七乐彩", Decimal("2"), 2035800, seven_lottery_sampler, fmt_7lc, "一等奖"),
        "kl8": Game("kl8", "快乐8", Decimal("2"), None, kl8_sampler, lambda x: f"号码：{fmt_numbers(x)}", f"选{kl8_count}全中"),
        "3d": Game("3d", "福彩3D", Decimal("2"), 1000, digit_sampler(3), lambda x: "号码：" + "".join(map(str, x)), "直选"),
        "pl3": Game("pl3", "排列3", Decimal("2"), 1000, digit_sampler(3), lambda x: "号码：" + "".join(map(str, x)), "直选"),
        "pl5": Game("pl5", "排列5", Decimal("2"), 100000, digit_sampler(5), lambda x: "号码：" + "".join(map(str, x)), "一等奖"),
        "7xc": Game("7xc", "7星彩", Decimal("2"), 15000000, seven_star_sampler, lambda x: "前六位：" + "".join(map(str, x[:6])) + f" | 后位：{x[6]:02d}", "一等奖"),
    }


def parse_budget(raw: str) -> Decimal:
    try:
        budget = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("budget must be a positive RMB amount") from exc
    if not budget.is_finite() or budget <= 0:
        raise ValueError("budget must be a positive RMB amount")
    return budget


def choose_auto(profile: str) -> tuple[str, str, int]:
    if profile == "frequency":
        return "kl8", "偏向更频繁的小额命中；不代表更高收益。", 1
    if profile == "tail":
        return "ssq", "偏向低频、高波动的头奖型玩法；不代表更高中奖率。", 6
    return "dlt", "作为默认的乐透型平衡选项；没有实时数据时不宣称存在优势。", 5


def jackpot_probability(game: Game, lines: int) -> float | None:
    if game.jackpot_space is None:
        return None
    return min(1.0, lines / game.jackpot_space)


def probability_summary(game: Game, lines: int) -> dict[str, Any]:
    if game.code == "kl8":
        return {
            "formula": "C(20,n) / C(80,n)",
            "one_line_event": "选定的 n 个号码全部落在当期20个开奖号码中",
            "note": "n 由风险偏好决定；这只是目标事件概率，不是综合中奖概率。",
        }
    assert game.jackpot_space is not None
    one = 1 / game.jackpot_space
    portfolio = min(1.0, lines / game.jackpot_space)
    return {
        "formula": f"1 / {game.jackpot_space:,}；{lines}注覆盖概率 = {lines} / {game.jackpot_space:,}",
        "one_line_probability": one,
        "portfolio_probability": portfolio,
        "one_line_odds": f"1/{game.jackpot_space:,}",
        "portfolio_odds_approx": f"1/{game.jackpot_space / lines:,.2f}",
        "note": "仅针对头奖/直选等精确目标事件；不等于任一奖级中奖概率。",
    }


def build_analysis(
    game: Game,
    budget: Decimal,
    spent: Decimal,
    leftover: Decimal,
    lines: int,
    profile: str,
    auto_reason: str | None,
) -> dict[str, Any]:
    probability = probability_summary(game, lines)
    selection = auto_reason or "用户指定玩法；未替换为历史热冷号或走势预测。"
    return {
        "decision_conclusion": f"在 {budget} 元预算内生成 {lines} 注{game.name}，实际支出 {spent} 元；{selection}",
        "budget_constraint": {
            "requested_rmb": str(budget),
            "spent_rmb": str(spent),
            "leftover_rmb": str(leftover),
            "reason": "只购买完整注数，不为了凑整超出预算。",
        },
        "game_screen": [
            {"label": "精确计算", "statement": f"{game.name}的目标事件为{game.event_label}，组合空间和基本概率按玩法结构计算。"},
            {"label": "模型估计", "statement": "组合采用轻度反人群启发式，目标是降低明显撞号模式，不改变开奖概率。"},
            {"label": "未验证假设", "statement": "本次未接入当期奖池、销量、派奖和真实选号分布，因此没有宣称存在动态优势。"},
        ],
        "probability_calculation": probability,
        "portfolio_strategy": {
            "line_count": lines,
            "duplicate_policy": "尽量生成互不重复的组合",
            "risk_profile": profile,
            "why": "增加覆盖面或改变收益分布，不创造正期望值。",
        },
        "ev_and_tax": {
            "status": "EV_unverified",
            "reason": "缺少当期官方奖金、奖池、促销、共奖人数分布和组合税务情景。",
            "tax_note": "电脑彩票同一人同一期同一游戏的相关奖金需要按适用规则合并判断，不能逐注假设独立免税。",
        },
        "reproducibility": "seed is included in the top-level result; rerunning with the same seed and arguments reproduces the combinations.",
    }


class ReservationClient:
    """Optional shared reservation client for multi-user deployments."""

    def __init__(self, base_url: str, draw_issue: str, game: str, timeout: float = 10.0):
        self.url = base_url.rstrip("/") + "/v1/reservations"
        self.batch_url = base_url.rstrip("/") + "/v1/reservations/batch"
        self.draw_issue = draw_issue
        self.game = game
        self.timeout = timeout

    def _request(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128 Safari/537.36",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                return json.loads(exc.read().decode("utf-8"))
            raise RuntimeError(f"共享去重服务返回 HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"共享去重服务不可用：{exc.reason}") from exc

    def reserve_many(self, combinations: list[str]) -> set[str]:
        result = self._request(self.batch_url, {
            "draw_issue": self.draw_issue,
            "game": self.game,
            "combinations": combinations,
        })
        return set(result.get("reserved_combinations", []))


def generate(game: Game, lines: int, rng: random.Random, reservation: ReservationClient | None = None) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    def sample_candidate() -> str:
        if game.code == "ssq":
            line = anti_crowd_pick(rng, game.pick_line, lambda x: score_set(x[0], 33), seen, game.formatter)
        elif game.code == "dlt":
            line = anti_crowd_pick(rng, game.pick_line, lambda x: score_set(x[0], 35) + score_set(x[1], 12) * 0.5, seen, game.formatter)
        elif game.code in {"7lc", "kl8"}:
            line = anti_crowd_pick(rng, game.pick_line, lambda x: score_set(x, 30 if game.code == "7lc" else 80), seen, game.formatter)
        else:
            line = game.pick_line(rng)
        return game.formatter(line)

    if reservation is None:
        for _ in range(lines):
            for _attempt in range(2000):
                rendered = sample_candidate()
                if rendered in seen:
                    continue
                seen.add(rendered)
                output.append(rendered)
                break
            else:
                raise RuntimeError("Could not generate a distinct combination")
        return output

    for _attempt in range(2000):
        needed = lines - len(output)
        candidates: list[str] = []
        candidate_seen = set(seen)
        for _ in range(max(needed * 2, 8)):
            rendered = sample_candidate()
            if rendered in candidate_seen:
                continue
            candidate_seen.add(rendered)
            candidates.append(rendered)
        accepted = reservation.reserve_many(candidates)
        for rendered in candidates:
            if rendered in accepted:
                seen.add(rendered)
                output.append(rendered)
                if len(output) == lines:
                    return output
    raise RuntimeError("共享去重服务拒绝了过多组合，无法在当前预算内生成足量号码")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate budget-bounded lottery combinations.")
    parser.add_argument("--budget", required=True, help="RMB budget, e.g. 100")
    parser.add_argument("--game", choices=["auto", "ssq", "dlt", "7lc", "kl8", "3d", "pl3", "pl5", "7xc"], default="auto")
    parser.add_argument("--risk-profile", choices=["frequency", "balanced", "tail"], default="balanced")
    parser.add_argument("--seed", type=int, help="Optional reproducibility seed")
    parser.add_argument("--draw-issue", help="Current draw issue used by the optional shared reservation service")
    parser.add_argument("--reservation-url", help="Shared reservation service base URL; defaults to LOTTERY_RESERVATION_URL")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    budget = parse_budget(args.budget)
    auto_reason = None
    kl8_count = 5
    game_code = args.game
    if game_code == "auto":
        game_code, auto_reason, kl8_count = choose_auto(args.risk_profile)
    elif game_code == "kl8":
        kl8_count = {"frequency": 1, "balanced": 5, "tail": 10}[args.risk_profile]
    games = make_games(kl8_count)
    game = games[game_code]
    lines = int(budget // game.price)
    spent = game.price * lines
    leftover = budget - spent
    if lines < 1:
        raise SystemExit(f"预算不足：{game.name}每注需要 {game.price} 元。")

    seed = args.seed if args.seed is not None else secrets.randbits(64)
    rng = random.Random(seed)
    reservation_url = args.reservation_url or os.environ.get("LOTTERY_RESERVATION_URL")
    if args.draw_issue and not reservation_url:
        reservation_url = DEFAULT_RESERVATION_URL
    if reservation_url and not args.draw_issue:
        raise SystemExit("启用共享去重服务时必须提供当前开奖期号 --draw-issue。")
    reservation = ReservationClient(reservation_url, args.draw_issue, game.code) if reservation_url else None
    combinations = generate(game, lines, rng, reservation)
    probability = jackpot_probability(game, lines)
    probability_details = probability_summary(game, lines)
    analysis = build_analysis(game, budget, spent, leftover, lines, args.risk_profile, auto_reason)
    result: dict[str, Any] = {
        "tool": "lottery-quant",
        "mode": "offline_combination_generation",
        "game": {"code": game.code, "name": game.name, "event": game.event_label, "line_price_rmb": str(game.price)},
        "risk_profile": args.risk_profile,
        "budget_rmb": str(budget),
        "spent_rmb": str(spent),
        "leftover_rmb": str(leftover),
        "lines": lines,
        "seed": seed,
        "combinations": combinations,
        "jackpot_probability_for_distinct_lines": probability,
        "analysis": analysis,
        "live_edge_status": "no_live_edge_established",
        "global_uniqueness": "reserved_for_draw_issue" if reservation else "unverified_standalone",
        "assumptions": [
            "号码候选组合均为离线生成；本工具不代替官方规则、奖池、派奖或销量核验。",
            "每个合法组合的开奖概率相同；反人群启发式只可能影响撞号风险，不能提高开奖概率。",
            "未计算实时奖金、共奖人数分布、税后收益或促销活动。",
            "不执行购票、代购、支付或自动投注。",
        ],
    }
    if auto_reason:
        result["selection_reason"] = auto_reason
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=== 决策结论 ===")
        print(analysis["decision_conclusion"])
        print("=== 预算约束 ===")
        print(f"预算 {budget} 元；实际支出 {spent} 元；剩余 {leftover} 元；注数 {lines}。")
        print("只购买完整注数，不为了凑整超出预算。")
        print("=== 玩法筛选 ===")
        for item in analysis["game_screen"]:
            print(f"[{item['label']}] {item['statement']}")
        print("=== 概率计算 ===")
        print(f"{probability_details['formula']}")
        if "one_line_odds" in probability_details:
            print(f"单注目标事件：{probability_details['one_line_odds']}；本组约：{probability_details['portfolio_odds_approx']}。")
        print(probability_details["note"])
        print("=== 组合策略 ===")
        print("组合互不重复；反人群启发式只可能影响撞号风险，不能提高开奖概率。")
        print("共享去重：" + (f"已按开奖期号 {args.draw_issue} 登记到共享服务。" if reservation else "未启用共享服务，仅保证本次结果内部不重复。"))
        print("=== EV与税务 ===")
        print("EV_unverified：未接入当期官方奖池、派奖、共奖人数和税务情景，没有伪造收益率。")
        print("=== 执行清单 ===")
        print(f"seed：{seed}")
        print("组合：")
        for index, combination in enumerate(combinations, 1):
            print(f"{index:02d}. {combination}")
        print("说明：号码候选离线生成；不代表提高中奖率，也未验证正EV。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        raise SystemExit(f"输入错误：{exc}")
