#!/usr/bin/env python3
"""
YMOS vNext Memory Module — 投资工作流动态上下文加载器

这是 YMOS 当前目录结构下的投资专用记忆模块，用于把：
  - 当前关注方向与投资偏好
  - 持仓 / Watchlist 状态机
  - 最近市场洞察
  - 最近投资雷达
统一拼接为可直接复用的系统上下文。

设计原则：
  - 只服务当前 YMOS 投资工作流
  - 默认不依赖 YMOS 之外的任何目录
  - 路径由 runtime_paths.py 统一解析（持仓与关注/ / Eyes/市场洞察/ / Eyes/投资雷达/）

【命令行调试】
  python3 Eyes/scripts/openclaw_memory.py --preview --workflow investment
  python3 Eyes/scripts/openclaw_memory.py --diagnose
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parents[1]  # Eyes/scripts → Eyes → YMOS
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from runtime_paths import repo_paths


class OpenClawMemory:
    """YMOS vNext 投资工作流动态上下文加载器。"""

    def __init__(self, openclaw_root: str = None):
        if openclaw_root is None:
            # Eyes/scripts/openclaw_memory.py → scripts → Eyes → YMOS
            openclaw_root = Path(__file__).resolve().parents[2]
        self.workspace = Path(openclaw_root)
        self.paths = repo_paths(self.workspace)
        self.paths.ensure_layout()

        self.holdings_root = self.paths.holdings_root
        self.report_dir = self.paths.market_root
        self.raw_data_dir = self.report_dir / "Raw_Data"
        self.radar_reports_dir = self.paths.radar_root
        self.watchlist_dir = self.holdings_root / "动态Watchlist"
        self.holdings_dir = self.holdings_root / "持仓"
        self.radar_archive_dir = self.paths.radar_root
        self.strategy_dir = self.paths.strategy_root

        self.research_context_files = {
            "当前关注方向与投资偏好": self.holdings_root / "当前关注方向与投资偏好.md",
            "持仓状态机": self.holdings_root / "持仓_状态机.md",
            "Watchlist状态机": self.holdings_root / "Watchlist_状态机.md",
        }

    # ═══════════════════════════════════════════════════════════════
    # 统一入口：build_prompt
    # ═══════════════════════════════════════════════════════════════

    def build_prompt(
        self,
        sources: list = None,
        days: int = 14,
        max_chars: int = 800,
        base_instruction: str = None,
    ) -> str:
        """
        组合多个数据源，返回完整系统提示词。

        可用数据源（sources 参数值）：
          "research_context"    — 当前关注方向与投资偏好 + 两份状态机
          "user_profile"        — 旧调用别名；内容同 research_context，不表示 Strategy Profile
          "investment_reports"  — 最近 N 天市场洞察（Eyes/市场洞察/）
          "radar_reports"       — 最近 N 天投资雷达（Eyes/投资雷达/）
          "radar_archive"       — 最近 N 天投资雷达正式归档（Eyes/投资雷达/）
          "strategy_notes"      — 最近 N 天策略分析归档（Brain/策略分析/）
          "watchlist_notes"     — Watchlist 标的双文档摘要
          "holding_notes"       — 持仓标的双文档摘要

        Args:
            sources:         数据源列表（None 则加载全部）
            days:            历史文件追溯天数
            max_chars:       每份文件截取的最大字符数
            base_instruction: 系统提示词头部角色指令

        Returns:
            完整系统提示词字符串
        """
        if sources is None:
            sources = [
                "research_context", "investment_reports", "radar_reports",
            ]

        if base_instruction is None:
            base_instruction = (
                "你是我的专属 AI 助手。"
                "基于以下所有历史信息、个人配置和近期思考脉络，帮我完成当前任务。"
            )

        parts = [base_instruction, "\n\n---\n"]

        loader_map = {
            "research_context":    lambda: self._load_research_context(),
            "user_profile":        lambda: self._load_research_context(),
            "investment_reports":  lambda: self._load_recent_files(
                self.report_dir, days=days, max_chars=max_chars,
                label="市场洞察报告", date_format="%Y-%m-%d", glob="**/*.md",
            ),
            "radar_reports": lambda: self._load_recent_files(
                self.radar_reports_dir,
                days=days,
                max_chars=max_chars,
                label="投资雷达（正式归档）",
                date_format="%Y-%m-%d",
                glob="**/投资雷达_*.md",
            ),
            "radar_archive": lambda: self._load_recent_files(
                self.radar_archive_dir,
                days=days,
                max_chars=max_chars,
                label="投资雷达（正式归档）",
                date_format="%Y-%m-%d",
                glob="**/*.md",
            ),
            "strategy_notes": lambda: self._load_recent_files(
                self.strategy_dir,
                days=days,
                max_chars=max_chars,
                label="策略分析归档",
                date_format="%Y-%m-%d",
                glob="**/*.md",
            ),
            "watchlist_notes": lambda: self._load_ticker_notes(
                self.watchlist_dir,
                label="Watchlist 标的笔记",
                max_chars=max_chars,
            ),
            "holding_notes": lambda: self._load_ticker_notes(
                self.holdings_dir,
                label="持仓标的笔记",
                max_chars=max_chars,
            ),
        }

        for source in sources:
            if source in loader_map:
                content = loader_map[source]()
                if content:
                    parts.append(content)
                    parts.append("\n---\n")
            else:
                parts.append(f"## ⚠️ 未知数据源：{source}\n")

        parts.append("\n请基于以上所有信息完成当前任务。")
        return "\n".join(parts)

    # ═══════════════════════════════════════════════════════════════
    # 各数据源加载函数
    # ═══════════════════════════════════════════════════════════════

    def _load_research_context(self) -> str:
        """加载投研层轻量关注状态与对象身份；不加载 Strategy Profile。"""
        parts = ["## 📋 投研层当前上下文\n"]
        for label, path in self.research_context_files.items():
            if path.exists():
                text = path.read_text(encoding="utf-8").strip()
                parts.append(f"### {label}\n{text}\n")
            else:
                parts.append(f"### {label}\n（文件未找到：{path.name}）\n")
        return "\n".join(parts)

    def _load_ticker_notes(self, directory: Path, label: str, max_chars: int) -> str:
        """读取标的双文档摘要，避免默认带入无关模块。"""
        if not directory.exists():
            return f"## ⚠️ {label}目录未找到\n路径：{directory}\n"

        parts = [f"## 📁 {label}\n"]
        ticker_dirs = sorted([d for d in directory.iterdir() if d.is_dir()])
        if not ticker_dirs:
            parts.append("（暂无标的目录）\n")
            return "\n".join(parts)

        for ticker_dir in ticker_dirs:
            ticker = ticker_dir.name
            parts.append(f"### {ticker}\n")
            for note_name in ["个股基础知识库.md", "买入卖出备忘录.md"]:
                note_path = ticker_dir / note_name
                if note_path.exists():
                    content = note_path.read_text(encoding="utf-8").strip()
                    preview = content[:max_chars] + (
                        "…（已截断）" if len(content) > max_chars else ""
                    )
                    parts.append(f"#### {note_name}\n{preview}\n")
            parts.append("")
        return "\n".join(parts)

    def _load_recent_files(
        self, directory: Path, days: int, max_chars: int,
        label: str, date_format: str, glob: str,
    ) -> str:
        """扫描目录，加载最近 N 天的文件摘要。"""
        if not directory.exists():
            return f"## ⚠️ {label}目录未找到\n路径：{directory}\n"

        cutoff = datetime.now() - timedelta(days=days)
        found = []

        for f in sorted(directory.glob(glob), reverse=True):
            if f.name.lower() == "readme.md":
                continue
            # 尝试从文件名提取日期
            date_str = f.stem.split("_")[0]
            try:
                file_date = datetime.strptime(date_str, date_format)
            except ValueError:
                continue
            if file_date < cutoff:
                continue
            content = f.read_text(encoding="utf-8").strip()
            preview = content[:max_chars] + ("…（已截断）" if len(content) > max_chars else "")
            found.append(f"### {date_str}\n{preview}\n")

        if not found:
            return f"## 📭 {label}（最近 {days} 天无记录）\n"
        return f"## 📅 {label}（最近 {days} 天，共 {len(found)} 份）\n\n" + "\n".join(found)

    def for_investment_report(self, days: int = 30) -> str:
        """市场洞察 / 投资雷达专用上下文。"""
        return self.build_prompt(
            sources=["research_context", "investment_reports", "radar_reports"],
            days=days,
            base_instruction=(
                "你是我的专属投研助手。基于以下市场洞察、投资雷达、当前关注状态与对象身份，"
                "帮我分析最新数据、识别值得验证的信号并形成研究队列；不要生成买卖动作。"
            ),
        )

    # ═══════════════════════════════════════════════════════════════
    # 诊断工具
    # ═══════════════════════════════════════════════════════════════

    def diagnose(self):
        """打印所有关键路径的状态，用于调试。"""
        print("=" * 60)
        print("YMOS vNext Memory Module — 路径诊断")
        print("=" * 60)
        print(f"📁 工作区根目录：{self.workspace}")
        print()

        checks = {
            "持仓与关注目录": self.holdings_root,
            "市场洞察报告目录": self.report_dir,
            "原始数据目录": self.raw_data_dir,
            "投资雷达目录": self.radar_reports_dir,
            "Watchlist目录": self.watchlist_dir,
            "持仓目录": self.holdings_dir,
        }
        for label, path in checks.items():
            status = "✅" if path.exists() else "❌ 未找到"
            print(f"  {status} {label}")

        print()
        for label, directory in [
            ("市场洞察", self.report_dir),
            ("投资雷达", self.radar_reports_dir),
            ("Watchlist 标的", self.watchlist_dir),
            ("持仓标的", self.holdings_dir),
        ]:
            if directory.exists():
                count = len(list(directory.rglob("*.md")))
                print(f"  📊 {label} 历史文件数：{count}")
        print("=" * 60)


# ═══════════════════════════════════════════════════════════════════
# 快捷函数（工作流暗号一行调用）
# ═══════════════════════════════════════════════════════════════════

def get_prompt(sources: list = None, days: int = 14, root: str = None) -> str:
    """通用快捷函数，工作流暗号最常用调用方式。"""
    return OpenClawMemory(root).build_prompt(sources=sources, days=days)


# ═══════════════════════════════════════════════════════════════════
# 命令行执行（调试 / 预览）
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="YMOS vNext Memory Module — 调试与预览"
    )
    parser.add_argument("--root", default=None, help="工作区根目录（不填则自动定位）")
    parser.add_argument("--days", type=int, default=14, help="历史追溯天数（默认 14）")
    parser.add_argument(
        "--sources", nargs="*",
        default=["research_context", "investment_reports", "radar_reports"],
        help="数据源列表（空格分隔）",
    )
    parser.add_argument("--diagnose", action="store_true", help="只输出路径诊断")
    parser.add_argument("--preview", action="store_true", help="输出系统提示词预览")
    parser.add_argument(
        "--workflow",
        choices=["investment"],
        help="使用预设工作流快捷入口",
    )
    args = parser.parse_args()

    mem = OpenClawMemory(args.root)
    mem.diagnose()

    if args.diagnose:
        sys.exit(0)

    if args.preview or args.workflow:
        print("\n" + "─" * 60)
        print("📝 系统提示词预览（前 2000 字）：")
        print("─" * 60)

        if args.workflow == "investment":
            prompt = mem.for_investment_report(days=args.days)
        else:
            prompt = mem.build_prompt(sources=args.sources, days=args.days)

        print(prompt[:2000])
        if len(prompt) > 2000:
            print(f"\n…（已截断，完整 {len(prompt)} 字）")
