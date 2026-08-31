---
name: mac-to-harmony-pc-controller
description: macOS 应用迁移鸿蒙 PC 的治理薄壳（四阶段门禁/人工审核/防伪返工），按执行环境两态路由源端取证：Agent 在 macOS 上时源端可直接构建/启动/AX 驱动，RUNTIME 不降级；非 mac 执行机才整体降级为静态 + GAP。迁移 macOS(AppKit/SwiftUI) 桌面应用时由 controller 加载；不写目标端代码。
---

# mac → harmony-pc 迁移控制器（薄壳）

> **执行环境两态路由（本路径最高优先级）**：macOS 源端是桌面进程——**Agent 执行机若是 macOS，源端可直接构建（xcodebuild）、启动（open）、驱动与断言（Accessibility API / XCUITest）、读偏好（defaults）、截图（screencapture），源端运行取证可用，RUNTIME 项不降级**（与 iOS 路径需模拟器全链路不同）。执行机为 Windows/Linux 时，上述能力全部不可用，RUNTIME 项整体降级 `SOURCE_CONFIRM + GAP`（原因注明"需 macOS 环境"）。开工第一件事：跑下方环境自证，把本次 run 锁定在两态之一，禁止中途含糊。

## 引用

- `skills/_shared/controller-core.md`（通用四阶段治理内核，全部铁律原样继承，本文件只补差异）
- `skills/_shared/00-CONVENTIONS.md`（撰写与引用规范、工具链双平台路径总表）
- `skills/_shared/inventory-macos.md`（macOS 静态分析附录 + §5 运行取证命令细节——两态路由的事实来源）

## 环境自证（Gate 1 冻结 source_env，留痕 evidence/env）

```bash
sw_vers && xcodebuild -version          # macOS 版本 / Xcode 版本
swift /tmp/ax_trust.swift               # AXIsProcessTrusted() 探针（脚本见 inventory-macos §5.1）
```

- 输出含 macOS 版本且 Xcode 在 → `source_env: ENV_MAC_NATIVE`（若 AXIsProcessTrusted 为 false，先走授权，见下条）。
- `command -v xcodebuild` 为空 → `source_env: ENV_NO_MAC`，全量降级。

## 本路径差异（相对 controller-core）

1. **TCC 授权受阻 = TOOL_GAP，不降级补位**（ENV_MAC_NATIVE 态）：AX 驱动需"辅助功能"授权、截图需"屏幕录制"授权；自证不通过时记 TOOL_GAP 并要求人工在系统设置授权后重取，**不许跳过取证改写为源码猜测**（对齐 windows 路径 UAC 口径）。
2. **Phase 2 完成判据按环境态分叉**：
   - ENV_MAC_NATIVE：`source_oracle_status: RUNTIME_AVAILABLE`——高风险功能真实运行取证（AX 驱动 + 探针）照 controller-core 原口径执行，**跑不动是环境问题（修环境/授权），不许降级 SOURCE_CONFIRM**；
   - ENV_NO_MAC：收紧为"高风险已**静态**确认（SOURCE_CONFIRM）或显式记 GAP"，Gate 2 报告含 `source_oracle_status: UNAVAILABLE_STATIC_ONLY`，不存在"源端真机取证通过"这一档。
3. **Phase 4 判据按环境态分叉**：ENV_MAC_NATIVE 按 verify-core 双端差分全量执行（源端真 oracle）；ENV_NO_MAC 时源端 oracle 缺失，改为**行为契约（Phase 2 冻结的六要素断言）+ 源码静态断言为 oracle**，persistence/side-effect 若只能从代码推断，判 `CONTRACT_CONFIRMED` 而非 `CONFIRMED`，禁止冒充运行级确认（细则见本套件 implementation.md）。
4. **环境态跃迁 = 新 run**：ENV_NO_MAC 的 run 后续获得 macOS 机器，controller 签发新 run 将 source_env 升级为 ENV_MAC_NATIVE 并补齐 RUNTIME 取证；旧 run 的 GAP 不回填、只在新 run 取证。
5. **平台替换审批重点**：macOS 特有面（全局菜单栏 NSMenu/MenuBarExtra、Dock 行为、Keychain、App Sandbox entitlements、Apple Event 自动化）映射到鸿蒙 PC 无对等物时，必须走 Gate 1 的 `APPROVED_DEVIATION` 登记而不是静默丢弃。
6. **范围冻结附加项**：Gate 1 必须冻结 Swift 包清单（Package.swift / Package.resolved 哈希）与 pbxproj 指纹；仅二进制分发时改冻 `X.app/Contents/_CodeSignature/CodeResources`（文件级哈希表），防止"分析期间源码漂移"。

## 目标端不豁免

鸿蒙 PC 目标端构建/安装/启动/差分照常真实执行（DevEco Studio + PC/2in1 模拟器或真机，环境要求见 `_shared/scaffold-core-pc.md`）；**手机模拟器证据对本路径无效**（自由窗口与键鼠范式不同）。

## 最小验证设想

- **ENV_MAC_NATIVE 态**：本机（macOS）取任一开源 SwiftUI macOS 示例（GitHub 带 `WindowGroup` 的小型 App，或 Apple SwiftUI Tutorials Landmarks 的 mac 形态）走 Phase 1-2：环境自证（sw_vers/xcodebuild/AX 探针）→ 构建 → `open` 启动 → ax_dump 导出 AX 树 → `defaults export` 前后读数，feature-map 的 RUNTIME 项全部真取证闭包（GAP=0），证据含真实命令输出。
- **ENV_NO_MAC 态**：同一仓库在 Windows 机上走静态流水线：Info.plist/entitlements 解析 + SwiftUI 视图树扫描产出 feature-map，检查每条 RUNTIME 均已降级且 GAP 原因含"需 macOS 环境"，全程零虚构运行证据。

## 参考

- 源端取证命令细节与实测留痕：`skills/_shared/inventory-macos.md` §5（2026-09-01 于 macOS 27.0 + Xcode 27.0 实测 swift AX 探针/osascript/screencapture 形态）
- 鸿蒙电脑(PC)与平板应用适配开发指南（目标端形态要求）：https://developer.huawei.com/consumer/cn/multidevice/pc/adapt
- Apple AXUIElement（驱动工具依据）：https://developer.apple.com/documentation/applicationservices/axuielement ；App Sandbox（entitlements 风险面） https://developer.apple.com/documentation/xcode/app-sandbox
- 真实开源 macOS App 样本（最小验证对象类型）：AltTab https://github.com/lwouis/alt-tab-macOS ；SwiftUI Tutorials https://developer.apple.com/tutorials/swiftui
