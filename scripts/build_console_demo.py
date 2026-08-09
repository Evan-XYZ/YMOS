#!/usr/bin/env python3
"""Build a backend-free, privacy-safe YMOS Console demo for GitHub Pages."""

from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "Console"

SAMPLES = {
    "market.md": ROOT / "Eyes/市场洞察/_示例/示例_市场洞察_DEMO.md",
    "radar.md": ROOT / "Eyes/投资雷达/_示例/示例_投资雷达_DEMO.md",
    "strategy.md": ROOT / "Brain/策略分析/_示例/示例_策略分析_DEMO.md",
}


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one adaptation anchor, found {count}")
    return text.replace(old, new, 1)


def adapt_index(text: str) -> str:
    text = replace_once(
        text,
        "    // file:// 直接打开时，路由要退回相对文件名\n",
        "    const STATIC_DEMO = true;\n"
        "    // GitHub Pages 使用项目子路径，因此 Demo 链接必须保持相对路径。\n",
        "Console index runtime mode",
    )
    text = text.replace('location.protocol === "file:"', "STATIC_DEMO")
    text = replace_once(
        text,
        '      document.getElementById("linkSettings").href = "settings.html";\n',
        '      document.getElementById("linkSettings").style.display = "none";\n',
        "hide settings in demo",
    )
    text = replace_once(
        text,
        '      const el = document.getElementById("statusText");\n',
        '      const el = document.getElementById("statusText");\n'
        '      if (STATIC_DEMO) {\n'
        '        el.innerHTML = "🟡 GitHub Pages 浏览器 Demo · 可交互并保存到当前浏览器，也可导出 Markdown / JSON；不会写入真实账户或服务器。";\n'
        '        return;\n'
        '      }\n',
        "demo status banner",
    )
    text = text.replace("这几个页面都是可修改的样板", "这三个页面都是可修改的样板")
    text = text.replace("；数据源 Key 写在 <code>.env</code>", "")
    text = text.replace(
        "填的东西都写回<b>你自己的 Obsidian</b>，是纯 Markdown。没有数据库，没有云端，没有账号。",
        "正式版把内容写回<b>你自己的 Obsidian</b>；当前 Demo 只在浏览器中体验，不接触本地文件。",
    )
    return text


def adapt_plan(text: str) -> str:
    text = replace_once(
        text,
        "    const CHECK_SVG = ",
        "    const STATIC_DEMO = true;\n"
        "    const DEMO_FETCH = window.fetch.bind(window);\n"
        "    window.fetch = (input, options) => {\n"
        "      const url = typeof input === \"string\" ? input : (input && input.url) || \"\";\n"
        "      if (url.startsWith(\"/api/\")) return Promise.reject(new Error(\"Demo backend disabled\"));\n"
        "      return DEMO_FETCH(input, options);\n"
        "    };\n"
        "    const CHECK_SVG = ",
        "plan runtime mode",
    )
    text = replace_once(
        text,
        "    function pushDraft(useBeacon) {\n",
        "    function pushDraft(useBeacon) {\n      if (STATIC_DEMO) return;\n",
        "disable plan draft API",
    )
    text = replace_once(
        text,
        "    async function saveExec() {\n      if (!execPlan || !execRec) {",
        "    async function saveExec() {\n      if (!execPlan || !execRec) {",
        "save execution anchor",
    )
    text = replace_once(
        text,
        '      if (!execPlan || !execRec) { toast("没有可保存的执行计划", "warn"); return; }\n',
        '      if (!execPlan || !execRec) { toast("没有可保存的执行计划", "warn"); return; }\n'
        '      if (STATIC_DEMO) {\n'
        '        saveExecDraft();\n'
        '        toast("Demo 已保存到当前浏览器 · 可继续导出 Markdown", "ok");\n'
        '        return;\n'
        '      }\n',
        "save execution locally",
    )
    text = replace_once(
        text,
        "    async function save() {\n",
        "    async function save() {\n"
        "      if (STATIC_DEMO) {\n"
        "        persist();\n"
        '        toast("Demo 已保存到当前浏览器 · 可导出 Markdown / JSON", "ok");\n'
        "        return;\n"
        "      }\n",
        "save plan locally",
    )
    text = text.replace('location.protocol === "file:"', "STATIC_DEMO")
    text = replace_once(
        text,
        "    async function checkVault() {\n",
        "    async function checkVault() {\n"
        "      if (STATIC_DEMO) {\n"
        "        vaultOnline = false;\n"
        '        const bar = document.getElementById("vaultBar");\n'
        "        if (bar) {\n"
        '          bar.classList.add("show");\n'
        '          bar.innerHTML = "<span>🟡 <b>GitHub Pages Demo</b> —— 可交互并保存到当前浏览器；使用下方按钮导出 Markdown / JSON。此页面不会写入真实账户或远程服务器。</span>";\n'
        "        }\n"
        '        const btn = document.getElementById("saveBtn");\n'
        '        if (btn) btn.title = "保存到当前浏览器缓存";\n'
        "        return;\n"
        "      }\n",
        "plan demo boundary banner",
    )
    return text


def adapt_decision(text: str) -> str:
    text = replace_once(
        text,
        '        const res = await fetch("/rules.json", { cache: "no-store" });',
        '        const res = await fetch(STATIC_DEMO ? "rules.json" : "/rules.json", { cache: "no-store" });',
        "relative demo rules",
    )
    text = replace_once(
        text,
        '    const ACCOUNT_KEY = "ymos-trade-account";',
        '    const STATIC_DEMO = true;\n    const ACCOUNT_KEY = "ymos-trade-account";',
        "decision runtime mode",
    )
    text = replace_once(
        text,
        "    async function api(path, opts) {\n",
        "    async function api(path, opts) {\n"
        "      if (STATIC_DEMO) {\n"
        "        serverOk = false;\n"
        '        const error = new Error("GitHub Pages Demo 不提供后端写盘");\n'
        "        error.status = 503;\n"
        "        throw error;\n"
        "      }\n",
        "disable decision API",
    )
    text = text.replace('location.protocol === "file:"', "STATIC_DEMO")
    text = replace_once(
        text,
        "    async function saveAccount() {\n      account.updated = nowStamp();\n      persistAccountLocal();\n",
        "    async function saveAccount() {\n"
        "      account.updated = nowStamp();\n"
        "      persistAccountLocal();\n"
        "      if (STATIC_DEMO) {\n"
        "        renderAll();\n"
        '        toast("Demo 账户参数已保存到当前浏览器");\n'
        "        return;\n"
        "      }\n",
        "save decision account locally",
    )
    text = replace_once(
        text,
        "      el.innerHTML = '<span class=\"sc-icon\">🗄️</span><div><b>当前是 file:// 页面预览，不是 YMOS 数据模式。</b>' +\n"
        "        '<br>这里填写的内容不会形成可供 Agent 复盘的 Markdown 真相源。请先在 <b>Console</b> 目录运行 <code>python3 server.py</code>，再从 ' +\n"
        "        '<a class=\"sc-link\" href=\"http://127.0.0.1:5273/decide\">http://127.0.0.1:5273/decide</a> 打开。</div>';",
        "      el.innerHTML = '<span class=\"sc-icon\">🗄️</span><div><b>当前是 GitHub Pages 浏览器 Demo。</b>' +\n"
        "        '<br>账户参数和草稿只保存在当前浏览器，不会形成可供 Agent 复盘的 Markdown 真相源，也不会执行真实交易。</div>';",
        "decision demo boundary banner",
    )
    return text


def assert_sample_safe(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    required = ("ymos_sample: true", "synthetic: true", "demoOnly: true")
    missing = [marker for marker in required if marker not in text[:500]]
    if missing:
        raise RuntimeError(f"refusing to publish unmarked sample {path}: missing {missing}")


def write_build_info(output: Path) -> None:
    info = {
        "mode": "static-demo",
        "source": "Evan-XYZ/YMOS",
        "privacy": "synthetic-samples-only",
    }
    (output / "build-info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def build(output: Path) -> None:
    output = output.resolve()
    if output == ROOT or output == output.parent or output.name not in {"_site", "site"}:
        raise RuntimeError(f"unsafe output path: {output}")
    if output.exists():
        shutil.rmtree(output)
    (output / "samples").mkdir(parents=True)

    pages = {
        "index.html": adapt_index((CONSOLE / "index.html").read_text(encoding="utf-8")),
        "交易计划台.html": adapt_plan((CONSOLE / "交易计划台.html").read_text(encoding="utf-8")),
        "买卖决策台.html": adapt_decision((CONSOLE / "买卖决策台.html").read_text(encoding="utf-8")),
        "reader.html": (CONSOLE / "demo/reader.html").read_text(encoding="utf-8"),
    }
    for name, text in pages.items():
        (output / name).write_text(text, encoding="utf-8")

    shutil.copy2(CONSOLE / "rules.example.json", output / "rules.json")
    for name, source in SAMPLES.items():
        assert_sample_safe(source)
        shutil.copy2(source, output / "samples" / name)

    (output / ".nojekyll").write_text("\n", encoding="utf-8")
    write_build_info(output)

    allowed = {
        ".nojekyll", "build-info.json", "index.html", "reader.html",
        "rules.json", "交易计划台.html", "买卖决策台.html",
        "samples/market.md", "samples/radar.md", "samples/strategy.md",
    }
    actual = {
        str(path.relative_to(output))
        for path in output.rglob("*")
        if path.is_file()
    }
    if actual != allowed:
        raise RuntimeError(
            "unexpected files in Pages artifact: "
            + html.escape(str(sorted(actual.symmetric_difference(allowed))))
        )
    print(f"Built privacy-safe YMOS demo: {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
