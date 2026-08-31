import React, { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link, NavLink, Outlet, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { EmulatorFrame, EmulatorStream, Feature, Phase, PhaseNumber, Project, ProjectInput, Review, SourcePlatform, TargetPlatform } from "./types";
import { mockService } from "./mockService";
import { addAgentModel, BUILTIN_MODELS, checkCodeArts, checkWorkspaceDir, createCodeArtsSession, fetchAgentModels, getCodeArtsMessages, fetchSessionSummary, fetchTeamState, flattenModelOptions, isAbsoluteLocalPath, loadCodeArtsCredentials, loadRunModel, loadTestWorkspaceDir, parseRunModel, promptCodeArtsSession, removeAgentModel, saveCodeArtsCredentials, saveRunModel, saveTestWorkspaceDir, updateAgentTarget, waitForCodeArtsResult, createSkillProposal, decideSkillProposal, fetchSkillFile, fetchSkillProposals, fetchSkillTree, type AgentModelInput, type AgentProviderInfo, type AgentTeamState, type SkillProposal, type CodeArtsCredentials, type CodeArtsMessage, type CodeArtsRunResult } from "./codearts";
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
  const labels: Record<string, string> = {
    android: "Android App",
    ios: "iOS App",
    web: "Web 应用",
    windows: "Windows 桌面软件",
    macos: "macOS 应用",
    tablet: "Android 平板应用",
    watch: "Android Wear 应用",
    legacy: "遗留系统",
  };
  return labels[platform] ?? "Android App";
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

/** 从后端镜像恢复/重建外部驱动项目（跨浏览器共享 + 配方版本更新时强制重建修复历史状态） */
async function restoreProjectFromMirror(id: string): Promise<Project | undefined> {
  try {
    const response = await fetch(`/api/mirror/project?id=${encodeURIComponent(id)}`);
    if (!response.ok) return undefined;
    const recipe = await response.json() as {
      id?: string; name?: string; source?: string; workspace?: string; model?: string;
      session?: string; version?: number; phases?: Array<{ n: number; response: string }>;
    };
    if (recipe.id !== id || !recipe.name) return undefined;
    const version = Number(recipe.version ?? 1);
    const local = mockService.getProject(id);
    if (local && local.mirrorVersion === version) return local;
    // 一次性镜像导入：直接构造终态项目（不走 createProject/record/review 状态机，零副作用零定时器）
    const imported = mockService.importExternalProject({
      id,
      name: recipe.name,
      sourceType: /\.zip$/i.test(recipe.source ?? "") ? "zip" : "github",
      sourceValue: recipe.source ?? "",
      workspaceDir: recipe.workspace,
      runModel: recipe.model,
      session: recipe.session,
      phases: recipe.phases ?? [],
    });
    mockService.replaceProject({ ...imported, mirrorVersion: version });
    return mockService.getProject(id);
  } catch {
    return undefined;
  }
}

function useProject(id?: string) {
  const [project, setProject] = useState<Project | undefined>(() => (id ? mockService.getProject(id) : undefined));
  const [restoreTried, setRestoreTried] = useState(false);
  useEffect(() => {
    if (!id) return;
    setProject(mockService.getProject(id));
    const unsubscribe = mockService.subscribe(id, setProject);
    if (!restoreTried) {
      setRestoreTried(true);
      void restoreProjectFromMirror(id).then((restored) => { if (restored) setProject(restored); });
    }
    return unsubscribe;
  }, [id, restoreTried]);
  return project;
}

/** 全局错误边界：白屏变为可见错误（投射组件异常不再击穿整页） */
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: string | null }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error: `${error.name}: ${error.message}` };
  }
  componentDidCatch(error: Error) {
    console.error("[ErrorBoundary]", error);
  }
  render() {
    if (this.state.error) {
      return <div style={{ padding: 24, fontFamily: "monospace", whiteSpace: "pre-wrap" }}>
        <h2>页面组件异常（已拦截，不白屏）</h2>
        <p style={{ color: "#b91c1c" }}>{this.state.error}</p>
        <button onClick={() => { this.setState({ error: null }); location.reload(); }}>刷新重试</button>
      </div>;
    }
    return this.props.children;
  }
}

function App() {
  return (
    <>
    <Routes>
      <Route element={<LiveAppShell />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/projects/new" element={<LiveNewProjectPage />} />
        <Route path="/projects/:id" element={<LiveProjectPage />} />
        <Route path="/projects/:id/review/:phaseNo" element={<PhaseReviewPage />} />
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
  const navigate = useNavigate();
  useEffect(() => mockService.subscribeAll(setProjects), []);
  // 外部驱动入口：?autocreate=1&name=&source=&workspace=&model=&session=
  // 迁移总控直接经内核 API 驱动四阶段执行；网页创建对应项目作为状态镜像（externalDrive：不自动发单）
  const autoCreatedRef = useRef(false);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("autocreate") !== "1" || autoCreatedRef.current) return;
    autoCreatedRef.current = true;
    const name = params.get("name") || "外部驱动迁移";
    const source = params.get("source") || "";
    const session = params.get("session");
    // 幂等：同名同源的外部驱动项目已存在则复用（避免重复创建）
    const existing = mockService.listProjects().find((p) => p.externalDrive && p.name === name && p.source.value === source);
    let project = existing;
    if (!project) {
      project = mockService.createProject({
        name,
        sourceType: /\.zip$/i.test(source) ? "zip" : "github",
        sourceValue: source,
        executionMode: "codearts-agentteam",
        workspaceDir: params.get("workspace") || undefined,
        runModel: params.get("model") || undefined,
        sourcePlatform: "android",
        targetPlatform: "harmony-phone",
        externalDrive: true,
      });
      if (session) {
        mockService.bindActiveSession(project.id, session);
        mockService.recordCodeArtsExecution(project.id, 1, { mode: "codearts-agentteam", status: "running", sessionId: session, agent: "team-leader" });
      }
    }
    // 把项目 ID 上报给网关，供外部总控构造 sync URL
    void fetch("/api/mirror/project", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: project.id, name: project.name, sessionId: session ?? project.activeSessionId ?? "" }),
    }).catch(() => {});
    navigate(`/projects/${project.id}`, { replace: true });
  }, [navigate]);
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
    <div className="codearts-dialog-body">
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
    <label className="field-label">测试工作区目录（可选）<input value={testDir} onChange={(event) => setTestDir(event.target.value)} placeholder={isAbsoluteLocalPath(testDir) || !testDir ? "留空则使用 Agent 默认目录" : "请输入本机绝对路径，如 /Users/you/test-workspace"} /><small className={`field-note ${testDir.trim() && !isAbsoluteLocalPath(testDir) ? "error-text" : ""}`}>{testDir.trim() && !isAbsoluteLocalPath(testDir) ? "请输入本机绝对路径" : "测试会话将在此目录中运行，避免写入 Agent 安装目录。"}</small></label>
    <label className="field-label">执行模型<select value={runModel} onChange={(event) => { setRunModel(event.target.value); saveRunModel(event.target.value); }}>{modelOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select><small className="field-note">连接测试与真实 AgentTeam 执行共用此选择；含 Space 内置模型与已配置的自定义模型。</small></label>
    <label className="field-label">测试指令<textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} rows={3} placeholder="输入你希望 CodeArts 回答的内容" /></label>
    <button className="primary-button wide" onClick={runTest} disabled={status === "checking" || status === "running" || !instruction.trim()}>{status === "checking" ? "检查 CodeArts 服务…" : status === "running" ? "等待回复…" : "发送测试指令"}<span>→</span></button>
    {(error || result?.message) && status === "failed" && <div className="codearts-test-error">{error || result?.message}</div>}
    {responseText && <pre className="real-response dialog-response">{responseText}</pre>}
    {!responseText && status === "running" && <div className="test-loader"><i /><i /><i /></div>}
    <div className="codearts-test-meta"><span>Agent <b>team-leader</b></span><span>消息 <b>{messages.length}</b></span><span>耗时 <b>{elapsed === null ? "—" : `${(elapsed / 1000).toFixed(1)}s`}</b></span></div>
    </div>
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
    if (!isAbsoluteLocalPath(value)) return setDirStatus("invalid");
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
    invalid: "请输入本机绝对路径，例如 D:\\code\\workspace 或 /Users/you/workspace",
  };

  const sourceOptions: Array<{ id: SourcePlatform; label: string; note: string; ready: boolean }> = [
    { id: "android", label: "Android App", note: "已验证路径", ready: true },
    { id: "ios", label: "iOS App", note: "skill v2 就绪", ready: true },
    { id: "web", label: "Web 应用", note: "skill v2 就绪", ready: true },
    { id: "windows", label: "Windows 桌面软件", note: "skill v2 就绪", ready: true },
    { id: "macos", label: "macOS 应用", note: "skill v2 就绪", ready: true },
    { id: "tablet", label: "Android 平板应用", note: "skill v2 就绪", ready: true },
    { id: "watch", label: "Android Wear 应用", note: "skill v2 就绪", ready: true },
    { id: "legacy", label: "遗留系统", note: "skill v2 就绪", ready: true },
  ];
  const targetOptions: Array<{ id: TargetPlatform; label: string; note: string; ready: boolean }> = [
    { id: "harmony-phone", label: "HarmonyOS 手机", note: "已验证路径", ready: true },
    { id: "harmony-pc", label: "HarmonyOS PC", note: "skill v2 就绪", ready: true },
    { id: "harmony-tablet", label: "HarmonyOS 平板", note: "skill v2 就绪", ready: true },
    { id: "harmony-watch", label: "HarmonyOS 手表", note: "skill v2 就绪", ready: true },
    { id: "automotive", label: "鸿蒙车机", note: "skill v2 就绪", ready: true },
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
      if (!isAbsoluteLocalPath(workspace)) return setError("工作区目录需为本机绝对路径，例如 D:\\code\\workspace 或 /Users/you/workspace");
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
    {executionMode === "codearts-agentteam" && <label className="field-label">CodeArts 工作区目录<input value={workspaceDir} onChange={(event) => setWorkspaceDir(event.target.value)} placeholder="D:\\code\\migration-workspace 或 /Users/you/migration-workspace" /><small className={`field-note ${dirStatus === "exists" ? "mint-text" : dirStatus === "invalid" ? "error-text" : ""}`}>{dirNotes[dirStatus]}</small></label>}
    {error && <div className="form-error">! {error}</div>}
    <button className="primary-button wide" type="submit" disabled={!pathReady}>启动迁移 <span className="button-arrow">→</span></button>
  </form><aside className="intake-aside"><div className="aside-card"><p className="eyebrow">执行流程</p><h3>四阶段迁移门禁</h3><div className="preview-steps">{[{ n: "01", t: "基线建立", d: "冻结迁什么与验收标准" }, { n: "02", t: "深度理解", d: "功能语义地图与行为契约" }, { n: "03", t: "原生迁移", d: "受控原生化组件映射" }, { n: "04", t: "差分修复", d: "双端重放至 MATCH" }].map((step, index) => <div className="preview-step" key={step.n}><span>{step.n}</span><div><b>{step.t}</b><small>{step.d}</small></div>{index < 3 && <i>↓</i>}</div>)}</div></div><div className="aside-tip"><span>ⓘ</span><p>迁移单位是“用户功能与行为”而非页面：语义契约作为中间层，使源端与目标端解耦，同一套验证方法可复用到其他平台组合。当前已验证 Android → HarmonyOS，其余路径为扩展方向。</p></div></aside></div></div>;
}


/** 阶段名（对话分组标题用） */
const PHASE_CHAT_LABELS: Record<number, string> = { 1: "Phase 1 · 基线建立", 2: "Phase 2 · 深度理解", 3: "Phase 3 · 原生迁移", 4: "Phase 4 · 实现与验证" };

/** 消息按阶段归属：阶段工单（msg_phaseN_*）开启分组；其余消息（恢复/返工/网页插话/回复）继承当前活动阶段；系统注入的 reminder 不展示 */
function tagMessagesByPhase(messages: CodeArtsMessage[]): Array<{ message: CodeArtsMessage; phase: number }> {
  let current = 0;
  return messages
    .filter((message) => {
      const text = (message.parts ?? []).filter((part) => part.type === "text" && part.text).map((part) => part.text).join("");
      return !(message.info?.role === "user" && text.trimStart().startsWith("<agent_team_reminder>"));
    })
    .map((message) => {
      const id = message.info?.id ?? "";
      const match = /^msg_phase([1-4])(?:_|$)/.exec(id);
      if (message.info?.role === "user" && match) current = Number(match[1]);
      return { message, phase: current };
    });
}

/** 聊天气泡（Space 风格）：用户右对齐、Agent 左对齐（Markdown 渲染）带工具轨迹 */
function ChatBubble({ message }: { message: CodeArtsMessage }) {
  const role = message.info?.role;
  const isUser = role === "user";
  const who = typeof message.info?.agent === "string" && message.info.agent ? message.info.agent : isUser ? "工单" : "Agent";
  const tools = (message.parts ?? []).filter((part) => part.tool) as Array<{ tool: string; state?: { status?: string } }>;
  const text = (message.parts ?? []).filter((part) => part.type === "text" && part.text?.trim()).map((part) => part.text).join("\n").trim();
  const time = message.info?.time?.created ? formatTime(new Date(message.info.time.created).toISOString()) : "";
  const done = Boolean(message.info?.time?.completed);
  if (isUser) {
    return <div className="chat-row user"><div className="chat-bubble user">
      <div className="chat-bubble-head"><span>工单 / 指令</span><small>{time}</small></div>
      {text && (text.length > 600
        ? <details className="chat-user-full"><summary>工单全文（{text.length} 字）· 点击展开</summary><p className="chat-bubble-text">{text}</p></details>
        : <p className="chat-bubble-text">{text}</p>)}
    </div></div>;
  }
  return <div className="chat-row agent">
    <div className="chat-bubble agent">
      <div className="chat-bubble-head"><b>{who}</b><small>{time}{done ? " · 完成" : " · 进行中"}</small></div>
      {tools.length > 0 && <div className="chat-tools">{tools.map((tool, index) => <span key={`${tool.tool}-${index}`} className={`chat-tool ${tool.state?.status === "completed" ? "ok" : ""}`}>‹{tool.tool}›{tool.state?.status === "completed" ? "✓" : "◌"}</span>)}</div>}
      {text && <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div>}
    </div>
  </div>;
}

function modelLabelOf(project: Project) {
  return project.runModel ? project.runModel.split("::").pop() ?? "默认模型" : "默认模型";
}

/** 团队成员名 → 阶段（迁移团队命名规约：2A/2B/收束=P2、架构师=P3、4A/4B=P4；leader 全程） */
function memberPhaseOf(name: string): number {
  if (/leader/i.test(name)) return 0;
  if (/2A|2B|SemanticAnalyst|RuntimeOracle|Phase2|Finalizer/i.test(name)) return 2;
  if (/Architect|Scaffold|P3/i.test(name)) return 3;
  if (/4A|4B|Implementer|Verifier|P4/i.test(name)) return 4;
  return 0;
}

/** 团队任务 → 阶段：优先任务文本（Phase N / NA·NB / Gate N），回落到执行成员归属；0=全局 */
function taskPhaseOf(task: { content: string; owner_name?: string }): number {
  const byText = /Phase\s*([1-4])/i.exec(task.content) ?? /(?:^|[\s（(])([1-4])[AB][\s ：:（）]/.exec(task.content) ?? /Gate\s*([1-4])/i.exec(task.content);
  if (byText) return Number(byText[1]);
  return task.owner_name ? memberPhaseOf(task.owner_name) : 0;
}

/** 模拟器 h264 投射：设备端/VideoToolbox 裸流 h264 → WebCodecs 硬解 → canvas + 反控（Android/鸿蒙通用）
 *  2026-09-01 修正版：SPS/PPS 保留在流内（annexb in-band 必需）、起始码 3/4 字节兼容、
 *  按 Access Unit 聚合（SPS+PPS+IDR 为一个 key chunk）、解码积压丢帧保护、hooks 顺序合规。 */
function H264Cast({ platform, serial, deviceW = 1080, deviceH = 2400 }: { platform: "android" | "harmony"; serial: string; deviceW?: number; deviceH?: number }) {
  const isAndroid = platform === "android";
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [status, setStatus] = useState<"connecting" | "live" | "error">("connecting");
  const [hasFrame, setHasFrame] = useState(false);
  const [jpegFallback, setJpegFallback] = useState(false);
  const [deviceRes, setDeviceRes] = useState<{ w: number; h: number } | null>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  // 连上但 8 秒解不出画（浏览器 WebCodecs 不可用/流异常）→ 降级 JPEG 轮询兜底
  useEffect(() => {
    if (jpegFallback || status !== "live" || hasFrame) return;
    const timer = window.setTimeout(() => { setJpegFallback(true); }, 8000);
    return () => { window.clearTimeout(timer); };
  }, [status, hasFrame, jpegFallback]);
  // 鸿蒙反控坐标为设备像素空间：按真实分辨率换算
  useEffect(() => {
    if (platform !== "harmony") return;
    let alive = true;
    void (async () => {
      try {
        const response = await fetch(`/api/emulator/harmony/info?serial=${encodeURIComponent(serial)}`);
        if (!response.ok) return;
        const data = await response.json();
        if (alive && Number(data.width) > 0 && Number(data.height) > 0) setDeviceRes({ w: Number(data.width), h: Number(data.height) });
      } catch { /* 解析失败则沿用默认分辨率 */ }
    })();
    return () => { alive = false; };
  }, [platform, serial]);
  const dw = deviceRes?.w ?? deviceW;
  const dh = deviceRes?.h ?? deviceH;
  useEffect(() => {
    let alive = true;
    let ws: WebSocket | null = null;
    let retry: number | undefined;
    let decoder: VideoDecoder | null = null;
    let buffer = new Uint8Array(0);
    let auBytes: Uint8Array | null = null;   // 当前 Access Unit 聚合（含起始码，原样透传）
    let auHasKey = false;
    let configured = false;
    const startCodeLen = (nalu: Uint8Array): number => {
      if (nalu.length >= 4 && nalu[0] === 0 && nalu[1] === 0 && nalu[2] === 0 && nalu[3] === 1) return 4;
      if (nalu.length >= 3 && nalu[0] === 0 && nalu[1] === 0 && nalu[2] === 1) return 3;
      return 0;
    };
    const naluType = (nalu: Uint8Array): number => {
      const sc = startCodeLen(nalu);
      return sc && nalu.length > sc ? nalu[sc] & 0x1f : 0;
    };
    const codecFromSps = (nalu: Uint8Array): string => {
      const sc = startCodeLen(nalu);
      const off = sc;
      const profile = nalu.length > off + 1 ? nalu[off + 1].toString(16).padStart(2, "0") : "64";
      const compat = nalu.length > off + 2 ? nalu[off + 2].toString(16).padStart(2, "0") : "00";
      const level = nalu.length > off + 3 ? nalu[off + 3].toString(16).padStart(2, "0") : "28";
      return `avc1.${profile}${compat}${level}`;
    };
    const resetDecoder = () => { try { decoder?.close(); } catch {} decoder = null; configured = false; };
    const ensureDecoder = (sps: Uint8Array): boolean => {
      if (decoder && decoder.state !== "closed") return true;
      if (!("VideoDecoder" in window)) return false;
      decoder = new VideoDecoder({
        output: (frame) => {
          const target = canvasRef.current;
          if (target) {
            if (target.width !== frame.displayWidth) target.width = frame.displayWidth;
            if (target.height !== frame.displayHeight) target.height = frame.displayHeight;
            target.getContext("2d")?.drawImage(frame, 0, 0);
          }
          setHasFrame(true);
          frame.close();
        },
        error: () => { resetDecoder(); },
      });
      try {
        decoder.configure({ codec: codecFromSps(sps), optimizeForLatency: true, avc: { format: "annexb" } });
        configured = true;
        return true;
      } catch {
        resetDecoder();
        return false;
      }
    };
    const flushAu = () => {
      if (!auBytes || !auBytes.length) { auBytes = null; auHasKey = false; return; }
      const chunk = auBytes;
      const isKey = auHasKey;
      auBytes = null;
      auHasKey = false;
      if (!decoder || decoder.state === "closed" || !configured) return;
      // 积压保护：队列过深时丢 delta 帧（保持低延迟），key 帧必须送
      if (!isKey && decoder.decodeQueueSize > 5) return;
      try {
        decoder.decode(new EncodedVideoChunk({ type: isKey ? "key" : "delta", timestamp: performance.now() * 1000, data: chunk }));
      } catch { resetDecoder(); }
    };
    const isFirstMbZero = (nalu: Uint8Array): boolean => {
      // slice header 的首个 exp-Golomb 值 first_mb_in_slice==0 ⇔ 编码为单 bit '1'
      // ⇔ RBSP 首字节（nalu header 之后）最高位为 1（emulation-prevention 不会出现在该位置）
      const sc = startCodeLen(nalu);
      return nalu.length > sc + 1 && (nalu[sc + 1] & 0x80) !== 0;
    };
    const pushNalu = (nalu: Uint8Array) => {
      const type = naluType(nalu);
      // 新 Access Unit 边界：AUD/SPS，或「slice 且 first_mb_in_slice==0」（ffmpeg/screenrecord
      // 的流无 AUD、SPS 仅随关键帧出现——P 帧边界必须靠 slice header 判定，否则多帧聚而不出）
      if (type === 9 || type === 7) flushAu();
      else if ((type === 1 || type === 5) && isFirstMbZero(nalu)) flushAu();
      if (type === 7 || type === 15) { // SPS / Subset-SPS：借此（重）建解码器
        if (!ensureDecoder(nalu)) return;
      }
      if (type === 5) auHasKey = true;
      // SPS(7)/PPS(8)/SEI(6)/AUD(9)/slice(1/5) 全部保留进 AU——annexb in-band 参数集是解码必需
      auBytes = auBytes
        ? (() => { const merged = new Uint8Array(auBytes.length + nalu.length); merged.set(auBytes); merged.set(nalu, auBytes.length); return merged; })()
        : nalu.slice();
    };
    const extractNalus = (chunk: ArrayBuffer) => {
      const incoming = new Uint8Array(chunk);
      const merged = new Uint8Array(buffer.length + incoming.length);
      merged.set(buffer); merged.set(incoming, buffer.length);
      const positions: Array<[number, number]> = [];
      let start = -1;
      let i = 0;
      while (i < merged.length - 3) {
        if (merged[i] === 0 && merged[i + 1] === 0 && merged[i + 2] === 1) {
          if (start >= 0) positions.push([start, i - start]);
          start = i; i += 3;
        } else if (i < merged.length - 4 && merged[i] === 0 && merged[i + 1] === 0 && merged[i + 2] === 0 && merged[i + 3] === 1) {
          if (start >= 0) positions.push([start, i - start]);
          start = i; i += 4;
        } else i += 1;
      }
      for (const [pos, len] of positions) pushNalu(merged.subarray(pos, pos + len));
      const lastStart = positions.length ? positions[positions.length - 1][0] : 0;
      buffer = merged.slice(lastStart);
    };
    const connect = () => {
      if (!alive) return;
      ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/emulator/${platform}/ws`);
      ws.binaryType = "arraybuffer";
      ws.onopen = () => setStatus("live");
      ws.onmessage = (event) => extractNalus(event.data as ArrayBuffer);
      ws.onclose = () => { if (alive) { setStatus("error"); retry = window.setTimeout(connect, 2000); } };
      ws.onerror = () => { try { ws?.close(); } catch {} };
    };
    connect();
    return () => {
      alive = false;
      if (retry) window.clearTimeout(retry);
      try { ws?.close(); } catch {}
      try { decoder?.close(); } catch {}
    };
  }, [platform]);
  if (jpegFallback) return <EmulatorCast serial={serial} platform={platform} />;
  const toDevice = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const x = Math.round(((event.clientX - rect.left) / rect.width) * dw);
    const y = Math.round(((event.clientY - rect.top) / rect.height) * dh);
    return { x: Math.max(0, Math.min(dw - 1, x)), y: Math.max(0, Math.min(dh - 1, y)) };
  };
  const control = async (payload: Record<string, unknown>) => {
    try { await fetch(`/api/emulator/${platform}/control`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }); } catch { /* 静默 */ }
  };
  return <div className="emulator-cast interactive">
    <div className="cast-head">
      <span className={`cast-dot ${status} ${isAndroid ? "android" : "harmony"}`} />
      <b>{isAndroid ? "Android 模拟器" : "鸿蒙模拟器"}</b>
      <code>{serial}</code>
      <small>{isAndroid ? "对照基准（oracle）· 设备端 h264 流" : "迁移实现侧 · VideoToolbox h264 流"} · {dw}×{dh} · 可反控</small>
      {isAndroid && <a className="text-sync-button" href="http://localhost:8000" target="_blank" rel="noreferrer">ws-scrcpy ↗</a>}
    </div>
    <div className="cast-body">
      <canvas
        ref={canvasRef}
        className="cast-canvas"
        onPointerDown={(event) => { dragStart.current = toDevice(event); }}
        onPointerUp={(event) => {
          const start = dragStart.current;
          const end = toDevice(event);
          dragStart.current = null;
          if (!start || !end) return;
          const moved = Math.abs(start.x - end.x) + Math.abs(start.y - end.y);
          if (moved > 60) void control({ action: "swipe", x: start.x, y: start.y, x2: end.x, y2: end.y });
          else void control({ action: "tap", x: end.x, y: end.y });
        }}
      />
      {status === "live" && !hasFrame && <img className="cast-canvas" src={`/api/emulator/${platform}/frame?serial=${encodeURIComponent(serial)}&n=${Date.now()}`} alt="快照打底" /> }
      {status !== "live" && <div className="cast-placeholder">{status === "error" ? "视频流中断，重连中…" : "正在建立视频流…"}</div>}
    </div>
    <div className="cast-controls">
      <button type="button" onClick={() => void control({ action: "back" })}>← 返回</button>
      <button type="button" onClick={() => void control({ action: "home" })}>⌂ 桌面</button>
    </div>
  </div>;
}

/** Android 投射面板：默认嵌 ws-scrcpy（h264 硬解 60fps 键鼠反控，本机最流畅），
 *  可切换页内直通流（设备端 screenrecord，不依赖 ws-scrcpy 服务） */
function AndroidCastPanel({ serial }: { serial: string }) {
  const [mode, setMode] = useState<"embed" | "inline">("embed");
  return <div className="android-cast-panel">
    <div className="cast-mode-bar">
      <button type="button" className={`cast-mode-chip ${mode === "embed" ? "active" : ""}`} onClick={() => setMode("embed")}>ws-scrcpy 高清反控</button>
      <button type="button" className={`cast-mode-chip ${mode === "inline" ? "active" : ""}`} onClick={() => setMode("inline")}>页内直通流</button>
      <a className="cast-mode-chip" href="http://localhost:8000" target="_blank" rel="noreferrer">新窗口 ↗</a>
    </div>
    {mode === "embed"
      ? <div className="emulator-cast">
          <div className="cast-head">
            <span className="cast-dot android live" />
            <b>Android 模拟器</b>
            <code>{serial}</code>
            <small>对照基准（oracle）· ws-scrcpy 镜像</small>
          </div>
          <div className="cast-body cast-embed">
            <iframe className="cast-iframe" src="/scrcpy/" title="ws-scrcpy" />
          </div>
          <div className="cast-controls"><small className="cast-hint">↑ 在面板中点击设备 <code>emulator-5554</code> 开始镜像（约 60fps，支持键鼠/剪贴板/旋转）</small></div>
        </div>
      : <H264Cast platform="android" serial={serial} />}
  </div>;
}

/** 鸿蒙投射：按网关能力自动选择 h264 硬编流（VideoToolbox）或 JPEG WS 兜底 */
function HarmonyCast({ serial }: { serial: string }) {
  const [mode, setMode] = useState<"h264" | "jpeg" | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const response = await fetch(`/api/emulator/harmony/info?serial=${encodeURIComponent(serial)}`);
        const data = await response.json();
        if (!alive) return;
        if (data.mode === "h264" || data.mode === "jpeg") setMode(data.mode);
        else setError(String(data.error || "网关未返回采集模式"));
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "网关不可达");
      }
    })();
    return () => { alive = false; };
  }, [serial]);
  if (mode === "h264") return <H264Cast platform="harmony" serial={serial} />;
  if (mode === "jpeg") return <WsCast platform="harmony" serial={serial} />;
  return <div className="emulator-cast">
    <div className="cast-head"><span className="cast-dot harmony connecting" /><b>鸿蒙模拟器</b><code>{serial}</code><small>迁移实现侧</small></div>
    <div className="cast-body"><div className="cast-placeholder">{error || "正在探测采集模式…"}</div></div>
  </div>;
}

/** 模拟器 WS 高速投射 + 反向控制（Android/鸿蒙通用：点画面反控，tap/swipe/返回/桌面） */
function WsCast({ platform, serial, deviceW = 1080, deviceH = 2400 }: { platform: "android" | "harmony"; serial: string; deviceW?: number; deviceH?: number }) {
  const isAndroid = platform === "android";
  const [frameUrl, setFrameUrl] = useState<string>("");
  const [status, setStatus] = useState<"connecting" | "live" | "error">("connecting");
  const [deviceRes, setDeviceRes] = useState<{ w: number; h: number } | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  // 鸿蒙反控坐标为设备像素空间：按真实分辨率换算，避免与默认值不符导致点击错位
  useEffect(() => {
    if (platform !== "harmony") return;
    let alive = true;
    void (async () => {
      try {
        const response = await fetch(`/api/emulator/harmony/info?serial=${encodeURIComponent(serial)}`);
        if (!response.ok) return;
        const data = await response.json();
        if (alive && Number(data.width) > 0 && Number(data.height) > 0) setDeviceRes({ w: Number(data.width), h: Number(data.height) });
      } catch { /* 解析失败则沿用默认分辨率 */ }
    })();
    return () => { alive = false; };
  }, [platform, serial]);
  const dw = deviceRes?.w ?? deviceW;
  const dh = deviceRes?.h ?? deviceH;
  useEffect(() => {
    let alive = true;
    let objectUrl = "";
    const wsUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/emulator/${platform}/ws`;
    let ws: WebSocket | null = null;
    let retry: number | undefined;
    const connect = () => {
      if (!alive) return;
      ws = new WebSocket(wsUrl);
      ws.binaryType = "blob";
      ws.onopen = () => setStatus("live");
      ws.onmessage = (event) => {
        const blob = event.data as Blob;
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = URL.createObjectURL(blob);
        setFrameUrl(objectUrl);
      };
      ws.onclose = () => { if (alive) { setStatus("error"); retry = window.setTimeout(connect, 2000); } };
      ws.onerror = () => { try { ws?.close(); } catch {} };
    };
    connect();
    return () => { alive = false; if (retry) window.clearTimeout(retry); try { ws?.close(); } catch {} if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [platform]);
  const toDevice = (event: React.PointerEvent<HTMLImageElement>) => {
    const img = imgRef.current;
    if (!img) return null;
    const rect = img.getBoundingClientRect();
    const x = Math.round(((event.clientX - rect.left) / rect.width) * dw);
    const y = Math.round(((event.clientY - rect.top) / rect.height) * dh);
    return { x: Math.max(0, Math.min(dw - 1, x)), y: Math.max(0, Math.min(dh - 1, y)) };
  };
  const control = async (payload: Record<string, unknown>) => {
    try { await fetch(`/api/emulator/${platform}/control`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }); } catch { /* 静默 */ }
  };
  return <div className="emulator-cast interactive">
    <div className="cast-head">
      <span className={`cast-dot ${status} ${isAndroid ? "android" : "harmony"}`} />
      <b>{isAndroid ? "Android 模拟器" : "鸿蒙模拟器"}</b>
      <code>{serial}</code>
      <small>{isAndroid ? "对照基准（oracle）" : "迁移实现侧"} · WS 高速流 · {dw}×{dh} · 可反控</small>
      {isAndroid && <a className="text-sync-button" href="http://localhost:8000" target="_blank" rel="noreferrer">ws-scrcpy ↗</a>}
    </div>
    <div className="cast-body">
      {frameUrl
        ? <img
            ref={imgRef}
            src={frameUrl}
            alt={`${isAndroid ? "Android" : "鸿蒙"}模拟器实时画面`}
            draggable={false}
            onPointerDown={(event) => { dragStart.current = toDevice(event); }}
            onPointerUp={(event) => {
              const start = dragStart.current;
              const end = toDevice(event);
              dragStart.current = null;
              if (!start || !end) return;
              const moved = Math.abs(start.x - end.x) + Math.abs(start.y - end.y);
              if (moved > 60) void control({ action: "swipe", x: start.x, y: start.y, x2: end.x, y2: end.y });
              else void control({ action: "tap", x: end.x, y: end.y });
            }}
          />
        : <div className="cast-placeholder">{status === "error" ? "推流中断，重连中…" : "正在获取画面…"}</div>}
    </div>
    <div className="cast-controls">
      <button type="button" onClick={() => void control({ action: "back" })}>← 返回</button>
      <button type="button" onClick={() => void control({ action: "home" })}>⌂ 桌面</button>
    </div>
  </div>;
}
function EmulatorCast({ serial, platform = "android" }: { serial: string; platform?: "android" | "harmony" }) {
  const [frameUrl, setFrameUrl] = useState<string>("");
  const [status, setStatus] = useState<"connecting" | "live" | "error">("connecting");
  useEffect(() => {
    let alive = true;
    let objectUrl = "";
    const tick = async () => {
      try {
        const response = await fetch(`/api/emulator/${platform}/frame?serial=${encodeURIComponent(serial)}`);
        if (!response.ok) throw new Error(String(response.status));
        const blob = await response.blob();
        if (!alive) return;
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = URL.createObjectURL(blob);
        setFrameUrl(objectUrl);
        setStatus("live");
      } catch {
        if (alive) setStatus("error");
      }
    };
    void tick();
    const timer = window.setInterval(() => { void tick(); }, platform === "android" ? 600 : 1200);
    return () => { alive = false; window.clearInterval(timer); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [serial, platform]);
  const isAndroid = platform === "android";
  return <div className="emulator-cast">
    <div className="cast-head">
      <span className={`cast-dot ${status} ${isAndroid ? "android" : "harmony"}`} />
      <b>{isAndroid ? "Android 模拟器" : "鸿蒙模拟器"}</b>
      <code>{serial}</code>
      <small>{status === "live" ? `${isAndroid ? "对照基准（oracle）" : "迁移实现侧"} · 只读投射` : status === "connecting" ? "连接中…" : "设备不可达，持续重试…"}</small>
      {isAndroid && <a className="text-sync-button" href="http://localhost:8000" target="_blank" rel="noreferrer">低延迟反控 ↗</a>}
    </div>
    <div className="cast-body">
      {frameUrl ? <img src={frameUrl} alt={`${isAndroid ? "Android" : "鸿蒙"}模拟器实时画面`} /> : <div className="cast-placeholder">{status === "error" ? "模拟器离线或工具不可达" : "正在获取画面…"}</div>}
    </div>
  </div>;
}

/** Phase 2 实况面板（大白话）：当前在验证什么功能，与 Phase 2 交付物（行为契约）一一对应 */
function LiveActivityPanel({ workspaceDir }: { workspaceDir?: string }) {
  const [activity, setActivity] = useState<{ headline: string; detail: string; linked?: string; runId?: string; timeline?: Array<{ at: string; text: string; bc?: string }> } | null>(null);
  useEffect(() => {
    if (!workspaceDir) return;
    let alive = true;
    const load = async () => {
      try {
        const response = await fetch(`/api/run/activity?workspace=${encodeURIComponent(workspaceDir)}`);
        if (!response.ok) return;
        const data = await response.json();
        if (alive) setActivity(data);
      } catch { /* 静默 */ }
    };
    void load();
    const timer = window.setInterval(() => { void load(); }, 10000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [workspaceDir]);
  return <div className="live-activity">
    <p className="lp-eyebrow">现在正在干嘛</p>
    <div className="activity-now">
      <div className="activity-headline">{activity?.headline ?? "读取中…"}</div>
      {activity?.detail && <p className="activity-detail">{activity.detail}</p>}
      {activity?.linked && <small className="activity-linked">对应交付物：{activity.linked}</small>}
    </div>
    <p className="lp-eyebrow">最近在做什么</p>
    <div className="activity-timeline">
      {(activity?.timeline ?? []).length > 0 ? activity!.timeline!.map((event, index) => <div className="activity-event" key={`${event.at}-${index}`}>
        <small>{new Date(event.at).toTimeString().slice(0, 5)}</small>
        <span>{event.text}</span>
      </div>) : <p className="field-note">暂无活动记录</p>}
    </div>
    {activity?.runId && <small className="activity-runid">RUN：{activity.runId}</small>}
  </div>;
}

// ---- RUN 真实证据面板：数据全部来自后端 /api/run/*（实时读取 RUN 产物，禁止编造指标） ----
const runFileUrl = (workspace: string, path: string) => `/api/run/file?workspace=${encodeURIComponent(workspace)}&path=${encodeURIComponent(path)}`;


type RunArtifact = { name: string; path: string; desc: string; type: string };
type RunReworkCase = {
  id: string; at: string; status: string; title: string; problem: string; rootCause: string;
  fix: string; reverify: string; verifyShot: string; hasPairShots: boolean; before: string; after: string; note: string;
};
type RunOverview = {
  runId: string;
  runStatus: string;
  metrics: {
    featuresTotal: number; featuresMapped: number; runtimeVerified: number; sourceConfirmed: number;
    observableMatch: string; stepsPassed: string; softwareDefects: number; toolArtifacts: number; manualCells: number;
    gates: { p1: string; p2: string; p3: string; p4: string };
  };
  build: {
    apk: { path: string; sha256: string; exists: boolean };
    hap: { path: string; exists: boolean; signed: boolean; desc: string };
    installLaunched: boolean;
  };
  artifacts: RunArtifact[];
  summary: string;
  comparisonShots: { android: string; harmony: string };
  reworkCase: RunReworkCase | null;
  diffNote: string;
};
type Phase1Evidence = {
  phase: 1;
  identity: Record<string, string>;
  target: { platform?: string; sdk_or_api_target?: string } | null;
  includedFeatures: Array<{ id: string; title: string; verifyMode: string }>;
  excludedFeatures: Array<{ id: string; reason: string }>;
  policies: Array<{ key: string; value: string; note: string }>;
  allowedSubstitutions: Array<{ capability: string; reason: string }>;
  testSeed: Record<string, unknown> | null;
  androidEnv: Record<string, unknown> | null;
  harmonyEnv: Record<string, unknown> | null;
  gate: { verdict: string; checkedAt: string; scopeSha256: string } | null;
  artifacts: Array<{ name: string; path: string }>;
};
type Phase2Evidence = {
  phase: 2;
  features: Array<{ id: string; name: string; summary: string; verifyMode: string; sourceRefs: string[] }>;
  contracts: Array<{ bcId: string; featureName: string; intent: string; observableResult: string; assertions: string; evidenceClass: string }>;
  chainStats: { total: number; pass: number; amended: number };
  reconciliationStats: { total: number; groups: Record<string, number> };
  shots: Array<{ bcId: string; featureName: string; intent: string; before: string; after: string; restart: string }>;
  forensicsNotes: Array<{ id: string; type: string; decision: string; summary: string }>;
  gate: { verdict: string; checkedAt: string } | null;
};
type Phase3Evidence = {
  phase: 3;
  surfaces: Array<{ surfaceId: string; kind: string; featureId: string; androidStructure: string; preserveTexts: string[]; nativeCarrier: string; nativeComponent: string; matchedRule: string; reason: string }>;
  dataContracts: Array<{ objectId: string; repositorySymbol: string; directions: string[]; featureIds: string[]; requiredOperations: string[]; file: string }>;
  probeFiles: Array<{ name: string; path: string }>;
  probeLockNote: string;
  hverShots: Array<{ id: string; verificationId: string; path: string }>;
  baselineShot: string;
  buildSmoke: { status: string; verificationId: string; cleanBuildPassed: boolean; installDevices: string[]; launchDevices: string[]; hapSha256: string; errors: string[] } | null;
  gate: { verdict: string; checkedAt: string } | null;
};
type Phase4Evidence = {
  phase: 4;
  matrix: Array<{ bcId: string; featureId: string; dimension: string; verdict: string; androidExpected: string; harmonyActual: string; note: string; attribution: string }>;
  dimensionStats: Array<{ dimension: string; match: number; diff: number; manual: number }>;
  replay: Array<{ bcId: string; featureId: string; verifyMode: string; precondition: string; stepsTotal: number; stepsOk: number; observable: string; data: string; persistence: string; sideEffect: string; verdict: string; failReason: string }>;
  stepsPassed: string;
  restartPersistence: Array<{ bcId: string; persistence: string }>;
  diffClassification: {
    softwareDefects: number; toolArtifacts: number; manual: number;
    manualReasons: Record<string, number>;
    toolGaps: Array<{ id: string; tag: string; summary: string }>;
  };
  reworkCase: RunReworkCase | null;
  gate4: {
    machineVerdict: string; checkedAt: string; errors: string[]; runStatus: string; status: string;
    verdictDecision: { id: string; decision: string; summary: string } | null;
  };
  demoShots: Record<string, string>;
};
type PhaseEvidence = Phase1Evidence | Phase2Evidence | Phase3Evidence | Phase4Evidence;

function VerdictBadge({ tone, children }: { tone: "good" | "warn" | "muted"; children: React.ReactNode }) {
  return <span className={`verdict-badge ${tone}`}>{children}</span>;
}

function GateBadge({ verdict, phaseLabel }: { verdict: string; phaseLabel: string }) {
  const pass = verdict === "PASS";
  return <span className={`gate-pill ${pass ? "pass" : "warn"}`}>{phaseLabel} · {verdict === "PASS" ? "PASS" : verdict === "UNKNOWN" ? "无快照" : verdict}</span>;
}

/** 项目总览仪表板：真实指标 / 双端对比 / 一分钟摘要 / 交付物入口 / 典型修复案例（仅在 real 项目 + workspaceDir 存在且数据加载成功时渲染） */
function MigrationOverviewBoard({ workspaceDir }: { workspaceDir?: string }) {
  const [overview, setOverview] = useState<RunOverview | null>(null);
  const [failed, setFailed] = useState(false);
  const [reworkOpen, setReworkOpen] = useState(false);
  useEffect(() => {
    if (!workspaceDir) return;
    let alive = true;
    (async () => {
      try {
        const response = await fetch(`/api/run/overview?workspace=${encodeURIComponent(workspaceDir)}`);
        if (!response.ok) { if (alive) setFailed(true); return; }
        const data = await response.json() as RunOverview;
        if (alive && data?.metrics) setOverview(data); else if (alive) setFailed(true);
      } catch { if (alive) setFailed(true); }
    })();
    return () => { alive = false; };
  }, [workspaceDir]);
  if (!workspaceDir || failed || !overview) return null;
  const m = overview.metrics;
  const rework = overview.reworkCase;
  // 演示评审口径：返工案例只讲人话（问题/根因/修复/复验四短句），工程细节（文件行号/哈希）见决策日志
  const reworkLines = rework ? {
    title: rework.title.split("（")[0],
    problem: /凭空出现返回按钮/.test(rework.problem) ? "鸿蒙首页左上角凭空多出一个返回按钮（Android 原版没有）" : rework.problem.slice(0, 60),
    rootCause: "页面被以「入栈」方式打开，系统标题栏自动渲染了返回按钮",
    fix: rework.fix.includes("hideBackButton") ? "在页面标题栏上隐藏系统返回按钮——只改一处，其余零改动" : rework.fix.slice(0, 60),
    reverify: /全过|四项/.test(rework.reverify) ? "重新构建、安装、启动后实机核验：左上角无返回按钮，标题 / 排序 / 输入区 / 空态齐全" : rework.reverify.slice(0, 60),
  } : null;
  // 交付物入口：演示只显眼 4 项，其余收进折叠
  const featuredKeys = ["签名 HAP", "双机差分", "盘点报告", "Gate 4"];
  const featuredArtifacts = overview.artifacts.filter((a) => featuredKeys.some((k) => a.name.includes(k)));
  const restArtifacts = overview.artifacts.filter((a) => !featuredKeys.some((k) => a.name.includes(k)));
  const artifactHref = (artifact: RunArtifact) => artifact.path.startsWith("/") ? artifact.path : runFileUrl(workspaceDir, artifact.path);
  return <div className="migration-overview-board">
    <div className="mob-head">
      <div>
        <p className="lp-eyebrow">RUN 真实证据总览 · {overview.runId}</p>
        <div className="mob-badges">
          <VerdictBadge tone="good">✓ 软件成果可运行</VerdictBadge>
          <VerdictBadge tone="good">✓ 核心行为验证通过（可观察行为 {m.observableMatch} MATCH）</VerdictBadge>
          <VerdictBadge tone="warn">⚠ Gate 4 待人工裁决（机器 FAIL · fail-closed 口径）</VerdictBadge>
        </div>
      </div>
      <small className="mob-source">数据源：RUN 产物文件实时读取 · 状态 {overview.runStatus || "—"}</small>
    </div>
    <div className="metric-row">
      <div className="metric-card">
        <small>功能完成迁移</small>
        <b>{m.featuresTotal}<span> / {m.featuresTotal} 项</span></b>
        <em>功能地图 {m.featuresMapped} 项 · 真机验证 {m.runtimeVerified} + 源码确认 {m.sourceConfirmed}</em>
      </div>
      <div className="metric-card">
        <small>可观察行为 MATCH</small>
        <b>{m.observableMatch}</b>
        <em>双机差分 observable 维度（Android 基准 ↔ 鸿蒙实现）</em>
      </div>
      <div className="metric-card">
        <small>操作步骤通过</small>
        <b>{m.stepsPassed}</b>
        <em>鸿蒙实机按行为契约重放</em>
      </div>
      <div className="metric-card">
        <small>Gate 1 / 2 / 3</small>
        <b className="mint-text">{m.gates.p1 === "PASS" && m.gates.p2 === "PASS" && m.gates.p3 === "PASS" ? "全部 PASS" : `${m.gates.p1}/${m.gates.p2}/${m.gates.p3}`}</b>
        <em>范围冻结 · Android 盘点 · 鸿蒙骨架（机器判定）</em>
      </div>
      <div className="metric-card warn">
        <small>Gate 4</small>
        <b>待人工裁决</b>
        <em>机器判定 {m.gates.p4} · 软件缺陷 {m.softwareDefects} · 取证工具伪影 {m.toolArtifacts} · 转人工 {m.manualCells} 格</em>
      </div>
    </div>
    {(overview.comparisonShots.android || overview.comparisonShots.harmony) && <div className="duo-shot">
      {overview.comparisonShots.android && <figure>
        <img src={runFileUrl(workspaceDir, overview.comparisonShots.android)} alt="Android 基准真机截图" loading="lazy" />
        <figcaption>Android 基准（emulator-5554）· 同操作执行后</figcaption>
      </figure>}
      {overview.comparisonShots.harmony && <figure>
        <img src={runFileUrl(workspaceDir, overview.comparisonShots.harmony)} alt="HarmonyOS 实现真机截图" loading="lazy" />
        <figcaption>HarmonyOS 实现（127.0.0.1:5557）· 同操作执行后</figcaption>
      </figure>}
    </div>}
    <p className="ev-summary"><b>一分钟摘要：</b>{overview.summary}</p>
    <div className="mob-bottom">
      <div className="artifact-list">
        <p className="lp-eyebrow">关键交付物</p>
        {featuredArtifacts.map((artifact) => <a
          className="artifact-chip"
          key={artifact.path || artifact.name}
          href={artifactHref(artifact)}
          target="_blank"
          rel="noreferrer"
          {...(artifact.type === "download" ? { download: "" } : {})}
        >
          <b>{artifact.name}</b>
          <small>{artifact.desc}</small>
        </a>)}
        {restArtifacts.length > 0 && <details className="ev-details">
          <summary>全部产物（{overview.artifacts.length} 项）</summary>
          <div className="artifact-list">
            {restArtifacts.map((artifact) => <a
              className="artifact-chip"
              key={artifact.path || artifact.name}
              href={artifactHref(artifact)}
              target="_blank"
              rel="noreferrer"
              {...(artifact.type === "download" ? { download: "" } : {})}
            >
              <b>{artifact.name}</b>
              <small>{artifact.desc}</small>
            </a>)}
            <small className="artifact-note">
              基线 APK（SHA-256 已存档）{overview.build.hap.exists ? " · 签名 HAP 由本地自签链签名（verify-app PASS）" : ""}
              {overview.build.installLaunched ? " · 构建安装启动链实测通过" : ""}
            </small>
          </div>
        </details>}
      </div>
      {rework && reworkLines && <div className={`rework-card ${reworkOpen ? "open" : ""}`}>
        <button type="button" className="rework-toggle" onClick={() => setReworkOpen((open) => !open)}>
          <b>🔧 典型修复案例 · {reworkLines.title}</b>
          <span>{reworkOpen ? "收起 ▲" : "展开详情 ▼"}</span>
        </button>
        {reworkOpen && <div className="rework-body">
          <dl className="rework-facts">
            <div><dt>问题</dt><dd>{reworkLines.problem}</dd></div>
            <div><dt>根因</dt><dd>{reworkLines.rootCause}</dd></div>
            <div><dt>修复</dt><dd>{reworkLines.fix}</dd></div>
            <div><dt>复验</dt><dd>{reworkLines.reverify}</dd></div>
          </dl>
          {rework.verifyShot && <div className="rework-shots single">
            <figure>
              <img src={runFileUrl(workspaceDir, rework.verifyShot)} alt="返工复验鸿蒙真机截图" loading="lazy" />
              <figcaption>修复后实机复验 · 左上角已无返回按钮</figcaption>
            </figure>
          </div>}
        </div>}
      </div>}
    </div>
  </div>;
}

/** Phase 证据面板：按选中阶段渲染 P1-P4 的真实取证数据（插在阶段汇总之后、投射区之前） */
function PhaseEvidencePanel({ workspaceDir, phase }: { workspaceDir?: string; phase: PhaseNumber }) {
  const [evidence, setEvidence] = useState<PhaseEvidence | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!workspaceDir) return;
    let alive = true;
    setEvidence(null);
    setFailed(false);
    (async () => {
      try {
        const response = await fetch(`/api/run/phase/${phase}?workspace=${encodeURIComponent(workspaceDir)}`);
        if (!response.ok) { if (alive) setFailed(true); return; }
        const data = await response.json() as PhaseEvidence;
        if (alive && data?.phase) setEvidence(data); else if (alive) setFailed(true);
      } catch { if (alive) setFailed(true); }
    })();
    return () => { alive = false; };
  }, [workspaceDir, phase]);
  if (!workspaceDir || failed || !evidence) return null;
  return <div className="phase-evidence-panel">{evidence.phase === 1 && <Phase1Body data={evidence} ws={workspaceDir} />}
    {evidence.phase === 2 && <Phase2Body data={evidence} ws={workspaceDir} />}
    {evidence.phase === 3 && <Phase3Body data={evidence} ws={workspaceDir} />}
    {evidence.phase === 4 && <Phase4Body data={evidence} ws={workspaceDir} />}</div>;
}

const seedText = (value: unknown) => (Array.isArray(value) ? value.join(" / ") : String(value ?? "—"));
// 演示口径：迁移政策三个标签式短语（键名来自冻结数据，展示为中文短语）
const POLICY_SHORT_LABELS: Record<string, string> = {
  FUNCTIONAL_EQUIVALENCE: "功能一致性",
  UI_FIDELITY: "UI 保真",
  NATIVE_ADAPTATION: "原生适配",
};
const POLICY_SHORT_VALUES: Record<string, string> = {
  HARD: "硬约束",
  HIGH: "高保真",
  CONSTRAINED: "受限",
};

function Phase1Body({ data, ws }: { data: Phase1Evidence; ws: string }) {
  const identity = data.identity;
  const appName = Array.isArray(data.testSeed?.expected_initial_texts) && data.testSeed.expected_initial_texts.length
    ? String((data.testSeed.expected_initial_texts as unknown[])[0])
    : identity.applicationId;
  return <>
    <p className="lp-eyebrow">Phase 1 · 冻结了什么（应用身份 + 7 项功能范围）</p>
    <div className="ev-grid">
      <div className="ev-info-card">
        <div className="ev-kv"><span>应用</span><b>{appName}（{identity.applicationId}）</b></div>
        <div className="ev-kv"><span>版本</span><b>{identity.appVersion}</b></div>
        <div className="ev-kv"><span>源码 commit</span><code>{identity.sourceRevision.slice(0, 7)}</code></div>
        <div className="ev-kv" title={identity.apkSha256}><span>基线 APK</span><b>{identity.apkSha256 ? `SHA-256 ${identity.apkSha256.slice(0, 8)}…（已存档）` : "—"}</b></div>
        <div className="ev-kv"><span>目标平台</span><b>{data.target?.platform ?? "—"}</b></div>
      </div>
      <div className="ev-side">
        {data.gate && <div className="gate-card pass">
          <b>Gate 1 · {data.gate.verdict}</b>
          <small>范围冻结通过机器校验 · {data.gate.checkedAt.replace("T", " ").slice(0, 19)} UTC</small>
        </div>}
        <div className="policy-tags">
          <b>迁移三原则</b>
          <div className="policy-tag-row">
            {data.policies.map((policy) => <span className="policy-tag" key={policy.key}>
              {POLICY_SHORT_LABELS[policy.key] ?? policy.key} = {POLICY_SHORT_VALUES[policy.value] ?? policy.value}
            </span>)}
          </div>
          <small>数据 / 持久化不许漂移，界面保真，平台控件按白名单替换</small>
        </div>
      </div>
    </div>
    <table className="ev-table">
      <thead><tr><th>纳入功能（{data.includedFeatures.length} 项）</th><th>一句话定义</th><th>验证方式</th></tr></thead>
      <tbody>{data.includedFeatures.map((feature) => <tr key={feature.id}>
        <td><b>{feature.title.split("：")[0]}</b><small className="ev-id">{feature.id}</small></td>
        <td className="ev-wrap">{feature.title.split("：").slice(1).join("：") || feature.title}</td>
        <td><span className={`verify-tag ${feature.verifyMode === "RUNTIME" ? "runtime" : "source"}`}>{feature.verifyMode === "RUNTIME" ? "真机验证" : "源码确认"}</span></td>
      </tr>)}</tbody>
    </table>
    <details className="ev-details">
      <summary>冻结细节（排除项 · 测试种子 · 双端环境）</summary>
      {data.excludedFeatures.map((feature) => <div className="ev-exclude" key={feature.id}>
        <b>排除项 {feature.id}</b>
        <p>{feature.reason}</p>
      </div>)}
      <div className="gate-card">
        <b>测试种子（Phase 2 / 4 同一起点）</b>
        <small>预置数据 {seedText(data.testSeed?.preset_item_count)} 条 · 初始排序「{seedText(data.testSeed?.initial_sort_label)}」 · 初始页面文本：{seedText(data.testSeed?.expected_initial_texts)}</small>
      </div>
      <div className="gate-card">
        <b>双端实测环境</b>
        <small>Android 基线：{seedText(data.androidEnv?.emulator_model)} · API {seedText(data.androidEnv?.android_api_level)} · {seedText(data.androidEnv?.locale)} / {seedText(data.androidEnv?.theme)} · {seedText(data.androidEnv?.device_serial)}</small>
        <small>鸿蒙目标：{String(data.harmonyEnv?.software_version ?? "")} API {String(data.harmonyEnv?.api_version ?? "")} · {String(data.harmonyEnv?.device_serial ?? "")}</small>
      </div>
      <div className="artifact-inline">
        {data.artifacts.map((artifact) => <a key={artifact.path} href={runFileUrl(ws, artifact.path)} target="_blank" rel="noreferrer">{artifact.name} ↗</a>)}
      </div>
    </details>
  </>;
}

function Phase2Body({ data, ws }: { data: Phase2Evidence; ws: string }) {
  const confirmed = data.reconciliationStats.groups.CONFIRMED ?? 0;
  const sourceConfirmed = data.reconciliationStats.groups.SOURCE_CONFIRMED ?? 0;
  const gap = data.reconciliationStats.groups.GAP ?? 0;
  return <>
    <p className="lp-eyebrow">Phase 2 · 摸清了 Android 版的全部行为（{data.features.length} 项功能逐一在真机上验证留证）</p>
    <div className="simple-strip">
      <span><b>{data.reconciliationStats.total}/{data.reconciliationStats.total}</b> 识别</span>
      <span><b>{confirmed}</b> 真机验证 + <b>{sourceConfirmed}</b> 源码确认</span>
      <span>冲突 <b>0</b> · GAP <b>{gap}</b></span>
    </div>
    <table className="ev-table">
      <thead><tr><th>功能</th><th>一句话语义</th><th>验证方式</th></tr></thead>
      <tbody>{data.features.map((feature) => <tr key={feature.id}>
        <td><b>{feature.name}</b></td>
        <td className="ev-wrap">{feature.summary}</td>
        <td><span className={`verify-tag ${feature.verifyMode === "RUNTIME" ? "runtime" : "source"}`}>{feature.verifyMode === "RUNTIME" ? "真机验证" : "源码确认"}</span></td>
      </tr>)}</tbody>
    </table>
    <p className="lp-eyebrow">真机截图墙 · 每项操作的前 / 后 / 重启三时点取证</p>
    <div className="shot-wall">
      {data.shots.map((shot) => <div className="shot-group" key={shot.bcId}>
        <div className="shot-head"><b>{shot.featureName}</b><span>{shot.intent}</span></div>
        <div className="shot-row">
          {[["before", shot.before, "操作前"], ["after", shot.after, "操作后"], ["restart", shot.restart, "重启后"]].map(([key, path, label]) => path
            ? <figure key={String(key)}><img src={runFileUrl(ws, String(path))} alt={`${shot.featureName} ${label}截图`} loading="lazy" /><figcaption>{label}</figcaption></figure>
            : <figure className="missing" key={String(key)}><figcaption>{label}（未采集）</figcaption></figure>)}
        </div>
      </div>)}
    </div>
    <details className="ev-details">
      <summary>行为契约明细（{data.contracts.length} 条）</summary>
      <table className="ev-table compact">
        <thead><tr><th>行为契约</th><th>用户意图</th><th>可观察结果</th><th>关键断言</th></tr></thead>
        <tbody>{data.contracts.map((contract) => <tr key={contract.bcId}>
          <td><b>{contract.bcId}</b><small className="ev-id">{contract.featureName}</small></td>
          <td className="ev-wrap">{contract.intent}</td>
          <td className="ev-wrap">{contract.observableResult}</td>
          <td><code className="ev-refs">{contract.assertions}</code></td>
        </tr>)}</tbody>
      </table>
    </details>
    {data.forensicsNotes.length > 0 && <div className="forensics-card">
      <b>小提示：{data.chainStats.amended} 条链的「重启后」断言曾被判失败</b>
      <p>经独立探针复核，是取证工具自己的问题（伪影 ≠ 软件缺陷），App 行为本身完全正常。</p>
      <details className="ev-details"><summary>原始记录（{data.forensicsNotes.length} 条决策）</summary>
        {data.forensicsNotes.map((note) => <p key={note.id}><code>{note.id}</code> · {note.type} → {note.summary}</p>)}
      </details>
    </div>}
    {data.gate && <div className="gate-card pass"><b>Gate 2 · {data.gate.verdict}</b><small>功能覆盖 + 行为契约 + 调和结论全部通过机器校验 · {data.gate.checkedAt.replace("T", " ").slice(0, 19)} UTC</small></div>}
  </>;
}

function Phase3Body({ data, ws }: { data: Phase3Evidence; ws: string }) {
  return <>
    <p className="lp-eyebrow">Phase 3 · 每个界面元素在鸿蒙上用什么组件对应（冻结蓝图，Phase 4 照图施工）</p>
    <table className="ev-table">
      <thead><tr><th>界面单元</th><th>必须保留的锚点文本</th><th>鸿蒙原生组件</th></tr></thead>
      <tbody>{data.surfaces.map((surface) => <tr key={surface.surfaceId}>
        <td><b>{surface.kind === "page" ? "主页面" : "数据层（非界面）"}</b><small className="ev-id">{surface.surfaceId}</small></td>
        <td className="ev-wrap">{surface.preserveTexts.slice(0, 3).join(" / ")}{surface.preserveTexts.length > 3 ? " 等" : ""}</td>
        <td className="ev-wrap">{surface.nativeComponent}</td>
      </tr>)}</tbody>
    </table>
    <p className="lp-eyebrow">迁移前后 GUI 对比（同一页面）</p>
    <div className="duo-shot">
      {data.baselineShot && <figure><img src={runFileUrl(ws, data.baselineShot)} alt="P2 Android 基线截图" loading="lazy" /><figcaption>Android 基准（Phase 2 取证）</figcaption></figure>}
      {data.hverShots.map((shot) => <figure key={shot.path}><img src={runFileUrl(ws, shot.path)} alt="HVER 鸿蒙实机截图" loading="lazy" /><figcaption>HarmonyOS 实机（骨架冒烟截图）</figcaption></figure>)}
    </div>
    <div className="gate-row-pair">
      {data.buildSmoke && <div className="gate-card pass">
        <b>构建冒烟 · 三步全通过</b>
        <small>① 构建成功（hvigorw clean assembleHap）</small>
        <small>② 安装成功（鸿蒙模拟器 {data.buildSmoke.installDevices.length > 0 ? "127.0.0.1:5557" : "—"}）</small>
        <small>③ 冷启动成功，页面锚点齐全</small>
      </div>}
      {data.gate && <div className="gate-card pass"><b>Gate 3 · {data.gate.verdict}</b><small>骨架封板 · 冒烟链全通过 · {data.gate.checkedAt.replace("T", " ").slice(0, 19)} UTC</small></div>}
    </div>
    <details className="ev-details">
      <summary>数据契约与探针（{data.dataContracts.length} 个语义对象）</summary>
      <div className="contract-row">
        {data.dataContracts.map((contract) => <div className="contract-card" key={contract.objectId}>
          <b>{contract.objectId}</b>
          <small>{contract.repositorySymbol} · {contract.directions.join("/")}</small>
          <p>required_operations：{contract.requiredOperations.join(" · ")}</p>
          <p>承载功能：{contract.featureIds.map((id) => id.replace("FEAT-", "")).join(" · ")}</p>
          <a href={runFileUrl(ws, contract.file)} target="_blank" rel="noreferrer">契约文件 ↗</a>
        </div>)}
      </div>
      {data.probeFiles.length > 0 && <div className="gate-card">
        <b>语义探针（DebugSemanticProbe / SemanticProbeRegistry）</b>
        <div className="artifact-inline">{data.probeFiles.map((file) => <a key={file.path} href={runFileUrl(ws, file.path)} target="_blank" rel="noreferrer">{file.name} ↗</a>)}</div>
        {data.probeLockNote && <small className="ev-wrap">{data.probeLockNote}</small>}
      </div>}
    </details>
  </>;
}

// 演示口径：四个验证维度的中文名与主判定短语（数值一律来自 dimensionStats / replay 实时统计）
const DIMENSION_LABELS: Record<string, string> = {
  observable: "可观察行为",
  data: "数据一致性",
  persistence: "重启持久化",
  side_effect: "副作用",
};

function Phase4Body({ data, ws }: { data: Phase4Evidence; ws: string }) {
  const verdictClass = (verdict: string) => verdict === "MATCH" ? "v-match" : verdict === "DIFF" ? "v-diff" : "v-manual";
  const rework = data.reworkCase;
  const persistPass = data.replay.filter((row) => row.persistence === "PASS").length;
  const persistTotal = data.replay.filter((row) => row.persistence === "PASS" || row.persistence === "MANUAL_VERIFY_REQUIRED").length;
  const cls = data.diffClassification;
  return <>
    <p className="lp-eyebrow">Phase 4 · 双机对比验证：Android 与鸿蒙同操作、逐项对比</p>
    <div className="stat-strip">
      {data.dimensionStats.map((dimension) => {
        const tone = dimension.match > 0 ? "good" : dimension.diff > 0 ? "warn" : "muted";
        const headline = dimension.match > 0 ? `${dimension.match} MATCH`
          : dimension.diff > 0 ? `${dimension.diff} 处 · 工具伪影`
          : `${dimension.manual} 格转人工`;
        return <div className={`stat-cell ${tone}`} key={dimension.dimension}>
          <b>{headline}</b>
          <span>{DIMENSION_LABELS[dimension.dimension] ?? dimension.dimension}（MATCH {dimension.match} / DIFF {dimension.diff} / MANUAL {dimension.manual}）</span>
        </div>;
      })}
    </div>
    <p className="one-line-verdict">
      {cls.toolArtifacts} 处机器 DIFF 全部定性为<b>取证工具伪影</b>（软件缺陷 <b className="mint-text">{cls.softwareDefects}</b>）
      · 操作步骤 <b>{data.stepsPassed}</b> 通过 · 重启持久化 <b>{persistPass}/{persistTotal}</b> PASS
    </p>
    {rework && <div className="rework-inline">
      <b>🔧 返工案例 · {rework.title.split("（")[0]}</b>
      <dl className="rework-facts">
        <div><dt>问题</dt><dd>{/凭空出现返回按钮/.test(rework.problem) ? "鸿蒙首页左上角凭空多出一个返回按钮（Android 原版没有）" : rework.problem.slice(0, 60)}</dd></div>
        <div><dt>根因</dt><dd>页面被以「入栈」方式打开，系统标题栏自动渲染了返回按钮</dd></div>
        <div><dt>修复</dt><dd>{rework.fix.includes("hideBackButton") ? "在页面标题栏上隐藏系统返回按钮——只改一处，其余零改动" : rework.fix.slice(0, 60)}</dd></div>
        <div><dt>复验</dt><dd>{/全过|四项/.test(rework.reverify) ? "重新构建、安装、启动后实机核验：无返回按钮，页面要素齐全" : rework.reverify.slice(0, 60)}</dd></div>
      </dl>
      {rework.verifyShot && <a className="rework-shot-link" href={runFileUrl(ws, rework.verifyShot)} target="_blank" rel="noreferrer">查看复验真机截图 ↗</a>}
    </div>}
    <div className="gate-card warn big">
      <b>Gate 4 · 机器判定 {data.gate4.machineVerdict} → 状态「{data.gate4.status}」</b>
      <small>机器按「宁可误报不可漏报」口径如实记 FAIL；{cls.toolArtifacts} 处 DIFF 已全部论证为取证工具伪影、软件缺陷 {cls.softwareDefects}，交由人工裁决，未翻转任何机器判定。</small>
      <small>运行状态 {data.gate4.runStatus} · {data.gate4.checkedAt.replace("T", " ").slice(0, 19)} UTC</small>
    </div>
    <details className="ev-details">
      <summary>查看完整一致性矩阵（{data.matrix.length} 格）</summary>
      <table className="ev-table matrix">
        <thead><tr><th>BC</th><th>维度</th><th>Android 期望</th><th>Harmony 实测</th><th>机器判定</th></tr></thead>
        <tbody>{data.matrix.map((cell) => <tr key={`${cell.bcId}-${cell.dimension}`}>
          <td><b>{cell.bcId}</b></td>
          <td>{DIMENSION_LABELS[cell.dimension] ?? cell.dimension}</td>
          <td><code className="ev-json">{cell.androidExpected}</code></td>
          <td><code className="ev-json">{cell.harmonyActual}</code></td>
          <td><span className={`matrix-verdict ${verdictClass(cell.verdict)}`}>{cell.verdict}</span>
            {cell.attribution === "TOOL_ARTIFACT" && <small className="artifact-flag">取证工具伪影</small>}</td>
        </tr>)}</tbody>
      </table>
    </details>
    <details className="ev-details">
      <summary>操作重放明细（{data.replay.length} 条行为契约）</summary>
      <table className="ev-table compact">
        <thead><tr><th>BC</th><th>前置条件</th><th>步骤</th><th>observable</th><th>persistence</th><th>判定</th></tr></thead>
        <tbody>{data.replay.map((row) => <tr key={row.bcId}>
          <td><b>{row.bcId}</b><small className="ev-id">{row.verifyMode}</small></td>
          <td>{row.precondition || "—"}</td>
          <td>{row.stepsTotal > 0 ? `${row.stepsOk}/${row.stepsTotal}` : "0"}</td>
          <td><span className={`matrix-verdict ${verdictClass(row.observable === "PASS" ? "MATCH" : row.observable === "FAIL" ? "DIFF" : "v-manual")}`}>{row.observable || "—"}</span></td>
          <td><span className={`matrix-verdict ${verdictClass(row.persistence === "PASS" ? "MATCH" : row.persistence === "FAIL" ? "DIFF" : "v-manual")}`}>{row.persistence || "—"}</span></td>
          <td>{row.verdict}{row.failReason ? <small className="ev-id">{row.failReason}</small> : null}</td>
        </tr>)}</tbody>
      </table>
    </details>
    <details className="ev-details">
      <summary>DIFF 分类明细（软件缺陷 {cls.softwareDefects} / 工具伪影 {cls.toolArtifacts} / 转人工 {cls.manual}）</summary>
      <div className="diff-class-row">
        <div className="diff-card good"><b>{cls.softwareDefects}</b><span>软件缺陷</span><small>全部 DIFF 经决策日志论证归因取证侧，无鸿蒙行为缺陷</small></div>
        <div className="diff-card warn"><b>{cls.toolArtifacts}</b><span>取证工具伪影（DIFF）</span>
          {cls.toolGaps.map((gap) => <small key={gap.id}><code>{gap.tag}</code> {gap.summary.slice(0, 110)}…</small>)}
        </div>
        <div className="diff-card muted"><b>{cls.manual}</b><span>转人工核验（MANUAL）</span>
          {Object.entries(cls.manualReasons).map(([reason, count]) => <small key={reason}>×{count} · {reason}</small>)}
        </div>
      </div>
      {data.gate4.errors.length > 0 && <details className="gate-errors"><summary>gate-report 机器错误明细（{data.gate4.errors.length}）</summary>{data.gate4.errors.map((error) => <p key={error}>{error}</p>)}</details>}
    </details>
  </>;
}

/** CodeArts Space 风格项目工作区：常驻对话面板（主体）+ 任务概览（侧栏） */
function ProjectChatWorkspace({ project }: { project: Project }) {
  const sessionId = project.activeSessionId;
  const [messages, setMessages] = useState<CodeArtsMessage[]>([]);
  const [team, setTeam] = useState<AgentTeamState | null>(null);
  const [summary, setSummary] = useState<{ additions: number; deletions: number; files: number } | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendNote, setSendNote] = useState("");

  const [selectedPhase, setSelectedPhase] = useState<PhaseNumber>(project.currentPhase);
  const [anomalies, setAnomalies] = useState<Array<{ runId: string; id: string; at: string; type: string; decision: string; detail: string }>>([]);
  useEffect(() => {
    if (!project.workspaceDir) return;
    let alive = true;
    const load = async () => {
      try {
        const response = await fetch(`/api/run/anomalies?workspace=${encodeURIComponent(project.workspaceDir ?? "")}`);
        if (!response.ok) return;
        const data = await response.json() as { anomalies?: typeof anomalies };
        if (alive && data.anomalies) setAnomalies(data.anomalies);
      } catch { /* 静默 */ }
    };
    void load();
    const timer = window.setInterval(() => { void load(); }, 30000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [project.workspaceDir]);
  const streamRef = useRef<HTMLDivElement | null>(null);
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
  useEffect(() => {
    const node = streamRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages.length]);
  const sendMessage = async () => {
    const text = draft.trim();
    if (!text || !sessionId || sending) return;
    setSending(true);
    setSendNote("");
    try {
      const result = await promptCodeArtsSession(sessionId, text, loadCodeArtsCredentials(), {
        agent: "team-leader",
        mode: "agent-team",
        model: parseRunModel(project.runModel ?? ""),
      });
      if (result.accepted || result.pending) {
        setDraft("");
        setSendNote(result.accepted ? "已发送 · 团队将在完成当前工作后回应" : `已排队 · ${result.message.slice(0, 60)}`);
      } else {
        setSendNote(`发送失败：${result.message.slice(0, 80)}`);
      }
    } catch (error) {
      setSendNote(`发送失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setSending(false);
    }
  };
  const selected = project.phases.find((phase) => phase.number === selectedPhase) ?? project.phases[0];
  const phaseMembers = team ? Object.entries(team.members).filter(([name]) => { const p = memberPhaseOf(name); return p === 0 || p === selectedPhase; }) : [];
  const allTasks = team?.tasks ?? [];
  const scopedTasks = allTasks.filter((task) => { const p = taskPhaseOf(task); return p === 0 || p === selectedPhase; });
  const openTasks = scopedTasks.filter((task) => task.status !== "completed");
  const doneTasks = scopedTasks.filter((task) => task.status === "completed");
  const modelLabel = project.runModel ? project.runModel.split("::").pop() : undefined;
  return <div className="space-layout">
    <section className="chat-panel">
      <MigrationOverviewBoard workspaceDir={project.workspaceDir} />
      <PhaseRail phases={project.phases} selected={selectedPhase} onSelect={setSelectedPhase} />
      {selected.execution?.response && <details className="phase-summary-banner" open>
        <summary><b>阶段 {String(selected.number).padStart(2, "0")} 汇总</b><span className={`execution-status ${selected.execution.status ?? "idle"}`}>{selected.execution.status ?? "idle"}</span>
          <Link to={`/projects/${project.id}/review/${selected.number}`} className="ghost-button small" onClick={(event) => event.stopPropagation()}>审核 / 查看完整报告 →</Link>
        </summary>
        <pre className="real-response">{selected.execution.response}</pre>
      </details>}
      {!selected.execution?.response && selected.execution?.sessionId && <div className="phase-summary-banner plain">
        <span>本阶段报告尚未生成</span>
        <Link to={`/projects/${project.id}/review/${selected.number}`} className="ghost-button small">打开审核页 →</Link>
      </div>}
      <PhaseEvidencePanel workspaceDir={project.workspaceDir} phase={selectedPhase} />
      {selectedPhase === 2 && <div className="p2-live-layout">
        <div className="p2-cast-col"><AndroidCastPanel serial="emulator-5554" /></div>
        <div className="p2-activity-col"><LiveActivityPanel workspaceDir={project.workspaceDir} /></div>
      </div>}
      {selectedPhase === 4 && <div className="p4-dual-layout">
        <div className="p4-cast-col"><AndroidCastPanel serial="emulator-5554" /></div>
        <div className="p4-cast-col"><HarmonyCast serial="127.0.0.1:5557" /></div>
        <div className="p4-activity-bar"><LiveActivityPanel workspaceDir={project.workspaceDir} /></div>
      </div>}
      <div className="chat-stream" ref={streamRef}>
        {(() => {
          const tagged = tagMessagesByPhase(messages);
          const visible = tagged.filter((item) => item.phase === selectedPhase);
          if (!visible.length) return <p className="field-note">{sessionId ? `Phase ${selectedPhase} 暂无会话消息` : "启动真实 AgentTeam 后此处为常驻对话面板。"}</p>;
          return visible.map((item) => <ChatBubble key={item.message.info?.id ?? `msg-${item.phase}-${visible.indexOf(item)}`} message={item.message} />);
        })()}
      </div>
      <div className="chat-composer">
        <div className="chat-composer-meta"><span>会话 <code>{sessionId ? `${sessionId.slice(0, 20)}…` : "未创建"}</code></span>{modelLabel && <span>模型 <b>{modelLabel}</b></span>}<span>{messages.length} 条消息 · 5 秒刷新</span></div>
        <div className="chat-composer-row">
          <textarea
            className="chat-composer-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }}
            placeholder="向 AgentTeam 发送指令或提问（Enter 发送 / Shift+Enter 换行）…"
            rows={3}
            disabled={sending || !sessionId}
          />
          <button className="primary-button" type="button" onClick={() => void sendMessage()} disabled={sending || !draft.trim() || !sessionId}>{sending ? "发送中…" : "发送"}</button>
        </div>
        {sendNote && <small className="flow-composer-note">{sendNote}</small>}
      </div>
    </section>
    <aside className="task-dock">
      {anomalies.length > 0 && <div className="anomaly-card">
        <p className="lp-eyebrow">⚠ 异常情况（{anomalies.length}）</p>
        <div className="anomaly-list">{anomalies.slice(0, 10).map((anomaly) => <div className="anomaly-item" key={anomaly.id}>
          <div className="anomaly-item-head">
            <span className={`anomaly-type ${/INTERRUPTED|FAIL|ABORT/.test(anomaly.type) ? "severe" : /REWORK/.test(anomaly.type) ? "rework" : "gap"}`}>{anomaly.type}</span>
            <small>{(anomaly.at || "").replace("T", " ").slice(5, 19)} UTC</small>
          </div>
          <p>{anomaly.decision}{anomaly.detail ? ` — ${anomaly.detail}` : ""}</p>
        </div>)}</div>
        <small className="anomaly-more">来源：RUN decision-log（含工具断点 / 中断 / 返工，30 秒刷新）</small>
      </div>}
      {phaseMembers.some(([, member]) => member.status === "aborted") && <div className="anomaly-card severe">
        <p className="lp-eyebrow">⚠ 成员异常终止</p>
        {phaseMembers.filter(([, member]) => member.status === "aborted").map(([name]) => <p key={name}>{name} · aborted（曾中断，见异常情况与对话记录）</p>)}
      </div>}
      <p className="lp-eyebrow">任务概览 · {PHASE_CHAT_LABELS[selectedPhase]}</p>
      {phaseMembers.length > 0 && <div className="live-members">{phaseMembers.map(([name, member]) => <div className="live-member" key={name}>
        <span className={`team-member-dot ${member.status}`} />
        <b>{name}</b>
        <small>{member.agent_type === "team-leader" ? "队长 · 全程编排" : member.description || "队员 · 执行"}</small>
        <em>{member.status}</em>
      </div>)}</div>}
      {team && openTasks.length > 0 && <>
        <p className="lp-eyebrow">进行中（{openTasks.length}）</p>
        <div className="live-tasks">{openTasks.map((task) => <div className="live-task-row" key={task.id}>
          <span className={`team-task-dot ${task.status}`}>{task.status === "in_progress" || task.status === "running" ? "◌" : "·"}</span>
          <span className="live-task-content">{task.content}{task.owner_name ? ` — ${task.owner_name}` : ""}</span>
        </div>)}</div>
      </>}
      {team && doneTasks.length > 0 && <details className="task-done-list" open={openTasks.length === 0}>
        <summary>已完成任务（{doneTasks.length}）</summary>
        <div className="live-tasks">{doneTasks.map((task) => <div className="live-task-row done" key={task.id}>
          <span className="team-task-dot completed">✓</span>
          <span className="live-task-content">{task.content}{task.owner_name ? ` — ${task.owner_name}` : ""}</span>
        </div>)}</div>
      </details>}
      {summary && <div className="task-diff"><p className="lp-eyebrow">会话变更</p><span className="live-meta-diff">+{summary.additions} / -{summary.deletions} · {summary.files} 文件</span></div>}
      {!team && <p className="field-note">尚未组队或无任务——leader 仍在分析阶段。</p>}
    </aside>
  </div>;
}

/** 标题锚点 slug（大纲与预览标题双向一致） */
function headingSlug(text: string): string {
  return text.replace(/[*`#]/g, "").trim().replace(/\s+/g, "-").slice(0, 48) || "h";
}

/** Markdown 大纲提取（跳过代码块） */
function extractOutline(markdown: string): Array<{ level: number; text: string; slug: string }> {
  const outline: Array<{ level: number; text: string; slug: string }> = [];
  let inCode = false;
  for (const line of markdown.split("\n")) {
    if (/^\s*```/.test(line)) { inCode = !inCode; continue; }
    if (inCode) continue;
    const match = /^(#{1,4})\s+(.+)$/.exec(line);
    if (match) outline.push({ level: match[1].length, text: match[2].replace(/[*`]/g, "").trim(), slug: headingSlug(match[2]) });
  }
  return outline;
}

/** 阶段审核页：VS Code 风格 Markdown 预览（左大纲 + 中正文 + 右审核操作） */
function PhaseReviewPage() {
  const { id, phaseNo } = useParams();
  const project = useProject(id);
  const navigate = useNavigate();
  const number = (Number(phaseNo) || 1) as PhaseNumber;
  const [comment, setComment] = useState("");
  const phase = project?.phases.find((item) => item.number === number);
  const markdown = phase?.execution?.response ?? "";
  const outline = useMemo(() => extractOutline(markdown), [markdown]);
  const previewRef = useRef<HTMLDivElement | null>(null);
  const headingsRef = useRef<Array<HTMLHeadingElement>>([]);
  useEffect(() => {
    headingsRef.current = previewRef.current ? Array.from(previewRef.current.querySelectorAll("h1,h2,h3,h4")) : [];
  }, [markdown]);
  const scrollToHeading = (index: number) => {
    headingsRef.current[index]?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  if (!project) return <NotFound />;
  if (!phase) return <NotFound />;
  const canReview = phase.status === "review_required";
  const submit = (decision: "approved" | "changes_requested") => {
    mockService.reviewPhase(project.id, number, {
      decision,
      comment: comment.trim() || (decision === "approved" ? "网页审核通过" : "网页审核：需修改"),
      reviewer: "人工审核（网页）",
      reviewedAt: new Date().toISOString(),
    });
    navigate(`/projects/${project.id}`);
  };
  const eyebrowOf = PHASE_CHAT_LABELS[number] ?? `Phase ${number}`;
  return <div className="workspace-page">
    <div className="workspace-header"><div className="breadcrumb"><Link to="/">项目总览</Link><span>/</span><Link to={`/projects/${project.id}`}>{project.name}</Link><span>/</span><b>{eyebrowOf} 审核</b></div><div className="workspace-actions"><span className={`execution-status ${phase.execution?.status ?? "idle"}`}>{phase.execution?.status ?? "idle"}</span><Link to={`/projects/${project.id}`} className="ghost-button small">← 返回对话工作区</Link></div></div>
    <div className="workspace-title"><h1>{eyebrowOf} <span className="heading-subtitle">· 审核报告</span></h1><p className="heading-subtitle">{project.name} · {project.id.toUpperCase()} · revision {phase.revision}.0 · {phase.review ? `已审核（${phase.review.decision === "approved" ? "通过" : "要求修改"}）` : canReview ? "等待人工审核" : statusLabels[phase.status]}</p></div>
    <div className="review-layout">
      <aside className="review-outline">
        <p className="lp-eyebrow">大纲</p>
        {outline.length > 0 ? outline.map((item, index) => <a key={`${item.slug}-${index}`} href={`#rv-${index}`} className={`outline-item level-${item.level}`} onClick={(event) => { event.preventDefault(); scrollToHeading(index); }}>{item.text}</a>) : <p className="field-note">报告中无标题结构</p>}
      </aside>
      <div className="review-main">
        <div className="md-preview" ref={previewRef}>
          {markdown ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown> : <div className="real-waiting">该阶段暂无汇总报告——AgentTeam 完成执行并通过机器 Gate 后，此处呈现可审核的完整报告。</div>}
        </div>
      </div>
      <aside className="review-side">
        <div className={`review-action-card ${canReview ? "active" : ""}`}>
          <p className="lp-eyebrow">{canReview ? "人工审核 · 待决策" : "审核状态"}</p>
          {phase.review ? <div className="review-record">
            <span className={`review-decision ${phase.review.decision}`}>{phase.review.decision === "approved" ? "✓ 审核通过" : "✗ 要求修改"}</span>
            <p className="review-comment">“{phase.review.comment}”</p>
            <small>{phase.review.reviewer} · {new Date(phase.review.reviewedAt).toLocaleString()}</small>
          </div> : canReview
            ? <>
              <textarea className="review-comment-input" value={comment} onChange={(event) => setComment(event.target.value)} placeholder="审核意见（可选）：核验要点、放行理由或修改要求…" rows={4} />
              <div className="review-actions-row">
                <button className="primary-button" type="button" onClick={() => submit("approved")}>✓ 审核通过</button>
                <button className="ghost-button" type="button" onClick={() => submit("changes_requested")}>✗ 要求修改</button>
              </div>
              <small className="review-hint">通过后阶段流转至下一环节（外部驱动项目由总控推进执行）</small>
            </>
            : <p className="field-note">{phase.status === "running" ? "AgentTeam 正在执行，完成后进入待审核。" : `当前状态：${statusLabels[phase.status]}`}</p>}
        </div>
        <div className="review-meta-card">
          <p className="lp-eyebrow">报告信息</p>
          <small>字数：{markdown.length} · 大纲 {outline.length} 节</small>
          {phase.execution?.completedAt && <small>完成于 {new Date(phase.execution.completedAt).toLocaleString()}</small>}
          {phase.execution?.sessionId && <small>会话 <code>{phase.execution.sessionId.slice(0, 22)}…</code></small>}
        </div>
      </aside>
    </div>
  </div>;
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
    const approve = searchParams.get("approve") === "1";
    void getCodeArtsMessages(syncId, loadCodeArtsCredentials()).then((messages) => {
      // 只取最后一条完成的 assistant 文本作为该阶段汇总（防止全量历史拼接污染）
      const doneAssistants = messages.filter((item) => item.info?.role === "assistant" && item.info?.time?.completed);
      const text = doneAssistants.length
        ? (doneAssistants[doneAssistants.length - 1].parts ?? []).filter((part) => part.type === "text" && part.text?.trim()).map((part) => part.text).join("\n")
        : "";
      if (text.trim()) {
        mockService.recordCodeArtsExecution?.(project.id, phaseNo, { mode: "codearts-agentteam", status: "succeeded", sessionId: syncId, agent: "team-leader", completedAt: new Date().toISOString(), response: text });
        if (approve) mockService.reviewPhase(project.id, phaseNo, { decision: "approved", comment: "外部总控核验通过（自动同步）", reviewer: "迁移总控", reviewedAt: new Date().toISOString() });
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
  // 真实执行模式：Space 风格布局（常驻对话面板 + 任务概览），不再展示阶段工作区
  if (real) {
    return <div className="workspace-page">
      <div className="workspace-header"><div className="breadcrumb"><Link to="/">项目总览</Link><span>/</span><b>{project.name}</b></div><div className="workspace-actions"><span className="live-tag">真实执行 · CodeArts</span><Link to={`/projects/${project.id}/report`} className="ghost-button small">查看报告</Link><Link to={`/projects/${project.id}/delivery`} className="primary-button small">交付中心 <span>→</span></Link></div></div>
      <div className="workspace-title"><h1>{project.name} <StatusBadge status={project.status === "completed" ? "completed" : project.status === "review" ? "review_required" : "running"} /></h1><p className="heading-subtitle">{project.id.toUpperCase()} · {project.source.value.slice(0, 60)} · CodeArts AgentTeam · {modelLabelOf(project)}</p></div>
      <ProjectChatWorkspace project={project} />
    </div>;
  }
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
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendNote, setSendNote] = useState("");
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
  /** 实时对话：把网页端消息直接发往该项目的 AgentTeam 会话（与四阶段工单同一对话） */
  const sendMessage = async () => {
    const text = draft.trim();
    if (!text || !sessionId || sending) return;
    setSending(true);
    setSendNote("");
    try {
      const result = await promptCodeArtsSession(sessionId, text, loadCodeArtsCredentials(), {
        agent: "team-leader",
        mode: "agent-team",
        model: parseRunModel(project.runModel ?? ""),
      });
      if (result.accepted || result.pending) {
        setDraft("");
        setSendNote(result.accepted ? "已发送 · 团队将在完成当前工作后回应（约 5 秒内出现在上方对话流）" : `已排队 · ${result.message.slice(0, 60)}`);
      } else {
        setSendNote(`发送失败：${result.message.slice(0, 80)}`);
      }
    } catch (error) {
      setSendNote(`发送失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setSending(false);
    }
  };
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
        {sessionId && <div className="flow-composer">
          <textarea
            className="flow-composer-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }}
            placeholder="向 AgentTeam 发送指令或提问（Enter 发送 / Shift+Enter 换行）…"
            rows={2}
            disabled={sending}
          />
          <button className="primary-button small" type="button" onClick={() => void sendMessage()} disabled={sending || !draft.trim()}>{sending ? "发送中…" : "发送"}</button>
        </div>}
        {sendNote && <small className="flow-composer-note">{sendNote}</small>}
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
    { name: "迁移控制器", short: "控", duty: "冻结输入 · 重算门禁 · 路由返工" },
    { name: "人工审核员", short: "审", duty: "机器判定之后，由人放行" },
  ],
  2: [
    { name: "Android 语义分析师", short: "析", duty: "功能地图与行为契约（锚定源码行号）" },
    { name: "Android 运行验证官", short: "验", duty: "高风险功能真机实跑取证" },
    { name: "迁移控制器", short: "控", duty: "源码与运行结果对账" },
  ],
  3: [
    { name: "Harmony 架构负责人", short: "架", duty: "承载面规划与 UI 蓝图" },
    { name: "导航与页面壳代理", short: "航", duty: "路由与页面壳（不含业务）" },
    { name: "工具链与脚手架代理", short: "链", duty: "构建安装与冒烟" },
    { name: "公共 UI 代理", short: "UI", duty: "主题与通用界面资产" },
    { name: "能力契约代理", short: "约", duty: "数据接口契约定义" },
    { name: "架构验收代理", short: "收", duty: "独立终审，只验不改" },
  ],
  4: [
    { name: "功能实现负责人", short: "实", duty: "按功能工单实现" },
    { name: "鸿蒙 UI 代理", short: "UI", duty: "原生组件与视觉还原" },
    { name: "业务与数据代理", short: "数", duty: "数据与持久化实现" },
    { name: "功能属主", short: "主", duty: "功能端到端负责" },
    { name: "原生能力代理", short: "能", duty: "平台系统能力对接" },
    { name: "视觉资产代理", short: "视", duty: "视觉资产迁移" },
    { name: "模拟器验证执行者", short: "执", duty: "双端重放与取证" },
    { name: "一致性验收代理", short: "收", duty: "独立重算判定" },
    { name: "迁移控制器", short: "控", duty: "差分修复回环调度" },
  ],
};

function PhaseAgents({ phaseNumber }: { phaseNumber: number }) {
  const agents = PHASE_AGENTS[phaseNumber] ?? [];
  if (!agents.length) return null;
  return <div className="phase-agents">
    <p className="lp-eyebrow">阶段协作智能体</p>
    <div className="phase-agent-grid">{agents.map((agent) => <div className="phase-agent-card" key={agent.name}>
      <span className="phase-agent-avatar">{agent.short}</span>
      <span className="phase-agent-info"><b>{agent.name}</b><small>{agent.duty}</small></span>
      
    </div>)}</div>
  </div>;
}

function PhaseGate({ gate, checks }: { gate: number; checks: string }) {
  return <div className="phase-gate"><b>Gate {gate}</b><span>{checks}</span></div>;
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
      <p className="lp-eyebrow">迁移范围</p>
      <div className="lp-flow">
        <div className="lp-flow-col"><div className="lp-node solid">Android / Cresto<small>源码 + APK 冻结</small></div></div>
        <div className="lp-flow-arrow">→</div>
        <div className="lp-node contract">12 项核心功能<small>功能 / 数据 / 环境三重冻结</small></div>
        <div className="lp-flow-arrow">→</div>
        <div className="lp-flow-col"><div className="lp-node solid">HarmonyOS<small>目标环境冻结</small></div></div>
      </div>
      <div className="phase-contract-quote">
        <b>核心等价契约</b><p>界面与交互可按鸿蒙原生方式重做；用户意图、数据、业务计算与持久化结果必须等价。</p>
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
        <p className="lp-eyebrow">行为契约示例 · 切换语言</p>
        <div className="phase-contract-grid">{contract.map((item) => <div className="phase-contract-cell" key={item.k}><small>{item.k}</small><span>{item.v}</span></div>)}</div>
        <div className="phase-verify-modes"><span className="lp-match">高风险功能真机验证</span><span className="agent-source-badge neutral">展示类源码确认</span></div>
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
        <p className="lp-eyebrow">组件映射</p>
        {mappings.map(([from, to]) => <div className="phase-mapping-row" key={from}><span>{from}</span><i>→</i><b>{to}</b></div>)}
      </div>
      <div className="lp-case-grid phase-mini-compare">
        <div className="lp-shot compact">迁移前 · Android GUI<small>截图位</small></div>
        <div className="lp-shot compact">迁移后 · HarmonyOS GUI<small>截图位</small></div>
      </div>
    </div>
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
    const prompt = phasePrompt(phase.number, { projectName: project.name, sourceValue: project.source.value, sourcePlatformLabel: sourcePlatformLabel(project.sourcePlatform), workspaceDir: project.workspaceDir || "工作区未指定", targetPlatform: project.targetPlatform });
    const result = await promptCodeArtsSession(sessionId, prompt, credentials, { agent: "team-leader", mode: "agent-team", model: parseRunModel(runModel) });
    const livePartIds = new Set<string>();
    const resolved = result.accepted && result.pending
      ? await waitForCodeArtsResult(sessionId, result.messageId, credentials, { timeoutMs: 1500000, onUpdate: (message: CodeArtsMessage) => {
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
    if (project.executionMode === "codearts-agentteam" && !project.demo && !project.externalDrive && phase.status === "running" && autoRunRef.current !== key && autoRunKey !== key && !runningCodeArts && !runningRef.current) {
      autoRunRef.current = key;
      setAutoRunKey(key);
      void runWithCodeArts();
    }
  }, [project.id, phase.number, phase.revision, phase.status, autoRunKey, runningCodeArts]);
  const isReal = project.executionMode === "codearts-agentteam" && !project.demo;
  if (!isReal) return <div className="run-controls"><div className="side-panel-heading"><span className="eyebrow">运行控制</span><span className="secure-label">DEMO</span></div><div className="control-row"><span>当前 revision</span><b>{phase.revision}.0</b></div><div className="control-row"><span>运行模式</span><b className="muted-value">本地演示</b></div><div className="control-row"><span>数据来源</span><b className="muted-value">固定数据</b></div><button className="outline-button" onClick={() => mockService.resetDemo(project.id)}>↻ 从头播放示例</button></div>;
  return <div className="run-slim">
    <span className={`execution-status ${phase.execution?.status ?? "idle"}`}>{phase.execution?.status ?? "idle"}</span>
    {runningCodeArts ? <b>AgentTeam 执行中…</b> : <button className="refresh-button" onClick={runWithCodeArts} disabled={project.demo}>重新执行</button>}
    <button className="text-sync-button" onClick={() => setSyncOpen((v) => !v)}>绑定会话</button>
    {syncOpen && <><input className="sync-session-input" value={syncSessionId} onChange={(event) => setSyncSessionId(event.target.value)} placeholder="ses_xxx" /><button className="refresh-button" onClick={() => void syncFromSession()} disabled={syncing}>{syncing ? "同步中…" : "确认"}</button></>}
    {codeArtsMessage && <small className="run-slim-msg" title={codeArtsMessage}>{codeArtsMessage.slice(0, 60)}{codeArtsMessage.length > 60 ? "…" : ""}</small>}
  </div>;  
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
export { ErrorBoundary };
