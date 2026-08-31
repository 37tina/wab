---
name: legacy-to-automotive-implementation
description: 传统桌面软件迁鸿蒙车机的实现与双端差分薄壳：桌面端 oracle 取证 vs 车机端重放、驾驶安全四断言的差分判定、源端取证不可用时的三态降级验收（参照 ios 路径模式）、模拟器不可得时的降级验收。Phase 4 使用。
---

# legacy-to-automotive · implementation 薄壳

## 引用

- `skills/_shared/verify-core.md`（双端行为差分四维 + 修复回环通用内核；Phase 4 判据：断言全过/对账无未解释差异/视觉还原达标）
- `skills/_shared/scaffold-core-automotive.md`（安全约束规约四断言 + 环境与工具/降级策略）
- `skills/_shared/inventory-core.md`（对账四态，车机端同口径复用）

## 本路径差异（双端差分：桌面 oracle vs 车机被验证方）

- **oracle 在源端桌面**：按 inventory.md 取证工具（GammaRay/pywinauto/CDP）跑行为契约操作序列，采断言 + 前后快照；oracle 结果冻结缓存，源程序/种子数据/契约行不变则不重跑。
- **车机端重放**：同一契约的 harmony_steps（交互范式重设计后的路径）在座舱模拟器/实车执行；`hdc shell uitest dumpLayout` 组件树 + `snapshot_display` 截图 + DebugSemanticProbe 类数据探针（沿用 android 套范式）采集。**比较结果不比较路径**：同意图、异交互、只验结果断言（数据/状态/持久化/副作用）。
- **驾驶安全四断言的差分判定**（在行为等价之外叠加）：
  - 遮挡：dump 组件树核心控件 bounds 与冻结遮挡矩形求交，交集非空 → FAIL。
  - 行车状态：行车态注入（官方 Mock/电源信号工具；行车工况 API `PENDING_CONFIRM`）→ 管控清单功能必须呈现禁用/降级/替代；注入不可得 → 该断言记 GAP，不算 PASS。
  - 最小交互：harmony_steps 步数与 Gate 1 冻结门槛比对；超步 → 回交互重设计（回环算 DIFF 类）。
  - 音频焦点：声明占用的 feature 用官方音频抓流工具核对焦点行为（无音频 feature 核对"零占用"）。
- **交互差异大的修复策略**：DIFF 定位只修车机端（桌面 oracle 不动）。行为语义 DIFF（数据/状态错）→ 实现修复；纯交互形态差异（路径不同但结果断言一致）→ 不是 DIFF，登记 decision-log。≤2 轮修复回环，round 2 仍 DIFF → MANUAL_TAKEOVER。
- **视觉还原口径**：不做像素 A/B；车机端按"信息结构还原 + 官方车机 HMI 规范达标"验收（分栏/多窗三态/字号目标/深浅模式），依据 scaffold-core 组件规约。
- **契约反推条的差分（CONTRACT_INFERRED 痕）**：oracle 侧来自黑盒反推的契约，其 verdict 为 MATCH 时**不算自动通过**——须附原始反推证据（操作序列 + 状态差对拍）供人工复核，复核通过才闭包；MEDIUM/LOW confidence 条目只出 GAP/人工清单，禁入自动差分。

### 源端取证不可用的三态降级验收（参照 ios 路径模式）

| 源端状态 | oracle 口径 | 验收规则 |
|---|---|---|
| 源端可运行取证（正常态） | 桌面运行证据（冻结缓存） | verify-core 标准四维差分 |
| SOURCE_CONFIRM（有源码、取证工具不可得） | 契约文本 + 源码锚（file:line） | 目标端差分 vs 契约断言；源码锚漂移才回 Phase 2 |
| GAP（无源码无运行，或反推 MEDIUM/LOW） | 无 oracle | 目标端自证（车机模拟器取证），对账停 `SELF_ASSERTED_ONLY`，**不许自动闭包为 CONFIRMED**；人工 APPROVED_DEVIATION 放行或继续挂 GAP |

降级必须已在 Gate 1 冻结批准；三态混排时逐契约行标注，禁止整 run 笼统降级。

**模拟器不可得的降级验收（如实执行，禁止冒充）**：按 scaffold-core 降级策略逐级执行——① 手机/平板模拟器跑通行为断言（语义等价可验）+ 分栏/多窗代码层断言（`GridRow` 断点、`SideBarContainer` 结构）；② Previewer 3402×1620 画幅目检（支持度 `PENDING_CONFIRM`）；③ 录屏人工评审。降级 run 的 Gate 报告必须标注："车机形态类断言（行车态/遮挡/焦点/真实分辨率）未在座舱环境验证，全量 GAP"。

## 最小验证设想

Qt 计算器双端差分：桌面端 pywinauto/GammaRay 跑"7+3×2=13 → 清零 → 重启后历史列表含该记录"；车机端座舱模拟器以触屏路径重放同断言（结果 13、历史持久化）；叠加四断言（数字键不落遮挡区、行车态下"历史查看"可用而"语音播报结果"降级为停车后可用——按冻结的管控清单）。降级演示：对同工程再跑一轮"源端取证不可用"三态链（SOURCE_CONFIRM 静态比对 + SELF_ASSERTED_ONLY 挂 GAP），验证降级验收不冒充。模拟器不可得时演示手机模拟器行为差分 + 布局断言，并明示降级。

## 参考（调研来源，2026-09 访问）

- 内核：`skills/_shared/verify-core.md`（四维差分/修复回环）、`skills/_shared/scaffold-core-automotive.md`（四断言/降级策略/官方工具链）
- 降级模式参照：`skills/ios-to-harmony-phone/implementation.md`（三态验证 + SELF_ASSERTED_ONLY 口径出处）
- 源端取证工具：GammaRay https://github.com/KDAB/GammaRay ；pywinauto https://github.com/pywinauto/pywinauto
- 华为官方：智能座舱 2.0 工具专区（Mock 注入/录屏/音频抓流）https://developer.huawei.com/consumer/cn/overview/ICS-v2
- 生态对照：Android for Cars https://developer.android.com/training/cars
- 最小验证可跑例：Qt 官方计算器示例 https://github.com/qt/qtbase/tree/dev/examples/widgets/widgets/calculator
