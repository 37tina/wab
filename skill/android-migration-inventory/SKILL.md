---
name: android-migration-inventory
description: Build a feature-semantic map plus high-risk behavior evidence pack for a frozen Android app, feeding Phase 4 with what the app actually does (feature map, behavior contracts, data relations, runtime-verified behavior chains, explicit gaps). Runtime is spent only on migration-prone behaviors; containers and pure displays are source-confirmed. Use before Android-to-HarmonyOS implementation; do not write HarmonyOS code.
---

# Android Migration Inventory (v3, feature-semantic paradigm)

**定位**：Phase 2 不是"把 Android 所有页面证明一遍"，而是给 Phase 4 做一张**功能语义地图 + 高风险行为证据包**。先看源码把 App 的功能和数据关系搞清楚，再挑最容易迁错的功能上 Android 真机验证行为链，最后交付"这个 App 到底应该怎么工作"的地图。UI 鸿蒙原生化，但业务行为不能漂移。

## Non-negotiable contract

- Models never approve, create `PASS`, or declare Phase 2 complete; all verdicts are machine-recomputed.
- No manual page enumeration or annotation occurs inside Phase 2.
- Every factual claim cites a frozen `file:line`, sealed runtime evidence, or both; otherwise `PENDING_CONFIRMATION`.
- 产物由真实脚本生成（LLM 只做分片填充与蒸馏输入，且必须过 `--validate` 闭环）。
- Runtime 防伪铁律不变：页面/行为绝不能凭"点过了"算数——foreground ∈ 目标包 且 结果断言匹配才算；uiautomator 诱发的伪 ANR 按 collector-induced 分类记录，不计为 app 缺陷。
- Evidence and assets are immutable; recapture or supersede with new IDs.
- 已知 GAP 必须显式（feature_id + reason），不允许静默吞掉。

Phase 2 automation ends at its machine Gate. The human review happens only after the machine Gate, when the controller enters `WAITING_HUMAN_REVIEW`.

## 九步流程

1. **开工**：消费 Gate 1 PASS 的 run、冻结 `scope.json`、Phase 2 工单（审批支持 `--approval-source task-mandate`，任务授权可登记）。`scripts/init_inventory.py` 初始化 + `scripts/attest_environment.py` 环境证明。冻结语义（与 controller 批次 4 一致）：**正式 run（`run_status: IN_MIGRATION`）期间禁止修改 Skill**——skill 哈希漂移即 TOOL_GAP；`--refresh-freeze` 仅在 run 未开始（`INIT`）或已结束（`CLOSED`）状态可用（重算哈希 + 更新 run-manifest + 记 decision-log）；运行中发现 Skill 缺陷走 TOOL_GAP（终止 run → 修复 → 新开 run）。
2. **扫源码分类**：`scripts/analyze_static_pages.py` 产出 surface-index（先分类：page / container / sheet / dialog / menu / reusable-component / viewmodel / repository / database / settings / system-capability），**防止普通 Compose 函数被当独立页面**；带接收者的 Compose 函数（`fun BoxScope.X()`）必须识别。`scripts/validate_static_analysis.py` 静态自检。
3. **功能地图**：`scripts/feature_map.py` 以**用户功能为中心**（不再以 Page-ID 为中心）生成 `feature-map.json`——每个功能含：feature_id / 名称 / 一句话语义 / source_refs(file:line) / surfaces[]（含 `is_container` 标注）/ data_objects / risk_level / verify_mode。**feature↔surface 绑定用显式映射 + source_refs 交叉校验，禁止子串匹配兜底**。scope 每个 included feature 必须有条目（功能覆盖门禁取代全仓 UNMAPPED=0）。
4. **行为契约**：`scripts/build_behavior_contracts.py` 骨架 + LLM 分片填语义列 + `--validate` 闭环。每条 BC 写清"用户想干什么 → 做了什么操作 → 哪个状态/数据变化 → 用户看到什么 → 重启后还在不在 → 有无系统副作用"（含 `operation_steps` 操作序列与 `result_assertions` 结果断言，供行为链消费）。
5. **分级验证**：`verify_mode=RUNTIME`（增删改/持久化/语言/主题/同步/权限/复杂设置——容易迁错的）vs `SOURCE_CONFIRM`（普通展示/跳转/容器宿主）。容器宿主页（MainScreen/DetailActivity 类）一律 SOURCE_CONFIRM——不为证明"被访问过"硬跑。
6. **行为链实跑**：`scripts/gmi_runtime.py --mode chain`（默认）只对 RUNTIME 功能按 BC 的 operation_steps 驱动，断言 result_assertions（如 `新增X → 列表出现X → 杀进程 → 重启 → X还在`）。**证据重点是结果，不是截图数量**：每链 = 操作日志 + 断言逐条判定 + before/after/restart 三点关键快照（`evidence/chains/<bc_id>/`）。复用已验证的实战能力：跳板级联导航 / 图标兜底 / 伪 ANR 防护（TTL 降频 + compressed）/ 稳定性双确认 / foreground 校验。产出 `runtime-evidence/runtime-chains.csv`。旧页面模式 `--mode pages` 保留兼容。
7. **源码↔runtime 对账**：`scripts/reconcile.py` 四态判定——`CONFIRMED`（声明且实测确认）/ `CONFLICT`（源码说有变化但实测断言 FAIL，需人工解释）/ `SOURCE_CONFIRMED`（容器/纯展示）/ `GAP`（没跑，note 记原因）。产出 `reconciliation.csv`。链 blocked（NAV_FAIL/ANR_BLOCKED 等）归 GAP 不是 CONFLICT。
8. **蒸馏交付**（一步到位，无候选表→正式表两段）：`feature-map.json` / `surface-index.csv` / `behavior-contracts.csv` / `data-relations.csv`（功能↔数据对象↔持久化位置）/ `reconciliation.csv` / `runtime-chains.csv` / `visual-memory.json`（per-surface 视觉基准：链快照截图引用 + ui-tree 摘要 + 色板聚合，`scripts/visual_memory.py` 从既有产物派生——参考 legacy screenshot/ui.xml/color-palette 写法，不新增采集）+ 关键源码定位 file:line / 已知 GAP。gmi.py 的 12 张候选表保留为参考附件（不再进门禁）。
9. **Gate 2（v2）**：`gmi_closure.py` 闭包（gate 数字 + artifact_hashes 哈希链——含 `reconciliation_sha256` 防篡改 + `gaps[]` + `conflicts_explained` 骨架）→ controller `validate_gate.py --phase 2` 检查六条：①功能覆盖（included ⊆ feature-map）②BC 完整（每 feature ≥1 行）③高风险验证（每 RUNTIME BC ∈ CONFIRMED/SOURCE_CONFIRMED/GAP带理由；CONFLICT 必须有 closure 解释）④数据无未知（无 high 风险 UNKNOWN 持久化）⑤GAP 明确（每条含 feature_id+reason）⑥闭包哈希链完整。**核心功能无未解释 GAP 即放行 Phase 3**。

## Work separation

Use focused logical lenses (feature mapping, behavior contracts, runtime chains, reconciliation, evidence administration). Outputs remain role-owned and independently recomputed. Record the real CodeArts task and artifact receipt required by the controller.

## Reference map

- [inventory-contract.md](references/inventory-contract.md): IDs, rows, and catalogs.
- [static-page-analysis.md](references/static-page-analysis.md): source denominator and runtime backlog.
- [android-cli-procedure.md](references/android-cli-procedure.md) and [evidence-contract.md](references/evidence-contract.md): formal runtime capture.
- [advanced-runtime-analysis.md](references/advanced-runtime-analysis.md): dynamic risks, side effects, and scenarios.
- [deterministic-page-gates.md](references/deterministic-page-gates.md) and [review-and-rework.md](references/review-and-rework.md): closure and failure routing.

## Agent 分派执行表（2026-09-01 增补：角色已定义于 roles-and-authority.md，此处规定怎么派）

大规模源码（>1万行）必须拆多 agent 并行/接力；小项目可合并但角色职责不变。

| 序 | 角色 | 职责一句话 | 产出物 | 依赖 | 并行 |
|---|---|---|---|---|---|
| 1 | inventory lead | 领工单/分号段/仲裁冲突 | 分片表+ENV-ID | — | 前置 |
| 2 | code-map agent ×N | 按模块出代码地图 | code-map-<module>.json | ① | 可并行 |
| 3 | business-rule agent ×N | 按模块出 BC 十字段 | bc-<module>.csv | ② | 可并行 |
| 4 | data-dependency agent | 全局数据/能力/第三方依赖 | data-relations.csv | ② | 与③并行 |
| 5 | runtime-state agent ×N | 按功能域真机取证 | chains/BC-*/evidence | ③ | 可并行 |
| 6 | visual-memory agent | 色板/ui_tree_summary/截图基准（**独立角色**，别让 code-map 兼） | visual-memory.json | ⑤ | 与⑤并行 |
| 7 | evidence administrator | 封 Evidence-ID/索引/哈希 | evidence-index | ⑤⑥ | 接力 |
| 8 | coverage checker | 终审覆盖/开返工 | closure report | ⑦ | 末置 |

**规则**：角色 2-6 每个可派多个实例（按模块/功能域分片，≤45 分钟/片）；同一 agent 不得兼任 2-6 中互为上下游的两个角色；visual-memory agent 是独立角色（CapyReader 教训：色板空集导致下游无视觉基准）。
