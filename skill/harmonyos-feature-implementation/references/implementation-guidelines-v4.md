# Phase 4 v4 原生优先实现规约（implementation-guidelines-v4）

> 本规约是 Phase 4（harmonyos-feature-implementation）v4 范式的实施纪律
> 唯一权威。配套工具：`scripts/replayer.py`（七段断言重放器）、
> `scripts/surface_contract.py`（功能承载面薄表）。冲突时以本文件 +
> `NATIVE-ADAPTIVE-CONTRACT.md` 为准。

## 0. 一句话原则

**优先使用 HarmonyOS 官方原生组件与推荐交互模式；自定义实现只有在
原生组件不能表达需求时才允许，且必须登记豁免理由。** UI 结构与交互
适配鸿蒙原生惯例，不追求 Android 像素 1:1；但同一份 BC 七段
（intent / precondition / semantic_input / expected_state_change /
observable_result / persistence / side_effect）在双端语义等价，
同意图异路径（android_steps / harmony_steps 各自独立），只验结果断言。

## 1. 原生优先组件映射（强制）

以下模式必须使用对应 ArkUI 原生实现。`surface_contract.py` 的
native_impl_check 静态扫描会逐条检查（R1–R6），命中自造信号且无原生
反证 → FAIL（Gate 4 阻断）。

| 交互模式 | 必用原生实现 | 禁止的手搓形态 | 检查规则 |
|---|---|---|---|
| 底部导航 | `Tabs` + `TabContent`（`barPosition(BarPosition.End)`），状态保持交给 Tabs | Row/Flex + currentIndex + 多个 onClick 自拼底栏 | R1 |
| 应用内路由/页面栈 | `Navigation` + `NavPathStack` + `NavDestination`（官方推荐；router 为旧方案不再新用） | @State currentPage + if/else 条件渲染切"页" | R2 |
| 半模态/底弹 | `bindSheet`（新建 TODO 底弹首选）、`bindContentCover`（全屏模态） | Stack + .position + 半透明遮罩自造面板 | R3 |
| 对话框 | `AlertDialog`（确认类）/ `@CustomDialog`（自定义）/ `promptAction`（Toast） | 同上自造弹层底盘 | R3 |
| 锚点菜单 | `Menu`（排序菜单首选）/ `ActionSheet`（列表选择） | 自绘浮层菜单 | R3/R5 |
| 开关 | `Toggle(ToggleType.Switch)` | Circle + animateTo 自绘滑块 | R4 |
| 选择器 | `Select`（下拉）/ `TextPicker`（滚轮）/ `DatePicker` / `TimePicker` | List 滚动模拟滚轮 | R5 |
| 长列表 | `List` + `LazyForEach`（+ `ForEach` 分组头） | ForEach 全量实例化长列表（性能反模式，列入评审） | — |
| 返回 | 系统返回手势 / `NavPathStack.pop()`；`onBackPress` 只做委托 | PanGesture 自管侧滑返回栈 | R6 |
| 文本输入 | `TextInput` / `TextArea`（含 `@State` 双向） | 自绘光标/键盘拦截 | — |

**判定边界**：native_impl_check 只判「明显用错平台模式」，不做像素比
较、不比较组件树结构。用对原生组件后的样式定制（颜色/圆角/间距）完全
自由，不属于本表管辖。

## 2. 自定义实现豁免流程（唯一例外通道）

1. **先证伪**：实施者必须先在 [arkui-next-reference/] 知识库（见 §7）
   检索对应组件文档，确认原生组件确实不能表达该需求（如 Tabs 均分
   栏宽无法表达磁贴式非等宽底栏）。
2. **代码内登记**（机器可查，replayer/surface_contract 扫描豁免的
   唯一权威标记）：在被豁免文件头加注释——
   `// native-exception(<规则ID>): <为什么原生组件不能表达>`
   例：`// native-exception(R1): 磁贴式非等宽底栏，Tabs 均分栏宽无法表达`
3. **薄表补记**：在 `surface-contract.csv` 对应 feature 行的 `notes`
   列追加 `native-exception` 说明（generate 会覆盖 notes 的扫描段，
   豁免明细请保留在代码注释里；人工补充的豁免理由写在 notes 尾部）。
4. **无豁免标记的自造实现 = native_impl_check FAIL**，Gate 4 阻断，
   不接受口头/文档解释。

## 3. 数据实现规约（Phase 3 data-contracts）

- **只走接口**：所有语义数据对象（data-relations.csv 聚合出的
  Repository 契约）必须通过 Phase 3 `data-contracts` 生成的
  interface-only 契约访问；实施者实现接口，**物理载体自由**
  （Preferences / RelationalStore / 内存 + 持久化策略自选）——
  Android 参考实现（persistence_kind/persistence_location）仅作语义
  对照记录，鸿蒙侧不比物理存储。
- **语义对象级对账**：重放器 data 断言按语义对象名比较
  （`{"object": "sort_option", "op": "equals", "value": "截止日期"}`），
  不比较文件路径/表结构/序列化格式。
- **自检接口义务（RUNTIME feature 强制）**：凡 verify_mode=RUNTIME 的
  feature，其实施必须提供**应用侧数据自检接口**——把语义数据快照
  （对象名 → 当前值）以 JSON 写入应用沙箱
  `<files>/replay-data.json`（可通过自检 Ability/菜单触发）。这是
  `replayer.py` `export_app_data()` 的数据来源；缺失时该 feature 的
  data 断言一律 FAIL（不降级、不放行）。

## 4. harmony_steps 记录规范

实施完成后，为每条 RUNTIME BC 在 `harmony-steps.csv`（或 BC 内嵌
`harmony_steps` 列）记录**真实可重放**的操作序列：

```csv
bc_id,feature_id,steps,notes
BC-SORT-01,FEATURE-HOME-SORT,"[{""action"":""tap"",""target"":""排序""},{""action"":""tap"",""target"":""截止日期""}]",""
```

- `action` 枚举：`tap` / `input` / `back` / `swipe`（与重放器
  `HARMONY_STEP_ACTIONS` 一致；新增 action 必须先改重放器）；
- `target` 用**语义文本**（页面可见文字，如"截止日期"），不用坐标
  （坐标随设备分辨率漂移；重放器负责语义→坐标解析）；
- `input` 必须带 `value`；`swipe` 必须带 `start`/`end`（`"x,y"` 格式，
  仅滑删/拖拽等手势场景使用）；
- **路径自由**：harmony_steps 与 android operation_steps 无需一致
  （同意图异路径）；但必须真的能在最终 HAP 上走通——重放器会逐条
  执行，走不通即该 BC FAIL（fail-closed）；
- 记录必须来自**真实操作**（实施者在模拟器/真机上验证过的序列），
  禁止凭想象编写（重放器 foreground 校验 + 快照断言会戳穿伪记录）。

## 5. 七段 BC 的实施对照方法

每条 BC 按七段逐段对照实施（段名与 `replayer.py` `SEGMENT_ALIASES`
列映射一致；v3 列名自动兼容）：

| 段 | BC 列（v4/v3 别名） | 实施时怎么用 |
|---|---|---|
| intent | intent / user_intent | 功能语义锚点；实现不得偏离意图本身 |
| precondition | precondition / pre_state | 重放前置状态；harmony_steps 起点必须满足 |
| semantic_input | semantic_input | 测试输入值（如关键词"9/5"）；写用例与 harmony_steps 的 value 保持一致 |
| expected_state_change | expected_state_change / data_state_change | 数据义务：映射到 data-contracts 对象写入 + data 断言（`data_object`） |
| observable_result | observable_result | 可见义务：映射到 UI 文案/组件状态 + observable 断言（`text_visible`/`text_gone`/`component_state`） |
| persistence | persistence / persistence_targets | 持久化义务：非空 → 重放器自动做杀进程重启重验（force-stop + start + 重验 observable/data） |
| side_effect | side_effect / external_side_effects | 副作用义务：通知/文件导出等；断言 kind 见 §6 表 |

**义务铁律**：段非空即有验证义务。段非空但 result_assertions 没有对
应机器断言 → 重放器判 `MANUAL_VERIFY_REQUIRED`（进 Gate 4 人工队列，
不是 PASS）。实施者交付前应自查：每个非空段都有对应 kind 的断言。

## 6. 结果断言与四类判定对接（replayer 消费面）

`result_assertions`（JSON-in-CSV，双端共享，android 侧链路同源）按
kind 归入四类，重放器逐类独立判定：

| 类 | 断言 kind | 机器验方式 | 判定 |
|---|---|---|---|
| observable | `text_visible` / `text_gone` / `component_state` | uitest dumpLayout 快照（稳定性双确认后） | PASS/FAIL |
| data | `data_object`（object/op/value；op=equals/contains/exists/not_exists/gt/lt） | 应用侧自检接口导出的语义快照（§3） | PASS/FAIL（无自检接口=FAIL） |
| persistence | `persist_after_restart` / `persist_data_after_restart`（或由 persistence 段隐式触发） | aa force-stop + aa start + 前台校验后重验 observable/data | PASS/FAIL |
| side_effect | `notification` / `file_export`（机器可验）；`calendar` / `clipboard` / `system_setting` / `share`（无公开 API） | hdc 查询系统服务（anm dump / ls） | 可验类 PASS/FAIL；无公开 API 类 → MANUAL_VERIFY_REQUIRED；平台无能力 → PLATFORM_LIMITATION |

判定铁律（重放器无解释权）：断言 FAIL 就是 FAIL；平台无法执行 →
PLATFORM_LIMITATION（Gate 4 PLATFORM_DEVIATION 队列）；操作序列中断/
无记录 → 该 BC 总判定 FAIL（四类单元格按义务独立记录）。防伪三件套：
每步后前台校验（伪访问防护）、快照双确认（动画中间态防护）、重启后
前台校验（伪持久化防护）。

## 7. 参考知识库（项目根 arkui-next-reference/）

实施前必读（按需检索，不要求通读）：

- `README.md`——索引与 TL;DR 高频结论速查；
- `03-navigation.md`——Tabs / Navigation+NavPathStack / 三 Tab + Navigation
  组合架构建议（对应 R1/R2/R6）；
- `07-dialogs-menus.md`——AlertDialog / @CustomDialog / Menu /
  promptAction / bindSheet / bindContentCover 与弹层选型速查（对应 R3）；
- `05-buttons-selection.md`——Toggle / Select / Picker 族（对应 R4/R5）；
- `02-scroll-list.md`——List + LazyForEach 长列表；
- `10-state-management.md` / `11-threading-data.md`——状态管理与数据
  线程（data-contracts 实现参考）；
- `compose-mapping.md`——Compose → ArkUI 组件映射总表；
- `home-page-playbook.md`——Home 页场景实战手册；
- 其余 01/04/06/08/09/12 按场景检索。

## 8. 交付前自查清单（实施者）

1. 每条 RUNTIME BC：harmony_steps 已记录且真实可走通（§4）；
2. 每个非空段有对应 kind 机器断言（§5 义务铁律）；
3. RUNTIME feature 提供数据自检接口（§3）；
4. 无手搓 R1–R6 形态；确需自定义的已加 `native-exception` 注释（§2）；
5. `surface_contract.py generate` + `check` 双过（entry_reachable /
   native_impl_check 全 PASS）；
6. `replayer.py replay --dry-run` 无 unmapped/无 missing_steps；
   有设备环境跑 `replay` 后 `validate` 通过。
## UI 保真红线（R7-R9，2026-09-01 增补：来自 CapyReader 实测教训）

### R7 组件保真：蓝图声明的容器必须落地
- P3 蓝图 `native_component` 中声明的容器/组件**必须在 P4 实现代码中出现**：
  - `SideBarContainer(Overlay 抽屉)` → 实现必须有 `SideBarContainer(SideBarContainerType.Overlay)` + `showSideBar` 状态切换，**禁止退化为 Row 固定并排**
  - `bindSheet` → 必须有 bindSheet，禁止退化为静态 Column
- **Gate 4 加静态扫描**：对蓝图 native_component 中声明的每个容器名 grep 实现代码，未命中 → FAIL（或书面豁免）

### R8 图标保真：禁止纯文字代替图标位
- Android 端是 Icon/Image/Drawable 的位置（底栏菜单/星标/已读标记/添加按钮/汉堡菜单/返回箭头等），鸿蒙端**必须用 SymbolGlyph（系统图标）或 Resource 资源**，禁止 `Text("✕")` / `Text("☆")` / 纯文字代替
- 菜单项格式：`SymbolGlyph(图标) + Text(标签)` 组合（对齐源端"图标+文字"模式）
- 常用映射参考 14-android-to-harmony-map.md 图标映射节

### R9 正文渲染：内容型应用禁止占位符正文
- 涉及文章/帖子/消息等**内容正文展示**的页面：
  - 渲染必须用 `RichText`（解析 HTML）或 Web 组件，**禁止纯 Text 显示 HTML 源码或 '(no content)' 占位符上线**
  - 数据层字段必须核对源端实际消费的字段（RSS 场景：`summary` vs `content` vs `content:encoded`——读源端解析代码确认），鸿蒙端逐字段对齐
- 验收：用一个真实 feed 实测，正文完整可见且非标签原文

### R10 实现完整性：页面级交付定义（2026-09-01 增补）
- 每个页面的"完成" = 同时满足：
  1. 布局结构：蓝图 native_component 全部落地（R7）
  2. 组件保真：图标/控件对齐源端（R8）
  3. 数据接线：真实 Repository/Preferences 调用（探针可读）
  4. 真机可走查：构建安装后页面可达、核心操作可用
- **禁止把"部分实现"标记为完成**：要么完整交付，要么显式标 `partial` 并列出缺失清单（进返工队列）
- 页面间导航：每个页面的入口路由必须接通（禁止"页面写了但进不去"）
