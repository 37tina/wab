# -*- coding: utf-8 -*-
"""gmi_closure -- 生成 gmi Phase 2 闭包证书 phase-2-closure.json（供 Phase 3 消费）。

用法：
  python gmi_closure.py --workspace <TASKS-RUN1 等 Phase-2 工作区>

前置校验（任一失败 exit 1，不生成）：
  - 【新范式门禁】范围内功能覆盖：workspace/scope.json（或 controller/scope.json）
    存在 included_features 时，feature-map.json 必须存在且 coverage_gate 闭合
    （每个 included feature 有条目）；feature-map.json 存在时无论 scope 与否
    都校验其 coverage_gate
  - runtime-evidence/audit-replay.csv 全部 discrepancy=no（缺失/无数据行同样失败，
    不把"无数据"当零差异）；runtime-evidence/runtime-gate.csv 必须存在且有数据行
  - candidates/ 12 表 + manifest.sha256 存在；phase-2-report.md 存在（门禁前置第 4 项）
  - coverage-ledger.csv 必须存在且有数据行；其 UNMAPPED(GAP) 行自新范式起为
    参考信息（gate.unmapped 保留实算），不再阻塞闭包
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sha256_dir(d: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(d.rglob("*")):
        if f.is_file():
            h.update(f.relative_to(d).as_posix().encode())
            h.update(sha256_file(f).encode())
    return h.hexdigest()


def read_rows(p: Path) -> List[Dict[str, str]]:
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def require_rows(p: Path, errors: List[str]) -> List[Dict[str, str]]:
    """fail-closed：关键门禁 CSV 缺失或无数据行 -> 记 error（绝不把'无数据'当'零差异'）。

    文件存在但不可读时维持既有行为：read_rows 内 open/read 抛异常崩溃（退出非零）。
    """
    if not p.exists():
        errors.append(f"gmi-gate-incomplete: {p} missing")
        return []
    rows = read_rows(p)
    if not rows:
        errors.append(f"gmi-gate-incomplete: {p} has no data rows")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="gmi phase-2 closure")
    ap.add_argument("--workspace", required=True)
    args = ap.parse_args()
    ws = Path(args.workspace)
    cands = ws / "candidates"
    cov = ws / "coverage"
    rt_ = ws / "runtime-evidence"

    errors: List[str] = []

    # 1) 前置校验
    # coverage-ledger：必须有数据行（D-6 fail-closed 保留）；GAP/UNMAPPED 行自
    # 新范式起为参考信息（12 表 + ledger 是参考附件），不再阻塞闭包。
    ledger_rows = require_rows(cov / "coverage-ledger.csv", errors)
    gaps = [r for r in ledger_rows if r.get("status") == "GAP"]

    # 【新范式门禁】范围内功能覆盖：scope included ⊆ feature-map 条目。
    scope_included: List[str] = []
    for scope_path in (ws / "scope.json", ws / "controller" / "scope.json"):
        if scope_path.exists():
            try:
                scope_included = [str(f) for f in (json.loads(
                    scope_path.read_text(encoding="utf-8")
                ).get("migration_scope", {}) or {}).get("included_features") or []]
            except Exception:  # noqa: BLE001
                errors.append(f"scope.json 解析失败: {scope_path}")
            break
    fmap_path = ws / "feature-map.json"
    feature_coverage: Dict[str, Any] = {"required": bool(scope_included or fmap_path.exists()),
                                        "ok": True, "included": scope_included,
                                        "covered": [], "missing": []}
    if fmap_path.exists():
        try:
            fmap = json.loads(fmap_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"feature-map.json 解析失败: {exc}")
            fmap = None
        if fmap is not None:
            covered = [str(f.get("feature_id") or "") for f in fmap.get("features", [])
                       if f.get("feature_id")]
            gate = fmap.get("coverage_gate") or {}
            included = list(gate.get("included") or scope_included)
            missing = [f for f in included if f not in covered]
            feature_coverage.update(
                included=included, covered=covered, missing=missing,
                ok=bool(gate.get("included_features_covered") is True and not missing))
            if not feature_coverage["ok"]:
                errors.append(f"feature coverage gate FAIL: missing={missing} "
                              f"(scope included features 必须都有 feature-map 条目)")
    elif scope_included:
        errors.append("feature coverage gate FAIL: scope 声明了 included_features "
                      f"({len(scope_included)} 个) 但 feature-map.json 缺失"
                      "（先跑 feature_map.py 生成并 --validate 收口）")

    comp_rows = read_rows(cands / "phase-2-completeness.csv") if (cands / "phase-2-completeness.csv").exists() else []
    missing_total = sum(1 for r in comp_rows if r.get("status") == "MISSING")
    na_total = sum(1 for r in comp_rows if r.get("status") == "N/A")
    # MISSING 必须带 hint（逐项点名=无隐瞒）；无 hint 的 MISSING 才阻塞
    silent_missing = [r for r in comp_rows
                      if r.get("status") == "MISSING" and not str(r.get("hint", "")).strip()]
    if silent_missing:
        errors.append(f"silent MISSING (no hint): {len(silent_missing)}")

    # v5.0 行为链模式（SKILL v3 步骤 6/7）：runtime-chains.csv 在场且有数据行
    # 时按 chain 口径闭包——runtime-gate.csv/audit-replay.csv 是 --mode pages
    # 产物，不再 fail-closed 强制（存在时仍读入作参考数字）。防伪由每链
    # evidence/chains/<bc_id>/（操作日志+断言判定+三点快照）与 reconcile.py
    # 对账承担。
    chain_rows = read_rows(rt_ / "runtime-chains.csv")
    chain_mode = bool(chain_rows)

    audit_rows = read_rows(rt_ / "audit-replay.csv")
    if not audit_rows and not chain_mode:
        errors.append(f"gmi-gate-incomplete: {rt_ / 'audit-replay.csv'} missing or no data rows")
    audit_disc = sum(1 for r in audit_rows if r.get("discrepancy") == "YES")
    if audit_disc:
        errors.append(f"audit discrepancy>0: {audit_disc}")

    gate_rows = read_rows(rt_ / "runtime-gate.csv")
    if not gate_rows and not chain_mode:
        errors.append(f"gmi-gate-incomplete: {rt_ / 'runtime-gate.csv'} missing or no data rows")
    visited_rows = [r for r in gate_rows if r.get("status") == "VISITED"]
    not_entered_rows = [r for r in gate_rows if r.get("status") == "NOT_ENTERED"]
    visited = len(visited_rows)
    not_entered = len(not_entered_rows)
    # 符号级口径：去重（tab 重复大小写/主页项不计）
    visited_syms = set(r.get("symbol", "") for r in visited_rows if r.get("symbol"))
    ne_syms = set(r.get("symbol", "") for r in not_entered_rows if r.get("symbol"))
    visited_u = len(visited_syms)
    not_entered_u = len(ne_syms)
    # P：以页面符号口径（completeness 的页面数），避免 gate 行数虚高
    comp_symbols = set(r.get("page_symbol", "") for r in comp_rows if r.get("page_symbol"))
    pages_total = len(comp_symbols) if comp_symbols else (visited_u + not_entered_u)
    # chain 口径数字：CHAIN_PASS / blocked（NAV_FAIL/ANR_BLOCKED 等）；
    # chain 模式下取代 pages 口径成为权威 gate 数字。
    chains_total = len(chain_rows)
    chains_pass = sum(1 for r in chain_rows if r.get("chain_status") == "CHAIN_PASS")
    if chain_mode:
        pages_total = chains_total
        visited_u = chains_pass
        not_entered_u = chains_total - chains_pass

    if not (cands / "manifest.sha256").exists():
        errors.append("candidates/manifest.sha256 missing (12 表未固化)")
    if not (ws / "phase-2-report.md").exists():
        errors.append("gmi-gate-incomplete: phase-2-report.md missing (门禁前置第 4 项)")

    if errors:
        print("CLOSURE BLOCKED:")
        for e in errors:
            print("  -", e)
        return 1

    # 2) 生成闭包
    bc_path = next((p for p in (ws / "behavior-contracts.csv",
                                cands / "behavior-contracts.csv") if p.exists()), None)
    report_path = ws / "phase-2-report.md"
    # 新范式对账产物（reconcile.py 产出；chain 模式）——gaps/conflicts 从对账表派生，
    # CONFLICT 骨架带空 explanation（人工解释后 Gate 2 v2 规则 3 放行，fail-closed）
    recon_path = ws / "reconciliation.csv"
    recon_rows = read_rows(recon_path) if recon_path.exists() else []

    def _recon_verdict(r):
        return str(r.get("verdict", r.get("status", ""))).strip().upper()

    closure_gaps = [
        {
            "feature_id": r.get("feature_id", ""),
            "reason": (r.get("note", r.get("reason", "")) or "").strip() or "unexplained gap",
        }
        for r in recon_rows if _recon_verdict(r) == "GAP"
    ]
    conflicts_explained = [
        {"bc_id": r.get("bc_id", ""), "explanation": ""}
        for r in recon_rows if _recon_verdict(r) == "CONFLICT"
    ]
    closure = {
        "generator": "gmi_closure",
        "workspace": str(ws),
        "closure_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gaps": closure_gaps,
        "conflicts_explained": conflicts_explained,
        "gate": {
            "unmapped": len(gaps),
            "feature_coverage": feature_coverage,
            "completeness_rows": len(comp_rows),
            "completeness_missing_total": missing_total,
            "completeness_na_total": na_total,
            "audit_discrepancy": audit_disc,
            "visited": visited_u,
            "visited_rows": visited,
            "not_entered": not_entered_u,
            "not_entered_rows": not_entered,
            "pages_total": pages_total,
            "pages_visited_pct": round(visited_u / pages_total * 100, 1) if pages_total else 0,
            # v5.0 chain 口径（SKILL v3：结果导向，证据重点是断言判定而非截图数）
            "chain_mode": chain_mode,
            "chains_total": chains_total,
            "chains_pass": chains_pass,
            "chains_fail_blocked": chains_total - chains_pass,
        },
        "artifact_hashes": {
            "candidates_dir_sha256": sha256_dir(cands),
            "coverage_ledger_sha256": sha256_file(cov / "coverage-ledger.csv") if (cov / "coverage-ledger.csv").exists() else "",
            "runtime_evidence_dir_sha256": sha256_dir(rt_) if (rt_ / "evidence-index.csv").exists() else "",
            # 哈希链补口（P1-6）：BC 与 phase-2-report.md 纳入冻结范围。
            # BC 为可选产物（缺失记空串，允许闭包）；report 缺失已在前置 errors 拦截。
            "behavior_contracts_sha256": sha256_file(bc_path) if bc_path else "",
            "phase2_report_sha256": sha256_file(report_path) if report_path.exists() else "",
            # 新范式（#41）：对账表入链——Gate 2 v2 规则 3 的核心判定输入必须防篡改
            "reconciliation_sha256": sha256_file(recon_path) if recon_path.exists() else "",
            # v5.0 chain：行为链结果表入链（断言判定的权威记录）
            "runtime_chains_sha256": (sha256_file(rt_ / "runtime-chains.csv")
                                      if (rt_ / "runtime-chains.csv").exists() else ""),
            # P2 视觉记忆（#75）：per-surface 基准截图/ui-tree 摘要/色板入链
            # （可选产物，缺失记空串不阻塞；由 visual_memory.py 生成）
            "visual_memory_sha256": (sha256_file(ws / "visual-memory.json")
                                     if (ws / "visual-memory.json").exists() else ""),
        },
    }
    out = ws / "phase-2-closure.json"
    out.write_text(json.dumps(closure, indent=2, ensure_ascii=False), encoding="utf-8")
    g = closure["gate"]
    print(f"CLOSURE OK: feature_coverage_ok={g['feature_coverage']['ok']} "
          f"unmapped(ref)={g['unmapped']} audit_disc={g['audit_discrepancy']} "
          f"visited={g['visited']}/{g['pages_total']} ({g['pages_visited_pct']}%) "
          f"missing_completeness={g['completeness_missing_total']}")
    print("->", out)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
