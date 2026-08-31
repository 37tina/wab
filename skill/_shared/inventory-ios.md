---
name: inventory-ios
description: iOS 源端静态分析附录（工程结构解剖 / Xcode 工程解析 / Storyboard 与 SwiftUI 双范式扫描 / Swift 行为锚点清单 / simctl+XCUITest 运行取证命令细节 / 持久化与系统能力风险面 / 六要素对接点）。何时用：ios-to-harmony-phone 路径的 Phase 2 及 mac 补取证；何时不适用：其他源平台。
---

# iOS 静态分析附录（inventory-core 的 iOS 参数库）

**定位**：回答"没有 mac 时，iOS 工程里什么是真实可核验的；有 mac 时，运行取证用什么命令"。§1-§3、§5-§6 的全部手段在 Windows（Git Bash / Python / Ruby）上即可执行——iOS 工程的关键输入（Swift 源码、Storyboard/XIB XML、`project.pbxproj`、Info.plist、entitlements、`.xcdatamodeld`）**都是纯文本**。§4 的运行取证必须 macOS+Xcode，命令均已核对真实子命令形态（simctl 子命令集于 2026-09-01 在 macOS 27.0 + Xcode 27.0 上实测存在：boot/bootstatus/install/launch/terminate/privacy/io/ui/get_app_container），只给命令形态不虚构输出。

## Non-negotiable

- 源端运行取证默认不可用（本机无 Xcode/swiftc/simctl）：RUNTIME 项降级 `SOURCE_CONFIRM + GAP`（原因码 `SOURCE_RUNTIME_UNAVAILABLE`），禁止伪造 `xcodebuild`/`simctl`/`xcresult` 输出或用演示截图冒充。
- 一切静态锚点可复核：`文件:行`、`sceneID`、`storyboardIdentifier`、Info.plist key 路径，登记时同步记录提取命令，让第三方能重跑同一 grep 得出同一清单。
- 枚举必须来自工具遍历（grep/脚本），禁止手抄 surface 清单。
- 命令不虚构：mac 侧命令以 Xcode 16.x-27.x 为参考形态，子命令随版本变化处标 `PENDING_CONFIRM`；设备名（如 iPhone 16 / iPhone 17）随本机 runtime 变化，一律以 `xcrun simctl list devices available` 实测输出为准；不确定的鸿蒙 Kit 名标 `待验证`。

## §1 工程结构解剖（纯静态，任何机器可做）

按顺序读以下文件，建立工程骨架认知：

| 文件 | 判定什么 |
|---|---|
| `*.xcodeproj/project.pbxproj` | targets（App/扩展/UI 测试 target）、源文件清单、build phases、依赖（见 §2） |
| `Info.plist`（或 build settings 里 `INFOPLIST_KEY_*`） | 生命周期范式：`UIApplicationSceneManifest`（iOS13+ 多场景）vs `UIMainStoryboardFile`（旧单场景）；`UIBackgroundModes`（如 `remote-notification`=APNs 后台）；`CFBundleURLTypes`（deep link scheme）；`NSUserActivityTypes`（Handoff/SiriKit）；`UILaunchStoryboardName` |
| `*.entitlements` | 系统强绑定清单：`aps-environment`（推送）、`com.apple.developer.healthkit`（HealthKit）、iCloud 容器、App Groups、钱包/家庭等 capability —— **每个条目都是一条潜在 PLATFORM_DEVIATION 候选** |
| `Package.swift` / `Podfile` / `*.xcworkspace` | 依赖面：SPM / CocoaPods / 依赖库中含平台强绑定组件（如 KeychainAccess、CloudKit 封装） |
| Swift 源码入口 | SwiftUI 范式：`@main struct X: App`；UIKit 范式：`AppDelegate`（+ `SceneDelegate`），后续沿 `UIWindow.rootViewController` / 首个 `TabView`/`NavigationStack` 找主入口 |
| `*.xcdatamodeld/contents` | Core Data 模型（XML），实体/属性/关系可静态解析进 data-relations |
| `*.xcassets/Contents.json` | 资源清单（图标/图片，迁移时资产搬运） |

## §2 Xcode 工程解析

- **pbxproj 本体**是 OpenStep 风格的 plist 文本：`grep -c` / Python 逐行可解析出 target 名、`PBXBuildFile`/`PBXFileReference`、build phases。适合做"源文件清单指纹"（Gate 1 冻结源码范围用）。
- **Ruby xcodeproj gem（跨平台，Windows 装 Ruby 即可用）**：`gem install xcodeproj`，然后 `Xcodeproj::Project.open('X.xcodeproj')` 读 `project.targets`、`target.source_build_phase.files`——结构化解析 target→文件→build phase，比裸 grep 稳。
- **mac 上才有**：`xcodebuild -list -project X.xcodeproj`（schemes/targets/configurations）、`xcodebuild -showBuildSettings`（SDK/签名/bundle id 指纹）、`xcodebuild -showsdks`。这些作为 mac 补取证的环境自证输出（见 §4 步骤 0）。

## §3 双范式 UI 静态扫描（surface 枚举的真实手段）

**范式 A：UIKit + Storyboard/XIB**。storyboard/XIB 是 XML（右键 Open As → Source Code 可见）：`<document>` 下 `<scenes>`，每 `<scene sceneID="…">` 含 `<viewController customClass="…" storyboardIdentifier="…" customModule="…">`；连线在 `<connections><segue kind="show|presentation|custom|relationship" identifier="…" destination="…"/>`；`kind="relationship" relationship="viewControllers"` 是 TabBar 子页挂载；IB 里设置的 accessibility identifier 存为 `userDefinedRuntimeAttributes` 的 `keyPath="accessibilityIdentifier"`。Git Bash 下真实可跑的枚举命令：

```bash
# scene 与控制器类清单
grep -RnoE 'sceneID="[^"]+"|customClass="[^"]+"|storyboardIdentifier="[^"]+"' --include='*.storyboard' .
# segue 关系（导航图原始边）
grep -RnoE '<segue[^>]*(kind|relationship)="[^"]+"[^>]*' --include='*.storyboard' .
# IB 无障碍标识（XCUITest 取证的前置资产，见 §4）
grep -RnoE 'keyPath="accessibilityIdentifier" value="[^"]+"' --include='*.storyboard' .
# 纯代码 UIKit 路由（programmatic UI 不走 storyboard）
grep -RnoE 'performSegue|instantiateViewController\(withIdentifier|present\(|dismiss\(' --include='*.swift' .
```

**范式 B：SwiftUI**。视图树 = `struct X: View` 的 `body`；导航/弹层锚点全在修饰符与容器：

```bash
grep -RnoE 'NavigationStack|NavigationView|NavigationLink|navigationDestination|TabView|\.sheet\(|\.fullScreenCover|\.alert\(|\.confirmationDialog' --include='*.swift' .
grep -RnoE 'struct [A-Za-z0-9_]+: *View' --include='*.swift' .           # 视图清单
grep -RnoE '@State|@Binding|@EnvironmentObject|@AppStorage|@Observable' --include='*.swift' .  # 状态范式
grep -RnoE '\.accessibilityIdentifier\("[^"]+"\)' --include='*.swift' .  # SwiftUI 侧取证 id（同 IB 扫描目的）
```

**混合工程判定**：同时命中 `customClass=`（storyboard）与 `struct …: View`（SwiftUI）→ 双范式分别扫，用 `UIHostingController` 出现处标注桥接点。**防"普通 View 被当页面"**：SwiftUI 只把持有 `NavigationStack`/`TabView`/被 `navigationDestination`/`NavigationLink` 指向、或被 `.sheet`/`.fullScreenCover` 挂载的结构体算承载面；UIKit 只把 `UIViewController` 子类 + storyboard scene 算承载面，`UIView`/cell 子类归 component。

**§3C Swift 行为锚点清单（迁移高危行为 → grep 锚点 → 六要素关联）**。以下锚点全部是 Apple 公开 API 名，任何机器 grep 即可复核；命中即须在 feature-map 登记并评估迁移语义（六要素编号见 §6）：

| 行为类别 | grep 锚点（真实 API 名） | 迁移风险 → 关联要素 |
|---|---|---|
| 应用/场景生命周期 | `applicationDidFinishLaunching` / `sceneDidBecomeActive` / `sceneWillResignActive` / `applicationDidEnterBackground` / `applicationWillTerminate` | 后台刷数据、退场保存等隐式行为极易迁漏 → 对应 UIAbility `onForeground/onBackground/onDestroy`，关联 ④重启后状态 ⑤副作用 |
| 页面显隐 | `viewWillAppear` / `viewDidAppear` / `viewWillDisappear` / SwiftUI `onAppear` / `onDisappear` | 进页面拉数据/埋点 → 对应 `aboutToAppear/aboutToDisappear`，关联 ②操作序列 ⑤副作用 |
| 系统通知监听 | `NotificationCenter.default.addObserver` / `NotificationCenter.default.publisher(for:` / `UIApplication.didBecomeActiveNotification` | 生命周期联动逻辑分散在各监听点 → 关联 ⑤副作用 |
| 定时器 | `Timer.scheduledTimer` / `DispatchSourceTimer` / `Timer.publish` | 前后台暂停/恢复语义差 → 关联 ③数据变化 |
| 后台任务 | `beginBackgroundTask` / `BGTaskScheduler` / `BGAppRefreshTask` | 鸿蒙后台机制不同，默认 PLATFORM_DEVIATION → 关联 ⑤副作用 |
| 深链/URL Scheme | `onOpenURL` / `openURLContexts` / `application(_:open:options:)` + Info.plist `CFBundleURLTypes` | 鸿蒙 Deep Linking/App Linking 配置位不同 → 关联 ②操作序列 |
| 推送处理 | `didReceiveRemoteNotification` / `UNUserNotificationCenter` delegate / `willPresent notification` | Push Kit 替换 + 前台展示语义 → 关联 ⑤副作用 |
| 剪贴板/分享 | `UIPasteboard` / `UIActivityViewController` / `ShareLink` | 粘贴板权限提示语义不同 → 关联 ②⑤ |
| 权限请求 | `requestAuthorization`（`CLLocationManager` / `AVCaptureDevice` / `PHPhotoLibrary`） | 权限弹窗时机与拒后行为须进契约 → 关联 ②操作序列 |
| 键盘/输入焦点 | `UITextFieldDelegate` / `UIKeyboardWillShow` 通知 / `@FocusState` | 键盘避让语义 → 关联 ④可见结果 |

**可选增强（不作为必经步骤）**：Swift 官方工具链支持 Windows（swift.org），装好后可用 SwiftSyntax（github.com/swiftlang/swift-syntax）做源码精确 AST 解析；`swiftc -dump-ast` 需全模块依赖可解析，跨模块工程常失败——Phase 2 用上述 grep + xcodeproj 已足够，AST 属深挖手段。

## §4 运行取证（**需 macOS + Xcode**，命令细节已实测核对）

前置事实：Xcode 9+ 起 `xcodebuild test` 默认 headless 跑模拟器（CI 友好）；`xcrun simctl` 管理设备生命周期；结果包 `.xcresult` 用 `xcrun xcresulttool` 导出（Xcode 16+ 新语法 `get test-results`，旧 `get object` 已标 deprecated——2026-09-01 于 Xcode 27 实测确认；以本机 `xcrun xcresulttool get --help` 为准）。

**步骤 0：环境与设备自证（留痕 evidence/env）**

```bash
xcodebuild -version && xcodebuild -showsdks && xcrun simctl list runtimes
xcrun simctl list devices available    # 设备名以本机输出为准（Xcode 版本不同机型名不同：16.x 系 iPhone 16，27.x 系 iPhone 17）
```

**步骤 1：模拟器生命周期（取证 run 的前置复位）**

```bash
xcrun simctl boot "<iPhone 型号>"              # 机型名来自上一步输出；已 boot 报错属正常幂等
xcrun simctl bootstatus "<iPhone 型号>" -b     # 阻塞等待开机完成
open -a Simulator                              # 显示 GUI（headless 取证可省）
xcrun simctl shutdown all && xcrun simctl erase all   # 冷复位：erase 清空数据，等价恢复出厂，持久化取证前必做
```

**步骤 2：构建/安装/启动/驱动**

```bash
# 构建（产物在 DerivedData 或 -derivedDataPath 指定目录）
xcodebuild -project X.xcodeproj -scheme X \
  -destination 'platform=iOS Simulator,name=<iPhone 型号>' \
  -derivedDataPath build | tee build.log
xcrun simctl install booted build/Build/Products/Debug-iphonesimulator/X.app
xcrun simctl launch booted <bundle.id>          # 回显 pid；可加 --console-pty 附 stdout 日志
xcrun simctl terminate booted <bundle.id>       # 杀进程：persistence 维"冷重启重放"用
```

**步骤 3：取证采集（快照/录屏/主题/权限）**

```bash
xcrun simctl io booted screenshot evidence/chains/<bc_id>/before.png   # 老形态 simctl screenshot booted 亦可用
xcrun simctl io booted recordVideo --codec=h264 evidence/chains/<bc_id>/replay.mp4   # 过程录屏，Ctrl-C 结束
xcrun simctl ui booted appearance dark          # 深/浅色切换：主题类契约取证
xcrun simctl privacy booted reset all <bundle.id>   # 权限状态复位；亦可 grant/revoke <service> 预置权限免弹窗
```

**步骤 4：数据探针（persistence 维，应用侧自报不算，直接读落盘）**

```bash
CONTAINER=$(xcrun simctl get_app_container booted <bundle.id> data)
plutil -p "$CONTAINER/Library/Preferences/<bundle.id>.plist"    # UserDefaults 落盘 k-v（前后各读一次做差分）
sqlite3 "$CONTAINER/Library/Application Support/<store>.sqlite" '.tables'   # Core Data（NSSQLiteStoreType 时），前后快照差分
```

**步骤 5：行为取证（把 GAP 名单行为契约写成 XCUITest 后执行）**

```bash
xcodebuild -project X.xcodeproj -scheme X \
  -destination 'platform=iOS Simulator,name=<iPhone 型号>' \
  test -resultBundlePath evidence/chains/<bc_id>/run.xcresult
xcrun xcresulttool get test-results summary --path evidence/chains/<bc_id>/run.xcresult   # 机器可读摘要
```

XCUITest 断言形态（对应 inventory-core 行为契约的 result_assertions）：

```swift
let app = XCUIApplication()
app.launch()                                            // 可加 launchArguments 隔离测试数据
let cell = app.cells["noteCell_0"]                      // 优先 accessibilityIdentifier 查询，抗本地化
XCTAssertTrue(cell.waitForExistence(timeout: 5)); cell.tap()
```

**探索性遍历（monkey 类）**：iOS **无官方 monkey 等价物**（Android `adb shell monkey` 在 iOS 无对应子命令，如实登记不虚构）。已知第三方：SwiftMonkey（Zalado 开源，基于 XCUITest 基础设施随机 tap/swipe，https://github.com/zalando/SwiftMonkey ，维护状态 `PENDING_CONFIRM`）；idb（facebook/idb，曾提供 UI 描述/点击 CLI，项目已归档停维护 `PENDING_CONFIRM` 后继）。半自动替代：Xcode → Open Developer Tool → **Accessibility Inspector** 浏览模拟器内 app 的 AX 树，辅助定位元素与 id 缺口。

注意事项：① **前置改造**——XCUITest 依赖 `accessibilityIdentifier`（SwiftUI 用 `.accessibilityIdentifier()`，IB 见 §3），补 id 属于修改冻结的 app 源码，须经 controller 批准新基线，不许为取证私改；② 权限弹窗用 `addUIInterruptionMonitor(withDescription:)` + 触发 `app.tap()` 处理，或以 `XCUIApplication(bundleIdentifier: "com.apple.springboard")` 点系统弹窗；③ 证据 = xcresult 断言记录 + before/after 截图 + 命令与 exit code，三者齐备才可把 GAP 升级 CONFIRMED。

## §5 持久化与系统能力风险面（含鸿蒙侧初判，供 Phase 4 裁决）

**持久化面（静态锚点 → 鸿蒙初判载体）**：

| iOS 机制 | 静态锚点 | 鸿蒙初判 | 备注 |
|---|---|---|---|
| UserDefaults | `UserDefaults.standard` / `@AppStorage("k")` | `@ohos.data.preferences` | k-v 明文，语义同构 |
| Keychain | `SecItemAdd/SecItemUpdate/SecItemCopyMatching`；依赖 KeychainAccess 等 | Asset Store Kit（关键资产，import 名待验证） | 设备级加密与卸载语义**不同**，需 PLATFORM_DEVIATION 复核 |
| Core Data | `NSPersistentContainer` + `.xcdatamodeld/contents`(XML 可解析) | RelationalStore（RDB） | 模型→表结构映射在 data-relations 里显式登记 |
| 文件 | `FileManager` + `documentsDirectory` | `@ohos.file.fs` + `Context.filesDir` | 沙箱路径重映射 |
| iCloud | `NSUbiquitousKeyValueStore` / CloudKit 容器 | 无直接等价 | 默认 GAP / 自建后端，人工裁决 |

**系统服务强绑定（entitlements/imports 命中即登记候选 PLATFORM_DEVIATION）**：APNs（`aps-environment`）→ Push Kit（待验证）；HealthKit → 运动健康类 Kit（待验证）；StoreKit/IAP → 华为应用内支付；PassKit/Wallet、HomeKit、SiriKit → 无直接等价；LocalAuthentication（Face ID）→ 用户认证 Kit（待验证）；CoreLocation → Location Kit；UserNotifications（本地通知）→ `@ohos.notificationManager`。**裁决口径**：能语义等价替换的进"允许的平台替换"清单（Gate 1 冻结）；不能的进 excluded 或 PLATFORM_DEVIATION，不许静默降级功能。

## §6 与 inventory-core 六要素的对接点（静态锚点 ↔ 运行取证分工）

| 六要素 | 静态来源（§1/§3/§5，任何机器） | 运行取证来源（§4，需 macOS+Xcode） |
|---|---|---|
| ①意图 | feature-map 一句话语义 + 功能入口锚（IB action / SwiftUI `Button` 所在 file:line） | —（意图不由运行证明） |
| ②操作序列 | §3 accessibilityIdentifier 清单 + §3C 深链/权限请求锚点 | XCUITest 脚本按 id 逐条 `tap()/typeText()`，录屏作重放凭证 |
| ③数据变化 | §5 持久化 API 写点（`set(_:forKey:)`/`save()` 所在 file:line） | §4 步骤 4 探针：plutil/sqlite3 前后读数差分 |
| ④可见结果 | UI 组件锚（sceneID / `struct: View`） | §4 步骤 3 截图 + XCUITest `waitForExistence` 断言 + xcresult 记录 |
| ⑤重启后状态 | §5 持久化机制结论（有无/何处/语义） | terminate → erase 否（保留数据）→ launch 后探针再读 |
| ⑥副作用 | §3C 系统服务调用点 + entitlements 清单 | 有通道的实测（通知中心/权限页）；无公开通道的按 verify-core 标 MANUAL，不自动 MATCH |

对接铁律：**静态锚点只证明"契约出处真实"，运行证据才证明"行为确实发生"**——GAP 升级 CONFIRMED 必须落在运行侧产物（xcresult/截图/探针读数）上。

## 参考（调研来源，真实 URL；不确定项已标 PENDING_CONFIRM）

- ArkTrans：Porting Declarative UI to HarmonyOS: A Heuristic-guided LLM Approach（arXiv:2606.07085）——启发式提取源端 UI 元数据构造 ArkUI 骨架 + LLM 翻译 + 规则后修复，90.67% 可编译；本套件 scaffold 的"骨架先行"映射表直接借鉴：https://arxiv.org/abs/2606.07085
- Java2ArkTS（LLM 转换器工程化先例）：https://github.com/Java2ArkTS/Java2ArkTS
- 华为 ArkUI 组件导航 Navigation 官方文档（已核验全文：NavPathStack/NavDestination/router_map.json/onBackPressed）：https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-navigation-navigation
- ArkUI 开发入门：https://developer.huawei.com/consumer/cn/arkui/devstart/
- Swift→ArkTS 官方迁移对照（语法/范式映射口径）：https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-for-other-languages
- Asset Store Kit（Keychain 等价初判载体）指南：https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/asset-store-kit （`PENDING_CONFIRM` URL 以文档站搜索为准）
- SwiftUI→ArkUI 思维转换（华为云社区）：https://bbs.huaweicloud.com/blogs/480637
- iOS 开发者迁 HarmonyOS 指南：https://www.harmony-developers.com/p/harmonyos-next-is-integrated-with
- Apple：SwiftUI https://developer.apple.com/documentation/swiftui ；SwiftUI Tutorials（Landmarks 工程，最小验证候选）https://developer.apple.com/tutorials/swiftui ；UIKit https://developer.apple.com/documentation/uikit ；NavigationStack https://developer.apple.com/documentation/swiftui/navigationstack ；XCUIApplication https://developer.apple.com/documentation/xctest/xcuiapplication ；ViewController https://developer.apple.com/documentation/uikit/displaying-and-managing-views-with-a-view-controller ；UserDefaults https://developer.apple.com/documentation/foundation/userdefaults ；Keychain Services https://developer.apple.com/documentation/security/keychain-services ；Core Data https://developer.apple.com/documentation/coredata
- simctl/xcresulttool 无独立 Web 文档页，以 `man simctl` / `xcrun simctl help` / `xcrun xcresulttool get --help` 为准（子命令集 2026-09-01 于 macOS 27.0 + Xcode 27.0 实测核对）
- SwiftMonkey（iOS 随机 UI 遍历，第三方）：https://github.com/zalando/SwiftMonkey （维护状态 `PENDING_CONFIRM`）；idb（已归档）：https://github.com/facebook/idb （后继 `PENDING_CONFIRM`）
- 最小验证候选工程集：twostraws/HackingWithSwift（大量小型 UIKit/SwiftUI demo 工程）https://github.com/twostraws/HackingWithSwift
- Xcodeproj Ruby gem（已核验）：https://github.com/CocoaPods/Xcodeproj ；SwiftSyntax（已核验）：https://github.com/swiftlang/swift-syntax
- xcodebuild headless 模拟器：https://stackoverflow.com/questions/47302665/ ；模拟器 runtime 下载：https://www.donnywals.com/installing-simulator-runtimes-from-the-command-line/
