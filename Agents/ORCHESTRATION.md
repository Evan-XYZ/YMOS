# YMOS 角色编排协议

> 三层是业务架构；本文件是跨层运行合同。默认由一个主控顺序扮演角色，不依赖任何宿主专有的多 Agent 接口。

## 1. 运行关系

```text
数据源 / Skills
  → Market Insight（事实压缩）
  → Investment Radar（与持仓、关注的相关性）
  → Strategy（只消费明确研究队列或 Human 指令）
  → Human 确认
  → Portfolio State（唯一 Agent 状态写回出口）
  → Reader / 交易计划台 / 买卖决策台
  → 复盘证据与 BrainStorm
```

这不是每次必须全部运行的流水线：

- 日常投研主链通常只运行 Market Insight → Investment Radar。
- Strategy 没有明确触发项时返回 `no_change`。
- Portfolio State 没有 Human 确认、账户事实变化或体检请求时不写状态。
- Console 是 Human 交互与文件投影，不负责调用 Agents，也不是 Agent 调度器。

## 2. 可执行映射

| 角色 | 角色卡 | 本次任务必须再读 | 前置依赖 | 允许产出 |
|:---|:---|:---|:---|:---|
| Market Insight | `market-insight-agent.md` | `Eyes/SOP_市场洞察.md` | 需要的数据源与市场时间已就绪 | `Eyes/市场洞察/` 与其 Raw Data |
| Investment Radar | `investment-radar-agent.md` | `Eyes/SOP_投资雷达.md` | 按模式核验：`balanced/event` 优先用有效洞察与热门报告，`price` 需要真实 ticker 与价格路由；Profile 可选 | `Eyes/投资雷达/` 与待分析队列 |
| Strategy | `strategy-agent.md` | `Brain/SOP_策略分析.md`；专项任务再读对应调研 SOP / 已启用 P 模块 | Human 点名或 Radar 明确列入队列；事实调研允许 draft，动作结论要求 active + Human 批准 | `Brain/策略分析/`、可追溯知识库增量、待 Human 决定事项 |
| Portfolio State：体检 | `portfolio-state-agent.md` | `持仓与关注/SOP_持仓日常体检.md` | 组合快照存在；过期则标 stale | 默认只输出体检，不改交易事实 |
| Portfolio State：身份 | `portfolio-state-agent.md` | `持仓与关注/SOP_标的管理.md` | Human 明确指令与必要前置研究 | 持仓 / Watchlist 身份状态和变更日志 |
| Portfolio State：真实动作 | `portfolio-state-agent.md` | `Console/TRADE_DATA_CONTRACT.md`、`Brain/买入卖出决策/README.md` | Human 在 Console 明确确认 | 本地服务追加的单笔事件与派生组合快照 |

所有角色还必须读取 `EXECUTION_PLAYBOOK.md` 中对应段落。任务提示词如果没有明确角色卡和具体 SOP，不视为完整启用本协议。

## 3. 读写边界

| 角色 | 读取 | 写入 | 禁止 |
|:---|:---|:---|:---|
| Market Insight | 驱动数据、历史洞察、只读组合摘要 | 市场洞察与原始数据 | 修改持仓、给出交易指令 |
| Investment Radar | 有效市场洞察、组合快照、观察状态 | 雷达报告与分析队列 | 迁移身份、改写决策结论 |
| Strategy | Profile、标的档案、决策状态、雷达触发 | 策略报告与明确的单标的增量 | 静默改 Profile、自动执行交易 |
| Portfolio State | 已确认动作、决策文件、账户与行情快照 | 明确授权的身份状态、组合快照与变更日志 | 创造新论点、替代 Human 确认、改写历史事件 |

“Portfolio State 是唯一写回者”限定的是 **Agent 产生的最终状态变更**。Human 通过 Console 形成的真实确认和成交事件是事实来源；Console 本地服务可依照数据契约写盘，但任何 Agent 都不能伪造这类事件。

## 4. 真相源优先级

1. Human 明确确认并由真实操作产生的事实事件；
2. 最新、已确认的 Strategy Profile 与单笔买卖决策文件；
3. 持仓 / Watchlist 身份状态；
4. 带来源和时间戳的组合快照；
5. 派生报告与可视化；
6. 未确认的 Agent 建议。

快照与单笔文件冲突时，以单笔文件为事实源并要求刷新快照。Human 的口头修正只有在完成确认和留痕后，才替代旧文件成为持久真相源。

## 5. 并发与失败

- 写回前使用版本号或内容哈希进行乐观校验；发现变化则停止并重算。
- 数据缺失返回 `data_incomplete`，输入过期返回 `stale_input`。
- 只有所选模式的最小必需输入失败时返回 `blocked_by_dependency`，并记录失败输入与最后有效版本；局部上游缺失写明降级模式。
- “没有触发事项”是成功结果，返回 `no_change`。
- 冲突不能靠最后写入者覆盖；必须进入 Human 审阅。
- 禁止把“文件存在”当成功；必须同时检查日期、结构和 SOP 成功条件。

## 6. 旧任务迁移守卫

旧自用链曾使用 `持仓与关注/SOP_持仓收口.md`、`持仓备忘录_视图.md` 与 dashboard 刷新。这些路径已退出 V4。迁移旧任务时：

1. 市场洞察与投资雷达任务补上角色卡 + Playbook + SOP。
2. Strategy 从“每天全量跑”改为只处理明确触发项。
3. Portfolio State 按触发类型选择体检、标的管理或真实动作数据契约。
4. Reader / Console 直接读取新的 Markdown 真相源，不再生成第二份持仓视图。

## 7. 内核变化

任何跨案例的规则变化都先进入 `Brain/内核审计/_模板_判断层变更提案.md`，经 Human 批准后才更新 Profile。角色编排本身不能绕过这一流程。

---

*YMOS V4 · Agents 跨层运行合同*
