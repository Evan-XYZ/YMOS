# 📊 市场洞察 SOP

> 暗号：`跑一下市场洞察`
> 模块：Eyes/（眼睛 — 盯市场）

---

## 一句话定位

市场洞察只回答一件事：**今天市场发生了什么，哪些方向值得进入下一步分析**

- 只处理事件 + 宏观信号
- **不负责价格扫描**（价格扫描在投资雷达里做）
- P14 板块猎手不是默认链路，有需要时再手动深挖

---

## 🔑 触发暗号

| 暗号 | 操作 |
|:---|:---|
| `跑一下市场洞察` | 完整流程（拉数据 → P13分析 → 保存） |
| `今天有什么新闻` | 快速浏览（拉1天数据 → 简要总结，不保存） |
| `抓 N 天数据` | 只抓数据不分析（运行脚本，存 Raw_Data） |

---

## ⚙️ 完整执行步骤

### Step 1：创建输出目录

```bash
mkdir -p "Eyes/市场洞察/Raw_Data/$(date +%Y-%m)"
mkdir -p "Eyes/市场洞察/$(date +%Y-%m)"
```

### Step 2：拉取市场数据（自动回退）

**方式 A：市场信息 API（优先）**
```bash
python3 Eyes/scripts/fetch_market_api.py 1 \
  --output "Eyes/市场洞察/Raw_Data/$(date +%Y-%m)/financial_data_$(date +%Y%m%d).json"
```

> 脚本会自动加载 `.env` 中的 `YMOS_MARKET_API_KEY`。无 key 时脚本以 exit(0) 退出并提示使用 RSS。

**方式 B：RSS 免费数据源（回退 / 无 API Key 时使用）**
```bash
python3 Eyes/scripts/fetch_rss.py 1 \
  --output "Eyes/市场洞察/Raw_Data/$(date +%Y-%m)/financial_data_$(date +%Y%m%d).json"
```

**Agent 执行规则**：
1. 先尝试方式 A
2. 若方式 A 的脚本输出包含"跳过 API 数据源"或未生成输出文件 → 自动回退到方式 B
3. 用户指定天数时，把 `1` 替换为对应天数

### Step 2.5：CIO 半成品处理（仅 RSS 路径需要）

> **仅当 Step 2 使用了方式 B（RSS）时执行此步。**
> API 路径（方式 A）的数据已经过清洗和分类，跳过此步。

读取 Step 2 生成的 RSS 原始 JSON，调用：
- `Brain/references/cio-rss-processor.md`

CIO 处理器会执行：去重合并 → 噪音过滤 → 事件聚类 → 信号提取

**输出路径**：`Eyes/市场洞察/Raw_Data/YYYY-MM/cio_processed_YYYYMMDD.md`

### Step 2.6：拉取 Finnhub 持仓个股新闻（补充数据源，可选）

> **仅当 `.env` 或环境变量中存在 `FINNHUB_API_KEY` 时执行。无 key 则静默跳过。**

```bash
python3 Eyes/scripts/fetch_finnhub_news.py \
  --hours 24 \
  --output "Eyes/市场洞察/Raw_Data/$(date +%Y-%m)/finnhub_news_$(date +%Y%m%d).json"
```

**策略说明**：
- 只对【持仓状态机】中的美股/Crypto 标的调用 `/company-news` 接口
- Watchlist 不拉个股新闻（节省 rate limit）
- A股/港股 Ticker 不支持 Finnhub，自动过滤

### Step 2.7：拉取补充 RSS 数据（可选）

> **仅当 `Eyes/scripts/rss_sources_custom.json` 存在时执行。无此文件则静默跳过。**
>
> 补充 RSS 与主数据源（API 或默认 RSS）独立运行，不互斥。
> 适用场景：用户已有 Market Data API，但还想订阅特定行业/深度分析的 RSS 源。

```bash
python3 Eyes/scripts/fetch_rss.py {天数} \
  --config Eyes/scripts/rss_sources_custom.json \
  --output "Eyes/市场洞察/Raw_Data/$(date +%Y-%m)/supplementary_rss_$(date +%Y%m%d).json"
```

**Agent 执行规则**：
1. 检查 `Eyes/scripts/rss_sources_custom.json` 是否存在
2. 存在 → 执行拉取，输出为 `supplementary_rss_YYYYMMDD.json`
3. 不存在 → 静默跳过，不提示用户

### Step 3：调用 P13 分析

> ⚠️ **无论数据来自 API 还是 RSS，都必须严格按照 P13 标准模板输出。**
> API 数据质量更高 ≠ 可以简化输出格式。P13 的价值不在于数据清洗（那是 CIO 的活），
> 而在于 **信号识别 + 结构化呈现**（战略信号仪表盘 + 势能分析 + 风险警告）。

**P13 分析输入文件（按优先级读取）**：
1. **主输入**：`financial_data_YYYYMMDD.json`（API 路径）或 `cio_processed_YYYYMMDD.md`（RSS 路径）
2. **补充输入**（如存在）：`finnhub_news_YYYYMMDD.json`
   - `p15_trigger=true` 的条目 → P13 报告中标注「建议跑 P15」
3. **补充输入**（如存在）：`supplementary_rss_YYYYMMDD.json`（用户自定义 RSS）

调用：`Brain/references/p13-market-scanner.md`

**P13 分析时，参考过去几天的历史洞察（如有）**：
- 路径：`Eyes/市场洞察/YYYY-MM/` 目录下最近几份报告

**输出格式硬约束**（缺一不可）：
1. **市场体温**标签（Risk On / Risk Off / Chaos）+ **一句话摘要**
2. **战略信号仪表盘**（表格形式，3-5 个信号，含 信号类型 / 核心主题 / 信号解读）
3. **势能与机会详解**（短期势能 + 长线配置，含来源链接）
4. **风险与纪律警告**
5. 页脚声明

> 具体模板见 `Brain/references/p13-market-scanner.md` 的 `# Output Format` 区块。

> ⚠️ **P14 不在默认链路内**：用户明确要做板块深挖时再手动触发 `Brain/references/p14-sector-hunter.md`

### Step 4：保存洞察报告

**输出路径**：`Eyes/市场洞察/YYYY-MM/YYYY-MM-DD_市场洞察.md`

### Step 5：在对话中输出

直接在对话中输出完整 Markdown 报告内容。

---

## 📦 产出物清单

| 文件 | 路径 | 命名规则 | 说明 |
|:---|:---|:---|:---|
| Raw Data（API/RSS） | `Eyes/市场洞察/Raw_Data/YYYY-MM/` | `financial_data_YYYYMMDD.json` | 必有 |
| CIO 半成品情报 | `Eyes/市场洞察/Raw_Data/YYYY-MM/` | `cio_processed_YYYYMMDD.md` | 仅 RSS 路径 |
| Finnhub News | `Eyes/市场洞察/Raw_Data/YYYY-MM/` | `finnhub_news_YYYYMMDD.json` | 有 key 才有 |
| 市场洞察报告 | `Eyes/市场洞察/YYYY-MM/` | `YYYY-MM-DD_市场洞察.md` | 必有 |

---

## 📤 下游分发规则

市场洞察本身不触发个股分析或策略制定，但它是投资雷达的核心输入：

- 生成的洞察报告会被 `跑一下投资雷达` 自动读取
- 洞察中出现的相关板块/事件信号，在投资雷达里会与持仓 + Watchlist 做关联匹配
- 重大事件在投资雷达报告的「下一步建议」中推荐对应的策略分析路由

---

## 📁 路径速查

| 内容 | 路径 |
|:---|:---|
| 市场数据脚本（API） | `Eyes/scripts/fetch_market_api.py` |
| 市场数据脚本（RSS） | `Eyes/scripts/fetch_rss.py` |
| RSS 源配置 | `Eyes/scripts/rss_sources.json` |
| CIO 处理提示词 | `Brain/references/cio-rss-processor.md` |
| Finnhub News 脚本 | `Eyes/scripts/fetch_finnhub_news.py` |
| P13 提示词 | `Brain/references/p13-market-scanner.md` |
| P14 提示词（手动深挖） | `Brain/references/p14-sector-hunter.md` |
| 历史洞察报告归档 | `Eyes/市场洞察/YYYY-MM/` |
| Raw Data 归档 | `Eyes/市场洞察/Raw_Data/YYYY-MM/` |

---

## ⚠️ 边界

- 市场洞察**不看持仓**，不看价格
- 不自动更新状态机
- 不进入策略判断

---

*SOP 版本：2026-03-18 · YMOS V3 三模块制（Eyes / Brain / 持仓与关注）*
