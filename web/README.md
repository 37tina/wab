# 脱胎换骨 Web 初版

这是迁移流程工作台。新建任务时默认使用 CodeArts Space / AgentTeam：Phase 启动后创建本地 CodeArts 会话，选择 `team-leader`，调用 `prompt_async`，轮询真实会话消息，并在真实结果返回后进入人工审核。页面中的阶段门禁、会话 ID、推理和工具事件均来自该会话。

本地演示项目仍保留用于无 CodeArts 环境的界面预览，但会明确标记为 `DEMO DATA`，不会与真实执行混淆。

## 启动

```bash
npm install
npm run dev
```

打开 `http://localhost:5173`。CodeArts Agent 需要运行在 `http://127.0.0.1:27546`，Vite 本地桥接会转发 `/api/codearts/*` 并读取 Agent 的本机加密凭据。

## 验证

```bash
npm run build
npm test -- --run
```

GitHub 源码会在提示中要求 Agent 在 CodeArts 工作目录检出后再分析。浏览器选择的 ZIP 在当前初版只保存文件名；若要进行真实 ZIP 构建，需要后续增加上传到 CodeArts 工作目录的后端接口。
