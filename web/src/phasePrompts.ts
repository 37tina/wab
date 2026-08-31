// 四阶段执行提示词：完整导入 skill-snapshot 的工作流。
// 提示词不复述 skill 内容（避免转述失真），而是要求 AgentTeam 先用 read 工具读取完整 skill
// 文档与关键 reference，再按其定义的流程执行；环境信息由本文件注入。

export const SKILL_ROOT = "D:/2026挑战杯待定网站/skill-snapshot/governance-tree";

export interface PhasePromptContext {
  projectName: string;
  sourceValue: string;
  sourcePlatformLabel: string;
  workspaceDir: string;
}

const ENVIRONMENT = [
  "## 本机环境（已验证可用，禁止声称“无运行环境”）",
  "- Android SDK：D:\\Android\\Sdk（adb、emulator、build-tools、platforms 齐全）",
  "- adb：D:\\Android\\Sdk\\platform-tools\\adb.exe（模拟器 serial 以 `adb devices -l` 实际输出为准）",
  "- Android 模拟器 AVD：CrestoP2A、CrestoP2B、TodoAPI36、TodoAPI36-slotB（emulator.exe 在 D:\\Android\\Sdk\\emulator）",
  "- Android CLI：`android --version` = 1.0.159（运行时取证必须用它 + adb，见 android-cli-procedure.md）",
  "- Python：3.12（skill scripts 可直接运行，脚本目录见下方各阶段）",
  "- DevEco Studio（含 JBR，可作 JDK17 用于 Gradle 构建）：D:\\DevEco Studio",
  "- 每次 RUNTIME 取证前必须 `adb devices -l` 确认设备、`dumpsys activity activities` 绑定前台包；分辨率/密度用 `wm size`/`wm density` 记录并冻结",
].join("\n");

const TEAM_RULES = [
  "## 执行方式（AgentTeam）",
  "1. 先调用 get-team-setup 获取团队搭建流程并招募成员；",
  "2. publish-task 建立任务清单，background-task 派发 team-mate 并行执行（模型 write 大文件会超时——产物一律直接在回复文本输出，不要写文件）；",
  "3. 每个成员的真实产出（命令、输出、结论）必须可追溯，禁止虚构；无环境才可降级并显式记 GAP（本机环境见上，先检查再下结论）；",
  "4. 完成后在回复文本输出结构化汇总，等待人工审核（WAITING_HUMAN_REVIEW），模型不得自我放行。",
].join("\n");

export function phasePrompt(number: 1 | 2 | 3 | 4, ctx: PhasePromptContext): string {
  const base = [
    `你是脱胎换骨迁移系统的迁移控制器（Controller），现在执行项目「${ctx.projectName}」的 Phase ${number}。`,
    `源项目：${ctx.sourceValue}（${ctx.sourcePlatformLabel}）；工作区目录：${ctx.workspaceDir}（源码若未检出则检出到此目录下）。`,
    "",
    "## 第一步：读取完整 Skill（禁止凭记忆执行）",
    "先用 read 工具完整阅读以下文档，严格按其流程执行，不要自行发挥或跳步：",
  ];
  const reading: Record<number, string[]> = {
    1: [
      `${SKILL_ROOT}/android-harmony-migration-controller/SKILL.md`,
      `${SKILL_ROOT}/android-harmony-migration-controller/references/controller-contract.md`,
      `${SKILL_ROOT}/android-harmony-migration-controller/references/phase-gates.md`,
    ],
    2: [
      `${SKILL_ROOT}/android-migration-inventory/SKILL.md`,
      `${SKILL_ROOT}/android-migration-inventory/references/inventory-contract.md`,
      `${SKILL_ROOT}/android-migration-inventory/references/android-cli-procedure.md`,
      `${SKILL_ROOT}/android-migration-inventory/references/environment-contract.md`,
    ],
    3: [
      `${SKILL_ROOT}/harmonyos-migration-scaffold/SKILL.md`,
      `${SKILL_ROOT}/harmonyos-migration-scaffold/references/roles-and-authority.md`,
    ],
    4: [
      `${SKILL_ROOT}/harmonyos-feature-implementation/SKILL.md`,
      `${SKILL_ROOT}/harmonyos-feature-implementation/references/implementation-guidelines-v4.md`,
    ],
  };
  const duty: Record<number, string> = {
    1: "按 Controller skill 的 Inputs 与 Phase 1 要求冻结：功能范围（included/excluded）、数据范围、关键业务能力、允许的平台替换、源码 revision 与 APK、双端环境与工具策略、验收标准（等价契约具体化）。产出 scope 冻结清单与 Gate 1 自检要点。",
    2: "按 Inventory skill 的九步流程执行：静态分类 → 功能语义地图（file:line 锚点）→ 行为契约六要素 → RUNTIME/SOURCE_CONFIRM 分级 → 用 Android CLI + adb + 模拟器对 RUNTIME 功能真实跑行为链（操作日志 + 断言判定 + 关键截图引用）→ 源码↔运行对账四态 → 汇总。运行环境必须先检查再使用，不许未检查就降级。",
    3: "按 Scaffold skill 的五步流程执行：消费 Phase 2 功能地图 → 分面搭壳（page→路由 / dialog·sheet→模态挂载宿主 / container·reusable 不建壳）→ UI 蓝图（android_structure/preserve/native_carrier/native_component 四字段）→ 数据契约（interface-only）→ 构建/安装/启动冒烟结论与 Gate 3 自检。",
    4: "按 Implementation skill 的 v5 双机差分范式执行：按功能实现（原生优先规约）→ 双机差分（Android 为 oracle，四类结果 observable/semantic data/persistence/side effect，比结果不比路径）→ DIFF 只修 Harmony 并重验（≤2 轮转人工）→ Surface/UI 检查 → Gate 4 自检。",
  };
  return [...base, ...reading[number].map((p) => `- ${p}`), "", "## 本阶段职责", duty[number], "", ENVIRONMENT, "", TEAM_RULES].join("\n");
}
