# YMOS 定时任务编排（Schedules）

> 基准路径：`<你的 YMOS 根目录>`
> 当前执行模式：**单主控（main）模拟 4 Agent 编排**

> 📎 **想看一套真实跑过的完整配置？** → [`SCHEDULES_REFERENCE.md`](SCHEDULES_REFERENCE.md)
>
> **时间只是示例。** 下面的 10:30 / 10:45 / 10:55 / 11:05 是按 A 股盘中节奏排的一组样例。
> 真正重要的不是几点跑，而是**顺序和依赖**：洞察 → 雷达 → 策略 → 状态写回。
> 换成你自己的市场和作息（美股盘后、欧股开盘前……），把时间整体平移即可，链路不变。

---

## 一、当前定时任务链

### 1. 10:30 — Market Insight Agent
- **任务名**：YMOS - 每日市场洞察 10:30
- **职责**：生成当日市场洞察，作为全链路起点
- **输出**：`Eyes/市场洞察/YYYY-MM/YYYY-MM-DD_市场洞察.md`

### 2. 10:45 — Investment Radar Agent
- **任务名**：YMOS - 工作日投资雷达 10:45
- **依赖**：当日市场洞察已完成
- **职责**：结合市场洞察 + 状态机 + 价格扫描，生成桥接报告
- **输出**：`Eyes/投资雷达/YYYY-MM/投资雷达_YYYY-MM-DD.md`

### 3. 10:55 — Strategy Agent
- **任务名**：YMOS - 工作日策略分析 10:55
- **依赖**：当日投资雷达已完成
- **职责**：消费雷达建议，推进初始调研 / 持有评估 / 策略判断
- **输出**：`Brain/策略分析/YYYY-MM/`

### 4. 11:05 — Portfolio State Agent（建议新增）
- **建议职责**：统一写回状态机 + 生成持仓备忘录视图
- **输出**：
  - `持仓与关注/持仓_状态机.md`
  - `持仓与关注/Watchlist_状态机.md`
  - `持仓与关注/持仓备忘录_视图.md`

---

## 二、当前现实限制

### 可用 Agent 能力
多数 Agent 宿主（Claude Code / Codex / OpenClaw 等）默认只暴露一个主控会话，可直接调用的 agent 只有：
- `main`

这意味着：
- ✅ 可以做 **单主控 + 多角色协议**
- ✅ 可以做 **顺序编排**
- ✅ 可以把各角色职责写死到文档与定时任务中
- ❌ 还不能真正把 Market / Radar / Strategy / State 分别交给独立 subagent 并发运行

---

## 三、当前推荐执行模式

### 模式 A：现在就能稳定跑
由 `main` 统一按以下顺序模拟 4 Agent：

```text
10:30 Market Insight Agent
10:45 Investment Radar Agent
10:55 Strategy Agent
11:05 Portfolio State Agent
```

优点：
- 简单稳定
- 不需要新增平台能力
- 已经足够把 YMOS 从“暗号系统”升级成“编排系统”

---

## 四、未来升级模式

### 模式 B：真子 Agent 编排（未来）
当你的 Agent 宿主支持真正的子 agent 编排后，可升级为：
- `market-insight-agent`
- `investment-radar-agent`
- `strategy-agent`
- `portfolio-state-agent`

到时主控只负责：
- 发任务
- 收结果
- 写最终状态

---

## 五、推荐 cron 文案口径

### 市场洞察
> 提醒：现在请运行 Market Insight Agent（对应「跑一下市场洞察」）。请严格读取 Eyes/SOP_市场洞察.md，并只写入 Eyes/市场洞察/；保存后必须做结构校验。

### 投资雷达
> 提醒：现在请运行 Investment Radar Agent（对应「跑一下投资雷达」）。请严格读取 Eyes/SOP_投资雷达.md，依赖当日 Eyes/市场洞察/ 成功产物后执行，只写入 Eyes/投资雷达/。

### 策略分析
> 提醒：现在请运行 Strategy Agent（对应「跑一下策略分析」）。依赖当日投资雷达完成后执行，负责消费建议并推进策略判断。

### 状态写回（建议新增）
> 提醒：现在请运行 Portfolio State Agent。请严格读取 持仓与关注/SOP_持仓收口.md，统一写回状态机、刷新持仓备忘录视图，并生成当日 dashboard HTML。
