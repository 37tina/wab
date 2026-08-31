#!/usr/bin/env python3
"""Issue an immutable Phase 4 feature-implementation work order from a current Gate 3 PASS.

v3（v4 蓝图，重写级授权）：Phase 4 工单从"按页面（32 输入文件）"改为
"按功能签发"，输入面收敛为 7 类核心产物：

  ① feature-map.json             功能语义地图（verify_mode 信任根）
  ② behavior-contracts.csv       行为契约（v4 七段结构）
  ③ data-relations.csv           功能 ↔ 数据对象读写关系
  ④ reconciliation.csv           源码理解 ↔ runtime 实测对账
  ⑤ runtime-chains 证据 + Phase 2 闭包（gmi_closure 唯一闭包权威）
  ⑥ Phase 3 骨架（input-lock / 闭包三件套 / 注册表）
  ⑦ H4ENV（phase3_henvs 逐 HENV 冻结记录）

旧 32 文件输入面（closure-report/CLOSED 三件套、inventory/evidence-index、
asset 四件套、静态五件套、advanced 三件套、probe/page gate、
architecture-map/public-ui/capability/asset-registry/advanced-obligations）、
GMI_EXEMPT_INPUT_KEYS 豁免集与 gmi_native_layout_of 探测整体退役——
v4 唯一路径原则，删旧不留双路径。

工单新增 feature_manifest（用户修正 4，SOURCE_CONFIRMED 功能覆盖清单）：
全部 included feature 逐条登记 verify_mode（RUNTIME / SOURCE_CONFIRM）——
普通功能也进工单，Gate 4 最低覆盖门槛的信任根；每功能附数据读写集
（data-relations 引用）、BC 引用（含 RUNTIME_REQUIRED 子集）、对账四态
计数与 surfaces 绑定。android_steps 已由 runtime-chains.csv 承载
（android_steps_ref）；harmony_steps 留空由 Phase 4 实施时填写。

本文件 STAGE4_INPUT_RELATIVES 必须与 harmonyos-feature-implementation/
scripts/init_implementation.py 的同名表保持一致（两处同步，勿单侧修改）。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from _human_gate import require_current_human_approval

from _team_execution import validate_order_receipts


ACTOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,95}$")
STAGE4_ROLE_KEYS = (
    "implementation_lead_id",
    "visual_asset_agent_id",
    "verification_executor_id",
    "parity_acceptance_agent_id",
)

# v4 七类核心产物输入面（Phase 2 侧 ①–⑤ + Phase 3 骨架 ⑥；⑦ H4ENV 走
# phase3_henvs 逐环境记录）。与 harmonyos-feature-implementation/scripts/
# init_implementation.py 的 STAGE4_INPUT_RELATIVES 保持一致。
STAGE4_INPUT_RELATIVES = {
    # ① 功能语义地图
    "phase2_feature_map_sha256": "phase-02-android-inventory/feature-map.json",
    # ② 行为契约（七段结构：user_intent/pre_state/semantic_input/
    #    data_state_change/observable_result/persistence_targets/
    #    external_side_effects）
    "phase2_behavior_contracts_sha256": "phase-02-android-inventory/behavior-contracts.csv",
    # ③ 数据关系
    "phase2_data_relations_sha256": "phase-02-android-inventory/data-relations.csv",
    # ④ 源码 ↔ runtime 对账
    "phase2_reconciliation_sha256": "phase-02-android-inventory/reconciliation.csv",
    # ⑤ runtime 行为链证据 + Phase 2 闭包
    "phase2_runtime_chains_sha256": "phase-02-android-inventory/runtime-evidence/runtime-chains.csv",
    "phase2_closure_sha256": "phase-02-android-inventory/phase-2-closure.json",
    # ⑥ Phase 3 骨架：input-lock / 闭包三件套 / 注册表
    "phase3_input_lock_sha256": "phase-03-harmony-scaffold/stage-03-input-lock.json",
    "phase3_gate_report_sha256": "phase-03-harmony-scaffold/stage-03-gate-report.json",
    "phase3_closure_manifest_sha256": "phase-03-harmony-scaffold/stage-03-closure-manifest.sha256",
    "phase3_closed_sha256": "phase-03-harmony-scaffold/CLOSED",
    "phase3_scaffold_snapshot_sha256": "phase-03-harmony-scaffold/scaffold-snapshot-manifest.json",
    "phase3_module_registry_sha256": "phase-03-harmony-scaffold/module-registry.csv",
    "phase3_route_registry_sha256": "phase-03-harmony-scaffold/route-registry.csv",
    "phase3_surface_registry_sha256": "phase-03-harmony-scaffold/surface-registry.csv",
    "phase3_capability_contracts_sha256": "phase-03-harmony-scaffold/capability-contracts.csv",
    "phase3_henv_registry_sha256": "phase-03-harmony-scaffold/environments/henv-registry.csv",
    # ⑦ H4ENV：phase3_henvs 逐环境冻结记录（见下方 HENV 循环）
}

# BC 七段结构必需列（v4 表头 fail-closed 子集校验）。semantic_input 为 v4
# 新增可选列（inventory 侧 BC_FIELDS 尾部追加，DictReader 兼容，缺值仅警告）：
# 本脚本行级消费不读取该列，v3 范式冻结 Phase 2 产物表头可缺——缺列不阻断
# （跨版本兼容修复：fail-closed 仅对真正被消费的列；replayer 侧别名映射已兼容）。
BC_SEMANTIC_COLUMNS = (
    "bc_id", "feature_id", "page_ref", "user_intent", "pre_state",
    "data_state_change", "observable_result", "persistence_targets",
    "external_side_effects", "evidence_class",
)
# v4 可选列（表头不在场时按空值兼容；在场时语义校验归 replayer 别名映射）
BC_OPTIONAL_V4_COLUMNS = ("semantic_input",)
DATA_RELATION_COLUMNS = ("relation_id", "feature_id", "data_object", "relation")
RECONCILIATION_COLUMNS = ("bc_id", "feature_id", "verdict")
RUNTIME_CHAINS_COLUMNS = ("bc_id", "feature_id", "chain_status")
# 批次 2 #85：runtime_evidence_refs 消费 evidence_dir；must_read 段聚合需要
RUNTIME_CHAINS_READ_COLUMNS = ("bc_id", "feature_id", "evidence_dir")
SURFACE_REGISTRY_COLUMNS = ("surface_shell_id", "page_id", "feature_ids")
VERIFY_MODES = ("RUNTIME", "SOURCE_CONFIRM")
RISK_LEVELS = ("high", "normal")
RECONCILIATION_VERDICTS = ("CONFIRMED", "CONFLICT", "SOURCE_CONFIRMED", "GAP")


def split_semicolon(raw: str) -> list[str]:
    """`;`/`,` 分隔列表 → 去空格去重保序（must_read 聚合用）。"""
    items: list[str] = []
    for token in (raw or "").replace(",", ";").split(";"):
        token = token.strip()
        if token and token not in items:
            items.append(token)
    return items


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_run_file(run_dir: Path, relative: str, label: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ValueError(f"Unsafe {label} path: {relative!r}")
    current = run_dir
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symbolic links are prohibited in {label} path: {relative}")
    resolved = current.resolve()
    try:
        resolved.relative_to(run_dir)
    except ValueError as exc:
        raise ValueError(f"{label} path escapes the migration run: {relative}") from exc
    if not resolved.is_file():
        raise ValueError(f"Missing {label}: {resolved}")
    return resolved


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Refusing symbolic-link output: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Refusing symbolic-link output: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if path.is_symlink():
        raise ValueError(f"Symbolic-link controller record is prohibited: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if not fields:
        raise ValueError(f"CSV has no header: {path}")
    return fields, rows


def atomic_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    if path.is_symlink():
        raise ValueError(f"Refusing symbolic-link controller record: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass


def require_columns(fields: list[str], required: tuple[str, ...], label: str) -> None:
    missing = [column for column in required if column not in fields]
    if missing:
        raise ValueError(f"{label} lacks required columns: {missing}")


def ownership_actor_ids(ownership: dict[str, Any]) -> set[str]:
    actors: set[str] = set()
    for value in ownership.values():
        if isinstance(value, str) and value:
            actors.add(value)
        elif isinstance(value, list):
            actors.update(str(item) for item in value if isinstance(item, str) and item)
    return actors


def build_feature_manifest(
    input_paths: dict[str, Path],
    included_features: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build the per-feature SOURCE_CONFIRMED coverage manifest (v4 user fix 4).

    Reads ① feature-map / ② behavior-contracts / ③ data-relations /
    ④ reconciliation with fail-closed checks, and returns
    (feature_manifest, shared_data_relation_ids). Every included feature gets
    exactly one entry — plain SOURCE_CONFIRM features are work-ordered too.

    收敛式重构批次 2（#85）：每项追加 must_read 段（机械化保证 Phase 4
    实施者读过 P2/Android 源码——declarations 的 consumed_* 列回执子集，
    Gate 4 强制）与 p3_surface_plan（surface-registry 承载体计划行）。
    本函数与 harmonyos-feature-implementation/scripts/init_implementation.py
    的同名函数必须保持逐字节一致（两处同步，勿单侧修改）。
    """
    # ① feature-map.json：verify_mode 信任根
    feature_map = load_json(input_paths["phase2_feature_map_sha256"])
    raw_features = feature_map.get("features")
    if not isinstance(raw_features, list) or any(not isinstance(item, dict) for item in raw_features):
        raise ValueError("feature-map.json features must be an object array")
    coverage = feature_map.get("coverage_gate")
    if not isinstance(coverage, dict) or coverage.get("included_features_covered") is not True:
        raise ValueError("feature-map coverage_gate has not confirmed included feature coverage")
    if coverage.get("missing"):
        raise ValueError(f"feature-map coverage_gate still reports missing features: {coverage['missing']}")
    fm_by_id: dict[str, dict[str, Any]] = {}
    for raw in raw_features:
        feature_id = str(raw.get("feature_id", "")).strip()
        if not feature_id or feature_id in fm_by_id:
            raise ValueError(f"feature-map has an empty or duplicate feature_id: {feature_id!r}")
        if raw.get("verify_mode") not in VERIFY_MODES:
            raise ValueError(f"feature-map {feature_id}: verify_mode must be one of {VERIFY_MODES}")
        if raw.get("risk_level") not in RISK_LEVELS:
            raise ValueError(f"feature-map {feature_id}: risk_level must be one of {RISK_LEVELS}")
        fm_by_id[feature_id] = raw
    outside = set(fm_by_id) - set(included_features)
    uncovered = set(included_features) - set(fm_by_id)
    if outside or uncovered:
        raise ValueError(
            "feature-map features and controller included scope differ: "
            f"extra={sorted(outside)} missing={sorted(uncovered)}"
        )

    # ② behavior-contracts.csv：BC 引用（含 RUNTIME_REQUIRED 子集）+
    # 批次 2 #85 android_source_refs 聚合（MUST_READ 段）
    bc_fields, bc_rows = load_csv(input_paths["phase2_behavior_contracts_sha256"])
    require_columns(bc_fields, BC_SEMANTIC_COLUMNS, "behavior-contracts.csv")
    bc_by_feature: dict[str, list[str]] = {}
    runtime_bc_by_feature: dict[str, list[str]] = {}
    source_refs_by_feature: dict[str, list[str]] = {}
    for row in bc_rows:
        feature_id = str(row.get("feature_id", "")).strip()
        bc_id = str(row.get("bc_id", "")).strip()
        if not bc_id:
            continue
        if feature_id and feature_id not in set(included_features):
            raise ValueError(f"behavior-contracts row {bc_id} references feature outside scope: {feature_id}")
        if not feature_id:
            continue
        bc_by_feature.setdefault(feature_id, []).append(bc_id)
        if str(row.get("evidence_class", "")) == "RUNTIME_REQUIRED":
            runtime_bc_by_feature.setdefault(feature_id, []).append(bc_id)
        for ref in split_semicolon(str(row.get("source_refs", ""))):
            if ref and ref not in source_refs_by_feature.setdefault(feature_id, []):
                source_refs_by_feature[feature_id].append(ref)

    # ③ data-relations.csv：每功能数据读写集引用（feature_id 空行 = 共享对象）
    dr_fields, dr_rows = load_csv(input_paths["phase2_data_relations_sha256"])
    require_columns(dr_fields, DATA_RELATION_COLUMNS, "data-relations.csv")
    relations_by_feature: dict[str, list[str]] = {}
    shared_relation_ids: list[str] = []
    for row in dr_rows:
        relation_id = str(row.get("relation_id", "")).strip()
        feature_id = str(row.get("feature_id", "")).strip()
        if str(row.get("relation", "")).strip() not in ("read", "write"):
            raise ValueError(f"data-relations row has an invalid relation: {relation_id!r}")
        if not relation_id:
            continue
        if feature_id:
            if feature_id not in set(included_features):
                raise ValueError(f"data-relations row {relation_id} references feature outside scope: {feature_id}")
            relations_by_feature.setdefault(feature_id, []).append(relation_id)
        else:
            shared_relation_ids.append(relation_id)

    # ④ reconciliation.csv：对账四态计数；CONFLICT 阻断签发
    rec_fields, rec_rows = load_csv(input_paths["phase2_reconciliation_sha256"])
    require_columns(rec_fields, RECONCILIATION_COLUMNS, "reconciliation.csv")
    verdicts_by_feature: dict[str, dict[str, int]] = {}
    conflict_rows: list[str] = []
    for row in rec_rows:
        feature_id = str(row.get("feature_id", "")).strip()
        bc_id = str(row.get("bc_id", "")).strip()
        verdict = str(row.get("verdict", "")).strip()
        if verdict not in RECONCILIATION_VERDICTS:
            raise ValueError(f"reconciliation row {bc_id} has an unknown verdict: {verdict!r}")
        if verdict == "CONFLICT":
            conflict_rows.append(bc_id or "<no-bc-id>")
        if not feature_id:
            continue
        bucket = verdicts_by_feature.setdefault(feature_id, {name: 0 for name in RECONCILIATION_VERDICTS})
        bucket[verdict] += 1
    if conflict_rows:
        raise ValueError(
            "reconciliation still records CONFLICT rows; resolve source-vs-runtime "
            f"conflicts before issuing Phase 4: {conflict_rows[:10]}"
        )

    # ⑤ runtime-chains.csv：批次 2 #85 读行聚合 evidence 引用（MUST_READ
    # 段 runtime_evidence_refs；evidence_dir 缺列按空处理，不阻断签发）
    chain_fields, chain_rows = load_csv(input_paths["phase2_runtime_chains_sha256"])
    require_columns(chain_fields, RUNTIME_CHAINS_COLUMNS, "runtime-chains.csv")
    evidence_refs_by_feature: dict[str, list[str]] = {}
    for row in chain_rows:
        feature_id = str(row.get("feature_id", "")).strip()
        evidence = str(row.get("evidence_dir", "") or "").strip()
        if not feature_id or not evidence:
            continue
        ref = (
            f"phase-02-android-inventory/runtime-evidence/{evidence}"
            if not evidence.startswith("runtime-evidence")
            else f"phase-02-android-inventory/{evidence}"
        )
        refs = evidence_refs_by_feature.setdefault(feature_id, [])
        if ref not in refs:
            refs.append(ref)

    # ⑥ surface-registry.csv：批次 2 #85 p3_surface_plan（承载体计划行）
    surface_fields, surface_rows = load_csv(input_paths["phase3_surface_registry_sha256"])
    require_columns(surface_fields, SURFACE_REGISTRY_COLUMNS, "surface-registry.csv")
    surface_plan_by_feature: dict[str, list[str]] = {}
    for row in surface_rows:
        shell_id = str(row.get("surface_shell_id", "")).strip()
        if not shell_id:
            continue
        for feature_id in split_semicolon(str(row.get("feature_ids", ""))):
            if feature_id and feature_id in set(included_features):
                plan = surface_plan_by_feature.setdefault(feature_id, [])
                if shell_id not in plan:
                    plan.append(shell_id)
    # feature-map surfaces 与 registry page_id 双向挂接（surfaces 里的
    # PAGE-ID 命中的 registry 行也计入对应 feature 的计划）
    for feature_id in included_features:
        entry = fm_by_id[feature_id]
        page_ids = {
            str(surface.get("id", "")).strip()
            for surface in (entry.get("surfaces") or [])
            if isinstance(surface, dict) and surface.get("id")
        }
        plan = surface_plan_by_feature.setdefault(feature_id, [])
        for row in surface_rows:
            shell_id = str(row.get("surface_shell_id", "")).strip()
            if not shell_id or shell_id in plan:
                continue
            if str(row.get("page_id", "")).strip() in page_ids:
                plan.append(shell_id)

    manifest: list[dict[str, Any]] = []
    for feature_id in included_features:
        entry = fm_by_id[feature_id]
        data_objects = entry.get("data_objects") if isinstance(entry.get("data_objects"), dict) else {}
        surface_ids = sorted(
            {
                str(surface.get("id", ""))
                for surface in (entry.get("surfaces") or [])
                if isinstance(surface, dict) and surface.get("id")
            }
        )
        manifest.append(
            {
                "feature_id": feature_id,
                "verify_mode": entry.get("verify_mode"),
                "risk_level": entry.get("risk_level"),
                "surfaces": entry.get("surfaces", []),
                # 数据读写集：feature-map 语义集合 + data-relations 行级引用
                "data_reads": list(data_objects.get("reads", [])),
                "data_writes": list(data_objects.get("writes", [])),
                "data_relation_ids": sorted(relations_by_feature.get(feature_id, [])),
                # BC 引用：全量 + RUNTIME_REQUIRED 子集（Phase 4 双端实跑分母）
                "bc_ids": sorted(bc_by_feature.get(feature_id, [])),
                "runtime_bc_ids": sorted(runtime_bc_by_feature.get(feature_id, [])),
                # 批次 2 #85 MUST_READ 段（read-receipt 分母，Gate 4 强制）
                "must_read": {
                    "behavior_contract_ids": sorted(bc_by_feature.get(feature_id, [])),
                    "android_source_refs": source_refs_by_feature.get(feature_id, []),
                    "runtime_evidence_refs": evidence_refs_by_feature.get(feature_id, []),
                    "data_relations": sorted(
                        set(relations_by_feature.get(feature_id, []))
                        | set(shared_relation_ids)),
                    "visual_memory_surface": surface_ids,
                    "p3_surface_plan": surface_plan_by_feature.get(feature_id, []),
                },
                # 对账四态计数（CONFLICT 恒为 0——上方已阻断）
                "reconciliation": verdicts_by_feature.get(
                    feature_id, {name: 0 for name in RECONCILIATION_VERDICTS}
                ),
                # android 步骤已由 runtime-chains.csv 承载；harmony 步骤由
                # Phase 4 实施时填写（工单模板留列）
                "android_steps_ref": "phase-02-android-inventory/runtime-evidence/runtime-chains.csv",
                "harmony_steps": [],
            }
        )
        if not bc_by_feature.get(feature_id):
            raise ValueError(f"feature {feature_id}: 0 behavior contracts (every included feature needs >= 1 BC)")
    return manifest, sorted(shared_relation_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--issued-by", required=True)
    for key in STAGE4_ROLE_KEYS:
        parser.add_argument("--" + key.replace("_", "-"), required=True)
    args = parser.parse_args()

    run_input = Path(args.run_dir).expanduser().absolute()
    if run_input.is_symlink():
        parser.error("Migration run must not be a symbolic link")
    run_dir = run_input.resolve()
    if not run_dir.is_dir():
        parser.error(f"Migration run does not exist: {run_dir}")

    try:
        scope_path = safe_run_file(run_dir, "controller/scope.json", "controller scope")
        gate_path = safe_run_file(run_dir, "controller/gate-report.json", "Gate 3 report")
        scope = load_json(scope_path)
        gate = load_json(gate_path)
        scope_sha256 = sha256_file(scope_path)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if (
        gate.get("phase") != 3
        or gate.get("verdict") != "PASS"
        or gate.get("scope_sha256") != scope_sha256
        or gate.get("errors")
    ):
        parser.error("A current, complete controller Gate 3 PASS is required")

    recheck = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("validate_gate.py")), "--run-dir", str(run_dir), "--phase", "3"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=180,
        check=False,
    )
    if recheck.returncode != 0:
        detail = recheck.stderr.strip() or recheck.stdout.strip()
        parser.error(f"Gate 3 baseline changed after its recorded PASS: {detail[:800]}")
    try:
        human_review = require_current_human_approval(run_dir, 3, gate_path)
    except ValueError as exc:
        parser.error(f"Current human approval is required after Gate 3 recheck: {exc}")

    controller_ownership = scope.get("ownership") if isinstance(scope.get("ownership"), dict) else {}
    controller_id = controller_ownership.get("migration_controller_id")
    if args.issued_by != controller_id:
        parser.error("--issued-by must equal the frozen migration controller")

    stage4_ownership = {key: str(getattr(args, key)).strip() for key in STAGE4_ROLE_KEYS}
    invalid = [key for key, value in stage4_ownership.items() if not ACTOR_RE.fullmatch(value)]
    if invalid:
        parser.error(f"Invalid Phase 4 actor ID(s): {invalid}")
    role_values = list(stage4_ownership.values())
    if len(role_values) != len(set(role_values)):
        parser.error("All four Phase 4 actor IDs must be distinct")

    try:
        registry_path = run_dir / "controller" / "work-order-registry.csv"
        registry_fields, registry_rows = load_csv(registry_path)
        active_phase3 = [
            row for row in registry_rows
            if row.get("phase") == "3" and row.get("status", "").upper() != "SUPERSEDED"
        ]
        if len(active_phase3) != 1:
            raise ValueError("Controller must have exactly one active Phase 3 work order")
        phase3_order_path = safe_run_file(
            run_dir, active_phase3[0].get("relative_path", ""), "Phase 3 work order"
        )
        phase3_order = load_json(phase3_order_path)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    receipt_errors = validate_order_receipts(run_dir, phase3_order_path)
    if receipt_errors:
        parser.error("Phase 3 worker dispatch is incomplete: " + "; ".join(receipt_errors[:8]))
    prior_actors = ownership_actor_ids(controller_ownership)
    phase3_ownership = phase3_order.get("ownership") if isinstance(phase3_order.get("ownership"), dict) else {}
    prior_actors.update(ownership_actor_ids(phase3_ownership))
    overlaps = sorted(set(role_values) & prior_actors)
    if overlaps:
        parser.error(f"Phase 4 actors must differ from all frozen Phase 1–3 actors: {overlaps}")

    # v4：7 类产物输入面（无豁免分支——gmi_exempt/gmi_native 探测已退役）
    try:
        input_paths = {
            digest_key: safe_run_file(run_dir, relative, digest_key)
            for digest_key, relative in STAGE4_INPUT_RELATIVES.items()
        }
        henv_rows = load_csv(input_paths["phase3_henv_registry_sha256"])[1]
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    included_features = scope.get("migration_scope", {}).get("included_features", [])
    if not isinstance(included_features, list) or not included_features:
        parser.error("Controller scope has no included features to order")
    try:
        feature_manifest, shared_data_relation_ids = build_feature_manifest(input_paths, list(included_features))
    except (OSError, ValueError) as exc:
        parser.error(f"v4 feature manifest is not orderable: {exc}")

    # 批次 2 #85：DebugSemanticProbe expected hash——从 Phase 3 scaffold
    # 快照清单抽探针条目（P4 实施者禁改；Gate 4 校验工作区探针一致）。
    # 快照无探针（旧 Phase 3 产物）→ semantic_probe=None（Gate 4 跳过，
    # 向后兼容）。
    semantic_probe_binding: dict[str, Any] | None = None
    try:
        snapshot = load_json(input_paths["phase3_scaffold_snapshot_sha256"])
        entries = snapshot.get("files") if isinstance(snapshot, dict) else None
        if isinstance(entries, dict):
            entries = [
                {"path": key, **(value if isinstance(value, dict) else {})}
                for key, value in entries.items()
            ]
        probe_entry = None
        if isinstance(entries, list):
            probe_entry = next(
                (
                    item for item in entries
                    if isinstance(item, dict)
                    and str(item.get("path", "")).endswith(
                        "probe/DebugSemanticProbe.ets")
                ),
                None,
            )
        if isinstance(probe_entry, dict) and probe_entry.get("sha256"):
            semantic_probe_binding = {
                "probe_relative_path": str(probe_entry["path"]),
                "expected_sha256": str(probe_entry["sha256"]),
                "immutable": True,
                "note": (
                    "Phase 4 implementers must NOT modify this file; wire "
                    "providers via SemanticProbeRegistry.registerProbe in "
                    "their own source files instead"),
            }
    except (OSError, ValueError):
        semantic_probe_binding = None

    henv_records: list[dict[str, str]] = []
    seen_henv_ids: set[str] = set()
    try:
        for row in henv_rows:
            henv_id = str(row.get("henv_id", ""))
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{2,79}", henv_id) or henv_id in seen_henv_ids:
                raise ValueError(f"Unsafe or duplicate HENV-ID: {henv_id!r}")
            seen_henv_ids.add(henv_id)
            if row.get("status") != "FROZEN":
                raise ValueError(f"Phase 4 may consume only frozen HENV rows: {henv_id}")
            relative = f"phase-03-harmony-scaffold/environments/{henv_id}/harmony-environment.json"
            path = safe_run_file(run_dir, relative, f"HENV {henv_id}")
            digest = sha256_file(path)
            if row.get("environment_sha256") != digest:
                raise ValueError(f"HENV registry hash differs for {henv_id}")
            henv_records.append({"henv_id": henv_id, "relative_path": relative, "sha256": digest})
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not henv_records:
        parser.error("Phase 3 has no frozen HENV available to Phase 4")

    ledger_path = run_dir / "controller" / "task-ledger.csv"
    try:
        ledger_fields, ledger_rows = load_csv(ledger_path)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    phase4_ledger = [row for row in ledger_rows if row.get("phase") == "4"]
    if len(phase4_ledger) != 1:
        parser.error("Task ledger must contain exactly one Phase 4 row")
    active_phase4 = [
        row for row in registry_rows
        if row.get("phase") == "4" and row.get("status", "").upper() != "SUPERSEDED"
    ]
    if active_phase4:
        parser.error("A Phase 4 work order is already registered; supersede it explicitly before reissuing")

    gate_sha256 = sha256_file(gate_path)
    binding = "|".join(
        [scope_sha256, gate_sha256, sha256_file(phase3_order_path)]
        + [sha256_file(input_paths[key]) for key in sorted(input_paths)]
        + [record["sha256"] for record in sorted(henv_records, key=lambda item: item["henv_id"])]
        + role_values
    )
    suffix = hashlib.sha256(binding.encode("utf-8")).hexdigest()[:12].upper()
    work_order_id = f"WO-PHASE-04-{suffix}"
    work_order_relative = f"controller/work-orders/{work_order_id}.json"
    gate_snapshot_relative = f"controller/work-orders/{work_order_id}.phase-03-gate-report.json"
    work_orders_dir = run_dir / "controller" / "work-orders"
    if work_orders_dir.is_symlink():
        parser.error("Controller work-orders directory must not be a symbolic link")
    try:
        work_orders_dir.mkdir(parents=True, exist_ok=True)
        if not work_orders_dir.is_dir() or work_orders_dir.resolve().parent != (run_dir / "controller").resolve():
            raise ValueError("Controller work-orders directory is not canonical")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    work_order_path = run_dir / work_order_relative
    gate_snapshot_path = run_dir / gate_snapshot_relative
    if work_order_path.exists() or gate_snapshot_path.exists():
        parser.error(f"Phase 4 work order already exists; overwrite is prohibited: {work_order_id}")

    issued_at = utc_now()
    work_order: dict[str, Any] = {
        "work_order_id": work_order_id,
        "run_id": scope.get("run_id"),
        "phase": 4,
        "status": "ISSUED",
        "issued_at": issued_at,
        "issued_by": args.issued_by,
        "scope_relative_path": "controller/scope.json",
        "scope_sha256": scope_sha256,
        "controller_gate3_snapshot_relative_path": gate_snapshot_relative,
        "controller_gate3_sha256": gate_sha256,
        "human_review_id": human_review["review_id"],
        "human_review_decision": human_review["decision"],
        "human_review_gate_sha256": human_review["gate_report_sha256"],
        "upstream_phase3_work_order_id": phase3_order.get("work_order_id"),
        "upstream_phase3_work_order_relative_path": active_phase3[0].get("relative_path"),
        "upstream_phase3_work_order_sha256": sha256_file(phase3_order_path),
        "included_features": included_features,
        "excluded_features": scope.get("migration_scope", {}).get("excluded_features", []),
        # v4 按功能签发：SOURCE_CONFIRMED 功能覆盖清单（用户修正 4）——
        # 全部 included feature 逐条登记（普通功能也进工单），verify_mode 为
        # Gate 4 最低覆盖门槛的信任根；replayer/Gate 4 消费字段：
        # feature_id / verify_mode / bc_ids / runtime_bc_ids / data_relation_ids /
        # reconciliation / surfaces / harmony_steps。
        "feature_manifest": feature_manifest,
        "shared_data_relation_ids": shared_data_relation_ids,
        # 批次 2 #85：探针冻结绑定（expected hash；null = Phase 3 无探针，
        # Gate 4 跳过校验）
        "semantic_probe": semantic_probe_binding,
        "ownership": stage4_ownership,
        "phase3_henvs": sorted(henv_records, key=lambda item: item["henv_id"]),
        "required_skill": "harmonyos-feature-implementation",
        "business_implementation_allowed": True,
        "mp4_allowed": False,
        "required_return": [
            "stage-04-input-lock.json", "phase-manifest.json", "feature-dispatch.json",
            "feature-work-orders/", "implementation-ledger.csv", "surface-contracts.csv",
            "environments/", "harmony-project/", "builds/", "evidence/", "evidence-index.csv",
            "attempt-ledger.csv", "reviews/", "acceptance-ledger.csv", "rework-tickets.csv",
            "stage-04-gate-report.json", "stage-04-closure-manifest.sha256", "CLOSED",
        ],
    }
    for digest_key, relative in STAGE4_INPUT_RELATIVES.items():
        work_order[digest_key] = sha256_file(input_paths[digest_key])
        work_order[digest_key.removesuffix("_sha256") + "_relative_path"] = relative

    missing_registry_fields = {
        "work_order_id", "phase", "relative_path", "scope_sha256", "work_order_sha256",
        "issued_at", "issued_by", "status",
    } - set(registry_fields)
    if missing_registry_fields:
        parser.error(f"Work-order registry lacks columns: {sorted(missing_registry_fields)}")

    try:
        atomic_bytes(gate_snapshot_path, gate_path.read_bytes())
        atomic_json(work_order_path, work_order)
        work_order_sha256 = sha256_file(work_order_path)
        registry_rows.append(
            {
                "work_order_id": work_order_id,
                "phase": "4",
                "relative_path": work_order_relative,
                "scope_sha256": scope_sha256,
                "work_order_sha256": work_order_sha256,
                "issued_at": issued_at,
                "issued_by": args.issued_by,
                "status": "ISSUED",
            }
        )
        phase4_ledger[0].update(
            {
                "owner": stage4_ownership["implementation_lead_id"],
                "status": "IN_PROGRESS",
                "updated_at": issued_at,
                "notes": work_order_id,
            }
        )
        atomic_csv(registry_path, registry_fields, registry_rows)
        atomic_csv(ledger_path, ledger_fields, ledger_rows)
    except (OSError, ValueError) as exc:
        parser.error(f"Could not persist Phase 4 work order: {exc}")

    print(json.dumps({
        "work_order_id": work_order_id,
        "work_order": str(work_order_path),
        "work_order_sha256": work_order_sha256,
        "controller_gate3_snapshot": str(gate_snapshot_path),
        "features": len(feature_manifest),
        "runtime_features": sum(1 for item in feature_manifest if item["verify_mode"] == "RUNTIME"),
        "source_confirm_features": sum(1 for item in feature_manifest if item["verify_mode"] == "SOURCE_CONFIRM"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
