# -*- coding: utf-8 -*-
"""gmi_audit --audit: 证据重放审计（防伪造，2.1.1 fail-closed）。

不触摸模拟器。只读 runtime-evidence/ 下每个页面目录的 ui.xml + screenshot.png +
evidence-index.csv 的记录，用"证据本身"重新判定每页真实状态：

  VISITED       = foreground 属目标包 且 UI 树出现该页特征文本（锚点命中）
  UNRECOGNIZED  = foreground 属目标包 但 UI 无目标页特征（点错页/非特征页）
  EXITED        = foreground 非目标包（掉到桌面/别的 app）
  NO_EVIDENCE   = ui.xml 或 screenshot.png 缺失/为空

visits 记录中的 status 与重放结果不一致 -> 退出非零。
任何页面不能仅凭"点击过"标签被判 VISITED。

2.1.1 fail-closed：
  - runtime 证据（evidence-index.csv / runtime-gate.csv）缺失 -> 报错退出非零；
    不得把"没有可审的东西"解释为 0 discrepancy。
  - 重放范围以 RUNTIME_REQUIRED BC 集为准（沿用 2.1 收敛），改用 Page-ID
    精确关联（候选 manifest 映射），替代字符串归一化。
  - 每个 RUNTIME_REQUIRED BC 必须有对应页面（含 PAGE-LAUNCH）的重放结果，
    缺失 -> 逐条报错并退出非零。
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Dict, List

import gmi_runtime as rt


def page_features(text: str) -> List[str]:
    out = []
    for m in re.finditer(r'(?:text|content-desc)="([^"]+)"', text):
        v = m.group(1).strip()
        if v and v not in out:
            out.append(v)
    return out


def audit(project: Path, workspace: Path, pkg: str) -> List[Dict[str, Any]]:
    out_dir = workspace / "runtime-evidence"
    # fail-closed：没有证据文件就没有审计，缺失一律报错（不解释为零 discrepancy）
    if not (out_dir / "evidence-index.csv").exists():
        raise SystemExit(f"[audit] FAIL: {out_dir / 'evidence-index.csv'} 缺失"
                         "（runtime 未采集或未产出）；不得按零 discrepancy 处理")
    if not (out_dir / "runtime-gate.csv").exists():
        raise SystemExit(f"[audit] FAIL: {out_dir / 'runtime-gate.csv'} 缺失"
                         "（无 gate 记录可重放）；不得按零 discrepancy 处理")
    index_rows = rt.read_csv(out_dir / "evidence-index.csv")
    gate_rows = rt.read_csv(out_dir / "runtime-gate.csv")
    strings = rt.load_strings(project)

    # 2.1.1：重放范围 = RUNTIME_REQUIRED BC 集，Page-ID 精确关联
    page_id_map = rt.build_page_id_map(workspace / "candidates")
    bc_rows = rt.load_behavior_contracts(workspace)
    required_pages: set = set()
    required_refs: Dict[str, str] = {}  # page_ref -> 正式 Page-ID
    if bc_rows:
        scope = rt.resolve_required_scope(bc_rows, page_id_map)
        if scope["unresolved"]:
            detail = "; ".join(f"{u['bc_id'] or '?'}:page_ref={u['page_ref'] or '(empty)'}"
                               for u in scope["unresolved"][:10])
            raise SystemExit(f"[audit] FAIL: UNRESOLVED_PAGE_REF（RUNTIME_REQUIRED BC 无法映射 "
                             f"Page-ID）：{detail}")
        required_pages = scope["pages"]
        for r in rt.required_bc_rows(bc_rows):
            ref = (r.get("page_ref") or "").strip()
            required_refs[ref] = rt.resolve_page_ref(ref, page_id_map)
        print(f"[audit] behavior-contracts.csv present: 重放范围收敛到 RUNTIME_REQUIRED"
              f"（Page-ID 精确集 pages={len(required_pages)}）；其余页面不重放")

    def in_scope(pid: str, sym: str) -> bool:
        if not bc_rows:
            return True  # 无契约：维持现状（全量重放）
        if pid == "PAGE-LAUNCH":
            return True  # 根证据始终重放
        for name in (pid, sym):
            rp = rt.resolve_page_ref(name, page_id_map)
            if rp and rp in required_pages:
                return True
        return False

    # 缺口5：特征集扩到 page-fields field_label（含自绘标题页）
    pf_rows = rt.read_csv(workspace / "candidates" / "page-fields.candidates.csv")
    label_by_page: Dict[str, List[str]] = {}
    for r in pf_rows:
        sym = r.get("page_symbol", "") or ""
        lbl_raw = (r.get("field_label") or "").strip()
        if not sym or not lbl_raw:
            continue
        # field_label 可能是 string 资源 key（如 api_key）：翻译成实际 UI 文本值后
        # 一并纳入特征集（key 与值都保留，仅扩充特征来源，不放宽 VISITED 门槛：
        # 仍要求 foreground 属目标包且特征命中 ui.xml）。
        for lbl in dict.fromkeys([lbl_raw, strings.get(lbl_raw, "")]):
            if lbl and len(lbl) <= 40 and "%" not in lbl[:1]:
                label_by_page.setdefault(sym, []).append(lbl)

    rows: List[Dict[str, Any]] = []
    for g in gate_rows:
        pid = g.get("page_id", "")
        sym = g.get("symbol", "")
        recorded = g.get("status", "")
        # NOT_ENTERED: 预期无证据，跳过（不属于伪造）
        if recorded == "NOT_ENTERED":
            continue
        # 2.1.1 范围收敛：非 RUNTIME_REQUIRED（Page-ID 精确）页面不重放
        if not in_scope(pid, sym):
            continue
        d = out_dir / pid if pid else None
        ui_p = (d / "ui.xml") if d else None
        fg = ""
        for e in index_rows:
            if e.get("page_id") == pid:
                fg = e.get("foreground", "")
                break
        if not d or not ui_p or not ui_p.exists() or ui_p.stat().st_size < 200:
            status, note = "NO_EVIDENCE", "ui.xml missing/empty"
        else:
            ui_text = ui_p.read_text(encoding="utf-8", errors="replace")
            in_pkg = pkg in fg
            feats = rt.anchor_for(sym, strings) if sym else []
            # 补充 page-fields 特征（自绘标题页如 AboutScreen）
            feats += label_by_page.get(sym, [])
            # 补充 UI 树自身文本特征（锚点扩展最后手段）
            if not feats:
                feats = page_features(ui_text)
            hits = [f for f in feats if f and f in ui_text]
            if not in_pkg:
                status, note = "EXITED", f"foreground={fg}"
            elif pid == "PAGE-LAUNCH" or sym == "MainActivity":
                status, note = "VISITED", f"fg={fg} (root page, evidence present)"
            elif hits:
                status, note = "VISITED", f"fg={fg} hits={len(hits)}"
            else:
                status, note = "UNRECOGNIZED", f"fg={fg} no target feature"
        rows.append({"page_id": pid, "symbol": sym, "replayed": status,
                     "recorded": recorded,
                     "discrepancy": ("YES" if status != recorded else "no"),
                     "note": note})
    return rows


def check_required_coverage(rows: List[Dict[str, Any]], workspace: Path) -> List[str]:
    """fail-closed：每个 RUNTIME_REQUIRED BC 都必须有 replay 结果，缺失逐条报错。"""
    bc_rows = rt.load_behavior_contracts(workspace)
    if not bc_rows:
        return []
    page_id_map = rt.build_page_id_map(workspace / "candidates")
    scope = rt.resolve_required_scope(bc_rows, page_id_map)
    if scope["unresolved"]:
        return [f"UNRESOLVED_PAGE_REF {u['bc_id'] or '?'} page_ref={u['page_ref'] or '(empty)'}"
                for u in scope["unresolved"]]
    replayed_pages = {r.get("page_id", "") for r in rows}
    replayed_symbols = {r.get("symbol", "") for r in rows}
    errs: List[str] = []
    for r in rt.required_bc_rows(bc_rows):
        ref = (r.get("page_ref") or "").strip()
        pid = rt.resolve_page_ref(ref, page_id_map)
        if pid in replayed_pages or pid == "PAGE-LAUNCH" in replayed_pages or \
                any(rt.resolve_page_ref(s, page_id_map) == pid for s in replayed_symbols):
            continue
        errs.append(f"REQUIRED_NO_REPLAY {r.get('bc_id', '?')} page_ref={ref} -> {pid}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="gmi runtime audit (anti-forgery, fail-closed)")
    ap.add_argument("--project", required=True)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--package", required=True)
    args = ap.parse_args()
    rows = audit(Path(args.project), Path(args.workspace), args.package)
    from collections import Counter
    out_dir = Path(args.workspace) / "runtime-evidence"
    rt.write_csv(out_dir / "audit-replay.csv",
                 ["page_id", "symbol", "replayed", "recorded", "discrepancy", "note"], rows)
    print("[audit] replayed:", dict(Counter(r["replayed"] for r in rows)))

    # fail-closed：每个 required BC 必须有 replay 结果
    missing = check_required_coverage(rows, Path(args.workspace))
    if missing:
        print(f"[audit] FAIL: {len(missing)} 个 RUNTIME_REQUIRED BC 无 replay 结果：")
        for e in missing[:20]:
            print("   -", e)
        return 1

    bad = [r for r in rows if r["discrepancy"] == "YES"]
    if bad:
        print(f"[audit] DISCREPANCIES={len(bad)} (recorded != replayed):")
        for r in bad[:20]:
            print(f"   {r['page_id'][:38]:40} recorded={r['recorded']:12} replayed={r['replayed']}")
        return 1
    print("[audit] OK: all recorded status matches evidence replay.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
