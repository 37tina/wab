// CodeArts Agent 网关：Agent 与本服务同机运行，启动时会把真实端口写入
// ~/.codeartsdoer/CodeArts_Agent/<版本目录>/server_config.properties。
// 这里负责发现该端口、按需解密 Agent 本机托管凭据，并向上提供
// 状态查询与带回退重试的反向代理 fetch。
const { createDecipheriv, scryptSync } = require("node:crypto");
const { copyFileSync, existsSync, readFileSync, readdirSync, statSync, writeFileSync } = require("node:fs");
const { homedir } = require("node:os");
const { join } = require("node:path");

const DEFAULT_PORT = process.env.CODEARTS_PORT || "27546";
const DISCOVERY_TTL_MS = 5000;
const HEALTH_TIMEOUT_MS = 4000;

function codeArtsHome() {
  return process.env.CODEARTS_HOME || join(homedir(), ".codeartsdoer");
}

// ---- 端口发现 ----

function parseProperties(text) {
  const props = {};
  for (const line of text.split(/\r?\n/)) {
    const match = line.match(/^([A-Za-z_][\w.-]*)\s*=\s*(.*)$/);
    if (match) props[match[1].trim()] = match[2].trim();
  }
  return props;
}

function readServerConfig(dir) {
  const file = join(dir, "server_config.properties");
  if (!existsSync(file)) return null;
  try {
    const props = parseProperties(readFileSync(file, "utf8"));
    const port = Number(props.port);
    if (!Number.isInteger(port) || port <= 0 || port > 65535) return null;
    const pid = Number(props.pid);
    const stats = statSync(file);
    return {
      port,
      pid: Number.isInteger(pid) && pid > 0 ? pid : undefined,
      pidAlive: false,
      version: props.version || undefined,
      configFile: file,
      configMtime: stats.mtimeMs,
    };
  } catch {
    return null;
  }
}

function pidAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

let discoveryCache = { at: 0, value: null };

function discoverAgent({ force = false } = {}) {
  const now = Date.now();
  if (!force && discoveryCache.value && now - discoveryCache.at < DISCOVERY_TTL_MS) {
    return discoveryCache.value;
  }
  const root = join(codeArtsHome(), "CodeArts_Agent");
  let found = null;
  try {
    for (const entry of readdirSync(root)) {
      const dir = join(root, entry);
      try {
        if (!statSync(dir).isDirectory()) continue;
      } catch {
        continue;
      }
      const config = readServerConfig(dir);
      if (config && (!found || config.configMtime > found.configMtime)) found = config;
    }
  } catch {
    // 未安装 Agent 或目录不可读：按未发现处理
  }
  if (found) found.pidAlive = pidAlive(found.pid);
  discoveryCache = { at: now, value: found };
  return found;
}

function invalidateDiscovery() {
  discoveryCache = { at: 0, value: null };
}

// ---- 目标地址解析：env > 手动覆盖(loopback) > 自动发现 > 默认端口 ----

let manualTarget = "";

function normalizeTarget(value) {
  const trimmed = String(value ?? "").trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  let parsed;
  try {
    parsed = new URL(/^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`);
  } catch {
    throw new Error("地址格式无效，示例：http://127.0.0.1:16217");
  }
  if (parsed.protocol !== "http:") throw new Error("本机 Agent 仅支持 http:// 地址");
  const host = parsed.hostname;
  if (host !== "127.0.0.1" && host !== "localhost" && host !== "[::1]" && host !== "::1") {
    throw new Error("Agent 与网关同机运行，地址只能是 127.0.0.1 / localhost / [::1]");
  }
  return `http://127.0.0.1:${parsed.port || "80"}`;
}

function setManualTarget(value) {
  manualTarget = normalizeTarget(value);
  return manualTarget;
}

function getManualTarget() {
  return manualTarget;
}

function resolveTarget({ forceDiscover = false } = {}) {
  const explicit = process.env.CODEARTS_URL || process.env.AGENT_BASE_URL;
  if (explicit) return { target: explicit.replace(/\/+$/, ""), source: "env" };
  if (manualTarget) return { target: manualTarget, source: "manual" };
  const discovered = discoverAgent({ force: forceDiscover });
  if (discovered) return { target: `http://127.0.0.1:${discovered.port}`, source: "discovered" };
  return { target: `http://127.0.0.1:${DEFAULT_PORT}`, source: "default" };
}

// ---- 凭据：浏览器头 > env > 解密 Agent 本机托管凭据 ----

function readManagedPassword() {
  if (process.env.CODEARTS_AUTO_AUTH === "0") return undefined;
  const dataRoot = process.env.CODEARTS_DATA_DIR || join(codeArtsHome(), "codearts-data");
  const keyFile = join(dataRoot, "4", "data");
  const cipherFile = join(dataRoot, "custom-dir", "data");
  const metaFile = join(dataRoot, "1", "data");
  const saltFile = join(dataRoot, "2", "data");
  const ivFile = join(dataRoot, "3", "data");
  if (![keyFile, cipherFile, metaFile, saltFile, ivFile].every(existsSync)) return undefined;
  try {
    const secret = Buffer.from(readFileSync(keyFile, "utf8").trim(), "base64").toString("utf8");
    const cipher = JSON.parse(readFileSync(cipherFile, "utf8"));
    const algorithm = JSON.parse(readFileSync(metaFile, "utf8")).algorithm;
    const salt = Buffer.from(JSON.parse(readFileSync(saltFile, "utf8")), "base64");
    const iv = Buffer.from(JSON.parse(readFileSync(ivFile, "utf8")), "base64");
    const key = scryptSync(secret, salt, 32, { N: 65536, r: 8, p: 1, maxmem: 128 * 1024 * 1024 });
    const decipher = createDecipheriv(algorithm, key, iv);
    decipher.setAuthTag(Buffer.from(cipher.authTag, "base64"));
    return Buffer.concat([decipher.update(Buffer.from(cipher.ciphertext, "base64")), decipher.final()]).toString("utf8");
  } catch {
    return undefined;
  }
}

function authMode(req) {
  if (req?.headers?.authorization) return "user";
  if (process.env.CODEARTS_SERVER_PASSWORD) return "env";
  return readManagedPassword() ? "auto" : "none";
}

function upstreamHeaders(req) {
  const headers = {};
  if (req?.headers?.authorization) {
    headers.authorization = req.headers.authorization;
  } else {
    const password = process.env.CODEARTS_SERVER_PASSWORD || readManagedPassword();
    if (password) {
      const username = process.env.CODEARTS_SERVER_USERNAME || "codearts";
      headers.authorization = "Basic " + Buffer.from(`${username}:${password}`).toString("base64");
    }
  }
  if (req?.headers?.["content-type"]) headers["content-type"] = req.headers["content-type"];
  if (req?.headers?.accept) headers.accept = req.headers.accept;
  return headers;
}

// ---- 健康探测与状态 ----

/** Node fetch 失败时真实原因在 error.cause（如 connect ECONNREFUSED host:port） */
function describeFetchError(error) {
  const cause = error?.cause;
  return String(cause?.message || cause?.code || error?.message || error).slice(0, 300);
}

async function probeHealth(target, headers) {
  const started = Date.now();
  try {
    const upstream = await fetch(new URL("/global/health", `${target}/`).toString(), {
      headers,
      signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
    });
    let body = {};
    try {
      body = await upstream.json();
    } catch {
      // 非 JSON 响应仍视为可达
    }
    return {
      reachable: true,
      status: upstream.status,
      healthy: upstream.ok && body.healthy !== false,
      latencyMs: Date.now() - started,
      service: typeof body.service === "string" ? body.service : undefined,
      version: typeof body.version === "string" ? body.version : undefined,
    };
  } catch (error) {
    return {
      reachable: false,
      healthy: false,
      latencyMs: Date.now() - started,
      error: describeFetchError(error),
    };
  }
}

async function getStatus(req) {
  const resolution = resolveTarget();
  const discovered = discoverAgent();
  const health = await probeHealth(resolution.target, upstreamHeaders(req));
  return {
    target: resolution.target,
    source: resolution.source,
    reachable: health.reachable,
    healthy: health.healthy,
    status: health.status,
    latencyMs: health.latencyMs,
    error: health.error,
    service: health.service,
    version: health.version,
    authMode: authMode(req),
    discovered: discovered
      ? { port: discovered.port, pid: discovered.pid, pidAlive: discovered.pidAlive, version: discovered.version }
      : undefined,
    checkedAt: new Date().toISOString(),
  };
}

// ---- 反向代理 fetch：网络失败时强制重新发现并换目标重试一次 ----

async function rawFetch(target, upstreamPath, { method, headers, body, timeoutMs }) {
  return fetch(new URL(upstreamPath, `${target}/`).toString(), {
    method,
    headers,
    body,
    ...(timeoutMs ? { signal: AbortSignal.timeout(timeoutMs) } : {}),
  });
}

async function fetchWithDiscovery(upstreamPath, { method = "GET", headers = {}, body, timeoutMs } = {}) {
  const first = resolveTarget();
  try {
    const response = await rawFetch(first.target, upstreamPath, { method, headers, body, timeoutMs });
    return { response, resolution: first, retried: false };
  } catch (error) {
    const second = resolveTarget({ forceDiscover: true });
    if (second.target === first.target) throw error;
    const response = await rawFetch(second.target, upstreamPath, { method, headers, body, timeoutMs });
    return { response, resolution: second, retried: true };
  }
}

function unreachableHint(detail) {
  if (/ECONNREFUSED/i.test(detail)) {
    return "目标端口没有服务在监听。若 Agent 已启动，点「重新检测」；也可以在连接设置里手动指定本机地址。";
  }
  if (/timeout|abort/i.test(detail)) return "Agent 健康检查超时，请确认本机 Agent 已启动且未卡死。";
  return "请确认本机 CodeArts Agent 已启动，然后在连接设置里重新检测。";
}

// ---- 模型管理：读取 Agent /config，新增/删除写回 codearts.json（与客户端共用同一文件） ----

function configFilePath() {
  return process.env.CODEARTS_DATA_DIR
    ? join(process.env.CODEARTS_DATA_DIR, "codearts.json")
    : join(codeArtsHome(), "codearts-data", "codearts.json");
}

/** 记录由网页创建的服务商；删除模型后若服务商因此变空，可安全连壳移除 */
function webManagedFilePath() {
  return configFilePath() + ".web-managed.json";
}

function readWebManaged() {
  try {
    const data = JSON.parse(readFileSync(webManagedFilePath(), "utf8"));
    return Array.isArray(data.providers) ? data.providers : [];
  } catch {
    return [];
  }
}

function writeWebManaged(providers) {
  try {
    writeFileSync(webManagedFilePath(), JSON.stringify({ providers }, null, 2), "utf8");
  } catch {
    // 标记写失败只影响"删空后自动移除壳"的优化，不阻塞主流程
  }
}

function hasModelDefs(provider) {
  return Object.values(provider?.options ?? {}).some((def) => def && typeof def === "object" && def.sourceType === "provider");
}

function maskKey(key) {
  const value = String(key ?? "");
  if (!value) return "";
  return value.length <= 12 ? value.slice(0, 4) + "…" : value.slice(0, 12) + "…";
}

function collectModels(providers = {}) {
  return Object.entries(providers).map(([providerID, provider]) => ({
    providerID,
    name: provider?.name || providerID,
    npm: provider?.npm || "",
    baseURL: provider?.options?.baseURL || "",
    apiKeyMasked: maskKey(provider?.options?.apiKey),
    hasApiKey: Boolean(provider?.options?.apiKey),
    models: Object.entries(provider?.options ?? {})
      .filter(([, def]) => def && typeof def === "object" && def.sourceType === "provider")
      .map(([modelId, def]) => ({
        modelID: modelId,
        modelName: def.modelName || modelId,
        modelDesc: def.modelDesc || "",
        modelType: def.modelType || "textConversation",
        displayEnabled: def.displayEnabled !== false,
        isCustomModel: def.isCustomModel === true,
        contextWindow: def.contextWindow ?? def.inputContextWindow ?? 0,
        outputContextWindow: def.outputContextWindow ?? 0,
      })),
  }));
}

/** 读取模型配置：直接读客户端共用的 codearts.json（比内核内存态更及时），失败时回落内核 /config */
async function listModels(req) {
  const file = configFilePath();
  if (existsSync(file)) {
    try {
      const config = JSON.parse(readFileSync(file, "utf8"));
      return { providers: collectModels(config.provider || {}), source: "file" };
    } catch {
      // 文件损坏或正在被客户端写入时回落到内核
    }
  }
  const { response } = await fetchWithDiscovery("/config", {
    headers: upstreamHeaders(req),
    timeoutMs: HEALTH_TIMEOUT_MS,
  });
  if (!response.ok) throw new Error(`读取 Agent 配置失败（HTTP ${response.status}）`);
  const config = await response.json();
  return { providers: collectModels(config.provider || {}), source: "kernel" };
}

function normalizeProviderID(value) {
  const id = String(value ?? "").trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  if (!id) throw new Error("服务商 ID 只能包含字母、数字、- 和 _");
  return id;
}

const API_FORMAT_NPM = {
  openai: "@ai-sdk/openai-compatible",
  anthropic: "@ai-sdk/anthropic",
};

/** 新增自定义模型：与客户端写同一份 codearts.json，字段结构与客户端保存格式一致 */
async function addModel(payload = {}) {
  const file = configFilePath();
  if (!existsSync(file)) throw new Error("未找到 Agent 配置文件：" + file);
  const config = JSON.parse(readFileSync(file, "utf8"));
  config.provider = config.provider || {};

  const providerID = normalizeProviderID(payload.providerID || payload.providerName);
  const modelId = String(payload.modelID ?? payload.modelId ?? "").trim();
  if (!modelId) throw new Error("请填写模型 ID");
  const createdProvider = !config.provider[providerID];
  const provider = config.provider[providerID] || {
    name: String(payload.providerName || providerID).trim(),
    npm: API_FORMAT_NPM[payload.apiFormat] || "@ai-sdk/openai-compatible",
    options: {},
    models: {},
  };
  provider.options = provider.options || {};
  provider.models = provider.models || {};
  if (payload.baseURL?.trim()) provider.options.baseURL = payload.baseURL.trim();
  if (payload.apiKey?.trim()) provider.options.apiKey = payload.apiKey.trim();

  const now = new Date().toISOString();
  const contextWindow = Math.max(0, Number(payload.contextWindow) || 0);
  const outputContextWindow = Math.max(0, Number(payload.outputContextWindow) || 0);
  provider.options[modelId] = {
    ...(provider.options[modelId] || {}),
    sourceType: "provider",
    providerType: providerID,
    provider: String(payload.providerName || provider.name || providerID).trim(),
    modelId,
    modelName: String(payload.modelName || modelId).trim(),
    modelType: payload.modelType || "textConversation",
    modelDesc: String(payload.modelDesc || "").trim(),
    displayEnabled: payload.displayEnabled !== false,
    isCustomModel: true,
    maxTokens: 0,
    truncateLength: 0,
    inputLength: 0,
    inputContextWindow: contextWindow,
    outputContextWindow,
    contextWindow: contextWindow,
    createdAt: provider.options[modelId]?.createdAt || now,
    updatedAt: now,
  };
  provider.models[modelId] = {
    id: modelId,
    limit: { context: contextWindow || 128000, output: outputContextWindow || 8192 },
  };
  config.provider[providerID] = provider;

  if (createdProvider) {
    const managed = readWebManaged();
    if (!managed.includes(providerID)) {
      managed.push(providerID);
      writeWebManaged(managed);
    }
  }

  const backup = `${file}.bak-${Date.now()}`;
  copyFileSync(file, backup);
  writeFileSync(file, JSON.stringify(config, null, 2), "utf8");
  return { providerID, modelID: modelId, backup, providers: collectModels(config.provider) };
}

/** 删除自定义模型（仅限 isCustomModel 标记的条目），同样先备份；网页创建的服务商删空后连壳移除 */
async function removeModel(providerID, modelId) {
  const file = configFilePath();
  if (!existsSync(file)) throw new Error("未找到 Agent 配置文件：" + file);
  const config = JSON.parse(readFileSync(file, "utf8"));
  const provider = config.provider?.[providerID];
  if (!provider) throw new Error(`服务商 ${providerID} 不存在`);
  const def = provider.options?.[modelId];
  if (!def || def.isCustomModel !== true) throw new Error("该模型不是自定义模型，不能从这里删除");
  const backup = `${file}.bak-${Date.now()}`;
  copyFileSync(file, backup);
  delete provider.options[modelId];
  delete provider.models?.[modelId];
  let removedProvider = false;
  if (!hasModelDefs(provider) && readWebManaged().includes(providerID)) {
    delete config.provider[providerID];
    writeWebManaged(readWebManaged().filter((id) => id !== providerID));
    removedProvider = true;
  }
  writeFileSync(file, JSON.stringify(config, null, 2), "utf8");
  return { providerID, modelID: modelId, removedProvider, backup, providers: collectModels(config.provider) };
}

// ---- AgentTeam 团队状态：任务清单 + 花名册（内核 /cag/agent-team/* 私有路由） ----

async function getTeamState(sessionId, req) {
  const headers = upstreamHeaders(req);
  const eps = [
    ["tasks", `/cag/agent-team/task?session_id=${encodeURIComponent(sessionId)}`],
    ["contact", `/cag/agent-team/contact?session_id=${encodeURIComponent(sessionId)}`],
  ];
  const state = {};
  await Promise.all(
    eps.map(async ([key, ep]) => {
      try {
        const { response } = await fetchWithDiscovery(ep, { headers, timeoutMs: HEALTH_TIMEOUT_MS });
        if (response.ok) state[key] = await response.json();
      } catch {
        // 单个接口失败不影响另一部分
      }
    })
  );
  return {
    sessionId,
    tasks: Array.isArray(state.tasks) ? state.tasks : [],
    members: state.contact && typeof state.contact === "object" ? state.contact : {},
  };
}

module.exports = {
  DEFAULT_PORT,
  discoverAgent,
  invalidateDiscovery,
  getManualTarget,
  setManualTarget,
  resolveTarget,
  authMode,
  upstreamHeaders,
  getStatus,
  fetchWithDiscovery,
  unreachableHint,
  normalizeTarget,
  describeFetchError,
  listModels,
  addModel,
  removeModel,
  getTeamState,
};
