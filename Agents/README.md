# YMOS Agents — 跨层运行时编排协议

> 三层说明 YMOS 有哪些能力；`Agents/` 说明 Agent 宿主怎样按顺序、安全地调用这些能力。

V3 主要靠“暗号 → SOP”运行。它能用，但角色容易混在一起，顺序和写权限也主要依赖当前会话记得多少。V4 保留 SOP，同时增加四张角色卡和一条依赖链，固定三件事：**谁来做、先读什么、能写哪里**。

`Agents/` 因此不是独立的第四个业务层，也不是四个常驻机器人。它是 Hermes、Claude Code、Codex、OpenClaw 或其他 Agent 宿主可以读取的 Markdown 运行协议。

## 它什么时候才算真正启用？

这些文件不会自动运行。真正的执行链是：

```text
Human 或定时任务触发
  → 主控读取对应角色卡
  → 读取 EXECUTION_PLAYBOOK 的角色段落
  → 读取本次具体 SOP
  → 核验上游和数据时间
  → 调用脚本 / Skill / 文件工具
  → 只在角色权限内落盘
  → 按成功或失败语义结束
```

只有任务提示词同时指定**工作目录、角色卡、Playbook、具体 SOP、成功标准**时，Agents 协议才算完整激活。只写“你是 Investment Radar Agent”只是改了任务名；只让 Agent 读 SOP，则工作流会执行，但角色边界主要仍靠 SOP 自己维持。

默认采用 **Single Controller / Multi-Role**：一个统筹 Agent 按依赖顺序扮演四个角色。宿主支持子 Agent 时可以拆开执行，但所有角色仍共享同一套文件真相源和写回规则。

## 四个角色怎样接上现有 SOP？

| 角色 | 服务位置 | 默认入口 | 主要产出 | 是否自动进入下一环 |
|:---|:---|:---|:---|:---|
| **Market Insight** | 投研层 | `Eyes/SOP_市场洞察.md` | `Eyes/市场洞察/` | 可触发 Radar，但必须先通过成功判定 |
| **Investment Radar** | 投研层汇总 → 可选内核路由 | `Eyes/SOP_投资雷达.md` | `Eyes/投资雷达/`、待分析队列 | `balanced / price / event` 均不要求 Profile；不自动给出买卖动作 |
| **Strategy** | 策略内核层 | `Brain/SOP_策略分析.md`；按需进入初始调研或 P 链 | `Brain/策略分析/`、待 Human 决定事项 | 不自动写真实持仓或成交 |
| **Portfolio State** | 内核记忆 ↔ 操盘层 | 依据触发选择“持仓日常体检”“标的管理”或买卖决策数据契约 | 已确认的身份状态、组合快照与变更日志 | 不创造新论点，不替 Human 成交 |

Portfolio State 没有一份包办所有情况的万能 SOP：

- 扫账户敞口、判断是否需要深入分析 → `持仓与关注/SOP_持仓日常体检.md`，默认只读。
- Human 明确要求关注、建档、移除或身份迁移 → `持仓与关注/SOP_标的管理.md`。
- Human 在买卖决策台确认真实动作 → 遵守 `Console/TRADE_DATA_CONTRACT.md` 与 `Brain/买入卖出决策/README.md`，由本地服务形成 append-only 事件。

旧版本中的 `持仓与关注/SOP_持仓收口.md`、`持仓备忘录_视图.md` 和 dashboard 路径已经退出 V4。旧定时任务如果仍引用这些文件，必须迁移，不能把任务名称正常当成链路可用。

## 两条硬规则

### 1. 依赖不能假装成功

```text
Market Insight → Investment Radar → Strategy（仅明确触发项）
                                      ↓
                              Human 确认或事实变动
                                      ↓
                              Portfolio State 写回
```

日常不要求每次跑完整链。市场洞察和投资雷达可以独立形成投研主链；没有明确研究队列时 Strategy 返回 `no_change`；没有 Human 确认或状态变化时 Portfolio State 不写任何事实。只有当前模式的**最小必需输入**失败时才返回 `blocked_by_dependency`；局部事件源或报告缺失应显式降级，不得用旧产物冒充当日产物。

### 2. Agent 状态写回只有一个出口

只有 Portfolio State 角色可以代表 Agent 修改最终状态。Market Insight、Radar 和 Strategy 再确信，也只能提出建议。Human 通过 Console 确认的真实成交与资金事件属于事实来源，不是 Agent 越权。

## 最小可运行提示词

```text
工作目录：<你的 YMOS 根目录>
你现在承担 Market Insight Agent 角色。
先读取 Agents/market-insight-agent.md，
再读取 Agents/EXECUTION_PLAYBOOK.md 的 Market Insight 段落，
最后读取 Eyes/SOP_市场洞察.md 并执行。
只写角色允许的目录；通过 SOP 成功判定后才结束。
失败时返回 data_incomplete、stale_input 或具体错误，不静默跳过。
```

把角色卡和 SOP 换成 `investment-radar-agent.md` + `Eyes/SOP_投资雷达.md`，即可配置雷达任务。Strategy 和 Portfolio State 的精确入口见 `ORCHESTRATION.md`；不要让定时任务凭角色名猜 SOP。

## 三步验证它是否真的可用

1. **角色加载测试**：让宿主复述当前角色的允许写入与禁止动作；答不出说明角色卡没有被读取。
2. **模式依赖测试**：分别运行 `balanced / price / event`。局部报告缺失应降级；只有所选模式的最小输入也不存在时才返回 `blocked_by_dependency`，而不是拿旧报告继续。
3. **写回边界测试**：在没有 Human 确认的情况下要求 Strategy 改持仓；正确结果应是拒绝写回，并把事项交给 Human / Portfolio State。

这三步通过，说明角色、依赖和权限协议已经生效；它验证的是运行编排，不代表外部数据源、模型结论或真实交易本身一定正确。

## 文件导航

| 文件 | 用途 |
|:---|:---|
| `ORCHESTRATION.md` | 技术依赖图、角色 → SOP → 产出映射、真相源与失败处理 |
| `EXECUTION_PLAYBOOK.md` | 每个角色的运行检查、标准动作和成功条件 |
| `RUNTIME_MODE.md` | 单主控与多 Agent 的映射方式 |
| `SCHEDULES.md` | 不绑定个人时间的调度依赖合同 |
| `SCHEDULES_REFERENCE.md` | 实际使用过的时间安排、踩坑约束与停用原则 |
| `*-agent.md` | 给宿主快速加载的四张角色卡 |

更上层的三层定义见 `../ARCHITECTURE.md`；宿主权限和新会话规则见 `../AGENT_GUIDE.md`。

---

*YMOS V4 · 模型可换，文件真相源与角色协议不变*
