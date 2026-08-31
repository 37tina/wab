export interface CodeArtsSession {
  id: string;
  title?: string;
  status?: string;
  directory?: string;
  agent?: string;
  mode?: string;
}

export interface CodeArtsConnection {
  connected: boolean;
  status: number;
  message: string;
  hint?: string;
  target?: string;
  service?: string;
  version?: string;
}

/** backend 网关 /api/agent/status 的返回：聚合端口发现与健康探测结果 */
export interface AgentStatus {
  target: string;
  source: "env" | "manual" | "discovered" | "default";
  reachable: boolean;
  healthy: boolean;
  status?: number;
  latencyMs?: number;
  error?: string;
  service?: string;
  version?: string;
  authMode?: "user" | "env" | "auto" | "none";
  discovered?: { port?: number; pid?: number; pidAlive?: boolean; version?: string };
  checkedAt: string;
}

export interface CodeArtsModel {
  providerID: string;
  modelID: string;
}

export interface CodeArtsPart {
  id?: string;
  type?: string;
  text?: string;
  synthetic?: boolean;
  [key: string]: unknown;
}

export interface CodeArtsMessage {
  info?: {
    id?: string;
    parentID?: string;
    role?: string;
    modelID?: string;
    providerID?: string;
    time?: { created?: number; completed?: number };
    error?: { name?: string; data?: { message?: string; statusCode?: number } };
    [key: string]: unknown;
  };
  parts?: CodeArtsPart[];
  [key: string]: unknown;
}

export interface CodeArtsRunResult {
  accepted: boolean;
  pending?: boolean;
  session?: CodeArtsSession;
  response?: unknown;
  message: string;
  messageId?: string;
}

/** deploy: VITE_API_BASE injects cloud backend URL; local dev keeps relative path via Vite bridge */
const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

const STORAGE_KEY = "tuotaihuangu_codearts_connection_v1";

export interface CodeArtsCredentials {
  username: string;
  password: string;
}

export function loadCodeArtsCredentials(): CodeArtsCredentials {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as CodeArtsCredentials;
  } catch {
    // Session storage can be unavailable in private browsing.
  }
  return { username: "codearts", password: "" };
}

export function saveCodeArtsCredentials(credentials: CodeArtsCredentials) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(credentials));
  } catch {
    // Keep credentials in memory when storage is unavailable.
  }
}

function authHeader(credentials: CodeArtsCredentials): Record<string, string> {
  if (!credentials.password) return {};
  return { Authorization: `Basic ${btoa(`${credentials.username}:${credentials.password}`)}` };
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

/** 统一从错误响应里提取人话。兼容：纯字符串、网关 502 的 {error, detail, hint}、
 * Agent 自身的 {message | error_msg | error.data.message} 形状。 */
export function formatApiError(data: unknown, fallback: string): string {
  if (typeof data === "string" && data.trim()) return data;
  if (data && typeof data === "object") {
    const value = data as Record<string, unknown>;
    const head = typeof value.error === "string" && value.error.trim() ? value.error : "";
    const detail = typeof value.detail === "string" && value.detail.trim() ? value.detail : "";
    if (detail) return head ? `${head}：${detail}` : detail;
    if (head) return head;
    const nested = value.error && typeof value.error === "object" ? value.error as Record<string, unknown> : undefined;
    const nestedData = nested?.data && typeof nested.data === "object" ? nested.data as Record<string, unknown> : undefined;
    for (const candidate of [value.message, value.error_msg, nestedData?.message, nested?.message]) {
      if (typeof candidate === "string" && candidate.trim()) return candidate;
    }
  }
  return fallback;
}

function errorHint(data: unknown): string | undefined {
  if (data && typeof data === "object" && typeof (data as Record<string, unknown>).hint === "string") {
    return (data as Record<string, unknown>).hint as string;
  }
  return undefined;
}

export async function checkCodeArts(credentials = loadCodeArtsCredentials()): Promise<CodeArtsConnection> {
  try {
    const response = await fetch(`${API_BASE}/api/codearts/global/health`, { headers: authHeader(credentials) });
    const data = await readJson(response);
    if (!response.ok) {
      if (response.status === 502) {
        // 网关转发失败：真实原因在 detail，target 是实际尝试的地址
        const value = data && typeof data === "object" ? data as Record<string, unknown> : {};
        return {
          connected: false,
          status: 502,
          message: formatApiError(data, "CodeArts Agent 服务不可达"),
          hint: errorHint(data),
          target: typeof value.target === "string" ? value.target : undefined,
        };
      }
      return {
        connected: false,
        status: response.status,
        message: response.status === 401 ? "CodeArts Agent 在线，但认证失败" : formatApiError(data, `CodeArts 返回 HTTP ${response.status}`),
      };
    }
    const value = data && typeof data === "object" ? data as Record<string, unknown> : {};
    return {
      connected: value.healthy !== false,
      status: response.status,
      message: value.healthy === false ? "CodeArts Agent 健康检查失败" : "CodeArts Agent 本地服务已连接",
      service: typeof value.service === "string" ? value.service : "CodeArts Agent",
      version: typeof value.version === "string" ? value.version : undefined,
    };
  } catch {
    return { connected: false, status: 0, message: "无法连接本地网关（backend 未运行？）" };
  }
}

export async function fetchAgentStatus(): Promise<AgentStatus | null> {
  try {
    const response = await fetch(`${API_BASE}/api/agent/status`);
    if (!response.ok) return null;
    const data = await readJson(response);
    return data && typeof data === "object" ? data as AgentStatus : null;
  } catch {
    return null;
  }
}

/** 保存手动地址覆盖（仅允许本机地址；传空字符串清除覆盖恢复自动发现） */
export async function updateAgentTarget(baseUrl: string): Promise<{ ok: boolean; error?: string }> {
  try {
    const response = await fetch(`${API_BASE}/api/agent/target`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ baseUrl }),
    });
    if (response.ok) return { ok: true };
    const data = await readJson(response);
    return { ok: false, error: formatApiError(data, `保存地址失败（HTTP ${response.status}）`) };
  } catch {
    return { ok: false, error: "无法连接本地网关（backend 未运行？）" };
  }
}

const WORKSPACE_DIR_KEY = "tuotaihuangu_test_workspace_v1";

/** 连接测试会话使用的工作区目录（非敏感，localStorage 持久化） */
export function loadTestWorkspaceDir(): string {
  try {
    return localStorage.getItem(WORKSPACE_DIR_KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveTestWorkspaceDir(dir: string) {
  try {
    localStorage.setItem(WORKSPACE_DIR_KEY, dir);
  } catch {
    // 忽略存储不可用的场景
  }
}

/** 让网关检查本机目录是否存在（新建任务时给用户即时反馈） */
export async function checkWorkspaceDir(dir: string): Promise<{ exists: boolean; isDirectory?: boolean } | null> {
  try {
    const response = await fetch(`${API_BASE}/api/agent/workspace?path=${encodeURIComponent(dir)}`);
    if (!response.ok) return null;
    const data = await readJson(response);
    return data && typeof data === "object" ? (data as { exists: boolean; isDirectory?: boolean }) : null;
  } catch {
    return null;
  }
}

/** Windows 本机绝对路径（盘符开头），用于工作区目录的前端格式校验 */
export function isAbsoluteWindowsPath(dir: string): boolean {
  return /^[a-zA-Z]:[\\/].+/.test(dir.trim());
}

/** 本机绝对路径：Windows 盘符路径或 POSIX 绝对路径（macOS/Linux，如 /Users/xxx） */
export function isAbsoluteLocalPath(dir: string): boolean {
  return isAbsoluteWindowsPath(dir) || /^\/.+/.test(dir.trim());
}

// ---- 模型管理 ----

/** CodeArts Space 登录态内置的模型（inferhub-provider 网关提供，不写入本地配置文件）。
 * ID 已通过真实推理验证（GLM-4.7-ArkTS-SPARK 的注册 ID 与显示名不一致，待确认）。 */
export const BUILTIN_PROVIDER_ID = "inferhub-provider";

export const BUILTIN_MODELS: Array<{ id: string; name: string; desc: string; verified: boolean }> = [
  { id: "GLM-5.2", name: "GLM-5.2", desc: "最新旗舰模型，专为长任务打磨", verified: true },
  { id: "openpangu-2.0-flash", name: "OpenPangu-2.0-Flash", desc: "均衡推理效果与性能", verified: true },
  { id: "GLM-4.7-ArkTS-SPARK", name: "GLM-4.7-ArkTS-SPARK", desc: "基于 GLM-4.7 训练鸿蒙代码与开发", verified: false },
  { id: "openpangu-2.0-pro", name: "OpenPangu-2.0-Pro", desc: "最新旗舰模型，专为长任务打磨（默认调度）", verified: true },
];

export interface AgentModelDef {
  modelID: string;
  modelName: string;
  modelDesc: string;
  modelType: string;
  displayEnabled: boolean;
  isCustomModel: boolean;
  contextWindow: number;
  outputContextWindow: number;
}

export interface AgentProviderInfo {
  providerID: string;
  name: string;
  npm: string;
  baseURL: string;
  apiKeyMasked: string;
  hasApiKey: boolean;
  models: AgentModelDef[];
  /** 内核运行时是否已注册该服务商（false = 配置存在但内核不认，显式指定会失败） */
  runtimeRegistered?: boolean;
}

export interface AgentModelInput {
  providerID: string;
  providerName: string;
  baseURL: string;
  apiKey: string;
  modelID: string;
  modelName: string;
  modelDesc: string;
  /** 自定义接口协议：决定服务商使用哪个 AI SDK 适配器 */
  apiFormat?: "openai" | "anthropic";
  contextWindow?: number;
  outputContextWindow?: number;
}

/** 读取客户端已有模型（来自 Agent 实时配置，apiKey 仅掩码） */
export async function fetchAgentModels(): Promise<AgentProviderInfo[] | null> {
  try {
    const response = await fetch(`${API_BASE}/api/agent/models`);
    if (!response.ok) return null;
    const data = await readJson(response);
    return data && typeof data === "object" ? (data as { providers: AgentProviderInfo[] }).providers : null;
  } catch {
    return null;
  }
}

/** 新增模型：写入客户端共用的 codearts.json，客户端同步可见 */
export async function addAgentModel(
  input: AgentModelInput,
): Promise<{ ok: boolean; error?: string; providers?: AgentProviderInfo[] }> {
  try {
    const response = await fetch(`${API_BASE}/api/agent/models`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (response.ok) {
      const data = await readJson(response);
      return { ok: true, providers: (data as { providers?: AgentProviderInfo[] })?.providers };
    }
    const data = await readJson(response);
    return { ok: false, error: formatApiError(data, `新增模型失败（HTTP ${response.status}）`) };
  } catch {
    return { ok: false, error: "无法连接本地网关（backend 未运行？）" };
  }
}

/** 删除网页新增的自定义模型（客户端内置模型不可删） */
export async function removeAgentModel(
  providerID: string,
  modelID: string,
): Promise<{ ok: boolean; error?: string; providers?: AgentProviderInfo[] }> {
  try {
    const response = await fetch(
      `${API_BASE}/api/agent/models/${encodeURIComponent(providerID)}/${encodeURIComponent(modelID)}`,
      { method: "DELETE" },
    );
    if (response.ok) {
      const data = await readJson(response);
      return { ok: true, providers: (data as { providers?: AgentProviderInfo[] })?.providers };
    }
    const data = await readJson(response);
    return { ok: false, error: formatApiError(data, `删除模型失败（HTTP ${response.status}）`) };
  } catch {
    return { ok: false, error: "无法连接本地网关（backend 未运行？）" };
  }
}

// ---- AgentTeam 团队状态（内核 /cag/agent-team/* 路由） ----

export interface AgentTeamMember {
  sessionID: string;
  parentSessionID?: string;
  modelInfo?: { providerID: string; modelID: string };
  agent_type: string;
  description?: string;
  agent_name: string;
  status: string;
  startedAt?: string;
  lastUpdated?: string;
}

export interface AgentTeamTask {
  id: number;
  content: string;
  status: string;
  owner?: string;
  owner_name?: string;
  publisher?: string;
  publisher_name?: string;
  blocked_by?: number[];
}

export interface AgentTeamState {
  sessionId: string;
  tasks: AgentTeamTask[];
  members: Record<string, AgentTeamMember>;
}

/** 读取某会话的 AgentTeam 团队状态（任务清单 + 花名册） */
export async function fetchTeamState(sessionId: string): Promise<AgentTeamState | null> {
  try {
    const response = await fetch(`${API_BASE}/api/agent/team/${encodeURIComponent(sessionId)}`);
    if (!response.ok) return null;
    const data = await readJson(response);
    return data && typeof data === "object" ? (data as AgentTeamState) : null;
  } catch {
    return null;
  }
}

/** 把模型列表压平成下拉选项（providerID + modelID 复合值） */export function flattenModelOptions(providers: AgentProviderInfo[]): Array<{ value: string; label: string }> {
  const options: Array<{ value: string; label: string }> = [
    { value: "", label: "跟随客户端默认（OpenPangu-2.0-Pro）" },
  ];
  for (const model of BUILTIN_MODELS) {
    if (model.id === "openpangu-2.0-pro") continue; // 与默认项重复，仅保留默认项
    options.push({
      value: `${BUILTIN_PROVIDER_ID}::${model.id}`,
      label: `内置 · ${model.name}${model.verified ? "" : "（ID 待验证）"}`,
    });
  }
  for (const provider of providers) {
    // 未注册进内核运行时的自定义服务商不可用（prompt 显式指定会 500），直接过滤
    if (provider.runtimeRegistered === false) continue;
    for (const model of provider.models) {
      if (!model.displayEnabled) continue;
      options.push({
        value: `${provider.providerID}::${model.modelID}`,
        label: `${model.modelName}（${provider.name}）`,
      });
    }
  }
  return options;
}

const RUN_MODEL_KEY = "tuotaihuangu_run_model_v1";

/** AgentTeam 执行时使用的模型（providerID::modelID 复合值，空 = 跟随客户端默认） */
export function loadRunModel(): string {
  try {
    return localStorage.getItem(RUN_MODEL_KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveRunModel(value: string) {
  try {
    localStorage.setItem(RUN_MODEL_KEY, value);
  } catch {
    // 忽略存储不可用的场景
  }
}

export function parseRunModel(value: string): CodeArtsModel | undefined {
  const index = value.indexOf("::");
  if (index <= 0 || index === value.length - 2) return undefined;
  return { providerID: value.slice(0, index), modelID: value.slice(index + 2) };
}

export async function createCodeArtsSession(
  title: string,
  credentials = loadCodeArtsCredentials(),
  options: { directory?: string } = {},
): Promise<CodeArtsRunResult> {
  try {
    // AgentKernel 的目录是 URL 查询参数（放在请求体里会被忽略）；必须用正斜杠，
    // 单反斜杠的 "D:\目录" 会被当作相对路径拼到 Agent 默认目录后面。
    const query = options.directory?.trim()
      ? `?directory=${encodeURIComponent(options.directory.trim().replace(/\\/g, "/"))}`
      : "";
    const response = await fetch(`${API_BASE}/api/codearts/session${query}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader(credentials) },
      body: JSON.stringify({ title }),
    });
    const data = await readJson(response);
    if (!response.ok) return { accepted: false, message: formatApiError(data, `创建 CodeArts 会话失败（HTTP ${response.status}）`) };
    const session = data as CodeArtsSession;
    if (!session?.id) return { accepted: false, message: "CodeArts 未返回会话 ID" };
    return { accepted: true, session, response: data, message: "CodeArts 会话已创建" };
  } catch {
    return { accepted: false, message: "CodeArts Agent 服务不可达" };
  }
}

function requestId() {
  const uuid = globalThis.crypto?.randomUUID?.();
  return uuid ? `msg_web_${uuid}` : `msg_web_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

/** Submit a real, asynchronous AgentKernel prompt. The endpoint returns 204;
 * the assistant answer is delivered through session messages/events. */
export async function promptCodeArtsSession(
  sessionId: string,
  prompt: string,
  credentials = loadCodeArtsCredentials(),
  options: { model?: CodeArtsModel; agent?: string; mode?: "agent-team" | "single-agent" } = {},
): Promise<CodeArtsRunResult> {
  const messageId = requestId();
  try {
    const response = await fetch(`${API_BASE}/api/codearts/session/${encodeURIComponent(sessionId)}/prompt_async`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader(credentials) },
      body: JSON.stringify({
        messageID: messageId,
        agent: options.agent ?? "team-leader",
        mode: options.mode ?? "agent-team",
        ...(options.model ? { model: options.model } : {}),
        parts: [{ type: "text", text: prompt }],
      }),
    });
    const data = await readJson(response);
    if (!response.ok) return { accepted: false, message: formatApiError(data, `CodeArts 推理提交失败（HTTP ${response.status}）`), messageId };
    return { accepted: true, pending: true, response: data, message: "已提交 CodeArts Agent 异步推理", messageId };
  } catch {
    return { accepted: false, message: "CodeArts 推理请求不可达", messageId };
  }
}

export async function getCodeArtsMessages(
  sessionId: string,
  credentials = loadCodeArtsCredentials(),
): Promise<CodeArtsMessage[]> {
  const response = await fetch(`${API_BASE}/api/codearts/session/${encodeURIComponent(sessionId)}/message?limit=100`, {
    headers: authHeader(credentials),
  });
  const data = await readJson(response);
  if (!response.ok) throw new Error(formatApiError(data, `读取 CodeArts 会话失败（HTTP ${response.status}）`));
  return Array.isArray(data) ? data as CodeArtsMessage[] : [];
}

function assistantText(message: CodeArtsMessage): string {
  return (message.parts ?? [])
    .filter((part) => part.type === "text" && !part.synthetic && typeof part.text === "string")
    .map((part) => part.text as string)
    .join("\n")
    .trim();
}

function assistantError(message: CodeArtsMessage): string | undefined {
  const error = message.info?.error;
  if (!error) return undefined;
  return error.data?.message || error.name || "CodeArts Agent 推理失败";
}

const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms));

/** Poll the real session until an assistant message is completed. This is a
 * fallback-friendly equivalent of subscribing to /global/event and works in
 * browsers without custom SSE authorization headers. */
export async function waitForCodeArtsResult(
  sessionId: string,
  messageId: string | undefined,
  credentials = loadCodeArtsCredentials(),
  options: { timeoutMs?: number; pollMs?: number; onUpdate?: (message: CodeArtsMessage) => void } = {},
): Promise<CodeArtsRunResult> {
  const timeoutMs = options.timeoutMs ?? 90_000;
  const pollMs = options.pollMs ?? 1_200;
  const started = Date.now();
  try {
    while (Date.now() - started < timeoutMs) {
      const messages = await getCodeArtsMessages(sessionId, credentials);
      messages.filter((item) => item.info?.role === "assistant").forEach((item) => options.onUpdate?.(item));
      // leader 多步执行时每步都会产生 assistant 短回复，只有按契约输出 WAITING_HUMAN_REVIEW
      // 的最终汇总（或显式错误）才算阶段完成，否则继续等待后台执行。
      const assistant = [...messages].reverse().find((item) => {
        if (item.info?.role !== "assistant") return false;
        if (messageId && item.info?.parentID && item.info.parentID !== messageId) return false;
        if (assistantError(item)) return true;
        return assistantText(item).toUpperCase().includes("WAITING_HUMAN_REVIEW");
      });
      if (assistant) {
        const failure = assistantError(assistant);
        if (failure) return { accepted: false, response: assistant, message: `CodeArts 推理失败：${failure}`, messageId };
        const text = assistantText(assistant);
        return { accepted: true, response: text || assistant, message: "CodeArts Agent 已完成真实推理", messageId };
      }
      await sleep(pollMs);
    }
    return { accepted: false, pending: true, message: "CodeArts 推理仍在后台运行，已超过页面等待时间", messageId };
  } catch (error) {
    return { accepted: false, message: error instanceof Error ? error.message : "读取 CodeArts 推理结果失败", messageId };
  }
}

// ---- Skill 治理（提案 → 人工审核 → 落盘） ----

export interface SkillFileEntry { path: string; size: number }
export interface SkillProposal {
  id: string;
  path: string;
  author: string;
  reason: string;
  status: "pending" | "approved" | "rejected";
  createdAt: string;
  decidedAt?: string | null;
  reviewerComment?: string;
  originalLines: number;
  newLines: number;
  backupFile?: string;
}

export async function fetchSkillTree(): Promise<Array<{ skill: string; files: SkillFileEntry[] }> | null> {
  try {
    const response = await fetch(`${API_BASE}/api/skill/tree`);
    if (!response.ok) return null;
    return ((await readJson(response)) as { skills: Array<{ skill: string; files: SkillFileEntry[] }> }).skills;
  } catch {
    return null;
  }
}

export async function fetchSkillFile(path: string): Promise<string | null> {
  try {
    const response = await fetch(`${API_BASE}/api/skill/file?path=${encodeURIComponent(path)}`);
    if (!response.ok) return null;
    return ((await readJson(response)) as { content: string }).content;
  } catch {
    return null;
  }
}

export async function fetchSkillProposals(): Promise<SkillProposal[] | null> {
  try {
    const response = await fetch(`${API_BASE}/api/skill/proposals`);
    if (!response.ok) return null;
    return ((await readJson(response)) as { proposals: SkillProposal[] }).proposals;
  } catch {
    return null;
  }
}

export async function createSkillProposal(input: { path: string; newContent: string; reason: string; author?: string }): Promise<{ ok: boolean; error?: string }> {
  try {
    const response = await fetch(`${API_BASE}/api/skill/proposals`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (response.ok) return { ok: true };
    return { ok: false, error: formatApiError(await readJson(response), "提交提案失败") };
  } catch {
    return { ok: false, error: "无法连接本地网关（backend 未运行？）" };
  }
}

export async function decideSkillProposal(id: string, decision: "approved" | "rejected", comment = ""): Promise<{ ok: boolean; error?: string }> {
  try {
    const response = await fetch(`${API_BASE}/api/skill/proposals/${encodeURIComponent(id)}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, comment }),
    });
    if (response.ok) return { ok: true };
    return { ok: false, error: formatApiError(await readJson(response), "审核操作失败") };
  } catch {
    return { ok: false, error: "无法连接本地网关（backend 未运行？）" };
  }
}

/** 会话变更统计（additions/deletions/files），用于阶段页「交付与变更」 */
export async function fetchSessionSummary(sessionId: string): Promise<{ additions: number; deletions: number; files: number } | null> {
  try {
    const response = await fetch(`${API_BASE}/api/codearts/session`);
    if (!response.ok) return null;
    const list = (await readJson(response)) as Array<{ id: string; summary?: { additions?: number; deletions?: number; files?: number } }>;
    const found = Array.isArray(list) ? list.find((item) => item.id === sessionId) : undefined;
    return found?.summary ? { additions: found.summary.additions ?? 0, deletions: found.summary.deletions ?? 0, files: found.summary.files ?? 0 } : null;
  } catch {
    return null;
  }
}
