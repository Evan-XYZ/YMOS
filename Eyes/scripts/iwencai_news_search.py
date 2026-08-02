#!/usr/bin/env python3
"""
问财财经新闻搜索封装脚本。

用途：为 YMOS 自动建档 / 初始调研 / 策略分析提供“最新事件层”。
不依赖 Hermes 官方 Skill；直接调用 SkillHub news-search 同款 OpenAPI channel。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from env_loader import load_dotenv

SCRIPTS_DIR = Path(__file__).resolve().parent
YMOS_ROOT = SCRIPTS_DIR.parents[1]
load_dotenv()


def ensure_cert_file() -> None:
    if os.environ.get('SSL_CERT_FILE'):
        return
    try:
        import certifi  # type: ignore
        os.environ['SSL_CERT_FILE'] = certifi.where()
    except Exception:
        pass


def get_api_key() -> str:
    key = os.getenv('IWENCAI_API_KEY')
    if not key:
        raise RuntimeError('IWENCAI_API_KEY not found. Load ~/.zprofile or ~/.zshrc first.')
    return key


def search_news(query: str, limit: int = 10) -> dict[str, Any]:
    ensure_cert_file()
    base_url = os.getenv('IWENCAI_BASE_URL', 'https://openapi.iwencai.com').rstrip('/')
    url = f'{base_url}/v1/comprehensive/search'
    trace_id = secrets.token_hex(32)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {get_api_key()}',
        'X-Claw-Call-Type': 'normal',
        'X-Claw-Skill-Id': 'news-search',
        'X-Claw-Skill-Version': '1.0.0',
        'X-Claw-Plugin-Id': 'none',
        'X-Claw-Plugin-Version': 'none',
        'X-Claw-Trace-Id': trace_id,
    }
    payload = {'channels': ['news'], 'app_id': 'AIME_SKILL', 'query': query}
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            status_code = response.status
            body = response.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        body = exc.read().decode('utf-8', errors='replace')
    except urllib.error.URLError as exc:
        return {'status_code': 0, 'trace_id': trace_id, 'query': query, 'error': str(exc)}
    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        raw = {'raw_text': body}
    return {'status_code': status_code, 'trace_id': trace_id, 'query': query, 'raw_response': raw}


def extract_items(raw: dict[str, Any]) -> list[dict[str, Any]]:
    data = raw.get('raw_response', raw)
    if isinstance(data, dict):
        for key in ['data', 'datas', 'results', 'items', 'news']:
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def one_line(text: Any, max_len: int = 240) -> str:
    s = str(text or '').replace('\n', ' ').replace('\r', ' ').strip()
    return s[:max_len] + ('…' if len(s) > max_len else '')


def normalize_date(item: dict[str, Any]) -> str:
    for key in ['publish_date', 'publish_time', 'date', 'time', 'ctime']:
        v = item.get(key)
        if v:
            return str(v)
    return '—'


def build_markdown(query: str, items: list[dict[str, Any]], raw_path: Path, days: int | None) -> str:
    now = dt.datetime.now().strftime('%Y-%m-%d %H:%M CST')
    lines = [
        f'# 问财财经新闻搜索：{query}',
        '',
        f'> 生成时间：{now}',
        '> 用途：自动建档 / 初始调研 / 策略分析中的最新事件层；不等于买卖建议。',
        f'> Raw：`{raw_path}`',
        f'> 时间过滤：最近 {days} 天' if days else '> 时间过滤：未启用',
        '',
        '## 快速结论层',
        '',
        f'- 命中资讯数：{len(items)}',
        '- 用法：提取最新催化、政策/订单/产业事件、媒体传播势能；关键事实仍需公告/财报核验。',
        '',
    ]
    if not items:
        lines.append('- 未检索到新闻。')
        return '\n'.join(lines) + '\n'
    lines += ['## 新闻列表', '', '| 日期 | 来源 | 标题 | 摘要 | URL |', '|:---|:---|:---|:---|:---|']
    for item in items:
        lines.append(
            f"| {normalize_date(item)[:19]} "
            f"| {one_line(item.get('source') or item.get('media') or item.get('site'), 40)} "
            f"| {one_line(item.get('title'), 90)} "
            f"| {one_line(item.get('summary') or item.get('content') or item.get('desc'), 220)} "
            f"| {item.get('url') or item.get('link') or '—'} |"
        )
    lines += [
        '',
        '## 使用纪律',
        '',
        '- 新闻用于回答“最近发生了什么 / 市场在传播什么”，优先级低于公告与结构化财务。',
        '- 若新闻与价格异动共振，可提升 P4 关注优先级；若无一手来源支撑，P3/P5 不得把它当作硬事实。',
    ]
    return '\n'.join(lines) + '\n'


def safe_name(s: str, max_len: int = 60) -> str:
    return ''.join(ch if ch.isalnum() or '\u4e00' <= ch <= '\u9fff' else '_' for ch in s)[:max_len]


def main() -> int:
    p = argparse.ArgumentParser(description='问财财经新闻搜索封装脚本')
    p.add_argument('query', help='搜索关键词，例如：大族激光 AI PCB 最新新闻')
    p.add_argument('-l', '--limit', type=int, default=10)
    p.add_argument('--days', type=int, default=None, help='保留最近 N 天；当前按文本日期尽量过滤，失败则保留')
    p.add_argument('--date-tag', default=dt.datetime.now().strftime('%Y%m%d'))
    p.add_argument('--output-root', default=str(YMOS_ROOT / 'Eyes' / '新闻搜索'))
    args = p.parse_args()

    month = f'{args.date_tag[:4]}-{args.date_tag[4:6]}'
    day = f'{args.date_tag[:4]}-{args.date_tag[4:6]}-{args.date_tag[6:8]}'
    root = Path(args.output_root).resolve()
    raw = root / 'Raw_Data' / month / f'news_search_{safe_name(args.query)}_{args.date_tag}.json'
    md = root / month / f'新闻搜索_{safe_name(args.query)}_{day}.md'
    raw.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)

    result = search_news(args.query, args.limit)
    raw.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    items = extract_items(result)[:args.limit]
    md.write_text(build_markdown(args.query, items, raw, args.days), encoding='utf-8')
    print(f'✅ news={len(items)}')
    print(f'✅ raw: {raw}')
    print(f'✅ report: {md}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
