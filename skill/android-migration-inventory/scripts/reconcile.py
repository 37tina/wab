# -*- coding: utf-8 -*-
"""reconcile -- 源码理解 ↔ runtime 实测 对账引擎（Phase 2 新范式第 7 步）。

范式定位（用户原话）：源码说"开关写 preference"但模拟器点完没变化 → CONFLICT；
两边一致 → CONFIRMED；宿主页面/纯展示直接 SOURCE_CONFIRMED，不为证明"被访问
过"硬跑；runtime 没跑且无声明 → GAP。

输入（--workspace 下）：
  behavior-contracts.csv               源码声明侧（data_state_change /
                                       persistence_targets /
                                       external_side_effects / evidence_class）
  runtime-evidence/runtime-chains.csv  实测侧（gmi_runtime --mode chain 产出）
  feature-map.json                     可选（#38 改造A 产物）；缺失时按
                                       evidence_class 降级对账
                                       （RUNTIME_REQUIRED→RUNTIME，
                                        其余→SOURCE_CONFIRM）

四态判定规则（verdict，blocked 优先：采集受阻≠行为矛盾）：
  ┌──────────────┬───────────────────────┬──────────────────┬──────────────────┐
  │ feature 归属 │ runtime-chains 行     │ 断言/链状态       │ verdict          │
  ├──────────────┼───────────────────────┼──────────────────┼──────────────────┤
  │ SOURCE_CONFIRM│ 无行                  │ -                │ SOURCE_CONFIRMED │
  │ SOURCE_CONFIRM│ 有行 CHAIN_FAIL       │ 断言 FAIL        │ CONFLICT(意外)   │
  │ RUNTIME      │ 有行 CHAIN_PASS       │ 断言全 PASS      │ CONFIRMED        │
  │ RUNTIME      │ 有行 CHAIN_FAIL       │ 有断言 FAIL      │ CONFLICT         │
  │ RUNTIME      │ 无行                  │ -                │ GAP              │
  │ RUNTIME      │ 有行 blocked*         │ -                │ GAP(blocked)     │
  │ unmapped**   │ 无行                  │ -                │ GAP(unmapped)    │
  └──────────────┴───────────────────────┴──────────────────┴──────────────────┘
  * blocked = NAV_FAIL | STEPS_FAIL | ANR_BLOCKED | UNRESOLVED_PAGE_REF |
    INVALID_CONTRACT | UNSUPPORTED_ORACLE | PRECONDITION_FAILED
    （收敛式重构批次1 #81/#83：契约不完整 / 无可用 oracle / 前置不满足均归
    GAP，degraded CHAIN_PASS 路径已彻底删除——无断言或无 oracle 的链绝不
    CONFIRMED；Gate 2 对 INVALID_CONTRACT/UNSUPPORTED_ORACLE 记 error）
  ** feature-map 在但 BC.feature_id 不在其中（runtime 侧已 fail-closed 拒跑）
  CHAIN_PASS 且无源码声明 → 仍 CONFIRMED，note 标 runtime-observed。

输出 reconciliation.csv：
  bc_id, feature_id, page_ref, verify_side(FEATURE_MAP|EVIDENCE_CLASS_FALLBACK),
  verdict(CONFIRMED|CONFLICT|SOURCE_CONFIRMED|GAP), evidence_ref, runtime_status,
  note
  （核心消费列：bc_id / feature_id / verdict / evidence_ref / note，供
   Gate 2（#40 改造C）直接消费；runtime_status/verify_side 为诊断辅助列。）

退出码：0=正常产出（含 GAP，GAP 是"明确状态"不是错误）；1=输入缺失；
        2=存在 CONFLICT（源码与实测矛盾，Gate 2 应阻塞或转人工）。

用法：
  python reconcile.py --workspace <gmi-workspace> [--out <reconciliation.csv>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gmi_runtime import (  # noqa: E402  复用同仓口径，避免 schema 漂移
    CHAIN_BLOCKED_STATUS,
    load_feature_map,
    read_csv,
    write_csv,
)

RECON_FIELDS = ["bc_id", "feature_id", "page_ref", "verify_side",
                "verdict", "evidence_ref", "runtime_status", "note"]

VERDICTS = ("CONFIRMED", "CONFLICT", "SOURCE_CONFIRMED", "GAP")

# 视为"无声明"的占位值（中文 BC 里常见 "无" / "无(...)" 短注记）
_NO_VALUE_TOKENS = {"", "无", "none", "n/a", "-", "不适用"}


def field_declared(value: str) -> bool:
    """源码声明侧字段是否构成真实声明（非空且非"无"类占位）。"""
    v = (value or "").strip()
    if v.lower() in _NO_VALUE_TOKENS:
        return False
    if v.startswith("无") and len(v) <= 24:  # 无 / 无(范围外) 等短注记
        return False
    return True


def declared_sides(bc: Dict[str, str]) -> Dict[str, bool]:
    """BC 的三个源码声明维度（对账输入，与 BC schema 对齐）。"""
    return {
        "data_state_change": field_declared(bc.get("data_state_change", "")),
        "persistence_targets": field_declared(bc.get("persistence_targets", "")),
        "external_side_effects": field_declared(bc.get("external_side_effects", "")),
    }


def bc_verify_mode(bc: Dict[str, str], fmap: Dict[str, Any]) -> Tuple[str, str]:
    """返回 (mode, side)：mode ∈ RUNTIME|SOURCE_CONFIRM|""（unmapped）；
    side ∈ FEATURE_MAP|EVIDENCE_CLASS_FALLBACK（降级口径标记）。"""
    if not fmap.get("missing"):
        fid = (bc.get("feature_id") or "").strip()
        if fid in fmap["runtime_features"]:
            return "RUNTIME", "FEATURE_MAP"
        if fid in fmap["source_confirm_features"]:
            return "SOURCE_CONFIRM", "FEATURE_MAP"
        return "", "FEATURE_MAP"
    ec = (bc.get("evidence_class") or "").strip().upper()
    return ("RUNTIME" if ec == "RUNTIME_REQUIRED" else "SOURCE_CONFIRM",
            "EVIDENCE_CLASS_FALLBACK")


def load_chain_rows(ws: Path) -> Dict[str, Dict[str, str]]:
    """runtime-chains.csv -> {bc_id: row}（缺失返回空，由调用方记 GAP）。"""
    p = ws / "runtime-evidence" / "runtime-chains.csv"
    out: Dict[str, Dict[str, str]] = {}
    for r in read_csv(p):
        _id = (r.get("bc_id") or "").strip()
        if _id:
            out[_id] = r
    return out


def _failed_assertions_note(chain_row: Dict[str, str]) -> str:
    """CONFLICT note：列出 FAIL 的断言（kind=value），方便人审。"""
    try:
        results = json.loads(chain_row.get("assertion_results") or "")
    except Exception:
        results = []
    fails = [a for a in results
             if isinstance(a, dict) and a.get("verdict") == "FAIL"]
    if not fails:
        return "assertions failed"
    return "assertions failed: " + "; ".join(
        f"{a.get('kind')}={a.get('value')}" for a in fails[:4])


def reconcile_one(bc: Dict[str, str], mode: str, side: str,
                  chain_row: Optional[Dict[str, str]],
                  declared: Dict[str, bool]) -> Tuple[str, str, str]:
    """单条 BC 对账（纯函数）。返回 (verdict, note, evidence_ref)。

    判定顺序（blocked 优先于断言矛盾：采集链路受损不构成行为矛盾）：
    1) SOURCE_CONFIRM：不跑是设计（容器页/纯展示）；意外出现 CHAIN_FAIL
       行才升级 CONFLICT（防御性对账：跑了且失败=有实际矛盾证据）；
    2) 无 runtime 行：GAP（note 区分 有声明未跑 / 无声明未跑 / unmapped）；
    3) CHAIN_PASS：CONFIRMED（无源码声明时 note 标 runtime-observed；
       #81 后无 degraded 链——无断言/无 oracle 在 runtime 侧已是
       INVALID_CONTRACT/UNSUPPORTED_ORACLE，不会到达这里）；
    4) CHAIN_FAIL：CONFLICT（源码说有变化/BC 期望有结果但实测断言 FAIL）；
    5) blocked（NAV_FAIL/STEPS_FAIL/ANR_BLOCKED/UNRESOLVED_PAGE_REF/
       INVALID_CONTRACT/UNSUPPORTED_ORACLE/PRECONDITION_FAILED）：GAP。"""
    has_decl = any(declared.values())
    if mode == "SOURCE_CONFIRM":
        if chain_row and (chain_row.get("chain_status") or "") == "CHAIN_FAIL":
            return ("CONFLICT",
                    "source-confirm feature ran and failed (unexpected); "
                    + _failed_assertions_note(chain_row),
                    (chain_row.get("evidence_dir") or "").strip())
        return ("SOURCE_CONFIRMED",
                "verify_mode=SOURCE_CONFIRM (container/pure-display); "
                "not run by design"
                + (f"; ran as {chain_row.get('chain_status', '')} (unexpected)"
                   if chain_row else ""),
                (bc.get("source_refs") or "").strip())
    if not chain_row:
        if mode == "":
            return "GAP", "feature_id not in feature-map (unmapped)", ""
        if has_decl:
            return "GAP", "declared but chain not run", ""
        return "GAP", "no declaration and chain not run", ""
    status = (chain_row.get("chain_status") or "").strip()
    ev = (chain_row.get("evidence_dir") or "").strip()
    if status == "CHAIN_PASS":
        note = "declared & asserted" if has_decl else \
            "runtime-observed (no source declaration)"
        return "CONFIRMED", note, ev
    if status == "CHAIN_FAIL":
        note = _failed_assertions_note(chain_row)
        if not has_decl:
            note += "; no source declaration for observed expectation"
        return "CONFLICT", note, ev
    if status in CHAIN_BLOCKED_STATUS:
        return "GAP", f"chain blocked ({status}): " + \
            (chain_row.get("note") or "")[:60], ev
    # 未知链状态：fail-closed 记 GAP 并显式暴露，绝不猜
    return "GAP", f"unknown chain_status '{status}'", ev


def build_reconciliation(bc_rows: List[Dict[str, str]],
                         chain_by_id: Dict[str, Dict[str, str]],
                         fmap: Dict[str, Any]) -> Tuple[List[Dict[str, str]],
                                                        Dict[str, int]]:
    """全量对账：每个 bc_id 一行。返回 (rows, 四态计数)。"""
    rows: List[Dict[str, str]] = []
    counts = {v: 0 for v in VERDICTS}
    for bc in bc_rows:
        bc_id = (bc.get("bc_id") or "").strip()
        if not bc_id:
            continue
        mode, side = bc_verify_mode(bc, fmap)
        chain_row = chain_by_id.get(bc_id)
        verdict, note, ev = reconcile_one(bc, mode, side, chain_row,
                                          declared_sides(bc))
        counts[verdict] += 1
        rows.append({
            "bc_id": bc_id,
            "feature_id": (bc.get("feature_id") or "").strip(),
            "page_ref": (bc.get("page_ref") or "").strip(),
            "verify_side": side,
            "verdict": verdict,
            "evidence_ref": ev,
            "runtime_status": (chain_row or {}).get("chain_status", ""),
            "note": note,
        })
    return rows, counts


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="reconcile -- 源码理解 vs runtime 实测 对账引擎"
                    "（CONFIRMED/CONFLICT/SOURCE_CONFIRMED/GAP）")
    ap.add_argument("--workspace", required=True, help="gmi 工作区根目录")
    ap.add_argument("--out", default=None,
                    help="输出 CSV 路径（缺省 <workspace>/reconciliation.csv）")
    args = ap.parse_args(argv)
    ws = Path(args.workspace)

    bc_rows: List[Dict[str, str]] = []
    for p in (ws / "behavior-contracts.csv",
              ws / "candidates" / "behavior-contracts.csv"):
        if p.exists():
            bc_rows = read_csv(p)
            if bc_rows:
                break
    if not bc_rows:
        print("[reconcile] FAIL: behavior-contracts.csv 缺失或无数据行，"
              "fail-closed 退出")
        return 1
    chains_p = ws / "runtime-evidence" / "runtime-chains.csv"
    if not chains_p.exists():
        print("[reconcile] WARNING: runtime-chains.csv 缺失 -> "
              "全部 RUNTIME BC 记 GAP（先跑 gmi_runtime --mode chain）")
        chain_by_id: Dict[str, Dict[str, str]] = {}
    else:
        chain_by_id = load_chain_rows(ws)
        print(f"[reconcile] runtime-chains rows={len(chain_by_id)}")
    fmap = load_feature_map(ws)
    if fmap.get("missing"):
        print("[reconcile] WARNING: feature-map.json 缺失，按 evidence_class "
              "降级对账（RUNTIME_REQUIRED→RUNTIME，其余→SOURCE_CONFIRM）")
    else:
        print(f"[reconcile] feature-map ok: runtime_features="
              f"{len(fmap['runtime_features'])} "
              f"source_confirm_features={len(fmap['source_confirm_features'])}")

    rows, counts = build_reconciliation(bc_rows, chain_by_id, fmap)
    out = Path(args.out) if args.out else ws / "reconciliation.csv"
    write_csv(out, RECON_FIELDS, rows)
    print(f"[reconcile] bc_rows={len(rows)} "
          f"CONFIRMED={counts['CONFIRMED']} CONFLICT={counts['CONFLICT']} "
          f"SOURCE_CONFIRMED={counts['SOURCE_CONFIRMED']} GAP={counts['GAP']}"
          f" -> {out}")
    for r in rows:
        if r["verdict"] == "CONFLICT":
            print(f"[reconcile]   CONFLICT {r['bc_id']:14} {r['note'][:70]}")
    if counts["CONFLICT"]:
        print("[reconcile] FAIL: 源码声明与 runtime 实测存在矛盾（CONFLICT），"
              "退出码 2（Gate 2 应阻塞或转人工裁决）")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())