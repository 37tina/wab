---
name: windows-to-harmony-pc-controller
description: Windows 桌面应用（WinForms/WPF/Win32/Electron）迁移到鸿蒙 PC（2in1）的四阶段治理入口薄壳。任何以 Windows 桌面程序为源的迁移 run 从这里开始；本文件不写目标端代码，四阶段状态机/等价契约/防伪口径全部继承 controller-core。
---

# Windows → 鸿蒙 PC 迁移控制器（薄壳）

## 引用

- [../_shared/controller-core.md](../_shared/controller-core.md)——四阶段状态机、核心等价契约、失败路由、防伪口径全部继承；本文件只补 Windows→PC 的差异参数与裁决项。

## 本路径差异

1. **Gate 1 特有冻结项**（在通用冻结清单之上追加）：
   - 源程序形态：进程与模块清单（exe/dll，.NET / native / Electron 判定）、安装形态（绿色目录 / MSI / 其他安装器）、是否可得源码或只有二进制；
   - 窗口拓扑基线：顶层窗口清单（类名+标题+模态关系），供 Phase 3 承载仲裁；
   - 持久化基线：注册表键范围（HKCU/HKLM）、AppData 目录（Roaming/Local/LocalLow）、INI/程序目录旁文件；涉及 HKLM 写入、驱动、COM/ActiveX、全局热键、托盘、自启动的功能必须逐项裁决（等价替换 / APPROVED_DEVIATION / excluded），禁止默认"鸿蒙侧总有办法"；
   - 双端环境：Windows 源机（OS 版本 + UIA/取证工具链版本）+ 鸿蒙目标端（2in1 模拟器，DevEco Studio 6.0.0+，或鸿蒙电脑真机）。
   - 源端静态锚点包（有源码时必冻，Gate 2 对账分母的静态半边）：WPF XAML 布局文件清单 / WinForms `*.Designer.cs` / `.csproj`（TargetFramework、PackageReference、COM 引用）/ 打包清单（MSIX AppxManifest，或 MSI 内元数据）/ 源码内注册表读写调用点清单（`Microsoft.Win32.Registry` 系）。
2. **Gate 3/4 复核环境必须是 2in1 模拟器或鸿蒙电脑真机**；手机/平板模拟器证据对本路径无效（自由窗口与键鼠范式不同）。
3. **源端取证可用性分级**（Gate 1 对每个高风险功能圈定，作为 Phase 2 取证与 Phase 4 重放的通道裁决输入）：**A** = UIA 全可自动化（标准 Win32/WPF/WinForms 控件，FlaUI 脚本可驱动）；**B** = GDI/DirectX 自绘区域（UIA 不可见 → 图像断言域 + GAP）；**C** = Electron（`--remote-debugging-port` 走 CDP）；**D** = UAC/提权/驱动安装类干扰（人工辅助步骤留痕或 TOOL_GAP）。分级只切换取证通道，**不降低断言强度**。
4. **失败路由补充**：源端取证受 UAC/管理员权限阻碍 → 记 TOOL_GAP 并要求人工提供提权环境重取；不许跳过取证降级为源码猜测。
5. 无对等物清单（裁决参照）：注册表自启、全局热键、系统托盘、COM 组件、设备驱动、其他进程间通信（命名管道/窗口消息）——迁移时必须 APPROVED_DEVIATION 或 excluded 并在冻结清单留痕，不允许静默丢失。

## 最小验证设想

选开源 WinForms 小工具（如 lessmsi，GitHub activescott/lessmsi）走通四阶段：冻结（窗口拓扑+持久化基线+静态锚点包）→ UIA 取证 → 2in1 模拟器壳冒烟 → 双端差分；全程只依赖真实工具链（FlaUI / ProcMon / hdc）。

## 环境与工具（双平台）

- 源端取证机**必须是 Windows**：FlaUI / UIA / FlaUInspect / Inspect.exe / ProcMon 均仅 Windows 运行，macOS 无法驱动 UIA；若操作机为 macOS，源端取证经远程 Windows 机执行并将机器指纹（主机名/OS 版本/工具版本）记入 HENV。Electron 的 CDP 通道两平台皆可（Node + Chromium 系内核）。
- 目标端（鸿蒙 PC）工具链路径两式并列，总表见 `_shared/00-CONVENTIONS.md`：
  - Windows：`D:\DevEco Studio\tools\hvigor\bin\hvigorw.bat`、`D:\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe`
  - macOS：`/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw`、`/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc`
- 复核设备：2in1 模拟器（DevEco Studio 6.0.0+）或鸿蒙电脑真机；手机/平板模拟器证据对本路径无效。

## 参考（真实 URL，调研 2026-09-01）

- Microsoft UI Automation 文档区入口 — https://learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32 ；WPF 文档区 — https://learn.microsoft.com/en-us/dotnet/desktop/wpf/ ；WinForms 文档区 — https://learn.microsoft.com/en-us/dotnet/desktop/winforms/
- WinAppDriver 仓库（已归档，选用须记降级风险）— https://github.com/microsoft/WinAppDriver ；Appium Windows Driver — https://github.com/appium/appium-windows-driver
- MSIX 打包文档区（AppxManifest 冻结口径）— https://learn.microsoft.com/en-us/windows/msix/
- 鸿蒙电脑应用适配开发指南（自由窗口/键鼠/多窗专题入口）— https://developer.huawei.com/consumer/cn/multidevice/pc/adapt
