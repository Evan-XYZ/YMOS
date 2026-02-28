---
name: stock-research
description: 个股研究与分析技能。用于：初次调研某只股票建立基石档案、生成个股关注信息清单、进行估值泡沫度量、事件触发的公司深度洞察分析。当用户提到"分析某只股票"、"调研个股"、"建立股票档案"、"估值分析"、"公司深度分析"时使用此技能。
---

# 个股研究与分析 (Stock Research)

本技能提供个股深度研究的完整框架，覆盖从初始调研到持续跟踪的全流程。

## 核心理念

投资提示词的本质是"投资思维的代码化"，用于固定投资思维与逻辑，确保分析视角不遗漏，情绪上保持克制。

## 全局执行协议 (Global Protocol)
**所有 Skill 执行前必须遵守：**
1.  **Anchor Date**: 永远首先确认系统当前时间。
2.  **Freshness Check**: 任何输入的 Knowledge Base 视为"历史参考"。必须进行一次`Verify`性质的联网搜索（如："NIO latest earnings 2025 2026"），确保决策基于当下最新数据。
3.  **Version Override**: 当知识库数据与联网数据冲突时，以联网最新数据为准（Timestamp Priority）。

## 提示词矩阵

| 提示词 | 场景 | 参考文件 |
|-------|------|---------|
| P1-Genesis | 初次调研，建立个股基石档案 | [p1-genesis.md](references/p1-genesis.md) |
| P4-Radar | 生成个股强制关注信息清单 | [p4-radar.md](references/p4-radar.md) |
| P9-Valuation | 反向 DCF 估值泡沫度量 | [p9-valuation.md](references/p9-valuation.md) |
| P15-Insight | 事件触发的 7 维深度洞察 | [p15-insight.md](references/p15-insight.md) |

## 使用指南

### 场景 1: 初次关注某只股票

读取 [p1-genesis.md](references/p1-genesis.md)，使用 P1 模板建立深度基石档案。

**输入要求：**
- `ticker`: 股票代码（必填）
- `context`: 补充的公司资料、财报数据（可选）

**输出：** 包含治理结构、商业壁垒、财务健康、周期维度、博弈维度的结构化 Markdown 档案。

### 场景 2: 设置个股关注雷达

读取 [p4-radar.md](references/p4-radar.md)，使用 P4 模板生成信息关注清单。

**输入要求：**
- `ticker`: 股票代码（必填）
- `context`: 已有的基石档案（可选）

**输出：** 覆盖本体核心、竞品映射、产业链、宏观因素的 Checklist。

### 场景 3: 评估估值是否过高

读取 [p9-valuation.md](references/p9-valuation.md)，使用 P9 模板进行反向 DCF 分析。

**输入要求：**
- `ticker`: 股票代码（必填）
- `price`: 当前价格/市值（必填）
- `financials`: 最近一年 FCF 或净利润（必填）
- `context`: 市场共识增长率（可选）

**输出：** 隐含增长率、现实检验、安全边际建议。

### 场景 4: 事件触发的深度洞察

读取 [p15-insight.md](references/p15-insight.md)，使用 P15 模板进行 7 维分析。

**输入要求：**
- `ticker`: 股票代码（必填）
- `event`: 触发事件详情（必填）
- `notes`: 补充说明（可选）

**输出：** 包含 5 个内部维度 + 2 个外部维度的深度洞察报告。

## 分析框架速查

### 五维分析框架 (P1/P15 通用)

1. **治理结构 (The Soul)**: 掌舵人类型、团队稳定性、股东结构
2. **商业壁垒 (The Engine)**: 盈利逻辑、护城河、反脆弱性
3. **财务健康 (The Fuel)**: 现金流、资本效率、北极星指标
4. **周期维度 (The Cycle)**: 行业阶段、宏观敏感度、竞争终局
5. **博弈维度 (The Alpha)**: Bull/Bear Case、预期差

### 信息关注四维度 (P4)

1. **本体核心**: 官方文件、管理层动作
2. **竞品映射**: 直接竞争对手动态
3. **产业链**: 上下游价格与政策
4. **宏观因素**: 利率、地缘、政策
