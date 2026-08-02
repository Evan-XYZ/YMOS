#!/usr/bin/env python3
"""
BrainStorm Memory Module — 头脑风暴文件复用与动态上下文加载器

YMOS BrainStorm 模块的上下文加载器。加载、归档与预览只用标准库，路径全部相对推导；
可选的 auto_summarize() 需要 OpenAI SDK 或兼容其 chat.completions 接口的客户端。

核心功能：
  1. load_context()        — 加载 MEMORY.md + STATUS + 最近 N 天总结；可选历史资料索引
  2. archive_today()       — 将今日原始对话存入 Raw_Thoughts/YYYY-MM-DD.md
  3. auto_summarize()      — 调用 LLM 生成结构化总结 → 存入 Summarized_Insights/
  4. append_to_memory()    — 经 Human 确认后追加新认知到 MEMORY.md
  5. diagnose()            — 打印路径诊断，调试用

【工作流暗号调用方式】
  from scripts.brainstorm_memory import BrainStormMemory
  mem = BrainStormMemory()
  system_prompt = mem.load_context()   # 一行获取完整历史上下文

【命令行调试】
  python3 scripts/brainstorm_memory.py --preview
  python3 scripts/brainstorm_memory.py --days 14
"""

from datetime import datetime, timedelta
from pathlib import Path


class BrainStormMemory:
    """
    BrainStorm 工作区的文件复用与动态上下文加载器。

    brainstorm_root: BrainStorm 根目录路径（绝对路径或相对路径均可）。
    默认自动定位：scripts/brainstorm_memory.py 的上一级即 BrainStorm 根目录。
    """

    def __init__(self, brainstorm_root: str = None):
        if brainstorm_root is None:
            brainstorm_root = Path(__file__).resolve().parent.parent
        self.root = Path(brainstorm_root)

        # ── 核心目录路径 ──────────────────────────────────────────
        # 约定：Raw 与 Insight 都按月归档到 YYYY-MM/ 子目录下
        self.raw_dir       = self.root / "每日头脑风暴" / "Raw_Thoughts"
        self.summary_dir   = self.root / "Summarized_Insights"
        self.invest_st_dir = self.root / "投资感悟归档" / "短期灵感"
        self.invest_lt_dir = self.root / "投资感悟归档" / "长期框架"
        self.invest_ck_dir = self.root / "投资感悟归档" / "执行清单"
        self.status_dir    = self.root / "状态机"
        self.history_dir   = self.root / "历史投资资料"
        self.history_summary_dir = self.history_dir / "索引与梳理"

        # ── 核心文件 ──────────────────────────────────────────────
        self.memory_file   = self.root / "MEMORY.md"
        self.status_file   = self.status_dir / "STATUS.md"
        self.history_index_file = self.history_dir / "资料索引.md"
        self.readme_file   = self.root / "README.md"

        # 确保目录存在
        for d in [self.raw_dir, self.summary_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # ── 按月归档的路径helper ─────────────────────────────────────
    def raw_path_for(self, date: datetime) -> Path:
        """Raw_Thoughts/YYYY-MM/YYYY-MM-DD.md"""
        return self.raw_dir / date.strftime("%Y-%m") / f"{date.strftime('%Y-%m-%d')}.md"

    def summary_path_for(self, date: datetime) -> Path:
        """Summarized_Insights/YYYY-MM/YYYY-MM-DD_Insight.md"""
        return self.summary_dir / date.strftime("%Y-%m") / f"{date.strftime('%Y-%m-%d')}_Insight.md"

    # ═══════════════════════════════════════════════════════════════
    # 1. 加载上下文（一行搞定系统提示词）
    # ═══════════════════════════════════════════════════════════════
    def load_context(
        self,
        days: int = 7,
        max_chars_per_summary: int = 600,
        include_history: bool = False,
        max_chars_history: int = 5000,
        base_instruction: str = (
            "你是我专属的头脑风暴伙伴和思维教练。"
            "基于以下所有历史记忆和近期思考脉络，"
            "用口语化方式帮我深入探索今天的想法。"
        ),
    ) -> str:
        """
        组合 MEMORY.md + 最近 N 天总结，返回完整系统提示词。

        Args:
            days:                 向前追溯总结文件的天数（默认 7 天）
            max_chars_per_summary: 每份总结截取的最大字符数
            include_history:      是否加载历史资料索引与最近梳理（默认关闭）
            max_chars_history:    历史资料上下文的总字符上限
            base_instruction:     系统提示词头部的角色指令

        Returns:
            完整系统提示词字符串，可直接塞入 AI 对话
        """
        parts = [base_instruction, "\n\n---\n"]

        # 加载长期记忆
        if self.memory_file.exists():
            memory_text = self.memory_file.read_text(encoding="utf-8").strip()
            parts.append(f"## 📚 长期记忆（MEMORY.md）\n{memory_text}\n")
        else:
            parts.append("## 📚 长期记忆\n（MEMORY.md 文件未找到）\n")

        # 加载当前阶段状态；它回答“我现在在哪”，与长期记忆分开
        if self.status_file.exists():
            status_text = self.status_file.read_text(encoding="utf-8").strip()
            parts.append(f"\n---\n\n## 🧭 当前阶段（STATUS.md）\n{status_text}\n")
        else:
            parts.append("\n---\n\n## 🧭 当前阶段\n（STATUS.md 文件未找到）\n")

        # 加载最近 N 天总结
        recent = self._load_recent_summaries(days=days, max_chars=max_chars_per_summary)
        if recent:
            parts.append(f"\n---\n\n## 📅 最近 {days} 天思考脉络\n{recent}")
        else:
            parts.append(f"\n---\n\n## 📅 最近 {days} 天思考脉络\n（暂无总结，今天是第一天）\n")

        # 历史资料只在入职、诊断或相关主题复盘时按需加载；日常默认关闭
        if include_history:
            history = self._load_historical_context(max_chars=max_chars_history)
            parts.append(f"\n---\n\n## 🗂️ 历史投资资料导航\n{history}\n")

        parts.append("\n\n---\n\n请基于以上所有背景，和我继续今天的对话。")
        return "\n".join(parts)

    def _load_recent_summaries(self, days: int, max_chars: int) -> str:
        """扫描 Summarized_Insights/ 加载最近 N 天总结。"""
        if not self.summary_dir.exists():
            return ""
        cutoff = datetime.now() - timedelta(days=days)
        found = []
        # rglob：兼容按月归档（YYYY-MM/）与早期平铺存放
        files = [f for f in self.summary_dir.rglob("*.md") if f.name.lower() != "readme.md"]
        files.sort(key=lambda f: f.stem, reverse=True)
        for f in files:
            date_str = f.stem.split("_")[0]
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue
            if file_date < cutoff:
                continue
            content = f.read_text(encoding="utf-8").strip()
            preview = content[:max_chars] + ("…（已截断）" if len(content) > max_chars else "")
            found.append(f"### {date_str}\n{preview}\n")
        return "\n".join(found)

    def _load_historical_context(self, max_chars: int = 5000) -> str:
        """加载历史资料索引与最近梳理，不直接全量读取原始资料。"""
        parts = []
        remaining = max(0, max_chars)

        if self.history_index_file.exists() and remaining:
            index_text = self.history_index_file.read_text(encoding="utf-8").strip()
            excerpt = index_text[:remaining]
            if len(index_text) > len(excerpt):
                excerpt += "\n…（资料索引已截断）"
            parts.append(f"### 资料索引\n{excerpt}")
            remaining -= len(excerpt)
        else:
            parts.append("### 资料索引\n（尚未生成资料索引；先运行 SOP_历史投资资料入职.md）")

        if self.history_summary_dir.exists() and remaining > 0:
            summaries = [
                path
                for path in self.history_summary_dir.glob("*.md")
                if not path.name.startswith("_模板_") and path.name.lower() != "readme.md"
            ]
            summaries.sort(key=lambda path: path.stat().st_mtime, reverse=True)
            for path in summaries[:2]:
                text = path.read_text(encoding="utf-8").strip()
                excerpt = text[:remaining]
                if not excerpt:
                    break
                if len(text) > len(excerpt):
                    excerpt += "\n…（梳理报告已截断）"
                parts.append(f"### 最近梳理：{path.name}\n{excerpt}")
                remaining -= len(excerpt)

        parts.append("原始资料未自动加载；请按索引只读取与当前问题直接相关的代表文件。")
        return "\n\n".join(parts)

    # ═══════════════════════════════════════════════════════════════
    # 2. 存档今日原始对话
    # ═══════════════════════════════════════════════════════════════
    def archive_today(self, content: str, date: datetime = None) -> Path:
        """
        将今日原始对话/想法存入 Raw_Thoughts/YYYY-MM-DD.md。
        如文件已存在，则追加（同一天多次头脑风暴）。

        Args:
            content: 原始对话内容
            date:    日期（默认今天）

        Returns:
            写入的文件 Path
        """
        if date is None:
            date = datetime.now()
        filename = self.raw_path_for(date)
        filename.parent.mkdir(parents=True, exist_ok=True)
        header = f"### {date.strftime('%H:%M')} 记录\n"
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"\n{header}{content.strip()}\n")
        print(f"✅ 原始记录已存档：{filename}")
        return filename

    # ═══════════════════════════════════════════════════════════════
    # 3. LLM 自动总结 → 存档到 Summarized_Insights/
    # ═══════════════════════════════════════════════════════════════
    def auto_summarize(
        self,
        full_conversation: str,
        client=None,
        model: str = "gpt-4o-mini",
        date: datetime = None,
    ) -> str:
        """
        调用 LLM 将完整对话压缩成结构化 Markdown 总结，
        写入 Summarized_Insights/YYYY-MM-DD_Insight.md，
        MEMORY 候选只写进总结，不自动修改 MEMORY.md。

        Args:
            full_conversation: 完整对话文本
            client:            OpenAI 兼容 client（None 则自动初始化 OpenAI）
            model:             使用的模型
            date:              对话日期（默认今天）

        Returns:
            生成的总结字符串
        """
        if client is None:
            try:
                from openai import OpenAI
                client = OpenAI()
            except ImportError:
                return "⚠️ auto_summarize 需要安装 openai：pip install openai"

        if date is None:
            date = datetime.now()

        prompt = f"""请把下面这次头脑风暴对话压缩成简洁的 Markdown 总结（300-500字以内）。

格式严格如下：
# {date.strftime('%Y-%m-%d')} 头脑风暴总结

## 🔑 关键洞察（3-5条）
- 

## ✅ 下一步行动（具体可执行）
- [ ] 

## ❓ 待深入思考的问题
- 

## 📌 值得写入 MEMORY.md 的新认知
- （无则写"无"）

## 🔗 是否该联动 YMOS
- 触发模块：（无 / P2 环境识别 / P3 事件审计 / P5 买入审计 / P6 退出审计 / P7 组合检查 / P11 复盘 / P12 最终裁判 / diagnosis）
- 触发理由：（如有则说明）

## 🧬 内核演化判断
- 暂不处理 / 继续积累 / 建议起草变更提案
- 证据、反例与缺口：

---
对话内容：
{full_conversation[:12000]}"""

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        summary = response.choices[0].message.content

        # 写入 Summarized_Insights/
        summary_path = self.summary_path_for(date)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(summary, encoding="utf-8")
        print(f"✅ 总结已存档：{summary_path}")

        return summary

    # ═══════════════════════════════════════════════════════════════
    # 4. 追加单条认知到 MEMORY.md
    # ═══════════════════════════════════════════════════════════════
    def append_to_memory(self, content: str, section: str = "💡 积累的认知节点") -> None:
        """
        把一条新认知追加到 MEMORY.md 的指定章节。

        Args:
            content: 认知内容（一行）
            section: 目标章节标题（默认"💡 积累的认知节点"）
        """
        today = datetime.now().strftime("%Y-%m-%d")
        entry = f"\n[{today}] {content.strip()}"

        text = self.memory_file.read_text(encoding="utf-8")
        if section in text:
            # 在章节标题下方插入
            text = text.replace(
                f"## {section}\n",
                f"## {section}\n{entry}\n",
            )
            self.memory_file.write_text(text, encoding="utf-8")
        else:
            # 章节不存在，直接追加在文件末尾
            with open(self.memory_file, "a", encoding="utf-8") as f:
                f.write(f"\n## {section}\n{entry}\n")

        print(f"✅ 已追加到 MEMORY.md [{section}]")

    # ═══════════════════════════════════════════════════════════════
    # 5. 诊断工具
    # ═══════════════════════════════════════════════════════════════
    def diagnose(self):
        """打印路径状态，用于调试。"""
        print("=" * 55)
        print("BrainStorm Memory Module — 路径诊断")
        print("=" * 55)
        print(f"📁 BrainStorm 根目录：{self.root}")
        print()

        checks = {
            "Raw_Thoughts 目录":        (self.raw_dir, True),
            "Summarized_Insights 目录": (self.summary_dir, True),
            "MEMORY.md":               (self.memory_file, True),
            "STATUS.md":               (self.status_file, True),
            "历史资料目录":             (self.history_dir, True),
            "历史资料索引":             (self.history_index_file, False),
        }
        for label, (path, required) in checks.items():
            if path.exists():
                status = "✅"
            elif required:
                status = "❌ 未找到"
            else:
                status = "— 可选未创建"
            print(f"  {status} {label}: {path}")

        # 统计总结文件
        if self.summary_dir.exists():
            summaries = [
                f for f in self.summary_dir.rglob("*.md")
                if f.name.lower() != "readme.md"
            ]
            print(f"\n  📊 历史总结数量：{len(summaries)} 份")
            recent = [
                f for f in summaries
                if self._parse_date(f) is not None
                and self._parse_date(f) >= datetime.now() - timedelta(days=7)
            ]
            print(f"  📅 最近 7 天总结：{len(recent)} 份")
        print("=" * 55)

    def _parse_date(self, path: Path):
        try:
            return datetime.strptime(path.stem.split("_")[0], "%Y-%m-%d")
        except ValueError:
            return None


# ═══════════════════════════════════════════════════════════════════
# 快捷函数
# ═══════════════════════════════════════════════════════════════════

def get_brainstorm_prompt(
    brainstorm_root: str = None,
    days: int = 7,
    include_history: bool = False,
) -> str:
    """
    快捷函数：一行获取 BrainStorm 完整系统提示词。

    工作流暗号用法：
        from scripts.brainstorm_memory import get_brainstorm_prompt
        system_prompt = get_brainstorm_prompt()
    """
    return BrainStormMemory(brainstorm_root).load_context(
        days=days,
        include_history=include_history,
    )


# ═══════════════════════════════════════════════════════════════════
# 命令行独立执行（调试 / 诊断用）
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="BrainStorm Memory Module — 诊断与预览工具"
    )
    parser.add_argument("--root", default=None, help="BrainStorm 根目录路径（不填则自动定位）")
    parser.add_argument("--days", type=int, default=7, help="历史总结追溯天数（默认 7）")
    parser.add_argument("--preview", action="store_true", help="输出完整系统提示词预览")
    parser.add_argument(
        "--include-history",
        action="store_true",
        help="额外加载历史投资资料索引与最近梳理，不加载原始资料全文",
    )
    args = parser.parse_args()

    mem = BrainStormMemory(args.root)
    mem.diagnose()

    if args.preview:
        print("\n" + "─" * 55)
        print("📝 系统提示词预览（前 2000 字）：")
        print("─" * 55)
        prompt = mem.load_context(days=args.days, include_history=args.include_history)
        print(prompt[:2000])
        if len(prompt) > 2000:
            print(f"\n…（已截断，完整 {len(prompt)} 字）")
