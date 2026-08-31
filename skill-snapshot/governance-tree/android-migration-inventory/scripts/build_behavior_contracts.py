# -*- coding: utf-8 -*-
"""build_behavior_contracts -- 行为契约（Behavior Contract）骨架构建器（2.1 新增）。

消费 run 目录 `candidates/` 现有候选表（inventory / business-rules /
navigation-relations / risk-probes / field-options，格式见 gmi_generate.py）
与 `scope.json` 的 `migration_scope.key_business_capabilities`，产出
`behavior-contracts.csv` 候选骨架：

  * 机器可推导列由本脚本确定性填充：
    bc_id / feature_id / page_ref / business_computation_refs / impact /
    evidence_class / source_refs
  * 语义列留空，由 LLM 按既有「分片填充」约定逐行填写
    （user_intent / pre_state / semantic_input / operation /
      data_state_change / observable_result / persistence_targets /
      external_side_effects），
    填完后跑 `--validate` 收口。

v4 七段结构（用户修正 2）：BC 语义描述按七段组织——
  intent(user_intent) / precondition(pre_state) / semantic_input /
  expected_state_change(data_state_change) / observable_result /
  persistence(persistence_targets) / side_effect(external_side_effects)。
semantic_input 为 v4 新增可选列（尾部追加，DictReader 兼容）：描述触发该
行为所需的语义输入（如「选择 English」「输入标题 TEST-X」「勾选重复规则」），
骨架阶段留空由 LLM 分片填充；--validate 对 RUNTIME_REQUIRED 行强制非空
（收敛式重构批次1 #81：RUNTIME_REQUIRED 十字段强制完整，缺值 →
INVALID_CONTRACT FAIL，不再仅警告），表头固定含该列（fail-closed）。

evidence_class 保守白名单（命中即 RUNTIME_REQUIRED/high）：
  增删改（CRUD）、设置持久化、语言、主题、权限、同步、关键业务计算；
  feature 命中 scope.key_business_capabilities 一律 RUNTIME_REQUIRED/high。
  白名单不是封闭集：源码识别出的其他高影响 intent 由 LLM 填行时升级为
  impact=high + RUNTIME_REQUIRED（--validate 允许该方向的手动升级）。

用法：
  python build_behavior_contracts.py --workspace <run 目录>
        [--scope <scope.json>]        # 缺省自动找 <ws>/scope.json、<ws>/controller/scope.json
        [--out <behavior-contracts.csv>]   # 缺省 <ws>/behavior-contracts.csv
        [--features A,B]              # 显式 included features（覆盖 scope）
        [--validate]                  # 校验已有 behavior-contracts.csv（不重写）

fail-closed 校验判据（生成路径自校验与 --validate 共用 validate_bc_rows）：
  1. 表头必须与本文件 BC_FIELDS 完全一致（列固定）；
  2. bc_id 必填且全局唯一：空 bc_id → FAIL；重复 bc_id → FAIL 并报全部重复行号；
  3. feature_id / page_ref / user_intent / operation / source_refs 必填，缺失 → FAIL；
  4. evidence_class ∈ {STATIC_ONLY, RUNTIME_REQUIRED}，impact ∈ {high, normal}；
     impact=high 必须 evidence_class=RUNTIME_REQUIRED，否则 FAIL；
  5. page_ref 必须精确等于候选表（candidates/ 下 inventory /
     navigation-relations 等）中的正式 Page-ID：页面名称、模糊 token、
     hash 猜测值一律拒绝，不在集合中 → FAIL 并报具体行与值；
  6. 每个 included feature ≥ 1 行；
  7. source_refs 每项必须可解析为 `file:line`（行号为正整数）；
  8. 收敛式重构批次1（#81）：RUNTIME_REQUIRED 行十字段强制非空——
     user_intent / pre_state / semantic_input / operation_steps /
     data_state_change / observable_result / persistence_targets /
     external_side_effects / result_assertions / source_refs，缺值 →
     INVALID_CONTRACT FAIL（--validate 退出非零）；external_side_effects
     无副作用时写 NONE 占位也算填；STATIC_ONLY 行不强制（保持宽松）；
     骨架生成路径走 skeleton 豁免（骨架语义列本就留空待 LLM 分片填充）。
不合格行逐条报错并 exit 1。

注：骨架生成阶段语义列（user_intent/operation）按设计留空待 LLM 分片
填充（既有输出格式不变），故生成路径自校验对这两列走 skeleton 豁免；
其余全部判据两路径完全一致，生成器自身拒绝输出坏 BC。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BC_FIELDS = [
    "bc_id", "feature_id", "page_ref", "user_intent", "pre_state", "operation",
    "data_state_change", "business_computation_refs", "observable_result",
    "persistence_targets", "external_side_effects", "evidence_class", "impact",
    "source_refs",
    # v5.0 行为链扩展列（SKILL v3 步骤 4/6）：JSON-in-CSV，LLM 分片填充，
    # gmi_runtime --mode chain 消费（无列/为空 → 链降级仅导航+快照）。
    "operation_steps", "result_assertions",
    # v4 七段结构新增可选列（尾部追加，DictReader 兼容）：语义输入描述，
    # 骨架留空由 LLM 分片填充；--validate 缺值仅警告不阻断。
    "semantic_input",
]
EVIDENCE_CLASSES = ("STATIC_ONLY", "RUNTIME_REQUIRED")
IMPACTS = ("high", "normal")

# 收敛式重构批次1（任务 #81）：RUNTIME_REQUIRED 行强制完整的十字段。
# external_side_effects 无副作用时写 NONE 占位也算填（大小写不敏感）；
# 其余字段空 -> INVALID_CONTRACT 错误（--validate 退出非零）。
RUNTIME_REQUIRED_MANDATORY_FIELDS = [
    "user_intent", "pre_state", "semantic_input", "operation_steps",
    "data_state_change", "observable_result", "persistence_targets",
    "external_side_effects", "result_assertions", "source_refs",
]
# external_side_effects 合法占位（不算"空"）
_SIDE_EFFECT_NONE_PLACEHOLDER = "NONE"

# RUNTIME_REQUIRED 保守白名单关键词（不是封闭集，见模块注释）
_SEED_CRUD = ("create", "add", "insert", "save", "update", "edit", "modify", "delete",
              "remove", "swipetodelete", "新增", "添加", "新建", "删除", "修改", "编辑", "保存")
_SEED_PERSIST = ("setting", "preference", "datastore", "sharedpref", "persist", "room",
                 "sqlite", "database", "设置", "偏好", "持久化", "存储")
_SEED_LANGUAGE = ("language", "locale", "i18n", "语言")
_SEED_THEME = ("theme", "dark", "night", "主题", "深色", "夜间")
_SEED_PERMISSION = ("permission", "权限")
_SEED_SYNC = ("sync", "synchron", "backup", "restore", "同步", "备份", "恢复")
_SEED_COMPUTE = ("calculat", "comput", "sum", "progress", "统计", "计算", "汇总")
_WHITELIST_SEEDS = (_SEED_CRUD + _SEED_PERSIST + _SEED_LANGUAGE + _SEED_THEME +
                    _SEED_PERMISSION + _SEED_SYNC + _SEED_COMPUTE)

_FILE_LINE_RE = re.compile(r"^(?P<file>[^:\s][^:]*\.[A-Za-z0-9]+):(?P<line>\d+)$")


# ---------------------------------------------------------------------------
# io helpers（与 gmi_generate.py 同风格）
# ---------------------------------------------------------------------------

def _csv_read(p: Path) -> List[Dict[str, str]]:
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _csv_write(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as h:
            w = csv.DictWriter(h, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _find_scope_json(workspace: Path, explicit: Optional[str]) -> Optional[Path]:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.exists():
            raise SystemExit(f"[bc] --scope not found: {p}")
        return p
    for cand in (workspace / "scope.json",
                 workspace / "controller" / "scope.json"):
        if cand.exists():
            return cand
    return None


def _load_scope(scope_path: Optional[Path]) -> Tuple[List[str], List[str]]:
    """返回 (key_business_capabilities, included_features)。"""
    if scope_path is None:
        return [], []
    try:
        scope = json.loads(scope_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa
        raise SystemExit(f"[bc] scope.json 解析失败 {scope_path}: {e}")
    ms = scope.get("migration_scope", {}) or {}
    caps = [str(c).strip() for c in (ms.get("key_business_capabilities") or []) if str(c).strip()]
    feats = [str(f).strip() for f in (ms.get("included_features") or []) if str(f).strip()]
    return caps, feats


def _seed_hit(text: str) -> str:
    """返回命中的白名单种子类别（空串=未命中）。"""
    t = (text or "").lower()
    if not t:
        return ""
    for seed in _SEED_CRUD:
        if seed in t:
            return "crud"
    for seed in _SEED_PERSIST:
        if seed in t:
            return "persistence"
    for seed in _SEED_LANGUAGE:
        if seed in t:
            return "language"
    for seed in _SEED_THEME:
        if seed in t:
            return "theme"
    for seed in _SEED_PERMISSION:
        if seed in t:
            return "permission"
    for seed in _SEED_SYNC:
        if seed in t:
            return "sync"
    for seed in _SEED_COMPUTE:
        if seed in t:
            return "computation"
    return ""


def _cap_hit(text: str, caps: List[str]) -> bool:
    tl = (text or "").lower()
    return bool(tl) and any(c.lower() in tl or tl in c.lower() for c in caps)


# ---------------------------------------------------------------------------
# 校验（生成路径自校验与 --validate 共用；fail-closed）
# ---------------------------------------------------------------------------

def parse_file_line(ref: str) -> Optional[Tuple[str, int]]:
    """`file:line` 解析；不可解析返回 None。"""
    m = _FILE_LINE_RE.match((ref or "").strip())
    if not m:
        return None
    line = int(m.group("line"))
    if line < 1:
        return None
    return m.group("file"), line


def validate_source_refs(value: str) -> List[str]:
    """source_refs（`;` 分隔）逐项解析；返回解析出的 `file:line` 列表，空=非法。"""
    out: List[str] = []
    for ref in (value or "").split(";"):
        ref = ref.strip()
        if not ref:
            continue
        if parse_file_line(ref) is None:
            return []
        out.append(ref)
    return out


def collect_candidate_page_ids(cands: Path) -> set:
    """候选表中全部正式 Page-ID 的集合（page_ref 精确匹配用）。

    来源：inventory / navigation-relations（from/to）/ business-rules /
    risk-probes / field-options 候选表。页面名称、模糊 token、hash 猜测值
    不会出现在该集合中。
    """
    page_ids: set = set()
    for r in _csv_read(cands / "inventory.candidates.csv"):
        pid = (r.get("page_id") or "").strip()
        if pid:
            page_ids.add(pid)
    for r in _csv_read(cands / "navigation-relations.candidates.csv"):
        for col in ("from_page_id", "to_page_id"):
            pid = (r.get(col) or "").strip()
            if pid:
                page_ids.add(pid)
    for name in ("business-rules.candidates.csv", "risk-probes.candidates.csv",
                 "field-options.candidates.csv"):
        for r in _csv_read(cands / name):
            pid = (r.get("page_id") or "").strip()
            if pid:
                page_ids.add(pid)
    return page_ids


def validate_bc_rows(rows: List[Dict[str, str]], included: List[str],
                     page_ids: set, skeleton_mode: bool = False) -> List[str]:
    """逐行校验（生成路径与 --validate 共用）；返回错误列表（空=通过）。

    skeleton_mode=True 仅用于骨架生成阶段：语义列 user_intent/operation
    按设计留空待 LLM 分片填充（既有输出格式不变），故该两列暂不强制；
    其余全部判据（含 bc_id 唯一性、必填列、page_ref 精确匹配、
    impact=high→RUNTIME_REQUIRED）两路径完全一致。
    """
    errors: List[str] = []
    bc_lines: Dict[str, List[int]] = {}
    required = ["feature_id", "page_ref", "source_refs"]
    if not skeleton_mode:
        required += ["user_intent", "operation"]
    for i, r in enumerate(rows, start=2):  # 行号对齐 CSV（1=表头）
        bc_raw = (r.get("bc_id") or "").strip()
        bc = bc_raw or f"<row {i}>"
        if not bc_raw:
            errors.append(f"L{i}: 必填列 bc_id 为空（bc_id 不允许为空）")
        else:
            bc_lines.setdefault(bc_raw, []).append(i)
        for col in required:
            if not (r.get(col) or "").strip():
                errors.append(f"L{i} {bc}: 必填列 {col} 为空")
        ec = (r.get("evidence_class") or "").strip()
        if ec not in EVIDENCE_CLASSES:
            errors.append(f"L{i} {bc}: evidence_class={ec!r} 非法（应为 {'|'.join(EVIDENCE_CLASSES)}）")
        imp = (r.get("impact") or "").strip()
        if imp not in IMPACTS:
            errors.append(f"L{i} {bc}: impact={imp!r} 非法（应为 {'|'.join(IMPACTS)}）")
        if imp == "high" and ec != "RUNTIME_REQUIRED":
            errors.append(f"L{i} {bc}: impact=high 必须 evidence_class=RUNTIME_REQUIRED"
                          f"（当前 {ec!r}）")
        # 收敛式重构批次1（#81）：RUNTIME_REQUIRED 十字段强制完整（仅收口路径；
        # 骨架生成 skeleton_mode 豁免——语义列留空待 LLM 分片填充是设计内）。
        if not skeleton_mode and ec == "RUNTIME_REQUIRED":
            for col in RUNTIME_REQUIRED_MANDATORY_FIELDS:
                val = (r.get(col) or "").strip()
                if col == "external_side_effects" and \
                        val.upper() == _SIDE_EFFECT_NONE_PLACEHOLDER:
                    continue  # NONE 占位 = 显式声明"无副作用"，算填
                if not val:
                    hint = ("（无副作用时写 NONE 占位）"
                            if col == "external_side_effects" else "")
                    errors.append(f"L{i} {bc}: INVALID_CONTRACT: RUNTIME_REQUIRED "
                                  f"必填字段 {col} 为空{hint}")
        page_ref = (r.get("page_ref") or "").strip()
        if page_ref and page_ref not in page_ids:
            errors.append(f"L{i} {bc}: page_ref={page_ref!r} 不是候选表正式 Page-ID"
                          f"（拒绝页面名称/模糊 token/hash 猜测值；"
                          f"候选表共 {len(page_ids)} 个 Page-ID）")
        refs = validate_source_refs(r.get("source_refs", ""))
        if not refs:
            errors.append(f"L{i} {bc}: source_refs 必须为可解析的 file:line（`;` 分隔）："
                          f"{(r.get('source_refs') or '')[:80]!r}")
        # v5.0 行为链扩展列：非空必须可解析为 JSON 数组（gmi_runtime json_col_broken
        # 同口径）；空=允许（该链降级仅导航+快照，不 fail）。
        for col in ("operation_steps", "result_assertions"):
            raw = (r.get(col) or "").strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                errors.append(f"L{i} {bc}: {col} 非空但不是合法 JSON（JSON-in-CSV）")
                continue
            if not isinstance(data, list):
                errors.append(f"L{i} {bc}: {col} 必须是 JSON 数组（步骤/断言序列）")
                continue
            # 提交前自检 2-A（最小修复）：P2 生成侧断言一律 required——
            # optional:true 豁免只属于 P4 重放侧（且有 Gate 4 receipt/probe 兜底）；
            # LLM 分片填充不得借 optional 把 required 断言降级成可静默跳过。
            if col == "result_assertions" and ec == "RUNTIME_REQUIRED":
                marked = [
                    item for item in data if isinstance(item, dict) and (
                        item.get("optional") is True
                        or str(item.get("optional", "")).strip().lower() == "true")
                ]
                if marked:
                    errors.append(
                        f"L{i} {bc}: INVALID_CONTRACT: RUNTIME_REQUIRED 断言不得标记 "
                        f"optional:true（{len(marked)} 处——P2 断言一律 required；"
                        "豁免只属于 P4 重放侧且需登记）")
    for bc_raw, lines in bc_lines.items():
        if len(lines) > 1:
            errors.append(f"bc_id 重复：{bc_raw!r} 出现在行 "
                          f"{', '.join(f'L{n}' for n in lines)}（bc_id 必须全局唯一）")
    if included:
        covered = {(r.get("feature_id") or "").strip() for r in rows}
        for feat in included:
            if feat not in covered:
                errors.append(f"feature {feat}: 0 行（每个 included feature 至少 1 条 BC）")
    return errors



# ---------------------------------------------------------------------------
# 骨架构建
# ---------------------------------------------------------------------------

def build_rows(cands: Path, caps: List[str]) -> List[Dict[str, Any]]:
    inv = _csv_read(cands / "inventory.candidates.csv")
    brs = _csv_read(cands / "business-rules.candidates.csv")
    navs = _csv_read(cands / "navigation-relations.candidates.csv")
    risks = _csv_read(cands / "risk-probes.candidates.csv")
    opts = _csv_read(cands / "field-options.candidates.csv")

    # page_id -> feature_id 映射（来自 inventory 候选）
    feat_by_page: Dict[str, str] = {}
    for r in inv:
        if r.get("page_id") and r.get("feature_id"):
            feat_by_page.setdefault(r["page_id"], r["feature_id"])
    # page_id -> business-rule candidate_ids
    rules_by_page: Dict[str, List[str]] = {}
    for r in brs:
        pid = r.get("page_id", "")
        cid = r.get("candidate_id", "")
        if pid and cid:
            rules_by_page.setdefault(pid, []).append(cid)

    rows: List[Dict[str, Any]] = []
    seq = 0
    seen: set = set()
    # source_ref 不可解析为 file:line 的候选行：跳过并显式记录（不静默丢弃，
    # 也不让整盘生成失败——这类行仍由 runtime 任务覆盖，见 static-analysis/runtime-tasks.json）
    skipped: List[Tuple[str, str, str]] = []

    def emit(feature_id: str, page_ref: str, text_signal: str,
             source_refs: List[str], rule_refs: List[str],
             force_high: bool = False) -> None:
        nonlocal seq
        refs = [s for s in source_refs if validate_source_refs(s)]
        if not refs:
            skipped.append((feature_id, page_ref, ";".join(source_refs)))
            return
        key = (feature_id, page_ref, ";".join(sorted(refs)))
        if key in seen:
            return
        seen.add(key)
        seq += 1
        cap = _cap_hit(f"{feature_id} {page_ref} {text_signal}", caps)
        seed = _seed_hit(text_signal)
        high = force_high or cap or seed in ("crud", "persistence", "language",
                                             "theme", "permission", "sync")
        rows.append({
            "bc_id": f"BC-{seq:04d}",
            "feature_id": feature_id,
            "page_ref": page_ref,
            # 语义列：留待 LLM 分片填充（--validate 允许为空）
            "user_intent": "", "pre_state": "", "operation": "",
            "data_state_change": "", "observable_result": "",
            "persistence_targets": "", "external_side_effects": "",
            "business_computation_refs": ";".join(sorted(set(rule_refs))),
            "evidence_class": "RUNTIME_REQUIRED" if (high or cap or seed == "computation")
                              else "STATIC_ONLY",
            "impact": "high" if (high or cap) else "normal",
            "source_refs": ";".join(refs),
            # v4 七段结构：语义输入描述留待 LLM 分片填充
            "semantic_input": "",
        })

    # 1) inventory：每个 (feature, page) 一条页面级行为契约
    done_pages: set = set()
    for r in inv:
        feat, page = r.get("feature_id", ""), r.get("page_id", "")
        if not feat or not page or (feat, page) in done_pages:
            continue
        done_pages.add((feat, page))
        emit(feat, page,
             f"{r.get('state_expression', '')} {r.get('entry_condition', '')}",
             [r.get("source_ref", "")], rules_by_page.get(page, []))

    # 2) navigation-relations：每条导航关系一条契约（跳转=用户意图）
    for r in navs:
        page = r.get("from_page_id", "")
        if not page:
            continue
        feat = feat_by_page.get(page) or feat_by_page.get(r.get("to_page_id", ""), "") or ""
        if not feat:
            continue
        signal = f"{r.get('trigger', '')} {r.get('action', '')} {r.get('relation_type', '')}"
        emit(feat, page, signal, [r.get("source_ref", "")], rules_by_page.get(page, []))

    # 3) field-options：设置/选项树（偏好持久化白名单）
    done_opts: set = set()
    for r in opts:
        page = r.get("page_id", "")
        grp = r.get("group", "") or r.get("group_key", "")
        if not page or not grp or (page, grp) in done_opts:
            continue
        done_opts.add((page, grp))
        feat = feat_by_page.get(page, "")
        if not feat:
            continue
        signal = f"{grp} {r.get('summary', '')} settings"
        emit(feat, page, signal, [r.get("source_ref", "")], rules_by_page.get(page, []))

    # 4) risk-probes：高危信号（severity high/critical）强制 RUNTIME_REQUIRED
    done_risk: set = set()
    for r in risks:
        sev = (r.get("severity", "") or "").lower()
        if sev not in ("high", "critical"):
            continue
        page = r.get("page_id", "")
        sig = f"{r.get('category', '')} {r.get('signal', '')}"
        key = (page, sig)
        if not page or key in done_risk:
            continue
        done_risk.add(key)
        feat = feat_by_page.get(page, "")
        if not feat:
            continue
        f, ln = r.get("file", ""), r.get("line", "")
        ref = f"{f}:{ln}" if f and ln else ""
        emit(feat, page, sig, [ref], rules_by_page.get(page, []), force_high=True)

    return rows, skipped


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="build behavior-contracts.csv skeleton (2.1)")
    ap.add_argument("--workspace", required=True, help="run 目录（含 candidates/）")
    ap.add_argument("--scope", default=None,
                    help="scope.json 路径（缺省自动找 <ws>/scope.json、<ws>/controller/scope.json）")
    ap.add_argument("--out", default=None,
                    help="输出 CSV（缺省 <workspace>/behavior-contracts.csv）")
    ap.add_argument("--features", default="",
                    help="included features 逗号分隔（覆盖 scope.json；用于 --validate）")
    ap.add_argument("--validate", action="store_true",
                    help="只校验已有 behavior-contracts.csv，不重写")
    args = ap.parse_args()

    ws = Path(args.workspace).resolve()
    cands = ws / "candidates"
    out = Path(args.out).resolve() if args.out else ws / "behavior-contracts.csv"
    explicit_feats = [f.strip() for f in args.features.split(",") if f.strip()]

    caps, scope_feats = _load_scope(_find_scope_json(ws, args.scope))
    included = explicit_feats or scope_feats
    if not included:
        # 回退：candidates.json 或 inventory 候选的 feature 并集
        cj = cands / "candidates.json"
        if cj.exists():
            try:
                included = [str(f) for f in json.loads(cj.read_text(encoding="utf-8")).get("features", [])]
            except Exception:  # noqa
                included = []
        if not included:
            included = sorted({r.get("feature_id", "") for r in _csv_read(cands / "inventory.candidates.csv")
                               if r.get("feature_id")})

    if args.validate:
        if not out.exists():
            raise SystemExit(f"[bc] --validate: 未找到 {out}")
        with open(out, encoding="utf-8-sig") as f:
            header = f.readline().rstrip("\r\n").split(",")
        if header != BC_FIELDS:
            raise SystemExit(f"[bc] 表头不符（列固定）：\n  expect={BC_FIELDS}\n  actual={header}")
        # fail-closed：page_ref 校验依赖候选表正式 Page-ID，缺失即 FAIL。
        if not cands.is_dir():
            raise SystemExit(f"[bc] validate FAIL: candidates/ 不存在：{cands}"
                             f"（无法取得候选表 Page-ID 集合，fail-closed）")
        page_ids = collect_candidate_page_ids(cands)
        if not page_ids:
            raise SystemExit(f"[bc] validate FAIL: 候选表未解析出任何正式 Page-ID：{cands}"
                             f"（fail-closed）")
        rows = _csv_read(out)
        errors = validate_bc_rows(rows, included, page_ids)
        rr = sum(1 for r in rows if (r.get("evidence_class") or "") == "RUNTIME_REQUIRED")
        # 收敛式重构批次1（#81）：RUNTIME_REQUIRED 十字段强制完整——
        # semantic_input 等缺值从 WARNING 升级为 INVALID_CONTRACT error
        # （validate_bc_rows 内判定），此处只统计提示口径。
        incomplete = sum(1 for e in errors if "INVALID_CONTRACT" in e)
        print(f"[bc] validate {out.name}: rows={len(rows)} runtime_required={rr}"
              f" features_covered={len({r.get('feature_id') for r in rows})}"
              f" invalid_contracts={incomplete}")
        if errors:
            for e in errors[:50]:
                print(f"[bc] ERROR {e}")
            raise SystemExit(f"[bc] validate FAIL: {len(errors)} error(s)")
        print("[bc] validate OK")
        return 0

    if not cands.is_dir():
        raise SystemExit(f"[bc] candidates/ 不存在：{cands}（先跑 scripts/gmi.py）")
    page_ids = collect_candidate_page_ids(cands)
    if not page_ids:
        raise SystemExit(f"[bc] fail-closed: 候选表未解析出任何正式 Page-ID：{cands}")
    rows, skipped = build_rows(cands, caps)
    # 生成器自校验：与 --validate 共用 validate_bc_rows；骨架阶段语义列
    # （user_intent/operation）按设计留空待 LLM 填充，走 skeleton 豁免，
    # 其余判据（含 bc_id 唯一性、page_ref 精确匹配、impact=high→RUNTIME_REQUIRED）
    # 全部生效——生成器自身拒绝输出坏 BC，不留到 Gate 才发现。
    errors = validate_bc_rows(rows, [], page_ids, skeleton_mode=True)
    if errors:
        for e in errors[:50]:
            print(f"[bc] ERROR {e}")
        raise SystemExit(f"[bc] 生成路径自校验 FAIL: {len(errors)} error(s)，拒绝输出")
    _csv_write(out, BC_FIELDS, rows)
    rr = sum(1 for r in rows if r["evidence_class"] == "RUNTIME_REQUIRED")
    hi = sum(1 for r in rows if r["impact"] == "high")
    print(f"[bc] caps={len(caps)} included={len(included)} rows={len(rows)}"
          f" runtime_required={rr} high={hi} out={out}")
    if skipped:
        print(f"[bc] WARNING: {len(skipped)} candidate row(s) skipped (source_ref not file:line parsable):",
              file=sys.stderr)
        for feat, page, ref in skipped[:100]:
            print(f"[bc] SKIP feature={feat} page={page} source_ref={ref!r}", file=sys.stderr)
        if len(skipped) > 100:
            print(f"[bc] ... and {len(skipped) - 100} more", file=sys.stderr)
    print("[bc] 骨架已生成：语义列（含 v4 semantic_input 与行为链扩展列）留待 LLM "
          "分片填充，填完跑 --validate 收口（RUNTIME_REQUIRED 行十字段强制完整，"
          "缺值 → INVALID_CONTRACT FAIL；external_side_effects 无副作用写 NONE）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
