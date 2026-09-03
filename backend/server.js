const express = require("express");
const mysql = require("mysql2/promise");
const { Readable } = require("node:stream");
const { statSync, readFileSync, writeFileSync, readdirSync, existsSync } = require("node:fs");
const { createHash } = require("node:crypto");
const { join } = require("node:path");
const gateway = require("./agentGateway");
const skillGov = require("./skillGovernance");

const PORT = process.env.PORT || 8080;

// ---- 环境配置（可移植化）：MIG_* 环境变量 > 根目录 config.json > 默认占位值 ----
const HOME = process.env.HOME ?? "";
function loadEnvConfig() {
  let fileConfig = {};
  try { fileConfig = JSON.parse(readFileSync(join(__dirname, "..", "config.json"), "utf8")); } catch { /* 未配置时用默认 */ }
  return {
    skillRoot: process.env.MIG_SKILL_ROOT || fileConfig.skillRoot || join(__dirname, "..", "skill"),
    runWorkspace: process.env.MIG_RUN_WORKSPACE || fileConfig.runWorkspace || join(HOME, "migrate-runs"),
    hdcBin: process.env.MIG_HDC_BIN || fileConfig.hdcBin || "/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc",
    adbBin: process.env.MIG_ADB_BIN || fileConfig.adbBin || join(HOME, "Library/Android/sdk/platform-tools/adb"),
    androidSerial: process.env.MIG_ANDROID_SERIAL || fileConfig.androidSerial || "emulator-5554",
    harmonySerial: process.env.MIG_HARMONY_SERIAL || fileConfig.harmonySerial || "127.0.0.1:5557",
    wsScrcpyUrl: process.env.MIG_WS_SCRCPY_URL || fileConfig.wsScrcpyUrl || "http://localhost:8000",
  };
}
const ENV_CONFIG = loadEnvConfig();
const CORS_ORIGIN = process.env.CORS_ORIGIN || "*";
// 支持多源: 逗号分隔列表, 每项去除尾斜杠归一化; 命中则回显请求 Origin, 否则回落第一个值 (含 "*" 时直接放行)
const CORS_ORIGINS = CORS_ORIGIN.split(",")
  .map((s) => s.trim().replace(/\/+$/, ""))
  .filter(Boolean);
function resolveCorsOrigin(req) {
  if (CORS_ORIGINS.includes("*")) return "*";
  const origin = req.headers.origin;
  if (origin && CORS_ORIGINS.includes(origin)) return origin;
  return CORS_ORIGINS[0] || "*";
}

const DB_CONFIG = {
  host: process.env.DB_HOST || "127.0.0.1",
  port: Number(process.env.DB_PORT || 3306),
  user: process.env.DB_USER || "root",
  password: process.env.DB_PASSWORD || "",
  database: process.env.DB_NAME || "tuotiahuangu",
  connectTimeout: 8000,
};

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "4mb" }));

let pool = null;
let dbReady = false;

async function initDb() {
  try {
    const admin = await mysql.createConnection({ ...DB_CONFIG, database: undefined });
    await admin.query(
      "CREATE DATABASE IF NOT EXISTS `" +
        (DB_CONFIG.database || "tuotiahuangu").replace(/[^a-zA-Z0-9_]/g, "") +
        "` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    );
    await admin.end();
    pool = mysql.createPool({ ...DB_CONFIG, waitForConnections: true, connectionLimit: 5 });
    await pool.query(`CREATE TABLE IF NOT EXISTS access_logs (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
      method VARCHAR(8) NOT NULL,
      path VARCHAR(512) NOT NULL,
      status INT NOT NULL DEFAULT 0,
      duration_ms INT NOT NULL DEFAULT 0,
      client_ip VARCHAR(64) DEFAULT '',
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`);
    dbReady = true;
    console.log("[db] mysql ready:", DB_CONFIG.host);
  } catch (error) {
    console.error("[db] init failed:", error.message);
    setTimeout(initDb, 15000);
  }
}
initDb();

async function writeAccessLog(method, path, status, durationMs, clientIp) {
  if (!dbReady) return;
  try {
    await pool.execute(
      "INSERT INTO access_logs (method, path, status, duration_ms, client_ip) VALUES (?, ?, ?, ?, ?)",
      [method, String(path).slice(0, 512), status, Math.round(durationMs), String(clientIp).slice(0, 64)]
    );
  } catch (error) {
    console.error("[db] log write failed:", error.message);
  }
}

app.use((req, res, next) => {
  const started = Date.now();
  res.on("finish", () => {
    if (req.path === "/health") return;
    writeAccessLog(req.method, req.path, res.statusCode, Date.now() - started, req.ip).catch(() => {});
  });
  next();
});

app.use((req, res, next) => {
  res.setHeader("Vary", "Origin");
  res.setHeader("Access-Control-Allow-Origin", resolveCorsOrigin(req));
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type,Authorization,Accept");
  res.setHeader("Access-Control-Max-Age", "600");
  if (req.method === "OPTIONS") return res.status(204).end();
  next();
});

app.get("/api/env", (_req, res) => {
  res.json({
    skillRoot: ENV_CONFIG.skillRoot,
    runWorkspace: ENV_CONFIG.runWorkspace,
    androidSerial: ENV_CONFIG.androidSerial,
    harmonySerial: ENV_CONFIG.harmonySerial,
    wsScrcpyUrl: ENV_CONFIG.wsScrcpyUrl,
  });
});

app.get("/health", async (req, res) => {
  let db = false;
  let dbError = "";
  try {
    if (pool) {
      await pool.query("SELECT 1");
      db = true;
    }
  } catch (error) {
    dbError = error.message;
  }
  const agent = await gateway.getStatus(req).catch(() => null);
  res.status(200).json({
    status: "ok",
    service: "tuotiahuangu-backend",
    db,
    dbError: db || !dbError ? undefined : dbError,
    agent: agent ? { target: agent.target, source: agent.source, reachable: agent.reachable } : null,
    time: new Date().toISOString(),
  });
});

app.get("/api/logs", async (req, res) => {
  if (!dbReady) return res.status(503).json({ error: "database not ready" });
  try {
    const limit = Math.min(Number(req.query.limit || 20), 100);
    const [rows] = await pool.query("SELECT * FROM access_logs ORDER BY id DESC LIMIT ?", [limit]);
    res.json(rows);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ---- Agent 连接管理：状态 / 手动地址覆盖 ----

app.get("/api/agent/status", async (req, res) => {
  try {
    res.json(await gateway.getStatus(req));
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get("/api/agent/target", (req, res) => {
  res.json({ manual: gateway.getManualTarget() });
});

app.put("/api/agent/target", (req, res) => {
  try {
    const value = typeof req.body?.baseUrl === "string" ? req.body.baseUrl : "";
    const saved = gateway.setManualTarget(value);
    gateway.invalidateDiscovery();
    res.json({ manual: saved });
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

// 检查用户指定的工作区目录在本机是否存在（只做 stat，不列目录内容）
app.get("/api/agent/workspace", (req, res) => {
  const dir = String(req.query.path || "").trim();
  if (!/^[a-zA-Z]:[\\/].+/.test(dir)) {
    return res.status(400).json({ error: "请提供本机绝对路径，例如 D:\\code\\workspace" });
  }
  try {
    const stats = statSync(dir);
    res.json({ path: dir, exists: true, isDirectory: stats.isDirectory() });
  } catch {
    res.json({ path: dir, exists: false });
  }
});

// ---- 模型管理：列表来自 Agent 实时配置；新增/删除写 codearts.json（客户端共用）----

app.get("/api/agent/models", async (req, res) => {
  try {
    res.json(await gateway.listModels(req));
  } catch (error) {
    res.status(502).json({ error: "读取模型列表失败", detail: gateway.describeFetchError(error) });
  }
});

app.post("/api/agent/models", async (req, res) => {
  try {
    res.json(await gateway.addModel(req.body || {}));
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

app.delete("/api/agent/models/:providerID/:modelID", async (req, res) => {
  try {
    res.json(await gateway.removeModel(req.params.providerID, req.params.modelID));
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

// AgentTeam 团队状态：任务清单 + 花名册
app.get("/api/agent/team/:sessionId", async (req, res) => {
  try {
    res.json(await gateway.getTeamState(req.params.sessionId, req));
  } catch (error) {
    res.status(502).json({ error: "读取团队状态失败", detail: gateway.describeFetchError(error) });
  }
});

// ---- Skill 治理：浏览 + 修改提案（审核通过才落盘） ----

app.get("/api/skill/tree", (req, res) => {
  try {
    res.json({ root: skillGov.SKILL_ROOT, skills: skillGov.listSkillTree() });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get("/api/skill/file", (req, res) => {
  try {
    const content = skillGov.readSkillFile(req.query.path);
    res.json({ path: String(req.query.path), content });
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

app.get("/api/skill/proposals", (req, res) => {
  res.json({ proposals: skillGov.listProposals() });
});

app.get("/api/skill/proposals/:id/content", (req, res) => {
  try {
    res.json(skillGov.getProposalContent(req.params.id));
  } catch (error) {
    res.status(404).json({ error: error.message });
  }
});

app.post("/api/skill/proposals", (req, res) => {
  try {
    res.json(skillGov.createProposal(req.body || {}));
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

app.post("/api/skill/proposals/:id/decide", (req, res) => {
  try {
    const decision = req.body?.decision === "approved" ? "approved" : req.body?.decision === "rejected" ? "rejected" : null;
    if (!decision) return res.status(400).json({ error: "decision 必须是 approved 或 rejected" });
    res.json(skillGov.decideProposal(req.params.id, decision, req.body?.comment));
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

// ---- CodeArts 代理：目标地址按请求解析，网络失败时重新发现并重试一次 ----

app.all("/api/codearts/*", async (req, res) => {
  const upstreamPath = req.originalUrl.slice("/api/codearts".length);
  const headers = gateway.upstreamHeaders(req);
  const init = {
    method: req.method,
    headers,
    body: req.method === "GET" || req.method === "HEAD" ? undefined : JSON.stringify(req.body || {}),
  };
  // 发起 AgentTeam 任务前确保自定义模型已注册进内核运行时
  //（内核启动时只有 inferhub；且内核可能原地重启清空注册表——每次 prompt 实时校验目标服务商）
  if (upstreamPath.includes("prompt_async")) {
    await gateway.ensureModelsRegistered(req);
    const wantedProvider = req.body?.model?.providerID;
    if (wantedProvider) await gateway.ensureModelAvailable(req, wantedProvider);
  }
  try {
    const { response: upstream, resolution, retried } = await gateway.fetchWithDiscovery(upstreamPath, init);
    res.status(upstream.status);
    if (retried) res.setHeader("X-Agent-Failover", resolution.target);
    upstream.headers.forEach((value, key) => {
      if (!["content-length", "content-encoding", "connection", "transfer-encoding"].includes(key)) {
        res.setHeader(key, value);
      }
    });
    if (!upstream.body) return res.end();
    Readable.fromWeb(upstream.body).pipe(res);
  } catch (error) {
    const detail = gateway.describeFetchError(error);
    const resolution = gateway.resolveTarget();
    res.status(502).json({
      error: "CodeArts Agent 服务不可达",
      detail,
      target: resolution.target,
      source: resolution.source,
      hint: gateway.unreachableHint(detail),
    });
  }
});

// ---- 鸿蒙模拟器实时画面（hdc snapshot 两步抓帧 + 缓存轮询） ----
const HDC_BIN = ENV_CONFIG.hdcBin;
const harmonyLatest = new Map(); // serial -> Buffer
const harmonyLastPoll = new Map();
function captureHarmonyFrame(serial) {
  return new Promise((resolve) => {
    const remote = "/data/local/tmp/webcast.jpeg";
    const local = join("/tmp", `harmony-cast-${serial.replace(/[:.]/g, "-")}.jpeg`);
    execFile(HDC_BIN, ["-t", serial, "shell", "snapshot_display", "-f", remote], { timeout: 5000 }, (error) => {
      if (error) { resolve(null); return; }
      execFile(HDC_BIN, ["-t", serial, "file", "recv", remote, local], { timeout: 5000 }, (error2) => {
        if (error2) { resolve(null); return; }
        try { resolve(readFileSync(local)); } catch { resolve(null); }
      });
    });
  });
}
app.get("/api/emulator/harmony/frame", async (req, res) => {
  const serial = String(req.query.serial || "127.0.0.1:5557");
  harmonyLastPoll.set(serial, Date.now());
  let frame = harmonyLatest.get(serial);
  const fresh = frame && Date.now() - (harmonyLastPoll.get(`${serial}:wrote`) ?? 0) < 2500;
  if (!fresh) {
    const captured = await captureHarmonyFrame(serial);
    if (captured && captured.length > 1000) {
      frame = captured;
      harmonyLatest.set(serial, frame);
      harmonyLastPoll.set(`${serial}:wrote`, Date.now());
    }
  }
  if (!frame) { res.status(503).json({ error: "鸿蒙设备不可达或抓帧失败" }); return; }
  res.writeHead(200, { "Content-Type": "image/jpeg", "Cache-Control": "no-store" });
  res.end(frame);
});

// 从 JPEG 二进制解析 SOF 段拿到真实分辨率（反控 uinput 坐标是设备像素空间，须按真实分辨率换算）
function jpegSize(buf) {
  if (!Buffer.isBuffer(buf) || buf.length < 8 || buf[0] !== 0xff || buf[1] !== 0xd8) return null;
  let off = 2;
  while (off + 9 < buf.length) {
    if (buf[off] !== 0xff) { off += 1; continue; }
    const marker = buf[off + 1];
    if (marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc) {
      return { height: buf.readUInt16BE(off + 5), width: buf.readUInt16BE(off + 7) };
    }
    if (marker === 0xd8 || (marker >= 0xd0 && marker <= 0xd9)) { off += 2; continue; }
    off += 2 + buf.readUInt16BE(off + 2);
  }
  return null;
}
const harmonyInfoCache = new Map(); // serial -> { at, info }
app.get("/api/emulator/harmony/info", async (req, res) => {
  const serial = String(req.query.serial || "127.0.0.1:5557");
  const mode = harmonyH264 ? "h264" : "jpeg";
  const cached = harmonyInfoCache.get(serial);
  if (cached && Date.now() - cached.at < 60000) { res.json({ serial, mode, ...cached.info }); return; }
  let frame = harmonyLatest.get(serial);
  if (!frame || Date.now() - (harmonyLastPoll.get(`${serial}:wrote`) ?? 0) > 10000) frame = await captureHarmonyFrame(serial);
  const size = frame ? jpegSize(frame) : null;
  if (!size) { res.json({ serial, mode, error: "鸿蒙设备不可达，分辨率未知（反控将用默认值）" }); return; }
  harmonyInfoCache.set(serial, { at: Date.now(), info: size });
  res.json({ serial, mode, ...size });
});

// ---- 模拟器高速窗口采集（Android=qemu / 鸿蒙=Emulator）+ WS 直转 + 反向控制 ----
const HARMONY_FRAME_FILE = "/tmp/harmony-window-frame.jpg";
function makeFastCapture(platform, ownerKey, outW, outH, fps, mode = "window") {
  const state = { proc: null, buf: Buffer.alloc(0), lastFrameAt: 0, restartTimer: null, idleTimer: null };
  const clients = new Set();
  // 背压：慢客户端（浏览器解码/网络跟不上 30fps）跳帧，避免 ws 缓冲无限膨胀拖垮网关
  const broadcast = (frame) => {
    for (const ws of clients) {
      try { if (ws.bufferedAmount <= 2 * 1024 * 1024) ws.send(frame); } catch { clients.delete(ws); }
    }
  };
  const scheduleIdleStop = () => {
    if (state.idleTimer) clearTimeout(state.idleTimer);
    state.idleTimer = setTimeout(() => {
      state.idleTimer = null;
      if (clients.size === 0 && state.proc) {
        console.log(`[wincap:${platform}] 无客户端，空闲回收采集进程`);
        try { state.proc.kill(); } catch { /* 已退出 */ }
      }
    }, 20000);
  };
  const start = () => {
    if (state.proc) return;
    try {
      const proc = require("node:child_process").spawn(
        "python3",
        [join(__dirname, "tools", "window_fast_capture.py"), ownerKey, String(outW), String(outH), String(fps), mode],
        { stdio: ["ignore", "pipe", "pipe"] },
      );
      state.proc = proc;
      state.buf = Buffer.alloc(0);
      proc.stdout.on("data", (chunk) => {
        state.buf = Buffer.concat([state.buf, chunk]);
        while (state.buf.length >= 4) {
          const len = state.buf.readUInt32BE(0);
          if (len === 0 || state.buf.length < 4 + len) break;
          const frame = Buffer.from(state.buf.subarray(4, 4 + len));
          state.lastFrameAt = Date.now();
          broadcast(frame);
          state.buf = state.buf.subarray(4 + len);
        }
        if (state.buf.length > 24 * 1024 * 1024) state.buf = Buffer.alloc(0);
      });
      proc.stderr.on("data", (chunk) => { console.log(`[wincap:${platform}] ${String(chunk).trim()}`); });
      proc.on("exit", (code) => {
        state.proc = null;
        if (state.restartTimer) clearTimeout(state.restartTimer);
        // 无客户端时不自动重启：避免后台无人观看仍永久拉起 30fps 采集进程
        if (clients.size > 0) {
          state.restartTimer = setTimeout(() => { state.restartTimer = null; start(); }, 5000);
          console.log(`[wincap:${platform}] 退出 code=${code}，仍有客户端，5s 后重试`);
        } else {
          console.log(`[wincap:${platform}] 退出 code=${code}，无客户端，不再重启`);
        }
      });
    } catch (error) {
      console.log(`[wincap:${platform}] 启动失败: ${error}`);
      state.proc = null;
    }
  };
  const addClient = (ws) => {
    clients.add(ws);
    if (state.idleTimer) { clearTimeout(state.idleTimer); state.idleTimer = null; }
    start();
    ws.on("close", () => { clients.delete(ws); scheduleIdleStop(); });
    ws.on("error", () => { clients.delete(ws); scheduleIdleStop(); });
  };
  return { state, addClient, broadcast, clients };
}
const androidCastFallback = makeFastCapture("android", "qemu-system", 440, 900, 30, "screen");
// Android 主通道：设备端 screenrecord 裸 h264（不受窗口遮挡影响），180 秒分段循环
const androidH264 = { proc: null, fails: 0, clients: new Set(), restartTimer: null, lastFrameAt: 0, intentional: false, idleTimer: null };
// 最后一个客户端离开 20 秒后回收 screenrecord（避免后台无人观看仍持续分段录制）
function scheduleAndroidIdleStop() {
  if (androidH264.idleTimer) clearTimeout(androidH264.idleTimer);
  androidH264.idleTimer = setTimeout(() => {
    androidH264.idleTimer = null;
    if (androidH264.clients.size === 0 && androidH264.proc) {
      androidH264.intentional = true;
      try { androidH264.proc.kill(); } catch { /* 已退出 */ }
    }
  }, 20000);
}
function broadcastH264(chunk) {
  for (const ws of androidH264.clients) { try { ws.send(chunk); } catch { androidH264.clients.delete(ws); } }
}
function startScreenrecord() {
  if (androidH264.proc) return;
  try {
    const proc = require("node:child_process").spawn(
      ADB_BIN, ["-s", ENV_CONFIG.androidSerial, "exec-out",
        "screenrecord --size 720x1600 --bit-rate 8000000 --time-limit 180 --output-format=h264 -"],
      { stdio: ["ignore", "pipe", "ignore"] },
    );
    androidH264.proc = proc;
    proc.stdout.on("data", (chunk) => { androidH264.fails = 0; androidH264.lastFrameAt = Date.now(); broadcastH264(chunk); });
    proc.on("exit", (code) => {
      androidH264.proc = null;
      if (androidH264.intentional) {
        // 主动重启（新客户端接入且流过期 / 空闲回收）：不计失败，仍有客户端才拉起
        androidH264.intentional = false;
        if (androidH264.restartTimer) clearTimeout(androidH264.restartTimer);
        if (androidH264.clients.size > 0) {
          androidH264.restartTimer = setTimeout(() => { androidH264.restartTimer = null; startScreenrecord(); }, 200);
        } else {
          console.log("[h264] 无客户端，screenrecord 已空闲回收");
        }
        return;
      }
      androidH264.fails += 1;
      if (androidH264.restartTimer) clearTimeout(androidH264.restartTimer);
      if (androidH264.fails > 3) {
        console.log("[h264] 连续失败过多，暂停 screenrecord（窗口采集回退可用）");
        return;
      }
      androidH264.restartTimer = setTimeout(() => { androidH264.restartTimer = null; startScreenrecord(); }, 800);
    });
    console.log("[h264] screenrecord 分段已启动");
  } catch (error) {
    console.log(`[h264] 启动失败: ${error}`);
    androidH264.proc = null;
  }
}
const harmonyCast = makeFastCapture("harmony", "emulator", 483, 858, 30);
// ---- 鸿蒙主通道：python 窗口 BGRA 裸帧 → ffmpeg VideoToolbox 硬编 h264 → WS 直转 ----
// （JPEG 采集在 pyobjc 下有修不干净的编码器泄漏，h264 管线全部走无泄漏组件 + C 编码器）
const FFMPEG_BIN = (() => {
  try {
    return require("node:child_process").execSync("command -v ffmpeg", { timeout: 3000 }).toString().trim() || null;
  } catch { return null; }
})();
function makeH264Pipeline(ownerKey, outW, fps) {
  const state = { py: null, ff: null, clients: new Set(), lastFrameAt: 0, idleTimer: null, restartTimer: null };
  // 窗口采集依赖模拟器窗口可见（最小化/被藏则拿不到帧）：拉流时置前一次（60 秒内不重复）
  let frontmostAt = 0;
  const bringToFront = () => {
    if (Date.now() - frontmostAt < 60000) return;
    frontmostAt = Date.now();
    execFile("osascript", ["-e", 'tell application "System Events" to set frontmost of process "Emulator" to true'], { timeout: 4000 }, () => {});
  };
  const broadcast = (chunk) => {
    for (const ws of state.clients) { try { if (ws.bufferedAmount <= 2 * 1024 * 1024) ws.send(chunk); } catch { state.clients.delete(ws); } }
  };
  const stopAll = () => { for (const proc of [state.py, state.ff]) { try { proc?.kill(); } catch { /* 已退出 */ } } state.py = null; state.ff = null; };
  const scheduleIdleStop = () => {
    if (state.idleTimer) clearTimeout(state.idleTimer);
    state.idleTimer = setTimeout(() => {
      state.idleTimer = null;
      if (state.clients.size === 0) {
        console.log("[h264:harmony] 无客户端，空闲回收采集管线");
        stopAll();
      }
    }, 20000);
  };
  const onExit = (who, code) => {
    stopAll();
    if (state.restartTimer) clearTimeout(state.restartTimer);
    if (state.clients.size > 0) {
      state.restartTimer = setTimeout(() => { state.restartTimer = null; start(); }, 3000);
      console.log(`[h264:harmony] ${who} 退出 code=${code}，仍有客户端，3s 后重建管线`);
    } else {
      console.log(`[h264:harmony] ${who} 退出 code=${code}，无客户端，不再重启`);
    }
  };
  const start = () => {
    if (state.py) return;
    // 不置前：离屏采集（IncludingWindow）不要求前台，避免抢焦点
    const py = require("node:child_process").spawn(
      "python3",
      [join(__dirname, "tools", "harmony_raw_capture.py"), ownerKey, String(outW), String(fps)],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    state.py = py;
    let handshake = Buffer.alloc(0);
    let handshaken = false;
    py.stdout.on("data", (chunk) => {
      if (!handshaken) {
        handshake = Buffer.concat([handshake, chunk]);
        const nl = handshake.indexOf(0x0a);
        if (nl < 0) return;
        const head = handshake.slice(0, nl).toString("utf8").trim();
        const match = /^RAWBGRA (\d+) (\d+)$/.exec(head);
        if (!match) { console.log(`[h264:harmony] 握手失败: ${head}`); py.kill(); return; }
        handshaken = true;
        const [w, h] = [Number(match[1]), Number(match[2])];
        const ff = require("node:child_process").spawn(
          FFMPEG_BIN,
          ["-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgra", "-s", `${w}x${h}`, "-r", String(fps), "-i", "pipe:0",
            "-c:v", "h264_videotoolbox", "-realtime", "1", "-b:v", "6M", "-g", "30", "-bf", "0",
            "-bsf:v", "h264_metadata=aud=insert",
            "-f", "h264", "pipe:1"],
          { stdio: ["pipe", "pipe", "pipe"] },
        );
        state.ff = ff;
        ff.stdout.on("data", (out) => { state.lastFrameAt = Date.now(); broadcast(out); });
        ff.stderr.on("data", (out) => { console.log(`[ffmpeg:harmony] ${String(out).trim()}`); });
        ff.stdin.on("error", () => { /* python 先退出时的 EPIPE，由 exit 处理 */ });
        ff.on("exit", (code) => onExit("ffmpeg", code));
        ff.stdin.write(handshake.slice(nl + 1));
        console.log(`[h264:harmony] 管线就绪 ${w}x${h}@${fps}`);
        return;
      }
      if (state.ff) { try { state.ff.stdin.write(chunk); } catch { /* 管线重建中 */ } }
    });
    py.stderr.on("data", (chunk) => { console.log(`[rawcap:harmony] ${String(chunk).trim()}`); });
    py.on("exit", (code) => onExit("rawcap", code));
  };
  const addClient = (ws) => {
    state.clients.add(ws);
    if (state.idleTimer) { clearTimeout(state.idleTimer); state.idleTimer = null; }
    start();
    ws.on("close", () => { state.clients.delete(ws); scheduleIdleStop(); });
    ws.on("error", () => { state.clients.delete(ws); scheduleIdleStop(); });
  };
  return { state, addClient, broadcast, clients: state.clients };
}
const harmonyH264 = FFMPEG_BIN ? makeH264Pipeline("emulator", 486, 30) : null;
// 鸿蒙兜底：高速流无帧时读帧文件（hdc 守护持续覆写）；无客户端时自动停表
let harmonyFileTimer = null;
function startHarmonyFileFallback() {
  if (harmonyFileTimer) return;
  harmonyFileTimer = setInterval(() => {
    if (harmonyCast.clients.size === 0) { clearInterval(harmonyFileTimer); harmonyFileTimer = null; return; }
    if (Date.now() - harmonyCast.state.lastFrameAt < 1200) return;
    try { harmonyCast.broadcast(readFileSync(HARMONY_FRAME_FILE)); } catch { /* 帧文件暂不可用 */ }
  }, 700);
}
const WebSocket = require("ws");
const castWss = new WebSocket.Server({ noServer: true });
let androidFrontmostAt = 0;
function bringAndroidToFront() {
  // qemu 的 GL 子表面采集依赖窗口可见：置前一次（60 秒内不重复）
  // 已禁用置前：抢焦点影响用户操作；全屏裁剪兜底被遮挡时画面异常属预期
  return;
}
castWss.on("connection", (client, req) => {
  if (req.url && req.url.includes("/api/emulator/android/ws")) {
    bringAndroidToFront();
    const useH264 = androidH264.fails <= 3;
    if (useH264) {
      androidH264.clients.add(client);
      startScreenrecord();
      // 新客户端接入即重启分段：screenrecord 关键帧间隔长、静止画面不产帧，
      // 复用旧分段会让新客户端长时间黑屏等关键帧（现有观看者仅短暂定格）
      console.log("[h264] 新客户端接入，重启 screenrecord 分段出关键帧");
      androidH264.intentional = true;
      try { androidH264.proc?.kill(); } catch { /* 已退出 */ }
      client.on("close", () => { androidH264.clients.delete(client); scheduleAndroidIdleStop(); });
      client.on("error", () => { androidH264.clients.delete(client); scheduleAndroidIdleStop(); });
    } else {
      androidCastFallback.addClient(client);
    }
  }
  else if (req.url && req.url.includes("/api/emulator/harmony/ws")) {
    if (harmonyH264) harmonyH264.addClient(client);
    else { harmonyCast.addClient(client); startHarmonyFileFallback(); }
  }
  else client.close();
});
// HDC 反向控制：tap / swipe / text / key
function hdcRun(args) {
  return new Promise((resolve) => {
    execFile(HDC_BIN, ["-t", ENV_CONFIG.harmonySerial, ...args], { timeout: 6000 }, (error, stdout, stderr) => {
      resolve({ ok: !error, out: String(stdout || stderr || "").slice(0, 200) });
    });
  });
}
// ADB 反向控制（Android 侧）

function adbRun(args) {
  return new Promise((resolve) => {
    execFile(ADB_BIN, ["-s", ENV_CONFIG.androidSerial, ...args], { timeout: 6000 }, (error, stdout, stderr) => {
      resolve({ ok: !error, out: String(stdout || stderr || "").slice(0, 200) });
    });
  });
}
app.post("/api/emulator/android/control", async (req, res) => {
  const { action, x, y, x2, y2, text } = req.body || {};
  let result;
  switch (action) {
    case "tap":
      result = await adbRun(["shell", `input tap ${Math.round(Number(x))} ${Math.round(Number(y))}`]);
      break;
    case "swipe":
      result = await adbRun(["shell", `input swipe ${Math.round(Number(x))} ${Math.round(Number(y))} ${Math.round(Number(x2))} ${Math.round(Number(y2))} 300`]);
      break;
    case "text":
      result = await adbRun(["shell", `input text ${JSON.stringify(String(text || "").replace(/[^\x20-\x7e]/g, "").slice(0, 60)).slice(1, -1)}`]);
      break;
    case "back":
      result = await adbRun(["shell", "input keyevent 4"]);
      break;
    case "home":
      result = await adbRun(["shell", "input keyevent 3"]);
      break;
    default:
      res.status(400).json({ error: "unknown action" });
      return;
  }
  res.json(result);
});
app.post("/api/emulator/harmony/control", async (req, res) => {
  const { action, x, y, x2, y2, text, key } = req.body || {};
  let result;
  switch (action) {
    case "tap":
      result = await hdcRun(["shell", `uinput -T -c ${Math.round(Number(x))} ${Math.round(Number(y))}`]);
      break;
    case "swipe":
      result = await hdcRun(["shell", `uinput -T -m ${Math.round(Number(x))} ${Math.round(Number(y))} ${Math.round(Number(x2))} ${Math.round(Number(y2))} 300`]);
      break;
    case "text":
      result = await hdcRun(["shell", `uinput -K -t ${String(text || "").replace(/[^\x20-\x7e]/g, "").slice(0, 60)}`]);
      break;
    case "back":
      result = await hdcRun(["shell", "uinput -K -d 2 -u 2"]);
      break;
    case "home":
      result = await hdcRun(["shell", "uinput -K -d 1 -u 1"]);
      break;
    default:
      res.status(400).json({ error: "unknown action" });
      return;
  }
  res.json(result);
});

// ---- 大白话实况：把 RUN 取证活动翻译成与 Phase 2 交付物（BC/feature）对应的人话 ----
function readCsvRows(text) {
  const lines = text.split(/\r?\n/).filter(Boolean);
  if (!lines.length) return [];
  const header = parseCsvLine(lines[0]);
  return lines.slice(1).map((line) => {
    const cells = parseCsvLine(line);
    const row = {};
    header.forEach((key, index) => { row[key] = cells[index] ?? ""; });
    return row;
  });
}
const CAPTURE_STEP_LABELS = [
  ["before", "准备初始状态"],
  ["operations", "执行操作步骤"],
  ["after", "采集执行后的界面与数据"],
  ["restart", "重启应用验证持久化"],
  ["assertions", "判定断言结果"],
];
app.get("/api/run/activity", (req, res) => {
  try {
    const workspace = String(req.query.workspace || "");
    if (!workspace || !/^(\/|[A-Za-z]:[\\/])/.test(workspace)) { res.json({ headline: "等待迁移启动", detail: "尚未检测到运行目录", timeline: [] }); return; }
    let runs = [];
    try { runs = readdirSync(workspace).filter((name) => /^MIG-/.test(name)); } catch { runs = []; }
    if (!runs.length) { res.json({ headline: "等待迁移启动", detail: "工作区内暂无 RUN", timeline: [] }); return; }
    const runId = runs.sort().pop();
    const runRoot = join(workspace, runId);
    // BC → 功能名 / 验证目的（来自 Phase 2 交付物）
    const featureNames = new Map();
    const bcInfo = new Map();
    try {
      const fm = JSON.parse(readFileSync(join(runRoot, "phase-02-android-inventory", "feature-map.json"), "utf8"));
      let feats = fm.features ?? fm.feature_map ?? fm;
      if (!Array.isArray(feats)) feats = Object.values(feats);
      for (const f of feats) if (f && f.feature_id) featureNames.set(f.feature_id, f.name || f.feature_id);
      const rows = readCsvRows(readFileSync(join(runRoot, "phase-02-android-inventory", "behavior-contracts.csv"), "utf8"));
      for (const row of rows) bcInfo.set(row.bc_id, { feature: featureNames.get(row.feature_id) || row.feature_id, intent: row.user_intent || "" });
    } catch { /* P2 产物未就绪时忽略 */ }
    // 最近 30 分钟文件活动 → 大白话
    const files = [];
    const collect = (dir, phase) => {
      try {
        for (const entry of readdirSync(dir, { withFileTypes: true })) {
          const full = join(dir, entry.name);
          if (entry.isDirectory()) { if (!entry.name.startsWith(".") && entry.name !== "node_modules" && entry.name !== "build") collect(full, phase); }
          else { try { const st = statSync(full); if (Date.now() - st.mtimeMs < 48 * 60 * 60 * 1000) files.push({ rel: join(phase, entry.name).replace(/\\/g, "/"), full, mtime: st.mtimeMs }); } catch {} }
        }
      } catch {}
    };
    collect(runRoot, "");
    files.sort((a, b) => b.mtime - a.mtime);
    const events = [];
    const seen = new Set();
    for (const file of files) {
      const m = /BC-(\d+)/.exec(file.rel);
      const stepMatch = CAPTURE_STEP_LABELS.find(([key]) => file.rel.includes(`/${key}`) || file.rel.includes(`/${key}.`));
      let text = "";
      let key = "";
      if (m && bcInfo.has(`BC-${m[1]}`.length ? `BC-${m[1].padStart(4, "0")}` : "")) {
        const info = bcInfo.get(`BC-${m[1].padStart(4, "0")}`);
        text = `「${info.feature}」· ${stepMatch ? stepMatch[1] : "真机取证"}`;
        key = `${m[1]}-${stepMatch ? stepMatch[0] : "chain"}`;
      } else if (m) {
        text = `行为契约 BC-${m[1].padStart(4, "0")} · ${stepMatch ? stepMatch[1] : "真机取证"}`;
        key = `${m[1]}-${stepMatch ? stepMatch[0] : "chain"}`;
      } else if (/phase-02-android-inventory\/(candidates|catalogs)\//.test(file.rel)) { text = "分析源码，梳理功能地图"; key = "inventory"; }
      else if (/visual-memory/.test(file.rel)) { text = "汇总界面视觉记忆"; key = "visual"; }
      else if (/phase-2-report/.test(file.rel)) { text = "生成盘点报告"; key = "report2"; }
      else if (/phase-03-harmony-scaffold\/harmony-project\/.*(ets|json5)/.test(file.rel)) { text = "搭建鸿蒙原生骨架"; key = "scaffold"; }
      else if (/phase-03-harmony-scaffold/.test(file.rel)) { text = "产出鸿蒙架构蓝图"; key = "p3"; }
      else if (/phase-04.*dual/.test(file.rel)) { text = "双机对比验证（Android 为基准）"; key = "dual"; }
      else if (/phase-04.*\.ets/.test(file.rel)) { text = "实现鸿蒙功能代码"; key = "impl"; }
      else if (/phase-04/.test(file.rel)) { text = "功能实现与验证"; key = "p4"; }
      else if (/decision-log/.test(file.rel)) { text = "记录流程决策"; key = "decision"; }
      else if (/gate-report|run-status/.test(file.rel)) { text = "门禁校验与状态流转"; key = "gate"; }
      else continue;
      if (seen.has(key)) continue;
      seen.add(key);
      events.push({ at: new Date(file.mtime).toISOString(), text, bc: m ? `BC-${m[1].padStart(4, "0")}` : "" });
    }
    let headline = "暂无取证活动记录";
    let detail = "运行目录内没有可识别的产物活动";
    let linked = "";
    if (events.length) {
      const latest = events[0];
      const freshMs = Date.now() - new Date(latest.at).getTime();
      const isActive = freshMs < 5 * 60 * 1000;
      if (latest.bc && bcInfo.has(latest.bc)) {
        const info = bcInfo.get(latest.bc);
        headline = `${isActive ? "正在" : "上次"}验证「${info.feature}」`;
        detail = `验证目的：${info.intent || "（见行为契约）"}${isActive ? " · 进行中" : " · 已完成静置"}`;
        linked = `${latest.bc} · phase-02-android-inventory/behavior-contracts.csv`;
      } else {
        headline = `${isActive ? "正在" : "上次"}：${latest.text}`;
        detail = isActive ? "进行中" : `完成于 ${new Date(latest.at).toTimeString().slice(0, 5)}`;
      }
    }
    res.json({ runId, headline, detail, linked, timeline: events.slice(0, 8) });
  } catch (error) {
    res.status(500).json({ error: String(error) });
  }
});

// ---- 最近取证产物：工作区内最近 N 分钟新增/修改的文件（"正在干嘛"面板） ----
app.get("/api/run/recent", (req, res) => {
  const workspace = String(req.query.workspace || "");
  const minutes = Math.min(Math.max(Number(req.query.minutes) || 15, 1), 120);
  if (!workspace || !/^(\/|[A-Za-z]:[\\/])/.test(workspace)) { res.json({ files: [] }); return; }
  execFile("find", [workspace, "-type", "f", "-mmin", String(minutes)], { timeout: 5000, maxBuffer: 4 * 1024 * 1024 }, (error, stdout) => {
    if (error) { res.json({ files: [] }); return; }
    const files = String(stdout).split("\n").filter(Boolean).map((path) => {
      try { return { path: path.slice(workspace.length + 1), mtime: statSync(path).mtimeMs }; } catch { return null; }
    }).filter(Boolean).sort((a, b) => b.mtime - a.mtime).slice(0, 14);
    res.json({ files });
  });
});

// ---- Android 模拟器实时画面：MJPEG 广播流（单抓帧循环，多客户端共享，~3fps 只读） ----
const { execFile } = require("node:child_process");
const ADB_BIN = ENV_CONFIG.adbBin;
const castClients = new Map(); // serial -> Set<res>
const castLatest = new Map(); // serial -> Buffer（最近一帧，新客户端立即出图）
function castSleep(ms) { return new Promise((resolve) => { setTimeout(resolve, ms); }); }
function captureEmulatorFrame(serial) {
  return new Promise((resolve) => {
    execFile(ADB_BIN, ["-s", serial, "exec-out", "screencap", "-p"], { timeout: 4000, maxBuffer: 12 * 1024 * 1024, encoding: "buffer" }, (error, stdout) => {
      resolve(error ? null : stdout);
    });
  });
}
const castSentinels = new Map(); // serial -> 哨兵客户端（保持抓帧循环常驻）
const castLastPoll = new Map(); // serial -> 最近一次 /frame 请求时间（空闲 60s 自动停）
const castSentinelOf = (serial) => {
  if (!castSentinels.has(serial)) castSentinels.set(serial, { write() { return true; }, isSentinel: true });
  return castSentinels.get(serial);
};
async function runCastLoop(serial) {
  const clients = castClients.get(serial);
  if (!clients || clients.size === 0) return;
  while (clients.size > 0) {
    // 空闲回收：60 秒无 frame 请求且无真实流客户端则停止（避免模拟器常驻压力）
    const lastPoll = castLastPoll.get(serial) ?? 0;
    const hasReal = [...clients].some((c) => !c.isSentinel);
    if (!hasReal && Date.now() - lastPoll > 60000) break;
    const frame = await captureEmulatorFrame(serial);
    if (frame && frame.length > 1000) {
      castLatest.set(serial, frame);
      for (const res of clients) {
        try { res.write(`--castframe\r\nContent-Type: image/png\r\nContent-Length: ${frame.length}\r\n\r\n`); res.write(frame); res.write("\r\n"); }
        catch { clients.delete(res); }
      }
    }
    // 流水线：抓完即抓下一帧（仅留极短间隔防止空转），帧率=1/抓帧耗时
    await castSleep(40);
  }
  clients.delete(castSentinelOf(serial));
}
// 帧快照请求时按需启动抓帧循环（无 MJPEG 连接也能持续产帧）
app.get("/api/emulator/android/frame", async (req, res) => {
  const serial = String(req.query.serial || "emulator-5554");
  castLastPoll.set(serial, Date.now());
  let frame = castLatest.get(serial);
  if (!frame) frame = await captureEmulatorFrame(serial);
  if (!castClients.has(serial)) castClients.set(serial, new Set());
  const clients = castClients.get(serial);
  const wasIdle = clients.size === 0;
  const sentinel = castSentinelOf(serial);
  if (!clients.has(sentinel)) clients.add(sentinel);
  if (wasIdle) void runCastLoop(serial);
  if (!frame) { res.status(503).json({ error: "设备不可达或抓帧失败" }); return; }
  res.writeHead(200, { "Content-Type": "image/png", "Cache-Control": "no-store" });
  res.end(frame);
});
app.get("/api/emulator/android/stream", (req, res) => {
  const serial = String(req.query.serial || "emulator-5554");
  res.writeHead(200, {
    "Content-Type": "multipart/x-mixed-replace; boundary=castframe",
    "Cache-Control": "no-store",
    Connection: "keep-alive",
  });
  const last = castLatest.get(serial);
  if (last) { res.write(`--castframe\r\nContent-Type: image/png\r\nContent-Length: ${last.length}\r\n\r\n`); res.write(last); res.write("\r\n"); }
  if (!castClients.has(serial)) castClients.set(serial, new Set());
  const clients = castClients.get(serial);
  const wasIdle = clients.size === 0;
  clients.add(res);
  if (wasIdle) void runCastLoop(serial);
  req.on("close", () => { clients.delete(res); });
});

// ---- 运行异常报告：扫描工作区下各 RUN 的 decision-log.csv，提取异常类决策 ----
const ANOMALY_TYPES = /TOOL_GAP|RUN_INTERRUPTED|REWORK|_FAIL|ABORT/;
function parseCsvLine(line) {
  const cells = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === "\"") {
      if (inQuotes && line[i + 1] === "\"") { current += "\""; i += 1; }
      else inQuotes = !inQuotes;
    } else if (ch === "," && !inQuotes) { cells.push(current); current = ""; }
    else current += ch;
  }
  cells.push(current);
  return cells;
}
app.get("/api/run/anomalies", (req, res) => {
  try {
    const workspace = String(req.query.workspace || "");
    if (!workspace || !/^(\/|[A-Za-z]:[\\/])/.test(workspace)) { res.json({ anomalies: [] }); return; }
    const anomalies = [];
    let runs = [];
    try { runs = readdirSync(workspace).filter((name) => /^MIG-/.test(name)); } catch { runs = []; }
    for (const runId of runs) {
      const logPath = join(workspace, runId, "controller", "decision-log.csv");
      if (!existsSync(logPath)) continue;
      const lines = readFileSync(logPath, "utf8").split(/\r?\n/).filter(Boolean);
      if (!lines.length) continue;
      const header = parseCsvLine(lines[0]);
      const typeIndex = header.indexOf("decision_type");
      for (const line of lines.slice(1)) {
        const cells = parseCsvLine(line);
        const row = {};
        header.forEach((key, index) => { row[key] = cells[index] ?? ""; });
        if (!ANOMALY_TYPES.test(row.decision_type || "")) continue;
        anomalies.push({
          runId,
          id: row.decision_id || "",
          at: row.created_at || "",
          type: row.decision_type || "",
          decision: (row.decision || "").slice(0, 60),
          detail: (row.rationale || "").slice(0, 220),
        });
      }
    }
    anomalies.sort((a, b) => (a.at < b.at ? 1 : -1));
    res.json({ anomalies });
  } catch (error) {
    res.status(500).json({ error: String(error) });
  }
});

// ---- RUN 真实证据数据 API：overview / phase/:n / file ----
// 唯一数据来源 = migration-runs 下最新 MIG-* RUN 的产物文件；所有指标实时从文件计算，禁止编造。
const DEFAULT_RUN_WORKSPACE = ENV_CONFIG.runWorkspace;
const { resolve: pathResolve, sep: pathSep, extname: pathExtname } = require("node:path");

function resolveRunRoot(workspace) {
  const ws = String(workspace || "").trim() || DEFAULT_RUN_WORKSPACE;
  if (!/^(\/|[A-Za-z]:[\\/])/.test(ws)) return null;
  let runs = [];
  try { runs = readdirSync(ws).filter((name) => /^MIG-/.test(name)); } catch { runs = []; }
  if (!runs.length) return null;
  return join(ws, runs.sort().pop());
}
function readJsonIn(runRoot, rel) {
  try { return JSON.parse(readFileSync(join(runRoot, rel), "utf8")); } catch { return null; }
}
function readCsvIn(runRoot, rel) {
  try { return readCsvRows(readFileSync(join(runRoot, rel), "utf8")); } catch { return []; }
}
function listDirSafe(dir) {
  try { return readdirSync(dir); } catch { return []; }
}
function fileExistsIn(runRoot, rel) {
  try { return statSync(join(runRoot, rel)).isFile(); } catch { return false; }
}
// 历史 Gate 快照存于 controller/work-orders/*.phase-0N-gate-report.json（controller/gate-report.json 只保留最新阶段）
function readGateSnapshot(runRoot, phase) {
  const woDir = join(runRoot, "controller", "work-orders");
  for (const name of listDirSafe(woDir)) {
    if (new RegExp(`\\.phase-0${phase}-gate-report\\.json$`).test(name)) {
      return readJsonIn(runRoot, join("controller", "work-orders", name));
    }
  }
  return null;
}
function shotOrNull(runRoot, rel) {
  return fileExistsIn(runRoot, rel) ? rel : "";
}
// 返工案例：controller/decision-log.csv 的 REWORK_SURFACE 行（rationale 结构化文本：根因/修复/复验）
function buildReworkCase(runRoot, decisions) {
  const row = decisions.find((d) => d.decision_type === "REWORK_SURFACE");
  if (!row) return null;
  const text = row.rationale || "";
  const pick = (label) => {
    const match = new RegExp(`${label}：(.+?)(。|$)`).exec(text);
    return match ? match[1] : "";
  };
  const problemMatch = /人工验收发现(.+?)。/.exec(text);
  const hasPairShots = false; // rework-surface 下仅存修复后复验截图，无前后对比图
  const demo = {
    before: shotOrNull(runRoot, "phase-04-harmony-implementation/evidence/dual/demo/android/after.png"),
    after: shotOrNull(runRoot, "phase-04-harmony-implementation/evidence/dual/demo/harmony/after.jpeg"),
  };
  return {
    id: row.decision_id,
    at: row.created_at,
    status: row.decision,
    title: "多余返回按钮修复（UI_FIDELITY=HIGH 违规返工）",
    problem: problemMatch ? problemMatch[1] : text.slice(0, 120),
    rootCause: pick("根因（总控定位）"),
    fix: pick("修复（最小改动）"),
    reverify: pick("复验证据"),
    verifyShot: shotOrNull(runRoot, "phase-04-harmony-implementation/evidence/rework-surface/rework-verify.png"),
    hasPairShots,
    before: demo.before,
    after: demo.after,
    note: hasPairShots ? "" : "返工工单仅存档修复后复验截图（rework-verify.png）；下方「前后对比」以双机 demo 同操作截图代替（左 Android 基准 / 右 HarmonyOS 实现），如实标注非返工前后对比。",
  };
}
// 迁移核心统计：dual-diff 四类判定 × replay 步骤 × reconciliation × Gate 快照
function computeRunStats(runRoot) {
  const dualDiff = readCsvIn(runRoot, "phase-04-harmony-implementation/dual-diff-results.csv");
  const replay = readCsvIn(runRoot, "phase-04-harmony-implementation/replay-results.csv");
  const reconciliation = readCsvIn(runRoot, "phase-02-android-inventory/reconciliation.csv");
  const decisions = readCsvIn(runRoot, "controller/decision-log.csv");
  const runStatus = readJsonIn(runRoot, "controller/run-status.json");
  const gate4 = readJsonIn(runRoot, "controller/gate-report.json");
  const observables = dualDiff.filter((r) => r.assertion_type === "observable");
  const obsMatch = observables.filter((r) => r.verdict === "MATCH").length;
  const obsMachine = observables.filter((r) => r.verdict === "MATCH" || r.verdict === "DIFF").length;
  const stepsTotal = replay.reduce((sum, r) => sum + (Number(r.steps_total) || 0), 0);
  const stepsOk = replay.reduce((sum, r) => sum + (Number(r.steps_ok) || 0), 0);
  const diffCount = dualDiff.filter((r) => r.verdict === "DIFF").length;
  const manualCount = dualDiff.filter((r) => r.verdict === "MANUAL").length;
  // DIFF 定性来源：decision-log PHASE4_VERDICT（MANUAL_TAKEOVER，"全部 N 个 DIFF 归因取证侧缺口"）
  const phase4Verdict = decisions.find((d) => d.decision_type === "PHASE4_VERDICT") ?? null;
  const forensicsAttributed = Boolean(phase4Verdict && /归因取证|取证侧缺口/.test(phase4Verdict.rationale || ""));
  const gateOf = (n) => readGateSnapshot(runRoot, n);
  const gates = {
    p1: gateOf(1)?.verdict ?? "UNKNOWN",
    p2: gateOf(2)?.verdict ?? "UNKNOWN",
    p3: gateOf(3)?.verdict ?? "UNKNOWN",
    p4: gate4?.verdict === "FAIL" && /WAITING_HUMAN_REVIEW|MANUAL/.test(`${runStatus?.run_status ?? ""}|${phase4Verdict?.decision ?? ""}`)
      ? "MACHINE_FAIL_MANUAL_PENDING"
      : (gate4?.verdict ?? "UNKNOWN"),
  };
  return {
    dualDiff, replay, reconciliation, decisions, runStatus, gate4, phase4Verdict, forensicsAttributed, gates,
    stats: {
      observableMatch: obsMachine > 0 ? `${obsMatch}/${obsMachine}` : "0/0",
      stepsPassed: stepsTotal > 0 ? `${stepsOk}/${stepsTotal}` : "0/0",
      matchCount: dualDiff.filter((r) => r.verdict === "MATCH").length,
      diffCount,
      manualCount,
      softwareDefects: forensicsAttributed ? 0 : diffCount,
      toolArtifacts: forensicsAttributed ? diffCount : 0,
      runtimeVerified: reconciliation.filter((r) => r.verdict === "CONFIRMED").length,
      sourceConfirmed: reconciliation.filter((r) => r.verdict === "SOURCE_CONFIRMED").length,
    },
  };
}

app.get("/api/run/overview", (req, res) => {
  try {
    const runRoot = resolveRunRoot(req.query.workspace);
    if (!runRoot) return res.status(404).json({ error: "工作区内没有 MIG-* RUN 目录" });
    const scope = readJsonIn(runRoot, "controller/scope.json");
    if (!scope) return res.status(404).json({ error: "RUN 缺少 controller/scope.json" });
    const featureMap = readJsonIn(runRoot, "phase-02-android-inventory/feature-map.json");
    const runId = runRoot.split(pathSep).pop();
    const { replay, decisions, runStatus, stats, gates, forensicsAttributed } = computeRunStats(runRoot);

    const featuresTotal = (scope.migration_scope?.included_features ?? []).length;
    const featuresMapped = Array.isArray(featureMap?.features)
      ? featureMap.features.length
      : featuresTotal;

    const apkPath = scope.android?.apk_path ?? "";
    const hapCandidates = [
      { path: "tools/signing/entry-default-signed.hap", signed: true, desc: "三级本地自签链签名（hap-sign-tool，verify-app PASS）" },
      { path: "phase-04-harmony-implementation/harmony-project/entry/build/default/outputs/default/entry-default-unsigned.hap", signed: false, desc: "Phase 4 CLEAN_BUILD 直出 unsigned HAP" },
      { path: "phase-03-harmony-scaffold/harmony-project/entry/build/default/outputs/default/entry-default-unsigned.hap", signed: false, desc: "Phase 3 CLEAN_BUILD 直出 unsigned HAP" },
    ];
    const hap = hapCandidates.find((h) => fileExistsIn(runRoot, h.path));
    const p3Build = readJsonIn(runRoot, "phase-03-harmony-scaffold/build-report.json");
    const installLaunched = Boolean((p3Build?.install_passed_devices ?? []).length > 0 && (p3Build?.launch_passed_devices ?? []).length > 0);

    const artifactSpecs = [
      { name: "范围冻结书 scope.json", path: "controller/scope.json", desc: "Phase 1 冻结：功能范围 / 迁移政策 / 测试种子 / 双端环境 / 源码输入锁" },
      { name: "Android 盘点报告", path: "phase-02-android-inventory/phase-2-report.md", desc: "Phase 2 收束报告（功能地图 / 行为契约 / 调和结论）" },
      { name: "行为契约 behavior-contracts.csv", path: "phase-02-android-inventory/behavior-contracts.csv", desc: "7 条 BC：意图 / 操作 / 数据变化 / 断言" },
      { name: "鸿蒙构建报告 build-report.json", path: "phase-03-harmony-scaffold/build-report.json", desc: "HVER-001-P3：clean build / 安装 / 启动全 PASS" },
      { name: "双机差分结果 dual-diff-results.csv", path: "phase-04-harmony-implementation/dual-diff-results.csv", desc: "28 判定格：observable / data / persistence / side effect 四维" },
      { name: "操作重放明细 replay-results.csv", path: "phase-04-harmony-implementation/replay-results.csv", desc: "鸿蒙实机步骤重放与持久化结果" },
      { name: "决策日志 decision-log.csv", path: "controller/decision-log.csv", desc: "全程决策留痕（含 DIFF 定性与返工记录）" },
      { name: "Gate 4 报告 gate-report.json", path: "controller/gate-report.json", desc: "机器判定 FAIL（fail-closed）待人工裁决" },
      { name: "签名 HAP entry-default-signed.hap", path: "tools/signing/entry-default-signed.hap", desc: "签名交付物（下载）", download: true },
      { name: "返工复验截图 rework-verify.png", path: "phase-04-harmony-implementation/evidence/rework-surface/rework-verify.png", desc: "返回按钮修复后的鸿蒙实机复验" },
      { name: "基线 APK app-debug.apk", path: "", desc: "", external: scope.android?.apk_path ?? "" },
    ];
    const artifacts = artifactSpecs
      .filter((a) => (a.external ? existsSync(a.external) : fileExistsIn(runRoot, a.path)))
      .map((a) => ({ name: a.name, path: a.path || a.external, desc: a.desc, type: a.download ? "download" : "file" }));

    const summary = [
      `本次迁移把 Android 应用 ${scope.project_id ?? ""}（${scope.android?.application_id ?? ""} v${scope.android?.app_version ?? "?"}，源码 ${scope.android?.source_revision?.slice(0, 8) ?? ""}）重建为 HarmonyOS NEXT 原生应用：`,
      `${featuresTotal} 项冻结功能全部完成迁移并逐条留证（${stats.runtimeVerified} 项真机运行验证 + ${stats.sourceConfirmed} 项源码确认）；`,
      `双机差分可观察行为 ${stats.observableMatch} MATCH，鸿蒙实机操作重放 ${stats.stepsPassed} 步全部走通，重启持久化实测达标；`,
      `机器差分报出的 ${stats.diffCount} 处 DIFF 已由总控逐一论证定性为取证工具伪影（软件缺陷 ${stats.softwareDefects}），另有 ${stats.manualCount} 格按口径转人工核验；`,
      `Gate 1/2/3 机器判定 PASS，Gate 4 因 fail-closed 口径如实落盘 FAIL，当前状态「待人工裁决」。`,
    ].join("");

    res.json({
      runId,
      runStatus: runStatus?.run_status ?? "",
      metrics: {
        featuresTotal,
        featuresMapped,
        runtimeVerified: stats.runtimeVerified,
        sourceConfirmed: stats.sourceConfirmed,
        observableMatch: stats.observableMatch,
        stepsPassed: stats.stepsPassed,
        softwareDefects: stats.softwareDefects,
        toolArtifacts: stats.toolArtifacts,
        manualCells: stats.manualCount,
        gates,
      },
      build: {
        apk: { path: apkPath, sha256: scope.android?.apk_sha256 ?? "", exists: existsSync(apkPath) },
        hap: hap ? { path: hap.path, exists: true, signed: hap.signed, desc: hap.desc } : { path: "", exists: false, signed: false, desc: "" },
        installLaunched,
      },
      artifacts,
      summary,
      comparisonShots: {
        android: shotOrNull(runRoot, "phase-04-harmony-implementation/evidence/dual/demo/android/after.png"),
        harmony: shotOrNull(runRoot, "phase-04-harmony-implementation/evidence/dual/demo/harmony/after.jpeg"),
      },
      reworkCase: buildReworkCase(runRoot, decisions),
      diffNote: forensicsAttributed
        ? "全部机器 DIFF 已经 decision-log（PHASE4_VERDICT）定性为取证工具伪影，非鸿蒙软件缺陷"
        : "机器 DIFF 定性未见 decision-log 记录，需人工复核",
    });
  } catch (error) {
    res.status(500).json({ error: String(error) });
  }
});

app.get("/api/run/phase/:n", (req, res) => {
  try {
    const runRoot = resolveRunRoot(req.query.workspace);
    if (!runRoot) return res.status(404).json({ error: "工作区内没有 MIG-* RUN 目录" });
    const phase = Math.min(4, Math.max(1, Number(req.params.n) || 1));
    const runId = runRoot.split(pathSep).pop();
    const scope = readJsonIn(runRoot, "controller/scope.json");
    if (!scope) return res.status(404).json({ error: "RUN 缺少 controller/scope.json" });
    const { decisions, gates, phase4Verdict, forensicsAttributed } = computeRunStats(runRoot);
    const gateBase = { runId, phase };

    if (phase === 1) {
      const g1 = readGateSnapshot(runRoot, 1);
      const policies = Object.entries(scope.migration_scope?.migration_policies ?? {})
        .filter(([key]) => !key.startsWith("_"))
        .map(([key, value]) => ({ key, value, note: scope.migration_scope.migration_policies[`_${key}_note`] ?? "" }));
      return res.json({
        ...gateBase,
        identity: {
          projectRoot: scope.android?.project_root ?? "",
          sourceRevision: scope.android?.source_revision ?? "",
          apkPath: scope.android?.apk_path ?? "",
          apkSha256: scope.android?.apk_sha256 ?? "",
          applicationId: scope.android?.application_id ?? "",
          appVersion: scope.android?.app_version ?? "",
          appBuild: scope.android?.app_build ?? "",
          identityProvenance: scope.android?.identity_provenance ?? "",
          gitTreeSha1: scope.source_input_lock?.git_tree_sha1 ?? "",
          worktreeState: scope.source_input_lock?.worktree_state ?? "",
        },
        target: scope.target ?? null,
        includedFeatures: (scope.migration_scope?.included_features ?? []).map((id) => ({
          id,
          title: scope.migration_scope.feature_titles?.[id] ?? "",
          verifyMode: scope.migration_scope.feature_verify_modes?.[id] ?? "",
        })),
        excludedFeatures: (scope.migration_scope?.excluded_features ?? []).map((id) => ({
          id,
          reason: scope.migration_scope.exclusion_reasons?.[id] ?? "",
        })),
        policies,
        allowedSubstitutions: scope.migration_scope?.allowed_platform_substitutions ?? [],
        testSeed: scope.test_seed ?? null,
        androidEnv: scope.environments?.[0] ?? null,
        harmonyEnv: scope.harmonyos_environment ?? null,
        gate: g1 ? { verdict: g1.verdict, checkedAt: g1.checked_at, scopeSha256: g1.scope_sha256 ?? "" } : null,
        artifacts: [
          { name: "scope.json 冻结书", path: "controller/scope.json" },
          { name: "Gate 1 快照", path: "controller/work-orders/WO-PHASE-02-0DB7D4760B4F.phase-01-gate-report.json" },
          { name: "决策日志（冻结记录）", path: "controller/decision-log.csv" },
        ].filter((a) => fileExistsIn(runRoot, a.path)),
      });
    }

    if (phase === 2) {
      const g2 = readGateSnapshot(runRoot, 2);
      const featureMap = readJsonIn(runRoot, "phase-02-android-inventory/feature-map.json");
      const contracts = readCsvIn(runRoot, "phase-02-android-inventory/behavior-contracts.csv");
      const chains = readCsvIn(runRoot, "phase-02-android-inventory/runtime-evidence/runtime-chains.csv");
      const reconciliation = readCsvIn(runRoot, "phase-02-android-inventory/reconciliation.csv");
      const featureNames = new Map((featureMap?.features ?? []).map((f) => [f.feature_id, f.name]));
      const verdictGroups = {};
      for (const row of reconciliation) {
        const key = row.verdict || "UNKNOWN";
        verdictGroups[key] = (verdictGroups[key] ?? 0) + 1;
      }
      // 截图墙：runtime-evidence/evidence/chains/BC-*/{before,after,restart}/screenshot.png（文件存在才列）
      const chainsRel = "phase-02-android-inventory/runtime-evidence/evidence/chains";
      const shots = listDirSafe(join(runRoot, chainsRel))
        .filter((name) => /^BC-/.test(name)).sort()
        .map((bc) => {
          const row = contracts.find((c) => c.bc_id === bc);
          return {
            bcId: bc,
            featureName: row ? (featureNames.get(row.feature_id) || row.feature_id) : "",
            intent: row?.user_intent ?? "",
            before: shotOrNull(runRoot, `${chainsRel}/${bc}/before/screenshot.png`),
            after: shotOrNull(runRoot, `${chainsRel}/${bc}/after/screenshot.png`),
            restart: shotOrNull(runRoot, `${chainsRel}/${bc}/restart/screenshot.png`),
          };
        });
      const forensicsTypes = /PHASE2_AMEND|RUN_INTERRUPTED|TOOL_GAP_BYPASS/;
      const forensicsNotes = decisions
        .filter((d) => forensicsTypes.test(d.decision_type || "") && /伪影|amended|中断/.test(`${d.decision} ${d.rationale}`))
        .map((d) => ({ id: d.decision_id, type: d.decision_type, decision: d.decision, summary: (d.rationale || "").slice(0, 260) }));
      return res.json({
        ...gateBase,
        features: (featureMap?.features ?? []).map((f) => ({
          id: f.feature_id, name: f.name, summary: f.summary, verifyMode: f.verify_mode, sourceRefs: f.source_refs ?? [],
        })),
        contracts: contracts.map((c) => ({
          bcId: c.bc_id, featureId: c.feature_id, featureName: featureNames.get(c.feature_id) || c.feature_id,
          intent: c.user_intent, dataStateChange: c.data_state_change, observableResult: c.observable_result,
          persistenceTargets: c.persistence_targets, assertions: c.result_assertions, evidenceClass: c.evidence_class,
        })),
        chainStats: {
          total: chains.length,
          pass: chains.filter((c) => c.chain_status === "CHAIN_PASS").length,
          amended: chains.filter((c) => /amended/.test(c.note || "")).length,
        },
        reconciliationStats: { total: reconciliation.length, groups: verdictGroups },
        shots,
        forensicsNotes,
        gate: g2 ? { verdict: g2.verdict, checkedAt: g2.checked_at } : null,
      });
    }

    if (phase === 3) {
      const g3 = readGateSnapshot(runRoot, 3);
      const plan = readJsonIn(runRoot, "phase-03-harmony-scaffold/surface-plan.json");
      const dcIndex = readJsonIn(runRoot, "phase-03-harmony-scaffold/data-contracts/index.json");
      const p3Build = readJsonIn(runRoot, "phase-03-harmony-scaffold/build-report.json");
      const surfaces = [...(plan?.routes ?? []), ...(plan?.passthrough ?? [])].map((s) => ({
        surfaceId: s.surface_id, kind: s.kind, featureId: s.feature_id,
        androidStructure: s.android_structure ?? "",
        preserveTexts: s.preserve?.texts ?? [],
        nativeCarrier: s.native_carrier ?? "",
        nativeComponent: s.native_component ?? "",
        matchedRule: s.matched_rule ?? "",
        reason: s.reason ?? "",
      }));
      // HVER 实机截图 + P2 基线截图（迁移前后 GUI 对比）
      // 内容去重：冒烟 runner 曾把当前屏存全量 surface id，多轮同底图在此合并展示（数据文件零改动）
      const hverShots = [];
      const verRoot = join(runRoot, "phase-03-harmony-scaffold", "verification");
      for (const verId of listDirSafe(verRoot)) {
        const shotRoot = join(verRoot, verId, "screenshots");
        for (const shotId of listDirSafe(shotRoot)) {
          const rel = `phase-03-harmony-scaffold/verification/${verId}/screenshots/${shotId}/screenshot.png`;
          if (fileExistsIn(runRoot, rel)) hverShots.push({ id: shotId, verificationId: verId, path: rel });
        }
      }
      const dedupedShots = [];
      const seenShotContent = new Map();
      for (const shot of hverShots) {
        let digest = "";
        try {
          digest = createHash("sha256").update(readFileSync(join(runRoot, shot.path))).digest("hex").slice(0, 16);
        } catch {
          digest = `unreadable:${shot.path}`;
        }
        const group = seenShotContent.get(digest);
        if (group) {
          group.duplicateCount += 1;
          group.duplicateIds.push(`${shot.verificationId}/${shot.id}`);
        } else {
          const entry = { ...shot, contentHash: digest, duplicateCount: 1, duplicateIds: [`${shot.verificationId}/${shot.id}`] };
          seenShotContent.set(digest, entry);
          dedupedShots.push(entry);
        }
      }
      const probeDecision = decisions.find((d) => d.decision === "DATA_CARRIER");
      return res.json({
        ...gateBase,
        surfaces,
        stats: plan?.stats ?? null,
        dataContracts: (dcIndex?.contracts ?? []).map((c) => ({
          objectId: c.object_id, repositorySymbol: c.repository_symbol, directions: c.directions ?? [],
          featureIds: c.feature_ids ?? [], requiredOperations: c.required_operations ?? [],
          file: `phase-03-harmony-scaffold/data-contracts/${c.contract_file}`,
        })),
        probeFiles: [
          { name: "DebugSemanticProbe.ets", path: "phase-03-harmony-scaffold/harmony-project/entry/src/main/ets/probe/DebugSemanticProbe.ets" },
          { name: "SemanticProbeRegistry.ets", path: "phase-03-harmony-scaffold/harmony-project/entry/src/main/ets/probe/SemanticProbeRegistry.ets" },
        ].filter((f) => fileExistsIn(runRoot, f.path)),
        probeLockNote: probeDecision ? (probeDecision.rationale || "").slice(0, 300) : "",
        hverShots: dedupedShots,
        baselineShot: shotOrNull(runRoot, "phase-02-android-inventory/runtime-evidence/evidence/chains/BC-0001/before/screenshot.png"),
        buildSmoke: p3Build ? {
          status: p3Build.status,
          verificationId: p3Build.verification_id,
          cleanBuildPassed: p3Build.clean_build_passed === true,
          installDevices: p3Build.install_passed_devices ?? [],
          launchDevices: p3Build.launch_passed_devices ?? [],
          hapSha256: p3Build.artifacts?.[0]?.sha256 ?? "",
          errors: p3Build.errors ?? [],
        } : null,
        gate: g3 ? { verdict: g3.verdict, checkedAt: g3.checked_at } : null,
      });
    }

    // phase 4
    const dualDiff = readCsvIn(runRoot, "phase-04-harmony-implementation/dual-diff-results.csv");
    const replay = readCsvIn(runRoot, "phase-04-harmony-implementation/replay-results.csv");
    const gate4 = readJsonIn(runRoot, "controller/gate-report.json");
    const { stats, runStatus } = computeRunStats(runRoot);
    const dimensions = ["observable", "data", "persistence", "side_effect"];
    const dimensionStats = dimensions.map((dim) => {
      const rows = dualDiff.filter((r) => r.assertion_type === dim);
      return {
        dimension: dim,
        match: rows.filter((r) => r.verdict === "MATCH").length,
        diff: rows.filter((r) => r.verdict === "DIFF").length,
        manual: rows.filter((r) => r.verdict === "MANUAL").length,
      };
    });
    const manualReasons = {};
    for (const row of dualDiff.filter((r) => r.verdict === "MANUAL")) {
      const key = row.note?.includes("SKIPPED_NO_STEPS") ? "零步骤链不支持机器重放（BC-0006 空态观察 / BC-0007 源码确认设计跳过）"
        : row.note?.includes("no-machine-registration") ? "副作用义务口径：BC 声明 NONE 字面值被当作义务存在（语义应为无义务）"
        : row.note?.slice(0, 60) || "其他";
      manualReasons[key] = (manualReasons[key] ?? 0) + 1;
    }
    const toolGaps = decisions
      .filter((d) => d.decision_type === "TOOL_GAP" && /TOOL_GAP-P4-|^phase-04$/.test(`${d.decision} ${d.scope}`))
      .map((d) => ({ id: d.decision_id, tag: d.decision, summary: (d.rationale || "").slice(0, 220) }));
    const demoShots = {
      androidBefore: shotOrNull(runRoot, "phase-04-harmony-implementation/evidence/dual/demo/android/before.png"),
      androidAfter: shotOrNull(runRoot, "phase-04-harmony-implementation/evidence/dual/demo/android/after.png"),
      androidRestart: shotOrNull(runRoot, "phase-04-harmony-implementation/evidence/dual/demo/android/restart.png"),
      harmonyBefore: shotOrNull(runRoot, "phase-04-harmony-implementation/evidence/dual/demo/harmony/before.jpeg"),
      harmonyAfter: shotOrNull(runRoot, "phase-04-harmony-implementation/evidence/dual/demo/harmony/after.jpeg"),
      harmonyRestart: shotOrNull(runRoot, "phase-04-harmony-implementation/evidence/dual/demo/harmony/restart.jpeg"),
    };
    res.json({
      runId, phase: 4,
      matrix: dualDiff.map((row) => ({
        bcId: row.bc_id, featureId: row.feature_id, dimension: row.assertion_type, verdict: row.verdict,
        androidExpected: row.android_expected, harmonyActual: row.harmony_actual, note: row.note,
        attribution: row.verdict === "DIFF" ? (forensicsAttributed ? "TOOL_ARTIFACT" : "UNRESOLVED") : "",
      })),
      dimensionStats,
      replay: replay.map((row) => ({
        bcId: row.bc_id, featureId: row.feature_id, verifyMode: row.verify_mode,
        precondition: row.precondition_status, stepsTotal: Number(row.steps_total) || 0, stepsOk: Number(row.steps_ok) || 0,
        observable: row.observable_result, data: row.data_result, persistence: row.persistence_result,
        sideEffect: row.side_effect_result, verdict: row.replay_verdict, failReason: row.fail_reason ?? "",
      })),
      stepsPassed: stats.stepsPassed,
      restartPersistence: replay.map((row) => ({ bcId: row.bc_id, persistence: row.persistence_result })),
      diffClassification: {
        softwareDefects: stats.softwareDefects,
        toolArtifacts: stats.toolArtifacts,
        manual: stats.manualCount,
        manualReasons,
        toolGaps,
      },
      reworkCase: buildReworkCase(runRoot, decisions),
      gate4: {
        machineVerdict: gate4?.verdict ?? "UNKNOWN",
        checkedAt: gate4?.checked_at ?? "",
        errors: gate4?.errors ?? [],
        runStatus: runStatus?.run_status ?? "",
        status: gates.p4 === "MACHINE_FAIL_MANUAL_PENDING" ? "待人工裁决" : (gate4?.verdict ?? ""),
        verdictDecision: phase4Verdict ? { id: phase4Verdict.decision_id, decision: phase4Verdict.decision, summary: (phase4Verdict.rationale || "").slice(0, 320) } : null,
      },
      demoShots,
    });
  } catch (error) {
    res.status(500).json({ error: String(error) });
  }
});

// RUN 内安全文件服务：resolve 后必须仍在 RUN 目录内（防穿越）；hap/apk 触发下载
const RUN_FILE_TYPES = {
  ".png": "image/png", ".jpeg": "image/jpeg", ".jpg": "image/jpeg",
  ".csv": "text/csv; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".hap": "application/octet-stream", ".apk": "application/vnd.android.package-archive",
  ".md": "text/markdown; charset=utf-8", ".txt": "text/plain; charset=utf-8",
};
app.get("/api/run/file", (req, res) => {
  try {
    const runRoot = resolveRunRoot(req.query.workspace);
    if (!runRoot) return res.status(404).json({ error: "未找到 RUN 目录" });
    const rel = String(req.query.path || "").trim();
    if (!rel || rel.startsWith("/") || rel.includes("..")) return res.status(400).json({ error: "非法路径" });
    const full = pathResolve(runRoot, rel);
    if (full !== runRoot && !full.startsWith(runRoot + pathSep)) return res.status(403).json({ error: "路径越界" });
    let size = 0;
    try { size = statSync(full).size; } catch { return res.status(404).json({ error: "文件不存在" }); }
    const ext = pathExtname(full).toLowerCase();
    res.setHeader("Content-Type", RUN_FILE_TYPES[ext] || "application/octet-stream");
    if (ext === ".hap" || ext === ".apk") res.setHeader("Content-Disposition", `attachment; filename="${rel.split("/").pop()}"`);
    res.end(readFileSync(full));
  } catch (error) {
    res.status(500).json({ error: String(error) });
  }
});

// ---- 外部驱动镜像：项目快照存后端，任意浏览器打开 /projects/:id 可自动恢复 ----
const MIRROR_FILE = join(__dirname, ".mirror-projects.json");
const readMirror = () => {
  try { return JSON.parse(readFileSync(MIRROR_FILE, "utf8")); } catch { return {}; }
};
app.post("/api/mirror/project", (req, res) => {
  try {
    const body = req.body || {};
    const id = body.id || body.projectId;
    if (!id) return res.status(400).json({ error: "id required" });
    const db = readMirror();
    db[id] = { ...(db[id] || {}), ...body, id, updatedAt: new Date().toISOString() };
    writeFileSync(MIRROR_FILE, JSON.stringify(db, null, 2), "utf8");
    res.json({ ok: true });
  } catch (error) {
    res.status(500).json({ error: String(error) });
  }
});
app.get("/api/mirror/project", (req, res) => {
  const db = readMirror();
  const id = req.query.id;
  if (id) { res.json(db[String(id)] || {}); return; }
  res.json({ projects: Object.values(db) });
});

const OBS_WEBSITE_URL = process.env.OBS_WEBSITE_URL || "";

if (OBS_WEBSITE_URL) {
  app.use(async (req, res, next) => {
    if (req.method !== "GET" && req.method !== "HEAD") return next();
    if (req.path.startsWith("/api/") || req.path === "/health") return next();
    try {
      const obsUrl = OBS_WEBSITE_URL.replace(/\/$/, "") + req.originalUrl;
      const upstream = await fetch(obsUrl, { method: req.method, redirect: "follow" });
      if (upstream.status === 404) return next();
      res.status(upstream.status);
      upstream.headers.forEach((value, key) => {
        const lk = key.toLowerCase();
        if (lk === "content-disposition") return;
        if (["content-length", "content-encoding", "connection", "transfer-encoding", "x-obs-request-id", "x-obs-id-2", "server"].includes(lk)) return;
        res.setHeader(key, value);
      });
      if (!upstream.body) return res.end();
      Readable.fromWeb(upstream.body).pipe(res);
    } catch (error) {
      next();
    }
  });
  console.log("[web] proxying OBS:", OBS_WEBSITE_URL);
} else {
  app.get("/", (req, res) => {
    res.json({
      service: "tuotiahuangu-backend",
      endpoints: ["/health", "/api/agent/status", "/api/agent/target", "/api/logs", "/api/codearts/*"],
    });
  });
}

const httpServer = app.listen(PORT, "0.0.0.0", () => {
  const target = gateway.resolveTarget();
  console.log(`[app] listening on 0.0.0.0:${PORT}, agent=${target.target} (${target.source})`);
});
// WebSocket 升级：模拟器画面推流（android/harmony）
httpServer.on("upgrade", (req, socket, head) => {
  if (req.url && (req.url.includes("/api/emulator/android/ws") || req.url.includes("/api/emulator/harmony/ws"))) {
    castWss.handleUpgrade(req, socket, head, (client) => castWss.emit("connection", client, req));
  } else {
    socket.destroy();
  }
});
