---
name: ios-to-harmony-phone-controller
description: iOS 应用迁移到鸿蒙手机的治理薄壳（引用通用 controller-core，声明本路径源端运行取证默认不可用的降级策略与 mac 补取证闭环协议）。何时用：iOS → HarmonyOS 手机迁移 run 的四阶段门禁治理；何时不适用：源端可在本机运行取证的其他路径，或目标端非手机。
---

# iOS → 鸿蒙手机 迁移控制器（薄壳）

## 引用

- `skills/_shared/controller-core.md` —— 四阶段门禁 / 人工审核 / 失败路由 / 防伪铁律**全部继承**，本文件不重复，只声明本路径差异。
- `skills/_shared/00-CONVENTIONS.md` —— 撰写与引用规范、工具链双平台路径总表。
- `skills/_shared/inventory-ios.md` —— §4 运行取证命令细节（mac 补取证的事实来源）。

## 本路径差异：源端运行取证默认不可用（降级 + mac 补证闭环）

- **如实声明**：执行本 skill 的机器通常非 macOS（Windows/Linux），无 Xcode / swiftc / simctl，**iOS 源端运行取证默认不可用**。开工时以环境自证留痕：`command -v xcodebuild swiftc` 与 `xcrun simctl list devices 2>&1`（无 Xcode 时报错原文也是证据），存为 TOOL_ABSENCE 证据，作为降级依据而非假设。
- **降级规则**：controller-core 第 2 阶段"高风险功能真实运行取证"在本路径默认降级为 `SOURCE_CONFIRM + GAP`——每条 GAP 记 feature_id + 原因码 `SOURCE_RUNTIME_UNAVAILABLE(需 macOS+Xcode)`。**禁止**虚构任何 iOS 运行取证记录：伪造 `xcodebuild`/`simctl`/`xcresult` 输出、用演示数据冒充 iOS 模拟器截图，均触犯 controller-core 防伪红线。
- **静态证据仍然可核验**：Swift 源码、Storyboard/XIB XML、`project.pbxproj`、Info.plist、entitlements 均为纯文本，任何机器可按 `文件:行` / `sceneID` 复核（静态行为锚点清单见 `inventory-ios.md` §3C）。这是本路径 Phase 2 的事实底线：静态锚点真实、完整、可复算。
- **目标端不降级**：鸿蒙手机模拟器（DevEco Studio Phone Emulator）真实可用，Phase 3/4 目标端构建/安装/启动/差分与其他手机路径同标准，无任何豁免。

## mac 补证闭环协议（补证不是"改记录"，是新证据链）

1. **触发**：任一 GAP 可由用户在 mac 上补做运行取证（命令形态见 `inventory-ios.md` §4，含模拟器生命周期/安装启动/截图/数据探针/XCUITest）。
2. **补证工单**：controller 签发四段式工单（MUST READ = 该 GAP 的行为契约与静态锚；MUST DO = §4 对应命令；MUST PRODUCE = xcresult + before/after 截图 + 探针读数 + 命令与 exit code；FORBIDDEN = 代填/推测/转写二进制证据内容）。
3. **证据取代规则**：补证产物以**新 evidence ID 取代旧记录**（旧 GAP 不删，标 `superseded_by`），随后 reconciliation 重算：GAP → CONFIRMED 或 CONFLICT（实测与静态契约矛盾时走 CONFLICT 人工解释，不许静默改契约）。
4. **核验后再入账**：Agent 侧仅核验产物与登记命令一致（文件哈希、时间戳），不解读 xcresult 二进制本体；读不了时让用户以 `xcresulttool get test-results summary` 导出文本摘要后**原样附上**。
5. **Gate 2 复核**：补证后 Gate 2 重算——`source_oracle_status` 由 `UNAVAILABLE_STATIC_ONLY` 升级为 `PARTIAL_RUNTIME`（列出已升级 bc_id 清单），人工重审后方可推进。
6. **Phase 4 联动**：已补证功能的差分从"源端锚点比对"升级为"源端运行 oracle"（三态路由见 `skills/ios-to-harmony-phone/implementation.md`）。

## 双端环境指纹（Gate 1 冻结用，Mac/Windows 双式见 00-CONVENTIONS 总表）

| 端 | 冻结项 | 自证命令 |
|---|---|---|
| 源端（mac，补取证时） | macOS 版本 / Xcode 版本 / 模拟器 runtime 与机型 | `sw_vers && xcodebuild -version && xcrun simctl list runtimes`（iOS 工具链仅 Mac 形态，如实登记） |
| 目标端（本机） | DevEco 版本 / SDK / 模拟器镜像 | Windows：`"D:\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe" list targets`；macOS：`/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc list targets` |

## 最小验证设想

一台 Windows 机器 + 任一开源 iOS 工程（GitHub 小型 demo，如 twostraws/HackingWithSwift 中的 UIKit 或 SwiftUI 单页示例）：Phase 2 全静态产物（surface-index / feature-map / behavior-contracts / data-relations）可生成并独立复核；同 run 内鸿蒙侧冒烟真实执行；iOS 运行项全部显式 GAP 列出，等待用户 mac 补证后闭包（补证链路可逆性验证见 implementation.md 最小验证设想）。

## 参考

- 华为 ArkUI Navigation 官方文档（NavPathStack/onBackPressed，映射口径依据）：https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-navigation-navigation
- Swift→ArkTS 官方迁移对照：https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-for-other-languages
- Apple Xcode/Simulator 工具链文档区：https://developer.apple.com/documentation/xctest/xcuiapplication ；SwiftUI https://developer.apple.com/documentation/swiftui ；UIKit https://developer.apple.com/documentation/uikit
- simctl/xcodebuild 取证命令细节与实测留痕：`skills/_shared/inventory-ios.md` §4（无独立 Web 文档页，以 `man simctl` / `xcrun simctl help` 为准）
- ArkTrans（骨架先行迁移方法论出处）：https://arxiv.org/abs/2606.07085
