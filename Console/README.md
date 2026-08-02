# YMOS Console — Reader + 操盘层

Console 将 Reader、买卖决策台和交易计划台放在同一个本地服务中，但三个页面的语义归属不同：Reader 是投研层的阅读入口；后两个工作台属于操盘层，把策略内核的判断变成 Human 可确认、可追溯的计划与动作记录。

| 页面 | 用途 | 主要产出 |
|---|---|---|
| Reader | 阅读投研、策略内核与状态产物 | 只读 |
| 买卖决策台 | 建立并维护单笔交易生命周期 | `Brain/买入卖出决策/` |
| 交易计划台 | 盘前确认计划，盘中记录偏差 | `Brain/交易计划/` |

## 正式运行

```bash
cd Console
cp config.example.json config.json
python3 server.py
```

访问 <http://127.0.0.1:5273>。需要 Python 3.9+，本地后端只使用标准库。

直接打开 HTML 只用于界面预览，不会写入正式 Markdown。公开仓库不包含公共嵌入版、云端账户或浏览器数据库方案。

## Markdown-first

- `vault_root` 留空时使用仓库根目录，也可指向用户自己的 YMOS vault。
- `plan_dir`、`audit_dir`、`trade_dir` 决定三个可写目录。
- Reader 只读取 `reader_pages` 声明的目录。
- 浏览器状态不是交易与持仓真相源；服务端 Markdown 才是。
- 成功保存后，页面应重新读取最新文件并刷新派生状态。

## Reader 如何发现后续产物

默认的市场洞察、投资雷达、策略分析、交易记录、持仓和 BrainStorm 目录已经预先登记。它们使用递归模式，因此：

- 新增 `YYYY-MM` 月份目录、专题目录、标的目录或更深层子目录后，刷新 Reader 即可出现；
- 目录启动时还不存在也没关系，后续由 Agent 创建后同样会被发现；
- 不需要为每个月修改配置，也不建议提前生成一堆空目录。

如果用户新增的是一条**默认配置完全不知道的新产出路径**，在 `config.json` 增加最简入口即可：

```json
{
  "reader_custom_paths": [
    { "label": "我的专项研究", "path": "Brain/专项研究", "mode": "tree" },
    { "label": "外部投研笔记", "path": "~/Documents/Research", "mode": "tree-text" }
  ]
}
```

相对路径以 `vault_root` 为基准，绝对路径和 `~` 也支持。重启 Console 后，这些目录会自动进入 Reader 的“自定义工作区”；其后新增的子目录和文件只需刷新页面。需要多页面、白名单或“仅最近月份”等高级布局时，再修改 `reader_pages`。

公开版在市场洞察、投资雷达和策略分析目录内各放一份 `_示例/` 脱敏合成产物，让首次打开 Reader 的用户能直接看到报告结构。文件带有 `ymos_sample: true`、`demoOnly: true` 和 `excludeFromKernelAudit: true`，不应被策略路由、P11 复盘或真实统计当作运行证据。

买入逻辑建档后即生成决策文件；建仓准备会复现论点、失效信号和退出规则，允许 Human 在成交前修订。成交、加仓、减仓、退出规则调整和平仓都以事件追加，不能覆盖历史。

持仓总览从活动单笔文件聚合股数和成本，并从 `买卖决策_状态机.md` 恢复最近一次已保存行情快照。价格过期时显示旧值与更新时间，不能伪装成实时行情。

## 规则

`rules.example.json` 只演示 UI 规则结构。公开版不提供策略阈值默认答案。长期有效规则应写入 `Brain/策略配置/` 的 Strategy Profile，再投影到 Console 所需规则；投影结果不能反向改写 Profile。

## 数据与安全

- 服务仅绑定 `127.0.0.1`。
- 写入文件名与目录由服务端生成，前端不能提交任意路径。
- 行情、账户资金变化和规则调整记录时间、来源与旧值/新值。
- Agent 可读取状态快照做体检，但交易动作始终需要 Human 确认。

数据结构见 `TRADE_DATA_CONTRACT.md`。回归测试：

```bash
python3 Console/tests/test_trade_api.py
```
