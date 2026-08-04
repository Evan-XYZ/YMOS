#!/usr/bin/env python3
"""
YMOS Console — 决策台的本地数据服务。

它只做一件事：把决策台里填的东西，读写成你自己 Obsidian vault 里的 Markdown。

启动：
    cd 到本目录，跑 `python3 server.py`，浏览器开 http://localhost:5273

设计约束（和 YMOS 主仓一致）：
  1. 零依赖 —— 只用 Python 标准库，不装任何 pip 包。
  2. Markdown-first —— 所有产出都是纯 .md，落在你自己的 vault 里，没有数据库、没有 SaaS。
  3. 只绑 127.0.0.1 —— 不对外暴露。
  4. 路径由服务端生成 —— 客户端只能传日期，不能传路径，杜绝越权写入。

配置见同目录 config.example.json（复制成 config.json 后改）。
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# 配置：config.json 覆盖默认值；没有这个文件也能跑（回落到仓库自身目录）
# ---------------------------------------------------------------------------
DEFAULTS = {
    "vault_root": "",                    # 留空 = 用 Console/ 的上级目录（即 YMOS/）
    "plan_dir": "Brain/交易计划",         # 交易计划归档目录（相对 vault_root）
    "audit_dir": "Brain/决策审计",        # 决策留痕归档目录（相对 vault_root）
    "trade_dir": "Brain/买入卖出决策",    # 单笔交易生命周期档案（相对 vault_root）
    "reader_roots": {"ymos": "."},        # Reader 根目录（相对 vault_root）
    "reader_pages": {},                   # Reader 页面结构；空时从 config.example.json 读取
    "reader_custom_paths": [],            # 简易自定义入口；自动追加到 Reader 的“自定义工作区”
    "port": 5273,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    cfg_file = HERE / "config.json"
    if cfg_file.exists():
        try:
            user_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            if isinstance(user_cfg, dict):
                # 下划线开头的键是注释，忽略；空值表示「用默认」
                cfg.update({
                    k: v for k, v in user_cfg.items()
                    if not k.startswith("_") and k in DEFAULTS and v not in ("", None)
                })
        except (json.JSONDecodeError, OSError) as exc:
            print(f"⚠️  config.json 读取失败，改用默认配置：{exc}")
    return cfg


CONFIG = load_config()
VAULT_ROOT = Path(CONFIG["vault_root"]).expanduser().resolve() if CONFIG["vault_root"] else HERE.parent
ROOT_PLAN = (VAULT_ROOT / CONFIG["plan_dir"]).resolve()
ROOT_AUDIT = (VAULT_ROOT / CONFIG["audit_dir"]).resolve()
ROOT_TRADE = (VAULT_ROOT / CONFIG["trade_dir"]).resolve()
DRAFT_FILE = (ROOT_PLAN / "_当前草稿_自动备份.md").resolve()
TRADE_CLOSED = (ROOT_TRADE / "已平仓").resolve()
TRADE_VOID = (ROOT_TRADE / "已作废").resolve()
ACCOUNT_FILE = (ROOT_TRADE / "买卖决策_状态机.md").resolve()
PORT = int(CONFIG["port"])

def initial_account_markdown() -> str:
    """生成空账户状态机；只在目标 vault 尚无文件时使用。"""
    payload = {
        "version": 4,
        "accounts": {
            "CNY": {"capital": 0, "horizonFund": ""},
            "HKD": {"capital": 0, "horizonFund": ""},
            "USD": {"capital": 0, "horizonFund": ""},
        },
        "maxSingleRatio": 0.33,
        "changes": [],
        "settlements": [],
        "updated": "",
        "portfolioSnapshot": None,
    }
    return (
        "# 买卖决策 · 状态机\n\n"
        "> 买卖决策台的账户级参数、资金流水与最近一次 Agent 持仓体检快照。\n"
        "> 单笔交易 Markdown 仍是持仓事实源；`portfolioSnapshot` 是可重新生成的派生视图。\n\n"
        "<!-- ymos-trade-account：买卖决策台结构化数据，请勿手动修改 -->\n"
        "```json\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n```\n"
    )


def ensure_runtime_layout() -> None:
    """启动即补齐 Markdown-first 运行目录，而不是等第一次保存才创建。"""
    for directory in (ROOT_PLAN, ROOT_AUDIT, ROOT_TRADE, TRADE_CLOSED, TRADE_VOID):
        directory.mkdir(parents=True, exist_ok=True)
    if not ACCOUNT_FILE.exists():
        ACCOUNT_FILE.write_text(initial_account_markdown(), encoding="utf-8")

# Reader 默认页面结构来自 config.example.json。这样用户自己的 config.json 只写路径也能开箱运行。
if not CONFIG.get("reader_pages"):
    try:
        example_cfg = json.loads((HERE / "config.example.json").read_text(encoding="utf-8"))
        CONFIG["reader_pages"] = example_cfg.get("reader_pages", {})
    except (OSError, json.JSONDecodeError):
        CONFIG["reader_pages"] = {}

READER_ROOTS: dict[str, Path] = {}
for key, rel in (CONFIG.get("reader_roots") or {"ymos": "."}).items():
    if key.startswith("_"):
        continue
    raw = Path(str(rel)).expanduser()
    READER_ROOTS[key] = raw.resolve() if raw.is_absolute() else (VAULT_ROOT / raw).resolve()
READER_ROOTS.setdefault("ymos", VAULT_ROOT)

READER_MODES = {
    "tree", "flat-md", "flat-whitelist", "tree-text", "flat-text",
    "latest-month-dirs-text", "recent-days-text",
}

READER_PAGES: dict[str, dict] = {}
for key, page in (CONFIG.get("reader_pages") or {}).items():
    if key.startswith("_"):
        continue
    sections = []
    for sec in page.get("sections", []):
        cats = []
        for original_cat in sec.get("categories", []):
            cat = dict(original_cat)
            if isinstance(cat.get("whitelist"), list):
                cat["whitelist"] = set(cat["whitelist"])
            if cat.get("root") in READER_ROOTS:
                cats.append(cat)
        if cats:
            sections.append({**sec, "categories": cats})
    READER_PAGES[key] = {"label": page.get("label", key), "sections": sections}

def build_custom_reader_categories(items: list | None) -> list[dict]:
    """把简易路径配置转换成 Reader 分类，并拒绝相对路径越界。"""
    categories = []
    for index, item in enumerate(items or []):
        if isinstance(item, str):
            item = {"path": item}
        if not isinstance(item, dict) or not str(item.get("path", "")).strip():
            continue

        path_value = str(item["path"]).strip()
        raw_path = Path(path_value).expanduser()
        mode = str(item.get("mode", "tree-text"))
        if mode not in READER_MODES:
            print(f"⚠️  Reader 自定义路径模式无效，已跳过：{mode}")
            continue

        if raw_path.is_absolute():
            root_key = f"_custom_{index}"
            READER_ROOTS[root_key] = raw_path.resolve()
            rel = "."
            default_label = raw_path.name or f"自定义路径 {index + 1}"
        else:
            root_key = str(item.get("root", "ymos"))
            if root_key not in READER_ROOTS:
                print(f"⚠️  Reader 自定义路径 root 不存在，已跳过：{root_key}")
                continue
            root_base = READER_ROOTS[root_key].resolve()
            READER_ROOTS[root_key] = root_base
            target = (root_base / raw_path).resolve()
            if not target.is_relative_to(root_base):
                print(f"⚠️  Reader 自定义相对路径越界，已跳过：{path_value}")
                continue
            rel = str(raw_path)
            default_label = raw_path.name or f"自定义路径 {index + 1}"

        cat = {
            "label": str(item.get("label") or default_label),
            "root": root_key,
            "rel": rel,
            "mode": mode,
        }
        for key in ("months", "limit", "days", "fallback"):
            if key in item:
                cat[key] = item[key]
        if isinstance(item.get("whitelist"), list):
            cat["whitelist"] = set(item["whitelist"])
        categories.append(cat)
    return categories


# 用户新增产出目录时，不必复制整份 reader_pages。相对路径默认基于 vault_root，
# 绝对路径则成为一个显式只读根；目录可以暂时不存在，后续创建后会自动出现在列表中。
custom_categories = build_custom_reader_categories(CONFIG.get("reader_custom_paths"))

if custom_categories:
    page = READER_PAGES.setdefault("ymos", {"label": "YMOS Reader", "sections": []})
    page["sections"].append({
        "label": "自定义工作区",
        "icon": "🧩",
        "defaultOpen": False,
        "categories": custom_categories,
    })

TEXT_SUFFIXES = {
    ".md", ".markdown", ".txt", ".html", ".css", ".js", ".mjs", ".json",
    ".py", ".toml", ".yaml", ".yml",
}
SKIP_DIR_NAMES = {".git", ".obsidian", ".venv", "__pycache__", "node_modules", "dist", "build"}
READER_CATEGORIES: list[dict] = [
    cat
    for page in READER_PAGES.values()
    for sec in page["sections"]
    for cat in sec["categories"]
]

DATE_FULL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

# 一份计划 md 可含两块结构化数据：计划块（盘前定的，永远第一块）+ 执行块（盘中补的）
EXEC_DATA_MARK = "ymos-exec-data"
EXEC_SECTION_MARK = "<!-- ymos-exec-section -->"

MAX_BODY = 5_000_000

# ---------------------------------------------------------------------------
# 买入卖出决策：单笔交易生命周期（append-only）
# ---------------------------------------------------------------------------
TRADE_OPEN_MARK = "ymos-trade-open"
TRADE_EVENT_MARK = "ymos-trade-event"
TRADE_ACCOUNT_MARK = "ymos-trade-account"
CLOSED_MONTH_SPLIT = 12

TRADE_STATUS_PLAN = "计划中"
TRADE_STATUS_FILLING = "建仓中"      # 已有真实成交，但这份建仓计划还没建满
TRADE_STATUS_HELD = "持仓中"
TRADE_STATUS_CLOSED = "已平仓"
TRADE_STATUS_VOID = "已作废"        # 零成交的计划被主动放弃：不是交易结果，是这条记录本不该存在
# 有真实仓位的两种状态。「还没建满」不等于「没风险」——取价、卖出、平仓都要认它。
TRADE_STATUS_IN_MARKET = (TRADE_STATUS_FILLING, TRADE_STATUS_HELD)

_BAD_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_seg(value: str, limit: int = 48) -> str:
    """把标的名 / Ticker 净化成安全文件名片段。"""
    value = _BAD_NAME_CHARS.sub("", str(value or "")).strip().strip(".")
    value = re.sub(r"\s+", " ", value)
    return value[:limit]


def trade_filename(name: str, code: str, date: str) -> str | None:
    """生成 `{名称}_{Ticker}_{日期}.md`；客户端不能直接指定写入路径。"""
    if not DATE_FULL_RE.match(date or ""):
        return None
    safe_name, safe_code = sanitize_seg(name), sanitize_seg(code)
    if not safe_name and not safe_code:
        return None
    stem = "_".join(part for part in (safe_name, safe_code, date) if part)
    return stem[:120] + ".md"


def trade_open_path(filename: str) -> Path | None:
    """解析计划中 / 持仓中根目录文件；拒绝目录穿越与内部文件。"""
    if not filename or not filename.endswith(".md") or filename != Path(filename).name:
        return None
    if filename.startswith(("_", ".")):
        return None
    target = (ROOT_TRADE / filename).resolve()
    return target if target.parent == ROOT_TRADE else None


def find_trade_file(filename: str) -> Path | None:
    """先查活动文件，再递归查已平仓归档。"""
    active = trade_open_path(filename)
    if active is None:
        return None
    if active.exists():
        return active
    for archive in (TRADE_CLOSED, TRADE_VOID):
        if not archive.exists():
            continue
        for path in archive.rglob(filename):
            if path.is_file():
                return path.resolve()
    return None


def closed_dir_for(date: str) -> Path:
    """平仓少时按年归档；同年达到阈值后，新文件按月归档。"""
    year_dir = TRADE_CLOSED / date[:4]
    if not year_dir.exists():
        return year_dir
    count = sum(1 for path in year_dir.rglob("*.md") if not path.name.startswith("_"))
    return year_dir / date[:7] if count >= CLOSED_MONTH_SPLIT else year_dir


def parse_front_matter(text: str) -> dict:
    """解析本项目使用的平铺 `key: value` YAML front matter。"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    result: dict = {}
    for line in text[3:end].splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.split("#")[0].strip()
    return result


def set_front_matter(text: str, updates: dict) -> str:
    """只更新当前状态事实；JSON 事件流保持 append-only。"""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    lines = text[3:end].splitlines()
    for key, value in updates.items():
        replacement = f"{key}: {value}"
        for index, line in enumerate(lines):
            if line.strip().startswith(f"{key}:"):
                lines[index] = replacement
                break
        else:
            lines.append(replacement)
    return "---" + "\n".join(lines) + text[end:]


def _json_after(text: str, mark: str):
    index = text.find(mark)
    if index == -1:
        return None
    match = re.search(r"```json\s*\n(.*?)\n```", text[index:], re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def extract_trade_events(text: str) -> list:
    """读取所有追加事件，而不是只读取第一个 JSON 围栏。"""
    events = []
    pattern = re.escape(TRADE_EVENT_MARK) + r".*?\n```json\s*\n(.*?)\n```"
    for match in re.finditer(pattern, text, re.S):
        try:
            event = json.loads(match.group(1))
            if isinstance(event, dict):
                event.setdefault("schemaVersion", 1)
                events.append(event)
        except json.JSONDecodeError:
            continue
    return events


def parse_event_block(block: str, allowed_kinds: set[str]) -> dict | None:
    """校验前端提交的是一个完整事件块，并限制可走当前 endpoint 的事件类型。"""
    if not isinstance(block, str) or not block.strip() or TRADE_EVENT_MARK not in block:
        return None
    event = _json_after(block, TRADE_EVENT_MARK)
    if not isinstance(event, dict) or event.get("kind") not in allowed_kinds:
        return None
    event.setdefault("schemaVersion", 1)
    return event


def _fmt_num(value: float) -> str:
    """写回 front matter 的数字：去掉尾零，避免 60.00000000 这种噪音。"""
    return f"{float(value):.8f}".rstrip("0").rstrip(".") or "0"


def filled_amount(events: list) -> float:
    """累计已建仓金额：所有 fill 事件的实际成交额之和，不因后来减仓而回退。
    它是「建仓计划能缩到多低」的硬下限 —— 已经买进去的钱，改计划改不动。"""
    total = 0.0
    for event in events:
        if not isinstance(event, dict) or event.get("kind") != "fill":
            continue
        fill = event.get("fill")
        if not isinstance(fill, dict) or fill.get("finalizeOnly"):
            continue
        amount = _number(fill.get("actualAmount"))
        if amount is None:
            shares, price = _number(fill.get("shares")), _number(fill.get("price"))
            amount = shares * price if shares is not None and price is not None else 0.0
        total += amount
    return total


def count_fill_batches(events: list) -> int:
    """已经录过几笔真实成交（收口事件不算一笔）。"""
    total = 0
    for event in events:
        if not isinstance(event, dict) or event.get("kind") != "fill":
            continue
        fill = event.get("fill")
        if isinstance(fill, dict) and fill.get("finalizeOnly"):
            continue
        total += 1
    return total


def _number(value) -> float | None:
    """读取有限数值；交易事实不能接受 NaN / Infinity。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def trade_runtime(path: Path) -> tuple[str, dict, list]:
    """读取一笔交易当前状态；所有写接口都以服务端 Markdown 为准。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text, parse_front_matter(text), extract_trade_events(text)


def has_event(events: list, *kinds: str) -> bool:
    wanted = set(kinds)
    return any(isinstance(event, dict) and event.get("kind") in wanted for event in events)


def valid_calendar_date(value: str) -> bool:
    if not DATE_FULL_RE.match(value or ""):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _vault_rel(path: Path) -> str:
    try:
        return str(path.relative_to(VAULT_ROOT))
    except ValueError:
        return str(path)


def trade_summary(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    front = parse_front_matter(text)
    open_data = _json_after(text, TRADE_OPEN_MARK)
    if isinstance(open_data, dict):
        open_data.setdefault("schemaVersion", 1)
    events = extract_trade_events(text)
    return {
        "file": path.name,
        "front": front,
        "open": open_data,
        "events": events,
        "eventCount": len(events),
        "lastEvent": events[-1] if events else None,
        "rel": _vault_rel(path),
        "abs": str(path),
        "mtime": path.stat().st_mtime,
    }


def _collect_trade(path: Path, bucket: list) -> None:
    if not path.is_file() or path.suffix != ".md" or path.name.startswith(("_", ".")):
        return
    try:
        item = trade_summary(path)
    except OSError:
        return
    if item["front"].get("ymos_trade", "").lower() in ("true", "1", "yes", "v1"):
        bucket.append(item)


def list_trades() -> dict:
    """返回活动交易与递归归档交易，两种归档深度均兼容。"""
    open_items, closed_items, void_items = [], [], []
    if ROOT_TRADE.exists():
        for path in ROOT_TRADE.iterdir():
            _collect_trade(path, open_items)
    if TRADE_CLOSED.exists():
        for path in TRADE_CLOSED.rglob("*.md"):
            _collect_trade(path, closed_items)
    if TRADE_VOID.exists():
        for path in TRADE_VOID.rglob("*.md"):
            _collect_trade(path, void_items)
    for bucket in (open_items, closed_items, void_items):
        bucket.sort(key=lambda item: item["mtime"], reverse=True)
    return {"open": open_items, "closed": closed_items, "voided": void_items}


# ---------------------------------------------------------------------------
# 持仓行情：复用 Eyes 的三源价格路由器；失败不阻塞决策流程
# ---------------------------------------------------------------------------
PRICE_ROUTER = VAULT_ROOT / "Eyes" / "scripts" / "fetch_price_router.py"
STATE_FILES = [
    VAULT_ROOT / "持仓与关注" / "持仓_状态机.md",
    VAULT_ROOT / "持仓与关注" / "Watchlist_状态机.md",
]
PRICE_CACHE: dict = {"at": 0.0, "data": {}}
PRICE_TTL = 600
TICKER_RE = re.compile(r"^\^?[A-Z0-9]{1,10}(\.[A-Z]{2})?$")


def name_ticker_map() -> dict:
    """从持仓和 Watchlist 状态机提取 `标的名 → Ticker`。"""
    result: dict = {}
    for path in STATE_FILES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            name, ticker = cells[0], cells[1].strip("`").upper()
            if name and name != "名称" and TICKER_RE.match(ticker):
                result.setdefault(name, ticker)
    return result


def _norm_symbol(symbol: str) -> str:
    symbol = (symbol or "").upper()
    if ":" in symbol:
        return symbol.split(":", 1)[1].replace("USDT", "")
    if symbol.endswith("-USD"):
        return symbol[:-4]
    return symbol


def _parse_price_file(path: Path, output: dict, source: str) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return
    for row in payload.get("data", []):
        if not isinstance(row, dict) or row.get("ok") is False:
            continue
        symbol = _norm_symbol(row.get("symbol", ""))
        price = row.get("price", row.get("last_close"))
        if not symbol or price in (None, ""):
            continue
        pct = row.get("pct_chg", row.get("change_pct"))
        if pct is None:
            previous = row.get("prev_close") or row.get("pre_close")
            if previous is None:
                bars = row.get("bars") or []
                if len(bars) >= 2:
                    previous = bars[-2].get("close")
            if previous:
                try:
                    pct = (float(price) - float(previous)) / float(previous) * 100
                except (TypeError, ValueError, ZeroDivisionError):
                    pct = None
        output[symbol] = {"price": price, "pctChg": pct, "source": source}


def price_sources() -> dict:
    env_path = VAULT_ROOT / ".env"
    env_text = env_path.read_text(encoding="utf-8", errors="replace") if env_path.exists() else ""

    def configured(key: str) -> bool:
        for line in env_text.splitlines():
            line = line.strip()
            if line.startswith(key + "=") and line.split("=", 1)[1].strip():
                return True
        return bool(os.getenv(key, "").strip())

    return {
        "finnhub": configured("FINNHUB_API_KEY"),
        "tushare": configured("TUSHARE_TOKEN"),
        "yahoo": True,
        "router": PRICE_ROUTER.exists(),
    }


def fetch_prices(symbols: list[str]) -> dict:
    """调用现有路由器，返回已成功取得的部分行情。"""
    symbols = [symbol for symbol in dict.fromkeys(
        value.strip().upper() for value in symbols if value and value.strip()
    )]
    if not symbols or not PRICE_ROUTER.exists():
        return {}
    import tempfile

    output: dict = {}
    with tempfile.TemporaryDirectory() as tmp_dir:
        command = [
            sys.executable, str(PRICE_ROUTER),
            "--symbols", ",".join(symbols),
            "--output-dir", tmp_dir,
            "--date-tag", "latest",
        ]
        try:
            subprocess.run(
                command,
                cwd=str(VAULT_ROOT.parent),
                timeout=90,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        for source in ("finnhub", "tushare", "yahoo"):
            for path in Path(tmp_dir).glob(f"price_scan_{source}_*.json"):
                _parse_price_file(path, output, source)
    return output


# ---------------------------------------------------------------------------
# Reader：只读目录扫描与系统快捷操作
# ---------------------------------------------------------------------------
def is_text_file(path: Path, base: Path) -> bool:
    if path.name.startswith(".") or path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    try:
        rel_parts = path.relative_to(base).parts
    except ValueError:
        return False
    return not any(part in SKIP_DIR_NAMES for part in rel_parts[:-1])


def is_reader_path_allowed(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for cat in READER_CATEGORIES:
        base = (READER_ROOTS[cat["root"]] / cat["rel"]).resolve()
        mode = cat.get("mode")
        if mode == "flat-whitelist":
            if resolved.parent == base and resolved.name in cat.get("whitelist", set()):
                return True
        elif mode == "flat-md":
            if resolved.parent == base and resolved.suffix.lower() == ".md":
                return True
        elif mode == "flat-text":
            if resolved.parent == base and is_text_file(resolved, base):
                return True
        elif resolved.is_relative_to(base) and is_text_file(resolved, base):
            return True
    return False


def collect_reader_items(cat: dict) -> list[dict]:
    base_root = READER_ROOTS[cat["root"]]
    base = (base_root / cat["rel"]).resolve()
    if not base.exists():
        return []

    mode = cat["mode"]
    if mode == "tree":
        files = list(base.rglob("*.md"))
    elif mode == "flat-md":
        files = [p for p in base.iterdir() if p.is_file() and p.suffix == ".md"]
    elif mode == "flat-whitelist":
        whitelist = cat.get("whitelist", set())
        files = [p for p in base.iterdir() if p.is_file() and p.name in whitelist]
    elif mode == "tree-text":
        files = [p for p in base.rglob("*") if p.is_file() and is_text_file(p, base)]
    elif mode == "flat-text":
        files = [p for p in base.iterdir() if p.is_file() and is_text_file(p, base)]
    elif mode == "latest-month-dirs-text":
        months = int(cat.get("months", cat.get("limit", 2)))
        month_dirs = sorted(
            [p for p in base.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}", p.name)],
            key=lambda p: p.name,
            reverse=True,
        )[:months]
        files = [
            p for month_dir in month_dirs for p in month_dir.rglob("*")
            if p.is_file() and is_text_file(p, month_dir)
        ]
    elif mode == "recent-days-text":
        all_files = [p for p in base.rglob("*") if p.is_file() and is_text_file(p, base)]
        cutoff = time.time() - int(cat.get("days", 31)) * 86400
        files = [p for p in all_files if p.stat().st_mtime >= cutoff]
        if not files:
            files = sorted(all_files, key=lambda p: p.stat().st_mtime, reverse=True)[:int(cat.get("fallback", 10))]
    else:
        files = []

    items = []
    for file in files:
        if file.name.startswith("."):
            continue
        match = DATE_RE.search(file.name) or DATE_RE.search(str(file.parent))
        items.append({
            "name": file.name,
            "title": file.stem,
            "date": match.group(1) if match else "",
            "root": cat["root"],
            "path": str(file.relative_to(base_root)),
            "abs": str(file),
            "ext": file.suffix.lower(),
            "mtime": file.stat().st_mtime,
        })
    items.sort(key=lambda item: (item["date"], item["mtime"]), reverse=True)
    return items


def list_reader_pages() -> list[dict]:
    return [{"key": key, "label": page["label"]} for key, page in READER_PAGES.items()]


def list_reader_reports(page_key: str = "ymos") -> list[dict]:
    page = READER_PAGES.get(page_key) or next(iter(READER_PAGES.values()), {"sections": []})
    return [{
        "label": sec["label"],
        "icon": sec["icon"],
        "defaultOpen": bool(sec.get("defaultOpen")),
        "categories": [
            {"label": cat["label"], "items": collect_reader_items(cat)}
            for cat in sec["categories"]
        ],
    } for sec in page["sections"]]


def reveal_in_file_manager(target: Path) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(target)])
        elif sys.platform.startswith("win"):
            subprocess.Popen(["explorer", f"/select,{target}"])
        else:
            subprocess.Popen(["xdg-open", str(target.parent)])
        return True
    except (OSError, FileNotFoundError):
        return False


def copy_to_clipboard(text: str) -> bool:
    commands = {
        "darwin": [["pbcopy"]],
        "win32": [["clip"]],
    }.get(sys.platform, [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-ib"]])
    for command in commands:
        try:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE)
            proc.communicate(text.encode("utf-8"))
            if proc.returncode == 0:
                return True
        except (OSError, FileNotFoundError):
            continue
    return False


# ---------------------------------------------------------------------------
# Markdown 解析 / 路径映射
# ---------------------------------------------------------------------------
def extract_plan_json(text: str):
    """抽计划块：文件里第一个 json 围栏。抽不到返回 None。"""
    m = re.search(r"```json\s*\n(.*?)\n```", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def extract_exec_json(text: str):
    """抽执行块：EXEC_DATA_MARK 之后的那个 json 围栏。没有返回 None。"""
    i = text.find(EXEC_DATA_MARK)
    if i == -1:
        return None
    m = re.search(r"```json\s*\n(.*?)\n```", text[i:], re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def plan_file_for(date: str) -> Path | None:
    """YYYY-MM-DD → <plan_dir>/YYYY-MM/YYYY-MM-DD日交易计划.md。日期非法返回 None。"""
    if not DATE_FULL_RE.match(date or ""):
        return None
    return (ROOT_PLAN / date[:7] / f"{date}日交易计划.md").resolve()


def audit_file_for(date: str) -> Path | None:
    """YYYY-MM-DD → <audit_dir>/YYYY-MM/YYYY-MM-DD决策记录.md。日期非法返回 None。"""
    if not DATE_FULL_RE.match(date or ""):
        return None
    return (ROOT_AUDIT / date[:7] / f"{date}决策记录.md").resolve()


def render_audit_entry(payload: dict) -> str:
    """把一次决策台审计渲染成一段 Markdown（追加写入当日文件）。"""
    ts = datetime.now().strftime("%H:%M:%S")
    mode = str(payload.get("modeLabel") or payload.get("mode") or "未命名模式")
    passed = bool(payload.get("passed"))
    verdict = "✅ 放行（扣扳机）" if passed else "🛑 拦截（未全绿）"
    target = str(payload.get("target") or "").strip()
    ticker = str(payload.get("ticker") or "").strip().upper()
    trade_file = str(payload.get("tradeFile") or "").strip()
    note = str(payload.get("note") or "").strip()
    stance = str(payload.get("stance") or "").strip()

    lines = [f"## {ts} · {mode} · {verdict}", ""]
    meta = []
    if target:
        meta.append(f"- **标的/场景**：{target}")
    if ticker:
        meta.append(f"- **Ticker**：{ticker}")
    if trade_file:
        meta.append(f"- **交易文件**：`{Path(trade_file).name}`")
    if stance:
        meta.append(f"- **当日定调**：{stance}")
    if meta:
        lines.extend(meta)
        lines.append("")

    for section in payload.get("gates") or []:
        if not isinstance(section, dict):
            continue
        lines.append(f"**{section.get('label', '未命名门')}**")
        lines.append("")
        for item in section.get("items") or []:
            if not isinstance(item, dict):
                continue
            box = "x" if item.get("checked") else " "
            flag = " 🚩红线" if item.get("redline") else ""
            lines.append(f"- [{box}] {item.get('label', '')}{flag}")
        lines.append("")

    missed = [str(x) for x in (payload.get("missing") or []) if str(x).strip()]
    if missed:
        lines.append(f"> **未勾选**：{'、'.join(missed)}")
        lines.append("")
    if note:
        lines.append(f"> **备注**：{note}")
        lines.append("")

    audit_data = {
        "schemaVersion": 1,
        "kind": "decision_audit",
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": str(payload.get("mode") or ""),
        "passed": passed,
        "target": target,
        "ticker": ticker,
        "tradeFile": Path(trade_file).name if trade_file else "",
        "missing": missed,
    }
    lines.extend([
        "<!-- ymos-decision-audit -->",
        "```json",
        json.dumps(audit_data, ensure_ascii=False, indent=2),
        "```",
        "",
    ])

    lines.append("---")
    lines.append("")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
STATIC_ROUTES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/reader": "reader.html",
    "/reader.html": "reader.html",
    "/plan": "交易计划台.html",
    "/交易计划台.html": "交易计划台.html",
    "/decide": "买卖决策台.html",
    "/买卖决策台.html": "买卖决策台.html",
    "/sop": "买卖决策台.html",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send_json(self, code: int, payload, *, allow_file_preview: bool = False) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # 只给只读 health 接口开放 file:// 探测。交易写接口绝不开放跨域，
        # 避免任意网页借本机服务改写用户的 vault。
        if allow_file_preview:
            self.send_header("Access-Control-Allow-Origin", "null")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, mime: str) -> None:
        if not path.exists():
            self.send_response(404)
            self.end_headers()
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            length = 0
        if length <= 0 or length > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _resolve_reader_target(self, qs: dict) -> Path | None:
        root_key = (qs.get("root", ["ymos"]) or ["ymos"])[0]
        rel = (qs.get("path", [""]) or [""])[0]
        root = READER_ROOTS.get(root_key)
        if root is None or not rel:
            return None
        target = (root / rel).resolve()
        if not is_reader_path_allowed(target) or not target.exists() or not target.is_file():
            return None
        return target

    # -- GET ----------------------------------------------------------------
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        path = parsed.path

        if path in STATIC_ROUTES:
            self._send_file(HERE / STATIC_ROUTES[path], "text/html")
            return

        # Reader：同一端口下的只读报告浏览 API
        if path == "/api/reader/pages":
            self._send_json(200, list_reader_pages())
            return

        if path == "/api/reader/list":
            page_key = (qs.get("view", ["ymos"]) or ["ymos"])[0]
            self._send_json(200, list_reader_reports(page_key))
            return

        if path == "/api/reader/file":
            target = self._resolve_reader_target(qs)
            if target is None:
                self._send_json(403, {"error": "forbidden or missing"})
                return
            self._send_json(200, {
                "abs": str(target),
                "ext": target.suffix.lower(),
                "content": target.read_text(encoding="utf-8", errors="replace"),
            })
            return

        if path == "/api/reader/reveal":
            target = self._resolve_reader_target(qs)
            if target is None:
                self._send_json(403, {"error": "forbidden"})
                return
            ok = reveal_in_file_manager(target)
            self._send_json(200 if ok else 500, {
                "ok": ok,
                "error": None if ok else "当前平台不支持在文件管理器中显示",
            })
            return

        if path == "/api/reader/copy-path":
            target = self._resolve_reader_target(qs)
            if target is None:
                self._send_json(403, {"error": "forbidden"})
                return
            ok = copy_to_clipboard(str(target))
            self._send_json(200, {"ok": ok, "abs": str(target)})
            return

        # 规则文件：决策台启动时拉一次，拉不到就用页面内置默认
        if path == "/rules.json":
            for name in ("rules.json", "rules.example.json"):
                f = HERE / name
                if f.exists():
                    self._send_file(f, "application/json")
                    return
            self._send_json(404, {"error": "no rules file"})
            return

        # file:// 预览只允许探测服务是否存在，不暴露 vault 路径，也不开任何写接口跨域。
        if path == "/api/ping":
            self._send_json(200, {"ok": True, "storage": "markdown"}, allow_file_preview=True)
            return

        # 连接状态：由同源正式页面读取，包含实际 Markdown 目录。
        if path == "/api/health":
            self._send_json(200, {
                "ok": True,
                "storage": "markdown",
                "vaultRoot": str(VAULT_ROOT),
                "planDir": str(ROOT_PLAN),
                "auditDir": str(ROOT_AUDIT),
                "tradeDir": str(ROOT_TRADE),
                "planDirExists": ROOT_PLAN.exists(),
                "tradeDirExists": ROOT_TRADE.exists(),
                "accountStateExists": ACCOUNT_FILE.exists(),
            })
            return

        # 读某日计划归档，抽出结构化 JSON 回填前端
        if path == "/api/plan/load":
            date = (qs.get("date", [""]) or [""])[0]
            target = plan_file_for(date)
            if target is None:
                self._send_json(400, {"error": "bad date"}); return
            if not target.exists():
                self._send_json(200, {"found": False}); return
            text = target.read_text(encoding="utf-8", errors="replace")
            data = extract_plan_json(text)
            if data is None:
                self._send_json(200, {"found": False}); return
            self._send_json(200, {"found": True, "state": data, "exec": extract_exec_json(text)})
            return

        # 兼容旧版：读「严格早于某日」的最近一份盘前计划。
        if path == "/api/plan/latest":
            before = (qs.get("before", [""]) or [""])[0]
            if not DATE_FULL_RE.match(before or ""):
                self._send_json(400, {"error": "bad before"}); return
            candidates = []
            if ROOT_PLAN.exists():
                for md in ROOT_PLAN.rglob("*日交易计划.md"):
                    m = DATE_RE.search(md.name)
                    if m and m.group(1) < before:
                        candidates.append((m.group(1), md))
            candidates.sort(key=lambda x: x[0], reverse=True)
            for d, md in candidates:
                text = md.read_text(encoding="utf-8", errors="replace")
                data = extract_plan_json(text)
                if data is not None:
                    self._send_json(200, {"found": True, "date": d, "state": data,
                                          "exec": extract_exec_json(text)})
                    return
            self._send_json(200, {"found": False})
            return

        # 盘中自动数据源：优先读取执行日当天的盘前计划；若没有，则回退到
        # 最近一份更早的旧版计划。这样既支持收盘后提前做下一交易日计划，
        # 也支持第二天开盘前补计划，同时不让 V4.0 的历史计划失效。
        if path == "/api/plan/current":
            date = (qs.get("date", [""]) or [""])[0]
            if not DATE_FULL_RE.match(date or ""):
                self._send_json(400, {"error": "bad date"}); return
            candidates = []
            if ROOT_PLAN.exists():
                for md in ROOT_PLAN.rglob("*日交易计划.md"):
                    match = DATE_RE.search(md.name)
                    if match and match.group(1) <= date:
                        candidates.append((match.group(1), md))
            candidates.sort(key=lambda item: item[0], reverse=True)
            for plan_date, md in candidates:
                text = md.read_text(encoding="utf-8", errors="replace")
                data = extract_plan_json(text)
                if data is not None:
                    self._send_json(200, {
                        "found": True,
                        "date": plan_date,
                        "match": "exact" if plan_date == date else "fallback",
                        "state": data,
                        "exec": extract_exec_json(text),
                    })
                    return
            self._send_json(200, {"found": False})
            return

        # 列出所有已存计划日期（供执行台手动选数据源）
        if path == "/api/plan/dates":
            dates = []
            if ROOT_PLAN.exists():
                for md in ROOT_PLAN.rglob("*日交易计划.md"):
                    m = DATE_RE.search(md.name)
                    if m:
                        dates.append(m.group(1))
            self._send_json(200, {"dates": sorted(set(dates), reverse=True)})
            return

        # 读草稿镜像（浏览器缓存被清后恢复常驻名单）
        if path == "/api/plan/draft":
            if not DRAFT_FILE.exists():
                self._send_json(200, {"found": False}); return
            data = extract_plan_json(DRAFT_FILE.read_text(encoding="utf-8", errors="replace"))
            if data is None:
                self._send_json(200, {"found": False}); return
            self._send_json(200, {"found": True, "state": data})
            return

        if path == "/api/trade/list":
            self._send_json(200, list_trades())
            return

        if path == "/api/trade/load":
            filename = (qs.get("file", [""]) or [""])[0]
            target = find_trade_file(filename)
            if target is None:
                self._send_json(200, {"found": False})
                return
            payload = trade_summary(target)
            payload["found"] = True
            payload["markdown"] = target.read_text(encoding="utf-8", errors="replace")
            self._send_json(200, payload)
            return

        if path == "/api/trade/prices":
            mapping = name_ticker_map()
            wanted, resolved, unresolved = [], {}, []
            for item in list_trades()["open"]:
                front, open_data = item["front"], (item["open"] or {})
                if front.get("状态") not in TRADE_STATUS_IN_MARKET + (None,):
                    continue
                name = front.get("标的", "")
                ticker = (open_data.get("ticker") or front.get("Ticker") or mapping.get(name) or "").strip().upper()
                if ticker:
                    wanted.append(ticker)
                    resolved[name] = ticker
                elif name:
                    unresolved.append(name)
            force = (qs.get("force", ["0"]) or ["0"])[0] == "1"
            if not force and PRICE_CACHE["data"] and time.time() - PRICE_CACHE["at"] < PRICE_TTL:
                prices = PRICE_CACHE["data"]
            else:
                prices = fetch_prices(wanted)
                if prices:
                    PRICE_CACHE.update(at=time.time(), data=prices)
            self._send_json(200, {
                "prices": prices,
                "resolved": resolved,
                "unresolved": unresolved,
                "asOf": time.strftime("%Y-%m-%d %H:%M", time.localtime(PRICE_CACHE["at"] or time.time())),
                "sources": price_sources(),
            })
            return

        if path == "/api/trade/account":
            if not ACCOUNT_FILE.exists():
                self._send_json(200, {"found": False})
                return
            account = _json_after(
                ACCOUNT_FILE.read_text(encoding="utf-8", errors="replace"),
                TRADE_ACCOUNT_MARK,
            )
            if not isinstance(account, dict):
                self._send_json(200, {"found": False})
                return
            account.setdefault("schemaVersion", 1)
            self._send_json(200, {"found": True, "account": account})
            return

        self.send_response(404)
        self.end_headers()

    # -- POST ---------------------------------------------------------------
    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path

        # 保存某日交易计划 → <plan_dir>/YYYY-MM/YYYY-MM-DD日交易计划.md
        if path == "/api/plan/save":
            payload = self._read_json_body()
            if payload is None:
                self._send_json(400, {"error": "bad body"}); return
            target = plan_file_for(str(payload.get("date", "")))
            if target is None:
                self._send_json(400, {"error": "bad date"}); return
            markdown = payload.get("markdown", "")
            if not isinstance(markdown, str) or not markdown.strip():
                self._send_json(400, {"error": "empty markdown"}); return
            # 若来的是纯计划（无执行区）而旧文件已有执行区，保留旧执行区，
            # 避免收盘复盘覆盖当日已记录的执行情况
            if EXEC_SECTION_MARK not in markdown and target.exists():
                old = target.read_text(encoding="utf-8", errors="replace")
                i = old.find(EXEC_SECTION_MARK)
                if i != -1:
                    markdown = markdown.rstrip() + "\n\n" + old[i:]
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(markdown, encoding="utf-8")
            except OSError as exc:
                self._send_json(500, {"error": f"write failed: {exc}"}); return
            self._send_json(200, {"ok": True, "abs": str(target)})
            return

        # 写实时草稿镜像（固定单文件，随编辑 debounce 刷新）
        if path == "/api/plan/draft":
            payload = self._read_json_body()
            if payload is None:
                self._send_json(400, {"error": "bad body"}); return
            markdown = payload.get("markdown", "")
            if not isinstance(markdown, str) or not markdown.strip():
                self._send_json(400, {"error": "empty markdown"}); return
            try:
                DRAFT_FILE.parent.mkdir(parents=True, exist_ok=True)
                DRAFT_FILE.write_text(markdown, encoding="utf-8")
            except OSError as exc:
                self._send_json(500, {"error": f"write failed: {exc}"}); return
            self._send_json(200, {"ok": True})
            return

        # 决策留痕：每次扣扳机 / 被拦截，追加一条到 <audit_dir>/YYYY-MM/YYYY-MM-DD决策记录.md
        if path == "/api/audit/save":
            payload = self._read_json_body()
            if payload is None:
                self._send_json(400, {"error": "bad body"}); return
            date = str(payload.get("date", "")) or datetime.now().strftime("%Y-%m-%d")
            target = audit_file_for(date)
            if target is None:
                self._send_json(400, {"error": "bad date"}); return
            entry = render_audit_entry(payload)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    header = f"# {date} 决策记录\n\n> 由 YMOS Console · 买卖决策台自动留痕。每一次扣扳机和每一次被拦截都在这里。\n\n"
                    target.write_text(header + entry, encoding="utf-8")
                else:
                    with target.open("a", encoding="utf-8") as fh:
                        fh.write(entry)
            except OSError as exc:
                self._send_json(500, {"error": f"write failed: {exc}"}); return
            self._send_json(200, {"ok": True, "abs": str(target)})
            return

        # 买入逻辑建档：服务端生成文件名，已有文件绝不覆盖。
        if path == "/api/trade/open":
            payload = self._read_json_body()
            if payload is None:
                self._send_json(400, {"error": "bad body"}); return
            filename = trade_filename(
                payload.get("name", ""),
                payload.get("code", ""),
                str(payload.get("date", "")),
            )
            markdown = payload.get("markdown", "")
            if filename is None or not valid_calendar_date(str(payload.get("date", ""))):
                self._send_json(400, {"error": "bad name/code/date"}); return
            if not isinstance(markdown, str) or not markdown.strip():
                self._send_json(400, {"error": "empty markdown"}); return
            front = parse_front_matter(markdown)
            open_data = _json_after(markdown, TRADE_OPEN_MARK)
            if front.get("ymos_trade", "").lower() not in ("true", "1", "yes", "v1") or not isinstance(open_data, dict):
                self._send_json(400, {"error": "invalid trade markdown"}); return
            name = str(payload.get("name", "")).strip()
            code = str(payload.get("code", "")).strip().upper()
            date = str(payload.get("date", ""))
            open_name = str(open_data.get("symbol", "")).strip()
            open_code = str(open_data.get("ticker", "")).strip().upper()
            open_date = str(open_data.get("openDate") or open_data.get("date") or "")
            front_name = str(front.get("标的", "")).strip()
            front_code = str(front.get("Ticker", "")).strip().upper()
            front_date = str(front.get("建仓决策日") or front.get("创建日期") or "")
            if (
                open_data.get("kind") != "open"
                or front.get("状态") != TRADE_STATUS_PLAN
                or open_name != name
                or front_name != name
                or open_date != date
                or front_date != date
                or (code and (open_code != code or front_code != code))
                or (not code and (open_code or front_code))
            ):
                self._send_json(400, {"error": "trade identity mismatch"}); return
            if find_trade_file(filename) is not None:
                self._send_json(409, {"error": "exists", "file": filename}); return
            target = trade_open_path(filename)
            if target is None:
                self._send_json(400, {"error": "bad path"}); return
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(markdown, encoding="utf-8")
            except OSError as exc:
                self._send_json(500, {"error": f"write failed: {exc}"}); return
            self._send_json(200, {"ok": True, "file": filename, "rel": _vault_rel(target)})
            return

        # prepare / revise / add / adjust：只能追加到活动文件。
        if path == "/api/trade/append":
            payload = self._read_json_body()
            if payload is None:
                self._send_json(400, {"error": "bad body"}); return
            target = find_trade_file(str(payload.get("file", "")))
            if target is None:
                self._send_json(404, {"error": "trade file not found"}); return
            if target.parent != ROOT_TRADE:
                self._send_json(409, {"error": "trade is already closed"}); return
            block = payload.get("block", "")
            event = parse_event_block(block, {"prepare", "revise", "add", "trim", "adjust"})
            if event is None:
                self._send_json(400, {"error": "invalid event block"}); return
            _, front, events = trade_runtime(target)
            status = front.get("状态")
            kind = event.get("kind")
            prepared = has_event(events, "prepare", "revise")
            filled = has_event(events, "fill")
            allowed = (
                (kind == "prepare" and status == TRADE_STATUS_PLAN and not prepared and not filled)
                or (kind == "revise" and status == TRADE_STATUS_PLAN and prepared and not filled)
                # add 改的是「建仓计划总额」，不改持仓事实：股数 / 成本价只由 fill 事件写。
                # 执行后状态回到「建仓中」，实际成交回 /api/trade/fill 分批录入。
                or (
                    kind == "add" and status in TRADE_STATUS_IN_MARKET and filled
                    and event.get("planOnly") is True
                    and event.get("changesPositionFacts") is False
                )
                # 缩减建仓计划：只对「还没建满」的文件有意义；持仓中没有未执行的计划可缩。
                or (
                    kind == "trim" and status == TRADE_STATUS_FILLING and filled
                    and event.get("planOnly") is True
                    and event.get("changesPositionFacts") is False
                )
                or (kind == "adjust" and status in TRADE_STATUS_IN_MARKET and filled)
            )
            if not allowed:
                self._send_json(409, {"error": "illegal trade transition", "status": status, "kind": kind}); return
            updates = {}
            if kind in ("add", "trim"):
                planned_total = _number(event.get("plannedTotal"))
                if planned_total is None or planned_total <= 0:
                    self._send_json(400, {"error": "bad plannedTotal"}); return
                already = filled_amount(events)
                # 硬下限：计划不能低于已经买进去的钱。想低于，那要说的是「这笔到此为止」，
                # 对应动作是建仓收口（fill + complete），不是改计划。
                if planned_total < already - 0.01:
                    self._send_json(400, {
                        "error": "plan below filled amount",
                        "plannedTotal": planned_total, "filledAmount": already,
                    }); return
                plan_meta = event.get("plan") if isinstance(event.get("plan"), dict) else {}
                if kind == "trim" and not str(plan_meta.get("reason", "")).strip():
                    self._send_json(400, {"error": "trim requires reason"}); return
                updates["建仓计划"] = _fmt_num(planned_total)
                # 缩到刚好等于已建仓 = 这笔建仓就此收口
                if kind == "trim" and planned_total <= already + 0.01:
                    updates["状态"] = TRADE_STATUS_HELD
                else:
                    updates["状态"] = TRADE_STATUS_FILLING
            try:
                with target.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + block.rstrip() + "\n")
                if updates:
                    text = target.read_text(encoding="utf-8", errors="replace")
                    target.write_text(set_front_matter(text, updates), encoding="utf-8")
            except OSError as exc:
                self._send_json(500, {"error": f"append failed: {exc}"}); return
            self._send_json(200, {"ok": True, "file": target.name, "rel": _vault_rel(target),
                                  "status": updates.get("状态", status)})
            return

        # 部分卖出：追加事件，同时更新剩余股数和剩余成本。
        if path == "/api/trade/sell":
            payload = self._read_json_body()
            if payload is None:
                self._send_json(400, {"error": "bad body"}); return
            target = find_trade_file(str(payload.get("file", "")))
            if target is None:
                self._send_json(404, {"error": "trade file not found"}); return
            if target.parent != ROOT_TRADE:
                self._send_json(409, {"error": "trade is already closed"}); return
            block = payload.get("block", "")
            event = parse_event_block(block, {"tp", "sl"})
            if event is None:
                self._send_json(400, {"error": "invalid sell event"}); return
            _, front, events = trade_runtime(target)
            # 建仓中也能减仓 —— 仓位是真的，止损不该等到建满才允许执行。
            if front.get("状态") not in TRADE_STATUS_IN_MARKET or not has_event(events, "fill"):
                self._send_json(409, {"error": "illegal trade transition"}); return
            current_shares = _number(front.get("持仓股数"))
            cost_price = _number(front.get("成本价"))
            sell = event.get("sell") if isinstance(event.get("sell"), dict) else {}
            before = _number(sell.get("beforeShares"))
            sold = _number(sell.get("sellShares"))
            declared_remaining = _number(sell.get("remainingShares"))
            if (
                current_shares is None or current_shares <= 0
                or cost_price is None or cost_price < 0
                or before is None or abs(before - current_shares) > 1e-8
                or sold is None or sold <= 0 or sold >= current_shares
            ):
                self._send_json(400, {"error": "bad sell facts"}); return
            remaining = current_shares - sold
            if declared_remaining is None or abs(declared_remaining - remaining) > 1e-8:
                self._send_json(400, {"error": "sell remainder mismatch"}); return
            updates = {
                "持仓股数": f"{remaining:.8f}".rstrip("0").rstrip("."),
                "实际投入": f"{remaining * cost_price:.8f}".rstrip("0").rstrip("."),
            }
            try:
                with target.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + block.rstrip() + "\n")
                text = target.read_text(encoding="utf-8", errors="replace")
                target.write_text(set_front_matter(text, updates), encoding="utf-8")
            except OSError as exc:
                self._send_json(500, {"error": f"sell failed: {exc}"}); return
            self._send_json(200, {"ok": True, "file": target.name, "rel": _vault_rel(target)})
            return

        # 全部平仓：追加结果事件、更新状态，再移动到归档目录。
        if path == "/api/trade/close":
            payload = self._read_json_body()
            if payload is None:
                self._send_json(400, {"error": "bad body"}); return
            target = find_trade_file(str(payload.get("file", "")))
            if target is None:
                self._send_json(404, {"error": "trade file not found"}); return
            if target.parent != ROOT_TRADE:
                self._send_json(409, {"error": "trade is already closed"}); return
            block = payload.get("block", "")
            close_date = str(payload.get("closeDate", ""))
            event = parse_event_block(block, {"close"})
            if event is None:
                self._send_json(400, {"error": "invalid close event"}); return
            if not valid_calendar_date(close_date):
                self._send_json(400, {"error": "bad closeDate"}); return
            _, front, events = trade_runtime(target)
            # 建仓中同样可以整笔平掉 —— 没建满不是继续扛着的理由。
            if front.get("状态") not in TRADE_STATUS_IN_MARKET or not has_event(events, "fill"):
                self._send_json(409, {"error": "illegal trade transition"}); return
            current_shares = _number(front.get("持仓股数"))
            sell = event.get("sell") if isinstance(event.get("sell"), dict) else {}
            before = _number(sell.get("beforeShares"))
            sold = _number(sell.get("sellShares"))
            remaining = _number(sell.get("remainingShares"))
            if (
                current_shares is None or current_shares <= 0
                or before is None or abs(before - current_shares) > 1e-8
                or sold is None or abs(sold - current_shares) > 1e-8
                or remaining is None or abs(remaining) > 1e-8
            ):
                self._send_json(400, {"error": "bad close facts"}); return
            destination_dir = closed_dir_for(close_date)
            destination = destination_dir / target.name
            if destination.exists():
                self._send_json(409, {"error": "archive target exists"}); return
            try:
                with target.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + block.rstrip() + "\n")
                text = target.read_text(encoding="utf-8", errors="replace")
                text = set_front_matter(text, {
                    "状态": TRADE_STATUS_CLOSED,
                    "平仓日": close_date,
                    "持仓股数": 0,
                    "实际投入": 0,
                })
                target.write_text(text, encoding="utf-8")
                destination_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(destination))
            except OSError as exc:
                self._send_json(500, {"error": f"close failed: {exc}"}); return
            self._send_json(200, {"ok": True, "file": destination.name, "rel": _vault_rel(destination)})
            return

        # 确认建仓：计划中 →（分批）建仓中 → 持仓中，同时累加成交事实。
        # 建仓允许多笔：每次只送「本次这一笔」的增量，累计股数与加权成本由服务端按
        # front matter 里的既有事实推进 —— 界面算错了也污染不了账本。
        if path == "/api/trade/fill":
            payload = self._read_json_body()
            if payload is None:
                self._send_json(400, {"error": "bad body"}); return
            target = find_trade_file(str(payload.get("file", "")))
            if target is None:
                self._send_json(404, {"error": "trade file not found"}); return
            if target.parent != ROOT_TRADE:
                self._send_json(409, {"error": "trade is already closed"}); return
            block = payload.get("block", "")
            fill_date = str(payload.get("fillDate", ""))
            event = parse_event_block(block, {"fill"})
            if event is None:
                self._send_json(400, {"error": "invalid fill event"}); return
            if not valid_calendar_date(fill_date):
                self._send_json(400, {"error": "bad fillDate"}); return
            _, front, events = trade_runtime(target)
            status = front.get("状态")
            # 计划中 = 还没成交过；建仓中 = 建了一部分，继续分批录。
            if status not in (TRADE_STATUS_PLAN, TRADE_STATUS_FILLING) or not has_event(events, "prepare", "revise"):
                self._send_json(409, {"error": "illegal trade transition", "status": status}); return
            event_fill = event.get("fill") if isinstance(event.get("fill"), dict) else {}
            complete = bool(payload.get("complete"))
            finalize_only = bool(payload.get("finalizeOnly"))
            if bool(event_fill.get("complete")) != complete or bool(event_fill.get("finalizeOnly")) != finalize_only:
                self._send_json(400, {"error": "fill flag mismatch"}); return

            previous_shares = _number(front.get("持仓股数")) or 0.0
            previous_cost = _number(front.get("成本价")) or 0.0
            previous_amount = _number(front.get("实际投入"))
            if previous_amount is None:
                previous_amount = previous_shares * previous_cost
            batches = count_fill_batches(events)

            if finalize_only:
                # 只收口：不再买了，把「建仓中」结成「持仓中」。必须已经有真实仓位。
                if status != TRADE_STATUS_FILLING or previous_shares <= 0 or not complete:
                    self._send_json(400, {"error": "nothing to finalize"}); return
                new_shares, new_cost, new_amount = previous_shares, previous_cost, previous_amount
                updates = {"状态": TRADE_STATUS_HELD, "建仓完成日": fill_date}
            else:
                shares = _number(payload.get("shares"))
                cost_price = _number(payload.get("costPrice"))
                event_shares = _number(event_fill.get("shares"))
                event_price = _number(event_fill.get("price"))
                if shares is None or cost_price is None or shares <= 0 or cost_price <= 0:
                    self._send_json(400, {"error": "bad fill values"}); return
                if event_shares is None or event_price is None or abs(event_shares - shares) > 1e-8 or abs(event_price - cost_price) > 1e-8:
                    self._send_json(400, {"error": "fill event mismatch"}); return
                batch_amount = shares * cost_price
                declared_amount = _number(payload.get("actualAmount", batch_amount))
                event_amount = _number(event_fill.get("actualAmount", batch_amount))
                if (
                    declared_amount is None or abs(declared_amount - batch_amount) > 0.01
                    or event_amount is None or abs(event_amount - batch_amount) > 0.01
                ):
                    self._send_json(400, {"error": "fill amount mismatch"}); return
                new_shares = previous_shares + shares
                new_amount = previous_amount + batch_amount
                new_cost = new_amount / new_shares if new_shares else 0.0
                batches += 1
                updates = {
                    # 勾了「建仓已完成」才转持仓中；否则一直留在建仓中，首页看得到还差多少。
                    "状态": TRADE_STATUS_HELD if complete else TRADE_STATUS_FILLING,
                    "持仓股数": _fmt_num(new_shares),
                    "成本价": _fmt_num(round(new_cost, 6)),
                    "实际投入": _fmt_num(round(new_amount, 4)),
                }
                updates["建仓完成日" if complete else "建仓更新日"] = fill_date

            planned_amount = _number(event_fill.get("plannedAmount"))
            if planned_amount is not None and planned_amount > 0:
                updates["建仓计划"] = _fmt_num(planned_amount)
            try:
                with target.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + block.rstrip() + "\n")
                text = target.read_text(encoding="utf-8", errors="replace")
                target.write_text(set_front_matter(text, updates), encoding="utf-8")
            except OSError as exc:
                self._send_json(500, {"error": f"fill failed: {exc}"}); return
            self._send_json(200, {
                "ok": True, "file": target.name, "rel": _vault_rel(target),
                "batch": batches, "status": updates["状态"],
                "shares": new_shares, "costPrice": round(new_cost, 6), "actualAmount": round(new_amount, 4),
            })
            return

        # 作废：只对「零成交的计划」开放。
        # 有过真实成交的一律走平仓 —— 有仓位就必须有出场记录，这是账要对得上的底线。
        # 作废不是删除：追加一条必须写理由的 void 事件，再移进 已作废/YYYY/。
        if path == "/api/trade/void":
            payload = self._read_json_body()
            if payload is None:
                self._send_json(400, {"error": "bad body"}); return
            target = find_trade_file(str(payload.get("file", "")))
            if target is None:
                self._send_json(404, {"error": "trade file not found"}); return
            if target.parent != ROOT_TRADE:
                self._send_json(409, {"error": "trade is already archived"}); return
            block = payload.get("block", "")
            void_date = str(payload.get("voidDate", ""))
            event = parse_event_block(block, {"void"})
            if event is None:
                self._send_json(400, {"error": "invalid void event"}); return
            if not valid_calendar_date(void_date):
                self._send_json(400, {"error": "bad voidDate"}); return
            void_meta = event.get("void") if isinstance(event.get("void"), dict) else {}
            if not str(void_meta.get("reason", "")).strip():
                self._send_json(400, {"error": "void requires reason"}); return
            _, front, events = trade_runtime(target)
            if front.get("状态") != TRADE_STATUS_PLAN or has_event(events, "fill"):
                self._send_json(409, {
                    "error": "only zero-fill plans can be voided",
                    "status": front.get("状态"),
                    "hint": "有过成交的交易请走平仓归档",
                }); return
            destination_dir = TRADE_VOID / void_date[:4]
            destination = destination_dir / target.name
            if destination.exists():
                self._send_json(409, {"error": "archive target exists"}); return
            try:
                with target.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + block.rstrip() + "\n")
                text = target.read_text(encoding="utf-8", errors="replace")
                text = set_front_matter(text, {"状态": TRADE_STATUS_VOID, "作废日": void_date})
                target.write_text(text, encoding="utf-8")
                destination_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(destination))
            except OSError as exc:
                self._send_json(500, {"error": f"void failed: {exc}"}); return
            self._send_json(200, {"ok": True, "file": destination.name, "rel": _vault_rel(destination)})
            return

        # 账户参数是固定单文件；写入前必须包含可解析的账户 JSON。
        if path == "/api/trade/account":
            payload = self._read_json_body()
            if payload is None:
                self._send_json(400, {"error": "bad body"}); return
            markdown = payload.get("markdown", "")
            account = _json_after(markdown, TRADE_ACCOUNT_MARK) if isinstance(markdown, str) else None
            if not isinstance(account, dict):
                self._send_json(400, {"error": "invalid account markdown"}); return
            try:
                ACCOUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
                ACCOUNT_FILE.write_text(markdown, encoding="utf-8")
            except OSError as exc:
                self._send_json(500, {"error": f"write failed: {exc}"}); return
            self._send_json(200, {"ok": True, "rel": _vault_rel(ACCOUNT_FILE)})
            return

        self.send_response(404)
        self.end_headers()


def main() -> None:
    ensure_runtime_layout()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  YMOS Console · Reader + 决策台")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  📂 vault 根目录 : {VAULT_ROOT}")
    print(f"  📝 交易计划     : {ROOT_PLAN}  ✅")
    print(f"  🧾 决策审计     : {ROOT_AUDIT}  ✅")
    print(f"  📈 买卖决策     : {ROOT_TRADE}  ✅")
    print(f"  📚 Reader 页面  : {len(READER_PAGES)}")
    if not (HERE / "config.json").exists():
        print("  ⚠️  未找到 config.json —— 正在使用默认路径。")
        print("     想接自己的 Obsidian vault：cp config.example.json config.json 后修改。")
    print(f"\n  🚀 http://localhost:{PORT}     Ctrl-C 停止\n")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
