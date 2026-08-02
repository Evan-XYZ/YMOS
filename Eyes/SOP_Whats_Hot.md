# 🔥 What’s Hot SOP（A股热门追踪 / A股观察池入口）

> **作者内核扩展｜`disabled_by_default: true`** 这是特定市场的候选发现流程，内含作者的扫描口径与 P17 分类。默认不运行、不调度；启用前需替换为用户自己的数据源、阈值和 Profile 映射。

> 暗号：`跑一下 What's Hot` / `跑一下热门板块` / `看看什么最热` / `跑一下A股热门`
> 模块：Eyes/（眼睛 — A股价格事件 + 板块热度）
> 下游：`持仓与关注/A股观察/` + `SOP_Watchlist自动建档.md`
> 配套提示词：`Brain/references/p14-sector-hunter.md`（板块热度）+ `Brain/references/p17-core-asset.md`（v3：资产等级 + 当前机会拆分）

---

## 一句话定位

**What’s Hot = A股热门追踪**：用问财 A股三池（单日涨幅异动 + 新高抢筹 + 单日跌幅/资金流出）+ 当日/7天市场洞察 + 美股热门追踪映射层，先做 P14-lite 板块热度收敛，再用 P17 v3 拆成两层结果：

- **资产等级**：🟢 A类核心资产 / 🟣 A类高赔率资产 / 👀 B类跟踪资产 / 🟡 P2观察 / 🔴 跳过。
- **当前机会标签**：🚀 抢筹初期 / 👀 待回调 / 🟡 Conditional / 🔴 跳过。

A类资产不等于当前买点；What’s Hot 输出的 A/B/P2 是“热门入池初筛评级”，不是最终核心资产判决。A 类默认写入 `持仓与关注/A股观察/`，等待 Human 复核与自动建档；只有经过 P9/P17 深研或 `SOP_核心资产动态判定表.md` 二次确认后，才同步写入 `持仓与关注/核心资产库/核心资产状态机.md`。B类标记为价格跟踪候选，Human 确认或连续入池后再进入 `动态Watchlist/`。

关键关系：**美股对 A股有强映射意义；A股对美股只有弱参考意义。** A股 SOP 必须主动吸收美股热门追踪/市场洞察中的美股主线，用来识别 A股映射标的。

### 统一链路契约（2026-05-11）

本 SOP 负责 A股侧的**动量发现 + 映射验证**。它不是“涨停榜复述”，而是把价格事件转成后续研究任务：

```text
A股价格事件（三池：涨幅异动 / 新高 / 跌幅）
  + 美股强映射输入（美股热门追踪 / 市场洞察）
  → 主线代表权 / 龙头组候选预警（中军 / 弹性 / 低估值补涨 / 价格发现）
  → P14-lite 收敛主线、真龙头、跟风与退潮
  → 基本面证据链优先级：财务/公告事实层 > 研报叙事层 > 新闻事件层 > 热门初筛
  → P17 v3 拆分资产等级与当前机会标签
  → A股观察状态机（A 类待自动建档；B 类待确认/价格跟踪候选）
  → Watchlist 自动建档补 P1/P2/P4/P9/P17
  → 核心资产动态判定表周度确认是否入核心资产库
```

关键口径：
- 动量是研究任务，不是买点信号；A股“强势”只说明市场在交易它，不说明它已经是核心资产。
- `双池强抢筹` 与 `新高单池核心复核` 必须分表；不能因为当日涨幅没到 8% 漏掉澜起/胜宏/江波龙这类右侧早中期资产。
- A股侧更容易出现题材温度计和补涨噪音，必须用财务/公告事实层压住研报和新闻叙事。
- 当同一主线连续入池并出现大市值/高流动性代表股时，必须额外输出 `mainline_groups`：先问“市场买这个方向，第一组会买谁”，再进入单票 P17/P9。
- 不得因为静态毛利率低、商业模式不够“性感”而自动降权市场已经买出来的平台型中军；封测/代工/服务器/制造服务类龙头要检查稼动率、产品结构、经营杠杆和边际重估。

```text
A股涨幅异动池（单日 >8%）
  + A股新高池（持续抢筹）
  + A股跌幅/资金流出池（单日 <-8% / 退潮预警）
  + 自持基本面事件增量 + 3~7 天市场洞察
  + 美股热门追踪 / 美股市场洞察（强映射输入）
  + P14-lite 板块热度层
  + P17 v3（资产等级 + 当前机会标签）
= What’s Hot 日报 + A股观察池候选 + A股观察状态机 + 核心资产库 + 动态 Watchlist 候选
```

---

## 🔑 触发暗号

| 暗号 | 操作 |
|:---|:---|
| `跑一下 What's Hot` | 完整流程（三池 + 美股映射 + P14-lite + P17 A/B 分类） |
| `跑一下热门板块` | 同上 |
| `看看什么最热` | 同上 |
| `跑一下A股热门` | 同上 |
| `A股热门 只看异动` | 只跑单日涨跌异动池 |
| `A股热门 只看新高` | 只跑新高池 |

---

## 🧩 运行前条件

What’s Hot 的问财三池不是 YMOS 内置数据源。首次运行前确认：

1. Agent 宿主已安装 `hithink-astock-selector` Skill；
2. YMOS 根目录 `.env` 已配置 `IWENCAI_API_KEY`；
3. Skill 不在默认搜索位置时，`.env` 还要配置 `YMOS_SKILL_ROOT`；
4. 运行 `python3 Eyes/scripts/skill_resolver.py` 能找到 A 股选股 Skill。

完整安装与冒烟测试见 `进阶指南.md` →「问财数据层（可选 · Level 1++）」。

缺少 Skill 或 Key 时不得伪装成功：必须在 Raw_Data 留下 status，并按 Step 3 降级。问财只是可选手脚，不得因此阻断市场洞察、投资雷达、策略分析等主链路。

---

## ⚙️ 完整执行步骤

### Step 1：加载市场背景（自持增量 + 3~7 天市场洞察）

> 2026-05-10 修订：What’s Hot **不再依赖“当日市场洞察已生成”**，也不触发 `跑一下市场洞察`。市场洞察按自己的节奏运行；What’s Hot 只读取已有报告，并按“上一份 What’s Hot 报告 mtime → 当前时间”的窗口，独立抓取本 SOP 所需的基本面事件增量。

1. **计算本 SOP 自己的增量窗口 `LOOKBACK_DAYS`**：

```bash
LATEST_WHATS_HOT=$(ls -1 "Eyes/Whats_Hot/"*/Whats_Hot_????-??-??.md 2>/dev/null | sort | tail -1)
if [ -z "$LATEST_WHATS_HOT" ]; then
  LOOKBACK_DAYS=1
else
  LOOKBACK_DAYS=$(python3 -c "import os,time; m=os.path.getmtime('$LATEST_WHATS_HOT'); print(f'{max(0.5, round((time.time()-m)/86400, 2)):.2f}')")
fi
echo "上一份 What's Hot：${LATEST_WHATS_HOT:-无} | LOOKBACK_DAYS=$LOOKBACK_DAYS"
```

2. **独立抓取基本面事件增量（存到 What’s Hot 自己的 Raw_Data）**：

```bash
python3 Eyes/scripts/fetch_market_api.py $LOOKBACK_DAYS   --output "Eyes/Whats_Hot/Raw_Data/YYYY-MM/market_increment_YYYYMMDD.json"

python3 Eyes/scripts/fetch_finnhub_news.py   --hours $(python3 -c "print(int(float('$LOOKBACK_DAYS') * 24))")   --output "Eyes/Whats_Hot/Raw_Data/YYYY-MM/finnhub_increment_YYYYMMDD.json"
```

若任一增量抓取失败：保留 status/错误说明，降级为读取最近 3~7 天市场洞察；**不要补跑市场洞察**。

3. **过去 3~7 天市场洞察（只读已有报告）**：提取重复出现的主线、新强化主题、退潮主题、事件链条。
4. **美股热门追踪 / 美股盘面映射（强输入）**：读取最近一份 `Eyes/美股热门追踪/YYYY-MM/美股热门追踪_YYYY-MM-DD.md`，提取：
   - 美股 A/B 类机会；
   - 美股 P14-lite 最强板块；
   - AI / 半导体 / 存储 / 电力 / 商业航天 / 核能等可映射方向；
   - 美股已退潮但 A股仍补涨的风险信号。
5. **A股观察状态机（写回目标）**：`持仓与关注/A股观察/A股Watchlist状态机.md`。本 SOP 结束时必须把 A/B 候选、Human状态、建档状态、价格跟踪候选写回该状态机，供 Watchlist 自动建档消费。
6. **当前持仓 / 动态 Watchlist / A股观察池去重**：避免重复推荐已在跟踪的标的。

---

### Step 2：运行问财 A股三池

> 数据源：`Eyes/scripts/iwencai_stockpick.py`。
> 原则：Raw_Data 抓全量，正文只提炼主线/龙头，不堆表。

#### 2.1 涨幅异动池（单日强事件 · 新增）

```text
流通市值大于100亿，今日涨幅大于8%，非ST
```

用途：捕捉当天资金突然抢筹的方向，解决旧版只看新高、漏掉“首日异动”的问题。

```bash
python3 Eyes/scripts/iwencai_stockpick.py \
  '流通市值大于100亿，今日涨幅大于8%，非ST' \
  --json-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_movers_YYYYMMDD.json \
  --csv-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_movers_YYYYMMDD.csv \
  --desc-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_movers_YYYYMMDD_description.txt \
  --status-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_movers_YYYYMMDD_status.txt \
  --limit 50
```

#### 2.2 新高池（持续抢筹）

```text
流通市值大于100亿，近2周股价创60日新高，近1月创1年新高，近5个交易日上涨大于8%，非ST
```

输出前缀：`whats_hot_newhighs_YYYYMMDD`

用途：捕捉持续抱团、趋势已被市场确认的方向。

#### 2.2b 宽口径新高 / 近高池（可选增强，用于防漏）

当报告发现 `新高单池` 中 A 类/准 A 资产较多，或 Human 明确要求“新高附近也要留意”时，加跑一组宽口径池，不替代标准新高池：

```text
流通市值大于100亿，近2周股价创60日新高，近1月创1年新高，近5个交易日上涨大于3%，非ST
```

输出前缀：`whats_hot_newhighs_wide_YYYYMMDD`

用途：捕捉“还没单日爆发、但已经被资金持续抬升”的早中期右侧资产。正文只纳入 A 类/准 A 核心资产、历史 A/P0、核心资产库成员或强美股映射标的；不要把宽口径池原样堆进报告。

如果问财支持“距高点”类表达，可再试一组近高增强：

```text
流通市值大于100亿，距60日高点小于5%，近5个交易日上涨大于3%，非ST
```

若返回字段不稳定，只保留 Raw，不作为主流程依赖。

标准新高池运行示例：

```bash
python3 Eyes/scripts/iwencai_stockpick.py \
  '流通市值大于100亿，近2周股价创60日新高，近1月创1年新高，近5个交易日上涨大于8%，非ST' \
  --json-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_newhighs_YYYYMMDD.json \
  --csv-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_newhighs_YYYYMMDD.csv \
  --desc-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_newhighs_YYYYMMDD_description.txt \
  --status-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_newhighs_YYYYMMDD_status.txt \
  --limit 50
```

宽口径池运行示例：

```bash
python3 Eyes/scripts/iwencai_stockpick.py \
  '流通市值大于100亿，近2周股价创60日新高，近1月创1年新高，近5个交易日上涨大于3%，非ST' \
  --json-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_newhighs_wide_YYYYMMDD.json \
  --csv-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_newhighs_wide_YYYYMMDD.csv \
  --desc-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_newhighs_wide_YYYYMMDD_description.txt \
  --status-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_newhighs_wide_YYYYMMDD_status.txt \
  --limit 100
```

#### 2.3 跌幅 / 资金流出池（退潮预警 · 新增）

```text
流通市值大于100亿，今日跌幅大于8%，非ST
```

用途：不产 A/B 新机会，主要用于：
- 判断热门板块是否退潮；
- 检查持仓 / 动态 Watchlist 是否踩中风险；
- 识别“美股强、A股映射却资金流出”的背离。

```bash
python3 Eyes/scripts/iwencai_stockpick.py \
  '流通市值大于100亿，今日跌幅大于8%，非ST' \
  --json-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_decliners_YYYYMMDD.json \
  --csv-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_decliners_YYYYMMDD.csv \
  --desc-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_decliners_YYYYMMDD_description.txt \
  --status-out Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_decliners_YYYYMMDD_status.txt \
  --limit 50
```

#### 2.4 全量抓取原则

- 默认不只取首页结果。
- 若 `code_count > returned_count`，脚本必须自动翻页，直到抓完整个结果集、触发 `max-pages` 上限或 API 返回空页。
- Raw_Data 保存全量 JSON / CSV；报告正文只提炼主线、龙头、A/B 候选。

---

### Step 3：失败降级规则

如果问财不可用：
1. 不阻塞主流程；
2. Raw_Data 下保留查询说明和 status；
3. 报告进入 best-effort：用市场洞察 + 美股热门追踪 + 公开盘后摘要拼接；
4. 正文显式标注“本次问财未成功执行”。

---

### Step 4.0：主线代表权 / 龙头组候选预警

在进入 P14-lite 前，必须先做一次主题成组扫描。这个模块的职责是 **attention allocation**，不是买点判断：它只负责提醒后续 `SOP_Watchlist自动建档.md` 做横向 P9/P17，不直接触发交易或 P5/P12。

触发条件（满足 2 条以上即输出）：

1. 同一主题在 2-3 个交易日内连续出现在 `movers / newhighs / newhighs_wide`；
2. 至少一个大市值、高流动性、机构可配置的代表股参与；
3. 组内出现 `中军 / 弹性 / 低估值补涨 / 二线价格发现` 的扩散结构；
4. 与美股映射、产业事件、政策/订单/产品周期之一共振。

输出口径：

```yaml
mainline_groups:
  - theme: 先进封装/封测/OSAT
    leader_anchor: 长电科技          # 中军 / 定价锚 / 机构可配置代表
    beta_leader: 通富微电            # 弹性 / AI-HPC 叙事抓手
    value_repair: 华天科技           # 低估值补涨 / 修复锚
    price_discovery: [甬矽电子, 盛合晶微, 伟测科技]
    prettier_chokepoints: [深南电路, 联瑞新材, 安集科技, 芯源微, 中科飞测]
    miss_type: data_seen_needs_escalation
    next_action: 横向P9/P17；不触发买入
```

裁决标签：

- `data_miss`：Raw 没看见；数据层要补；
- `escalation_miss`：Raw 已看见，但没有升权成主线代表权/龙头组审计；
- `valuation_veto`：已看见且已审计，但赔率/估值不支持；
- `evidence_gap`：价格强，但公告/财务/客户证据不足。

关键坑：**不能只找“漂亮环节”。** 设备、材料、载板、耗材等 Choke Point 能提供非对称收益，但主线确认初期，市场最先买出来的中军/平台型代表股通常承担资金配置权。低毛利不等于低优先级，必须检查边际重估：稼动率、先进产品占比、ASP、利润率修复、经营杠杆、客户结构变化。

#### Step 4.0.1：板块首发信号（Sector Ignition Signal · SIS · 2026-07-01 新增）

`mainline_groups` 是软预警（满足 2 条即输出，用于提醒横向 P9/P17）。SIS 是它之上的**量化硬触发**，用于把"多股指向同一板块"从"提醒深研"升级为"立刻启动组级别先手裁决"。SIS 三条**全满足**才算首发信号：

1. **成组**：某一细分板块 **≥3 只**个股在**近 3 个交易日内**进入 `movers / newhighs / newhighs_wide`（跨日累计，去重后按板块计数）；
2. **龙头强度**：组内龙头**近 5 日涨幅 >30%**；
3. **产业催化**：有**明确产业催化**（财报/订单/政策/产能/海外映射之一，非纯情绪概念）。

**跨日累计怎么算**：只读最近 3 份 `Whats_Hot_YYYY-MM-DD.md`（含今日三池），按细分板块把去重后的入池个股累计计数；价格强度取 `newhighs` 池对应字段或单独补算。

**SIS 触发后必须做**：

- 报告新增置顶段 `## 🚨 板块首发信号（SIS）`，输出结构化 `sis` yaml（含代表权分工初判 + 势能阶段初判）；
- 该组 `next_action` 从"横向P9/P17；不触发买入"**升级为**"启动组级别 P17-lite（先定代表权，不逐只深研）——见 `Brain/references/p17-core-asset.md` §0.7"；
- 将主题键、累计成员、阶段和代表权写入当期报告；下期通过最近报告继续计算。

```yaml
sis:
  - sector: 半导体硅材料
    member_count_3d: 4              # 近3日去重入池只数（≥3 才触发）
    members: [标的A, 标的B, 标的C, 标的D]
    leader: 标的B
    leader_5d_gain: 0.30+           # 近5日涨幅（>30% 才触发）
    catalyst: 国产替代 + 产品涨价 + 上游 CapEx 扩张（硬催化，非纯概念）
    us_mapping: 对应美股设备链共振 / 无
    roles:                          # 组级别 P17-lite 代表权初判
      anchor: 标的A                 # 中军 / 定价锚 / 先手首选
      beta_leader: 标的B            # 弹性龙头
      choke_point: 标的C            # 稀缺卡点（上游材料/设备）
      value_repair: null
    stage: 第一波加速后段          # 初期/中段/后段/退潮
    verdict: 已确认主线，但当前加速后段——不追高，等回踩击球区或第二波
    next_action: 启动组级别 P17-lite（p17 §0.7）；先登记代表权+击球区，不追高
```

关键坑：**SIS 是先手裁决的触发器，不是买入信号。** 它把注意力从"逐只深研"转到"先定代表权 + 判断处于第几波"；加速后段的 SIS 只登记不追高。

---

### Step 4：P14-lite 板块热度层

P14 在 A股里仍然重要，但目标不是写长篇板块报告，而是为 P17 A/B 分类提供“方向是否对”的前置判断。

合并输入：
1. 本 SOP 自持的基本面事件增量 + 过去 3~7 天市场洞察；
2. A股涨幅异动池；
3. A股新高池；
4. A股跌幅/资金流出池；
5. 美股热门追踪的强势板块与 A/B 类；
6. `mainline_groups` 主线代表权候选；
7. 当前持仓 / Watchlist / A股观察池去重。

P14-lite 必须输出：
- **今日最强主线**：资金最集中在哪里；
- **真龙头 vs 跟风股**：谁是资金选择，谁只是补涨；
- **主线代表权 / 龙头组**：同一主线里谁是中军、弹性、低估值补涨、二线价格发现；是否需要横向 P9/P17；
- **美股映射关系**：美股信号如何解释 A股机会；
- **退潮/背离**：哪些板块涨幅池强但跌幅池也多，说明内部松动；
- **进入 P17 的候选清单**：必须拆成两张候选表，而不是只看双池命中：
  1. `双池强抢筹表`：涨幅异动池 ∩ 新高池，最多 10 只，回答“今天资金抢谁”；
  2. `新高单池核心复核表`：新高池 - 涨幅异动池，优先挑选 A 类/准 A 核心资产、历史 A/P0、核心资产库成员、或与美股强主线高度映射的标的，最多 10-15 只，回答“谁已经在右侧趋势里但当天没有涨超 8%，容易被双池门槛漏掉”。

#### 4.1 新高单池复核规则（2026-05-10 补丁）

双池命中是强信号，但不是硬门槛。What’s Hot 必须显式复核 `newhigh_only = 新高池 - 涨幅异动池`：

- 若标的是核心资产库成员、历史 A/P0、或 P17 Q1/Q4/Q5 明显成立，即使当日涨幅 <8%，也要进入 `新高单池核心复核表`；
- 若标的是主线温度计（例如国产算力大市值高估值品种），可以进入“温度计/情绪锚”，但不得因为市值大或涨幅强自动给买点；
- 若标的是周期/题材补涨，除非有财务/公告/研报事实层支撑，否则只记录不建档；
- 报告正文必须写出：`新高池总数 / 双池命中数 / 新高单池数`，并说明是否存在“被双池门槛漏掉的 A 类/准 A 资产”。

---

### Step 5：量化打分 + P17 v3 A/B 分类（热门初筛，不等于最终核心库）

A股版借鉴美股热门追踪的“先量化，再判断”。

```text
Score = PriceEvent(0-20)
      + MomentumPersistence(0-15)
      + USMappingCatalyst(0-15)
      + AShareSectorHeat(0-15)
      + CoreAssetScarcity(0-20)
      + FutureOptionality(0-10)
      + NewDiscoveryBonus(0-5)
      - RiskPenalty(0-20)
```

| 因子 | 分值 | 判定方式 |
|:---|---:|:---|
| PriceEvent | 0-20 | 涨幅池 +8；新高池 +8；双命中 +4 额外分。双池满分代表当日抢筹强，不代表资产等级更高 |
| MomentumPersistence | 0-15 | 5 日 / 2 周 / 1 月趋势是否持续 |
| USMappingCatalyst | 0-15 | 美股是否已有同方向催化 / 龙头验证 / 财报验证 |
| AShareSectorHeat | 0-15 | P14-lite 主线热度、板块内强股密度、真龙头地位；新高单池核心资产若处于强主线，可获得同等主线分 |
| CoreAssetScarcity | 0-20 | P17 Q1 + Q4：核心资产 + 稀缺性 |
| FutureOptionality | 0-10 | 3-5 年终局空间 / 国产替代 / 产业份额 |
| NewDiscoveryBonus | 0-5 | 新方向早期发现加分 |
| RiskPenalty | 0-20 | 业绩爆雷、题材纯炒作、高位末期、流动性差、监管风险 |

分层：
- ≥75：P0 / A 类候选 → 写入 `A股观察/`，Human 复核后可触发初始调研；**不自动进入核心资产库**，需 P9/P17 深研或核心资产动态判定表确认；
- 60-74：P1 / B 类候选 → 写入 `A股观察/`，标记“需回调/价格跟踪”；Human 确认后进动态 Watchlist；若后续 P9/P17 深研显示资产质量更高，可在核心资产动态判定表里反向升级为 A 类核心资产；
- 45-59：P2 观察 → 报告记录，不建档；
- <45：跳过。

P17 v3 必须回答六问，且拆开输出“资产等级”和“当前机会标签”，尤其：
- Q1 是否核心资产；
- Q4 是否稀缺；
- Q5 是否有终局空间；
- Q6 处于右侧早期、中期还是末期。

#### 5.1 盘后复核校准规则

What’s Hot 的职责是快速发现“市场正在交易什么”，因此允许初筛误差。后续若出现手动深研报告或自动建档结果，必须允许反向校准：

- `What’s Hot A/P0` 但 P9/P17 深研显示证据不足 → 降为 `B类验证观察`，不进核心资产库；
- `What’s Hot B/P1` 但 P9/P17 深研显示资产质量与赔率更好 → 升为 `A类核心资产` 或 `A类高赔率资产`；
- 题材温度计 / 纯补涨股即使短线涨幅强，也不要混入核心资产库；
- 状态机中同时保留 `Agent评级`（热门入池口径）和 `核心资产判定`（深研口径），避免二者互相覆盖。

#### 5.2 候选表硬约束：双池与新高单池分表输出

每日报告的量化总表不能只列双池命中。至少包含：

1. `双池强抢筹`：单日 >8% 且新高，优先识别抢筹式上涨初期；
2. `新高单池核心复核`：新高但单日未涨超 8%，优先识别“涨了很多但仍在右侧早中期”的资产；
3. `温度计/情绪锚`：大市值强趋势但估值或兑现压力过高，只用于判断板块热度；
4. `剔除/噪音`：新高但与主策略弱相关、资产质量弱、或纯事件异常。

如果 `新高单池核心复核` 里出现已在核心资产库 / 历史 A/P0 / 明确 AI 主线核心资产的标的，必须进入 P17/P9 候选或至少写入“待刷新复核”，不能因为当日涨幅未达 8% 被遗漏。

---

### Step 6：生成 What’s Hot 报告

输出路径：`Eyes/Whats_Hot/YYYY-MM/Whats_Hot_YYYY-MM-DD.md`

```markdown
# What's Hot - YYYY-MM-DD

> 数据池：涨幅异动 X 只 / 新高 Y 只 / 跌幅 Z 只
> 粗筛后：A 类 N 只 / B 类 M 只 / P2 L 只 / 跳过 K 只
> 核心结论：今天 A股最强主线 + 美股映射是否有效

## 🚨 板块首发信号（SIS，如触发）
> 仅当某板块满足「近3日≥3只入池 + 龙头5日>30% + 明确产业催化」三条时输出；否则写"今日无 SIS"。
> 触发即启动组级别 P17-lite（`Brain/references/p17-core-asset.md` §0.7），结果写入当期报告。

| 板块 | 近3日入池数 | 龙头/5日涨幅 | 催化 | 中军 | 弹性龙头 | Choke Point | 势能阶段 | 裁决/先手动作 |
|:---|:---:|:---|:---|:---|:---|:---|:---|:---|

```yaml
sis:
  - sector: ...
    member_count_3d: ...
    members: [...]
    leader: ...
    leader_5d_gain: ...
    catalyst: ...
    roles: {anchor: ..., beta_leader: ..., choke_point: ..., value_repair: ...}
    stage: 第一波抢筹初期 | 第一波加速中段 | 第一波加速后段 | 退潮
    verdict: ...
    next_action: 启动组级别 P17-lite（p17 §0.7）；先定代表权，不逐只深研
```

## 🔥 今日主线与板块热度（P14-lite）
| 主线 | 龙头 | 来自池 | 美股映射 | 热度阶段 | 风险 |

## 🧭 主线代表权 / 龙头组候选预警
| 主线 | 中军/定价锚 | 弹性龙头 | 低估值补涨 | 二线价格发现 | 漂亮环节/Choke Point | 裁决 | 下一步 |
|:---|:---|:---|:---|:---|:---|:---|:---|

```yaml
mainline_groups:
  - theme: ...
    leader_anchor: ...
    beta_leader: ...
    value_repair: ...
    price_discovery: [...]
    prettier_chokepoints: [...]
    miss_type: data_seen_needs_escalation | escalation_miss | valuation_veto | evidence_gap
    next_action: 横向P9/P17；不触发买入
```

## 📊 量化总表（先量化，再判断）
> 必须分表展示：①双池强抢筹；②新高单池核心复核；③温度计/情绪锚；④剔除/噪音。

| 代码 | 公司 | Score | 队列 | 价格事件 | 美股映射 | 核心/稀缺 | 终局空间 | 风险扣分 | 结论 |

## 🚀 A 类机会（抢筹式上涨初期 · 放入 A股观察）
| 代码 | 公司 | Score | 主线 | Q1 | Q2 应得估值 | Q4 稀缺度 | Q5 终局空间 | Q6 阶段 | 三因子快照（业/卡/K） | 观察原因 |

## 👀 B 类机会（待回调 · 价格跟踪候选）
| 代码 | 公司 | Score | 主线 | 当前位置 | 回调击球区 | 三因子快照（业/卡/K） | 跟踪事件 | 是否建议进动态Watchlist |

> 三因子快照（2026-06-11 新增）：初筛级标注，用 `强/中/弱/未知` 三档即可（如 `中/强/强`），不要求打分——精确分数留给优先级排序与深研；目的是让"业绩、卡位、股性"三要点从入池第一天就可见。

## 🚨 退潮板块与风险点
| 板块/方向 | 代表股 | 风险信号 | 与持仓/Watchlist关系 |

## 🌍 美股映射层
- 美股强势方向如何映射 A股：
- 哪些 A股方向是美股验证后的补涨：
- 哪些 A股方向和美股背离，需要谨慎：

## 📤 A股观察池 / 自动建档队列
- 写入 `持仓与关注/A股观察/` 的 A 类，并同步更新 `持仓与关注/A股观察/A股Watchlist状态机.md`：
- 写入 `持仓与关注/A股观察/` 且建议价格跟踪的 B 类；状态机标记“需价格跟踪候选”：
- 自动建档任务输入：状态机中 `Agent评级=A/P0` 且 `建档状态=待自动建档` 的标的：

## 📝 降级说明（如有）
```

---

### Step 7：写回与归档

必须写入：
1. `Eyes/Whats_Hot/YYYY-MM/Whats_Hot_YYYY-MM-DD.md`
2. `Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_movers_YYYYMMDD.*`
3. `Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_newhighs_YYYYMMDD.*`
4. `Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_decliners_YYYYMMDD.*`

联动写回：
5. A/B 候选 → 默认先写入 `持仓与关注/A股观察/`，形成 Human-in-the-loop 中转层，并同步更新 `持仓与关注/A股观察/A股Watchlist状态机.md`。
6. A 类核心资产候选 → 状态机标记 `建档状态=待自动建档`，供北京时间 00:00 的 A股观察自动建档任务消费；是否写入核心资产库，必须等自动建档/手动深研/核心资产动态判定表确认。
7. B 类“需价格跟踪” → 状态机标记为价格跟踪候选；Human 确认后由 `SOP_Watchlist自动建档.md` 放入 `动态Watchlist/`。
8. `mainline_groups` → 写入报告正文，作为 `SOP_Watchlist自动建档.md` 的横向主线代表权审计输入；不得直接变成买入信号。
8.5 `sis`（若触发）→ 写入报告 `## 🚨 板块首发信号` 段，包含稳定主题键、累计成员与阶段；作为 `SOP_Watchlist自动建档.md` 的组级别 P17-lite 输入。
9. 已在持仓 / Watchlist 的异常涨跌 → 后续交给投资雷达 / 策略分析 / P6。

---

## 📦 产出物清单

| 文件 | 路径 | 说明 |
|:---|:---|:---|
| What’s Hot 报告 | `Eyes/Whats_Hot/YYYY-MM/` | 主报告：P14-lite + P17 A/B 分类 |
| 涨幅异动 Raw | `Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_movers_*` | 问财原始结果 |
| 新高 Raw | `Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_newhighs_*` | 问财原始结果 |
| 跌幅 Raw | `Eyes/Whats_Hot/Raw_Data/YYYY-MM/whats_hot_decliners_*` | 退潮/预警用 |
| A股观察池 | `持仓与关注/A股观察/` | Human-in-the-loop 候选沉淀 |

---

## 📁 路径速查

| 内容 | 路径 |
|:---|:---|
| 市场洞察 | `Eyes/市场洞察/YYYY-MM/` |
| 美股热门追踪 | `Eyes/美股热门追踪/YYYY-MM/` |
| P14 提示词 | `Brain/references/p14-sector-hunter.md` |
| P17 提示词 | `Brain/references/p17-core-asset.md` |
| What’s Hot 报告 | `Eyes/Whats_Hot/YYYY-MM/` |
| What’s Hot Raw | `Eyes/Whats_Hot/Raw_Data/YYYY-MM/` |
| A股观察池 | `持仓与关注/A股观察/` |
| 问财 A股脚本 | `Eyes/scripts/iwencai_stockpick.py` |

---

## ⚠️ 边界与反模式

**What’s Hot 不做：**
- 不直接输出买卖建议；
- 不把 A 类直接塞进动态 Watchlist；
- 不替代投资雷达；
- 不替代策略分析；
- 不把美股映射当作唯一理由，必须有 A股自己的价格事件与板块反馈。

**反模式：**
- 只看新高，不看当天涨跌异动；
- 只看上涨，不看跌幅/资金流出；
- 把题材跟风股当核心资产；
- P14 只写板块热闹，不落到 P17 A/B 个股；
- B 类没有回调击球区却进 Watchlist；
- 只因为毛利率低、商业模式不性感，就跳过市场已经买出来的中军/平台型主线代表；
- 只挖 Choke Point，不审计市场第一选择的龙头组。

---

## 🎯 定时任务（建议）

| 项 | 值 |
|:---|:---|
| 定时任务（在你的 Agent 宿主里创建）| `YMOS - What's Hot` |
| cron 表达式 | `30 15 * * 1-5` |
| 运行日 | 周一-周五 15:30（A股收盘 + 30 分钟落库缓冲） |
| 数据时间锚 | T+0 当日 A股收盘 |
| 下游消费 | A股观察池；Human 勾选后触发 Watchlist 自动建档；次日投资雷达读取 |

---

*版本：2026-08-02 · V4 开源扩展标记：SIS 仅写入按日报告，不再维护个人全局注册表；所有阈值仍属于作者 Profile，默认关闭。*
*历史版本：2026-06-11 · v2.4 · A/B 候选表新增"三因子快照（业/卡/K）"列（强/中/弱/未知 三档初筛标注）；配套优先级排序 v3.4 三因子首屏列与 P17 0.6 强制输出*
*历史版本：2026-05-26 · v2.3 · 新增主线代表权 / 龙头组候选预警：输出 mainline_groups，防止 Raw 看见主线但未升权成横向 P9/P17*
*历史版本：2026-05-11 · v2.2 · 对齐“动量发现 → 基本面证据链 → P17/P9 → 观察/建档/巡检”统一链路；保留新高单池复核与双池强抢筹分表输出*
*历史版本：2026-05-10 · v2.1 · 新高单池复核补丁：双池强抢筹与新高单池核心复核分表输出，避免 A类/准A趋势资产被单日涨幅门槛漏掉*
*历史版本：2026-05-10 · v2.0 · A股热门追踪重写：三池扫描 + 美股强映射 + P14-lite + P17 A/B 分类 + A股观察池 Human-in-the-loop*
*历史版本：2026-04-25 · v1.6 · 盘前 → 盘后链路重构*
