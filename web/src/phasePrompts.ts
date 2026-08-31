// 四阶段执行提示词（2026-08-31 定稿版）：完整导入 skill 工作流，含 Agent 分工与关键铁律。
// 提示词不复述 skill 内容（避免转述失真），要求 AgentTeam 先用 read 工具读完整 skill 文档
// 与 Reference map 再按其流程执行；项目相关值（名称/源/工作区）由表单运行时注入。

// skill 根目录：由后端 /api/env 注入（App 启动时 setSkillRoot）；默认取 import.meta 相对定位失败时的空串并在工单生成时报警
let SKILL_ROOT = "";
export function setSkillRoot(root: string) { if (root) SKILL_ROOT = root; }
export function getSkillRoot() { return SKILL_ROOT; }

/** 迁移路径套件路由：(source, target) → skill 套件目录（薄壳 4 文件 + _shared 内核） */
const SUITE_ROUTES: Record<string, { dir: string; form: string; sourceInventory?: string }> = {
  "ios>harmony-phone": { dir: "ios-to-harmony-phone", form: "phone", sourceInventory: "inventory-ios.md" },
  "macos>harmony-pc": { dir: "mac-to-harmony-pc", form: "pc", sourceInventory: "inventory-macos.md" },
  "web>harmony": { dir: "web-to-harmony", form: "phone" },
  "windows>harmony-pc": { dir: "windows-to-harmony-pc", form: "pc" },
  "android>harmony-tablet": { dir: "tablet-to-harmony-tablet", form: "tablet" },
  "android>harmony-watch": { dir: "watch-to-harmony-watch", form: "watch" },
  "legacy>automotive": { dir: "legacy-to-automotive", form: "automotive" },
};

const PHASE_READINGS: Record<number, { shell: string; cores: string[] }> = {
  1: { shell: "controller.md", cores: ["controller-core.md"] },
  2: { shell: "inventory.md", cores: ["inventory-core.md"] },
  3: { shell: "scaffold.md", cores: ["scaffold-core-{form}.md"] },
  4: { shell: "implementation.md", cores: ["verify-core.md"] },
};

/** 非 android-phone 路径的通用工单（薄壳体系：skill 是流程主体，工单只做路由与纪律绑定） */
function suitePrompt(phase: 1 | 2 | 3 | 4, ctx: PhasePromptContext, route: { dir: string; form: string; sourceInventory?: string }): string {
  const reading = PHASE_READINGS[phase];
  const cores = reading.cores.map((c) => c.replace("{form}", route.form));
  const files = [
    `${SKILL_ROOT}/_shared/00-CONVENTIONS.md`,
    `${SKILL_ROOT}/${route.dir}/${reading.shell}`,
    ...cores.map((c) => `${SKILL_ROOT}/_shared/${c}`),
    ...(phase === 2 && route.sourceInventory ? [`${SKILL_ROOT}/_shared/${route.sourceInventory}`] : []),
  ];
  const duty: Record<number, string> = {
    1: "冻结迁移基线：按 controller 内核产出 scope 冻结件（功能范围/迁移政策/test_seed/双端环境/输入指纹/验收标准），Gate 1 自检后输出冻结完成报告。",
    2: "源端深度理解：按 inventory 内核九步产出功能语义地图、行为契约（六要素+强断言）、分级验证与运行取证（源端取证可用性以薄壳差异节为准，不可用按其降级策略记 GAP）、对账四态与数据关系，Gate 2 自检后输出盘点报告。",
    3: "目标端承载：按 scaffold 内核分面搭壳（page/sheet·dialog/container 三规则）+ UI 蓝图四字段 + interface-only 数据契约 + 真实构建/安装/启动冒烟（命令按 CONVENTIONS 双平台表），Gate 3 自检后输出骨架报告。",
    4: "实现与双端差分：按 verify 内核逐功能实现（原生优先）→ 双端执行同一行为考卷 → 四维机器判分 → DIFF 只修目标端（≤2 轮转人工）→ Gate 4 自检，输出终局汇总（含四维结果与待人工裁决项）。",
  };
  const lines = [
    `你是脱胎换骨迁移系统的迁移控制器（Controller），现在执行项目「${ctx.projectName}」的 Phase ${phase}（${ctx.sourcePlatformLabel} → 鸿蒙目标端）。`,
    `源项目：${ctx.sourceValue}（${ctx.sourcePlatformLabel}）；工作区目录：${ctx.workspaceDir}/<RUN-ID>（本次 run 的全部产物落此目录，<RUN-ID> 由本次 run 生成并全程沿用）。`,
    "",
    "## 第一步：读取完整 Skill（禁止凭记忆执行）",
    "先用 read 工具完整阅读以下文档（顺序即依赖顺序），严格按其流程执行，不要自行发挥或跳步：",
  ];
  for (const f of files) lines.push(`- ${f}`);
  lines.push(
    "",
    "## 本阶段职责",
    duty[phase],
    "",
    "## 执行纪律（controller-core 铁律，任何路径不变）",
    "- 产物全部由真实脚本/命令生成并如实留痕；禁止手工拼装、禁止编造输出、禁止用演示数据冒充运行结果",
    "- 证据不可变：旧产物只取代不修改；GAP 必须显式（feature_id + 原因码），禁止静默吞掉",
    "- 无法执行的环境按薄壳降级策略处理并记 TOOL_GAP/GAP；模型/机器不得自我放行，完成后输出终局汇总并进入 WAITING_HUMAN_REVIEW",
    "- 工具链路径以 CONVENTIONS 的 Mac/Windows 双平台表为准，本机实际位置先实测再写入环境冻结",
    "",
    "## 本机环境（macOS）",
    "- DevEco/hvigor/hdc：/Applications/DevEco-Studio.app/（详见 CONVENTIONS 双平台表与薄壳环境节）",
    "- 源端工具链可用性以开工实测为准（不可用如实记 TOOL_ABSENCE 并按薄壳降级策略处理）",
  );
  return lines.join("\n");
}

export interface PhasePromptContext {
  projectName: string;
  sourceValue: string;
  sourcePlatformLabel: string;
  workspaceDir: string;
  /** 目标端（默认 harmony-phone 保持向后兼容）；与 sourcePlatformLabel 组成路由键 */
  targetPlatform?: string;
}

/** 本机环境（四阶段共享，逐字注入每个工单） */
const ENVIRONMENT = [
  "## 本机环境",
  "- Android 模拟器：emulator-5554（adb 可用，源 App 已安装；applicationId/versionCode/versionName 以 Phase 1 实测身份三元组为准，与 scope 声明一致才继续）",
  "- 鸿蒙模拟器：127.0.0.1:5557（hdc=/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc；DevEco 6.1.1；hvigor 可用）",
  `- Skill 树：${SKILL_ROOT}/（本 run 冻结基准；改任何 skill 文件后仅在 INIT/CLOSED 态可 --refresh-freeze）`,
].join("\n");

/** 执行方式（四阶段共享，逐字注入每个工单） */
const EXECUTION_RULES = [
  "## 执行方式",
  "- 产物全部由真实脚本生成（init_migration.py / validate_gate.py），禁止手工拼装 JSON/CSV",
  "- 逐条如实记录命令与产物；遇到 Skill 断点按 TOOL_GAP 纪律处置并写入 decision-log",
  "- 严禁读取任何人工参考实现（如 ~/Desktop/ 下的 *-manual-reference/ 目录）",
].join("\n");

function header(phase: 1 | 2 | 3 | 4, ctx: PhasePromptContext): string {
  return [
    `你是脱胎换骨迁移系统的迁移控制器（Controller），现在执行项目「${ctx.projectName}」的 Phase ${phase}。`,
    `源项目：${ctx.sourceValue}（${ctx.sourcePlatformLabel}，git 锁定）；工作区目录：${ctx.workspaceDir}/<RUN-ID>（本次 run 的全部产物落此目录，<RUN-ID> 由本次 run 生成并全程沿用）。`,
  ].join("\n");
}

const READ_FIRST = "## 第一步：读取完整 Skill（禁止凭记忆执行）\n先用 read 工具完整阅读以下文档，严格按其流程执行，不要自行发挥或跳步：";

const READING: Record<number, string[]> = {
  1: [
    `${SKILL_ROOT}/android-harmony-migration-controller/SKILL.md`,
    `SKILL.md 的 Reference map 中列出的全部 references 文档（读完再动手）`,
  ],
  2: [
    `${SKILL_ROOT}/android-migration-inventory/SKILL.md`,
    `SKILL.md Reference map 列出的全部 references`,
  ],
  3: [
    `${SKILL_ROOT}/harmonyos-migration-scaffold/SKILL.md`,
    `${SKILL_ROOT}/harmonyos-migration-scaffold/references/roles-and-authority.md`,
    `${SKILL_ROOT}/arkui-next-reference/14-android-to-harmony-map.md（安卓→鸿蒙原生对照表，组件选型必查）`,
  ],
  4: [
    `${SKILL_ROOT}/harmonyos-feature-implementation/SKILL.md`,
    `${SKILL_ROOT}/harmonyos-feature-implementation/references/implementation-guidelines-v4.md（原生优先规约）`,
    `${SKILL_ROOT}/arkui-next-reference/14-android-to-harmony-map.md`,
  ],
};

const DUTY_1 = [
  "## 本阶段职责（Controller Agent，单 Agent，全程只做冻结与裁决）",
  "按 Controller skill 流程执行：",
  "- 源码与 APK 冻结：git commit 锁定；基线 APK 身份三元组实测（applicationId/versionCode/versionName），与 scope 声明一致才继续",
  "- 功能范围冻结：included_features 逐条列出（每条含 verify_mode：RUNTIME / SOURCE_CONFIRM）；排除项显式列出并写理由（decision-log）",
  "- 冻结三条迁移政策（写入 scope，Phase 3/4 的 Gate 都会消费）：",
  "  - FUNCTIONAL_EQUIVALENCE = HARD——数据/业务计算/状态变化/持久化/副作用不许漂移",
  "  - UI_FIDELITY = HIGH——页面信息架构/内容/关键控件/图标/视觉层级/关键颜色必须保留",
  "  - NATIVE_ADAPTATION = CONSTRAINED——仅 Navigation/Tabs/返回/Sheet/Dialog/Toggle/Picker/系统菜单/权限交互允许平台化替换",
  "- seed 冻结：按源项目实际初始状态冻结（初始语言/初始主题/预置数据与条数/排序方式等，以实测为准；Phase 2 与 Phase 4 必须测同一起点，写进 scope 的 test_seed 段）",
  "- 环境冻结：Android 模拟器 emulator-5554 与鸿蒙模拟器 127.0.0.1:5557 的实测参数（分辨率 1080×2400 / API / 密度）入档",
  "- 输入锁：源码树哈希冻结",
  "- 签发 Phase 2 工单（run 状态 INIT → IN_MIGRATION；此后 Skill/Gate/validator 全部冻结，发现 Skill 缺陷走 TOOL_GAP：能绕过且不影响事实则继续，否则终止 run → 修 Skill → 新开 run，禁止运行中改规则）",
  "",
  "禁止：看 UI / 写业务代码 / 修改 validator / 自己补事实。",
  "",
  "Gate 1 放行条件：冻结件齐备且一致（0 error 0 warning）。",
].join("\n");

const DUTY_2 = [
  "## 本阶段职责：产出「功能语义地图 + 高风险行为标准答案」",
  "Phase 2 内部拆为两个 Agent，职责硬隔离，先后接力：",
  "",
  "### Agent 2A：Android Semantic Analyst（只看源码，禁止碰模拟器）",
  "- surface 分类：page / sheet / dialog / container / reusable-component（先分类防误判：容器与普通 Compose 函数绝不冒充页面；带接收者函数如 fun BoxScope.X() 必须识别）",
  "- feature-map：以用户功能为中心（非页面）。每功能：feature_id / 名称 / 一句话语义 / surfaces[]（含 is_container）/ data_objects / verify_mode / source_refs（file:line 全可解析；绑定用显式映射，禁止子串匹配兜底）",
  "- 行为契约（BC 十字段硬门槛）：user_intent / pre_state / semantic_input / operation_steps / data_state_change / observable_result / persistence_targets / external_side_effects（无则写 NONE）/ result_assertions / source_refs——RUNTIME_REQUIRED 任一为空 → INVALID_CONTRACT → --validate 退出非零；断言 JSON 里出现 optional:true → 同样 INVALID_CONTRACT（P2 侧断言一律 required，豁免只属于 P4 重放侧）；每条 result_assertions 至少一条强断言（如 text_visible=当天、data_equals(prefs.sort_option, 3) 级别）",
  "- data-relations：功能↔语义对象↔读写方向↔Android 参考持久化",
  "- visual-memory：每 surface 基准截图引用 + ui-tree 摘要（组件序列/可见文本集/content-desc/关键 bounds）+ 全局色板 + fidelity 三态（源码显式值 / INHERITED[theme 继承] / 缺失——显式必须记录，INHERITED 合法，字段缺失才 FAIL）",
  "- 交接物给 2B：behavior-contracts.csv（含完整 operation_steps + result_assertions）+ feature-map + data-relations。",
  "",
  "### Agent 2B：Android Runtime Oracle（只碰真机，禁止改期望值）",
  "对每条 RUNTIME 链执行：",
  "  冷复位（force-stop + start）→ prepare → verify precondition（pre_state token 校验；失败重试一次 → 仍失败 = PRECONDITION_FAILED，归 GAP 不算功能错）",
  "  → 按 android_steps 真机执行",
  "  → 三时点采集：before / after / restart",
  "     UI：screenshot + ui.xml（锚点文本）",
  "     data：android_data_probe 真实读取（MMKV 二进制解析含覆盖语义 / shared_prefs XML / Room SQLite 三件套；DataStore → TOOL_GAP 显式标注，禁止伪造）",
  "  → 断言判定 → force-stop 重启 → persistence 断言再判",
  "",
  "判定铁律：只有 CONFIRMED / CONFLICT / GAP 三态。degraded PASS 已废除——无断言=INVALID_CONTRACT；required 断言任一 UNSUPPORTED=UNSUPPORTED_ORACLE（归 GAP，绝不 PASS）；链间必须冷复位（上一链遗留状态不得泄漏到下一链）。",
  "",
  "### Gate 2 放行条件（五条）",
  "①所有 included feature 有 feature-map ②每 feature ≥1 条 BC ③RUNTIME_REQUIRED 字段与断言全部完整（INVALID_CONTRACT / UNSUPPORTED_ORACLE → error）④CONFLICT 一律 error（解释不能翻转——必须重新采集或重新理解源码归 CONFIRMED；high-impact GAP 进 warnings 供人工复审）⑤visual-memory 与 data-relations 在案。",
  "",
  "补充：2A 与 2B 可并行启动（2A 先做分类与 feature-map，2B 等 BC 齐备后上真机）；两人产物分别落 phase-02-android-inventory/ 的正式产物位。",
].join("\n");

const DUTY_3 = [
  "## 本阶段职责（单 Agent：Harmony Native Architect）",
  "按 Scaffold skill 的流程执行：消费 Phase 2 功能地图 → 分面搭壳（page→路由 / dialog·sheet→模态挂载宿主 / container·reusable 不建壳）→ UI 蓝图（android_structure / preserve / native_carrier / native_component 四字段）→ 数据契约（interface-only + required_operations + DebugSemanticProbe 探针本体）→ 主题层（AppTheme 从 visual-memory 色板派生，含明暗双资源）→ 构建/安装/启动冒烟结论与 Gate 3 自检。",
  "",
  "细化要求：",
  "- UI 蓝图三字段是 Gate 3 硬门槛：每个用户可见 surface（routes+modals）必须有非空 preserve（UI_FIDELITY=HIGH 的机械表达：文本/图标/列表项/操作入口/关键配色清单）+ native_component（对照表映射，如三Tab主页→Navigation+NavPathStack+Tabs(barPosition=End)+List+LazyForEach）+ native_carrier——缺任一 Gate 3 FAIL，旧产物同样 FAIL 无豁免；custom_allowed 默认 no，自定义须登记 reason",
  "- 数据契约：每语义对象含 required_operations（create/update/setCompleted/delete/restore/list…，从 BC 行为动词推导）；同时生成 DebugSemanticProbe（读真实 Repository/Preferences/RelationalStore 的探针本体，哈希锁定，P4 禁改——这是 P4 数据验证不自答的基础）",
  "- 构建冒烟必须真实：hvigor 构建（工程路径含非 ASCII 时用 /tmp ASCII 副本）→ hdc 安装到 5557 → aa 启动，命令行证据落档",
  "",
  "禁止：实现 Todo CRUD / 写假 Repository / 塞 placeholder 业务结果 / 自造 Android 风格导航组件",
  "",
  "Gate 3 放行条件（四条）：①所有重要 surface 有承载且蓝图三字段齐 ②所有数据对象有 contract（无孤儿）③标准交互都有 native mapping ④build/install/launch PASS。",
].join("\n");

const DUTY_4 = [
  "## 本阶段职责：逐 Feature 小闭环（一个功能完成才做下一个）",
  "流程固化顺序：实现(3) → 双机差分(4) → 有 DIFF 走修复回环(7) → 回(4)（≤2 轮，超限转人工）→ 全 MATCH → Surface/UI 检查(5) → Gate 4(6)。",
  "",
  "### Agent 4A：Feature Implementer（写实现）",
  "每个 Feature 的固定动作：",
  "- 先读题（工单强制 + 回执核验）：读 Feature BC / Android source_refs（打开 Android 源码对应文件行）/ Android runtime evidence / P3 surface-plan / data-contract——完成时在 implementation-declarations.csv 交 consumed_bc_ids / consumed_source_refs / consumed_runtime_refs 回执。没读 Android 源码的功能不许验收（Gate 4 第 6 条机械核验，且必须是工单子集——防编造）",
  "- 原生优先实现：Navigation/Tabs/List+LazyForEach/bindSheet/CustomDialog/Toggle/Picker 官方组件优先；自定义须 surface-contract notes 登记理由（R1-R6 静态扫描：手搓底栏/自绘导航栈/自造弹层底盘/自绘Switch/自造Picker/自造返回 → FAIL）",
  "- 数据走真库：实现经 P3 data-contract + SemanticProbeRegistry.registerProbe 接线（探针本体禁改，哈希锁定）——数据验证读真实存储，不是实现方自报",
  "- UI 高还原：照 visual-memory 做（内容/结构/视觉三重还原；色板/布局/文本/图标对齐）；全部用户可见 surface 进 visual-fidelity 验收（不像素级死复刻，平台标准交互原生化）",
  "- 如实记录 harmony_steps（复测的操作依据）",
  "- V2 状态管理注意：bindSheet 等 UI 绑定用 @Local boolean 直绑（嵌套 @Trace 属性不响应——历史上栽过的坑）；跨组件路径栈用模块级单例（V1 @Provide 与 V2 @Consumer 跨版本不配对）",
  "- 收到 DIFF 修复单（rework-orders.csv）→ 只修 Harmony（Android 是 oracle）→ 修复后交 4B 复测",
  "",
  "禁止：改 P2 / 改 Oracle / 改 replayer / 改 Gate / 改 Skill / 自己宣布 PASS。",
  "",
  "### Agent 4B：Independent Verifier（零业务代码，只验证）",
  "双机行为差分验证（dual_verify.py）：",
  "  两侧恢复同一语义前置状态（任一侧 precondition 未建立 → 四类 MANUAL 归人工队列，不算 DIFF）",
  "  → Android 按 android_steps 执行（live oracle cache：APK/seed/BC 不变则命中不重跑；仅 Oracle 可疑才 --refresh-oracle 强制重采）",
  "  → Harmony 按 harmony_steps 执行（复用 replayer 链：冷复位/prepare/前置校验/探针数据）",
  "  → 机器直接 A/B 四类结果：",
  "     observable（锚点可见性对比——比较结果不比较路径，不做 UI 像素 A/B）",
  "     semantic data（语义对象真值对比——独立探针读取，防自答）",
  "     persistence（两侧重启后互相确认）",
  "     side effect（通知/日历/文件副作用等价；无公开 API 侧 MANUAL）",
  "  → DIFF 即 FAIL（例：Android 切英文 locale=en vs Harmony locale=zh → DIFF）",
  "  → dual-diff-results.csv（MATCH/DIFF/MANUAL，Gate 4 兼容输入）",
  "",
  "修复回环：DIFF → rework-orders.csv 聚合（feature/bc/断言类别/两侧实测值）→ 4A 修 Harmony → --rework-round 1/2 只重跑 DIFF 的 BC（Android 走 cache）→ 轮次记 attempt-ledger（只追加）→ 硬上限 2 轮：round 2 仍 DIFF → MANUAL_TAKEOVER 转人工。退出码 0=收敛 / 1=待修 / 2=错误或转人工。",
  "",
  "SOURCE_CONFIRM 功能（无真机重放）：四门槛——实现存在 / 无 no-op·placeholder（静态扫描）/ 源码可追溯 / 可构建。",
  "",
  "### Gate 4 放行条件（六条，只做最终判定）",
  "①所有 RUNTIME BC 断言全 PASS（含 dual-diff 消费：任一 DIFF → FAIL）②数据/状态/业务计算/持久化无差异 ③SOURCE_CONFIRM 四门槛 ④Surface 的 content/structure/native check PASS（UI 四重验收，不像素 A/B）⑤环境链 + build/full regression PASS ⑥must_read 回执核验（无 consumed_source_refs 不得验收）。",
  "",
  "补充：4A 与 4B 串行接力（4A 实现一个 Feature → 4B 差分 → DIFF 回 4A → 循环至 MATCH → 下一个 Feature）；修复回环全程机器留痕（attempt-ledger 哈希链）。",
].join("\n");

const DUTY: Record<number, string> = { 1: DUTY_1, 2: DUTY_2, 3: DUTY_3, 4: DUTY_4 };

export function phasePrompt(number: 1 | 2 | 3 | 4, ctx: PhasePromptContext): string {
  const target = (ctx.targetPlatform ?? "harmony-phone").toLowerCase();
  const SOURCE_KEYS: Record<string, string> = {
    "android app": "android", "ios app": "ios", "web 应用": "web", "windows 桌面软件": "windows",
    "macos 应用": "macos", "android 平板应用": "android", "android wear 应用": "android", "遗留系统": "legacy",
  };
  const sourceKey = SOURCE_KEYS[ctx.sourcePlatformLabel.toLowerCase()] ?? (ctx.sourcePlatformLabel.toLowerCase().includes("android") ? "android" : ctx.sourcePlatformLabel.toLowerCase().split(/\s|\(|-/)[0]);
  const matched = SUITE_ROUTES[`${sourceKey}>${target}`];
  if (matched) return suitePrompt(number, ctx, matched);
  return [
    header(number, ctx),
    "",
    READ_FIRST,
    ...READING[number].map((line) => `- ${line}`),
    "",
    DUTY[number],
    "",
    ENVIRONMENT,
    "",
    EXECUTION_RULES,
  ].join("\n");
}
