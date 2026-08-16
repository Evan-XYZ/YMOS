# YMOS Agent Execution Playbook

## 通用运行前检查

每个角色在运行前记录：角色、触发原因、输入路径、输入版本、数据截至时间、允许写入路径和成功条件。唯一 Profile 路径是 `Brain/策略配置/当前策略_Profile.md`。Profile 缺失或为 `draft` 不阻塞 Market Insight、Investment Radar 和基础事实调研；它只阻塞动作级结论。关键事实缺失时停止，不使用示例值补齐。

## Market Insight

1. 核验来源、市场日历、币种、数据时间与缺口。
2. 分开记录事实、解释和未知。
3. 生成市场洞察及必要的 Raw Data 索引。
4. 不改组合状态，不输出交易动作。

成功：产物非空、来源和时间完整、缺失项显式标记。

## Investment Radar

1. 先确定 `balanced / price / event` 模式，并按模式核验最小输入；局部上游缺失只降级。
2. 读取可用的市场洞察、A/美股热门观察、最新持仓/Watchlist 与价格/事件数据；过期输入标记 stale。
3. 说明哪些变化与哪些对象相关，并生成去重分析队列。
4. Profile 缺失或 draft 只关闭策略增强，不关闭价格、事件和热门报告收敛。
5. 不把相关性直接翻译为买卖指令。

成功：每个触发项均能追溯上游证据，且有下一步分析类型。

## Strategy

1. 读取当前 Strategy Profile、目标档案和买卖决策状态。
2. 复现原论点、失效信号、退出规则和版本。
3. 先检查 `modules.enabled / disabled / replacements`，再运行适用的 P 系列审计；停用项不读、替换项改读替代模块，缺失条件返回 `data_incomplete`。
4. 输出结论、证据、反证、风险和待 Human 决定事项。
5. 不静默修改 Profile 或状态身份。

成功：结论可证伪、规则来源明确、没有公共默认参数。

Profile 不存在、仍为 `draft` 或未获 Human 批准时，允许完成事实整理与研究缺口清单；买卖、持有、加仓、退出、衍生品和再平衡请求返回 `kernel_not_ready`。

## Portfolio State

1. 重新读取最新状态并检查版本冲突。
2. 消费 Human 已确认的账户变动、交易动作和行情快照。
3. 更新 `持仓与关注/持仓_状态机.md`、`Watchlist_状态机.md` 以及 `Brain/买入卖出决策/` 中对应状态。
4. 记录更新时间、来源、旧值、新值、原因和操作者。
5. 保存后重读并验证派生汇总；不得依赖用户手工刷新。

成功：组合数量、币种、现金、持仓市值与决策状态能够互相核对；旧行情被正确标记。

## 异常处理

- `data_incomplete`：列出缺失字段，不继续推断。
- `stale_input`：保留旧值供展示，但禁止描述为实时。
- `version_conflict`：停止写回，重读并请求 Human 处理冲突。
- `blocked_by_dependency`：记录失败的上游任务和最后有效版本。
- `no_change`：正常结束，并写明已检查的范围。
