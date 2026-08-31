---
name: ios-to-harmony-phone-scaffold
description: iOS → 鸿蒙手机 Phase 3 搭壳薄壳（引用 scaffold-core-phone 通用内核 + iOS 导航/控件/状态/生命周期到 ArkUI 的官方映射表与交互范式裁决）。何时用：消费 Phase 2 功能地图搭 ArkUI 原生壳；何时不适用：Phase 2 未闭包，或要在本阶段写业务逻辑。
---

# iOS → 鸿蒙手机 目标承载搭壳（薄壳）

## 引用

- `skills/_shared/scaffold-core-phone.md` —— 手机端搭壳通用内核（承载面规则 / 数据契约 interface-only / 构建-安装-启动冒烟链）。
- `skills/_shared/controller-core.md` —— Gate 3 判定口径与等价契约。
- 映射口径对齐 `skills/android-to-harmony-phone/arkui-next-reference/14-android-to-harmony-map.md`（同一 ArkUI 基线 API 12 / HarmonyOS NEXT，组件词汇一致，避免同仓两套口径）。

## 本路径差异

源端 surface 语义来自 iOS 双范式（UIKit Storyboard scene / SwiftUI 视图树，见 `_shared/inventory-ios.md` §3）。借鉴 ArkTrans（arXiv:2606.07085）的"先机械提取结构骨架、再映射、后按规则修复"思路：先按下表机械替换导航与容器骨架，控件细节由 Phase 4 填充。左=源端语义锚，右=ArkUI 官方载体（不做 iOS 式手搓模仿）：

### 导航与容器

| iOS 源端 | ArkUI（API 12） |
|---|---|
| `UINavigationController` push/pop | `Navigation` + `NavPathStack`（`pushPathByName` / `pop`） |
| `NavigationStack` + `NavigationLink(value:)` + `navigationDestination(for:)`（iOS16+） | `Navigation` + `NavPathStack` + `navDestination` @Builder 页面表（或系统路由表 `router_map.json`） |
| `TabView` / `UITabBarController` + `UITab` | `Tabs` + `TabContent`（底栏多页时 tabs_owner 唯一仲裁，同 Android 口径） |
| `UIPageViewController` | `Swiper` |
| `performSegue`（show/push 型） | `pushPathByName` |
| `present` 全屏模态 / `.fullScreenCover` | `bindContentCover` 或 `NavDestinationMode.DIALOG` |
| `.sheet` / `UISheetPresentationController`（半模态） | `bindSheet` |
| `.alert` / `UIAlertController`（alert 样式） | `CustomDialog` / `AlertDialog` |
| `.confirmationDialog` / `UIAlertController`（actionSheet 样式） | `ActionSheet`（调用形态待验证）或 `bindMenu` / `bindContextMenu` |
| unwind segue / `dismiss` | `pop` / `bindSheet` 关闭回调 |

### 控件与状态

| iOS 源端 | ArkUI |
|---|---|
| `UILabel` | `Text` |
| `UIButton` | `Button`（图标 = Row 自组） |
| `UIImageView`（contentMode） | `Image`（`objectFit`：scaleAspectFill→Cover，fit→Contain） |
| `UITextField` / `UITextView` | `TextInput` / `TextArea`（受控陷阱同 Android 表 A2：不回写 `.text`） |
| `UISwitch` / `UISlider` / `UIStepper` | `Toggle(ToggleType.Switch)` / `Slider` / `Stepper` |
| `UITableView` / `UICollectionView` | `List` + `ListItem` + `LazyForEach`；网格 `Grid`+`GridItem`，瀑布流 `WaterFlow`（待验证） |
| `UIScrollView` | `Scroll` |
| `UIStackView` | `Row` / `Column` |
| `UIPickerView` / `UIDatePicker` | `TextPicker` / `DatePicker`（时间 `TimePicker`） |
| `UIRefreshControl` | `Refresh`（包 `List`，`refreshing` 状态驱动） |
| `UIActivityIndicatorView` | `LoadingProgress` |
| `UIProgressView` | `Progress` |
| `UISearchController` / `.searchable` | `Search` 组件 |
| `WKWebView` | `Web`（ArkWeb） |
| `SF Symbols` | `SymbolGlyph`（符号名逐个查鸿蒙符号库映射，非同名直搬，标待验证） |
| `UIImagePickerController` / `PhotosUI` | 照片选择器（`PhotoViewPicker` 形态待验证） |
| `UIVisualEffectView`（毛玻璃） | 背景模糊能力（API 名待验证） |
| `@State` / `@Binding` / `@EnvironmentObject` | `@State` / `@Link`·`@Prop`·`@Provide`+`@Consume`（按单向/双向语义选） |

### 生命周期映射（隐式行为的落点，锚点来源 inventory-ios §3C）

| iOS 源端 | 鸿蒙承载 |
|---|---|
| `applicationDidFinishLaunching` | UIAbility `onCreate` / `onWindowStageCreate` |
| `sceneDidBecomeActive` / `sceneWillResignActive` | UIAbility `onForeground` / `onBackground` |
| `applicationDidEnterBackground`（退场保存） | `onBackground` 内落盘（持久化契约的⑤重启后状态落点） |
| `applicationWillTerminate` | UIAbility `onDestroy`（注意：移动端 kill 不保证回调，契约按 onBackground 兜底写） |
| `viewWillAppear` / `onAppear` | 页面 `aboutToAppear` / `onPageShow`；NavDestination `onShown` |

### 交互范式裁决（PLATFORM_DEVIATION 默认口径，Phase 4 逐条复核）

- **返回逻辑**：iOS edge-swipe 返回 / 导航栏返回按钮 → 鸿蒙全局侧滑返回；源端禁用返回（`interactivePopGesture` 拦截、返回时弹确认）必须显式迁到 `NavDestination.onBackPressed`，否则语义漂移。
- **导航栏**：`UINavigationBar` 大标题/隐藏 → `Navigation` titleMode(Full/Mini) / hideTitleBar；`rightBarButtonItem` → `.menus()`。
- **3D Touch（peek & pop）/ Force Touch**：鸿蒙无压力维 → 长按（`LongPressGesture` / `bindContextMenu`）替代或登记 PLATFORM_DEVIATION 由人工裁决。
- **手势冲突**：源端自定义左滑手势与系统返回手势共存的逻辑，迁后须在鸿蒙侧滑返回语境下重测（Phase 4 差分项）。

## 环境与工具（冒烟链，Mac/Windows 双式；总表见 00-CONVENTIONS）

| 项目 | Windows（实测本机） | macOS（常规安装） |
|---|---|---|
| hvigorw 构建 | `D:\DevEco Studio\tools\hvigor\bin\hvigorw.bat`（或 `tools\node\node.exe` 调 `hvigorw.js`） | `/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw` |
| hdc 安装/启动/截图 | `D:\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe` | `/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc` |
| 手机模拟器 | `D:\DevEco Studio\tools\emulator\Emulator.exe`（`-list/-start`） | Device Manager 内启动（CLI 形态 PENDING_CONFIRM） |

## 最小验证设想

- **映射核验**：一个 `NavigationStack`+`TabView` 的 SwiftUI 双页 demo 工程与一个 Storyboard segue 工程（HackingWithSwift 内即有此两类）：Phase 3 产出的 surface-plan 路由/模态落点与上表逐条对得上；生命周期锚点（§3C grep 命中行）在 UI 蓝图中有承载落点。
- **冒烟真跑**：DevEco 手机模拟器构建（hvigorw assembleHap）→ 安装（hdc install）→ 启动（hdc `aa start`）→ 截图（hdc `snapshot_display`）留痕，全部为目标端真实命令输出。

## 参考

- ArkTrans（arXiv:2606.07085，"骨架先行-映射-规则修复"方法论）：https://arxiv.org/abs/2606.07085
- 华为 ArkUI Navigation 官方文档：https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-navigation-navigation ；ArkUI 开发入门（组件总览）：https://developer.huawei.com/consumer/cn/arkui/devstart/
- Swift→ArkTS 官方迁移对照（状态管理范式映射依据）：https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-for-other-languages
- SwiftUI→ArkUI 思维转换（华为云社区）：https://bbs.huaweicloud.com/blogs/480637
- Apple 生命周期/组件语义对照源：UIApplication 场景生命周期 https://developer.apple.com/documentation/uikit/uiapplicationscene-delegate ；SwiftUI https://developer.apple.com/documentation/swiftui ；UIKit https://developer.apple.com/documentation/uikit
