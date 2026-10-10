# YMOS × ymskill 适配

> 给装了 [ymskill](https://github.com/Evan-XYZ/ymskill) 的 Agent 读。**YMOS 不依赖 ymskill**：没装照常用；装了，按这一页分工，两套流程不会打架。
>
> ymskill 是《AI 投资指南》的动作版，装在 Agent 这一层（`~/.claude/skills/`、`~/.agents/skills/` 或 Claude Code 插件），在任何文件夹里都能被叫起来。YMOS 是装在磁盘上的文件夹。两边的接口就是这一页：哪些事交给 YMOS，哪些事 ymskill 来补，补出来的东西放在哪。
>
> 这一页随 YMOS 分发，桌面端「增量补全」也会补上它。你改过自己的目录，就直接改这一页，ymskill 以这一页为准。

---

## 一、分工

1. **YMOS 已经有的流程，用 YMOS 的。** 用户说的话能在 `总入口暗号.md` 里找到对应暗号，就按暗号走 YMOS 的 SOP，ymskill 不另起一套记录（比如不另建门禁日志，买卖走 Console 和 `Brain/SOP_策略分析.md`）。
2. **YMOS 没有的动作，ymskill 来做**，产物写进第四节列的目录。
3. **用户点名 `/yms-*`**（例如 `/yms-gate`），才用 ymskill 的版本；产物仍然写进 YMOS 的目录，不在 YMOS 里另建 `01_…07_` 那套标准目录。
4. 两边说法冲突时，以 YMOS 里 Human 确认过的 Profile 和状态机为准；ymskill 的输出只是候选。
5. ymskill 的红线和 YMOS 一致：不下单、不替用户做买卖决定、不改用户写的东西、不改评价自己的尺子。

## 二、路径映射

ymskill 的动作文件里写的是标准路径（`01_我的投资框架/…`），在 YMOS 里一律换成右边：

```markdown
## 路径映射（YMOS）
- Strategy_Profile = Brain/策略配置/当前策略_Profile.md
- 观测清单 = 持仓与关注/当前关注方向与投资偏好.md（只有占位、没填关注方向的空模板，按「没有」处理）
- 长期规则 = 当前策略_Profile 里的红线和门禁部分；Console/rules.json 只是它在操盘台的投影，冲突时以 Profile 为准
- 研究档案 = 持仓与关注/持仓/<标的>/、持仓与关注/动态Watchlist/<标的>/（只读已有的；新建按 持仓与关注/_模板_单标的/，先问用户）
  - 两把尺子、核心资产七问、反向 DCF、财报叙事：标的已有目录的，写进那个目录；没有的，写到 Brain/策略分析/ymskill/<名称>.md
- 每日观测 = Eyes/市场洞察/、Eyes/投资雷达/
  - 事件登记 = Eyes/事件登记.md
  - 核实记录 = Eyes/核实记录/
  - 传导推演 = Eyes/传导推演/
- 交易记录 = Brain/交易计划/、Brain/买入卖出决策/、Brain/决策审计/（都由 Console 写，只读）
  - 门禁日志（只在用户点名 /yms-gate 时）= Brain/决策审计/门禁日志.md（这个目录里只有这一份由 ymskill 追加）
  - 券商导出 = Brain/内核审计/数据/券商导出/
- 复盘 = Brain/内核审计/
  - 持有期复盘、纪律体检报告、回看台账、回看汇总 = Brain/内核审计/ 下同名文件
  - 标准化成交数据 = Brain/内核审计/数据/
- BrainStorm = BrainStorm/
  - 原始想法 = BrainStorm/每日头脑风暴/Raw_Thoughts/
  - Insight = BrainStorm/Summarized_Insights/
  - 感悟归档 = BrainStorm/投资感悟归档/（短期灵感/、长期框架/、执行清单/）
  - MEMORY.md = BrainStorm/MEMORY.md；STATUS.md = BrainStorm/状态机/STATUS.md
  - 状态快照 = BrainStorm/状态机/快照/
  - 动作记录 = BrainStorm/动作记录/
  - 回看 = BrainStorm/回看/
  - 历史资料 = BrainStorm/历史投资资料/（原始资料/、索引与梳理/）
- 主控 = Agents/
  - 交接 = Agents/交接/；回执 = Agents/回执/；心跳日志 = Agents/心跳日志/
  - 全局状态 = Agents/全局状态.md；机会卡 = Agents/机会卡/
```

写之前三条：

1. **ymskill 自己的产物位置**（核实记录、传导推演、事件登记、`Brain/策略分析/ymskill/`、门禁日志、`Brain/内核审计/` 下的数据和复盘文件、动作记录、回看、状态快照、`Agents/` 下的交接、回执、心跳日志、全局状态、机会卡）不存在就直接建，建完在回复里说一句建在哪。
2. **YMOS 自己的文件**（Profile、观测清单、Console 写的交易记录）不存在或是空模板，说明那部分还没配置：引导用户说对应的 YMOS 暗号（「配置一下我的内核」「更新我的关注方向」），不自己建；当次的输出标「无档案对照」或「无观测清单对照」。
3. **文件夹是 git 仓库的**（根目录有 `.git/`），第一次往上面这些位置写之前，看 `.gitignore` 有没有忽略它们。没有，就把下面几行给用户看，问要不要追加。交割单、复盘、核实记录都是个人数据，不该进仓库。

```gitignore
# ymskill 写进 YMOS 的个人产物
Eyes/核实记录/
Eyes/传导推演/
Eyes/事件登记.md
Brain/策略分析/ymskill/
Brain/内核审计/数据/
Brain/内核审计/持有期复盘_*.md
Brain/内核审计/纪律体检报告_*.md
Brain/内核审计/回看台账.md
Brain/内核审计/回看汇总_*.md
BrainStorm/动作记录/
BrainStorm/回看/
BrainStorm/状态机/快照/
Agents/交接/
Agents/回执/
Agents/心跳日志/
Agents/机会卡/
Agents/全局状态.md
```

## 三、交给 YMOS 的

| ymskill 动作 | 在 YMOS 里走 |
|:---|:---|
| 搭底座 · 建文件夹 | 不用建，用上面的映射 |
| 搭底座 · 策略档案 | 「配置一下我的内核」→ `Brain/内核审计/SOP_内核入职配置.md` |
| 搭底座 · 观测清单 | 「更新我的关注方向」→ `持仓与关注/SOP_关注方向维护.md` |
| 看 · 每日变化 | 「跑一下市场洞察」「跑一下投资雷达」 |
| 想 · 核心资产七问 | 启用了 P17 的：「用 P9/P17 看一下」；没启用的照常用 ymskill |
| 做 · 买入门禁 | 「我想买」「加仓」→ `Brain/SOP_策略分析.md` + Console 买卖决策台 |
| 做 · 卖出对照 | 「我想卖」→ `Brain/SOP_策略分析.md` |
| 做 · 操盘台 | Console（`cd Console && python3 server.py`，或桌面客户端） |
| 回看 · 单笔归因 | 「复盘一下这笔」→ `Brain/内核审计/SOP_平仓复盘归档.md` |
| 回看 · 规则变更 | 「审计一下我的内核」→ 判断层变更提案 |
| BrainStorm · 记下来 / 整理 / 沉淀 | 「开始今天的头脑风暴」「整理一下今天说的」→ `BrainStorm/SOP_头脑风暴.md` |
| BrainStorm · 历史资料入职 | 「整理我的历史投资资料」→ `BrainStorm/SOP_历史投资资料入职.md` |
| 自己跑 · 定时任务 | `Agents/SCHEDULES.md`、`Agents/ORCHESTRATION.md` |
| 总入口 · 起点诊断卡在策略 | 「帮我做一次投资诊断」→ `Brain/ymos-diagnosis/` |

## 四、ymskill 来补的

| ymskill 动作 | YMOS 里为什么要它 | 产物写到 |
|:---|:---|:---|
| 看 · 开原件核实 | YMOS 能取公告、新闻，没有「原件说了什么、没说什么」的核实动作 | `Eyes/核实记录/` |
| 看 · 事件分级 | 范围 / 触达 / 持续 + 阶段的分级法，比 P3 新 | `Eyes/事件登记.md` |
| 看 · 跨市场传导 | 带真映射 / 蹭概念三项核查 | `Eyes/传导推演/` |
| 想 · 两把尺子 | Profile 里有不止一类机会时，同一件事每把尺子各量一遍 | 标的目录，没有就 `Brain/策略分析/ymskill/` |
| 想 · 反向 DCF | 带计算脚本，可和 P9 对照 | 标的目录，没有就 `Brain/策略分析/ymskill/` |
| 想 · 财报叙事 | 两个季度管理层口径对比 | 标的目录，没有就 `Brain/策略分析/ymskill/` |
| 回看 · 持有期复盘 | 直接读券商交割单，按持有期分组；不依赖 Console 记录 | `Brain/内核审计/` |
| 回看 · 三红旗 | 没用 Console 的，直接扫交割单；用了 Console 的，以内核周期审计为准 | `Brain/内核审计/` |
| 回看 · 回看台账 | 系统推过的方向 7 / 30 / 60 天对比基准 | `Brain/内核审计/回看台账.md` |
| BrainStorm · 动作记录 | 今天真的做了什么，和想法对着看 | `BrainStorm/动作记录/` |
| BrainStorm · 状态机与回看 | 每周对照想法和动作，到期假设对真值 | `BrainStorm/回看/`，状态机改版前留快照到 `BrainStorm/状态机/快照/` |
| 自己跑 · 主控心跳 | 每天读完所有产物写一份交接 | `Agents/交接/` |

这些都是新目录或新文件，YMOS 的增量补全只补缺失的官方文件、不动已有文件，不会碰它们。新版 YMOS 的 `.gitignore` 已经忽略它们；老版本按第二节第 3 条处理。

## 五、版本

- 适用：YMOS V4.x，ymskill 1.x。
- ymskill 没读到这一页时（老版本 YMOS 还没补上它），用它内置的同一份映射，效果一样。
