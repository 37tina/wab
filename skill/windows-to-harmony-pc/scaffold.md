---
name: windows-to-harmony-pc-scaffold
description: Windows 桌面程序迁移到鸿蒙 PC 的 Phase 3 承载薄壳：窗口拓扑到鸿蒙承载的映射、键鼠交互映射、最小窗口尺寸锚点。只搭壳立数据接口，不写业务逻辑。
---

# Windows → 鸿蒙 PC 承载（薄壳）

## 引用

- [../_shared/scaffold-core-pc.md](../_shared/scaffold-core-pc.md)——PC 承载内核（承载仲裁规则、module.json5 窗口规约、键鼠规约、最小尺寸锚点、Gate 3 四条）全部继承；本文件只补 Windows 源端的映射差异。
- [../_shared/controller-core.md](../_shared/controller-core.md)——Phase 3 边界与铁律（壳 contract-only、数据契约 interface-only）。

## 本路径差异

1. **窗口拓扑映射表**（源 → 鸿蒙承载，逐项写入 `window-topology.json`，判不定的记 PENDING_CONFIRM）：
   - WinForms `Form` / WPF `Window`（独立顶层、独立任务栏项）→ 应用主窗口或 `createWindow` 子窗口；
   - `ShowDialog` 模态框 / WPF 模态 Window → 宿主页 `CustomDialog`/`bindSheet` 挂载；非模态浮动工具窗 → 子窗口/悬浮窗（`module.json5` 声明 supportWindowMode floating）；
   - MDI 子窗体 / `TabControl` / 页内切换 → 应用内 `Navigation`+`NavPathStack`（不建窗口）；
   - `MenuStrip`/`ToolStrip`/Ribbon → `Navigation`+`Tabs` 组合；`ContextMenuStrip`（右键菜单）→ `bindContextMenu`；
   - 通知气泡/托盘菜单 → 无直接对等物：Gate 1 裁决（APPROVED_DEVIATION 或 excluded），Phase 3 不私设载体。
2. **键鼠映射**（每条进 UI 蓝图与行为契约，未映射项记 GAP）：
   - 快捷键表（Ctrl+O/F5 等）→ ArkTS KeyEvent 逐条映射；右键菜单 → `bindContextMenu`；悬停提示 → `onHover`/`hoverEffect` + tooltip；双击（如列表项双击打开）→ `TapGesture`(count=2)；文件拖入拖出 → onDrag 接口族；滚轮 → Scroll/List 滚动。
3. **窗口尺寸锚点来自源端实测**：源窗口默认/最小尺寸（UIA 取证的窗口矩形）换算为 `minWindowWidth/minWindowHeight`（vp）初值，最小状态布局不塌为验收断言。
4. **数据契约必须收录注册表/AppData/INI 读写集为语义数据对象**（interface-only；鸿蒙侧物理载体 Preferences/RelationalStore/文件由 Phase 4 决定），来源为 Phase 2 持久化基线。
5. **.NET→ArkTS 数据契约类型映射要点**（interface-only 建模逐字段过表；精度/语义损失显式记 GAP，不许静默丢精度）：

   | .NET | ArkTS | 注记 |
   |---|---|---|
   | `int`/`short`/`byte` | `number` | 直对（ArkTS number 为双精度浮点） |
   | `long` | `number` 或 `string` | 超 2^53 精度损失 → 契约改 `string` + GAP |
   | `double`/`float` | `number` | IEEE 754 double 直对 |
   | `decimal` | `string`（推荐）或 `number` | decimal 128 位精度无对等；金额/精度敏感场景必须 `string` + GAP |
   | `bool` / `string` / `char` | `boolean` / `string` / `string` | 直对；`char` 语义（单字符）写进契约注释 |
   | `DateTime` / `DateTimeOffset` | `number`（epoch ms）或 `Date` | 时区语义必须显式（建议统一 UTC 基准） |
   | `TimeSpan` | `number`（ms） | 单位冻结进契约 |
   | `Guid` | `string` | 格式（大小写/连字符）冻结 |
   | `Nullable<T>` / `T?` | `T \| null` | 可空语义靠契约声明 |
   | `List<T>` / `T[]` | `Array<T>` | 直对 |
   | `Dictionary<K,V>` | `Map<K,V>` 或 `Record<string, V>` | 键型限 `string`/`number` |
   | `class` / `struct` / `enum` | `interface` / `class` / `enum` | 数据契约面用 `interface`；enum 数值/字符串双形态注明 |
6. **环境**：冒烟与冻结环境为 2in1 模拟器（DevEco Studio 6.0.0+；6.0.1+ 可自定义屏幕配置）；构建/安装/启动命令链同内核（hvigor + hdc）。

## 最小验证设想

以 lessmsi 的窗口拓扑（主窗体 + 进度对话框 + 错误提示框 + 最近文件菜单）映射为 1 主窗口 + 2 模态壳 + 0 路由 + 1 右键菜单挂载，module.json5 配 min/max 窗口尺寸，2in1 模拟器完成构建-安装-启动冒烟（断言窗口形态启动、最小尺寸不塌）。

## 环境与工具（双平台）

- 冒烟设备：2in1 模拟器（DevEco Studio 6.0.0+，6.0.1+ 可自定义屏幕配置）或鸿蒙电脑真机。
- 构建/安装/启动命令链（参数两端一致）：hvigorw `assembleHap` → `hdc install` → `hdc shell aa start <ability>`；可执行文件路径两式：
  - Windows：`D:\DevEco Studio\tools\hvigor\bin\hvigorw.bat`（或以 `tools\node\node.exe` 调 `hvigorw.js`）、`D:\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe`
  - macOS：`/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw`、`/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc`

## 参考（真实 URL，调研 2026-09-01）

- 鸿蒙电脑应用适配开发指南 — https://developer.huawei.com/consumer/cn/multidevice/pc/adapt ；智慧多窗应用开发指导（`supportWindowMode`/`MultiWindowEntryInAPP`）— https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/multi-window-support
- module.json5 窗口字段（abilities 的 min/max 窗口尺寸）— https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/module-configuration-file ；自由窗口适配（一多白皮书 §5.1）— https://developer.huawei.com/consumer/cn/doc/guidebook/develop-once-deploy-everwhere-5-1-0000002594832922
- microsoft/WPF-Samples（微软官方 WPF 示例库，窗口拓扑映射的练习素材）— https://github.com/microsoft/WPF-Samples
- ArkTS 与 TypeScript 类型差异（类型映射表的语言侧依据）：developer.huawei.com 文档站内"从 TypeScript 到 ArkTS"迁移手册（PENDING_CONFIRM：具体深链 slug，从 https://developer.huawei.com/consumer/cn/doc/ 检索标题）
