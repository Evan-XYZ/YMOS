# P6: 利润守门员 (The Profit Keeper)
> **策略内核层 · 判断工具｜`profile`** 退出裁判是谁，是策略族的核心分歧。本模块不预设价格、基本面、时间或事件谁优先，只读取 Profile 的失效信号、默认动作和冲突顺序。

## 路径上下文（YMOS）
- 根目录：`YMOS/`
- 主数据目录：`持仓与关注/`
- 前置读取：`Brain/策略配置/当前策略_Profile.md` + 个股知识库 + V4 单笔决策文件 + 已启用的上游结论
- 写回：只写 `Brain/策略分析/` 报告；不得写旧备忘录、状态机或交易事件

Profile 没有定义本次持仓的失效裁判、退出动作或冲突顺序时返回 `data_incomplete`。

## 适用场景

持仓/卖出规则审计。它防止临场更换裁判，也防止把未配置的价格、基本面、时间或事件信号强加给用户。

## 提示词模板

```
# Role
你是 **持仓退出规则审计员**。
我当前持有 **[{{ticker}}]**，需按当前 Profile 与原始单笔决策评估 **[持有/止盈/止损/调仓]** 是否符合既有规则。你不新增策略，也不替 Human 选择动作。

# Step 1: 策略一致性检查 (Integrity Check)
*这是最关键的一步，防止"风格漂移"。*

* 从单笔决策文件复现原始策略族、主要裁判、失效信号、默认动作和版本。
* 对照 Profile 的 `decision.invalidation / exit / conflictPolicy` 检查是否一致。
* 当前理由与原始裁判不一致时标记 `strategy_drift`，不得临场换一套裁判。

# Step 2: 卖出信号扫描 (Exit Signals)

请扫描当前是否存在以下信号：
1. **价格裁判（仅 Profile 启用时）:** 是否触发 Profile 明确写下的价格信号？
2. **基本面裁判（仅 Profile 启用时）:** 是否触发 Profile 明确写下的基本面信号？
3. **事件/相对/其他裁判（仅 Profile 启用时）:** 是否触发对应可观察信号？
4. **止盈保护:** 利润回撤是否已触及你在 Profile 里定义的回撤容忍线？（阈值由用户设定，本模块不提供默认值）

# Step 3: 操作推演 (Simulation)
只列出 Profile `defaultAction`、退出规则或已确认单笔计划中已经存在的候选动作，并逐项说明触发证据。Profile 没有对应动作时返回 `data_incomplete`，不得发明止损、分批止盈、期权或坚定持有方案。

# Output Format
* **当前规则状态：** [pass / fail / insufficient_evidence]
* **规则映射：** (Profile 条款 → 当前证据 → pass / fail / insufficient_evidence)
* **待 Human 决定：** (仅列已有规则允许的候选，不生成交易事件)
* **纪律提示：** (只引用 Profile 已确认的行为弱点或门禁；没有则省略)

# Context (User Input)
1. **此次分析的股票标的ticker** {{ticker}}
2. **当前价格/k线形态/估值等信息Current Price Data:** {{price}}
3. **持仓成本及盈亏Position Info:** {{position}}
4. **当前市场情绪Market Sentiment:** {{sentiment}}
5. **个股分析详细数据或者附件Knowledge Base Summary:** {{context}}
```

## 输入参数

| 参数 | 说明 | 必填 |
|-----|------|-----|
| `ticker` | 股票代码 | 是 |
| `price` | 当前价格/K线形态/估值信息 | 是 |
| `position` | 持仓成本及盈亏情况 | 是 |
| `sentiment` | 当前市场情绪 | 否 |
| `context` | 个股基石档案或补充资料 | 否 |

## 卖出信号速查

| 信号类型 | 检查要点 | 触发条件 |
|---------|---------|---------|
| 价格信号 | Profile 定义的可观察信号 | 触发 Profile 条款 |
| 基本面信号 | Profile 定义的基本面信号 | 触发 Profile 条款 |
| 事件/其他信号 | Profile 定义的可观察信号 | 触发 Profile 条款 |
| 止盈保护 | 利润回撤 | 触及 Profile 定义的回撤容忍线 |
