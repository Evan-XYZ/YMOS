#!/usr/bin/env python3
"""
问财公告搜索封装脚本。

用途：为 YMOS 自动建档 / 初始调研 / 策略分析提供“公告事实层”。
不依赖 Hermes 官方 Skill；直接调用 SkillHub announcement-search 同款 OpenAPI channel。
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


def search_announcement(query: str) -> dict[str, Any]:
    ensure_cert_file()
    base_url = os.getenv('IWENCAI_BASE_URL', 'https://openapi.iwencai.com').rstrip('/')
    url = f'{base_url}/v1/comprehensive/search'
    trace_id = secrets.token_hex(32)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {get_api_key()}',
        'X-Claw-Call-Type': 'normal',
        'X-Claw-Skill-Id': 'announcement-search',
        'X-Claw-Skill-Version': '1.0.0',
        'X-Claw-Plugin-Id': 'none',
        'X-Claw-Plugin-Version': 'none',
        'X-Claw-Trace-Id': trace_id,
    }
    payload = {'channels': ['announcement'], 'app_id': 'AIME_SKILL', 'query': query}
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
        for key in ['data', 'datas', 'results', 'items', 'announcements']:
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def one_line(text: Any, max_len: int = 240) -> str:
    s = str(text or '').replace('\n', ' ').replace('\r', ' ').strip()
    return s[:max_len] + ('…' if len(s) > max_len else '')


def normalize_date(item: dict[str, Any]) -> str:
    for key in ['publish_date', 'publish_time', 'date', 'time', '公告日期', '披露日期']:
        v = item.get(key)
        if v:
            return str(v)
    return '—'


def classify_title(title: str) -> str:
    if any(k in title for k in ['年度报告', '季报', '半年度报告', '财务报告']):
        return '定期财报'
    if any(k in title for k in ['业绩预告', '业绩快报']):
        return '业绩预告/快报'
    if any(k in title for k in ['回购', '增持']):
        return '回购/增持'
    if any(k in title for k in ['分红', '派息', '权益分派']):
        return '分红派息'
    if any(k in title for k in ['重组', '收购', '重大资产']):
        return '资产重组'
    if any(k in title for k in ['合同', '订单', '中标']):
        return '合同/订单'
    return '其他公告'


def build_markdown(query: str, items: list[dict[str, Any]], raw_path: Path) -> str:
    now = dt.datetime.now().strftime('%Y-%m-%d %H:%M CST')
    lines = [
        f'# 问财公告搜索：{query}',
        '',
        f'> 生成时间：{now}',
        '> 用途：自动建档 / 初始调研 / 策略分析中的公告事实层；不等于买卖建议。',
        f'> Raw：`{raw_path}`',
        '',
        '## 快速结论层',
        '',
        f'- 命中公告数：{len(items)}',
        '- 用法：优先核验财报、业绩预告、分红回购、重大合同、资产重组等硬事实。',
        '',
    ]
    if not items:
        lines.append('- 未检索到公告。')
        return '\n'.join(lines) + '\n'
    lines += ['## 公告列表', '', '| 日期 | 类型 | 标题 | 摘要 | URL |', '|:---|:---|:---|:---|:---|']
    for item in items:
        title = str(item.get('title') or item.get('公告标题') or '')
        lines.append(
            f"| {normalize_date(item)[:19]} "
            f"| {classify_title(title)} "
            f"| {one_line(title, 100)} "
            f"| {one_line(item.get('summary') or item.get('content') or item.get('desc'), 220)} "
            f"| {item.get('url') or item.get('link') or '—'} |"
        )
    lines += [
        '',
        '## 使用纪律',
        '',
        '- 公告是 A 股调研中最高优先级事实层，优先级高于新闻、研报、搜索摘要。',
        '- 关键买卖判断前，财务指标与业务事件必须尽量回到公告/财报原文核验。',
        '- 公告命中少不代表事实不存在，可改写查询：股票名 + 年报/季报/业绩预告/回购/合同。',
    ]
    return '\n'.join(lines) + '\n'


def safe_name(s: str, max_len: int = 60) -> str:
    return ''.join(ch if ch.isalnum() or '\u4e00' <= ch <= '\u9fff' else '_' for ch in s)[:max_len]


def main() -> int:
    p = argparse.ArgumentParser(description='问财公告搜索封装脚本')
    p.add_argument('query', help='搜索关键词，例如：大族激光 2026 一季报 公告')
    p.add_argument('-l', '--limit', type=int, default=10)
    p.add_argument('--date-tag', default=dt.datetime.now().strftime('%Y%m%d'))
    p.add_argument('--output-root', default=str(YMOS_ROOT / 'Eyes' / '公告搜索'))
    args = p.parse_args()

    month = f'{args.date_tag[:4]}-{args.date_tag[4:6]}'
    day = f'{args.date_tag[:4]}-{args.date_tag[4:6]}-{args.date_tag[6:8]}'
    root = Path(args.output_root).resolve()
    raw = root / 'Raw_Data' / month / f'announcement_search_{safe_name(args.query)}_{args.date_tag}.json'
    md = root / month / f'公告搜索_{safe_name(args.query)}_{day}.md'
    raw.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)

    result = search_announcement(args.query)
    raw.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    items = extract_items(result)[:args.limit]
    md.write_text(build_markdown(args.query, items, raw), encoding='utf-8')
    print(f'✅ announcements={len(items)}')
    print(f'✅ raw: {raw}')
    print(f'✅ report: {md}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
