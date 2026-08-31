---
name: tablet-to-harmony-tablet-controller
description: 治理"平板应用（Android 平板/iPad）→ 鸿蒙平板"的一次迁移 run（四阶段门禁/人工审核/防伪返工）。用于该路径的 run 初始化、阶段推进与返工路由；禁止在控制器角色里写鸿蒙代码或亲自采集证据。
---

# 平板 → 鸿蒙平板 迁移控制器（薄壳）

## 引用

- 必读内核：`skills/_shared/00-CONVENTIONS.md`、`skills/_shared/controller-core.md`（四阶段状态机/核心等价契约/失败路由/工单留痕全部继承，本文件不重复）。
- 方法论载体：android-to-harmony-phone 现有四件套（`skills/android-to-harmony-phone/`）是本路径的可执行基线——init/issue/validate 脚本族直接复用，差异由本壳的裁决参数注入。

## 本路径差异（在内核之上的增量）

1. **双源入口**：源端为 Android 平板（首选，可真机取证）或 iPad（无 mac，运行取证不可用）。Gate 1 必须先裁决 `source_profile ∈ {android_tablet, ipad_static}` 并冻结——两条源的 Phase 2 证据强度不同（见 inventory.md），验收标准随 source_profile 分别冻结。
2. **形态冻结进 Gate 1**：除功能/数据范围外，必须冻结**断点验收矩阵**——目标端至少验证 `md`（平板竖屏）与 `lg`（平板横屏）两个断点场景，sm（分屏/自由窗落入）为可选加分项但需显式 included/excluded。未冻结断点矩阵的 run 不得进 Phase 2。
3. **断点矩阵的最低场景集**：矩阵中每个 included 断点场景必须绑定可复现的制造手段（鸿蒙平板模拟器旋转 / 窗口调节，能力以 HENV 冻结实测为准）；手段不可复现的断点场景不得写入矩阵（写进去就是 Phase 4 无法执行的验收标准）。
4. **语义放大裁决**：若源端是"手机拉伸型平板应用"（无分栏/多窗/拖放/笔输入任何平板特性，见 Phase 2 形态取证），Gate 1 须裁决迁移口径：`as-is`（等价拉伸，形态不升级）或 `amplify`（升级为分栏/并排形态，形态变化逐面登记 AMPLIFY_DEVIATION 供 Gate 4 人工裁决）。禁止 Phase 3/4 擅自放大或擅自不放大。
5. **iPad 源降级声明**：ipad_static 的 run，Gate 2 完成判据中"高风险已验证"降为"高风险已 SOURCE_CONFIRM + 运行类 GAP 全部显式带因"；Gate 4 差分的 oracle 侧只有静态断言（无运行 A/B），双机差分降级为"静态契约比对 + 鸿蒙端运行取证"，此降级必须在 Gate 1 冻结并经人工批准。
6. **返工路由增量**：断点行为差异（某断点下布局形态/分栏行为与契约不符）归"目标端载体落点错误"→ 回 Phase 3；形态正确但选中/数据行为错 → Phase 4 内修复。手写笔/多窗等模拟器不可注入的能力，走 PLATFORM_LIMITATION → 人工裁决，不许伪证。

## Gate 判据速查（本路径叠加项）

| Gate | 手机基线判据 | 本路径叠加 |
|---|---|---|
| Gate 1 | 范围/环境/验收标准冻结 | + source_profile 裁决 + 断点验收矩阵 + as-is/amplify 口径 +（ipad_static 时）降级批准 |
| Gate 2 | 功能全覆盖/契约六要素/高风险已验证 | + 形态取证（form-factor-evidence）覆盖矩阵全部断点场景的**源端对应面** |
| Gate 3 | 四条基线判定 | + breakpoint_plan 三字段齐全 + 分栏占位声明 + 双断点启动冒烟 |
| Gate 4 | 断言全过/对账/视觉 | + 多断点差分矩阵全执行 + 分栏行为断言过 + FORM_FACTOR_DIFF 清零或转人工 |

## 最小验证设想

用 Android 平板 AVD 上的一个小型 List-Detail 应用（笔记/待办类，可取 Android 官方大屏 codelab 工程，见下参考）跑一次完整 run：Gate 1 冻结 md+lg 断点矩阵与 as-is/amplify 口径 → Gate 2 平板 AVD 取证（含旋转取证）→ Gate 3 产断点形态契约 + Navigation 分栏壳 → Gate 4 双端差分含分栏行为断言。工具链见 inventory.md/scaffold.md。

## 参考（调研来源，2026-09 访问）

- 华为官方：平板应用开发最佳实践（一多/多窗/分栏基线）https://developer.huawei.com/consumer/cn/doc/best-practices/bpta-pad-guide
- 华为官方：响应式布局（断点与四类样式）https://developer.huawei.com/consumer/cn/doc/best-practices/bpta-multi-device-responsive-layout
- Android 官方：平板应用质量标准（验收矩阵的生态对照）https://developer.android.com/docs/quality-guidelines/tablet-app-quality
- Android 官方：大屏适配文档区（sw600dp/窗口模式/拖放）https://developer.android.com/develop/ui/views/layout/large-screens
- Apple 官方：SwiftUI `horizontalSizeClass`（iPad 分栏判定的源端语义）https://developer.apple.com/documentation/swiftui/environmentvalues/horizontalsizeclass ；UIKit `UISplitViewController` https://developer.apple.com/documentation/uikit/uisplitviewcontroller
- 最小验证可跑例：Android 官方大屏 codelab（"Support different screen sizes"）https://developer.android.com/codelabs/large-screens ；自适应布局 codelab https://developer.android.com/codelabs/adaptive-layouts （标题以页面为准）
