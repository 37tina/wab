# 脱胎换骨 Web 初版

这是迁移流程工作台。新建任务时默认使用 CodeArts Space / AgentTeam：Phase 启动后创建本地 CodeArts 会话，选择 `team-leader`，调用 `prompt_async`，轮询真实会话消息，并在真实结果返回后进入人工审核。页面中的阶段门禁、会话 ID、推理和工具事件均来自该会话。

本地演示项目仍保留用于无 CodeArts 环境的界面预览，但会明确标记为 `DEMO DATA`，不会与真实执行混淆。

## CodeArts 连接架构

CodeArts Agent（AgentKernel）与网页服务同机运行，启动端口不固定。连接链路统一收敛到本仓库 backend 网关：

```
浏览器 → Vite (5173, 纯静态 + /api 转发) → backend 网关 (8080) → 本机 CodeArts Agent
```

- **端口自动发现**：Agent 启动时会把真实端口写入 `~/.codeartsdoer/CodeArts_Agent/<版本目录>/server_config.properties`，网关读取该文件（校验 pid 存活，5 秒缓存）确定目标，不再写死端口。目标优先级：`CODEARTS_URL`/`AGENT_BASE_URL` 环境变量 → 界面手动指定（仅限本机地址，`PUT /api/agent/target`）→ 自动发现 → 默认 27546。
- **凭据**：浏览器携带的 Authorization > `CODEARTS_SERVER_PASSWORD` 环境变量 > 解密 Agent 本机托管凭据（`CODEARTS_AUTO_AUTH=0` 关闭）。
- **状态可见**：`GET /api/agent/status` 返回目标地址、来源、pid/版本、健康与延迟；前端每 20 秒轮询，顶栏状态点与连接对话框实时反映，代理 502 会把真实 `detail` 与 `hint` 透传到界面。
- **工作区目录由用户指定**：新建迁移任务时必须填写本机绝对路径作为 CodeArts 工作区目录（`GET /api/agent/workspace` 会即时检查目录是否存在），会话将在该目录中检出源码并构建；连接测试会话也可在连接对话框中指定测试目录，避免写入 Agent 安装目录。
- **模型管理（Space / AgentTeam）**：连接对话框 →「模型管理」展示客户端已有模型（读取同一份 `codearts.json`，apiKey 仅掩码显示）；「添加模型」对话框与客户端一致（模型提供商 / 自定义配置两个页签），新增/删除由网关合并写回配置文件（写前自动备份，网页创建的服务商删空后自动移除）。注意 Agent 内核不热加载配置，新增的模型需**重启 CodeArts Agent** 后才在客户端与执行中生效；运行控制面板可选择执行使用的模型并随 `prompt_async` 下发。
- Agent 未运行时页面保持可用（DEMO 数据照常），真实执行入口会给出具体排查提示。

## 启动

本地开发需要同时跑后端网关与前端（Agent 相关请求都经过后端）：

```bash
# 终端 1：后端网关（必需）
cd backend && npm install && npm start   # 0.0.0.0:8080

# 终端 2：前端
cd web && npm install && npm run dev
```

打开 `http://localhost:5173`。后端地址可用 `BACKEND_URL` 覆盖（默认 `http://127.0.0.1:8080`）。本机 CodeArts Agent 需已安装并登录（`~/.codeartsdoer`）；后端 MySQL 可选，未配置时仅访问日志不可用，不影响 CodeArts 功能。

## 验证

```bash
npm run build
npm test -- --run
```

GitHub 源码会在提示中要求 Agent 在 CodeArts 工作目录检出后再分析。浏览器选择的 ZIP 在当前初版只保存文件名；若要进行真实 ZIP 构建，需要后续增加上传到 CodeArts 工作目录的后端接口。
