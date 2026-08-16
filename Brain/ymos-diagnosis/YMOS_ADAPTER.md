# YMOS Diagnosis Adapter

> 只在用户已经确认结构诊断报告，并明确要求配置 YMOS 时使用。

## 输入

1. 已确认的 diagnosis 报告。
2. `Brain/策略配置/strategy-profile.schema.json`。
3. `Brain/策略配置/_模板_策略_Profile.md`。
4. 用户选择提供的现有状态与历史证据。

`持仓与关注/当前关注方向与投资偏好.md` 可以作为理解近期研究重点的上下文，但不是本 Adapter 的输出，也不能作为动作规则的替代真相源。

## 输出草案

生成四份互相一致的草案：

1. **Strategy Profile**：入场、失效、风险、期限、证据、节奏和 Human 门禁。
2. **驱动清单**：需要/可选/不需要的数据与 Skills，含失败降级。
3. **模块清单**：启用、停用、替换的 P/SOP/Agent/Console 能力。
4. **执行投影**：`Console/rules.json` 需要呈现的用户判断问题和红线。

规范草案路径：

- 已确认诊断：`Brain/内核审计/诊断记录/YYYY-MM/YYYY-MM-DD_结构诊断.md`
- 唯一运行 Profile：`Brain/策略配置/当前策略_Profile.md`
- 驱动清单：`Brain/策略配置/驱动清单.md`
- 模块清单：`Brain/策略配置/模块清单.md`
- 执行投影：`Console/rules.json`

## 映射规则

| 诊断结论 | YMOS 草案位置 |
|:---|:---|
| 策略范围 | `scope` |
| 入场逻辑 | `decision.entry` |
| 可证伪信号 | `decision.invalidation` |
| 加仓/退出一致性 | `decision.add / exit / conflictPolicy` |
| 风险与期限 | `risk` |
| 数据缺口 | `evidence` + 驱动清单 |
| 频率错配 | `cadence` |
| 执行偏离 | `execution.requiredGates` |
| 无用或冲突模块 | `modules.disabled / replacements` |

## 参数边界

- 诊断报告没有的数值保持 `null`。
- 不从作者案例、旧模板或模型常识中复制阈值。
- 用户必须亲自提供并确认仓位、止损、期限和频率参数。

## 一致性检查

提交给 Human 前检查：

- 每个入场判断是否有对应失效方式。
- 不同策略族混合时是否写明裁判优先级。
- 论点周期是否不超过资金可用期限。
- Console 门禁是否来自 Profile，而不是新增另一套策略。
- 停用模块是否仍被路由或文档引用。

## Human 确认

逐段展示草案。用户可以批准、修改、留空或驳回。只有明确批准后才允许：

- 生成/更新 `Brain/策略配置/当前策略_Profile.md`、`驱动清单.md` 与 `模块清单.md`。
- 生成/更新 `Console/rules.json`。
- 更新 Profile 的模块清单。

Adapter 不更新轻量关注文件。用户同时要求改变当前关注方向时，先完成本次 Profile 确认，再单独展示关注文件的变更草案并调用 `持仓与关注/SOP_关注方向维护.md`。

不要修改 P 系列或 SOP。若需要修改稳定内核，转到 `Brain/内核审计/_模板_判断层变更提案.md`。
