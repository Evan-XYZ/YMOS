# YMOS 调度依赖

本文件只描述依赖，不提供作者个人市场、时区或作息参数。用户应按自己的市场日历和数据可用时间配置宿主调度器。

```text
市场数据可用
  → Market Insight
  → Investment Radar
  → Strategy（仅处理明确触发项）
  → Human 确认 / 账户事实变化
  → Portfolio State（统一 Agent 写回）
```

## 任务契约

每个定时任务必须声明：

- YMOS 工作目录；
- 使用的角色卡、`EXECUTION_PLAYBOOK.md` 章节与具体 SOP；
- 上游成功标记或文件；
- 输入数据的最大允许陈旧度；
- 唯一允许写入的目录；
- 幂等键（通常是市场、交易日、任务名）；
- 失败、重试与“无变化”的记录方式。

## 依赖规则

1. Market Insight 只在关键驱动数据齐备后运行。
2. Investment Radar 必须引用一份已完成且时间有效的市场洞察。
3. Strategy 只处理 Human 点名或 Radar 明确列入审阅队列的对象；不建议无差别每日全量运行。
4. Portfolio State 只消费已落盘且已确认的事实，并在写回前重新读取最新状态，避免覆盖并发修改。
5. 任一上游失败时，下游返回 `blocked_by_dependency`，不得拿旧产物冒充今日产物。
6. 没有触发项返回 `no_change`，不为了让任务“有产出”而制造结论或状态变化。

## 可直接改路径使用的任务文案

### Market Insight

```text
工作目录：<你的 YMOS 根目录>
先读取 Agents/market-insight-agent.md，
再读取 Agents/EXECUTION_PLAYBOOK.md 的 Market Insight 段落，
最后执行 Eyes/SOP_市场洞察.md。
只写 Eyes/市场洞察/；按 SOP 校验日期、结构与来源后才算成功。
```

### Investment Radar

```text
工作目录：<你的 YMOS 根目录>
先读取 Agents/investment-radar-agent.md，
再读取 Agents/EXECUTION_PLAYBOOK.md 的 Investment Radar 段落，
最后执行 Eyes/SOP_投资雷达.md。
先核验当日市场洞察；无有效上游则返回 blocked_by_dependency。
只写 Eyes/投资雷达/，不得迁移标的身份或输出已执行动作。
```

### Strategy

```text
工作目录：<你的 YMOS 根目录>
先读取 Agents/strategy-agent.md，
再读取 Agents/EXECUTION_PLAYBOOK.md 的 Strategy 段落，
最后执行 Brain/SOP_策略分析.md。
只处理 Human 点名或最新 Radar 明确列入队列的对象；没有对象返回 no_change。
不静默修改 Profile，不写真实成交和资金事实。
```

### Portfolio State

Portfolio State 不应绑定一个“万能收口 SOP”。按任务目的三选一：

```text
账户体检：portfolio-state-agent.md + EXECUTION_PLAYBOOK + SOP_持仓日常体检.md
标的身份：portfolio-state-agent.md + EXECUTION_PLAYBOOK + SOP_标的管理.md
真实动作：由 Human 在 Console 确认，遵守 TRADE_DATA_CONTRACT.md
```

旧任务如果仍引用 `SOP_持仓收口.md`、`持仓备忘录_视图.md` 或 dashboard 刷新，应先迁移后再启用。

具体时间安排、停用原则与踩坑记录见 `SCHEDULES_REFERENCE.md`。公开仓库不自动注册任务，也不分发真实账户、通知渠道或作者宿主配置。
