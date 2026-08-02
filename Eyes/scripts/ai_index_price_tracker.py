#!/usr/bin/env python3
"""作者内核扩展（默认关闭）：为作者维护的产业索引提供价格跟踪。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
YMOS_ROOT = SCRIPTS_DIR.parents[1]


def clean_ticker_token(ticker: str) -> str:
    """清洗 INDEX 里用于展示的 ticker token，转为机器可查询代码。"""
    t = ticker.strip().upper()
    # Markdown / wiki 展示噪音：**688981.SH**、`NVDA`
    t = t.replace('**', '').replace('`', '').strip()
    # 去掉括号注释：CBRS（IPO 中）、688721.SH（新上市）
    t = re.sub(r'（.*?）', '', t)
    t = re.sub(r'\(.*?\)', '', t)
    return t.strip()


def should_skip_ticker_token(ticker: str) -> bool:
    raw = ticker.strip().upper()
    if not raw:
        return True
    skip_markers = ['未上市', '待确认', 'IPO 中', 'IPO中', '代码待定']
    return any(m.upper() in raw for m in skip_markers)


def market_from_ticker(ticker: str) -> str:
    t = clean_ticker_token(ticker)
    if t.endswith(('.SS', '.SZ', '.SH')):
        return 'CN'
    if t.endswith('.HK'):
        return 'HK'
    if re.fullmatch(r'[A-Z][A-Z0-9^:-]*', t):
        return 'US'
    return 'OTHER'


def normalize_ticker(ticker: str) -> str:
    t = clean_ticker_token(ticker)
    if t.endswith('.SH'):
        return t[:-3] + '.SS'
    return t


def parse_index(index_path: Path) -> list[dict]:
    text = index_path.read_text(encoding='utf-8')
    rows = []
    current_layer = ''
    in_table = False
    for raw in text.splitlines():
        line = raw.rstrip('\n')
        if line.startswith('## '):
            current_layer = line.replace('## ', '').strip()
            in_table = False
            continue
        if not line.strip().startswith('|'):
            in_table = False
            continue
        cols = [c.strip() for c in line.split('|')[1:-1]]
        if not cols:
            continue
        if cols[0] == '公司':
            in_table = True
            continue
        if not in_table:
            continue
        if all(set(c) <= set('-:') for c in cols):
            continue
        if len(cols) < 6:
            continue
        company, ticker_field, market_field, priority, added, note = cols[:6]
        tickers = []
        for token in re.split(r'\s*/\s*', ticker_field):
            if should_skip_ticker_token(token):
                continue
            tk = normalize_ticker(token)
            if tk:
                tickers.append(tk)
        for tk in tickers:
            m = market_from_ticker(tk)
            if m not in {'US', 'CN', 'HK'}:
                continue
            rows.append({
                'layer': current_layer,
                'company': company.replace('**', '').strip(),
                'ticker': tk,
                'market': m,
                'priority': priority,
                'added': added,
                'note': note.replace('**', '').strip(),
            })
    # dedupe by ticker keep first
    out, seen = [], set()
    for r in rows:
        if r['ticker'] in seen:
            continue
        seen.add(r['ticker'])
        out.append(r)
    return out


def load_quotes(raw_dir: Path, date_tag: str) -> dict[str, dict]:
    quotes = {}
    for name in [f'price_scan_finnhub_{date_tag}.json', f'price_scan_tushare_{date_tag}.json', f'price_scan_yahoo_{date_tag}.json']:
        p = raw_dir / name
        if not p.exists():
            continue
        obj = json.loads(p.read_text(encoding='utf-8'))
        for item in obj.get('data', []):
            symbol = item.get('symbol', '').upper()
            if symbol.startswith('BINANCE:'):
                continue
            if 'price' in item:
                quotes[symbol] = {
                    'price': item.get('price'),
                    'pct': item.get('change_pct'),
                    'prev_close': item.get('prev_close'),
                    'source': obj.get('source', ''),
                }
            elif item.get('ok'):
                prev_close = item.get('pre_close')
                pct = item.get('pct_chg')
                if pct is None:
                    bars = item.get('bars') or []
                    if len(bars) >= 2:
                        prev_close = bars[-2].get('close')
                    if prev_close not in (None, 0):
                        try:
                            pct = (float(item.get('last_close')) - float(prev_close)) / float(prev_close) * 100
                        except Exception:
                            pct = None
                quotes[symbol] = {
                    'price': item.get('last_close'),
                    'pct': pct,
                    'prev_close': prev_close,
                    'source': obj.get('source', ''),
                }
    return quotes


def fmt_price(x, market):
    if x is None:
        return '—'
    if market == 'CN':
        return f'¥{x:.2f}'
    if market == 'HK':
        return f'HK${x:.2f}'
    return f'${x:.2f}'


def fmt_pct(x):
    if x is None:
        return '—'
    return f'{x:+.2f}%'


def flag(x):
    if x is None:
        return '无数据'
    if abs(x) >= 5:
        return '⚠️ >5%异动'
    return '—'


def build_report(rows: list[dict], quotes: dict[str, dict], date_value: dt.date, index_path: Path, raw_dir: Path) -> str:
    enriched = []
    for r in rows:
        q = quotes.get(r['ticker'], {})
        enriched.append({**r, 'price': q.get('price'), 'pct': q.get('pct'), 'source': q.get('source', '')})
    movers = [r for r in enriched if r['pct'] is not None and abs(r['pct']) >= 5]
    no_data = [r for r in enriched if r['pct'] is None]
    by_layer = {}
    for r in enriched:
        by_layer.setdefault(r['layer'], []).append(r)
    lines = []
    lines.append(f'# AI 标的价格跟踪 - {date_value.isoformat()}\n')
    lines.append(f'> INDEX 来源：`{index_path}`')
    lines.append(f'> Raw_Data：`{raw_dir}`')
    lines.append('> 作用：跟踪 INDEX 列表里**已上市的中/美/港标的**价格表现，单日涨跌幅绝对值 >5% 的标的单独高亮。\n')
    lines.append('## 今日概览\n')
    lines.append(f'- 跟踪标的数：{len(enriched)}')
    lines.append(f'- 有效报价数：{len(enriched) - len(no_data)}')
    lines.append(f'- >5% 异动数：{len(movers)}')
    lines.append(f'- 无报价数：{len(no_data)}\n')
    lines.append('## 单日异动（|涨跌幅| > 5%）\n')
    if movers:
        lines.append('| 公司 | Ticker | 市场 | 所属层 | 现价 | 涨跌幅 | 备注 |')
        lines.append('|:---|:---|:---:|:---|:---:|:---:|:---|')
        for r in sorted(movers, key=lambda x: abs(x['pct']), reverse=True):
            lines.append(f"| {r['company']} | {r['ticker']} | {r['market']} | {r['layer']} | {fmt_price(r['price'], r['market'])} | {fmt_pct(r['pct'])} | {r['note']} |")
    else:
        lines.append('- 今日无 >5% 异动标的。')
    lines.append('\n## 全量跟踪列表\n')
    for layer, layer_rows in by_layer.items():
        lines.append(f'### {layer}\n')
        lines.append('| 公司 | Ticker | 市场 | 优先级 | 现价 | 涨跌幅 | 异动 | 备注 |')
        lines.append('|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|')
        def sort_key(x):
            return (0 if x['priority'] == '🔥' else 1, -(abs(x['pct']) if x['pct'] is not None else -1), x['company'])
        for r in sorted(layer_rows, key=sort_key):
            lines.append(f"| {r['company']} | {r['ticker']} | {r['market']} | {r['priority']} | {fmt_price(r['price'], r['market'])} | {fmt_pct(r['pct'])} | {flag(r['pct'])} | {r['note']} |")
        lines.append('')
    if no_data:
        lines.append('## 无报价 / 待排查\n')
        for r in no_data:
            lines.append(f"- {r['company']} ({r['ticker']}) / {r['layer']}")
        lines.append('')
    lines.append('---')
    lines.append('*注：本报告仅做价格跟踪与异动筛选，不构成投资建议。*')
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser(description='AI 产业链 INDEX 已上市标的价格跟踪')
    p.add_argument('--index', required=True)
    p.add_argument('--output-root', required=True)
    p.add_argument('--date-tag', default=dt.date.today().strftime('%Y%m%d'))
    args = p.parse_args()

    index_path = Path(args.index)
    out_root = Path(args.output_root)
    date_value = dt.datetime.strptime(args.date_tag, '%Y%m%d').date()
    month_tag = args.date_tag[:4] + '-' + args.date_tag[4:6]
    raw_dir = out_root / 'Raw_Data' / month_tag
    report_dir = out_root / month_tag
    raw_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    rows = parse_index(index_path)
    tickers = [r['ticker'] for r in rows]
    universe_path = raw_dir / f'index_universe_{args.date_tag}.json'
    universe_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')

    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / 'fetch_price_router.py'),
        '--symbols', ','.join(tickers),
        '--output-dir', str(raw_dir),
        '--date-tag', args.date_tag,
    ]
    subprocess.call(cmd, cwd=str(YMOS_ROOT.parent))

    quotes = load_quotes(raw_dir, args.date_tag)
    report = build_report(rows, quotes, date_value, index_path, raw_dir)
    report_path = report_dir / f'ai标的价格跟踪_{date_value.isoformat()}.md'
    report_path.write_text(report, encoding='utf-8')
    print(report_path)

if __name__ == '__main__':
    main()
