---
name: scaffold-core-pc
description: 鸿蒙 PC（电脑/2in1 形态）端承载通用内核：自由窗口默认形态、窗口拓扑承载仲裁、自适应布局最小尺寸锚点、键鼠交互规约。所有以鸿蒙 PC 为目标的迁移路径（windows-to-harmony-pc、mac-to-harmony-pc）的 scaffold.md 薄壳必须引用本文件；不写业务逻辑、不替代 phone 内核。
---

# 鸿蒙 PC 端承载内核（scaffold-core-pc）

## 定位

Phase 3 在鸿蒙电脑（PC/2in1 形态）上给功能地图装壳、给数据关系立接口。与 phone 内核最大的差异：**窗口是一等承载单元**——PC 上应用默认以自由窗口打开，多窗口/应用内导航的承载仲裁、键鼠交互（点击/滚动/文本输入/焦点导航 + 右键/悬停/快捷键/拖放）、最小窗口尺寸下的布局可用性，都必须在壳与数据契约层面就位。本文件只写官方公开能力；未公开或未核实的能力一律标 `PENDING_CONFIRM`。

## Non-negotiable

- 继承 controller-core 全部铁律（模型不放行 / 机器判定 / 证据不可变 / GAP 显式）。
- **窗口拓扑显式**：源程序每个顶层窗口必须有承载决策（应用主窗口 / createWindow 子窗口·悬浮窗 / 应用内 Navigation 路由 / 容器不建壳），决策表 `window-topology.json` 是 Gate 3 必交产物；把源端多窗口静默折叠为单窗口路由而未经 Gate 1 裁决 = FAIL。
- **最小窗口尺寸是最坏情况锚点**：布局验证必须覆盖 `minWindowWidth × minWindowHeight`（vp）状态；只在大窗或最大化状态验证通过不算通过。
- **键鼠四项强制**（官方 PC 适配要求）：点击、滚动、文本输入、焦点导航必须可用；右键菜单、悬停、快捷键按行为契约声明按需落地，不虚构源端没有的交互。
- Phase 3 不写业务逻辑：壳 contract-only、确定性、可构建；数据契约 interface-only，物理载体（Preferences/RelationalStore）由 Phase 4 决定。

## 流程（五步，对齐 phone 版 scaffold，PC 差异处加粗）

1. **拿工单开工**：消费 Gate 2 三件套（feature-map / data-relations / surface-index）；**另消费源端窗口拓扑取证**——顶层窗口清单、父子与模态关系、默认尺寸、多显示器行为。
2. **分面搭壳（先承载仲裁）**：
   - 仲裁规则：源端独立顶层窗口（独立任务栏项/独立生命周期/可单独关闭）→ 主窗口或 `createWindow` 子窗口；同一窗口内的视图切换（MDI/标签页/页内导航）→ 应用内 `Navigation`+`NavPathStack`；模态对话框 → 宿主页挂载 `CustomDialog`/`bindSheet`；容器/reusable-component → 不建壳。判不定 → 记 `PENDING_CONFIRM` + 降级应用内路由 + GAP，不许猜。
   - page → 路由节点或窗口壳；sheet/dialog → 模态挂载（宿主三层推断同 phone 版，来源透明记录）。
3. **PC 承载规约（壳层落地，逐条可判定）**：
   - module.json5（abilities 标签）：`supportWindowMode`（fullscreen/split/floating）、`minWindowWidth`/`maxWindowWidth`/`minWindowHeight`/`maxWindowHeight`（单位 vp）；声明非全屏模式时必须同时配置 min/max，否则窗口拖动异常；窗口元数据经 metadata 配置（官方 window-config）。
   - 自由窗口默认形态：PC 设备应用默认在窗口模式下打开（官方白皮书），壳与冒烟禁止硬编码全屏；源端显式全屏语义（如 F11）→ 映射 `window.maximize()` / `window.recover()` 进行为契约。
   - 自适应布局：官方七种自适应能力（拉伸/缩放/折行/隐藏/延伸/均分/占比）+ 栅格断点；最坏锚点 = minWindowWidth。
   - 键鼠规约：右键菜单 → `bindContextMenu`（官方 Menu，标注"鸿蒙电脑开发"场景）；悬停 → `onHover` 事件 + `hoverEffect`（Auto/Scale/Highlight）；鼠标事件 → `onMouse`；源端快捷键表逐条映射（KeyEvent 系），未映射项记 GAP；文件拖放 → onDrag 接口族（源端有拖放的功能必列）。已知限制如实登记（如官方 FAQ：TextInput 暂无自定义 hover 效果接口）。
   - 标题栏沉浸式（仅当源端有自定义标题栏行为才启用）：`isInFreeWindowMode()` / `on('freeWindowModeChange')` / `setWindowDecorVisible()` / `setWindowDecorHeight()`（官方白皮书 API）。
   - 窗口生命周期语义：PC 上窗口进后台/最小化/关闭 ≠ UIAbility 生命周期同步变化（官方白皮书），"重启后状态"契约必须按窗口语义撰写。
   - 多显示器：源端跨屏行为 → `display.getAllDisplays()` / `getWindowProperties().displayId` 判断；单屏验证环境跑不了的跨屏行为记 GAP。
4. **立数据接口**：interface-only 数据契约（同 phone 内核）；**源端桌面特有持久化读写集（注册表/AppData/INI 等）必须登记为语义数据对象**，不得因"鸿蒙没有注册表"而漏登。
5. **上锁冻结 + Gate 3（四条）**：HENV 环境冻结必须记录 2in1 模拟器；构建/安装/启动冒烟在 2in1 模拟器执行，启动断言含"以窗口形态启动且最小尺寸布局不塌"；Gate 3 判定——①功能承载面覆盖（含窗口拓扑条目逐一有载体）②数据契约无孤儿 ③冒烟链（TOOLCHAIN/BUILD/INSTALL/LAUNCH，2in1 设备）④环境链。PASS → CLOSED + `WAITING_HUMAN_REVIEW`。

## 鸿蒙 PC 端形态能力清单（搭壳前逐项对照；未核实项标 PENDING_CONFIRM，不得据此设计）

| 能力 | 鸿蒙 PC 支持 | 载体 / API | 依据 |
|---|---|---|---|
| 自由窗口（默认窗口化、拖动/缩放/最大化/最小化） | 支持 | 系统窗口管理；`window.maximize()` / `window.recover()` | 参考 3（一多白皮书 §5.1） |
| 最小/最大窗口尺寸与宽高比 | 支持 | module.json5 abilities：`minWindowWidth/maxWindowWidth/minWindowHeight/maxWindowHeight`（vp） | 参考 2/3/4 |
| 多窗口模式声明 | 支持 | `supportWindowMode`（fullscreen / split / floating） | 参考 2/4 |
| 应用内创建子窗口 | API 支持 | `@ohos.window` `createWindow`（PENDING_CONFIRM：子窗口在 PC 桌面形态的任务栏/焦点表现细节，以真机实测为准） | 参考 9 |
| 应用内多窗 / 分屏 | 支持（HarmonyOS 6+） | `MultiWindowEntryInAPP`、`preferMultiWindowOrientation` | 参考 2 |
| 鼠标事件与悬停 | 支持 | `onMouse`、`onHover` + `hoverEffect`（Auto/Scale/Highlight）；已知限制：TextInput 暂无自定义 hover 效果接口（官方 FAQ） | 参考 6 |
| 右键菜单 | 支持 | `bindContextMenu`（标注"鸿蒙电脑开发"场景） | 参考 6 |
| 键盘快捷键 | 支持 | 组件 KeyEvent 系事件逐条映射源端快捷键表 | 参考 1（键鼠要求） |
| 焦点导航（Tab 遍历） | 支持 | `focusable`、`focusControl`；PENDING_CONFIRM：自定义 Tab 顺序的接口与默认遍历序细则，以 SDK d.ts 实测为准 | 参考 1（键鼠四项） |
| 鼠标滚轮 | 支持 | Scroll / List / Grid 响应滚轮 | 参考 1（键鼠四项之"滚动"） |
| 拖放 | 支持 | onDrag 接口族（universal） | 参考 1 |
| 鼠标光标样式 | API 支持 | ArkUI 通用属性 cursor（PENDING_CONFIRM：CursorType 枚举全集以 SDK d.ts 为准） | d.ts 实测 |
| 标题栏沉浸（自定义标题栏） | 支持 | `isInFreeWindowMode()` / `on('freeWindowModeChange')` / `setWindowDecorVisible()` / `setWindowDecorHeight()` | 参考 3 |
| 多显示器 | 支持 | `display.getAllDisplays()`、`getWindowProperties().displayId` | 参考 3 |
| 系统剪贴板 | 支持 | `@ohos.pasteboard`（源端 Ctrl+C/V 语义的落点；按键组合本身归 KeyEvent 映射） | 参考 10 |
| 触控板双指滚动/捏合 | 系统层换算 | 归一为滚轮/缩放语义（PENDING_CONFIRM：应用层收到的事件形态以真机实测为准） | 参考 7 |
| 窗口生命周期与 UIAbility 解耦 | 是（PC 语义） | 窗口最小化/关闭不必然触发 UIAbility 销毁——"重启后状态"契约按窗口语义撰写 | 参考 3 |

## 平台差异参数（各路径薄壳可覆盖）

| 参数 | PC 默认值 |
|---|---|
| 目标设备形态 | 2in1（鸿蒙电脑）；模拟器设备类型官方含 2in1 |
| 默认窗口形态 | 自由窗口（窗口化打开），全屏是显式动作 |
| 承载单元 | 双层：窗口（主/子/悬浮）+ 应用内 Navigation 路由 |
| 布局最坏锚点 | minWindowWidth × minWindowHeight（vp） |
| 输入范式 | 键鼠四项强制；右键/悬停/快捷键/拖放按行为契约 |
| 生命周期语义 | 窗口操作与 UIAbility 生命周期解耦（白皮书） |
| 栅格断点 | 宽屏主用 lg（断点体系 sm/md/lg 以官方响应式设计文档数值为准，lg 下限 840vp）；窗口宽度连续可变 → 断点切换行为必须纳入冒烟（拖动改窗口宽度触发 sm↔md↔lg） |
| 输入方式组合 | 键鼠为主（2in1 兼触摸）；断言必含键鼠通道，触屏通道按目标设备能力选测 |
| 控件密度 | PC 信息密度高于手机：间距/命中区可收紧、支持多列与紧凑列表；具体密度数值 PENDING_CONFIRM（以官方设计规范实测为准），不虚构具体 px |
| 复核设备 | 2in1 模拟器（DevEco Studio 6.0.0+）或鸿蒙电脑真机；手机/平板模拟器证据对 PC 路径无效 |

## 与 scaffold-core-phone 的分叉点（冲突时，以鸿蒙 PC 为目标的路径以本文件优先）

**完全继承 phone 内核**：分面搭壳三规则（page / sheet·dialog / container / reusable-component 判定与不建壳原则）、宿主三层推断、UI 蓝图四字段、interface-only 数据契约、真实冒烟链结构（TOOLCHAIN/BUILD/INSTALL/LAUNCH）、Gate 3 四条判定框架。

**PC 分叉（本文件覆盖 phone 内核之处）**：

1. **承载单元**：phone = 单窗口 + 应用内路由；PC = 双层（窗口 + 应用内路由），多一道窗口拓扑仲裁，`window-topology.json` 为 PC 特有必交产物。
2. **布局锚点**：phone = 主流设备视口与折叠态；PC = 自由缩放连续区间，最坏锚点锁定 minWindowWidth × minWindowHeight。
3. **断点假设**：phone 以 sm/md 为主；PC 宽屏以 lg 为主，且断点由窗口拖动触发（非设备形态切换），切换行为入冒烟。
4. **输入范式**：phone = 触摸手势（tap/swipe/长按）；PC = 键鼠四项强制 + 右键/悬停/快捷键/拖放按契约；触摸手势在 PC 仅为 2in1 选测项。
5. **生命周期语义**：phone = 前后台切换驱动 UIAbility；PC = 窗口最小化/关闭与 UIAbility 解耦，"关闭后重开状态恢复"契约两平台语义不同，PC 按窗口语义撰写。
6. **冲突裁决**：两内核都未覆盖、或口径冲突且本文件未显式分叉的点 → 记 PENDING_CONFIRM + GAP 走人工，不许任选一边猜。

## PC 适配自检清单（Gate 3 前逐条过，任一不满足即回修）

1. `window-topology.json` 覆盖源端全部顶层窗口，且每条有承载决策（窗口 / 子窗口·悬浮 / 应用内路由 / 模态挂载 / 不建壳），无"静默折叠"。
2. module.json5 声明了 `supportWindowMode` 与 min/max 窗口尺寸（声明非全屏模式时 min/max 必须同时配置），数值锚定源端窗口实测矩形。
3. 壳与蓝图无硬编码全屏假设；全屏语义仅当源端显式存在时映射为行为契约动作。
4. 键鼠四项（点击/滚动/文本输入/焦点导航）在蓝图层面可判定可用；快捷键表逐条有 KeyEvent 映射或显式 GAP。
5. 最坏锚点 minWindowWidth × minWindowHeight 状态列入验收断言（布局不塌、无不可达交互）。
6. 窗口生命周期语义（最小化/关闭 ≠ 数据丢失）在契约中显式，与 UIAbility 生命周期解耦口径一致。
7. 源端桌面特有持久化读写集（注册表/AppData/INI 等）全部登记为语义数据对象，无孤儿。
8. 冒烟在 2in1 模拟器或鸿蒙电脑真机完成（手机/平板模拟器证据无效），启动断言含"窗口形态启动"。

## 环境与工具（真实可得性，调研于 2026-08-31）

- **2in1 模拟器**：DevEco Studio 6.0.0（API 20 / HarmonyOS 6.0.0）新增支持；6.0.1 新增 2in1 等类型自定义屏幕配置；6.1.0 Release 支持一键启动模拟器运行调试。模拟器可用范围：6.1.0 Beta1 起中国大陆（港澳台除外），6.1.1 Release 起所有国家/地区。低于 6.0.0 的 DevEco 无 2in1 模拟器 → 目标端验证环境 TOOL_GAP。
- 模拟器设备类型（官方文档）：手机、折叠屏、平板、2in1、智慧屏、穿戴。
- **工程模板**：DevEco 新建工程可选设备形态与"一多"模板；**"PC 专用工程模板"未在官方文档核实到（PENDING_CONFIRM）**，PC 适配走"一多能力 + module.json5 窗口配置"路线，不假设专用模板存在。
- 工具链：hvigor（构建）、hdc（安装/启动/截图），路径两式并列（总表见 `_shared/00-CONVENTIONS.md`「环境路径双平台对照」）：
  - Windows：`D:\DevEco Studio\tools\hvigor\bin\hvigorw.bat`（或以 `tools\node\node.exe` 调 `hvigorw.js`）、`D:\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe`
  - macOS：`/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw`、`/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc`

## 参考（真实 URL，调研 2026-08-31）

1. 鸿蒙电脑(PC)与平板应用适配开发指南（自适应布局/自由多窗/键鼠交互专题入口；键鼠验证要求"点击、滚动、文本输入、焦点导航正常，高频编辑工具场景可增加右键、悬停、快捷键"）— https://developer.huawei.com/consumer/cn/multidevice/pc/adapt
2. 智慧多窗应用开发指导（module.json5 声明 `supportWindowMode`/`preferMultiWindowOrientation`；应用内分屏；应用内多窗 `MultiWindowEntryInAPP`，HarmonyOS 6.0.0+）— https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/multi-window-support
3. 自由窗口适配（一次开发多端部署白皮书 §5.1：PC 默认窗口模式、生命周期差异、最小/最大尺寸与宽高比在 module.json5 abilities 配置、标题栏沉浸式 isInFreeWindowMode/setWindowDecorVisible/setWindowDecorHeight、window.maximize/recover、多显示器 display API）— https://developer.huawei.com/consumer/cn/doc/guidebook/develop-once-deploy-everwhere-5-1-0000002594832922
4. module.json5 配置（abilities 窗口字段）— https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/module-configuration-file ；窗口元数据配置 — https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/window-config-m
5. 响应式设计方法（自适应折行等）— https://developer.huawei.com/consumer/cn/doc/guidebook/develop-once-deploy-everwhere-3-2-0000002625192363 ；自适应布局 Codelab（七种自适应能力）— https://developer.huawei.com/consumer/cn/codelabsPortal/carddetails/tutorials_NEXT-MultiAdaptiveLayout
6. Menu 菜单控制（`bindContextMenu` 右键/长按，标注鸿蒙电脑开发场景）— https://developer.huawei.com/consumer/cn/doc/doccenter-capabilities/arkts-popup-and-menu-components-menu ；悬浮事件 onHover — https://developer.huawei.com/consumer/cn/doc/harmonyos-references-v5/ts-universal-events-hover-V5
7. 人机交互设计指南·交互事件归一（鼠标右键 ≈ 触控板双指轻点 ≈ Shift+F10）— https://developer.huawei.com/consumer/cn/doc/design-guides/hmi-interaction-events-0000001795531217
8. DevEco Studio 版本说明（2in1 模拟器能力线）：6.0.0 — https://developer.huawei.com/consumer/cn/doc/harmonyos-releases/deveco-studio-new-features-600 ；6.0.1 — https://developer.huawei.com/consumer/cn/doc/harmonyos-releases/deveco-studio-new-features-601 ；6.1.0 — https://developer.huawei.com/consumer/cn/doc/harmonyos-releases/deveco-studio-new-features-610 ；模拟器设备类型 — https://developer.harmonyos.cool/docs/tools/coding-debug/ide-emulator-devicetype
9. @ohos.window（`createWindow` 子窗口、`maximize`/`recover` 等窗口 API）— https://developer.huawei.com/consumer/cn/doc/harmonyos-references/js-apis-window ；@ohos.display（`getAllDisplays` 多显示器）— https://developer.huawei.com/consumer/cn/doc/harmonyos-references/js-apis-display
10. @ohos.pasteboard（系统剪贴板）— https://developer.huawei.com/consumer/cn/doc/harmonyos-references/js-apis-pasteboard

补充环境口径：工作区路径两式（Windows `D:\migrate-runs\<run-id>\`，Git Bash 传设备路径加 `MSYS_NO_PATHCONV=1`；macOS `~/migrate-runs/<run-id>/`）；模拟器 CLI 形态与镜像根目录随 DevEco 版本差异较大，以 `deveco-preflight` 实测为准（总表见 `_shared/00-CONVENTIONS.md`）。
