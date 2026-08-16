# Route Cheatsheet（暗号 → 模块 → 提示词 → 写回）

> 一页速查：先判触发类型，再按 Watchlist / 持仓分流。
> 完整暗号表见 `总入口暗号.md`，各 SOP 见 `Eyes/SOP_*.md` 和 `Brain/SOP_*.md`。

---

## 0) 通用前置

执行策略前必须确认：
1. 已读取 `个股基础知识库.md`
2. 已读取唯一 Profile：`Brain/策略配置/当前策略_Profile.md`
3. 已读取对应 V4 单笔决策文件（若存在）
4. 已检查 `modules.enabled / disabled / replacements`
5. 只运行 Profile 允许的模块；最终纪律裁判只引用 Profile 红线

Profile 为 `draft` 时允许市场洞察、雷达和事实调研；动作级路由返回 `kernel_not_ready`。

---

## 1) 市场扫描入口

| 暗号 | SOP | 提示词 | 写回 |
|:---|:---|:---|:---|
| `跑一下市场洞察` | `Eyes/SOP_市场洞察.md` | CIO + P13（+ P14 按需） | `Eyes/市场洞察/YYYY-MM/` |
| `跑一下投资雷达` | `Eyes/SOP_投资雷达.md` | balanced：市场/热门/价格/事件；也可切 price 或 event | `Eyes/投资雷达/YYYY-MM/`；身份变化需 Human/Portfolio State |
| `查一下价格` | `Eyes/scripts/fetch_price_router_v2.py` | Finnhub/Tushare/Yahoo 价格路由（失败回落问财） | `Eyes/投资雷达/YYYY-MM/Raw_Data/` |

---

## 2) Watchlist 分流（目标：建仓机会）

| 触发 | 模块链路 | 提示词顺序 | 写回 |
|:---|:---|:---|:---|
| 价格触发 | Eyes → Brain | Quotes → 按 Profile 路由已启用/替换模块 | `Brain/策略分析/`；身份与事件需 Human/Portfolio State |
| 事件触发 | Eyes → Brain | 事件事实 → 按 Profile 路由已启用/替换模块 | 同上 |
| 宏观触发 | Eyes → Brain | 宏观事实 → 仅在 Profile 启用时进入对应模块 | 同上 |

---

## 3) 持仓分流（目标：加仓/持有/卖出）

| 触发 | 模块链路 | 提示词顺序 | 写回 |
|:---|:---|:---|:---|
| 价格触发 | Eyes → Brain | Quotes → 按 Profile 路由退出审计与最终裁判 | `Brain/策略分析/`；不得直接写状态或交易事件 |
| 事件触发 | Eyes → Brain | 事件事实 → 按 Profile 路由已启用/替换模块 | 同上 |
| 宏观触发 | Eyes → Brain | 宏观事实 → 仅在 Profile 启用时进入对应模块 | 同上 |

---

## 4) 人工意图直达

| 暗号 | SOP | 提示词 | 写回 |
|:---|:---|:---|:---|
| `调研一下 [股票]` | `Brain/SOP_初始调研.md` | P1 → P4（P2/P9 仅按 Profile 启用） | 已批准建档则写知识库；否则写 `Eyes/投资雷达/YYYY-MM/` |
| `我想买 [股票]` | `Brain/SOP_策略分析.md` | 按 Profile 模块清单解析首次买入链 | `Brain/策略分析/`；Human 决定后进入 Console |
| `我想卖 [股票]` | `Brain/SOP_策略分析.md` | 复现原规则后按 Profile 路由退出链 | `Brain/策略分析/`；Human 决定后进入 Console |
| `复盘一下` | `Brain/SOP_策略分析.md` | P11（个股）/ P7（组合） | `Brain/策略分析/` |

---

## 5) 策略分析五大路由（详细版）

> 完整 SOP 见 `Brain/SOP_策略分析.md`
> 进入任何路由前必须读取 Profile、个股知识库和 V4 单笔决策文件，并执行模块守卫。P2/P9 等 `profile` 模块不是公共强制项。

| 动作意图 | 提示词顺序 | 归档路径 |
|:---|:---|:---|
| **买入（首次建仓）** | Profile 模块守卫 → 已启用入场审计 → 最终裁判 | `Brain/策略分析/YYYY-MM/YYYY-MM-DD_TICKER_买入.md` |
| **加仓** | 复现原论点 → Profile 模块守卫 → 已启用加仓审计 → 最终裁判 | `Brain/策略分析/YYYY-MM/YYYY-MM-DD_TICKER_加仓.md` |
| **持有评估** | 复现原论点/退出规则 → 已启用持有审计 → 最终裁判 | `Brain/策略分析/YYYY-MM/YYYY-MM-DD_TICKER_持有.md` |
| **减仓/卖出** | 读 V4 单笔文件核对原规则 → 已启用退出审计 → 最终裁判 | `Brain/策略分析/YYYY-MM/YYYY-MM-DD_TICKER_卖出.md` |
| **仓位再平衡** | 读组合快照 → 已启用组合审计 → 最终裁判 | `Brain/策略分析/YYYY-MM/YYYY-MM-DD_仓位再平衡.md` |

---

## 6) 标的管理

| 暗号 | SOP | 动作 | 写回 |
|:---|:---|:---|:---|
| `关注 XX` | `持仓与关注/SOP_标的管理.md` | 新增 Watchlist + 可选初始调研 | `Watchlist_状态机.md` + 标的文件夹 |
| `建仓 XX` | `持仓与关注/SOP_标的管理.md` | 标记候选建仓并进入策略/Console | Watchlist + 决策计划；`fill` 后才写持仓 |
| `移除关注 XX` | `持仓与关注/SOP_标的管理.md` | Watchlist → 归档 | `Watchlist_状态机.md` |
| `清仓 XX` | `持仓与关注/SOP_标的管理.md` | 先核对 Console `close`；未平仓则进入卖出门禁 | `close` 后才迁移身份与归档 |

---

## 7) 输出格式建议（每次）

1. 一句话结论
2. 裁决、缺失数据与待 Human 决定事项
3. 策略报告路径；确认后的事实写回角色
