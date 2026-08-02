#!/usr/bin/env python3
"""
Finnhub 持仓个股新闻拉取脚本（company-news 模式）

策略说明（2026-03-16 重构）：
  原版使用 category=general 全量拉取，但 general 新闻与 yongmai.xyz API
  数据高度重合，且 related 字段在宏观新闻中几乎全为空，命中率为 0。
  新版改为对【持仓标的】单独调用 /company-news 接口，精准命中个股新闻。

接口限制（Finnhub 免费 Key）：
  - 60 calls/min。持仓通常 ≤5 个，每日调用 5 次完全够用。
  - /company-news 只支持美股/Crypto Ticker，A股/港股不支持，自动过滤。
  - Watchlist 不启用个股新闻（优先级低 + 节省 rate limit）。

用法：
  python3 scripts/fetch_finnhub_news.py \
    --hours 24 \
    --output "Report/市场洞察/Raw_Data/YYYY-MM/finnhub_news_YYYYMMDD.json"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parents[1]  # Eyes/scripts → Eyes → YMOS

sys.path.insert(0, str(SCRIPTS_DIR))
from env_loader import load_dotenv

# 触发 P15 深度分析的关键词
P15_KEYWORDS = {
    "earnings", "revenue", "guidance", "acquisition", "merger",
    "bankruptcy", "layoff", "recall", "investigation", "settlement",
    "partnership", "contract", "upgrade", "downgrade", "beat", "miss",
}


# ── Ticker 提取 ────────────────────────────────────────────────────────────

def extract_tickers_from_state_machine(filepath: Path, us_only: bool = True) -> set[str]:
    """
    从 Markdown 状态机表格中提取 Ticker 列。
    us_only=True 时只返回美股/Crypto（排除 .HK/.SS/.SZ 后缀）。
    """
    if not filepath.exists():
        return set()

    text = filepath.read_text(encoding="utf-8")
    tickers: set[str] = set()
    in_table = False
    ticker_col_idx = -1

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            in_table = False
            continue

        # 模板中的示例行只用于说明格式，不得进入真实数据链。
        normalized_line = line.replace("（", "(").replace("）", ")")
        if "(示例)" in normalized_line or "demo_only" in normalized_line.lower():
            continue

        cols = [c.strip() for c in line.split("|") if c.strip()]

        if not in_table:
            lowered = [col.lower() for col in cols]
            for header in ("ticker", "代码", "标的"):
                if header in lowered:
                    ticker_col_idx = lowered.index(header)
                    in_table = True
                    break
            continue

        if all(c.replace("-", "").replace(":", "") == "" for c in cols):
            continue

        if 0 <= ticker_col_idx < len(cols):
            val = cols[ticker_col_idx].strip().upper()
            if val and not val.startswith(":") and val != "---" and re.fullmatch(r"[A-Z0-9.:-]+", val):
                if us_only:
                    if not any(val.endswith(s) for s in (".SS", ".SZ", ".HK")):
                        tickers.add(val)
                else:
                    tickers.add(val)

    return tickers


def load_holding_tickers() -> list[str]:
    """仅从【持仓状态机】加载美股/Crypto Ticker（Watchlist 不拉个股新闻）。"""
    holding_path = ROOT / "持仓与关注" / "持仓_状态机.md"
    tickers = sorted(extract_tickers_from_state_machine(holding_path, us_only=True))
    if tickers:
        print(f"📋 持仓美股/Crypto ticker（将拉取个股新闻）: {', '.join(tickers)}")
    else:
        print("⚠️ 未从持仓状态机中找到美股/Crypto ticker，跳过个股新闻拉取。")
    return tickers


# ── API 请求 ───────────────────────────────────────────────────────────────

def fetch_company_news(ticker: str, api_key: str, from_date: str, to_date: str) -> list[dict]:
    """
    调用 Finnhub /company-news 接口获取单个标的的个股新闻。
    from_date / to_date 格式：YYYY-MM-DD
    """
    url = (
        f"https://finnhub.io/api/v1/company-news"
        f"?symbol={ticker}&from={from_date}&to={to_date}&token={api_key}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "YMOS/4.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  ❌ {ticker} HTTP {e.code}: {e.reason}")
        return []
    except Exception as e:
        print(f"  ❌ {ticker} 请求失败: {e}")
        return []


# ── 处理与去重 ──────────────────────────────────────────────────────────────

def enrich_article(item: dict, ticker: str, cutoff_ts: float) -> dict | None:
    """给单条新闻打标签，过滤掉超时间窗口的条目。"""
    ts = item.get("datetime", 0)
    if ts < cutoff_ts:
        return None

    headline = item.get("headline", "")
    summary  = item.get("summary", "")
    text_lc  = (headline + " " + summary).lower()

    return {
        "ticker":           ticker,
        "datetime_ts":      ts,
        "datetime_readable": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source":           item.get("source", ""),
        "headline":         headline,
        "summary":          summary,
        "url":              item.get("url", ""),
        "image":            item.get("image", ""),
        "p15_trigger":      any(kw in text_lc for kw in P15_KEYWORDS),
    }


def deduplicate(articles: list[dict]) -> list[dict]:
    """headline 前 40 字符相同视为重复，保留最早一条。"""
    seen: dict[str, dict] = {}
    for art in sorted(articles, key=lambda x: x["datetime_ts"]):
        key = re.sub(r"\s+", " ", art["headline"][:40].lower()).strip()
        if key not in seen:
            seen[key] = art
    return sorted(seen.values(), key=lambda x: x["datetime_ts"], reverse=True)


# ── 主函数 ─────────────────────────────────────────────────────────────────

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Finnhub 持仓个股新闻拉取（company-news，持仓专用）"
    )
    parser.add_argument("--output", default="finnhub_news.json", help="输出文件路径")
    parser.add_argument("--hours", type=int, default=24, help="回溯小时数，默认 24")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("FINNHUB_API_KEY", ""),
        help="Finnhub API Key，也可通过环境变量 FINNHUB_API_KEY 传入",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("⚠️ 未提供 Finnhub API Key，跳过个股新闻拉取。")
        print("   如需启用，请在 .env 中配置 FINNHUB_API_KEY")
        sys.exit(0)

    holding_tickers = load_holding_tickers()
    if not holding_tickers:
        print("⚠️ 无持仓美股标的，退出。")
        sys.exit(0)

    now_utc   = datetime.now(timezone.utc)
    cutoff_ts = (now_utc - timedelta(hours=args.hours)).timestamp()
    to_date   = now_utc.strftime("%Y-%m-%d")
    from_date = (now_utc - timedelta(hours=args.hours)).strftime("%Y-%m-%d")

    print(f"📡 拉取个股新闻（过去 {args.hours}h：{from_date} ~ {to_date}）")
    print(f"   ⚠️  Rate limit 提示：Finnhub 免费 key = 60 calls/min，当前持仓 {len(holding_tickers)} 个标的")

    all_articles: list[dict] = []
    ticker_counts: dict[str, int] = {}

    for ticker in holding_tickers:
        print(f"  → {ticker}...", end=" ", flush=True)
        raw = fetch_company_news(ticker, args.api_key, from_date, to_date)
        enriched = [enrich_article(item, ticker, cutoff_ts) for item in raw]
        enriched = [a for a in enriched if a is not None]
        ticker_counts[ticker] = len(enriched)
        all_articles.extend(enriched)
        print(f"{len(enriched)} 条")

    # 去重（跨标的同一事件只保留一条）
    deduped = deduplicate(all_articles)
    p15_count = sum(1 for a in deduped if a.get("p15_trigger"))

    output = {
        "meta": {
            "source":          "Finnhub company-news",
            "mode":            "holdings_only",
            "hours_back":      args.hours,
            "date_range":      f"{from_date} ~ {to_date}",
            "generated_at":    now_utc.strftime("%Y-%m-%d %H:%M UTC"),
            "holding_tickers": holding_tickers,
            "note":            "Watchlist 不拉个股新闻（节省 rate limit，Watchlist 由 yongmai API 覆盖）",
            "rate_limit_note": "Finnhub 免费 key = 60 calls/min；当前持仓标的数量决定调用次数",
            "counts": {
                "total_raw":          sum(ticker_counts.values()),
                "after_dedup":        len(deduped),
                "p15_trigger":        p15_count,
                "by_ticker":          ticker_counts,
            },
        },
        "articles": deduped,
    }

    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 已保存：{args.output}")
    print(f"   总计：{len(deduped)} 条（去重后）｜其中 p15_trigger={p15_count} 条建议深度分析")


if __name__ == "__main__":
    main()
