#!/usr/bin/env python3
"""YMOS V4 路径解析 — 三模块 + 运行时 + 决策台（Eyes / Brain / 持仓与关注）"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    root: Path  # YMOS 根目录

    # ── 模块根 ──────────────────────────────────────
    @property
    def eyes_root(self) -> Path:
        return self.root / "Eyes"

    @property
    def brain_root(self) -> Path:
        return self.root / "Brain"

    @property
    def holdings_root(self) -> Path:
        return self.root / "持仓与关注"

    # ── Eyes: scripts ────────────────────────────────
    @property
    def scripts_root(self) -> Path:
        return self.eyes_root / "scripts"

    # ── Eyes: 报告（直接在 Eyes/ 下，无 Report 层级）──
    @property
    def market_root(self) -> Path:
        return self.eyes_root / "市场洞察"

    @property
    def radar_root(self) -> Path:
        return self.eyes_root / "投资雷达"

    # ── Brain: 策略分析（直接在 Brain/ 下，无 Report 层级）
    @property
    def strategy_root(self) -> Path:
        return self.brain_root / "策略分析"

    # ── Brain: references ────────────────────────────
    @property
    def references_root(self) -> Path:
        return self.brain_root / "references"

    # ── 持仓与关注 ───────────────────────────────────
    @property
    def watchlist_dir(self) -> Path:
        return self.holdings_root / "动态Watchlist"

    @property
    def holding_dir(self) -> Path:
        return self.holdings_root / "持仓"

    @property
    def template_dir(self) -> Path:
        return self.holdings_root / "_模板_单标的"

    @property
    def watchlist_state(self) -> Path:
        return self.holdings_root / "Watchlist_状态机.md"

    @property
    def holding_state(self) -> Path:
        return self.holdings_root / "持仓_状态机.md"

    @property
    def strategy_pref(self) -> Path:
        """旧属性名，向前兼容；返回投研层轻量关注文件，不是 Strategy Profile。"""
        return self.current_focus

    @property
    def current_focus(self) -> Path:
        return self.holdings_root / "当前关注方向与投资偏好.md"

    # ── 目录布局初始化 ──────────────────────────────
    def ensure_layout(self) -> None:
        for path in [
            self.scripts_root,
            self.market_root,
            self.radar_root,
            self.strategy_root,
            self.references_root,
            self.holdings_root,
            self.holding_dir,
            self.watchlist_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    # ── 日期路径工具 ─────────────────────────────────
    def month_dir(self, base: Path, date_value) -> Path:
        return base / date_value.strftime("%Y-%m")

    # Eyes: 市场洞察
    def market_report_path(self, date_value) -> Path:
        return self.month_dir(self.market_root, date_value) / f"{date_value.isoformat()}_市场洞察.md"

    def market_raw_path(self, date_tag: str) -> Path:
        month_tag = f"{date_tag[:4]}-{date_tag[4:6]}"
        return self.market_root / "Raw_Data" / month_tag / f"financial_data_{date_tag}.json"

    # Eyes: 投资雷达
    def radar_report_path(self, date_value) -> Path:
        return self.month_dir(self.radar_root, date_value) / f"投资雷达_{date_value.isoformat()}.md"

    def radar_raw_dir(self, date_tag: str) -> Path:
        month_tag = f"{date_tag[:4]}-{date_tag[4:6]}"
        return self.radar_root / "Raw_Data" / month_tag

    # Brain: 策略分析
    def strategy_report_path(self, date_value, ticker: str = "", action: str = "") -> Path:
        if ticker:
            return self.month_dir(self.strategy_root, date_value) / f"{date_value.isoformat()}_{ticker}_{action}.md"
        return self.month_dir(self.strategy_root, date_value) / f"{date_value.isoformat()}_策略分析.md"

    def strategy_log_path(self, date_value) -> Path:
        """策略分析日志（当日汇总）"""
        return self.month_dir(self.strategy_root, date_value) / f"策略分析日志_{date_value.isoformat()}.md"

    def strategy_raw_dir(self, date_tag: str) -> Path:
        month_tag = f"{date_tag[:4]}-{date_tag[4:6]}"
        return self.strategy_root / "Raw_Data" / month_tag

    # ── Legacy 兼容（读取旧路径，迁移期使用）────────
    @property
    def legacy_root(self) -> Path:
        return self.root / "legacy"

    def resolve_existing(self, canonical: Path, legacy: Path) -> Path:
        if canonical.exists():
            return canonical
        return legacy


def repo_paths(root: Path | None = None) -> RuntimePaths:
    """从脚本位置推导 YMOS 根目录。
    脚本在 Eyes/scripts/ 下，所以 parents[2] = YMOS root。
    """
    base = root or Path(__file__).resolve().parents[2]
    return RuntimePaths(base)
