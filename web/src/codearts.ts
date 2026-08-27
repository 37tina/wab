export interface CodeArtsSession {
  id: string;
  title?: string;
  status?: string;
}

export interface CodeArtsConnection {
  connected: boolean;
  status: number;
  message: string;
  service?: string;
  version?: string;
}

export interface CodeArtsRunResult {
  accepted: boolean;
  session?: CodeArtsSession;
  response?: unknown;
  message: string;
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

async function readJson(response: Response): Promise<Record<string, unknown> | undefined> {
  try {
    const value = await response.json();
    return value && typeof value === "object" ? value as Record<string, unknown> : undefined;
  } catch {
    return undefined;
  }
}

export async function checkCodeArts(credentials = loadCodeArtsCredentials()): Promise<CodeArtsConnection> {
  try {
    const response = await fetch("/api/codearts/global/health", {
      headers: { ...authHeader(credentials) },
    });
    const data = await readJson(response);
    if (!response.ok) {
      return {
        connected: false,
        status: response.status,
        message: response.status === 401 ? "CodeArts 服务在线，但认证失败" : `CodeArts 返回 HTTP ${response.status}`,
      };
    }
    return {
      connected: true,
      status: response.status,
      message: "CodeArts Agent 服务已连接",
      service: typeof data?.service === "string" ? data.service : "CodeArts Agent",
      version: typeof data?.version === "string" ? data.version : undefined,
    };
  } catch {
    return {
      connected: false,
      status: 0,
      message: "未找到本地 CodeArts Agent 服务（请先启动 Agent）",
    };
  }
}

export async function createCodeArtsSession(
  title: string,
  credentials = loadCodeArtsCredentials(),
): Promise<CodeArtsRunResult> {
  try {
    const response = await fetch("/api/codearts/session", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader(credentials) },
      body: JSON.stringify({ title }),
    });
    const data = await readJson(response);
    if (!response.ok) {
      return { accepted: false, message: response.status === 401 ? "CodeArts 认证失败" : `创建 CodeArts 会话失败（HTTP ${response.status}）` };
    }
    const session = data as unknown as CodeArtsSession;
    return { accepted: Boolean(session?.id), session, response: data, message: session?.id ? "CodeArts 会话已创建" : "CodeArts 未返回会话 ID" };
  } catch {
    return { accepted: false, message: "CodeArts 服务不可达" };
  }
}

export async function promptCodeArtsSession(
  sessionId: string,
  prompt: string,
  credentials = loadCodeArtsCredentials(),
): Promise<CodeArtsRunResult> {
  try {
    const response = await fetch(`/api/codearts/session/${encodeURIComponent(sessionId)}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader(credentials) },
      body: JSON.stringify({ parts: [{ type: "text", text: prompt }] }),
    });
    const data = await readJson(response);
    if (!response.ok) {
      return { accepted: false, message: response.status === 401 ? "CodeArts 认证失败" : `CodeArts 推理请求失败（HTTP ${response.status}）` };
    }
    return { accepted: true, response: data, message: "CodeArts 已接受推理任务" };
  } catch {
    return { accepted: false, message: "CodeArts 服务不可达" };
  }
}
