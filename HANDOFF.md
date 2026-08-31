# 项目交接状态（HANDOFF）

> 本文件是跨会话/长会话的状态锚点。改完东西请同步更新此文件。

## 服务启动

```bash
# 终端 1：后端网关（必须先启动）
cd backend && npm start          # 0.0.0.0:8080
# 终端 2：前端
cd web && npm run dev            # 5173，/api 转发到 8080（BACKEND_URL 可覆盖）
```

MySQL 可选（未配置只影响 /api/logs）。CodeArts Agent 必须本机运行（内核端口自动发现：`~/.codeartsdoer/CodeArts_Agent/<版本>/server_config.properties`）。

## 架构（核心不变量）

```
浏览器 → Vite(5173 静态) → backend 网关(8080) → CodeArts AgentKernel(动态端口, Basic Auth 自动解密)
```

- `backend/agentGateway.js`：端口发现 / 凭据解密 / 健康探测 / 模型管理（读写 `~/.codeartsdoer/codearts-data/codearts.json`，写前备份 .bak-时间戳；网页创建的服务商记录在 `codearts.json.web-managed.json`，删空自动移除壳）/ AgentTeam 团队状态（`/cag/agent-team/task|contact?session_id=` 私有路由）
- `backend/server.js`：路由总表 `/health` `/api/agent/status|target|workspace|models|team/:sessionId` `/api/codearts/*`
- 前端关键文件：`web/src/App.tsx`（所有页面组件）、`codearts.ts`（API client + BUILTIN_MODELS）、`useAgentConnection.ts`（20s 轮询）、`mockService.ts`（项目/阶段数据，localStorage `tuotaihuangu_projects_v1`，**schema 变更后旧缓存会显示旧阶段名**）

## 已实现功能清单

1. CodeArts 连接：自动发现端口、状态轮询、错误详情透传、连接测试会真实派发双子代理（background-task 并行验证过）
2. 工作区目录：新建任务必填本机绝对路径（`GET /api/agent/workspace` 校验存在性）；会话目录必须走 **URL 查询参数且用正斜杠**（`?directory=D:/xx`，请求体里会被忽略，单反斜杠会被拼到默认目录后）
3. 模型管理：客户端已有模型 + 网页新增（表单对齐客户端，OpenAI/Anthropic 两种 API 格式映射 `@ai-sdk/openai-compatible`/`@ai-sdk/anthropic`）；**内核不热加载，新增模型需重启 CodeArts Agent**
4. 内置模型（inferhub-provider）：openpangu-2.0-pro / openpangu-2.0-flash / GLM-5.2 已真实验证可用；GLM-4.7-ArkTS-SPARK 注册 ID 未找到（标"待验证"）
5. AgentTeam：prompt 强制 get-team-setup→publish-task→background-task 流程；240s 等待，超时不算失败；时间线面板展示团队花名册+任务清单（5s 轮询）
6. 四阶段详情页：目标+3动作+可视化+协作智能体(17角色卡)+门禁条；口径对齐 skill 快照
7. 首页：跨平台定位（Android/Windows/传统软件→语义契约→鸿蒙手机/PC/车载，实虚线区分）+ 成果速览三卡
8. 新建迁移：源/目标平台选择器（仅 Android→鸿蒙手机可提交，其余禁用并提示）

## skill 快照

`skill-snapshot/`（仓库内持久副本，源自用户提供的 skill-snapshot-final-20260831.zip）：
- `governance-tree/android-harmony-migration-controller`：主控（四阶段、Gate、六代理模型、核心等价契约）
- `governance-tree/android-migration-inventory`：Phase 2（九步：surface-index→feature-map→BC六要素→RUNTIME/SOURCE_CONFIRM 分级→行为链→对账四态）
- `governance-tree/harmonyos-migration-scaffold`：Phase 3（分面搭壳：page→路由/dialog→模态/container不建壳；UI蓝图；数据契约）
- `governance-tree/harmonyos-feature-implementation`：Phase 4（双机差分四维 observable/data/persistence/side-effect；Android=oracle 只修 Harmony；2轮上限转人工）

## 进行中的需求（用户 2026-08-31 提出）

1. ✅ skill 治理：`/api/skill/*`（tree/file/proposals/decide），前端顶栏「Skill 治理」对话框；提案 pending → approved 才写文件（先备份 .bak-时间戳），E2E 已验证；提案存储在 `backend/skill-proposals.json`
2. ✅ 真实迁移演示（2026-08-31 已完成 Phase 1）：对象 JetNews（原计划 compose-samples/TodoSample 已被官方移除，leader 发现后改用仓库最小的 JetNews）。会话 `ses_fab01a1a6ffeLSBLQHVPiQdNHC`，4 任务全 completed：3 个 team-mate 并行分析（数据层/UI结构/功能范围）+ leader 汇总。仓库克隆在 `C:\Users\Rainyday\workspace\compose-samples`（注意：leader 的 bash cwd 落在旧默认目录而非 D:/code/migration-todo-demo，目录参数对 prompt 生效但 bash 起始 cwd 未必切换）。产出：12 项功能清单（P0/P1/P2）、9 个数据对象字段表、持久化结论（无 Room、Flow 内存 + Fake Repository）、UI 结构清单
3. 审核循环（待做）：每 Gate 审核由 ZCode 承担，不通过→分析原因→派对应阶段子代理修改→重审至通过。网站已有 ReviewDialog 人工审核 UI；Phase 2-4 尚未执行

## 已知坑

- compose-samples 是 monorepo，TodoSample 已移除（现为 JetNews/Jetchat/Jetsnack/Jetcaster/Reply/JetLagged）
- Agent write 工具写大文件会超时，让 leader 直接在回复文本输出报告更稳
- CodeArts Agent 重启后端口变化（16217→48349），网关自动发现正常；网站任务需手动点「启动真实 AgentTeam」重试（auto-run key 已消耗）

## 待办（等用户提供）

- 阶段页 6 处真机截图占位、XX 指标真实值
- localStorage 旧缓存导致旧阶段名（可加 schema 版本自动清理）
