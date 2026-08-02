# 🩺 持仓日常体检 SOP

> 暗号：`检查一下持仓` / `扫一下账户敞口` / `跑一下持仓体检`
> 数据入口：`Brain/买入卖出决策/买卖决策_状态机.md`

---

## 一句话定位

让 Agent 像 Human 打开买卖决策台的「持仓总览」一样，先扫账户敞口、盈亏和结构异常，再决定是否需要打开单笔交易文件或运行 P 系列提示词。

这是一条**读取与分析流程**，不授权 Agent 自动交易。

---

## Step 1：读取账户状态机

读取：

```
Brain/买入卖出决策/买卖决策_状态机.md
```

优先解析 `ymos-trade-account` JSON 中的：

```
portfolioSnapshot.asOf
portfolioSnapshot.accounts
portfolioSnapshot.positions
portfolioSnapshot.health
portfolioSnapshot.agentRouting
```

数据边界：

- 单笔交易 Markdown 是持仓股数、成本、论点和退出规则的事实源。
- `portfolioSnapshot` 是最近一次行情刷新时生成的派生视图，不是第二套持仓账本。
- 如果快照不存在、`asOf` 明显过期或行情覆盖不足，不得把成本口径冒充实时市值；提示 Human 去买卖决策台刷新行情。

---

## Step 2：先扫账户级敞口

逐币种输出：

- 资金基数、账户净值。
- 持仓成本、持仓市值、浮动与已实现盈亏。
- 待建计划、剩余可开金额。
- 持仓数量与行情覆盖数量。

若账户级口径与单笔明细加总不一致，标记为“状态待刷新”，不要自行修改交易文件。

---

## Step 3：读取结构体检

先看 `portfolioSnapshot.health.status`：

| 状态 | 含义 | 动作 |
|---|---|---|
| `critical` | 止损已破、仓位超限、期限错配或出局权外生 | 优先处理 alerts；打开对应 `sourceFile` |
| `attention` | 临近止损、逻辑退出待复核、跳过冷却期 | 列入当日复核 |
| `normal` | 当前数据没有发现可计算异常 | 只输出简报，不强行制造任务 |

逐条读取 `health.alerts`，保留：`severity`、`type`、`ticker`、`message`、`suggestedPrompts`、`file`。

---

## Step 4：按告警路由分析

| 告警类型 | 建议流程 |
|---|---|
| `stop_breached` | 打开单笔文件，核对失效信号与退出动作；重跑 P2 → P6 → P12 |
| `near_stop` | 重跑 P6 → P12；确认是继续持有、减仓还是执行原规则 |
| `logic_exit_review` | 对照 `invalidationSignal` 与最新事实；重跑 P2 → P6 |
| `position_limit_exceeded` | 跑 P7 → P12，检查组合敞口与纪律 |
| `horizon_mismatch` | 跑 P6 → P7 → P12，检查资金期限是否能承载论点 |
| `external_exit_control` | 跑 P6 → P12，恢复自主退出权 |
| `cooldown_skipped` | 记录为纪律样本；组合级跑 P7 / P12 |

`suggestedPrompts` 只是分析路由，不是交易指令。任何买卖动作仍须 Human 确认并回到买卖决策台执行。

---

## Step 5：按需打开单笔文件

只有下列情况才继续读取 `health.alerts[].file`：

- 告警需要核对原始论点、失效信号或退出动作。
- Agent 需要判断快照是否与最新交易事件一致。
- Human 指定某个持仓做深入分析。

无告警时不要把所有单笔文件全部塞进上下文。

---

## 输出模板

```markdown
# 持仓日常体检｜YYYY-MM-DD HH:mm

- 快照时间：
- 行情覆盖：
- 总体状态：normal / attention / critical

## 账户敞口
| 账户 | 净值 | 持仓市值 | 浮动盈亏 | 剩余可开 |
|---|---:|---:|---:|---:|

## 需要处理
1. [级别] TICKER｜告警｜建议 P 路由｜源文件

## 当前无需处理
- ...

## 数据质量
- 快照是否新鲜：
- 缺价标的：
- 是否需要 Human 刷新买卖决策台：
```

---

## 硬边界

1. 不把快照当实时行情；必须显示 `asOf`。
2. 不因 Agent 建议自动买卖。
3. 不直接改写单笔交易历史。
4. 发现快照与单笔文件冲突时，以单笔文件为事实源，并要求刷新快照。
5. 无告警不等于方向正确，只代表当前结构化数据没有触发已定义的红线。
