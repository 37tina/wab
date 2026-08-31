---
name: windows-to-harmony-pc-implementation
description: Windows→鸿蒙 PC 的 Phase 4 实现与双端差分薄壳：源端按行为契约用 UIA（FlaUI/CDP）在真实 Windows 进程重放取 oracle，鸿蒙 PC 侧在 2in1 模拟器用 hdc+uitest 验证窗口/键鼠/持久化断言，DIFF 只修目标端。
---

# Windows → 鸿蒙 PC 实现与双端差分（薄壳）

## 引用

- [../_shared/controller-core.md](../_shared/controller-core.md)——Phase 4 判据（断言全过/数据对账无未解释差异/视觉达标）、失败路由（≤2 轮自动修复转 MANUAL_TAKEOVER）、防伪口径全部继承。
- [../_shared/scaffold-core-pc.md](../_shared/scaffold-core-pc.md)——PC 承载规约（窗口语义/键鼠断言维度/最小尺寸锚点），Phase 4 断言从中派生。

## 本路径差异（双端差分两端怎么跑）

1. **源端 oracle 重放（Windows 侧，源端为唯一 oracle）**：
   - 每条 RUNTIME 行为契约在真实 Windows 进程重放：FlaUI 脚本按 AutomationId 定位、读 Text/Value/ToggleState 断言；Electron 程序用 Playwright `connectOverCDP('http://localhost:<port>')` 同序操作（启动参数 `--remote-debugging-port`）；
   - 重放绑定 PID + 前台窗口句柄；断言 = 控件属性 + 持久化状态（注册表值/AppData 文件内容），截图仅目检；
   - 副作用对账用 ProcMon：操作前后各采一遍，diff 出键值/文件变化作为"数据变化"要素的机器证据。
2. **鸿蒙 PC 侧验证（目标端）**：
   - 设备：2in1 模拟器或鸿蒙电脑真机（hdc 工具链）；断言绑定前台 bundleName + 窗口状态；
   - UI 驱动与控件断言：`@ohos.uitest`（ArkTS E2E 组件断言，hypium 运行，见 OpenHarmony testfwk_arkxtest）或 `hdc shell uitest`（dumpLayout 导出控件树 + 输入注入；具体子命令以工程 SDK 实测为准，未核实的命令族标 PENDING_CONFIRM）；
   - **PC 特有断言维度**（从 scaffold-core-pc 派生，逐条判定）：最小/最大窗口尺寸下布局可用；窗口关闭/最小化后状态语义正确（≠ 数据丢失）；右键菜单条目与源端 ContextMenuStrip 语义一致；快捷键逐条；拖放链路；重启（重进应用）后持久化数据仍在。
3. **差分与修复回环**：DIFF 只修鸿蒙侧并重放（≤2 轮转人工）；**桌面范式差异引发的断言不等价**（如源端多窗口 vs 目标端应用内路由、源端托盘 vs 目标端无托盘）必须回 Gate 1 裁决（APPROVED_DEVIATION 留痕），不许 Phase 4 私自改判或删断言。
4. **可搬现成方案**（来源见下）：TestMig（ISSTA 2019，iOS→Android 测试迁移的语义匹配映射）的"操作语义对齐而非坐标对齐"思路用于差分重放；GUITAR/MobiGUITAR 的 GUI ripping 对应本路径 UIA 控件树扫描；Google LLM 大规模迁移（arXiv 2504.09691）与 Zalando UI 组件库 LLM 迁移的"分片+人工复核"节奏对应本四阶段门禁。
5. **取证分级的 Phase 4 落地**（分级定义见 controller.md/inventory.md）：A/C 级契约照既有通道机器重放；B 级（自绘）用冻结坐标的图像断言域比对（源端截图区域 ↔ 目标端 `hdc shell snapshot_display` 截图同区域），比对区域与阈值随工单冻结；D 级（提权/UAC）人工辅助步骤逐条写入脚本注释，录屏文件哈希入证据链；无法稳定人工复现 → TOOL_GAP，不许删断言。
6. **环境路径双平台**：源端取证机为 Windows（FlaUI/ProcMon/Playwright connectOverCDP 均在 Windows 跑；Electron 的 CDP 通道 macOS 亦可）；目标端 hvigorw/hdc 路径两式并列（Windows：`D:\DevEco Studio\tools\hvigor\bin\hvigorw.bat`、`D:\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe`；macOS：`/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw`、`/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc`），命令参数两端一致，差异只在路径与 shell 转义（总表见 `_shared/00-CONVENTIONS.md`）。
7. **差分证据留档**：源端 FlaUI 脚本 + ProcMon CSV/PML、目标端 uitest dump 与 `snapshot_display` 截图，统一存 `<run-id>/evidence/{source,target}/`（双式路径同 `_shared/00-CONVENTIONS.md`），文件哈希入工单，DIFF 判定必须可引用到具体证据文件。

## 参考（本薄壳直接依赖的工具与方案）

- FlaUI — https://github.com/FlaUI/FlaUI ；Playwright Electron（CDP）— https://electronjs.org/docs/latest/tutorial/debugging-main-process
- Process Monitor（Sysinternals 官方）— https://learn.microsoft.com/en-us/sysinternals/downloads/procmon
- @ohos.uitest API — https://developer.huawei.com/consumer/cn/doc/harmonyos-references/js-apis-uitest ；hypium/arkxtest — https://gitee.com/openharmony/testfwk_arkxtest
- Microsoft UI Automation 文档区（控件属性/模式的权威口径）— https://learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32 ；Appium Windows Driver — https://github.com/appium/appium-windows-driver
- microsoft/WPF-Samples（微软官方 WPF 示例库，双端差分练习素材）— https://github.com/microsoft/WPF-Samples ；WPF/WinForms 桌面文档区（源端控件语义核对）— https://learn.microsoft.com/en-us/dotnet/desktop/wpf/ 、https://learn.microsoft.com/en-us/dotnet/desktop/winforms/
- TestMig（ISSTA 2019，GUI 测试迁移）；GUITAR（GUI ripping 模型驱动测试）；Migrating Code At Scale With LLMs At Google — https://arxiv.org/html/2504.09691v1 ；Zalando UI 组件库 LLM 迁移 — https://engineering.zalando.com/posts/2025/02/llm-migration-ui-component-libraries.html

## 最小验证设想

lessmsi"提取 MSI 内容"契约双端重放：Windows 侧 FlaUI（选 msi→提取→断言输出目录出现文件）；鸿蒙侧 2in1 模拟器 uitest 同序操作，断言应用沙箱目录出现文件 + 重启后最近文件仍在 + 最小窗口尺寸下列表不塌。第二例（WPF 源）：microsoft/WPF-Samples 中带菜单/对话框的示例页按同一差分口径跑通"快捷键 + 模态框关闭后状态"断言。
