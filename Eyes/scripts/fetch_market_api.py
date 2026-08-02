#!/usr/bin/env python3
"""
YMOS Market Data API 示例脚本

说明：
- 这是“市场信息洞察”数据源的示例模板
- 适合用户替换为自己的市场信息 API
- 不内置任何真实私钥，统一通过环境变量或命令行参数传入
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parents[1]  # Eyes/scripts → Eyes → YMOS
sys.path.insert(0, str(SCRIPTS_DIR))
from env_loader import load_dotenv


DEFAULT_API_URL = "https://example.com/wp-json/tib/v1/reports"
DEFAULT_CATEGORIES = [
    "#中国股市",
    "#美国股市",
    "#Crypto",
    "#宏观经济",
    "#科技动态",
    "#个人精选",
]


def _do_fetch(api_url, api_key, time_value, categories):
    """单次 HTTP 请求（内部函数，由 fetch_reports 调用）。"""
    params = {
        "time_value": time_value,
        "categories": ",".join(categories),
    }
    full_url = f"{api_url}?{urllib.parse.urlencode(params)}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "YMOS-MarketAPI/1.0",
        "Accept": "application/json",
    }
    req = urllib.request.Request(full_url, headers=headers, method="GET")

    # 使用系统默认证书链；Bearer Key 不得通过关闭 TLS 校验来换取兼容性。
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _is_retryable(exc):
    """判断错误是否值得重试。"""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500  # 5xx 服务端错误可重试
    if isinstance(exc, urllib.error.URLError):
        return True  # 网络连接错误可重试
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    return False


def fetch_reports(api_url, api_key, time_value, categories, max_retries=3):
    """带重试的报告获取。对可恢复错误最多重试 max_retries 次（指数退避）。"""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return _do_fetch(api_url, api_key, time_value, categories)
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if not _is_retryable(exc):
                print(f"❌ HTTP Error: {exc.code} - {exc.reason}（不可恢复，放弃重试）")
                try:
                    print(exc.read().decode("utf-8")[:1000])
                except Exception:
                    pass
                return None
            wait = 2 ** attempt
            print(f"⚠️ HTTP {exc.code}（第 {attempt}/{max_retries} 次），{wait}s 后重试…")
            time.sleep(wait)
        except urllib.error.URLError as exc:
            last_exc = exc
            wait = 2 ** attempt
            print(f"⚠️ 网络错误: {exc.reason}（第 {attempt}/{max_retries} 次），{wait}s 后重试…")
            time.sleep(wait)
        except json.JSONDecodeError as exc:
            print(f"❌ JSON 解析失败: {exc}")
            return None
        except Exception as exc:
            last_exc = exc
            if _is_retryable(exc):
                wait = 2 ** attempt
                print(f"⚠️ {exc}（第 {attempt}/{max_retries} 次），{wait}s 后重试…")
                time.sleep(wait)
            else:
                print(f"❌ Unexpected Error: {exc}")
                return None

    print(f"❌ 重试 {max_retries} 次后仍失败: {last_exc}")
    return None


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="YMOS Market Data API 示例脚本")
    parser.add_argument("time_value", type=float, nargs="?", default=1, help="回溯天数，默认 1")
    parser.add_argument("--output", default="market_data.json", help="输出文件路径")
    parser.add_argument(
        "--api-url",
        default=os.environ.get("YMOS_MARKET_API_URL", DEFAULT_API_URL),
        help="市场数据 API URL，可用环境变量 YMOS_MARKET_API_URL 覆盖",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("YMOS_MARKET_API_KEY", ""),
        help="市场数据 API Key；不提供时将要求显式配置 YMOS_MARKET_API_KEY",
    )
    parser.add_argument(
        "--categories",
        default=",".join(DEFAULT_CATEGORIES),
        help="逗号分隔的分类列表",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("⚠️ 未提供 Market API Key（YMOS_MARKET_API_KEY），跳过 API 数据源。")
        print("   💡 建议使用 RSS 免费数据源作为替代：")
        print(f"   python3 scripts/fetch_rss.py {args.time_value} --output \"{args.output}\"")
        print("   如需启用 Market API，请参考 进阶指南.md Level 2")
        sys.exit(0)

    categories = [item.strip() for item in args.categories.split(",") if item.strip()]

    print("=" * 60)
    print("YMOS Market Data API 示例脚本")
    print("=" * 60)
    print(f"API URL: {args.api_url}")
    print(f"Categories: {', '.join(categories)}")

    result = fetch_reports(args.api_url, args.api_key, args.time_value, categories)
    if not result:
        sys.exit(1)

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)

    count = result.get("count", "N/A") if isinstance(result, dict) else "N/A"
    print(f"\n💾 已保存：{args.output}")
    print(f"✅ 成功拉取：{count} 条")


if __name__ == "__main__":
    main()
