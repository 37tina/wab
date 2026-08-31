#!/usr/bin/env python3
"""Issue per-feature Phase 4 work orders (the single dispatching path).

收敛式重构批次 2（#85）：反转旧 stub——旧 stub 一律拒绝功能级工单并把
实施者推回页面级工单路径；v4 唯一路径原则下 **Feature 工单是唯一
路径**（页面级工单体系已退役），本工具从 P4 工作区的
feature-dispatch.json 逐 feature 签发实施工单。

每份 Feature 工单携带（消费面：Phase 4 实施代理 + Gate 4）：
  * 语义分派：verify_mode / bc_ids / runtime_bc_ids / 数据读写集 /
    data_relation_ids / surfaces / harmony_steps 留列；
  * **MUST_READ 段**（批次 2 #85 机械化保证实施者读过 P2/Android 源码）：
      - behavior_contract_ids   本 feature 全部 BC（七段考卷）
      - android_source_refs     BC.source_refs 聚合（Android 源码锚点）
      - runtime_evidence_refs   runtime-chains 证据目录引用（真机基线）
      - data_relations          数据读写关系行 + 共享对象
      - visual_memory_surface   feature-map surfaces（视觉基线面）
      - p3_surface_plan         Phase 3 surface-registry 承载体计划行
    实施者在 implementation-declarations.csv 以 consumed_bc_ids /
    consumed_source_refs / consumed_runtime_refs 回执（Gate 4 强制）；
  * semantic_probe 段：DebugSemanticProbe.ets 的 expected sha256（P4
    实施者禁改探针本体；Gate 4 校验哈希一致）。旧 run 无探针 → null
    （Gate 4 跳过该项校验，向后兼容）。

幂等：重复签发同一 feature（registry 已有非 SUPERSEDED 行）→ 报错，
显式 supersede 后才可重发。--all 一次签发全部 NOT_STARTED feature。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACTOR_RE_MIN = 3
UPSTREAM = "inputs/upstream"
BC_SNAPSHOT = f"{UPSTREAM}/06-phase2_behavior_contracts.csv"
CHAINS_SNAPSHOT = f"{UPSTREAM}/09-phase2_runtime_chains.csv"
FEATURE_MAP_SNAPSHOT = f"{UPSTREAM}/05-phase2_feature_map.json"
SURFACE_REGISTRY_SNAPSHOT = f"{UPSTREAM}/18-phase3_surface_registry.csv"
PROBE_RELATIVE_PATH = "entry/src/main/ets/probe/DebugSemanticProbe.ets"
REGISTRY_FIELDS = [
    "work_order_id", "feature_id", "relative_path",
    "work_order_sha256", "issued_by", "issued_at", "status",
]
MUST_READ_KEYS = (
    "behavior_contract_ids", "android_source_refs",
    "runtime_evidence_refs", "data_relations",
    "visual_memory_surface", "p3_surface_plan",
)


def utc_now() -> str:
    return (datetime.now(timezone.utc).replace(microsecond=0)
            .isoformat().replace("+00:00", "Z"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def split_refs(raw: str) -> list[str]:
    """`;`/`,` 分隔引用列表 → 去重保序。"""
    items: list[str] = []
    for token in (raw or "").replace(",", ";").split(";"):
        token = token.strip()
        if token and token not in items:
            items.append(token)
    return items


def build_must_read(
    item: dict[str, Any],
    bc_rows: list[dict[str, str]],
    chain_rows: list[dict[str, str]],
    feature_map: dict[str, Any],
    surface_rows: list[dict[str, str]],
    shared_relation_ids: list[str],
) -> dict[str, list[str]]:
    """MUST_READ 段（批次 2 #85）：从冻结快照聚合该 feature 的必读输入。"""
    feature_id = str(item.get("feature_id", ""))
    bc_ids = {str(b) for b in item.get("bc_ids", [])}

    android_source_refs: list[str] = []
    for row in bc_rows:
        if str(row.get("bc_id", "")).strip() in bc_ids:
            for ref in split_refs(str(row.get("source_refs", ""))):
                if ref not in android_source_refs:
                    android_source_refs.append(ref)

    runtime_evidence_refs: list[str] = []
    for row in chain_rows:
        if str(row.get("feature_id", "")).strip() != feature_id:
            continue
        evidence = str(row.get("evidence_dir", "")).strip()
        if not evidence:
            continue
        ref = (f"phase-02-android-inventory/runtime-evidence/{evidence}"
               if not evidence.startswith("runtime-evidence") else
               f"phase-02-android-inventory/{evidence}")
        if ref not in runtime_evidence_refs:
            runtime_evidence_refs.append(ref)

    surfaces = item.get("surfaces") or []
    surface_ids = {
        str(s.get("id", "")).strip()
        for s in surfaces if isinstance(s, dict) and s.get("id")
    }
    p3_surface_plan: list[str] = []
    for row in surface_rows:
        row_surface = str(row.get("page_id", "")).strip()
        row_features = split_refs(str(row.get("feature_ids", "")))
        if row_surface in surface_ids or feature_id in row_features:
            shell_id = str(row.get("surface_shell_id", "")).strip()
            if shell_id and shell_id not in p3_surface_plan:
                p3_surface_plan.append(shell_id)

    data_relations = sorted(
        {str(r) for r in item.get("data_relation_ids", [])}
        | set(shared_relation_ids))

    return {
        "behavior_contract_ids": sorted(bc_ids),
        "android_source_refs": android_source_refs,
        "runtime_evidence_refs": runtime_evidence_refs,
        "data_relations": data_relations,
        "visual_memory_surface": sorted(surface_ids),
        "p3_surface_plan": p3_surface_plan,
    }


def semantic_probe_binding(workspace: Path) -> dict[str, Any] | None:
    """读工作区探针本体的 expected hash（存在才绑定；旧 run 兼容 null）。"""
    probe_path = workspace / "harmony-project" / PROBE_RELATIVE_PATH
    if not probe_path.is_file():
        return None
    return {
        "probe_relative_path": PROBE_RELATIVE_PATH,
        "expected_sha256": sha256_file(probe_path),
        "immutable": True,
        "note": ("Phase 4 implementers must NOT modify this file; wire "
                 "providers via SemanticProbeRegistry.registerProbe in "
                 "their own source files instead"),
    }


def issue_one(
    workspace: Path,
    item: dict[str, Any],
    issued_by: str,
    bc_rows: list[dict[str, str]],
    chain_rows: list[dict[str, str]],
    feature_map: dict[str, Any],
    surface_rows: list[dict[str, str]],
    shared_relation_ids: list[str],
    input_lock_sha256: str,
    ledger_row: dict[str, str] | None,
) -> dict[str, str]:
    feature_id = str(item.get("feature_id", "")).strip()
    if not feature_id:
        raise ValueError("feature-dispatch entry lacks feature_id")
    must_read = build_must_read(
        item, bc_rows, chain_rows, feature_map, surface_rows,
        shared_relation_ids)
    if not must_read["behavior_contract_ids"]:
        raise ValueError(
            f"{feature_id}: no behavior contracts to read (dispatch broken)")
    probe = semantic_probe_binding(workspace)

    # ownership：从 implementation-ledger 行读四 owner（必须先填，fail-closed
    # 不发明默认 actor；manage_stage4_rework 校验工单与 ledger 一致）。
    ownership: dict[str, str] = {}
    if ledger_row is not None:
        for field in ("feature_owner_id", "ui_agent_id",
                      "business_data_agent_id",
                      "native_capability_agent_id"):
            value = str(ledger_row.get(field, "")).strip()
            if not value:
                raise ValueError(
                    f"{feature_id}: implementation-ledger row lacks "
                    f"{field}; fill the ledger before issuing the order")
            ownership[field] = value

    work_order_id = "FWO-" + hashlib.sha256(
        f"{feature_id}|{input_lock_sha256}".encode("utf-8")
    ).hexdigest()[:12].upper()
    relative = f"feature-work-orders/{work_order_id}.json"
    target = workspace / relative
    if target.exists():
        raise ValueError(
            f"Feature work order already exists (overwrite prohibited): "
            f"{work_order_id}")

    order = {
        "schema_version": "2.0",
        "work_order_id": work_order_id,
        "phase": 4,
        "feature_id": feature_id,
        "status": "ISSUED",
        "issued_at": utc_now(),
        "issued_by": issued_by,
        "verify_mode": item.get("verify_mode"),
        "risk_level": item.get("risk_level"),
        "bc_ids": item.get("bc_ids", []),
        "runtime_bc_ids": item.get("runtime_bc_ids", []),
        "data_reads": item.get("data_reads", []),
        "data_writes": item.get("data_writes", []),
        "data_relation_ids": item.get("data_relation_ids", []),
        "surfaces": item.get("surfaces", []),
        "harmony_steps": [],
        "ownership": ownership,
        # 批次 2 #85：机械化读回执的必读面（declarations 的
        # consumed_* 列必须回执其中的子集，Gate 4 强制）
        "must_read": must_read,
        "read_receipt_contract": {
            "consumed_bc_ids": ("implementation-declarations.csv column; "
                                "subset of must_read.behavior_contract_ids"),
            "consumed_source_refs": ("implementation-declarations.csv "
                                     "column; subset of must_read."
                                     "android_source_refs"),
            "consumed_runtime_refs": ("implementation-declarations.csv "
                                      "column; subset of must_read."
                                      "runtime_evidence_refs"),
            "gate_rule": ("verify_stage4 rule must_read_receipt: RUNTIME "
                          "feature with empty consumed_source_refs fails "
                          "the gate"),
        },
        "semantic_probe": probe,
        "stage04_input_lock_sha256": input_lock_sha256,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(order, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return {
        "work_order_id": work_order_id,
        "feature_id": feature_id,
        "relative_path": relative,
        "work_order_sha256": sha256_file(target),
        "issued_by": issued_by,
        "issued_at": order["issued_at"],
        "status": "ISSUED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="issue_feature_work_order.py",
        description="Issue per-feature Phase 4 work orders "
                    "(single dispatching path, batch 2 #85)")
    parser.add_argument("--workspace", required=True,
                        help="Phase 4 workspace (has feature-dispatch.json)")
    parser.add_argument("--feature-id", default="",
                        help="single feature to order")
    parser.add_argument("--all", action="store_true",
                        help="order every NOT_STARTED feature")
    parser.add_argument("--issued-by", required=True,
                        help="implementation lead actor id")
    args = parser.parse_args(argv)

    if not args.all and not args.feature_id:
        parser.error("either --feature-id or --all is required")
    if len(args.issued_by) < ACTOR_RE_MIN:
        parser.error("--issued-by is too short")

    workspace = Path(args.workspace).expanduser().absolute()
    dispatch_path = workspace / "feature-dispatch.json"
    lock_path = workspace / "stage-04-input-lock.json"
    registry_path = workspace / "feature-work-order-registry.csv"
    for path in (dispatch_path, lock_path):
        if not path.is_file():
            parser.error(f"Workspace artifact missing: {path}")

    dispatch = load_json(dispatch_path)
    entries = dispatch.get("dispatch")
    if not isinstance(entries, list) or not entries:
        parser.error("feature-dispatch.json has no dispatch entries")
    shared_relation_ids = list(dispatch.get("shared_data_relation_ids", []))

    existing = (read_csv_rows(registry_path)
                if registry_path.is_file() else [])
    active = {
        str(row.get("feature_id", "")).strip()
        for row in existing
        if str(row.get("status", "")).upper() != "SUPERSEDED"
    }

    selected = []
    if args.all:
        for item in entries:
            fid = str(item.get("feature_id", "")).strip()
            if fid in active:
                continue
            if str(item.get("status", "")) == "NOT_STARTED" or not active:
                selected.append(item)
    else:
        for item in entries:
            if str(item.get("feature_id", "")).strip() == args.feature_id:
                selected.append(item)
                break
        if not selected:
            parser.error(
                f"feature {args.feature_id!r} not in feature-dispatch.json")
    clash = sorted({str(i.get("feature_id", "")) for i in selected} & active)
    if clash:
        parser.error(
            f"Feature work order already active for: {clash}; supersede "
            "explicitly before reissuing")

    try:
        bc_rows = read_csv_rows(workspace / BC_SNAPSHOT)
        chain_rows = read_csv_rows(workspace / CHAINS_SNAPSHOT)
        feature_map = load_json(workspace / FEATURE_MAP_SNAPSHOT)
        surface_rows = read_csv_rows(workspace / SURFACE_REGISTRY_SNAPSHOT)
    except OSError as exc:
        parser.error(f"Cannot read upstream snapshot: {exc}")

    input_lock_sha256 = sha256_file(lock_path)
    # implementation-ledger：读 owner + 签发后回写 work_order_id/status
    ledger_path = workspace / "implementation-ledger.csv"
    ledger_rows: list[dict[str, str]] = []
    ledger_fields: list[str] = []
    if ledger_path.is_file():
        with ledger_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            ledger_fields = list(reader.fieldnames or [])
            ledger_rows = list(reader)
    ledger_by_feature = {
        str(row.get("feature_id", "")).strip(): row
        for row in ledger_rows
    }

    issued = []
    for item in selected:
        fid = str(item.get("feature_id", "")).strip()
        row = issue_one(
            workspace, item, args.issued_by, bc_rows, chain_rows,
            feature_map, surface_rows, shared_relation_ids,
            input_lock_sha256, ledger_by_feature.get(fid))
        issued.append(row)
        if fid in ledger_by_feature:
            ledger_by_feature[fid]["work_order_id"] = row["work_order_id"]
            ledger_by_feature[fid]["status"] = "IN_PROGRESS"

    if ledger_rows and ledger_fields:
        with ledger_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ledger_fields)
            writer.writeheader()
            writer.writerows(ledger_rows)

    write_header = not registry_path.exists()
    with registry_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerows(issued)

    print(json.dumps({
        "issued": [
            {"work_order_id": row["work_order_id"],
             "feature_id": row["feature_id"],
             "must_read_counts": {
                 key: len(load_json(
                     workspace / row["relative_path"])["must_read"][key])
                 for key in MUST_READ_KEYS
             },
             "semantic_probe_bound": bool(
                 load_json(workspace / row["relative_path"])
                 ["semantic_probe"])}
            for row in issued
        ],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
