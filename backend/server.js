const express = require("express");
const mysql = require("mysql2/promise");
const { Readable } = require("node:stream");

const PORT = process.env.PORT || 8080;
const AGENT_BASE_URL = process.env.AGENT_BASE_URL || "http://127.0.0.1:27546";
const AGENT_USERNAME = process.env.CODEARTS_SERVER_USERNAME || "codearts";
const AGENT_PASSWORD = process.env.CODEARTS_SERVER_PASSWORD || "";
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
  res.status(200).json({
    status: "ok",
    service: "tuotiahuangu-backend",
    db,
    dbError: db || !dbError ? undefined : dbError,
    agentBase: AGENT_BASE_URL,
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

app.all("/api/codearts/*", async (req, res) => {
  const upstreamPath = req.originalUrl.slice("/api/codearts".length);
  const headers = {};
  if (req.headers.authorization) {
    headers.authorization = req.headers.authorization;
  } else if (AGENT_PASSWORD) {
    headers.authorization =
      "Basic " + Buffer.from(`${AGENT_USERNAME}:${AGENT_PASSWORD}`).toString("base64");
  }
  if (req.headers["content-type"]) headers["content-type"] = req.headers["content-type"];
  if (req.headers.accept) headers.accept = req.headers.accept;
  try {
    const upstream = await fetch(new URL(upstreamPath, AGENT_BASE_URL).toString(), {
      method: req.method,
      headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : JSON.stringify(req.body || {}),
    });
    res.status(upstream.status);
    upstream.headers.forEach((value, key) => {
      if (!["content-length", "content-encoding", "connection", "transfer-encoding"].includes(key)) {
        res.setHeader(key, value);
      }
    });
    if (!upstream.body) return res.end();
    Readable.fromWeb(upstream.body).pipe(res);
  } catch (error) {
    res.status(502).json({
      error: "CodeArts Agent 服务不可达",
      detail: error instanceof Error ? error.message : String(error),
      agentBase: AGENT_BASE_URL,
    });
  }
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
      endpoints: ["/health", "/api/logs", "/api/codearts/*"],
    });
  });
}

app.listen(PORT, "0.0.0.0", () => {
  console.log(`[app] listening on 0.0.0.0:${PORT}, agent=${AGENT_BASE_URL}`);
});