---
title: SOP_问财公告搜索
version: v0.1
updated: 2026-05-10
status: active
scope: YMOS 自动建档 / 初始调研 / 策略分析 / A股事实核验
---

# SOP_问财公告搜索

## 1. 定位

问财公告搜索是 A 股调研中的「公告事实层」，优先级高于新闻、研报、普通搜索摘要。

它回答：

- 公司最近披露了哪些硬公告？
- 最新年报/季报/业绩预告/快报在哪里？
- 是否有回购、增持、分红、重大合同、资产重组等关键事件？
- 新闻或研报提到的事实，能不能回公告核验？

## 2. 本机安装位置

SkillHub 技能已安装：

```bash
<SKILL_ROOT>/announcement-search
```

YMOS 不直接调用 Skill 的官方接口，而是走仓库内的封装脚本（统一输出格式、统一失败降级）：

```bash
<你的 YMOS 根目录>/Eyes/scripts/iwencai_announcement_search.py
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
python3 Eyes/scripts/iwencai_announcement_search.py "大族激光 2026 一季报 公告" -l 5
```

输出：

```bash
Eyes/公告搜索/Raw_Data/YYYY-MM/announcement_search_[query]_YYYYMMDD.json
Eyes/公告搜索/YYYY-MM/公告搜索_[query]_YYYY-MM-DD.md
```

## 4. 查询模板

按优先级使用：

```text
[股票名] 最新公告
[股票名] 最新一季报 公告
[股票名] 年报 公告
[股票名] 业绩预告 OR 业绩快报
[股票名] 回购 增持 公告
[股票名] 重大合同 订单 中标 公告
[股票名] 资产重组 收购 公告
```

自动建档默认至少跑：

```bash
python3 Eyes/scripts/iwencai_announcement_search.py "股票名 最新一季报 年报 业绩预告 公告" -l 8
```

## 5. 写入规则

公告搜索结果用于补：

- `P1 基石档案`：最新财报、业务事件、治理变化、分红回购；
- `P2 阶段判断`：业绩是否兑现，叙事是否被公告验证；
- `P4 重点关注点`：下一份财报/公告要验证什么；
- `P9 估值分析`：财报口径的收入、利润、现金流、利润率；
- `P3 事件影响审计`：作为公告事实与论点变化的证据底座。

## 6. 使用纪律

1. 公告是事实层，优先级高于研报和新闻。
2. 公告摘要仍不等于原文；关键买卖判断前，要尽量点开公告/财报原文核验。
3. 如果公告与新闻/研报冲突，以公告为准。
4. 如果查询不到，先改写关键词，不要直接判断“没有披露”。
5. 自动建档里，公告搜索应放在财务查询之后、研报/新闻之前。

## 7. 已验证样例

2026-05-10 smoke test：

```bash
python3 Eyes/scripts/iwencai_announcement_search.py "大族激光 2026 一季报 公告" -l 3 --date-tag 20260510
```

验证结果：成功返回 3 条公告结果。

样例文件：

```bash
Eyes/公告搜索/2026-05/公告搜索_大族激光_2026_一季报_公告_2026-05-10.md
Eyes/公告搜索/Raw_Data/2026-05/announcement_search_大族激光_2026_一季报_公告_20260510.json
```
