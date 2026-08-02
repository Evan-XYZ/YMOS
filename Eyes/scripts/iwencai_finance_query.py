#!/usr/bin/env python3
"""
问财个股财务数据查询封装脚本。

用途：为 YMOS 自动建档 / 策略分析 / 初始调研提供确定性的财务指标层，减少搜索摘要幻觉。
底层复用 SkillHub 安装的 hithink-finance-query CLI。
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

DEFAULT_METRICS = '营业收入 净利润 毛利率 净利率 ROE 资产负债率 经营现金流 营收同比 净利润同比'


def find_cli() -> Path:
    cli = resolve_skill_cli('hithink-finance-query')
    if cli is None:
        raise SystemExit(skill_missing_message('hithink-finance-query', '个股财务数据查询'))
    return cli


def run_finance_query(query: str, limit: int, output_json: Path, page: int = 1) -> None:
    cli = find_cli()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(cli),
        '-q', query,
        '--page', str(page),
        '--limit', str(limit),
    ]

    env = os.environ.copy()
    # 官方 CLI 在 macOS 上常遇到系统 CA 问题；显式指定 certifi。
    if not env.get('SSL_CERT_FILE'):
        try:
            import certifi  # type: ignore
            env['SSL_CERT_FILE'] = certifi.where()
        except Exception:
            pass

    proc = subprocess.run(cmd, cwd=str(YMOS_ROOT), env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f'finance-query failed exit={proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}')
    output_json.write_text(proc.stdout, encoding='utf-8')


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {'data': data}
    except Exception as e:
        return {'error': f'json parse failed: {e}', 'raw': path.read_text(encoding='utf-8')[:2000]}


def fmt_num(x: Any) -> str:
    if x is None or x == '':
        return '—'
    if isinstance(x, (int, float)):
        ax = abs(float(x))
        if ax >= 1e8:
            return f'{x/1e8:.2f}亿'
        if ax >= 1e4:
            return f'{x/1e4:.2f}万'
        return f'{x:.4g}'
    return str(x)


def classify_field(key: str) -> str:
    if any(s in key for s in ['营业收入', '营收']):
        return '收入'
    if any(s in key for s in ['净利润', '归母净利润']):
        return '利润'
    if any(s in key for s in ['毛利率', '净利率', 'ROE', '净资产收益率', '资产负债率']):
        return '质量/结构'
    if any(s in key for s in ['现金流']):
        return '现金流'
    if any(s in key for s in ['同比', '增长率']):
        return '增速'
    if key in ['股票代码', '股票简称', '最新价', '最新涨跌幅']:
        return '基础'
    return '其他'


def build_markdown(query: str, result: dict[str, Any], raw_path: Path) -> str:
    now = dt.datetime.now().strftime('%Y-%m-%d %H:%M CST')
    datas = result.get('datas') if isinstance(result.get('datas'), list) else []
    lines = [
        f'# 问财个股财务数据：{query}',
        '',
        f'> 生成时间：{now}',
        '> 用途：自动建档 / 策略分析 / 初始调研的确定性财务指标层；不等于投资建议。',
        f'> Raw：`{raw_path}`',
        '',
        '## 查询概况',
        '',
        f'- success：{result.get("success", "—")}',
        f'- code_count：{result.get("code_count", "—")}',
        f'- returned_count：{result.get("returned_count", len(datas))}',
        f'- query：{result.get("query", query)}',
        '',
    ]
    if result.get('error'):
        lines += ['## 错误', '', f'- {result.get("error")}', '']
        return '\n'.join(lines) + '\n'
    if not datas:
        lines += ['## 数据', '', '- 未返回 datas；建议简化问句后重试。', '']
        return '\n'.join(lines) + '\n'

    for idx, row in enumerate(datas, 1):
        if not isinstance(row, dict):
            continue
        name = row.get('股票简称') or row.get('名称') or f'Row {idx}'
        code = row.get('股票代码') or row.get('代码') or ''
        lines += [f'## {idx}. {name} {code}', '', '| 类型 | 指标 | 值 |', '|:---|:---|:---|']
        for k, v in row.items():
            lines.append(f'| {classify_field(str(k))} | {k} | {fmt_num(v)} |')
        lines.append('')

    lines += [
        '## 使用提醒',
        '',
        '- 这是结构化财务指标层，优先级高于搜索摘要；但字段口径仍需在关键决策前回公告/财报确认。',
        '- 可用于 P1 基础快照、P2 环境识别与 P9 估值输入；必须保留数据口径和时间。',
        '- 如果字段缺失，优先改写问句：股票名 + 报告期 + 指标名，例如“大族激光 2026一季报 营业收入 净利润 毛利率 ROE”。',
    ]
    return '\n'.join(lines) + '\n'


def main() -> int:
    p = argparse.ArgumentParser(description='问财个股财务数据查询封装脚本')
    p.add_argument('stock_or_query', help='股票名/代码，或完整问财自然语言问句')
    p.add_argument('--metrics', default=DEFAULT_METRICS, help='指标列表；如果 stock_or_query 已是完整问句，可传空字符串')
    p.add_argument('-l', '--limit', type=int, default=5)
    p.add_argument('--page', type=int, default=1)
    p.add_argument('--date-tag', default=dt.datetime.now().strftime('%Y%m%d'))
    p.add_argument('--output-root', default=str(YMOS_ROOT / 'Eyes' / '财务数据查询'))
    args = p.parse_args()

    query = args.stock_or_query.strip()
    if args.metrics.strip() and not any(word in query for word in ['营业收入', '净利润', 'ROE', '毛利率', '资产负债率', '现金流']):
        query = f'{query} {args.metrics.strip()}'

    month = f'{args.date_tag[:4]}-{args.date_tag[4:6]}'
    day = f'{args.date_tag[:4]}-{args.date_tag[4:6]}-{args.date_tag[6:8]}'
    safe_query = ''.join(ch if ch.isalnum() or '\u4e00' <= ch <= '\u9fff' else '_' for ch in query)[:60]
    root = Path(args.output_root).resolve()
    raw = root / 'Raw_Data' / month / f'finance_query_{safe_query}_{args.date_tag}.json'
    md = root / month / f'财务数据_{safe_query}_{day}.md'
    md.parent.mkdir(parents=True, exist_ok=True)

    run_finance_query(query, args.limit, raw, args.page)
    result = load_json(raw)
    md.write_text(build_markdown(query, result, raw), encoding='utf-8')
    datas = result.get('datas') if isinstance(result.get('datas'), list) else []
    print(f'✅ rows={len(datas)}')
    print(f'✅ raw: {raw}')
    print(f'✅ report: {md}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
