# Android → HarmonyOS ArkUI 迁移 Skill 套件

这是一个面向 **Android 应用迁移到 HarmonyOS ArkUI** 的四阶段 Agent Skill 工作流。仓库当前处于 2.1 行为等价化改造阶段，正在以 Android 应用 **Cresto** 进行真实链路验证。

> 当前状态：开发中。真实验证已完成 Phase 1～3，但 Phase 4 尚未闭环，因此不能将本仓库描述为已经可稳定完成全应用迁移的成品。

## 目标

本项目不再要求 HarmonyOS UI 像素级复刻 Android，而是采用 ArkUI 原生组件、导航和布局。迁移后必须保持以下语义等价：

- 用户意图；
- 存储数据；
- 业务计算；
- 状态变化；
- 可观察结果；
- 跨重启持久化；
- 外部副作用。

Android 和 HarmonyOS 可以使用不同控件和操作路径，但同一用户目标执行后的业务结果不能漂移。

## 四阶段工作流

| 阶段 | Skill | 职责与主要产物 |
|---|---|---|
| Phase 1 | `android-harmony-migration-controller` | 冻结功能范围、源码/APK、环境、运行模式、角色和阶段输入 |
| Phase 2 | `android-migration-inventory` | 分析 Android 源码与运行状态，生成页面清单、行为契约、数据/计算/副作用事实和运行证据 |
| Phase 3 | `harmonyos-migration-scaffold` | 生成可构建、可安装、可启动的 ArkUI Stage 原生骨架，建立路由、页面载体和能力边界 |
| Phase 4 | `harmonyos-feature-implementation` | 实现真实业务，按相同用户意图执行 Android/HarmonyOS 双端比较，完成返修、Gate 4 和最终 HAP |

总控 Skill 负责范围冻结、工单、证据绑定和 Gate，不直接编写业务代码。Phase 2 负责理解源应用；Phase 3 只建立原生基座；Phase 4 才迁移和验证真实功能。

## 仓库结构

```text
.codeartsdoer/skills/
├── android-harmony-migration-controller/  # 总控、工单、输入锁和 Gate
├── android-migration-inventory/           # Android 静态分析、运行证据和行为契约
├── harmonyos-migration-scaffold/          # ArkUI Stage 原生工程骨架
└── harmonyos-feature-implementation/      # 业务实现、双端比较和最终验收
```

每个 Skill 包含自己的 `SKILL.md`、脚本、模板、契约和评测材料。四个 Skill 设计为整包协作，不应把其中任意一个单独理解成一键自动迁移器。

## 行为等价验证

核心验证单位是 Behavior Contract：

```text
用户意图
→ 前置状态
→ 操作
→ 数据变化
→ 业务计算
→ 状态转换
→ 可观察结果
→ 持久化
→ 外部副作用
```

Phase 4 应在 Android 和 HarmonyOS 上分别完成同一用户意图，再由确定性比较器生成 verdict。运行记录不能自行声明 PASS，人工“鸿蒙原生感”验收也不能覆盖行为差异。

## 当前真实验证结果

最近一次完整验证使用 `CRESTO-VERIFY-RUN1` 和 `native-adaptive` 模式：

| 项目 | 结果 | 含义 |
|---|---|---|
| Phase 1 | PASS | 冻结 6 项核心功能和 native-adaptive 模式 |
| Phase 2 | PASS | Android 静态分析、行为契约和部分运行证据完成 |
| Phase 3 | PASS | ArkUI 原生骨架可构建、安装和启动，页面路由完成冒烟 |
| Phase 4 | BLOCKED | 初始化阶段的 page-contract 输入不兼容 |
| 双端行为比较 | 未完成 | 尚无完整的 Android/HarmonyOS 六维结果 |
| Gate 4 | 未执行 | 不能形成最终一致性结论 |
| 最终 HAP | 未生成 | 当前没有本次验证对应的最终交付包 |

因此，P1～P3 PASS 只能说明前三段链路可以工作，不能证明 Cresto 已完成迁移，也不能证明绝大部分业务功能已经正确。

## 当前已知问题

### 1. Phase 4 的 GMI page-contract 不兼容（D-17，主要阻断）

GMI inventory 使用的正式 Page-ID、状态范围和运行证据结构，与旧 `compile_page_contracts` 所要求的静态页面事实空间不同。旧编译器要求：

- inventory Page-ID 必须精确存在于静态 `pages.json`；
- 静态扫描得到的全部状态必须拥有 inventory 证据；
- 证据必须采用旧目录结构；
- 所有 active 行必须存在旧格式 runtime observation。

这些条件与当前 GMI 产物不能直接对应，导致 Phase 4 无法初始化。需要为 `gmi + native-adaptive` 增加正式的 page-contract 编译路径，同时保持 strict 模式兼容。不能通过硬编码 Cresto 页面或补造证据绕过。

### 2. native-adaptive 比较脚本崩溃（D-1，已修复）

`compare_migration_unit.py` 曾在第 22 行导入中缺少 `comparison_result`（定义于 `comparison_common.py` 的工厂函数），导致 `compare_information_completeness` 等分支运行时必然产生 `NameError`。现已补全导入并验证：模块可导入、六维比较调用链恢复完整，修复方式与本地 2.1.1 演进版一致。

### 3. 六维比较尚未完全闭环（D-2）

现有比较链已经覆盖数据、状态、持久化和副作用等内容，但业务计算和可观察结果仍需要独立、确定性的双端比较。纯计算漂移不能继续被记录级 verdict 判为 PASS。

### 4. Phase 2 存在 fail-open 风险（D-4～D-6）

需要确保：

- `bc_id` 非空且全局唯一（已实现：`build_behavior_contracts.py` 对空 `bc_id` 与重复 `bc_id` 均 FAIL 并报错行号）；
- `RUNTIME_REQUIRED` 缺少真实运行证据时必须失败，不能只记录 warning；
- `audit-replay.csv` 缺失、不可读或为空时必须失败，不能被解释为零差异（已修复：`validate_gate.py` 在 runtime-gate 有记录而 audit-replay 缺失或为空时 fail-closed 报错，不再静默视为零差异）。

### 5. Gate 4 尚未严格消费行为验证（D-7）

Gate 4 必须读取正式 behavior-verification 结果，要求关键 Behavior Contract 分母非零、每条双端执行完成、所有必需维度 PASS，并由真实结果计算 `intent_pass_rate=100%`。缺少行为数据时不能默认 100%。

### 6. 高影响页面映射仍需回归确认（D-8）

旧实现对带 hash 的 Page-ID 和 Compose/Activity 符号归一化不稳定，可能导致高影响页面零命中。当前分支正在改为候选清单中的 Page-ID ↔ symbol 精确映射；正式验证仍需确认零命中和未解析引用会 fail closed。

## 当前开发原则

- 保持 strict 与 native-adaptive 两种模式隔离；
- 只在 `gmi + native-adaptive` 路径增加必要适配；
- 不把单次验证的 `.bridge` 或具体 Cresto 页面硬编码进正式 Skill；
- 不伪造 screenshot、runtime observation、persistence 或 side-effect 证据；
- 不通过降低 Gate 标准换取表面 PASS；
- UI 原生化只能改变表现方式，不能豁免行为差异；
- 旧 run 可以用于回归，但新版 Skill 的正式可用性必须由干净的新 run 证明。

## 安装

将四个 Skill 整体复制到目标项目：

```bash
git clone https://github.com/Ra1nyDayyy/android-harmony-skills-gmi-phase2-adaptation.git
cp -R android-harmony-skills-gmi-phase2-adaptation/.codeartsdoer/skills/* \
  /path/to/project/.codeartsdoer/skills/
```

示例入口指令：

```text
使用 $android-harmony-migration-controller 对当前 Android 项目执行 Phase 1–4。
采用 native-adaptive：HarmonyOS UI 使用 ArkUI 原生设计，但用户意图、数据、
业务计算、状态、结果、持久化和副作用必须保持语义等价。
Gate 通过后进入下一阶段；只有真实外部阻断时暂停，并完整列出阻断项。
```

## 何时可以宣布可用

至少需要一次干净的新 run 同时满足：

1. Phase 1～4 的正式 Gate 全部 PASS；
2. Phase 4 初始化和业务实现完成；
3. 所有 `RUNTIME_REQUIRED` 行为契约完成真实双端比较；
4. 业务计算、数据、状态、结果、持久化和副作用均无漂移；
5. 跨重启持久化验证通过；
6. Gate 4 确认非零分母且关键意图 100% PASS；
7. 最终 HAP 构建成功，并与本次输入锁、证据和报告绑定；
8. 注入任一维度的故意漂移时，Gate 能够稳定判定 FAIL。

在以上条件完成之前，本仓库应被描述为“正在验证的迁移 Skill 工作流”，而不是已经完成的自动迁移产品。
