import React, { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { EmulatorFrame, EmulatorStream, Feature, Phase, PhaseNumber, Project, ProjectInput, Review, SourcePlatform, TargetPlatform } from "./types";
import { mockService } from "./mockService";
import { addAgentModel, BUILTIN_MODELS, checkCodeArts, checkWorkspaceDir, createCodeArtsSession, fetchAgentModels, getCodeArtsMessages, fetchSessionSummary, fetchTeamState, flattenModelOptions, isAbsoluteWindowsPath, loadCodeArtsCredentials, loadRunModel, loadTestWorkspaceDir, parseRunModel, promptCodeArtsSession, removeAgentModel, saveCodeArtsCredentials, saveRunModel, saveTestWorkspaceDir, updateAgentTarget, waitForCodeArtsResult, createSkillProposal, decideSkillProposal, fetchSkillFile, fetchSkillProposals, fetchSkillTree, type AgentModelInput, type AgentProviderInfo, type AgentTeamState, type SkillProposal, type CodeArtsCredentials, type CodeArtsMessage, type CodeArtsRunResult } from "./codearts";
import { agentSourceLabel, agentTargetLabel, useAgentConnection } from "./useAgentConnection";
import { phasePrompt } from "./phasePrompts";

const statusLabels: Record<Phase["status"], string> = {
  pending: "待执行",
  running: "执行中",
  review_required: "待审核",
  approved: "已审核",
  changes_requested: "修改中",
  completed: "已完成"
};

const statusClasses: Record<Phase["status"], string> = {
  pending: "status-pending",
  running: "status-running",
  review_required: "status-review",
  approved: "status-approved",
  changes_requested: "status-running",
  completed: "status-approved"
};

function sourcePlatformLabel(platform: Project["sourcePlatform"]): string {
  if (platform === "windows") return "Windows 桌面";
  if (platform === "legacy-desktop") return "传统桌面";
  return "Android";
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function phaseFromNumber(number: number) {
  return Math.min(4, Math.max(1, number)) as PhaseNumber;
}

function makeReview(decision: Review["decision"], comment: string): Review {
  return { decision, comment, reviewer: "当前审核员", reviewedAt: new Date().toISOString() };
}

function useProject(id?: string) {
  const [project, setProject] = useState<Project | undefined>(() => (id ? mockService.getProject(id) : undefined));
  useEffect(() => {
    if (!id) return;
    setProject(mockService.getProject(id));
    return mockService.subscribe(id, setProject);
  }, [id]);
  return project;
}

function App() {
  return (
    <>
    <Routes>
      <Route element={<LiveAppShell />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/projects/new" element={<LiveNewProjectPage />} />
        <Route path="/projects/:id" element={<LiveProjectPage />} />
        <Route path="/projects/:id/report" element={<ReportPage />} />
        <Route path="/projects/:id/delivery" element={<DeliveryPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
    </>
  );
}

function LiveAppShell() {
  const [projects, setProjects] = useState<Project[]>(() => mockService.listProjects());
  const [codeArtsOpen, setCodeArtsOpen] = useState(false);
  const [skillGovOpen, setSkillGovOpen] = useState(false);
  const { status: agent } = useAgentConnection();
  useEffect(() => mockService.subscribeAll(setProjects), []);
  const connected = Boolean(agent?.reachable && agent?.healthy);
  const active = projects.find((project) => project.status === "running" || project.status === "review");
  const navClass = ({ isActive }: { isActive: boolean }) => isActive ? "active" : "";
  const pillTitle = agent
    ? `${agent.target} · ${agentSourceLabel(agent.source)}${agent.error ? ` · ${agent.error}` : ""}`
    : "正在检测本机 CodeArts Agent…";
  const bannerReason = agent
    ? agent.reachable
      ? "Agent 健康检查未通过"
      : agent.error || "目标端口没有服务在监听"
    : "正在自动发现本机 Agent…";
  return <div className="app-shell">
    <header className="topbar">
      <Link className="brand" to="/"><span className="brand-mark">脱</span><strong>脱胎换骨</strong></Link>
      <nav className="topnav">
        <NavLink to="/" end className={navClass}>项目总览</NavLink>
        <NavLink to="/projects/new" className={navClass}>新建迁移</NavLink>
        {active && <NavLink to={`/projects/${active.id}`} className={navClass}>当前工作台</NavLink>}
      </nav>
      <div className="topbar-right">
        <button className="refresh-button" onClick={() => setSkillGovOpen(true)}>Skill 治理</button>
        <button className="env-pill" onClick={() => setCodeArtsOpen(true)} title={pillTitle}>
          <span className={`env-dot ${connected ? "connected" : agent ? "unreachable" : ""}`} />
          {connected ? `CodeArts 已连接 · ${agentTargetLabel(agent?.target)}` : agent ? "CodeArts 未连接" : "CodeArts 检测中…"}
        </button>
        <span className="user-chip"><span className="avatar">审</span>当前审核员</span>
      </div>
    </header>
    <div className={`demo-banner ${connected ? "live-banner" : ""}`}>
      {connected
        ? `真实执行模式 · CodeArts Space / AgentTeam · ${agentTargetLabel(agent?.target)}`
        : `CodeArts Agent 未连接（${bannerReason}）· 新任务将无法启动真实推理`}
      <span className="banner-link" onClick={() => setCodeArtsOpen(true)}>{connected ? "查看连接状态 →" : "排查连接 →"}</span>
    </div>
    <main className="main-content"><div className="page-content"><Outlet /></div></main>
    {codeArtsOpen && <CodeArtsConnectionDialog initial={loadCodeArtsCredentials()} onClose={() => setCodeArtsOpen(false)} />}
    {skillGovOpen && <SkillGovernanceDialog onClose={() => setSkillGovOpen(false)} />}
  </div>;
}

function CodeArtsConnectionDialog({ initial, onClose }: { initial: CodeArtsCredentials; onClose: () => void }) {
  const { status: agent, refreshing, refresh } = useAgentConnection();
  const [credentials, setCredentials] = useState<CodeArtsCredentials>(initial);
  const [instruction, setInstruction] = useState("请用 background-task 同时并行派发两个 team-mate 子代理：一个查询政治方面的最新新闻，一个查询AI圈的最新新闻（可用 webfetch 访问新闻网站）。两个都完成后，用 background-output 收集结果并汇总汇报每个子代理的产出。不要亲自执行，也不要用 Task 顺序执行。");
  const [status, setStatus] = useState<"idle" | "checking" | "running" | "succeeded" | "failed">("idle");
  const [result, setResult] = useState<CodeArtsRunResult | null>(null);
  const [messages, setMessages] = useState<CodeArtsMessage[]>([]);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [targetDraft, setTargetDraft] = useState("");
  const [targetMessage, setTargetMessage] = useState("");
  const [savingTarget, setSavingTarget] = useState(false);
  const [testDir, setTestDir] = useState(() => loadTestWorkspaceDir());
  const [modelsOpen, setModelsOpen] = useState(false);
  const [runModel, setRunModel] = useState(() => loadRunModel());
  const [modelOptions, setModelOptions] = useState(() => flattenModelOptions([]));
  const runningRef = useRef(false);
  useEffect(() => { void fetchAgentModels().then((list) => { if (list) setModelOptions(flattenModelOptions(list)); }); }, []);
  const connected = Boolean(agent?.reachable && agent?.healthy);

  const applyTarget = async () => {
    if (savingTarget) return;
    setSavingTarget(true);
    setTargetMessage("");
    const saved = await updateAgentTarget(targetDraft.trim());
    if (!saved.ok) {
      setTargetMessage(saved.error ?? "保存失败");
    } else {
      setTargetMessage(targetDraft.trim() ? "已保存，后续请求将使用该地址" : "已清除覆盖，恢复自动发现");
      await refresh();
    }
    setSavingTarget(false);
  };

  const runTest = async () => {
    if (runningRef.current || !instruction.trim()) return;
    runningRef.current = true;
    const started = Date.now();
    setElapsed(null);
    setError("");
    setResult(null);
    setMessages([]);
    setStatus("checking");
    try {
      const checked = await checkCodeArts(credentials);
      if (!checked.connected) {
        setStatus("failed");
        setError(checked.hint ? `${checked.message}。${checked.hint}` : checked.message);
        void refresh();
        return;
      }
      saveCodeArtsCredentials(credentials);
      saveTestWorkspaceDir(testDir);
      void refresh();
      setStatus("running");
      const created = await createCodeArtsSession(`脱胎换骨 · 连接测试 · ${new Date(started).toLocaleTimeString("zh-CN")}`, credentials, { directory: testDir.trim() || undefined });
      if (!created.accepted || !created.session?.id) {
        setStatus("failed");
        setError(created.message);
        return;
      }
      const submitted = await promptCodeArtsSession(created.session.id, instruction.trim(), credentials, { agent: "team-leader", mode: "agent-team", model: parseRunModel(runModel) });
      if (!submitted.accepted) {
        setResult(submitted);
        setStatus("failed");
        setError(submitted.message);
        return;
      }
      const resolved = submitted.pending
        ? await waitForCodeArtsResult(created.session.id, submitted.messageId, credentials, {
            timeoutMs: 120000,
            pollMs: 1200,
            onUpdate: (message) => setMessages((current) => {
              const key = message.info?.id;
              if (key && current.some((item) => item.info?.id === key)) return current;
              return [...current, message];
            }),
          })
        : submitted;
      setResult(resolved);
      setStatus(resolved.accepted ? "succeeded" : "failed");
      if (!resolved.accepted) setError(resolved.message);
    } catch (caught) {
      setStatus("failed");
      setError(caught instanceof Error ? caught.message : "CodeArts 测试请求失败");
    } finally {
      setElapsed(Date.now() - started);
      runningRef.current = false;
    }
  };

  const responseText = typeof result?.response === "string" ? result.response : result?.response ? JSON.stringify(result.response, null, 2) : "";
  const statusLabel = status === "idle" ? "尚未测试" : status === "checking" ? "健康检查中" : status === "running" ? "推理中" : status === "succeeded" ? "测试通过" : "测试失败";
  return <><div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="review-dialog codearts-dialog">
    <div className="dialog-top"><div><h2>CodeArts 连接</h2><p>网关自动发现本机 AgentKernel 端口。默认指令会通过 Task 工具真实派发子智能体，直接验证 Space AgentTeam 团队协作可用。</p></div><div className="dialog-top-right"><span className={`test-status-pill ${status}`}>{statusLabel}</span><button className="close-button" onClick={onClose}>×</button></div></div>
    <div className="agent-card">
      <div className="agent-card-top">
        <span className={`agent-state-pill ${connected ? "ok" : "bad"}`}><i />{agent ? (connected ? "已连接" : "未连接") : "检测中…"}</span>
        <span className="agent-card-actions">
          <button className="refresh-button" onClick={() => setModelsOpen(true)}>模型管理</button>
          <button className="refresh-button" onClick={() => void refresh()} disabled={refreshing}>{refreshing ? "检测中…" : "↻ 重新检测"}</button>
        </span>
      </div>
      <div className="agent-target-row">
        <code>{agent ? agentTargetLabel(agent.target) : "—"}</code>
        {agent && <span className="agent-source-badge">{agentSourceLabel(agent.source)}</span>}
        {agent?.discovered?.pidAlive && <span className="agent-source-badge neutral">PID {agent.discovered.pid}</span>}
      </div>
      <div className="agent-meta">
        <span>版本 <b>{agent?.version ?? agent?.discovered?.version ?? "—"}</b></span>
        <span>延迟 <b>{agent?.reachable ? `${agent.latencyMs ?? "—"} ms` : "—"}</b></span>
        <span>认证 <b>{agent?.authMode === "user" ? "页面凭据" : agent?.authMode === "env" ? "环境变量" : agent?.authMode === "auto" ? "本机托管凭据" : "未配置"}</b></span>
        <span>检测于 <b>{agent ? formatTime(agent.checkedAt) : "—"}</b></span>
      </div>
      {!connected && agent?.error && <div className="agent-error-line">{agent.error}</div>}
      {connected && agent?.source === "default" && <div className="agent-error-line">正在使用默认端口连接。若本机 Agent 实际端口不同，请在下方手动指定。</div>}
    </div>
    <label className="field-label">手动指定本机地址（可选）
      <div className="target-override-row">
        <input value={targetDraft} onChange={(event) => setTargetDraft(event.target.value)} placeholder={agent ? agent.target : "http://127.0.0.1:16217"} />
        <button className="ghost-button" onClick={() => void applyTarget()} disabled={savingTarget}>{savingTarget ? "保存中…" : "保存"}</button>
      </div>
      <small className="field-note">仅支持本机地址；清空后保存即恢复自动发现。{targetMessage && <b className={targetMessage.startsWith("已") ? "mint-text" : "error-text"}> {targetMessage}</b>}</small>
    </label>
    <div className="field-divider" />
    <label className="field-label">用户名<input value={credentials.username} onChange={(event) => setCredentials({ ...credentials, username: event.target.value })} placeholder="codearts" /></label>
    <label className="field-label">本地服务密码（可选）<input type="password" value={credentials.password} onChange={(event) => setCredentials({ ...credentials, password: event.target.value })} placeholder="留空则使用本机 Agent 凭据" /></label>
    <label className="field-label">测试工作区目录（可选）<input value={testDir} onChange={(event) => setTestDir(event.target.value)} placeholder={isAbsoluteWindowsPath(testDir) || !testDir ? "留空则使用 Agent 默认目录" : "请输入本机绝对路径，如 D:\\code\\test-workspace"} /><small className={`field-note ${testDir.trim() && !isAbsoluteWindowsPath(testDir) ? "error-text" : ""}`}>{testDir.trim() && !isAbsoluteWindowsPath(testDir) ? "请输入本机绝对路径" : "测试会话将在此目录中运行，避免写入 Agent 安装目录。"}</small></label>
    <label className="field-label">执行模型<select value={runModel} onChange={(event) => { setRunModel(event.target.value); saveRunModel(event.target.value); }}>{modelOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select><small className="field-note">连接测试与真实 AgentTeam 执行共用此选择；含 Space 内置模型与已配置的自定义模型。</small></label>
    <label className="field-label">测试指令<textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} rows={3} placeholder="输入你希望 CodeArts 回答的内容" /></label>
    <button className="primary-button wide" onClick={runTest} disabled={status === "checking" || status === "running" || !instruction.trim()}>{status === "checking" ? "检查 CodeArts 服务…" : status === "running" ? "等待回复…" : "发送测试指令"}<span>→</span></button>
    {(error || result?.message) && status === "failed" && <div className="codearts-test-error">{error || result?.message}</div>}
    {responseText && <pre className="real-response dialog-response">{responseText}</pre>}
    {!responseText && status === "running" && <div className="test-loader"><i /><i /><i /></div>}
    <div className="codearts-test-meta"><span>Agent <b>team-leader</b></span><span>消息 <b>{messages.length}</b></span><span>耗时 <b>{elapsed === null ? "—" : `${(elapsed / 1000).toFixed(1)}s`}</b></span></div>
  </div></div>
  {modelsOpen && <ModelManagerDialog onClose={() => setModelsOpen(false)} />}</>;
}

function SkillGovernanceDialog({ onClose }: { onClose: () => void }) {
  const [skills, setSkills] = useState<Array<{ skill: string; files: Array<{ path: string; size: number }> }> | null>(null);
  const [selectedFile, setSelectedFile] = useState("");
  const [fileContent, setFileContent] = useState("");
  const [proposals, setProposals] = useState<SkillProposal[] | null>(null);
  const [draft, setDraft] = useState("");
  const [reason, setReason] = useState("");
  const [author, setAuthor] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    const [tree, list] = await Promise.all([fetchSkillTree(), fetchSkillProposals()]);
    setSkills(tree);
    setProposals(list);
  };
  useEffect(() => { void reload(); }, []);

  const openFile = async (path: string) => {
    setSelectedFile(path);
    setError("");
    setDraft("");
    const content = await fetchSkillFile(path);
    if (content === null) return setError("读取文件失败");
    setFileContent(content);
  };

  const startEdit = () => setDraft(fileContent);

  const submitProposal = async () => {
    if (busy) return;
    setError(""); setMessage("");
    if (!selectedFile) return setError("请先选择 skill 文件");
    if (!draft.trim()) return setError("请点击「基于当前内容编辑」后修改");
    if (!reason.trim()) return setError("必须填写修改理由（审核依据）");
    setBusy(true);
    const result = await createSkillProposal({ path: selectedFile, newContent: draft, reason: reason.trim(), author: author.trim() || "agent" });
    setBusy(false);
    if (!result.ok) return setError(result.error ?? "提交失败");
    setMessage("提案已提交，等待人工审核。审核通过前 skill 文件不会被修改。");
    setDraft(""); setReason("");
    await reload();
  };

  const decide = async (id: string, decision: "approved" | "rejected") => {
    if (busy) return;
    setBusy(true);
    const comment = decision === "rejected" ? window.prompt("驳回理由（会反馈给提案方）：") ?? "" : "";
    if (decision === "rejected" && !comment) { setBusy(false); return; }
    const result = await decideSkillProposal(id, decision, comment);
    setBusy(false);
    if (!result.ok) return setError(result.error ?? "操作失败");
    setMessage(decision === "approved" ? "已通过：新内容写入 skill 文件（原文件已备份）。若在正式 run 中，请按 TOOL_GAP 规则重启 run。" : "已驳回。");
    await reload();
  };

  const pending = proposals?.filter((p) => p.status === "pending") ?? [];
  const decided = proposals?.filter((p) => p.status !== "pending").slice(0, 6) ?? [];
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="review-dialog codearts-dialog skill-dialog">
    <div className="dialog-top"><div><h2>Skill 治理</h2><p>智能体可对 skill 提交修改提案；审核通过前文件不会被改动，通过后写入并自动备份。</p></div><div className="dialog-top-right"><span className="test-status-pill idle">{pending.length ? `${pending.length} 条待审` : "无待审"}</span><button className="close-button" onClick={onClose}>×</button></div></div>
    {error && <div className="codearts-test-error">{error}</div>}
    {message && <div className="model-form-message model-success">{message}</div>}
    <div className="skill-layout">
      <div className="skill-tree">
        {(skills ?? []).map((group) => <div key={group.skill}>
          <p className="lp-eyebrow">{group.skill}</p>
          {group.files.filter((f) => f.path.endsWith(".md") || f.path.endsWith(".yaml")).slice(0, 12).map((file) => <button key={file.path} className={`skill-file ${selectedFile === file.path ? "active" : ""}`} onClick={() => void openFile(file.path)}>{file.path.split("/").slice(1).join("/")}</button>)}
        </div>)}
        {!skills && <p className="field-note">正在读取 skill 目录…</p>}
      </div>
      <div className="skill-main">
        {!selectedFile && <p className="field-note">← 从左侧选择 skill 文件查看内容</p>}
        {selectedFile && !draft && <>
          <div className="skill-file-head"><code>{selectedFile}</code><button className="refresh-button" onClick={startEdit}>基于当前内容编辑</button></div>
          <pre className="skill-content">{fileContent.slice(0, 4000)}{fileContent.length > 4000 ? "\n…（仅预览前 4000 字，编辑时为全文）" : ""}</pre>
        </>}
        {selectedFile && draft && <>
          <div className="skill-file-head"><code>{selectedFile} · 编辑中</code></div>
          <textarea className="skill-editor" value={draft} onChange={(event) => setDraft(event.target.value)} spellCheck={false} />
          <div className="field-label">修改理由（必填，审核依据）<input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="为什么需要改这个 skill？改动的依据是什么？" /></div>
          <div className="field-label">提案方<input value={author} onChange={(event) => setAuthor(event.target.value)} placeholder="例如：android-migration-inventory / agent" /></div>
          <div className="dialog-actions"><button className="ghost-button" onClick={() => setDraft("")}>取消编辑</button><button className="primary-button" onClick={() => void submitProposal()} disabled={busy}>{busy ? "提交中…" : "提交提案待审"}</button></div>
        </>}
      </div>
    </div>
    <div className="field-divider" />
    <p className="lp-eyebrow">审核队列</p>
    <div className="skill-review-list">
      {pending.length === 0 && <p className="field-note">暂无待审提案。</p>}
      {pending.map((proposal) => <div className="skill-review-row" key={proposal.id}>
        <div className="skill-review-info"><b>{proposal.path}</b><small>{proposal.author} · {proposal.originalLines} → {proposal.newLines} 行</small><p>{proposal.reason}</p></div>
        <div className="skill-review-actions"><button className="refresh-button danger" onClick={() => void decide(proposal.id, "rejected")} disabled={busy}>驳回</button><button className="refresh-button" onClick={() => void decide(proposal.id, "approved")} disabled={busy}>通过并写入</button></div>
      </div>)}
      {decided.map((proposal) => <div className="skill-review-row decided" key={proposal.id}>
        <div className="skill-review-info"><b>{proposal.path}</b><small>{proposal.author} · {proposal.status === "approved" ? "已通过并写入" : "已驳回"}{proposal.reviewerComment ? ` · ${proposal.reviewerComment}` : ""}</small></div>
      </div>)}
    </div>
  </div></div>;
}

const PROVIDER_PRESETS: Array<{ id: string; name: string; baseURL: string }> = [
  { id: "deepseek", name: "深度求索 DeepSeek", baseURL: "https://api.deepseek.com" },
  { id: "glm", name: "智谱 GLM", baseURL: "https://open.bigmodel.cn/api/coding/paas/v4" },
  { id: "qwen", name: "阿里云通义千问", baseURL: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  { id: "moonshot", name: "月之暗面 Kimi", baseURL: "https://api.moonshot.cn/v1" },
  { id: "openai", name: "OpenAI", baseURL: "https://api.openai.com/v1" },
];

function ModelManagerDialog({ onClose }: { onClose: () => void }) {
  const [providers, setProviders] = useState<AgentProviderInfo[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const [addOpen, setAddOpen] = useState(false);

  const load = async () => {
    setLoadError("");
    const list = await fetchAgentModels();
    if (list === null) setLoadError("无法读取模型列表：请确认后端网关与本机 Agent 正在运行。");
    setProviders(list);
  };
  useEffect(() => { void load(); }, []);

  const remove = async (providerID: string, modelID: string) => {
    setLoadError("");
    const result = await removeAgentModel(providerID, modelID);
    if (result.ok) {
      if (result.providers) setProviders(result.providers);
      setNotice(`已从客户端配置移除模型 ${modelID}`);
    } else {
      setLoadError(result.error ?? "删除失败");
    }
  };

  const totalModels = (providers?.reduce((sum, p) => sum + p.models.length, 0) ?? 0) + BUILTIN_MODELS.length;
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="review-dialog codearts-dialog model-dialog">
    <div className="dialog-top"><div><h2>模型管理</h2><p>与 CodeArts 客户端共用同一份模型配置；新增的模型写入客户端配置文件，重启 Agent 后在客户端和执行中同步生效。</p></div><div className="dialog-top-right"><span className="test-status-pill idle">{providers ? `已有 ${totalModels} 个模型` : "加载中"}</span><button className="close-button" onClick={onClose}>×</button></div></div>
    {notice && <div className="model-form-message model-success">{notice}</div>}
    {loadError && <div className="codearts-test-error">{loadError}</div>}
    <div className="model-list">
      <div className="model-provider-card">
        <div className="model-provider-top"><b>客户端内置模型</b><span className="agent-source-badge">Space 内置</span><code className="model-baseurl">inferhub-provider</code><span className="model-key">由登录态提供</span></div>
        {BUILTIN_MODELS.map((model) => <div className="model-row" key={model.id}>
          <span className="model-name" title={model.desc}><b>{model.name}</b><small>{model.desc}{model.verified ? "" : " · 注册 ID 待确认"}</small></span>
          <span className="model-row-right"><span className="agent-source-badge neutral">内置</span></span>
        </div>)}
      </div>
      {(providers ?? []).map((provider) => <div className="model-provider-card" key={provider.providerID}>
        <div className="model-provider-top"><b>{provider.name}</b><span className="agent-source-badge neutral">{provider.providerID}</span><span className="agent-source-badge">{provider.npm.includes("anthropic") ? "Anthropic Messages" : "OpenAI 兼容"}</span>{provider.baseURL && <code className="model-baseurl">{provider.baseURL}</code>}<span className="model-key">{provider.apiKeyMasked ? `Key ${provider.apiKeyMasked}` : "未配置 Key"}</span></div>
        {provider.models.length === 0 && <div className="model-row"><small className="field-note">该服务商暂无模型</small></div>}
        {provider.models.map((model) => <div className="model-row" key={model.modelID}>
          <span className="model-name" title={model.modelDesc || model.modelID}><b>{model.modelName}</b><small>{model.modelID}{model.modelDesc ? ` · ${model.modelDesc}` : ""}</small></span>
          <span className="model-row-right">
            <span className="agent-source-badge">{model.isCustomModel ? "自定义" : "客户端内置"}</span>
            {model.contextWindow > 0 && <small className="field-note">{Math.round(model.contextWindow / 1000)}K 上下文</small>}
            {model.isCustomModel && <button className="refresh-button danger" onClick={() => void remove(provider.providerID, model.modelID)}>删除</button>}
          </span>
        </div>)}
      </div>)}
    </div>
    <div className="dialog-actions model-dialog-actions"><button className="ghost-button" onClick={onClose}>关闭</button><button className="primary-button" onClick={() => setAddOpen(true)}>＋ 添加模型</button></div>
    {addOpen && <AddModelDialog providers={providers ?? []} onClose={() => setAddOpen(false)} onAdded={(message, list) => { setNotice(message); if (list) setProviders(list); }} />}
  </div></div>;
}

function AddModelDialog({ providers, onClose, onAdded }: { providers: AgentProviderInfo[]; onClose: () => void; onAdded: (message: string, providers?: AgentProviderInfo[]) => void }) {
  const [tab, setTab] = useState<"provider" | "custom">("provider");
  const [apiFormat, setApiFormat] = useState<"openai" | "anthropic">("openai");
  const [providerChoice, setProviderChoice] = useState("");
  const [modelID, setModelID] = useState("");
  const [modelName, setModelName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [advOpen, setAdvOpen] = useState(false);
  const [contextWindow, setContextWindow] = useState("");
  const [outputWindow, setOutputWindow] = useState("");
  const [apiURL, setApiURL] = useState("");
  const [customModelID, setCustomModelID] = useState("");
  const [customModelName, setCustomModelName] = useState("");
  const [customKey, setCustomKey] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const existing = providers.find((p) => p.providerID === providerChoice);
  const preset = PROVIDER_PRESETS.find((p) => p.id === providerChoice);
  const providerKnown = providers.some((p) => p.providerID === providerChoice);
  const knownModels = existing?.models.map((m) => m.modelID) ?? [];

  const submit = async () => {
    if (submitting) return;
    setError("");
    let input: AgentModelInput;
    if (tab === "provider") {
      if (!providerChoice) return setError("请先选择模型提供商");
      if (!modelID.trim()) return setError("请填写模型 ID");
      if (!providerKnown && !apiKey.trim()) return setError("该服务商尚未配置 API Key，请填写");
      input = {
        providerID: providerChoice,
        providerName: preset?.name ?? existing?.name ?? providerChoice,
        baseURL: providerKnown ? "" : preset?.baseURL ?? "",
        apiKey: apiKey.trim(),
        modelID: modelID.trim(),
        modelName: modelName.trim() || modelID.trim(),
        modelDesc: "",
        contextWindow: contextWindow ? Number(contextWindow) : undefined,
        outputContextWindow: outputWindow ? Number(outputWindow) : undefined,
      };
    } else {
      if (!/^https?:\/\//.test(apiURL.trim())) return setError("请填写有效的模型 URL（以 http(s):// 开头，不要以斜杠结尾）");
      if (!customModelID.trim()) return setError("请填写模型 ID");
      input = {
        providerID: apiFormat === "anthropic" ? "custom-anthropic" : "custom",
        providerName: "自定义",
        baseURL: apiURL.trim().replace(/\/+$/, ""),
        apiKey: customKey.trim(),
        modelID: customModelID.trim(),
        modelName: customModelName.trim() || customModelID.trim(),
        modelDesc: "",
        apiFormat,
        contextWindow: contextWindow ? Number(contextWindow) : undefined,
        outputContextWindow: outputWindow ? Number(outputWindow) : undefined,
      };
    }
    setSubmitting(true);
    const result = await addAgentModel(input);
    setSubmitting(false);
    if (!result.ok) return setError(result.error ?? "新增模型失败");
    onAdded(`模型「${input.modelName}」已写入客户端配置文件，重启 CodeArts Agent 后生效。`, result.providers);
  };

  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="review-dialog add-model-dialog">
    <div className="dialog-top"><div><h2>添加模型</h2></div><button className="close-button" onClick={onClose}>×</button></div>
    <div className="model-tabs">
      <button type="button" className={`model-tab ${tab === "provider" ? "active" : ""}`} onClick={() => { setTab("provider"); setError(""); }}>模型提供商</button>
      <button type="button" className={`model-tab ${tab === "custom" ? "active" : ""}`} onClick={() => { setTab("custom"); setError(""); }}>自定义配置</button>
    </div>
    {tab === "provider" ? <>
      <label className="field-label">模型提供商
        <select value={providerChoice} onChange={(event) => setProviderChoice(event.target.value)}>
          <option value="">请选择模型提供商</option>
          {PROVIDER_PRESETS.map((presetItem) => <option key={presetItem.id} value={presetItem.id}>{presetItem.name}{providers.some((p) => p.providerID === presetItem.id) ? "（已配置）" : ""}</option>)}
          {providers.filter((p) => !PROVIDER_PRESETS.some((presetItem) => presetItem.id === p.providerID)).map((p) => <option key={p.providerID} value={p.providerID}>{p.name}（已配置）</option>)}
        </select>
      </label>
      <label className="field-label">模型 ID <span className="help-dot" title="服务商的模型标识，例如 glm-5.3-flash">?</span>
        <input list="known-model-ids" value={modelID} onChange={(event) => setModelID(event.target.value)} placeholder="请选择或输入模型 ID" maxLength={64} />
        <datalist id="known-model-ids">{knownModels.map((id) => <option key={id} value={id} />)}</datalist>
      </label>
      <label className="field-label"><span className="label-row">模型展示名称 <span className="help-dot" title="展示在客户端和执行列表里的名称">?</span><em className="char-count">{modelName.length}/64</em></span>
        <input value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder="请输入模型展示名称，例如：OpenAI-3-Next" maxLength={64} />
      </label>
      <label className="field-label"><span className="label-row">API Key{existing?.hasApiKey && <em className="char-count">已配置，留空沿用原 Key</em>}</span>
        <span className="key-input-wrap">
          <input type={showKey ? "text" : "password"} value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="请输入API密钥" />
          <button type="button" className="key-toggle" onClick={() => setShowKey((value) => !value)} aria-label={showKey ? "隐藏密钥" : "显示密钥"}>{showKey ? "隐蔽" : "👁"}</button>
        </span>
      </label>
    </> : <>
      <label className="field-label">API格式
        <select value={apiFormat} onChange={(event) => setApiFormat(event.target.value as "openai" | "anthropic")}>
          <option value="openai">OpenAI Chat Completions</option>
          <option value="anthropic">Anthropic Messages</option>
        </select>
      </label>
      <label className="field-label">模型URL
        <input value={apiURL} onChange={(event) => setApiURL(event.target.value)} placeholder="请输入模型URL" />
        <small className="field-note">{apiFormat === "anthropic" ? "请填写Anthropic API服务端点地址，不要以斜杠结尾。" : "请填写OpenAI API服务端点地址，不要以斜杠结尾。系统会自动补充 /chat/completions 路径。"}</small>
      </label>
      <label className="field-label"><span className="label-row">模型ID<em className="char-count">{customModelID.length}/64</em></span>
        <input value={customModelID} onChange={(event) => setCustomModelID(event.target.value)} placeholder="请输入模型ID" maxLength={64} />
      </label>
      <label className="field-label"><span className="label-row">模型展示名称<em className="char-count">{customModelName.length}/64</em></span>
        <input value={customModelName} onChange={(event) => setCustomModelName(event.target.value)} placeholder="请输入模型展示名称，例如：OpenAI-3-Next" maxLength={64} />
      </label>
      <label className="field-label">API Key
        <span className="key-input-wrap">
          <input type={showKey ? "text" : "password"} value={customKey} onChange={(event) => setCustomKey(event.target.value)} placeholder="请输入API密钥" />
          <button type="button" className="key-toggle" onClick={() => setShowKey((value) => !value)} aria-label={showKey ? "隐藏密钥" : "显示密钥"}>{showKey ? "隐蔽" : "👁"}</button>
        </span>
      </label>
    </>}
    <button type="button" className="adv-toggle" onClick={() => setAdvOpen((value) => !value)}>高级配置 <span>{advOpen ? "⌄" : "›"}</span></button>
    {advOpen && <div className="adv-grid">
      <label className="field-label">上下文窗口（tokens）<input type="number" min={0} value={contextWindow} onChange={(event) => setContextWindow(event.target.value)} placeholder="128000" /></label>
      <label className="field-label">最大输出（tokens）<input type="number" min={0} value={outputWindow} onChange={(event) => setOutputWindow(event.target.value)} placeholder="8192" /></label>
      <small className="field-note model-span2">其余参数保持客户端默认值。</small>
    </div>}
    <div className="model-disclaimer"><b>ⓘ 免责声明</b><p>不对第三方模型的可用性、合规性及安全性承担责任。使用前请评估相关模型并查阅其许可协议，确保符合法规要求。</p></div>
    {error && <div className="codearts-test-error">{error}</div>}
    <div className="dialog-actions"><button className="ghost-button" onClick={onClose}>取消</button><button className="primary-button" onClick={() => void submit()} disabled={submitting}>{submitting ? "正在写入…" : "确认"}</button></div>
  </div></div>;
}

function HomePage() {
  const projects = mockService.listProjects();
  const running = projects.filter((project) => project.status === "running").length;
  const completed = projects.filter((project) => project.status === "completed").length;
  const features = projects.flatMap((project) => project.features);
  const covered = features.filter((feature) => feature.status === "covered").length;
  return (
    <div className="home-page">
      <section className="home-hero" aria-labelledby="home-hero-title">
        <div className="hero-copy">
          <p className="eyebrow">跨平台软件迁移 · 功能一致性保障</p>
          <h1 id="home-hero-title">平台可换，功能语义不丢。</h1>
          <p className="hero-sub">面向异构软件平台的智能迁移系统：多智能体完成软件语义理解、目标平台原生适配与双端行为验证，让迁移后的软件仍然正确工作。<b>当前已完成 Android → HarmonyOS 的端到端工程验证</b>，架构可扩展至桌面、车载等终端场景。</p>
          <div className="hero-actions"><Link to="/projects/new" className="primary-button">开始一次迁移 <span>→</span></Link><a className="hero-text-link" href="#migration-outcomes">查看迁移成果 ↓</a></div>
          <div className="hero-proof"><span><b>4</b>阶段门禁</span><span><b>2</b>端运行证据</span><span><b>0</b>占位页面</span><span><b>1</b>份可追溯报告</span></div>
        </div>
        <div className="hero-flow" aria-label="跨平台迁移架构">
          <div className="flow-caption"><span>迁移架构</span><code>MULTI-PLATFORM</code></div>
          <div className="lp-flow hero-lp-flow">
            <div className="lp-flow-col">
              <div className="lp-node solid">Android<small>已验证</small></div>
              <div className="lp-node dashed">Windows<small>可扩展</small></div>
              <div className="lp-node dashed">传统桌面软件<small>可扩展</small></div>
            </div>
            <div className="lp-flow-arrow">→</div>
            <div className="lp-node contract">平台无关<br />功能语义契约<small>Feature Map · Behavior Contract</small></div>
            <div className="lp-flow-arrow">→</div>
            <div className="lp-flow-col">
              <div className="lp-node solid">HarmonyOS 手机<small>已验证</small></div>
              <div className="lp-node dashed">HarmonyOS PC<small>规划中</small></div>
              <div className="lp-node dashed">车载等异构终端<small>规划中</small></div>
            </div>
          </div>
          <div className="flow-foot"><span className="live-dot" />实线为已完成端到端验证的路径，虚线为架构预留的扩展方向</div>
        </div>
      </section>

      <section className="outcome-section" id="migration-outcomes" aria-labelledby="outcome-title">
        <div className="home-section-heading"><div><p className="eyebrow">迁移成果速览</p><h2 id="outcome-title">做了什么、解决了什么、效果怎么样</h2></div><span>以 Android → HarmonyOS 已验证案例呈现</span></div>
        <div className="outcome-grid">
          <div className="outcome-card">
            <p className="eyebrow">GUI 迁移前后对比</p>
            <div className="outcome-compare">
              <div className="lp-shot compact">Android 原版<small>真机截图位</small></div>
              <div className="lp-shot compact">HarmonyOS 迁移版<small>真机截图位</small></div>
            </div>
            <p className="outcome-desc">视觉结构<b>高还原</b>，交互组件<b>原生适配</b>（Tabs / Navigation / Toggle）。</p>
          </div>
          <div className="outcome-card">
            <p className="eyebrow">功能一致性测试</p>
            <div className="outcome-matrix">{[["新增 Todo", "数据写入并展示"], ["完成任务", "completed = true"], ["列表排序", "重启后保持"], ["语言切换", "en · 重启保持"]].map(([name, detail]) => <div className="outcome-matrix-row" key={name}><span>{name}</span><small>{detail}</small><i className="lp-match">MATCH</i></div>)}</div>
            <p className="outcome-desc">双端各跑一遍同一行为契约，机器比较数据 / 状态 / 持久化结果。</p>
          </div>
          <div className="outcome-card">
            <p className="eyebrow">典型问题自动修复</p>
            <div className="outcome-fixflow">
              <span className="lp-match diff">Persistence DIFF</span>
              <div className="outcome-fixchain">定位 SettingsRepository → 修复持久化 → 二次重放 <b>MATCH ✓</b></div>
            </div>
            <div className="outcome-build"><span>构建安装 <b>PASS</b></span><span>占位页面 <b>0</b></span><span>可运行 HAP <b>✓</b></span></div>
            <p className="outcome-desc">发现差异 → 自动定位 → 只修迁移端 → 重验通过，全程留痕可追溯。</p>
          </div>
        </div>
      </section>

      <div className="home-section-heading" id="migration-tasks"><div><p className="eyebrow">工作台总览</p><h2>迁移任务</h2></div><span>所有版本均可回到阶段证据</span></div>
      <div className="stats-grid"><StatCard label="进行中的迁移" value={String(running).padStart(2, "0")} /><StatCard label="已完成交付" value={String(completed).padStart(2, "0")} /><StatCard label="登记功能点" value={String(features.length).padStart(2, "0")} unit="项" /><StatCard label="已确认功能" value={String(covered).padStart(2, "0")} unit="项" /></div>
      <div className="task-table">
        <div className="task-row task-head"><span>项目名称</span><span>来源</span><span>当前阶段</span><span>阶段进度</span><span>状态</span><span>更新时间</span><span /></div>
        {projects.map((project) => { const current = project.phases.find((phase) => phase.number === project.currentPhase); const completedPhases = project.phases.filter((phase) => phase.status === "approved" || phase.status === "completed").length; return (
          <Link to={`/projects/${project.id}`} className="task-row" key={project.id}>
            <span className="task-name"><b>{project.name}</b></span>
            <span>{sourcePlatformLabel(project.sourcePlatform)} · {project.source.type === "github" ? "GitHub" : "ZIP"}</span>
            <span>{String(project.currentPhase).padStart(2, "0")} · {current?.shortTitle}</span>
            <span>{completedPhases}/4</span>
            <span><StatusBadge status={current?.status ?? "pending"} /></span>
            <span className="task-time">{project.demo ? "刚刚" : "今天 14:32"}</span>
            <span className="task-arrow">›</span>
          </Link>
        ); })}
      </div>
      <p className="mock-note"><span>ⓘ</span> 任务表为演示数据；成果速览中的截图位与指标将在接入真实运行记录后填充</p>
    </div>
  );
}


function StatCard({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return <div className="stat-card"><p>{label}</p><div className="stat-value">{value}<small>{unit}</small></div></div>;
}

function LiveNewProjectPage() {
  const navigate = useNavigate();
  const [sourcePlatform, setSourcePlatform] = useState<SourcePlatform>("android");
  const [targetPlatform, setTargetPlatform] = useState<TargetPlatform>("harmony-phone");
  const [sourceType, setSourceType] = useState<"github" | "zip">("github");
  const [sourceValue, setSourceValue] = useState("");
  const [name, setName] = useState("");
  const [executionMode, setExecutionMode] = useState<"codearts-agentteam" | "demo">("codearts-agentteam");
  const [workspaceDir, setWorkspaceDir] = useState("");
  const [projectModel, setProjectModel] = useState(() => loadRunModel());
  const [modelOptions, setModelOptions] = useState(() => flattenModelOptions([]));
  const [dirStatus, setDirStatus] = useState<"unknown" | "checking" | "exists" | "missing" | "invalid">("unknown");
  const [error, setError] = useState("");

  useEffect(() => {
    const value = workspaceDir.trim();
    if (!value) return setDirStatus("unknown");
    if (!isAbsoluteWindowsPath(value)) return setDirStatus("invalid");
    setDirStatus("checking");
    const timer = window.setTimeout(async () => {
      const result = await checkWorkspaceDir(value);
      if (!result) return setDirStatus("unknown");
      setDirStatus(result.exists && result.isDirectory !== false ? "exists" : "missing");
    }, 400);
    return () => window.clearTimeout(timer);
  }, [workspaceDir]);

  useEffect(() => { void fetchAgentModels().then((list) => { if (list) setModelOptions(flattenModelOptions(list)); }); }, []);

  const dirNotes: Record<typeof dirStatus, string> = {
    unknown: "Agent 将在该目录中检出源码并执行构建，不同任务建议使用不同目录。",
    checking: "正在检查目录…",
    exists: "✓ 目录已存在，Agent 将直接使用。",
    missing: "目录当前不存在，Agent 运行时会自动创建。",
    invalid: "请输入本机绝对路径，例如 D:\\code\\workspace",
  };

  const sourceOptions: Array<{ id: SourcePlatform; label: string; note: string; ready: boolean }> = [
    { id: "android", label: "Android App", note: "已验证", ready: true },
    { id: "windows", label: "Windows 桌面软件", note: "扩展方向", ready: false },
    { id: "legacy-desktop", label: "传统桌面软件", note: "扩展方向", ready: false },
  ];
  const targetOptions: Array<{ id: TargetPlatform; label: string; note: string; ready: boolean }> = [
    { id: "harmony-phone", label: "HarmonyOS 手机", note: "已验证", ready: true },
    { id: "harmony-pc", label: "HarmonyOS PC", note: "规划中", ready: false },
    { id: "vehicle", label: "车载系统", note: "规划中", ready: false },
  ];
  const pathReady = sourceOptions.find((o) => o.id === sourcePlatform)?.ready && targetOptions.find((o) => o.id === targetPlatform)?.ready;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const value = sourceValue.trim();
    const workspace = workspaceDir.trim();
    if (!name.trim()) return setError("请先填写项目名称");
    if (!pathReady) return setError("该迁移路径为扩展方向，当前版本已验证 Android App → HarmonyOS 手机");
    if (sourceType === "github" && !/^https?:\/\/(www\.)?github\.com\/.+/.test(value)) return setError("请输入有效的 GitHub 仓库链接");
    if (sourceType === "zip" && !/\.zip$/i.test(value)) return setError("请选择 .zip 格式的源项目压缩包");
    if (executionMode === "codearts-agentteam") {
      if (!workspace) return setError("真实执行需要指定 CodeArts 工作区目录");
      if (!isAbsoluteWindowsPath(workspace)) return setError("工作区目录需为本机绝对路径，例如 D:\\code\\workspace");
    }
    const project = mockService.createProject({ name: name.trim(), sourceType, sourceValue: value, executionMode, workspaceDir: executionMode === "codearts-agentteam" ? workspace : undefined, sourcePlatform, targetPlatform, runModel: executionMode === "codearts-agentteam" ? projectModel : undefined });
    navigate(`/projects/${project.id}`);
  };
  return <div className="new-project-page"><div className="page-heading"><div><h1>新建迁移任务</h1><p className="heading-subtitle">选择源平台与目标平台，启动跨平台迁移与一致性验证。</p></div><Link to="/" className="ghost-button">← 返回项目总览</Link></div><div className="new-project-layout"><form className="intake-card" onSubmit={submit}>
    <div className="card-title-row"><div><span className="section-index">01</span><h2>选择迁移路径</h2></div><span className="required-note">必填</span></div>
    <label className="field-label">源平台<span className="field-sub">当前已验证 Android；其余为架构预留的扩展方向</span>
      <div className="platform-picker">{sourceOptions.map((option) => <button type="button" key={option.id} className={`platform-option ${sourcePlatform === option.id ? "active" : ""} ${option.ready ? "" : "dashed"}`} onClick={() => { setSourcePlatform(option.id); setError(""); }}><b>{option.label}</b><small>{option.note}</small></button>)}</div>
    </label>
    <label className="field-label">目标平台<span className="field-sub">当前已验证 HarmonyOS 手机；PC 与车载为规划中</span>
      <div className="platform-picker">{targetOptions.map((option) => <button type="button" key={option.id} className={`platform-option ${targetPlatform === option.id ? "active" : ""} ${option.ready ? "" : "dashed"}`} onClick={() => { setTargetPlatform(option.id); setError(""); }}><b>{option.label}</b><small>{option.note}</small></button>)}</div>
    </label>
    {!pathReady && <div className="form-error">! 该迁移路径为扩展方向，暂不可执行。当前版本已完成 Android App → HarmonyOS 手机的端到端验证。</div>}
    <div className="field-divider" />
    <div className="card-title-row"><div><span className="section-index">02</span><h2>源项目</h2></div></div>
    <div className="source-toggle"><button type="button" className={sourceType === "github" ? "toggle active" : "toggle"} onClick={() => { setSourceType("github"); setSourceValue(""); setError(""); }}>GitHub 链接</button><button type="button" className={sourceType === "zip" ? "toggle active" : "toggle"} onClick={() => { setSourceType("zip"); setSourceValue(""); setError(""); }}>源项目 ZIP</button></div>
    {sourceType === "github" ? <label className="field-label">源项目仓库链接<input value={sourceValue} onChange={(event) => setSourceValue(event.target.value)} placeholder="https://github.com/example/project" /></label> : <label className="file-drop"><input type="file" accept=".zip" onChange={(event) => { setSourceValue(event.target.files?.[0]?.name ?? ""); setError(""); }} /><span className="upload-icon">↑</span><b>{sourceValue || "点击选择源项目压缩包"}</b><small>{sourceValue ? "已选择；真实构建前需上传到 CodeArts 工作目录" : "支持 .zip，建议不超过 50 MB"}</small></label>}
    <div className="field-divider" />
    <div className="card-title-row compact"><div><span className="section-index">03</span><h2>任务信息</h2></div></div>
    <label className="field-label">迁移项目名称<input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：待办应用跨平台迁移" /></label>
    <div className="execution-mode-picker"><div className="mode-picker-heading"><b>选择执行引擎</b></div><button type="button" className={executionMode === "codearts-agentteam" ? "mode-option active" : "mode-option"} onClick={() => setExecutionMode("codearts-agentteam")}><strong>CodeArts Space / AgentTeam</strong><small>真实大模型推理、团队调度和工具执行</small></button><button type="button" className={executionMode === "demo" ? "mode-option active" : "mode-option"} onClick={() => setExecutionMode("demo")}><strong>本地演示</strong><small>仅播放固定数据，不产生真实构建</small></button></div>
    {executionMode === "codearts-agentteam" && <label className="field-label">执行模型<select value={projectModel} onChange={(event) => { setProjectModel(event.target.value); saveRunModel(event.target.value); }}>{modelOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select><small className="field-note">AgentTeam 真实执行使用的模型；含 Space 内置模型与客户端已配置模型。</small></label>}
    {executionMode === "codearts-agentteam" && <label className="field-label">CodeArts 工作区目录<input value={workspaceDir} onChange={(event) => setWorkspaceDir(event.target.value)} placeholder="D:\\code\\migration-workspace" /><small className={`field-note ${dirStatus === "exists" ? "mint-text" : dirStatus === "invalid" ? "error-text" : ""}`}>{dirNotes[dirStatus]}</small></label>}
    {error && <div className="form-error">! {error}</div>}
    <button className="primary-button wide" type="submit" disabled={!pathReady}>启动迁移 <span className="button-arrow">→</span></button>
  </form><aside className="intake-aside"><div className="aside-card"><p className="eyebrow">执行流程</p><h3>四阶段迁移门禁</h3><div className="preview-steps">{[{ n: "01", t: "基线建立", d: "冻结迁什么与验收标准" }, { n: "02", t: "深度理解", d: "功能语义地图与行为契约" }, { n: "03", t: "原生迁移", d: "受控原生化组件映射" }, { n: "04", t: "差分修复", d: "双端重放至 MATCH" }].map((step, index) => <div className="preview-step" key={step.n}><span>{step.n}</span><div><b>{step.t}</b><small>{step.d}</small></div>{index < 3 && <i>↓</i>}</div>)}</div></div><div className="aside-tip"><span>ⓘ</span><p>迁移单位是“用户功能与行为”而非页面：语义契约作为中间层，使源端与目标端解耦，同一套验证方法可复用到其他平台组合。当前已验证 Android → HarmonyOS，其余路径为扩展方向。</p></div></aside></div></div>;
}


function LiveProjectPage() {
  const { id } = useParams();
  const project = useProject(id);
  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => {
    const syncId = searchParams.get("sync");
    if (!syncId || !project || project.demo) return;
    const phaseNo = phaseFromNumber(Number(searchParams.get("phase") ?? project.currentPhase));
    const target = project.phases.find((item) => item.number === phaseNo);
    if (!target || target.execution?.status === "succeeded") { setSearchParams({}, { replace: true }); return; }
    void getCodeArtsMessages(syncId, loadCodeArtsCredentials()).then((messages) => {
      const text = messages
        .filter((item) => item.info?.role === "assistant" && item.info?.time?.completed)
        .map((item) => (item.parts ?? []).filter((part) => part.type === "text" && part.text?.trim()).map((part) => part.text).join("\n"))
        .join("\n\n");
      if (text.trim()) {
        mockService.recordCodeArtsExecution?.(project.id, phaseNo, { mode: "codearts-agentteam", status: "succeeded", sessionId: syncId, agent: "team-leader", completedAt: new Date().toISOString(), response: text });
      }
      setSearchParams({}, { replace: true });
    }).catch(() => setSearchParams({}, { replace: true }));
  }, [searchParams, project]);
  const [selectedPhase, setSelectedPhase] = useState<PhaseNumber>(project?.currentPhase ?? 1);
  const [reviewOpen, setReviewOpen] = useState(false);
  useEffect(() => { if (project?.currentPhase) setSelectedPhase(project.currentPhase); }, [project?.currentPhase]);
  if (!project) return <NotFound />;
  const selected = project.phases.find((phase) => phase.number === selectedPhase) ?? project.phases[0];
  const canReview = selected.status === "review_required";
  const real = project.executionMode === "codearts-agentteam" && !project.demo;
  const coveredFeatures = project.features.filter((feature) => feature.status === "covered").length;
  const performReview = (review: Review) => { mockService.reviewPhase(project.id, selected.number, review); setReviewOpen(false); };
  return <div className="workspace-page"><div className="workspace-header"><div className="breadcrumb"><Link to="/">项目总览</Link><span>/</span><b>{project.name}</b></div><div className="workspace-actions"><span className={real ? "live-tag" : "demo-tag"}>{real ? "真实执行 · CodeArts" : "演示数据"}</span><Link to={`/projects/${project.id}/report`} className="ghost-button small">查看报告</Link><Link to={`/projects/${project.id}/delivery`} className="primary-button small">交付中心 <span>→</span></Link></div></div><div className="workspace-title"><h1>{project.name} <StatusBadge status={project.status === "completed" ? "completed" : project.status === "review" ? "review_required" : "running"} /></h1><p className="heading-subtitle">{project.id.toUpperCase()} · {project.source.type === "github" ? "GitHub 源码" : "Android ZIP"} · {real ? "CodeArts AgentTeam" : "本地演示"} · revision {selected.revision}.0</p></div><div className="overview-strip"><div className="overview-item"><small>功能覆盖度</small><b>{Math.round((coveredFeatures / project.features.length) * 100)}%<span>{coveredFeatures}/{project.features.length} 项已确认</span></b></div><div className="overview-item"><small>本阶段交付物</small><b>{selected.artifacts.length} 项</b></div><div className="overview-item"><small>当前阶段</small><b>{String(project.currentPhase).padStart(2, "0")} · {selected.shortTitle}</b></div><div className="overview-item"><small>运行模式</small><b>{real ? "CodeArts AgentTeam" : "本地演示"}</b></div></div><PhaseRail phases={project.phases} selected={selectedPhase} onSelect={setSelectedPhase} /><EvidenceRibbon phase={selected} real={real} /><div className="workspace-grid"><section className="workspace-center"><PhaseContent project={project} phase={selected} /><div className="review-bar"><div><span className={`review-dot ${canReview ? "active" : ""}`} /><div><b>{canReview ? "本阶段等待人工审核" : selected.status === "running" ? (real ? "CodeArts AgentTeam 正在执行" : "演示工作流正在执行") : statusLabels[selected.status]}</b>{canReview && <small>确认真实会话结果后才能进入下一阶段</small>}</div></div><div className="review-actions">{selected.status === "running" && !real && <><button className="icon-button" onClick={() => selected.paused ? mockService.resumePhase(project.id, selected.number) : mockService.pausePhase(project.id, selected.number)}>{selected.paused ? "▶ 继续" : "Ⅱ 暂停"}</button><button className="icon-button" onClick={() => mockService.skipPhase(project.id, selected.number)}>跳过等待</button></>}{canReview && <button className="primary-button" onClick={() => setReviewOpen(true)}>打开审核 <span>→</span></button>}{(selected.status === "approved" || selected.status === "completed") && !real && <button className="icon-button" onClick={() => mockService.restartPhase(project.id, selected.number)}>↻ 重新演示</button>}</div></div></section><aside className="workspace-right"><AgentTimeline phase={selected} /><RunControls project={project} phase={selected} /></aside></div><WorkspaceFooter project={project} phase={selected} real={real} />{reviewOpen && <ReviewDialog phase={selected} onClose={() => setReviewOpen(false)} onSubmit={performReview} />}</div>;
}

function WorkspaceFooter({ project, phase, real }: { project: Project; phase: Phase; real: boolean }) {
  return <div className="workspace-footer"><span><i className={phase.status === "review_required" ? "waiting" : ""} />{phase.status === "review_required" ? "审核决定将写入迁移报告" : "阶段证据持续保存"}</span><span>revision {phase.revision}.0 · {real ? "CodeArts AgentTeam" : "演示工作流"}</span><Link to={`/projects/${project.id}/report`}>查看完整证据报告 →</Link></div>;
}

function EvidenceRibbon({ phase, real }: { phase: Phase; real: boolean }) {
  const evidenceState = phase.execution?.status === "succeeded" ? "已收到真实返回" : phase.execution?.status === "failed" ? "真实会话失败" : phase.status === "review_required" ? "证据待人工确认" : "正在采集";
  return <div className={`evidence-ribbon ${real ? "is-real" : "is-demo"}`}><div className="evidence-ribbon-main"><span className="evidence-ribbon-dot" /><div><b>{real ? "CodeArts 证据链" : "演示证据链"}</b><span>{evidenceState} · 当前阶段 {phase.code}</span></div></div><div className="evidence-ribbon-items"><span><b>{phase.events.length}</b> 条事件</span><span><b>{phase.artifacts.length}</b> 项产物</span><span><b>{phase.execution?.sessionId ? "已绑定" : "未绑定"}</b> 会话</span></div><span className="evidence-ribbon-note">{real ? "结果来自真实 AgentTeam 会话" : "固定数据，仅用于现场演示"}</span></div>;
}

function PhaseRail({ phases, selected, onSelect }: { phases: Phase[]; selected: PhaseNumber; onSelect: (phase: PhaseNumber) => void }) {
  return <div className="phase-rail">{phases.map((phase, index) => <button key={phase.number} className={`phase-rail-item ${selected === phase.number ? "selected" : ""} ${statusClasses[phase.status]}`} onClick={() => onSelect(phase.number)}><span className="phase-number">{phase.code}</span><span className="phase-rail-text"><b>{phase.shortTitle}</b><small>{phase.title.split("·")[1]?.trim()}</small></span><span className="phase-rail-status">{phase.status === "running" ? <span className="spinner" /> : phase.status === "approved" || phase.status === "completed" ? "✓" : phase.status === "review_required" ? "!" : "·"}</span>{index < phases.length - 1 && <i className="rail-connector" />}</button>)}</div>;
}

function PhaseContent({ project, phase }: { project: Project; phase: Phase }) {
  if (project.executionMode === "codearts-agentteam" && !project.demo) return <RealPhaseContent project={project} phase={phase} />;
  if (phase.number === 1) return <PhaseOne phase={phase} />;
  if (phase.number === 2) return <PhaseTwo phase={phase} />;
  if (phase.number === 3) return <PhaseThree phase={phase} />;
  return <PhaseFour phase={phase} />;
}

/** 真实执行阶段内容：团队任务与分工 + 对话流 + 交付变更 直观展示 */
function LiveFlowMessage({ message }: { message: CodeArtsMessage }) {
  const role = message.info?.role;
  const isUser = role === "user";
  const who = typeof message.info?.agent === "string" && message.info.agent
    ? message.info.agent
    : isUser ? "用户工单" : "Agent";
  const tools = (message.parts ?? []).filter((part) => part.tool) as Array<{ tool: string; state?: { status?: string } }>;
  const text = (message.parts ?? []).filter((part) => part.type === "text" && part.text?.trim()).map((part) => part.text).join(" ").trim();
  const time = message.info?.time?.created ? formatTime(new Date(message.info.time.created).toISOString()) : "";
  const done = Boolean(message.info?.time?.completed);
  return <div className={`flow-msg ${isUser ? "user" : "assistant"}`}>
    <div className="flow-msg-head">
      <span className="flow-msg-role">{isUser ? "工单" : who}</span>
      <small>{time}{!isUser && (done ? " · 完成" : " · 进行中")}</small>
    </div>
    {tools.length > 0 && <div className="flow-tools">{tools.map((tool, index) => <span key={`${tool.tool}-${index}`} className={`flow-tool ${tool.state?.status === "completed" ? "ok" : ""}`}>‹› {tool.tool}{tool.state?.status === "completed" ? " ✓" : " ◌"}</span>)}</div>}
    {text && <p className="flow-text">{text.length > 180 ? `${text.slice(0, 180)}…` : text}</p>}
  </div>;
}

function RealPhaseContent({ project, phase }: { project: Project; phase: Phase }) {
  const eyebrow = phase.number === 1 ? "阶段 01 · 迁移基线建立" : phase.number === 2 ? "阶段 02 · 源软件深度理解" : phase.number === 3 ? "阶段 03 · 目标平台原生迁移" : "阶段 04 · 一致性验证与自动修复";
  const execution = phase.execution;
  const sessionId = execution?.sessionId ?? project.activeSessionId;
  const [team, setTeam] = useState<AgentTeamState | null>(null);
  const [messages, setMessages] = useState<CodeArtsMessage[]>([]);
  const [summary, setSummary] = useState<{ additions: number; deletions: number; files: number } | null>(null);
  const [flowExpanded, setFlowExpanded] = useState(false);
  useEffect(() => {
    if (!sessionId) return;
    let alive = true;
    const load = async () => {
      const [teamState, msgs, sum] = await Promise.all([
        fetchTeamState(sessionId),
        getCodeArtsMessages(sessionId, loadCodeArtsCredentials()).catch(() => [] as CodeArtsMessage[]),
        fetchSessionSummary(sessionId),
      ]);
      if (!alive) return;
      if (teamState && (Object.keys(teamState.members).length || teamState.tasks.length)) setTeam(teamState);
      if (msgs.length) setMessages(msgs);
      if (sum) setSummary(sum);
    };
    void load();
    const timer = window.setInterval(() => { void load(); }, 5000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [sessionId]);
  const flowMessages = flowExpanded ? messages.slice(-40) : messages.slice(-6);
  const response = execution?.response?.trim();
  const modelLabel = project.runModel ? project.runModel.split("::").pop() : undefined;
  return <div className="phase-content">
    <PhaseHeader phase={phase} eyebrow={eyebrow} />
    <div className="live-meta">
      <span className={`execution-status ${execution?.status ?? "idle"}`}>{execution?.status ?? "idle"}</span>
      <span>会话 <code>{sessionId ? `${sessionId.slice(0, 18)}…` : "未创建"}</code></span>
      {modelLabel && <span>模型 <b>{modelLabel}</b></span>}
      {summary && <span className="live-meta-diff">变更 <b>+{summary.additions}</b> / <b>-{summary.deletions}</b> · {summary.files} 文件</span>}
    </div>
    <div className="live-grid">
      <div className="live-card live-team">
        <p className="lp-eyebrow">团队任务与分工</p>
        {team && team.tasks.length > 0 ? <div className="live-tasks">{team.tasks.map((task) => <div className="live-task-row" key={task.id}>
          <span className={`team-task-dot ${task.status}`}>{task.status === "completed" ? "✓" : task.status === "in_progress" || task.status === "running" ? "◌" : "·"}</span>
          <span className="live-task-content">{task.content}{task.owner_name ? ` — ${task.owner_name}` : ""}{task.blocked_by?.length ? `（依赖 ${task.blocked_by.join(",")}）` : ""}</span>
          <em>{task.status}</em>
        </div>)}</div> : <p className="field-note">尚未组队或无任务——leader 仍在分析阶段。</p>}
        {team && Object.keys(team.members).length > 0 && <div className="live-members">{Object.entries(team.members).map(([name, member]) => <div className="live-member" key={name}>
          <span className={`team-member-dot ${member.status}`} />
          <b>{name}</b>
          <small>{member.agent_type === "team-leader" ? "队长 · 编排" : member.description || "队员 · 执行"}</small>
          <em>{member.status}</em>
        </div>)}</div>}
      </div>
      <div className="live-card live-flow">
        <div className="live-flow-head">
          <p className="lp-eyebrow" style={{ margin: 0 }}>对话流{messages.length ? `（${messages.length} 条 · 5 秒刷新）` : ""}</p>
          {messages.length > 6 && <button className="text-sync-button" onClick={() => setFlowExpanded((value) => !value)}>{flowExpanded ? "收起" : `展开全部 ${Math.min(messages.length, 40)} 条`}</button>}
        </div>
        {flowMessages.length > 0 ? <div className="live-flow-list">{flowMessages.map((message, index) => <LiveFlowMessage key={`${message.info?.id ?? index}`} message={message} />)}</div> : <p className="field-note">{sessionId ? "等待会话消息…" : "启动真实 AgentTeam 后此处展示工单、派发与回复的实时对话流。"}</p>}
      </div>
    </div>
    <div className="live-card live-report">
      <p className="lp-eyebrow">阶段汇总与交付</p>
      {execution?.error && <div className="real-error">{execution.error}</div>}
      {response ? <pre className="real-response">{response}</pre> : <div className="real-waiting">页面不会生成固定分析或演示数据；AgentTeam 返回真实结果后，这里才会显示可审核的汇总报告。</div>}
    </div>
    {phase.number === 2 && phase.emulator && <div className="runner-placeholder"><div><h3>等待真实 Android 模拟器</h3><p>当前只保留 Runner 接口位置；不会用本地帧流冒充真实执行。</p></div><EmulatorPanel stream={phase.emulator} /></div>}
    {phase.number === 4 && <div className="runner-placeholder"><div><h3>等待真实 HarmonyOS 模拟器</h3><p>一致性判别将在真实鸿蒙运行轨迹和 Android 基线都返回后生成。</p></div></div>}
  </div>;
}

function PhaseHeader({ phase, eyebrow }: { phase: Phase; eyebrow: string }) {
  return <div className="phase-header"><div><p className="eyebrow">{eyebrow} <span className="phase-live-label">{phase.status === "running" ? "· 执行中" : phase.status === "review_required" ? "· 待审核" : ""}</span></p><h2>{phase.title}</h2><p>{phase.description}</p></div><div className="phase-progress"><strong>{String(phase.progress).padStart(2, "0")}<small>%</small></strong><span>阶段进度</span></div></div>;
}

/** 四阶段统一结构：一句话目标 + 3 个核心动作 + 1 个最能说明问题的可视化 */

/** 四阶段统一结构：一句话目标 + 3 个核心动作 + 1 个最能说明问题的可视化 + 阶段门禁
 *  内容口径对齐 android-harmony-migration-controller 及三个专家 Skill 的真实工作流。 */

function PhaseActions({ items }: { items: string[] }) {
  return <div className="phase-actions">{items.map((action, index) => <div className="phase-action" key={action}><i>{index + 1}</i><span>{action}</span></div>)}</div>;
}

interface PhaseAgentInfo { name: string; short: string; duty: string; badge?: string; }

/** 各阶段协作智能体（对齐 skill 六代理模型与 roles-and-authority 角色定义） */
const PHASE_AGENTS: Record<number, PhaseAgentInfo[]> = {
  1: [
    { name: "迁移控制器", short: "控", duty: "冻结输入、签发工单、重算机器门禁、路由返工", badge: "全程在岗" },
    { name: "人工审核员", short: "审", duty: "机器 PASS 后审核放行：APPROVED / REWORK / DEVIATION", badge: "模型永不放行" },
  ],
  2: [
    { name: "Android 语义分析师", short: "析", duty: "功能语义地图与行为契约，逐条锚定源码 file:line" },
    { name: "Android 运行验证官", short: "验", duty: "高风险功能真机实跑行为链，密封运行证据", badge: "Runtime Oracle" },
    { name: "迁移控制器", short: "控", duty: "源码↔运行对账四态判定与 Gate 2 重算" },
  ],
  3: [
    { name: "Harmony 架构负责人", short: "架", duty: "承载面规划与 UI 蓝图冻结，唯一可冻结环境角色" },
    { name: "导航与页面壳代理", short: "航", duty: "路由注册表与页面壳，不写业务逻辑" },
    { name: "工具链与脚手架代理", short: "链", duty: "构建 / 安装 / 启动冒烟与密封截图" },
    { name: "公共 UI 代理", short: "UI", duty: "主题、色板、加载 / 空 / 错误壳等通用资产" },
    { name: "能力契约代理", short: "约", duty: "编译期 interface-only 契约，无实现无假数据" },
    { name: "架构验收代理", short: "收", duty: "只验证不修改，视觉逐张核验密封截图", badge: "不得自证" },
  ],
  4: [
    { name: "功能实现负责人", short: "实", duty: "按功能工单实现，接线语义数据探针" },
    { name: "鸿蒙 UI 代理", short: "UI", duty: "原生组件落地，视觉还原达标" },
    { name: "业务与数据代理", short: "数", duty: "数据契约对接与持久化实现" },
    { name: "功能属主", short: "主", duty: "对 assigned 功能端到端负责，消费工单必读清单" },
    { name: "原生能力代理", short: "能", duty: "平台系统能力（权限/通知等）的原生对接" },
    { name: "视觉资产代理", short: "视", duty: "图标/图片等视觉资产迁移与适配" },
    { name: "模拟器验证执行者", short: "执", duty: "双端按各自步骤执行，采集四类结果" },
    { name: "一致性验收代理", short: "收", duty: "Gate 4 独立重算，生产者证据不能自证", badge: "不得自证" },
    { name: "迁移控制器", short: "控", duty: "差分结果路由修复回环，两轮未收敛转人工", badge: "全程在岗" },
  ],
};

function PhaseAgents({ phaseNumber }: { phaseNumber: number }) {
  const agents = PHASE_AGENTS[phaseNumber] ?? [];
  if (!agents.length) return null;
  return <div className="phase-agents">
    <p className="lp-eyebrow">阶段协作智能体 · 每个角色独立留痕，一个任务不能充当两个角色</p>
    <div className="phase-agent-grid">{agents.map((agent) => <div className="phase-agent-card" key={agent.name}>
      <span className="phase-agent-avatar">{agent.short}</span>
      <span className="phase-agent-info"><b>{agent.name}</b><small>{agent.duty}</small></span>
      {agent.badge && <em className="agent-source-badge">{agent.badge}</em>}
    </div>)}</div>
  </div>;
}

function PhaseGate({ gate, checks }: { gate: number; checks: string }) {
  return <div className="phase-gate"><b>Gate {gate}</b><span>{checks}</span><em>机器判定 → 人工审核放行 · 证据不可变留痕</em></div>;
}

function PhaseOne({ phase }: { phase: Phase }) {
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow="阶段 01 · 迁移基线建立" />
    <div className="phase-goal">明确“迁什么、迁到哪、什么算迁移成功”。</div>
    <PhaseActions items={[
      "识别功能范围、数据范围与关键业务能力，划定纳入 / 排除清单",
      "冻结源码 Git 版本、APK 指纹、双端运行环境与工具策略",
      "确定等价判据与允许的平台原生适配边界，形成统一验收标准",
    ]} />
    <div className="phase-viz">
      <p className="lp-eyebrow">迁移范围与冻结基线</p>
      <div className="lp-flow">
        <div className="lp-flow-col"><div className="lp-node solid">Android / Cresto<small>源码 + APK 冻结</small></div></div>
        <div className="lp-flow-arrow">→</div>
        <div className="lp-node contract">12 项核心功能<small>功能 / 数据 / 环境三重冻结</small></div>
        <div className="lp-flow-arrow">→</div>
        <div className="lp-flow-col"><div className="lp-node solid">HarmonyOS<small>目标环境冻结</small></div></div>
      </div>
      <div className="phase-contract-quote">
        <b>核心等价契约</b>
        <p>UI 结构与交互可按目标平台原生规范改造，但用户意图、存储数据、业务计算、状态转换、可观察结果、持久化与副作用必须语义等价——全部四个阶段共用这一条判据。</p>
      </div>
    </div>
    <PhaseAgents phaseNumber={1} />
    <PhaseGate gate={1} checks="冻结清单完整 · 范围无歧义 · 验收标准可执行" />
  </div>;
}

function PhaseTwo({ phase }: { phase: Phase }) {
  const contract = [
    { k: "意图", v: "把界面切换为英文" },
    { k: "操作", v: "设置 → 语言 → English" },
    { k: "数据", v: "locale = en" },
    { k: "可见结果", v: "全部文案变英文" },
    { k: "重启持久", v: "杀进程重启仍为英文" },
    { k: "副作用", v: "无系统级影响" },
  ];
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow="阶段 02 · 源软件深度理解" />
    <div className="phase-goal">不仅识别页面，更理解每个功能实际是怎么工作的。</div>
    <PhaseActions items={[
      "扫描源码建立功能语义地图：每个功能锚定到源码 file:line",
      "逐功能编写行为契约六要素：意图 / 操作 / 数据 / 可见结果 / 重启持久 / 副作用",
      "高风险功能在 Android 真机实跑行为链，建立可判定的运行基线",
    ]} />
    <div className="phase-viz phase-two-cols">
      <div className="phase-contract">
        <p className="lp-eyebrow">Behavior Contract · 切换语言</p>
        <div className="phase-contract-grid">{contract.map((item) => <div className="phase-contract-cell" key={item.k}><small>{item.k}</small><span>{item.v}</span></div>)}</div>
        <div className="phase-verify-modes"><span className="lp-match">RUNTIME 真机实跑</span><span className="agent-source-badge neutral">SOURCE_CONFIRM 源码确认</span></div>
        <p className="phase-note">增删改 / 持久化 / 语言 / 主题类功能必须真机验证；纯展示与容器宿主由源码确认，不为证明“被访问过”硬跑。</p>
      </div>
      <div className="lp-shot">Android 真机截图<br /><small>替换为实际运行截图</small></div>
    </div>
    <div className="phase-stats"><span><b>45</b> 页面</span><span><b>XX</b> 项功能语义</span><span><b>XX</b> 条行为契约</span><span><b>XX</b> 条运行证据</span></div>
    <PhaseAgents phaseNumber={2} />
    <PhaseGate gate={2} checks="功能全覆盖 · 契约完整 · 高风险均已验证或显式记 GAP" />
  </div>;
}

function PhaseThree({ phase }: { phase: Phase }) {
  const mappings = [
    ["底部导航", "Tabs"],
    ["页面跳转", "Navigation + NavPathStack"],
    ["弹层", "Dialog / Sheet"],
    ["开关", "Toggle"],
    ["长列表", "List + LazyForEach"],
  ];
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow="阶段 03 · 目标平台原生迁移" />
    <div className="phase-goal">保留原软件的视觉与信息结构，同时转化为目标平台的原生实现方式。</div>
    <PhaseActions items={[
      "按功能承载面搭壳：页面建路由、弹层挂模态、容器不建壳",
      "冻结 UI 蓝图：原应用视觉与信息结构高保留，标准交互映射原生组件",
      "建立数据契约接口（仅接口不含业务逻辑），打通数据进出口",
    ]} />
    <div className="phase-viz phase-two-cols">
      <div className="phase-mapping">
        <p className="lp-eyebrow">原生组件映射（受控原生化，非自由重设计）</p>
        {mappings.map(([from, to]) => <div className="phase-mapping-row" key={from}><span>{from}</span><i>→</i><b>{to}</b></div>)}
      </div>
      <div className="lp-case-grid phase-mini-compare">
        <div className="lp-shot compact">迁移前 · Android GUI<small>截图位</small></div>
        <div className="lp-shot compact">迁移后 · HarmonyOS GUI<small>截图位</small></div>
      </div>
    </div>
    <p className="phase-note">自定义交互仅在原生组件无法表达时允许，且必须登记理由——从规则上杜绝“用 ArkUI 写出 Android 味 UI”。</p>
    <PhaseAgents phaseNumber={3} />
    <PhaseGate gate={3} checks="承载面全覆盖 · 数据契约无孤儿 · 构建冒烟链通过" />
  </div>;
}

function PhaseFour({ phase }: { phase: Phase }) {
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow="阶段 04 · 一致性验证与自动修复" />
    <div className="phase-goal">迁过去不算完成，功能结果一致才算完成。</div>
    <PhaseActions items={[
      "同一份行为契约双端各自执行：Android 是基准 oracle，HarmonyOS 是被验证方",
      "机器对比四类结果：可观察 / 数据 / 持久化 / 副作用——比结果，不比路径",
      "DIFF 自动定位、只修迁移端并重放验证；两轮未收敛转人工接管",
    ]} />
    <div className="phase-viz">
      <div className="phase-diff">
        <div className="phase-diff-card">Android（基准）<b>切换语言 → 重启后英文</b></div>
        <span className="lp-match diff">Persistence DIFF</span>
        <div className="phase-diff-card">HarmonyOS 初版<b>切换语言 → 重启恢复中文</b></div>
      </div>
      <div className="phase-fixchain">定位 SettingsRepository <i>→</i> 只修 HarmonyOS 持久化 <i>→</i> 二次重放 <i className="ok">→ MATCH ✓</i></div>
      <div className="phase-fourdims"><span>observable</span><span>semantic data</span><span>persistence</span><span>side effect</span></div>
      <div className="lp-case-grid phase-mini-compare">
        <div className="lp-shot compact">Android 原版<small>最终截图位</small></div>
        <div className="lp-shot compact">HarmonyOS 最终版<small>最终截图位</small></div>
      </div>
      <div className="phase-stats"><span><b>XX/XX</b> 核心功能通过</span><span><b>XX/XX</b> 持久化测试</span><span><b>PASS</b> 构建安装</span><span><b>0</b> 占位页面</span></div>
    </div>
    <PhaseAgents phaseNumber={4} />
    <PhaseGate gate={4} checks="断言全过 · 数据对账无未解释差异 · 视觉还原达标" />
  </div>;
}

function EmulatorPanel({ stream, compact = false }: { stream: EmulatorStream; compact?: boolean }) {
  const [playing, setPlaying] = useState(stream.status !== "offline");
  const [frameIndex, setFrameIndex] = useState(stream.currentFrame);
  useEffect(() => { setFrameIndex(stream.currentFrame); }, [stream.currentFrame, stream.platform]);
  useEffect(() => {
    if (!playing || stream.status === "offline" || !stream.frames.length) return;
    const timer = window.setInterval(() => setFrameIndex((current) => (current + 1) % stream.frames.length), 1500);
    return () => window.clearInterval(timer);
  }, [playing, stream.status, stream.frames.length]);
  const frame = stream.frames[frameIndex % Math.max(1, stream.frames.length)] ?? { id: "empty", title: "等待模拟器", subtitle: "连接后开始", accent: "#556078", detail: "当前没有画面数据" };
  const isAndroid = stream.platform === "android";
  return <div className={`emulator-card ${compact ? "compact" : ""} platform-${stream.platform}`} role="region" aria-label={`${isAndroid ? "Android" : "HarmonyOS"} 模拟器${stream.streamType === "mock" ? "演示帧流" : "实时画面"}`}><div className="emulator-toolbar"><div className="emulator-name"><span className={`platform-dot ${stream.platform}`} />{isAndroid ? "Android Emulator" : "HarmonyOS Emulator"}<small>{stream.streamType === "mock" ? "演示帧流" : stream.streamType.toUpperCase()}</small></div><div className="emulator-status"><span className={`status-light ${stream.status}`} />{stream.status === "live" ? "LIVE" : stream.status === "replay" ? "REPLAY" : "OFFLINE"}<span className="emulator-menu">···</span></div></div><div className="device-frame"><div className="device-screen" aria-live="polite"><div className="device-topbar"><span>{isAndroid ? "9:41" : "10:28"}</span><span>▮▮▮ ◇</span></div><div className="device-appbar"><span className="app-back">‹</span><b>{frame.title}</b><span>···</span></div><div className="device-body" style={{ "--screen-accent": frame.accent } as React.CSSProperties}><div className="screen-orbit" /><span className="screen-kicker">{isAndroid ? "Android 基线" : "HarmonyOS · ArkUI"}</span><h4>{frame.title}</h4><p className="screen-subtitle">{frame.subtitle}</p><div className="screen-metric" style={{ color: frame.accent }}>{frame.metric ?? "QC"}</div><div className="screen-card"><span className="screen-card-dot" style={{ background: frame.accent }} /><span>{frame.detail}</span></div><div className="screen-actions"><i /><i /><i /></div><div className="screen-nav"><span className="active" /><span /><span /></div></div><div className="device-home-indicator" /></div></div><div className="emulator-foot"><div className="emulator-step"><span className="step-index">{String(frameIndex + 1).padStart(2, "0")}</span><span><b>{stream.currentStep === "等待开始" ? frame.detail : stream.currentStep}</b><small>语义测试步骤 · {frameIndex + 1}/{stream.frames.length}</small></span></div><div className="emulator-controls"><button onClick={() => setPlaying((value) => !value)} aria-label={playing ? "暂停" : "播放"}>{playing ? "Ⅱ" : "▶"}</button><button onClick={() => setFrameIndex((value) => (value + 1) % Math.max(1, stream.frames.length))} aria-label="下一帧">→</button></div></div></div>;
}

function AgentTimeline({ phase }: { phase: Phase }) {
  const events = phase.events.slice(-10).reverse();
  const sessionId = phase.execution?.sessionId;
  const [team, setTeam] = useState<AgentTeamState | null>(null);
  useEffect(() => {
    if (!sessionId) return;
    let alive = true;
    const load = async () => {
      const state = await fetchTeamState(sessionId);
      if (alive && state && (Object.keys(state.members).length || state.tasks.length)) setTeam(state);
    };
    void load();
    const timer = window.setInterval(() => { void load(); }, 5000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [sessionId]);
  return <div className="timeline-panel" role="region" aria-live="polite" aria-label="AgentTeam 执行时间线"><div className="timeline-heading"><div><h3>执行时间线</h3></div><span className="event-live"><i /> {phase.execution?.mode === "codearts-agentteam" ? (phase.execution.status === "running" || phase.execution.status === "starting" ? "CodeArts 实时" : "CodeArts 已归档") : phase.status === "running" ? "演示实时" : "演示已固化"}</span></div>{events.length ? <div className="timeline-list">{events.map((event) => <div className="timeline-event" key={event.id}><span className={`timeline-icon event-${event.type}`}>{event.type === "thinking" ? "•" : event.type === "tool" ? "‹›" : event.type === "build" ? "≡" : event.type === "test" ? "✓" : "·"}</span><div><b>{event.agent}</b><p>{event.message}</p><small>{formatTime(event.timestamp)}</small></div></div>)}</div> : <div className="timeline-empty"><span>·</span><p>等待 Agent Team 开始工作<br /><small>阶段启动后会显示实时事件</small></p></div>}{team && <div className="team-state">
    <p className="eyebrow">AgentTeam 团队花名册</p>
    <div className="team-members">{Object.entries(team.members).map(([name, member]) => <div className="team-member-row" key={name}>
      <span className={`team-member-dot ${member.status}`} />
      <b>{name}</b>
      <small>{member.agent_type === "team-leader" ? "队长 · 编排派发" : member.description || "队员 · 执行"}</small>
      <em>{member.status}</em>
    </div>)}</div>
    {team.tasks.length > 0 && <>
      <p className="eyebrow">团队任务清单</p>
      <div className="team-tasks">{team.tasks.map((task) => <div className="team-task-row" key={task.id}>
        <span className={`team-task-dot ${task.status}`}>{task.status === "completed" ? "✓" : task.status === "in_progress" || task.status === "running" ? "◌" : "·"}</span>
        <span>{task.content}{task.owner_name ? ` — ${task.owner_name}` : ""}</span>
        <em>{task.status}</em>
      </div>)}</div>
    </>}
  </div>}<div className="timeline-footer"><span>Session</span><code>{sessionId ?? "尚未创建真实会话"}</code>{sessionId && <button onClick={() => navigator.clipboard?.writeText(sessionId)}>复制</button>}</div></div>;
}

function RunControls({ project, phase }: { project: Project; phase: Phase }) {
  const [runningCodeArts, setRunningCodeArts] = useState(false);
  const [codeArtsMessage, setCodeArtsMessage] = useState("");
  const [runModel, setRunModel] = useState(project.runModel ?? loadRunModel());
  const [modelOptions, setModelOptions] = useState(() => flattenModelOptions([]));
  const [syncOpen, setSyncOpen] = useState(false);
  const [syncSessionId, setSyncSessionId] = useState("");
  const [syncing, setSyncing] = useState(false);
  const runningRef = useRef(false);
  useEffect(() => { void fetchAgentModels().then((list) => { if (list) setModelOptions(flattenModelOptions(list)); }); }, []);
  const syncFromSession = async () => {
    if (syncing || !syncSessionId.trim()) return;
    setSyncing(true);
    setCodeArtsMessage("正在读取会话 " + syncSessionId.slice(0, 14) + "… 的真实结果…");
    try {
      const messages = await getCodeArtsMessages(syncSessionId.trim(), loadCodeArtsCredentials());
      const finals = messages.filter((item) => item.info?.role === "assistant" && item.info?.time?.completed);
      const text = finals.map((item) => (item.parts ?? []).filter((part) => part.type === "text" && part.text?.trim()).map((part) => part.text).join("\n")).join("\n\n");
      if (!text.trim()) {
        setCodeArtsMessage("该会话暂无已完成的助手汇报，稍后再试。");
        return;
      }
      mockService.recordCodeArtsExecution?.(project.id, phase.number, { mode: "codearts-agentteam", status: "succeeded", sessionId: syncSessionId.trim(), agent: "team-leader", completedAt: new Date().toISOString(), response: text });
      setCodeArtsMessage("已同步真实会话结果（" + text.length + " 字）。阶段进入待审核。");
      setSyncOpen(false);
    } catch (error) {
      setCodeArtsMessage("同步失败：" + (error instanceof Error ? error.message : "未知错误"));
    } finally {
      setSyncing(false);
    }
  };

  const runWithCodeArts = async () => {
    if (runningRef.current) return;
    runningRef.current = true;
    setRunningCodeArts(true);
    setCodeArtsMessage("正在连接 CodeArts Agent…");
    const credentials = loadCodeArtsCredentials();
    const health = await checkCodeArts(credentials);
    if (!health.connected) {
      setCodeArtsMessage(`${health.message}。${health.hint ?? "点击右上角「CodeArts」状态可查看连接详情。"}`);
      runningRef.current = false;
      setRunningCodeArts(false);
      return;
    }
    // 会话延续：项目已有会话则复用（审核通过进入下一 Phase 时在同一对话继续），否则创建
    let sessionId = project.activeSessionId;
    if (sessionId) {
      setCodeArtsMessage(`复用运行中的会话 ${sessionId.slice(0, 14)}… 发送 Phase ${phase.number} 工单…`);
    } else {
      const session = await createCodeArtsSession(`脱胎换骨 · ${project.name}`, credentials, { directory: project.workspaceDir || undefined });
      if (!session.accepted || !session.session?.id) {
        setCodeArtsMessage(session.message);
        runningRef.current = false;
        setRunningCodeArts(false);
        return;
      }
      sessionId = session.session.id;
      mockService.bindActiveSession?.(project.id, sessionId);
    }
    mockService.recordCodeArtsExecution?.(project.id, phase.number, { mode: "codearts-agentteam", status: "starting", sessionId, agent: "team-leader", startedAt: new Date().toISOString() });
    const prompt = phasePrompt(phase.number, { projectName: project.name, sourceValue: project.source.value, sourcePlatformLabel: project.sourcePlatform === "windows" ? "Windows 桌面" : project.sourcePlatform === "legacy-desktop" ? "传统桌面软件" : "Android App", workspaceDir: project.workspaceDir || "工作区未指定" });
    const result = await promptCodeArtsSession(sessionId, prompt, credentials, { agent: "team-leader", mode: "agent-team", model: parseRunModel(runModel) });
    const livePartIds = new Set<string>();
    const resolved = result.accepted && result.pending
      ? await waitForCodeArtsResult(sessionId, result.messageId, credentials, { timeoutMs: 240000, onUpdate: (message: CodeArtsMessage) => {
          (message.parts ?? []).forEach((part) => {
            if (!part.id || livePartIds.has(part.id) || !part.text?.trim()) return;
            livePartIds.add(part.id);
            const agentName = typeof message.info?.agent === "string" ? message.info.agent : "CodeArts AgentTeam";
            mockService.recordCodeArtsEvent?.(project.id, phase.number, { agent: agentName === "team-leader" ? "Team Leader" : agentName, type: part.type === "tool" ? "tool" : part.type === "reasoning" ? "thinking" : "system", message: part.text.replace(/\s+/g, " ").slice(0, 280) });
          });
        } })
      : result;
    if (resolved.accepted) {
      const raw = typeof resolved.response === "string" ? resolved.response : resolved.response ? JSON.stringify(resolved.response) : "";
      const preview = raw.replace(/\s+/g, " ").slice(0, 110);
      setCodeArtsMessage(`已触发真实 CodeArts 推理（会话 ${sessionId.slice(0, 12)}…）${preview ? ` · ${preview}${raw.length > 110 ? "…" : ""}` : ""}`);
      mockService.recordCodeArtsExecution?.(project.id, phase.number, { mode: "codearts-agentteam", status: "succeeded", sessionId: sessionId, agent: "team-leader", completedAt: new Date().toISOString(), response: raw });
    } else if (resolved.pending) {
      // AgentTeam 派发可能超过页面等待时间：保持执行中状态，任务在后台继续
      setCodeArtsMessage(`${resolved.message} · 会话 ${sessionId.slice(0, 12)}…。团队仍在后台执行，稍后可重新点击查看结果。`);
      mockService.recordCodeArtsExecution?.(project.id, phase.number, { mode: "codearts-agentteam", status: "running", sessionId: sessionId, agent: "team-leader" });
    } else {
      setCodeArtsMessage(`${resolved.message} · session ${sessionId.slice(0, 12)}…`);
      mockService.recordCodeArtsExecution?.(project.id, phase.number, { mode: "codearts-agentteam", status: "failed", sessionId: sessionId, agent: "team-leader", completedAt: new Date().toISOString(), error: resolved.message });
    }
    setRunningCodeArts(false);
    runningRef.current = false;
  };
  const [autoRunKey, setAutoRunKey] = useState("");
  const autoRunRef = useRef("");
  useEffect(() => {
    const key = `${project.id}:${phase.number}:${phase.revision}`;
    if (project.executionMode === "codearts-agentteam" && !project.demo && phase.status === "running" && autoRunRef.current !== key && autoRunKey !== key && !runningCodeArts && !runningRef.current) {
      autoRunRef.current = key;
      setAutoRunKey(key);
      void runWithCodeArts();
    }
  }, [project.id, phase.number, phase.revision, phase.status, autoRunKey, runningCodeArts]);
  const isReal = project.executionMode === "codearts-agentteam" && !project.demo;
  if (!isReal) return <div className="run-controls"><div className="side-panel-heading"><span className="eyebrow">运行控制</span><span className="secure-label">DEMO</span></div><div className="control-row"><span>当前 revision</span><b>{phase.revision}.0</b></div><div className="control-row"><span>运行模式</span><b className="muted-value">本地演示</b></div><div className="control-row"><span>数据来源</span><b className="muted-value">固定数据</b></div><button className="outline-button" onClick={() => mockService.resetDemo(project.id)}>↻ 从头播放示例</button></div>;
  return <div className="run-controls"><div className="side-panel-heading"><span className="eyebrow">运行控制</span><span className="secure-label">{project.demo ? "DEMO" : "LIVE"}</span></div><div className="control-row"><span>当前 revision</span><b>{phase.revision}.0</b></div><div className="control-row"><span>事件数量</span><b>{phase.events.length}</b></div><div className="control-row"><span>运行模式</span><b className={project.demo ? "muted-value" : "mint-text"}>{project.demo ? "本地演示" : "CodeArts Space / AgentTeam"}</b></div><div className="control-row"><span>工作区</span><b title={project.workspaceDir ?? ""}>{shortenPath(project.workspaceDir)}</b></div><div className="control-row"><span>执行模型</span><select className="model-select" value={runModel} onChange={(event) => { setRunModel(event.target.value); saveRunModel(event.target.value); }} title="AgentTeam 真实执行使用的模型">{modelOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div><div className="control-row"><span>会话状态</span><b>{phase.execution?.sessionId ? phase.execution.status : "未启动"}</b></div><button className="codearts-run-button" onClick={runWithCodeArts} disabled={runningCodeArts || project.demo}>{runningCodeArts ? "CodeArts AgentTeam 推理中…" : project.demo ? "演示项目不可发起真实构建" : "启动真实 AgentTeam"}</button>{codeArtsMessage && <p className="codearts-message">{codeArtsMessage}</p>}{!project.demo && <div className="sync-session-box">{syncOpen ? <><input className="sync-session-input" value={syncSessionId} onChange={(event) => setSyncSessionId(event.target.value)} placeholder="粘贴 CodeArts 会话 ID，如 ses_xxx" /><button className="refresh-button" onClick={() => void syncFromSession()} disabled={syncing}>{syncing ? "同步中…" : "确认同步"}</button><button className="refresh-button" onClick={() => setSyncOpen(false)}>收起</button></> : <button className="text-sync-button" onClick={() => setSyncOpen(true)}>↺ 绑定已有会话同步结果</button>}</div>}{project.demo && <button className="outline-button" onClick={() => mockService.resetDemo(project.id)}>↻ 从头播放示例</button>}</div>;
}

function shortenPath(value: string | undefined, max = 28): string {
  if (!value) return "未指定";
  if (value.length <= max) return value;
  return `${value.slice(0, 6)}…${value.slice(-18)}`;
}

function StatusBadge({ status }: { status: Phase["status"] }) {
  return <span className={`status-badge ${statusClasses[status]}`}><i />{statusLabels[status]}</span>;
}

function ReviewDialog({ phase, onClose, onSubmit }: { phase: Phase; onClose: () => void; onSubmit: (review: Review) => void }) {
  const [comment, setComment] = useState("");
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="review-dialog"><div className="dialog-top"><div><span className="eyebrow">人工审核 · 阶段 {phase.code}</span><h2>审核阶段交付物</h2><p>{phase.title} · revision {phase.revision}.0</p></div><button className="close-button" onClick={onClose}>×</button></div><div className="review-checklist"><span>✓</span><div><b>阶段执行已完成</b><small>{phase.events.length} 条 Agent 事件 · {phase.artifacts.length} 项交付物</small></div></div><div className="review-artifacts">{phase.artifacts.map((artifact) => <div key={artifact.id}><span className={`artifact-icon artifact-${artifact.kind}`}>件</span><span><b>{artifact.name}</b><small>{artifact.description}</small></span><span className="ready-label">已就绪</span></div>)}</div><label className="field-label">审核意见（可选）<textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="记录需要留痕的判断或修改建议…" rows={3} /></label><div className="dialog-actions"><button className="ghost-button" onClick={() => onSubmit(makeReview("changes_requested", comment))}>要求修改</button><button className="primary-button" onClick={() => onSubmit(makeReview("approved", comment))}>审核通过 <span>→</span></button></div></div></div>;
}

function ReportPage() {
  const { id } = useParams();
  const project = useProject(id);
  if (!project) return <NotFound />;
  return <div className="report-page"><div className="workspace-header"><div className="breadcrumb"><Link to={`/projects/${project.id}`}>工作台</Link><span>/</span><b>迁移报告</b></div><div className="workspace-actions"><span className="demo-tag">演示数据</span><button className="ghost-button small" onClick={() => downloadText("migration-quick-report.md", `# ${project.name}\n\n一致性评分：94/100\n\n当前为演示数据。`)}>↓ 下载速览版</button><button className="primary-button small" onClick={() => downloadText("migration-full-report.json", JSON.stringify(project, null, 2))}>↓ 导出完整 JSON</button></div></div><div className="page-heading report-heading"><div><h1>迁移结果报告</h1><p className="heading-subtitle">{project.name} · 由四阶段审核记录汇总生成</p></div><StatusBadge status="completed" /></div><div className="report-hero"><div className="report-score"><span className="eyebrow">功能一致性</span><strong>94<small>/100</small></strong></div><div className="report-stat"><span>功能用例</span><b>05</b><small>4 通过 · 1 部分</small></div><div className="report-stat"><span>自动修复</span><b>02</b></div><div className="report-stat"><span>人工审核</span><b>04</b></div></div><div className="report-grid"><div className="report-main"><div className="section-heading"><div><p className="eyebrow">执行摘要</p><h2>一分钟了解这次迁移</h2></div></div><div className="summary-copy"><p>本次迁移已完成从 Android 到 HarmonyOS 的核心功能验证。项目总览、图片导入、结果详情和历史记录通过一致性检查；缺陷检测功能的字段映射经过一次自动修复后，与 Android 基线保持一致。</p><div className="summary-points"><span><i className="mint-dot" />核心流程可复现</span><span><i className="blue-dot" />证据可追溯</span><span><i className="amber-dot" />1 项差异已解释</span></div></div><FeatureReportTable features={project.features} /><div className="report-section"><div className="section-heading"><div><h2>CodeArts Agent Team 使用记录</h2></div><span className="subtle-link">查看全部 →</span></div><div className="trace-cards">{["需求分析与 Codebase 索引", "单元测试与语义契约", "ArkTS 生成与编译修复"].map((item, index) => <div className="trace-card" key={item}><span>{String(index + 1).padStart(2, "0")}</span><div><b>{item}</b><small>Session team_{index + 1}_demo_8f21 · 已归档</small></div><em>✓</em></div>)}</div></div></div><aside className="report-aside"><div className="aside-card report-nav"><p className="eyebrow">报告目录</p>{["执行摘要", "功能一致性矩阵", "差异与修复", "Agent 使用记录", "环境与依赖"].map((item, index) => <a className={index === 0 ? "active" : ""} href={`#report-${index}`} key={item}><span>0{index + 1}</span>{item}<i>→</i></a>)}</div><div className="aside-tip"><span>注</span><p>完整版报告将包含原始 Markdown 与可打印 PDF。</p></div></aside></div></div>;
}

function FeatureReportTable({ features }: { features: Feature[] }) {
  return <div className="report-table-card"><div className="card-title-row"><div><h3>功能一致性矩阵</h3></div></div><div className="feature-report-table"><div className="table-row table-head"><span>功能</span><span>Android 基线</span><span>HarmonyOS 结果</span><span>结论</span></div>{features.map((feature) => <div className="table-row" key={feature.id}><span><b>{feature.name}</b><small>{feature.description}</small></span><span className="result-cell"><i className="check-icon">✓</i>{feature.androidResult}</span><span className="result-cell"><i className={`check-icon ${feature.status === "partial" ? "partial" : feature.status === "risk" ? "risk" : ""}`}>{feature.status === "covered" ? "✓" : feature.status === "partial" ? "!" : "·"}</i>{feature.harmonyResult}</span><span><span className={`table-status ${feature.status}`}>{feature.status === "covered" ? "通过" : feature.status === "partial" ? "部分" : "待验证"}</span></span></div>)}</div></div>;
}

function DeliveryPage() {
  const { id } = useParams();
  const project = useProject(id);
  if (!project) return <NotFound />;
  const deliveryArtifacts = [
    { name: "harmony-project.zip", desc: "完整 HarmonyOS 工程源码", size: "4.2 MB", type: "code", color: "mint" },
    { name: "migration-full-report.pdf", desc: "完整迁移报告（可打印）", size: "1.8 MB", type: "report", color: "red" },
    { name: "quick-report.html", desc: "人能快速看懂的速览版", size: "86 KB", type: "report", color: "blue" },
    { name: "comparison-screenshots.zip", desc: "Android / HarmonyOS 对照截图", size: "2.1 MB", type: "screenshot", color: "violet" },
    { name: "test-results.json", desc: "完整执行轨迹和断言结果", size: "28 KB", type: "trace", color: "amber" },
    { name: "hvigor-build.log", desc: "鸿蒙构建与修复日志", size: "31 KB", type: "build", color: "slate" }
  ];
  return <div className="delivery-page"><div className="workspace-header"><div className="breadcrumb"><Link to={`/projects/${project.id}`}>工作台</Link><span>/</span><b>交付中心</b></div><div className="workspace-actions"><button className="primary-button small" onClick={() => downloadText("delivery-manifest.json", JSON.stringify({ project: project.name, generatedAt: new Date().toISOString(), artifacts: deliveryArtifacts }, null, 2))}>↓ 下载交付清单</button></div></div><div className="page-heading"><div><h1>交付中心</h1><p className="heading-subtitle">所有文件来自已审核版本 · revision 4.0</p></div><div className="delivery-ready"><span>✓</span><div><b>交付包已就绪</b><small>6 个文件 · 8.4 MB</small></div></div></div><div className="delivery-layout"><main><div className="delivery-hero"><div className="package-icon">包</div><div><h2>{project.name} · HarmonyOS 迁移包</h2><p>含完整工程、执行证据与双层报告</p></div><button className="primary-button" onClick={() => downloadText("delivery-manifest.json", JSON.stringify(deliveryArtifacts, null, 2))}>下载全部 <span>↓</span></button></div><div className="artifact-grid">{deliveryArtifacts.map((artifact) => <button className="delivery-artifact" key={artifact.name} onClick={() => downloadText(artifact.name.endsWith("json") ? artifact.name : `${artifact.name}.txt`, `${artifact.name}\n\n${artifact.desc}\n\n当前为演示数据。`)}><span className={`delivery-file-icon ${artifact.color}`}>{artifact.type === "code" ? "码" : artifact.type === "screenshot" ? "图" : artifact.type === "trace" ? "迹" : artifact.type === "build" ? "建" : "报"}</span><span><b>{artifact.name}</b><small>{artifact.desc}</small></span><em>{artifact.size}</em><i>↓</i></button>)}</div></main><aside className="delivery-aside"><div className="aside-card"><p className="eyebrow">交付清单</p><div className="manifest-row"><span>源项目</span><b>{project.source.type === "github" ? "GitHub" : "ZIP"}</b></div><div className="manifest-row"><span>目标平台</span><b>HarmonyOS</b></div><div className="manifest-row"><span>审核阶段</span><b>4 / 4</b></div><div className="manifest-row"><span>一致性评分</span><b className="mint-text">94 / 100</b></div><div className="manifest-row"><span>数据模式</span><b>演示数据</b></div></div></aside></div></div>;
}

function downloadText(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function NotFound() {
  return <div className="not-found"><span className="not-found-mark">404</span><h1>找不到这个迁移任务</h1><p>项目可能已被清理，或链接尚未建立。</p><Link to="/" className="primary-button">返回项目总览</Link></div>;
}

export default App;
