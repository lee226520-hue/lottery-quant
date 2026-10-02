#!/usr/bin/env python3
"""Fetch, validate, snapshot, and analyze official Chinese lottery data.

The adapters intentionally use curl rather than urllib/requests because the
official sites use redirects/WAF rules that vary by user-agent and session.
No third-party or unofficial fallback source is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.parse import urlencode


ASIA_SHANGHAI = "Asia/Shanghai"
CWL_GAMES = {"ssq", "7lc", "kl8", "3d"}
SPORTTERY_GAMES = {"dlt", "pl3", "pl5", "7xc"}
ALL_GAMES = sorted(CWL_GAMES | SPORTTERY_GAMES)

GAME_CONFIG: dict[str, dict[str, Any]] = {
    "ssq": {"name": "双色球", "source": "cwl", "cwl_name": "ssq", "page": "ssq", "main_count": 6, "main_max": 33, "extra_count": 1, "extra_max": 16},
    "7lc": {"name": "七乐彩", "source": "cwl", "cwl_name": "qlc", "page": "qlc", "main_count": 7, "main_max": 30, "extra_count": 1, "extra_max": 30},
    "kl8": {"name": "快乐8", "source": "cwl", "cwl_name": "kl8", "page": "kl8", "main_count": 20, "main_max": 80, "extra_count": 0, "extra_max": 0},
    "3d": {"name": "福彩3D", "source": "cwl", "cwl_name": "3d", "page": "fc3d", "main_count": 3, "main_max": 9, "ordered": True, "extra_count": 0, "extra_max": 0},
    "dlt": {"name": "超级大乐透", "source": "sporttery", "game_no": "85", "main_count": 5, "main_max": 35, "extra_count": 2, "extra_max": 12},
    "pl3": {"name": "排列3", "source": "sporttery", "game_no": "35", "main_count": 3, "main_max": 9, "ordered": True, "extra_count": 0, "extra_max": 0},
    "pl5": {"name": "排列5", "source": "sporttery", "game_no": "350133", "main_count": 5, "main_max": 9, "ordered": True, "extra_count": 0, "extra_max": 0},
    "7xc": {"name": "7星彩", "source": "sporttery", "game_no": "04", "main_count": 7, "main_max": 14, "ordered": True, "extra_count": 0, "extra_max": 0},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def run_curl(args: list[str], input_text: str | None = None) -> str:
    command = ["curl", "--fail", "--silent", "--show-error", "--location", "--http1.1", "--max-time", "30", "--retry", "2"] + args
    completed = subprocess.run(command, input=input_text, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(f"curl failed ({completed.returncode}): {completed.stderr.strip()}")
    return completed.stdout


def cwl_records(game: str, page_size: int, max_records: int, delay: float) -> list[dict[str, Any]]:
    cfg = GAME_CONFIG[game]
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128 Safari/537.36"
    referer = f"https://www.cwl.gov.cn/ygkj/wqkjgg/{cfg['page']}/"
    with tempfile.NamedTemporaryFile(prefix="lottery-cwl-", delete=False) as cookie_file:
        cookie_path = cookie_file.name
    try:
        run_curl(["-c", cookie_path, "-A", user_agent, "-o", os.devnull, referer])
        records: list[dict[str, Any]] = []
        page_no = 1
        target = max_records if max_records > 0 else 10**9
        while len(records) < target:
            query = urlencode({
                "name": cfg["cwl_name"], "issueCount": "", "issueStart": "", "issueEnd": "",
                "dayStart": "", "dayEnd": "", "pageNo": page_no, "pageSize": page_size, "systemType": "PC",
            })
            url = f"https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice?{query}"
            raw = run_curl(["-b", cookie_path, "-A", user_agent, "-H", "Accept: application/json", "-H", f"Referer: {referer}", url])
            payload = json.loads(raw)
            result = payload.get("result") or []
            if not result:
                break
            for item in result:
                records.append(normalize_cwl(game, item, url, raw))
                if len(records) >= target:
                    break
            page_no += 1
            if len(result) < page_size:
                break
            if delay:
                time.sleep(delay)
        return records
    finally:
        try:
            Path(cookie_path).unlink(missing_ok=True)
        except OSError:
            pass


def sporttery_records(game: str, page_size: int, max_records: int, delay: float) -> list[dict[str, Any]]:
    cfg = GAME_CONFIG[game]
    user_agent = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
    referer = "https://m.lottery.gov.cn/"
    records: list[dict[str, Any]] = []
    page_no = 1
    target = max_records if max_records > 0 else 10**9
    while len(records) < target:
        query = urlencode({"gameNo": cfg["game_no"], "provinceId": 0, "pageSize": page_size, "isVerify": 1, "pageNo": page_no})
        url = f"https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?{query}"
        raw = run_curl(["-A", user_agent, "-H", "Accept: application/json", "-H", f"Referer: {referer}", url])
        payload = json.loads(raw)
        value = payload.get("value") or {}
        result = value.get("list") or []
        if not result:
            break
        for item in result:
            records.append(normalize_sporttery(game, item, url, raw))
            if len(records) >= target:
                break
        page_no += 1
        if len(result) < page_size:
            break
        if delay:
            time.sleep(delay)
    return records


def parse_numbers(raw: str) -> list[int]:
    return [int(part) for part in re.findall(r"\d+", raw or "")]


def parse_money(raw: Any) -> float | None:
    if raw in (None, "", "---", "-"):
        return None
    try:
        return float(str(raw).replace(",", "").replace("元", "").strip())
    except ValueError:
        return None


def parse_count(raw: Any) -> int:
    if raw in (None, "", "---", "-"):
        return 0
    try:
        return int(str(raw).replace(",", ""))
    except ValueError:
        return 0


def normalize_prizes(items: Any) -> list[dict[str, Any]]:
    prizes = []
    for item in items or []:
        prizes.append({
            "type": item.get("type", item.get("prizeLevel", "")),
            "name": item.get("prizeLevel", ""),
            "count": parse_count(item.get("typenum", item.get("stakeCount", 0))),
            "amount_rmb": parse_money(item.get("typemoney", item.get("stakeAmountFormat"))),
        })
    return prizes


def normalize_cwl(game: str, item: dict[str, Any], url: str, raw: str) -> dict[str, Any]:
    cfg = GAME_CONFIG[game]
    all_numbers = parse_numbers(item.get("red", ""))
    main = all_numbers[: cfg["main_count"]]
    extra = parse_numbers(item.get("blue", ""))[: cfg["extra_count"]]
    record = {
        "game": game, "name": cfg["name"], "issue": str(item.get("code", "")), "date": item.get("date", ""),
        "main": main, "extra": extra, "sales_rmb": parse_money(item.get("sales")),
        "pool_afterdraw_rmb": parse_money(item.get("poolmoney")), "prizes": normalize_prizes(item.get("prizegrades")),
        "source": "cwl.gov.cn", "source_url": url, "fetched_at": now_iso(),
        "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }
    validate_record(record)
    return record


def normalize_sporttery(game: str, item: dict[str, Any], url: str, raw: str) -> dict[str, Any]:
    cfg = GAME_CONFIG[game]
    numbers = parse_numbers(item.get("lotteryDrawResult", ""))
    main = numbers[: cfg["main_count"]]
    extra = numbers[cfg["main_count"] : cfg["main_count"] + cfg["extra_count"]]
    record = {
        "game": game, "name": cfg["name"], "issue": str(item.get("lotteryDrawNum", "")), "date": item.get("lotteryDrawTime", ""),
        "main": main, "extra": extra, "sales_rmb": None,
        "pool_afterdraw_rmb": parse_money(item.get("poolBalanceAfterdraw")), "prizes": normalize_prizes(item.get("prizeLevelList")),
        "source": "webapi.sporttery.cn", "source_url": url, "fetched_at": now_iso(),
        "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }
    validate_record(record)
    return record


def validate_record(record: dict[str, Any]) -> None:
    cfg = GAME_CONFIG[record["game"]]
    main = record["main"]
    extra = record["extra"]
    if not record["issue"] or not record["date"]:
        raise ValueError(f"{record['game']}: missing issue/date")
    if len(main) != cfg["main_count"]:
        raise ValueError(f"{record['game']} {record['issue']}: expected {cfg['main_count']} main numbers, got {main}")
    if any(n < 0 or n > cfg["main_max"] for n in main):
        raise ValueError(f"{record['game']} {record['issue']}: main number out of range: {main}")
    if not cfg.get("ordered") and len(set(main)) != len(main):
        raise ValueError(f"{record['game']} {record['issue']}: duplicate main number: {main}")
    if len(extra) != cfg["extra_count"]:
        raise ValueError(f"{record['game']} {record['issue']}: expected {cfg['extra_count']} extra numbers, got {extra}")
    if any(n < 0 or n > cfg["extra_max"] for n in extra):
        raise ValueError(f"{record['game']} {record['issue']}: extra number out of range: {extra}")
    if not cfg.get("ordered") and len(set(extra)) != len(extra):
        raise ValueError(f"{record['game']} {record['issue']}: duplicate extra number: {extra}")


def data_root(raw: str | None) -> Path:
    return Path(raw).expanduser() if raw else Path.home() / ".lottery-quant" / "data"


def write_snapshot(root: Path, game: str, records: list[dict[str, Any]], raw_records: list[dict[str, Any]] | None = None) -> Path:
    history_dir = root / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    path = history_dir / f"{game}.json"
    existing: dict[str, dict[str, Any]] = {}
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            existing = {str(item["issue"]): item for item in old.get("records", [])}
        except (OSError, json.JSONDecodeError, KeyError):
            existing = {}
    for record in records:
        existing[str(record["issue"])] = record
    merged = sorted(existing.values(), key=lambda item: (item.get("date", ""), item.get("issue", "")), reverse=True)
    payload = {
        "schema": "lottery-quant.official.v1", "game": game, "name": GAME_CONFIG[game]["name"],
        "updated_at": now_iso(), "source_policy": "official-only", "records": merged,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_records(root: Path, game: str) -> list[dict[str, Any]]:
    path = root / "history" / f"{game}.json"
    if not path.exists():
        raise FileNotFoundError(f"没有本地快照：{path}。先运行 sync。")
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records") or []
    for record in records:
        validate_record(record)
    return records


def theoretical_spaces(game: str) -> str:
    formulas = {
        "ssq": "C(33,6)×16 = 17,721,088",
        "dlt": "C(35,5)×C(12,2) = 21,425,712",
        "7lc": "C(30,7) = 2,035,800",
        "kl8": "C(80,10) for a 10-number line; actual play varies by selected count",
        "3d": "10^3 = 1,000",
        "pl3": "10^3 = 1,000",
        "pl5": "10^5 = 100,000",
        "7xc": "10^6×15 = 15,000,000 under the current structure",
    }
    return formulas[game]


def history_policy(total: int, requested: str | int) -> dict[str, Any]:
    recent = min(total, 100)
    medium = min(total, 500)
    if requested in ("auto", 0, "0"):
        selected = total
        selected_label = "all_available"
    else:
        selected = min(total, int(requested))
        selected_label = f"requested_{requested}"
    return {
        "stored_draws": total,
        "recent_window": recent,
        "medium_window": medium,
        "long_window": total,
        "selected_window": selected,
        "selected_window_label": selected_label,
        "decision": "默认全量用于历史描述，同时保留100期和500期窗口用于稳定性对照。",
        "sufficiency": "adequate_for_descriptive_stats" if total >= 500 else "limited_sample" if total >= 100 else "insufficient_sample",
        "backtest_note": "如果样本少于500期，回测结果只作探索，不作为策略有效性的证据；样本越多也不代表能预测随机开奖。",
    }


def window_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"count": 0}
    main_sums = [sum(record["main"]) for record in records]
    extra_sums = [sum(record["extra"]) for record in records if record["extra"]]
    summary: dict[str, Any] = {
        "count": len(records),
        "latest_issue": records[0]["issue"],
        "oldest_issue": records[-1]["issue"],
        "main_sum_mean": round(mean(main_sums), 4),
    }
    if extra_sums:
        summary["extra_sum_mean"] = round(mean(extra_sums), 4)
    return summary


def analyze(root: Path, game: str, window: str | int) -> dict[str, Any]:
    all_records = load_records(root, game)
    policy = history_policy(len(all_records), window)
    records = all_records[: policy["selected_window"]]
    window_comparison = {
        "recent_100": window_summary(all_records[: policy["recent_window"]]),
        "medium_500": window_summary(all_records[: policy["medium_window"]]),
        "all_available": window_summary(all_records),
    }
    cfg = GAME_CONFIG[game]
    main_counts = Counter(n for record in records for n in record["main"])
    extra_counts = Counter(n for record in records for n in record["extra"])
    latest = records[0]
    omission = {}
    for number in range(0 if cfg.get("ordered") else 1, cfg["main_max"] + 1):
        omission[number] = next((i for i, record in enumerate(records) if number in record["main"]), len(records))
    structural: dict[str, Any] = {"sample_size": len(records)}
    if records and cfg.get("ordered"):
        sums = [sum(record["main"]) for record in records]
        structural.update({"sum_mean": round(mean(sums), 4), "sum_min": min(sums), "sum_max": max(sums)})
        structural["shape_counts"] = dict(Counter("豹子" if len(set(record["main"])) == 1 else "组三" if len(set(record["main"])) == 2 else "组六" for record in records))
    elif records:
        sums = [sum(record["main"]) for record in records]
        structural.update({"main_sum_mean": round(mean(sums), 4), "main_sum_min": min(sums), "main_sum_max": max(sums)})
        structural["odd_even_counts"] = dict(Counter(f"{sum(n % 2 for n in record['main'])}:{len(record['main']) - sum(n % 2 for n in record['main'])}" for record in records))
    return {
        "game": game, "name": cfg["name"], "generated_at": now_iso(), "timezone": ASIA_SHANGHAI,
        "source_policy": "official-only", "record_count": len(records), "latest": latest,
        "history_policy": policy,
        "window_comparison": window_comparison,
        "period_range": {"latest": latest["issue"], "oldest": records[-1]["issue"]},
        "theoretical_space": theoretical_spaces(game),
        "main_frequency": dict(sorted(main_counts.items())), "extra_frequency": dict(sorted(extra_counts.items())),
        "main_omission_in_window": omission, "structural": structural,
        "interpretation": [
            "这些统计描述历史数据，不证明下一期存在可利用的预测优势。",
            "遗漏值是样本描述，不是回补信号；不使用赌徒谬误生成确定性结论。",
            "推荐号码若需要生成，应以预算、覆盖和反撞号目标为主，并与均匀随机基线比较。",
        ],
    }


def sync_one(root: Path, game: str, count: int, page_size: int, delay: float) -> Path:
    fetcher = cwl_records if GAME_CONFIG[game]["source"] == "cwl" else sporttery_records
    records = fetcher(game, page_size, count, delay)
    if not records:
        raise RuntimeError(f"{game}: official API returned no records")
    return write_snapshot(root, game, records)


def main() -> int:
    parser = argparse.ArgumentParser(description="Official-only lottery history sync and analysis")
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync", help="fetch latest history and merge into local snapshots")
    sync.add_argument("--games", default="all", help="comma-separated games or all")
    sync.add_argument("--count", type=int, default=0, help="number of recent draws to fetch; default/0 means all available pages")
    sync.add_argument("--page-size", type=int, default=100)
    sync.add_argument("--delay", type=float, default=0.5)
    sync.add_argument("--data-dir")
    report = sub.add_parser("analyze", help="analyze a local official snapshot")
    report.add_argument("--game", required=True, choices=ALL_GAMES)
    report.add_argument("--window", default="auto", help="auto=全量历史并同时保留100/500期对照；也可填具体期数")
    report.add_argument("--data-dir")
    report.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = data_root(args.data_dir)
    if args.command == "sync":
        games = ALL_GAMES if args.games == "all" else [game.strip() for game in args.games.split(",") if game.strip()]
        unknown = [game for game in games if game not in GAME_CONFIG]
        if unknown:
            raise SystemExit(f"不支持的玩法：{', '.join(unknown)}")
        for game in games:
            path = sync_one(root, game, args.count, args.page_size, args.delay)
            print(f"{GAME_CONFIG[game]['name']}: {path}")
        return 0
    result = analyze(root, args.game, args.window)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"=== {result['name']} 官方数据回溯 ===")
        print(f"时间：{result['generated_at']}；样本：{result['record_count']}期；期号：{result['period_range']['oldest']}—{result['period_range']['latest']}")
        print(f"理论组合空间：{result['theoretical_space']}")
        print(f"最新一期：{result['latest']['issue']} / {result['latest']['date']} / 主区 {result['latest']['main']} / 附加区 {result['latest']['extra']}")
        print("主区频次：", result["main_frequency"])
        if result["extra_frequency"]:
            print("附加区频次：", result["extra_frequency"])
        print("窗口遗漏：", result["main_omission_in_window"])
        print("结构统计：", result["structural"])
        print("窗口对照：", result["window_comparison"])
        print("口径：官方数据快照；统计用于描述历史，不代表预测下一期。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        raise SystemExit(f"数据流程失败：{exc}")
