---
name: inventory-core
description: 源程序深度理解的通用方法论内核（功能语义地图/行为契约六要素/分级验证/对账四态）。各路径的 inventory.md 薄壳引用本文件并补充平台差异。回答"如何全面理解源程序"。
---

# 源端理解内核（平台无关）

目标：给 Phase 4 一张"源程序到底怎么工作"的地图——不是把每个页面证明一遍，而是**以用户功能为中心**，把最容易迁错的行为做成可验证的标准答案。

## 流程（九步，继承 Android 版范式并平台无关化）

1. 消费 Gate 1 冻结的 scope（included/excluded 功能、数据范围、环境）。
2. **静态扫描分类**：把源程序界面/结构枚举为 surface-index——page / container / sheet·dialog / component / viewmodel·logic / repository·data / settings / platform-capability。防"普通组件被当独立页面"；枚举必须来自工具或代码遍历，不许手抄清单。
3. **功能语义地图** feature-map：每功能一行——feature_id / 一句话语义 / source_refs（锚定到源码或工程文件的具体位置）/ surfaces[] / data_objects / risk_level / verify_mode。
4. **行为契约**（每 included 功能 ≥1 条）：六要素 = 意图 / 操作序列 / 数据变化 / 可见结果 / 重启后状态 / 副作用。操作序列要具体到可重放（点哪里、输什么、等什么）；结果写成可判定断言。
5. **分级验证** verify_mode：
   - RUNTIME（易迁错才真跑）：增删改、持久化、语言/主题、账号、同步、权限、复杂设置
   - SOURCE_CONFIRM（纯展示/跳转/容器宿主）：源码确认即可，不为"被访问过"硬跑
6. **真实运行取证**（仅 RUNTIME）：在源平台真实执行操作序列，采集断言判定 + 关键前后快照。取证规范：记录实际命令/操作、绑定前台进程/路由、前后状态各一份、截图先目检。源端工具链由各路径薄壳指定（如 Android 用 adb+uiautomator、Web 用 DevTools/CDP、Windows 用 WinAppDriver/UIA）。
7. **源码↔运行对账** 四态：CONFIRMED（声明且实测确认）/ CONFLICT（源码说有变化但实测断言失败，需人工解释）/ SOURCE_CONFIRMED / GAP（没跑，注明原因）。执行受阻（导航失败/崩溃）归 GAP 不归 CONFLICT。
8. **数据关系**：功能 ↔ 数据对象读写集矩阵 + 持久化机制结论（有无本地存储、存在哪、重启行为）。
9. **蒸馏交付**：feature-map、behavior-contracts、data-relations、reconciliation、运行证据包、已知 GAP。Gate 2 前闭包校验。

## 平台差异参数（各路径薄壳必须填）

| 参数 | 说明 |
|---|---|
| surface 枚举工具 | 该源平台上真实可用的结构扫描方式 |
| 运行取证工具 | 真实驱动 + 断言采集的命令/脚本 |
| source_refs 粒度 | 文件:行 / 选择器 / 路由，取该平台最稳定的锚 |
| 特有风险面 | 该平台独有且易迁错的维度（如 Web 的 localStorage、Windows 的注册表） |

## 防伪口径

运行事实 = 真实执行 + 断言匹配，二者缺一即不是事实。无法运行降级 SOURCE_CONFIRM + GAP，**禁止**以"应该没问题"补位。

## 行为契约 schema（每 included 功能 ≥1 条）

| 字段 | 要求 |
|---|---|
| bc_id / feature_id | 唯一 ID，可追溯 |
| 意图 user_intent | 一句话，用户视角 |
| 前置状态 pre_state | 可校验的种子/初始条件（含 test_seed 引用） |
| 操作序列 operation_steps | 具体到可重放：动作（tap/input/swipe/…）+ 目标锚点 + 输入值 + 等待条件；双端各自映射列在 P3/P4 补 |
| 数据变化 data_state_change | 语义对象读写集（对象.字段 级） |
| 可见结果 observable_result | 可判定断言（锚点文本/存在性/数量），至少一条强断言 |
| 重启后状态 persistence_targets | 对象级期望；无则显式 NONE |
| 副作用 side_effects | 外部可见项（网络/通知/系统设置）；无则 NONE |
| verify_mode | RUNTIME / SOURCE_CONFIRM（P2 侧断言一律 required，豁免只属于 P4 重放侧） |

## 对账四态判定矩阵

| 源码声明 | 运行实测 | 态 |
|---|---|---|
| 有行为 | 断言全过 | CONFIRMED |
| 有行为 | 断言失败 | CONFLICT（必须人工解释：改断言/改理解/环境问题，三选一并留痕；解释不能翻转 CONFLICT 本身） |
| 有行为 | 未跑（降级） | SOURCE_CONFIRMED |
| 无/弱声明 | 未跑 | GAP + 原因码 |

GAP 原因码约定：SOURCE_RUNTIME_UNAVAILABLE（平台工具缺失）/ ENV_NOT_FROZEN / SCOPE_EXCLUDED / PENDING_HUMAN。high-impact GAP 进 Gate warnings 供人工复审。

## BC 内容展示断言规则（2026-09-01 增补）

涉及内容展示（文章正文/帖子内容/消息详情等）的 BC，`observable_result` **必须具体到**：
- "正文文字出现且非占位符"（而非笼统的"显示正文内容"）
- 建议断言格式：`text_visible=<正文前N字符>` 或 `rich_content_rendered=true`（正文区有非元信息文字）
- 禁止只断言标题/元信息就放行阅读页契约——CapyReader BC-0011 教训：契约写了"显示正文内容"但粒度不够，验证时只验了标题
