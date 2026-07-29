#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from skill_resolver import resolve_skill_cli, skill_missing_message

SCRIPTS_DIR = Path(__file__).resolve().parent
# Skill 路径由 skill_resolver 统一解析（支持 YMOS_SKILL_ROOT 环境变量覆盖）
SKILL_CLI = resolve_skill_cli('hithink-astock-selector', '问财选A股/hithink-astock-selector')


def read_shell_env_var(name: str) -> str:
    if os.getenv(name):
        return os.getenv(name, '')
    for profile in [Path.home()/'.zprofile', Path.home()/'.zshrc', Path.home()/'.profile', Path.home()/'.bash_profile', Path.home()/'.bashrc']:
        if not profile.exists():
            continue
        try:
            for line in profile.read_text(encoding='utf-8', errors='ignore').splitlines():
                line = line.strip()
                if not line.startswith(f'export {name}='):
                    continue
                value = line.split('=', 1)[1].strip()
                if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                if value:
                    return value
        except Exception:
            continue
    return ''


def run_cli(query: str, page: int, limit: int, env: dict[str, str]) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(SKILL_CLI),
        '--query', query,
        '--page', str(page),
        '--limit', str(limit),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    if proc.returncode != 0:
        raise RuntimeError(f'CLI_ERROR exit={proc.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}')
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f'NON_JSON_OUTPUT\n{stdout}\n{stderr}') from e
    if not result.get('success'):
        raise RuntimeError(f"API_ERROR: {result.get('error', 'unknown')}")
    return result


def write_csv(rows: list[dict[str, Any]], csv_out: Path) -> None:
    headers: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            for k in row.keys():
                if k not in seen:
                    seen.add(k)
                    headers.append(k)
    with csv_out.open('w', encoding='utf-8-sig') as f:
        if not headers:
            f.write('message\nNo rows returned\n')
            return
        f.write(','.join('"' + h.replace('"', '""') + '"' for h in headers) + '\n')
        for row in rows:
            vals = []
            for h in headers:
                v = row.get(h, '') if isinstance(row, dict) else ''
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                vals.append('"' + str(v).replace('"', '""') + '"')
            f.write(','.join(vals) + '\n')


def main() -> int:
    p = argparse.ArgumentParser(description='Run 问财选A股 and save full raw JSON/CSV for YMOS What\'s Hot')
    p.add_argument('query', help='自然语言选股问句')
    p.add_argument('--json-out', required=True)
    p.add_argument('--csv-out', required=True)
    p.add_argument('--desc-out', required=True)
    p.add_argument('--status-out', required=True)
    p.add_argument('--page', default='1')
    p.add_argument('--limit', default='50')
    p.add_argument('--max-pages', type=int, default=200)
    p.add_argument('--fetch-all', action='store_true', default=True)
    p.add_argument('--no-fetch-all', dest='fetch_all', action='store_false')
    p.add_argument('--api-key', default=read_shell_env_var('IWENCAI_API_KEY'))
    args = p.parse_args()

    json_out = Path(args.json_out)
    csv_out = Path(args.csv_out)
    desc_out = Path(args.desc_out)
    status_out = Path(args.status_out)
    for pth in [json_out, csv_out, desc_out, status_out]:
        pth.parent.mkdir(parents=True, exist_ok=True)

    desc_out.write_text(
        f"query: {args.query}\nstart_page: {args.page}\nlimit: {args.limit}\nfetch_all: {args.fetch_all}\nmax_pages: {args.max_pages}\napi_url: {os.getenv('IWENCAI_BASE_URL', 'https://openapi.iwencai.com')}\n",
        encoding='utf-8',
    )

    if SKILL_CLI is None:
        message = skill_missing_message('hithink-astock-selector', "What's Hot / A股条件选股")
        status_out.write_text(message.strip() + '\n', encoding='utf-8')
        print(message)
        return 2

    env = os.environ.copy()
    if args.api_key:
        env['IWENCAI_API_KEY'] = args.api_key
    if not env.get('SSL_CERT_FILE'):
        try:
            import certifi  # type: ignore
            env['SSL_CERT_FILE'] = certifi.where()
        except Exception:
            pass

    start_page = int(args.page)
    limit = int(args.limit)
    try:
        first = run_cli(args.query, start_page, limit, env)
        total = int(first.get('code_count', 0) or 0)
        rows = list(first.get('datas', []) or [])
        pages = [first]
        fetched_pages = 1
        if args.fetch_all and total > len(rows):
            next_page = start_page + 1
            while len(rows) < total and fetched_pages < args.max_pages:
                page_result = run_cli(args.query, next_page, limit, env)
                page_rows = list(page_result.get('datas', []) or [])
                if not page_rows:
                    break
                rows.extend(page_rows)
                pages.append(page_result)
                fetched_pages += 1
                next_page += 1

        output = {
            'success': True,
            'query': args.query,
            'code_count': total,
            'returned_count': len(rows),
            'all_results_fetched': len(rows) >= total if total else True,
            'start_page': start_page,
            'limit': limit,
            'pages_fetched': fetched_pages,
            'chunks_info': first.get('chunks_info', {}),
            'datas': rows,
            'page_summaries': [
                {
                    'page': r.get('page'),
                    'returned_count': r.get('returned_count'),
                    'has_more': r.get('has_more'),
                }
                for r in pages
            ],
        }
        json_out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
        write_csv(rows, csv_out)
        status_out.write_text(
            f"OK: fetched result\nrows_extracted: {len(rows)}\ncode_count: {total}\npages_fetched: {fetched_pages}\nall_results_fetched: {output['all_results_fetched']}\nquery: {args.query}\n",
            encoding='utf-8',
        )
        print(f"✅ fetched result, extracted {len(rows)} rows (code_count={total}, pages={fetched_pages}, all={output['all_results_fetched']})")
        return 0
    except Exception as e:
        status_out.write_text(f'ERROR: {e}\n', encoding='utf-8')
        print(f'❌ {e}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
