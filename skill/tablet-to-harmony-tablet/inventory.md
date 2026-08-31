---
name: tablet-to-harmony-tablet-inventory
description: 为冻结的平板应用（Android 平板真机取证 / iPad 静态降级）产出功能语义地图、行为契约与形态取证，回答"如何全面理解一个平板应用"。用于本路径 Phase 2；禁止在此写鸿蒙代码。
---

# 平板 → 鸿蒙平板 源端理解（薄壳）

## 引用

- 必读内核：`skills/_shared/inventory-core.md`（九步流程/契约六要素/分级验证/对账四态全部继承）。
- Android 源端执行基线：`skills/android-to-harmony-phone/android-migration-inventory/`（脚本族 + 防伪口径：foreground 校验/伪 ANR 防护/断言才算事实）。
- 平板差异仅在"多出的取证维度"，不另立流程。

## 平台差异参数（inventory-core 参数表的填充）

| 参数 | Android 平板（source_profile=android_tablet） | iPad（source_profile=ipad_static） |
|---|---|---|
| surface 枚举工具 | 手机路径 analyze_static_pages 原样适用；平板追加扫描：`layout-sw600dp`/`-w600dp` 资源限定符目录、window size class 判断（`WindowSizeClass`/`currentWindowAdaptiveInfo`）、`android:resizeableActivity` 与多窗清单标志 | SwiftSyntax（Apple 开源解析器）解析 SwiftUI View 树与 UIKit ViewController；无 Xcode 也能跑（Python/Swift 绑定或 ripgrep 结构遍历兜底）；枚举 body 内 NavigationLink/sheet/fullScreenCover/HStack 分栏结构 |
| 运行取证工具 | adb + uiautomator（adb 双平台路径：Windows `D:\Android\Sdk\platform-tools\adb.exe` 或 `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`；macOS `~/Library/Android/sdk/platform-tools/adb`；平板 AVD）；多窗：`adb shell am start --windowingMode <1全屏/2画中画/3分屏/5自由窗> --launchBounds l,t,r,b`（自由窗需先 `settings put global enable_freeform_support 1`）；笔输入：模拟器宿主笔支持或 root 下 `getevent`/`sendevent` 注入 TOOL_TYPE_STYLUS、`input motionevent DOWN/MOVE/UP x y` | **不可用**（无 mac）——运行取证整档声明 TOOL_GAP，全部降级 SOURCE_CONFIRM |
| source_refs 粒度 | `file:line` + 资源限定符目录（形态证据锚 `-sw600dp` 布局文件） | Swift `file:line`（SwiftUI body / ViewController 类） |
| 特有风险面 | ①多窗：分屏/自由窗下状态保存恢复（`onSaveInstanceState`/ViewModel）②DragAndDrop：ClipData MIME 类型与拖放目标行为 ③手写笔：压感/倾斜/手势与文本手写输入（Android 14 起任意文本框可手写）④键盘/快捷键（平板外设高频）⑤横竖屏与窗口变化时布局/状态漂移 | ①同左维度但只能源码确认：size class 分支、`horizontalSizeClass` 分栏、UIDragInteraction/UISplitViewController ②GAP 必须逐条带因，供 Gate 4 静态比对 |

## 大屏适配静态指纹（android_tablet 追加扫描锚点）

判定"源端做了多少平板适配"直接影响 as-is/amplify 口径，以下指纹逐项扫描并记入形态取证摘要：

- **资源限定符分栏**：`res/layout-sw600dp/`、`layout-w600dp/`、`values-sw600dp/`（列数常放 integers/dimens 差异文件）——存在即"有断点化布局"。
- **双 pane 组件**：`SlidingPaneLayout`（androidx.slidingpanelayout）、`ListDetailPaneScaffold`（androidx.adaptive/compose-adaptive）、`NavRail`（Material3 NavigationRail）/ 自定义双 Fragment 布局——存在即"有 List-Detail 分栏语义"。
- **窗口能力声明**：`android:resizeableActivity`、`resizableActivity` 支持-sizing，`SplitPairFilter`/`SplitRule`（androidx.window embedding 规则）——多窗取证的风险面依据。
- **尺寸计算代码**：`currentWindowAdaptiveInfo()`/`WindowWidthSizeClass`/`Configuration.smallestScreenWidthDp` 分支——运行时断点逻辑。
- **键盘/笔/拖拽**：`dispatchKeyEvent`/快捷键 menu XML、`onGenericMotionEvent`（SOURCE_STYLUS）、`startDragAndDrop`/`OnDragListener` 调用点。

## 本路径增量产物（在九步产物之上加两件）

1. **form-factor-evidence（形态取证）**：逐 RUNTIME 页面级 surface 记录源端形态行为——断点 A（窄窗/竖屏）与断点 B（宽窗/横屏）下各是单栏/分栏/网格几列；List-Detail 面在宽窗下"选中列表项 → 右侧更新（分栏）还是整页跳转（单栏）"。取证手段：AVD 旋转 + `--windowingMode 3/5` 制造不同窗口宽度，前后截图 + ui-tree 判定。此产物是 Gate 1 as-is/amplify 口径的证据与 Phase 3 breakpoint_plan 的源端基准。
2. **BC 平板扩展列**：behavior-contracts 对涉平板特性功能增加 `form_factor` 列（multi_window / drag_drop / stylus / keyboard / none），操作序列与结果断言写明在哪个窗口形态下执行（如"分屏态下拖 A 至 B，断言 B 出现条目"）。断言只写语义结果（条目出现/状态保持），不写像素。

## 防伪口径（继承 + 平板补充）

- 多窗取证必须绑定 `adb shell dumpsys window`/`dumpsys activity` 的窗口态证据（windowing mode 实测值），不得以"命令发出去了"当作已进入分屏。
- 手写笔注入在 AVD 上不可得压感/倾斜时，降级 GAP（原因：模拟器无笔注入），禁用 touch 冒充 stylus。
- iPad 源：一切"运行过"的说法均不成立，产物只有静态证据 + GAP 清单；摘要里不得出现运行时口吻。

## 最小验证设想

取 Android 官方大屏 codelab 工程（见参考）作源端：静态指纹扫描应命中资源限定符分栏与 ListDetailPaneScaffold；平板 AVD 旋转 + 分屏窗口取证产出两断点形态取证；对"窄窗整页跳转 / 宽窗右栏更新"写一条带 form_factor 列的 BC——全流程可静态复核、运行证据带 dumpsys 窗口态锚。

## 参考（调研来源，2026-09 访问）

- Android 官方：大屏适配文档区 https://developer.android.com/develop/ui/views/layout/large-screens
- Android 官方：window size classes（Compose 尺寸分级）https://developer.android.com/develop/ui/compose/layouts/adaptive/use-window-size-classes
- Android 官方：资源限定符（sw600dp/w600dp 语义）https://developer.android.com/guide/topics/resources/providing-resources
- Android 官方：SlidingPaneLayout（双 pane List-Detail 范式）https://developer.android.com/jetpack/androidx/releases/slidingpanelayout ；ListDetailPaneScaffold https://developer.android.com/develop/ui/compose/layouts/adaptive/list-detail-pane-scaffold
- Android 官方：拖放 https://developer.android.com/develop/ui/views/touch-and-input/drag-drop ；多窗口支持 https://developer.android.com/develop/ui/views/multi-window
- Apple 官方：SwiftUI 自适应布局（size class）文档区 https://developer.apple.com/documentation/swiftui （检索 horizontalSizeClass）
- 最小验证可跑例：Android 大屏 codelab https://developer.android.com/codelabs/large-screens ；自适应布局 codelab https://developer.android.com/codelabs/adaptive-layouts
