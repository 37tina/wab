---
name: inventory-macos
description: macOS 应用静态分析共享附录：工程形态判定、Xcode 工程(pbxproj/SPM)解析、SwiftUI/AppKit 三范式静态扫描与行为锚点清单、.app bundle 解剖、Info.plist/entitlements 风险面，以及 mac 执行机上的运行取证可执行命令细节（AX 树导出/驱动/快照/defaults/Keychain 探针）。供 mac 源端的 inventory 薄壳引用；所有命令区分 CROSS_PLATFORM / MAC_NATIVE / MAC_TCC_GATE 三档。
---

# macOS 静态分析附录（inventory-macos）

**定位**：回答"如何全面理解一个 macOS 应用，以及源端取证怎么真跑"（四问之一）。本附录是事实来源清单：什么能静态看、用什么命令看、结论锚到哪里。与 iOS 路径的关键不同：**macOS 源端就是桌面进程——Agent 执行机若是 macOS，源端运行取证可直接执行（AX API 驱动、`defaults` 读偏好、`screencapture` 截图），不降级**；执行机非 macOS 时才整体降级为静态 + GAP（降级口径由 mac 薄壳 controller 声明）。目标端（鸿蒙 PC）事实由 `scaffold-core-pc.md` 与华为官方文档承担，不在本文件。

## Non-negotiable

- 静态证据必须**可独立复核**：每条结论附工具 + 可重演命令（grep/plistlib 等），第三方跑同命令得同结果才算证据；手抄清单不算。
- 三档工具真实性，声明即约束：`CROSS_PLATFORM`（纯静态：Python/grep/node，任何机器可跑）/ `MAC_NATIVE`（mac 执行机原生可用：swift 脚本、osascript、screencapture、defaults、security、plutil、xcodebuild）/ `MAC_TCC_GATE`（MAC_NATIVE 之上还需系统"辅助功能/屏幕录制"授权，受授权阻碍时记 TOOL_GAP 不许绕过或降级编造）。2026-09-01 已在 macOS 27.0 + Xcode 27.0 实测的条目在 §5.7 留痕。
- 运行取证禁止编造：任何 AX 树/截图/defaults 读数必须是真实命令输出；读不了的东西（如闭源二进制内部行为）标 `PENDING_CONFIRM`，禁止臆断。
- **Keychain 红线**：只验证条目存在性与属性（`security find-generic-password` 不带 `-w`），**禁止导出明文凭据**（不使用 `-w`、不使用 `dump-keychain`）。

## 1. 工程形态判定（第一步先做）

| 形态 | 判定特征（静态可见） | 对 surface 枚举的影响 |
|---|---|---|
| Xcode App 工程 | `<App>.xcodeproj/project.pbxproj` + `Contents/Info.plist` | Storyboard 与 SwiftUI 混合可能，逐文件判定范式 |
| SwiftPM 纯包 | `Package.swift`（`.executableTarget`；桌面 App 需 Xcode 工程或 `swift build` + AppKit 手搭） | 纯代码 AppKit/SwiftUI 视图树，无 storyboard |
| 仅二进制分发 | `X.app` bundle（无源码） | 走 §4B bundle 解剖；UI 语义从 Info.plist/资源/AX 树（mac 执行机）取 |
| Workspace 多工程 | `.xcworkspace/contents.xcws` + Podfile/Podfile.lock | 依赖闭包必须并入指纹 |
| 混合 | 以上叠加 | 以 buildPhase 的源文件清单为准 |

辅助命令（CROSS_PLATFORM，Windows 亦可）：`find . -name "*.xcodeproj" -o -name "*.xcworkspace" -o -name "Package.swift" -o -name "*.storyboard" -o -name "*.xib"`。

## 2. Xcode 工程解析（pbxproj 与 SPM）

- `project.pbxproj` 是 **OpenStep plist 文本格式**（非 XML）：`PBXFileReference`（文件登记）、`PBXBuildFile`（编译单元）、`PBXNativeTarget`（产物）、`PBXSourcesBuildPhase`（源文件集合）、`XCConfigurationList`（MACOSX_DEPLOYMENT_TARGET、PRODUCT_BUNDLE_IDENTIFIER、CODE_SIGN_ENTITLEMENTS 等关键配置）。
- 跨机器解析手段（pbxproj 无 plutil 可用）：
  - 首选：Python 正则/分节解析提取 `PBXFileReference` 路径与 `PBXNativeTarget`（CROSS_PLATFORM，纯文本无需安装）；
  - 可选：`pip install pbxproj`（kronenthaler/mod-pbxproj）结构化读写；
  - 可选：Ruby `xcodeproj` gem（CocoaPods 同款）。
- SPM：`Package.swift`（依赖与 target 声明）+ `Package.resolved`（精确版本闭包，**必须进 Gate 1 指纹**）。
- MAC_NATIVE（mac 执行机直接可用）：`xcodebuild -list / -showBuildSettings`（工程指纹自证）；`swiftc -frontend -dump-ast` 对 `import AppKit/SwiftUI` 文件做类型级 AST（Windows 上即使装 Swift 工具链也拿不到 Apple SDK，仅纯逻辑文件可用）。

## 3. surface 枚举与 source_refs（三类 UI 范式 + 行为锚点）

**A. SwiftUI 声明式**（扫描 `.swift` 文本，CROSS_PLATFORM：grep/rg）：
- 视图：`^\s*(private |final |public )?struct\s+(\w+)\s*:\s*[^{]*\bView\b` → page/component 候选（再按"是否被 TabView/NavigationSplitView 顶层引用"分级，防普通组件被当页面）。
- 场景：`@main` + `WindowGroup|Window\b|Settings|MenuBarExtra|DocumentGroup` → 应用级窗口面（菜单栏应用 = MenuBarExtra/NSStatusItem 特有风险面）。
- 弹层：`\.sheet\(|\.alert\(|\.confirmationDialog\(|\.popover\(` → sheet·dialog 面（含宿主 = 修饰符所在 struct）。
- 导航：`NavigationStack|NavigationSplitView|TabView` → 容器面（container，不建壳）。
- source_refs 锚：`文件路径:struct声明行号`。

**B. Storyboard/XIB**（XML 文件，CROSS_PLATFORM：ElementTree 解析；`plistlib` 不适用于 storyboard）：
- AppKit storyboard 根：`<document type="com.apple.InterfaceBuilder3.Cocoa.Storyboard.XIB...">`；`<scenes>` 下每个 `<scene sceneID="...">` 一个界面单元；`storyboardIdentifier="..."` 是运行时查找键；`<segue kind="modal|sheet|popover|relationship" identifier="...">` 给出弹层与 containment 关系。
- source_refs 锚：`文件名#sceneID`（无 identifier 时）或 `文件名#storyboardIdentifier`。
- 仅二进制分发时 storyboard 已编译为 `.storyboardc`：优先找源仓库；确无源码可用 mac `ibtool` 反编译（MAC_NATIVE，输出保真度 `PENDING_CONFIRM`）。

**C. AppKit 代码式**：`NSWindowController/NSViewController` 子类、`NSStoryboard(name:)`、`applicationDidFinishLaunching` 中的窗口装配 → `ui_paradigm: appkit`，锚 `file:line`。

**§3D AppKit/SwiftUI 行为锚点清单（桌面特有高危行为，grep 即可复核）**：

| 行为类别 | grep 锚点（真实 API 名） | 迁移风险 |
|---|---|---|
| 应用生命周期 | `applicationDidFinishLaunching` / `applicationWillTerminate` / `applicationShouldTerminateAfterLastWindowClosed` | 最后窗口关闭即退出（true）vs 常驻——鸿蒙 PC 窗口/生命周期语义解耦，必须显式裁决 |
| 窗口行为 | `NSWindowDelegate` 的 `windowWillClose` / `windowDidChangeScreen`；`NSWindow` `collectionBehavior` / `level` | 多窗口拓扑与多显示器行为 → window-topology.json |
| 全局菜单栏 | `mainMenu` / `NSMenu` / `validateMenuItem` / `MenuBarExtra` / `NSStatusItem` / `setActivationPolicy` | 鸿蒙 PC 无全局菜单栏对等物 → APPROVED_DEVIATION 候选 |
| 快捷键 | `keyEquivalent` / `.keyboardShortcut(` / `performKeyEquivalent` / `NSEvent.addLocalMonitorForEvents` / `ModifierFlags` | ⌘/⌥ 修饰键体系 → 鸿蒙快捷键逐条映射（KeyEvent 系） |
| Dock 行为 | `NSApp.dockTile` / `LSUIElement`（Info.plist） | 无 Dock 图标的后台/菜单栏应用形态 |
| 定时器/通知 | `Timer.scheduledTimer` / `NSWorkspace` 通知（`didLaunchApplicationNotification` 等） | 桌面事件联动逻辑易迁漏 |
| 文档型应用 | `NSDocument` / `DocumentGroup` / `CFBundleDocumentTypes` | 文档生命周期/自动保存语义 |
| 自动化外发 | `NSAppleScript` / `NSAppleEventManager` / `open -e` Apple Event | 无对等，副作用登记 |
| 拖放 | `registerForDraggedTypes` / `NSDraggingDestination` | 鸿蒙 onDrag 接口族映射 |
| 沙盒书签 | `bookmarkData(with:` 含 `withSecurityScope` | security-scoped bookmark 无等价 → 数据访问路径重设计 |

枚举产物必须由上述工具命令生成（surface-index.csv），禁止手抄；三类范式以 `ui_paradigm` 列区分。

## 4. 配置与风险面静态扫描

**§4A 配置文件**：
- `Info.plist`（XML 或二进制 plist，Python `plistlib.load` 双格式均可，CROSS_PLATFORM）：`LSUIElement`（无 Dock 图标的背景/菜单栏应用）、`LSMinimumSystemVersion`、usage description 键（NSCameraUsageDescription 等 → TCC 权限面）、`CFBundleDocumentTypes`（文档型应用 → DocumentGroup 语义）。
- `*.entitlements`（XML plist）：`com.apple.security.app-sandbox`（是否沙盒）、`com.apple.security.*`（文件/网络/设备例外）、`keychain-access-groups`（Data Protection Keychain 使用 → 数据迁移风险）。
- 持久化静态结论（写进 data-relations 的 reference 列）：
  - UserDefaults：`UserDefaults.standard` 使用点 + 自定义键集合（`set(_:forKey:)` 扫描）；**沙盒与否决定落盘位置**（`~/Library/Containers/<bundleid>/Data` 容器内外的 `Preferences/<bundleid>.plist`）。
  - Keychain：`SecItemAdd/SecItemCopyMatching` 使用点 → 鸿蒙侧需映射到安全凭据存储并记差异。
  - Core Data：`.xcdatamodeld`（目录内 `contents` XML）→ 实体/关系即数据契约输入。
  - 文件系统：`FileManager` 写点 + `NSURL/bookmarkData` → 沙盒安全书签（security-scoped bookmarks）特有行为。
- 菜单栏与 Dock 行为（特有风险面）：`NSMenu/mainMenu`、`NSStatusItem`、`NSApp.setActivationPolicy`、`LSUIElement`——迁移到鸿蒙 PC 无全局菜单栏对等物，一律 Gate 1 登记 `APPROVED_DEVIATION` 候选。

**§4B .app bundle 解剖（仅二进制分发时的静态事实来源，CROSS_PLATFORM）**：

| 路径 | 判定什么 |
|---|---|
| `X.app/Contents/Info.plist` | bundle id（`CFBundleIdentifier`）、`LSUIElement`、文档类型、最低系统版本——等价于源码工程的 Info.plist 事实 |
| `X.app/Contents/MacOS/X` | Mach-O 主可执行；`strings`/`nm` 粗查符号可发现框架依赖（AppKit/SwiftUI 混用痕迹） |
| `X.app/Contents/Frameworks/` | 捆绑动态库（依赖闭包） |
| `X.app/Contents/Resources/` | 资产：`.car`（Asset 编译产物）、`.strings`（多语言清单）、`.storyboardc`（编译后 storyboard，见 §3B） |
| `X.app/Contents/_CodeSignature/CodeResources` | 签名资源清单（文件级哈希表）——Gate 1 冻结二进制指纹的现成来源 |

## 5. 运行取证（mac 执行机可执行——本路径与 iOS 的关键差异：源端是本机进程，无需模拟器）

macOS 应用**不需要模拟器**：构建产物 `.app` 直接 `open` 启动即为本机进程，AX API 可直接驱动。命令细节如下（档位标注见 Non-negotiable 三档）。

**§5.1 权限前置自证（MAC_TCC_GATE，先做，留痕 evidence/env）**

```bash
cat > /tmp/ax_trust.swift <<'EOF'
import ApplicationServices
print(AXIsProcessTrusted())   // 只查询信任态，不触发弹窗
EOF
swift /tmp/ax_trust.swift     # false → 需在 系统设置→隐私与安全性→辅助功能 授权终端/IDE 后重跑
```

屏幕截图需"屏幕录制"授权（TCC）；首次执行 `screencapture` 系统会弹授权。授权受阻 → 记 TOOL_GAP 由人工授权后重取，不许跳过取证改写为猜测。

**§5.2 构建/启动/退出（MAC_NATIVE）**

```bash
# 有源码：构建 macOS 产物
xcodebuild -project X.xcodeproj -scheme X -configuration Debug \
  -destination 'platform=macOS' -derivedDataPath build | tee build.log
open build/Build/Products/Debug/X.app && pgrep -x X      # 启动并绑定 pid（AX 驱动要用）
osascript -e 'tell application "X" to quit'              # 温和退出（persistence 维重启重放前半段）
# 仅二进制分发：跳过构建，直接 open /path/to/X.app
```

**§5.3 AX 树导出与驱动（MAC_TCC_GATE）**——`swift ax_dump.swift > evidence/chains/<bc_id>/ax_tree.txt` 导出 AX 树；脚本（聚焦应用，递归 children，带剪枝；API 均为 ApplicationServices 公开接口）：

```swift
import ApplicationServices

func dump(_ el: AXUIElement, depth: Int) {
    var role: CFTypeRef?;  AXUIElementCopyAttributeValue(el, kAXRoleAttribute as CFString, &role)
    var title: CFTypeRef?; AXUIElementCopyAttributeValue(el, kAXTitleAttribute as CFString, &title)
    var val: CFTypeRef?;   AXUIElementCopyAttributeValue(el, kAXValueAttribute as CFString, &val)
    print(String(repeating: "  ", count: depth) + "\(role as? String ?? "?") | \(title as? String ?? "") | \(val as? String ?? "")")
    if depth < 8 {   // 剪枝防树过大；大窗口可加 kAXSubrole/位置过滤
        var kids: CFTypeRef?; AXUIElementCopyAttributeValue(el, kAXChildrenAttribute as CFString, &kids)
        if let kids = kids as? [AXUIElement] { kids.forEach { dump($0, depth: depth + 1) } }
    }
}

let sys = AXUIElementCreateSystemWide()
var app: CFTypeRef?
AXUIElementCopyAttributeValue(sys, kAXFocusedApplicationAttribute as CFString, &app)  // 或 AXUIElementCreateApplication(pid)
if let app = app as? AXUIElement { dump(app, depth: 0) }
```

驱动形态（写成 Swift 小脚本或嵌入取证程序）：坐标定位 `AXUIElementCopyElementAtPosition(sys, x, y, &el)` → 点击 `AXUIElementPerformAction(el, kAXPressAction as CFString)`；取值断言用 `AXUIElementCopyAttributeValue`（role/title/value）。AppleScript 替代形态（同一 AX 基础设施）：

```bash
osascript -e 'tell application "System Events" to tell process "X" to get name of every window'
osascript -e 'tell application "System Events" to tell process "X" to click button 1 of window 1'
```

**§5.4 快照与录屏（MAC_NATIVE / 截图需录屏授权）**

```bash
screencapture -x evidence/chains/<bc_id>/full.png          # 静默全屏
# 窗口级截图：先用 CGWindowList 拿 CGWindowID（注意：AX 的 window id ≠ CGWindowID）
swift cgwindows.swift | tee evidence/env/windows.txt       # 列 <windowID> <owner> <title>
screencapture -l<CGWindowID> evidence/chains/<bc_id>/window.png
```

`cgwindows.swift` 核心：`CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID)` 读 `kCGWindowNumber/kCGWindowOwnerName/kCGWindowName`（`kCGWindowName` 在新系统需屏幕录制授权）。

**§5.5 数据探针（MAC_NATIVE；语义出口独立于应用自报）**

```bash
# UserDefaults：非沙盒 app 直接读域；沙盒 app 读容器内落盘路径（两者都真实存在，读得到哪个用哪个）
defaults export <bundle.id> evidence/chains/<bc_id>/defaults_before.plist
defaults read <bundle.id>                                  # 快速目检
plutil -p ~/Library/Containers/<bundle.id>/Data/Library/Preferences/<bundle.id>.plist   # 沙盒落盘直读
# Keychain：只验存在性与属性（红线：不带 -w、不 dump-keychain）
security find-generic-password -s <service> -a <account> 2>&1 | tee evidence/chains/<bc_id>/keychain_probe.txt
# 文件副作用：容器/写点目录前后快照差分
diff -rq evidence/chains/<bc_id>/fs_before evidence/chains/<bc_id>/fs_after
```

**§5.6 XCUITest（macOS 目标）行为取证（MAC_NATIVE）**

```bash
xcodebuild test -project X.xcodeproj -scheme X \
  -destination 'platform=macOS' -resultBundlePath evidence/chains/<bc_id>/run.xcresult
xcrun xcresulttool get test-results summary --path evidence/chains/<bc_id>/run.xcresult
```

XCUIApplication 驱动 macOS app 的断言形态与 iOS 相同（`app.buttons["id"].tap()` + `waitForExistence`），依赖 accessibility 标签（SwiftUI `.accessibilityIdentifier()` / AppKit `accessibilityIdentifier`）。

**§5.7 工具实测留痕（2026-09-01，macOS 27.0 + Xcode 27.0）**：`swift` 脚本形态跑通（AXIsProcessTrusted 返回 true、`AXUIElementCreateSystemWide` 创建成功）；`osascript` 基础 AppleScript 执行通过；`screencapture`（usage 输出核对）、`defaults/security/plutil` 二进制存在于系统路径；`xcrun simctl`/`xcresulttool` 子命令集核对（iOS 侧见 inventory-ios.md §4）。AX 深取（CopyAttributeValue 遍历、PerformAction 驱动）与窗口截图未在取证语境下全量演练，首次执行时以 §5.1 自证输出为准。

## 6. 环境与工具三档清单（按执行机分档，取代按"本机 Windows"假设的旧口径）

| 档位 | 工具/命令 | 用途 |
|---|---|---|
| CROSS_PLATFORM（任何执行机） | Python 3 `plistlib`、`xml.etree.ElementTree`、grep/rg、node、`pip install pbxproj`（可选）、ruby+xcodeproj（可选） | Info.plist/entitlements 解析、storyboard scene 提取、SwiftUI/AppKit 正则扫描、pbxproj 结构化解析 |
| MAC_NATIVE（mac 执行机） | `xcodebuild`（build/test/-list/-showBuildSettings）、`swift`（脚本直跑）、`swiftc -dump-ast`、`osascript`（基础 AppleScript）、`defaults`、`plutil`、`security`（探针用法）、`open`/`pgrep`、`diff`、`sqlite3`、`ibtool`（storyboardc 反编译，保真度 PENDING_CONFIRM） | 构建、类型级 AST、命令行驱动辅助、偏好/Keychain 探针、窗口启动/退出、Core Data 读数 |
| MAC_TCC_GATE（MAC_NATIVE + 系统授权） | AX API 全量（CopyAttributeValue 遍历/PerformAction 驱动/ElementAtPosition）、osascript "System Events" 面向 UI 的驱动、`screencapture`、`kCGWindowName` 读取、XCUITest UI 驱动 | 源端运行取证（observable/操作序列/快照） |

执行机非 macOS 时：MAC_NATIVE/MAC_TCC_GATE 全档不可用 → RUNTIME 项降级 `SOURCE_CONFIRM + GAP_NEEDS_MAC`（口径见 mac 薄壳 controller.md）；**禁止假装跑过**。

## 7. 与 inventory-core 六要素的对接点

| 六要素 | 静态来源（§1-§4，任何机器） | 运行来源（§5，mac 执行机） |
|---|---|---|
| ①意图 | feature-map 语义 + 入口锚（menu item action / Button file:line） | — |
| ②操作序列 | §3D 快捷键/菜单/拖放锚点 + accessibilityIdentifier 清单 | §5.3 AX `PerformAction` / osascript click 按锚驱动，§5.6 XCUITest 脚本 |
| ③数据变化 | §4A 持久化写点（UserDefaults/Keychain/Core Data/文件） | §5.5 defaults/plutil/sqlite3 前后差分（探针独立于应用自报） |
| ④可见结果 | sceneID / `struct: View` / bundle 资源清单 | §5.3 ax_dump 树 + §5.4 screencapture |
| ⑤重启后状态 | §4A 持久化机制结论（含沙盒落盘位置差异） | quit → open → §5.5 再读数 |
| ⑥副作用 | §3D 自动化外发/通知/沙盒书签锚点 | 文件 diff、通知人工核验；无公开通道标 MANUAL |

## 参考来源（调研，2026-08-31 起累计；不确定项已标 PENDING_CONFIRM）

- Apple：SwiftUI App 结构（scene/view hierarchy） https://developer.apple.com/tutorials/swiftui-concepts/exploring-the-structure-of-a-swiftui-app ；scene 声明 https://developer.apple.com/tutorials/swiftui-concepts/specifying-the-view-hierarchy-of-an-app-using-a-scene ；SwiftUI 框架文档 https://developer.apple.com/documentation/swiftui ；AppKit 框架文档（NSWindow/NSMenu/NSStatusItem 类文档入口） https://developer.apple.com/documentation/appkit
- Apple：App Sandbox https://developer.apple.com/documentation/xcode/app-sandbox ；AXUIElement https://developer.apple.com/documentation/applicationservices/axuielement ；AXUIElement.h https://developer.apple.com/documentation/applicationservices/axuielement_h ；辅助功能审计（XCTest）WWDC23 https://developer.apple.com/videos/play/wwdc2023/10035/
- screencapture/defaults/security/CGWindowList 无聚合 Web 文档页，以 `man <cmd>` 与框架头文件为准（CGWindowListCopyWindowInfo 见 CoreGraphics 框架文档）
- macOS AX 树自动化实践 https://t8r.tech/t/macos-accessibility-ui-tree ；SwiftUI 内容抓取（AX API） https://medium.com/@itsuki.enjoy/swiftui-macos-contents-scrapping-with-accessibilityapi-c7e39daf2b19
- 工程解析：tuist/XcodeProj https://github.com/tuist/xcodeproj ；Tuist 工程生成 https://tuist.dev/blog/2025/02/25/project-generation ；XcodeGen/Tuist 对比讨论 https://www.reddit.com/r/swift/comments/1rf630m/xcodegen_vs_tuist_vs_bazel/
- Swift 静态分析：swift-syntax https://github.com/swiftlang/swift-syntax ；SwiftSyntax 教程 https://www.avanderlee.com/swift/swiftsyntax-parse-and-generate-swift-source-code/ ；符号图讨论 https://forums.swift.org/t/is-the-swift-symbolgraph-extract-tool-redundant/72125
- 沙盒/Keychain/UserDefaults 风险：沙盒迁移与 UserDefaults 落盘差异 https://www.reddit.com/r/swift/comments/1k0j051/risks_when_transitioning_from_sandbox_to/ ；Keychain 迁移问题 https://eclecticlight.co/2023/08/27/last-week-on-my-mac-the-problem-with-macos-keychains/ ；临时例外 entitlements https://developer.apple.com/library/archive/documentation/Miscellaneous/Reference/EntitlementKeyReference/Chapters/AppSandboxTemporaryExceptionEntitlements.html
- 真实开源 macOS App 样本（静态/取证演练对象）：AltTab（AppKit 重度，窗口管理） https://github.com/lwouis/alt-tab-macOS ；SwiftUI Tutorials（Landmarks，最小验证候选） https://developer.apple.com/tutorials/swiftui
- 迁移映射（Swift→ArkTS，官方）： https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-for-other-languages ；SwiftUI→ArkUI 思维转换 https://bbs.huaweicloud.com/blogs/480637
- 论文：DeclarUI（声明式 UI 自动实现，覆盖 ArkUI） https://dl.acm.org/doi/10.1145/3715726 ；规则驱动 Android→iOS UI 迁移 https://arxiv.org/html/2409.16656v1
