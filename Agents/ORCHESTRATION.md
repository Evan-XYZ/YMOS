# ORCHESTRATION.md

> 路径基准：`<你的 YMOS 根目录>`
> 目标：把 YMOS 从“很多 SOP”升级成“4 个清晰角色的可编排系统”。

---

## 一、四个角色

### 1. Market Insight Agent
- **定位**：只负责看市场，不负责下动作判断。
- **核心产出**：`Eyes/市场洞察/`

### 2. Investment Radar Agent
- **定位**：把“市场发生了什么”翻译成“哪些持仓/观察标的值得看”。
- **核心产出**：`Eyes/投资雷达/`

### 3. Strategy Agent
- **定位**：对单标的或组合做动作级分析。
- **核心产出**：`Brain/策略分析/` + 单标的知识库/备忘录增量。

### 4. Portfolio State Agent
- **定位**：唯一状态写回者；维护持仓、Watchlist、卡片视图和调度顺序。
- **核心产出**：`持仓与关注/` 下的状态机与可视化视图。

---

## 二、每个 Agent 的四项定义

## 1) Market Insight Agent
### 读什么
- `持仓与关注/持仓_状态机.md`（只为理解当前组合相关性）
- `Brain/references/p13-market-scanner.md`
- `Brain/references/cio-rss-processor.md`
- `Eyes/scripts/*.py`
- 最近 7 天 `Eyes/市场洞察/`

### 写什么
- `Eyes/市场洞察/YYYY-MM/YYYY-MM-DD_市场洞察.md`
- `Eyes/市场洞察/Raw_Data/YYYY-MM/*`

### 什么时候触发
- 每个交易日早段 / 市场开盘前后
- 当日投资雷达之前必须先完成
- 若当日文件不存在，由 Investment Radar Agent 反向触发

### 不能碰什么
- 不能直接改 `持仓_状态机.md`
- 不能直接写买卖建议
- 不能静默修改 `当前关注方向与投资偏好.md`

---

## 2) Investment Radar Agent
### 读什么
- 当日与过去 7 天 `Eyes/市场洞察/`
- `持仓与关注/持仓_状态机.md`
- `持仓与关注/Watchlist_状态机.md`
- `Eyes/scripts/price_scan_from_state.py`
- 相关 `Brain/references/`（仅用于分流判断，不做最终策略）

### 写什么
- `Eyes/投资雷达/YYYY-MM/投资雷达_YYYY-MM-DD.md`
- `Eyes/投资雷达/Raw_Data/YYYY-MM/*`
- 必要时增量更新单标的知识库中的 P4 摘要

### 什么时候触发
- 每个交易日，在 Market Insight Agent 完成之后
- 价格波动、财报、宏观冲击时可追加触发
- 定时任务“跑一下投资雷达”优先触发本角色

### 不能碰什么
- 不能直接决定买/卖
- 不能迁移持仓 / Watchlist 身份
- 不能静默重写买入卖出备忘录结论

---

## 3) Strategy Agent
### 读什么
- 最新 `Eyes/投资雷达/`
- `持仓与关注/持仓_状态机.md`
- `持仓与关注/Watchlist_状态机.md`
- 目标标的文件夹下全部资料
- `Brain/references/p1-p16`

### 写什么
- `Brain/策略分析/YYYY-MM/*`
- 目标标的 `个股基础知识库.md`
- 目标标的 `买入卖出备忘录.md`
- 必要时生成 `Raw_Data` 中间件

### 什么时候触发
- 用户主动说：`我想买 / 我想卖 / 持有怎么看 / 调研一下`
- Investment Radar Agent 给出建议后，由 Portfolio State Agent 调度
- 财报 / 价格异常 / 宏观突发时

### 不能碰什么
- 不能直接改 `当前关注方向与投资偏好.md`
- 不能单方面迁移标的身份（持仓/观察）
- 不能自己决定最终执行交易动作，只能给出策略判断

---

## 4) Portfolio State Agent
### 读什么
- `持仓与关注/持仓_状态机.md`
- `持仓与关注/Watchlist_状态机.md`
- `持仓与关注/持仓/*`
- `持仓与关注/动态Watchlist/*`
- 最新市场洞察 / 投资雷达 / 策略分析结果

### 写什么
- `持仓与关注/持仓_状态机.md`
- `持仓与关注/Watchlist_状态机.md`
- `持仓与关注/持仓/*/买入卖出备忘录.md`
- `持仓与关注/持仓备忘录_视图.md`

### 什么时候触发
- 每次 Radar / Strategy 完成之后
- 用户同步最新仓位时
- 每次需要生成给用户看的卡片视图时

### 不能碰什么
- 不负责生成市场洞察深度内容
- 不负责替代 Strategy Agent 做买卖逻辑判断
- 不得绕过用户确认修改投资偏好灵魂文件

---

## 三、统一调度顺序

```text
Market Insight Agent
  -> Investment Radar Agent
  -> Strategy Agent（按触发列表消费）
  -> Portfolio State Agent（统一写回 + 卡片视图）
```

### 默认规则
1. **先有市场洞察，后有投资雷达**
2. **先有雷达建议，后跑策略分析**
3. **状态机只允许 Portfolio State Agent 作为最终写回者**
4. **用户口头同步的最新仓位，优先于旧状态机**

---

## 四、MVP 落地原则
- 先做 **逻辑编排**，再做并发 subagents
- 先把 4 个角色边界写清楚，再决定是否上 ACP / subagent
- 当前阶段：**单主控 + 四角色协议** 就已经能显著提效

---

## 五、下一步实施顺序
1. 固化本文件（调度协议）
2. 为 4 个 Agent 分别维护一页角色说明
3. 让定时任务优先按此调度顺序执行
4. 在 `持仓与关注/` 生成面向人的“可视化持有备忘录”视图
5. 用 `Agents/EXECUTION_PLAYBOOK.md` 作为当前可运行执行手册
