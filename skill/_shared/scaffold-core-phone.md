---
name: scaffold-core-phone
description: 鸿蒙手机目标端承载的通用内核（分面搭壳三规则/原生优先规约/UI 蓝图四字段/interface-only 数据契约/真实冒烟链）。所有以手机为目标端的路径（android/ios/web）的 scaffold.md 薄壳必须引用本文件；从 android 套 harmonyos-migration-scaffold v3 平台无关化而来，不含业务逻辑。
---

# 鸿蒙手机承载内核（分面搭壳 / 原生优先 / 冒烟链）

**定位**：Phase 3 不"为每个页面建壳"，而是**给功能地图里的每个 UI 承载面装壳、给数据关系立接口**。输入 = Gate 2 PASS 的 feature-map 三件套（surfaces[] 含 kind: page/container/sheet/dialog/reusable-component、navigation-relations 候选、data-relations），输出 = 一个能构建、能安装、能启动的 ArkUI 原生骨架——**一行业务逻辑都不写**（那是 Phase 4 的事）。源端 UI 可原生化改造，但行为的载体与数据进出口必须就位。

## Non-negotiable

- 继承四阶段治理铁律（模型不放行 / 机器判定 / 证据不可变 / 显式 GAP，见 controller-core）；surface 来自冻结的功能地图，**禁止人工手抄页面清单**。
- **分面搭壳三规则**（唯一途径）：
  1. `page` → 路由节点 + 页面壳（`Navigation`+`NavPathStack` 目的地表或系统路由表，page_shell_id 唯一大写 ID）；
  2. `sheet`/`dialog` → 模态载体挂到宿主页（`bindSheet` / `CustomDialog` / `ActionSheet` / `bindContentCover`；宿主三层推断：导航显式边 → 同 feature 页面 → 确定性兜底，来源透明记录）；
  3. `container` / `reusable-component` → **不建壳**（透明宿主不需要证明——防"普通组件被当独立页面"的死锁根源）。
- **原生优先规约**：壳与后续实现都优先鸿蒙官方组件与推荐交互——`Navigation`+`NavPathStack`（页面栈/返回）/ `Tabs`+`TabContent`（底栏多页，tabs_owner 唯一仲裁）/ `List`+`LazyForEach`（长列表）/ `Scroll`·`Grid`·`Swiper` / `CustomDialog`·`bindSheet`·`ActionSheet`（弹层）/ `Toggle(Switch)` / `Select`·`TextPicker`·`DatePicker` / 系统返回（侧滑 + `onBackPressed`）。自定义实现仅当原生不能表达，且必须在 surface-contract notes 登记理由（受控原生化，非自由重设计）。
- **UI 蓝图四字段**：surface-plan 每个用户可见 surface（routes/modals）冻结——`source_structure`（源端结构锚：Android View 层级 / iOS scene·视图树 / Web DOM+路由路径）/ `preserve`（UI_FIDELITY=HIGH 的机械表达：texts / content_desc 或选择器 / 配色）/ `native_carrier`（route | modal@HOST | none + 承载组件）/ `native_component`（ArkUI 原生组件映射）。**缺任一 Gate 3 FAIL，无豁免**。
- **数据契约 interface-only**：按 data-relations 聚合语义对象生成 `data-contracts/<object>.json`（feature_id / data_object / 读写方向 / 源端持久化仅作参考记录），不规定鸿蒙物理载体（Preferences / RelationalStore 由 Phase 4 裁决）。壳内**无** ViewModel、业务状态、网络请求、持久化、假数据。
- **冒烟链必须真实**：构建/安装/启动证据必须来自冻结的命令行工具与真实模拟器/真机，不接受 IDE 预览、口头声明或手贴截图。
- 已知缺口显式登记（skipped surfaces / route hints），不允许静默吞掉。

## 流程（五步）

1. **拿工单开工**：消费 Gate 2 三件套；核对 stage-03-input-lock（绝对路径 + sha256，篡改可检测）。
2. **分面搭壳**：按三规则生成 surface-plan（page→route / sheet·dialog→modal@HOST / container→none）；资产链三态（完整→校验 / 缺失→跳过 / 残缺→报错）。
3. **立 UI 蓝图**：每 surface 四字段非空；底栏 Tabs 特征多页命中时 tabs_owner 唯一仲裁，防双壳。
4. **立数据接口**：interface-only 契约 + (feature, object) 组合展开，双向闭合无孤儿。
5. **Gate 3 四条（机器可查）**：① 承载面覆盖——每个 verify_mode=RUNTIME 的 feature ≥1 个非 container surface 有 route/modal 载体；② 数据契约无孤儿——data-relations ↔ data_contracts 双向闭合；③ 冒烟链——构建/安装/启动类别覆盖（TOOLCHAIN / CLEAN_BUILD / BUNDLE_CHECK / SIGNING_CHECK 单例 + INSTALL / LAUNCH 每设备）；④ 环境链——HENV 冻结 + preflight 完整。PASS → CLOSED + 闭包 manifest + 四项 attestations（real_file_review / contract_only / dependency_review / runtime_smoke）。

## 常见 FAIL 形态（Gate 3 机器可直接判出）

- 普通组件/布局壳被登记为 page → 承载面冗余且路由表污染（分面规则 3 违例）。
- sheet/dialog 找不到宿主或挂到 container 上 → modal@HOST 落点非法。
- UI 蓝图四字段任一为空 / native_carrier 写了组件但 surface-plan 无对应路由或模态登记。
- data-contracts 里出现物理选型字样（违反 interface-only）或壳代码里出现网络请求/持久化/假数据。
- 冒烟证据缺命令参数数组、退出码或截图时间戳链（预览截图/手贴 PNG 不是证据）。

## 角色与留痕（沿用 android 套分工）

architecture-lead（壳与路由）、navigation agent（注册表登记）、toolchain agent（构建与 lock 依赖）、environment freezer（HENV）、acceptance reviewer 各自留痕；Gate 3 结论由 controller 按同一规则**独立重算**（不信任 scaffold 侧自述报告）。

## 平台差异参数（各路径薄壳必须填）

| 参数 | 说明 |
|---|---|
| 源端 surface 语义来源 | 该路径 inventory 产出的结构扫描方式（View 层级 / scene / 路由+DOM） |
| source_structure 锚粒度 | 源码 file:line / sceneID / CSS 选择器+路由路径 |
| 控件映射表 | 源端控件 → ArkUI 官方载体（各路径薄壳给表，或指向已有映射参考） |
| 特有承载裁决 | 本路径独有（如 web 路径的 ArkWeb vs ArkUI 承载裁决） |

## 环境与工具

- DevEco Studio + HarmonyOS NEXT SDK（API 12+ 基线，与 `skills/android-to-harmony-phone/arkui-next-reference/` 同一 ArkUI 口径）；DevEco 手机模拟器（Phone Emulator，Windows x86 本地可用，受限时远程模拟器补）。
- 冒烟链示例命令（具体以冻结环境为准）：`hvigorw assembleHap`（构建+签名）→ `hdc install entry-default-signed.hap` → `hdc shell aa start -b <bundleName> -a <ability>`（启动）→ 前台校验 + `hdc shell snapshot_display -f <file>` 截图目检。每个命令记录参数数组、退出码、输出与可执行文件哈希。可执行文件路径两式并列（总表见 `_shared/00-CONVENTIONS.md`）：
  - Windows：`D:\DevEco Studio\tools\hvigor\bin\hvigorw.bat`、`D:\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe`（Git Bash 下传设备路径需 `MSYS_NO_PATHCONV=1`）
  - macOS：`/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw`、`/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc`

## 参考（调研来源）

- android 套 v3 范式出处：`skills/android-to-harmony-phone/harmonyos-migration-scaffold/SKILL.md`（分面搭壳/蓝图四字段/数据契约/九类冒烟命令类目）及其 `references/environment-toolchain.md`（命令冻结与证据规则）。
- 华为官方：组件导航 Navigation https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkts-navigation-navigation ；ArkTS 声明式开发指南（Tabs/List/CustomDialog 等组件，developer.huawei.com 搜对应组件名）。
- UI 迁移映射思路借鉴：Android→iOS UI 迁移论文 https://arxiv.org/html/2409.16656v1 （源端 UI 层级提取→按规则映射目标端组件→语义约束保真，本内核 native_component 字段的范式来源）。

## 冒烟链命令（双平台，按 CONVENTIONS 路径表）

1. 构建：`hvigorw clean assembleHap`（Windows 用 DevEco 自带 Node 调 hvigorw.js；macOS 直接 hvigorw）→ 产物 hap + 构建日志落档；
2. 安装：`hdc install <hap>`（设备序列以 `hdc list targets` 实测为准）；
3. 启动：`hdc shell aa start -b <bundle> -a <ability>`，随后 `uitest dumpLayout` 采集首屏组件树作启动证据。工程路径含非 ASCII 时复制 ASCII 临时目录构建。

## Gate 3 自检清单（机器可复核项）

① 所有 included 功能的承载面有壳且 surface-plan 四字段齐（缺一 FAIL）② sheet/dialog 均有宿主且宿主来源透明 ③ 数据契约覆盖全部 data-relations 对象（无孤儿）④ 标准交互均有原生映射或登记自定义理由 ⑤ 构建/安装/启动三证齐全（命令 + 真实输出）⑥ 探针本体（如设）已生成并记哈希。
