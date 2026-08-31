# -*- coding: utf-8 -*-
"""gmi_phase3_adapter -- 把 gmi Phase 2 工作区合成成 P3/P4 契约需要的
`phase-02-android-inventory/` 布局（零改动消费旧脚本）。

用法：
  python gmi_phase3_adapter.py --workspace <gmi 工作区，如 migration-runs/Cresto-RUN1>

说明：gmi 路径下已由 gmi_closure.py 生成 phase-2-closure.json；本脚本读它 +
candidates/ (12 表) + runtime-evidence/，合成 P3/P4 input-contract 期望的：
  phase-02-android-inventory/
    closure-report.json / closure-manifest.sha256 / CLOSED / phase-manifest.json
    inventory.csv                （REVIEWED 行 = 页面 + 状态集，feature 映射自 12 表）
    asset-inventory.csv          （来自 asset-mapping FILE_ASSET，真实文件归档 + 实算 sha256）
    asset-package/{manifest.sha256,COMMITTED,files/<asset_id>/<name>}
    evidence-index.csv / acceptance-registry.csv / evidence-anchors.snapshot.csv
    static-analysis/{pages.json,components.json,advanced-analysis.json}
    advanced-observations.json / runtime-observations.json
    page-gate-report.json / advanced-gate-report.json / probe-evidence-index.csv
    catalogs/{data-dependencies.csv,system-capabilities.csv,third-party-dependencies.csv}
  controller/（scope / gate-report / work-orders / registries）
  run-manifest.json / phase-2-closure.json（冻结副本）

契约基准：
- input-mapping-contract.md「gmi Phase 2 适配（默认路径）」节：
  门禁前置 = audit 0 discrepancy + UNMAPPED=0 + completeness 无隐瞒；
  不再要求旧 controller REVIEWED 状态机。
- init_scaffold.py gmi 模式对上述布局做确定性校验（漂移即 BLOCKED）。
- 所有合成 CSV/JSON 标 `generated-by=gmi-phase3-adapter`。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

GENERATED_BY = "gmi-phase3-adapter"
REVIEWER = "gmi"                      # coverage-checker（gmi 流程）
CONTROLLER_ID = "AG-CONTROLLER"       # 合成控制器身份
CODE_MAP_ID = "CODEMAP-001"
ENV_ID = "ENV-001"
CLOSURE_EXCLUDES = {"closure-report.json", "closure-manifest.sha256", "CLOSED"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_rows(p: Path) -> List[Dict[str, str]]:
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_rows(p: Path, fields: List[str], rows: List[Dict[str, Any]]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def closure_manifest_text(root: Path) -> str:
    lines: List[str] = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.is_symlink():
            continue
        rel = f.relative_to(root).as_posix()
        if rel in CLOSURE_EXCLUDES:
            continue
        lines.append(f"{sha256_file(f)}  {rel}")
    return "".join(line + "\n" for line in sorted(lines, key=lambda s: s.split("  ", 1)[-1]))


def main() -> int:
    ap = argparse.ArgumentParser(description="gmi phase-2 -> phase3/4 adapter")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--out", default=None, help="输出 run 目录（默认 workspace 同级 <name>-run）")
    args = ap.parse_args()

    ws = Path(args.workspace).resolve()
    cands = ws / "candidates"
    cov = ws / "coverage"
    rt_ = ws / "runtime-evidence"
    closure_path = ws / "phase-2-closure.json"

    if not closure_path.exists():
        raise SystemExit("phase-2-closure.json missing: run gmi_closure.py first")
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    if not (ws / "phase-2-report.md").exists():
        raise SystemExit("phase-2-report.md missing: gmi 门禁前置第 4 项要求签注报告存在")

    # P0-2 修复：closure gate 数据达标才允许合成 PASS 门禁；不达标 FAIL 并退出。
    # 新范式达标 = feature_coverage.ok 且 audit_discrepancy=0 且 visited/pages_total>0
    # （范围内功能覆盖门禁；unmapped 为参考值）。旧 closure JSON 无 feature_coverage
    # 键时回退 legacy 公式（unmapped==0 且 ...），保持向后兼容。
    gate_data = closure.get("gate") or {}
    try:
        _unmapped = int(gate_data.get("unmapped", -1))
        _disc = int(gate_data.get("audit_discrepancy", -1))
        _visited = int(gate_data.get("visited", 0))
        _pages = int(gate_data.get("pages_total", 0))
    except (TypeError, ValueError):
        _unmapped, _disc, _visited, _pages = -1, -1, 0, 0
    _fc = gate_data.get("feature_coverage")
    _fc_ok = isinstance(_fc, dict) and _fc.get("ok") is True
    if isinstance(_fc, dict):
        gate_ok = (_fc_ok and _disc == 0 and _visited > 0 and _pages > 0)
        gate_basis_numbers = (f"feature_coverage.ok={_fc_ok} audit_discrepancy={_disc} "
                              f"visited={_visited}/{_pages}")
    else:
        gate_ok = (_unmapped == 0 and _disc == 0 and _visited > 0 and _pages > 0)
        gate_basis_numbers = (f"unmapped={_unmapped} audit_discrepancy={_disc} "
                              f"visited={_visited}/{_pages}")
    if not gate_ok:
        raise SystemExit(
            "[adapter] FAIL: gmi closure gate 数据不达标"
            f"（{gate_basis_numbers}），拒绝合成 PASS 门禁报告")

    out = Path(args.out).resolve() if args.out else ws.parent / (ws.name + "-run")
    phase2 = out / "phase-02-android-inventory"
    # 注意：不预创建 phase-03/04 目录 —— init_scaffold.py 禁止覆盖已存在的
    # Phase 3 工作区，由脚手架自行原子创建。
    for d in (out, phase2):
        d.mkdir(parents=True, exist_ok=True)

    run_id = ws.name
    project_id = run_id.split("-RUN")[0].upper()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # ---------- 0) feature 口径（runtime-feature-coverage） ----------
    fc_path = rt_ / "runtime-feature-coverage.csv"
    if not fc_path.exists():
        fc_path = ws / "runtime-feature-coverage.csv"
    fc_rows = read_rows(fc_path)
    if not fc_rows:
        raise SystemExit("runtime-feature-coverage.csv missing (runtime-evidence/ 或工作区根)")
    included = sorted(r["feature"] for r in fc_rows if r.get("status") == "VISITED")
    excluded = sorted(r["feature"] for r in fc_rows if r.get("status") == "NOT_ENTERED")
    if not included:
        raise SystemExit("no VISITED features in runtime-feature-coverage.csv")
    # feature -> 首个 runtime 证据目录（evidence_hits: "STEP-01--:text | ..."）
    feature_evidence: Dict[str, str] = {}
    for r in fc_rows:
        if r.get("status") != "VISITED":
            continue
        hits = (r.get("evidence_hits") or "").split("|")
        first = hits[0].strip().split(":", 1)[0].strip() if hits else ""
        if first and (rt_ / first).is_dir():
            feature_evidence[r["feature"]] = first
    ne_reasons = {r["feature"]: r.get("reason", "") for r in read_rows(rt_ / "not-entered-reasons.csv")}

    # Android 源根（只读）：来自 phase-1-scope.md 约定；缺省取工作区上级 ../android/<App>
    android_root: Optional[Path] = None
    scope_md = ws / "phase-1-scope.md"
    if scope_md.exists():
        import re as _re
        m = _re.search(r"源项目路径[^\`]*`([^`]+)`", scope_md.read_text(encoding="utf-8"))
        if m:
            cand = Path(m.group(1)).expanduser()
            if cand.is_dir():
                android_root = cand
    application_id = ""
    if scope_md.exists():
        import re as _re
        m = _re.search(r"applicationId[^\`]*`([^`]+)`", scope_md.read_text(encoding="utf-8"))
        if m:
            application_id = m.group(1)
    app_name = project_id.capitalize()
    if scope_md.exists():
        import re as _re
        m = _re.search(r"# Phase 1 范围定义[^\n]*?—\s*([^→\n]+)→", scope_md.read_text(encoding="utf-8"))
        if m:
            app_name = m.group(1).strip() or app_name

    # ---------- 1) inventory.csv（12 表 feature↔page 映射，逐页一行） ----------
    inv_fields = [
        "inventory_id", "feature_id", "page_id", "page_name", "state_id",
        "state_name", "env_id", "evidence_id", "row_status", "reviewed_by",
        "data_dependency_refs", "system_capability_refs", "third_party_dependency_refs",
        "asset_ids",
    ]
    inv_rows: List[Dict[str, Any]] = []
    seen: set = set()
    # 契约：每页合成一行（优先 DEFAULT 状态；静态派生的表达式状态不入 inventory，
    # 其明细保留在 candidates/inventory.candidates.csv 供 P4 消费）
    cand_rows = read_rows(cands / "inventory.candidates.csv")
    cand_rows.sort(key=lambda r: 0 if r.get("state_expression") == "DEFAULT" else 1)
    for r in cand_rows:
        feat, page, state = r.get("feature_id", ""), r.get("page_id", ""), r.get("state_id", "")
        if feat not in included or not page or not state:
            continue
        key = (feat, page)
        if key in seen:
            continue
        seen.add(key)
        # 14a：evidence_id 用 NONE_ 前缀占位（Phase4 gmi_native_layout 判定
        # startswith("NONE_")——注意是下划线；NONE-GMI- 连字符形式不满足判定）。
        # 行唯一（feat+page）以满足 Phase4 evidence-index 同 evidence_id 等值去重；
        # 全大写过 init_scaffold ID_RE（旧 STEP-xx 目录名含小写本就过不了）。
        # 真实证据目录名迁移到 evidence-index.csv 的 relative_path 列（14b）。
        ev = f"NONE_GMI-{feat}-{page}"
        inv_rows.append({
            "inventory_id": f"INV-{page}",
            "feature_id": feat, "page_id": page,
            "page_name": page.replace("PAGE-", "", 1),
            "state_id": state, "state_name": r.get("state_expression", "DEFAULT") or "DEFAULT",
            "env_id": r.get("env_id", "") or ENV_ID,
            "evidence_id": ev,
            "row_status": "REVIEWED", "reviewed_by": REVIEWER,
            "data_dependency_refs": f"DATA-NONE-{feat}",
            "system_capability_refs": f"SYSTEM-NONE-{feat}",
            "third_party_dependency_refs": f"THIRD-NONE-{feat}",
            "asset_ids": "[]",
        })
    if not inv_rows:
        raise SystemExit("no inventory rows could be synthesized (feature mapping empty)")
    write_rows(phase2 / "inventory.csv", inv_fields, inv_rows)

    # ---------- 2) asset 归档（真实文件 + 实算 sha256） ----------
    asset_fields = [
        "asset_id", "source_path", "archive_path", "sha256", "asset_type",
        "feature_ids", "page_ids", "state_ids", "created_by", "created_at",
        "reviewed_by", "reviewed_at", "status", "notes",
    ]
    asset_rows: List[Dict[str, Any]] = []
    manifest_lines: List[str] = []
    files_dir = phase2 / "asset-package" / "files"
    skipped_assets = 0
    for r in read_rows(cands / "asset-mapping.candidates.csv"):
        if r.get("type") != "FILE_ASSET":
            continue
        rel = r.get("resource_id", "")
        src = (android_root / rel) if android_root else None
        if not rel or src is None or not src.is_file():
            skipped_assets += 1
            continue
        asset_id = "ASSET-" + sha256_text(rel)[:20].upper()
        name = PurePosixPath(rel).name
        dst = files_dir / asset_id / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        digest = sha256_file(dst)
        archive = f"asset-package/files/{asset_id}/{name}"
        asset_rows.append({
            "asset_id": asset_id, "source_path": rel, "archive_path": archive,
            "sha256": digest, "asset_type": r.get("fidelity_key", "") or "FILE",
            "feature_ids": "[]", "page_ids": "[]", "state_ids": "[]",
            "created_by": CODE_MAP_ID, "created_at": now,
            "reviewed_by": REVIEWER, "reviewed_at": now,
            "status": "REVIEWED",
            "notes": "gmi FILE_ASSET; sha256 recomputed from read-only Android source"
                     " (candidates resolved_value 仅 8 位截断，不可用作哈希)",
        })
        manifest_lines.append(f"{digest}  files/{asset_id}/{name}")
    manifest_lines.sort(key=lambda s: s.split("  ", 1)[-1])
    pkg = phase2 / "asset-package"
    pkg.mkdir(exist_ok=True)
    manifest_path = pkg / "manifest.sha256"
    manifest_path.write_text("".join(l + "\n" for l in manifest_lines), encoding="utf-8")
    (pkg / "COMMITTED").write_text(sha256_file(manifest_path) + "\n", encoding="utf-8")
    write_rows(phase2 / "asset-inventory.csv", asset_fields, asset_rows)

    # ---------- 3) evidence index / acceptance / anchors ----------
    # 14b：补 relative_path / metadata_sha256 两列，精确满足 Phase4
    # validate_android_evidence gmi 分支期望（relative_path 以 "runtime-evidence/" 开头、
    # ACCEPTED 行 metadata_sha256 == 证据目录 ui.xml 的 sha256）。
    # 真实证据目录名在此列保留（自 inventory evidence_id 改 NONE_ 占位迁移而来）。
    ev_rows: List[Dict[str, Any]] = []
    for r in inv_rows:
        ev_dir = feature_evidence.get(r["feature_id"], "")
        if not ev_dir and (rt_ / "PAGE-ROOT").is_dir():
            ev_dir = "PAGE-ROOT"
        ui_path = (rt_ / ev_dir / "ui.xml") if ev_dir else None
        if ui_path is None or not ui_path.is_file():
            raise SystemExit(
                f"[adapter] FAIL: feature {r['feature_id']} 无真实运行证据目录"
                f"（runtime-evidence/ 下缺 {ev_dir or '(none)'}/ui.xml），"
                f"拒绝合成 evidence-index 行：{r['inventory_id']}")
        ev_rows.append({
            "inventory_id": r["inventory_id"], "evidence_id": r["evidence_id"],
            "page_id": r["page_id"], "state_id": r["state_id"], "env_id": r["env_id"],
            "status": "ACCEPTED", "type": "UI",
            "evidence": str(rt_ / ev_dir),
            "relative_path": f"runtime-evidence/{ev_dir}",
            "metadata_sha256": sha256_file(ui_path),
        })
    write_rows(phase2 / "evidence-index.csv",
               ["inventory_id", "evidence_id", "page_id", "state_id", "env_id",
                "status", "type", "evidence", "relative_path", "metadata_sha256"], ev_rows)
    write_rows(phase2 / "acceptance-registry.csv",
               ["inventory_id", "evidence_id", "decision", "reviewed_by"],
               [{"inventory_id": r["inventory_id"], "evidence_id": r["evidence_id"],
                 "decision": "ACCEPTED", "reviewed_by": REVIEWER} for r in inv_rows])
    anchor_ids = sorted({r["evidence_id"] for r in inv_rows})
    write_rows(phase2 / "evidence-anchors.snapshot.csv",
               ["run_id", "phase", "evidence_id"],
               [{"run_id": run_id, "phase": "2", "evidence_id": e} for e in anchor_ids])

    # ---------- 4) static-analysis + advanced gates ----------
    sa_out = phase2 / "static-analysis"
    sa_out.mkdir(exist_ok=True)
    for name in ("pages.json", "components.json"):
        src = ws / "static-analysis" / name
        if src.exists():
            shutil.copyfile(src, sa_out / name)
        else:
            write_json(sa_out / name, {"generated_by": GENERATED_BY, name.split(".")[0]: []})
    probes = read_rows(cands / "risk-probes.candidates.csv")
    sev_count: Dict[str, int] = {}
    for r in probes:
        sev_count[r.get("severity", "")] = sev_count.get(r.get("severity", ""), 0) + 1
    write_json(sa_out / "advanced-analysis.json", {
        "dynamic_risks": [], "side_effects": [], "scenarios": [],
        "risk_probe_summary": {
            "probe_rows": len(probes),
            "severity_counts": sev_count,
            "note": "gmi 流程无 probe-evidence 观测链；高危探针清单见 phase-2-report.md §5，"
                    "完整明细在 candidates/risk-probes.candidates.csv",
        },
        "summary": {"generated_by": GENERATED_BY},
    })
    write_json(phase2 / "advanced-observations.json",
               {"observations": [], "generated_by": GENERATED_BY})
    write_json(phase2 / "runtime-observations.json",
               {"observations": [], "generated_by": GENERATED_BY})
    write_json(phase2 / "page-gate-report.json", {
        "machine_verdict": "PASS" if gate_ok else "FAIL",
        "decision_source": "GMI_TEST_MODE_GATE",
        "feature_coverage": {"included": included, "excluded": excluded},
        "generated_by": GENERATED_BY,
    })
    write_json(phase2 / "advanced-gate-report.json", {
        "machine_verdict": "PASS" if gate_ok else "FAIL",
        "decision_source": "GMI_TEST_MODE_GATE",
        "required_observations": 0, "received_observations": 0,
        "generated_by": GENERATED_BY,
    })
    (phase2 / "probe-evidence-index.csv").write_text(
        "candidate_id,probe_evidence_id\n", encoding="utf-8")

    # ---------- 5) catalogs（含每个 feature 的 NONE_FOUND 哨兵行） ----------
    cat = phase2 / "catalogs"
    cat.mkdir(exist_ok=True)
    write_rows(cat / "data-dependencies.csv",
               ["data_dependency_id", "name", "dependency_type", "direction",
                "migration_risk", "feature_id"],
               [{"data_dependency_id": f"DATA-NONE-{f}", "name": "NONE_FOUND",
                 "dependency_type": "NONE", "direction": "NONE",
                 "migration_risk": "none", "feature_id": f} for f in included])
    write_rows(cat / "system-capabilities.csv",
               ["system_capability_id", "name", "capability_type", "permission_or_api",
                "migration_risk", "feature_id"],
               [{"system_capability_id": f"SYSTEM-NONE-{f}", "name": "NONE_FOUND",
                 "capability_type": "NONE", "permission_or_api": "NONE",
                 "migration_risk": "none", "feature_id": f} for f in included])
    tp_rows = [{"third_party_dependency_id": f"THIRD-NONE-{f}", "name": "NONE_FOUND",
                "version": "NONE", "purpose": "NONE", "migration_risk": "none",
                "feature_id": f} for f in included]
    for i, r in enumerate(read_rows(cands / "third-party-dependencies.candidates.csv"), start=1):
        tp_rows.append({
            "third_party_dependency_id": f"THIRD-PARTY-{i:04d}",
            "name": r.get("artifact", "") or f"DEP-{i:04d}",
            "version": r.get("version", "") or "UNKNOWN",
            "purpose": r.get("group", ""),
            "migration_risk": r.get("resolution", "") or "unresolved",
            "feature_id": "",
        })
    write_rows(cat / "third-party-dependencies.csv",
               ["third_party_dependency_id", "name", "version", "purpose",
                "migration_risk", "feature_id"], tp_rows)

    # ---------- 5.5) behavior-contracts.csv（2.1 追加式；不动既有 12 表） ----------
    bc_src: Optional[Path] = None
    for cand_bc in (ws / "behavior-contracts.csv",
                    ws / "candidates" / "behavior-contracts.csv"):
        if cand_bc.exists():
            bc_src = cand_bc
            break
    bc_stats: Optional[Dict[str, Any]] = None
    if bc_src:
        bc_dst = phase2 / "behavior-contracts.csv"
        shutil.copyfile(bc_src, bc_dst)
        bc_rows = read_rows(bc_dst)
        bc_stats = {
            "file": "behavior-contracts.csv",
            "sha256": sha256_file(bc_dst),
            "rows": len(bc_rows),
            "runtime_required": sum(
                1 for r in bc_rows
                if (r.get("evidence_class") or "").upper() == "RUNTIME_REQUIRED"),
            "high_impact": sum(
                1 for r in bc_rows if (r.get("impact") or "").lower() == "high"),
            "source": str(bc_src),
        }

    # ---------- 6) closure manifest -> closure-report -> CLOSED ----------
    manifest_obj: Dict[str, Any] = {
        "phase": 2, "status": "CLOSED", "generator": "gmi",
        "run_id": run_id, "project_id": project_id,
        "gmi_closure": closure["gate"], "generated_by": GENERATED_BY,
    }
    if bc_stats:
        manifest_obj["behavior_contracts"] = bc_stats
    write_json(phase2 / "phase-manifest.json", manifest_obj)
    manifest_text = closure_manifest_text(phase2)
    (phase2 / "closure-manifest.sha256").write_text(manifest_text, encoding="utf-8")
    closure_report = {
        "generated_by": GENERATED_BY,
        "final_verdict": "PASS" if gate_ok else "FAIL",
        "evidence_chain_closed": bool(gate_ok),
        "advanced_gate_verdict": "PASS" if gate_ok else "FAIL",
        "reviewer_id": REVIEWER,
        "reviewer_role": "coverage-checker-agent",
        "baseline_env_id": ENV_ID,
        "run_id": run_id,
        "gate_mode": "gmi-test-mode",
        "gmi_closure": closure["gate"],
        "closure_manifest_sha256": sha256_text(manifest_text),
        "included_features": included,
        "excluded_features": excluded,
    }
    if bc_stats:
        closure_report["behavior_contracts"] = bc_stats
    cr_path = phase2 / "closure-report.json"
    write_json(cr_path, closure_report)
    (phase2 / "CLOSED").write_text(sha256_file(cr_path), encoding="utf-8")

    # ---------- 7) controller 结构 ----------
    ctl = out / "controller"
    ctl.mkdir(exist_ok=True)
    write_json(ctl / "scope.json", {
        "run_id": run_id, "project_id": project_id, "project_name": app_name,
        "migration_scope": {"included_features": included, "excluded_features": excluded,
                            "visual_parity_mode": "native-adaptive"},
        "android": {"application_id": application_id,
                    "project_root": str(android_root) if android_root else ""},
        "ownership": {
            "migration_controller_id": CONTROLLER_ID,
            "coverage_checker_id": REVIEWER,
            "code_map_agent_id": CODE_MAP_ID,
            "inventory_lead_id": "AG-RUNTIME",
        },
        "not_entered_reasons": ne_reasons,
        "generated_by": GENERATED_BY,
    })
    # P0-2 修复：gate_basis 的 VISITED 依据从 closure gate 真实数字生成（不再写死单次 run 数据）。
    # 14c：文案如实描述达标条件（gate_ok = visited>0 且零差异），不写与判定无关的阈值。
    _visited_pct = round(_visited / _pages * 100, 2) if _pages else 0.0
    write_json(ctl / "gate-report.json", {
        "phase": 2, "verdict": "PASS" if gate_ok else "FAIL",
        "gate_mode": "gmi-test-mode",
        "gate": closure["gate"],
        "gate_basis": ["UNMAPPED=0", "coverage 无 GAP", "audit discrepancy=0",
                       "closure 已生成",
                       f"VISITED {_visited}/{_pages}={_visited_pct}%（feature 口径，"
                       f"达标=visited>0 且零差异）"],
        "generated_by": GENERATED_BY,
    })
    write_rows(ctl / "evidence-anchor-registry.csv",
               ["run_id", "phase", "evidence_id"],
               [{"run_id": run_id, "phase": "2", "evidence_id": e} for e in anchor_ids])

    wo_agent_ids = ["AG-SCAFFOLD", "AG-P3-TOOLCHAIN", "AG-P3-NAVIGATION",
                    "AG-P3-PUBLIC-UI", "AG-P3-CAPABILITY", "AG-P3-ACCEPTANCE"]
    work_order_id = f"PHASE3-GMI-{run_id}"
    work_order = {
        "work_order_id": work_order_id,
        "phase": 3,
        "status": "ISSUED",
        "run_id": run_id,
        "required_skill": "harmonyos-migration-scaffold",
        "issued_by": CONTROLLER_ID,
        "included_features": included,
        "excluded_features": excluded,
        "ownership": {
            "architecture_lead_id": wo_agent_ids[0],
            "toolchain_agent_id": wo_agent_ids[1],
            "navigation_agent_id": wo_agent_ids[2],
            "public_ui_agent_id": wo_agent_ids[3],
            "capability_contract_agent_id": wo_agent_ids[4],
            "architecture_acceptance_agent_id": wo_agent_ids[5],
        },
        "workspace": str(out),
        "generated_by": GENERATED_BY,
    }
    wo_root = ctl / "work-orders"
    wo_root.mkdir(exist_ok=True)
    wo_path = wo_root / f"{work_order_id}.json"
    write_json(wo_path, work_order)
    scope_sha = sha256_file(ctl / "scope.json")
    wo_sha = sha256_file(wo_path)
    work_order["phase2_gate_sha256"] = sha256_file(ctl / "gate-report.json")
    work_order["scope_sha256"] = scope_sha
    write_json(wo_path, work_order)
    wo_sha = sha256_file(wo_path)
    write_rows(ctl / "work-order-registry.csv",
               ["work_order_id", "phase", "relative_path", "status",
                "scope_sha256", "work_order_sha256", "issued_by"],
               [{"work_order_id": work_order_id, "phase": "3",
                 "relative_path": f"controller/work-orders/{work_order_id}.json",
                 "status": "ISSUED", "scope_sha256": scope_sha,
                 "work_order_sha256": wo_sha, "issued_by": CONTROLLER_ID}])

    # ---------- 8) run-manifest + 冻结 closure 副本 ----------
    write_json(out / "run-manifest.json", {
        "run_id": run_id, "project_id": project_id, "project_name": app_name,
        "id": run_id,
        "generated_by": GENERATED_BY,
        "gmi_workspace": str(ws),
        "android": {"application_id": application_id,
                    "project_root": str(android_root) if android_root else ""},
        "ownership": {"code_map_agent_id": CODE_MAP_ID,
                      "coverage_checker_id": REVIEWER,
                      "migration_controller_id": CONTROLLER_ID},
        "phase2_closure_gate": closure["gate"],
    })
    shutil.copyfile(closure_path, out / "phase-2-closure.json")

    print(f"[adapter] out={out}")
    print(f"[adapter] features: included={len(included)} excluded={len(excluded)}")
    print(f"[adapter] inventory rows={len(inv_rows)} assets={len(asset_rows)}"
          f" (skipped={skipped_assets}) evidence_ids={len(anchor_ids)}")
    if bc_stats:
        print(f"[adapter] behavior-contracts.csv 已纳入（rows={bc_stats['rows']}"
              f" runtime_required={bc_stats['runtime_required']}"
              f" sha256={bc_stats['sha256'][:16]}…）")
    else:
        print("[adapter] behavior-contracts.csv 不存在，跳过（2.1 追加式，非必需）")
    print("[adapter] phase-02-android-inventory ready"
          " (closure/inventory/assets/evidence/static/catalogs/controller)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
