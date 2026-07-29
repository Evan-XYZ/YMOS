#!/usr/bin/env python3
"""
外部 Skill CLI 解析器 — 让 YMOS 的问财/选股封装脚本不绑定任何特定 Agent 宿主。

背景：
    YMOS 的 A股/美股选股、公告/研报/新闻搜索、财务数据查询，底层调用的是
    「同花顺问财」系列 Skill。这些 Skill 不属于 YMOS，需要你在自己的 Agent
    宿主里单独安装（见 进阶指南.md「问财数据层」一节）。

    本模块负责在多个常见位置里找到它们的 cli.py，找不到时给出清晰的指引，
    而不是抛一个看不懂的 FileNotFoundError。

解析优先级：
    1. 环境变量 YMOS_SKILL_ROOT 指定的目录
    2. ~/.openclaw/workspace/skills/
    3. ~/.claude/skills/
    4. ~/.agents/skills/         ← Codex / 多 Agent 共用目录
    5. ~/.codex/skills/
    6. ~/.config/ymos/skills/
    7. ~/skills/
    8. <YMOS根>/.agents/skills/
    9. <YMOS根>/.claude/skills/
   10. <YMOS根>/.codex/skills/
   11. <YMOS根>/skills/          ← 想把 skill 直接放进项目里的话

用法：
    from skill_resolver import resolve_skill_cli, skill_missing_message

    SKILL_CLI = resolve_skill_cli(
        "hithink-astock-selector",              # 主名
        "问财选A股/hithink-astock-selector",     # 旧版兼容名（可多个）
    )
    if SKILL_CLI is None:
        print(skill_missing_message("hithink-astock-selector"))
        sys.exit(2)
"""
from __future__ import annotations

import os
from pathlib import Path

from env_loader import load_dotenv

YMOS_ROOT = Path(__file__).resolve().parents[2]      # Eyes/scripts/ → YMOS/

# 让 YMOS_SKILL_ROOT / IWENCAI_API_KEY 等统一从 YMOS 根目录的 .env 生效。
# 已由宿主注入的环境变量优先，env_loader 不会覆盖它们。
load_dotenv()


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    env_root = os.getenv("YMOS_SKILL_ROOT", "").strip()
    if env_root:
        roots.append(Path(env_root).expanduser())
    home = Path.home()
    roots += [
        home / ".openclaw" / "workspace" / "skills",
        home / ".claude" / "skills",
        home / ".agents" / "skills",
        home / ".codex" / "skills",
        home / ".config" / "ymos" / "skills",
        home / "skills",
        YMOS_ROOT / ".agents" / "skills",
        YMOS_ROOT / ".claude" / "skills",
        YMOS_ROOT / ".codex" / "skills",
        YMOS_ROOT / "skills",
    ]
    # 保留优先级，同时避免 HOME / YMOS_ROOT 配置重合时重复扫描。
    return list(dict.fromkeys(path.resolve() for path in roots))


def resolve_skill_cli(*skill_names: str, filename: str = "cli.py") -> Path | None:
    """
    在所有候选根目录下依次查找 <root>/<skill_name>/scripts/<filename>。

    skill_names 按优先级传入；也支持带子路径的旧版名（如 "问财选A股/xxx"）。
    找到第一个存在的就返回，全都没有则返回 None。
    """
    for root in _candidate_roots():
        for name in skill_names:
            candidate = root / name / "scripts" / filename
            if candidate.exists():
                return candidate
    return None


def skill_missing_message(skill_name: str, purpose: str = "") -> str:
    """Skill 没装时的统一提示——告诉用户装什么、装哪、怎么绕过。"""
    what = f"（用于：{purpose}）" if purpose else ""
    roots = "\n".join(f"      - {r}" for r in _candidate_roots())
    return (
        f"\n❌ 未找到 Skill：{skill_name} {what}\n"
        f"\n   这是一个**可选的外部数据层**，不装也不影响 YMOS 主链路运行。\n"
        f"\n   已查找的位置：\n{roots}\n"
        f"\n   两种解决方式：\n"
        f"      1) 登录 https://www.iwencai.com/skillhub ，打开该官方 Skill，\n"
        f"         把「Agent 用户」安装 Prompt 复制给你的 AI 助手；\n"
        f"      2) 已经装在别处的话，指定根目录：\n"
        f"         export YMOS_SKILL_ROOT=\"/你的/skills\"\n"
        f"\n   安装完成的最低验收：\n"
        f"      <Skill根>/{skill_name}/SKILL.md\n"
        f"      <Skill根>/{skill_name}/scripts/cli.py\n"
        f"      python3 Eyes/scripts/skill_resolver.py 能显示 ✅\n"
        f"\n   详见 进阶指南.md → 「问财数据层（可选）」\n"
    )


if __name__ == "__main__":
    print("YMOS Skill 解析器 — 当前环境检测\n")
    print("候选根目录：")
    for r in _candidate_roots():
        print(f"  {'✅' if r.exists() else '  '} {r}")
    print("\n各 Skill 状态：")
    for name, alt, purpose in [
        ("hithink-astock-selector", "问财选A股/hithink-astock-selector", "A股选股"),
        ("hithink-hkstock-selector", "问财选港股/hithink-hkstock-selector", "港股选股"),
        ("hithink-usstock-selector", "问财选美股/hithink-usstock-selector", "美股选股"),
        ("hithink-market-query", "行情数据查询/hithink-market-query", "通用行情查询"),
        ("hithink-finance-query", "", "个股财务数据"),
        ("report-search", "", "研报搜索"),
    ]:
        names = [n for n in (name, alt) if n]
        cli = resolve_skill_cli(*names)
        print(f"  {'✅' if cli else '❌'} {name:28s} {purpose:12s} {cli or '未安装'}")
