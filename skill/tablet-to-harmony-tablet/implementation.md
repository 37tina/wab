---
name: tablet-to-harmony-tablet-implementation
description: 按冻结契约在鸿蒙平板端实现功能，并与 Android 平板源端做多断点双端行为差分（含分栏行为断言），DIFF 只修鸿蒙侧、≤2 轮转人工。用于本路径 Phase 4；仅在 Gate 3 批准后使用。
---

# 平板 → 鸿蒙平板 实现与双端差分（薄壳）

## 引用

- 执行基线：`skills/_shared/verify-core.md`（双端行为差分四维 + 修复回环通用内核；android 套 v5 双机差分范式已平台无关化于其中——Feature 工单唯一路径、同一 BC 双端共享语义段、四类结果差分、Android 为 oracle、DIFF 只修 Harmony、≤2 轮转 MANUAL_TAKEOVER、行为断言 FAIL 不可翻转全部继承）。
- 形态标准：`skills/_shared/scaffold-core-tablet.md`（断点/分栏锚点）。

## 本路径差异（在双机差分范式之上）

1. **多断点差分矩阵**：每条 RUNTIME 契约至少在两个断点场景重放——`md`（平板竖屏）与 `lg`（平板横屏）；两端各自用真实手段制造窗口形态（Android 平板 AVD：旋转 + `--windowingMode`；鸿蒙平板模拟器：旋转，自由窗能力实测为准）。同一 BC 的断点场景两端必须一致，否则该轮归 PRECONDITION_FAILED 进人工队列（前置无法对齐 ≠ 行为差异）。
2. **断点场景对齐口径**（前置对齐的平板特化）：断点按**语义档位**命名对齐，不按像素尺寸。两端各自建立"档位制造脚本"并冻结——Android 侧=指定 AVD 分辨率+方向/窗口模式命令，鸿蒙侧=模拟器旋转/窗口操作；每轮重放前各自 dump 窗口宽度档位（Android `dumpsys window` 实测 / 鸿蒙侧以截图+断点日志）入证据。档位对不上即 PRECONDITION_FAILED。
3. **分栏行为断言（本路径核心新增，入 observable 类）**：List-Detail 契约在 md/lg 下断言"选中列表项 → 右侧内容区更新为该条目（左栏条目仍可见）"，而非整页替换；sm 下断言整页跳转 + 返回仍见列表。断言锚点：右侧区域出现条目标识文本 + 左栏列表节点仍在 ui-tree（语义级，不做像素 A/B）。
4. **形态漂移即 DIFF**：目标端在契约声明的断点下出现错误形态（lg 仍单栏拉伸、分栏右侧空白无占位）→ 记 FORM_FACTOR_DIFF，按"载体落点错误"路由：壳错回 Phase 3，行为错 Phase 4 内修（见 controller.md 路由）。as-is 口径下源端为拉伸形态时，目标端升级形态不构成 DIFF，但须比对 AMPLIFY_DEVIATION 清单已获人工批准。
5. **平板特性断言口径**：多窗（分屏态数据/状态恢复）、拖放（拖 A 入 B 后 B 的语义集合变化；Android ClipData MIME ↔ 鸿蒙 UDMF 类型按数据契约比对）、键盘（快捷键触发的语义结果）照常走四类结果差分；手写笔压感/倾斜在鸿蒙模拟器不可注入 → PLATFORM_LIMITATION 人工裁决，禁止 touch 冒充笔迹证据。
6. **iPad 源（ipad_static）降级差分**：oracle 侧无运行 → 差分退化为"静态契约比对（BC 断言 vs 鸿蒙实测）+ 鸿蒙端运行取证"，dual-diff-results 的 verdict 增 `STATIC_BASE` 态（不算 MATCH，须人工复核）；此降级必须已获 Gate 1 冻结批准。
7. **手机→平板语义放大修复**：amplify 口径下新增的分栏/并排形态引入的回归（如分栏下返回键行为、双栏选中态持久化、列表滚动位置）按普通 DIFF 修复回环处理——放大不是豁免，语义断言（数据/状态/结果）与手机强度一致。

## 多窗/窗口变化状态保持断言（persistence 维度的平板特化）

- 触发手段：两端各自执行一次"契约操作中途改变窗口形态"（Android 平板 AVD：旋转或 `--windowingMode 3/5` 切入分屏/自由窗；鸿蒙平板模拟器：旋转，自由窗以实测为准）——改变后断言语义状态仍成立（选中项、草稿、滚动位置、过滤条件）。
- 断言锚点：窗口变化事件后目标端 ui-tree/数据探针读出的状态集合与变化前一致（语义级），禁以"未崩溃"代替状态保持。
- 双端窗口变化手段不可对齐时（一端无自由窗能力），该轮归 PRECONDITION_FAILED 人工队列，不得单端假对齐。

## 差分产物路由速查（本路径增量）

| 差分产物 | 判定 | 路由 |
|---|---|---|
| FORM_FACTOR_DIFF（断点下形态错/分栏右侧空白） | 壳缺陷 | 回 Phase 3 |
| 分栏行为断言 FAIL（右侧未更新/左栏消失） | 行为缺陷 | Phase 4 内修复回环 |
| AMPLIFY_DEVIATION 未批准即放大 | 流程违规 | controller 驳回工单 |
| 笔/压感类 PLATFORM_LIMITATION | 平台能力 | 人工裁决（禁 touch 冒充） |

## 最小验证设想

在 Android 平板 AVD 与 DevEco 平板模拟器上对同一条"新增笔记 → 列表出现 → 选中查看详情 → 重启数据保持"契约做双断点双端差分：Android 侧（oracle，横竖屏各一轮）产出断言基线；鸿蒙侧验证 lg 分栏断言（右侧更新 + 左栏仍在）与 md/lg 两形态下持久化一致；人为在鸿蒙侧造一个分栏缺陷（漏 splitPlaceholder）验证 FORM_FACTOR_DIFF 能被机器捕获并走修复回环。源端样本可取 Android 官方大屏 codelab 工程（见参考），保证双端可真实运行。

## 参考（调研来源，2026-09 访问）

- 内核：`skills/_shared/verify-core.md`（四维差分/前置对齐/修复回环）、`skills/_shared/scaffold-core-tablet.md`（断点/分栏行为锚点）
- 华为官方：Navigation 分栏行为（路由只替换右侧的断言依据）https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-navigation-navigation
- Android 官方：多窗口支持（`--windowingMode` 制造窗口形态）https://developer.android.com/develop/ui/views/multi-window
- Android 官方：平板应用质量标准（大屏验收矩阵生态对照）https://developer.android.com/docs/quality-guidelines/tablet-app-quality
- 最小验证可跑例：Android 大屏 codelab https://developer.android.com/codelabs/large-screens ；自适应布局 codelab https://developer.android.com/codelabs/adaptive-layouts
