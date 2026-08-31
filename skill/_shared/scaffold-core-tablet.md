---
name: scaffold-core-tablet
description: 鸿蒙平板目标端承载的通用内核（断点体系/一多布局/折叠态/分栏/并排规约，及与 scaffold-core-phone 的分叉点）。tablet-to-harmony-tablet 路径的 scaffold.md 薄壳必须引用本文件；其他涉及大屏（折叠屏/2in1）的路径可复用。依据华为官方文档撰写，不含业务逻辑。
---

# 鸿蒙平板承载内核（断点 / 一多 / 折叠 / 分栏 / 并排）

**定位**：平板不是"放大的手机"。Phase 3 在平板目标端搭壳时，每个承载面除了路由/模态归属，还必须冻结**形态契约**——在哪些断点下以什么布局形态出现（单栏/分栏/并排/栅格几列）。形态是 UI 自由项，但"哪个断点显示什么信息结构"必须可判定、可断言，否则 Phase 4 差分无从下手。本内核在 `_shared/scaffold-core-phone.md` 之上定义全部平板增量（分叉点清单见文末）。

## Non-negotiable

- 继承四阶段治理：模型不放行 / 机器判定 / 证据不可变 / 显式 GAP。
- 每个页面级 surface 的形态契约（breakpoint_plan）三字段齐全（sm/md/lg 布局形态 + 承载组件），缺任一 Gate 3 FAIL——与手机路径 UI 蓝图四字段非空同一强度。
- List-Detail 语义面在 md/lg 断点必须分栏承载（Navigation 分栏或等价并排），sm 断点单栏；不得整页拉伸手机布局充当平板适配。
- 分栏载体必须处理右侧占位（splitPlaceholder 或默认 pushPath）——分栏右侧空白是官方 FAQ 认定的适配缺陷，不是风格差异。
- 断点差异必须显式声明（GridRow 按断点的 columns、条件渲染），禁止依赖"默认值碰巧正确"。
- 一多适配必须**显式建模**：自适应能力（拉伸/均分等）与响应式布局（断点/栅格）在蓝图可辨识——"用了什么适配手段"是蓝图字段，不是隐式代码风格；审阅者应能不看实现就枚举 surface 的适配策略。
- 若 run 的目标设备集含折叠形态（Foldable 模拟器/真机），折叠与展开两个窗口场景**都要进契约**（同断点体系，折叠态变化即窗口宽度变化）；只在展开态验证的折叠 run 视为断点矩阵不完整。

## 流程（五步）

1. **消费功能地图**：与手机路径相同（feature-map 的 surfaces[] + data-relations）；平板路径额外读 Phase 2 的形态取证（源端在大窗/分屏下的布局行为，见各路径薄壳）。
2. **分面搭壳并写形态契约**：每个 surface 在 surface-plan 增加 `breakpoint_plan` 字段——
   - `sm`（[320,600)vp）：布局形态（单栏 / 折叠面板）+ 承载组件（Navigation Stack / Tabs / List）
   - `md`（[600,840)vp，平板竖屏典型）：单栏或分栏 + 承载组件
   - `lg`（[840,1440)vp，平板横屏典型）：分栏/并排 + 承载组件（Navigation Split / SideBarContainer / GridRow 栅格）
   - List-Detail 面：`carrier = Navigation(mode: NavigationMode.Auto 或 Split) + NavDestination`；宽度 ≥600vp 自动分栏（Auto 模式，API 10+）
   - 侧栏/过滤/导航类面：lg 常驻（SideBarContainer 并排式），sm 收起（Embed 抽屉或 Tab 收纳）
   - 重复网格面（卡片流/图库）：GridRow/GridCol，按断点显式声明列数
3. **立数据接口**：与手机路径相同（interface-only）；拖拽类功能的数据契约必须写明 UDMF 数据类型（unifiedData 封装 + uniformTypeDescriptor 类型标识），源端 Android 的 ClipData MIME 类型映射到 UDMF 类型并登记。
4. **上锁与冻结**：breakpoint_plan 随 surface-plan 进 stage input-lock；环境冻结时记录目标端形态验证手段（模拟器设备类型 + 旋转/窗口能力，见下"环境与工具"）。
5. **Gate 3 附加判定（平板加两条，机器可查）**：
   - ① 形态契约完整：每个 verify_mode=RUNTIME 的页面级 surface 的 breakpoint_plan 三断点字段非空且形态枚举合法
   - ② 分栏占位完备：每个 List-Detail 承载面有 splitPlaceholder 或默认路由推送的显式声明
   - （手机路径原有四条：承载面覆盖 / 数据契约无孤儿 / 冒烟链 / 环境链照常）

## 一多布局体系（自适应 + 响应式，按官方"一次开发多端部署"口径）

平板适配 = **自适应布局**（组件随容器尺寸自动变化）+ **响应式布局**（按断点/媒体查询切换组织结构）两层叠加；蓝图应写明每个 surface 依赖哪几项。

### 自适应布局能力（容器内自动，无需断点判断）

| 能力 | 语义 | 典型 ArkUI 载体 |
|---|---|---|
| 拉伸 | 容器尺寸变化时子元素按比例分配增减空间 | `flexGrow` / `flexShrink`（Flex/Row/Column 弹性能力） |
| 均分 | 子元素均分容器空间 | Flex 弹性子元素等比分配 |
| 占比 | 子元素按容器百分比定尺寸 | 百分比宽高 / `aspectRatio` |
| 缩放 | 子元素尺寸随容器按比例缩放 | 组件尺寸随父容器等比计算 |
| 延伸 | 可滚动容器按空间展示更多内容 | `List` / `Grid` / `Scroll` + `LazyForEach` |
| 隐藏 | 空间不足按优先级隐藏次要元素 | `displayPriority` |
| 折行 | 一行放不下自动折到下一行 | `Flex({ wrap: FlexWrap.Wrap })` |

### 响应式布局能力（跨断点切换结构）

- **断点**：窗口宽度分档（见下节表）；监听手段三选一：GridRow `onBreakpointChange` / `mediaquery.matchMediaSync` / UIContext 窗口断点查询（API 名称以本地 SDK d.ts 为准）。
- **栅格**：GridRow/GridCol 按断点分配列 span 与偏移——断点差异的机械表达首选。
- **场景样式四类**（形态字段的官方枚举来源）：分栏（≥600vp 出侧栏）、重复（列数随断点变化）、挪移（内容移位/换位）、缩进（边距随断点变化）。

## 折叠态承载规约

- **折叠屏不引入新断点体系**：合态窗口宽度典型落入 sm（<600vp），展开态典型落入 md/lg——同一物理设备跨断点，契约按窗口宽度判定而非按设备类型判定。
- **形态回退语义**：Navigation `Auto` 模式在容器宽度回落 <600vp 时自动退回单栏（Stack）——折叠合屏/分屏收窄后的行为断言按"单栏 + 返回仍见列表"书写。
- **折叠状态感知**：display 模块的折叠状态/铰链监听 API 名称与可用性 `PENDING_CONFIRM`（以本地 SDK d.ts 核对为准，不得凭记忆写 API 名）；壳阶段用窗口尺寸事件即可覆盖大多数形态切换，不依赖折叠专属 API。
- **验证载体**：DevEco Studio 本地模拟器 Foldable 设备类型（见环境与工具）；模拟器不支持折叠切换操作时，降级为"合态/展开态两种屏幕配置各建一个模拟器实例"分别取证并显式记录。

## 平板承载规约（按官方文档）

### 断点体系（窗口宽度，非设备）

| 断点 | 取值范围（vp） | 典型形态 |
|---|---|---|
| xs | (0, 320) | 穿戴 |
| sm | [320, 600) | 手机、折叠屏合态（**平板分屏/自由窗可落入**） |
| md | [600, 840) | 折叠屏展开、平板竖屏 |
| lg | [840, 1440) | 平板横屏 |
| xl | [1440, +∞) | 大屏/智慧屏 |

- 断点面向**应用窗口**：设备旋转、分屏、自由窗口调节都会触发断点变化——同一平板横竖屏是两个断点场景，都要进契约。
- 获取方式（任选，均可机器断言）：GridRow `breakpoints` + `onBreakpointChange`；`mediaquery.matchMediaSync`；UIContext 窗口断点查询 API（名称以 ts- 参考文档为准，实现时核对本地 SDK d.ts）。
- GridRow `columns` **默认所有断点统一 12 列**；需要按断点差异化（如 sm 4 列 / md-lg 12 列）必须显式传 GridRowColumnOptions 对象，禁止依赖前端框架式默认值想象。
- 断点取值范围可按 GridRow `breakpoints` 参数自定义（官方栅格指南支持）；本体系契约仍按默认 sm/md/lg 语义书写，自定义断点必须换算回默认档位并登记映射，防止"自造档位"逃逸验收矩阵。

### 分栏（Navigation）

- `NavigationMode`：`Stack`（单栏）/ `Split`（强制分栏）/ `Auto`（自适应：容器宽度 ≥600vp 自动分栏，API 10+；API 9 及之前阈值为 520vp）。平板路径默认 Auto。
- Split 形态：NavBar + NavDestination 左右双栏；**路由跳转只替换右侧内容区**，左侧导航不动——这是 Phase 4 分栏行为断言的锚点。
- 右侧占位：分栏进入时未选任何条目，右侧必须显示占位页（splitPlaceholder 属性或默认 pushPath），否则为承载缺陷。
- 官方交互细节：Navigation 标题栏 menus 竖屏最多 3 个图标、横屏最多 5 个（超出用 Capsule/More 收纳）。

### 并排与响应式样式

- 响应式布局四类样式（官方）：**分栏**（≥600vp 出现侧栏）、**重复**（栅格列数随断点变化）、**挪移**（内容移位/换位）、**缩进**（页面边距变化）。surface-plan 的形态字段应落在这四类 + 组件承载。
- 三分栏形态（列表 + 内容 + 侧栏）官方实践为 Navigation 分栏 + SideBarContainer 组合；SideBarContainer 两种模式：并排式（SideBarPosition，大屏常驻）与 Embed（抽屉覆盖，小屏）。

## 平板特有能力（进数据契约/风险面，不强制搭壳）

- **全景多窗**：鸿蒙平板系统级支持最高三窗口同屏；应用侧主要是多窗恢复行为（窗口态数据保存/恢复）进行为契约。窗口尺寸事件（旋转/折叠/分屏/自由窗调节）下的**状态保持断言**（列表滚动位置、选中项、草稿态）按四类结果差分的 persistence/semantic data 维度验收。
- **拖拽（DragAndDrop）**：ArkUI 通用事件 `onDragStart/onDragMove/onDrop/onDragEnd` + `draggable`/`allowDrop` 属性；跨组件/跨应用拖拽数据用 **UDMF**（unifiedData + uniformTypeDescriptor）封装。源端 Android `ClipData`/`View.startDragAndDrop` 的数据类型必须映射登记。
- **手写笔**：华为 Pen Kit（笔迹/笔刷/批注能力）+ M-Pencil 系列压感（消费级介绍达万级压感）。模拟器上手写笔注入能力 `PENDING_CONFIRM`——无法注入时该功能面降级 GAP + 人工裁决，禁止伪造压感数据。

## 与 scaffold-core-phone 的分叉点（薄壳与审阅者的对照清单）

| 维度 | phone 内核 | 本内核（tablet） |
|---|---|---|
| UI 蓝图字段 | 四字段 | 四字段 + 第五字段 `breakpoint_plan`（三断点形态枚举 + 承载组件） |
| 导航默认 | Navigation Stack 单栏为主 | Navigation `Auto` 分栏为默认（List-Detail 强制分栏） |
| 重复内容承载 | List/Grid | GridRow/GridCol 显式断点列数（覆写默认 12 列） |
| 特性面（多窗/拖拽/笔） | 不涉及 | 不建独立壳，落行为契约 + 数据契约（UDMF 映射） |
| Gate 3 判定 | 四条 | 四条 + 形态契约完整 + 分栏占位完备 |
| 冒烟链 | 单设备类型启动 | 平板模拟器竖屏 + 横屏两次启动冒烟（覆盖 md/lg） |
| 输入假设 | 触控 | 触控 + 键盘快捷键（外设高频）进交互重映射表；笔输入按 PLATFORM_LIMITATION 处理 |

## 环境与工具

- **DevEco Studio 本地模拟器**：设备类型支持 Phone / Foldable / **Tablet** / 2in1（Windows x86 可用）；DevEco Studio 6.0.0 Beta1 起支持**自定义屏幕配置**（创建/修改模拟器屏幕参数），可用于模拟不同平板尺寸；Mac ARM 部分版本设备类型受限时用云端远程模拟器补充。
- **断点验证手段**：平板模拟器旋转（横 md↔竖 lg 场景切换）；2in1/自由窗口形态下调节窗口尺寸触发断点变化（模拟器能力以实测为准，实测不支持时降级为"旋转 + 多设备模板"两种窗口宽度取证，并记 TOOL_GAP）。
- **横竖屏与窗口事件的证据锚**：每轮形态取证记录制造手段（旋转角度/窗口命令/参数）与结果证据（截图 + 断点档位日志或 ui-tree 判定），两端同格式留痕供差分重放。
- hvigor 构建/hdc 安装启动链与手机路径一致（见 android-to-harmony-phone 路径）；可执行文件路径双平台对照总表见 `skills/_shared/00-CONVENTIONS.md`。

## 参考（调研来源，2026-08 访问）

- 华为官方：响应式布局（断点定义/栅格/四类响应式样式）https://developer.huawei.com/consumer/cn/doc/best-practices/bpta-multi-device-responsive-layout
- 华为官方：一多能力开发入口（应用开发大纲：自适应/响应式布局体系）https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/application-model-development-outline （标题以文档中心检索"应用开发大纲/一多"为准）
- 华为官方：组件导航 Navigation（Stack/Split/Auto、600vp 阈值、分栏行为）https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-navigation-navigation
- 华为官方 FAQ：Navigation 分栏模式右侧空白（splitPlaceholder）https://developer.huawei.com/consumer/cn/forum/ （UI 框架常见问题）
- 华为官方：平板应用开发最佳实践（全景多窗最高三窗口同屏）https://developer.huawei.com/consumer/cn/doc/best-practices/bpta-pad-guide
- 华为官方：栅格布局开发指导（columns 默认 12、GridRowColumnOptions、断点自定义）https://developer.huawei.com/consumer/cn/doc/harmonyos-guides-V13/arkts-layout-development-grid-layout-V13
- 华为官方：拖拽事件（onDragStart/onDrop、draggable/allowDrop）https://developer.huawei.com/consumer/cn/doc/harmonyos-references-v5/ts-universal-events-drag-drop-V5 ；拖拽控制属性 https://developer.huawei.com/consumer/cn/doc/harmonyos-references/ts-universal-attributes-drag-drop
- 华为官方：模拟器（设备类型/自定义屏幕配置）https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/ide-run-emulator 、https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/ide-emulator-customize-screen-configuration
- 华为 Pen Kit 能力综述（第三方）：https://www.cnblogs.com/yiyiyiyiu898/p/19410045 ；M-Pencil Pro 官方支持说明 https://consumer.huawei.com/cn/support/content/zh-cn16080039/
- 生态对照（源端参考系）：Android 大屏/平板适配指南 https://developer.android.com/develop/ui/views/layout/large-screens ；平板应用质量标准 https://developer.android.com/docs/quality-guidelines/tablet-app-quality
