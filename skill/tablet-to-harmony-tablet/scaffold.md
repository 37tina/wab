---
name: tablet-to-harmony-tablet-scaffold
description: 为冻结的平板功能地图搭建鸿蒙平板原生承载骨架（断点形态契约/Navigation 分栏/栅格并排 + interface-only 数据契约），并通过含平板附加判定的 Gate 3。用于本路径 Phase 3；禁止实现业务逻辑。
---

# 平板 → 鸿蒙平板 目标承载（薄壳）

## 引用

- 必读内核：`skills/_shared/scaffold-core-tablet.md`（断点体系/一多布局/折叠态/分栏/并排规约、breakpoint_plan 三字段、Gate 3 平板加两条判定——本壳的形态标准全部以此为准）。
- 手机路径方法论参照：`skills/android-to-harmony-phone/harmonyos-migration-scaffold/SKILL.md` 五步范式（分面搭壳/不建容器壳/UI 蓝图四字段/数据契约 interface-only/冒烟链）。`_shared/scaffold-core-phone.md`（已落地，手机通用基线）；原生命令与 ArkUI 组件对照查 `skills/android-to-harmony-phone/arkui-next-reference/14-android-to-harmony-map.md`。

## 本路径差异（在手机壳范式之上）

1. **UI 蓝图增第五字段**：手机路径四字段（android_structure/preserve/native_carrier/native_component）之上，每个页面级 surface 增加 `breakpoint_plan`——sm/md/lg 三断点各自的布局形态枚举（single / split / sidebar+content / grid(n列)）+ 承载组件名。List-Detail 面的 md/lg 必须为 split（Navigation Auto/Split + NavDestination），并显式声明右侧占位（splitPlaceholder 或默认 pushPath）。
2. **承载映射核心**（详见内核规约节）：分栏=Navigation（宽度 ≥600vp 自动分栏）；常驻侧栏=SideBarContainer 并排式（lg）/Embed 抽屉（sm）；重复网格=GridRow/GridCol（columns 按断点显式传 GridRowColumnOptions，默认全断点 12 列须覆写为业务列数）；多窗/拖放/笔输入面不建独立壳，落行为契约与数据契约（拖拽数据登记 UDMF 类型）。
3. **as-is / amplify 口径落地**：Gate 1 冻结为 as-is 时，breakpoint_plan 按源端形态取证照搬（拉伸即拉伸，形态不升级）；amplify 时按内核规约升级，且每个被升级的 surface 登记 AMPLIFY_DEVIATION（源形态 → 目标形态）随工单带入 Gate 4 人工裁决队列。
4. **冒烟链形态项**：构建/安装/启动冒烟在平板模拟器（DevEco 本地 Tablet 设备类型；本机 DevEco Studio 6.1 + 模拟器）上执行，至少各跑一次竖屏与横屏启动冒烟（覆盖 md/lg 两断点），启动截图入证据。

## Android 大屏模式 → 鸿蒙断点承载映射表（蓝图 native_carrier/native_component 填表依据）

| Android 源端大屏手段 | 鸿蒙平板承载（组件级） | 备注 |
|---|---|---|
| `layout-sw600dp` 资源限定符双布局 | GridRow/GridCol 断点差异 + 条件渲染（同一页面内按断点切换结构） | 语义=显式断点分档，禁拉伸冒充 |
| SlidingPaneLayout / ListDetailPaneScaffold（双 pane） | `Navigation(NavigationMode.Auto)` + NavDestination 双栏，splitPlaceholder 占位 | Phase 4 断言锚=路由只替换右栏 |
| `values-sw600dp` 列数（Grid 列数随屏） | GridRow + GridRowColumnOptions 显式列数（如 sm 4 / md 8 / lg 12） | 须覆写默认 12 列 |
| Material NavigationRail / 常驻侧栏 | SideBarContainer 并排式（md/lg 常驻），sm 收 Embed 抽屉或 Tab | 侧栏面在 blueprint 标 sidebar+content |
| 多窗/分屏（windowingMode） | 不建壳；立"窗口变化下状态保持"行为契约 | 断点由窗口宽度自然触发 |
| ClipData/startDragAndDrop 拖放 | 不建壳；数据契约登记 UDMF 类型映射（MIME → uniformTypeDescriptor） | 见内核 UDMF 规约 |
| 键盘快捷键 | 交互重映射表登记快捷键 → 触控/菜单入口等价物 | 结果断言不变 |
| 手写笔（TOOL_TYPE_STYLUS） | 不建壳；契约登记，注入能力 PENDING_CONFIRM 时降 GAP | 禁 touch 冒充 |

## 最小验证设想

List-Detail 小应用（可承接 Android 大屏 codelab 工程的迁移）：feature-map 含 1 个列表页 + 1 个详情面 + 1 条持久化数据对象 → 壳 = Navigation(Auto) + NavDestination×2 + splitPlaceholder 占位 + GridRow 列表（sm 4 列 / lg 12 列显式声明）；Gate 3 自检：breakpoint_plan 三字段非空、分栏占位声明存在、冒烟链含横竖屏两启动、数据契约无孤儿。产出能在平板模拟器上安装启动并横竖屏切换不崩的零业务骨架。

## 参考（调研来源，2026-09 访问）

- 华为官方：Navigation（Auto/Split、600vp 阈值、splitPlaceholder 语义）https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-navigation-navigation
- 华为官方：栅格布局（GridRowColumnOptions/断点列数）https://developer.huawei.com/consumer/cn/doc/harmonyos-guides-V13/arkts-layout-development-grid-layout-V13
- 华为官方：一多能力开发入口（自适应/响应式布局）https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/application-model-development-outline
- 华为官方：拖拽与 UDMF https://developer.huawei.com/consumer/cn/doc/harmonyos-references-v5/ts-universal-events-drag-drop-V5
- 华为官方：模拟器自定义屏幕配置（多平板尺寸取证）https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/ide-emulator-customize-screen-configuration
- Android 官方（源端映射出处）：大屏适配 https://developer.android.com/develop/ui/views/layout/large-screens ；SlidingPaneLayout https://developer.android.com/jetpack/androidx/releases/slidingpanelayout
- 最小验证可跑例：Android 大屏 codelab https://developer.android.com/codelabs/large-screens ；自适应布局 codelab https://developer.android.com/codelabs/adaptive-layouts
