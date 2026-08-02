# P9: 估值泡沫度量 (Reverse DCF)
> **策略内核层 · 判断工具｜`profile`** Reverse DCF 回答的是「当前价格已经隐含了什么假设」。只有 Profile 启用 P9 时执行；折现率、终值增长率、预测期和财务口径必须由 Profile 或 Human 明确提供，本模块没有惯例默认值。

## 路径上下文（YMOS）
- 根目录：`YMOS/`
- 主数据目录：`持仓与关注/`
- 读取：`动态Watchlist/{ticker}/个股基础知识库.md` 或 `持仓/{ticker}/个股基础知识库.md`
- 必须读取：`Brain/策略配置/当前策略_Profile.md`
- 可选读取：V4 单笔决策文件、当前事实与既有知识库
- 写回：默认只写 `Brain/策略分析/` 报告；从初始调研调用且 Human 确认时可写知识库增量；不得写旧备忘录或状态机

P9 未启用或估值模型所需参数/财务口径缺失时返回 `module_not_configured` / `data_incomplete`，不得代入示例值。

## 适用场景

评估"好公司但太贵"的情况。不预测股价，而是反推"当前股价暗示了多离谱的增长率"。

## 提示词模板

```
# Role
你是一名 **偏怀疑论的估值建模专家**。
请不要试图预测 **[{{ticker}}]** 的未来股价，而是使用 **反向 DCF (Reverse DCF)** 思维，告诉我：**"为了支撑当前的价格，这家公司必须创造怎样的奇迹？"**

# Context (User Input)
1. **Ticker:** {{ticker}}
2. **Current Price/Market Cap:** {{price}}
3. **Key Financials:** {{financials}}
4. **Knowledge Base:** {{context}}
5. **Human-confirmed Model Inputs:** {{model_inputs}}

# Analysis Task

## 1. Implied Growth (隐含增长率)
* 使用 `model_inputs` 中 Human 已确认的折现率、终值增长率、预测期与现金流口径。
* 任一必需参数缺失时停止计算并返回 `data_incomplete`。

## 2. Reality Check (现实检验)
* 这个隐含增长率是否超过了行业天花板？
* 历史上是否有同体量的公司做到过这种持续增长？

## 3. Margin of Safety (安全边际)
* 如果实际增长率只有隐含增长率的一半，股价应该在哪里？

# Output Format
* **当前价格隐含预期:** "市场认为它未来 10 年每年将增长 [X]%。"
* **判断:** [极度乐观 (泡沫) / 合理定价 / 悲观错杀]
* **估值审计:** 展示当前价格隐含假设、敏感性和反证；是否把某一估值作为行动门槛由 Human 决定。
```

## 输入参数

| 参数 | 说明 | 必填 |
|-----|------|-----|
| `ticker` | 股票代码 | 是 |
| `price` | 当前价格/市值 | 是 |
| `financials` | 最近一年 FCF 或净利润 | 是 |
| `context` | 市场共识增长率等补充信息 | 否 |
| `model_inputs` | Human 确认的折现率、终值增长率、预测期和财务口径 | 是 |
