#!/usr/bin/env python3
"""
YMOS 价格路由器 v2

定位：
1) 先沿用原主路由：美股/Crypto -> Finnhub, A股 -> Tushare, 港股 -> Yahoo
2) 对主路由失败/缺失的 symbol，追加用「问财行情数据查询」做 fallback
3) 额外输出一个 price_scan_iwencai_YYYYMMDD.json，作为补丁层结果

注意：
- 问财 fallback 更适合 股票 / ETF / 指数 / A股特色字段，不建议作为 Crypto 主源
- 本脚本不替换旧路由，只是增强版
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parents[2]

sys.path.insert(0, str(SCRIPTS_DIR))
from env_loader import load_dotenv
from skill_resolver import resolve_skill_cli

CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "AVAX", "DOT"}

COMMON_INDEX_QUERY_MAP = {
    "000001.SH": "上证指数 最新价格，涨跌幅，成交额",
    "399001.SZ": "深证成指 最新价格，涨跌幅，成交额",
    "399006.SZ": "创业板指 最新价格，涨跌幅，成交额",
    "000300.SH": "沪深300 最新价格，涨跌幅，成交额",
    "000688.SH": "科创50 最新价格，涨跌幅，成交额",
    "000852.SH": "中证1000 最新价格，涨跌幅，成交额",
    "000905.SH": "中证500 最新价格，涨跌幅，成交额",
    "000016.SH": "上证50 最新价格，涨跌幅，成交额",
    "899050.BJ": "北证50 最新价格，涨跌幅，成交额",
}


def parse_symbols(raw: str) -> list[str]:
    if not raw:
        return []
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def classify(symbol: str) -> str:
    if symbol.endswith((".SS", ".SZ", ".SH")):
        return "tushare"
    if symbol.endswith(".HK"):
        return "yahoo"
    return "finnhub"


def normalize_for_finnhub(symbol: str) -> str:
    s = symbol.upper()
    if s == "BTC": return "BINANCE:BTCUSDT"
    if s == "ETH": return "BINANCE:ETHUSDT"
    if s == "SOL": return "BINANCE:SOLUSDT"
    if s == "DOGE": return "BINANCE:DOGEUSDT"
    if s == "XRP": return "BINANCE:XRPUSDT"
    if s == "ADA": return "BINANCE:ADAUSDT"
    if s == "AVAX": return "BINANCE:AVAXUSDT"
    if s == "DOT": return "BINANCE:DOTUSDT"
    return symbol


def normalize_for_yahoo(symbol: str) -> str:
    s = symbol.upper()
    if s == "BTC": return "BTC-USD"
    if s == "ETH": return "ETH-USD"
    if s == "SOL": return "SOL-USD"
    if s == "DOGE": return "DOGE-USD"
    if s == "XRP": return "XRP-USD"
    if s == "ADA": return "ADA-USD"
    if s == "AVAX": return "AVAX-USD"
    if s == "DOT": return "DOT-USD"
    return symbol


def run(cmd: list[str]) -> int:
    return subprocess.call(cmd, cwd=str(ROOT))


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def success_symbols_from_finnhub(path: Path) -> set[str]:
    raw = load_json(path) or {}
    ok = set()
    for item in raw.get("data", []):
        if item.get("type") == "quote" and item.get("symbol"):
            sym = str(item["symbol"]).upper()
            # map crypto source symbol back to state symbol when possible
            reverse = {
                "BINANCE:BTCUSDT": "BTC",
                "BINANCE:ETHUSDT": "ETH",
                "BINANCE:SOLUSDT": "SOL",
                "BINANCE:DOGEUSDT": "DOGE",
                "BINANCE:XRPUSDT": "XRP",
                "BINANCE:ADAUSDT": "ADA",
                "BINANCE:AVAXUSDT": "AVAX",
                "BINANCE:DOTUSDT": "DOT",
            }
            ok.add(reverse.get(sym, sym))
    return ok


def success_symbols_from_generic(path: Path) -> set[str]:
    raw = load_json(path) or {}
    ok = set()
    for item in raw.get("data", []):
        if item.get("ok") and item.get("symbol"):
            sym = str(item["symbol"]).upper()
            reverse = {
                "BTC-USD": "BTC",
                "ETH-USD": "ETH",
                "SOL-USD": "SOL",
                "DOGE-USD": "DOGE",
                "XRP-USD": "XRP",
                "ADA-USD": "ADA",
                "AVAX-USD": "AVAX",
                "DOT-USD": "DOT",
            }
            ok.add(reverse.get(sym, sym))
    return ok


def build_iwencai_query(symbol: str) -> str | None:
    s = symbol.upper()
    if s in CRYPTO_SYMBOLS:
        return None
    if s in COMMON_INDEX_QUERY_MAP:
        return COMMON_INDEX_QUERY_MAP[s]
    if s.endswith((".SS", ".SZ", ".SH", ".HK")):
        code = s.split(".")[0]
        return f"{code} 最新价格，涨跌幅，成交额"
    return f"{s} 最新价格，涨跌幅，成交额"


def extract_iwencai_item(symbol: str, row: dict[str, Any]) -> dict[str, Any]:
    # 尽量做字段归一化；问财字段不稳定，所以这里走 best-effort
    def first_key(*names: str):
        for n in names:
            if n in row:
                return row.get(n)
        return None

    price = first_key("最新价", "最新收盘价", "最新单位净值", "收盘价")
    pct = first_key("最新涨跌幅", "涨跌幅", "涨跌幅[20260417]", "最新涨跌幅:前复权")
    amount = first_key("成交额", "成交额[20260417]", "最新成交额")
    code = first_key("股票代码", "基金代码", "指数代码")
    name = first_key("股票简称", "基金简称", "指数简称")

    return {
        "symbol": symbol,
        "ok": price is not None,
        "source": "iwencai_market_query",
        "resolved_code": code,
        "resolved_name": name,
        "last_close": price,
        "pct_chg": pct,
        "amount": amount,
        "raw": row,
    }


def query_iwencai(symbols: list[str], output: Path) -> None:
    cli = resolve_skill_cli("hithink-market-query", "行情数据查询/hithink-market-query")
    if cli is None:
        cli = Path("/nonexistent")   # 走下方的 not exists 分支，优雅降级
    data: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    if not cli.exists():
        output.write_text(json.dumps({
            "source": "iwencai_market_query",
            "ok": False,
            "error": f"cli_not_found: {cli}",
            "data": [],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    env = os.environ.copy()
    for sym in symbols:
        query = build_iwencai_query(sym)
        if not query:
            skipped.append({"symbol": sym, "reason": "unsupported_for_iwencai_fallback"})
            continue

        cmd = [sys.executable, str(cli), "--query", query, "--limit", "10"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(ROOT))
            if proc.returncode != 0:
                data.append({"symbol": sym, "ok": False, "source": "iwencai_market_query", "error": proc.stdout.strip() or proc.stderr.strip()})
                continue
            raw = json.loads(proc.stdout)
            rows = raw.get("datas", []) or []
            if not rows:
                data.append({"symbol": sym, "ok": False, "source": "iwencai_market_query", "error": "empty_rows", "query": query})
                continue
            data.append(extract_iwencai_item(sym, rows[0]))
        except Exception as e:
            data.append({"symbol": sym, "ok": False, "source": "iwencai_market_query", "error": str(e)})

    out = {
        "source": "iwencai_market_query",
        "fetched_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "count": len(data),
        "skipped": skipped,
        "data": data,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    load_dotenv()

    p = argparse.ArgumentParser(description="YMOS 价格路由器 v2（带问财 fallback）")
    p.add_argument("--symbols", required=True)
    p.add_argument("--output-dir", default="Report/投资雷达/Raw_Data")
    p.add_argument("--date-tag", default="")
    p.add_argument("--finnhub-token", default="")
    p.add_argument("--tushare-token", default="")
    args = p.parse_args()

    symbols = parse_symbols(args.symbols)
    if not symbols:
        raise SystemExit("symbols 不能为空")

    finnhub_key = args.finnhub_token or os.getenv("FINNHUB_API_KEY", "")
    tushare_token = args.tushare_token or os.getenv("TUSHARE_TOKEN", "")

    finnhub_syms: list[str] = []
    tushare_syms: list[str] = []
    yahoo_syms: list[str] = []

    for s in symbols:
        bucket = classify(s)
        if bucket == "finnhub":
            if finnhub_key:
                finnhub_syms.append(s)
            else:
                yahoo_syms.append(s)
        elif bucket == "tushare":
            if tushare_token:
                tushare_syms.append(s)
            else:
                yahoo_syms.append(s)
        else:
            yahoo_syms.append(s)

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    date_tag = args.date_tag or "latest"

    print("📡 价格路由 v2 分流结果：")
    print(f"   Finnhub  ({len(finnhub_syms)}): {finnhub_syms or '—'}")
    print(f"   Tushare  ({len(tushare_syms)}): {tushare_syms or '—'}")
    print(f"   Yahoo    ({len(yahoo_syms)}): {yahoo_syms or '—'}")
    print()

    # Primary routes
    finnhub_out = out_dir / f"price_scan_finnhub_{date_tag}.json"
    tushare_out = out_dir / f"price_scan_tushare_{date_tag}.json"
    yahoo_out   = out_dir / f"price_scan_yahoo_{date_tag}.json"
    iwencai_out = out_dir / f"price_scan_iwencai_{date_tag}.json"

    if finnhub_syms:
        cmd = [sys.executable, str(SCRIPTS_DIR / "fetch_price_api.py"), "--quotes-only", "--symbols", ",".join(normalize_for_finnhub(s) for s in finnhub_syms), "--output", str(finnhub_out), "--token", finnhub_key]
        code = run(cmd)
        if code != 0:
            print(f"⚠️ Finnhub 调用失败（exit {code}）")

    if tushare_syms:
        cmd = [sys.executable, str(SCRIPTS_DIR / "fetch_price_tushare.py"), "--symbols", ",".join(tushare_syms), "--token", tushare_token, "--output", str(tushare_out)]
        code = run(cmd)
        if code != 0:
            print(f"⚠️ Tushare 调用失败（exit {code}）")

    if yahoo_syms:
        cmd = [sys.executable, str(SCRIPTS_DIR / "fetch_price_yahoo.py"), "--symbols", ",".join(normalize_for_yahoo(s) for s in yahoo_syms), "--output", str(yahoo_out)]
        code = run(cmd)
        if code != 0:
            print(f"⚠️ Yahoo 调用失败（exit {code}）")

    # detect failures / missing
    ok = set()
    if finnhub_out.exists():
        ok |= success_symbols_from_finnhub(finnhub_out)
    if tushare_out.exists():
        ok |= success_symbols_from_generic(tushare_out)
    if yahoo_out.exists():
        ok |= success_symbols_from_generic(yahoo_out)

    missing = [s for s in symbols if s not in ok]
    print(f"\n🧩 主路由成功: {sorted(ok) if ok else '—'}")
    print(f"🩹 待问财 fallback: {missing or '—'}")

    if missing:
        query_iwencai(missing, iwencai_out)
        print(f"💾 已保存问财 fallback：{iwencai_out}")
    else:
        iwencai_out.write_text(json.dumps({
            "source": "iwencai_market_query",
            "fetched_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "count": 0,
            "data": [],
            "note": "no_fallback_needed",
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("✅ 路由 v2 完成")


if __name__ == "__main__":
    main()
