#!/usr/bin/env python3
"""腾讯财经 A 股 / 港股 / 美股免 Key 快照行情（零第三方依赖）。

输出结构与 ``fetch_price_yahoo.py`` 保持兼容，可独立调用，也可由
``fetch_price_router.py`` 统一分流。腾讯接口只用于价格快照，不提供 YMOS
所需的历史 K 线；Crypto 和不支持的 Ticker 会明确返回失败，交给路由器兜底。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


QUOTE_URL = "https://qt.gtimg.cn/q="
DEFAULT_BATCH_SIZE = 50
CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "AVAX", "DOT"}


def parse_symbols(raw: str) -> list[str]:
    if not raw:
        return []
    return [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]


def load_symbols_from_dirs(root_dirs: list[str]) -> list[str]:
    output = []
    for raw_dir in root_dirs:
        directory = Path(raw_dir)
        if not directory.exists():
            continue
        for child in sorted(directory.iterdir()):
            if child.is_dir() and not child.name.startswith("_"):
                output.append(child.name.upper())
    return output


def tencent_code(symbol: str) -> str | None:
    """把 YMOS Ticker 转成腾讯行情代码。"""
    symbol = (symbol or "").strip().upper()
    if not symbol or symbol in CRYPTO_SYMBOLS or symbol.endswith("-USD") or symbol.startswith("^"):
        return None
    if re.fullmatch(r"\d{6}\.(SS|SH)", symbol):
        return "sh" + symbol[:6]
    if re.fullmatch(r"\d{6}\.SZ", symbol):
        return "sz" + symbol[:6]
    if re.fullmatch(r"\d{6}\.BJ", symbol):
        return "bj" + symbol[:6]
    if re.fullmatch(r"\d{1,5}\.HK", symbol):
        return "hk" + symbol.split(".", 1)[0].zfill(5)
    symbol = re.sub(r"\.(US|OQ|N|NYSE|NASDAQ)$", "", symbol)
    if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", symbol):
        return "us" + symbol
    return None


def _number(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_quote_text(text: str, code_to_symbol: dict[str, str]) -> dict[str, dict]:
    """解析腾讯 ``v_code=\"~分隔字段\"`` 响应，返回标准化成功记录。"""
    output: dict[str, dict] = {}
    lookup = {code.lower(): symbol for code, symbol in code_to_symbol.items()}
    for match in re.finditer(r'v_([^=]+)="([^"]*)";?', text):
        symbol = lookup.get(match.group(1).lower())
        fields = match.group(2).split("~")
        if symbol is None or len(fields) <= 32:
            continue
        price = _number(fields[3])
        if price is None or price <= 0:
            continue
        pct_chg = _number(fields[32])
        output[symbol] = {
            "symbol": symbol,
            "ok": True,
            "price": price,
            "last_close": price,
            "last_open": _number(fields[5]) or 0.0,
            "last_high": _number(fields[33]) if len(fields) > 33 else 0.0,
            "last_low": _number(fields[34]) if len(fields) > 34 else 0.0,
            "last_volume": _number(fields[6]) or 0.0,
            "pct_chg": pct_chg,
            "quote_time": fields[30] if len(fields) > 30 else "",
            "bars": [],
        }
    return output


def _request_batch(pairs: list[tuple[str, str]], retries: int) -> tuple[dict[str, dict], str | None]:
    code_to_symbol = {code: symbol for symbol, code in pairs}
    request = urllib.request.Request(
        QUOTE_URL + ",".join(code for _, code in pairs),
        headers={
            "User-Agent": "Mozilla/5.0 YMOS-Price-Router/1.0",
            "Referer": "https://gu.qq.com/",
        },
    )
    last_error = None
    for attempt in range(max(1, retries)):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                text = response.read().decode("gb18030", errors="replace")
            return parse_quote_text(text, code_to_symbol), None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
            if attempt < retries - 1:
                time.sleep(1.0 * (attempt + 1))
    return {}, last_error or "request_failed"


def fetch_many(symbols: list[str], retries: int = 3, batch_size: int = DEFAULT_BATCH_SIZE) -> list[dict]:
    """批量取价并保持输入顺序；每个 Ticker 都返回成功或显式失败记录。"""
    unique = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
    results: dict[str, dict] = {}
    supported: list[tuple[str, str]] = []
    for symbol in unique:
        code = tencent_code(symbol)
        if code is None:
            results[symbol] = {"symbol": symbol, "ok": False, "error": "unsupported_symbol"}
        else:
            supported.append((symbol, code))

    for start in range(0, len(supported), max(1, batch_size)):
        batch = supported[start:start + max(1, batch_size)]
        parsed, error = _request_batch(batch, retries)
        results.update(parsed)
        for symbol, _code in batch:
            results.setdefault(symbol, {
                "symbol": symbol,
                "ok": False,
                "error": error or "empty_quote",
            })
    return [results[symbol] for symbol in unique]


def main() -> int:
    parser = argparse.ArgumentParser(description="腾讯财经免 Key 快照行情（A 股 / 港股 / 美股）")
    parser.add_argument("--symbols", default="", help="逗号分隔，如 AAPL,600519.SS,0700.HK")
    parser.add_argument("--symbols-from-dir", action="append", default=[], help="从目录子文件夹名读取 Ticker")
    parser.add_argument("--retries", type=int, default=3, help="失败重试次数")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="单次请求最多 Ticker 数")
    parser.add_argument("--output", default="tencent_price_data.json", help="输出 JSON 路径")
    args = parser.parse_args()

    symbols = parse_symbols(args.symbols)
    symbols.extend(load_symbols_from_dirs(args.symbols_from_dir))
    symbols = list(dict.fromkeys(symbols))
    if not symbols:
        raise SystemExit("请提供 --symbols 或 --symbols-from-dir")

    data = fetch_many(symbols, retries=args.retries, batch_size=args.batch_size)
    for item in data:
        if item.get("ok"):
            print(f"  ✅ {item['symbol']:16s} {item['last_close']:.4f}")
        else:
            print(f"  ❌ {item['symbol']:16s} ERROR: {item.get('error')}")

    output = {
        "source": "Tencent Finance qt.gtimg.cn",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(data),
        "symbols": symbols,
        "data": data,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    succeeded = sum(1 for item in data if item.get("ok"))
    print(f"\n💾 已保存：{output_path}  ({succeeded}/{len(data)} 成功)")
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
