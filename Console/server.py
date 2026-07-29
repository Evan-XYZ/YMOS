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
import re
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
    "reader_roots": {"ymos": "."},        # Reader 根目录（相对 vault_root）
    "reader_pages": {},                   # Reader 页面结构；空时从 config.example.json 读取
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
DRAFT_FILE = (ROOT_PLAN / "_当前草稿_自动备份.md").resolve()
PORT = int(CONFIG["port"])

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

# 一份计划 md 可含两块结构化数据：计划块（收盘定的，永远第一块）+ 执行块（次日盘中补的）
EXEC_DATA_MARK = "ymos-exec-data"
EXEC_SECTION_MARK = "<!-- ymos-exec-section -->"

MAX_BODY = 5_000_000


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
    note = str(payload.get("note") or "").strip()
    stance = str(payload.get("stance") or "").strip()

    lines = [f"## {ts} · {mode} · {verdict}", ""]
    meta = []
    if target:
        meta.append(f"- **标的/场景**：{target}")
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
    "/sop": "新高买卖决策台.html",
    "/新高买卖决策台.html": "新高买卖决策台.html",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send_json(self, code: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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

        # 连接状态：前端状态条用它判断「已连 vault」还是「仅本地暂存」
        if path == "/api/health":
            self._send_json(200, {
                "ok": True,
                "vaultRoot": str(VAULT_ROOT),
                "planDir": str(ROOT_PLAN),
                "auditDir": str(ROOT_AUDIT),
                "planDirExists": ROOT_PLAN.exists(),
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

        # 读「严格早于某日」的最近一份收盘计划（= 今日要执行的上一交易日计划）
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
                    header = f"# {date} 决策记录\n\n> 由 YMOS Console · 新高买卖决策台自动留痕。每一次扣扳机和每一次被拦截都在这里。\n\n"
                    target.write_text(header + entry, encoding="utf-8")
                else:
                    with target.open("a", encoding="utf-8") as fh:
                        fh.write(entry)
            except OSError as exc:
                self._send_json(500, {"error": f"write failed: {exc}"}); return
            self._send_json(200, {"ok": True, "abs": str(target)})
            return

        self.send_response(404)
        self.end_headers()


def main() -> None:
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  YMOS Console · Reader + 决策台")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  📂 vault 根目录 : {VAULT_ROOT}")
    print(f"  📝 交易计划     : {ROOT_PLAN}  {'✅' if ROOT_PLAN.exists() else '（首次保存时自动创建）'}")
    print(f"  🧾 决策审计     : {ROOT_AUDIT}  {'✅' if ROOT_AUDIT.exists() else '（首次留痕时自动创建）'}")
    print(f"  📚 Reader 页面  : {len(READER_PAGES)}")
    if not (HERE / "config.json").exists():
        print("  ⚠️  未找到 config.json —— 正在使用默认路径。")
        print("     想接自己的 Obsidian vault：cp config.example.json config.json 后修改。")
    print(f"\n  🚀 http://localhost:{PORT}     Ctrl-C 停止\n")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
