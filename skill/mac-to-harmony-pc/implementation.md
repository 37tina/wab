---
name: mac-to-harmony-pc-implementation
description: macOS→鸿蒙 PC 的 Phase 4 实现与验证薄壳，按执行环境两态路由：ENV_MAC_NATIVE 走 verify-core 全量双端差分（源端真运行 oracle）；ENV_NO_MAC 以"冻结行为契约 + 源码静态断言"替代源端侧，目标端真实运行取证照常执行。写 HarmonyOS 代码时由 controller 派发加载。
---

# mac → harmony-pc 实现薄壳（Phase 4，oracle 策略按环境态路由）

> 环境态由 Gate 1 冻结（`source_env: ENV_MAC_NATIVE | ENV_NO_MAC`，见本套件 controller.md）。**禁止把任何静态推断表述为"源端实测"；禁止在 ENV_NO_MAC 态编造 AX 树/截图/defaults 读数。**

## 引用

- `skills/_shared/verify-core.md`（双端行为差分四维 + 修复回环内核；四维 = observable / data / persistence / side-effect，全部继承）
- `skills/mac-to-harmony-pc/scaffold.md`（键鼠/窗口交互裁决表——本阶段差分的重放依据）
- `skills/_shared/inventory-macos.md` §5/§7（源端取证命令细节 / 六要素对接）
- 官方语法迁移对照：从 Swift 到 ArkTS 的迁移指导 https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-for-other-languages （SwiftUI 与 ArkUI 同属声明式范式，状态管理与组件语义按此对照重写，不逐行翻译）

## verify-core 平台差异参数（本路径填值）

| 参数 | ENV_MAC_NATIVE | ENV_NO_MAC |
|---|---|---|
| 源端驱动与取证工具 | AX API（`AXUIElementPerformAction` 驱动 / ax_dump 树）+ XCUITest（`platform=macOS`）+ `screencapture` | 不可用（无源端运行） |
| 源端数据探针 | `defaults export` 前后差分 + `plutil -p` 沙盒落盘直读 + `sqlite3`（Core Data）+ 容器 `diff -rq`（文件副作用） | 无；以 §4A 持久化写点静态结论替代 |
| 目标端驱动工具 | hdc（`aa force-stop`/`aa start`、`snapshot_display`）+ `uitest dumpLayout`（2in1 设备，键鼠事件照契约） | 同左（目标端不降级） |
| 范式重映射表出处 | `skills/mac-to-harmony-pc/scaffold.md` 差异三（键鼠/窗口裁决表） | 同左 |

## ENV_MAC_NATIVE：全量双端差分（oracle = 源端真运行）

1. **oracle 采集（源端，mac 本机）**：对每条 RUNTIME 契约——前置对齐（`osascript quit` → 冷复位态 → `open` 启动）→ AX 驱动重放操作序列（坐标定位 `AXUIElementCopyElementAtPosition` + `kAXPressAction`）→ 采集 ax_dump 树（observable）+ `defaults export` 前后读数（data）+ quit→open 再读数（persistence）+ 容器 diff（side-effect，文件类）。oracle 指纹（app 哈希/系统版本/探针版本）冻结后缓存命中，不重跑。
2. **目标端执行与机器 A/B**：目标端（2in1 模拟器/真机）按重映射后的操作序列真跑（快捷键/hover/右键必须在 PC 形态驱动），四维直比，verdict ∈ MATCH/DIFF/MANUAL（口径全按 verify-core）。
3. **修复回环**：DIFF 只修目标端，≤2 轮转 MANUAL_TAKEOVER；只有 oracle 结果本身可疑（指纹漂移）才重采源端并留痕。

## ENV_NO_MAC：oracle 替代策略（四问之三）

1. **oracle 换源**：oracle = Phase 2 冻结的行为契约六要素断言 + 每条断言的源码静态锚（`file:line` / sceneID / plist 键 / bundle 路径）。契约本身的正确性由 Gate 2 人工审核背书，不由运行背书。
2. **四维差分的降级判定**：
   - observable：目标端真实驱动后，结果断言对照契约六要素的"可见结果"判定，证据 = 目标端截图/组件树 + 契约引用；
   - data：目标端前后状态采集（Preferences/RelationalStore 读数）对照契约"数据变化"；
   - persistence：目标端重启重放（杀进程→重启→读数）对照契约"重启后状态"；源端持久化机制仅为静态结论（如检出 UserDefaults 写点），判定标 `CONTRACT_CONFIRMED`；
   - side-effect：通知/文件/键鼠全局行为等，目标端可实测的照测；源端不可实测的（如全局快捷键注册行为）记 `GAP(需 macOS 环境)`。
3. **DIFF 只修目标端**："差异"的定义是"目标端实测 vs 契约断言"，不是"目标端 vs 源端实测"（后者本态不存在）。实现中发现源码静态证据与契约矛盾 → 回 Phase 2 走静态矛盾修复，不是改目标端。
4. **差异修复的仲裁级**：macOS 特有面（菜单栏/Dock/Keychain/sandbox 副作用/Apple Event）若鸿蒙无对等，输出 `APPROVED_DEVIATION` 清单交人工裁决，不进入自动回环。

## Keychain/凭据类差分的统一红线（两态同规）

源端凭据只验**存在性与属性**（`security find-generic-password` 不带 `-w`，不 dump-keychain）；差分断言只比对"凭据条目存在/服务名/账号"语义集合，**不比对也不传输明文**；目标端凭据载体（如关键资产存储）断言同口径。

## 目标端环境（两态同规）

DevEco Studio + 鸿蒙 PC（2in1）模拟器/真机；键盘快捷键、hover、右键、多窗口等 PC 形态交互必须在 PC 环境驱动验证，不得用 phone 模拟器替代后宣称 PC 通过。

## 最小验证设想

- **ENV_MAC_NATIVE**：挑一条增删改契约（如"新增条目→列表出现→重启仍在"）：mac 本机 AX 驱动源端真跑采 oracle（defaults 前后读数 + ax_dump）→ 目标端 2in1 模拟器真跑同一操作序列 + 重启重放 → 机器 A/B 出 MATCH；再故意改坏目标端一处（漏落盘）应出 DIFF 并经 1 轮修复转 MATCH——验证差分与回环真实可判分。
- **ENV_NO_MAC**：同一契约走替代策略：源侧出示 `file:line`（UserDefaults 写点）证明契约出处真实 → 目标端真实执行 + 采集断言 + 重启重放 → 对账行标 `CONTRACT_CONFIRMED`。全程源侧零运行、目标侧全真实、每条证据可复核，即为合规。

## 参考

- 源端取证命令细节（ax_dump/驱动/探针，含 2026-09-01 实测留痕）：`skills/_shared/inventory-macos.md` §5
- verify-core 四维口径与回环上限出处：`skills/_shared/verify-core.md`
- Swift→ArkTS 官方对照： https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-for-other-languages
- Apple AX 驱动依据： https://developer.apple.com/documentation/applicationservices/axuielement ；XCUITest https://developer.apple.com/documentation/xctest/xcuiapplication
- 鸿蒙 PC 形态验收口径： https://developer.huawei.com/consumer/cn/multidevice/pc/adapt （键鼠四项/自由窗口）
