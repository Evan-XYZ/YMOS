# 我的策略 Profile

> 状态：草稿
> 本文件描述“我怎样判断”，不保存账户、持仓和行情。
> 所有内容必须由用户确认；Agent 只能整理、检查矛盾和提出候选写法。
> Human 批准后，本模板的运行副本固定保存为 `Brain/策略配置/当前策略_Profile.md`；不要创建多个无法判断优先级的“当前版”。
> 这是一份首次入职的安全草稿骨架，不是通用投资策略。空数组和 `null` 表示“尚未决定”，不得为了消除提示而自动填入作者或模型参数。

## 0. 入职进度

- 当前可继续使用：市场洞察、投资雷达、Reader、基础事实调研
- 激活动作判断前仍需确认：
  - [ ] 市场、工具、能力圈与明确排除项
  - [ ] 入场证据与不可单独触发动作的辅助证据
  - [ ] 可观察的失效信号与默认动作
  - [ ] 仓位、损失预算、论点周期与资金期限
  - [ ] 加仓、减仓与退出规则
  - [ ] 模块、节奏与 Human 门禁

> 未勾完时保持 `draft`。动作级请求出现 `kernel_not_ready` 是配置提醒，不影响投研层运行。

## 1. 策略一句话

- 我处理什么市场、什么类型的机会：
- 我的主要优势或能力圈：
- 我明确不做什么：

## 2. 入场逻辑

- 一笔机会成立必须有哪些证据：
- 哪些只是辅助证据，不能单独触发动作：
- 什么情况下即使看好也不行动：

## 3. 可证伪与退出

| 论点 | 可观察的失效信号 | 信号出现后的默认动作 |
|:---|:---|:---|
|  |  |  |

## 4. 仓位、风险与期限

- 仓位计算口径：
- 单笔上限：由用户填写
- 单笔损失预算：由用户填写
- 论点兑现周期：由用户填写
- 资金可用期限：由用户填写
- 组合级限制：

## 5. 加仓与减仓

- 什么情况下允许加仓：
- 什么情况下禁止加仓：
- 什么情况下减仓但不否定原论点：
- 什么情况下必须退出：

## 6. 证据与节奏

- 必须使用的事实源：
- 信源优先级：
- 日常监控频率：
- 允许形成新判断的时间窗口：
- 周期复核频率：

## 7. Human 门禁

- 哪些步骤必须由 Human 确认：
- 盘中禁止临时修改什么：
- 哪些情况必须暂停并重新审计：

## 8. 模块清单

- 启用：
- 停用：
- 替换：

## 9. 机器接口

<!-- ymos-strategy-profile：复制模板后填写；null 表示用户尚未决定，不得由系统补默认值。 -->
```json
{
  "schemaVersion": 1,
  "profileId": "user-profile",
  "name": "我的策略",
  "status": "draft",
  "strategyFamilies": [],
  "scope": {
    "markets": [],
    "instruments": [],
    "abilityCircle": [],
    "excluded": []
  },
  "decision": {
    "entry": { "questions": [], "requiredEvidence": [], "redlines": [] },
    "invalidation": { "judgeTypes": [], "signals": [], "defaultAction": "" },
    "add": { "questions": [], "requiredEvidence": [], "redlines": [] },
    "exit": { "questions": [], "requiredEvidence": [], "redlines": [] },
    "conflictPolicy": ""
  },
  "risk": {
    "sizingBasis": "custom",
    "positionLimitPct": null,
    "lossBudgetPct": null,
    "thesisHorizonMonths": null,
    "fundAvailabilityMonths": null,
    "portfolioConstraints": []
  },
  "evidence": {
    "requiredSources": [],
    "sourcePriority": [],
    "freshnessRules": []
  },
  "cadence": { "monitor": "", "decisionWindow": "", "review": "" },
  "execution": {
    "humanConfirmation": true,
    "decisionExecutionSeparated": true,
    "requiredGates": [],
    "allowedDecisionWindows": []
  },
  "modules": { "enabled": [], "disabled": [], "replacements": {} },
  "meta": { "createdAt": "", "updatedAt": "", "approvedByHuman": false, "sourceDiagnosis": "" }
}
```
