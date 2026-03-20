#!/usr/bin/env python3
"""
YMOS RSS 数据获取工具（投资场景）

【数据源配置】
- 优先从 scripts/rss_sources.json 加载（支持分类、优先级）
- JSON 不存在时回退到内置默认源（6 个）

【分类体系】
- 美股 / 宏观 / 科技 / Crypto / 深度洞察
- 支持 --category 按分类过滤

【其他场景如何适配】
修改 rss_sources.json 中的源列表即可。核心不变：通过 RSS 自动抓取内容到本地。
"""

import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import argparse
import json
import ssl
import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ============================================================
# 内置默认源（当 rss_sources.json 不存在时使用）
# ============================================================
FALLBACK_SOURCES = [
    {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss", "category": "美股", "priority": "high"},
    {"name": "Bloomberg Tech", "url": "https://feeds.bloomberg.com/technology/news.rss", "category": "科技", "priority": "high"},
    {"name": "CNBC Markets", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", "category": "美股", "priority": "high"},
    {"name": "CNBC Finance", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "category": "宏观", "priority": "medium"},
    {"name": "Seeking Alpha Picks", "url": "https://seekingalpha.com/tag/editors-picks.xml", "category": "深度洞察", "priority": "high"},
    {"name": "Stratechery", "url": "https://stratechery.com/feed/", "category": "深度洞察", "priority": "high"},
]


def load_sources(category_filter=None, config_path=None):
    """加载 RSS 源配置。优先指定路径 → JSON → 内置。"""
    script_dir = Path(__file__).resolve().parent

    if config_path:
        # 使用指定的配置文件
        custom_path = Path(config_path)
        if not custom_path.is_absolute():
            custom_path = script_dir / config_path
        if custom_path.exists():
            try:
                with open(custom_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                sources = config.get("sources", [])
                print(f"📂 从 {custom_path.name} 加载 {len(sources)} 个源")
            except Exception as e:
                print(f"⚠️ 读取 {custom_path.name} 失败: {e}")
                return []
        else:
            print(f"⚠️ 指定的配置文件不存在: {custom_path}")
            return []
    else:
        # 默认：优先 rss_sources.json，回退内置
        json_path = script_dir / "rss_sources.json"
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                sources = config.get("sources", [])
                print(f"📂 从 rss_sources.json 加载 {len(sources)} 个源")
            except Exception as e:
                print(f"⚠️ 读取 rss_sources.json 失败: {e}，使用内置源")
                sources = FALLBACK_SOURCES
        else:
            print("📂 rss_sources.json 不存在，使用内置源（6 个）")
            sources = FALLBACK_SOURCES

    if category_filter:
        sources = [s for s in sources if s.get("category") == category_filter]
        print(f"🔍 按分类 [{category_filter}] 过滤后: {len(sources)} 个源")

    return sources


def fetch_rss(url, days=1):
    """从单个 RSS 源获取数据"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml",
    }

    req = urllib.request.Request(url, headers=headers, method="GET")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            xml_content = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"   ⚠️ 源站限制 (403)，跳过")
            return "BLOCKED_403"
        else:
            print(f"   ❌ HTTP 错误: {e.code} - {e.reason}")
        return None
    except urllib.error.URLError as e:
        print(f"   ❌ 网络错误: {e.reason}")
        return None
    except Exception as e:
        print(f"   ❌ 未知错误: {e}")
        return None

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"   ❌ XML 解析错误: {e}")
        return None

    channel = root.find("channel")
    if channel is None:
        # 尝试 Atom 格式
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)
        if not entries:
            print("   ❌ 未找到 RSS channel 或 Atom entries")
            return None
        # Atom 格式解析
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
        items = []
        for entry in entries:
            title = (entry.findtext("atom:title", "", ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            pub_date = (entry.findtext("atom:published", "", ns) or
                        entry.findtext("atom:updated", "", ns) or "").strip()
            summary = (entry.findtext("atom:summary", "", ns) or
                       entry.findtext("atom:content", "", ns) or "").strip()
            # 时间过滤（简单 ISO 解析）
            if pub_date:
                try:
                    parsed_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    if parsed_date < cutoff_time:
                        continue
                except ValueError:
                    pass
            categories = [cat.get("term", "") for cat in entry.findall("atom:category", ns) if cat.get("term")]
            items.append({
                "title": title, "link": link, "pub_date": pub_date,
                "categories": categories, "description": summary, "content": summary,
            })
        return items

    # RSS 2.0 格式解析
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
    items = []
    for item in channel.findall("item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        description = item.findtext("description", "").strip()

        content = ""
        for child in item:
            if "encoded" in child.tag:
                content = (child.text or "").strip()
                break

        parsed_date = None
        if pub_date:
            try:
                parsed_date = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z")
            except ValueError:
                try:
                    parsed_date = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %Z")
                    parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

        if parsed_date and parsed_date < cutoff_time:
            continue

        categories = [cat.text for cat in item.findall("category") if cat.text]
        items.append({
            "title": title, "link": link, "pub_date": pub_date,
            "categories": categories, "description": description,
            "content": content if content else description,
        })

    return items


def fetch_all_sources(sources, days=1):
    """从所有配置的 RSS 源获取数据"""
    all_items = []
    success_count = 0
    fail_count = 0
    blocked_sources = []

    for src in sources:
        name = src["name"]
        url = src["url"]
        category = src.get("category", "未分类")
        priority = src.get("priority", "medium")

        print(f"\n📡 [{name}] ({category})")
        items = fetch_rss(url, days)

        if items == "BLOCKED_403":
            blocked_sources.append(name)
            fail_count += 1
        elif items:
            for item in items:
                item["source_name"] = name
                item["source_category"] = category
                item["source_priority"] = priority
            all_items.extend(items)
            print(f"   ✅ 获取 {len(items)} 条")
            success_count += 1
        else:
            print(f"   ⚠️ 未获取到数据")
            fail_count += 1

    # 403 汇总提示
    if blocked_sources:
        print(f"\nℹ️ 本次被源站限制 (403) 的源: {len(blocked_sources)} 个（属正常波动，不影响主链）")
        for name in blocked_sources:
            print(f"   - {name}")

    # 分类统计
    categories_summary = {}
    for item in all_items:
        cat = item.get("source_category", "未分类")
        categories_summary[cat] = categories_summary.get(cat, 0) + 1

    source_names = [s["name"] for s in sources]

    return {
        "sources": source_names,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "time_range_days": days,
        "count": len(all_items),
        "sources_ok": success_count,
        "sources_fail": fail_count,
        "sources_blocked_403": len(blocked_sources),
        "categories_summary": categories_summary,
        "data": all_items,
    }


def main():
    parser = argparse.ArgumentParser(
        description="YMOS RSS 数据获取工具 - 从 RSS 源获取市场信息"
    )
    parser.add_argument(
        "days", type=float, nargs="?", default=1,
        help="获取最近 N 天的数据（默认: 1）",
    )
    parser.add_argument(
        "--url", default=None,
        help="指定单个 RSS 源 URL（不指定则使用全部配置源）",
    )
    parser.add_argument(
        "--category", default=None,
        help="按分类过滤源（美股/宏观/科技/Crypto/深度洞察）",
    )
    parser.add_argument(
        "--config", default=None,
        help="自定义 RSS 配置文件路径（默认使用 rss_sources.json）",
    )
    parser.add_argument(
        "--output", default="financial_data.json",
        help="输出文件路径（默认: financial_data.json）",
    )

    args = parser.parse_args()

    print("=" * 50)
    print("YMOS RSS 数据获取工具")
    print("=" * 50)

    if args.url:
        # 单源模式
        print(f"\n🚀 单源模式: {args.url}")
        items = fetch_rss(args.url, args.days)
        if items:
            result = {
                "source": args.url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "time_range_days": args.days,
                "count": len(items),
                "data": items,
            }
        else:
            result = None
    else:
        # 全源模式（支持分类过滤）
        sources = load_sources(category_filter=args.category, config_path=args.config)
        if not sources:
            print("❌ 无可用源")
            sys.exit(1)
        result = fetch_all_sources(sources, args.days)

    if result and result.get("count", 0) > 0:
        # 确保输出目录存在
        output_dir = os.path.dirname(args.output)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n💾 数据已保存: {args.output}")
        print(f"✅ 共获取 {result['count']} 条数据")

        # 分类统计
        cat_summary = result.get("categories_summary", {})
        if cat_summary:
            print(f"\n📁 分类统计:")
            for cat, num in sorted(cat_summary.items()):
                print(f"   {cat}: {num} 条")
        else:
            # 兼容单源模式
            cats = {}
            for item in result.get("data", []):
                for cat in item.get("categories", ["未分类"]):
                    cats[cat] = cats.get(cat, 0) + 1
            if cats:
                print(f"\n📁 标签统计:")
                for cat, num in sorted(cats.items()):
                    print(f"   {cat}: {num} 条")
    else:
        print("\n⚠️ 未获取到数据，请检查网络连接和 RSS 源地址")
        sys.exit(1)


if __name__ == "__main__":
    main()
