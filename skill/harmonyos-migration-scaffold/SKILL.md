---
name: harmonyos-migration-scaffold
description: Build and verify a non-business HarmonyOS NEXT native UI foundation from a frozen feature-semantic map. Scaffolds one ArkUI carrier per UI surface (routes for pages, modal mounts for sheets/dialogs, no shells for containers), declares interface-only semantic data contracts, and passes a four-rule machine Gate 3 (carrier coverage, data-contract closure, smoke chain, environment chain). No business logic.
---

# HarmonyOS Migration Scaffold (v3, feature-semantic paradigm)

**定位**：Phase 3 不再"为每个页面建壳"，而是**给功能地图里的每个 UI 承载面装壳、给数据关系立接口**。输入是 Phase 2 的功能语义地图（feature-map.json），输出是一个能构建、能安装、能启动的 ArkUI 原生骨架——**一行业务逻辑都不写**（那是 Phase 4 的事）。UI 鸿蒙原生化，但行为的载体与数据进出口必须就位。

> Core equivalence contract: UI structure and interaction may be adapted to HarmonyOS native conventions, but user intent, stored data, business computation, state transitions, observable results, persistence and side effects must remain semantically equivalent. Phase 3 only prepares the native carrier.

## Non-negotiable contract

- Models never approve; all Gate 3 verdicts are machine-recomputed (controller independently re-derives the rules).
- No manual page enumeration or annotation occurs inside Phase 3.
- Phase 3 automation ends at its machine Gate. The human review happens only after the machine Gate, when the controller enters `WAITING_HUMAN_REVIEW`.
- Scaffolding never implements business behavior; surface shells stay contract-only, deterministic, and buildable. Native-first carriers（`Navigation`+`NavPathStack`、`Tabs`、`List`+`LazyForEach`、`CustomDialog`/`bindSheet`，从 `entry/src/main/ets/foundation/` 组合）红线不变；无 ViewModel、业务状态、请求、持久化、假数据。
- Phase 2 inputs are frozen by `stage-03-input-lock.json` (schema `scaffold-v3`); every input record is an absolute canonical path with its sha256. Tampering after closure is detected by the closure manifest.
- 数据契约是**语义层**（feature_id/data_object/interface 键，(feature, object) 组合展开）：Android 持久化仅作参考记录，鸿蒙侧物理载体（Preferences/RelationalStore）由 Phase 4 自由选择。
- No manual page enumeration; surfaces come from the frozen feature map (feature-map 为权威，navigation-relations 仅参考，skipped 透明记录于 surface-plan.json).
- Build/install/launch/smoke evidence must come from frozen command-line tools and the emulator, not previews or claims.
- 已知缺口显式登记（skipped surfaces / route hints），不允许静默吞掉。

## 五步流程

1. **拿工单开工**：消费 Gate 2 PASS 的 run 与功能地图三件套——`feature-map.json`（surfaces[] 含 kind: page/container/sheet/dialog/reusable-component 与 is_container）、`candidates/navigation-relations.candidates.csv`（跳转参考）、`data-relations.csv`（语义数据关系）。
2. **分面搭壳**（`init_scaffold.py`，v3 唯一路径；旧 main_gmi/legacy 路径已删除）：
   - `page` → 路由节点 + 页面壳（page_shell_id 用大写 ID `PSHELL-*`，组件符号保持驼峰）
   - `sheet`/`dialog` → 模态载体挂载到宿主页（宿主三层推断：nav 显式边 → 同 feature 页面 → 确定性兜底；来源透明记录）
    - `container` 与 `reusable-component` → **不建壳**（容器死锁的根治：透明宿主不需要证明）
    - 资产链三态（完整→校验 / 缺失空→跳过 / 残缺→报错）
    - **UI 蓝图（批次 3 #86 + 提交前自检 4-A）**：`attach_ui_blueprint` 给 surface-plan 每个用户可见 surface（routes/modals）冻结 `android_structure / preserve（UI_FIDELITY=HIGH 的机械表达：texts/content_descs/palette）/ native_carrier / native_component（原生组件映射：三 Tab 主页→Navigation+NavPathStack+Tabs+List+LazyForEach 等）/ custom_allowed+reason（默认 no，登记制）`；底栏 Tabs 特征多页命中时 tabs_owner 唯一仲裁。**Gate 3 承载面规则强制检查三字段非空（缺任一 FAIL，无豁免）**
3. **立数据接口**（`data_contracts.py`）：按 data-relations 聚合语义对象，生成 `data-contracts/<object>.json` + index——interface-only 契约（读写方向、Android 参考持久化），不规定鸿蒙物理实现。
4. **上锁与冻结**：`stage-03-input-lock.json`（inputs 六记录绝对路径+哈希、surfaces[].route_or_mount ∈ {route, modal@HOST, none}、data_contracts 展开条目、capability 种子）+ HENV 环境冻结（`freeze_environment.py`）+ 构建冒烟（`run_verification.py`；机制枚举 ROUTE/MODAL 与 ROUTE_PAGE/VISUAL_SURFACE 归并并存）。
5. **Gate 3（v3 四条）**：`validate_stage3.py`（v3 唯一路径）判定——
   ① 功能承载面覆盖：每个 verify_mode=RUNTIME 的 feature 至少一个非 container surface 有 route/modal 载体
   ② 数据契约无孤儿：data-relations 语义对象 ↔ data_contracts 双向闭合
   ③ 冒烟链：构建/安装/启动类别覆盖（TOOLCHAIN/CLEAN_BUILD/BUNDLE_CHECK/SIGNING_CHECK 单例 + INSTALL/LAUNCH per-device；ROUTE_SMOKE/SCREENSHOT_CAPTURE 为可选记录）
   ④ 环境链：HENV 冻结 + preflight 完整
   PASS → CLOSED + 闭包 manifest + v3 四项 attestations（real_file_review/contract_only/dependency_review/runtime_smoke）。controller `validate_gate --phase 3` 独立重算规则①②并复核报告一致性、工单身份链、闭包完整性、scaffold 快照与 rework 镜像。

## Work separation

architecture-lead（壳与路由）、navigation agent（注册表登记）、toolchain agent（构建与 lock 依赖）、environment freezer（HENV）、acceptance reviewer 各自留痕；roles 沿用 [roles-and-authority.md](references/roles-and-authority.md)。

## Reference map

- [phase-3-handoff.md](references/phase-3-handoff.md): Phase 3 handoff contract (v3 inputs, deterministic outputs, Phase 4 obligations).
- [scaffold-boundaries.md](references/scaffold-boundaries.md): permitted and forbidden code, including the native-foundation rules.
- [environment-toolchain.md](references/environment-toolchain.md): frozen commands and emulator.
- [verification-and-rework.md](references/verification-and-rework.md): evidence, tickets, and closure.
- [roles-and-authority.md](references/roles-and-authority.md): responsibility and receipt rules.

## Agent 分派执行表（2026-09-01 增补）

| 序 | 角色 | 职责一句话 | 产出物 | 并行 |
|---|---|---|---|---|
| 1 | architecture lead | 消费 P2 地图/出分面规则/冻结蓝图 schema | surface 分面清单 | 前置 |
| 2 | navigation-page-shell agent | 搭壳/路由表/模态挂载（纯结构，不写业务） | shells/*.ets + Index.ets | 主线 |
| 3 | public-UI agent ×N | **按页面分片**写蓝图四字段（对照 visual-memory，逐 surface 编写不退化） | surface-plan.json 分片 | 与②并行 |
| 4 | capability-contract agent | 数据契约 interface + 探针 + 主题层 | data-contracts/*.json | 与②③并行 |
| 5 | toolchain-scaffold agent | 构建链/签名/安装/冒烟 | HAP + 构建三证 | ②③④完成后 |
| 6 | architecture acceptance agent | 截图身份校验（防同质）/蓝图完整性/独立于创建者 | HVER + gate 快照 | 末置 |

**蓝图质量红线**：public-UI agent 写的 android_structure **禁止出现"结构描述退化"字样**——visual-memory 未覆盖的 surface 必须回溯源码写出具体组件树（读 Compose/XML 源码），写不出就标 GAP 留痕（CapyReader 教训：退化蓝图 → P4 无从对齐）。
