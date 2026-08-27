# 脱胎换骨 Web 初版

这是一个单机可交互的迁移流程工作台原型。当前使用 `MockMigrationService` 和 `localStorage`，页面已经为后续真实 CodeArts、Android Runner 和 HarmonyOS Runner 预留服务接口。

## 启动

```bash
npm install
npm run dev
```

打开 `http://localhost:5173`。

## 验证

```bash
npm run build
npm test
```

新建任务后，Phase 1 会自动播放事件流；每个阶段会在 `REVIEW_REQUIRED` 状态暂停。项目总览中自带一个可从 Phase 4 回看的演示项目。

## 后续接入点

- 将 `MockMigrationService` 替换为 HTTP/SSE 实现。
- 将 `EmulatorPanel` 的 `streamType` 从 `mock` 替换为 `webrtc`、`mjpeg` 或 `video`。
- 将交付中心的本地 Blob 下载替换为对象存储产物地址。
## CodeArts Agent 本地接入（初版）

Vite 开发服务包含一个只转发本机请求的桥接：浏览器请求 `/api/codearts/*`，由 Vite 转发到
`http://127.0.0.1:27546`（可用 `CODEARTS_URL` 或 `CODEARTS_PORT` 覆盖）。桥接只转发
`Authorization`、`Content-Type` 和 `Accept` 请求头，不保存密码。

1. 启动本机 CodeArts Agent，使 AgentKernel 监听本地端口。
2. 打开工作台，点击左下角“演示环境 / 配置”，用户名可使用 `codearts`，密码留空即可由桥接自动读取本机 Agent 凭据；也支持手动输入。
3. 进入任意迁移任务，在右侧“运行控制”点击“发送到 CodeArts Agent”。这会创建一个
   OpenCode 兼容会话并发送当前 Phase 的验证提示词，等待真实模型响应。

手动输入的凭据只保存在当前浏览器 `sessionStorage`，关闭浏览器后自动清除；自动读取的密码只在 Vite 进程内存中使用。当前 Mock Phase 状态仍然
独立运行；后续可将 `promptCodeArtsSession` 的响应和 `/global/event` SSE 映射到
`AgentEvent`，再替换 `MockMigrationService`。

如果不希望在页面输入密码，也可以在启动 Vite 前设置 `CODEARTS_SERVER_PASSWORD`，并可选设置
`CODEARTS_SERVER_USERNAME`；桥接会在浏览器未携带 Authorization 时使用该环境变量。
