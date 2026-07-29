#!/usr/bin/env python3
"""
问财经研报搜索封装脚本。

调用本机安装的 report-search Skill CLI，为 YMOS 自动建档 / 初始调研补充「券商叙事层」。

Skill 路径由 skill_resolver 统一解析（支持 YMOS_SKILL_ROOT 覆盖）。
Skill 未安装时会给出安装指引并退出，不影响 YMOS 主链路。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from skill_resolver import resolve_skill_cli, skill_missing_message

SCRIPTS_DIR = Path(__file__).resolve().parent
YMOS_ROOT = SCRIPTS_DIR.parents[1]

# Skill 路径由 skill_resolver 统一解析（支持 YMOS_SKILL_ROOT 环境变量覆盖）


def find_cli() -> Path:
    cli = resolve_skill_cli('report-search')
    if cli is None:
        raise SystemExit(skill_missing_message('report-search', '研报搜索'))
    return cli


def run_report_search(query: str, limit: int, output_json: Path, days: int | None = None) -> None:
    cli = find_cli()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(cli),
        '-q', query,
        '-l', str(limit),
        '-f', 'json',
        '-o', str(output_json),
    ]
    if days:
        cmd.extend(['--days', str(days)])

    env = os.environ.copy()
    # 部分问财官方 CLI 在 macOS 上会遇到系统 CA 问题；有 certifi 就显式指定，没装则忽略。
    if not env.get('SSL_CERT_FILE'):
        try:
            import certifi  # type: ignore
            env['SSL_CERT_FILE'] = certifi.where()
        except Exception:
            pass

    proc = subprocess.run(cmd, cwd=str(YMOS_ROOT), env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f'report-search failed exit={proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}')
    if not output_json.exists():
        raise RuntimeError(f'report-search did not create output file: {output_json}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}')


def load_reports(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(data, list):
        rows = [x for x in data if isinstance(x, dict)]
    elif isinstance(data, dict):
        rows = []
        for key in ['data', 'datas', 'reports', 'results']:
            if isinstance(data.get(key), list):
                rows = [x for x in data[key] if isinstance(x, dict)]
                break
    else:
        rows = []

    # report-search 会按段落返回同一篇研报的多个命中；自动建档阶段按 uid/url 去重更有用。
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        key = str(r.get('uid') or r.get('url') or r.get('title') or r.get('id'))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


def safe_extra(report: dict[str, Any]) -> dict[str, Any]:
    extra = report.get('extra')
    return extra if isinstance(extra, dict) else {}


def one_line(text: Any, max_len: int = 260) -> str:
    s = str(text or '').replace('\n', ' ').replace('\r', ' ').strip()
    return s[:max_len] + ('…' if len(s) > max_len else '')


def build_markdown(query: str, reports: list[dict[str, Any]], json_path: Path) -> str:
    now = dt.datetime.now().strftime('%Y-%m-%d %H:%M CST')
    lines = [
        f'# 问财经研报搜索：{query}',
        '',
        f'> 生成时间：{now}',
        '> 用途：自动建档 / 初始调研中的券商叙事层补充；不等于买卖建议。',
        f'> Raw：`{json_path}`',
        '',
        '## 快速结论层',
        '',
    ]
    if not reports:
        lines.append('- 未检索到研报。')
        return '\n'.join(lines) + '\n'

    orgs = []
    ratings = []
    for r in reports:
        e = safe_extra(r)
        if e.get('organization'):
            orgs.append(str(e.get('organization')))
        if e.get('rating'):
            ratings.append(str(e.get('rating')))
        extracted = r.get('extracted_info')
        if isinstance(extracted, dict) and extracted.get('rating'):
            ratings.append(str(extracted.get('rating')))

    def uniq(xs: list[str]) -> list[str]:
        out = []
        for x in xs:
            if x and x not in out:
                out.append(x)
        return out

    lines += [
        f'- 命中研报数：{len(reports)}',
        f'- 覆盖机构：{" / ".join(uniq(orgs)[:8]) or "—"}',
        f'- 评级口径：{" / ".join(uniq(ratings)[:8]) or "—"}',
        '',
        '## 研报列表',
        '',
        '| 日期 | 机构 | 评级 | 标题 | 摘要/叙事 | URL |',
        '|:---|:---|:---|:---|:---|:---|',
    ]
    for r in reports:
        e = safe_extra(r)
        extracted = r.get('extracted_info') if isinstance(r.get('extracted_info'), dict) else {}
        rating = e.get('rating') or extracted.get('rating') or '—'
        lines.append(
            f"| {str(r.get('publish_date') or '')[:10] or '—'} "
            f"| {e.get('organization') or '—'} "
            f"| {rating} "
            f"| {one_line(r.get('title'), 80)} "
            f"| {one_line(r.get('summary') or r.get('source_original'), 220)} "
            f"| {r.get('url') or '—'} |"
        )
    lines += [
        '',
        '## 使用提醒',
        '',
        '- 研报提供的是“市场叙事 / 券商偏好 / 估值锚点”，不是事实本身。',
        '- 自动建档可引用其投资要点，但关键财务数据仍需回到公告/财报核验。',
        '- 对 A 股来说，研报里的“评级、目标价、核心催化”很适合补进 P1/P4/P9/P17。',
    ]
    return '\n'.join(lines) + '\n'


def main() -> int:
    p = argparse.ArgumentParser(description='问财经研报搜索封装脚本')
    p.add_argument('query', help='搜索关键词，例如：大族激光 / 光模块 / AI服务器PCB')
    p.add_argument('-l', '--limit', type=int, default=10)
    p.add_argument('--days', type=int, default=None, help='只搜最近 N 天')
    p.add_argument('--date-tag', default=dt.datetime.now().strftime('%Y%m%d'))
    p.add_argument('--output-root', default=str(YMOS_ROOT / 'Eyes' / '研报搜索'))
    args = p.parse_args()

    month = f'{args.date_tag[:4]}-{args.date_tag[4:6]}'
    day = f'{args.date_tag[:4]}-{args.date_tag[4:6]}-{args.date_tag[6:8]}'
    safe_query = ''.join(ch if ch.isalnum() or '\u4e00' <= ch <= '\u9fff' else '_' for ch in args.query)[:40]
    root = Path(args.output_root).resolve()
    raw = root / 'Raw_Data' / month / f'report_search_{safe_query}_{args.date_tag}.json'
    md = root / month / f'研报搜索_{safe_query}_{day}.md'
    md.parent.mkdir(parents=True, exist_ok=True)

    run_report_search(args.query, args.limit, raw, args.days)
    reports = load_reports(raw)[:args.limit]
    md.write_text(build_markdown(args.query, reports, raw), encoding='utf-8')
    print(f'✅ reports={len(reports)}')
    print(f'✅ raw: {raw}')
    print(f'✅ report: {md}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
