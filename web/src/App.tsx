import React, { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, Route, Routes, useNavigate, useParams } from "react-router-dom";
import type { Artifact, EmulatorFrame, EmulatorStream, Feature, Phase, PhaseNumber, Project, ProjectInput, Review } from "./types";
import { mockService } from "./mockService";
import { checkCodeArts, createCodeArtsSession, loadCodeArtsCredentials, promptCodeArtsSession, saveCodeArtsCredentials, waitForCodeArtsResult, type CodeArtsConnection, type CodeArtsCredentials, type CodeArtsMessage, type CodeArtsRunResult } from "./codearts";

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

const demoAndroidFrames: EmulatorFrame[] = [
  { id: "android-home", title: "质检工作台", subtitle: "今日任务 12 个", accent: "#39d2a8", detail: "选择图片开始一次新的质检任务", metric: "12" },
  { id: "android-import", title: "导入质检图片", subtitle: "支持 JPG / PNG", accent: "#7c8cff", detail: "正在读取生产线样本_0428.png" },
  { id: "android-running", title: "AI 缺陷检测", subtitle: "模型推理中 · 68%", accent: "#ffb454", detail: "正在扫描图像中的边缘与表面纹理", metric: "68%" },
  { id: "android-result", title: "检测完成", subtitle: "发现 2 个疑似缺陷", accent: "#ff7b82", detail: "缺陷类型：划痕、边缘缺口", metric: "02" },
  { id: "android-history", title: "历史记录", subtitle: "最近 7 天", accent: "#39d2a8", detail: "任务 #QC-0428 已归档" }
];

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
        <Route path="/codearts-test" element={<CodeArtsTestPage />} />
        <Route path="/projects/new" element={<LiveNewProjectPage />} />
        <Route path="/projects/:id" element={<LiveProjectPage />} />
        <Route path="/projects/:id/report" element={<ReportPage />} />
        <Route path="/projects/:id/delivery" element={<DeliveryPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
    <Link to="/codearts-test" className="global-codearts-test-link">⌁ CodeArts 实测</Link>
    </>
  );
}

function AppShell() {
  const [projects, setProjects] = useState<Project[]>(() => mockService.listProjects());
  const [codeArtsOpen, setCodeArtsOpen] = useState(false);
  const [codeArtsConnection, setCodeArtsConnection] = useState<CodeArtsConnection | null>(null);
  useEffect(() => mockService.subscribeAll(setProjects), []);
  useEffect(() => {
    checkCodeArts(loadCodeArtsCredentials()).then(setCodeArtsConnection);
  }, []);
  const active = projects.find((project) => project.status === "running" || project.status === "review");
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" to="/">
          <span className="brand-mark">脱</span>
          <span><strong>脱胎换骨</strong><small>国产化迁移工作台</small></span>
        </Link>
        <div className="workspace-label">WORKSPACE <span className="live-dot" /></div>
        <nav className="main-nav">
          <NavLink to="/" end className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}><span>⌂</span>项目总览</NavLink>
          <NavLink to="/projects/new" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}><span>＋</span>新建迁移</NavLink>
          {active && <NavLink to={`/projects/${active.id}`} className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}><span>◌</span>当前工作台</NavLink>}
        </nav>
        <div className="sidebar-section-title">最近项目</div>
        <div className="recent-projects">
          {projects.slice(0, 4).map((project) => (
            <Link key={project.id} to={`/projects/${project.id}`} className="recent-project">
              <span className={`project-dot ${project.status}`} />
              <span><b>{project.name}</b><small>{project.source.type === "github" ? "GitHub 源码" : "ZIP 源码"}</small></span>
            </Link>
          ))}
        </div>
        <div className="sidebar-footer">
          <button className="environment-card environment-button" onClick={() => setCodeArtsOpen(true)}><span className={`pulse-icon ${codeArtsConnection?.connected ? "connected" : ""}`}>✦</span><div><b>{codeArtsConnection?.connected ? "CodeArts Agent" : "演示环境"}</b><small>{codeArtsConnection?.connected ? "本地桥接 · 已连接" : "Mock Service · 可接入 CodeArts"}</small></div><span className={`online-pill ${codeArtsConnection?.connected ? "connected" : ""}`}>{codeArtsConnection?.connected ? "已连接" : "配置"}</span></button>
          <div className="user-chip"><span className="avatar">审</span><span><b>当前审核员</b><small>Demo Workspace</small></span><span className="chevron">⌄</span></div>
        </div>
      </aside>
      <main className="main-content"><div className="demo-banner"><span>✦</span> 演示数据模式 · CodeArts Agent 本地桥接可选接入 <span className="banner-link" onClick={() => setCodeArtsOpen(true)}>{codeArtsConnection?.connected ? "已连接，点击配置 →" : "连接 CodeArts →"}</span></div><div className="page-content"><Outlet /></div></main>
      {codeArtsOpen && <CodeArtsConnectDialog initial={loadCodeArtsCredentials()} onClose={() => setCodeArtsOpen(false)} onConnected={(value) => { setCodeArtsConnection(value); setCodeArtsOpen(false); }} />}
    </div>
  );
}

function LiveAppShell() {
  const [projects, setProjects] = useState<Project[]>(() => mockService.listProjects());
  const [connection, setConnection] = useState<CodeArtsConnection | null>(null);
  const [codeArtsOpen, setCodeArtsOpen] = useState(false);
  useEffect(() => mockService.subscribeAll(setProjects), []);
  useEffect(() => { checkCodeArts(loadCodeArtsCredentials()).then(setConnection); }, []);
  const active = projects.find((project) => project.status === "running" || project.status === "review");
  return <div className="app-shell"><aside className="sidebar"><Link className="brand" to="/"><span className="brand-mark">脱</span><span><strong>脱胎换骨</strong><small>国产化迁移工作台</small></span></Link><div className="workspace-label">WORKSPACE <span className="live-dot" /></div><nav className="main-nav"><NavLink to="/" end className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}><span>◈</span>项目总览</NavLink><NavLink to="/projects/new" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}><span>＋</span>新建迁移</NavLink>{active && <NavLink to={`/projects/${active.id}`} className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}><span>▣</span>当前工作台</NavLink>}</nav><div className="sidebar-section-title">最近项目</div><div className="recent-projects">{projects.slice(0, 4).map((project) => <Link key={project.id} to={`/projects/${project.id}`} className="recent-project"><span className={`project-dot ${project.status}`} /><span><b>{project.name}</b><small>{project.source.type === "github" ? "GitHub 源码" : "ZIP 源码"}</small></span></Link>)}</div><div className="sidebar-footer"><button className="environment-card environment-button" onClick={() => setCodeArtsOpen(true)}><span className={`pulse-icon ${connection?.connected ? "connected" : ""}`}>✦</span><div><b>{connection?.connected ? "CodeArts Agent" : "CodeArts 未连接"}</b><small>{connection?.connected ? "本地桥接 · 已连接" : "点击配置本地服务"}</small></div><span className={`online-pill ${connection?.connected ? "connected" : ""}`}>{connection?.connected ? "在线" : "配置"}</span></button><div className="user-chip"><span className="avatar">审</span><span><b>当前审核员</b><small>Local Workspace</small></span></div></div></aside><main className="main-content"><div className={`demo-banner ${connection?.connected ? "live-banner" : ""}`}><span>✦</span>{connection?.connected ? "真实执行模式 · CodeArts Space / AgentTeam" : "CodeArts Agent 未连接 · 新任务将无法启动真实推理"}<span className="banner-link" onClick={() => setCodeArtsOpen(true)}>{connection?.connected ? "查看连接状态 →" : "连接 CodeArts →"}</span></div><div className="page-content"><Outlet /></div></main>{codeArtsOpen && <CodeArtsConnectDialog initial={loadCodeArtsCredentials()} onClose={() => setCodeArtsOpen(false)} onConnected={(value) => { setConnection(value); setCodeArtsOpen(false); }} />}</div>;
}

function CodeArtsTestPage() {
  const [credentials, setCredentials] = useState<CodeArtsCredentials>(() => loadCodeArtsCredentials());
  const [instruction, setInstruction] = useState("请回复 CODEARTS_CONNECTION_OK，并用一句话说明你当前使用的执行模式。不要修改任何文件。");
  const [status, setStatus] = useState<"idle" | "checking" | "running" | "succeeded" | "failed">("idle");
  const [health, setHealth] = useState<CodeArtsConnection | null>(null);
  const [session, setSession] = useState<CodeArtsRunResult | null>(null);
  const [result, setResult] = useState<CodeArtsRunResult | null>(null);
  const [messages, setMessages] = useState<CodeArtsMessage[]>([]);
  const [error, setError] = useState("");
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const runningRef = useRef(false);

  const runTest = async () => {
    if (runningRef.current || !instruction.trim()) return;
    runningRef.current = true;
    const started = Date.now();
    setStartedAt(new Date(started).toISOString());
    setElapsed(null);
    setError("");
    setHealth(null);
    setSession(null);
    setResult(null);
    setMessages([]);
    setStatus("checking");
    try {
      const checked = await checkCodeArts(credentials);
      setHealth(checked);
      if (!checked.connected) {
        setStatus("failed");
        setError(checked.message);
        return;
      }
      saveCodeArtsCredentials(credentials);
      setStatus("running");
      const created = await createCodeArtsSession(`脱胎换骨 · 临时连接测试 · ${new Date(started).toLocaleTimeString("zh-CN")}`, credentials);
      setSession(created);
      if (!created.accepted || !created.session?.id) {
        setStatus("failed");
        setError(created.message);
        return;
      }
      const submitted = await promptCodeArtsSession(created.session.id, instruction.trim(), credentials, { agent: "team-leader", mode: "agent-team" });
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
  const statusLabel = status === "idle" ? "尚未测试" : status === "checking" ? "健康检查中" : status === "running" ? "真实推理中" : status === "succeeded" ? "测试通过" : "测试失败";
  return <div className="codearts-test-page">
    <div className="page-heading"><div><p className="eyebrow">TEMPORARY DIAGNOSTICS / REAL REQUEST</p><h1>CodeArts 实测</h1><p className="heading-subtitle">输入一条指令，直接验证本机 CodeArts AgentTeam 是否真的返回了 AI 结果。</p></div><Link to="/" className="ghost-button">← 返回项目总览</Link></div>
    <div className="codearts-test-grid">
      <section className="codearts-test-form">
        <div className="card-title-row"><div><span className="section-index">LIVE</span><h2>发送真实测试指令</h2></div><span className={`test-status-pill ${status}`}>{statusLabel}</span></div>
        <div className="codearts-test-warning"><strong>这不是 Mock 测试</strong><span>点击后会调用本地 AgentKernel，创建独立测试会话，并发送 AgentTeam 请求。不会读取或修改迁移项目。</span></div>
        <label className="field-label">CodeArts 用户名<input value={credentials.username} onChange={(event) => setCredentials({ ...credentials, username: event.target.value })} placeholder="codearts" /></label>
        <label className="field-label">本地服务密码（可选）<input type="password" value={credentials.password} onChange={(event) => setCredentials({ ...credentials, password: event.target.value })} placeholder="留空则使用本机 Agent 凭据" /></label>
        <label className="field-label">发送给 AgentTeam 的指令<textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} rows={6} placeholder="输入你希望 CodeArts 回答的内容" /></label>
        <button className="primary-button wide codearts-test-submit" onClick={runTest} disabled={status === "checking" || status === "running" || !instruction.trim()}>{status === "checking" ? "检查 CodeArts 服务…" : status === "running" ? "等待 CodeArts AI 回复…" : "发送并获取真实回复"}<span>→</span></button>
        <p className="form-hint">请求参数固定为 <code>agent: team-leader</code>、<code>mode: agent-team</code>；页面展示的 session/message 均来自接口响应。</p>
      </section>
      <section className="codearts-test-evidence">
        <div className="card-title-row"><div><span className="section-index">EVIDENCE</span><h2>连接与推理证据</h2></div><span className="evidence-live-dot" /></div>
        <div className="evidence-check-list">
          <div className={health?.connected ? "evidence-check passed" : "evidence-check"}><span>{health?.connected ? "✓" : "1"}</span><div><b>AgentKernel 健康检查</b><small>{health ? `${health.message} · HTTP ${health.status}` : "尚未请求 /api/codearts/global/health"}</small></div></div>
          <div className={session?.accepted ? "evidence-check passed" : "evidence-check"}><span>{session?.accepted ? "✓" : "2"}</span><div><b>独立测试会话</b><small>{session?.session?.id ? session.session.id : "尚未创建 /api/codearts/session"}</small></div></div>
          <div className={result?.messageId ? "evidence-check passed" : "evidence-check"}><span>{result?.messageId ? "✓" : "3"}</span><div><b>AgentTeam 异步请求</b><small>{result?.messageId ? `messageID ${result.messageId}` : "尚未发送 prompt_async"}</small></div></div>
          <div className={status === "succeeded" ? "evidence-check passed" : "evidence-check"}><span>{status === "succeeded" ? "✓" : "4"}</span><div><b>AI 回复</b><small>{messages.length ? `已收到 ${messages.length} 条会话消息` : "等待 CodeArts 返回 assistant message"}</small></div></div>
        </div>
        {(error || result?.message) && status === "failed" && <div className="codearts-test-error">{error || result?.message}</div>}
        {responseText && <div className="codearts-response"><div className="response-heading"><span>CODEARTS RESPONSE</span><small>真实 assistant 输出</small></div><pre>{responseText}</pre></div>}
        {!responseText && status === "running" && <div className="codearts-response waiting"><div className="response-heading"><span>WAITING FOR ASSISTANT</span><small>正在轮询真实会话消息</small></div><div className="test-loader"><i /><i /><i /></div></div>}
        <div className="codearts-test-meta"><span>模式 <b>CodeArts Space / AgentTeam</b></span><span>Agent <b>team-leader</b></span><span>耗时 <b>{elapsed === null ? "—" : `${(elapsed / 1000).toFixed(1)}s`}</b></span>{startedAt && <span>开始 <b>{formatTime(startedAt)}</b></span>}</div>
      </section>
    </div>
  </div>;
}

function HomePage() {
  const projects = mockService.listProjects();
  const running = projects.filter((project) => project.status === "running").length;
  const completed = projects.filter((project) => project.status === "completed").length;
  return (
    <div className="home-page">
      <div className="page-heading home-heading"><div><p className="eyebrow">MIGRATION CONTROL CENTER / 2026</p><h1>项目总览 <span className="heading-line" /></h1><p className="heading-subtitle">让平台可换，功能语义不丢。</p></div><Link to="/projects/new" className="primary-button"><span>＋</span> 新建迁移任务</Link></div>
      <section className="hero-card">
        <div className="hero-copy"><span className="hero-kicker">脱胎换骨 · V0.1 PREVIEW</span><h2>把一次迁移，变成一条<br /><em>可验证的证据链。</em></h2><p>从源项目语义重建，到双端执行对照，四个阶段，每一步都可回放、可审核、可交付。</p><Link to="/projects/demo-qc-001" className="text-link">查看示例迁移 <span>→</span></Link></div>
        <div className="hero-visual"><div className="orb orb-one" /><div className="orb orb-two" /><div className="hero-grid" /><div className="hero-flow"><span>源代码</span><i>→</i><span className="flow-accent">语义</span><i>→</i><span>新平台</span></div><div className="hero-stamp">FUNCTION<br /><b>INVARIANT</b></div></div>
      </section>
      <div className="stats-grid"><StatCard label="进行中的迁移" value={String(running).padStart(2, "0")} change="实时工作流" accent="mint" icon="◌" /><StatCard label="已完成交付" value={String(completed).padStart(2, "0")} change="可下载" accent="blue" icon="✓" /><StatCard label="平均一致性" value="94.2" unit="%" change="+6.8% 本月" accent="amber" icon="⌁" /><StatCard label="已固化证据" value="128" unit="项" change="截图 · 轨迹 · 报告" accent="violet" icon="▣" /></div>
      <div className="section-heading"><div><p className="eyebrow">RECENT MIGRATIONS</p><h2>最近迁移任务</h2></div><Link to="/projects/new" className="subtle-link">查看全部 <span>→</span></Link></div>
      <div className="project-list">{projects.map((project) => <ProjectRow key={project.id} project={project} />)}</div>
      <p className="mock-note"><span>ⓘ</span> 当前展示为可交互演示数据。创建任务后，Phase 1 会自动开始播放。</p>
    </div>
  );
}

function StatCard({ label, value, unit, change, accent, icon }: { label: string; value: string; unit?: string; change: string; accent: string; icon: string }) {
  return <div className={`stat-card stat-${accent}`}><div className="stat-icon">{icon}</div><p>{label}</p><div className="stat-value">{value}<small>{unit}</small></div><span className="stat-change">{change}</span></div>;
}

function ProjectRow({ project }: { project: Project }) {
  const current = project.phases.find((phase) => phase.number === project.currentPhase);
  const completedPhases = project.phases.filter((phase) => phase.status === "approved" || phase.status === "completed").length;
  return <Link to={`/projects/${project.id}`} className="project-row"><div className="project-row-title"><span className={`project-status-dot ${project.status}`} /><div><h3>{project.name}</h3><p>{project.source.type === "github" ? project.source.value : project.source.value || "Android project.zip"}</p></div></div><div className="project-row-progress"><span>PHASE {String(project.currentPhase).padStart(2, "0")}</span><b>{current?.shortTitle}</b><div className="mini-progress"><i style={{ width: `${current?.progress ?? 0}%` }} /></div><small>{completedPhases}/4 阶段完成</small></div><div className="project-row-meta"><StatusBadge status={current?.status ?? "pending"} /><span className="row-time">{project.demo ? "刚刚" : "今天 14:32"}</span><span className="arrow">→</span></div></Link>;
}

function NewProjectPage() {
  const navigate = useNavigate();
  const [sourceType, setSourceType] = useState<"github" | "zip">("github");
  const [name, setName] = useState("");
  const [sourceValue, setSourceValue] = useState("");
  const [fileName, setFileName] = useState("");
  const [executionMode, setExecutionMode] = useState<"codearts-agentteam" | "demo">("codearts-agentteam");
  const [error, setError] = useState("");
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const value = sourceType === "github" ? sourceValue.trim() : fileName;
    if (!name.trim()) return setError("请先填写项目名称");
    if (sourceType === "github" && !/^https?:\/\/(www\.)?github\.com\/.+/.test(value)) return setError("请输入有效的 GitHub 公共仓库链接");
    if (sourceType === "zip" && !/\.zip$/i.test(value)) return setError("请选择 .zip 格式的 Android 项目");
    const project = mockService.createProject({ name: name.trim(), sourceType, sourceValue: value, executionMode });
    navigate(`/projects/${project.id}`);
  };
  return <div className="new-project-page"><div className="page-heading"><div><p className="eyebrow">NEW MIGRATION / SOURCE INTAKE</p><h1>新建迁移任务</h1><p className="heading-subtitle">先把源项目交给工作台，语义分析会从这里开始。</p></div><Link to="/" className="ghost-button">← 返回项目总览</Link></div><div className="new-project-layout"><form className="intake-card" onSubmit={submit}><div className="card-title-row"><div><span className="section-index">01</span><h2>选择源项目</h2></div><span className="required-note">均为演示输入</span></div><div className="source-toggle"><button type="button" className={sourceType === "github" ? "toggle active" : "toggle"} onClick={() => { setSourceType("github"); setError(""); }}>◖ GitHub 链接</button><button type="button" className={sourceType === "zip" ? "toggle active" : "toggle"} onClick={() => { setSourceType("zip"); setError(""); }}>▣ Android ZIP</button></div>{sourceType === "github" ? <label className="field-label">GitHub 公共仓库链接<input value={sourceValue} onChange={(event) => setSourceValue(event.target.value)} placeholder="https://github.com/example/android-project" /></label> : <label className="file-drop"><input type="file" accept=".zip" onChange={(event) => { const file = event.target.files?.[0]; setFileName(file?.name ?? ""); setError(""); }} /><span className="upload-icon">↑</span><b>{fileName || "点击选择 Android 项目压缩包"}</b><small>{fileName ? "文件已选择，提交后进入演示流程" : "支持 .zip，建议不超过 50 MB"}</small></label>}<div className="field-divider" /><div className="card-title-row compact"><div><span className="section-index">02</span><h2>任务信息</h2></div></div><label className="field-label">迁移项目名称<input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：机器视觉质检助手迁移" /></label>{error && <div className="form-error">! {error}</div>}<button className="primary-button wide" type="submit"><span>✦</span> 创建并开始 Phase 1 <span className="button-arrow">→</span></button><p className="form-hint">创建后会自动播放 Mock Agent Team 事件流，每个阶段结束等待人工审核。</p></form><aside className="intake-aside"><div className="aside-card"><p className="eyebrow">WORKFLOW PREVIEW</p><h3>四步完成一次迁移</h3><div className="preview-steps">{[{n: "01", t: "识胎", d: "源项目语义重建" }, { n: "02", t: "验旧", d: "Android 行为基线" }, { n: "03", t: "换骨", d: "鸿蒙迁移生成" }, { n: "04", t: "验神", d: "功能一致性验证" }].map((step, index) => <div className="preview-step" key={step.n}><span>{step.n}</span><div><b>{step.t}</b><small>{step.d}</small></div>{index < 3 && <i>↓</i>}</div>)}</div></div><div className="aside-tip"><span>ⓘ</span><p>初版使用演示数据，后续可替换为真实 CodeArts、Android 和 HarmonyOS Runner。</p></div></aside></div></div>;
}

function LiveNewProjectPage() {
  const navigate = useNavigate();
  const [sourceType, setSourceType] = useState<"github" | "zip">("github");
  const [sourceValue, setSourceValue] = useState("");
  const [name, setName] = useState("");
  const [executionMode, setExecutionMode] = useState<"codearts-agentteam" | "demo">("codearts-agentteam");
  const [error, setError] = useState("");
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const value = sourceValue.trim();
    if (!name.trim()) return setError("请先填写项目名称");
    if (sourceType === "github" && !/^https?:\/\/(www\.)?github\.com\/.+/.test(value)) return setError("请输入有效的 GitHub 仓库链接");
    if (sourceType === "zip" && !/\.zip$/i.test(value)) return setError("请选择 .zip 格式的 Android 项目");
    const project = mockService.createProject({ name: name.trim(), sourceType, sourceValue: value, executionMode });
    navigate(`/projects/${project.id}`);
  };
  return <div className="new-project-page"><div className="page-heading"><div><p className="eyebrow">NEW MIGRATION / SOURCE INTAKE</p><h1>新建迁移任务</h1><p className="heading-subtitle">输入源项目后，直接启动真实 CodeArts AgentTeam 推理。</p></div><Link to="/" className="ghost-button">← 返回项目总览</Link></div><div className="new-project-layout"><form className="intake-card" onSubmit={submit}><div className="card-title-row"><div><span className="section-index">01</span><h2>选择源项目</h2></div><span className="required-note">必填</span></div><div className="source-toggle"><button type="button" className={sourceType === "github" ? "toggle active" : "toggle"} onClick={() => { setSourceType("github"); setSourceValue(""); setError(""); }}>GitHub 链接</button><button type="button" className={sourceType === "zip" ? "toggle active" : "toggle"} onClick={() => { setSourceType("zip"); setSourceValue(""); setError(""); }}>Android ZIP</button></div>{sourceType === "github" ? <label className="field-label">GitHub 公共仓库链接<input value={sourceValue} onChange={(event) => setSourceValue(event.target.value)} placeholder="https://github.com/example/android-project" /></label> : <label className="file-drop"><input type="file" accept=".zip" onChange={(event) => { setSourceValue(event.target.files?.[0]?.name ?? ""); setError(""); }} /><span className="upload-icon">↑</span><b>{sourceValue || "点击选择 Android 项目压缩包"}</b><small>{sourceValue ? "已选择；真实构建前需上传到 CodeArts 工作目录" : "支持 .zip，建议不超过 50 MB"}</small></label>}<div className="field-divider" /><div className="card-title-row compact"><div><span className="section-index">02</span><h2>任务信息</h2></div></div><label className="field-label">迁移项目名称<input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：机器视觉质检助手迁移" /></label><div className="execution-mode-picker"><div className="mode-picker-heading"><span className="eyebrow">EXECUTION MODE</span><b>选择执行引擎</b></div><button type="button" className={executionMode === "codearts-agentteam" ? "mode-option active" : "mode-option"} onClick={() => setExecutionMode("codearts-agentteam")}><strong>CodeArts Space / AgentTeam</strong><small>真实大模型推理、团队调度和工具执行</small></button><button type="button" className={executionMode === "demo" ? "mode-option active" : "mode-option"} onClick={() => setExecutionMode("demo")}><strong>本地演示</strong><small>仅播放固定数据，不产生真实构建</small></button></div>{error && <div className="form-error">! {error}</div>}<button className="primary-button wide" type="submit">启动迁移 <span className="button-arrow">→</span></button><p className="form-hint">选择 CodeArts AgentTeam 后，Phase 进度只由真实会话结果推进。</p></form><aside className="intake-aside"><div className="aside-card"><p className="eyebrow">LIVE WORKFLOW</p><h3>四阶段真实门禁</h3><div className="preview-steps">{[{n: "01", t: "识胎", d: "源项目语义重建" }, { n: "02", t: "验旧", d: "Android 行为基线" }, { n: "03", t: "换骨", d: "HarmonyOS 迁移生成" }, { n: "04", t: "验神", d: "功能一致性验证" }].map((step, index) => <div className="preview-step" key={step.n}><span>{step.n}</span><div><b>{step.t}</b><small>{step.d}</small></div>{index < 3 && <i>↓</i>}</div>)}</div></div><div className="aside-tip"><span>ⓘ</span><p>真实模式要求本机 CodeArts Agent 已登录并可用。GitHub 项目会由 Agent 在工作目录检出；ZIP 上传接口将在后续版本补齐。</p></div></aside></div></div>;
}

function ProjectPage() {
  const { id } = useParams();
  const project = useProject(id);
  const [selectedPhase, setSelectedPhase] = useState<PhaseNumber>(project?.currentPhase ?? 1);
  const [reviewOpen, setReviewOpen] = useState(false);
  const navigate = useNavigate();
  useEffect(() => { if (project?.currentPhase) setSelectedPhase(project.currentPhase); }, [project?.currentPhase]);
  if (!project) return <NotFound />;
  const selected = project.phases.find((phase) => phase.number === selectedPhase) ?? project.phases[0];
  const canReview = selected.status === "review_required";
  const performReview = (review: Review) => { mockService.reviewPhase(project.id, selected.number, review); setReviewOpen(false); };
  return <div className="workspace-page"><div className="workspace-header"><div className="breadcrumb"><Link to="/">项目总览</Link><span>/</span><b>{project.name}</b></div><div className="workspace-actions"><span className="demo-tag">DEMO DATA</span><Link to={`/projects/${project.id}/report`} className="ghost-button small">查看报告</Link><Link to={`/projects/${project.id}/delivery`} className="primary-button small">交付中心 <span>→</span></Link></div></div><div className="workspace-title"><div><p className="eyebrow">MIGRATION RUN / {project.id.toUpperCase()}</p><h1>{project.name}</h1><p className="heading-subtitle">{project.source.type === "github" ? "GitHub 公共仓库" : "Android 项目压缩包"} · 创建于 {new Date(project.createdAt).toLocaleDateString("zh-CN")}</p></div><div className="run-health"><span className="live-dot" /> <b>{project.status === "completed" ? "迁移已完成" : "工作流运行中"}</b><small>revision {selected.revision}.0</small></div></div><PhaseRail phases={project.phases} selected={selectedPhase} onSelect={setSelectedPhase} /><div className="workspace-grid"><aside className="workspace-left"><FeatureSidebar features={project.features} phase={selected} /><ArtifactList artifacts={selected.artifacts} /></aside><section className="workspace-center"><PhaseContent project={project} phase={selected} /><div className="review-bar"><div><span className={`review-dot ${canReview ? "active" : ""}`} /><div><b>{canReview ? "本阶段等待人工审核" : selected.status === "running" ? "Agent Team 正在执行" : statusLabels[selected.status]}</b><small>{canReview ? "确认交付物后才能进入下一阶段" : "所有阶段状态和事件均来自 Mock Service"}</small></div></div><div className="review-actions">{selected.status === "running" && <><button className="icon-button" onClick={() => selected.paused ? mockService.resumePhase(project.id, selected.number) : mockService.pausePhase(project.id, selected.number)}>{selected.paused ? "▶ 继续" : "Ⅱ 暂停"}</button><button className="icon-button" onClick={() => mockService.skipPhase(project.id, selected.number)}>跳过等待</button></>}{canReview && <button className="primary-button" onClick={() => setReviewOpen(true)}>打开审核 <span>→</span></button>}{selected.status === "approved" || selected.status === "completed" ? <button className="icon-button" onClick={() => mockService.restartPhase(project.id, selected.number)}>↻ 重新演示</button> : null}</div></div></section><aside className="workspace-right"><AgentTimeline phase={selected} /><RunControls project={project} phase={selected} /></aside></div>{reviewOpen && <ReviewDialog phase={selected} onClose={() => setReviewOpen(false)} onSubmit={performReview} />}</div>;
}

function LiveProjectPage() {
  const { id } = useParams();
  const project = useProject(id);
  const [selectedPhase, setSelectedPhase] = useState<PhaseNumber>(project?.currentPhase ?? 1);
  const [reviewOpen, setReviewOpen] = useState(false);
  useEffect(() => { if (project?.currentPhase) setSelectedPhase(project.currentPhase); }, [project?.currentPhase]);
  if (!project) return <NotFound />;
  const selected = project.phases.find((phase) => phase.number === selectedPhase) ?? project.phases[0];
  const canReview = selected.status === "review_required";
  const real = project.executionMode === "codearts-agentteam" && !project.demo;
  const performReview = (review: Review) => { mockService.reviewPhase(project.id, selected.number, review); setReviewOpen(false); };
  return <div className="workspace-page"><div className="workspace-header"><div className="breadcrumb"><Link to="/">项目总览</Link><span>/</span><b>{project.name}</b></div><div className="workspace-actions"><span className={real ? "live-tag" : "demo-tag"}>{real ? "LIVE · CODEARTS" : "DEMO DATA"}</span><Link to={`/projects/${project.id}/report`} className="ghost-button small">查看报告</Link><Link to={`/projects/${project.id}/delivery`} className="primary-button small">交付中心 <span>→</span></Link></div></div><div className="workspace-title"><div><p className="eyebrow">MIGRATION RUN / {project.id.toUpperCase()}</p><h1>{project.name}</h1><p className="heading-subtitle">{project.source.type === "github" ? "GitHub 源码" : "Android ZIP"} · {real ? "CodeArts Space / AgentTeam" : "本地演示"}</p></div><div className="run-health"><span className="live-dot" /><b>{project.status === "completed" ? "迁移已完成" : real ? "真实工作流运行中" : "演示工作流"}</b><small>revision {selected.revision}.0</small></div></div><PhaseRail phases={project.phases} selected={selectedPhase} onSelect={setSelectedPhase} /><div className="workspace-grid"><aside className="workspace-left"><FeatureSidebar features={project.features} phase={selected} /><ArtifactList artifacts={selected.artifacts} /></aside><section className="workspace-center"><PhaseContent project={project} phase={selected} /><div className="review-bar"><div><span className={`review-dot ${canReview ? "active" : ""}`} /><div><b>{canReview ? "本阶段等待人工审核" : selected.status === "running" ? (real ? "CodeArts AgentTeam 正在执行" : "演示工作流正在执行") : statusLabels[selected.status]}</b><small>{canReview ? "确认真实会话结果后才能进入下一阶段" : real ? "状态由 CodeArts AgentTeam 会话结果驱动" : "本项目使用本地演示数据"}</small></div></div><div className="review-actions">{selected.status === "running" && !real && <><button className="icon-button" onClick={() => selected.paused ? mockService.resumePhase(project.id, selected.number) : mockService.pausePhase(project.id, selected.number)}>{selected.paused ? "▶ 继续" : "Ⅱ 暂停"}</button><button className="icon-button" onClick={() => mockService.skipPhase(project.id, selected.number)}>跳过等待</button></>}{canReview && <button className="primary-button" onClick={() => setReviewOpen(true)}>打开审核 <span>→</span></button>}{(selected.status === "approved" || selected.status === "completed") && !real && <button className="icon-button" onClick={() => mockService.restartPhase(project.id, selected.number)}>↻ 重新演示</button>}</div></div></section><aside className="workspace-right"><AgentTimeline phase={selected} /><RunControls project={project} phase={selected} /></aside></div>{reviewOpen && <ReviewDialog phase={selected} onClose={() => setReviewOpen(false)} onSubmit={performReview} />}</div>;
}

function PhaseRail({ phases, selected, onSelect }: { phases: Phase[]; selected: PhaseNumber; onSelect: (phase: PhaseNumber) => void }) {
  return <div className="phase-rail">{phases.map((phase, index) => <button key={phase.number} className={`phase-rail-item ${selected === phase.number ? "selected" : ""} ${statusClasses[phase.status]}`} onClick={() => onSelect(phase.number)}><span className="phase-number">{phase.code}</span><span className="phase-rail-text"><b>{phase.shortTitle}</b><small>{phase.title.split("·")[1]?.trim()}</small></span><span className="phase-rail-status">{phase.status === "running" ? <span className="spinner" /> : phase.status === "approved" || phase.status === "completed" ? "✓" : phase.status === "review_required" ? "!" : "·"}</span>{index < phases.length - 1 && <i className="rail-connector" />}</button>)}</div>;
}

function FeatureSidebar({ features, phase }: { features: Feature[]; phase: Phase }) {
  return <div className="side-panel feature-panel"><div className="side-panel-heading"><span className="eyebrow">FEATURE MAP</span><span className="count-badge">{features.length} 项</span></div><div className="coverage-meter"><div className="coverage-ring"><strong>{Math.round((features.filter((item) => item.status === "covered").length / features.length) * 100)}<small>%</small></strong></div><div><b>功能覆盖度</b><small>{features.filter((item) => item.status === "covered").length} 项已确认</small></div></div><div className="feature-list">{features.map((feature) => <div className="feature-item" key={feature.id}><span className={`feature-status ${feature.status}`} /> <span><b>{feature.name}</b><small>{feature.description}</small></span><span className="feature-arrow">›</span></div>)}</div><div className="sidebar-context"><span>⌁</span><p>当前上下文<br /><b>Phase {phase.number} · {phase.shortTitle}</b></p></div></div>;
}

function ArtifactList({ artifacts }: { artifacts: Artifact[] }) {
  return <div className="side-panel artifact-panel"><div className="side-panel-heading"><span className="eyebrow">PHASE ARTIFACTS</span><span className="count-badge">{artifacts.length}</span></div>{artifacts.map((artifact) => <div className="artifact-mini" key={artifact.id}><span className={`artifact-icon artifact-${artifact.kind}`}>{artifact.kind === "code" ? "‹›" : artifact.kind === "screenshot" ? "▧" : artifact.kind === "report" ? "≡" : artifact.kind === "build" ? "⌁" : "◇"}</span><span><b>{artifact.name}</b><small>{artifact.size} · {artifact.status === "review" ? "待审核" : "已生成"}</small></span><span className="artifact-more">···</span></div>)}</div>;
}

function PhaseContent({ project, phase }: { project: Project; phase: Phase }) {
  if (project.executionMode === "codearts-agentteam" && !project.demo) return <RealPhaseContent project={project} phase={phase} />;
  if (phase.number === 1) return <PhaseOne phase={phase} features={project.features} />;
  if (phase.number === 2) return <PhaseTwo phase={phase} />;
  if (phase.number === 3) return <PhaseThree phase={phase} />;
  return <PhaseFour project={project} phase={phase} />;
}

function RealPhaseContent({ project, phase }: { project: Project; phase: Phase }) {
  const eyebrow = phase.number === 1 ? "SEMANTIC RECONSTRUCTION / PHASE 01" : phase.number === 2 ? "ANDROID BASELINE / PHASE 02" : phase.number === 3 ? "HARMONYOS GENERATION / PHASE 03" : "FUNCTIONAL PARITY / PHASE 04";
  const execution = phase.execution;
  const response = execution?.response?.trim();
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow={eyebrow} /><div className="real-evidence-card"><div className="real-evidence-heading"><div><span className="eyebrow">REAL CODEARTS EVIDENCE</span><h3>{execution?.status === "succeeded" ? "AgentTeam 已返回真实结果" : execution?.status === "failed" ? "AgentTeam 执行失败" : "等待 AgentTeam 真实执行"}</h3></div><span className={`execution-status ${execution?.status ?? "idle"}`}>{execution?.status ?? "idle"}</span></div><div className="real-evidence-meta"><span>模式 <b>CodeArts Space / AgentTeam</b></span><span>Agent <b>{execution?.agent ?? "team-leader"}</b></span><span>Session <code>{execution?.sessionId ?? "尚未创建"}</code></span></div>{execution?.error && <div className="real-error">{execution.error}</div>}{response && <pre className="real-response">{response}</pre>}{!response && !execution?.error && <div className="real-waiting">页面不会生成固定分析、构建日志或一致性分数。CodeArts 返回真实消息后，这里才会显示可审核证据。</div>}</div>{phase.number === 2 && phase.emulator && <div className="runner-placeholder"><div><span className="eyebrow">ANDROID RUNNER</span><h3>等待真实 Android 模拟器</h3><p>当前只保留 Runner 接口位置；不会用本地帧流冒充真实执行。</p></div><EmulatorPanel stream={phase.emulator} /></div>}{phase.number === 4 && <div className="runner-placeholder"><div><span className="eyebrow">HARMONYOS RUNNER</span><h3>等待真实 HarmonyOS 模拟器</h3><p>一致性判别将在真实鸿蒙运行轨迹和 Android 基线都返回后生成。</p></div></div>}</div>;
}

function PhaseHeader({ phase, eyebrow }: { phase: Phase; eyebrow: string }) {
  return <div className="phase-header"><div><p className="eyebrow">{eyebrow} <span className="phase-live-label">{phase.status === "running" ? "· LIVE" : phase.status === "review_required" ? "· REVIEW" : ""}</span></p><h2>{phase.title}</h2><p>{phase.description}</p></div><div className="phase-progress"><strong>{String(phase.progress).padStart(2, "0")}<small>%</small></strong><span>阶段进度</span></div></div>;
}

function PhaseOne({ phase, features }: { phase: Phase; features: Feature[] }) {
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow="SEMANTIC RECONSTRUCTION / PHASE 01" /><div className="analysis-grid"><div className="analysis-card analysis-highlight"><div className="card-topline"><span className="card-label">SOURCE PROJECT HEALTH</span><span className="health-pill">GOOD</span></div><div className="health-score">86<span>/100</span></div><p>源项目结构清晰，已识别关键迁移边界。</p><div className="health-bars"><span><i style={{ width: "92%" }} /><small>可构建性</small></span><span><i style={{ width: "82%" }} /><small>依赖可替代性</small></span><span><i style={{ width: "76%" }} /><small>隐式逻辑可见度</small></span></div></div><div className="analysis-card"><div className="card-topline"><span className="card-label">SEMANTIC GRAPH</span><span className="muted-value">86 files</span></div><div className="graph-visual"><span className="graph-node node-main">业务入口</span><span className="graph-node node-a">图片导入</span><span className="graph-node node-b">检测服务</span><span className="graph-node node-c">历史记录</span><i className="graph-line line-a" /><i className="graph-line line-b" /><i className="graph-line line-c" /></div><p>Codebase 索引已完成，功能节点之间的调用关系已建立。</p></div><div className="analysis-card risk-card"><div className="card-topline"><span className="card-label">MIGRATION RISKS</span><span className="risk-count">3 项</span></div><div className="risk-list"><span><i>!</i><b>视觉模型字段</b><small>需要跨端字段映射</small></span><span><i>!</i><b>权限申请流程</b><small>目标平台 API 不同</small></span><span><i>·</i><b>历史数据格式</b><small>建议保留兼容层</small></span></div></div></div><div className="data-table-card"><div className="card-title-row"><div><span className="section-index">FEATURE CONTRACT</span><h3>功能语义契约</h3></div><span className="table-note">Agent Team 自动生成 · revision {phase.revision}.0</span></div><div className="feature-table"><div className="table-row table-head"><span>功能</span><span>语义说明</span><span>风险级别</span><span>状态</span></div>{features.map((feature) => <div className="table-row" key={feature.id}><span><b>{feature.name}</b></span><span>{feature.description}</span><span><span className={`risk-label ${feature.status}`}>{feature.status === "covered" ? "低" : feature.status === "partial" ? "中" : "高"}</span></span><span><span className={`table-status ${feature.status}`}>{feature.status === "covered" ? "已覆盖" : feature.status === "partial" ? "需复核" : "待分析"}</span></span></div>)}</div></div></div>;
}

function PhaseTwo({ phase }: { phase: Phase }) {
  const stream = phase.emulator ?? { platform: "android" as const, status: "live" as const, frames: demoAndroidFrames, currentFrame: 0, currentStep: "执行测试用例", streamType: "mock" as const };
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow="ANDROID BASELINE / PHASE 02" /><div className="execution-layout"><EmulatorPanel stream={stream} /><div className="test-run-card"><div className="card-topline"><span className="card-label">TEST CONTRACTS</span><span className="live-tag">● RUNNING</span></div><div className="test-summary"><strong>05</strong><span>条核心用例<br /><small>已采集执行证据</small></span></div><div className="test-list"><TestItem code="TC-001" name="项目启动与首页加载" state="passed" time="1.2s" /><TestItem code="TC-002" name="导入质检图片" state="passed" time="3.8s" /><TestItem code="TC-003" name="完成缺陷检测" state="running" time="进行中" /><TestItem code="TC-004" name="查看结果详情" state="pending" time="排队中" /><TestItem code="TC-005" name="查询历史记录" state="pending" time="排队中" /></div><div className="trace-footer"><span>↗</span> 已保存 3 个执行轨迹快照 <b>查看轨迹 →</b></div></div></div><div className="evidence-strip"><div><span className="eyebrow">CAPTURED EVIDENCE</span><h3>Android 行为基线</h3></div><EvidenceThumb title="首页" accent="#39d2a8" /><EvidenceThumb title="导入图片" accent="#7c8cff" /><EvidenceThumb title="检测结果" accent="#ff7b82" /><div className="evidence-more">+2<br /><small>查看全部</small></div></div></div>;
}

function TestItem({ code, name, state, time }: { code: string; name: string; state: "passed" | "running" | "pending"; time: string }) {
  return <div className="test-item"><span className={`test-state ${state}`}>{state === "passed" ? "✓" : state === "running" ? "◌" : "·"}</span><span><b>{code}</b><small>{name}</small></span><em>{time}</em></div>;
}

function EvidenceThumb({ title, accent }: { title: string; accent: string }) {
  return <div className="evidence-thumb"><div className="thumb-screen" style={{ "--thumb-accent": accent } as React.CSSProperties}><span /><i /><b /></div><small>{title}</small></div>;
}

function PhaseThree({ phase }: { phase: Phase }) {
  const agents = [{ name: "Harmony 架构 Agent", role: "ArkUI / 状态模型", state: "working", initials: "架" }, { name: "UI 迁移 Agent", role: "页面和资源", state: "done", initials: "UI" }, { name: "API 迁移 Agent", role: "平台能力映射", state: "done", initials: "API" }, { name: "Repair Agent", role: "编译问题修复", state: "working", initials: "修" }];
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow="HARMONYOS GENERATION / PHASE 03" /><div className="migration-overview"><div className="codebase-card"><div className="card-topline"><span className="card-label">HARMONYOS PROJECT</span><span className="live-tag">ARKTS</span></div><div className="codebase-layout"><div className="file-tree"><FileTreeLine name="harmony-project" folder depth={0} /><FileTreeLine name="entry" folder depth={1} open /><FileTreeLine name="pages" folder depth={2} open /><FileTreeLine name="Index.ets" depth={3} active /><FileTreeLine name="Result.ets" depth={3} /><FileTreeLine name="History.ets" depth={3} /><FileTreeLine name="services" folder depth={2} /><FileTreeLine name="DetectionService.ets" depth={3} /><FileTreeLine name="module.json5" depth={1} /></div><div className="code-preview"><div className="code-tabs"><span className="active">Index.ets</span><span>DetectionService.ets</span></div><pre><code><i>01</i> <b>struct</b> <strong>Index</strong> &#123;{`\n`}<i>02</i>   <b>@State</b> isRunning: <strong>boolean</strong> = <strong>false</strong>{`\n`}<i>03</i>   <b>build</b>() &#123;{`\n`}<i>04</i>     <strong>Column</strong>() &#123;{`\n`}<i>05</i>       <strong>Text</strong>(<em>"质检工作台"</em>){`\n`}<i>06</i>       <strong>UploadCard</strong>(&#123;{`\n`}<i>07</i>         onStart: () =&gt; <strong>this</strong>.runDetection(){`\n`}<i>08</i>       &#125;){`\n`}<i>09</i>     &#125;{`\n`}<i>10</i>   &#125;{`\n`}<i>11</i> &#125;</code></pre><span className="code-cursor" /></div></div><div className="build-status"><span className="spinner" /> hvigor assembleHap <b>编译中</b><span className="build-time">01:42</span></div></div><div className="agent-team-card"><div className="card-topline"><span className="card-label">AGENT TEAM</span><span className="muted-value">4 teammates</span></div><div className="agent-member-list">{agents.map((agent) => <div className="agent-member" key={agent.name}><span className={`member-avatar ${agent.state}`}>{agent.initials}</span><span><b>{agent.name}</b><small>{agent.role}</small></span><span className={`member-state ${agent.state}`}>{agent.state === "done" ? "完成" : "工作中"}</span></div>)}</div><div className="agent-quote"><span>“</span><p>字段映射修复已准备，正在重新执行构建。</p></div></div></div><div className="diff-callout"><span>✦</span><div><b>当前修复焦点</b><p><code>DetectionService.ets</code> 的 <code>defectCount</code> 字段已从 Android `result.count` 映射完成。</p></div><span className="callout-status">待验证</span></div></div>;
}

function FileTreeLine({ name, folder, depth, open, active }: { name: string; folder?: boolean; depth: number; open?: boolean; active?: boolean }) {
  return <div className={`file-tree-line ${active ? "active" : ""}`} style={{ paddingLeft: `${depth * 16 + 8}px` }}><span>{folder ? (open ? "⌄" : "›") : "·"}</span><span className={folder ? "folder-name" : "file-name"}>{name}</span></div>;
}

function PhaseFour({ project, phase }: { project: Project; phase: Phase }) {
  const harmony = phase.emulator ?? { platform: "harmony" as const, status: "live" as const, frames: [], currentFrame: 0, currentStep: "执行一致性用例", streamType: "mock" as const };
  const android: EmulatorStream = { platform: "android", status: "replay", frames: demoAndroidFrames, currentFrame: 3, currentStep: "检测结果对照", streamType: "mock" };
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow="FUNCTIONAL PARITY / PHASE 04" /><div className="parity-summary"><div className="parity-score"><span className="eyebrow">CONSISTENCY SCORE</span><strong>94<span>/100</span></strong><small><i>↑</i> +6.8 vs initial run</small></div><div className="parity-bars"><ParityBar label="功能流程" value={100} tone="mint" /><ParityBar label="业务输出" value={96} tone="blue" /><ParityBar label="视觉语义" value={91} tone="violet" /><ParityBar label="异常处理" value={78} tone="amber" /></div><div className="parity-counts"><span><b>04</b><small>通过</small></span><span><b>01</b><small>部分通过</small></span><span><b>00</b><small>失败</small></span></div></div><div className="dual-emulators"><div className="dual-header"><div><span className="eyebrow">SYNCHRONIZED REPLAY</span><h3>同一条语义用例，两个运行时</h3></div><span className="sync-pill"><i />同步步骤 04 / 05</span></div><div className="dual-grid"><div className="dual-device"><div className="device-label"><span className="platform-dot android" />Android 基线 <small>REPLAY</small></div><EmulatorPanel stream={android} compact /></div><div className="dual-connector"><span>VS</span><i>⇄</i></div><div className="dual-device"><div className="device-label"><span className="platform-dot harmony" />HarmonyOS 迁移 <small>LIVE</small></div><EmulatorPanel stream={harmony} compact /></div></div></div><div className="difference-card"><div className="card-title-row"><div><span className="section-index">DIFF TRACE / TC-DETECT-002</span><h3>差异根因定位</h3></div><span className="resolved-pill">✓ 已修复 1 项</span></div><div className="difference-row"><span className="difference-icon">!</span><div><b>结果字段映射差异</b><p>Android 输出 <code>result.count</code>，HarmonyOS 初始输出为空。修复 Agent 已更新 <code>DetectionService.ets:42</code>。</p></div><span className="diff-tag">BUSINESS OUTPUT</span></div></div></div>;
}

function ParityBar({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <div className="parity-bar"><span>{label}</span><div><i className={`bar-${tone}`} style={{ width: `${value}%` }} /></div><b>{value}%</b></div>;
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
  return <div className={`emulator-card ${compact ? "compact" : ""} platform-${stream.platform}`}><div className="emulator-toolbar"><div className="emulator-name"><span className={`platform-dot ${stream.platform}`} />{isAndroid ? "Android Emulator" : "HarmonyOS Emulator"}<small>{stream.streamType === "mock" ? "演示帧流" : stream.streamType.toUpperCase()}</small></div><div className="emulator-status"><span className={`status-light ${stream.status}`} />{stream.status === "live" ? "LIVE" : stream.status === "replay" ? "REPLAY" : "OFFLINE"}<span className="emulator-menu">···</span></div></div><div className="device-frame"><div className="device-screen"><div className="device-topbar"><span>{isAndroid ? "9:41" : "10:28"}</span><span>▮▮▮ ◇</span></div><div className="device-appbar"><span className="app-back">‹</span><b>{frame.title}</b><span>···</span></div><div className="device-body" style={{ "--screen-accent": frame.accent } as React.CSSProperties}><div className="screen-orbit" /><span className="screen-kicker">{isAndroid ? "ANDROID BASELINE" : "HARMONYOS / ARKUI"}</span><h4>{frame.title}</h4><p className="screen-subtitle">{frame.subtitle}</p><div className="screen-metric" style={{ color: frame.accent }}>{frame.metric ?? "QC"}</div><div className="screen-card"><span className="screen-card-dot" style={{ background: frame.accent }} /><span>{frame.detail}</span></div><div className="screen-actions"><i /><i /><i /></div><div className="screen-nav"><span className="active" /><span /><span /></div></div><div className="device-home-indicator" /></div></div><div className="emulator-foot"><div className="emulator-step"><span className="step-index">{String(frameIndex + 1).padStart(2, "0")}</span><span><b>{stream.currentStep === "等待开始" ? frame.detail : stream.currentStep}</b><small>语义测试步骤 · {frameIndex + 1}/{stream.frames.length}</small></span></div><div className="emulator-controls"><button onClick={() => setPlaying((value) => !value)} aria-label={playing ? "暂停" : "播放"}>{playing ? "Ⅱ" : "▶"}</button><button onClick={() => setFrameIndex((value) => (value + 1) % Math.max(1, stream.frames.length))}>→</button></div></div></div>;
}

function AgentTimeline({ phase }: { phase: Phase }) {
  const events = phase.events.slice(-10).reverse();
  const sessionId = phase.execution?.sessionId;
  return <div className="timeline-panel"><div className="timeline-heading"><div><span className="eyebrow">AGENT TEAM ACTIVITY</span><h3>执行时间线</h3></div><span className="event-live"><i /> {phase.execution?.mode === "codearts-agentteam" ? (phase.execution.status === "running" || phase.execution.status === "starting" ? "CodeArts 实时" : "CodeArts 已归档") : phase.status === "running" ? "演示实时" : "演示已固化"}</span></div>{events.length ? <div className="timeline-list">{events.map((event) => <div className="timeline-event" key={event.id}><span className={`timeline-icon event-${event.type}`}>{event.type === "thinking" ? "✦" : event.type === "tool" ? "⌁" : event.type === "build" ? "⌘" : event.type === "test" ? "✓" : "·"}</span><div><b>{event.agent}</b><p>{event.message}</p><small>{formatTime(event.timestamp)}</small></div></div>)}</div> : <div className="timeline-empty"><span>✦</span><p>等待 Agent Team 开始工作<br /><small>阶段启动后会显示实时事件</small></p></div>}<div className="timeline-footer"><span>Session</span><code>{sessionId ?? "尚未创建真实会话"}</code>{sessionId && <button onClick={() => navigator.clipboard?.writeText(sessionId)}>复制</button>}</div></div>;
}

function RunControls({ project, phase }: { project: Project; phase: Phase }) {
  const [runningCodeArts, setRunningCodeArts] = useState(false);
  const [codeArtsMessage, setCodeArtsMessage] = useState("");
  const runningRef = useRef(false);
  const runWithCodeArts = async () => {
    if (runningRef.current) return;
    runningRef.current = true;
    setRunningCodeArts(true);
    setCodeArtsMessage("正在连接 CodeArts Agent…");
    const credentials = loadCodeArtsCredentials();
    const health = await checkCodeArts(credentials);
    if (!health.connected) {
      setCodeArtsMessage(health.message + "。点击左侧环境卡片配置账号。");
      runningRef.current = false;
      setRunningCodeArts(false);
      return;
    }
    const session = await createCodeArtsSession(`脱胎换骨 · ${project.name} · Phase ${phase.number}`, credentials);
    if (!session.accepted || !session.session?.id) {
      setCodeArtsMessage(session.message);
      runningRef.current = false;
      setRunningCodeArts(false);
      return;
    }
    mockService.recordCodeArtsExecution?.(project.id, phase.number, { mode: "codearts-agentteam", status: "starting", sessionId: session.session.id, agent: "team-leader", startedAt: new Date().toISOString() });
    const prompt = [
      "你是脱胎换骨迁移系统的 CodeArts Agent Team Leader。当前会话必须使用 CodeArts Space 的 AgentTeam 模式，由 team-leader 真实调度团队成员。",
      `请针对项目“${project.name}”执行 Phase ${phase.number}（${phase.title}）的分析，`,
      `输入来源：${project.source.value}。`,
      project.source.type === "github" ? `请先将该 GitHub 项目检出到当前 CodeArts 工作目录，再读取真实源代码。` : "当前输入是浏览器选择的 ZIP；如果本地工作目录中找不到该压缩包，请明确报告缺少源文件，不要伪造构建结果。",
      "不要只输出演示计划或固定模板：必须使用工具读取源文件，按阶段实际分析、修改或构建，并在最后返回真实命令、文件变更、构建/测试输出和仍未完成事项。",
    ].join(" ");
    const result = await promptCodeArtsSession(session.session.id, prompt, credentials, { agent: "team-leader", mode: "agent-team" });
    const livePartIds = new Set<string>();
    const resolved = result.accepted && result.pending
      ? await waitForCodeArtsResult(session.session.id, result.messageId, credentials, { timeoutMs: 90000, onUpdate: (message: CodeArtsMessage) => {
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
      setCodeArtsMessage(`已触发真实 CodeArts 推理（会话 ${session.session.id.slice(0, 12)}…）${preview ? ` · ${preview}${raw.length > 110 ? "…" : ""}` : ""}`);
      mockService.recordCodeArtsExecution?.(project.id, phase.number, { mode: "codearts-agentteam", status: "succeeded", sessionId: session.session.id, agent: "team-leader", completedAt: new Date().toISOString(), response: raw });
    } else {
      setCodeArtsMessage(`${resolved.message} · session ${session.session.id.slice(0, 12)}…`);
      mockService.recordCodeArtsExecution?.(project.id, phase.number, { mode: "codearts-agentteam", status: "failed", sessionId: session.session.id, agent: "team-leader", completedAt: new Date().toISOString(), error: resolved.message });
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
  if (!isReal) return <div className="run-controls"><div className="side-panel-heading"><span className="eyebrow">RUN CONTROLS</span><span className="secure-label">DEMO</span></div><div className="control-row"><span>当前 revision</span><b>{phase.revision}.0</b></div><div className="control-row"><span>运行模式</span><b className="muted-value">本地演示</b></div><div className="control-row"><span>数据来源</span><b className="muted-value">固定数据</b></div><button className="outline-button" onClick={() => mockService.resetDemo(project.id)}>↻ 从头播放示例</button></div>;
  return <div className="run-controls"><div className="side-panel-heading"><span className="eyebrow">RUN CONTROLS</span><span className="secure-label">{project.demo ? "DEMO" : "LIVE"}</span></div><div className="control-row"><span>当前 revision</span><b>{phase.revision}.0</b></div><div className="control-row"><span>事件数量</span><b>{phase.events.length}</b></div><div className="control-row"><span>运行模式</span><b className={project.demo ? "muted-value" : "mint-text"}>{project.demo ? "本地演示" : "CodeArts Space / AgentTeam"}</b></div><div className="control-row"><span>会话状态</span><b>{phase.execution?.sessionId ? phase.execution.status : "未启动"}</b></div><button className="codearts-run-button" onClick={runWithCodeArts} disabled={runningCodeArts || project.demo}>{runningCodeArts ? "CodeArts AgentTeam 推理中…" : project.demo ? "演示项目不可发起真实构建" : "启动真实 AgentTeam"}</button>{codeArtsMessage && <p className="codearts-message">{codeArtsMessage}</p>}{project.demo && <button className="outline-button" onClick={() => mockService.resetDemo(project.id)}>↻ 从头播放示例</button>}</div>;
}

function StatusBadge({ status }: { status: Phase["status"] }) {
  return <span className={`status-badge ${statusClasses[status]}`}><i />{statusLabels[status]}</span>;
}

function ReviewDialog({ phase, onClose, onSubmit }: { phase: Phase; onClose: () => void; onSubmit: (review: Review) => void }) {
  const [comment, setComment] = useState("");
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="review-dialog"><div className="dialog-top"><div><span className="eyebrow">HUMAN REVIEW / PHASE {phase.code}</span><h2>审核阶段交付物</h2><p>{phase.title} · revision {phase.revision}.0</p></div><button className="close-button" onClick={onClose}>×</button></div><div className="review-checklist"><span>✓</span><div><b>阶段执行已完成</b><small>{phase.events.length} 条 Agent 事件 · {phase.artifacts.length} 项交付物</small></div></div><div className="review-artifacts">{phase.artifacts.map((artifact) => <div key={artifact.id}><span className={`artifact-icon artifact-${artifact.kind}`}>◇</span><span><b>{artifact.name}</b><small>{artifact.description}</small></span><span className="ready-label">已就绪</span></div>)}</div><label className="field-label">审核意见（可选）<textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="记录需要留痕的判断或修改建议…" rows={3} /></label><div className="dialog-actions"><button className="ghost-button" onClick={() => onSubmit(makeReview("changes_requested", comment))}>要求修改</button><button className="primary-button" onClick={() => onSubmit(makeReview("approved", comment))}>审核通过 <span>→</span></button></div></div></div>;
}

function CodeArtsConnectDialog({ initial, onClose, onConnected }: { initial: CodeArtsCredentials; onClose: () => void; onConnected: (value: CodeArtsConnection) => void }) {
  const [credentials, setCredentials] = useState<CodeArtsCredentials>(initial);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<CodeArtsConnection | null>(null);
  const verify = async () => {
    setChecking(true);
    const value = await checkCodeArts(credentials);
    setResult(value);
    setChecking(false);
    if (value.connected) {
      saveCodeArtsCredentials(credentials);
      onConnected(value);
    }
  };
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="review-dialog codearts-dialog"><div className="dialog-top"><div><span className="eyebrow">CODEARTS LOCAL BRIDGE</span><h2>连接 CodeArts Agent</h2><p>通过 Vite 本地桥接访问 AgentKernel（默认 127.0.0.1:27546）</p></div><button className="close-button" onClick={onClose}>×</button></div><div className="codearts-notice"><span>✦</span><p>密码框可以留空：桥接会优先使用页面凭据；留空时自动使用本机 CodeArts Agent 的加密凭据，不会显示或写入密码。</p></div><label className="field-label">用户名<input value={credentials.username} onChange={(event) => setCredentials({ ...credentials, username: event.target.value })} placeholder="opencode" /></label><label className="field-label">本地服务密码（可选）<input type="password" value={credentials.password} onChange={(event) => setCredentials({ ...credentials, password: event.target.value })} placeholder="留空以使用本机 Agent 凭据" /></label>{result && <div className={`codearts-result ${result.connected ? "success" : "error"}`}><span>{result.connected ? "✓" : "!"}</span><div><b>{result.message}</b><small>{result.connected ? `${result.service ?? "CodeArts Agent"}${result.version ? ` · ${result.version}` : ""}` : "请确认 AgentKernel 已启动，或手动输入用户名/密码"}</small></div></div>}<div className="dialog-actions"><button className="ghost-button" onClick={onClose}>取消</button><button className="primary-button" onClick={verify} disabled={checking}>{checking ? "检测中…" : "检测并连接"}<span>→</span></button></div></div></div>;
}

function ReportPage() {
  const { id } = useParams();
  const project = useProject(id);
  if (!project) return <NotFound />;
  return <div className="report-page"><div className="workspace-header"><div className="breadcrumb"><Link to={`/projects/${project.id}`}>工作台</Link><span>/</span><b>迁移报告</b></div><div className="workspace-actions"><span className="demo-tag">DEMO DATA</span><button className="ghost-button small" onClick={() => downloadText("migration-quick-report.md", `# ${project.name}\n\n一致性评分：94/100\n\n当前为演示数据。`)}>↓ 下载速览版</button><button className="primary-button small" onClick={() => downloadText("migration-full-report.json", JSON.stringify(project, null, 2))}>↓ 导出完整 JSON</button></div></div><div className="page-heading report-heading"><div><p className="eyebrow">MIGRATION REPORT / GENERATED FROM EVIDENCE</p><h1>迁移结果报告</h1><p className="heading-subtitle">{project.name} · 证据链完整度 92%</p></div><StatusBadge status="completed" /></div><div className="report-hero"><div className="report-score"><span className="eyebrow">FUNCTIONAL CONSISTENCY</span><strong>94<small>/100</small></strong><span className="score-caption">建议交付 · 2026-08-27</span></div><div className="report-stat"><span>功能用例</span><b>05</b><small>4 通过 · 1 部分</small></div><div className="report-stat"><span>自动修复</span><b>02</b><small>补丁均已回归</small></div><div className="report-stat"><span>人工审核</span><b>04</b><small>阶段门禁完整</small></div></div><div className="report-grid"><div className="report-main"><div className="section-heading"><div><p className="eyebrow">EXECUTIVE SUMMARY</p><h2>一分钟了解这次迁移</h2></div></div><div className="summary-copy"><p>本次迁移已完成从 Android 到 HarmonyOS 的核心功能验证。项目总览、图片导入、结果详情和历史记录通过一致性检查；缺陷检测功能的字段映射经过一次自动修复后，与 Android 基线保持一致。</p><div className="summary-points"><span><i className="mint-dot" />核心流程可复现</span><span><i className="blue-dot" />证据可追溯</span><span><i className="amber-dot" />1 项差异已解释</span></div></div><FeatureReportTable features={project.features} /><div className="report-section"><div className="section-heading"><div><p className="eyebrow">AGENT TRACE</p><h2>CodeArts Agent Team 使用记录</h2></div><span className="subtle-link">查看全部 →</span></div><div className="trace-cards">{["需求分析与 Codebase 索引", "单元测试与语义契约", "ArkTS 生成与编译修复"].map((item, index) => <div className="trace-card" key={item}><span>{String(index + 1).padStart(2, "0")}</span><div><b>{item}</b><small>Session team_{index + 1}_demo_8f21 · 已归档</small></div><em>✓</em></div>)}</div></div></div><aside className="report-aside"><div className="aside-card report-nav"><p className="eyebrow">REPORT INDEX</p>{["执行摘要", "功能一致性矩阵", "差异与修复", "Agent 使用记录", "环境与依赖"].map((item, index) => <a className={index === 0 ? "active" : ""} href={`#report-${index}`} key={item}><span>0{index + 1}</span>{item}<i>→</i></a>)}</div><div className="aside-tip"><span>▣</span><p>完整版报告将包含原始 Markdown、JSON 数据和可打印 PDF。</p></div></aside></div></div>;
}

function FeatureReportTable({ features }: { features: Feature[] }) {
  return <div className="report-table-card"><div className="card-title-row"><div><span className="section-index">FEATURE PARITY MATRIX</span><h3>功能一致性矩阵</h3></div><span className="table-note">Android vs HarmonyOS</span></div><div className="feature-report-table"><div className="table-row table-head"><span>功能</span><span>Android 基线</span><span>HarmonyOS 结果</span><span>结论</span></div>{features.map((feature) => <div className="table-row" key={feature.id}><span><b>{feature.name}</b><small>{feature.description}</small></span><span className="result-cell"><i className="check-icon">✓</i>{feature.androidResult}</span><span className="result-cell"><i className={`check-icon ${feature.status === "partial" ? "partial" : feature.status === "risk" ? "risk" : ""}`}>{feature.status === "covered" ? "✓" : feature.status === "partial" ? "!" : "·"}</i>{feature.harmonyResult}</span><span><span className={`table-status ${feature.status}`}>{feature.status === "covered" ? "通过" : feature.status === "partial" ? "部分" : "待验证"}</span></span></div>)}</div></div>;
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
  return <div className="delivery-page"><div className="workspace-header"><div className="breadcrumb"><Link to={`/projects/${project.id}`}>工作台</Link><span>/</span><b>交付中心</b></div><div className="workspace-actions"><span className="checksum-label">SHA256 · DEMO</span><button className="primary-button small" onClick={() => downloadText("delivery-manifest.json", JSON.stringify({ project: project.name, generatedAt: new Date().toISOString(), artifacts: deliveryArtifacts }, null, 2))}>↓ 下载交付清单</button></div></div><div className="page-heading"><div><p className="eyebrow">DELIVERY CENTER / FINAL PACKAGE</p><h1>交付中心</h1><p className="heading-subtitle">所有文件来自已审核版本 · revision 4.0</p></div><div className="delivery-ready"><span>✓</span><div><b>交付包已就绪</b><small>6 个文件 · 8.4 MB</small></div></div></div><div className="delivery-layout"><main><div className="delivery-hero"><div className="package-icon">⌘</div><div><p className="eyebrow">FINAL DELIVERY PACKAGE</p><h2>{project.name} · HarmonyOS 迁移包</h2><p>包含完整工程、执行证据、截图和双层报告，可直接交给评审或工程团队复现。</p></div><button className="primary-button" onClick={() => downloadText("delivery-manifest.json", JSON.stringify(deliveryArtifacts, null, 2))}>下载全部 <span>↓</span></button></div><div className="artifact-grid">{deliveryArtifacts.map((artifact) => <button className="delivery-artifact" key={artifact.name} onClick={() => downloadText(artifact.name.endsWith("json") ? artifact.name : `${artifact.name}.txt`, `${artifact.name}\n\n${artifact.desc}\n\n当前为演示数据。`)}><span className={`delivery-file-icon ${artifact.color}`}>{artifact.type === "code" ? "‹›" : artifact.type === "screenshot" ? "▧" : artifact.type === "trace" ? "≋" : artifact.type === "build" ? "⌁" : "≡"}</span><span><b>{artifact.name}</b><small>{artifact.desc}</small></span><em>{artifact.size}</em><i>↓</i></button>)}</div></main><aside className="delivery-aside"><div className="aside-card"><p className="eyebrow">PACKAGE MANIFEST</p><div className="manifest-row"><span>源项目</span><b>{project.source.type === "github" ? "GitHub" : "ZIP"}</b></div><div className="manifest-row"><span>目标平台</span><b>HarmonyOS</b></div><div className="manifest-row"><span>审核阶段</span><b>4 / 4</b></div><div className="manifest-row"><span>一致性评分</span><b className="mint-text">94 / 100</b></div><div className="manifest-row"><span>数据模式</span><b>演示数据</b></div><div className="manifest-hash"><small>PACKAGE HASH</small><code>sha256: 8f21…a93c</code></div></div><div className="aside-tip"><span>ⓘ</span><p>真实接入后，此处会显示对象存储地址、构建产物校验值和环境清单。</p></div></aside></div></div>;
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
