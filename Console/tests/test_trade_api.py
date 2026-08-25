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
assert 'navLabel: "变更建仓计划"' in decision_html
assert "j.changesPositionFacts = false" in decision_html

# 分批建仓：界面必须有「建仓中」状态、收口开关与批次累计口径。
assert 'ST_FILLING = "建仓中"' in decision_html
assert "function tradeFilledTotal(item)" in decision_html
assert "function tradeBuildProgress(item)" in decision_html
assert "finalizeOnly: finalizeOnly" in decision_html
assert "j.changesPlanAmount = true" in decision_html
assert '建仓中（分批未建满）' in decision_html
# 平仓结转：卖出成交价必填，归档后盈亏并入资金基数并留痕。
assert "async function settleClosedTrade(info)" in decision_html
assert "function tradeSettled(item)" in decision_html
assert "settlements: []" in decision_html
assert "先填成交价 —— 没有它，这笔的盈亏结转不进账户" in decision_html
# 加仓改的是计划总额：decisionPlan / effectivePlan / selectTrade 三处必须同一口径，
# 否则加完仓回到「确认建仓」，进度还按老计划算，会一直显示超买。
assert decision_html.count('(e.kind === "add" || e.kind === "trim") && e.metrics && num(e.metrics.amount)') == 2
assert 'else if ((e.kind === "add" || e.kind === "trim") && num(e.metrics.amount)) plan.amount = num(e.metrics.amount);' in decision_html
assert 'title: "确认建仓 · 纳入建仓数据"' in decision_html
assert 'title: "变更建仓计划"' in decision_html
# 只读的建仓档案必须给出「金额怎么改」的出口，否则用户只会得出「只能删了重来」
assert '要改<em>投入金额</em>：走 <em>「变更建仓计划」</em>' in decision_html
# 双向改计划：调小是降敞口，不该被门禁拦；下限锁在已建仓金额。
assert 'if (currentMode === "buy_add") return !metrics().trimming;' in decision_html
assert 'trimming: currentMode === "buy_add" && add < 0,' in decision_html
assert "不能低于已建仓的" in decision_html
assert "缩减计划必须写理由" in decision_html
# 作废：只对零成交计划开放，且必须写原因。
assert "function tradeVoidable(item)" in decision_html
assert "async function voidTrade(item, reason)" in decision_html
assert '"/api/trade/void"' in decision_html
assert "腾讯财经（免 Key）" in decision_html
assert "已配置的 Finnhub / Tushare 仍优先" in decision_html
assert module.price_sources()["tencent"] is True


def event(kind, extra=None):
    payload = {"schemaVersion": 1, "kind": kind, "ts": "2026-08-01 20:00"}
    payload.update(extra or {})
    return "<!-- ymos-trade-event -->\n```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


def fill_event(shares, price, *, complete=False, finalize=False, planned=1000):
    """确认建仓事件块。前端送的是「本次这一笔」的增量，累计由服务端推进。"""
    return event("fill", {"fill": {
        "shares": 0 if finalize else shares,
        "price": None if finalize else price,
        "actualAmount": 0 if finalize else round(shares * price, 2),
        "plannedAmount": planned,
        "complete": complete,
        "finalizeOnly": finalize,
    }})


def plan_event(kind, previous, new, filled, reason=""):
    """调整建仓计划：add 调大 / trim 调小。两者都只改计划，不碰持仓事实。"""
    return event(kind, {
        "metrics": {"amount": new},
        "planOnly": True, "changesPositionFacts": False,
        "changesPlanAmount": True, "plannedTotal": new,
        "plan": {
            "previousTotal": previous, "newTotal": new, "delta": new - previous,
            "direction": "decrease" if new < previous else "increase",
            "filledAmount": filled, "settlesBuild": new <= filled + 0.01,
            "reason": reason,
        },
    })


with tempfile.TemporaryDirectory(prefix="ymos-v4-trade-") as tmp:
    vault = Path(tmp)
    module.VAULT_ROOT = vault
    module.ROOT_PLAN = (vault / "Brain" / "交易计划").resolve()
    module.ROOT_AUDIT = (vault / "Brain" / "决策审计").resolve()
    module.ROOT_TRADE = (vault / "Brain" / "买入卖出决策").resolve()
    module.DRAFT_FILE = (module.ROOT_PLAN / "_当前草稿_自动备份.md").resolve()
    module.TRADE_CLOSED = (module.ROOT_TRADE / "已平仓").resolve()
    module.TRADE_VOID = (module.ROOT_TRADE / "已作废").resolve()
    module.ACCOUNT_FILE = (module.ROOT_TRADE / "买卖决策_状态机.md").resolve()
    module.PRICE_ROUTER = vault / "Eyes" / "scripts" / "fetch_price_router.py"
    module.STATE_FILES = []
    module.PRICE_CACHE = {"at": 0.0, "data": {}}
    module.ensure_runtime_layout()

    assert module.ROOT_PLAN.is_dir()
    assert module.ROOT_AUDIT.is_dir()
    assert module.TRADE_CLOSED.is_dir()
    assert module.TRADE_VOID.is_dir()
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

    def front_of(name):
        _, payload = call("/api/trade/load?file=" + urllib.parse.quote(name))
        return payload["front"]

    def create_trade(symbol, ticker, date):
        open_data = {
            "schemaVersion": 1, "kind": "open", "strategy": "general",
            "symbol": symbol, "ticker": ticker, "openDate": date,
        }
        markdown = (
            "---\n"
            "ymos_trade: v1\n"
            f"标的: {symbol}\n"
            f"Ticker: {ticker}\n"
            "状态: 计划中\n"
            "策略: 通用策略\n"
            f"建仓决策日: {date}\n"
            "---\n\n"
            "<!-- ymos-trade-open -->\n```json\n"
            + json.dumps(open_data, ensure_ascii=False)
            + "\n```\n\n"
            + event("open")
            + "\n"
        )
        return {"name": symbol, "code": ticker, "date": date, "markdown": markdown}

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
        assert status == 200 and data == {"open": [], "closed": [], "voided": []}

        account = {
            "schemaVersion": 1,
            "accounts": {"USD": {"capital": 20000, "horizonFund": "36m"}},
            "settlements": [],
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
        assert data["account"]["settlements"] == []

        create_payload = create_trade("Demo Corp", "DEMO", "2026-08-01")
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
        status, _ = call("/api/trade/fill", "POST", {
            "file": filename, "block": fill_event(6, 100), "fillDate": "2026-08-02",
            "shares": 6, "costPrice": 100, "actualAmount": 600,
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

        # 金额对不上要拒绝。
        status, _ = call("/api/trade/fill", "POST", {
            "file": filename, "block": fill_event(6, 100), "fillDate": "2026-08-02",
            "shares": 6, "costPrice": 100, "actualAmount": 999,
        })
        assert status == 400

        # 事件块里的收口标记必须和 payload 一致，否则文件和状态会讲两套故事。
        status, _ = call("/api/trade/fill", "POST", {
            "file": filename, "block": fill_event(6, 100), "fillDate": "2026-08-02",
            "shares": 6, "costPrice": 100, "actualAmount": 600, "complete": True,
        })
        assert status == 400

        # ---- 第 1 笔建仓：没勾「建仓已完成」→ 状态停在建仓中 ----
        status, data = call("/api/trade/fill", "POST", {
            "file": filename, "block": fill_event(6, 100), "fillDate": "2026-08-02",
            "shares": 6, "costPrice": 100, "actualAmount": 600,
        })
        assert status == 200 and data["batch"] == 1 and data["status"] == "建仓中"

        front = front_of(filename)
        assert front["状态"] == "建仓中"
        assert front["持仓股数"] == "6" and front["成本价"] == "100" and front["实际投入"] == "600"
        assert front["建仓计划"] == "1000"
        assert "建仓完成日" not in front and front["建仓更新日"] == "2026-08-02"

        # ---- 第 2 笔建仓：累加股数与金额，成本价按加权平均重算 ----
        status, data = call("/api/trade/fill", "POST", {
            "file": filename, "block": fill_event(4, 110), "fillDate": "2026-08-03",
            "shares": 4, "costPrice": 110, "actualAmount": 440,
        })
        assert status == 200 and data["batch"] == 2 and data["status"] == "建仓中"
        front = front_of(filename)
        assert front["持仓股数"] == "10" and front["实际投入"] == "1040" and front["成本价"] == "104"

        # ---- 收口：不再追加成交，只把建仓中结成持仓中 ----
        status, data = call("/api/trade/fill", "POST", {
            "file": filename, "block": fill_event(0, 0, complete=True, finalize=True),
            "fillDate": "2026-08-03", "shares": 0, "costPrice": 0,
            "complete": True, "finalizeOnly": True,
        })
        assert status == 200 and data["status"] == "持仓中"
        front = front_of(filename)
        assert front["状态"] == "持仓中" and front["持仓股数"] == "10" and front["建仓完成日"] == "2026-08-03"

        # 已经建满了（持仓中）就不再是可录成交的状态，收口请求应被状态机挡下。
        status, _ = call("/api/trade/fill", "POST", {
            "file": filename, "block": fill_event(0, 0, complete=True, finalize=True),
            "fillDate": "2026-08-03", "shares": 0, "costPrice": 0,
            "complete": True, "finalizeOnly": True,
        })
        assert status == 409

        # ---- 加仓改的是建仓计划：不动成交事实，状态回到建仓中 ----
        status, _ = call("/api/trade/append", "POST", {
            "file": filename, "block": event("add", {"metrics": {"amount": 1500}}),
        })
        assert status == 409
        status, data = call("/api/trade/append", "POST", {
            "file": filename, "block": plan_event("add", 1040, 1500, 1040),
        })
        assert status == 200 and data["status"] == "建仓中"
        front = front_of(filename)
        assert front["状态"] == "建仓中"
        assert front["持仓股数"] == "10" and front["成本价"] == "104"   # 加仓不改成交事实
        assert front["建仓计划"] == "1500"

        # ---- 缩减建仓计划：降敞口，但不得低于已经买进去的钱，且必须写理由 ----
        status, data = call("/api/trade/append", "POST", {
            "file": filename, "block": plan_event("trim", 1500, 500, 1040, "想缩到已建仓以下"),
        })
        assert status == 400 and data["error"] == "plan below filled amount"
        status, data = call("/api/trade/append", "POST", {
            "file": filename, "block": plan_event("trim", 1500, 1200, 1040, ""),
        })
        assert status == 400 and data["error"] == "trim requires reason"
        status, data = call("/api/trade/append", "POST", {
            "file": filename, "block": plan_event("trim", 1500, 1200, 1040, "论点变弱，先只做一半"),
        })
        assert status == 200 and data["status"] == "建仓中"
        front = front_of(filename)
        assert front["建仓计划"] == "1200"
        # 缩的是计划，不是仓位 —— 已经买进去的一股没动。
        assert front["持仓股数"] == "10" and front["实际投入"] == "1040"
        # 再调回去，后面的分批建仓仍按 1500 的计划走。
        status, _ = call("/api/trade/append", "POST", {
            "file": filename, "block": plan_event("add", 1200, 1500, 1040),
        })
        assert status == 200 and front_of(filename)["建仓计划"] == "1500"

        # ---- 建仓中也能减仓：仓位是真的，止损不该等到建满才允许 ----
        status, _ = call("/api/trade/sell", "POST", {
            "file": filename,
            "block": event("tp", {"sell": {"beforeShares": 10, "sellShares": 2, "remainingShares": 8}}),
            "remainingShares": 8, "costPrice": 104,
        })
        assert status == 200
        front = front_of(filename)
        assert front["持仓股数"] == "8" and front["实际投入"] == "832" and front["状态"] == "建仓中"

        # ---- 第 3 笔：执行加仓计划并收口 ----
        status, data = call("/api/trade/fill", "POST", {
            "file": filename, "block": fill_event(2, 120, complete=True, planned=1500),
            "fillDate": "2026-08-04", "shares": 2, "costPrice": 120, "actualAmount": 240,
            "complete": True,
        })
        assert status == 200 and data["status"] == "持仓中"
        front = front_of(filename)
        assert front["状态"] == "持仓中" and front["持仓股数"] == "10" and front["实际投入"] == "1072"
        assert front["成本价"] == "107.2"

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
            "block": event("tp", {"sell": {"beforeShares": 10, "sellShares": 10, "remainingShares": 0}}),
            "closeDate": "2026-08-05",
        })
        assert status == 400
        status, _ = call("/api/trade/close", "POST", {
            "file": filename,
            "block": event("close", {
                "exitKind": "tp",
                "sell": {"beforeShares": 10, "sellShares": 10, "remainingShares": 0,
                         "costPrice": 107.2, "price": 130, "realizedPnl": 228.0},
                "result": {"layer": "执行层", "realizedPnl": 228.0, "account": "USD"},
            }),
            "closeDate": "2026-08-05",
        })
        assert status == 200

        status, data = call("/api/trade/list")
        assert status == 200 and len(data["open"]) == 0 and len(data["closed"]) == 1
        closed = data["closed"][0]
        assert closed["front"]["状态"] == "已平仓"
        assert closed["front"]["持仓股数"] == "0"
        assert closed["front"]["实际投入"] == "0"
        # open + prepare + fill×3(含收口) + add + trim + add + tp + fill + adjust + close
        assert closed["eventCount"] == 12
        assert closed["lastEvent"]["kind"] == "close"
        assert closed["lastEvent"]["exitKind"] == "tp"
        assert closed["lastEvent"]["sell"]["realizedPnl"] == 228.0

        status, _ = call("/api/trade/append", "POST", {"file": filename, "block": event("adjust")})
        assert status == 409

        archived = module.TRADE_CLOSED / "2026" / filename
        assert archived.exists()

        # ---- 第二笔交易：验证「建仓中」可以直接整笔平掉（没建满不是继续扛着的理由）----
        second = create_trade("Half Corp", "HALF", "2026-08-04")
        status, data = call("/api/trade/open", "POST", second)
        assert status == 200
        half = data["file"]
        status, _ = call("/api/trade/append", "POST", {
            "file": half, "block": event("prepare", {"metrics": {"amount": 2000}})})
        assert status == 200
        status, data = call("/api/trade/fill", "POST", {
            "file": half, "block": fill_event(5, 200, planned=2000), "fillDate": "2026-08-04",
            "shares": 5, "costPrice": 200, "actualAmount": 1000,
        })
        assert status == 200 and data["status"] == "建仓中"
        status, _ = call("/api/trade/close", "POST", {
            "file": half,
            "block": event("close", {
                "exitKind": "sl",
                "sell": {"beforeShares": 5, "sellShares": 5, "remainingShares": 0,
                         "costPrice": 200, "price": 180, "realizedPnl": -100.0},
                "result": {"layer": "策略层", "realizedPnl": -100.0, "account": "USD"},
            }),
            "closeDate": "2026-08-05",
        })
        assert status == 200

        # ---- 作废：只对「一笔都没成交」的计划开放，且必须写原因 ----
        typo = create_trade("Typo Corp", "TYPO", "2026-08-05")
        status, data = call("/api/trade/open", "POST", typo)
        assert status == 200
        typo_file = data["file"]
        status, _ = call("/api/trade/append", "POST", {
            "file": typo_file, "block": event("prepare", {"metrics": {"amount": 5000}})})
        assert status == 200
        status, _ = call("/api/trade/void", "POST", {
            "file": typo_file, "voidDate": "2026-08-05",
            "block": event("void", {"void": {"reason": ""}})})
        assert status == 400
        status, _ = call("/api/trade/void", "POST", {
            "file": typo_file, "voidDate": "2026-08-05",
            "block": event("void", {"void": {"reason": "Ticker 填错，已重建一笔"}})})
        assert status == 200
        status, data = call("/api/trade/list")
        assert all(item["file"] != typo_file for item in data["open"])
        assert [item["file"] for item in data["voided"]] == [typo_file]
        assert data["voided"][0]["front"]["状态"] == "已作废"
        assert data["voided"][0]["front"]["作废日"] == "2026-08-05"
        assert (module.TRADE_VOID / "2026" / typo_file).exists()

        # 有过真实成交的不能作废 —— 有仓位就必须有出场记录。
        held_now = create_trade("Real Corp", "REAL", "2026-08-05")
        status, data = call("/api/trade/open", "POST", held_now)
        real_file = data["file"]
        call("/api/trade/append", "POST", {
            "file": real_file, "block": event("prepare", {"metrics": {"amount": 1000}})})
        call("/api/trade/fill", "POST", {
            "file": real_file, "block": fill_event(5, 100), "fillDate": "2026-08-05",
            "shares": 5, "costPrice": 100, "actualAmount": 500})
        status, data = call("/api/trade/void", "POST", {
            "file": real_file, "voidDate": "2026-08-05",
            "block": event("void", {"void": {"reason": "不想要了"}})})
        assert status == 409 and data["error"] == "only zero-fill plans can be voided"

        # ---- 平仓结转：界面把盈亏并进资金基数后写回状态机，服务端应原样读回 ----
        settled = dict(account)
        settled["accounts"] = {"USD": {"capital": 20128, "horizonFund": "36m"}}
        settled["settlements"] = [
            {"file": filename, "symbol": "Demo Corp", "account": "USD",
             "realizedPnl": 228.0, "closeDate": "2026-08-05",
             "capitalBefore": 20000, "capitalAfter": 20228},
            {"file": half, "symbol": "Half Corp", "account": "USD",
             "realizedPnl": -100.0, "closeDate": "2026-08-05",
             "capitalBefore": 20228, "capitalAfter": 20128},
        ]
        settled_md = "# 买卖决策状态机\n\n<!-- ymos-trade-account -->\n```json\n" + json.dumps(settled, ensure_ascii=False) + "\n```\n"
        status, _ = call("/api/trade/account", "POST", {"markdown": settled_md})
        assert status == 200
        status, data = call("/api/trade/account")
        assert status == 200
        assert data["account"]["accounts"]["USD"]["capital"] == 20128
        assert [s["file"] for s in data["account"]["settlements"]] == [filename, half]
        # 净增 128 = +228 − 100，资金基数确实滚动了。
        assert data["account"]["accounts"]["USD"]["capital"] - 20000 == sum(
            s["realizedPnl"] for s in data["account"]["settlements"])

        print("trade API lifecycle OK")
        print(vault)
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
