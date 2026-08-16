#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from skill_resolver import resolve_skill_cli, skill_missing_message

# Skill 路径由 skill_resolver 统一解析（支持 YMOS_SKILL_ROOT 环境变量覆盖）
SKILL_CLI = resolve_skill_cli('hithink-usstock-selector', '问财选美股/hithink-usstock-selector')


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


def validate_us_result(query: str, rows: list[dict[str, Any]], chunks_info: Any = None) -> None:
    if not rows:
        return

    sample = rows[:5]
    a_share_codes = []
    a_share_schema_keys = set()
    a_share_domains = []
    for row in sample:
        if not isinstance(row, dict):
            continue
        code = str(row.get('股票代码', ''))
        if code.endswith(('.SZ', '.SH', '.BJ')):
            a_share_codes.append(code)
        domain = str(row.get('成分领域', ''))
        if 'A股' in domain or 'a股' in domain.lower():
            a_share_domains.append(domain)
        for key in row.keys():
            key_text = str(key)
            if 'a股' in key_text.lower():
                a_share_schema_keys.add(key_text)

    chunks_text = json.dumps(chunks_info, ensure_ascii=False) if chunks_info is not None else ''
    chunks_look_like_a_share = 'A股指数' in chunks_text or '成分领域等于A股' in chunks_text

    if a_share_codes or a_share_schema_keys or a_share_domains or chunks_look_like_a_share:
        hints = []
        if a_share_codes:
            hints.append(f"sample_a_share_codes={a_share_codes}")
        if a_share_schema_keys:
            hints.append(f"sample_a_share_schema_keys={sorted(a_share_schema_keys)}")
        if a_share_domains:
            hints.append(f"sample_a_share_domains={a_share_domains}")
        if chunks_look_like_a_share:
            hints.append('chunks_info_contains_a_share_index=true')
        raise RuntimeError(
            'US_RESULT_LOOKS_LIKE_A_SHARE: '
            f"query={query}; {'; '.join(hints)}; "
            'the API routed this request to A-share data. Reject this result and use only a '
            'validated US-stock template from the active SOP; do not retry by freely rewriting the query.'
        )


def main() -> int:
    p = argparse.ArgumentParser(description='Run 问财选美股 and save full raw JSON/CSV for YMOS')
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
        message = skill_missing_message('hithink-usstock-selector', '美股条件选股')
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
        validate_us_result(args.query, rows, first.get('chunks_info'))
        pages = [first]
        fetched_pages = 1
        if args.fetch_all and total > len(rows):
            next_page = start_page + 1
            while len(rows) < total and fetched_pages < args.max_pages:
                page_result = run_cli(args.query, next_page, limit, env)
                page_rows = list(page_result.get('datas', []) or [])
                if not page_rows:
                    # 与 A 股抓取器保持一致：空页先按瞬时失败重试一次。
                    time.sleep(1.0)
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
