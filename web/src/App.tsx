import React, { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, Route, Routes, useNavigate, useParams } from "react-router-dom";
import type { EmulatorFrame, EmulatorStream, Feature, Phase, PhaseNumber, Project, ProjectInput, Review } from "./types";
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
  const [connection, setConnection] = useState<CodeArtsConnection | null>(null);
  const [codeArtsOpen, setCodeArtsOpen] = useState(false);
  useEffect(() => mockService.subscribeAll(setProjects), []);
  useEffect(() => { checkCodeArts(loadCodeArtsCredentials()).then(setConnection); }, []);
  const active = projects.find((project) => project.status === "running" || project.status === "review");
  const navClass = ({ isActive }: { isActive: boolean }) => isActive ? "active" : "";
  return <div className="app-shell">
    <header className="topbar">
      <Link className="brand" to="/"><span className="brand-mark">脱</span><strong>脱胎换骨</strong></Link>
      <nav className="topnav">
        <NavLink to="/" end className={navClass}>项目总览</NavLink>
        <NavLink to="/projects/new" className={navClass}>新建迁移</NavLink>
        {active && <NavLink to={`/projects/${active.id}`} className={navClass}>当前工作台</NavLink>}
      </nav>
      <div className="topbar-right">
        <button className="env-pill" onClick={() => setCodeArtsOpen(true)}><span className={`env-dot ${connection?.connected ? "connected" : ""}`} />{connection?.connected ? "CodeArts 已连接" : "CodeArts 未连接"}</button>
        <span className="user-chip"><span className="avatar">审</span>当前审核员</span>
      </div>
    </header>
    <div className={`demo-banner ${connection?.connected ? "live-banner" : ""}`}>{connection?.connected ? "真实执行模式 · CodeArts Space / AgentTeam" : "CodeArts Agent 未连接 · 新任务将无法启动真实推理"}<span className="banner-link" onClick={() => setCodeArtsOpen(true)}>{connection?.connected ? "查看连接状态 →" : "连接 CodeArts →"}</span></div>
    <main className="main-content"><div className="page-content"><Outlet /></div></main>
    {codeArtsOpen && <CodeArtsTestDialog initial={loadCodeArtsCredentials()} onClose={() => setCodeArtsOpen(false)} onConnected={(value) => setConnection(value)} />}
  </div>;
}

function CodeArtsTestDialog({ initial, onClose, onConnected }: { initial: CodeArtsCredentials; onClose: () => void; onConnected: (value: CodeArtsConnection) => void }) {
  const [credentials, setCredentials] = useState<CodeArtsCredentials>(initial);
  const [instruction, setInstruction] = useState("请回复 CODEARTS_CONNECTION_OK，并用一句话说明你当前使用的执行模式。不要修改任何文件。");
  const [status, setStatus] = useState<"idle" | "checking" | "running" | "succeeded" | "failed">("idle");
  const [result, setResult] = useState<CodeArtsRunResult | null>(null);
  const [messages, setMessages] = useState<CodeArtsMessage[]>([]);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState<number | null>(null);
  const runningRef = useRef(false);

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
        setError(checked.message);
        return;
      }
      saveCodeArtsCredentials(credentials);
      onConnected(checked);
      setStatus("running");
      const created = await createCodeArtsSession(`脱胎换骨 · 连接测试 · ${new Date(started).toLocaleTimeString("zh-CN")}`, credentials);
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
  const statusLabel = status === "idle" ? "尚未测试" : status === "checking" ? "健康检查中" : status === "running" ? "推理中" : status === "succeeded" ? "测试通过" : "测试失败";
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="review-dialog codearts-dialog">
    <div className="dialog-top"><div><h2>CodeArts 连接测试</h2><p>向本机 AgentKernel 发送一条真实指令，验证 AgentTeam 推理可用。</p></div><div className="dialog-top-right"><span className={`test-status-pill ${status}`}>{statusLabel}</span><button className="close-button" onClick={onClose}>×</button></div></div>
    <div className="codearts-test-warning"><strong>这不是 Mock 测试</strong><span>会创建独立测试会话，不读取或修改迁移项目。</span></div>
    <label className="field-label">用户名<input value={credentials.username} onChange={(event) => setCredentials({ ...credentials, username: event.target.value })} placeholder="codearts" /></label>
    <label className="field-label">本地服务密码（可选）<input type="password" value={credentials.password} onChange={(event) => setCredentials({ ...credentials, password: event.target.value })} placeholder="留空则使用本机 Agent 凭据" /></label>
    <label className="field-label">测试指令<textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} rows={3} placeholder="输入你希望 CodeArts 回答的内容" /></label>
    <button className="primary-button wide" onClick={runTest} disabled={status === "checking" || status === "running" || !instruction.trim()}>{status === "checking" ? "检查 CodeArts 服务…" : status === "running" ? "等待回复…" : "发送测试指令"}<span>→</span></button>
    {(error || result?.message) && status === "failed" && <div className="codearts-test-error">{error || result?.message}</div>}
    {responseText && <pre className="real-response dialog-response">{responseText}</pre>}
    {!responseText && status === "running" && <div className="test-loader"><i /><i /><i /></div>}
    <div className="codearts-test-meta"><span>Agent <b>team-leader</b></span><span>消息 <b>{messages.length}</b></span><span>耗时 <b>{elapsed === null ? "—" : `${(elapsed / 1000).toFixed(1)}s`}</b></span></div>
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
      <div className="page-heading home-heading"><div><h1>项目总览</h1><p className="heading-subtitle">脱胎换骨把 Android 到 HarmonyOS 的迁移拆成识胎、验旧、换骨、验神四个阶段，每个阶段的产物经人工审核后才能进入下一步。</p></div><Link to="/projects/new" className="primary-button">新建迁移任务</Link></div>
      <div className="stats-grid"><StatCard label="进行中的迁移" value={String(running).padStart(2, "0")} /><StatCard label="已完成交付" value={String(completed).padStart(2, "0")} /><StatCard label="登记功能点" value={String(features.length).padStart(2, "0")} unit="项" /><StatCard label="已确认功能" value={String(covered).padStart(2, "0")} unit="项" /></div>
      <div className="section-heading"><h2>迁移任务</h2></div>
      <div className="task-table">
        <div className="task-row task-head"><span>项目名称</span><span>来源</span><span>当前阶段</span><span>阶段进度</span><span>状态</span><span>更新时间</span><span /></div>
        {projects.map((project) => { const current = project.phases.find((phase) => phase.number === project.currentPhase); const completedPhases = project.phases.filter((phase) => phase.status === "approved" || phase.status === "completed").length; return (
          <Link to={`/projects/${project.id}`} className="task-row" key={project.id}>
            <span className="task-name"><b>{project.name}</b></span>
            <span>{project.source.type === "github" ? "GitHub 仓库" : "Android ZIP"}</span>
            <span>{String(project.currentPhase).padStart(2, "0")} · {current?.shortTitle}</span>
            <span>{completedPhases}/4</span>
            <span><StatusBadge status={current?.status ?? "pending"} /></span>
            <span className="task-time">{project.demo ? "刚刚" : "今天 14:32"}</span>
            <span className="task-arrow">›</span>
          </Link>
        ); })}
      </div>
      <p className="mock-note"><span>ⓘ</span> 当前为演示数据</p>
    </div>
  );
}

function StatCard({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return <div className="stat-card"><p>{label}</p><div className="stat-value">{value}<small>{unit}</small></div></div>;
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
  return <div className="new-project-page"><div className="page-heading"><div><h1>新建迁移任务</h1><p className="heading-subtitle">输入源项目后，直接启动真实 CodeArts AgentTeam 推理。</p></div><Link to="/" className="ghost-button">← 返回项目总览</Link></div><div className="new-project-layout"><form className="intake-card" onSubmit={submit}><div className="card-title-row"><div><span className="section-index">01</span><h2>选择源项目</h2></div><span className="required-note">必填</span></div><div className="source-toggle"><button type="button" className={sourceType === "github" ? "toggle active" : "toggle"} onClick={() => { setSourceType("github"); setSourceValue(""); setError(""); }}>GitHub 链接</button><button type="button" className={sourceType === "zip" ? "toggle active" : "toggle"} onClick={() => { setSourceType("zip"); setSourceValue(""); setError(""); }}>Android ZIP</button></div>{sourceType === "github" ? <label className="field-label">GitHub 公共仓库链接<input value={sourceValue} onChange={(event) => setSourceValue(event.target.value)} placeholder="https://github.com/example/android-project" /></label> : <label className="file-drop"><input type="file" accept=".zip" onChange={(event) => { setSourceValue(event.target.files?.[0]?.name ?? ""); setError(""); }} /><span className="upload-icon">↑</span><b>{sourceValue || "点击选择 Android 项目压缩包"}</b><small>{sourceValue ? "已选择；真实构建前需上传到 CodeArts 工作目录" : "支持 .zip，建议不超过 50 MB"}</small></label>}<div className="field-divider" /><div className="card-title-row compact"><div><span className="section-index">02</span><h2>任务信息</h2></div></div><label className="field-label">迁移项目名称<input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：机器视觉质检助手迁移" /></label><div className="execution-mode-picker"><div className="mode-picker-heading"><b>选择执行引擎</b></div><button type="button" className={executionMode === "codearts-agentteam" ? "mode-option active" : "mode-option"} onClick={() => setExecutionMode("codearts-agentteam")}><strong>CodeArts Space / AgentTeam</strong><small>真实大模型推理、团队调度和工具执行</small></button><button type="button" className={executionMode === "demo" ? "mode-option active" : "mode-option"} onClick={() => setExecutionMode("demo")}><strong>本地演示</strong><small>仅播放固定数据，不产生真实构建</small></button></div>{error && <div className="form-error">! {error}</div>}<button className="primary-button wide" type="submit">启动迁移 <span className="button-arrow">→</span></button></form><aside className="intake-aside"><div className="aside-card"><p className="eyebrow">执行流程</p><h3>四阶段真实门禁</h3><div className="preview-steps">{[{n: "01", t: "识胎", d: "源项目语义重建" }, { n: "02", t: "验旧", d: "Android 行为基线" }, { n: "03", t: "换骨", d: "HarmonyOS 迁移生成" }, { n: "04", t: "验神", d: "功能一致性验证" }].map((step, index) => <div className="preview-step" key={step.n}><span>{step.n}</span><div><b>{step.t}</b><small>{step.d}</small></div>{index < 3 && <i>↓</i>}</div>)}</div></div><div className="aside-tip"><span>ⓘ</span><p>真实模式要求本机 CodeArts Agent 已登录并可用。GitHub 项目会由 Agent 在工作目录检出；ZIP 上传接口将在后续版本补齐。</p></div></aside></div></div>;
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
  const coveredFeatures = project.features.filter((feature) => feature.status === "covered").length;
  const performReview = (review: Review) => { mockService.reviewPhase(project.id, selected.number, review); setReviewOpen(false); };
  return <div className="workspace-page"><div className="workspace-header"><div className="breadcrumb"><Link to="/">项目总览</Link><span>/</span><b>{project.name}</b></div><div className="workspace-actions"><span className={real ? "live-tag" : "demo-tag"}>{real ? "真实执行 · CodeArts" : "演示数据"}</span><Link to={`/projects/${project.id}/report`} className="ghost-button small">查看报告</Link><Link to={`/projects/${project.id}/delivery`} className="primary-button small">交付中心 <span>→</span></Link></div></div><div className="workspace-title"><h1>{project.name} <StatusBadge status={project.status === "completed" ? "completed" : project.status === "review" ? "review_required" : "running"} /></h1><p className="heading-subtitle">{project.id.toUpperCase()} · {project.source.type === "github" ? "GitHub 源码" : "Android ZIP"} · {real ? "CodeArts AgentTeam" : "本地演示"} · revision {selected.revision}.0</p></div><div className="overview-strip"><div className="overview-item"><small>功能覆盖度</small><b>{Math.round((coveredFeatures / project.features.length) * 100)}%<span>{coveredFeatures}/{project.features.length} 项已确认</span></b></div><div className="overview-item"><small>本阶段交付物</small><b>{selected.artifacts.length} 项</b></div><div className="overview-item"><small>当前阶段</small><b>{String(project.currentPhase).padStart(2, "0")} · {selected.shortTitle}</b></div><div className="overview-item"><small>运行模式</small><b>{real ? "CodeArts AgentTeam" : "本地演示"}</b></div></div><PhaseRail phases={project.phases} selected={selectedPhase} onSelect={setSelectedPhase} /><div className="workspace-grid"><section className="workspace-center"><PhaseContent project={project} phase={selected} /><div className="review-bar"><div><span className={`review-dot ${canReview ? "active" : ""}`} /><div><b>{canReview ? "本阶段等待人工审核" : selected.status === "running" ? (real ? "CodeArts AgentTeam 正在执行" : "演示工作流正在执行") : statusLabels[selected.status]}</b>{canReview && <small>确认真实会话结果后才能进入下一阶段</small>}</div></div><div className="review-actions">{selected.status === "running" && !real && <><button className="icon-button" onClick={() => selected.paused ? mockService.resumePhase(project.id, selected.number) : mockService.pausePhase(project.id, selected.number)}>{selected.paused ? "▶ 继续" : "Ⅱ 暂停"}</button><button className="icon-button" onClick={() => mockService.skipPhase(project.id, selected.number)}>跳过等待</button></>}{canReview && <button className="primary-button" onClick={() => setReviewOpen(true)}>打开审核 <span>→</span></button>}{(selected.status === "approved" || selected.status === "completed") && !real && <button className="icon-button" onClick={() => mockService.restartPhase(project.id, selected.number)}>↻ 重新演示</button>}</div></div></section><aside className="workspace-right"><AgentTimeline phase={selected} /><RunControls project={project} phase={selected} /></aside></div>{reviewOpen && <ReviewDialog phase={selected} onClose={() => setReviewOpen(false)} onSubmit={performReview} />}</div>;
}

function PhaseRail({ phases, selected, onSelect }: { phases: Phase[]; selected: PhaseNumber; onSelect: (phase: PhaseNumber) => void }) {
  return <div className="phase-rail">{phases.map((phase, index) => <button key={phase.number} className={`phase-rail-item ${selected === phase.number ? "selected" : ""} ${statusClasses[phase.status]}`} onClick={() => onSelect(phase.number)}><span className="phase-number">{phase.code}</span><span className="phase-rail-text"><b>{phase.shortTitle}</b><small>{phase.title.split("·")[1]?.trim()}</small></span><span className="phase-rail-status">{phase.status === "running" ? <span className="spinner" /> : phase.status === "approved" || phase.status === "completed" ? "✓" : phase.status === "review_required" ? "!" : "·"}</span>{index < phases.length - 1 && <i className="rail-connector" />}</button>)}</div>;
}

function PhaseContent({ project, phase }: { project: Project; phase: Phase }) {
  if (project.executionMode === "codearts-agentteam" && !project.demo) return <RealPhaseContent project={project} phase={phase} />;
  if (phase.number === 1) return <PhaseOne phase={phase} features={project.features} />;
  if (phase.number === 2) return <PhaseTwo phase={phase} />;
  if (phase.number === 3) return <PhaseThree phase={phase} />;
  return <PhaseFour project={project} phase={phase} />;
}

function RealPhaseContent({ project, phase }: { project: Project; phase: Phase }) {
  const eyebrow = phase.number === 1 ? "阶段 01 · 语义重建" : phase.number === 2 ? "阶段 02 · 行为基线" : phase.number === 3 ? "阶段 03 · 迁移生成" : "阶段 04 · 一致性验证";
  const execution = phase.execution;
  const response = execution?.response?.trim();
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow={eyebrow} /><div className="real-evidence-card"><div className="real-evidence-heading"><div><h3>{execution?.status === "succeeded" ? "AgentTeam 已返回真实结果" : execution?.status === "failed" ? "AgentTeam 执行失败" : "等待 AgentTeam 真实执行"}</h3></div><span className={`execution-status ${execution?.status ?? "idle"}`}>{execution?.status ?? "idle"}</span></div><div className="real-evidence-meta"><span>模式 <b>CodeArts Space / AgentTeam</b></span><span>Agent <b>{execution?.agent ?? "team-leader"}</b></span><span>Session <code>{execution?.sessionId ?? "尚未创建"}</code></span></div>{execution?.error && <div className="real-error">{execution.error}</div>}{response && <pre className="real-response">{response}</pre>}{!response && !execution?.error && <div className="real-waiting">页面不会生成固定分析、构建日志或一致性分数。CodeArts 返回真实消息后，这里才会显示可审核证据。</div>}</div>{phase.number === 2 && phase.emulator && <div className="runner-placeholder"><div><h3>等待真实 Android 模拟器</h3><p>当前只保留 Runner 接口位置；不会用本地帧流冒充真实执行。</p></div><EmulatorPanel stream={phase.emulator} /></div>}{phase.number === 4 && <div className="runner-placeholder"><div><h3>等待真实 HarmonyOS 模拟器</h3><p>一致性判别将在真实鸿蒙运行轨迹和 Android 基线都返回后生成。</p></div></div>}</div>;
}

function PhaseHeader({ phase, eyebrow }: { phase: Phase; eyebrow: string }) {
  return <div className="phase-header"><div><p className="eyebrow">{eyebrow} <span className="phase-live-label">{phase.status === "running" ? "· 执行中" : phase.status === "review_required" ? "· 待审核" : ""}</span></p><h2>{phase.title}</h2><p>{phase.description}</p></div><div className="phase-progress"><strong>{String(phase.progress).padStart(2, "0")}<small>%</small></strong><span>阶段进度</span></div></div>;
}

function PhaseOne({ phase, features }: { phase: Phase; features: Feature[] }) {
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow="阶段 01 · 语义重建" /><div className="analysis-grid"><div className="analysis-card analysis-highlight"><div className="card-topline"><span className="card-label">源项目健康度</span><span className="health-pill">良好</span></div><div className="health-score">86<span>/100</span></div><p>源项目结构清晰，已识别关键迁移边界。</p><div className="health-bars"><span><i style={{ width: "92%" }} /><small>可构建性</small></span><span><i style={{ width: "82%" }} /><small>依赖可替代性</small></span><span><i style={{ width: "76%" }} /><small>隐式逻辑可见度</small></span></div></div><div className="analysis-card"><div className="card-topline"><span className="card-label">语义结构</span><span className="muted-value">86 个文件</span></div><div className="graph-visual"><span className="graph-node node-main">业务入口</span><span className="graph-node node-a">图片导入</span><span className="graph-node node-b">检测服务</span><span className="graph-node node-c">历史记录</span><i className="graph-line line-a" /><i className="graph-line line-b" /><i className="graph-line line-c" /></div><p>Codebase 索引已完成，功能节点之间的调用关系已建立。</p></div><div className="analysis-card risk-card"><div className="card-topline"><span className="card-label">迁移风险</span><span className="risk-count">3 项</span></div><div className="risk-list"><span><i>!</i><b>视觉模型字段</b><small>需要跨端字段映射</small></span><span><i>!</i><b>权限申请流程</b><small>目标平台 API 不同</small></span><span><i>·</i><b>历史数据格式</b><small>建议保留兼容层</small></span></div></div></div><div className="data-table-card"><div className="card-title-row"><div><h3>功能语义契约</h3></div><span className="table-note">revision {phase.revision}.0</span></div><div className="feature-table"><div className="table-row table-head"><span>功能</span><span>语义说明</span><span>风险级别</span><span>状态</span></div>{features.map((feature) => <div className="table-row" key={feature.id}><span><b>{feature.name}</b></span><span>{feature.description}</span><span><span className={`risk-label ${feature.status}`}>{feature.status === "covered" ? "低" : feature.status === "partial" ? "中" : "高"}</span></span><span><span className={`table-status ${feature.status}`}>{feature.status === "covered" ? "已覆盖" : feature.status === "partial" ? "需复核" : "待分析"}</span></span></div>)}</div></div></div>;
}

function PhaseTwo({ phase }: { phase: Phase }) {
  const stream = phase.emulator ?? { platform: "android" as const, status: "live" as const, frames: demoAndroidFrames, currentFrame: 0, currentStep: "执行测试用例", streamType: "mock" as const };
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow="阶段 02 · 行为基线" /><div className="execution-layout"><EmulatorPanel stream={stream} /><div className="test-run-card"><div className="card-topline"><span className="card-label">测试用例</span><span className="live-tag">● RUNNING</span></div><div className="test-summary"><strong>05</strong><span>条核心用例</span></div><div className="test-list"><TestItem code="TC-001" name="项目启动与首页加载" state="passed" time="1.2s" /><TestItem code="TC-002" name="导入质检图片" state="passed" time="3.8s" /><TestItem code="TC-003" name="完成缺陷检测" state="running" time="进行中" /><TestItem code="TC-004" name="查看结果详情" state="pending" time="排队中" /><TestItem code="TC-005" name="查询历史记录" state="pending" time="排队中" /></div><div className="trace-footer"><span>↗</span> 已保存 3 个执行轨迹快照 <b>查看轨迹 →</b></div></div></div><div className="evidence-strip"><div><span className="eyebrow">已采集证据</span><h3>Android 行为基线</h3></div><EvidenceThumb title="首页" accent="#39d2a8" /><EvidenceThumb title="导入图片" accent="#7c8cff" /><EvidenceThumb title="检测结果" accent="#ff7b82" /><div className="evidence-more">+2<br /><small>查看全部</small></div></div></div>;
}

function TestItem({ code, name, state, time }: { code: string; name: string; state: "passed" | "running" | "pending"; time: string }) {
  return <div className="test-item"><span className={`test-state ${state}`}>{state === "passed" ? "✓" : state === "running" ? "◌" : "·"}</span><span><b>{code}</b><small>{name}</small></span><em>{time}</em></div>;
}

function EvidenceThumb({ title, accent }: { title: string; accent: string }) {
  return <div className="evidence-thumb"><div className="thumb-screen" style={{ "--thumb-accent": accent } as React.CSSProperties}><span /><i /><b /></div><small>{title}</small></div>;
}

function PhaseThree({ phase }: { phase: Phase }) {
  const agents = [{ name: "Harmony 架构 Agent", role: "ArkUI / 状态模型", state: "working", initials: "架" }, { name: "UI 迁移 Agent", role: "页面和资源", state: "done", initials: "UI" }, { name: "API 迁移 Agent", role: "平台能力映射", state: "done", initials: "API" }, { name: "Repair Agent", role: "编译问题修复", state: "working", initials: "修" }];
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow="阶段 03 · 迁移生成" /><div className="migration-overview"><div className="codebase-card"><div className="card-topline"><span className="card-label">HarmonyOS 工程</span><span className="live-tag">ArkTS</span></div><div className="codebase-layout"><div className="file-tree"><FileTreeLine name="harmony-project" folder depth={0} /><FileTreeLine name="entry" folder depth={1} open /><FileTreeLine name="pages" folder depth={2} open /><FileTreeLine name="Index.ets" depth={3} active /><FileTreeLine name="Result.ets" depth={3} /><FileTreeLine name="History.ets" depth={3} /><FileTreeLine name="services" folder depth={2} /><FileTreeLine name="DetectionService.ets" depth={3} /><FileTreeLine name="module.json5" depth={1} /></div><div className="code-preview"><div className="code-tabs"><span className="active">Index.ets</span><span>DetectionService.ets</span></div><pre><code><i>01</i> <b>struct</b> <strong>Index</strong> &#123;{`\n`}<i>02</i>   <b>@State</b> isRunning: <strong>boolean</strong> = <strong>false</strong>{`\n`}<i>03</i>   <b>build</b>() &#123;{`\n`}<i>04</i>     <strong>Column</strong>() &#123;{`\n`}<i>05</i>       <strong>Text</strong>(<em>"质检工作台"</em>){`\n`}<i>06</i>       <strong>UploadCard</strong>(&#123;{`\n`}<i>07</i>         onStart: () =&gt; <strong>this</strong>.runDetection(){`\n`}<i>08</i>       &#125;){`\n`}<i>09</i>     &#125;{`\n`}<i>10</i>   &#125;{`\n`}<i>11</i> &#125;</code></pre><span className="code-cursor" /></div></div><div className="build-status"><span className="spinner" /> hvigor assembleHap <b>编译中</b><span className="build-time">01:42</span></div></div><div className="agent-team-card"><div className="card-topline"><span className="card-label">Agent 团队</span><span className="muted-value">4 个成员</span></div><div className="agent-member-list">{agents.map((agent) => <div className="agent-member" key={agent.name}><span className={`member-avatar ${agent.state}`}>{agent.initials}</span><span><b>{agent.name}</b><small>{agent.role}</small></span><span className={`member-state ${agent.state}`}>{agent.state === "done" ? "完成" : "工作中"}</span></div>)}</div><div className="agent-quote"><span>“</span><p>字段映射修复已准备，正在重新执行构建。</p></div></div></div><div className="diff-callout"><span>●</span><div><b>当前修复焦点</b><p><code>DetectionService.ets</code> 的 <code>defectCount</code> 字段已从 Android `result.count` 映射完成。</p></div><span className="callout-status">待验证</span></div></div>;
}

function FileTreeLine({ name, folder, depth, open, active }: { name: string; folder?: boolean; depth: number; open?: boolean; active?: boolean }) {
  return <div className={`file-tree-line ${active ? "active" : ""}`} style={{ paddingLeft: `${depth * 16 + 8}px` }}><span>{folder ? (open ? "⌄" : "›") : "·"}</span><span className={folder ? "folder-name" : "file-name"}>{name}</span></div>;
}

function PhaseFour({ project, phase }: { project: Project; phase: Phase }) {
  const harmony = phase.emulator ?? { platform: "harmony" as const, status: "live" as const, frames: [], currentFrame: 0, currentStep: "执行一致性用例", streamType: "mock" as const };
  const android: EmulatorStream = { platform: "android", status: "replay", frames: demoAndroidFrames, currentFrame: 3, currentStep: "检测结果对照", streamType: "mock" };
  return <div className="phase-content"><PhaseHeader phase={phase} eyebrow="阶段 04 · 一致性验证" /><div className="parity-summary"><div className="parity-score"><span className="eyebrow">一致性得分</span><strong>94<span>/100</span></strong><small>对照 Android 基线</small></div><div className="parity-bars"><ParityBar label="功能流程" value={100} tone="mint" /><ParityBar label="业务输出" value={96} tone="blue" /><ParityBar label="视觉语义" value={91} tone="violet" /><ParityBar label="异常处理" value={78} tone="amber" /></div></div><div className="dual-emulators"><div className="dual-header"><div><span className="eyebrow">双端对照回放</span><h3>同一条语义用例，两个运行时</h3></div><span className="sync-pill"><i />同步步骤 04 / 05</span></div><div className="dual-grid"><div className="dual-device"><div className="device-label"><span className="platform-dot android" />Android 基线 <small>REPLAY</small></div><EmulatorPanel stream={android} compact /></div><div className="dual-connector"><span>VS</span><i>⇄</i></div><div className="dual-device"><div className="device-label"><span className="platform-dot harmony" />HarmonyOS 迁移 <small>LIVE</small></div><EmulatorPanel stream={harmony} compact /></div></div></div><div className="difference-card"><div className="card-title-row"><div><h3>差异根因定位</h3></div><span className="resolved-pill">✓ 已修复 1 项</span></div><div className="difference-row"><span className="difference-icon">!</span><div><b>结果字段映射差异</b><p>Android 输出 <code>result.count</code>，HarmonyOS 初始输出为空。修复 Agent 已更新 <code>DetectionService.ets:42</code>。</p></div><span className="diff-tag">业务输出</span></div></div></div>;
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
  return <div className={`emulator-card ${compact ? "compact" : ""} platform-${stream.platform}`}><div className="emulator-toolbar"><div className="emulator-name"><span className={`platform-dot ${stream.platform}`} />{isAndroid ? "Android Emulator" : "HarmonyOS Emulator"}<small>{stream.streamType === "mock" ? "演示帧流" : stream.streamType.toUpperCase()}</small></div><div className="emulator-status"><span className={`status-light ${stream.status}`} />{stream.status === "live" ? "LIVE" : stream.status === "replay" ? "REPLAY" : "OFFLINE"}<span className="emulator-menu">···</span></div></div><div className="device-frame"><div className="device-screen"><div className="device-topbar"><span>{isAndroid ? "9:41" : "10:28"}</span><span>▮▮▮ ◇</span></div><div className="device-appbar"><span className="app-back">‹</span><b>{frame.title}</b><span>···</span></div><div className="device-body" style={{ "--screen-accent": frame.accent } as React.CSSProperties}><div className="screen-orbit" /><span className="screen-kicker">{isAndroid ? "Android 基线" : "HarmonyOS · ArkUI"}</span><h4>{frame.title}</h4><p className="screen-subtitle">{frame.subtitle}</p><div className="screen-metric" style={{ color: frame.accent }}>{frame.metric ?? "QC"}</div><div className="screen-card"><span className="screen-card-dot" style={{ background: frame.accent }} /><span>{frame.detail}</span></div><div className="screen-actions"><i /><i /><i /></div><div className="screen-nav"><span className="active" /><span /><span /></div></div><div className="device-home-indicator" /></div></div><div className="emulator-foot"><div className="emulator-step"><span className="step-index">{String(frameIndex + 1).padStart(2, "0")}</span><span><b>{stream.currentStep === "等待开始" ? frame.detail : stream.currentStep}</b><small>语义测试步骤 · {frameIndex + 1}/{stream.frames.length}</small></span></div><div className="emulator-controls"><button onClick={() => setPlaying((value) => !value)} aria-label={playing ? "暂停" : "播放"}>{playing ? "Ⅱ" : "▶"}</button><button onClick={() => setFrameIndex((value) => (value + 1) % Math.max(1, stream.frames.length))}>→</button></div></div></div>;
}

function AgentTimeline({ phase }: { phase: Phase }) {
  const events = phase.events.slice(-10).reverse();
  const sessionId = phase.execution?.sessionId;
  return <div className="timeline-panel"><div className="timeline-heading"><div><h3>执行时间线</h3></div><span className="event-live"><i /> {phase.execution?.mode === "codearts-agentteam" ? (phase.execution.status === "running" || phase.execution.status === "starting" ? "CodeArts 实时" : "CodeArts 已归档") : phase.status === "running" ? "演示实时" : "演示已固化"}</span></div>{events.length ? <div className="timeline-list">{events.map((event) => <div className="timeline-event" key={event.id}><span className={`timeline-icon event-${event.type}`}>{event.type === "thinking" ? "•" : event.type === "tool" ? "‹›" : event.type === "build" ? "≡" : event.type === "test" ? "✓" : "·"}</span><div><b>{event.agent}</b><p>{event.message}</p><small>{formatTime(event.timestamp)}</small></div></div>)}</div> : <div className="timeline-empty"><span>·</span><p>等待 Agent Team 开始工作<br /><small>阶段启动后会显示实时事件</small></p></div>}<div className="timeline-footer"><span>Session</span><code>{sessionId ?? "尚未创建真实会话"}</code>{sessionId && <button onClick={() => navigator.clipboard?.writeText(sessionId)}>复制</button>}</div></div>;
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
  if (!isReal) return <div className="run-controls"><div className="side-panel-heading"><span className="eyebrow">运行控制</span><span className="secure-label">DEMO</span></div><div className="control-row"><span>当前 revision</span><b>{phase.revision}.0</b></div><div className="control-row"><span>运行模式</span><b className="muted-value">本地演示</b></div><div className="control-row"><span>数据来源</span><b className="muted-value">固定数据</b></div><button className="outline-button" onClick={() => mockService.resetDemo(project.id)}>↻ 从头播放示例</button></div>;
  return <div className="run-controls"><div className="side-panel-heading"><span className="eyebrow">运行控制</span><span className="secure-label">{project.demo ? "DEMO" : "LIVE"}</span></div><div className="control-row"><span>当前 revision</span><b>{phase.revision}.0</b></div><div className="control-row"><span>事件数量</span><b>{phase.events.length}</b></div><div className="control-row"><span>运行模式</span><b className={project.demo ? "muted-value" : "mint-text"}>{project.demo ? "本地演示" : "CodeArts Space / AgentTeam"}</b></div><div className="control-row"><span>会话状态</span><b>{phase.execution?.sessionId ? phase.execution.status : "未启动"}</b></div><button className="codearts-run-button" onClick={runWithCodeArts} disabled={runningCodeArts || project.demo}>{runningCodeArts ? "CodeArts AgentTeam 推理中…" : project.demo ? "演示项目不可发起真实构建" : "启动真实 AgentTeam"}</button>{codeArtsMessage && <p className="codearts-message">{codeArtsMessage}</p>}{project.demo && <button className="outline-button" onClick={() => mockService.resetDemo(project.id)}>↻ 从头播放示例</button>}</div>;
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
