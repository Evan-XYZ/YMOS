import importlib.util
import json
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
DECISION_HTML = Path(__file__).resolve().parents[1] / "买卖决策台.html"
spec = importlib.util.spec_from_file_location("ymos_console_server_test", SERVER_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

# 前端必须把真实 Ticker、拦截/放行审计和 close 终态送到 API；
# 后端集成测试不能再用手造理想 payload 掩盖 UI 合同错位。
decision_html = DECISION_HTML.read_text(encoding="utf-8")
assert 'code: (prep.ticker || "").trim().toUpperCase()' in decision_html
assert "saveDecisionAudit(false)" in decision_html
assert "await saveDecisionAudit(true, savedFile)" in decision_html
assert 'buildEventBlock("close", { closing: true, exitKind: modeKind()' in decision_html
assert 'navLabel: "加仓计划"' in decision_html
assert "j.changesPositionFacts = false" in decision_html


def event(kind, extra=None):
    payload = {"schemaVersion": 1, "kind": kind, "ts": "2026-08-01 20:00"}
    payload.update(extra or {})
    return "<!-- ymos-trade-event -->\n```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


with tempfile.TemporaryDirectory(prefix="ymos-v4-trade-") as tmp:
    vault = Path(tmp)
    module.VAULT_ROOT = vault
    module.ROOT_PLAN = (vault / "Brain" / "交易计划").resolve()
    module.ROOT_AUDIT = (vault / "Brain" / "决策审计").resolve()
    module.ROOT_TRADE = (vault / "Brain" / "买入卖出决策").resolve()
    module.DRAFT_FILE = (module.ROOT_PLAN / "_当前草稿_自动备份.md").resolve()
    module.TRADE_CLOSED = (module.ROOT_TRADE / "已平仓").resolve()
    module.ACCOUNT_FILE = (module.ROOT_TRADE / "买卖决策_状态机.md").resolve()
    module.PRICE_ROUTER = vault / "Eyes" / "scripts" / "fetch_price_router.py"
    module.STATE_FILES = []
    module.PRICE_CACHE = {"at": 0.0, "data": {}}
    module.ensure_runtime_layout()

    assert module.ROOT_PLAN.is_dir()
    assert module.ROOT_AUDIT.is_dir()
    assert module.TRADE_CLOSED.is_dir()
    assert module.ACCOUNT_FILE.is_file()

    # Reader：默认 tree 目录应在后续新增月份/子目录后自动发现；
    # 新的自定义根路径只需 reader_custom_paths，无需复制整份 reader_pages。
    module.READER_ROOTS = {"ymos": vault}
    external_notes = vault / "external-notes"
    custom_categories = module.build_custom_reader_categories([
        {"label": "专项研究", "path": "Brain/专项研究", "mode": "tree"},
        {"label": "外部笔记", "path": str(external_notes), "mode": "tree-text"},
        {"label": "越界路径", "path": "../escape", "mode": "tree"},
    ])
    assert len(custom_categories) == 2
    default_category = {
        "label": "市场洞察", "root": "ymos", "rel": "Eyes/市场洞察", "mode": "tree",
    }
    module.READER_PAGES = {
        "ymos": {
            "label": "YMOS Reader",
            "sections": [
                {"label": "每日产出", "icon": "📅", "defaultOpen": True, "categories": [default_category]},
                {"label": "自定义工作区", "icon": "🧩", "defaultOpen": False, "categories": custom_categories},
            ],
        }
    }
    module.READER_CATEGORIES = [default_category, *custom_categories]
    assert module.collect_reader_items(default_category) == []
    assert module.collect_reader_items(custom_categories[0]) == []

    month_dir = vault / "Eyes" / "市场洞察" / "2026-08"
    month_dir.mkdir(parents=True)
    first_report = month_dir / "2026-08-02_市场洞察.md"
    first_report.write_text("# first\n", encoding="utf-8")
    special_dir = vault / "Brain" / "专项研究" / "芯片"
    special_dir.mkdir(parents=True)
    special_report = special_dir / "专项结论.md"
    special_report.write_text("# special\n", encoding="utf-8")
    external_notes.mkdir(parents=True)
    external_report = external_notes / "research.txt"
    external_report.write_text("external\n", encoding="utf-8")

    assert [item["name"] for item in module.collect_reader_items(default_category)] == [first_report.name]
    assert [item["name"] for item in module.collect_reader_items(custom_categories[0])] == [special_report.name]
    assert [item["name"] for item in module.collect_reader_items(custom_categories[1])] == [external_report.name]
    assert module.is_reader_path_allowed(first_report)
    assert module.is_reader_path_allowed(special_report)
    assert module.is_reader_path_allowed(external_report)
    assert not module.is_reader_path_allowed(vault.parent / "not-configured.md")

    later_dir = vault / "Eyes" / "市场洞察" / "2026-09" / "专题"
    later_dir.mkdir(parents=True)
    later_report = later_dir / "2026-09-01_市场洞察.md"
    later_report.write_text("# later\n", encoding="utf-8")
    refreshed_names = {item["name"] for item in module.collect_reader_items(default_category)}
    assert refreshed_names == {first_report.name, later_report.name}

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_port}"

    def call(path, method="GET", payload=None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(base + path, data=body, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    try:
        status, data = call("/api/ping")
        assert status == 200 and data == {"ok": True, "storage": "markdown"}
        status, data = call("/api/health")
        assert status == 200 and data["storage"] == "markdown" and data["accountStateExists"]

        plan_state = {"version": 1, "date": "2026-08-01", "dashboard": {"stance": "watch"}, "holdings": [], "watch": []}
        plan_md = "# 2026-08-01 日交易计划\n\n```json\n" + json.dumps(plan_state, ensure_ascii=False) + "\n```\n"
        status, _ = call("/api/plan/save", "POST", {"date": "2026-08-01", "markdown": plan_md})
        assert status == 200
        status, data = call("/api/plan/current?date=2026-08-01")
        assert status == 200 and data["found"] and data["date"] == "2026-08-01" and data["match"] == "exact"
        status, data = call("/api/plan/current?date=2026-08-02")
        assert status == 200 and data["found"] and data["date"] == "2026-08-01" and data["match"] == "fallback"

        status, data = call("/api/trade/list")
        assert status == 200 and data == {"open": [], "closed": []}

        account = {
            "schemaVersion": 1,
            "accounts": {"USD": {"capital": 20000, "horizonFund": "36m"}},
            "portfolioSnapshot": {
                "schemaVersion": 1,
                "asOf": "2026-08-01 20:00",
                "prices": {"DEMO": {"price": 120}},
                "positions": [{"ticker": "DEMO", "lastPrice": 120}],
            },
        }
        account_md = "# 买卖决策状态机\n\n<!-- ymos-trade-account -->\n```json\n" + json.dumps(account, ensure_ascii=False) + "\n```\n"
        status, _ = call("/api/trade/account", "POST", {"markdown": account_md})
        assert status == 200
        status, data = call("/api/trade/account")
        assert status == 200 and data["found"] and data["account"]["accounts"]["USD"]["capital"] == 20000
        assert data["account"]["portfolioSnapshot"]["prices"]["DEMO"]["price"] == 120

        open_data = {
            "schemaVersion": 1,
            "kind": "open",
            "strategy": "general",
            "symbol": "Demo Corp",
            "ticker": "DEMO",
            "openDate": "2026-08-01",
        }
        markdown = (
            "---\n"
            "ymos_trade: v1\n"
            "标的: Demo Corp\n"
            "Ticker: DEMO\n"
            "状态: 计划中\n"
            "策略: 通用策略\n"
            "建仓决策日: 2026-08-01\n"
            "---\n\n"
            "<!-- ymos-trade-open -->\n```json\n"
            + json.dumps(open_data, ensure_ascii=False)
            + "\n```\n\n"
            + event("open")
            + "\n"
        )
        create_payload = {"name": "Demo Corp", "code": "DEMO", "date": "2026-08-01", "markdown": markdown}
        status, data = call("/api/trade/open", "POST", {**create_payload, "code": "WRONG"})
        assert status == 400 and data["error"] == "trade identity mismatch"
        status, data = call("/api/trade/open", "POST", create_payload)
        assert status == 200
        filename = data["file"]
        assert filename == "Demo Corp_DEMO_2026-08-01.md"
        status, _ = call("/api/trade/open", "POST", create_payload)
        assert status == 409

        status, data = call("/api/trade/load?file=../bad.md")
        assert status == 200 and not data["found"]

        # 服务端必须拒绝绕过建仓准备直接成交。
        fill_block = event("fill", {"fill": {"shares": 10, "price": 100, "actualAmount": 1000}})
        status, _ = call("/api/trade/fill", "POST", {
            "file": filename, "block": fill_block, "fillDate": "2026-08-02",
            "shares": 10, "costPrice": 100, "actualAmount": 1000,
        })
        assert status == 409

        prepare_block = event("prepare", {"metrics": {"amount": 1000}})
        status, _ = call("/api/trade/append", "POST", {"file": filename, "block": prepare_block})
        assert status == 200
        status, _ = call("/api/trade/append", "POST", {"file": filename, "block": prepare_block})
        assert status == 409

        # 计划中不能卖出。
        plan_sell = event("tp", {"sell": {"beforeShares": 10, "sellShares": 4, "remainingShares": 6}})
        status, _ = call("/api/trade/sell", "POST", {"file": filename, "block": plan_sell})
        assert status == 409

        status, _ = call("/api/trade/fill", "POST", {
            "file": filename, "block": fill_block, "fillDate": "2026-08-02",
            "shares": 10, "costPrice": 100, "actualAmount": 999,
        })
        assert status == 400

        status, _ = call("/api/trade/fill", "POST", {
            "file": filename,
            "block": fill_block,
            "fillDate": "2026-08-02",
            "shares": 10,
            "costPrice": 100,
            "actualAmount": 1000,
        })
        assert status == 200

        status, data = call("/api/trade/load?file=" + urllib.parse.quote(filename))
        assert data["front"]["状态"] == "持仓中"
        assert data["front"]["持仓股数"] == "10"
        assert data["eventCount"] == 3

        # 重复成交必须拒绝。
        status, _ = call("/api/trade/fill", "POST", {
            "file": filename, "block": fill_block, "fillDate": "2026-08-02",
            "shares": 10, "costPrice": 100, "actualAmount": 999,
        })
        assert status == 409

        # V4 的 add 明确是加仓计划 / 压力测试，不更新成交事实。
        status, _ = call("/api/trade/append", "POST", {
            "file": filename,
            "block": event("add", {"metrics": {"amount": 1200}}),
        })
        assert status == 409
        status, _ = call("/api/trade/append", "POST", {
            "file": filename,
            "block": event("add", {
                "metrics": {"amount": 1200},
                "planOnly": True,
                "changesPositionFacts": False,
            }),
        })
        assert status == 200
        status, data = call("/api/trade/load?file=" + urllib.parse.quote(filename))
        assert data["front"]["持仓股数"] == "10" and data["front"]["成本价"] == "100"

        status, _ = call("/api/trade/sell", "POST", {
            "file": filename,
            "block": event("tp", {"sell": {"beforeShares": 10, "sellShares": 4, "remainingShares": 6}}),
            "remainingShares": 6,
            "costPrice": 100,
        })
        assert status == 200
        status, data = call("/api/trade/load?file=" + urllib.parse.quote(filename))
        assert data["front"]["持仓股数"] == "6"
        assert data["front"]["实际投入"] == "600"

        status, _ = call("/api/trade/append", "POST", {"file": filename, "block": event("adjust", {"adjust": {"stopPct": 12}})})
        assert status == 200

        # 前端的拦截与成功写盘要分别进入结构化审计。
        audit_base = {
            "date": "2026-08-03", "mode": "prepare", "modeLabel": "建仓准备",
            "target": "Demo Corp", "ticker": "DEMO", "tradeFile": filename,
            "gates": [{"label": "结构门", "items": [{"label": "期限匹配", "checked": False, "redline": True}]}],
            "missing": ["期限匹配"],
        }
        status, _ = call("/api/audit/save", "POST", {**audit_base, "passed": False})
        assert status == 200
        status, _ = call("/api/audit/save", "POST", {**audit_base, "passed": True, "missing": []})
        assert status == 200
        audit_text = (module.ROOT_AUDIT / "2026-08" / "2026-08-03决策记录.md").read_text(encoding="utf-8")
        assert audit_text.count("ymos-decision-audit") == 2
        assert '"passed": false' in audit_text and '"passed": true' in audit_text
        assert '"tradeFile": "Demo Corp_DEMO_2026-08-01.md"' in audit_text

        # 终态只接受 kind=close；tp/sl 只能表示部分卖出。
        status, _ = call("/api/trade/close", "POST", {
            "file": filename,
            "block": event("tp", {"sell": {"beforeShares": 6, "sellShares": 6, "remainingShares": 0}}),
            "closeDate": "2026-08-03",
        })
        assert status == 400
        status, _ = call("/api/trade/close", "POST", {
            "file": filename,
            "block": event("close", {
                "exitKind": "tp",
                "sell": {"beforeShares": 6, "sellShares": 6, "remainingShares": 0},
                "result": {"layer": "执行层"},
            }),
            "closeDate": "2026-08-03",
        })
        assert status == 200

        status, data = call("/api/trade/list")
        assert status == 200 and len(data["open"]) == 0 and len(data["closed"]) == 1
        assert data["closed"][0]["front"]["状态"] == "已平仓"
        assert data["closed"][0]["front"]["持仓股数"] == "0"
        assert data["closed"][0]["front"]["实际投入"] == "0"
        assert data["closed"][0]["eventCount"] == 7
        assert data["closed"][0]["lastEvent"]["kind"] == "close"
        assert data["closed"][0]["lastEvent"]["exitKind"] == "tp"

        status, _ = call("/api/trade/append", "POST", {"file": filename, "block": event("adjust")})
        assert status == 409

        archived = module.TRADE_CLOSED / "2026" / filename
        assert archived.exists()
        print("trade API lifecycle OK")
        print(vault)
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
