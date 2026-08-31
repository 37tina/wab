import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 本地开发时浏览器请求 /api/* 由 Vite 转发到本仓库的 backend 网关（默认 127.0.0.1:8080）。
// CodeArts Agent 的端口发现、凭据解密与反向代理全部收敛在 backend（见 backend/agentGateway.js）。
const backendTarget = process.env.BACKEND_URL || "http://127.0.0.1:8080";
const apiProxy = { "/api": { target: backendTarget, changeOrigin: false } };

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: "0.0.0.0",
    proxy: apiProxy,
  },
  preview: {
    port: 4173,
    proxy: apiProxy,
  },
});
