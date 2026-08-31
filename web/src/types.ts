export type PhaseNumber = 1 | 2 | 3 | 4;

export type PhaseStatus =
  | "pending"
  | "running"
  | "review_required"
  | "approved"
  | "changes_requested"
  | "completed";

export type AgentEventType = "thinking" | "tool" | "build" | "test" | "system";

export interface Feature {
  id: string;
  name: string;
  description: string;
  status: "covered" | "partial" | "risk";
  androidResult: string;
  harmonyResult: string;
}

export interface Artifact {
  id: string;
  name: string;
  kind: "analysis" | "trace" | "code" | "report" | "screenshot" | "build";
  description: string;
  size: string;
  status: "ready" | "generating" | "review";
}

export interface AgentEvent {
  id: string;
  agent: string;
  type: AgentEventType;
  message: string;
  timestamp: string;
}

export interface Review {
  decision: "approved" | "changes_requested";
  comment: string;
  reviewedAt: string;
  reviewer: string;
}

export interface EmulatorFrame {
  id: string;
  title: string;
  subtitle: string;
  accent: string;
  detail: string;
  metric?: string;
}

export interface EmulatorStream {
  platform: "android" | "harmony";
  status: "offline" | "live" | "replay";
  frames: EmulatorFrame[];
  currentFrame: number;
  currentStep: string;
  streamType: "mock" | "webrtc" | "mjpeg" | "video";
}

export interface Phase {
  number: PhaseNumber;
  code: string;
  title: string;
  shortTitle: string;
  description: string;
  status: PhaseStatus;
  progress: number;
  revision: number;
  events: AgentEvent[];
  artifacts: Artifact[];
  review?: Review;
  paused?: boolean;
  emulator?: EmulatorStream;
  execution?: PhaseExecution;
}

export interface PhaseExecution {
  mode: "demo" | "codearts-agentteam";
  status: "idle" | "starting" | "running" | "succeeded" | "failed";
  sessionId?: string;
  agent?: string;
  startedAt?: string;
  completedAt?: string;
  response?: string;
  error?: string;
}

export type SourcePlatform = "android" | "windows" | "legacy-desktop";
export type TargetPlatform = "harmony-phone" | "harmony-pc" | "vehicle";

export interface Project {
  id: string;
  name: string;
  source: {
    type: "github" | "zip";
    value: string;
  };
  status: "running" | "review" | "completed";
  currentPhase: PhaseNumber;
  createdAt: string;
  updatedAt: string;
  demo: boolean;
  executionMode?: "demo" | "codearts-agentteam";
  /** CodeArts Agent 的工作区目录；真实执行会话在该目录中检出源码与构建 */
  workspaceDir?: string;
  sourcePlatform?: SourcePlatform;
  /** AgentTeam 主会话：四阶段工单连续发往同一对话 */
  activeSessionId?: string;
  /** 本项目 AgentTeam 执行模型（providerID::modelID，空=跟随全局默认） */
  runModel?: string;
  targetPlatform?: TargetPlatform;
  features: Feature[];
  phases: Phase[];
}


export interface ProjectInput {
  name: string;
  sourceType: "github" | "zip";
  sourceValue: string;
  executionMode?: "demo" | "codearts-agentteam";
  workspaceDir?: string;
  sourcePlatform?: SourcePlatform;
  targetPlatform?: TargetPlatform;
  runModel?: string;
}

export interface MigrationService {
  listProjects(): Project[];
  getProject(id: string): Project | undefined;
  createProject(input: ProjectInput): Project;
  startPhase(id: string, phase: PhaseNumber): void;
  pausePhase(id: string, phase: PhaseNumber): void;
  resumePhase(id: string, phase: PhaseNumber): void;
  restartPhase(id: string, phase: PhaseNumber): void;
  skipPhase(id: string, phase: PhaseNumber): void;
  reviewPhase(id: string, phase: PhaseNumber, review: Review): void;
  resetDemo(id: string): void;
  recordCodeArtsExecution?(id: string, phase: PhaseNumber, execution: PhaseExecution): void;
  recordCodeArtsEvent?(id: string, phase: PhaseNumber, event: Omit<AgentEvent, "id" | "timestamp">): void;
  bindActiveSession?(id: string, sessionId: string): void;
  deleteProject(id: string): void;
  subscribe(id: string, callback: (project: Project) => void): () => void;
  subscribeAll(callback: (projects: Project[]) => void): () => void;
}
