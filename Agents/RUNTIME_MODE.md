# YMOS Agent Runtime Mode

## 默认可移植模式：Single Controller / Multi-Role

YMOS 的公开版默认不假设宿主具有子 Agent 能力，而是：

- **1 个主控 Agent（main）**
- **扮演 4 个明确角色**
  - Market Insight Agent
  - Investment Radar Agent
  - Strategy Agent
  - Portfolio State Agent

这是跨 Claude Code、Codex、OpenClaw 等宿主最容易复现的基线。

---

## 为什么现在先这样做

### 原因 1：不能假设所有宿主都支持同一种多 Agent 接口

公开仓库只定义角色协议，不绑定某个平台的 allowlist、会话接口或进程模型。

### 原因 2：先把协议写清楚，比先并发更重要
真正决定 YMOS 是否好用的，不是“有没有 4 个进程”，而是：
- 角色边界清不清楚
- 输入输出清不清楚
- 状态写回有没有唯一出口

---

## 当前执行原则

### 1. 角色分离，执行不分裂
虽然由 main 执行，但每次执行时都要先明确自己正在扮演哪个角色。

### 2. 状态写回唯一出口
只有 **Portfolio State Agent** 口径可以做最终状态写回。

### 3. 文档与任务命名先 Agent 化
先把：
- ORCHESTRATION
- SCHEDULES
- AGENT_GUIDE
- cron 文案

都升级为 Agent 口径。

这样未来切真 subagent 时，几乎不需要推翻原系统。

---

## 未来升级条件

当你的 Agent 宿主支持子 Agent 编排后，可升级为：
- 主控：main
- 子角色：market-insight / investment-radar / strategy / portfolio-state

届时只需把当前文档协议映射到真实 sessions_spawn / subagent runtime 即可。
