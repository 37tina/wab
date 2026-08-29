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
  service?: string;
  version?: string;
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

function errorMessage(data: unknown, fallback: string): string {
  if (typeof data === "string" && data.trim()) return data;
  if (data && typeof data === "object") {
    const value = data as Record<string, unknown>;
    const nested = value.error && typeof value.error === "object" ? value.error as Record<string, unknown> : undefined;
    const nestedData = nested?.data && typeof nested.data === "object" ? nested.data as Record<string, unknown> : undefined;
    for (const candidate of [value.message, value.error_msg, nestedData?.message, nested?.message]) {
      if (typeof candidate === "string" && candidate.trim()) return candidate;
    }
  }
  return fallback;
}

export async function checkCodeArts(credentials = loadCodeArtsCredentials()): Promise<CodeArtsConnection> {
  try {
    const response = await fetch("/api/codearts/global/health", { headers: authHeader(credentials) });
    const data = await readJson(response);
    if (!response.ok) {
      return {
        connected: false,
        status: response.status,
        message: response.status === 401 ? "CodeArts Agent 在线，但认证失败" : `CodeArts 返回 HTTP ${response.status}`,
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
    return { connected: false, status: 0, message: "未找到本地 CodeArts Agent 服务，请先启动 Agent" };
  }
}

export async function createCodeArtsSession(
  title: string,
  credentials = loadCodeArtsCredentials(),
  options: { directory?: string } = {},
): Promise<CodeArtsRunResult> {
  try {
    const response = await fetch("/api/codearts/session", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader(credentials) },
      body: JSON.stringify({ title, ...(options.directory ? { directory: options.directory } : {}) }),
    });
    const data = await readJson(response);
    if (!response.ok) return { accepted: false, message: errorMessage(data, `创建 CodeArts 会话失败（HTTP ${response.status}）`) };
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
    const response = await fetch(`/api/codearts/session/${encodeURIComponent(sessionId)}/prompt_async`, {
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
    if (!response.ok) return { accepted: false, message: errorMessage(data, `CodeArts 推理提交失败（HTTP ${response.status}）`), messageId };
    return { accepted: true, pending: true, response: data, message: "已提交 CodeArts Agent 异步推理", messageId };
  } catch {
    return { accepted: false, message: "CodeArts 推理请求不可达", messageId };
  }
}

export async function getCodeArtsMessages(
  sessionId: string,
  credentials = loadCodeArtsCredentials(),
): Promise<CodeArtsMessage[]> {
  const response = await fetch(`/api/codearts/session/${encodeURIComponent(sessionId)}/message?limit=100`, {
    headers: authHeader(credentials),
  });
  const data = await readJson(response);
  if (!response.ok) throw new Error(errorMessage(data, `读取 CodeArts 会话失败（HTTP ${response.status}）`));
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
      const assistant = [...messages].reverse().find((item) => {
        if (item.info?.role !== "assistant") return false;
        if (messageId && item.info?.parentID && item.info.parentID !== messageId) return false;
        return Boolean(assistantText(item) || assistantError(item) || item.info?.time?.completed);
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
