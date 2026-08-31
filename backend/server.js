const express = require("express");
const mysql = require("mysql2/promise");
const { Readable } = require("node:stream");
const { statSync, readFileSync, writeFileSync, readdirSync, existsSync } = require("node:fs");
const { join } = require("node:path");
const gateway = require("./agentGateway");
const skillGov = require("./skillGovernance");

const PORT = process.env.PORT || 8080;
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
const HDC_BIN = "/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc";
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
      ADB_BIN, ["-s", "emulator-5554", "exec-out",
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
    bringToFront();
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
  if (Date.now() - androidFrontmostAt < 60000) return;
  androidFrontmostAt = Date.now();
  execFile("osascript", ["-e", 'tell application "System Events" to set frontmost of process "qemu-system-aarch64" to true'], { timeout: 4000 }, () => {});
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
    execFile(HDC_BIN, ["-t", "127.0.0.1:5557", ...args], { timeout: 6000 }, (error, stdout, stderr) => {
      resolve({ ok: !error, out: String(stdout || stderr || "").slice(0, 200) });
    });
  });
}
// ADB 反向控制（Android 侧）

function adbRun(args) {
  return new Promise((resolve) => {
    execFile(ADB_BIN, ["-s", "emulator-5554", ...args], { timeout: 6000 }, (error, stdout, stderr) => {
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
const ADB_BIN = join(process.env.HOME ?? "", "Library/Android/sdk/platform-tools/adb");
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
