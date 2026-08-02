#!/usr/bin/env python3
"""
价格路由器（三源分流版）

路由规则（优先级顺序）：
  美股 / Crypto（无后缀）→ Finnhub（若有 FINNHUB_API_KEY，否则 Yahoo 兜底）
  A股（.SS / .SZ）       → Tushare（若有 TUSHARE_TOKEN，否则 Yahoo 兜底）
  港股（.HK）            → Yahoo（固定，无需 Key）

设计原则：
  - Yahoo 是零配置开箱即用的兜底，任何市场在 Key 缺失时都回退到 Yahoo
  - 有对应的 Key/Token 就走专用源，精度和稳定性更高
  - 三个分支完全独立，互不阻塞

2026-03-16 重构：新增 Tushare A股分支，A股不再走 Yahoo（科创板数据质量问题）
2026-03-17 增强：Crypto 符号归一化（BTC→BINANCE:BTCUSDT / BTC-USD），避免裸符号返回股票语义价格
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
YMOS_ROOT = SCRIPTS_DIR.parents[1]   # Eyes/scripts → Eyes → YMOS
ROOT = SCRIPTS_DIR.parents[2]        # parent of YMOS（subprocess cwd）

sys.path.insert(0, str(SCRIPTS_DIR))
from env_loader import load_dotenv


# ── Crypto 符号归一化 ──────────────────────────────────────────────────────
# 状态机中统一写裸符号（BTC / ETH），路由器在调用数据源前自动转换
# - Finnhub crypto endpoint 需要交易所前缀（BINANCE:BTCUSDT）
# - Yahoo 需要 -USD 后缀（BTC-USD）
CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "AVAX", "DOT"}

CRYPTO_MAP_FINNHUB = {
    "BTC": "BINANCE:BTCUSDT",
    "ETH": "BINANCE:ETHUSDT",
    "SOL": "BINANCE:SOLUSDT",
    "DOGE": "BINANCE:DOGEUSDT",
    "XRP": "BINANCE:XRPUSDT",
    "ADA": "BINANCE:ADAUSDT",
    "AVAX": "BINANCE:AVAXUSDT",
    "DOT": "BINANCE:DOTUSDT",
}

CRYPTO_MAP_YAHOO = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "DOGE": "DOGE-USD",
    "XRP": "XRP-USD",
    "ADA": "ADA-USD",
    "AVAX": "AVAX-USD",
    "DOT": "DOT-USD",
}


def crypto_base(symbol: str) -> str | None:
    """接受状态机裸符号，也兼容常见 Yahoo / Finnhub 写法。"""
    upper = symbol.upper()
    if upper in CRYPTO_SYMBOLS:
        return upper
    if upper.endswith("-USD") and upper[:-4] in CRYPTO_SYMBOLS:
        return upper[:-4]
    if upper.startswith("BINANCE:") and upper.endswith("USDT"):
        base = upper[len("BINANCE:"):-len("USDT")]
        return base if base in CRYPTO_SYMBOLS else None
    return None


def is_crypto(symbol: str) -> bool:
    return crypto_base(symbol) is not None


def normalize_for_source(symbol: str, source: str) -> str:
    """将状态机中的 crypto 裸符号转换为数据源需要的格式。非 crypto 原样返回。"""
    base = crypto_base(symbol)
    if base is None:
        return symbol
    if source == "finnhub":
        return CRYPTO_MAP_FINNHUB.get(base, f"BINANCE:{base}USDT")
    if source == "yahoo":
        return CRYPTO_MAP_YAHOO.get(base, f"{base}-USD")
    return symbol


def parse_symbols(raw: str) -> list[str]:
    if not raw:
        return []
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def classify(symbol: str) -> str:
    """
    返回该 Ticker 优先走哪个数据源（不考虑 Key 是否存在）。
      'finnhub' → 美股 / Crypto
      'tushare' → A股（上交所 .SS / 深交所 .SZ）
      'yahoo'   → 港股（.HK），以及所有市场的兜底
    """
    if symbol.endswith((".SS", ".SZ")):
        return "tushare"
    if symbol.endswith(".HK"):
        return "yahoo"
    if is_crypto(symbol):
        return "finnhub"
    # BTC/ETH 等 Crypto 及纯字母美股
    return "finnhub"


def run(cmd: list[str]) -> int:
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> None:
    load_dotenv()

    p = argparse.ArgumentParser(description="YMOS 价格路由器（三源分流）")
    p.add_argument("--symbols", required=True,
                   help="逗号分隔，如 AAPL,NIO,688008.SS,0700.HK")
    p.add_argument("--output-dir", default="Report/投资雷达/Raw_Data", help="输出目录")
    p.add_argument("--date-tag", default="", help="日期标签，如 20260316")
    p.add_argument("--finnhub-token", default="",
                   help="Finnhub Key（可选，也可通过 FINNHUB_API_KEY 环境变量传入）")
    p.add_argument("--tushare-token", default="",
                   help="Tushare Token（可选，也可通过 TUSHARE_TOKEN 环境变量传入）")
    args = p.parse_args()

    symbols = parse_symbols(args.symbols)
    if not symbols:
        raise SystemExit("symbols 不能为空")

    finnhub_key   = args.finnhub_token  or os.getenv("FINNHUB_API_KEY", "")
    tushare_token = args.tushare_token  or os.getenv("TUSHARE_TOKEN", "")

    # ── 分流 ────────────────────────────────────────────────────────────────
    finnhub_syms: list[str] = []
    tushare_syms: list[str] = []
    yahoo_syms:   list[str] = []

    for s in symbols:
        bucket = classify(s)
        if bucket == "finnhub":
            if finnhub_key:
                finnhub_syms.append(s)
            else:
                yahoo_syms.append(s)          # 无 Key → Yahoo 兜底
        elif bucket == "tushare":
            if tushare_token:
                tushare_syms.append(s)
            else:
                yahoo_syms.append(s)          # 无 Token → Yahoo 兜底
        else:  # "yahoo"
            yahoo_syms.append(s)

    out_dir = Path(args.output_dir).resolve()   # 转绝对路径，避免子进程 CWD 不一致
    out_dir.mkdir(parents=True, exist_ok=True)
    date_tag = args.date_tag or "latest"

    print("📡 价格路由分流结果：")
    print(f"   Finnhub  ({len(finnhub_syms)}): {finnhub_syms or '—'}")
    print(f"   Tushare  ({len(tushare_syms)}): {tushare_syms or '—'}")
    print(f"   Yahoo    ({len(yahoo_syms)}): {yahoo_syms or '—'}")
    print()

    # ── Crypto 归一化：裸符号 → 数据源专用格式 ────────────────────────────
    finnhub_syms_norm = [normalize_for_source(s, "finnhub") for s in finnhub_syms]
    yahoo_syms_norm   = [normalize_for_source(s, "yahoo")   for s in yahoo_syms]

    if finnhub_syms_norm != finnhub_syms or yahoo_syms_norm != yahoo_syms:
        print("🔄 Crypto 归一化：")
        if finnhub_syms_norm != finnhub_syms:
            print(f"   Finnhub: {finnhub_syms} → {finnhub_syms_norm}")
        if yahoo_syms_norm != yahoo_syms:
            print(f"   Yahoo:   {yahoo_syms} → {yahoo_syms_norm}")
        print()

    # ── Finnhub ─────────────────────────────────────────────────────────────
    if finnhub_syms_norm:
        out = out_dir / f"price_scan_finnhub_{date_tag}.json"
        cmd = [
            sys.executable,
            str(SCRIPTS_DIR / "fetch_price_api.py"),
            "--quotes-only",
            "--symbols", ",".join(finnhub_syms_norm),
            "--output", str(out),
            "--token", finnhub_key,
        ]
        code = run(cmd)
        if code != 0:
            print(f"⚠️ Finnhub 调用失败（exit {code}），对应 ticker 可能无价格数据")

    # ── Tushare（A股）───────────────────────────────────────────────────────
    if tushare_syms:
        out = out_dir / f"price_scan_tushare_{date_tag}.json"
        cmd = [
            sys.executable,
            str(SCRIPTS_DIR / "fetch_price_tushare.py"),
            "--symbols", ",".join(tushare_syms),
            "--token", tushare_token,
            "--output", str(out),
        ]
        code = run(cmd)
        if code != 0:
            print(f"⚠️ Tushare 调用失败（exit {code}），对应 ticker 可能无价格数据")

    # ── Yahoo（港股 + 兜底）─────────────────────────────────────────────────
    if yahoo_syms_norm:
        out = out_dir / f"price_scan_yahoo_{date_tag}.json"
        cmd = [
            sys.executable,
            str(SCRIPTS_DIR / "fetch_price_yahoo.py"),
            "--symbols", ",".join(yahoo_syms_norm),
            "--output", str(out),
        ]
        code = run(cmd)
        if code != 0:
            print(f"⚠️ Yahoo 调用失败（exit {code}），对应 ticker 可能无价格数据")

    print("✅ 路由完成")


if __name__ == "__main__":
    main()
