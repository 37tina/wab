---
name: mac-to-harmony-pc-inventory
description: macOS 应用源端理解薄壳（按执行环境两态路由）：ENV_MAC_NATIVE 态源端可构建/启动/AX 驱动真取证；ENV_NO_MAC 态全静态范式。何时用：Phase 2 理解 macOS(AppKit/SwiftUI) 应用时加载；环境态由 controller 的自证锁定。
---

# mac 源端理解薄壳（执行环境两态范式）

> **真实性边界（四问之二，写死在文首；环境态判定见本套件 controller.md）**：
> - **算真实（静态，任何机器）**：源码/工程文件静态证据——SwiftUI `struct X: View` 的 `file:line`、Storyboard `.storyboard` 内 `<scene>` 的 sceneID/identifier、Info.plist/entitlements 键值、pbxproj/Package.swift 条目、`.app` bundle 解剖（Contents/Info.plist、_CodeSignature/CodeResources）。可被第三方用文本工具独立复核（`grep -n`、`python -c "import plistlib..."` 重演）。
> - **算真实（运行，仅 ENV_MAC_NATIVE）**：mac 执行机上真实执行 `xcodebuild`/`open`/AX 驱动（`ax_dump.swift`、`AXUIElementPerformAction`）/`screencapture`/`defaults export` 产生的 AX 树、截图、前后读数——命令细节见 `_shared/inventory-macos.md` §5。
> - **明确不可得（ENV_NO_MAC）**：macOS 上的运行取证（启动、驱动、截图、AX 树读取）。AXUIElement/XCUITest/AppleScript 均需 macOS + 辅助功能授权，**禁止编造任何"Mac 运行结果"**；RUNTIME 项全部降级 SOURCE_CONFIRM + GAP（原因：需 macOS 环境）。

## 引用

- `skills/_shared/inventory-core.md`（九步方法论内核；步骤 6"真实运行取证"仅在 ENV_NO_MAC 整步降级）
- `skills/_shared/inventory-macos.md`（**macOS 静态分析附录**：工程形态/pbxproj/三范式扫描/行为锚点清单(§3D)/.app bundle 解剖(§4B)/运行取证命令细节(§5)/六要素对接(§7)——本路径的主要事实来源）
- `skills/mac-to-harmony-pc/controller.md`（环境两态路由与 TOOL_GAP 口径）

## 本路径差异参数（填 inventory-core 的四参数表）

| 参数 | 本路径取值 |
|---|---|
| surface 枚举工具 | 静态扫描（两态通用）：SwiftUI 视图树（`*: View` 结构体 + scene 声明 `WindowGroup/Window/Settings/MenuBarExtra/DocumentGroup` + `NavigationSplitView/sheet/popover` 修饰符）、Storyboard scene 扫描（`<scene>`/`segue kind` XML 解析）、AppKit 代码式（NSWindowController/NSViewController 子类）；命令见附录 §3；仅二进制分发走 §4B bundle 解剖 |
| 运行取证工具 | **ENV_MAC_NATIVE**：AX API（`AXUIElementCreateApplication(pid)` + `AXUIElementCopyAttributeValue` + `AXUIElementPerformAction`；ax_dump.swift 导出树）+ XCUITest（`platform=macOS`）+ `defaults`/`security`/`plutil` 探针 + `screencapture`，命令细节见附录 §5。**ENV_NO_MAC**：不可用 → RUNTIME 全降级 `SOURCE_CONFIRM + GAP_NEEDS_MAC` |
| source_refs 粒度 | SwiftUI：`文件路径:行号`（struct 声明行）；Storyboard/XIB：`文件名#sceneID 或 storyboardIdentifier`；entitlements/Info.plist：`文件#键名`；二进制：`X.app/Contents/...` 路径 |
| 特有风险面 | Keychain（Data Protection 需签名配置；取证红线：不导明文）、UserDefaults（sandbox 与否落盘位置不同）、App Sandbox（com.apple.security.* 与容器路径 ~/Library/Containers）、菜单栏与 Dock 行为（NSMenu/MenuBarExtra/LSUIElement/激活策略）、快捷键 KeyEquivalent、多窗口 NSWindow/WindowGroup、TCC 权限声明；行为锚点 grep 清单见附录 §3D |

## 流程差异（对九步的改写，按环境态分叉）

1. 步骤 2 静态扫描分类（两态同规）：产出 surface-index 的**唯一合法来源是工具扫描**（附录 §3 命令），禁止手抄；三范式以 `ui_paradigm: appkit|swiftui|storyboard` 列区分。
2. 步骤 5 分级验证：
   - ENV_MAC_NATIVE：verify_mode 三档照 inventory-core 原样（RUNTIME 真跑）；
   - ENV_NO_MAC：三档改两档——`SOURCE_CONFIRM`（默认）与 `GAP_NEEDS_MAC`（原本会标 RUNTIME 的项），GAP 必须带 feature_id 与"需 macOS 环境"原因。
3. 步骤 6 运行取证：
   - ENV_MAC_NATIVE：**真实执行**——前置 §5.1 权限自证（AXIsProcessTrusted/屏幕录制），构建（`-destination 'platform=macOS'`）→ `open` 启动 → AX 驱动重放操作序列 → ax_dump/截图/探针采集；TCC 授权受阻记 TOOL_GAP；
   - ENV_NO_MAC：**整步跳过**，产物清单中 runtime-evidence 标注 `not_produced: source_runtime_unavailable`。
4. 步骤 7 对账：ENV_MAC_NATIVE 四态完整（CONFIRMED/CONFLICT/SOURCE_CONFIRMED/GAP）；ENV_NO_MAC 退化为三态（SOURCE_CONFIRMED / GAP / CONFLICT-静态内部矛盾）——不存在运行级 CONFIRMED。
5. 步骤 8 蒸馏：ENV_MAC_NATIVE 用真实截图作 visual-memory；ENV_NO_MAC 以"声明式 UI 文本快照"（SwiftUI body 组件序列摘要 / Storyboard scene 控件清单）替代，格式标 `static_derived`。

## 六要素分工（附录 §7 对接表的落地）

每条行为契约六要素：①意图/②操作序列静态锚 = §3/§3D 扫描命中行（菜单 action、快捷键、accessibilityIdentifier）；③数据变化/⑤重启后状态锚 = §4A 持久化写点（UserDefaults 键集、Keychain 服务名、Core Data 模型）；④可见结果锚 = sceneID/View struct；⑥副作用锚 = AppleScript/通知/沙盒书签调用点。ENV_MAC_NATIVE 态的运行证据按 §7 右列采集，**同 bc_id 静态锚与运行证据齐备才可判 CONFIRMED**。

## 最小验证设想

- **ENV_MAC_NATIVE**：本机对一个小型开源 SwiftUI macOS demo 跑全流程：`swift ax_trust.swift` 自证 → 构建 → `open` 启动 → `ax_dump.swift` 导树（surface 清单与静态扫描互核）→ `defaults export` 前后读数证明一条"设置修改→落盘→重启仍在"契约。产物全部真实命令输出。
- **ENV_NO_MAC**：Windows 上对同一仓库跑附录静态命令：`python plistlib` 解析 storyboard 提取全部 `<scene>`、`grep` 扫出全部 `struct *: View`，两者并集 = surface-index；验证每个 RUNTIME 候选项在 reconciliation.csv 中均为 `GAP_NEEDS_MAC` 且带原因。

## 参考

- 附录事实来源：`skills/_shared/inventory-macos.md`（§3/§3D/§4/§5/§7 + 文末参考 URL 清单）
- Apple：AppKit https://developer.apple.com/documentation/appkit ；SwiftUI https://developer.apple.com/documentation/swiftui ；AXUIElement https://developer.apple.com/documentation/applicationservices/axuielement ；App Sandbox https://developer.apple.com/documentation/xcode/app-sandbox
- Swift→ArkTS 官方迁移对照：https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-for-other-languages
- 最小验证候选：Apple SwiftUI Tutorials（Landmarks） https://developer.apple.com/tutorials/swiftui ；AltTab（AppKit 重度样本） https://github.com/lwouis/alt-tab-macOS
