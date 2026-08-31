---
name: watch-to-harmony-watch-inventory
description: 手表应用源端理解薄壳：watchOS 纯静态分析范式（无 mac）与 Wear OS 可运行取证范式（adb + Wear OS AVD）双源分派，产出 surface 枚举、行为契约与 GAP 清单。作为本路径 Phase 2 工单入口；禁止在此阶段写鸿蒙代码，禁止编造源端运行输出。
---

# watch-to-harmony-watch 源端理解（薄壳）

## 引用

- `skills/_shared/inventory-core.md`（九步流程/六要素/对账四态，全部继承）
- `skills/_shared/controller-core.md`（Phase 2 Gate 判据）
- 本文件按 source_profile（watchos_static / wearos_runtime，Gate 1 冻结）分派，只填手表平台差异参数与风险面。

## 本路径差异（平台差异参数）

| 参数 | watchos_static（watchOS） | wearos_runtime（Wear OS） |
|---|---|---|
| surface 枚举工具 | **静态扫描**（无 mac，不依赖 Xcode）：结构化 grep/Python 遍历源码树，锚点见下；不许手抄清单 | Android 静态扫描原样适用（manifest/导航图/Compose 或 View 体系）+ Wear 专属锚点（见下） |
| 运行取证工具 | **不可用**（无 mac/Xcode/watchOS 模拟器）——一律降级，见下 | **可用**：adb + Wear OS AVD（Android Studio SDK Manager 安装系统镜像后建 Wear 模拟器；adb 路径见 tablet 壳同式双平台口径）+ uiautomator dump（圆屏 dump 正常可用）+ `input swipe/tap` 注入 |
| source_refs 粒度 | Swift `file:line`（struct/class 声明行）；storyboard 锚 `Interface.storyboard` scene/identifier；工程配置锚 `project.pbxproj` target 与 `Info.plist` 键（`WKApplication`、`WKCompanionAppBundleIdentifier`、`WKRunsIndependentlyOfCompanionApp`） | Kotlin/Java `file:line`；manifest 中 service/receiver 声明行；Tile/Complication 的 XML 资源与 `previewImage` 资源项 |
| 特有风险面 | 见下表（watchOS 列） | 见下表（Wear OS 列） |

### watchOS 静态枚举方法（真实可用锚点）

- **判定应用范式**：现代单目标 watchOS app = `@main` + `App` 协议 + `WindowGroup`（无独立 extension target）；旧式 = WatchKit extension + `Interface.storyboard`（`WKExtensionDelegate` / `WKInterfaceController` 子类）。两种范式共存时分开登记。
- **SwiftUI 视图枚举**：`struct X: View` 为 view 候选；按组合关系分类 page（被 `NavigationStack`/`NavigationView`/`TabView` 或导航 destination 引用）vs component（仅被其他 view 内嵌）；`fullScreenCover`/`sheet` 为弹层 surface。**防"普通 View 被当独立页面"**——以导航引用链为准，不靠文件名。
- **特有能力静态指纹**：`WCSession`（手机联动）、`digitalCrownRotation`/`focusable`（数字表冠）、`WidgetBundle`/`accessoryCircular|accessoryRectangular|accessoryInline|accessoryCorner`（watchOS 9+ WidgetKit 复杂功能）与旧 `CLKComplicationDataSource`（ClockKit）、`HKWorkoutSession`/`HKLiveWorkoutBuilder`（体能训练）、`WKInterfaceDevice.current().play`（触觉）、`UNUserNotificationCenter`/通知 category（通知交互）。
- **页面层级极浅的先验**：watchOS 导航惯例 1-2 层（列表→详情），契约的操作序列应按短链书写；glance 型入口（复杂功能/通知）直达深层内容，须作为独立入口 surface 登记，不许折叠成"普通页面"。

### Wear OS 枚举锚点与运行取证（source_profile=wearos_runtime）

- **静态指纹**：`TileService`（androidx.wear.tiles，Tile 为表盘左滑常驻卡）、`ComplicationDataSourceService`（androidx.wear.watchface，表盘复杂功能数据源）、`SuspendingTileService` 协程变体；`SwipeDismissFrameLayout`/`SwipeDismissLayout`（androidx.wear.widget，侧滑返回范式）、`WearableRecyclerView`（偏离中心的曲线列表，androidx.wear.widget.recyclerview）、`BoxInsetLayout`（圆屏内接矩形适配）；手机联动 = Google Play services wearable 的 `DataClient`/`MessageClient`/`CapabilityClient`；旋转输入 = `GenericMotionEvent` SOURCE_ROTARY_ENCODER 与 `onGenericMotionEvent` 处理、`RotateInput`?（旋转 API 名称以官方 rotary-input 文档为准）；健康 = Health Services（`ExerciseClient`/`PassiveMonitoringClient`，androidx.health.services）。
- **运行取证规范**：Wear OS AVD（圆屏镜像）启动 app → `adb shell uiautomator dump` 取 ui-tree（圆屏设备树结构与手机一致，语义锚点可用）→ `input tap/swipe` 注入操作序列 → 前后截图（`adb exec-out screencap -p`）。旋转边圈（rotary bezel/虚拟表冠）在 AVD 上的注入能力**PENDING_CONFIRM**（部分镜像支持 rotary 模拟旋钮/键盘映射，以实测定）——不可用时滚动类操作降级为 swipe 语义等价取证并记 GAP 注记。
- **对账四态**：与手机路径同口径，允许 CONFIRMED（真机/AVD 实测）。

### watchOS 运行取证降级（watchos_static 强制）

所有 verify_mode=RUNTIME 的功能转 `GAP(feature_id, reason=NO_WATCHOS_RUNTIME)`；对账四态只允许 `SOURCE_CONFIRMED`（源码可核）与 `GAP`（源码也说不清/二进制/资源不确定），**禁止出现 CONFIRMED**（无运行即无实测）。iOS 配套 app 的任何行为只能作旁证（reference_only），不作 oracle。

### 手表特有风险面（易迁错清单，双源通用维度 + 各自条目）

| 风险面 | 为什么易迁错 |
|---|---|
| Complication/Tile 表盘常驻入口（两源各有） | 源端是表盘级入口+时间线/刷新语义；鸿蒙侧无逐项等价，易被静默丢弃或错当普通页面 |
| 手机联动通道（WCSession 五通道 / DataClient·MessageClient） | 实时消息/最新态快照/排队传输/后台文件各有送达与唤醒语义，混迁会丢消息 |
| 触觉语义类型 | 源端是语义（success/retry 或 Wear 的振动效果序列），鸿蒙只有效果序列，映射需裁决 |
| 体能训练后台会话 | 长时后台+传感器持续采集+自动暂停语义，前台 App 模型直接迁必错 |
| 前后台生命周期 | 手表 app 短时前台/系统挂起语义影响"重启后状态"契约要素的判定口径 |
| 旋转输入（digitalCrown / rotary encoder） | 源端绑定值域/步进；鸿蒙 onDigitalCrown 是事件流+度数，语义粒度不同 |
| 圆屏布局假设（BoxInsetLayout / SwiftUI safeAreaInset） | 源端按各自圆屏适配范式收敛内容；迁到 Arc 族要按鸿蒙弧形布局重排，直译必截角 |

## 最小验证设想

watchos_static：静态分析开源 watchOS 小项目（twostraws/watchOS：https://github.com/twostraws/watchOS ；WatchKit-UI-Sample：https://github.com/NAOYA-MAEDA-DEV/WatchKit-UI-Sample ）——surface-index 全部行带 file:line 锚、特有能力指纹全部命中归档、GAP 清单含 NO_WATCHOS_RUNTIME 理由。wearos_runtime：取 android/wear-os-samples（https://github.com/android/wear-os-samples ）任一 Tile 示例，静态指纹应命中 TileService；Wear OS AVD 运行取证产出"启动→列表滚动→详情"一条 CONFIRMED 契约，rotary 注入能力实测并在证据中标注结论。

## 参考（调研来源，2026-09 访问）

- Wear OS 官方：文档区首页 https://developer.android.com/training/wearables ；Tiles https://developer.android.com/training/wearables/tiles ；Complications https://developer.android.com/training/wearables/complications ；旋转输入 https://developer.android.com/training/wearables/rotary-input （标题以页面为准）
- Wear OS 官方示例仓库：https://github.com/android/wear-os-samples
- Apple 官方：watchOS/WKInterfaceController 文档区 https://developer.apple.com/documentation/watchkit ；WidgetKit https://developer.apple.com/documentation/widgetkit
- 华为目标端口径：`skills/_shared/scaffold-core-watch.md`（Arc 组件族/表冠事件/466×466 形态）及其参考节
