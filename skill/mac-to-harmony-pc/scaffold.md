---
name: mac-to-harmony-pc-scaffold
description: macOS→鸿蒙 PC 的 Phase 3 搭壳薄壳：按 surface 类型映射鸿蒙 PC 原生载体（窗口拓扑/路由/模态/控件/键鼠交互），interface-only 数据契约，目标端构建冒烟照常真实执行。写业务逻辑时禁用本 skill。
---

# mac → harmony-pc 搭壳薄壳（Phase 3）

> 源端运行取证可用与否的环境两态路由见本套件 `controller.md`。Phase 3 的构建/安装/启动冒烟在**鸿蒙 PC 目标端真实执行**（DevEco Studio + PC/2in1 模拟器或真机），不受源端环境态影响。

## 引用

- `skills/_shared/scaffold-core-pc.md`（鸿蒙 PC 搭壳内核，已落地，全部继承：窗口拓扑显式/最小窗口尺寸锚点/键鼠四项强制）
- `skills/_shared/scaffold-core-phone.md`（模态宿主推断等手机侧通用规则，PC 内核引用处沿同口径）
- 官方目标端文档（与 windows 路径共享 targets）：
  - 鸿蒙电脑(PC)与平板应用适配开发指南 https://developer.huawei.com/consumer/cn/multidevice/pc/adapt （大屏布局复用、自由多窗、键鼠交互优化、折叠屏/手写笔）
  - 应用开发指南总入口 https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/application-dev-guide
  - 多设备开发最佳实践 https://developer.huawei.com/consumer/cn/best-practices/multidevice/

## 本路径差异一：窗口与场景承载（mac 源面 → 鸿蒙 PC 载体）

| macOS 源面（静态识别） | 鸿蒙 PC 承载 | 备注 |
|---|---|---|
| SwiftUI WindowGroup / NSWindow 多窗口 | 自由多窗能力（主窗口 + 子窗口），按 PC 适配指南窗口化 | 多窗口语义必须在 window-topology.json 登记（内核必交产物） |
| NavigationSplitView / NSSplitViewController | 大屏分栏布局（断点/栅格自适应） | 布局复用优先，不逐像素复刻 |
| sheet / alert / NSAlert / NSPopover | 模态载体挂宿主页（modal@HOST；popover → `bindPopup`，sheet → `bindSheet`） | 宿主推断规则沿用内核 |
| MenuBarExtra / NSStatusItem 菜单栏应用 | **无全局菜单栏对等物** → APPROVED_DEVIATION 登记，映射为应用内导航或托盘近似物（以内核/官方文档为准） | 特有差异面，禁止静默丢弃 |
| Settings scene / NSUserDefaults 偏好窗 | 设置路由页；Preferences/RelationalStore 载体由 Phase 4 定 | 数据契约 interface-only |
| Storyboard scene（segue kind=modal/sheet/popover） | 路由节点（sceneID 作 route 名来源）；kind=modal → 模态 | 与 iOS 路径同法 |
| NSDocument / DocumentGroup 文档型 | 多实例窗口 + 文档打开/保存契约显式登记 | 文档自动保存语义进行为契约 |

## 本路径差异二：控件映射（AppKit/SwiftUI-macOS → ArkUI，写确信项；待验证显式标注）

| macOS 源端 | ArkUI |
|---|---|
| `NSButton` / SwiftUI `Button` | `Button` |
| `NSTextField`（输入）/ `NSTextView` | `TextInput` / `TextArea` |
| `NSTextField`（标签形态）/ `Text` | `Text` |
| `NSImageView` / `Image` | `Image`（`objectFit` 语义同 iOS 表） |
| `NSSlider` / `NSSwitch` / `NSStepper` | `Slider` / `Toggle` / `Stepper` |
| `NSPopUpButton` / `NSComboBox` / `Picker` | `Select`（下拉） |
| `NSTableView` / SwiftUI `Table` | `Table` 组件或 `List`（排序/多选语义进契约，逐条核对） |
| `NSOutlineView`（树形大纲） | `List` 嵌套/分组（树形语义待验证，登记裁决） |
| `NSScrollView` / `ScrollView` | `Scroll` |
| `NSToolbar` | 无直接等价 → 自定义 Builder 顶栏（APPROVED_DEVIATION 候选，登记） |
| `NSVisualEffectView`（毛玻璃） | 背景模糊能力（API 名待验证） |
| `NSProgressIndicator` | `Progress` / `LoadingProgress` |
| `WKWebView` | `Web`（ArkWeb） |
| `@State` / `@Binding` / `@EnvironmentObject` | `@State` / `@Link`·`@Prop`·`@Provide`+`@Consume`（同 iOS 表口径） |

## 本路径差异三：键鼠与窗口交互裁决（PC 形态核心差异，对齐 scaffold-core-pc）

| macOS 源端（静态锚，附录 §3D） | 鸿蒙 PC 承载 | 裁决 |
|---|---|---|
| 右键菜单（NSMenu contextual / `menu` 修饰符） | `bindContextMenu` | 高频编辑场景必备（内核键鼠规约） |
| hover（`onHover`/`mouseEntered/Exited`） | `onHover` + `hoverEffect` | 按行为契约声明落地，不虚构源端没有的交互 |
| 快捷键（`keyEquivalent` / `.keyboardShortcut`，⌘/⌥ 修饰） | KeyEvent 系逐条映射 | ⌘→鸿蒙快捷键规范逐条换算；未映射项记 GAP |
| 滚轮（`scrollWheel`） | `Scroll`/`List` 内建 | — |
| 拖放（`registerForDraggedTypes`） | onDrag 接口族 | 源端有拖放的功能必列 |
| 窗口关闭语义（`windowWillClose`、最后窗口关闭即退出） | 窗口操作与 UIAbility 生命周期解耦（内核白皮书口径） | "重启后状态"契约按窗口语义撰写 |
| 全屏（`toggleFullScreen`） | `window.maximize()` / `window.recover()` | 全屏是显式动作，非默认形态 |
| 多显示器（`windowDidChangeScreen`） | `display.getAllDisplays()` 判断 | 单屏验证环境跑不了的跨屏行为记 GAP |

- 数据契约：`data-contracts/<object>.json` 照内核 schema；macOS 侧参考持久化（UserDefaults/Keychain/Core Data，附录 §4A）仅作 reference 字段记录。
- UI 蓝图 preserve 字段：ENV_MAC_NATIVE 用真实截图（screencapture）；ENV_NO_MAC 改用"SwiftUI 组件序列摘要 / Storyboard 控件清单"（static_derived）。

## 环境与工具（冒烟链，Mac/Windows 双式；总表见 00-CONVENTIONS）

| 项目 | Windows（实测本机） | macOS（常规安装） |
|---|---|---|
| hvigorw 构建 | `D:\DevEco Studio\tools\hvigor\bin\hvigorw.bat`（或 `tools\node\node.exe` 调 `hvigorw.js`） | `/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw` |
| hdc 安装/启动/截图 | `D:\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe` | `/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc` |
| PC(2in1) 模拟器 | DevEco Studio 6.0.0+（Device Manager 内启动；`Emulator.exe -start` 形态同手机） | Device Manager 内启动（CLI 形态 PENDING_CONFIRM） |

## 最小验证设想

在 DevEco Studio 新建工程并选 2in1 形态设备，按 surface-plan/window-topology 生成路由/模态/多窗壳后：构建（hvigorw assembleHap）→ 部署到 2in1 模拟器 → 启动（hdc aa start）→ 路由逐个打开留痕（hdc snapshot_display 截图 + uitest 组件树），并核对：① 每个源端顶层窗口在 window-topology.json 有承载决策；② 最小窗口尺寸下布局不塌（内核最坏锚点）；③ 右键/hover 至少各一条真实驱动记录。全程目标端真实命令输出，可复核即合规。

## 参考

- 鸿蒙 PC 适配与自由窗口（官方）： https://developer.huawei.com/consumer/cn/multidevice/pc/adapt ；智慧多窗 https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/multi-window-support ；自由窗口白皮书 §5.1 https://developer.huawei.com/consumer/cn/doc/guidebook/develop-once-deploy-everwhere-5-1-0000002594832922
- Swift→ArkTS 官方迁移对照： https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-for-other-languages ；SwiftUI→ArkUI 思维转换 https://bbs.huaweicloud.com/blogs/480637
- Apple 控件/交互语义对照源：AppKit https://developer.apple.com/documentation/appkit （NSWindow/NSMenu/NSStatusItem/NSToolbar 类文档入口）；SwiftUI https://developer.apple.com/documentation/swiftui
- 人机交互·交互事件归一（右键/快捷键平台规范）： https://developer.huawei.com/consumer/cn/doc/design-guides/hmi-interaction-events-0000001795531217
