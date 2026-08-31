---
name: watch-to-harmony-watch-controller
description: 手表应用（watchOS / Wear OS）到鸿蒙手表（HarmonyOS WATCH）迁移的治理薄壳。当源项目为 watchOS 应用（SwiftUI/WatchKit）或 Wear OS 应用且目标端为鸿蒙手表时使用本套件；不适用于 iOS/Android 手机端为主的项目（走对应手机套件），也不允许跳过 Gate 直接写鸿蒙代码。
---

# watch-to-harmony-watch 迁移控制器（薄壳）

## 引用

先完整阅读：
- `skills/_shared/00-CONVENTIONS.md`（撰写/执行规范）
- `skills/_shared/controller-core.md`（四阶段门禁与失败路由，全部继承）
- `skills/_shared/inventory-core.md`（Phase 2 方法论）

本文件只声明本路径差异，不重复内核内容。

## 本路径差异

### 双源入口（Gate 1 必须先裁决并冻结 source_profile）

| source_profile | 源端形态 | Phase 2 证据强度 |
|---|---|---|
| `watchos_static` | watchOS 应用（SwiftUI/WatchKit），无 mac/Xcode | 全静态；运行类全降 SOURCE_CONFIRM + GAP |
| `wearos_runtime` | Wear OS 应用（Android 技术栈），adb + Wear OS AVD 可用 | 可真实运行取证，允许 CONFIRMED（与手机路径同强度） |

- 两条源的验收标准在 Gate 1 分别冻结；wearos_runtime 不得继承 watchos 的降级豁免（有环境却声明降级 = 伪降级，Gate 2 驳回）。
- watchos_static 的源端降级策略必须写进 run-manifest，开工即冻结（细则见下）。

### 源端降级策略（watchos_static 专用，写进 run-manifest）

- **源端运行取证不可用**：本路径预设源端无 mac/Xcode/watchOS 模拟器，Phase 2 不得出现任何 watchOS 侧"运行输出"；所有 verify_mode 强制降级为 `SOURCE_CONFIRM`，原定 RUNTIME 的功能逐条登记 `GAP(feature_id, reason=NO_WATCHOS_RUNTIME)`。
- **oracle 降级为双静态锚**：行为契约以「源码 file:line + Apple 官方文档语义」双锚为准；两者冲突以源码为准并记 CONFLICT 风险。
- **不对称豁免**：源端无环境允许降级（如实声明），目标端（鸿蒙手表）无环境**不允许**降级为纯静态——DevEco 手表模拟器/Previewer 为基线要求，缺失记 `TOOL_GAP` 停工。

### PLATFORM_DEVIATION 通道（本路径高频，人工裁决五类）

| # | 源端能力 | 目标端现状（调研） | 默认处置 |
|---|---|---|---|
| 1 | watchOS Complication（WidgetKit accessory 族，旧 ClockKit）/ Wear OS Complication（`ComplicationDataSourceService`） | 鸿蒙手表无逐项等价开放 API；最接近落点是 Wear Engine Kit 模板化通知（手机侧推送）；鸿蒙手表表盘卡片形态开放度 `PENDING_CONFIRM` | APPROVED_DEVIATION + 替代载体说明，或 excluded |
| 2 | Wear OS Tile（`TileService`，表盘左滑常驻卡） | 鸿蒙手表无逐项等价；候选载体同上（模板化通知/卡片形态，`PENDING_CONFIRM`） | APPROVED_DEVIATION + 替代载体说明，或 excluded |
| 3 | Taptic 细粒度触觉（WKHapticType：success/retry/notification…） | `@ohos.vibrator` 只有振动效果序列，无语义化触觉类型 | APPROVED_DEVIATION，映射到最近效果并记录用户可感知差异 |
| 4 | 手机联动会话（WCSession 五通道 / Wear OS DataClient·MessageClient） | Wear Engine Kit 是手机侧 SDK 且通道模型不同；手表侧对等会话无逐项等价 | 按消息/文件/通知三通道拆开逐条裁决，拆不清的整条 MANUAL_TAKEOVER |
| 5 | HealthKit 体能训练会话后台语义（HKWorkoutSession 持续运行/自动暂停） | 运动健康域 API 开放度需逐项核实（PENDING_CONFIRM） | 逐项核实后裁决，不得整类静默丢弃 |

裁决记录五字段：feature_id / 源端语义 / 目标端替代载体 / 用户可感知差异 / 审批人。缺任一字段不算完成裁决。

### Gate 特化

- Gate 2：watchos_static 以静态闭包标准（功能全覆盖、契约六要素来自双静态锚、RUNTIME 诉求全部转 GAP）放行，报告必须显式声明"源端零运行取证"；wearos_runtime 按手机路径标准（高风险真机/AVD 已验证）放行。
- Gate 3：叠加 scaffold-core-watch 的三件套检查（圆屏声明/交互映射表/联动裁决记录）。
- Gate 4：双端差分中 watchos_static 源端侧证据只有静态契约，断言以契约文本为 oracle；wearos_runtime 源端为完整运行 oracle（标准差分）。目标端侧两种源都必须有真实运行痕迹。

## 最小验证设想

watchos_static：用一个开源 watchOS 小项目（见 inventory.md 薄壳）走完整四阶段，检验"静态源端 + 真实目标端"的不对称治理闭环。wearos_runtime：用 Wear OS 官方示例（见 inventory.md 参考）走一轮，验证双端均可运行取证的标准差分链与 Tile/Complication 的 DEVIATION 裁决通道。

## 参考（调研来源，2026-09 访问）

- 华为官方：穿戴应用开发入口 https://developer.huawei.com/consumer/cn/multidevice/wearables/ ；Wear Engine Kit https://developer.huawei.com/consumer/cn/sdk/wear-engine-kit/
- 华为官方：API 18 版本说明（穿戴应用开发/Arc 组件族）https://developer.huawei.com/consumer/cn/doc/harmonyos-releases/os-new-feature-510
- Wear OS 官方文档区（Tile/Complication/旋转输入）https://developer.android.com/training/wearables ；Tiles https://developer.android.com/training/wearables/tiles ；Complications https://developer.android.com/training/wearables/complications
- Apple 官方：WidgetKit accessory 族（watchOS 复杂功能）文档区 https://developer.apple.com/documentation/widgetkit （检索 accessory）
- 开源最小验证例：twostraws/watchOS（SwiftUI watchOS 项目集）https://github.com/twostraws/watchOS ；android/wear-os-samples https://github.com/android/wear-os-samples
