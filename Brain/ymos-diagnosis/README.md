# ymos-diagnosis · YMOS 内嵌模块

核心诊断 Skill 与独立 `ymos-diagnosis` v2.0 保持一致，只输出结构诊断，不写运行文件。这里采用版本化内嵌副本，不是 Git submodule。

YMOS 额外提供 `YMOS_ADAPTER.md`，在用户确认诊断报告后，将结论映射成 Strategy Profile、驱动清单、节奏和模块启停草案。

确认后的个人诊断报告固定保存到 `Brain/内核审计/诊断记录/YYYY-MM/YYYY-MM-DD_结构诊断.md`。该目录属于用户运行数据，不进入 Git；未获 Human 确认的报告只保留为会话草案，不作为 Profile 来源。

```text
SKILL.md + agents/ + references/  上游诊断核心（与独立仓完全一致）
          ↓ 已确认报告
YMOS_ADAPTER.md              YMOS 配置适配
          ↓ Human 确认
Strategy Profile / rules 投影 / 模块清单
```

## 使用已有投资日志

核心诊断默认不读取用户全仓历史。用户主动提供旧日志、复盘或 BrainStorm 时，先运行 `../../BrainStorm/SOP_历史投资资料入职.md`：

```text
历史资料索引 → 阶段梳理 → 与当前诊断问题有关的代表原文 → 结构诊断
```

这样可以对照用户当前自我描述与过去实际记录，但诊断仍必须向 Human 确认“旧观点现在是否继续认可”。不得从历史日志直接生成生效 Profile，也不得为了支持当前结论只挑一致样本。

## 边界

- 核心诊断不读取用户全仓历史，除非用户主动提供。
- 历史资料只按索引读取相关样本；原件不改写，不全量塞入上下文。
- 适配器只能起草配置，不能替用户填数值。
- 写入 Profile、P/SOP 或 Console 规则必须获得 Human 确认。
- Day 0 不凭空定位历史拦截点；周期审计负责消费真实运行证据。

上游版本记录见 `UPSTREAM_VERSION`。

## 双仓同步约定

- 可移植核心：`SKILL.md`、`agents/`、`references/`，发布时必须与独立仓同版本逐文件一致。
- YMOS 适配层：本 README、`UPSTREAM_VERSION`、`YMOS_ADAPTER.md`，只存在于 YMOS 主仓。
- 更新顺序：先确定独立核心版本，再同步到这里，最后分别检查并推送两个仓库。
