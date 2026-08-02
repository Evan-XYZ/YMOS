#!/usr/bin/env python3
"""
核心资产动态判定表专用价格扫描。

作者内核扩展，默认关闭。它只提供数据，不应脱离用户 Profile 直接生成交易动作。

读取核心资产状态机 + 美股/A股观察状态机 + 持仓/Watchlist 状态机中的 ticker，
然后复用投资雷达同一套 fetch_price_router.py：
  - 美股 / Crypto → Finnhub（有 FINNHUB_API_KEY）否则 Yahoo
  - A股 .SS/.SZ → Tushare（有 TUSHARE_TOKEN）否则 Yahoo
  - 港股 .HK → Yahoo

设计原则：不影响现有 price_scan_from_state.py；这是核心资产库的独立 Raw 层。
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
YMOS_ROOT = SCRIPTS_DIR.parents[1]  # Eyes/scripts → Eyes → YMOS

sys.path.insert(0, str(SCRIPTS_DIR))
from env_loader import load_dotenv

DEFAULT_STATE_FILES = [
    "持仓与关注/核心资产库/核心资产状态机.md",
    "持仓与关注/美股观察/美股Watchlist状态机.md",
    "持仓与关注/A股观察/A股Watchlist状态机.md",
    "持仓与关注/持仓_状态机.md",
    "持仓与关注/Watchlist_状态机.md",
]

MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
CODE_RE = re.compile(r"`([^`]+)`")


def clean_cell(value: str) -> str:
    value = value.strip()
    value = MARKDOWN_LINK_RE.sub(r"\1", value)
    value = CODE_RE.sub(r"\1", value)
    value = value.replace("**", "").replace("*", "")
    return value.strip()


def normalize_symbol(raw: str) -> str | None:
    raw = clean_cell(raw)
    if not raw or raw in {"---", "—", "-"}:
        return None
    # 常见写法：AMD / AMD.US / 688012.SH / 300750.SZ / 0700.HK
    token = raw.split()[0].strip().upper().strip("，,;；")
    token = token.replace(".US", "")
    token = token.replace(".SH", ".SS")
    # 排除明显不是 ticker 的文本
    if len(token) > 18 or any(ch in token for ch in "：:（）()【】[]"):
        return None
    if not re.match(r"^[A-Z0-9.-]+$", token):
        return None
    return token


def extract_tickers_from_markdown_table(filepath: Path) -> list[str]:
    if not filepath.exists():
        return []
    text = filepath.read_text(encoding="utf-8")
    tickers: list[str] = []
    ticker_col_idx: int | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            ticker_col_idx = None
            continue
        cols = [c.strip() for c in stripped.strip("|").split("|")]
        if not cols:
            continue
        lowered = [c.lower().replace(" ", "") for c in cols]
        if any(c in {"ticker", "代码", "标的"} for c in lowered):
            for idx, col in enumerate(lowered):
                if col in {"ticker", "代码", "标的"}:
                    ticker_col_idx = idx
                    break
            continue
        if all(set(c) <= {"-", ":", " "} for c in cols):
            continue
        if ticker_col_idx is not None and ticker_col_idx < len(cols):
            symbol = normalize_symbol(cols[ticker_col_idx])
            if symbol:
                tickers.append(symbol)
    return tickers


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(description="核心资产动态判定表价格扫描")
    p.add_argument("--state-file", action="append", default=[], help="额外状态机文件；可多次传入")
    p.add_argument("--symbols", default="", help="额外 ticker，逗号分隔")
    p.add_argument("--date-tag", default=dt.datetime.now().strftime("%Y%m%d"))
    p.add_argument("--output-dir", default="", help="输出目录；默认 Eyes/核心资产动态判定表/Raw_Data/YYYY-MM")
    p.add_argument("--finnhub-token", default="", help="可选；不传则读取 FINNHUB_API_KEY")
    p.add_argument("--tushare-token", default="", help="可选；不传则读取 TUSHARE_TOKEN")
    args = p.parse_args()

    state_files = [YMOS_ROOT / rel for rel in DEFAULT_STATE_FILES]
    state_files.extend(Path(pth).expanduser() for pth in args.state_file)

    tickers: list[str] = []
    for path in state_files:
        found = extract_tickers_from_markdown_table(path)
        if found:
            print(f"📄 {path.relative_to(YMOS_ROOT) if path.is_relative_to(YMOS_ROOT) else path}: {len(found)} tickers")
            tickers.extend(found)
    if args.symbols:
        for raw in args.symbols.split(","):
            sym = normalize_symbol(raw)
            if sym:
                tickers.append(sym)

    seen: set[str] = set()
    deduped: list[str] = []
    for ticker in tickers:
        if ticker not in seen:
            seen.add(ticker)
            deduped.append(ticker)

    if not deduped:
        raise SystemExit("NO_SYMBOLS: 核心资产/观察状态机里没有可扫描 ticker")

    month_tag = f"{args.date_tag[:4]}-{args.date_tag[4:6]}" if len(args.date_tag) >= 6 else dt.datetime.now().strftime("%Y-%m")
    out_dir = Path(args.output_dir) if args.output_dir else YMOS_ROOT / "Eyes" / "核心资产动态判定表" / "Raw_Data" / month_tag
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"📊 核心资产价格扫描 ticker={len(deduped)}: {', '.join(deduped)}")
    print(f"📁 输出目录: {out_dir}")

    finnhub_key = args.finnhub_token or os.getenv("FINNHUB_API_KEY", "")
    tushare_token = args.tushare_token or os.getenv("TUSHARE_TOKEN", "")

    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "fetch_price_router.py"),
        "--symbols",
        ",".join(deduped),
        "--output-dir",
        str(out_dir),
        "--date-tag",
        args.date_tag,
    ]
    if finnhub_key:
        cmd += ["--finnhub-token", finnhub_key]
    if tushare_token:
        cmd += ["--tushare-token", tushare_token]

    code = subprocess.call(cmd, cwd=str(YMOS_ROOT))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
