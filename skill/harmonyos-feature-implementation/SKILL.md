---
name: harmonyos-feature-implementation
description: Implement HarmonyOS NEXT features from the frozen feature-semantic map, then verify behavioral equivalence by replaying shared semantic assertions (intent, preconditions, semantic_input, expected state change, observable result, persistence, side effect) on-device with platform-specific steps free to differ. Machine Gate 4 strictly judges behavior/data/side-effect parity; UI keeps high visual-identity and information-structure fidelity to the Android source — only platform-standard interactions (Navigation, Tabs, back, Dialog/Sheet, Toggle, Picker) may be natively re-expressed (controlled nativization, never free restyling); platform gaps route to human-adjudicated PLATFORM_DEVIATION. Use only after approved Gate 3.
---

# HarmonyOS Feature Implementation (v4, feature-semantic paradigm)

**定位**：拿着同一份行为考卷，在鸿蒙端把功能实现出来，再答一遍——**答对才算数（机器判定）**。视觉识别和信息结构对 Android 源应用**高还原**；仅 Navigation、Tabs、返回、Dialog/Sheet、Toggle、Picker 等平台标准交互允许原生化替换（受控原生化，非自由重设计——自定义实现须在 surface-contract notes 登记理由）；行为语义不许漂移；阅卷的是机器不是人。

> 同一份 BC 双端共享七段（intent / precondition / semantic_input / expected_state_change / observable_result / persistence / side_effect）；android_steps 与 harmony_steps 各自独立——**同意图、异路径、只验结果断言**（如语言切换：Android 走"三点→设置→语言"，鸿蒙直接原生设置列表皆可，locale 变英文 + 文案变英文 + 重启保持 = 过）。

> 批次 2 #85 两条硬边界：**Feature 工单是 Phase 4 唯一实施路径**（per-page 工单体系退役）；**data 断言的数据出口是冻结的 DebugSemanticProbe 独立探针**（Phase 3 生成、工单携带 expected hash、Gate 4 校验——应用侧自报数据通道已删除）。

## Non-negotiable contract

- Models never approve, create `PASS`, or declare Phase 4 complete; all verdicts are machine-recomputed — behavior equivalence is established by machine comparison of replayed assertions, never by model-authored claims.
- No manual page enumeration or annotation occurs inside Phase 4.
- Phase 4 automation ends at its machine Gate. The human review happens only after the machine Gate, when the controller enters `WAITING_HUMAN_REVIEW`.
- **行为断言 FAIL 就是 FAIL**：数据/业务计算/状态结果类断言失败不可通过任何解释翻转为 PASS——解释只能伴随，不能翻转。平台确实无法等价 → 重放器标 `PLATFORM_LIMITATION` → Gate 4 的 PLATFORM_DEVIATION 队列 → 人工裁决（decision-log），且仅平台能力差异可走此通道。
- 数据等价是**语义层**（语义对象读写集对等，如 todo.completed / sort_order / 删除状态 / 重启恢复），物理载体自由（Preferences vs RelationalStore 皆可，不比存储引擎与表结构）。
- 防伪铁律沿用：foreground ∈ 目标应用 + 结果断言匹配才算；重放器自带稳定性双确认与伪 ANR 防护；证据不可变，复验产生新 ID。
- 已知缺口显式（GAP / deviations / manual 队列），不允许静默吞掉。

## 七步流程（v5：双机行为差分范式）

> 流程顺序固化：**实现(3) → 双机差分(4) → 有 DIFF 走修复回环(7) → 回(4) 重验（≤2 轮，round 2 仍 DIFF 转人工）→ 全 MATCH → Surface/UI 检查(5) → Gate 4(6)**。双机差分在第 4 步内部完成，Gate 4 只做最终判定（不重做差分）。

1. **按功能开工单**：`issue_phase4_work_order.py`（v3）消费 Gate 3 PASS 与 7 类核心产物（①feature-map ②behavior-contracts（17 列含 semantic_input）③data-relations ④reconciliation ⑤runtime-chains+Phase 2 闭包 ⑥Phase 3 骨架（input-lock/闭包/注册表）⑦H4ENV），工单含 feature_manifest（每 included feature：verify_mode/bc_ids/data 读写集/reconciliation 计数/harmony_steps 留列 + **must_read 段**（批次 2 #85：behavior_contract_ids/android_source_refs/runtime_evidence_refs/data_relations/visual_memory_surface/p3_surface_plan 六类必读分母））与 **SOURCE_CONFIRM 覆盖清单** + **semantic_probe expected hash**（DebugSemanticProbe 冻结绑定）；CONFLICT 阻断签发（fail-closed）。审批 task-mandate 沿用。治理对齐 TOOL_GAP 冻结机制：正式 run（`run_status: IN_MIGRATION`）中**禁改 Skill**（哈希漂移即 TOOL_GAP，须关 run、修 Skill、开新 run）；`init_migration.py --refresh-freeze` 仅在 run 开始前（INIT）或关闭后（CLOSED）合法。
2. **初始化**：`init_implementation.py`（v4，输入面 7 类、旧 32 文件面与豁免集退役）→ 产出工作区 + **feature-dispatch.json（功能工单分派表）** + **surface-contracts.csv 空表骨架** + environments + harmony-project 快照 + stage-04-input-lock（schema 2.0）。
3. **Feature 工单签发与实现（唯一路径，原生优先规约）**：`issue_feature_work_order.py` 从 feature-dispatch 逐 feature 签发 FWO（含 must_read 段 + read_receipt_contract + semantic_probe expected hash；implementation-ledger 的四 owner 列必须先填，fail-closed；page-order 路径已退役）；实现按 `references/implementation-guidelines-v4.md`——**优先 HarmonyOS 官方原生组件与推荐交互模式**（Navigation+NavPathStack / Tabs / List+LazyForEach / CustomDialog/bindSheet / 系统返回 / Toggle / Select/TextPicker），自定义实现仅在原生不能表达时允许且必须在 surface-contract 的 notes 登记理由；数据读写走 Phase 3 data-contracts 接口 + **SemanticProbeRegistry.registerProbe 接线数据探针**（探针本体 DebugSemanticProbe.ets 禁改——Gate 4 校验工单 expected hash）；操作路径如实记录为 harmony_steps；实施声明（implementation-declarations.csv：feature 的 data 读写集 + harmony_persistence + 源码引用 + **consumed_bc_ids / consumed_source_refs / consumed_runtime_refs 读回执**——RUNTIME feature 无 consumed_source_refs 不得过 Gate 4）。
4. **双机行为差分验证（v5 核心，任务 #91/#93）**：`dual_verify.py`——Android 模拟器与鸿蒙模拟器先恢复到**同一语义前置状态**（两侧各自冷复位 + pre_state 校验；任一侧前置未建立 → 该 BC 四类一律 MANUAL 归人工队列，不算 DIFF——前置无法对齐≠行为差异），Android 按 android_steps（BC.operation_steps）、Harmony 按 harmony_steps **各自执行、分别采集，机器直接 A/B 对比四类结果**（observable / semantic data / persistence / side effect）——**比较结果不比较路径；不做 UI 像素 A/B**（observable 语义级文本集合/锚点对比；UI 仍按视觉记忆+蓝图验收）。DIFF 语义示例（语言切换）：Android 实测 locale=en 且重启仍 en，Harmony 实测 locale=zh → **DIFF 即 FAIL**。Android 侧是行为基准 **oracle**（live oracle cache：APK/seed/BC 行不变 → cache 命中不重跑；Harmony 是被验证方每轮真跑）；Harmony 侧复用 replayer 链执行（冷复位 → prepare_steps → precondition 校验，失败 PRECONDITION_FAILED 归人工队列；data 断言出口为 **DebugSemanticProbe 独立探针**），replay-results.csv 照常产出（Gate 4 ① 断言源不变）；无公开 API 可机器对比的副作用标 MANUAL（不是 MATCH），平台无法执行标 PLATFORM_LIMITATION（Gate 4 裁决通道沿用）。产出 **dual-diff-results.csv**（verdict ∈ MATCH/DIFF/MANUAL；`validate` 子命令校验格式；Gate 4 兼容输入——任一 DIFF → Gate 4 FAIL）；退出码 0=无 DIFF / 1=存在 DIFF / 2=执行受阻。
5. **Surface/UI 检查**：`surface_contract.py` 每功能一行——entry_reachable（入口可达）/ nav_pattern / **native_impl_check（静态扫描 R1-R6：手搓底栏/自绘导航栈/自造弹层底盘/自绘 Switch/自造 Picker/自造返回——只判模式用错，不做像素比较）**/notes；UI 视觉还原走 **visual-fidelity（视觉记忆+蓝图）** 验收（Gate 4 ⑤），与第 4 步双机差分"不做 UI 像素 A/B"同一口径。
6. **Gate 4（v4 六条，最终判定）**：`validate_stage4.py` 判定 → controller `validate_gate --phase 4` 独立重算（不信任报告自述）——
   ① RUNTIME 功能断言：每个 RUNTIME feature 的 BC 四类断言全 PASS（MANUAL 不算 PASS；PLATFORM_LIMITATION 须经裁决 accept；PRECONDITION_FAILED 行归 MANUAL_TAKEOVER 队列不算 PASS）
   ② 数据语义对账无未解释差异
   ③ PLATFORM_DEVIATION 队列全部人工裁决且 **FAIL 断言永不翻转**
   ④ SOURCE_CONFIRM 功能四门槛：实现存在 / 无 no-op/placeholder 桩（静态扫描）/ 源码可追溯 / 可构建
   ⑤ H4ENV 环境链完整（像素采集类可选）+ surface-contract 全 PASS + 闭包/输入锁哈希链沿用 + **visual-fidelity 全可见 surface 达标**（分母 = feature-map 中 kind ∈ page/sheet/dialog 的全部用户可见 surface，**不分 RUNTIME/SOURCE_CONFIRM**——每 surface 必须有 visual-fidelity.csv 结果行且 PASS；缺行/不达标 FAIL；Phase 2 无 visual-memory 基准时休眠）
   ⑥ **must_read_receipt（批次 2 #85）**：RUNTIME feature 的 consumed_source_refs 回执非空且为工单 must_read 子集（编造引用 FAIL）；DebugSemanticProbe 哈希与工单 expected 一致（实施者篡改探针 → FAIL）
   PASS → CLOSED。intent_pass_rate 单位混算已退役（runtime_bc_pass_rate 同口径）。dual-diff-results.csv 为可选输入（存在时任一 DIFF → FAIL；全 MATCH/MANUAL → 该断言源通过）。
7. **双机差分修复回环（任务 #93，与第 4 步成对）**：round 0 首轮差分有 DIFF → 读 **rework-orders.csv**（机器可读修复清单）→ Implementer **只修 Harmony**（Android 是 oracle 不动；APK/seed/BC 行不变 → oracle cache 命中不重跑 Android 侧；仅 Oracle 结果可疑才 --refresh-oracle 强制重采）→ 每修一轮 **--rework-round 递增**（带 --prev-results 承接上轮差异明细）回第 4 步重验；轮次自动记 **attempt-ledger**（只追加，哈希链防篡改）。**硬上限 2 轮**：round 2 仍 DIFF → **MANUAL_TAKEOVER 转人工**（进 Gate 4 人工队列，不再自动重试）；全 MATCH 才放行第 5 步。退出码语义同第 4 步（0=收敛 / 1=仍有 DIFF / 2=执行受阻转人工排查）。

## Retired (v4 唯一路径)

page_acceptance 页面验收体系、六维比较器家族（compare_behavior/compare_migration_unit/comparison_common/compare_screenshot/compare_component_tree/compare_geometry）、migration unit 三元组、32 文件输入面与 gmi 豁免集、HREV 自报 MATCH、prepare_uitest_probe 探针链——全部退役，不留双路径。

## Reference map

- [implementation-guidelines-v4.md](references/implementation-guidelines-v4.md): native-first rules, custom-exception registration, harmony_steps recording spec.
- [phase-4-handoff.md](references/phase-4-handoff.md) and [review-and-rework.md](references/review-and-rework.md): handoff and bounded repair (still applicable sections).
- [evidence-contract.md](references/evidence-contract.md): immutable evidence rules.
- [ui-test-snapshot-evidence.md](references/ui-test-snapshot-evidence.md): ArkUI Inspector / UiTest snapshot evidence rules (still applicable sections).

## Agent 角色强制矩阵（2026-09-01 增补：CapyReader 教训——曾用一个 agent 兼 UI+业务+资产，质量崩塌）

**必派独立 agent 的角色**（不可合并）：
| 角色 | 职责 | 分片方式 |
|---|---|---|
| 4-impl-lead | 分片清单/合并共享文件/统一构建 | Controller 兼任 |
| page-implementer ×N | **按页面分片**：一个页面=布局+组件+数据接线+导航入口（R10 四要件） | pages/<name>/ 专属目录 |
| visual-asset agent | 图标/图片资源迁移与 SymbolGlyph 映射（R8 执行者） | 全局资源目录 |
| merge-builder | 收集各片代码→统一构建→安装→冒烟 | 唯一构建者 |
| emulator-verification executor ×N | 按页面/BC 真机走查+截图+断言 | 与 page-implementer 错开（不能验自己的页面） |
| parity-acceptance agent | 终审：截图对比+**布局模式核对**+R7-R10 红线 | 独立（不能是任何创建者） |

**禁止**：
- 一个 agent 同时实现 3 个以上页面（会话超时风险+上下文污染）
- page-implementer 兼 visual-asset（会跳过图标直接文字——CapyReader 实锤）
- merge-builder 由 page-implementer 兼任（版本碎片）

**分片清单前置**：4-impl-lead 必须先出《页面分片表》（页面/文件范围/蓝图引用/预估时长），经 controller 确认后并行派发。
