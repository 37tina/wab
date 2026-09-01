---
name: controller-core
description: 任意源平台到鸿蒙终端迁移的通用治理内核（四阶段门禁/人工审核/防伪返工）。所有路径套件的 controller.md 薄壳必须引用本文件。平台差异由各路径薄壳补充，本文件不涉及具体平台。
---

# 迁移控制器内核（平台无关）

一次迁移 run = 源程序 → 平台无关功能语义契约 → 鸿蒙目标端原生实现，经四阶段门禁推进。控制器冻结输入、签发工单、重算门禁、路由返工；**绝不亲自写目标端代码**。

## 核心等价契约（唯一判据，四阶段共用）

> UI 结构与交互可按鸿蒙原生规范改造；但用户意图、存储数据、业务计算、状态转换、可观察结果、持久化与副作用必须语义等价。不得以"更简单的目标端实现"为由豁免任何行为维度。

## Non-negotiable

- 模型永不放行：机器 `PASS` 是必要非充分条件，每个 Gate 后必须 `WAITING_HUMAN_REVIEW`，由人决定 `APPROVED / REWORK / APPROVED_DEVIATION / MANUAL_TAKEOVER`。
- 一切判定可复算：Gate 结论由脚本/确定性规则从密封证据重推，生产者证据不能自证。
- 证据不可变：旧产物不修改只取代（新 ID）；复验产生新记录。
- GAP 必须显式：每条含 feature_id + 原因；禁止静默吞掉或翻转为 PASS。
- 真实性（防作假，但接受细微偏差）：运行类结论必须有真实执行痕迹（命令、输出、截图、探针数据）；**允许**与预期的措辞/布局/性能级偏差；**不允许**虚构未执行的命令、编造输出、用演示数据冒充运行结果。无法执行时降级为 SOURCE_CONFIRM 并记 GAP，而不是编造。

## 四阶段状态机

| Phase | 职责 | 完成判据（Gate） |
|---|---|---|
| 1 迁移基线 | 冻结：功能范围（included/excluded 逐项裁决）、数据范围、关键业务能力、允许的平台替换、源码/构建产物指纹、双端环境、验收标准 | 冻结清单完整 · 范围无歧义 · 验收标准可执行 |
| 2 源端理解 | 功能语义地图 + 行为契约 + 高风险功能真机/真实运行取证 | 功能全覆盖 · 契约六要素完整 · 高风险已验证或显式记 GAP |
| 3 目标承载 | 按承载面搭壳（页面路由/弹层模态/容器不建壳）+ UI 蓝图 + 数据契约（interface-only）+ 构建/安装/启动冒烟 | 承载面全覆盖 · 数据契约无孤儿 · 冒烟链通过 |
| 4 实现与双端差分 | 按功能实现（原生优先）→ 双机/双端行为差分（源端为 oracle）→ DIFF 只修目标端并重放（≤2 轮转人工）→ 表面/UI 检查 | 断言全过 · 数据对账无未解释差异 · 视觉还原达标 |

## 失败路由

- 源端事实缺失/矛盾（页面、状态、转换、副作用）→ 回 Phase 2。
- 目标端模块/路由/载体/契约落点错误 → 回 Phase 3。
- 上游契约正确但目标实现或证据错误 → Phase 4 内修复。
- 同一单元 1 次初试 + 2 次自动修复仍失败 → `MANUAL_TAKEOVER`，不许靠删证据重置计数。

## 工单与留痕

每工单四段：MUST READ / MUST DO / MUST PRODUCE / FORBIDDEN，并绑定冻结的 skill 快照。正式 run（IN_MIGRATION）期间改 skill 属 TOOL_GAP：关 run → 修 → 新开 run。

## run 生命周期（状态机）

`INIT`（冻结中，可修 skill）→ `IN_MIGRATION`（P1-P4 执行中，skill/Gate/validator 全冻结）→ 每 Gate 后 `WAITING_HUMAN_REVIEW`（人工四选一：APPROVED / REWORK / APPROVED_DEVIATION（带偏差登记）/ MANUAL_TAKEOVER）→ 全 Gate 通过 `CLOSED`（产物封存）。中断（环境故障/内核重启）记 `RUN_INTERRUPTED` 决策后可恢复；skill 缺陷只能关 run 修完新开 run（禁止运行中改规则）。

## 冻结件清单（Gate 1 产出，全 run 只读）

scope.json（included/excluded + 理由 / 三条迁移政策 / test_seed / 双端环境实测参数 / 源码树哈希与 revision / 构建产物指纹与 SHA-256 / 验收标准具体化）· run-manifest · decision-log（追加制，含 TOOL_GAP 处置）· task-ledger · skill-freeze-manifest（本轮 skill 快照哈希）。后续任何阶段引用冻结值必须带指纹（scope_sha256）。

## Gate 重算与门禁绑定

- 每 Gate 判定 = 脚本从密封证据重推（validate_gate 类脚本），结论附 errors[]/warnings[] 与被验产物哈希；Gate 报告绑定 scope_sha256，改 scope 即 Gate 失效。
- 机器 PASS ≠ 放行：Gate 报告仅证明"机器可复核项全过"，人工审核独立裁决；机器 FAIL（fail-closed 口径）时人工可裁决通道：核实每条机器 error 属实（属实→返工）或属取证工具伪影（→登记定性 + 人工放行/APPROVED_DEVIATION，不许静默翻转机器记录）。
- 工单模板四段（MUST READ / MUST DO / MUST PRODUCE / FORBIDDEN）+ 绑定 skill 快照哈希；子工单（如 phase-02）带上游 Gate 报告快照。

## 超时治理与任务分发粒度（2026-09-01 增补：CapyReader 教训——120 分钟会话上限导致批次任务中途被杀）

**原则：时间不是约束，质量是。宁可更多子代理/更多轮续任，不降验证标准。**

### Phase 4 实现阶段：按页面/文件集分发（替代功能域批次）
- 每个子任务 = **一个页面**（或一个独立文件集），预估 ≤45 分钟内可完成
- 多个实现者并行（background-task 同时派发），Controller 统一验收合并
- **文件冲突规避**：
  - 页面专属文件互不重叠（pages/reader/*.ets vs pages/settings/*.ets）
  - 共享文件（路由表 Index.ets / EntryAbility / 数据层 Repository）由 Controller 统一维护——子任务只声明"路由表需加一行 xxx"，不直接改共享文件
  - 子任务完成 → Controller 汇总变更集 → 统一构建安装（子任务不各自构建，省时且防版本碎片）
- 分发前 Controller 必须产出《任务分片清单》：每片的页面/文件范围、蓝图引用、预估时长、产出物
- 每片仍须过 R7-R9 红线 + 真机走查（质量不因粒度变小而降低）

### Phase 2 盘点阶段：按源码模块并行
- 源码按模块/目录分片（如 8 个 Kotlin 模块 → 2-4 个 2A 并行，每人 2-4 个模块）
- 产物按模块分片写入：feature-map-<module>.json / bc-<module>.csv，Controller 合并去重
- **BC 编号冲突规避**：分片预留号段（模块A=0001-0099，模块B=0100-0199…），合并时全局校验唯一性
- data-relations / visual-memory 同样按模块分片，合并时交叉引用对齐

### 通用规则
- 任何子任务预估 >60 分钟 → 必须再拆分
- 会话被杀 → 产物在磁盘上不丢（如实在 implementation-ledger 记 partial 状态），续任从磁盘续作不从零开始
- 并行度参考：同时运行的实现者 ≤4（避免模拟器/构建资源争抢）
