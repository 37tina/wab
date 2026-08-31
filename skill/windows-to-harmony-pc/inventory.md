---
name: windows-to-harmony-pc-inventory
description: Windows 桌面程序源端理解薄壳：UIA 控件树扫描枚举 surface、FlaUI/CDP 绑定真实进程取证、ProcMon 采集注册表与 AppData 副作用，产出功能语义地图与行为契约。Phase 2 使用；不写鸿蒙代码。
---

# Windows 源端理解（薄壳）

## 引用

- [../_shared/inventory-core.md](../_shared/inventory-core.md)——九步流程、行为契约六要素、分级验证、对账四态全部继承；本文件填平台差异参数表并补 Windows 特有口径。
- [../_shared/scaffold-core-pc.md](../_shared/scaffold-core-pc.md)——了解产出的窗口拓扑与持久化基线如何被 Phase 3 消费。

## 本路径差异（平台差异参数表）

| 参数 | 本路径取值 |
|---|---|
| surface 枚举工具 | 双通道交叉：①静态——有源码时代码遍历为准（WinForms Form/ UserControl、WPF Window/Page/XAML、Electron 页面路由）；②运行时——**UIA 控件树扫描**：FlaUInspect 或 Inspect.exe（Windows SDK）人工检视 + FlaUI（UIA2/UIA3）脚本化全树导出 `uia-tree.json`（含 AutomationId/ClassName/Name/ControlType/层级）；③Electron 加 `--remote-debugging-port` 走 CDP 导出 DOM。防漏判定：两通道 surface 并集为分母。 |
| 运行取证工具 | **FlaUI**（.NET 开源库，Attach/Launch 真实进程，AutomationId 定位控件，读 Text/Value/ToggleState 断言）为主；Appium windows driver（代理 WinAppDriver）为备选——注意 microsoft/WinAppDriver 仓库已归档、不再积极维护，选用时降级风险记 TOOL_GAP；Electron 用 Playwright `connectOverCDP` 重放。**副作用取证**：Sysinternals Process Monitor（按进程过滤 RegSetValue/RegQueryValue/CreateFile/WriteFile）+ RegShot 类前后快照 diff，锁定注册表键与 AppData 文件。 |
| source_refs 粒度 | 首选 控件 AutomationId / 窗口类名+标题（WinForms 控件 Name / WPF x:Name 通常透出为 AutomationId）；仅有二进制时用 UIA 锚；有源码时叠加 文件:行。 |
| 特有风险面 | 注册表（HKCU/HKLM 语义不同：用户偏好 vs 系统级依赖）、AppData（Roaming/Local/LocalLow）、INI 与程序目录旁文件、COM/ActiveX 依赖、多窗口与模态拓扑、全局热键、系统托盘、自启动项、UAC/管理员权限、安装包 CustomAction（MSI 可用 lessmsi / `msiexec /a` 管理安装 / dark.exe 反编译 WiX XML 查 Registry 表）、GDI/DirectX 自绘区域。 |
| 静态锚点包 | 有源码时冻结：WPF XAML 文件 / WinForms `*.Designer.cs` / `.csproj`（TargetFramework、PackageReference、COM 引用）/ MSIX AppxManifest（或 MSI 元数据）/ 源码注册表调用点清单。与 UIA 运行时树交叉对账：静态有·运行时无 → 死代码或延迟加载，两态都要注明；运行时有·静态无 → 动态生成 UI，source_refs 只能锚 UIA 属性。 |

补充口径（Windows 特有，回答"如何全面理解 + 真实性怎么保证"）：

- **UIA 控件树是本平台的控件树证据**：每条 RUNTIME 行为契约的操作序列必须锚定到 UIA 快照中的具体控件（AutomationId 或 类名+标题），保证 Phase 4 机器可重放；契约里写"点那个按钮"不算数。
- **真实性 = 真实进程前台绑定 + 属性断言**：取证脚本绑定目标进程 PID 与 MainWindowHandle；断言读取控件属性值（Text/Value/选中态）与持久化状态（注册表值/文件内容），截图只做目检辅助；无真实执行痕迹的结论降级 SOURCE_CONFIRM + GAP。
- **自绘区域降级规则**：GDI/DirectX 自绘内容 UIA 不可见 → 显式登记为图像断言域 + GAP 备注，禁止把整块区域伪造成控件。
- **持久化结论必须定位到机制**：每个数据对象给出"存在哪"（注册表键路径 / AppData 文件路径 / INI 段），ProcMon CSV/导出为证；只写"有本地存储"不合规。
- .NET 二进制无源码：ILSpy 反编译辅助源码确认（只读分析，不修改程序）。
- **取证可用性分级**（每条行为契约标注，与 controller.md 的 Gate 1 分级一致）：**A** = UIA 全可自动化（标准控件，FlaUI 脚本采集/重放，证据链全机器）；**B** = 自绘区域（UIA 不可见 → 图像断言域 + GAP，截图坐标冻结）；**C** = Electron（CDP 通道，DOM/网络证据同 web 路径口径）；**D** = UAC/提权/驱动类干扰（人工辅助步骤 + 录屏留痕；无法稳定复现 → TOOL_GAP）。分级只切换取证通道，断言强度不降级。

## 最小验证设想

lessmsi（WinForms 开源）：UIA 全树导出 → 提炼"提取 MSI 内容/查看 MSI 表"功能契约 → FlaUI 重放（选文件→提取→断言输出目录出现文件）→ ProcMon 取证其注册表与文件读写 → 重启进程验证最近文件列表仍在（持久化锚点）。

## 环境与工具（源端取证，仅 Windows）

- FlaUI：NuGet 引入取证脚本工程（.NET），仓库 README 为准 — https://github.com/FlaUI/FlaUI ；FlaUInspect 控件树检视工具：GitHub Releases 下载 exe — https://github.com/FlaUI/FlaUInspect 。
- Inspect.exe：随 Windows SDK 安装（位于 SDK bin 目录下，路径随 SDK 版本变化，以实际安装为准；文档见参考节）；Accessibility Insights for Windows（GUI 检视）— https://accessibilityinsights.io/ 。
- ProcMon：Sysinternals 官方下载，版本号记入 HENV — https://learn.microsoft.com/en-us/sysinternals/downloads/procmon 。
- 本阶段一般不触碰鸿蒙端；目标端工具链双式路径总表见 `_shared/00-CONVENTIONS.md`。

## 参考（真实 URL，调研 2026-09-01）

- Microsoft UI Automation 文档区入口 — https://learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32 ；Inspect.exe — https://learn.microsoft.com/en-us/windows/win32/winauto/inspect-objects
- FlaUI / FlaUInspect — https://github.com/FlaUI/FlaUI 、https://github.com/FlaUI/FlaUInspect ；Appium Windows Driver — https://github.com/appium/appium-windows-driver ；WinAppDriver（已归档，降级风险）— https://github.com/microsoft/WinAppDriver
- Process Monitor — https://learn.microsoft.com/en-us/sysinternals/downloads/procmon ；ILSpy — https://github.com/icsharpcode/ILSpy ；lessmsi — https://github.com/activescott/lessmsi
- .NET API 浏览器（`Microsoft.Win32.Registry` 等类型核对）— https://learn.microsoft.com/en-us/dotnet/api/
