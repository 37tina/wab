---
name: legacy-to-automotive-scaffold
description: 传统桌面软件迁鸿蒙车机的目标承载薄壳：桌面窗口拓扑到车机分栏/多窗三态的映射、安全约束进入 UI 蓝图、语音优先替代通道声明、AAOS 车机特性生态对照、模拟器冒烟链。Phase 3 使用；不写业务逻辑。
---

# legacy-to-automotive · scaffold 薄壳

## 引用

- `skills/_shared/scaffold-core-automotive.md`（车机承载模型/安全约束规约/组件规约/多窗三态断点映射/环境与工具，**本薄壳的全部车机事实来源**）
- `skills/_shared/controller-core.md`（Phase 3 判据）

## 本路径差异（源端桌面 → 目标座舱）

**承载面映射基线**（surface kind → 车机载体，scaffold-core"组件规约"的车机化落点）：

| 源端形态 | 车机承载 |
|---|---|
| 主窗口 + 菜单栏/工具栏 | 全屏分栏：左分栏 A（常用重要功能，官方规定）+ 内容区 B/C，`SideBarContainer` 或 `GridRow` 断点组合 |
| 多文档/MDI/多窗口平铺 | 多窗三态（1/3、2/3、全屏）或官方分屏比例（1:2 / 1:1）；不建多窗口 |
| 模态对话框/向导 | `CustomDialog`/`bindSheet`，多步向导改左分栏内分步或 Sheet 分步（行车中模态受限策略 `PENDING_CONFIRM`） |
| 右键菜单/快捷键 | 长按/更多按钮/方向盘按键与语音映射声明（能力 `PENDING_CONFIRM`，仅登记不实现承诺） |
| 托盘/常驻后台 | 去除或转任务卡片（PLATFORM_DEVIATION 候选） |
| 容器/可复用组件 | 不建壳（沿用功能语义范式） |

**UI 蓝图新增 safety 节**（Gate 3 检查非空，缺任一 FAIL）：每个用户可见 surface 冻结 `occlusion_policy`（关键控件避开方向盘遮挡区）/ `driving_state_policy`（行车禁用/降级/替代通道）/ `minimal_interaction_map`（桌面操作步数 → 车机重设计路径 harmony_steps 草案）/ `audio_focus_claim`（占用/不占用）。Electron 源端：默认裁决为 ArkUI 原生重构（不走 WebView），裁决记录进 decision-log。

**多窗三态形态声明**：涉及多窗承载的 surface 按 scaffold-core"多窗三态与断点形态映射"补窗态三字段（全屏/2/3/1/3 各自布局形态 + 承载组件），与 tablet 路径 breakpoint_plan 同构；禁止只设计全屏态。

**语音优先替代通道落点**（scaffold-core"语音优先"节的本路径落地）：`driving_state_policy` 与 `minimal_interaction_map` 中的驾驶态替代通道按 ①语音（登记语义意图，不绑实现）②停车后继续 ③简化触控 排序；源端键盘密集型功能（数据录入/搜索/长文本）默认进语音替代裁决，不允许"行车中弹软键盘"设计存活到 Gate 3。

**冒烟链**：DevEco Studio 构建 HAP → 座舱模拟器 `hdc install`/`aa start` 启动 → `snapshot_display` 截图留痕；模拟器不可得时按 scaffold-core 降级策略执行并显式记录降级级别（布局断言/Previewer/人工录屏）。

## AAOS 车机特性生态对照（参考系，非验收标准）

源端如曾在 Android Automotive 场景运行（或团队按 AAOS 习惯设计），按下表换算到鸿蒙口径；**四断言判定一律以 ICS-v2 为准**：

| AAOS 概念 | 鸿蒙座舱对位 | 落点 |
|---|---|---|
| Distraction Optimized（DO）应用规范 | 驾驶安全管控场景化方案（按行车状态管控屏幕与应用状态） | driving_state_policy |
| 驾驶分心限制（Driver Distraction Guidelines） | 行车态禁用/降级/替代通道断言 | 同上 |
| CarApp API/模板化 UI | 鸿蒙无逐项等价模板 API；落 ArkUI 原生分栏范式（`PENDING_CONFIRM` 模板规范开放度） | native_carrier |
| 车机多屏（instrument cluster/AAOS 多 display） | 中控默认落点 + 仪表/副驾屏逐项裁决（第三方上仪表 `PENDING_CONFIRM`） | 落屏裁决（Gate 1） |
| 语音（Google Assistant for Cars） | 语音替代通道声明（第三方语音技能接入 `PENDING_CONFIRM`） | minimal_interaction_map |

## 最小验证设想

开源 Qt 计算器迁车机：菜单栏 → 左分栏 A（数字键大目标化）、键盘输入功能（桌面主输入路径）→ 触屏按钮 + 语音映射声明；蓝图 safety 节四字段齐全 + 窗态三字段（计算器 1/3 窗态收为单列历史列表）；座舱模拟器启动冒烟 + 遮挡区断言（数字键区不落左下遮挡矩形）。

## 参考（调研来源，2026-09 访问）

- 华为官方：智能座舱 2.0 文档中心 https://developer.huawei.com/consumer/cn/overview/ICS-v2 ；设计指南（分栏/遮挡/多窗三态）https://developer.huawei.com/consumer/cn/doc/design-guides/smart-cockpit-0000002045925712
- 华为官方：应用架构（左分栏一级界面）https://developer.huawei.com/consumer/cn/doc/design-guides/smart-cockpit-application-architecture-0000002592486434
- 生态对照：Android for Cars 文档区（AAOS/CarApp/驾驶分心）https://developer.android.com/training/cars ；车机应用质量 https://developer.android.com/docs/quality-guidelines/cars-app-quality （标题以页面为准）
- 最小验证可跑例：Qt 官方计算器示例 https://github.com/qt/qtbase/tree/dev/examples/widgets/widgets/calculator
