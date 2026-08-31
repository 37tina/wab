import type {
  AgentEvent,
  Artifact,
  EmulatorFrame,
  EmulatorStream,
  Feature,
  MigrationService,
  Phase,
  PhaseExecution,
  PhaseNumber,
  Project,
  ProjectInput,
  Review
} from "./types";

const STORAGE_KEY = "tuotaihuangu_projects_v1";

const phaseDefinitions: Array<Pick<Phase, "number" | "code" | "title" | "shortTitle" | "description">> = [
  { number: 1, code: "01", title: "迁移基线建立", shortTitle: "基线建立", description: "明确迁什么、迁到哪、什么算迁移成功，冻结源码与验收标准" },
  { number: 2, code: "02", title: "源软件深度理解", shortTitle: "深度理解", description: "功能语义地图、行为契约与真机行为基线" },
  { number: 3, code: "03", title: "目标平台原生迁移", shortTitle: "原生迁移", description: "受控原生化：保留原应用辨识度，交互映射鸿蒙原生组件" },
  { number: 4, code: "04", title: "一致性验证与自动修复", shortTitle: "差分修复", description: "双端差分重放，DIFF 自动定位修复至 MATCH" }
];

const features: Feature[] = [
  { id: "f1", name: "项目总览", description: "查看任务指标与迁移状态", status: "covered", androidResult: "已验证", harmonyResult: "已验证" },
  { id: "f2", name: "图片导入", description: "导入质检图片并生成任务", status: "covered", androidResult: "已验证", harmonyResult: "已验证" },
  { id: "f3", name: "缺陷检测", description: "调用视觉模型并展示缺陷结果", status: "partial", androidResult: "已验证", harmonyResult: "字段待复核" },
  { id: "f4", name: "结果详情", description: "查看缺陷位置和检测结论", status: "covered", androidResult: "已验证", harmonyResult: "已验证" },
  { id: "f5", name: "历史记录", description: "查询历史质检任务", status: "covered", androidResult: "已验证", harmonyResult: "已验证" },
  { id: "f6", name: "异常处理", description: "处理空图片和服务异常", status: "risk", androidResult: "已记录", harmonyResult: "待验证" }
];

const androidFrames: EmulatorFrame[] = [
  { id: "android-home", title: "质检工作台", subtitle: "今日任务 12 个", accent: "#39d2a8", detail: "选择图片开始一次新的质检任务", metric: "12" },
  { id: "android-import", title: "导入质检图片", subtitle: "支持 JPG / PNG", accent: "#7c8cff", detail: "正在读取生产线样本_0428.png" },
  { id: "android-running", title: "AI 缺陷检测", subtitle: "模型推理中 · 68%", accent: "#ffb454", detail: "正在扫描图像中的边缘与表面纹理", metric: "68%" },
  { id: "android-result", title: "检测完成", subtitle: "发现 2 个疑似缺陷", accent: "#ff7b82", detail: "缺陷类型：划痕、边缘缺口", metric: "02" },
  { id: "android-history", title: "历史记录", subtitle: "最近 7 天", accent: "#39d2a8", detail: "任务 #QC-0428 已归档" }
];

const harmonyFrames: EmulatorFrame[] = [
  { id: "harmony-home", title: "质检工作台", subtitle: "HarmonyOS · 运行中", accent: "#61e8c0", detail: "迁移后的 ArkUI 首页已启动", metric: "READY" },
  { id: "harmony-import", title: "导入质检图片", subtitle: "选择本地样本", accent: "#9a9cff", detail: "正在加载生产线样本_0428.png" },
  { id: "harmony-running", title: "AI 缺陷检测", subtitle: "语义步骤 03 / 05", accent: "#ffc568", detail: "检测服务已返回候选区域", metric: "RUN" },
  { id: "harmony-result", title: "检测完成", subtitle: "发现 2 个疑似缺陷", accent: "#ff8990", detail: "结果与 Android 基线一致", metric: "PASS" },
  { id: "harmony-history", title: "历史记录", subtitle: "跨端结果已同步", accent: "#61e8c0", detail: "任务 #QC-0428 已归档" }
];

const eventTemplates: Record<PhaseNumber, Array<{ agent: string; type: AgentEvent["type"]; message: string }>> = {
  1: [
    { agent: "Team Leader", type: "thinking", message: "接收迁移目标，拆分源项目语义分析任务" },
    { agent: "语义分析 Agent", type: "tool", message: "建立 Codebase 索引：扫描 86 个源文件" },
    { agent: "架构分析 Agent", type: "thinking", message: "识别 6 项业务功能和 3 个高风险依赖" },
    { agent: "测试规划 Agent", type: "test", message: "生成 5 条跨平台语义测试契约" },
    { agent: "Team Leader", type: "system", message: "语义图、风险清单和迁移计划已生成" }
  ],
  2: [
    { agent: "Android Agent", type: "build", message: "执行 Gradle assembleDebug，构建基线 APK" },
    { agent: "Runner", type: "system", message: "Android 模拟器 Pixel 7 API 34 已连接" },
    { agent: "测试 Agent", type: "test", message: "执行用例 TC-IMPORT-001：导入图片" },
    { agent: "测试 Agent", type: "test", message: "执行用例 TC-DETECT-002：完成缺陷检测" },
    { agent: "取证 Agent", type: "tool", message: "保存 5 个步骤截图、UI 树和 logcat" },
    { agent: "Team Leader", type: "system", message: "Android 行为基线已固化，等待人工审核" }
  ],
  3: [
    { agent: "Harmony 架构 Agent", type: "thinking", message: "加载迁移规范，规划 ArkUI 页面和状态模型" },
    { agent: "UI 迁移 Agent", type: "tool", message: "生成 EntryAbility 与 5 个 ArkUI 页面" },
    { agent: "API 迁移 Agent", type: "tool", message: "映射 12 个 Android API 至 HarmonyOS 等价能力" },
    { agent: "Build Agent", type: "build", message: "执行 hvigor assembleHap，首次编译发现 2 个问题" },
    { agent: "Repair Agent", type: "tool", message: "修复资源路径和检测结果字段映射" },
    { agent: "Build Agent", type: "build", message: "HAP 构建成功，生成迁移文件映射" }
  ],
  4: [
    { agent: "Harmony Runner", type: "system", message: "HarmonyOS 模拟器 API 12 已连接" },
    { agent: "一致性 Agent", type: "test", message: "开始回放 5 条跨平台语义测试契约" },
    { agent: "一致性 Agent", type: "tool", message: "对比导航、文本、业务输出和副作用" },
    { agent: "诊断 Agent", type: "thinking", message: "发现 1 个字段命名差异，定位至 DetectionService.ets" },
    { agent: "Repair Agent", type: "tool", message: "应用字段映射补丁并重跑受影响用例" },
    { agent: "Team Leader", type: "system", message: "一致性验证完成，综合得分 94 / 100" }
  ]
};

function now() {
  return new Date().toISOString();
}

function makeArtifact(id: string, name: string, kind: Artifact["kind"], description: string, size: string, status: Artifact["status"] = "ready"): Artifact {
  return { id, name, kind, description, size, status };
}

function emulator(platform: "android" | "harmony", status: EmulatorStream["status"] = "live"): EmulatorStream {
  return {
    platform,
    status,
    frames: platform === "android" ? androidFrames : harmonyFrames,
    currentFrame: 0,
    currentStep: platform === "android" ? "等待开始" : "等待鸿蒙验证",
    streamType: "mock"
  };
}

function phase(number: PhaseNumber, status: Phase["status"] = "pending"): Phase {
  const definition = phaseDefinitions[number - 1];
  const artifacts: Artifact[] = number === 1
    ? [makeArtifact("a-feature", "feature-graph.json", "analysis", "功能语义图与依赖关系", "18 KB"), makeArtifact("a-plan", "migration-plan.md", "analysis", "迁移边界和风险清单", "12 KB")]
    : number === 2
      ? [makeArtifact("a-trace", "android-baseline.jsonl", "trace", "Android 端执行轨迹", "246 KB"), makeArtifact("a-android-shots", "android-screenshots.zip", "screenshot", "5 个步骤截图", "1.8 MB")]
      : number === 3
        ? [makeArtifact("a-harmony", "harmony-project.zip", "code", "完整 HarmonyOS 工程", "4.2 MB", "review"), makeArtifact("a-diff", "migration-diff.patch", "code", "迁移变更和修复补丁", "86 KB"), makeArtifact("a-build", "hvigor-build.log", "build", "鸿蒙构建日志", "31 KB")]
        : [makeArtifact("a-report", "consistency-report.json", "report", "跨平台一致性判定结果", "28 KB"), makeArtifact("a-pair", "comparison-screenshots.zip", "screenshot", "Android/Harmony 对照截图", "2.1 MB")];
  return {
    number,
    code: definition.code,
    title: definition.title,
    shortTitle: definition.shortTitle,
    description: definition.description,
    status,
    progress: status === "approved" || status === "completed" ? 100 : 0,
    revision: 1,
    events: [],
    artifacts,
    execution: { mode: "demo", status: "idle" },
    emulator: number === 2 ? emulator("android", "offline") : number === 4 ? emulator("harmony", "offline") : undefined
  };
}

function baseProject(input: ProjectInput, demo = false): Project {
  const createdAt = now();
  const phases = [phase(1), phase(2), phase(3), phase(4)];
  return {
    id: demo ? "demo-qc-001" : `migration-${Date.now()}`,
    name: input.name,
    source: { type: input.sourceType, value: input.sourceValue },
    status: "running",
    currentPhase: 1,
    createdAt,
    updatedAt: createdAt,
    demo,
    executionMode: input.executionMode ?? "demo",
    workspaceDir: input.workspaceDir,
    runModel: input.runModel,
    sourcePlatform: input.sourcePlatform,
    targetPlatform: input.targetPlatform,
    features: features.map((item) => ({ ...item })),
    phases
  };
}

function makeDemoProject(): Project {
  const project = baseProject({ name: "机器视觉质检助手迁移演示", sourceType: "github", sourceValue: "github.com/open-source/quality-inspector" }, true);
  project.status = "completed";
  project.currentPhase = 4;
  project.phases = project.phases.map((item) => ({
    ...item,
    status: "approved",
    progress: 100,
    events: eventTemplates[item.number].map((event, index) => ({ ...event, id: `demo-${item.number}-${index}`, timestamp: `2026-08-27T14:${20 + item.number}:${String(index * 7).padStart(2, "0")}.000Z` })),
    emulator: item.number === 2 ? emulator("android", "replay") : item.number === 4 ? emulator("harmony", "replay") : item.emulator
  }));
  project.phases[3].review = { decision: "approved", comment: "核心功能与视觉结果已完成复核。", reviewer: "演示审核员", reviewedAt: "2026-08-27T14:42:00.000Z" };
  return project;
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export class MockMigrationServiceImpl implements MigrationService {
  private projects: Project[];
  private timers = new Map<string, ReturnType<typeof setTimeout>>();
  private listeners = new Map<string, Set<(project: Project) => void>>();
  private allListeners = new Set<(projects: Project[]) => void>();

  constructor() {
    const raw = localStorage.getItem(STORAGE_KEY);
    this.projects = raw ? (JSON.parse(raw) as Project[]) : [makeDemoProject()];
    if (!this.projects.length) this.projects = [makeDemoProject()];
    this.projects.forEach((project) => {
      const active = project.phases.find((item) => item.status === "running");
      if (active) {
        active.status = "review_required";
        active.progress = 100;
        active.events.push({ id: `${active.number}-recovered`, agent: "系统", type: "system", message: "页面刷新后恢复演示状态，请审核本阶段结果", timestamp: now() });
      }
    });
    this.persist();
  }

  listProjects() { return clone(this.projects).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)); }
  getProject(id: string) { const item = this.projects.find((project) => project.id === id); return item ? clone(item) : undefined; }

  createProject(input: ProjectInput) {
    const project = baseProject(input);
    this.projects = [project, ...this.projects.filter((item) => !item.demo)];
    this.persist();
    this.emit(project);
    this.startPhase(project.id, 1);
    return clone(project);
  }

  startPhase(id: string, number: PhaseNumber) {
    const project = this.projects.find((item) => item.id === id);
    const target = project?.phases.find((item) => item.number === number);
    if (!project || !target || this.timers.has(`${id}-${number}`)) return;
    target.status = "running";
    const isReal = project.executionMode === "codearts-agentteam" && !project.demo;
    target.execution = { mode: isReal ? "codearts-agentteam" : "demo", status: isReal ? "starting" : "running", startedAt: now() };
    target.paused = false;
    target.progress = 0;
    target.review = undefined;
    if (number === 2 && target.emulator) target.emulator = { ...target.emulator, status: isReal ? "offline" : "live", currentStep: isReal ? "等待真实 Android Runner 接入" : "启动 Android 模拟器" };
    if (number === 4 && target.emulator) target.emulator = { ...target.emulator, status: isReal ? "offline" : "live", currentStep: isReal ? "等待真实 HarmonyOS Runner 接入" : "启动 HarmonyOS 模拟器" };
    project.status = "running";
    project.currentPhase = number;
    project.updatedAt = now();
    target.events = [{ id: `${number}-start-${Date.now()}`, agent: isReal ? "CodeArts AgentTeam" : "Team Leader", type: "system", message: isReal ? `已请求 CodeArts Space / AgentTeam 执行 Phase ${number}` : `开始执行 Phase ${number}`, timestamp: now() }];
    this.persist();
    this.emit(project);
    if (!isReal) this.schedule(id, number, 0);
  }

  recordCodeArtsExecution(id: string, number: PhaseNumber, execution: PhaseExecution) {
    const project = this.projects.find((item) => item.id === id);
    const target = project?.phases.find((item) => item.number === number);
    if (!project || !target) return;
    target.execution = { ...target.execution, ...execution, mode: "codearts-agentteam", response: execution.response?.slice(0, 20000) };
    if (execution.sessionId) {
      target.events.push({ id: `${number}-codearts-${Date.now()}`, agent: execution.agent ?? "CodeArts AgentTeam", type: execution.status === "failed" ? "system" : "thinking", message: execution.status === "succeeded" ? "CodeArts AgentTeam 已返回真实推理结果" : execution.error ? `CodeArts AgentTeam 执行失败：${execution.error}` : `CodeArts AgentTeam 会话 ${execution.sessionId} 已启动`, timestamp: now() });
    }
    if (execution.status === "succeeded" && execution.response?.trim()) {
      const preview = execution.response.replace(/\s+/g, " ").slice(0, 240);
      target.events.push({ id: `${number}-codearts-result-${Date.now()}`, agent: "CodeArts AgentTeam", type: "tool", message: `真实会话结果：${preview}${execution.response.length > 240 ? "…" : ""}`, timestamp: now() });
    }
    if (execution.status === "succeeded") {
      target.status = "review_required";
      target.progress = 100;
      project.status = "review";
      if (target.emulator && target.execution?.mode === "demo") target.emulator.status = "replay";
    } else if (execution.status === "failed") {
      target.status = "running";
      project.status = "running";
    }
    project.updatedAt = now();
    this.persist();
    this.emit(project);
  }

  recordCodeArtsEvent(id: string, number: PhaseNumber, event: Omit<AgentEvent, "id" | "timestamp">) {
    const project = this.projects.find((item) => item.id === id);
    const target = project?.phases.find((item) => item.number === number);
    if (!project || !target) return;
    target.events.push({ ...event, id: `${number}-codearts-event-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, timestamp: now() });
    project.updatedAt = now();
    this.persist();
    this.emit(project);
  }

  private schedule(id: string, number: PhaseNumber, index: number) {
    const key = `${id}-${number}`;
    const timer = setTimeout(() => {
      this.timers.delete(key);
      const project = this.projects.find((item) => item.id === id);
      const target = project?.phases.find((item) => item.number === number);
      const templates = eventTemplates[number];
      if (!project || !target) return;
      if (target.paused) return;
      if (index < templates.length) {
        const template = templates[index];
        target.events.push({ ...template, id: `${number}-${Date.now()}-${index}`, timestamp: now() });
        target.progress = Math.round(((index + 1) / templates.length) * 100);
        if (target.emulator) {
          target.emulator.currentFrame = Math.min(index, target.emulator.frames.length - 1);
          target.emulator.currentStep = template.message;
        }
        project.updatedAt = now();
        this.persist();
        this.emit(project);
        this.schedule(id, number, index + 1);
      } else {
        target.status = "review_required";
        target.progress = 100;
        if (target.emulator) target.emulator.status = "replay";
        project.status = "review";
        project.updatedAt = now();
        target.events.push({ id: `${number}-review-${Date.now()}`, agent: "系统", type: "system", message: "阶段执行完成，等待人工审核", timestamp: now() });
        this.persist();
        this.emit(project);
      }
    }, 850);
    this.timers.set(key, timer);
  }

  pausePhase(id: string, number: PhaseNumber) {
    const target = this.projects.find((item) => item.id === id)?.phases.find((item) => item.number === number);
    if (!target || target.status !== "running") return;
    target.paused = true;
    target.events.push({ id: `${number}-pause-${Date.now()}`, agent: "系统", type: "system", message: "演示已暂停", timestamp: now() });
    this.persist();
    this.emitById(id);
  }

  resumePhase(id: string, number: PhaseNumber) {
    const project = this.projects.find((item) => item.id === id);
    const target = project?.phases.find((item) => item.number === number);
    if (!project || !target || target.status !== "running" || !target.paused) return;
    target.paused = false;
    target.events.push({ id: `${number}-resume-${Date.now()}`, agent: "系统", type: "system", message: "演示已继续", timestamp: now() });
    this.persist();
    this.emit(project);
    const completed = eventTemplates[number].filter((template) => target.events.some((event) => event.message === template.message)).length;
    this.schedule(id, number, completed);
  }

  restartPhase(id: string, number: PhaseNumber) {
    const key = `${id}-${number}`;
    const timer = this.timers.get(key);
    if (timer) clearTimeout(timer);
    this.timers.delete(key);
    const target = this.projects.find((item) => item.id === id)?.phases.find((item) => item.number === number);
    if (!target) return;
    target.revision += 1;
    target.events = [];
    target.progress = 0;
    this.startPhase(id, number);
  }

  skipPhase(id: string, number: PhaseNumber) {
    const key = `${id}-${number}`;
    const timer = this.timers.get(key);
    if (timer) clearTimeout(timer);
    this.timers.delete(key);
    const project = this.projects.find((item) => item.id === id);
    const target = project?.phases.find((item) => item.number === number);
    if (!project || !target) return;
    target.events = eventTemplates[number].map((event, index) => ({ ...event, id: `${number}-skip-${index}`, timestamp: now() }));
    target.progress = 100;
    target.status = "review_required";
    if (target.emulator) target.emulator.status = "replay";
    project.status = "review";
    this.persist();
    this.emit(project);
  }

  reviewPhase(id: string, number: PhaseNumber, review: Review) {
    const project = this.projects.find((item) => item.id === id);
    const target = project?.phases.find((item) => item.number === number);
    if (!project || !target) return;
    target.review = review;
    target.events.push({ id: `${number}-reviewed-${Date.now()}`, agent: review.reviewer, type: "system", message: review.decision === "approved" ? "人工审核通过" : `提出修改意见：${review.comment || "请继续完善本阶段"}`, timestamp: now() });
    if (review.decision === "changes_requested") {
      target.status = "changes_requested";
      target.revision += 1;
      project.status = "running";
      this.persist();
      this.emit(project);
      setTimeout(() => this.startPhase(id, number), 600);
      return;
    }
    target.status = number === 4 ? "completed" : "approved";
    if (number < 4) {
      const next = project.phases.find((item) => item.number === (number + 1) as PhaseNumber);
      if (next) next.status = "pending";
      project.currentPhase = (number + 1) as PhaseNumber;
      project.status = "running";
    } else {
      project.status = "completed";
    }
    this.persist();
    this.emit(project);
    if (number < 4) setTimeout(() => this.startPhase(id, (number + 1) as PhaseNumber), 600);
  }

  resetDemo(id: string) {
    const index = this.projects.findIndex((item) => item.id === id);
    if (index < 0) return;
    const demo = makeDemoProject();
    demo.status = "running";
    demo.currentPhase = 1;
    demo.phases = demo.phases.map((item, itemIndex) => ({ ...item, status: itemIndex === 0 ? "pending" : "pending", progress: 0, events: [], review: undefined, emulator: item.number === 2 ? emulator("android", "offline") : item.number === 4 ? emulator("harmony", "offline") : undefined }));
    this.projects[index] = demo;
    this.persist();
    this.emit(demo);
    this.startPhase(id, 1);
  }

  bindActiveSession(id: string, sessionId: string) {
    const project = this.projects.find((item) => item.id === id);
    if (!project) return;
    project.activeSessionId = sessionId;
    this.persist();
    this.emit(project);
  }

  deleteProject(id: string) {
    this.projects = this.projects.filter((item) => item.id !== id);
    this.persist();
  }

  subscribe(id: string, callback: (project: Project) => void) {
    const set = this.listeners.get(id) ?? new Set();
    set.add(callback);
    this.listeners.set(id, set);
    return () => { set.delete(callback); };
  }

  subscribeAll(callback: (projects: Project[]) => void) {
    this.allListeners.add(callback);
    return () => { this.allListeners.delete(callback); };
  }

  private persist() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(this.projects));
    const snapshot = this.listProjects();
    this.allListeners.forEach((callback) => callback(snapshot));
  }

  private emit(project: Project) {
    const snapshot = clone(project);
    this.listeners.get(project.id)?.forEach((callback) => callback(snapshot));
  }

  private emitById(id: string) {
    const project = this.projects.find((item) => item.id === id);
    if (project) this.emit(project);
  }
}

export const mockService: MigrationService = new MockMigrationServiceImpl();
