#!/usr/bin/env python3
"""MX_StockPick runner for YMOS Eyes/What's Hot.

Uses EastMoney Miaoxiang stock screening endpoint directly.
- Loads EM_API_KEY from YMOS/.env via env_loader
- Sends natural-language keyword query
- Saves raw JSON + CSV + description/status files

This gives What's Hot a real execution path instead of a doc-only SOP.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from env_loader import load_dotenv

API_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/stock-screen"


def fetch_stockpick(keyword: str, api_key: str, page_no: int = 1, page_size: int = 100) -> dict[str, Any]:
    payload = {
        "keyword": keyword,
        "pageNo": page_no,
        "pageSize": page_size,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "apikey": api_key,
            "User-Agent": "YMOS-MX-StockPick/1.0",
            "Accept": "application/json",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON response: {body[:500]}") from exc


def extract_rows(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        if all(isinstance(x, dict) for x in obj):
            return obj
        rows = []
        for item in obj:
            rows.extend(extract_rows(item))
        return rows
    if isinstance(obj, dict):
        preferred = ["datalist", "dataList", "list", "rows", "result", "data", "items"]
        for key in preferred:
            if key in obj:
                rows = extract_rows(obj[key])
                if rows:
                    return rows
        rows = []
        for v in obj.values():
            rows.extend(extract_rows(v))
        return rows
    return []


def write_csv(rows: list[dict[str, Any]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with out_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["message"])
            writer.writerow(["No rows returned"])
        return
    headers = []
    seen = set()
    for row in rows:
        for k in row.keys():
            if k not in seen:
                seen.add(k)
                headers.append(k)
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            safe = {k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()}
            writer.writerow(safe)


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Run EastMoney MX_StockPick and save raw JSON/CSV")
    p.add_argument("keyword", help="Natural language stock screening query")
    p.add_argument("--json-out", required=True)
    p.add_argument("--csv-out", required=True)
    p.add_argument("--desc-out", required=True)
    p.add_argument("--status-out", required=True)
    p.add_argument("--page-no", type=int, default=1)
    p.add_argument("--page-size", type=int, default=100)
    p.add_argument("--api-key", default=os.getenv("EM_API_KEY", ""))
    args = p.parse_args()

    json_out = Path(args.json_out)
    csv_out = Path(args.csv_out)
    desc_out = Path(args.desc_out)
    status_out = Path(args.status_out)
    for pth in [json_out, csv_out, desc_out, status_out]:
        pth.parent.mkdir(parents=True, exist_ok=True)

    desc_out.write_text(
        f"keyword: {args.keyword}\npage_no: {args.page_no}\npage_size: {args.page_size}\napi_url: {API_URL}\n",
        encoding="utf-8",
    )

    if not args.api_key:
        status_out.write_text("FAIL: EM_API_KEY missing in env\n", encoding="utf-8")
        print("❌ EM_API_KEY missing")
        return 2

    try:
        result = fetch_stockpick(args.keyword, args.api_key, args.page_no, args.page_size)
        json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if isinstance(result, dict) and result.get("success") is False:
            status_out.write_text(
                f"API_ERROR: code={result.get('code')} status={result.get('status')} message={result.get('message')}\nkeyword: {args.keyword}\nrequestId: {result.get('requestId')}\n",
                encoding="utf-8",
            )
            print(f"❌ API error {result.get('code')}: {result.get('message')}")
            return 1
        rows = extract_rows(result)
        write_csv(rows, csv_out)
        status_out.write_text(
            f"OK: fetched result\nrows_extracted: {len(rows)}\nkeyword: {args.keyword}\n",
            encoding="utf-8",
        )
        print(f"✅ fetched result, extracted {len(rows)} rows")
        return 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        status_out.write_text(f"HTTP_ERROR: {exc.code} {exc.reason}\n{body[:2000]}\n", encoding="utf-8")
        print(f"❌ HTTP {exc.code}: {exc.reason}")
        print(body[:1000])
        return 1
    except Exception as exc:
        status_out.write_text(f"ERROR: {type(exc).__name__}: {exc}\n", encoding="utf-8")
        print(f"❌ {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
