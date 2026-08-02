#!/usr/bin/env python3
"""
Yahoo Finance A股/港股/美股轻量行情脚本（原生 V8 API，无第三方库依赖）

用途：为 YMOS 提供最小可行价格数据补充（A股/港股优先）。
- 支持代码：600519.SS / 000001.SZ / AAPL / 0700.HK / 688981.SS
- 输出：最新报价 + 最近N日OHLCV

实现说明（2026-03-16 重构）：
  原版使用 yfinance 库，在部分 A股（科创板/主板）出现 empty_history 问题。
  新版改为直接调用 Yahoo Finance V8 原生 Chart API（urllib 标准库），
  稳定性更高，避免 yfinance 版本兼容性问题。
  API 端点：https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}

已知限制：
  Yahoo Finance 对部分科创板标的（688xxx.SS）数据有时存在延迟或精度差异，
  如价格明显偏离，建议以东方财富/雪球等国内源人工核对。
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def parse_symbols(raw: str) -> list[str]:
    if not raw:
        return []
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def load_symbols_from_dirs(root_dirs: list[str]) -> list[str]:
    out = []
    for d in root_dirs:
        p = Path(d)
        if not p.exists():
            continue
        for child in sorted(p.iterdir()):
            if child.is_dir() and not child.name.startswith("_"):
                out.append(child.name.upper())
    return out


_PERIOD_TO_RANGE = {
    "1d": "1d", "5d": "5d", "1mo": "1mo",
    "3mo": "3mo", "6mo": "6mo", "1y": "1y", "2y": "2y", "5y": "5y",
}


def fetch_one(symbol: str, period: str, interval: str, retries: int) -> dict:
    """
    调用 Yahoo Finance V8 Chart API 获取单个标的行情。
    返回 {"symbol", "ok", "last_close", ...} 或 {"symbol", "ok": False, "error": ...}
    """
    yf_range = _PERIOD_TO_RANGE.get(period, "1mo")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval={interval}&range={yf_range}"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode())

            result = payload.get("chart", {}).get("result")
            if not result:
                err = payload.get("chart", {}).get("error", {})
                return {"symbol": symbol, "ok": False, "error": str(err) or "empty_result"}

            r = result[0]
            meta = r.get("meta", {})
            timestamps = r.get("timestamp", [])
            indicators = r.get("indicators", {})
            quotes = indicators.get("quote", [{}])[0]

            opens   = quotes.get("open",   [])
            highs   = quotes.get("high",   [])
            lows    = quotes.get("low",    [])
            closes  = quotes.get("close",  [])
            volumes = quotes.get("volume", [])

            if not closes or all(c is None for c in closes):
                return {"symbol": symbol, "ok": False, "error": "empty_history"}

            # regularMarketPrice 比 K线最后一根 close 更实时（盘中也有效）
            current_price = meta.get("regularMarketPrice") or next(
                (c for c in reversed(closes) if c is not None), 0
            )

            def _safe(arr, i, default=0.0):
                try:
                    v = arr[i]
                    return float(v) if v is not None else default
                except (IndexError, TypeError):
                    return default

            # 最多取末尾 10 根 K线
            n = len(timestamps)
            start_i = max(0, n - 10)
            rows = []
            for i in range(start_i, n):
                dt = datetime.fromtimestamp(timestamps[i], tz=timezone.utc).isoformat()
                rows.append({
                    "t":      dt,
                    "open":   _safe(opens,   i),
                    "high":   _safe(highs,   i),
                    "low":    _safe(lows,    i),
                    "close":  _safe(closes,  i),
                    "volume": _safe(volumes, i),
                })

            last_i = n - 1
            return {
                "symbol":      symbol,
                "ok":          True,
                "last_close":  float(current_price),
                "last_open":   _safe(opens,   last_i),
                "last_high":   _safe(highs,   last_i),
                "last_low":    _safe(lows,    last_i),
                "last_volume": _safe(volumes, last_i),
                "bars":        rows,
            }

        except Exception as e:
            last_err = str(e)
            if attempt < retries - 1:
                time.sleep(1.2 * (attempt + 1))

    return {"symbol": symbol, "ok": False, "error": last_err or "unknown_error"}


def main():
    p = argparse.ArgumentParser(description="Yahoo Finance V8 原生行情抓取（A股/港股/美股）")
    p.add_argument("--symbols", default="", help="逗号分隔代码，如 600519.SS,000001.SZ,0700.HK")
    p.add_argument("--symbols-from-dir", action="append", default=[], help="从目录子文件夹名读取ticker")
    p.add_argument("--period", default="1mo", help="历史范围，默认 1mo")
    p.add_argument("--interval", default="1d", help="K线粒度，默认 1d")
    p.add_argument("--retries", type=int, default=3, help="失败重试次数")
    p.add_argument("--output", default="yahoo_price_data.json", help="输出JSON路径")
    args = p.parse_args()

    symbols = parse_symbols(args.symbols)
    symbols.extend(load_symbols_from_dirs(args.symbols_from_dir))

    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    symbols = unique

    if not symbols:
        raise SystemExit("请提供 --symbols 或 --symbols-from-dir")

    data = [fetch_one(s, args.period, args.interval, args.retries) for s in symbols]

    for item in data:
        status = "✅" if item.get("ok") else "❌"
        if item.get("ok"):
            print(f"  {status} {item['symbol']:16s} ¥{item['last_close']:.2f}")
        else:
            print(f"  {status} {item['symbol']:16s} ERROR: {item.get('error')}")

    out = {
        "source":     "Yahoo Finance V8 Chart API",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count":      len(data),
        "symbols":    symbols,
        "period":     args.period,
        "interval":   args.interval,
        "data":       data,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for x in data if x.get("ok"))
    print(f"\n💾 已保存：{out_path}  ({ok}/{len(data)} 成功)")


if __name__ == "__main__":
    main()
