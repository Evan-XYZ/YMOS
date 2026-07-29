#!/usr/bin/env python3
"""
Finnhub 实时价格数据获取工具

用途：为投研中台补充价格维度数据
- 实时行情：持仓 + 关注列表当前价格、涨跌幅
- 个股新闻：关注标的最新事件
- 盈利日历：未来7天内关注标的的财报日期

API 文档：https://finnhub.io/docs/api/
"""

import urllib.request
import urllib.parse
import urllib.error
import argparse
import json
import ssl
import re
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── API 配置 ──────────────────────────────────────────────────
API_KEY = os.getenv("FINNHUB_API_KEY", "")
FINNHUB_BASE = "https://finnhub.io/api/v1"

# ── 兜底关注列表 ──────────────────────────────────────────────
# 正常情况下不会用到这里：脚本优先用 --symbols 或 --symbols-from-dir
# （由持仓/Watchlist 状态机自动喂入）。只有两者都没给时，才回落到这份默认清单。
#
# 想改成自己的：设环境变量 YMOS_DEFAULT_SYMBOLS="AAPL,MSFT,..." 即可，不用改代码。
# 注意 A 股不在 Finnhub 覆盖范围内，会自动走 Tushare / Yahoo 路由。
DEFAULT_WATCHLIST = ["NVDA", "AMD", "TSM"]   # 仅作占位示例，无任何推荐含义

WATCHLIST = [
    s.strip().upper() for s in os.getenv("YMOS_DEFAULT_SYMBOLS", "").split(",") if s.strip()
] or DEFAULT_WATCHLIST

# 市场新闻分类
NEWS_CATEGORIES = ["general", "merger"]


# ─────────────────────────────────────────────────────────────
def parse_symbols(raw_value):
    if not raw_value:
        return []
    return [item.strip().upper() for item in raw_value.split(",") if item.strip()]


def is_valid_ticker(name: str) -> bool:
    # 允许常见 ticker 形式：AAPL / BRK.B / 0700.HK / BINANCE:BTCUSDT（crypto）
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:\-]{0,25}", name))


def load_symbols_from_dirs(root_dirs):
    symbols = []
    for root_dir in root_dirs:
        path = Path(root_dir)
        if not path.exists():
            continue
        for child in sorted(path.iterdir()):
            if not child.is_dir():
                continue
            # 跳过归档/系统目录
            if child.name.startswith("_"):
                continue
            if not is_valid_ticker(child.name):
                continue
            symbols.append(child.name.upper())
    return symbols


def resolve_symbols(args):
    symbols = []
    if args.symbols:
        symbols.extend(parse_symbols(args.symbols))
    if args.symbols_from_dir:
        symbols.extend(load_symbols_from_dirs(args.symbols_from_dir))
    if not symbols:
        symbols.extend(WATCHLIST)

    deduped = []
    seen = set()
    for symbol in symbols:
        if symbol not in seen:
            seen.add(symbol)
            deduped.append(symbol)
    return deduped


def finnhub_get(endpoint, params=None):
    """Finnhub GET 请求（token 通过 URL 参数认证）"""
    if not API_KEY:
        print("   ❌ 缺少 FINNHUB_API_KEY（可通过环境变量或 --token 提供）")
        return None

    query = {"token": API_KEY}
    if params:
        query.update(params)

    url = FINNHUB_BASE + endpoint + "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "YMOS-Personal/1.0", "Accept": "application/json"},
        method="GET",
    )

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"   ❌ HTTP {e.code} — {endpoint}")
        if e.code == 429:
            print("     → 超出频率限制（60次/分钟），稍后再试")
        return None
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
        return None


def fetch_quotes(symbols):
    """
    实时行情  GET /quote
    返回：当前价(c)、涨跌额(d)、涨跌幅%(dp)、今高(h)、今低(l)、昨收(pc)
    """
    print(f"\n📊 实时行情：{', '.join(symbols)}")
    quotes = []

    for symbol in symbols:
        data = finnhub_get("/quote", {"symbol": symbol})

        if not data or data.get("c", 0) == 0:
            print(f"   ⚠️  {symbol}: 暂无报价（非交易时段）")
            continue

        pct = data.get("dp", 0) or 0
        sign = "+" if pct >= 0 else ""
        arrow = "📈" if pct >= 0 else "📉"
        print(f"   {arrow} {symbol:<6} ${data['c']:.2f}  {sign}{pct:.2f}%"
              f"  |  高 ${data['h']:.2f}  低 ${data['l']:.2f}  昨收 ${data['pc']:.2f}")

        quotes.append({
            "type": "quote",
            "symbol": symbol,
            "price":      data.get("c"),
            "change":     data.get("d"),
            "change_pct": data.get("dp"),
            "high":       data.get("h"),
            "low":        data.get("l"),
            "open":       data.get("o"),
            "prev_close": data.get("pc"),
            "timestamp":  data.get("t"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })

    return quotes


def fetch_company_news(symbol, days=1):
    """
    个股新闻  GET /company-news
    参数：symbol + from/to 日期范围（YYYY-MM-DD）
    """
    date_to   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_from = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    data = finnhub_get("/company-news", {
        "symbol": symbol,
        "from":   date_from,
        "to":     date_to,
    })

    if not data or not isinstance(data, list):
        return []

    return [
        {
            "type":     "company_news",
            "symbol":   symbol,
            "category": item.get("category", ""),
            "headline": item.get("headline", ""),
            "summary":  item.get("summary", ""),
            "source":   item.get("source", ""),
            "url":      item.get("url", ""),
            "datetime": datetime.fromtimestamp(
                item.get("datetime", 0), tz=timezone.utc
            ).isoformat(),
        }
        for item in data
    ]


def fetch_market_news(days=1):
    """
    市场大盘新闻  GET /news
    category 可选：general | forex | crypto | merger
    """
    print(f"\n📰 市场大盘新闻（最近 {days} 天）...")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()

    all_items = []
    for category in NEWS_CATEGORIES:
        data = finnhub_get("/news", {"category": category})

        if not data or not isinstance(data, list):
            continue

        filtered = [
            {
                "type":     "market_news",
                "category": category,
                "headline": item.get("headline", ""),
                "summary":  item.get("summary", ""),
                "source":   item.get("source", ""),
                "url":      item.get("url", ""),
                "datetime": datetime.fromtimestamp(
                    item.get("datetime", 0), tz=timezone.utc
                ).isoformat(),
                "related":  item.get("related", ""),
            }
            for item in data
            if item.get("datetime", 0) >= cutoff
        ]
        all_items.extend(filtered)
        print(f"   [{category}] → {len(filtered)} 条")

    return all_items


def fetch_earnings_calendar(symbols, days=7):
    """
    盈利日历  GET /calendar/earnings
    参数：from/to 日期范围
    返回 earningsCalendar 数组，过滤 WATCHLIST 内标的
    """
    print(f"\n📅 盈利日历（未来 {days} 天，仅关注列表）...")
    date_from = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_to   = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")

    data = finnhub_get("/calendar/earnings", {"from": date_from, "to": date_to})

    if not data or "earningsCalendar" not in data:
        print("   — 无数据")
        return []

    hits = [
        {
            "type":             "earnings",
            "symbol":           e.get("symbol"),
            "date":             e.get("date"),
            "eps_estimate":     e.get("epsEstimate"),
            "revenue_estimate": e.get("revenueEstimate"),
            "quarter":          e.get("quarter"),
            "year":             e.get("year"),
        }
        for e in data["earningsCalendar"]
        if e.get("symbol") in symbols
    ]

    if hits:
        print(f"   ⚠️  关注列表内有财报发布：{[e['symbol'] for e in hits]}")
    else:
        print(f"   — 未来 {days} 天内关注列表无财报发布")

    return hits


# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Finnhub 价格数据获取"
    )
    parser.add_argument(
        "days", type=float, nargs="?", default=1,
        help="获取最近 N 天的新闻数据（默认: 1）",
    )
    parser.add_argument(
        "--output", default="finnhub_data.json",
        help="输出文件路径（默认: finnhub_data.json）",
    )
    parser.add_argument(
        "--symbols", default="",
        help="逗号分隔的 ticker 列表",
    )
    parser.add_argument(
        "--symbols-from-dir", action="append", default=[],
        help="从目录名读取 ticker，可重复传入",
    )
    parser.add_argument(
        "--quotes-only", action="store_true",
        help="只获取实时行情，跳过新闻和盈利日历（快速查价模式）",
    )
    parser.add_argument(
        "--token", default="",
        help="Finnhub API Key（可选；若不传则读取环境变量 FINNHUB_API_KEY）",
    )
    args = parser.parse_args()

    global API_KEY
    if args.token:
        API_KEY = args.token

    symbols = resolve_symbols(args)

    print("=" * 55)
    print("Finnhub 价格数据工具")
    print(f"关注列表: {', '.join(symbols)}")
    print("=" * 55)

    all_data = []

    # 1. 实时行情（总是跑）
    all_data.extend(fetch_quotes(symbols))

    if not args.quotes_only:
        # 2. 个股新闻
        print(f"\n🔍 个股新闻（最近 {args.days} 天）...")
        for symbol in symbols:
            news = fetch_company_news(symbol, args.days)
            print(f"   [{symbol}] → {len(news)} 条")
            all_data.extend(news)

        # 3. 市场大盘新闻
        all_data.extend(fetch_market_news(args.days))

        # 4. 盈利日历
        all_data.extend(fetch_earnings_calendar(symbols, days=7))

    # 输出
    result = {
        "source":       "Finnhub.io",
        "watchlist":    symbols,
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "time_range_days": args.days,
        "count":        len(all_data),
        "data":         all_data,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    quote_n   = sum(1 for d in all_data if d["type"] == "quote")
    news_n    = sum(1 for d in all_data if d["type"].endswith("news"))
    earning_n = sum(1 for d in all_data if d["type"] == "earnings")

    print(f"\n💾 已保存：{args.output}")
    print(f"✅ 行情 {quote_n} 支 | 新闻 {news_n} 条 | 盈利日历 {earning_n} 条")


if __name__ == "__main__":
    main()
