---
name: watch-to-harmony-watch-scaffold
description: watchOS/Wear OS→鸿蒙手表 Phase 3 承载薄壳：SwiftUI/Compose 手表视图到 ArkUI 圆屏弧形组件的映射、表冠等腕上交互重映射、单页导航范式与 Wearable 工程脚手架。输入为 Phase 2 产物；本阶段不写业务逻辑、不实现传输通道。
---

# watch-to-harmony-watch 目标承载（薄壳）

## 引用

- `skills/_shared/scaffold-core-watch.md`（鸿蒙手表承载内核：圆屏规则/形态约束/可用组件子集/交互挂载点/性能预算/冒烟链/Gate 3 特化，全部继承）
- `skills/_shared/controller-core.md`（Phase 3 判据与失败路由）
- 本文件只补 watchOS / Wear OS 源端 → 鸿蒙手表的映射差异。

## 本路径差异

### 源端 surface → 鸿蒙手表承载面映射（watchOS 行 + Wear OS 行）

| 源端（watchOS / Wear OS） | 鸿蒙手表承载（API 18+） | 备注 |
|---|---|---|
| SwiftUI `List`/`ScrollView`；Wear OS `WearableRecyclerView`/`LazyColumn` | `ArcList` + `ArcListItem`（长列表 `LazyForEach`；可选 `ArcScrollBar`） | 圆屏默认承载；普通 List 须登记理由 |
| 全屏分页/`TabView`(page style)；Wear OS `HorizontalPager` | `ArcSwiper` | 表冠默认可驱动 |
| 按钮操作行（SwiftUI Button / Compose Button） | `ArcButton`（强调/普通/警告） | |
| `NavigationStack` / Wear OS NavHost 层级导航 | 鸿蒙页面路由，**页面层级 ≤2**（列表→详情） | 源端第 3 层及以上须在蓝图给出合并/降级方案 |
| `sheet`/`fullScreenCover`；Wear OS 对话类页面 | 模态挂载到宿主页 | 宿主推断规则同内核 |
| Complication（WidgetKit accessory / `ComplicationDataSourceService`） | 无逐项等价 → `PLATFORM_DEVIATION` 裁决（候选：Wear Engine 模板化通知；表盘卡片形态 `PENDING_CONFIRM`） | 不建壳，只建裁决记录 |
| Wear OS Tile（`TileService`） | 同上 → `PLATFORM_DEVIATION` 裁决 | 不建壳，只建裁决记录 |
| 通知交互页（长样式） | 普通页面/模态壳 + 通知通道语义契约 | 渲染可等价，触达通道不等价 |

### 交互重映射表（蓝图必填行）

| 源端输入 | 目标端挂载点 |
|---|---|
| `digitalCrownRotation`（值绑定）/ rotary encoder（`SOURCE_ROTARY_ENCODER` 泛型事件） | 首选承载于默认表冠响应组件（ArcList/Slider 类）；自处理用 `onDigitalCrown` + 获焦（`focusable`/`defaultFocus`/`focusOnTouch`）+ `digitalCrownSensitivity`；`CrownEvent.degree/angularVelocity` 换算成源端值域须写明公式 |
| 点按 `onTapGesture`/`onClick`（Compose） | `onClick` |
| 长按/上下文菜单 | 长按手势（并注明圆屏上的可达性权衡） |
| 系统返回（表冠长按/侧滑；Wear OS `SwipeDismissFrameLayout`） | 鸿蒙系统返回，不自绘 |
| 触觉（`WKInterfaceDevice.play` / Wear OS vibration effect） | 不在 Phase 3 实现——立语义占位契约，Phase 4 走 `@ohos.vibrator` 映射裁决 |

### Wear OS 组件极简映射表（补充）

| Wear OS 源端 | 鸿蒙落点 | 备注 |
|---|---|---|
| `BoxInsetLayout`（圆屏内接矩形） | Arc 族弧形布局 + 蓝图安全区字段 | 直译矩形 = 截角缺陷 |
| `SwipeDismissFrameLayout` | 系统返回（不建组件壳） | 语义=返回，载体=系统 |
| `ConfirmationOverlay`（确认动画浮层） | 模态壳（短时反馈类）或 ArcButton 结果页 | 语义=操作确认反馈 |
| Wear OS 通知（长样式） | 通知通道语义契约 + 普通页渲染 | 同上表通知行 |
| Health Services（ExerciseClient） | 数据契约 interface-only + 开放度 `PENDING_CONFIRM` 裁决 | 不假设可用 |

### 工程与环境

- DevEco Studio 5.1.0+，新建 Empty Ability 且 Device Type=**Wearable**，SDK API 18+，`module.json5` `deviceTypes` 含 `wearable`。
- 冒烟优先 Local Emulator 的 Wearable 模拟器（X86 本地模拟器支持 Phone/TV/Wearable；Mac ARM NEXT 模拟器当前仅 wearable 类型）；不可用降级 Previewer 并记录（证据等级较低）。
- 手机联动（WCSession 五通道 / Wear OS DataClient·MessageClient）本阶段只立 消息/文件/通知 三类 interface-only 契约 + 裁决记录，不实现传输。
- 源端取证环境（仅 wearos_runtime 需要）：Wear OS AVD 建立在 Android Studio/SDK 工具链内，与目标端 DevEco 环境互不混用，分别入 HENV 冻结。

## 最小验证设想

watchos_static：静态分析产出 → 本阶段产出 DevEco 中可构建、可安装进手表模拟器并启动的圆屏骨架——首页 `ArcList`（若干静态 ArcListItem，含至少一条 `ArcButton` 操作行）+ 详情路由页 + 交互映射表；`hvigorw assembleHap` 与模拟器启动截图留痕。wearos_runtime：承接 wear-os-samples 某 Tile 示例的静态产物——骨架同上，另产出 Tile→DEVIATION 裁决工单草稿（五字段），验证承载面覆盖、圆屏三件套声明齐备与裁决通道就位（hvigorw/hdc 双平台路径见 `_shared/00-CONVENTIONS.md`）。

## 参考（调研来源，2026-09 访问）

- 华为官方：ArcList 指南 https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-layout-development-create-arclist ；ArcSwiper https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-layout-development-arcswiper ；表冠事件 https://developer.huawei.com/consumer/cn/doc/harmonyos-references/ts-universal-events-crown
- 华为官方：穿戴应用开发（工程模板/Wearable 设备类型）https://developer.huawei.com/consumer/cn/multidevice/wearables/get-started/
- Wear OS 官方：Tiles https://developer.android.com/training/wearables/tiles ；Complications https://developer.android.com/training/wearables/complications ；旋转输入 https://developer.android.com/training/wearables/rotary-input
- AndroidX 对应组件（源端锚点）：androidx.wear（tiles/watchface/widget）发布页 https://developer.android.com/jetpack/androidx/releases/wear
- 开源最小验证例：twostraws/watchOS https://github.com/twostraws/watchOS ；android/wear-os-samples https://github.com/android/wear-os-samples
