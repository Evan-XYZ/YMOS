---
title: SOP_问财新闻搜索
version: v0.1
updated: 2026-05-10
status: active
scope: YMOS 自动建档 / 初始调研 / 策略分析 / 市场事件追踪
---

# SOP_问财新闻搜索

## 1. 定位

问财新闻搜索是 A 股调研中的「最新事件层 / 传播势能层」。

它回答：

- 最近市场在传播什么事件？
- 公司业务有没有新订单、新产品、政策催化、产业链变化？
- 价格异动对应的叙事是什么？
- 研报观点之外，媒体和产业侧有没有新增信息？

优先级：公告/财报事实 > 财务结构化数据 > 研报叙事 > 新闻事件 > 普通网页摘要。

## 2. 本机安装位置

SkillHub 技能已安装：

```bash
<SKILL_ROOT>/news-search
```

YMOS 不直接调用 Skill 的官方接口，而是走仓库内的封装脚本（统一输出格式、统一失败降级）：

```bash
<你的 YMOS 根目录>/Eyes/scripts/iwencai_news_search.py
```

环境变量来自 shell/profile 或当前进程环境：

```bash
IWENCAI_BASE_URL=...
IWENCAI_API_KEY=...
```

注意：不要把 API Key 写入 Obsidian 文件或报告正文。

## 3. 标准调用

```bash
cd "<你的 YMOS 根目录>"
python3 Eyes/scripts/iwencai_news_search.py "大族激光 AI PCB 最新新闻" -l 5 --days 30
```

输出：

```bash
Eyes/新闻搜索/Raw_Data/YYYY-MM/news_search_[query]_YYYYMMDD.json
Eyes/新闻搜索/YYYY-MM/新闻搜索_[query]_YYYY-MM-DD.md
```

## 4. 查询模板

```text
[股票名] 最新新闻
[股票名] [核心业务] 最新进展
[股票名] AI / 机器人 / 光模块 / PCB / 存储 等主题
[股票名] 订单 中标 合作
[股票名] 业绩 增长 原因
[股票名] 风险 监管 诉讼 减持
```

自动建档默认跑：

```bash
python3 Eyes/scripts/iwencai_news_search.py "股票名 核心业务 最新新闻" -l 8 --days 30
```

## 5. 写入规则

新闻搜索结果用于补：

- `P1 基石档案`：最新业务进展、客户/订单/产能变化；
- `P4 重点关注点`：传播中的催化与风险；
- `P2 阶段判断`：市场是否正在从“叙事”进入“兑现”；
- `P3 事件影响审计`：判断传播变化是否影响原论点、失效信号或仅属于噪音。

## 6. 使用纪律

1. 新闻是传播层，不是事实层。
2. 新闻提到订单、业绩、重大合作时，必须优先回公告搜索核验。
3. 新闻和价格异动共振时，才提高优先级；单纯新闻热但价格不动，标记为“叙事未被市场确认”。
4. 自动建档中，新闻搜索放在公告/财务/研报之后，用于补最新事件和传播势能。
5. 对负面新闻要单独进入 P4 风险项，不要只收集利好。

## 7. 已验证样例

2026-05-10 smoke test：

```bash
python3 Eyes/scripts/iwencai_news_search.py "大族激光 AI PCB 最新新闻" -l 3 --date-tag 20260510
```

验证结果：成功返回 3 条新闻结果。

样例文件：

```bash
Eyes/新闻搜索/2026-05/新闻搜索_大族激光_AI_PCB_最新新闻_2026-05-10.md
Eyes/新闻搜索/Raw_Data/2026-05/news_search_大族激光_AI_PCB_最新新闻_20260510.json
```
