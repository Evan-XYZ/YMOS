#!/usr/bin/env python3
"""
A股核心资产技术回踩扫描（问财版）。

目标：不改动现有 iwencai_stockpick.py，只复用它的问财 SkillHub 选股能力，
对核心资产库里的 A股 A类资产逐只查询 MA5/MA10/MA20，并识别：
  - price_below_ma10: 股价/收盘价低于 10 日均线
  - near_ma10: 距离 10 日均线 <= 阈值（默认 3%）
  - near_ma20: 距离 20 日均线 <= 阈值（默认 5%）
  - extended: 高于 MA10 过远（默认 >15%），提示不追高

说明：问财对“多个均线 + 多个条件”混合问句有时只返回 OHLC，
实测逐条问「{股票名} 最新价 10日均线 距10日均线」最稳定，
比「股价低于10日均线」更容易强制返回 ma10 字段；
所以本脚本按 MA5/10/20 分三次查询后合并，并自行计算是否跌破均线。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
YMOS_ROOT = SCRIPTS_DIR.parents[1]
IWENCAI_STOCKPICK = SCRIPTS_DIR / "iwencai_stockpick.py"
DEFAULT_STATE = YMOS_ROOT / "持仓与关注" / "核心资产库" / "核心资产状态机.md"


def parse_a_core_assets(state_file: Path) -> list[dict[str, str]]:
    text = state_file.read_text(encoding="utf-8")
    assets: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.startswith("|") or "A股" not in line:
            continue
        cols = [c.strip().replace("`", "") for c in line.strip("|").split("|")]
        if len(cols) < 4 or cols[0] in {"Ticker", ":---"}:
            continue
        ticker, name, grade = cols[0], cols[1], cols[3]
        if re.match(r"^\d{6}\.(SZ|SH|BJ)$", ticker) and "A类" in grade:
            assets.append({"ticker": ticker, "name": name, "grade": grade})
    return assets


def run_iwencai(query: str, limit: int = 5) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="iwencai_pullback_") as td:
        root = Path(td)
        json_out = root / "out.json"
        cmd = [
            sys.executable,
            str(IWENCAI_STOCKPICK),
            query,
            "--json-out", str(json_out),
            "--csv-out", str(root / "out.csv"),
            "--desc-out", str(root / "desc.txt"),
            "--status-out", str(root / "status.txt"),
            "--limit", str(limit),
            "--no-fetch-all",
        ]
        proc = subprocess.run(cmd, cwd=str(YMOS_ROOT), capture_output=True, text=True)
        if proc.returncode != 0:
            return {"success": False, "query": query, "error": proc.stdout.strip() + "\n" + proc.stderr.strip()}
        try:
            return json.loads(json_out.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"success": False, "query": query, "error": f"json_parse_failed: {exc}"}


def first_float(row: dict[str, Any], patterns: list[str]) -> float | None:
    for pat in patterns:
        rx = re.compile(pat)
        for k, v in row.items():
            if rx.search(k):
                try:
                    return float(str(v).replace("%", "").replace(",", ""))
                except Exception:
                    pass
    return None


def first_bool(row: dict[str, Any], patterns: list[str]) -> bool | None:
    for pat in patterns:
        rx = re.compile(pat)
        for k, v in row.items():
            if rx.search(k):
                if isinstance(v, bool):
                    return v
                s = str(v).strip().lower()
                if s in {"true", "1", "是", "yes"}:
                    return True
                if s in {"false", "0", "否", "no"}:
                    return False
    return None


def scan_asset(asset: dict[str, str], sleep_seconds: float = 0.2) -> dict[str, Any]:
    name = asset["name"]
    ticker = asset["ticker"]
    merged: dict[str, Any] = {**asset, "queries": [], "raw_rows": []}
    latest = None
    pct_chg = None

    for window in (5, 10, 20):
        query = f"{name} 最新价 {window}日均线 距{window}日均线"
        result = run_iwencai(query)
        merged["queries"].append({"ma": window, "query": query, "success": result.get("success")})
        rows = result.get("datas") or []
        row = None
        for candidate in rows:
            if candidate.get("股票代码") == ticker or candidate.get("股票简称") == name:
                row = candidate
                break
        if row is None and rows:
            row = rows[0]
        if row:
            merged["raw_rows"].append(row)
            latest = latest if latest is not None else first_float(row, [r"最新价", r"收盘价"])
            pct_chg = pct_chg if pct_chg is not None else first_float(row, [r"最新涨跌幅", r"涨跌幅"])
            ma = first_float(row, [rf"ma{window}\[", rf"{window}日均线", rf"MA{window}"])
            # 问财有时不返回 “收盘价 < ma” 布尔字段；MA 返回后自行计算更稳。
            below = first_bool(row, [rf"< ma{window}\[", rf"低于{window}日"])
            if below is None and latest is not None and ma is not None:
                below = latest < ma
            merged[f"ma{window}"] = ma
            merged[f"below_ma{window}"] = below
        else:
            merged[f"ma{window}"] = None
            merged[f"below_ma{window}"] = None
            if not result.get("success"):
                merged.setdefault("errors", []).append(result.get("error", "unknown_error"))
        time.sleep(sleep_seconds)

    merged["latest"] = latest
    merged["pct_chg"] = pct_chg
    for window in (5, 10, 20):
        ma = merged.get(f"ma{window}")
        if latest is not None and ma:
            merged[f"dist_ma{window}_pct"] = (latest / ma - 1) * 100
        else:
            merged[f"dist_ma{window}_pct"] = None
    return merged


def classify(row: dict[str, Any], near10: float, near20: float, extended10: float) -> str:
    latest = row.get("latest")
    ma10 = row.get("ma10")
    ma20 = row.get("ma20")
    d10 = row.get("dist_ma10_pct")
    d20 = row.get("dist_ma20_pct")
    below10 = row.get("below_ma10")
    below20 = row.get("below_ma20")
    if latest is None or ma10 is None:
        return "⚪ 数据不足"
    if below20 is True:
        return "🔴 跌破20日线：趋势需复核"
    if below10 is True:
        return "🟢 回踩/跌破10日线：重点提醒"
    if d10 is not None and 0 <= d10 <= near10:
        return "🟢 接近10日线：候选买点提醒"
    if ma20 is not None and d20 is not None and 0 <= d20 <= near20:
        return "🟡 接近20日线：深回踩观察"
    if d10 is not None and d10 > extended10:
        return "⚪ 高于10日线过远：不追高"
    return "👀 趋势内观察"


def build_report(rows: list[dict[str, Any]], date_tag: str, near10: float, near20: float, extended10: float) -> str:
    day = f"{date_tag[:4]}-{date_tag[4:6]}-{date_tag[6:8]}"
    lines = [
        f"# A股核心资产技术回踩扫描（问财） {day}",
        "",
        "> 数据源：同花顺问财 SkillHub / hithink-astock-selector 问句查询。",
        "> 用途：只做技术形态提醒，不替代 P5/P12 买入审计。",
        "",
        "## 参数",
        "",
        f"- near_ma10_threshold: {near10}%",
        f"- near_ma20_threshold: {near20}%",
        f"- extended_ma10_threshold: {extended10}%",
        "",
        "## 扫描结论",
        "",
        "| Ticker | 名称 | 最新价 | 涨跌幅 | MA10 | 距MA10 | MA20 | 距MA20 | 信号 |",
        "|:---|:---|---:|---:|---:|---:|---:|---:|:---|",
    ]
    order = {"🟢": 0, "🟡": 1, "🔴": 2, "👀": 3, "⚪": 4}
    def key(r: dict[str, Any]) -> tuple[int, str]:
        sig = r.get("signal", "")
        return (order.get(sig[:1], 9), r.get("ticker", ""))
    for r in sorted(rows, key=key):
        def fmt(v: Any, nd: int = 2) -> str:
            return "—" if v is None else f"{float(v):.{nd}f}"
        lines.append(
            f"| {r.get('ticker')} | {r.get('name')} | {fmt(r.get('latest'))} | {fmt(r.get('pct_chg'))}% | "
            f"{fmt(r.get('ma10'))} | {fmt(r.get('dist_ma10_pct'))}% | {fmt(r.get('ma20'))} | {fmt(r.get('dist_ma20_pct'))}% | {r.get('signal')} |"
        )
    alerts = [r for r in rows if str(r.get("signal", "")).startswith("🟢")]
    lines += [
        "",
        "## 今日需要看一眼",
        "",
    ]
    if alerts:
        for r in alerts:
            lines.append(f"- {r['ticker']} {r['name']}：{r['signal']}（距 MA10 {r.get('dist_ma10_pct'):.2f}%）")
    else:
        lines.append("- 暂无 A 类 A股核心资产触发 10 日线回踩/接近提醒。")
    lines += [
        "",
        "## 解释口径",
        "",
        "- 🟢 接近/跌破 10 日线：进入人工看 K 线 + P5/P12 的候选窗口。",
        "- 🟡 接近 20 日线：可能是更深回踩，也可能是趋势走弱，需要结合事件层。",
        "- 🔴 跌破 20 日线：不是直接买点，先复核趋势和基本面是否变坏。",
        "- ⚪ 高于 10 日线过远：核心资产也不追高，等待下一次承接。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="A股核心资产技术回踩扫描（问财版）")
    p.add_argument("--state-file", default=str(DEFAULT_STATE))
    p.add_argument("--date-tag", default=dt.datetime.now().strftime("%Y%m%d"))
    p.add_argument("--output-root", default=str(YMOS_ROOT / "Eyes" / "A股核心资产回踩扫描"))
    p.add_argument("--near-ma10", type=float, default=3.0)
    p.add_argument("--near-ma20", type=float, default=5.0)
    p.add_argument("--extended-ma10", type=float, default=15.0)
    p.add_argument("--sleep", type=float, default=0.2)
    args = p.parse_args()

    state_file = Path(args.state_file).expanduser().resolve()
    assets = parse_a_core_assets(state_file)
    if not assets:
        raise SystemExit(f"NO_A_CORE_ASSETS: {state_file}")

    rows = []
    for asset in assets:
        print(f"🔎 {asset['ticker']} {asset['name']}")
        row = scan_asset(asset, sleep_seconds=args.sleep)
        row["signal"] = classify(row, args.near_ma10, args.near_ma20, args.extended_ma10)
        rows.append(row)

    month = f"{args.date_tag[:4]}-{args.date_tag[4:6]}"
    day = f"{args.date_tag[:4]}-{args.date_tag[4:6]}-{args.date_tag[6:8]}"
    out_root = Path(args.output_root).resolve()
    raw_dir = out_root / "Raw_Data" / month
    report_dir = out_root / month
    raw_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    raw_path = raw_dir / f"a_core_pullback_{args.date_tag}.json"
    report_path = report_dir / f"A股核心资产回踩扫描_{day}.md"
    raw_path.write_text(json.dumps({"date_tag": args.date_tag, "assets": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(build_report(rows, args.date_tag, args.near_ma10, args.near_ma20, args.extended_ma10), encoding="utf-8")

    print(f"✅ raw: {raw_path}")
    print(f"✅ report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
