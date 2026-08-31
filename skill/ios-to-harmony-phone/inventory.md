---
name: ios-to-harmony-phone-inventory
description: iOS 应用源端理解薄壳（引用 inventory-core 九步 + inventory-ios 静态分析附录，填四项平台差异参数）。何时用：iOS → 鸿蒙手机迁移的 Phase 2 源端理解；何时不适用：已进入 Phase 3 搭壳，或源端非 iOS 工程。
---

# iOS → 鸿蒙手机 源端理解（薄壳）

## 引用

- `skills/_shared/inventory-core.md` —— 九步流程 / 行为契约六要素 / 对账四态 / 防伪口径**全部继承**。
- `skills/_shared/inventory-ios.md` —— iOS 静态分析附录：工程结构 / Xcode 工程解析 / Storyboard 与 SwiftUI 双范式扫描（§3）/ Swift 行为锚点清单（§3C）/ mac 取证命令细节（§4）/ 持久化风险面（§5）/ 六要素对接点（§6）。本文件只声明差异参数，不重复附录内容。
- `skills/ios-to-harmony-phone/controller.md` —— 源端运行取证默认不可用的降级声明与 mac 补证闭环协议。

## 平台差异参数（填 inventory-core 的表）

| 参数 | 本路径取值 |
|---|---|
| surface 枚举工具 | **双范式静态扫描**（附录 §3）：UIKit = Storyboard/XIB XML 解析（`<scene sceneID>` / `<viewController customClass storyboardID>` / `<segue identifier kind>` / `accessibilityIdentifier`）+ Swift 源码扫 `UIViewController` 子类与 `present/dismiss/performSegue`；SwiftUI = 视图树扫描（`struct X: View` 的 `body`、`NavigationStack`/`NavigationLink`/`TabView`/`.sheet`/`.fullScreenCover`/`.alert`/`.confirmationDialog`）。**产出必须由 grep/脚本遍历生成，禁止手抄清单**；混合工程两范式都要扫 |
| 运行取证工具 | **需 macOS+Xcode**：`xcrun simctl`（boot/install/launch/screenshot/io/privacy/get_app_container）+ `xcodebuild test`（XCUITest）+ `.xcresult` 证据包，命令细节见附录 §4（子命令集已实测核对）。本机（Windows）不可执行 → RUNTIME 项降级 `SOURCE_CONFIRM + GAP`（原因码 `SOURCE_RUNTIME_UNAVAILABLE`，见 controller.md） |
| source_refs 粒度 | Swift `文件:行`；Storyboard/XIB `文件名:sceneID` + storyboardID；SwiftUI 视图结构体名 + `文件:行`；Info.plist key 路径（如 `UIApplicationSceneManifest`）；entitlements 条目 |
| 特有风险面 | ① **三层持久化并存**：Keychain / UserDefaults / Core Data（重启语义各异，附录 §5）；② **系统服务强绑定**：APNs / HealthKit / StoreKit / PassKit(Wallet) / HomeKit / SiriKit / LocalAuthentication 等（鸿蒙无等价或需 PLATFORM_DEVIATION 裁决）；③ **委托与响应者链**：AppDelegate/SceneDelegate 与各 delegate 协议承载的隐式行为（如 `sceneWillResignActive` 中刷数据），静态可锚定（附录 §3C 生命周期锚点行）但极易迁漏；④ **交互范式差异**：edge-swipe 返回 / 3D Touch / 长按上下文菜单 |

## 分级验证落地（继承九步第 5 步）

- RUNTIME 名单照常圈定（增删改 / 持久化 / 账号 / 权限 / 复杂设置），但每条结论**三选一**：mac 可用 → 按附录 §4 实跑取 CONFIRMED/CONFLICT；本机无 mac → `SOURCE_CONFIRM + GAP`（带原因码）；**绝不允许写成 CONFIRMED**。
- 纯展示 / 跳转 / 容器宿主（`UITabBarController` 宿主页、SwiftUI 容器 View）一律 SOURCE_CONFIRM——静态证据链完整即闭包，不欠运行债。

## 六要素分工（继承 inventory-core 第 4 步，iOS 侧落地）

每条行为契约的六要素按附录 §6 对接表取材：①意图/②操作序列/⑥副作用的**静态锚**来自 §3 扫描与 §3C 行为锚点清单（生命周期/通知/深链/权限请求的 grep 命中行）；③数据变化/⑤重启后状态的锚来自 §5 持久化写点；④可见结果锚定到 sceneID/View 结构体。mac 补证时同一契约的运行侧证据按 §6 右列采集（截图/探针/xcresult），**静态锚与运行证据引用同一 bc_id 才可闭包**。

## 持久化面结论表（data-relations 必填）

每功能↔数据对象行须判定持久化机制并给**存在性判定锚点**：UserDefaults（`UserDefaults.standard` / `@AppStorage("key")` 出现处 file:line）/ Keychain（`SecItemAdd` 等调用或 KeychainAccess 类依赖）/ Core Data（`NSPersistentContainer` + `.xcdatamodeld` 模型文件，模型本身是 XML 可静态解析）/ FileManager（Documents 目录读写）/ iCloud（`NSUbiquitousKeyValueStore` / CloudKit）。鸿蒙侧语义等价目标载体初判见附录 §5，物理选型由 Phase 4 裁决。

## 最小验证设想

- **静态链（Windows 即可）**：取 twostraws/HackingWithSwift 中任一 UIKit 工程（含 storyboard）与任一 SwiftUI 工程，各走一遍九步：surface-index / feature-map / behavior-contracts / data-relations 全部由附录 §3 grep 命令生成、第三方重跑同命令得同清单；reconciliation 中 RUNTIME 项全部 GAP（带原因码）、SOURCE_CONFIRM 项闭包。
- **补证链（有 mac 时）**：对同一工程按附录 §4 补证（构建→模拟器安装启动→XCUITest→xcresult 导出），应能把 ≥1 条 GAP 升级为 CONFIRMED、旧记录标 superseded_by，验证降级-补证链路可逆。

## 参考

- 附录事实来源与命令实测留痕：`skills/_shared/inventory-ios.md`（§3/§3C/§4/§5/§6 + 文末参考 URL 清单）
- Apple 行为锚点 API 文档入口：UIKit https://developer.apple.com/documentation/uikit ；SwiftUI https://developer.apple.com/documentation/swiftui ；Core Data https://developer.apple.com/documentation/coredata ；Keychain Services https://developer.apple.com/documentation/security/keychain-services
- 持久化鸿蒙载体初判依据：Swift→ArkTS 对照 https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-for-other-languages ；Asset Store Kit 指南 https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/asset-store-kit （PENDING_CONFIRM）
- 最小验证候选仓库：twostraws/HackingWithSwift https://github.com/twostraws/HackingWithSwift ；Apple SwiftUI Tutorials（Landmarks） https://developer.apple.com/tutorials/swiftui
