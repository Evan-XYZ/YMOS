---
title: SOP_问财经研报搜索
version: v0.1
updated: 2026-05-10
status: active
scope: YMOS 自动建档 / 初始调研 / A股核心资产复核
---

# SOP_问财经研报搜索

## 1. 定位

问财经研报搜索不是用来替代 P17/P9 判断，而是补上「市场叙事层」：

- 券商正在怎么讲这个股票？
- 他们把增长归因到哪个业务/催化？
- 有没有明确评级、目标价、可比公司、估值方法？
- 市场当前交易的是业绩兑现、产业趋势、估值修复，还是纯主题？

在 A 股自动建档和核心资产复核里，它的价值很高：有研报时，Agent 可以更快抓住主流叙事和市场偏好；但关键财务、公告、订单、风险仍然要回到原始公告/财报核验。

## 2. 本机安装位置

本机已安装 SkillHub 的 `report-search`：

```bash
<SKILL_ROOT>/report-search
<SKILL_ROOT>/report-search/scripts/cli.py
```

历史上问财选股类技能也存在于：

```bash
<SKILL_ROOT>/hithink-astock-selector
<SKILL_ROOT>/hithink-usstock-selector
<SKILL_ROOT>/问财选A股
<SKILL_ROOT>/问财选美股
<SKILL_ROOT>/hithink-market-query
```

环境变量位于 shell profile：

```bash
~/.zprofile
~/.zshrc
```

包含：

```bash
IWENCAI_BASE_URL=...
IWENCAI_API_KEY=...
```

注意：不要把 API Key 写入 Obsidian 文件或报告正文。

## 3. YMOS 封装脚本

统一使用仓库内的封装脚本，不直接依赖 Skill 的官方 Prompt（保证输出结构稳定）：

```bash
cd "<你的 YMOS 根目录>"
python3 Eyes/scripts/iwencai_report_search.py "大族激光" -l 5 --date-tag 20260510
```

输出：

```bash
Eyes/研报搜索/Raw_Data/YYYY-MM/report_search_[query]_YYYYMMDD.json
Eyes/研报搜索/YYYY-MM/研报搜索_[query]_YYYY-MM-DD.md
```

脚本会自动查找 `report-search` CLI，优先路径：

1. `<SKILL_ROOT>/report-search/scripts/cli.py`
2. `~/.openclaw/workspace/skills/report-search/scripts/cli.py`
3. 当前目录下 `skills/report-search/scripts/cli.py`

## 4. 在自动建档中的使用方式

自动建档 / 初始调研时，对 A 股候选至少跑一次：

```bash
python3 Eyes/scripts/iwencai_report_search.py "股票名" -l 5
```

然后把研报结论写入：

- `P1 基石档案`：主流券商叙事、业务拆分、催化。
- `P4 重点关注点`：机构共同关注的问题、风险、财报验证点。
- `P9 估值分析`：目标价、PE/PS/PEG、可比公司，只作为估值锚点参考。
- `P17 核心资产判定`：市场是否把它当核心资产交易；叙事是否匹配稀缺性和终局结构。

## 5. 使用纪律

1. 研报是“市场怎么看”，不是“真相”。
2. 研报评级不能直接等于买入信号。
3. 如果研报和价格走势共振，优先进入深研；如果研报很多但价格不动，标记为“叙事未被市场确认”。
4. 如果研报观点集中但都来自同一机构，要降低置信度。
5. 关键数据必须回公告/财报二次确认。

## 6. 已验证样例

2026-05-10 smoke test：

```bash
python3 Eyes/scripts/iwencai_report_search.py "大族激光" -l 3 --date-tag 20260510
```

验证结果：成功返回国海证券 2026-05-07 研报《大族激光（002008）：公司动态研究：2026Q1业绩高速增长，消费电子+算力业务共振》，评级“买入”。

样例文件：

```bash
Eyes/研报搜索/2026-05/研报搜索_大族激光_2026-05-10.md
Eyes/研报搜索/Raw_Data/2026-05/report_search_大族激光_20260510.json
```

## 7. 后续集成点

- 稳定后接入 `SOP_Watchlist自动建档.md`，作为 A 股建档默认步骤。
- 已新增公告搜索/新闻搜索同级封装脚本；A 股调研统一形成：财务结构化事实层 + 公告事实层 + 研报叙事层 + 新闻事件层 + 价格事件层。
