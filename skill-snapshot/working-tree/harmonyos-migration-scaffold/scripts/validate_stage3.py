#!/usr/bin/env python3
"""Validate the Phase 3 scaffold and issue the Gate 3 report (v3 paradigm only).

新四条规则：功能承载面覆盖 / 数据契约无孤儿 / 冒烟链保留 / HENV 环境链保留；
输入锁哈希与 CLOSED/闭包快照机制保留（内容 v3 化）。
"""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Any, NoReturn

from _common import (
    atomic_json,
    atomic_text,
    build_snapshot_manifest,
    load_json,
    manifest_text,
    read_csv,
    safe_relative_path,
    sha256_file,
    utc_now,
    validate_id,
    SNAPSHOT_EXCLUDED_PARTS,
)


SECRET_FILE_SUFFIXES = {".p12", ".pfx", ".jks", ".key", ".pem"}
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(password|passwd|passphrase|token|secret|private[_-]?key|storepass|keypass)\s*[:=]\s*['\"][^'\"]+['\"]"
)
CATEGORY_ORDER = (
    "TOOLCHAIN", "DEVICE", "BUNDLE_CHECK", "SIGNING_CHECK", "CLEAN_BUILD",
    "INSTALL", "LAUNCH", "ROUTE_SMOKE", "SCREENSHOT_CAPTURE",
)
CATEGORY_RANK = {category: index for index, category in enumerate(CATEGORY_ORDER)}
DEVICE_CATEGORIES = {
    "DEVICE", "BUNDLE_CHECK", "INSTALL", "LAUNCH", "ROUTE_SMOKE", "SCREENSHOT_CAPTURE",
}
PER_DEVICE_CATEGORIES = {"DEVICE", "BUNDLE_CHECK", "INSTALL", "LAUNCH", "ROUTE_SMOKE"}
SINGLETON_CATEGORIES = {"TOOLCHAIN", "SIGNING_CHECK", "CLEAN_BUILD"}
CLOSURE_EXCLUDED = {
    "stage-03-gate-report.json", "stage-03-closure-manifest.sha256", "CLOSED",
}


def validate_hap(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if not names or archive.testzip() is not None:
                raise ValueError(f"HAP ZIP payload is empty or corrupt: {path}")
            for name in names:
                candidate = Path(name)
                if candidate.is_absolute() or ".." in candidate.parts:
                    raise ValueError(f"HAP contains an unsafe member path: {name}")
            if not any(Path(name).name in {"module.json", "config.json"} for name in names):
                raise ValueError(f"HAP lacks module.json or config.json: {path}")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Build artifact is not a valid HAP ZIP: {path}: {exc}") from exc


def check_locked_path_records(value: Any, label: str, errors: list[str]) -> None:
    """Recursively verify every input-lock object that binds path + sha256."""
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            raw_path = value.get("path")
            expected = value.get("sha256")
            if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
                errors.append(f"Frozen {label}.path is not an absolute canonical path")
            else:
                path = Path(raw_path)
                try:
                    resolved = path.resolve(strict=True)
                    if str(resolved) != raw_path:
                        errors.append(f"Frozen {label}.path is not canonical: {raw_path}")
                    if not resolved.is_file():
                        errors.append(f"Frozen {label}.path is not a file: {raw_path}")
                    elif sha256_file(resolved) != expected:
                        errors.append(f"Frozen {label} has changed")
                except OSError as exc:
                    errors.append(f"Frozen {label} no longer exists: {raw_path}: {exc}")
            for extra_field in ("snapshot_path", "source_path"):
                if extra_field not in value:
                    continue
                extra_raw = value.get(extra_field)
                if not isinstance(extra_raw, str) or not Path(extra_raw).is_absolute():
                    errors.append(f"Frozen {label}.{extra_field} is not an absolute canonical path")
                    continue
                try:
                    extra = Path(extra_raw).resolve(strict=True)
                    if str(extra) != extra_raw or not extra.is_file():
                        errors.append(f"Frozen {label}.{extra_field} is not a canonical file")
                    elif sha256_file(extra) != expected:
                        errors.append(f"Frozen {label}.{extra_field} differs from its locked hash")
                except OSError as exc:
                    errors.append(f"Frozen {label}.{extra_field} no longer exists: {exc}")
        for key, item in value.items():
            check_locked_path_records(item, f"{label}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            check_locked_path_records(item, f"{label}[{index}]", errors)


def command_output_verdict(
    stdout: str, stderr: str, success_patterns: list[str], error_patterns: list[str]
) -> tuple[list[str], list[str]]:
    combined = stdout + "\n" + stderr
    combined_lower = combined.lower()
    return (
        [pattern for pattern in success_patterns if pattern in combined],
        [pattern for pattern in error_patterns if pattern.lower() in combined_lower],
    )


def verify_tree_read_only(root: Path, errors: list[str]) -> None:
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            errors.append(f"Symbolic link is prohibited in sealed HVER: {path}")
        elif path.exists() and path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            errors.append(f"Sealed HVER path is writable: {path}")


def _excluded_generated(path: Path, workspace: Path) -> bool:
    """与源快照排除集一致：包管理器/构建生成目录不进入关闭包。"""
    try:
        relative = path.relative_to(workspace)
    except ValueError:
        return False
    return any(part in SNAPSHOT_EXCLUDED_PARTS for part in relative.parts)


def closure_manifest(workspace: Path) -> str:
    relative_names: list[str] = []
    for path in sorted(workspace.rglob("*")):
        if _excluded_generated(path, workspace):
            continue
        if path.is_symlink():
            raise ValueError(f"Symbolic link is prohibited at Phase 3 closure: {path}")
        if path.is_file():
            relative = path.relative_to(workspace).as_posix()
            if relative in CLOSURE_EXCLUDED:
                continue
            relative_names.append(relative)
    return manifest_text(workspace, relative_names)


def seal_workspace(workspace: Path) -> None:
    for path in sorted(workspace.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if _excluded_generated(path, workspace):
            continue
        if path.is_symlink():
            raise ValueError(f"Symbolic link is prohibited at Phase 3 closure: {path}")
        if path.is_file():
            path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        elif path.is_dir():
            path.chmod(
                stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP
                | stat.S_IROTH | stat.S_IXOTH
            )
    workspace.chmod(
        stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
    )


def text_file(path: Path, label: str, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"Cannot read {label} as UTF-8 text: {path}: {exc}")
        return ""


def verify_sealed_manifest(directory: Path, errors: list[str]) -> None:
    manifest = directory / "manifest.sha256"
    if not manifest.is_file() or not (directory / "COMMITTED").is_file():
        errors.append(f"Verification package is not committed: {directory}")
        return
    expected_paths: set[str] = set()
    for number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if "  " not in line:
            errors.append(f"Malformed verification manifest line {number}: {line}")
            continue
        expected, relative = line.split("  ", 1)
        if "\\" in relative:
            errors.append(f"Non-portable verification manifest entry: {relative}")
            continue
        if relative in expected_paths:
            errors.append(f"Duplicate verification manifest entry: {relative}")
            continue
        expected_paths.add(relative)
        try:
            path = safe_relative_path(directory, relative, "verification manifest artifact")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"Verification manifest path is not a file: {path}")
        elif sha256_file(path) != expected:
            errors.append(f"Verification artifact hash mismatch: {path}")
    actual_paths = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
        and path.relative_to(directory).as_posix() not in {"manifest.sha256", "COMMITTED"}
    }
    if expected_paths != actual_paths:
        errors.append(
            f"Verification manifest file set differs; missing={sorted(expected_paths - actual_paths)}, "
            f"extra={sorted(actual_paths - expected_paths)}"
        )


# =========================================================================
# Gate 3 v3（Phase 3 范式改造，用户批准的新规则集）
#
# 删除的检查：页面清单覆盖（inventory.csv 页面行）、旧契约四方一致性
# （closure-report/CLOSED/acceptance-registry/evidence-anchor 交叉）、
# evidence-index 对覆盖、audit-replay 差异阻断。
# 新增四条：
#   1) 功能承载面覆盖：feature-map 每个 verify_mode=RUNTIME 的 feature，
#      其 surfaces[] 中至少一个非 container 的 UI surface 有 ArkUI 载体
#      （input-lock v3 surfaces[].route_or_mount ∈ {route, modal@HOST}）；
#   2) 数据契约无孤儿：data-relations.csv 每个语义数据对象（feature_id 与
#      data_object 均非空）在 data-contracts 有 interface 声明；反向亦然；
#   3) 冒烟保留：构建/安装/启动冒烟机制原样保留（run_verification 消费链不动）；
#   4) 环境链保留：HENV 冻结完整性校验保留（现有逻辑）。
# 另保留：输入锁哈希校验（对象换成 v3 inputs 集）、CLOSED/闭包快照机制
# （报告内容 v3 化）。
#
# input-lock v3 schema 与改造 D（init_scaffold v3）约定，本侧做防御性解析：
# 键缺失/畸形给清晰 error；接口分歧由 Leader #48 验收统一。
# =========================================================================

V3_PARADIGM = "v3"
# #48 裁定：与 D（init_scaffold v3）的 input-lock schema_version 字面值对齐。
V3_INPUT_LOCK_SCHEMA_VERSION = "scaffold-v3"
V3_REQUIRED_INPUTS = (
    "feature_map", "navigation_relations", "data_relations",
    "scope", "phase2_gate", "phase2_closure",
)
V3_CARRIER_KINDS = {"route", "modal"}
V3_MODAL_MOUNT_RE = re.compile(r"^modal@(.+)$")
# 修复批次（任务 #89 修 3）：批次 3 生成的 UI 蓝图三字段进入 Gate 3 校验。
# 用户否决"蓝图建议不需要消费"的评估——blueprint 缺失说明 P3 没做 UI
# 决策；所有用户可见 surface（route 或 modal 承载）必须冻结这三项。
V3_BLUEPRINT_REQUIRED_FIELDS = ("preserve", "native_component", "native_carrier")
# 冒烟保留（规则 3）的必需命令类别：构建 = TOOLCHAIN/CLEAN_BUILD/BUNDLE_CHECK/
# SIGNING_CHECK，安装 = INSTALL，启动 = LAUNCH。ROUTE_SMOKE/SCREENSHOT_CAPTURE 在
# v3 为可选记录（页面/截图范式证据已删除），出现时仍接受 command 级机制校验。
V3_SMOKE_CATEGORIES = (
    "TOOLCHAIN", "CLEAN_BUILD", "BUNDLE_CHECK", "SIGNING_CHECK", "INSTALL", "LAUNCH",
)
V3_PASS_ATTESTATIONS = (
    "real_file_review", "contract_only", "dependency_review", "runtime_smoke",
)


def _cli_error(message: str) -> NoReturn:
    """argparse parser.error 的行为等价（stderr + 退出码 2），供拆分后的主函数使用。"""
    print(f"validate_stage3: error: {message}", file=sys.stderr)
    raise SystemExit(2)


def validate_v3_input_lock(input_lock: Any, errors: list[str]) -> dict[str, Any]:
    """结构化校验 input-lock v3，返回规范化视图（畸形键降级为空值，不抛异常）。"""
    if not isinstance(input_lock, dict):
        errors.append("stage-03-input-lock.json is not a JSON object")
        return {"inputs": {}, "surfaces": [], "data_contracts": []}
    if input_lock.get("schema_version") != V3_INPUT_LOCK_SCHEMA_VERSION:
        errors.append(
            "v3 paradigm requires input-lock schema_version "
            f"{V3_INPUT_LOCK_SCHEMA_VERSION!r}; got {input_lock.get('schema_version')!r}"
        )
    inputs = input_lock.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("v3 input lock lacks the inputs object")
        inputs = {}
    for key in V3_REQUIRED_INPUTS:
        record = inputs.get(key)
        if not isinstance(record, dict) or "path" not in record or "sha256" not in record:
            errors.append(f"v3 input lock inputs.{key} must be a record with path and sha256")
    surfaces = input_lock.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        errors.append("v3 input lock lacks a non-empty surfaces array")
        surfaces = []
    data_contracts = input_lock.get("data_contracts")
    if not isinstance(data_contracts, (list, dict)):
        errors.append("v3 input lock lacks the data_contracts array (or file record)")
        data_contracts = []
    return {"inputs": inputs, "surfaces": surfaces, "data_contracts": data_contracts}


def _v3_load_inputs_document(
    inputs: Any, key: str, errors: list[str], as_csv: bool
) -> Any:
    """按 inputs.<key> 冻结记录加载文档（JSON 或 CSV），失败给清晰 error 并降级。"""
    empty = [] if as_csv else {}
    record = inputs.get(key) if isinstance(inputs, dict) else None
    if not isinstance(record, dict):
        return empty
    path_value = record.get("path")
    if not isinstance(path_value, str) or not path_value:
        errors.append(f"v3 inputs.{key}.path is missing or invalid")
        return empty
    try:
        if as_csv:
            return read_csv(Path(path_value))
        return load_json(Path(path_value))
    except (ValueError, OSError) as exc:
        errors.append(f"Cannot load frozen v3 inputs.{key}: {exc}")
        return empty


def _v3_closure_is_pass(closure: Any) -> bool:
    """Frozen Phase 2 closure PASS judgment, layout-compatible.

    Legacy adapter closures carry final_verdict/evidence_chain_closed.
    gmi-native closures (generator=gmi_closure) carry no adapter verdict
    keys; per the init_scaffold v3 gate their PASS proof is a clean gmi
    gate (unmapped==0 and audit_discrepancy==0).
    """
    if not isinstance(closure, dict):
        return False
    if closure.get("final_verdict") == "PASS" and closure.get("evidence_chain_closed") is True:
        return True
    if closure.get("generator") == "gmi_closure":
        gate = closure.get("gate") if isinstance(closure.get("gate"), dict) else {}
        return gate.get("unmapped") == 0 and gate.get("audit_discrepancy") == 0
    return False


def parse_v3_route_or_mount(value: Any, label: str, errors: list[str]) -> str:
    """归一化 route_or_mount：'route' | 'modal'（modal@HOST）| 'none'；非法返回 ''。"""
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}: route_or_mount is missing or empty")
        return ""
    normalized = value.strip()
    if normalized in {"route", "none"}:
        return normalized
    match = V3_MODAL_MOUNT_RE.fullmatch(normalized)
    if match and match.group(1).strip():
        return "modal"
    errors.append(
        f"{label}: route_or_mount must be 'route', 'modal@HOST', or 'none'; got {value!r}"
    )
    return ""


def index_v3_lock_surfaces(surfaces: list[Any], errors: list[str]) -> dict[str, str]:
    """把 input-lock v3 surfaces[] 归一化为 {surface_id: carrier_kind}。"""
    indexed: dict[str, str] = {}
    for position, surface in enumerate(surfaces):
        label = f"input_lock.surfaces[{position}]"
        if not isinstance(surface, dict):
            errors.append(f"{label} is not an object")
            continue
        surface_id = ""
        for key in ("surface_id", "id", "page_id"):
            candidate = surface.get(key)
            if isinstance(candidate, str) and candidate.strip():
                surface_id = candidate.strip()
                break
        if not surface_id:
            errors.append(f"{label} lacks a surface identifier (surface_id/id/page_id)")
            continue
        if surface_id in indexed:
            errors.append(f"Duplicate v3 surface declaration: {surface_id}")
            continue
        indexed[surface_id] = parse_v3_route_or_mount(surface.get("route_or_mount"), label, errors)
    return indexed


def _v3_surface_is_container(surface: dict[str, Any]) -> bool:
    """feature-map surface 的 container 判定：优先 is_container，回退 kind=='container'。"""
    flag = surface.get("is_container")
    if isinstance(flag, bool):
        return flag
    return str(surface.get("kind", "")).strip().lower() == "container"


def _v3_blueprint_field_missing(surface: dict[str, Any], field: str) -> bool:
    """blueprint 字段非空判定：preserve 为非空对象，其余为非空白字符串。"""
    value = surface.get(field)
    if field == "preserve":
        return not isinstance(value, dict) or not value
    return not isinstance(value, str) or not value.strip()


def check_v3_blueprint_fields(surface_plan: Any, errors: list[str]) -> dict[str, int]:
    """规则 1 扩展（#89 修 3）：用户可见 surface 的 UI 蓝图三字段强制。

    surface-plan.json 的 routes/modals 段即全部用户可见承载面（route /
    modal）；每项必须有非空的 preserve + native_component + native_carrier
    ——缺任一 → 规则 1 FAIL（错误注明缺哪个字段）。passthrough 段
    （container/组件）无 UI，不要求。旧产物（无这些字段）同样 FAIL 并
    提示重新生成 surface-plan——不提供豁免（用户意图是强制）。
    """
    if not isinstance(surface_plan, dict) or not surface_plan:
        errors.append(
            "surface-plan.json is missing or unreadable; user-visible surfaces "
            "require blueprint decisions "
            f"({'/'.join(V3_BLUEPRINT_REQUIRED_FIELDS)}) — "
            "regenerate the surface-plan"
        )
        return {"user_visible_surfaces": 0, "blueprint_complete_surfaces": 0}
    visible = 0
    complete = 0
    for section in ("routes", "modals"):
        carrier = "route" if section == "routes" else "modal"
        entries = surface_plan.get(section)
        if not isinstance(entries, list):
            errors.append(
                f"surface-plan.json {section} must be an array; "
                "regenerate the surface-plan"
            )
            continue
        for position, entry in enumerate(entries):
            label = f"surface_plan.{section}[{position}]"
            if not isinstance(entry, dict):
                errors.append(f"{label} is not an object; regenerate the surface-plan")
                continue
            surface_id = str(entry.get("surface_id", "")).strip() or label
            visible += 1
            missing = [
                field
                for field in V3_BLUEPRINT_REQUIRED_FIELDS
                if _v3_blueprint_field_missing(entry, field)
            ]
            if missing:
                errors.append(
                    f"{surface_id}: user-visible surface ({carrier} carrier) "
                    f"lacks a non-empty blueprint field: {', '.join(missing)}; "
                    "blueprint absence means P3 made no UI decision — "
                    "regenerate the surface-plan"
                )
            else:
                complete += 1
    return {
        "user_visible_surfaces": visible,
        "blueprint_complete_surfaces": complete,
    }


def validate_v3_surface_carriers(
    feature_map: Any,
    surfaces_by_id: dict[str, str],
    surface_plan: Any,
    errors: list[str],
    warnings: list[str],
) -> dict[str, int]:
    """规则 1：功能承载面覆盖（含 #89 修 3 的 blueprint 三字段强制）。

    feature-map 每个 verify_mode=RUNTIME 的 feature，其 surfaces[] 中至少一个
    非 container 的 UI surface 有 ArkUI 载体（路由节点 route 或模态挂载 modal@HOST，
    从 input-lock v3 的 surfaces[].route_or_mount 判定）。

    扩展（#89 修 3，塞进本规则不新增规则条数）：surface-plan 的全部用户
    可见 surface（routes/modals 段）必须有非空的 preserve +
    native_component + native_carrier（check_v3_blueprint_fields）；
    passthrough 段无 UI 不要求。
    """
    features = feature_map.get("features") if isinstance(feature_map, dict) else None
    if not isinstance(features, list):
        errors.append("feature-map.json lacks a features array")
        features = []
    counts = {
        "features_total": 0,
        "runtime_features": 0,
        "runtime_features_carried": 0,
        "lock_surfaces_with_carrier": sum(
            1 for carrier in surfaces_by_id.values() if carrier in V3_CARRIER_KINDS
        ),
        **check_v3_blueprint_fields(surface_plan, errors),
    }
    for feature in features:
        if not isinstance(feature, dict):
            errors.append("feature-map features contains a non-object entry")
            continue
        counts["features_total"] += 1
        if str(feature.get("verify_mode", "")).strip().upper() != "RUNTIME":
            continue
        counts["runtime_features"] += 1
        feature_id = str(feature.get("feature_id") or "<unknown>")
        raw_surfaces = feature.get("surfaces")
        if not isinstance(raw_surfaces, list) or not raw_surfaces:
            errors.append(f"{feature_id}: RUNTIME feature declares no surfaces")
            continue
        ui_surfaces: list[str] = []
        for surface in raw_surfaces:
            if not isinstance(surface, dict):
                errors.append(f"{feature_id}: surfaces contains a non-object entry")
                continue
            if _v3_surface_is_container(surface):
                continue
            surface_id = ""
            for key in ("id", "surface_id", "page_id"):
                candidate = surface.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    surface_id = candidate.strip()
                    break
            if not surface_id:
                errors.append(f"{feature_id}: non-container surface lacks an identifier")
                continue
            ui_surfaces.append(surface_id)
            if surface_id not in surfaces_by_id:
                # 接口分歧留给 Leader #48 统一；此处降为 warning 不阻断四条主规则。
                warnings.append(
                    f"{feature_id}: surface {surface_id} is not declared in the v3 input lock"
                )
        if not ui_surfaces:
            errors.append(
                f"{feature_id}: RUNTIME feature has no non-container UI surface to carry it"
            )
            continue
        carried = [
            surface_id for surface_id in ui_surfaces
            if surfaces_by_id.get(surface_id) in V3_CARRIER_KINDS
        ]
        if not carried:
            errors.append(
                f"{feature_id}: no non-container UI surface has an ArkUI carrier "
                f"(route or modal mount); surfaces={ui_surfaces}"
            )
            continue
        counts["runtime_features_carried"] += 1
    return counts


def semantic_data_objects(rows: list[dict[str, str]]) -> set[tuple[str, str]]:
    """data-relations 的语义数据对象：feature_id 与 data_object 均非空的行（去重）。

    空 feature_id/空 data_object 的行（如 <Insert>/<Update> 泛化位置）不是语义对象。
    """
    return {
        (row.get("feature_id", "").strip(), row.get("data_object", "").strip())
        for row in rows
        if row.get("feature_id", "").strip() and row.get("data_object", "").strip()
    }


def _v3_contract_key(
    row: dict[str, Any], label: str, errors: list[str]
) -> tuple[str, str] | None:
    """提取 data-contract 行的语义键（feature_id+data_object，防御字段回退）。"""
    feature_id = ""
    for key in ("feature_id", "feature"):
        candidate = row.get(key)
        if isinstance(candidate, str) and candidate.strip():
            feature_id = candidate.strip()
            break
    data_object = ""
    for key in ("data_object", "object"):
        candidate = row.get(key)
        if isinstance(candidate, str) and candidate.strip():
            data_object = candidate.strip()
            break
    if not feature_id or not data_object:
        errors.append(f"{label}: data contract lacks feature_id/data_object identity")
        return None
    return feature_id, data_object


def _v3_contract_interface(row: dict[str, Any], label: str, errors: list[str]) -> str:
    """提取 data-contract 的 interface 声明（防御字段回退，空声明报 error）。"""
    for key in ("interface", "interface_symbol", "contract_symbol"):
        candidate = row.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    errors.append(f"{label}: data contract lacks a non-empty interface declaration")
    return ""


def load_v3_data_contracts(input_lock: Any, errors: list[str]) -> list[dict[str, Any]]:
    """防御性解析 data_contracts：内嵌数组，或 {path, sha256} 文件记录（CSV/JSON）。"""
    raw = input_lock.get("data_contracts") if isinstance(input_lock, dict) else None
    if isinstance(raw, list):
        contracts = [item for item in raw if isinstance(item, dict)]
        if len(contracts) != len(raw):
            errors.append("v3 data_contracts contains non-object entries")
        return contracts
    if isinstance(raw, dict) and "path" in raw:
        path_value = raw.get("path")
        if not isinstance(path_value, str) or not path_value:
            errors.append("v3 data_contracts.path is missing or invalid")
            return []
        try:
            path = Path(path_value)
            if path.suffix.lower() == ".csv":
                rows: Any = read_csv(path)
            else:
                document = load_json(path)
                rows = (
                    document.get("data_contracts", [])
                    if isinstance(document, dict) else document
                )
                if not isinstance(rows, list):
                    errors.append(f"v3 data-contracts document is not an array: {path}")
                    return []
            contracts = [row for row in rows if isinstance(row, dict)]
            if len(contracts) != len(rows):
                errors.append("v3 data-contracts document contains non-object rows")
            return contracts
        except (ValueError, OSError) as exc:
            errors.append(f"Cannot load v3 data-contracts: {exc}")
            return []
    errors.append(
        "v3 input lock data_contracts must be an embedded array or a {path, sha256} record"
    )
    return []


def validate_v3_data_contracts(
    semantic: set[tuple[str, str]],
    contracts: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, int]:
    """规则 2：数据契约无孤儿（正向覆盖 + 反向无孤儿，双向 fail-closed）。"""
    interface_by_key: dict[tuple[str, str], str] = {}
    for position, contract in enumerate(contracts):
        label = f"data_contracts[{position}]"
        key = _v3_contract_key(contract, label, errors)
        if key is None:
            continue
        _v3_contract_interface(contract, label, errors)
        if key in interface_by_key:
            errors.append(
                f"Duplicate v3 data contract for feature={key[0]} data_object={key[1]}"
            )
            continue
        interface_by_key[key] = contract.get("interface", "") or ""
    uncovered = sorted(semantic - set(interface_by_key))
    if uncovered:
        errors.append(
            "Semantic data objects without an interface contract: "
            + ", ".join(f"{feature}/{obj}" for feature, obj in uncovered)
        )
    orphans = sorted(set(interface_by_key) - semantic)
    if orphans:
        errors.append(
            "Data contracts orphaned outside data-relations: "
            + ", ".join(f"{feature}/{obj}" for feature, obj in orphans)
        )
    return {
        "semantic_data_objects": len(semantic),
        "data_contracts": len(contracts),
        "declared_interface_keys": len(interface_by_key),
        "uncovered": len(uncovered),
        "orphans": len(orphans),
    }


def check_v3_smoke_category_coverage(
    command_counts: dict[str, int],
    command_devices: dict[str, set[str]],
    required_devices: set[str],
    errors: list[str],
) -> None:
    """规则 3 的类别覆盖判定：必需类别存在、singleton 恰一、设备全覆盖。"""
    for category in V3_SMOKE_CATEGORIES:
        if not command_counts.get(category):
            errors.append(f"HVER lacks command category: {category}")
    for category in sorted(SINGLETON_CATEGORIES & set(V3_SMOKE_CATEGORIES)):
        if command_counts.get(category) != 1:
            errors.append(f"HVER must contain exactly one {category} command")
    for category in sorted(PER_DEVICE_CATEGORIES & set(V3_SMOKE_CATEGORIES)):
        if command_devices.get(category, set()) != required_devices:
            errors.append(
                f"HVER {category} device coverage differs from required HENV devices"
            )


def validate_v3_environment_chain(
    workspace: Path,
    henv_id: str,
    verification_dir: Path,
    errors: list[str],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], set[str], Path]:
    """规则 4：HENV 冻结完整性校验保留（注册表 FROZEN/环境哈希/预检 PASS/必需设备）。"""
    try:
        henv_registry = read_csv(workspace / "environments" / "henv-registry.csv")
    except (ValueError, OSError) as exc:
        errors.append(f"Cannot read the HENV registry: {exc}")
        henv_registry = []
    environment_path = workspace / "environments" / henv_id / "harmony-environment.json"
    try:
        environment = load_json(environment_path)
    except (ValueError, OSError) as exc:
        errors.append(f"Cannot load the frozen HENV {henv_id}: {exc}")
        environment = {}
    henv_row = next((row for row in henv_registry if row.get("henv_id") == henv_id), None)
    if not henv_row or henv_row.get("status") != "FROZEN":
        errors.append(f"HENV is not frozen: {henv_id}")
    elif environment_path.is_file() and sha256_file(environment_path) != henv_row.get(
        "environment_sha256"
    ):
        errors.append(f"Frozen HENV has changed: {henv_id}")
    try:
        preflight = load_json(verification_dir / "deveco-preflight-report.json")
    except (ValueError, OSError) as exc:
        errors.append(f"Cannot load the DevEco preflight report: {exc}")
        preflight = {}
    if preflight.get("verdict") != "PASS" or preflight.get("henv_id") != henv_id:
        errors.append("DevEco/HarmonyOS environment preflight is not PASS for the selected HENV")
    if preflight.get("environment_sha256") != (
        sha256_file(environment_path) if environment_path.is_file() else None
    ):
        errors.append("Preflight environment hash differs from the selected HENV")
    device_by_id = {
        str(device.get("device_id")): device
        for device in environment.get("devices", [])
        if isinstance(device, dict) and device.get("device_id")
    }
    required_devices = {
        device_id for device_id, device in device_by_id.items()
        if device.get("required") is True
    }
    if not required_devices:
        errors.append("Selected HENV contains no required device for install/launch smoke")
    return environment, device_by_id, required_devices, environment_path


def validate_v3_smoke_chain(
    workspace: Path,
    verification_id: str,
    henv_id: str,
    verification_dir: Path,
    environment: dict[str, Any],
    device_by_id: dict[str, dict[str, Any]],
    required_devices: set[str],
    ownership: dict[str, Any],
    phase_manifest: dict[str, Any],
    input_lock_path: Path,
    environment_path: Path,
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """规则 3：构建/安装/启动冒烟机制原样保留（消费现有 run_verification 产物链）。"""
    try:
        verification = load_json(verification_dir / "metadata.json")
        snapshot = load_json(verification_dir / "scaffold-snapshot-manifest.json")
        artifact_manifest = load_json(verification_dir / "artifact-manifest.json")
        build_report = load_json(workspace / "build-report.json")
    except (ValueError, OSError) as exc:
        errors.append(f"Cannot load the sealed verification package: {exc}")
        verification, snapshot, artifact_manifest, build_report = {}, {}, {}, {}

    if verification.get("status") != "PASS":
        errors.append("Selected verification package is not PASS")
    if (
        verification.get("verification_id") != verification_id
        or verification.get("henv_id") != henv_id
    ):
        errors.append("Selected verification metadata identity does not match")
    if verification.get("input_lock_sha256") != (
        sha256_file(input_lock_path) if input_lock_path.is_file() else None
    ):
        errors.append("Verification package references a different Phase 3 input lock")
    if verification.get("environment_sha256") != (
        sha256_file(environment_path) if environment_path.is_file() else None
    ):
        errors.append("Verification package references a different HENV")
    if ownership.get("toolchain_agent_id") and verification.get("executed_by") != ownership.get(
        "toolchain_agent_id"
    ):
        errors.append("HVER executor differs from frozen toolchain_agent_id")
    if ownership.get("architecture_lead_id") and (
        environment.get("created_by") != ownership.get("architecture_lead_id")
        or environment.get("frozen_by") != ownership.get("architecture_lead_id")
    ):
        errors.append("HENV creator/freezer differs from frozen architecture_lead_id")
    for field in ("work_order_id", "work_order_sha256"):
        if verification.get(field) != phase_manifest.get(field):
            errors.append(f"HVER work-order identity differs on {field}")
    if build_report.get("status") != "PASS" or build_report.get("verification_id") != verification_id:
        errors.append("build-report.json is not PASS for the selected HVER-ID")

    verify_sealed_manifest(verification_dir, errors)
    verify_tree_read_only(verification_dir, errors)
    try:
        current_snapshot = build_snapshot_manifest(workspace, henv_id)
        if current_snapshot.get("snapshot_sha256") != snapshot.get("snapshot_sha256"):
            errors.append("Current scaffold differs from the verified source snapshot")
        if verification.get("source_snapshot_sha256") != snapshot.get("snapshot_sha256"):
            errors.append("Verification metadata and snapshot manifest hashes differ")
    except (ValueError, OSError) as exc:
        errors.append(str(exc))

    bundle_name = str(environment.get("application", {}).get("bundle_name", ""))
    if not bundle_name:
        errors.append("Frozen HENV has no application.bundle_name")
    category_contracts = environment.get("toolchain", {}).get("category_contracts", {})
    if not isinstance(category_contracts, dict):
        errors.append("Frozen HENV category_contracts is invalid")
        category_contracts = {}
    missing_contracts = [
        category for category in V3_SMOKE_CATEGORIES if category not in category_contracts
    ]
    if missing_contracts:
        errors.append(
            f"Frozen HENV category_contracts lacks smoke categories: {missing_contracts}"
        )

    commands = verification.get("commands")
    if not isinstance(commands, list):
        errors.append("Verification metadata lacks a commands array")
        commands = []
    command_by_id: dict[str, dict[str, Any]] = {}
    command_counts = {category: 0 for category in CATEGORY_ORDER}
    command_devices = {category: set() for category in PER_DEVICE_CATEGORIES}
    last_rank = -1
    project = workspace / "harmony-project"
    project_resolved = project.resolve() if project.exists() else project
    for command in commands:
        if not isinstance(command, dict):
            errors.append("Verification metadata contains a non-object command record")
            continue
        command_id = str(command.get("command_id", ""))
        try:
            validate_id(command_id, "Command-ID")
        except ValueError as exc:
            errors.append(str(exc))
        if command_id in command_by_id:
            errors.append(f"Duplicate command record in verification metadata: {command_id}")
        command_by_id[command_id] = command
        category = str(command.get("category", ""))
        if category not in CATEGORY_RANK:
            errors.append(f"{command_id}: unknown command category {category}")
            continue
        if CATEGORY_RANK[category] < last_rank:
            errors.append(f"{command_id}: command category order differs from the required pipeline")
        last_rank = CATEGORY_RANK[category]
        command_counts[category] += 1
        if (
            command.get("command_verdict") != "PASS"
            or command.get("exit_code") != 0
            or command.get("timed_out") is not False
        ):
            errors.append(f"{command_id}: command record is not an untimed PASS")
        argv = command.get("argv")
        if not isinstance(argv, list) or not argv or any(
            not isinstance(item, str) or not item for item in argv
        ):
            errors.append(f"{command_id}: command argv is invalid")
            argv = []
        contract = category_contracts.get(category, {})
        if not isinstance(contract, dict):
            errors.append(f"{command_id}: frozen category contract is invalid")
            contract = {}
        executable = str(contract.get("resolved_executable", ""))
        executable_hash = str(contract.get("executable_sha256", "")).lower()
        required_tokens = contract.get("required_argv_tokens", [])
        success_patterns = contract.get("success_output_contains", [])
        error_patterns = contract.get("error_output_contains", [])
        if any(
            not isinstance(items, list) or not items
            or any(not isinstance(item, str) or not item for item in items)
            for items in (required_tokens, success_patterns, error_patterns)
        ):
            errors.append(f"{command_id}: frozen category contract string arrays are invalid")
            required_tokens, success_patterns, error_patterns = [], [], []
        if category in category_contracts:
            if not Path(executable).is_absolute() or str(Path(executable).resolve()) != executable:
                errors.append(f"{command_id}: frozen executable path is not absolute/canonical")
            elif not Path(executable).is_file() or sha256_file(Path(executable)) != executable_hash:
                errors.append(f"{command_id}: frozen executable is missing or changed")
            if (
                not argv
                or argv[0] != executable
                or command.get("resolved_executable") != executable
                or command.get("executable_sha256") != executable_hash
            ):
                errors.append(f"{command_id}: command executable identity differs from frozen contract")
            if command.get("required_argv_tokens") != required_tokens or any(
                token not in argv for token in required_tokens
            ):
                errors.append(f"{command_id}: argv does not satisfy its frozen required tokens")
            if command.get("success_output_contains") != success_patterns or command.get(
                "error_output_contains"
            ) != error_patterns:
                errors.append(f"{command_id}: output patterns differ from frozen category contract")
        try:
            stdout_path = safe_relative_path(
                verification_dir, str(command.get("stdout_path", "")),
                f"stdout log for {command_id}",
            )
            stderr_path = safe_relative_path(
                verification_dir, str(command.get("stderr_path", "")),
                f"stderr log for {command_id}",
            )
            stdout = text_file(stdout_path, f"stdout log for {command_id}", errors)
            stderr = text_file(stderr_path, f"stderr log for {command_id}", errors)
            if sha256_file(stdout_path) != command.get("stdout_sha256"):
                errors.append(f"{command_id}: stdout log hash differs")
            if sha256_file(stderr_path) != command.get("stderr_sha256"):
                errors.append(f"{command_id}: stderr log hash differs")
            success_hits, error_hits = command_output_verdict(
                stdout, stderr, list(success_patterns), list(error_patterns)
            )
            if len(success_hits) != len(success_patterns) or error_hits:
                errors.append(
                    f"{command_id}: sealed logs do not prove success or contain an error marker"
                )
            if command.get("success_output_matches") != success_hits or command.get(
                "error_output_matches"
            ) != error_hits:
                errors.append(
                    f"{command_id}: stored output-pattern matches differ from sealed logs"
                )
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
        try:
            cwd = Path(str(command.get("cwd", ""))).resolve(strict=True)
            cwd.relative_to(project_resolved)
            if not cwd.is_dir():
                raise ValueError("not a directory")
        except (OSError, ValueError) as exc:
            errors.append(f"{command_id}: command cwd is not a real project directory: {exc}")
        device_id = str(command.get("device_id", ""))
        if category in DEVICE_CATEGORIES:
            if device_id not in (
                required_devices | {
                    device for device, device_row in device_by_id.items()
                    if device_row.get("screenshot_required") is True
                }
                if category == "SCREENSHOT_CAPTURE" else required_devices
            ):
                errors.append(f"{command_id}: command device is not allowed for {category}")
            serial = str(device_by_id.get(device_id, {}).get("serial", ""))
            if not serial or serial not in argv or command.get("device_serial") != serial:
                errors.append(f"{command_id}: command does not bind the frozen exact device serial")
            if category in PER_DEVICE_CATEGORIES:
                command_devices[category].add(device_id)
        elif device_id:
            errors.append(f"{command_id}: non-device category declares a device")
        if category in {"BUNDLE_CHECK", "SIGNING_CHECK", "LAUNCH"} and bundle_name not in argv:
            errors.append(f"{command_id}: {category} argv does not bind the frozen bundle name")

    declared_order = verification.get("category_order")
    if (
        not isinstance(declared_order, list)
        or not set(V3_SMOKE_CATEGORIES).issubset({str(item) for item in declared_order})
    ):
        errors.append("HVER category_order does not cover the required smoke pipeline")
    else:
        ranks = [CATEGORY_RANK.get(str(item), -1) for item in declared_order]
        if any(later < earlier for earlier, later in zip(ranks, ranks[1:])):
            errors.append("HVER category_order violates the required pipeline order")

    check_v3_smoke_category_coverage(command_counts, command_devices, required_devices, errors)
    for category in ("ROUTE_SMOKE", "SCREENSHOT_CAPTURE"):
        if not command_counts.get(category):
            warnings.append(
                f"v3 paradigm: {category} commands are optional records; none recorded"
            )

    artifacts = artifact_manifest.get("artifacts", [])
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("Selected verification contains no sealed HAP artifact")
        artifacts = []
    clean_build_ids = {
        command_id for command_id, command in command_by_id.items()
        if command.get("category") == "CLEAN_BUILD" and command.get("command_verdict") == "PASS"
    }
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            errors.append("Artifact manifest contains a non-object row")
            continue
        if artifact.get("produced_by_command_id") not in clean_build_ids:
            errors.append("Sealed HAP is not bound to the passing CLEAN_BUILD command")
        try:
            source = safe_relative_path(
                project, str(artifact.get("path", "")), "source HAP artifact"
            )
            sealed = safe_relative_path(
                verification_dir, str(artifact.get("sealed_path", "")), "sealed HAP artifact"
            )
            validate_hap(source)
            validate_hap(sealed)
            source_hash = sha256_file(source)
            sealed_hash = sha256_file(sealed)
            if (
                source_hash != artifact.get("sha256")
                or sealed_hash != artifact.get("sealed_sha256")
                or source_hash != sealed_hash
                or source.stat().st_size != artifact.get("size")
            ):
                errors.append(
                    f"HAP source/sealed copy identity differs: {artifact.get('path')}"
                )
        except (ValueError, OSError) as exc:
            errors.append(str(exc))

    return {
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
        "artifact_hashes": [
            item.get("sha256") for item in artifacts if isinstance(item, dict)
        ],
        "counts": {
            "smoke_commands": sum(command_counts[category] for category in V3_SMOKE_CATEGORIES),
            "route_smoke_commands": command_counts.get("ROUTE_SMOKE", 0),
            "screenshot_commands": command_counts.get("SCREENSHOT_CAPTURE", 0),
        },
    }


def validate_stage3_v3(args: argparse.Namespace) -> int:
    """Gate 3 v3 主函数：新四条规则 + 输入锁哈希 + CLOSED/闭包快照（内容 v3 化）。"""
    workspace = Path(args.workspace).expanduser().resolve()
    if (workspace / "CLOSED").exists():
        _cli_error("Phase 3 is CLOSED; gate-report writes are prohibited")
    errors: list[str] = []
    warnings: list[str] = []
    try:
        henv_id = validate_id(args.henv_id, "HENV-ID")
        verification_id = validate_id(args.verification_id, "HVER-ID")
    except ValueError as exc:
        _cli_error(str(exc))
    reviewer = args.reviewer.strip()
    if not reviewer:
        _cli_error("--reviewer is required")

    # ---- 输入锁 v3：结构 + 哈希（保留项；对象换成 v3 inputs 集） ----
    input_lock_path = workspace / "stage-03-input-lock.json"
    try:
        input_lock = load_json(input_lock_path)
    except (ValueError, OSError) as exc:
        errors.append(f"Cannot load stage-03-input-lock.json: {exc}")
        input_lock = {}
    lock_view = validate_v3_input_lock(input_lock, errors)
    check_locked_path_records(input_lock, "input_lock", errors)

    try:
        phase_manifest = load_json(workspace / "phase-manifest.json")
    except (ValueError, OSError) as exc:
        errors.append(f"Cannot load phase-manifest.json: {exc}")
        phase_manifest = {}
    if phase_manifest.get("phase") != 3:
        errors.append("Not an initialized Phase 3 workspace")
    ownership = phase_manifest.get("ownership")
    if not isinstance(ownership, dict):
        errors.append("phase-manifest.json lacks the frozen Phase 3 ownership")
        ownership = {}
    acceptance_id = str(ownership.get("architecture_acceptance_agent_id", ""))
    if not acceptance_id:
        errors.append("Frozen Phase 3 ownership lacks architecture_acceptance_agent_id")
    elif reviewer != acceptance_id:
        _cli_error("--reviewer must equal the frozen architecture_acceptance_agent_id")
    for field in ("work_order_id", "work_order_sha256"):
        if (
            input_lock.get(field) is not None
            and input_lock.get(field) != phase_manifest.get(field)
        ):
            errors.append(f"Phase 3 {field} differs between manifest and input lock")

    # ---- 输入语义（沿用既有判据）：Phase 2 闭包/门必须 PASS ----
    closure = _v3_load_inputs_document(
        lock_view["inputs"], "phase2_closure", errors, as_csv=False
    )
    if not _v3_closure_is_pass(closure):
        errors.append("Frozen Phase 2 closure is not PASS")
    phase2_gate = _v3_load_inputs_document(
        lock_view["inputs"], "phase2_gate", errors, as_csv=False
    )
    if phase2_gate.get("phase") != 2 or phase2_gate.get("verdict") != "PASS":
        errors.append("Frozen Phase 2 controller gate is not PASS")

    # ---- 规则 1：功能承载面覆盖 ----
    rule1_before = len(errors)
    feature_map = _v3_load_inputs_document(
        lock_view["inputs"], "feature_map", errors, as_csv=False
    )
    # #89 修 3：surface-plan 的 blueprint 三字段（preserve/native_component/
    # native_carrier）进入规则 1 校验；加载失败按缺失处理（无豁免）。
    surface_plan: Any = None
    try:
        surface_plan = load_json(workspace / "surface-plan.json")
    except (ValueError, OSError):
        surface_plan = None
    surfaces_by_id = index_v3_lock_surfaces(lock_view["surfaces"], errors)
    surface_counts = validate_v3_surface_carriers(
        feature_map, surfaces_by_id, surface_plan, errors, warnings
    )
    rule1_status = "PASS" if len(errors) == rule1_before else "FAIL"

    # ---- 规则 2：数据契约无孤儿 ----
    rule2_before = len(errors)
    data_relations = _v3_load_inputs_document(
        lock_view["inputs"], "data_relations", errors, as_csv=True
    )
    semantic = semantic_data_objects(data_relations)
    contracts = load_v3_data_contracts(input_lock, errors)
    contract_counts = validate_v3_data_contracts(semantic, contracts, errors)
    rule2_status = "PASS" if len(errors) == rule2_before else "FAIL"

    # ---- 规则 4：环境链保留 ----
    verification_dir = workspace / "verification" / verification_id
    rule4_before = len(errors)
    environment, device_by_id, required_devices, environment_path = (
        validate_v3_environment_chain(workspace, henv_id, verification_dir, errors)
    )
    rule4_status = "PASS" if len(errors) == rule4_before else "FAIL"

    # ---- 规则 3：冒烟链保留 ----
    rule3_before = len(errors)
    smoke = validate_v3_smoke_chain(
        workspace, verification_id, henv_id, verification_dir,
        environment, device_by_id, required_devices, ownership, phase_manifest,
        input_lock_path, environment_path, errors, warnings,
    )
    rule3_status = "PASS" if len(errors) == rule3_before else "FAIL"

    # ---- 安全护栏（既有逻辑保留：MP4 非正式证据、项目内禁止私钥/凭据） ----
    mp4_files = [
        path for path in workspace.rglob("*")
        if path.is_file() and path.suffix.lower() == ".mp4"
    ]
    if mp4_files:
        errors.append(
            f"MP4 is not accepted as formal Phase 3 evidence; found {len(mp4_files)} file(s)"
        )
    project = workspace / "harmony-project"
    for path in project.rglob("*") if project.is_dir() else []:
        if not path.is_file():
            continue
        if path.suffix.lower() in SECRET_FILE_SUFFIXES:
            errors.append(f"Signing/private-key file is prohibited inside the project: {path}")
            continue
        if path.stat().st_size <= 2 * 1024 * 1024:
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "-----BEGIN" in content.upper() and "PRIVATE KEY-----" in content.upper():
                errors.append(f"Private-key material is prohibited inside the project: {path}")
            if SECRET_ASSIGNMENT_RE.search(content):
                errors.append(f"Possible embedded credential is prohibited inside the project: {path}")

    # ---- v3 PASS 认证口径（截图/页面壳两项为 legacy 范式认证，v3 不强制） ----
    attestations = {
        "real_file_review": args.attest_real_file_review,
        "placeholder_boundaries": args.attest_placeholder_boundaries,
        "contract_only": args.attest_contract_only,
        "dependency_review": args.attest_dependency_review,
        "runtime_smoke": args.attest_runtime_smoke,
        "screenshot_review": args.attest_screenshot_review,
    }
    if args.decision == "PASS":
        missing_attestations = [
            name for name in V3_PASS_ATTESTATIONS if not attestations[name]
        ]
        if missing_attestations:
            errors.append(f"PASS requires acceptance attestations: {missing_attestations}")

    effective_decision = args.decision
    if args.decision == "PASS" and errors:
        effective_decision = "INCOMPLETE"
    gate_id = f"GATE3-{utc_now().replace('-', '').replace(':', '')}-{uuid.uuid4().hex[:6].upper()}"
    report = {
        "gate_id": gate_id,
        "phase": 3,
        "paradigm": V3_PARADIGM,
        "verdict": effective_decision,
        "reviewer_role": "architecture-acceptance-agent",
        "reviewer_id": reviewer,
        "reviewed_at": utc_now(),
        "run_id": phase_manifest.get("run_id"),
        "work_order_id": phase_manifest.get("work_order_id"),
        "work_order_sha256": phase_manifest.get("work_order_sha256"),
        "input_lock_sha256": (
            sha256_file(input_lock_path) if input_lock_path.is_file() else None
        ),
        "henv_id": henv_id,
        "verification_id": verification_id,
        "source_snapshot_sha256": smoke.get("snapshot_sha256"),
        "artifact_hashes": smoke.get("artifact_hashes", []),
        "counts": {
            "features_total": surface_counts["features_total"],
            "runtime_features": surface_counts["runtime_features"],
            "runtime_features_carried": surface_counts["runtime_features_carried"],
            "lock_surfaces": len(surfaces_by_id),
            "lock_surfaces_with_carrier": surface_counts["lock_surfaces_with_carrier"],
            "user_visible_surfaces": surface_counts["user_visible_surfaces"],
            "blueprint_complete_surfaces": surface_counts["blueprint_complete_surfaces"],
            "semantic_data_objects": contract_counts["semantic_data_objects"],
            "data_contracts": contract_counts["data_contracts"],
            "smoke_commands": smoke["counts"]["smoke_commands"],
            "route_smoke_commands": smoke["counts"]["route_smoke_commands"],
            "screenshot_commands": smoke["counts"]["screenshot_commands"],
            "required_devices": len(required_devices),
        },
        "rules": {
            "surface_carrier_coverage": {
                "status": rule1_status,
                "runtime_features": surface_counts["runtime_features"],
                "runtime_features_carried": surface_counts["runtime_features_carried"],
                "user_visible_surfaces": surface_counts["user_visible_surfaces"],
                "blueprint_complete_surfaces": surface_counts["blueprint_complete_surfaces"],
            },
            "data_contract_closure": {"status": rule2_status, **contract_counts},
            "smoke_chain": {
                "status": rule3_status,
                "required_categories": list(V3_SMOKE_CATEGORIES),
                "smoke_commands": smoke["counts"]["smoke_commands"],
            },
            "environment_chain": {"status": rule4_status, "henv_id": henv_id},
        },
        "attestations": attestations,
        "errors": errors,
        "warnings": warnings,
        "notes": args.notes,
    }
    gate_history = workspace / "gate-reports" / f"{gate_id}.json"
    atomic_json(gate_history, report)
    atomic_json(workspace / "stage-03-gate-report.json", report)
    if smoke.get("snapshot_sha256"):
        snapshot_path = verification_dir / "scaffold-snapshot-manifest.json"
        if snapshot_path.is_file():
            atomic_json(
                workspace / "scaffold-snapshot-manifest.json",
                load_json(snapshot_path),
            )
    if effective_decision == "PASS" and not errors:
        try:
            closure_value = closure_manifest(workspace)
            atomic_text(workspace / "stage-03-closure-manifest.sha256", closure_value)
            atomic_text(
                workspace / "CLOSED",
                sha256_file(workspace / "stage-03-gate-report.json") + "\n",
            )
            seal_workspace(workspace)
        except (OSError, ValueError) as exc:
            # 闭包失败绝不能报告为 PASS；可变报告刻意排除在闭包清单外以记录该失败。
            errors.append(f"Cannot seal Phase 3 workspace: {exc}")
            report["verdict"] = "INCOMPLETE"
            report["errors"] = errors
            try:
                atomic_json(workspace / "stage-03-gate-report.json", report)
            except OSError:
                pass
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if effective_decision == "PASS" and not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--henv-id", required=True)
    parser.add_argument("--verification-id", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--decision", required=True, choices=("PASS", "INCOMPLETE", "BLOCKED"))
    parser.add_argument("--attest-real-file-review", action="store_true")
    parser.add_argument("--attest-placeholder-boundaries", action="store_true")
    parser.add_argument("--attest-contract-only", action="store_true")
    parser.add_argument("--attest-dependency-review", action="store_true")
    parser.add_argument("--attest-runtime-smoke", action="store_true")
    parser.add_argument("--attest-screenshot-review", action="store_true")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    return validate_stage3_v3(args)


if __name__ == "__main__":
    raise SystemExit(main())
