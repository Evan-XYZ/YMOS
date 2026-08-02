#!/usr/bin/env python3
"""
从状态机提取 ticker 后触发统一价格扫描。

读取 持仓_状态机.md 和 Watchlist_状态机.md 的 Ticker 列，
然后调用 fetch_price_router.py 完成价格路由。
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parents[1]  # Eyes/scripts → Eyes → YMOS

sys.path.insert(0, str(SCRIPTS_DIR))
from env_loader import load_dotenv
from runtime_paths import repo_paths

PATHS = repo_paths(ROOT)


def extract_tickers_from_state_machine(filepath: Path) -> list[str]:
    """从 Markdown 状态机表格中提取 Ticker 列的值。"""
    if not filepath.exists():
        return []

    text = filepath.read_text(encoding="utf-8")
    tickers = []

    # 找到表格行，提取 Ticker 列
    in_table = False
    ticker_col_idx = -1

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            in_table = False
            continue

        # 模板中的示例/灰度行不是用户真实状态，不能触发外部行情请求。
        normalized_line = line.replace("（", "(").replace("）", ")")
        if "(示例)" in normalized_line or "demo_only" in normalized_line.lower():
            continue

        cols = [c.strip() for c in line.split("|")]
        # 去掉首尾空列（| 开头和结尾产生的空字符串）
        cols = [c for c in cols if c or c == ""]

        if not in_table:
            # 寻找表头行
            lowered = [col.lower() for col in cols]
            for header in ("ticker", "代码", "标的"):
                if header in lowered:
                    ticker_col_idx = lowered.index(header)
                    in_table = True
                    break
            continue

        # 跳过分隔行 |:---|:---|
        if all(c.replace("-", "").replace(":", "") == "" for c in cols):
            continue

        # 提取 ticker 值
        if 0 <= ticker_col_idx < len(cols):
            val = cols[ticker_col_idx].strip()
            if val and val != "---" and not val.startswith(":") and re.fullmatch(r"[A-Z0-9.:-]+", val.upper()):
                tickers.append(val.upper())

    return tickers


def main() -> None:
    load_dotenv()

    p = argparse.ArgumentParser(description="从状态机触发统一价格扫描")
    p.add_argument("--finnhub-token", default="", help="可选；不传则尝试读取 FINNHUB_API_KEY")
    p.add_argument("--tushare-token", default="", help="可选；不传则尝试读取 TUSHARE_TOKEN")
    p.add_argument("--date-tag", default=dt.datetime.now().strftime("%Y%m%d"))
    p.add_argument("--output", default="", help="输出 JSON 路径（不传则自动按日期生成）")
    args = p.parse_args()

    PATHS.ensure_layout()

    # 1) 从状态机提取活跃 ticker
    watch_path = PATHS.watchlist_state
    hold_path = PATHS.holding_state

    tickers = []
    tickers.extend(extract_tickers_from_state_machine(watch_path))
    tickers.extend(extract_tickers_from_state_machine(hold_path))

    # 去重
    seen = set()
    deduped = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            deduped.append(t)

    if not deduped:
        print("NO_SYMBOLS: 状态机里没有可扫描 ticker")
        return

    print(f"📊 从状态机提取到 {len(deduped)} 个 ticker: {', '.join(deduped)}")

    # 2) 路由请求
    out_dir = str(PATHS.radar_raw_dir(args.date_tag))
    finnhub_key   = args.finnhub_token  or os.getenv("FINNHUB_API_KEY", "")
    tushare_token = args.tushare_token  or os.getenv("TUSHARE_TOKEN", "")

    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "fetch_price_router.py"),
        "--symbols", ",".join(deduped),
        "--output-dir", out_dir,
        "--date-tag", args.date_tag,
    ]
    if finnhub_key:
        cmd += ["--finnhub-token", finnhub_key]
    if tushare_token:
        cmd += ["--tushare-token", tushare_token]

    code = subprocess.call(cmd, cwd=str(ROOT))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
