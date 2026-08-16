#!/usr/bin/env python3
"""同花顺强势股题材归因取数器（YMOS 原子能力）。

定位：
  - 直接调用同花顺公开的强势股归因接口，不依赖外部 Skill、API Key 或第三方库。
  - 只输出市场事实，不生成板块结论、候选评级或买卖建议。
  - 后续可由 What's Hot 按股票代码与问财 movers/newhighs 等池做关联。

示例：
  python3 Eyes/scripts/fetch_ths_hot_reason.py \
    --date 2026-08-14 \
    --output /tmp/ths_hot_reason_20260814.json

未指定 --date 时使用 Asia/Shanghai 当天日期。非交易日返回 empty 属正常结果；
调用方需要最近交易日数据时，应显式传入对应交易日。
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SOURCE_ID = "ths_hot_reason"
SOURCE_NAME = "同花顺强势股题材归因"
SOURCE_TIMEZONE = "Asia/Shanghai"
SCHEMA_VERSION = "1.0"
ENDPOINT_TEMPLATE = (
    "https://zx.10jqka.com.cn/event/api/getharden/"
    "date/{query_date}/orderby/date/orderway/desc/charset/GBK/"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36 YMOS/4.0"
)


class THSHotReasonError(RuntimeError):
    """同花顺强势归因请求或响应不可用。"""


def default_query_date() -> str:
    """返回上海时区当天日期。"""
    return datetime.now(ZoneInfo(SOURCE_TIMEZONE)).strftime("%Y-%m-%d")


def validate_query_date(value: str) -> str:
    """校验并规范化 YYYY-MM-DD 日期。"""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("日期必须为 YYYY-MM-DD，例如 2026-08-14") from exc


def _decode_json(raw: bytes, declared_charset: str | None = None) -> dict[str, Any]:
    """兼容接口可能返回的 UTF-8 / GB18030 编码。"""
    encodings: list[str] = []
    if declared_charset:
        encodings.append(declared_charset)
    encodings.extend(["utf-8", "gb18030", "gbk"])

    last_error: Exception | None = None
    for encoding in dict.fromkeys(encodings):
        try:
            decoded = raw.decode(encoding)
            payload = json.loads(decoded)
            if not isinstance(payload, dict):
                raise THSHotReasonError("响应 JSON 顶层不是对象")
            return payload
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            last_error = exc
    raise THSHotReasonError(f"响应无法按 UTF-8/GB18030 解码为 JSON: {last_error}")


def split_reason_tags(reason: Any) -> list[str]:
    """把同花顺 reason 原文拆为便于后续主题聚合的标签，原文仍单独保留。"""
    text = str(reason or "").strip()
    if not text:
        return []
    tags = [part.strip() for part in re.split(r"[+＋、/｜|；;，,]", text)]
    return list(dict.fromkeys(tag for tag in tags if tag))


def _number(value: Any) -> int | float | None:
    """尽量规范化数值；缺失或异常值保留为 None，避免伪造 0。"""
    if value is None or value == "" or value == "--":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(str(value).replace(",", ""))
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return None


def normalize_row(row: dict[str, Any], query_date: str) -> dict[str, Any] | None:
    """将单条上游记录转换为稳定的 YMOS 数据字段。"""
    code = str(row.get("code") or "").strip()
    name = str(row.get("name") or "").strip()
    if not re.fullmatch(r"\d{6}", code) or not name:
        return None

    reason = str(row.get("reason") or "").strip()
    return {
        "code": code,
        "name": name,
        "source_date": str(row.get("date") or query_date)[:10],
        "reason": reason,
        "reason_tags": split_reason_tags(reason),
        "close": _number(row.get("close")),
        "change": _number(row.get("zhangdie")),
        "change_pct": _number(row.get("zhangfu")),
        "turnover_pct": _number(row.get("huanshou")),
        # 上游未公开稳定单位契约，避免把 chengjiaoe/chengjiaoliang 错标为元或股。
        "amount_raw": _number(row.get("chengjiaoe")),
        "volume_raw": _number(row.get("chengjiaoliang")),
        "dde_net_volume": _number(row.get("ddejingliang")),
        "market_raw": row.get("market"),
    }


def build_document(payload: dict[str, Any], query_date: str, source_url: str) -> dict[str, Any]:
    """校验接口业务状态并构造可供 SOP 消费的 JSON 文档。"""
    error_code = payload.get("errocode", 0)
    if str(error_code) not in {"0", "0.0", "None"}:
        message = payload.get("errormsg") or payload.get("message") or "unknown upstream error"
        raise THSHotReasonError(f"同花顺接口错误 errocode={error_code}: {message}")

    raw_rows = payload.get("data") or []
    if not isinstance(raw_rows, list):
        raise THSHotReasonError("同花顺响应 data 字段不是列表")

    data: list[dict[str, Any]] = []
    malformed_rows = 0
    for row in raw_rows:
        if not isinstance(row, dict):
            malformed_rows += 1
            continue
        normalized = normalize_row(row, query_date)
        if normalized is None:
            malformed_rows += 1
            continue
        data.append(normalized)

    reason_count = sum(1 for item in data if item["reason"])
    fetched_at = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if data else "empty",
        "source_id": SOURCE_ID,
        "source": SOURCE_NAME,
        "source_url": source_url,
        "source_timezone": SOURCE_TIMEZONE,
        "query_date": query_date,
        "fetched_at": fetched_at,
        "count": len(data),
        "quality": {
            "raw_count": len(raw_rows),
            "normalized_count": len(data),
            "reason_count": reason_count,
            "missing_reason_count": len(data) - reason_count,
            "malformed_row_count": malformed_rows,
        },
        "data": data,
        "error": None,
    }


def error_document(query_date: str, source_url: str, error: Exception) -> dict[str, Any]:
    """失败时也输出结构化文档，供上层明确降级。"""
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "error",
        "source_id": SOURCE_ID,
        "source": SOURCE_NAME,
        "source_url": source_url,
        "source_timezone": SOURCE_TIMEZONE,
        "query_date": query_date,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": 0,
        "quality": {
            "raw_count": 0,
            "normalized_count": 0,
            "reason_count": 0,
            "missing_reason_count": 0,
            "malformed_row_count": 0,
        },
        "data": [],
        "error": {"type": type(error).__name__, "message": str(error)},
    }


def fetch_hot_reason(query_date: str, timeout: float = 15.0, retries: int = 3) -> dict[str, Any]:
    """请求同花顺强势归因并返回标准化文档。"""
    source_url = ENDPOINT_TEMPLATE.format(query_date=query_date)
    request = urllib.request.Request(
        source_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://stock.10jqka.com.cn/",
        },
        method="GET",
    )

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                charset = response.headers.get_content_charset()
            return build_document(_decode_json(raw, charset), query_date, source_url)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code < 500 and exc.code != 429:
                break
        except (urllib.error.URLError, TimeoutError, socket.timeout, THSHotReasonError) as exc:
            last_error = exc
            # 业务错误或结构漂移重复请求通常无意义。
            if isinstance(exc, THSHotReasonError):
                break
        if attempt < retries:
            time.sleep(min(2 ** (attempt - 1), 4))

    raise THSHotReasonError(f"请求失败（尝试 {retries} 次）: {last_error}")


def write_document(document: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取同花顺强势股及人工题材归因，输出 YMOS JSON")
    parser.add_argument("--date", type=validate_query_date, default=default_query_date(), help="交易日 YYYY-MM-DD")
    parser.add_argument("--output", default="ths_hot_reason.json", help="输出 JSON 路径")
    parser.add_argument("--timeout", type=float, default=15.0, help="单次请求超时秒数")
    parser.add_argument("--retries", type=int, default=3, help="最大请求次数")
    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    if args.retries < 1:
        parser.error("--retries 必须至少为 1")

    output = Path(args.output).expanduser().resolve()
    source_url = ENDPOINT_TEMPLATE.format(query_date=args.date)
    try:
        document = fetch_hot_reason(args.date, timeout=args.timeout, retries=args.retries)
    except Exception as exc:
        document = error_document(args.date, source_url, exc)
        write_document(document, output)
        print(f"❌ {SOURCE_NAME}: {exc}")
        print(f"💾 错误状态已保存：{output}")
        return 1

    write_document(document, output)
    if document["status"] == "empty":
        print(f"⚠️ {args.date} 未返回强势股（可能为非交易日或当日暂无数据）")
    else:
        q = document["quality"]
        print(f"✅ {args.date} 强势股 {document['count']} 只，题材归因 {q['reason_count']} 只")
    print(f"💾 已保存：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
