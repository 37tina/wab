---
name: web-to-harmony-scaffold
description: Web → 鸿蒙手机 Phase 3 搭壳薄壳（引用 scaffold-core-phone 通用内核 + ArkWeb 与 ArkUI 原生重写的承载裁决规则：何时 Web 壳承载、何时必须原生重写，裁决必须记录理由）。何时用：消费 Phase 2 功能地图搭鸿蒙手机壳；何时不适用：Phase 2 未闭包，或要在本阶段写业务逻辑。
---

# Web → 鸿蒙手机 目标承载搭壳（薄壳）

## 引用

- `skills/_shared/scaffold-core-phone.md` —— 手机端搭壳通用内核（分面搭壳三规则 / 原生优先规约 / UI 蓝图四字段 / interface-only 数据契约 / 真实冒烟链），**全部继承**。
- `skills/_shared/controller-core.md` —— Gate 3 判定口径与等价契约。

## 本路径差异：ArkWeb 壳 vs ArkUI 原生重写的承载裁决

Web 迁移独有的一道裁决：每个页面级 surface 在**Web 壳（`Web({ src, controller })` ArkWeb 组件）**与 **ArkUI 原生重写**之间二选一。裁决写进 surface-plan 每个 surface 的 `carrier_decision`（值 ∈ `web | arkui | hybrid` + 一行 rationale），**不记录理由视为 Gate 3 FAIL**。默认口径：

### 可用 Web 壳承载（carrier = web）

- **内容型页面**：以浏览展示为主（文章/帮助/协议/活动页），交互 = 滚动 + 跳转。
- **复用成本高**：重 Web 特性依赖（复杂 canvas/WebGL 可视化、富文本编辑器、遗留组件库），ArkUI 重写成本或回归风险显著高于桥接成本。
- **交互标准**：表单/按钮等标准交互，ArkWeb 默认手势与滚动即可承载，无精细手势要求。
- **同源持续迭代**：页面由 Web 团队持续更新，双端一致性靠同一 Web 资产冻结指纹维护。

### 必须 ArkUI 原生重写（carrier = arkui）

- **系统级交互**：深度集成鸿蒙系统能力（通知/分享/账号/权限/后台任务/系统返回拦截/半模态手势）——经 `runJavaScript` / `registerJavaScriptProxy` 桥接可行但脆、时序难保，走原生。
- **性能敏感**：长列表、动画主路径、启动首屏——Web 内核加载与渲染时延不可接受。
- **离线主路径**：核心功能须离线可用，且 ArkWeb 内存储与原生存储双轨易失控。
- **核心数据面**：todo/账号等主数据对象必须落 Phase 3 原生 data-contracts；Web 壳页**不得私启 localStorage 独立存储**造成双轨真相。混合页（hybrid：外壳原生 + 内嵌 Web）允许，但数据面归属必须在 carrier_decision 中声明归原生。

### ArkWeb 能力边界（已核实/待核实）

- 已核实（2026-08 调研）：DOM Storage 支持（`domStorageAccess(true)` 开启，Local Storage 持久化在应用沙箱目录）；Cookie 经 `WebCookieManager.configCookie/configCookieSync` 管理并落盘；`runJavaScript` 注入、`registerJavaScriptProxy` 双向桥可用。
- `PENDING_CONFIRM`：IndexedDB 持久化细节、Service Worker/推送支持范围、离线缓存策略——**下结论前不得据此设计离线承载**，涉及面记 GAP + 人工裁决。

### 冒烟链补充（Web 壳页）

Web 壳页除 scaffold-core-phone 冒烟链外，须留 **ArkWeb 生命周期真实痕迹**：`onControllerAttached` / `onPageEnd` 回调日志或 hdc 截图目检页面真实渲染（不接受"Web 组件已挂载"的口头声明）；Web 资产（URL/离线包）指纹随 input-lock 冻结。

## UI 蓝图四字段的本路径取值

`source_structure` = DOM 结构锚（路由路径 + 关键选择器层级）；`preserve` = texts（`page.evaluate` 抽取的文本集合）+ 交互元素清单 + 配色；`native_carrier` = route/modal@HOST + `Web` 或 ArkUI 组件组合；`native_component` = 原生重写面给 Web 控件→ArkUI 映射（div→Column/Row、button→Button、input→TextInput、ul/li 列表→List+LazyForEach、select→Select/TextPicker、checkbox/radio→Toggle/Radio、dialog→bindSheet/CustomDialog、导航→Navigation+NavPathStack；映射思路借鉴 Android→iOS UI 迁移论文的层级映射法，https://arxiv.org/html/2409.16656v1 ）。

## 组件/布局/路由/存储映射细则（native_component 的扩展表）

- **布局**：CSS Flex 行/列 → `Row`/`Column`（flex-grow ↔ `layoutWeight`）；CSS Grid → `Grid`+`GridItem`（行列模板 1:1 换算，span 合并单元格保留）；栅格断点布局 → `GridRow`/`GridCol`；绝对定位/层叠 → `Stack`。
- **表单**：`input[type=text|password]`→`TextInput`；`textarea`→`TextArea`；`checkbox`→`Toggle`(check)；`radio`→`Radio`；`select`→`Select`/`TextPicker`；`input[type=date]`→`DatePicker`；富文本编辑器 → Web 壳承载或 `RichEditor`（组件能力对照后裁决）。
- **SPA 路由→Navigation**：路由表逐条映射为 `Navigation`+`NavPathStack` 路由节点（路径常量化防漂移）；history 与 hash 模式同法；路由参数 → NavPathStack params；浏览器后退/popstate → Navigation 返回（含系统返回手势）；锚点滚动 → Scroll 控制器。
- **存储载体初判**（Phase 3 只立接口，物理落点 Phase 4 定）：Web 壳页 localStorage → ArkWeb DOM Storage（应用沙箱内）；原生重写页 KV/设置项 → `@ohos.data.preferences`；IndexedDB 级结构化数据 → `@ohos.data.relationalStore` 或应用沙箱文件；sessionStorage → 内存态（显式生命周期注释，不落盘）。

## 最小验证设想

todo 单页应用：主列表页裁决 arkui（核心数据面+性能），"关于/帮助"页裁决 web（内容型）——surface-plan 含两条 carrier_decision 及理由；鸿蒙端工程构建/安装/启动冒烟真实通过，Web 壳页 onPageEnd 留痕 + 截图；原生页冒烟后空壳路由可跳转。

## 参考（真实 URL，调研 2026-09-01）

- ArkUI Web 组件（ArkWeb：`domStorageAccess`/`runJavaScript`/`registerJavaScriptProxy`）— https://developer.huawei.com/consumer/cn/doc/harmonyos-references/arkui-ts-component-web （如链接变更，从 https://developer.huawei.com/consumer/cn/doc/ 站内检索"Web 组件"）
- @ohos.data.preferences — https://developer.huawei.com/consumer/cn/doc/harmonyos-references/js-apis-data-preferences ；@ohos.data.relationalStore — https://developer.huawei.com/consumer/cn/doc/harmonyos-references/js-apis-data-relationalstore
- Navigation 导航开发指导（NavPathStack）— https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-navigation-navigation （站内检索"Navigation"兜底）
- Android→iOS UI 迁移论文（层级映射法来源，正文已引）— https://arxiv.org/html/2409.16656v1
- TodoMVC（carrier 裁决最小验证对象）— https://todomvc.com/
