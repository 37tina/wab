import { createDecipheriv, scryptSync, type DecipherGCM } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

function readBody(request: import("node:http").IncomingMessage) {
  return new Promise<Buffer>((resolve, reject) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk: Buffer | string) => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
    request.on("end", () => resolve(Buffer.concat(chunks)));
    request.on("error", reject);
  });
}

/** Read the AgentKernel password only into this process. The files are the
 * encrypted files written by CodeArts Agent itself; no plaintext is logged or
 * returned to the browser. Set CODEARTS_AUTO_AUTH=0 to disable this fallback.
 */
function readManagedCodeArtsPassword() {
  if (process.env.CODEARTS_AUTO_AUTH === "0") return undefined;
  const dataRoot = process.env.CODEARTS_DATA_DIR || join(homedir(), ".codeartsdoer", "codearts-data");
  const keyFile = join(dataRoot, "4", "data");
  const cipherFile = join(dataRoot, "custom-dir", "data");
  const metaFile = join(dataRoot, "1", "data");
  const saltFile = join(dataRoot, "2", "data");
  const ivFile = join(dataRoot, "3", "data");
  if (![keyFile, cipherFile, metaFile, saltFile, ivFile].every(existsSync)) return undefined;
  try {
    const secret = Buffer.from(readFileSync(keyFile, "utf8").trim(), "base64").toString("utf8");
    const cipher = JSON.parse(readFileSync(cipherFile, "utf8")) as { authTag: string; ciphertext: string };
    const algorithm = (JSON.parse(readFileSync(metaFile, "utf8")) as { algorithm: string }).algorithm;
    const salt = Buffer.from(JSON.parse(readFileSync(saltFile, "utf8")) as string, "base64");
    const iv = Buffer.from(JSON.parse(readFileSync(ivFile, "utf8")) as string, "base64");
    const key = scryptSync(secret, salt, 32, { N: 65536, r: 8, p: 1, maxmem: 128 * 1024 * 1024 });
    const decipher = createDecipheriv(algorithm, key, iv) as DecipherGCM;
    decipher.setAuthTag(Buffer.from(cipher.authTag, "base64"));
    return Buffer.concat([decipher.update(Buffer.from(cipher.ciphertext, "base64")), decipher.final()]).toString("utf8");
  } catch {
    return undefined;
  }
}

/**
 * Local-only bridge: the browser talks to Vite, while Vite forwards the
 * request to the CodeArts AgentKernel service on loopback. Credentials stay
 * in the browser session and are forwarded as an Authorization header.
 */
function codeArtsBridge(): Plugin {
  const handler = async (request: import("node:http").IncomingMessage, response: import("node:http").ServerResponse, next: () => void) => {
    const requestUrl = request.url ?? "/";
    if (!requestUrl.startsWith("/api/codearts/")) return next();
    if (request.method === "OPTIONS") {
      response.statusCode = 204;
      response.end();
      return;
    }
    const targetBase = process.env.CODEARTS_URL || `http://127.0.0.1:${process.env.CODEARTS_PORT || "27546"}`;
    const upstreamPath = requestUrl.slice("/api/codearts".length);
    const headers: Record<string, string> = {};
    const authorization = request.headers.authorization;
    if (authorization) headers.authorization = authorization;
    else {
      const password = process.env.CODEARTS_SERVER_PASSWORD || readManagedCodeArtsPassword();
      if (password) {
        const username = process.env.CODEARTS_SERVER_USERNAME || "codearts";
        headers.authorization = `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`;
      }
    }
    const contentType = request.headers["content-type"];
    if (contentType) headers["content-type"] = Array.isArray(contentType) ? contentType[0] : contentType;
    const accept = request.headers.accept;
    if (accept) headers.accept = Array.isArray(accept) ? accept[0] : accept;
    try {
      const body = request.method === "GET" || request.method === "HEAD" ? undefined : await readBody(request);
      const upstream = await fetch(new URL(upstreamPath, targetBase).toString(), {
        method: request.method,
        headers,
        body: body && body.length ? body : undefined,
      });
      response.statusCode = upstream.status;
      upstream.headers.forEach((value, key) => {
        if (!['content-length', 'content-encoding', 'connection', 'transfer-encoding'].includes(key)) response.setHeader(key, value);
      });
      if (!upstream.body) return response.end();
      Readable.fromWeb(upstream.body as import("node:stream/web").ReadableStream).pipe(response);
    } catch (error) {
      response.statusCode = 502;
      response.setHeader("Content-Type", "application/json; charset=utf-8");
      response.end(JSON.stringify({ error: "CodeArts Agent 服务不可达", detail: error instanceof Error ? error.message : String(error) }));
    }
  };
  return {
    name: "codearts-local-bridge",
    configureServer(server) {
      server.middlewares.use(handler);
    },
    configurePreviewServer(server) {
      server.middlewares.use(handler);
    },
  };
}

export default defineConfig({
  plugins: [react(), codeArtsBridge()],
  server: {
    port: 5173,
    host: "0.0.0.0"
  }
});
