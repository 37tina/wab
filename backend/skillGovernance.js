// Skill 治理：智能体可提交 skill 修改提案，人工审核通过后才写入文件。
// 对齐 controller skill 的 TOOL_GAP 冻结语义：正式 run 期间改 skill 须关 run → 修 → 新开 run。
const { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } = require("node:fs");
const { join, normalize, extname } = require("node:path");

const SKILL_ROOT = process.env.SKILL_ROOT
  ? normalize(process.env.SKILL_ROOT)
  : join(__dirname, "..", "skill");
const PROPOSAL_STORE = join(__dirname, "skill-proposals.json");
const ALLOWED_EXT = new Set([".md", ".yaml", ".yml", ".json", ".txt", ".csv"]);

function listSkillTree() {
  const skills = [];
  try {
    for (const entry of readdirSync(SKILL_ROOT)) {
      const dir = join(SKILL_ROOT, entry);
      if (!statSync(dir).isDirectory()) continue;
      const files = [];
      const walk = (rel, depth) => {
        if (depth > 3) return;
        const abs = join(SKILL_ROOT, rel);
        for (const name of readdirSync(abs)) {
          const childAbs = join(abs, name);
          const childRel = `${rel}/${name}`;
          const stats = statSync(childAbs);
          if (stats.isDirectory()) {
            if (name === "__pycache__" || name.startsWith(".")) continue;
            walk(childRel, depth + 1);
          } else if (ALLOWED_EXT.has(extname(name)) && stats.size < 300_000) {
            files.push({ path: childRel, size: stats.size });
          }
        }
      };
      walk(entry, 0);
      files.sort((a, b) => a.path.localeCompare(b.path));
      skills.push({ skill: entry, files });
    }
  } catch (error) {
    throw new Error("读取 skill 目录失败：" + error.message);
  }
  return skills;
}

function resolveSkillFile(relPath) {
  const normalized = normalize(String(relPath ?? "")).replace(/\\/g, "/");
  const abs = normalize(join(SKILL_ROOT, normalized));
  if (!abs.startsWith(normalize(SKILL_ROOT))) throw new Error("非法路径");
  if (!existsSync(abs) || !statSync(abs).isFile()) throw new Error("文件不存在：" + normalized);
  if (!ALLOWED_EXT.has(extname(abs))) throw new Error("仅支持文本类 skill 文件（md/yaml/json/txt/csv）");
  return { abs, rel: normalized };
}

function readSkillFile(relPath) {
  const { abs } = resolveSkillFile(relPath);
  return readFileSync(abs, "utf8");
}

// ---- 提案存储（pending → approved / rejected） ----

function loadProposals() {
  try {
    const data = JSON.parse(readFileSync(PROPOSAL_STORE, "utf8"));
    return Array.isArray(data.proposals) ? data.proposals : [];
  } catch {
    return [];
  }
}

function saveProposals(proposals) {
  writeFileSync(PROPOSAL_STORE, JSON.stringify({ proposals }, null, 2), "utf8");
}

function createProposal({ path: relPath, newContent, reason, author }) {
  const { rel } = resolveSkillFile(relPath);
  if (typeof newContent !== "string" || !newContent.trim()) throw new Error("修改内容不能为空");
  if (!String(reason ?? "").trim()) throw new Error("必须填写修改理由");
  const original = readFileSync(join(SKILL_ROOT, rel), "utf8");
  if (original === newContent) throw new Error("新内容与当前文件相同，无需提案");
  const proposals = loadProposals();
  const proposal = {
    id: `skp_${Date.now().toString(36)}_${proposals.length + 1}`,
    path: rel,
    author: String(author ?? "agent").trim() || "agent",
    reason: String(reason).trim(),
    status: "pending",
    createdAt: new Date().toISOString(),
    decidedAt: null,
    reviewerComment: "",
    originalLines: original.split("\n").length,
    newLines: newContent.split("\n").length,
    // 内容单独存放，避免列表接口把大文本带出去
    content: newContent,
  };
  proposals.unshift(proposal);
  saveProposals(proposals);
  return { id: proposal.id, path: rel, status: proposal.status };
}

function decideProposal(id, decision, comment = "") {
  const proposals = loadProposals();
  const proposal = proposals.find((item) => item.id === id);
  if (!proposal) throw new Error("提案不存在：" + id);
  if (proposal.status !== "pending") throw new Error(`提案已处理（${proposal.status}），不能重复决定`);
  if (decision === "approved") {
    const { abs } = resolveSkillFile(proposal.path);
    // 落盘前备份；提示 TOOL_GAP：正式 run 中改 skill 应先关 run
    const backup = `${abs}.bak-${Date.now()}`;
    copyFileSync(abs, backup);
    writeFileSync(abs, proposal.content, "utf8");
    proposal.backupFile = backup;
  }
  proposal.status = decision;
  proposal.reviewerComment = String(comment ?? "").trim();
  proposal.decidedAt = new Date().toISOString();
  saveProposals(proposals);
  return { id, status: decision, backupFile: proposal.backupFile, note: decision === "approved" ? "已写入 skill 文件（原文件已备份）。注意：若正在正式 run 中，按 TOOL_GAP 规则应关闭当前 run 后新开 run。" : undefined };
}

function listProposals() {
  return loadProposals().map(({ content, ...rest }) => ({ ...rest, hasContent: true }));
}

function getProposalContent(id) {
  const proposal = loadProposals().find((item) => item.id === id);
  if (!proposal) throw new Error("提案不存在：" + id);
  return { id, path: proposal.path, content: proposal.content, reason: proposal.reason };
}

module.exports = { SKILL_ROOT, listSkillTree, readSkillFile, createProposal, decideProposal, listProposals, getProposalContent };
