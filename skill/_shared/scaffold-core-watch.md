---
name: scaffold-core-watch
description: 任意源平台到鸿蒙手表（穿戴）端的 Phase 3 承载内核：圆屏弧形组件承载面与形态约束、可用组件子集（与手机全集的分叉）、腕上交互挂载点、单页导航范式、性能预算意识、interface-only 数据契约与手表模拟器冒烟链。所有迁往鸿蒙手表的路径套件 scaffold.md 薄壳必须引用本文件。
---

# 鸿蒙手表承载内核（scaffold-core-watch）

**定位**：Phase 3 在鸿蒙手表端搭原生承载壳。HarmonyOS 5.1.0（API 18）首次开放智能穿戴应用开发（首发面向 HUAWEI WATCH 5 系列），默认形态为**圆形屏幕**，ArkUI 为圆屏提供弧形组件族与表冠事件。本内核回答四件事：手表端的承载面长什么样（圆屏组件 + 极浅页面栈）、形态约束是什么（圆屏几何/安全区/信息预算）、交互怎么挂（表冠/点按/系统侧滑返回）、冒烟链在哪跑（DevEco 手表本地模拟器 / Previewer 兜底）。一行业务逻辑不写。

## Non-negotiable

- 继承四阶段治理铁律（`controller-core.md`）：模型不放行 / 机器判定 / 证据不可变 / 显式 GAP；本文件只加不减。
- **零业务逻辑**：壳只含页面路由、圆屏布局、交互挂载点与 interface-only 数据契约；无 ViewModel、无请求、无持久化、无假数据。
- **圆屏适配是硬门禁**：每个用户可见 surface 的 UI 蓝图必须声明①圆屏承载组件（ArcList 族优先）②安全区处理（内容内收，禁止直屏矩形布局硬套）；缺任一字段 = Gate 3 FAIL，无豁免。
- **交互重映射必须显式登记**：源端每类输入（表冠滚动/选择、点按、长按、系统侧滑返回）→ 目标端挂载点（内置默认表冠响应 或 `onDigitalCrown` 自处理 + `digitalCrownSensitivity`；`onClick`；长按手势；系统返回）。映射表缺行 = FAIL，不许"默认可行"。
- **手表↔手机联动只立语义契约**：消息/文件/通知三类通道写成 interface-only 契约；无法等价承载时走 `PLATFORM_DEVIATION` 人工裁决，禁止静默删功能或静默降级。
- **API 版本门槛**：穿戴开发需 HarmonyOS 5.1.0（API 18）及以上 SDK + DevEco Studio 5.1.0 Release 及以上；环境不满足记 `TOOL_GAP`，不得绕过。
- 构建与冒烟证据必须来自真实命令行（hvigorw / hdc）与真实运行载体（模拟器/Previewer/真机），预览截图冒充运行输出 = 作假。

## 手表形态约束（圆屏几何与信息预算）

- **圆屏几何**：有效信息区是圆的内接区域，四角内容必被裁切，上下边缘行宽急剧收窄——布局必须"中间行最宽、边缘行最短"（ArcList 的弧形排布/上下边缘自动缩放即为此设计）。长文本行不换行铺满宽度 = 四角截断缺陷。
- **安全区**：关键交互元素（按钮/选择器）与关键信息置于中央可视区，避开上下极点附近的窄条区；蓝图的安全区字段必须写"内收策略"（如内容半径预留、边缘页眉页脚短句化）。
- **触控目标**：小屏+运动腕上场景，触控目标须显著大于手机规范（具体最小尺寸数值以官方穿戴设计指南为准，`PENDING_CONFIRM`，不得自定数值充当官方标准）。
- **单页单职责**：手表页面一屏一意图（列表页/详情页/确认页各一），手机页面的信息聚合块拆成多页或滚动段；页面层级 ≤2（列表→详情），更深层级在源端就必须给出合并/降级方案。
- **文案预算**：标题短语级、正文短句级、操作动词按钮化——文案超预算先裁剪源端内容再映射，不允许小字号硬塞（字号低于可读下限的"还原"是假还原）。

## 可用组件子集（与 scaffold-core-phone 全集的分叉）

| 类别 | 组件 | 使用约束 |
|---|---|---|
| 优先族（圆屏原生） | `ArcList` / `ArcListItem` / `ArcSwiper` / `ArcButton` / `ArcScrollBar` / `ArcAlphabetIndexer`（均 API 18+） | 列表/轮播/按钮默认落点 |
| 默认响应表冠的内置组件 | Slider、DatePicker、TextPicker、TimePicker、Scroll、List、Grid、WaterFlow、Refresh、ArcSwiper、ArcList（CrownEvent 文档确认清单） | 表冠交互优先选这些，免自处理焦点 |
| 慎用族（直屏通用） | 默认 `List`/`Scroll`/`Grid`、直排 `Flex`/`Column` 大表单 | 圆屏可用但信息利用率低；蓝图 notes 必须登记理由 |
| 不引入族 | 底栏 `Tabs` 多页范式、富表格/大表单整页平铺、依赖精确像素对位的布局 | 手表形态不适配（单职责约束）；确需引入走人工裁决 |
| 事件能力 | `onDigitalCrown` + `focusable`/`defaultFocus`/`focusOnTouch` + `digitalCrownSensitivity`；`CrownEvent`（timestamp/angularVelocity/degree/action） | 自处理表冠时的全套挂载点 |

- 分叉规则：phone 内核"原生优先清单"在手表端收缩为上表子集；超出子集使用原生组件的，surface-contract notes 登记理由（受控扩展，非自由引入）。
- 分叉规则的判定口径：判定依据是**形态适配**而非 API 可用性——某组件 API 在穿戴 SDK 里存在 ≠ 适合手表（如底栏 Tabs 在 API 层可用但违反单职责约束）；形态不匹配的引入一律走人工裁决，API 层不可用的直接 TOOL_GAP，两类不得混谈。
- `ArcScroll`、`ArcSlider` 为社区文章提及的组件（`PENDING_CONFIRM`，使用前须在官方 API 参考核实）。

## 交互挂载点登记表（蓝图必填）

- 表冠滚动/调值：优先选**默认响应表冠的内置组件**；自定义处理用 `onDigitalCrown(handler)`，组件必须获焦（`focusable`/`defaultFocus`/`focusOnTouch`），灵敏度用 `digitalCrownSensitivity(CrownSensitivity.*)`；`CrownEvent.degree`(相对角度 [-360,360])/`angularVelocity`(°/s) 换算成源端值域须写明公式。
- 点按 → `onClick`；长按 → 长按手势（圆屏可达性权衡须注明）；系统侧滑/表冠默认行为承担返回，不自绘返回逻辑。

## 页面层级与导航范式（手表端固定式）

- 层级上限 **2 层**（列表 → 详情）；源端更深层级的承载方案只有三种：合并（第 3 层内容并入详情页分区）、降级（详情内展开/收起段）、裁剪（excluded + 裁决记录）——蓝图必须写明每处选了哪种。
- glance 型入口（表盘复杂功能/Tile/通知）直达深层内容时，登记为**独立入口 surface**（entry_point=glance），其落地页仍受 2 层限制；入口本体无等价承载时走联动裁决（流程第 6 步），不许折叠成"普通页面"。
- 返回语义全部交给系统（侧滑/表冠默认行为）；页面间传参走路由参数显式声明，禁全局可变状态传参。
- 模态（sheet/dialog 类）在手表端克制使用：一次仅一个活动模态、模态内不做二级模态；违反即蓝图退回（与单职责约束同判）。

## 性能预算意识（手表端弱于手机的资源约束）

- 穿戴设备体积/电池约束下 CPU/内存/电量预算显著低于手机——壳与实现都要按"最省"路径设计；官方公开的启动时间/帧率/内存门槛数值 `PENDING_CONFIRM`，未核实前只立意识不立数字，禁止编造预算值当验收线。
- 长列表必须 `LazyForEach` + `cachedCount` 控制（ArcList 支持两者，见官方指南）；禁止 ForEech 全量加载。
- 图像/动效：大图须压缩裁剪到位再上屏；复杂转场动效降级为系统默认转场，除非契约显式要求。
- 启动路径：壳阶段保持零初始化网络/磁盘 I/O（与零业务逻辑铁律一致）；首帧依赖数据全部走静态占位，真实数据填充是 Phase 4 事。

## 流程

1. **消费冻结输入**：Phase 2 的 feature-map、surface-index、data-relations（含本路径薄壳补充的源端特有 surface 分类）。
2. **承载面判定**：`page` → 路由壳；`sheet`/`dialog` → 模态壳挂到宿主页；`container`/`reusable-component` → 不建壳。**手表特有 surface 三选一裁决**：①原语等价承载（如通知长样式页→普通模态页）②`PLATFORM_DEVIATION` 载体（如表盘复杂功能→模板化通知，见步骤 6）③excluded（回 controller 修改冻结范围）；裁决必须留痕，禁止静默丢弃。
3. **圆屏承载规则**（结合"可用组件子集"表选型；每页一个职责，页面层级 ≤2）：
   - 可滚动列表 → `ArcList` + `ArcListItem`（长列表用 `LazyForEach` + `.cachedCount(n)`；可选 `ArcScrollBar` 共享 `Scroller`；首项定位 `initialIndex`；大量条目检索 `ArcAlphabetIndexer`）；
   - 全屏轮播/分页 → `ArcSwiper`；操作按钮 → `ArcButton`（强调/普通/警告样式）；
   - 默认 `List`/`Scroll`/`Grid` 在圆屏上可用但信息利用率低，使用必须在蓝图 notes 登记理由（慎用族）。
4. **交互挂载点登记表**（见上节，缺行 FAIL）。
5. **数据契约**：按 data-relations 聚合语义对象，interface-only（读写方向、字段），不规定物理载体（Preferences/RelationalStore 由 Phase 4 定）。手表本地存储：确认模块在穿戴形态下的可用性后再选型（`PENDING_CONFIRM` 项须实测后落定）。
6. **联动语义契约**（手表↔手机）：通道分类为 消息(P2P)/文件传输/模板化通知 三类 interface；目标端落点：手机侧 **Wear Engine Kit**（手机应用向华为穿戴设备发模板化消息通知、消息与文件互传）；手表侧独立应用与手机的对等会话语义（对位 watchOS WCSession / Wear OS DataLayer）无逐项等价 API → 一律进 `PLATFORM_DEVIATION` 裁决，不许假装等价。
7. **工程脚手架**：DevEco Studio 新建工程选 Empty Ability 模板且 Device Type = Wearable；`module.json5` 的 `deviceTypes` 含 `wearable`；SDK = API 18+；SDK/IDE 版本记入环境冻结。
8. **冒烟链**（真实执行留痕）：`hvigorw assembleHap` 构建 → Device Manager > Local Emulator 新建 **Wearable** 类型模拟器并启动 → `hdc list targets` 确认设备 → 安装、启动（命令以本机 hdc/aa 实际输出为准，缺工具记 `TOOL_GAP`）→ 前台页截图。模拟器不可用时降级 **Previewer** 并显式记录降级（Previewer 证据等级低于模拟器/真机，须在 Gate 报告注明）。
9. **Gate 3 判定**（在 controller-core 判据上特化）：①承载面覆盖（每个 verify 有据的 feature 至少一个非 container 载体）②数据契约无孤儿 ③冒烟链真实通过 ④圆屏声明 + 交互映射表 + 联动裁决记录三件齐全。

## 平台差异参数（本板块）

| 参数 | 值（来源见文末） |
|---|---|
| 目标形态 | 圆形屏幕穿戴设备（HUAWEI WATCH 5 系列，示例分辨率 466×466、半径 233px，出自 ArcList 官方指南示例） |
| API 门槛 | API 18（HarmonyOS 5.1.0）起支持穿戴应用开发 |
| 弧形组件族 | ArcList / ArcListItem / ArcScrollBar / ArcAlphabetIndexer / ArcButton / ArcSwiper（均 API 18 起） |
| 表冠 | `onDigitalCrown`（仅穿戴设备支持，API 18 起）；ArcList 指南另示 `digitalCrownSensitivity` |
| 触觉 | `@ohos.vibrator`（`vibrator.startVibration(effect, attribute)`，需 `ohos.permission.VIBRATE`；NDK 文档标注支持 Wearable 形态）——与源端语义化触觉（WKHapticType 等）非等价，进裁决 |
| 手机联动 | Wear Engine Kit（手机侧 Kit：模板化消息通知、消息/文件互传；HarmonyOS 5.1.0 起多 Kit 新增支持 Wearable 形态） |
| 运行载体优先级 | 手表本地模拟器（Local Emulator, X86，支持 Phone/TV/Wearable）> Previewer（降级须记录）；真机（WATCH 5，Wi-Fi HDC 调试）可选 |
| 模拟器表冠输入 | 模拟器能否模拟表冠旋转 **PENDING_CONFIRM**——取证时先探测（旋转输入触发 ArcList 滚动/事件日志），不可用则按降级路径记录 |

## 环境与工具

- DevEco Studio 5.1.0 Release（build 5.1.0.828）及以上，自带 API 18 SDK；新建工程：Empty Ability + Device Type=**Wearable**。
- 本地模拟器：`Tools > Device Manager > Local Emulator > New Emulator` 选 Wearable 设备类型（X86 本地模拟器支持 Phone/TV/Wearable；Mac ARM 的 NEXT 模拟器当前仅提供 wearable 设备类型）。另有 DevEco Testing 本地模拟器用于手表兼容测试。
- Previewer：IDE 内置，改 `@State` 即时刷新，无需设备（不产生真实运行证据，仅作兜底可视化）。
- 真机（可选）：WATCH 5 开发者选项开启 HDC debugging + Debug via Wi-Fi，IDE `Tools > IP Connection` 连接。
- 圆屏证据口径（供 scaffold/implementation 薄壳复用）：任何"已验证圆屏适配"的结论必须附模拟器/真机截图并过"圆屏三查"（四角无截断、弧形排布可见、触达在安全区）；Previewer 截图只能证明布局意图，不能证明圆屏适配通过。
- 命令行：`hvigorw assembleHap`（构建）、`hdc list targets` / `hdc install` / `hdc shell aa start`（安装启动）、`hdc shell snapshot_display`（截图，可用性以实际输出为准）。可执行文件路径两式并列（总表见 `_shared/00-CONVENTIONS.md`）：Windows 为 `D:\DevEco Studio\tools\hvigor\bin\hvigorw.bat` 与 `D:\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe`；macOS 为 `/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw` 与 `/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc`。

## 参考（调研来源，全部真实访问）

- 华为官方版本说明（API 18 新增 ArcList/ArcScrollBar/ArcButton/ArcAlphabetIndexer/表冠事件，首次支持穿戴）: https://developer.huawei.com/consumer/cn/doc/harmonyos-releases/os-new-feature-510
- 表冠事件参考: https://developer.huawei.com/consumer/cn/doc/harmonyos-references/ts-universal-events-crown ；OpenHarmony 同步文档（onDigitalCrown/CrownEvent 字段与默认表冠组件清单）: https://github.com/openharmony/docs/blob/master/en/application-dev/reference/apis-arkui/arkui-ts/ts-universal-events-crown.md
- 创建弧形列表 ArcList（指南，含 initialIndex/header/scroller、autoScale、space、cachedCount、digitalCrownSensitivity、466×466 示例）: https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-layout-development-create-arclist
- 创建弧形轮播 ArcSwiper: https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-layout-development-arcswiper
- 穿戴应用开发官方入口（穿戴设计规范/开发指南文档区）: https://developer.huawei.com/consumer/cn/multidevice/wearables/get-started/ （中文概览 https://developer.huawei.com/consumer/cn/multidevice/wearables/ ）
- DevEco Studio 5.1.0 + WATCH 5 实战（Empty Ability + Wearable、Previewer、真机 Wi-Fi HDC）: https://dev.to/harmonyos/deveco-studio-510-build-and-run-your-first-harmonyos-wearable-app-on-huawei-watch-5-40mc
- HarmonyOS 5.1.0 发布报道（API 18、DevEco 5.1.0.828、Wear Engine Kit 新增 Wearable 支持）: https://www.ithome.com/0/860/132.htm
- Wear Engine Kit（手机侧模板化消息/通知/文件到穿戴）: https://developer.huawei.com/consumer/cn/sdk/wear-engine-kit/
- 手表兼容测试（DevEco Testing 本地模拟器）: https://developer.huawei.com/consumer/cn/blog/topic/03213449051750459 ；本地模拟器支持 Phone/TV/Wearable: https://ost.51cto.com/posts/22707
- 振动 @ohos.vibrator: https://developer.huawei.com/consumer/cn/doc/harmonyos-references/js-apis-vibrator ；NDK vibrator.h 标注 Wearable: https://developer.huawei.com/consumer/cn/doc/harmonyos-references/capi-vibrator-h
- 手机→穿戴模板化通知（华为健康服务指南，含手表振动提醒条件）: https://developer.huawei.com/consumer/cn/doc/huaweihealth-Guides/device-notification-0000002342776768
