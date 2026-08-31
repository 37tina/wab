#!/usr/bin/env python3
"""Initialize governed Phase 4 from an issued controller work order.

v4（v4 蓝图，重写级授权）：输入面收敛为 7 类核心产物，Phase 4 按**功能**
组织实施（不再按页面/状态分派）：

  ① feature-map.json             功能语义地图（verify_mode 信任根）
  ② behavior-contracts.csv       行为契约（七段结构）
  ③ data-relations.csv           功能 ↔ 数据对象读写关系
  ④ reconciliation.csv           源码理解 ↔ runtime 实测对账
  ⑤ runtime-chains 证据 + Phase 2 闭包（gmi_closure 唯一闭包权威）
  ⑥ Phase 3 骨架（input-lock / 闭包三件套 / 注册表 / scaffold 快照）
  ⑦ H4ENV（基于 Phase 3 冻结 HENV 初始化，environments/ 落盘）

退役（v4 唯一路径原则，删旧不留双路径）：旧 32 文件输入面
（STAGE4_INPUT_RELATIVES 旧表）、gmi_exempt_input_keys 10 键豁免集、
gmi_native_layout 探测、静态五件套读取（pages/components/events/
transitions/runtime-observations）、advanced-obligations、旧 Phase 2
闭包三件套（closure-report/CLOSED）、inventory/evidence-index 行级链、
asset 四件套与资产快照/转换合同、architecture-map 精确覆盖校验、
page_acceptance 合同编译（compile_page_contracts /
compile_native_behavior_contracts / publish_page_contracts 调用移除；
page_acceptance_contract.py 文件本身的退役由改造 J 处理）、UiTest
snapshot 探针生成（prepare_uitest_probe 调用移除）、parity-map /
visual-elements / migration-unit-contracts / obligations /
page-implementation-ledger / page-contract-registry 页面范式产物。

初始化产出：
  * Phase 4 工作区（inputs/upstream 7 类输入快照 + harmony-project 骨架
    复制 + environments/ H4ENV 落盘 + 治理台账空表）
  * feature-dispatch.json——功能工单分派表（per-feature：verify_mode /
    BC 引用 / 数据读写集 / surfaces / 工单占位）
  * implementation-ledger.csv——per-feature 分派账本（治理列沿用模板）
  * surface-contracts.csv——薄表空骨架（replayer/Gate 4 消费列：
    feature_id / surfaces / entry_reachable / nav_pattern /
    native_impl_check / notes，实施期由 replayer 逐行回填）

本文件 STAGE4_INPUT_RELATIVES 与 feature manifest 构建口径必须与
android-harmony-migration-controller/scripts/issue_phase4_work_order.py
保持一致（两处同步，勿单侧修改）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from _common import (
    atomic_json,
    build_project_snapshot,
    csv_fieldnames,
    frozen_category_contracts,
    load_json,
    make_tree_read_only,
    parse_resolution,
    read_csv,
    safe_relative_path,
    sha256_file,
    utc_now,
    validate_actor,
    validate_id,
    write_csv,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSETS = SKILL_ROOT / "assets"
PHASE_NAME = "phase-04-harmony-implementation"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

STAGE4_ROLE_KEYS = (
    "implementation_lead_id",
    "visual_asset_agent_id",
    "verification_executor_id",
    "parity_acceptance_agent_id",
)
PHASE3_CLOSURE_EXCLUDES = {
    "stage-03-gate-report.json", "stage-03-closure-manifest.sha256", "CLOSED",
}
# P3 closure 生成时排除的生成目录（validate_stage3.py _excluded_generated）
P3_GENERATED_DIR_EXCLUDES = {
    ".git", ".hg", ".hvigor", ".idea", ".svn", "__pycache__",
    "build", "coverage", "dist", "node_modules", "oh_modules", "out",
}
BASE_CATEGORY_MAP = {
    "TOOLCHAIN": "TOOLCHAIN",
    "CLEAN_BUILD": "CLEAN_BUILD",
    "BUNDLE_CHECK": "BUNDLE_CHECK",
    "SIGNING_CHECK": "SIGNING_CHECK",
    "DEVICE_CHECK": "DEVICE",
    "CLEAN_INSTALL": "INSTALL",
    "LAUNCH": "LAUNCH",
    "SCREENSHOT_CAPTURE": "SCREENSHOT_CAPTURE",
}
SERIAL_CATEGORIES = {
    "BUNDLE_CHECK", "DEVICE_CHECK", "CLEAN_INSTALL", "SEED_RESET",
    "NETWORK_PROFILE", "PERMISSION_PROFILE", "LAUNCH", "NAVIGATE",
    "BUSINESS_ASSERT", "SCREENSHOT_CAPTURE", "UITEST_SNAPSHOT_CAPTURE",
}
BUNDLE_CATEGORIES = {
    "BUNDLE_CHECK", "SIGNING_CHECK", "CLEAN_INSTALL", "SEED_RESET", "PERMISSION_PROFILE",
    "LAUNCH", "NAVIGATE", "BUSINESS_ASSERT", "SCREENSHOT_CAPTURE",
    "UITEST_SNAPSHOT_CAPTURE",
}
BUSINESS_PROFILE_FIELDS = (
    "account_id", "account_role", "seed_data_id", "seed_reset_ref",
    "network_profile", "network_conditions_ref", "network_toggle_available",
    "locale", "theme", "font_scale", "timezone", "permissions_profile",
    "orientation",
)
SECRET_FIELD_RE = re.compile(
    r"(?i)^(?:password|passwd|passphrase|private[_-]?key|storepass|keypass|"
    r"api[_-]?token|access[_-]?token|client[_-]?secret|secret)$"
)

# v4 七类核心产物输入面（与 issue_phase4_work_order.py 保持一致，勿单侧修改）
STAGE4_INPUT_RELATIVES = {
    # ① 功能语义地图
    "phase2_feature_map_sha256": "phase-02-android-inventory/feature-map.json",
    # ② 行为契约（七段结构）
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
    # ⑦ H4ENV：work_order["phase3_henvs"] 逐环境冻结记录
}

# BC 七段结构必需列（表头 fail-closed 子集）。semantic_input 为 v4 新增可选列
# （inventory 侧尾部追加，DictReader 兼容，缺值仅警告）：init 行级消费不读取该列，
# v3 范式冻结 Phase 2 产物表头可缺——与 issue_phase4_work_order.py 同款跨版本
# 兼容修复（两处同步，勿单侧修改；replayer 侧别名映射已兼容）。
BC_SEMANTIC_COLUMNS = (
    "bc_id", "feature_id", "page_ref", "user_intent", "pre_state",
    "data_state_change", "observable_result", "persistence_targets",
    "external_side_effects", "evidence_class",
)
BC_OPTIONAL_V4_COLUMNS = ("semantic_input",)
DATA_RELATION_COLUMNS = ("relation_id", "feature_id", "data_object", "relation")
RECONCILIATION_COLUMNS = ("bc_id", "feature_id", "verdict")
RUNTIME_CHAINS_COLUMNS = ("bc_id", "feature_id", "chain_status")
VERIFY_MODES = ("RUNTIME", "SOURCE_CONFIRM")
RISK_LEVELS = ("high", "normal")
RECONCILIATION_VERDICTS = ("CONFIRMED", "CONFLICT", "SOURCE_CONFIRMED", "GAP")

# 薄表格式（replayer / Gate 4 消费）：init 只落 per-feature 空骨架，
# entry_reachable / nav_pattern / native_impl_check 由实施期回填。
SURFACE_CONTRACT_FIELDS = (
    "feature_id", "surfaces", "entry_reachable", "nav_pattern",
    "native_impl_check", "notes",
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_input(value: str, label: str) -> Path:
    raw = Path(value).expanduser().absolute()
    if raw.is_symlink():
        raise ValueError(f"{label} must not be a symbolic link: {raw}")
    try:
        return raw.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"Cannot resolve {label}: {exc}") from exc


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def indexed(rows: list[dict[str, str]], key: str, label: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        value = str(row.get(key, ""))
        if not value or value in result:
            raise ValueError(f"Missing or duplicate {label} {key}: {value!r}")
        result[value] = row
    return result


def reject_embedded_secrets(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_FIELD_RE.fullmatch(str(key)) and item not in (None, "", False, [], {}):
                raise ValueError(f"Secret-bearing field is prohibited: {path}.{key}")
            reject_embedded_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_embedded_secrets(item, f"{path}[{index}]")
    elif isinstance(value, str) and (
        "-----BEGIN" in value.upper() or "PRIVATE KEY-----" in value.upper()
    ):
        raise ValueError(f"Embedded private-key material is prohibited: {path}")


def closure_manifest_text(
    root: Path,
    *,
    exact_excludes: set[str],
    directory_excludes: set[str] | None = None,
) -> str:
    directory_excludes = directory_excludes or set()
    files: dict[str, Path] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        pure = PurePosixPath(relative)
        if relative in exact_excludes or any(part in directory_excludes for part in pure.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"Symbolic links are prohibited in a closed phase: {path}")
        files[relative] = path
    return "".join(f"{sha256_file(files[name])}  {name}\n" for name in sorted(files))


def verify_phase2_closure(closure_path: Path) -> None:
    """v4：Phase 2 闭包以 gmi_closure 产物为唯一权威（旧 closure-report/
    CLOSED 三件套退役）。校验强度对齐 gmi 闭包链：generator 绑定 + gate
    干净（unmapped=0、audit_discrepancy=0）。"""
    closure = require_object(load_json(closure_path), "Phase 2 gmi closure")
    if closure.get("generator") != "gmi_closure":
        raise ValueError("Phase 2 closure was not produced by gmi_closure")
    gate = require_object(closure.get("gate"), "gmi closure gate")
    if gate.get("unmapped") != 0 or gate.get("audit_discrepancy") != 0:
        raise ValueError(
            "Phase 2 closure gate is not clean: "
            f"unmapped={gate.get('unmapped')} audit_discrepancy={gate.get('audit_discrepancy')}"
        )


def verify_phase3_closed(phase3: Path) -> dict[str, Any]:
    report = require_object(load_json(phase3 / "stage-03-gate-report.json"), "Phase 3 gate report")
    actual = closure_manifest_text(
        phase3,
        exact_excludes=PHASE3_CLOSURE_EXCLUDES,
        directory_excludes=P3_GENERATED_DIR_EXCLUDES,
    )
    stored = (phase3 / "stage-03-closure-manifest.sha256").read_text(encoding="utf-8")
    if stored != actual:
        raise ValueError("Phase 3 closure manifest no longer exactly matches the workspace")
    if (phase3 / "CLOSED").read_text(encoding="utf-8").strip() != sha256_file(
        phase3 / "stage-03-gate-report.json"
    ):
        raise ValueError("Phase 3 CLOSED marker does not bind stage-03-gate-report.json")
    if report.get("phase") != 3 or report.get("verdict") != "PASS" or report.get("errors"):
        raise ValueError("Phase 3 is not an exact closed PASS")
    return report


def require_columns(fields: list[str], required: tuple[str, ...], label: str) -> None:
    missing = [column for column in required if column not in fields]
    if missing:
        raise ValueError(f"{label} lacks required columns: {missing}")


def _split_refs(raw: str) -> list[str]:
    """`;`/`,` 分隔列表 → 去空格去重保序（must_read 聚合用）。"""
    items: list[str] = []
    for token in (raw or "").replace(",", ";").split(";"):
        token = token.strip()
        if token and token not in items:
            items.append(token)
    return items


def build_feature_manifest(
    feature_map_path: Path,
    bc_path: Path,
    data_relations_path: Path,
    reconciliation_path: Path,
    runtime_chains_path: Path,
    included_features: list[str],
    surface_registry_path: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Rebuild the per-feature manifest from the locked inputs.

    口径与 issue_phase4_work_order.build_feature_manifest 完全一致（两处
    同步，勿单侧修改）；init 侧重算结果必须与工单冻结的 feature_manifest
    逐字节一致，防止工单与输入漂移。
    """
    feature_map = require_object(load_json(feature_map_path), "feature-map.json")
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

    with bc_path.open("r", encoding="utf-8", newline="") as handle:
        import csv as _csv

        bc_reader = _csv.DictReader(handle)
        bc_fields = list(bc_reader.fieldnames or [])
        bc_rows = list(bc_reader)
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
        # 批次 2 #85：android_source_refs 聚合（must_read 段）
        for ref in _split_refs(str(row.get("source_refs", ""))):
            if ref and ref not in source_refs_by_feature.setdefault(feature_id, []):
                source_refs_by_feature[feature_id].append(ref)

    data_rows = read_csv(data_relations_path)
    require_columns(list(data_rows[0].keys()) if data_rows else DATA_RELATION_COLUMNS,
                    DATA_RELATION_COLUMNS, "data-relations.csv")
    relations_by_feature: dict[str, list[str]] = {}
    shared_relation_ids: list[str] = []
    for row in data_rows:
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

    rec_rows = read_csv(reconciliation_path)
    require_columns(list(rec_rows[0].keys()) if rec_rows else RECONCILIATION_COLUMNS,
                    RECONCILIATION_COLUMNS, "reconciliation.csv")
    verdicts_by_feature: dict[str, dict[str, int]] = {}
    for row in rec_rows:
        feature_id = str(row.get("feature_id", "")).strip()
        verdict = str(row.get("verdict", "")).strip()
        if verdict not in RECONCILIATION_VERDICTS:
            raise ValueError(f"reconciliation row has an unknown verdict: {verdict!r}")
        if verdict == "CONFLICT":
            raise ValueError("reconciliation still records CONFLICT rows; Phase 4 may not initialize")
        if not feature_id:
            continue
        bucket = verdicts_by_feature.setdefault(feature_id, {name: 0 for name in RECONCILIATION_VERDICTS})
        bucket[verdict] += 1

    chain_rows = read_csv(runtime_chains_path)
    require_columns(list(chain_rows[0].keys()) if chain_rows else RUNTIME_CHAINS_COLUMNS,
                    RUNTIME_CHAINS_COLUMNS, "runtime-chains.csv")
    # 批次 2 #85：evidence 引用聚合（must_read 段 runtime_evidence_refs）
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

    # 批次 2 #85：surface-registry 计划行聚合（must_read 段 p3_surface_plan）
    surface_plan_by_feature: dict[str, list[str]] = {}
    if surface_registry_path is not None:
        surface_rows = read_csv(surface_registry_path)
        for row in surface_rows:
            shell_id = str(row.get("surface_shell_id", "")).strip()
            if not shell_id:
                continue
            for feature_id in _split_refs(str(row.get("feature_ids", ""))):
                if feature_id and feature_id in set(included_features):
                    plan = surface_plan_by_feature.setdefault(feature_id, [])
                    if shell_id not in plan:
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
        # 批次 2 #85：feature-map surfaces 命中的 registry 行也计入计划
        if surface_registry_path is not None:
            page_ids = set(surface_ids)
            plan = surface_plan_by_feature.setdefault(feature_id, [])
            for row in read_csv(surface_registry_path):
                shell_id = str(row.get("surface_shell_id", "")).strip()
                if not shell_id or shell_id in plan:
                    continue
                if str(row.get("page_id", "")).strip() in page_ids:
                    plan.append(shell_id)
        manifest.append(
            {
                "feature_id": feature_id,
                "verify_mode": entry.get("verify_mode"),
                "risk_level": entry.get("risk_level"),
                "surfaces": entry.get("surfaces", []),
                "data_reads": list(data_objects.get("reads", [])),
                "data_writes": list(data_objects.get("writes", [])),
                "data_relation_ids": sorted(relations_by_feature.get(feature_id, [])),
                "bc_ids": sorted(bc_by_feature.get(feature_id, [])),
                "runtime_bc_ids": sorted(runtime_bc_by_feature.get(feature_id, [])),
                # 批次 2 #85 MUST_READ 段（与 issue_phase4_work_order 同构，
                # 两处同步勿单侧修改）
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
                "reconciliation": verdicts_by_feature.get(
                    feature_id, {name: 0 for name in RECONCILIATION_VERDICTS}
                ),
                "android_steps_ref": "phase-02-android-inventory/runtime-evidence/runtime-chains.csv",
                "harmony_steps": [],
            }
        )
        if not bc_by_feature.get(feature_id):
            raise ValueError(f"feature {feature_id}: 0 behavior contracts (every included feature needs >= 1 BC)")
    return manifest, sorted(shared_relation_ids)


def verify_phase3_snapshot(phase3: Path, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    raw_entries = snapshot.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("Phase 3 scaffold snapshot has no entries")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise ValueError("Phase 3 scaffold snapshot contains a non-object entry")
        relative = str(raw.get("path", ""))
        if relative in seen:
            raise ValueError(f"Duplicate Phase 3 snapshot path: {relative}")
        seen.add(relative)
        path = safe_relative_path(phase3, relative, "Phase 3 snapshot entry")
        if not path.is_file():
            raise ValueError(f"Phase 3 snapshot entry is not a file: {path}")
        entry = {"path": relative, "sha256": sha256_file(path), "size": path.stat().st_size}
        if entry["sha256"] != raw.get("sha256") or entry["size"] != raw.get("size"):
            raise ValueError(f"Phase 3 snapshot entry changed: {relative}")
        entries.append(entry)
    canonical = json.dumps(entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if snapshot.get("entry_count") != len(entries) or snapshot.get("snapshot_sha256") != sha256_text(canonical):
        raise ValueError("Phase 3 scaffold snapshot digest/count differs")
    excluded = set(snapshot.get("excluded_generated_parts", []))
    project = phase3 / "harmony-project"
    actual_project: set[str] = set()
    for path in project.rglob("*"):
        relative = path.relative_to(project)
        if any(part in excluded for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"Symbolic links are prohibited in accepted project: {path}")
        if path.is_file():
            actual_project.add("harmony-project/" + relative.as_posix())
    snapshot_project = {item["path"] for item in entries if item["path"].startswith("harmony-project/")}
    if snapshot_project != actual_project:
        raise ValueError("Phase 3 snapshot does not exactly cover the accepted HarmonyOS project")
    return entries


def validate_environment_config(
    config_path: Path,
    scope_envs: dict[str, dict[str, Any]],
    base_henvs: dict[str, tuple[dict[str, Any], str]],
    henv_rows: dict[str, dict[str, str]],
    lead: str,
    frozen_at: str,
) -> dict[str, Any]:
    config = require_object(load_json(config_path), f"H4ENV config {config_path}")
    reject_embedded_secrets(config)
    h4env_id = validate_id(str(config.get("h4env_id", "")), "H4ENV-ID")
    source_env_id = validate_id(str(config.get("source_android_env_id", "")), "source ENV-ID")
    base_henv_id = validate_id(str(config.get("base_henv_id", "")), "base HENV-ID")
    device_id = validate_id(str(config.get("device_id", "")), "HDEVICE-ID")
    if validate_actor(str(config.get("created_by", "")), "H4ENV creator") != lead:
        raise ValueError(f"{h4env_id}: created_by must be the frozen implementation lead")
    if config.get("required") is not True:
        raise ValueError(f"{h4env_id}: only required H4ENV configurations may be initialized")
    source_env = scope_envs.get(source_env_id)
    if not source_env:
        raise ValueError(f"{h4env_id}: unknown Android environment {source_env_id}")
    base_pair = base_henvs.get(base_henv_id)
    if not base_pair:
        raise ValueError(f"{h4env_id}: base HENV is not in the controller work order: {base_henv_id}")
    base, base_sha = base_pair
    henv_row = henv_rows.get(base_henv_id)
    if not henv_row or henv_row.get("status") != "FROZEN" or henv_row.get("environment_sha256") != base_sha:
        raise ValueError(f"{h4env_id}: base HENV registry/hash differs")
    devices = [item for item in base.get("devices", []) if isinstance(item, dict)]
    device = next((item for item in devices if item.get("device_id") == device_id), None)
    if not device:
        raise ValueError(f"{h4env_id}: unknown frozen device {device_id}")
    if (
        str(device.get("device_type", "")).lower() != "emulator"
        or device.get("required") is not True
        or device.get("screenshot_required") is not True
    ):
        raise ValueError(f"{h4env_id}: formal validation requires a required screenshot emulator")
    serial = str(device.get("serial", ""))
    application = base.get("application") if isinstance(base.get("application"), dict) else {}
    bundle_name = str(application.get("bundle_name", ""))
    if (
        not serial or not bundle_name
        or config.get("device_serial") != serial
        or config.get("bundle_name") != bundle_name
    ):
        raise ValueError(f"{h4env_id}: config must bind the exact frozen serial and Bundle")
    selector = config.get("device_selector_tokens")
    if (
        not isinstance(selector, list) or not selector
        or any(not isinstance(token, str) or not token for token in selector)
        or serial not in selector
    ):
        raise ValueError(f"{h4env_id}: device_selector_tokens do not bind the frozen serial")
    contracts = frozen_category_contracts(config)
    if os.environ.get("ANDROID_HARMONY_TEST_FIXTURES") != "1":
        for category, contract in contracts.items():
            parts = {part.lower() for part in Path(contract["resolved_executable"]).parts}
            if "tests" in parts or "fake_harmony.py" in str(contract["resolved_executable"]).lower():
                raise ValueError(
                    f"{h4env_id}: synthetic test executable is prohibited for formal evidence: {category}"
                )
    for category in SERIAL_CATEGORIES:
        # native-adaptive 形状不含像素采集类别——跳过不存在的（形状合法性已由
        # frozen_category_contracts 保证，见 _common.PHASE4_NATIVE_ADAPTIVE_CATEGORY_SET）
        if category not in contracts:
            continue
        if serial not in contracts[category]["required_argv_tokens"]:
            raise ValueError(f"{h4env_id}: {category} does not bind the exact frozen serial")
    for category in BUNDLE_CATEGORIES:
        if category not in contracts:
            continue
        if bundle_name not in contracts[category]["required_argv_tokens"]:
            raise ValueError(f"{h4env_id}: {category} does not bind the exact frozen Bundle")
    base_contracts = base.get("toolchain", {}).get("category_contracts", {})
    for category, base_category in BASE_CATEGORY_MAP.items():
        # native-adaptive 形状不含像素采集类别——跳过（形状合法性已由
        # frozen_category_contracts 保证）
        if category not in contracts:
            continue
        base_contract = base_contracts.get(base_category)
        if not isinstance(base_contract, dict):
            raise ValueError(f"{h4env_id}: base HENV lacks category {base_category}")
        if (
            contracts[category]["resolved_executable"] != base_contract.get("resolved_executable")
            or contracts[category]["executable_sha256"] != base_contract.get("executable_sha256")
        ):
            raise ValueError(f"{h4env_id}: {category} executable differs from base HENV {base_category}")
    comparison = config.get("comparison")
    if not isinstance(comparison, dict):
        raise ValueError(f"{h4env_id}: comparison policy is missing")
    width = comparison.get("screenshot_width")
    height = comparison.get("screenshot_height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise ValueError(f"{h4env_id}: screenshot dimensions must be positive integers")
    if (width, height) != parse_resolution(str(device.get("resolution", ""))):
        raise ValueError(f"{h4env_id}: screenshot dimensions differ from the frozen emulator")
    # Fixed screen parity: the H4ENV resolution must stay byte-identical to the
    # frozen Android environment profile used for Phase 2 evidence capture on
    # the same ENV-ID (no resize fallback — resizing would mask real drift).
    android_resolution = str(source_env.get("resolution", "")).strip()
    if not android_resolution:
        raise ValueError(f"{h4env_id}: source Android environment lacks resolution")
    if (width, height) != parse_resolution(android_resolution):
        raise ValueError(
            f"{h4env_id}: screenshot dimensions differ from the frozen Android "
            f"environment resolution {android_resolution}"
        )
    bounds = comparison.get("content_bounds")
    if not isinstance(bounds, list) or len(bounds) != 4 or any(not isinstance(item, int) for item in bounds):
        raise ValueError(f"{h4env_id}: content_bounds must be four integers")
    x, y, content_width, content_height = bounds
    if (
        x < 0 or y < 0 or content_width <= 0 or content_height <= 0
        or x + content_width > width or y + content_height > height
    ):
        raise ValueError(f"{h4env_id}: content_bounds escape the screenshot")
    tolerance = comparison.get("geometry_tolerance_px")
    if not isinstance(tolerance, int) or tolerance < 0:
        raise ValueError(f"{h4env_id}: geometry_tolerance_px must be nonnegative")
    business_profile = {field: source_env.get(field) for field in BUSINESS_PROFILE_FIELDS}
    missing_business = [
        field for field, value in business_profile.items()
        if value is None or (isinstance(value, str) and not value.strip())
    ]
    if missing_business or not isinstance(business_profile["network_toggle_available"], bool):
        raise ValueError(f"{h4env_id}: Android business profile is incomplete: {missing_business}")
    if "business_profile" in config and config["business_profile"] != business_profile:
        raise ValueError(f"{h4env_id}: supplied business_profile differs from controller scope")
    return {
        "h4env_id": h4env_id,
        "source_android_env_id": source_env_id,
        "base_henv_id": base_henv_id,
        "device_id": device_id,
        "device_serial": serial,
        "bundle_name": bundle_name,
        "created_by": lead,
        "required": True,
        "frozen_at": frozen_at,
        "device_selector_tokens": selector,
        "category_contracts": contracts,
        "comparison": comparison,
        "business_profile": business_profile,
        "base_henv_sha256": base_sha,
        "base_application": application,
        "base_toolchain": base.get("toolchain"),
        "emulator": device,
    }


def copy_template_csv(target: Path, template_name: str) -> None:
    shutil.copyfile(ASSETS / template_name, target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--work-order", required=True)
    parser.add_argument("--implementation-lead", required=True)
    parser.add_argument("--environment-config", action="append", required=True)
    args = parser.parse_args()

    try:
        run_dir = canonical_input(args.run_dir, "migration run")
        work_order_path = canonical_input(args.work_order, "Phase 4 work order")
        lead = validate_actor(args.implementation_lead, "implementation lead")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not run_dir.is_dir():
        parser.error(f"Migration run does not exist: {run_dir}")
    work_orders_root = (run_dir / "controller" / "work-orders").resolve()
    try:
        work_order_path.relative_to(work_orders_root)
    except ValueError:
        parser.error(f"Work order must be controller-owned below: {work_orders_root}")
    if work_order_path.parent != work_orders_root:
        parser.error("Phase 4 work order must be a direct controller/work-orders child")

    controller_dir = run_dir / "controller"
    phase2 = run_dir / "phase-02-android-inventory"
    phase3 = run_dir / "phase-03-harmony-scaffold"
    phase_dir = run_dir / PHASE_NAME
    if phase_dir.exists():
        parser.error(f"Phase 4 workspace already exists; overwrite is prohibited: {phase_dir}")
    try:
        scope_path = safe_relative_path(run_dir, "controller/scope.json", "controller scope")
        current_gate_path = safe_relative_path(run_dir, "controller/gate-report.json", "current controller Gate 3")
        scope = require_object(load_json(scope_path), "controller scope")
        work_order = require_object(load_json(work_order_path), "Phase 4 work order")
        registry_path = controller_dir / "work-order-registry.csv"
        registry_rows = read_csv(registry_path)
        work_order_id = validate_id(str(work_order.get("work_order_id", "")), "Phase 4 Work-Order-ID")
        if work_order_path.name != f"{work_order_id}.json":
            raise ValueError("Phase 4 work-order filename does not match Work-Order-ID")
        active_phase4 = [
            row for row in registry_rows
            if row.get("phase") == "4" and row.get("status", "").upper() != "SUPERSEDED"
        ]
        matches = [
            row for row in registry_rows
            if row.get("phase") == "4" and row.get("work_order_id") == work_order_id
        ]
        if len(active_phase4) != 1 or len(matches) != 1 or active_phase4[0] != matches[0]:
            raise ValueError("Controller must register exactly this one active Phase 4 work order")
        registry_row = matches[0]
        registered_path = safe_relative_path(
            run_dir, registry_row.get("relative_path", ""), "registered Phase 4 work order"
        )
        scope_sha = sha256_file(scope_path)
        work_order_sha = sha256_file(work_order_path)
        controller_actor = scope.get("ownership", {}).get("migration_controller_id")
        if (
            registered_path != work_order_path
            or registry_row.get("status") != "ISSUED"
            or registry_row.get("scope_sha256") != scope_sha
            or registry_row.get("work_order_sha256") != work_order_sha
            or registry_row.get("issued_by") != controller_actor
            or work_order.get("run_id") != scope.get("run_id")
            or work_order.get("phase") != 4
            or work_order.get("status") != "ISSUED"
            or work_order.get("issued_by") != controller_actor
            or work_order.get("scope_relative_path") != "controller/scope.json"
            or work_order.get("scope_sha256") != scope_sha
            or work_order.get("required_skill") != "harmonyos-feature-implementation"
            or work_order.get("business_implementation_allowed") is not True
            or work_order.get("mp4_allowed") is not False
        ):
            raise ValueError("Phase 4 work-order registration, identity, scope, or authority differs")
        ownership = work_order.get("ownership")
        if not isinstance(ownership, dict) or set(ownership) != set(STAGE4_ROLE_KEYS):
            raise ValueError("Phase 4 work order must freeze exactly four governance roles")
        role_values = [validate_actor(str(ownership[key]), key) for key in STAGE4_ROLE_KEYS]
        if len(role_values) != len(set(role_values)):
            raise ValueError("Phase 4 governance actors must be distinct")
        if ownership["implementation_lead_id"] != lead:
            raise ValueError("--implementation-lead differs from the controller work order")
        if work_order.get("included_features") != scope.get("migration_scope", {}).get("included_features"):
            raise ValueError("Phase 4 included feature scope differs from controller scope")
        if work_order.get("excluded_features") != scope.get("migration_scope", {}).get("excluded_features"):
            raise ValueError("Phase 4 excluded feature scope differs from controller scope")

        phase3_relative = str(work_order.get("upstream_phase3_work_order_relative_path", ""))
        phase3_work_order_path = safe_relative_path(run_dir, phase3_relative, "upstream Phase 3 work order")
        phase3_work_order = require_object(load_json(phase3_work_order_path), "Phase 3 work order")
        phase3_registry = [
            row for row in registry_rows
            if row.get("phase") == "3" and row.get("status", "").upper() != "SUPERSEDED"
        ]
        if (
            len(phase3_registry) != 1
            or phase3_registry[0].get("work_order_id") != phase3_work_order.get("work_order_id")
            or phase3_registry[0].get("relative_path") != phase3_relative
            or phase3_registry[0].get("work_order_sha256") != sha256_file(phase3_work_order_path)
            or work_order.get("upstream_phase3_work_order_id") != phase3_work_order.get("work_order_id")
            or work_order.get("upstream_phase3_work_order_sha256") != sha256_file(phase3_work_order_path)
        ):
            raise ValueError("Phase 4 work order is not bound to the one active Phase 3 work order")
        prior_actors: set[str] = set()
        for source_ownership in (scope.get("ownership", {}), phase3_work_order.get("ownership", {})):
            if not isinstance(source_ownership, dict):
                continue
            for value in source_ownership.values():
                if isinstance(value, str) and value:
                    prior_actors.add(value)
                elif isinstance(value, list):
                    prior_actors.update(item for item in value if isinstance(item, str) and item)
        if set(role_values) & prior_actors:
            raise ValueError("Phase 4 governance roles overlap frozen Phase 1-3 actors")

        gate_snapshot_path = safe_relative_path(
            run_dir,
            str(work_order.get("controller_gate3_snapshot_relative_path", "")),
            "controller-owned Gate 3 snapshot",
        )
        if (
            sha256_file(gate_snapshot_path) != work_order.get("controller_gate3_sha256")
            or sha256_file(current_gate_path) != work_order.get("controller_gate3_sha256")
            or current_gate_path.read_bytes() != gate_snapshot_path.read_bytes()
        ):
            raise ValueError("Current/frozen controller Gate 3 differs from the Phase 4 work order")
        frozen_gate = require_object(load_json(gate_snapshot_path), "frozen controller Gate 3")
        if frozen_gate.get("phase") != 3 or frozen_gate.get("verdict") != "PASS" or frozen_gate.get("errors"):
            raise ValueError("Frozen controller Gate 3 is not a complete PASS")

        gate_hash_before = sha256_file(current_gate_path)
        controller_validator = SKILL_ROOT.parent / "android-harmony-migration-controller" / "scripts" / "validate_gate.py"
        recheck = subprocess.run(
            [sys.executable, str(controller_validator), "--run-dir", str(run_dir), "--phase", "3"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=240,
            check=False,
        )
        if recheck.returncode != 0 or sha256_file(current_gate_path) != gate_hash_before:
            detail = recheck.stderr.strip() or recheck.stdout.strip()
            raise ValueError(f"Read-only Gate 3 recheck failed or changed controller state: {detail[:800]}")

        # v4：Phase 2 闭包 = gmi_closure 唯一权威；Phase 3 闭包三件套沿用。
        verify_phase2_closure(phase2 / "phase-2-closure.json")
        phase3_report = verify_phase3_closed(phase3)
        if phase3_report.get("source_snapshot_sha256") is None:
            raise ValueError("Phase 3 gate does not bind a scaffold snapshot")

        small_sources: list[tuple[str, Path, str]] = [
            ("controller-scope", scope_path, scope_sha),
            ("phase4-work-order", work_order_path, work_order_sha),
            ("controller-gate3-snapshot", gate_snapshot_path, str(work_order["controller_gate3_sha256"])),
            ("phase3-work-order", phase3_work_order_path, str(work_order["upstream_phase3_work_order_sha256"])),
        ]
        locked_sources: dict[str, Path] = {}
        for digest_key, expected_relative in STAGE4_INPUT_RELATIVES.items():
            relative_key = digest_key.removesuffix("_sha256") + "_relative_path"
            if work_order.get(relative_key) != expected_relative:
                raise ValueError(f"Phase 4 work order has noncanonical {relative_key}")
            source = safe_relative_path(run_dir, expected_relative, digest_key)
            digest = str(work_order.get(digest_key, ""))
            if not SHA256_RE.fullmatch(digest) or sha256_file(source) != digest:
                raise ValueError(f"Phase 4 work-order input changed: {digest_key}")
            label = digest_key.removesuffix("_sha256")
            locked_sources[label] = source
            small_sources.append((label, source, digest))

        included_features = list(work_order.get("included_features", []))
        if (
            not included_features
            or len(included_features) != len(set(included_features))
        ):
            raise ValueError("Phase 4 work order has no unique included features")

        # v4 防御性复核：从锁定输入重算 feature manifest，必须与工单冻结值
        # 完全一致（口径与 issue_phase4_work_order.build_feature_manifest 相同）。
        feature_manifest, shared_data_relation_ids = build_feature_manifest(
            locked_sources["phase2_feature_map"],
            locked_sources["phase2_behavior_contracts"],
            locked_sources["phase2_data_relations"],
            locked_sources["phase2_reconciliation"],
            locked_sources["phase2_runtime_chains"],
            included_features,
            locked_sources.get("phase3_surface_registry"),
        )
        if work_order.get("feature_manifest") != feature_manifest:
            raise ValueError("Work-order feature_manifest differs from the locked Phase 2 inputs")
        if work_order.get("shared_data_relation_ids") != shared_data_relation_ids:
            raise ValueError("Work-order shared_data_relation_ids differs from the locked Phase 2 inputs")

        # Phase 3 骨架快照（harmony-project 复制源）
        phase3_snapshot = require_object(
            load_json(locked_sources["phase3_scaffold_snapshot"]), "Phase 3 scaffold snapshot"
        )
        snapshot_entries = verify_phase3_snapshot(phase3, phase3_snapshot)
        if phase3_report.get("source_snapshot_sha256") != phase3_snapshot.get("snapshot_sha256"):
            raise ValueError("Phase 3 gate references another scaffold snapshot")

        # Phase 3 注册表轻校验（行级业务判定归 Gate 3/实施期；此处只锁
        # 唯一性与在场性——内容哈希已由工单输入锁绑定）
        indexed(read_csv(locked_sources["phase3_module_registry"]), "harmony_module_id", "Harmony module")
        indexed(read_csv(locked_sources["phase3_route_registry"]), "route_id", "Harmony route")
        indexed(read_csv(locked_sources["phase3_surface_registry"]), "surface_shell_id", "Harmony surface")
        indexed(read_csv(locked_sources["phase3_capability_contracts"]), "capability_requirement_id", "capability")
        henv_rows = indexed(
            read_csv(locked_sources["phase3_henv_registry"]), "henv_id", "HENV registry"
        )

        henv_records = work_order.get("phase3_henvs")
        if not isinstance(henv_records, list) or not henv_records:
            raise ValueError("Phase 4 work order lacks Phase 3 HENV records")
        base_henvs: dict[str, tuple[dict[str, Any], str]] = {}
        seen_small_sources = {source.resolve() for _, source, _ in small_sources}
        for raw in henv_records:
            if not isinstance(raw, dict):
                raise ValueError("Phase 4 HENV record must be an object")
            henv_id = validate_id(str(raw.get("henv_id", "")), "HENV-ID")
            if henv_id in base_henvs:
                raise ValueError(f"Duplicate Phase 3 HENV: {henv_id}")
            expected_relative = f"phase-03-harmony-scaffold/environments/{henv_id}/harmony-environment.json"
            if raw.get("relative_path") != expected_relative:
                raise ValueError(f"Noncanonical Phase 3 HENV path: {henv_id}")
            path = safe_relative_path(run_dir, expected_relative, f"Phase 3 HENV {henv_id}")
            digest = str(raw.get("sha256", ""))
            if not SHA256_RE.fullmatch(digest) or sha256_file(path) != digest:
                raise ValueError(f"Frozen Phase 3 HENV changed: {henv_id}")
            if path.resolve() in seen_small_sources:
                raise ValueError(f"Duplicate Phase 4 small input source: {path}")
            seen_small_sources.add(path.resolve())
            base_henvs[henv_id] = (require_object(load_json(path), f"HENV {henv_id}"), digest)
            small_sources.append((f"phase3-henv-{henv_id}", path, digest))

        scope_env_values = scope.get("environments")
        if not isinstance(scope_env_values, list) or not scope_env_values:
            raise ValueError("Controller scope has no Android environments")
        scope_envs = {str(item.get("env_id")): item for item in scope_env_values if isinstance(item, dict)}
        initialized_at = utc_now()
        environments: list[dict[str, Any]] = []
        h4env_ids: set[str] = set()
        for raw_path in args.environment_config:
            config_path = canonical_input(raw_path, "H4ENV config")
            normalized = validate_environment_config(
                config_path, scope_envs, base_henvs, henv_rows, lead, initialized_at
            )
            if normalized["h4env_id"] in h4env_ids:
                raise ValueError(f"Duplicate H4ENV-ID: {normalized['h4env_id']}")
            h4env_ids.add(normalized["h4env_id"])
            environments.append(normalized)
        # v4：inventory 行级 env 绑定已退役；H4ENV 映射必须覆盖 scope 冻结的
        # 全部 Android 环境（环境面完整性不降级）。
        required_source_envs = set(scope_envs)
        mapped_source_envs = {item["source_android_env_id"] for item in environments}
        if required_source_envs != mapped_source_envs:
            raise ValueError(
                f"H4ENV mapping must exactly cover the frozen Android environments; "
                f"missing={sorted(required_source_envs - mapped_source_envs)}, "
                f"extra={sorted(mapped_source_envs - required_source_envs)}"
            )
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        parser.error(str(exc))

    try:
        with tempfile.TemporaryDirectory(prefix=f".{PHASE_NAME}-", dir=run_dir) as temp_name:
            temp_dir = Path(temp_name)
            for name in (
                "inputs/upstream", "environments", "feature-work-orders", "reviews",
                "builds", "evidence", "attempts", ".locks", ".staging", "harmony-project",
            ):
                (temp_dir / name).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ASSETS / "attempt-ledger.template.csv", temp_dir / "attempt-ledger.csv")

            input_records: list[dict[str, Any]] = []
            for number, (label, source, digest) in enumerate(small_sources, start=1):
                suffix = source.suffix or ".bin"
                snapshot_relative = f"inputs/upstream/{number:02d}-{label}{suffix}"
                snapshot_temp = temp_dir / snapshot_relative
                shutil.copyfile(source, snapshot_temp)
                if sha256_file(snapshot_temp) != digest or snapshot_temp.stat().st_size != source.stat().st_size:
                    raise ValueError(f"Small input copy changed: {label}")
                input_records.append(
                    {
                        "label": label,
                        "source_path": str(source.resolve()),
                        "snapshot_path": str((phase_dir / snapshot_relative).resolve()),
                        "sha256": digest,
                        "size": source.stat().st_size,
                    }
                )

            for entry in snapshot_entries:
                relative = entry["path"]
                if not relative.startswith("harmony-project/"):
                    continue
                project_relative = PurePosixPath(relative).relative_to("harmony-project")
                source = safe_relative_path(phase3, relative, "accepted HarmonyOS project file")
                target = temp_dir / "harmony-project" / Path(*project_relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                if sha256_file(target) != entry["sha256"] or target.stat().st_size != entry["size"]:
                    raise ValueError(f"Accepted HarmonyOS project copy differs: {relative}")

            h4env_rows: list[dict[str, Any]] = []
            h4env_lock_records: list[dict[str, Any]] = []
            for config in sorted(environments, key=lambda item: item["h4env_id"]):
                relative = f"environments/{config['h4env_id']}/phase4-environment.json"
                path = temp_dir / relative
                path.parent.mkdir(parents=True)
                atomic_json(path, config)
                digest = sha256_file(path)
                h4env_rows.append(
                    {
                        "h4env_id": config["h4env_id"],
                        "source_android_env_id": config["source_android_env_id"],
                        "base_henv_id": config["base_henv_id"],
                        "device_id": config["device_id"],
                        "environment_sha256": digest,
                        "frozen_by": lead,
                        "frozen_at": config["frozen_at"],
                        "required": "true",
                        "status": "FROZEN",
                    }
                )
                h4env_lock_records.append(
                    {
                        "h4env_id": config["h4env_id"],
                        "source_android_env_id": config["source_android_env_id"],
                        "base_henv_id": config["base_henv_id"],
                        "device_id": config["device_id"],
                        "relative_path": relative,
                        "sha256": digest,
                    }
                )
            write_csv(
                temp_dir / "environments" / "h4env-registry.csv",
                csv_fieldnames(ASSETS / "h4env-registry.template.csv"),
                h4env_rows,
            )

            # v4 功能工单分派表（per-feature）：feature-dispatch.json 承载语义
            # 分派（verify_mode / BC / 数据读写集 / surfaces / 工单占位），
            # implementation-ledger.csv 承载治理账本（列沿用冻结模板）。
            feature_dispatch = {
                "schema_version": 1,
                "created_at": initialized_at,
                "created_by": lead,
                "work_order_id": work_order_id,
                "dispatch": [
                    {
                        "feature_id": item["feature_id"],
                        "verify_mode": item["verify_mode"],
                        "risk_level": item["risk_level"],
                        "work_order_id": "",
                        "owner_id": "",
                        "bc_ids": item["bc_ids"],
                        "runtime_bc_ids": item["runtime_bc_ids"],
                        "data_reads": item["data_reads"],
                        "data_writes": item["data_writes"],
                        "data_relation_ids": item["data_relation_ids"],
                        "surfaces": item["surfaces"],
                        "harmony_steps": [],
                        "status": "NOT_STARTED",
                    }
                    for item in feature_manifest
                ],
                "shared_data_relation_ids": shared_data_relation_ids,
            }
            atomic_json(temp_dir / "feature-dispatch.json", feature_dispatch)

            implementation_rows: list[dict[str, Any]] = []
            for item in feature_manifest:
                implementation_rows.append(
                    {
                        "feature_id": item["feature_id"],
                        "work_order_id": "",
                        "feature_owner_id": "",
                        "ui_agent_id": "",
                        "business_data_agent_id": "",
                        "native_capability_agent_id": "",
                        "asset_agent_id": ownership["visual_asset_agent_id"],
                        # v4：inventory/architecture-map 页面链退役，语义引用
                        # （BC/数据/surfaces）由 feature-dispatch.json 承载。
                        "source_inventory_ids": "",
                        "harmony_module_ids": "",
                        "status": "NOT_STARTED",
                        "updated_by": lead,
                        "updated_at": initialized_at,
                        "notes": (
                            f"verify_mode={item['verify_mode']};"
                            f"bc={len(item['bc_ids'])};"
                            f"runtime_bc={len(item['runtime_bc_ids'])}"
                        ),
                    }
                )
            write_csv(
                temp_dir / "implementation-ledger.csv",
                csv_fieldnames(ASSETS / "implementation-ledger.template.csv"),
                implementation_rows,
            )

            # surface-contracts.csv 薄表空骨架（H 的格式）：per-feature 一行，
            # feature_id 预填、surfaces 预填 feature-map 绑定（JSON 数组），
            # 实施结论三列（entry_reachable/nav_pattern/native_impl_check）
            # 与 notes 由 replayer / Gate 4 消费方回填。
            surface_contract_rows: list[dict[str, Any]] = []
            for item in feature_manifest:
                surface_ids = sorted(
                    {
                        str(surface.get("id", ""))
                        for surface in (item.get("surfaces") or [])
                        if isinstance(surface, dict) and surface.get("id")
                    }
                )
                surface_contract_rows.append(
                    {
                        "feature_id": item["feature_id"],
                        "surfaces": json.dumps(surface_ids, ensure_ascii=False, separators=(",", ":")),
                        "entry_reachable": "",
                        "nav_pattern": "",
                        "native_impl_check": "",
                        "notes": "",
                    }
                )
            write_csv(temp_dir / "surface-contracts.csv", list(SURFACE_CONTRACT_FIELDS), surface_contract_rows)

            write_csv(
                temp_dir / "feature-work-order-registry.csv",
                csv_fieldnames(ASSETS / "feature-work-order-registry.template.csv"),
                [],
            )
            for template, target in (
                ("evidence-index.template.csv", "evidence-index.csv"),
                ("rework-tickets.template.csv", "rework-tickets.csv"),
                ("acceptance-ledger.template.csv", "acceptance-ledger.csv"),
            ):
                copy_template_csv(temp_dir / target, template)

            make_tree_read_only(temp_dir / "inputs")
            make_tree_read_only(temp_dir / "environments")

            input_lock = {
                "schema_version": "2.0",
                "stage": 4,
                "run_id": scope.get("run_id"),
                "created_at": initialized_at,
                "locked_by": lead,
                "work_order_id": work_order_id,
                "work_order_sha256": work_order_sha,
                "ownership": ownership,
                "controller_gate3_snapshot_sha256": work_order["controller_gate3_sha256"],
                "phase3_work_order_id": phase3_work_order["work_order_id"],
                "phase3_work_order_sha256": sha256_file(phase3_work_order_path),
                "inputs": input_records,
                "h4envs": h4env_lock_records,
                "required_h4env_ids": sorted(h4env_ids),
                "phase3_source_snapshot_sha256": phase3_snapshot["snapshot_sha256"],
                # v4 功能范式冻结件
                "feature_manifest": feature_manifest,
                "shared_data_relation_ids": shared_data_relation_ids,
                "feature_dispatch": {
                    "relative_path": "feature-dispatch.json",
                    "sha256": sha256_file(temp_dir / "feature-dispatch.json"),
                },
                "surface_contracts": {
                    "relative_path": "surface-contracts.csv",
                    "sha256": sha256_file(temp_dir / "surface-contracts.csv"),
                    "fields": list(SURFACE_CONTRACT_FIELDS),
                },
                "implementation_ledger": {
                    "relative_path": "implementation-ledger.csv",
                    "sha256": sha256_file(temp_dir / "implementation-ledger.csv"),
                },
            }
            atomic_json(temp_dir / "stage-04-input-lock.json", input_lock)
            initial_snapshot = build_project_snapshot(temp_dir / "harmony-project")
            atomic_json(temp_dir / "initial-project-snapshot.json", initial_snapshot)
            atomic_json(
                temp_dir / "phase-manifest.json",
                {
                    "schema_version": "2.0",
                    "run_id": scope.get("run_id"),
                    "project_id": scope.get("project_id"),
                    "phase": 4,
                    "status": "IN_PROGRESS",
                    "initialized_at": initialized_at,
                    "work_order_id": work_order_id,
                    "work_order_sha256": work_order_sha,
                    "work_order_relative_path": registry_row["relative_path"],
                    "ownership": ownership,
                    "roles": {
                        "implementation_lead": ownership["implementation_lead_id"],
                        "asset_agent": ownership["visual_asset_agent_id"],
                        "verification_executor": ownership["verification_executor_id"],
                        "parity_checker": ownership["parity_acceptance_agent_id"],
                    },
                    "input_lock_sha256": sha256_file(temp_dir / "stage-04-input-lock.json"),
                    "initial_project_snapshot_sha256": initial_snapshot["snapshot_sha256"],
                    "feature_dispatch_sha256": sha256_file(temp_dir / "feature-dispatch.json"),
                    "surface_contracts_sha256": sha256_file(temp_dir / "surface-contracts.csv"),
                    "formal_evidence_device_type": "emulator",
                    "mp4_allowed": False,
                },
            )
            for frozen_record in (
                temp_dir / "stage-04-input-lock.json",
                temp_dir / "phase-manifest.json",
                temp_dir / "initial-project-snapshot.json",
                temp_dir / "feature-dispatch.json",
                temp_dir / "surface-contracts.csv",
                temp_dir / "implementation-ledger.csv",
            ):
                frozen_record.chmod(0o444)
            temp_dir.rename(phase_dir)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    runtime_features = sum(1 for item in feature_manifest if item["verify_mode"] == "RUNTIME")
    print(
        json.dumps(
            {
                "workspace": str(phase_dir),
                "work_order_id": work_order_id,
                "h4env_ids": sorted(h4env_ids),
                "features": len(feature_manifest),
                "runtime_features": runtime_features,
                "source_confirm_features": len(feature_manifest) - runtime_features,
                "surface_contract_rows": len(surface_contract_rows),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
