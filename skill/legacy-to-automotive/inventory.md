---
name: legacy-to-automotive-inventory
description: 传统桌面/嵌入式软件的源端理解薄壳：按 Qt/Win32/Delphi/Electron 分别给出 surface 枚举工具、运行取证工具与特有风险面（注册表/ini 配置/驱动硬件依赖），声明无源码二进制的边界与契约反推规则。Phase 2 源端理解时使用；目标端承载见同目录 scaffold.md，勿在 Phase 3/4 单独使用。
---

# legacy-to-automotive · inventory 薄壳

## 引用

- `skills/_shared/inventory-core.md`（九步流程/六要素/对账四态/防伪口径，全部继承）
- `skills/legacy-to-automotive/controller.md`（源端三态冻结与降级策略）

## 本路径差异：平台差异参数（inventory-core 表格逐项落地）

**1) surface 枚举工具（静态扫描，按源端技术分派）**

| 源端 | 枚举方式（真实可得） |
|---|---|
| Qt Widgets | 解析 `.ui` XML（widget 树 + `<connections>` 节内的 Designer 级信号槽连接）；`uic` 生成代码与 `setupUi()` 为准；代码内 `connect()` 语句 grep/Clang 语法树扫描（clazy 是 Clang 插件，可做 old-style-connect 等检查）；`.qrc`/翻译文件补资源面 |
| Qt Quick/QML | 递归扫描 `.qml`（Loader/StackView 动态面单独标注） |
| Win32/MFC（C/C++） | 解析 `.rc` 资源脚本：`DIALOG`/`MENU`/`STRINGTABLE`/`ACCELERATORS`/`ICON` + `resource.h` 控件 ID；代码端扫 `CreateWindow`/`DialogBox`/消息映射宏 |
| Delphi/VCL/FMX | 解析 `.dfm`/`.fmx` 文本窗体（对象名/属性/事件绑定）；旧二进制 dfm 用 `convert` 工具转文本 |
| Electron | 同 Web：DOM/路由扫描 + `main`/`preload` 进程边界标注 |
| 纯代码构建 UI 的 C/C++ | 受控 grep + 编译期 Clang AST（不做全量反编译） |

**2) 运行取证工具（真实性，按可得性如实记录）**

- **Qt**：GammaRay（KDAB 开源，attach 运行中进程取 QObject 树/属性/信号槽连接，**首选**，Windows/Linux 可用）；Squish（Qt Group 商业，原生对象识别 Qt Widgets/QML，有免费试用——如实记录"商业授权可得性"）；QML 项目可用开源 Spix。Qt 在 Windows 上经 QAccessible 暴露给 UIA，Inspect.exe 可见性有限（自定义控件覆盖不全，如实记录）。全部不可得时降级：脚本化键鼠（pywinauto/xdotool）+ 截图 + 状态文件对拍。
- **Win32/MFC/Delphi**：pywinauto（`win32`/`uia` 双后端，开源）或 FlaUI（.NET，UIA/MSAA 封装，开源）；Inspect.exe（Windows SDK）/Accessibility Insights 做树检视；WinAppDriver 已停止积极维护，不作为依赖项。自绘控件 UIA 覆盖不全 → 坐标+截图兜底并标注置信度。
- **Electron**：`--remote-debugging-port=9222` + CDP（DevTools Protocol）或 Playwright `_electron`，与 web 路径同口径。
- 取证规范沿用 inventory-core：绑定前台进程、前后状态各一份、断言判定、截图先目检。

**3) source_refs 粒度**：Qt = `.ui` objectName 路径或 `file:line`（connect 语句）；Win32 = `.rc` 资源 ID + `file:line`；Delphi = `.dfm` 对象名路径；Electron = CSS/XPath 选择器；二进制样本 = PE 资源名 + 偏移（仅取证定位用）。

**4) 特有风险面（本路径易迁错维度）**

- **配置持久化三形态**：注册表（HKCU/HKLM，`reg export` 前后对拍）、ini/QSettings（注意 QSettings 在 Windows 默认写注册表、Linux 写 ini 的双后端差异）、`%APPDATA%`/散落文件。重启后状态断言必须覆盖真实后端。
- **驱动与硬件依赖**：串口/并口/USB 定制设备/加密狗/工控板卡——车机无对应硬件，Gate 1 裁决（替换/降级/排除），inventory 侧只负责把依赖面扫全（import 表、CreateFile 设备名、SetupAPI 调用）。
- **桌面拓扑假设**：MDI 多窗口、多显示器、全局热键、托盘图标、模态向导、右键菜单、快捷键体系——车机单焦点/分栏/触控模型下全部要重设计（scaffold 薄壳裁决）。
- **GDI/分辨率/字体假设**：写死像素坐标、系统字体探测。
- **管理员权限/UAC、开机自启、日志写 Program Files** 等安装态行为。

**5) 无源码仅有二进制的边界（声明，不许越界）**

- 仅对**自有软件、获书面授权软件、开源许可证允许的样本**做分析；禁止对第三方商业软件反编译/脱壳/绕过保护（法律风险）。
- 合法样本允许：PE 资源枚举（wrestool/icoutils、Resource Hacker 提取对话框/菜单/字符串表）、strings、受授权下的 Ghidra 静态分析；以及黑盒运行取证（UIA 可见部分 + 截图 + 配置对拍）。
- 诚实结论：二进制分析**不能**产出可信的完整行为契约；只能缩小 GAP 面。大面积未知 → 按 controller 薄壳"仅二进制"行处置。

**6) 契约反推规则（黑盒取证 → 行为契约的受控升级）**

- **反推四步**（每步产物入证据链）：①从可枚举入口（菜单/对话框 PE 资源 + 黑盒遍历截图）建 surface 候选清单；②对每个候选 surface 执行系统化操作序列（正常值/边界值/非法值三组输入），采集前后状态差（截图 + 配置文件/注册表对拍）；③从状态差归纳语义对象与结果断言（只登记输入→可见结果/持久化变化/副作用，不推内部算法）；④打 confidence 标（HIGH/MEDIUM/LOW 判定见 controller.md）并带 `CONTRACT_INFERRED` 痕。
- **反推契约的天花板**：无法触达的功能（快捷键未文档化/深层菜单未遍历/硬件依赖触发）一律 GAP（原因 `BLACKBOX_UNREACHABLE`），不许以"应该有"补全；副作用中不可观察项（如网络协议细节）标 MANUAL 进人工清单。
- **与源码态的混用**：部分源码 run 里，缺失模块可借同版本二进制做反推补面，但补出的条目同样带 confidence + CONTRACT_INFERRED，不算源码锚。

## 最小验证设想

开源 Qt 计算器（带 .ui）：`.ui` XML + connect 扫描产出 surface-index 与 feature-map；GammaRay（或降级 pywinauto）跑"连续运算→关进程重启→历史仍在"取证，对拍 ini/注册表后端；产出行车态不可用的功能清单（如键盘长输入）供车机端重设计。二进制反推链：对其 release 构建做黑盒操作序列取证 → 反推"按键→显示→历史"契约并打 confidence 标——验证反推四步与天花板规则可执行。

## 参考（调研来源，2026-09 访问）

- 源端取证工具：GammaRay（KDAB）https://github.com/KDAB/GammaRay ；pywinauto https://github.com/pywinauto/pywinauto ；Spix（QML 自动化）https://github.com/faaxm/spix ；FlaUI https://github.com/FlaUI/FlaUI ；Squish（商业）https://www.qt.io/product/squish
- Qt 官方示例（最小验证源）：widgets 计算器 https://github.com/qt/qtbase/tree/dev/examples/widgets/widgets/calculator ；Qt Examples 文档区 https://doc.qt.io/qt-6/examples-widgets.html
- 反编译边界参照：Ghidra（仅受授权样本）https://ghidra-sre.org/ ；icoutils/wrestool（PE 资源提取）https://www.nongnu.org/icoutils/
- 华为目标端口径：`skills/_shared/scaffold-core-automotive.md`（安全四断言/组件规约/降级策略）及其参考节
