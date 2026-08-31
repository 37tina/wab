#!/usr/bin/env python3
"""Validate Phase 1 through Phase 6 gates for a migration controller run."""

from __future__ import annotations

import argparse
import binascii
import csv
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


FEATURE_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "harmonyos-feature-implementation" / "scripts"
)
if str(FEATURE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FEATURE_SCRIPTS))
from uitest_snapshot import validate_uitest_evidence  # noqa: E402

CONTROLLER_SCRIPTS = Path(__file__).resolve().parent
if str(CONTROLLER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_SCRIPTS))
from _run_status import TOOL_GAP_REMEDY, transition_run_status  # noqa: E402



ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,79}$")
ACTOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,95}$")
PLACEHOLDER_RE = re.compile(r"^__.+__$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UNRESOLVED_WORDS = {"PENDING_CONFIRMATION", "UNKNOWN", "UNRESOLVED", "TBD", "TODO"}

STAGE3_CLOSURE_EXACT_EXCLUDES = {
    "stage-03-gate-report.json", "stage-03-closure-manifest.sha256", "CLOSED",
}
STAGE3_ROLE_KEYS = (
    "architecture_lead_id", "toolchain_agent_id", "navigation_agent_id",
    "public_ui_agent_id", "capability_contract_agent_id", "architecture_acceptance_agent_id",
)
STAGE3_SNAPSHOT_REGISTRIES = {
    "stage-03-input-lock.json", "module-registry.csv", "dependency-policy.json",
    "architecture-map.csv", "route-registry.csv", "surface-registry.csv",
    "public-ui-registry.csv", "capability-contracts.csv", "asset-registry.csv", "migration-status.csv",
    "architecture-decisions.csv", "phase-manifest.json",
}
STAGE3_SNAPSHOT_EXCLUDED_PARTS = {
    ".git", ".hg", ".svn", ".idea", ".hvigor", "oh_modules", "node_modules",
    "build", "out", "dist", "coverage", "__pycache__",
}
STAGE3_REWORK_ROUTES = {
    "ARCHITECTURE": ("architecture-lead", "architecture_lead_id"),
    "PLACEMENT": ("architecture-lead", "architecture_lead_id"),
    "DEPENDENCY": ("architecture-lead", "architecture_lead_id"),
    "INPUT": ("architecture-lead", "architecture_lead_id"),
    "TOOLCHAIN": ("toolchain-agent", "toolchain_agent_id"),
    "BUILD": ("toolchain-agent", "toolchain_agent_id"),
    "DEVICE": ("toolchain-agent", "toolchain_agent_id"),
    "BUNDLE": ("toolchain-agent", "toolchain_agent_id"),
    "SIGNING": ("toolchain-agent", "toolchain_agent_id"),
    "INSTALL": ("toolchain-agent", "toolchain_agent_id"),
    "LAUNCH": ("toolchain-agent", "toolchain_agent_id"),
    "ARTIFACT": ("toolchain-agent", "toolchain_agent_id"),
    "SCREENSHOT": ("toolchain-agent", "toolchain_agent_id"),
    "NAVIGATION": ("navigation-agent", "navigation_agent_id"),
    "ROUTE": ("navigation-agent", "navigation_agent_id"),
    "SURFACE": ("navigation-agent", "navigation_agent_id"),
    "MAPPING": ("navigation-agent", "navigation_agent_id"),
    "SMOKE": ("navigation-agent", "navigation_agent_id"),
    "PUBLIC_UI": ("public-ui-agent", "public_ui_agent_id"),
    "RESPONSIVE": ("public-ui-agent", "public_ui_agent_id"),
    "THEME": ("public-ui-agent", "public_ui_agent_id"),
    "CAPABILITY": ("capability-contract-agent", "capability_contract_agent_id"),
    "CONTRACT": ("capability-contract-agent", "capability_contract_agent_id"),
}
STAGE4_CLOSURE_EXACT_EXCLUDES = {
    "stage-04-gate-report.json", "stage-04-closure-manifest.sha256", "CLOSED",
}
STAGE4_ROLE_KEYS = (
    "implementation_lead_id", "visual_asset_agent_id",
    "verification_executor_id", "parity_acceptance_agent_id",
)
STAGE4_PROJECT_EXCLUDED_PARTS = {
    ".git", ".idea", ".hvigor", "build", "dist", "coverage", "node_modules",
    "oh_modules", "__pycache__", ".pytest_cache",
}
STAGE5_ROLE_KEYS = (
    "regression_lead_id", "candidate_build_agent_id", "journey_executor_id",
    "quality_agent_id", "system_acceptance_agent_id",
)
STAGE6_ROLE_KEYS = (
    "delivery_lead_id", "candidate_custody_agent_id", "candidate_validation_agent_id",
    "material_consistency_agent_id", "delivery_acceptance_agent_id",
)
STAGE5_CLOSURE_EXACT_EXCLUDES = {
    "stage-05-gate-report.json", "stage-05-closure-manifest.sha256", "CLOSED",
}
STAGE6_CLOSURE_EXACT_EXCLUDES = {
    "stage-06-gate-report.json", "stage-06-closure-manifest.sha256", "CLOSED",
}
PHASE56_TRANSIENT_PARTS = {".locks", ".staging", "__pycache__", ".pytest_cache"}
PHASE6_PROHIBITED_COMMAND_WORDS = {
    "build", "rebuild", "compile", "package", "sign", "resign", "upload", "send",
    "distribute", "publish", "release", "store", "market", "remote-sign", "remote_sign",
    "remotesign", "deploy", "submit",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unresolved(value: Any) -> bool:
    if value is None or value == "":
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return bool(PLACEHOLDER_RE.match(stripped)) or stripped.upper() in UNRESOLVED_WORDS
    if isinstance(value, list):
        return not value or any(unresolved(item) for item in value)
    if isinstance(value, dict):
        return any(unresolved(item) for item in value.values())
    return False


def need(mapping: dict[str, Any], key: str, label: str, errors: list[str]) -> Any:
    value = mapping.get(key)
    if unresolved(value):
        errors.append(f"Missing or unresolved {label}")
    return value


def run_checked(argv: list[str], label: str, errors: list[str]) -> str:
    try:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"{label} could not run: {exc}")
        return ""
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        errors.append(f"{label} failed: {detail[:500]}")
        return ""
    return completed.stdout.strip()


def validate_git_baseline(project_root: Path, revision: str, errors: list[str]) -> None:
    actual = run_checked(["git", "-C", str(project_root), "rev-parse", "HEAD"], "git revision check", errors)
    if actual and revision != actual:
        errors.append(f"android.source_revision must equal the exact Git HEAD: {actual}")
    dirty = run_checked(
        ["git", "-C", str(project_root), "status", "--porcelain", "--untracked-files=all"],
        "git worktree check",
        errors,
    )
    if dirty:
        errors.append("Android project has uncommitted or untracked files; freeze a clean source revision")


def validate_apk(apk_path: Path, declared_hash: str, errors: list[str]) -> str | None:
    if not apk_path.is_file():
        errors.append(f"Installable APK does not exist: {apk_path}")
        return None
    if not zipfile.is_zipfile(apk_path):
        errors.append(f"APK is not a valid ZIP/APK container: {apk_path}")
        return None
    try:
        with zipfile.ZipFile(apk_path) as archive:
            names = set(archive.namelist())
            bad_member = archive.testzip()
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"APK cannot be read: {exc}")
        return None
    if bad_member:
        errors.append(f"APK contains a corrupt member: {bad_member}")
    if "AndroidManifest.xml" not in names:
        errors.append("APK has no AndroidManifest.xml")
    if not any(name == "resources.arsc" or re.fullmatch(r"classes\d*\.dex", name) for name in names):
        errors.append("APK has neither resources.arsc nor a classes*.dex payload")
    actual_hash = sha256_file(apk_path)
    if not SHA256_RE.fullmatch(str(declared_hash)):
        errors.append("android.apk_sha256 must be a lowercase 64-character SHA-256")
    elif declared_hash != actual_hash:
        errors.append("android.apk_sha256 does not match the APK file")
    return actual_hash


def resolve_executable(value: str) -> str | None:
    candidate = Path(value).expanduser()
    if candidate.parent != Path(".") or candidate.is_absolute():
        return str(candidate.resolve()) if candidate.is_file() and os.access(candidate, os.X_OK) else None
    return shutil.which(value)


def validate_apk_identity(
    analyzer_value: str, apk_path: Path, android: dict[str, Any], errors: list[str]
) -> None:
    analyzer = resolve_executable(analyzer_value)
    if not analyzer:
        errors.append(f"APK analyzer is unavailable: {analyzer_value}")
        return
    checks = (
        ("application-id", str(android.get("application_id", ""))),
        ("version-name", str(android.get("app_version", ""))),
        ("version-code", str(android.get("app_build", ""))),
    )
    for command, expected in checks:
        command_prefix = [sys.executable, analyzer] if os.name == "nt" and analyzer.lower().endswith(".py") else [analyzer]
        actual = run_checked(
            [*command_prefix, "manifest", command, str(apk_path)],
            f"apkanalyzer manifest {command}",
            errors,
        )
        if actual and actual != expected:
            errors.append(f"APK {command} differs from controller scope: expected {expected!r}, got {actual!r}")


def validate_phase1(
    run_dir: Path, scope: dict[str, Any]
) -> tuple[list[str], list[str], str | None, dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    facts: dict[str, Any] = {}

    try:
        run_manifest = load_json(run_dir / "run-manifest.json")
    except ValueError as exc:
        errors.append(str(exc))
        run_manifest = {}
    if scope.get("run_id") != run_manifest.get("run_id"):
        errors.append("scope.run_id does not match run-manifest.json")
    if scope.get("project_id") != run_manifest.get("project_id"):
        errors.append("scope.project_id does not match run-manifest.json")

    android = scope.get("android") if isinstance(scope.get("android"), dict) else {}
    for key in (
        "project_root", "source_revision", "source_revision_kind", "apk_path", "apk_sha256",
        "application_id", "app_version", "app_build", "build_variant",
    ):
        need(android, key, f"android.{key}", errors)

    project_root = Path(str(android.get("project_root", ""))).expanduser().resolve()
    apk_path = Path(str(android.get("apk_path", ""))).expanduser().resolve()
    manifest_project = str(run_manifest.get("project_root", ""))
    if not unresolved(android.get("project_root")) and not project_root.is_dir():
        errors.append(f"Android project root does not exist: {project_root}")
    if manifest_project and str(project_root) != str(Path(manifest_project).expanduser().resolve()):
        errors.append("android.project_root does not match immutable run-manifest.json")
    settings_files = [project_root / "settings.gradle", project_root / "settings.gradle.kts"]
    gradle_files = list(project_root.rglob("build.gradle")) + list(project_root.rglob("build.gradle.kts")) if project_root.is_dir() else []
    source_manifests = list(project_root.rglob("src/main/AndroidManifest.xml")) if project_root.is_dir() else []
    if not any(path.is_file() for path in settings_files) or not gradle_files or not source_manifests:
        errors.append("Android project must contain settings.gradle(.kts), a build.gradle(.kts), and src/main/AndroidManifest.xml")
    elif not any("android" in path.read_text(encoding="utf-8", errors="replace").lower() for path in gradle_files):
        errors.append("No Android Gradle plugin declaration was found")
    if android.get("source_revision_kind") != "git-commit":
        errors.append("android.source_revision_kind must be git-commit")
    elif project_root.is_dir() and not unresolved(android.get("source_revision")):
        validate_git_baseline(project_root, str(android["source_revision"]), errors)
    if not unresolved(android.get("apk_path")):
        facts["apk_sha256"] = validate_apk(apk_path, str(android.get("apk_sha256", "")), errors)
    facts["source_revision"] = android.get("source_revision")

    target = scope.get("target") if isinstance(scope.get("target"), dict) else {}
    if need(target, "platform", "target.platform", errors) != "HarmonyOS NEXT":
        errors.append("target.platform must be HarmonyOS NEXT")
    need(target, "sdk_or_api_target", "target.sdk_or_api_target", errors)
    need(target, "device_classes", "target.device_classes", errors)

    migration_scope = scope.get("migration_scope") if isinstance(scope.get("migration_scope"), dict) else {}
    included = need(migration_scope, "included_features", "migration_scope.included_features", errors)
    excluded = migration_scope.get("excluded_features")
    if not isinstance(included, list) or any(not isinstance(item, str) or not ID_RE.fullmatch(item) for item in included):
        errors.append("migration_scope.included_features must contain valid Feature-IDs")
        included = []
    if len(set(included)) != len(included):
        errors.append("migration_scope.included_features contains duplicates")
    if "excluded_features" not in migration_scope:
        errors.append("migration_scope.excluded_features must be explicit, even when empty")
        excluded = []
    elif not isinstance(excluded, list) or any(not isinstance(item, str) or not ID_RE.fullmatch(item) for item in excluded):
        errors.append("migration_scope.excluded_features must contain valid Feature-IDs")
        excluded = []
    if set(included) & set(excluded):
        errors.append("A Feature-ID cannot be both included and excluded")
    need(migration_scope, "parity_dimensions", "migration_scope.parity_dimensions", errors)
    # 2.1 scope fields: validated only when explicitly present; historical strict runs
    # that omit them keep the legacy behavior and never fail here.
    if "key_business_capabilities" in migration_scope:
        capabilities = migration_scope.get("key_business_capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            errors.append("migration_scope.key_business_capabilities must be a non-empty list")
    if "data_scope" in migration_scope and not isinstance(migration_scope.get("data_scope"), dict):
        errors.append("migration_scope.data_scope must be an object")
    if "allowed_platform_substitutions" in migration_scope:
        substitutions = migration_scope.get("allowed_platform_substitutions")
        if not isinstance(substitutions, list):
            errors.append("migration_scope.allowed_platform_substitutions must be a list")
        else:
            for index, substitution in enumerate(substitutions):
                if (
                    not isinstance(substitution, dict)
                    or "capability" not in substitution
                    or "native_equivalence_allowed" not in substitution
                ):
                    errors.append(
                        f"migration_scope.allowed_platform_substitutions[{index}] "
                        "must carry capability and native_equivalence_allowed"
                    )
    parity_mode = migration_scope.get("visual_parity_mode", "strict")
    if parity_mode not in {"strict", "native-adaptive"}:
        errors.append("migration_scope.visual_parity_mode must be strict or native-adaptive")
        parity_mode = "strict"
    facts["visual_parity_mode"] = parity_mode
    facts["included_features"] = included

    ownership = scope.get("ownership") if isinstance(scope.get("ownership"), dict) else {}
    actor_values: list[str] = []
    for key in (
        "migration_controller_id", "inventory_lead_id", "code_map_agent_id", "business_rule_agent_id",
        "data_dependency_agent_id", "evidence_administrator_id", "coverage_checker_id",
    ):
        value = need(ownership, key, f"ownership.{key}", errors)
        if isinstance(value, str) and not unresolved(value):
            if not ACTOR_RE.fullmatch(value):
                errors.append(f"Invalid actor ID: ownership.{key}")
            actor_values.append(value)
    runtime_agents = ownership.get("runtime_state_agent_ids")
    if not isinstance(runtime_agents, list) or not runtime_agents:
        errors.append("ownership.runtime_state_agent_ids must be a non-empty list")
    else:
        for value in runtime_agents:
            if not isinstance(value, str) or not ACTOR_RE.fullmatch(value):
                errors.append("ownership.runtime_state_agent_ids contains an invalid actor ID")
            else:
                actor_values.append(value)
    if len(actor_values) != len(set(actor_values)):
        errors.append("Every frozen controller and Phase 2 actor ID must be distinct")

    pending = scope.get("pending_confirmations")
    if not isinstance(pending, list):
        errors.append("pending_confirmations must be an explicit list")
    elif pending:
        errors.append("Phase 1 cannot PASS with pending confirmations")

    policy = scope.get("tool_policy") if isinstance(scope.get("tool_policy"), dict) else {}
    if policy.get("runtime_ui_tool") != "android-cli":
        errors.append("tool_policy.runtime_ui_tool must be android-cli")
    if policy.get("layout_inspector_allowed") is not False:
        errors.append("tool_policy.layout_inspector_allowed must be false")
    analyzer_value = need(policy, "apk_analyzer_bin", "tool_policy.apk_analyzer_bin", errors)
    if apk_path.is_file() and isinstance(analyzer_value, str) and not unresolved(analyzer_value):
        validate_apk_identity(analyzer_value, apk_path, android, errors)

    environments = scope.get("environments")
    if not isinstance(environments, list) or not environments:
        errors.append("At least one environment is required")
        return errors, warnings, None, facts

    baseline_ids: list[str] = []
    env_ids: set[str] = set()
    required_env = (
        "env_id", "account_id", "account_role", "seed_data_id", "seed_reset_ref",
        "network_profile", "network_conditions_ref", "network_toggle_available", "emulator_model",
        "device_serial", "resolution", "density_dpi", "android_api_level", "orientation", "locale",
        "theme", "font_scale", "timezone", "permissions_profile",
    )
    for index, env in enumerate(environments):
        if not isinstance(env, dict):
            errors.append(f"environments[{index}] must be an object")
            continue
        for key in required_env:
            need(env, key, f"environments[{index}].{key}", errors)
        env_id = str(env.get("env_id", ""))
        if env_id and not ID_RE.fullmatch(env_id):
            errors.append(f"Invalid ENV-ID: {env_id}")
        if env_id in env_ids:
            errors.append(f"Duplicate ENV-ID: {env_id}")
        env_ids.add(env_id)
        if env.get("is_baseline") is True:
            baseline_ids.append(env_id)
        if not isinstance(env.get("network_toggle_available"), bool):
            errors.append(f"{env_id or index}: network_toggle_available must be boolean")
        if not isinstance(env.get("density_dpi"), int):
            errors.append(f"{env_id or index}: density_dpi must be an integer")
        if not isinstance(env.get("android_api_level"), int):
            errors.append(f"{env_id or index}: android_api_level must be an integer")
        if not isinstance(env.get("font_scale"), (int, float)):
            errors.append(f"{env_id or index}: font_scale must be numeric")

    if len(baseline_ids) != 1:
        errors.append(f"Exactly one baseline environment is required; found {len(baseline_ids)}")
    baseline_env_id = baseline_ids[0] if len(baseline_ids) == 1 else None
    for name in (
        "task-ledger.csv", "decision-log.csv", "rework-log.csv", "work-order-registry.csv",
        "evidence-anchor-registry.csv",
        "phase4-attempt-ledger.csv",
    ):
        if not (run_dir / "controller" / name).is_file():
            errors.append(f"Missing controller record: controller/{name}")
    try:
        ledger_rows = read_csv_rows(run_dir / "controller" / "task-ledger.csv")
        phase1_rows = [row for row in ledger_rows if row.get("phase") == "1"]
        phase2_rows = [row for row in ledger_rows if row.get("phase") == "2"]
        if len(phase1_rows) != 1 or len(phase2_rows) != 1:
            errors.append("Task ledger must contain exactly one Phase 1 and one Phase 2 row")
        else:
            expected_controller = ownership.get("migration_controller_id")
            expected_lead = ownership.get("inventory_lead_id")
            if phase1_rows[0].get("owner") not in {expected_controller, "migration-controller"}:
                errors.append("Phase 1 task owner differs from frozen controller")
            if phase2_rows[0].get("owner") not in {expected_lead, "android-inventory-lead"}:
                errors.append("Phase 2 task owner differs from frozen inventory lead")
            if phase1_rows[0].get("owner") != expected_controller or phase2_rows[0].get("owner") != expected_lead:
                warnings.append("Task owners are template defaults and will be normalized by --write")
    except (OSError, ValueError) as exc:
        errors.append(f"Invalid task ledger: {exc}")
    facts["scope_sha256"] = sha256_file(run_dir / "controller" / "scope.json")
    facts["run_manifest_sha256"] = sha256_file(run_dir / "run-manifest.json") if (run_dir / "run-manifest.json").is_file() else None
    return errors, warnings, baseline_env_id, facts



def read_csv_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except FileNotFoundError:
        return []


def parse_json_id_list(value: str, label: str, errors: list[str]) -> list[str]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        errors.append(f"{label} must be a JSON string array")
        return []
    if (
        not isinstance(parsed, list)
        or not parsed
        or any(not isinstance(item, str) or not ID_RE.fullmatch(item) for item in parsed)
        or len(parsed) != len(set(parsed))
    ):
        errors.append(f"{label} must contain unique safe IDs")
        return []
    return parsed



def safe_relative_path(root: Path, relative: str, label: str, errors: list[str]) -> Path | None:
    """Resolve an existing run-local path without following a symbolic-link component."""
    pure = PurePosixPath(str(relative))
    if pure.is_absolute() or ".." in pure.parts or not pure.parts or str(pure) in {"", "."}:
        errors.append(f"Unsafe {label} path: {relative!r}")
        return None
    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            errors.append(f"Symbolic links are prohibited in {label} path: {relative}")
            return None
    try:
        resolved_root = root.resolve()
        resolved = current.resolve()
        resolved.relative_to(resolved_root)
    except (OSError, ValueError):
        errors.append(f"{label} path escapes its root: {relative}")
        return None
    if not resolved.exists():
        errors.append(f"Missing {label}: {resolved}")
        return None
    return resolved


def actor_ids(ownership: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for value in ownership.values():
        if isinstance(value, str) and value:
            values.add(value)
        elif isinstance(value, list):
            values.update(str(item) for item in value if isinstance(item, str) and item)
    return values


def parse_sha256_manifest(path: Path, label: str, errors: list[str]) -> dict[str, str]:
    expected: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"Cannot read {label}: {exc}")
        return expected
    for number, line in enumerate(lines, start=1):
        if "  " not in line:
            errors.append(f"Malformed {label} line {number}")
            continue
        digest, relative = line.split("  ", 1)
        pure = PurePosixPath(relative)
        if (
            not SHA256_RE.fullmatch(digest)
            or pure.is_absolute()
            or ".." in pure.parts
            or not pure.parts
            or "\\" in relative
            or relative in expected
        ):
            errors.append(f"Unsafe or duplicate {label} entry: {relative!r}")
            continue
        expected[relative] = digest
    return expected


def verify_exact_manifest(
    directory: Path,
    manifest_name: str,
    excluded: set[str],
    label: str,
    errors: list[str],
) -> dict[str, str]:
    manifest_path = directory / manifest_name
    if not manifest_path.is_file() or manifest_path.is_symlink():
        errors.append(f"Missing or unsafe {label}: {manifest_path}")
        return {}
    excluded_parts = set(getattr(verify_exact_manifest, "_excluded_parts", set()))
    expected = parse_sha256_manifest(manifest_path, label, errors)
    actual: dict[str, Path] = {}
    for path in directory.rglob("*"):
        relative_probe = path.relative_to(directory).as_posix()
        if any(part in excluded_parts for part in PurePosixPath(relative_probe).parts):
            continue
        if path.is_symlink():
            errors.append(f"Symbolic links are prohibited in {label} package: {path}")
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        if relative in excluded:
            continue
        actual[relative] = path
    if set(expected) != set(actual):
        errors.append(
            f"{label} file set changed; missing={sorted(set(expected) - set(actual))[:5]}, "
            f"extra={sorted(set(actual) - set(expected))[:5]}"
        )
    for relative in sorted(set(expected) & set(actual)):
        if sha256_file(actual[relative]) != expected[relative]:
            errors.append(f"{label} hash mismatch: {relative}")
    return expected


def validate_complete_png(path: Path) -> tuple[int, int]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size < 45:
        raise ValueError(f"Missing, unsafe, or empty PNG: {path}")
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Invalid PNG signature: {path}")
    offset = 8
    chunks: list[tuple[bytes, bytes]] = []
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError(f"Truncated PNG chunk: {path}")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_type = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data):
            raise ValueError(f"Truncated PNG payload: {path}")
        payload = data[offset + 8:offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length:end])[0]
        if (binascii.crc32(chunk_type + payload) & 0xFFFFFFFF) != expected_crc:
            raise ValueError(f"PNG CRC mismatch: {path}")
        chunks.append((chunk_type, payload))
        offset = end
        if chunk_type == b"IEND":
            break
    if offset != len(data) or not chunks or chunks[0][0] != b"IHDR" or chunks[-1][0] != b"IEND":
        raise ValueError(f"PNG chunk order or trailing data is invalid: {path}")
    if len([kind for kind, _ in chunks if kind == b"IHDR"]) != 1 or len(chunks[0][1]) != 13:
        raise ValueError(f"PNG must contain one valid IHDR: {path}")
    width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1]
    )
    allowed_depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
    if (
        width < 1 or height < 1 or compression != 0 or filtering != 0 or interlace != 0
        or color_type not in allowed_depths or bit_depth not in allowed_depths[color_type]
    ):
        raise ValueError(f"PNG dimensions or encoding are unsupported: {path}")
    idat = b"".join(payload for kind, payload in chunks if kind == b"IDAT")
    if not idat:
        raise ValueError(f"PNG has no IDAT data: {path}")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    expected_size = height * (((width * channels * bit_depth + 7) // 8) + 1)
    try:
        decompressor = zlib.decompressobj()
        pixels = decompressor.decompress(idat, expected_size + 1)
        pixels += decompressor.flush()
    except zlib.error as exc:
        raise ValueError(f"PNG image data is corrupt: {path}: {exc}") from exc
    if not decompressor.eof or decompressor.unused_data or len(pixels) != expected_size:
        raise ValueError(f"PNG image data length is invalid: {path}")
    return width, height


def phase4_closure_excluded(relative: PurePosixPath) -> bool:
    value = relative.as_posix()
    if value in STAGE4_CLOSURE_EXACT_EXCLUDES:
        return True
    if any(part in {".locks", ".staging", "__pycache__", ".pytest_cache"} for part in relative.parts):
        return True
    if relative.suffix in {".tmp", ".pyc"} or relative.name.endswith(".lock"):
        return True
    return bool(
        relative.parts
        and relative.parts[0] == "harmony-project"
        and any(part in STAGE4_PROJECT_EXCLUDED_PARTS for part in relative.parts[1:])
    )


def verify_phase4_closure(workspace: Path, errors: list[str]) -> dict[str, str]:
    manifest = workspace / "stage-04-closure-manifest.sha256"
    if not manifest.is_file() or manifest.is_symlink():
        errors.append("Phase 4 closure manifest is missing or unsafe")
        return {}
    expected = parse_sha256_manifest(manifest, "Phase 4 closure manifest", errors)
    actual: dict[str, Path] = {}
    for path in workspace.rglob("*"):
        relative = PurePosixPath(path.relative_to(workspace).as_posix())
        if phase4_closure_excluded(relative):
            continue
        if path.is_symlink():
            errors.append(f"Symbolic links are prohibited in Phase 4 closure: {path}")
            continue
        if path.is_file():
            actual[relative.as_posix()] = path
    if set(expected) != set(actual):
        errors.append(
            "Phase 4 closure file set changed; "
            f"missing={sorted(set(expected) - set(actual))[:5]}, "
            f"extra={sorted(set(actual) - set(expected))[:5]}"
        )
    for relative in sorted(set(expected) & set(actual)):
        if sha256_file(actual[relative]) != expected[relative]:
            errors.append(f"Phase 4 closure hash mismatch: {relative}")
    return expected


def phase4_project_snapshot(project: Path, errors: list[str]) -> tuple[str | None, list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    if not project.is_dir() or project.is_symlink():
        errors.append(f"Phase 4 HarmonyOS project is missing or unsafe: {project}")
        return None, entries
    for path in sorted(project.rglob("*")):
        relative = path.relative_to(project)
        if any(part in STAGE4_PROJECT_EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.is_symlink():
            errors.append(f"Symbolic links are prohibited in the Phase 4 project: {path}")
            continue
        if path.is_file():
            entries.append(
                {"path": relative.as_posix(), "sha256": sha256_file(path), "size": path.stat().st_size}
            )
    entries.sort(key=lambda item: item["path"])
    canonical = json.dumps(entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), entries


def validate_phase4_attempt_chain(rows: list[dict[str, str]], errors: list[str]) -> None:
    previous = "0" * 64
    identities: set[str] = set()
    evidence_ids: set[str] = set()
    for row in rows:
        material = {field: row.get(field, "") for field in PHASE4_ATTEMPT_FIELDS[:-1]}
        expected = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if (
            set(row) != set(PHASE4_ATTEMPT_FIELDS)
            or not row.get("execution_id") or row.get("execution_id") in identities
            or not row.get("evidence_id") or row.get("evidence_id") in evidence_ids
            or row.get("previous_chain_sha256") != previous
            or row.get("chain_sha256") != expected
        ):
            errors.append("Phase 4 attempt ledger hash chain or identity differs")
            return
        identities.add(row["execution_id"])
        evidence_ids.add(row["evidence_id"])
        previous = expected


def directory_snapshot_facts(directory: Path) -> tuple[str, int, int]:
    entries: list[dict[str, Any]] = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symbolic links are prohibited in directory snapshot: {path}")
        if path.is_file():
            entries.append(
                {
                    "path": path.relative_to(directory).as_posix(),
                    "sha256": sha256_file(path),
                    "size": path.stat().st_size,
                }
            )
    canonical = json.dumps(entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), sum(item["size"] for item in entries), len(entries)


def verify_sealed_package(
    directory: Path,
    package_id: str,
    lifecycle: str,
    label: str,
    errors: list[str],
) -> dict[str, str]:
    expected = verify_exact_manifest(
        directory, "manifest.sha256", {"manifest.sha256", "COMMITTED"}, label, errors
    )
    marker = directory / "COMMITTED"
    manifest = directory / "manifest.sha256"
    if not marker.is_file() or marker.is_symlink() or not manifest.is_file():
        errors.append(f"{label} is not COMMITTED")
    else:
        try:
            value = marker.read_text(encoding="utf-8").strip()
            manifest_digest = sha256_file(manifest)
            if not value.startswith(f"{package_id} {lifecycle} manifest_sha256={manifest_digest}"):
                errors.append(f"{label} COMMITTED marker is invalid")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"Cannot read {label} COMMITTED marker: {exc}")
    sealed_paths = (directory, *directory.rglob("*")) if directory.is_dir() else ()
    for path in sealed_paths:
        if path.stat().st_mode & 0o222:
            display = "." if path == directory else path.relative_to(directory)
            errors.append(f"{label} contains a writable sealed path: {display}")
            break
    return expected


def index_unique_rows(
    rows: list[dict[str, str]], key: str, label: str, errors: list[str]
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        identifier = row.get(key, "")
        if not ID_RE.fullmatch(identifier) or identifier in result:
            errors.append(f"{label} has an unsafe or duplicate {key}: {identifier!r}")
            continue
        result[identifier] = row
    return result


def validate_phase4_commands(
    package_dir: Path,
    commands: Any,
    environment: dict[str, Any],
    expected_categories: list[str],
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(commands, list) or [
        item.get("category") if isinstance(item, dict) else None for item in commands
    ] != expected_categories:
        errors.append(f"{label} command category sequence differs")
        return
    contracts = environment.get("category_contracts") if isinstance(environment.get("category_contracts"), dict) else {}
    command_ids: set[str] = set()
    for command in commands:
        category = str(command.get("category", ""))
        command_id = str(command.get("command_id", ""))
        contract = contracts.get(category) if isinstance(contracts.get(category), dict) else {}
        stdout = safe_relative_path(
            package_dir, str(command.get("stdout_path", "")), f"{label} stdout", errors
        )
        stderr = safe_relative_path(
            package_dir, str(command.get("stderr_path", "")), f"{label} stderr", errors
        )
        argv = command.get("argv")
        plan_argv = command.get("plan_argv")
        if (
            not ID_RE.fullmatch(command_id)
            or command_id in command_ids
            or not contract
            or command.get("resolved_executable") != contract.get("resolved_executable")
            or command.get("executable_sha256") != contract.get("executable_sha256")
            or command.get("required_argv_tokens") != contract.get("required_argv_tokens")
            or command.get("success_output_contains") != contract.get("success_output_contains")
            or command.get("error_output_contains") != contract.get("error_output_contains")
            or command.get("success_output_matches") != contract.get("success_output_contains")
            or command.get("error_output_matches") != []
            or command.get("exit_code") != 0
            or command.get("timed_out") is not False
            or command.get("semantic_error") is not False
            or command.get("command_verdict") != "PASS"
            or not isinstance(plan_argv, list)
            or not isinstance(argv, list)
            or not argv
            or len(argv) != len(plan_argv)
            or plan_argv[0] != contract.get("resolved_executable")
            or argv[0] != contract.get("resolved_executable")
            or any(token not in plan_argv for token in contract.get("required_argv_tokens", []))
            or any(
                not isinstance(planned, str)
                or not isinstance(actual, str)
                or not actual
                or ("{" not in planned and actual != planned)
                or (planned.startswith("{") and planned.endswith("}") and actual == planned)
                for planned, actual in zip(plan_argv, argv)
            )
            or not stdout
            or not stderr
            or not stdout.is_file()
            or not stderr.is_file()
            or command.get("stdout_sha256") != sha256_file(stdout)
            or command.get("stderr_sha256") != sha256_file(stderr)
        ):
            errors.append(f"{label} command record differs from frozen contract: {category}")
        command_ids.add(command_id)
        selector = environment.get("device_selector_tokens")
        serial = str(environment.get("emulator", {}).get("serial", ""))
        bundle = str(environment.get("base_application", {}).get("bundle_name", ""))
        serial_categories = {
            "BUNDLE_CHECK", "DEVICE_CHECK", "CLEAN_INSTALL", "SEED_RESET", "NETWORK_PROFILE",
            "PERMISSION_PROFILE", "LAUNCH", "NAVIGATE", "BUSINESS_ASSERT",
            "SCREENSHOT_CAPTURE", "UITEST_SNAPSHOT_CAPTURE",
        }
        bundle_categories = {
            "BUNDLE_CHECK", "SIGNING_CHECK", "CLEAN_INSTALL", "SEED_RESET",
            "PERMISSION_PROFILE", "LAUNCH", "NAVIGATE", "BUSINESS_ASSERT",
            "SCREENSHOT_CAPTURE", "UITEST_SNAPSHOT_CAPTURE",
        }
        selector_present = False
        if isinstance(plan_argv, list) and isinstance(selector, list) and selector:
            selector_present = any(
                plan_argv[index:index + len(selector)] == selector
                for index in range(0, len(plan_argv) - len(selector) + 1)
            )
        if category in serial_categories and (
            not isinstance(plan_argv, list) or serial not in plan_argv or not selector_present
        ):
            errors.append(f"{label} command lacks exact frozen emulator selection: {category}")
        if category in bundle_categories and (
            not isinstance(plan_argv, list) or bundle not in plan_argv
        ):
            errors.append(f"{label} command lacks exact frozen Bundle: {category}")
        if stdout and stderr and stdout.is_file() and stderr.is_file():
            combined = stdout.read_text(encoding="utf-8", errors="replace") + "\n" + stderr.read_text(
                encoding="utf-8", errors="replace"
            )
            successes = [item for item in contract.get("success_output_contains", []) if item in combined]
            failures = [
                item for item in contract.get("error_output_contains", []) if item.lower() in combined.lower()
            ]
            if (
                successes != command.get("success_output_matches")
                or failures != command.get("error_output_matches")
                or failures
            ):
                errors.append(f"{label} command output verdict differs: {category}")



GMI_ARTIFACT_HASH_TARGETS = (
    ("candidates_dir_sha256", "dir", "candidates"),
    ("coverage_ledger_sha256", "file", "coverage/coverage-ledger.csv"),
    ("runtime_evidence_dir_sha256", "dir", "runtime-evidence"),
    ("behavior_contracts_sha256", "file", "behavior-contracts.csv"),
    ("phase2_report_sha256", "file", "phase-2-report.md"),
    # 新范式（#41）：对账表入链（reconciliation.csv 是规则 3 的核心判定输入）
    ("reconciliation_sha256", "file", "reconciliation.csv"),
    # P2 视觉记忆（#75）：per-surface 视觉基准（截图引用/ui-tree 摘要/色板）
    ("visual_memory_sha256", "file", "visual-memory.json"),
)


def gmi_directory_digest(directory: Path) -> str:
    """Reproduce gmi_closure.py's sha256_dir over sorted relative paths."""
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
            digest.update(sha256_file(path).encode("utf-8"))
    return digest.hexdigest()


def verify_gmi_artifact_hashes(
    phase_dir: Path, gmi: dict[str, Any], errors: list[str]
) -> None:
    """Gate 2 rule 6: the gmi closure hash chain must stay intact (no relaxation).

    gmi_closure.py records an empty digest for absent optional facts (for
    example behavior-contracts.csv); absence is not tampering, but every
    declared digest must still re-verify against the workspace.
    """
    declared = gmi.get("artifact_hashes")
    if not isinstance(declared, dict) or not declared:
        errors.append("gmi closure artifact_hashes is missing or empty")
        return
    for key, kind, relative in GMI_ARTIFACT_HASH_TARGETS:
        digest = str(declared.get(key, ""))
        if not digest:
            continue
        target = phase_dir / relative
        if kind == "dir":
            actual = gmi_directory_digest(target) if target.is_dir() else ""
        else:
            actual = sha256_file(target) if target.is_file() else ""
        if actual != digest:
            errors.append(f"gmi closure artifact hash mismatch: {key} ({relative})")


def _read_required_csv(
    phase_dir: Path, relative: str, errors: list[str]
) -> list[dict[str, str]]:
    """Read a Gate 2 v2 required CSV; a missing file is an error, not silence."""
    path = phase_dir / relative
    if not path.is_file():
        errors.append(f"Missing Phase 2 artifact: {path}")
        return []
    try:
        return read_csv_rows(path)
    except (OSError, ValueError) as exc:
        errors.append(f"{relative} is unreadable: {exc}")
        return []


def validate_phase2_gmi(
    run_dir: Path,
    scope: dict[str, Any],
    baseline_env_id: str | None,
    phase1_facts: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Gate 2 v2: release Phase 3 on explained core coverage (task #40 paradigm).

    Gate 2 no longer demands runtime proof for every page. PASS requires all
    six rules to hold with zero errors:
      1. functional coverage: every scope included feature appears in
         feature-map.json features[].feature_id;
      2. behavior-contract completeness: every included feature owns at least
         one behavior-contracts.csv row;
      3. high-risk verification: every RUNTIME_REQUIRED contract reconciles to
         CONFIRMED / SOURCE_CONFIRMED / a GAP with a non-empty reason; any
         CONFLICT is an error (fix batch #89-2): a self-contradictory
         "standard answer" must not be explained away — closure
         conflicts_explained stays in the closure structure as a human
         investigation record but Gate 2 no longer waives on it. Batch-1
         hardening (#81): a reconciliation row whose runtime_status is
         INVALID_CONTRACT or UNSUPPORTED_ORACLE on a RUNTIME_REQUIRED
         contract is an error (contract incompleteness must be fixed, not
         tolerated as GAP);
      4. data unknowns: data-relations.csv has no high-risk row with
         persistence_location=UNKNOWN;
      5. explicit gaps: every closure gaps[] entry carries a feature_id and a
         non-empty reason;
      6. the gmi closure artifact_hashes chain re-verifies (anti-tamper, kept).

    Removed strict/legacy checks (replaced by reconciliation, not by trust):
    page visit ratios, NOT_ENTERED on runtime pages, candidate-table
    completeness, file-level coverage UNMAPPED, hard audit-discrepancy blocks,
    and the catalogs/inventory distillation chain.
    """
    errors: list[str] = []
    warnings: list[str] = []
    phase_dir = run_dir / "phase-02-android-inventory"

    try:
        gmi = load_json(phase_dir / "phase-2-closure.json")
    except ValueError as exc:
        errors.append(f"gmi Phase 2 closure unreadable: {exc}")
        return errors, warnings
    if gmi.get("generator") != "gmi_closure":
        errors.append("phase-2-closure.json is not a gmi closure")
        return errors, warnings

    expected_features = {
        str(item).strip()
        for item in scope.get("migration_scope", {}).get("included_features", [])
        if str(item).strip()
    }

    # Rule 1 - functional coverage against the frozen feature map.
    try:
        feature_map = load_json(phase_dir / "feature-map.json")
    except ValueError as exc:
        errors.append(f"feature-map.json unreadable: {exc}")
        feature_map = {}
    mapped_features: list[dict[str, Any]] = []
    raw_features = feature_map.get("features")
    if isinstance(raw_features, list):
        mapped_features = [item for item in raw_features if isinstance(item, dict)]
    elif feature_map:
        errors.append("feature-map.json features[] is missing or not a list")
    mapped_ids = {str(item.get("feature_id", "")).strip() for item in mapped_features}
    mapped_ids.discard("")
    high_risk_features = {
        str(item.get("feature_id", "")).strip()
        for item in mapped_features
        if str(item.get("risk", item.get("impact", ""))).strip().lower() == "high"
    }
    for feature_id in sorted(expected_features - mapped_ids):
        errors.append(f"included feature missing from feature-map.json: {feature_id}")

    # Rule 2 - every included feature owns at least one behavior contract row.
    contract_rows = _read_required_csv(phase_dir, "behavior-contracts.csv", errors)
    covered_features = {str(row.get("feature_id", "")).strip() for row in contract_rows}
    for feature_id in sorted(expected_features - covered_features):
        errors.append(f"included feature has no behavior contract row: {feature_id}")

    # Rule 3 - high-risk reconciliation (replaces the audit-replay hard block).
    reconciliation_rows = _read_required_csv(phase_dir, "reconciliation.csv", errors)
    reconciliation_by_bc: dict[str, list[dict[str, str]]] = {}
    for row in reconciliation_rows:
        bc_id = str(row.get("bc_id", "")).strip()
        if bc_id:
            reconciliation_by_bc.setdefault(bc_id, []).append(row)
    # 修复批次（任务 #89 修 2）：CONFLICT 一律 error。conflicts_explained
    # 字段保留在 closure 结构中作为人工调查记录，但 Gate 2 不再以它放行
    # （"标准答案"自相矛盾时 Phase 4 拿到的是坏答案，解释不能替代重采集）。
    for row in contract_rows:
        if str(row.get("evidence_class", "")).strip().upper() != "RUNTIME_REQUIRED":
            continue
        bc_id = str(row.get("bc_id", "")).strip() or "<behavior contract row without bc_id>"
        matches = reconciliation_by_bc.get(bc_id)
        if not matches:
            errors.append(f"{bc_id}: RUNTIME_REQUIRED contract has no reconciliation row")
            continue
        for match in matches:
            # Column contract with reconcile.py (agent B, task #39): the formal
            # columns are `verdict` and `note`; `status`/`reason` are accepted
            # as legacy aliases. Blocked collections (NAV_FAIL/STEPS_FAIL/
            # ANR_BLOCKED/UNRESOLVED_PAGE_REF/PRECONDITION_FAILED) are already
            # distilled to GAP, and only evaluated assertion failures
            # (CHAIN_FAIL) surface as CONFLICT on B's side, so the four-value
            # verdict set is final here.
            #
            # 收敛式重构批次1（任务 #81）Gate 2 对齐：RUNTIME_REQUIRED 契约的
            # reconciliation 若出现 INVALID_CONTRACT（BC 缺 result_assertions
            # 等必填段）或 UNSUPPORTED_ORACLE（断言全部无可用 oracle）→ error，
            # 不再按 GAP 宽容放行——契约不完整必须回修 BC 而不是带病过关。
            runtime_status = str(match.get("runtime_status", "")).strip().upper()
            if runtime_status in {"INVALID_CONTRACT", "UNSUPPORTED_ORACLE"}:
                errors.append(
                    f"{bc_id}: reconciliation {runtime_status} on a "
                    "RUNTIME_REQUIRED contract is an error (fill the missing "
                    "contract fields / use supported oracle kinds "
                    "text_visible|text_gone|persist_after_restart; not a "
                    "tolerable GAP)"
                )
                continue
            status = str(match.get("verdict", match.get("status", ""))).strip().upper()
            reason = str(match.get("reason", "") or match.get("note", "") or "").strip()
            if status in {"CONFIRMED", "SOURCE_CONFIRMED"}:
                continue
            if status == "GAP":
                if not reason:
                    errors.append(f"{bc_id}: reconciliation GAP lacks a reason")
                elif str(row.get("impact", "")).strip().lower() == "high":
                    # 提交前自检 3-A（最小修复）：high-impact 核心契约以 GAP 结项
                    # 虽符合"明确 GAP 可放行"方案，但 reason 质量无门槛——进
                    # warnings 供人工复审可见（不改放行行为，非 error）。
                    warnings.append(
                        f"{bc_id}: high-impact RUNTIME contract resolved as GAP "
                        f"(reason={reason[:60]!r}); verify reason quality in human "
                        "review — Phase 4 will lack this standard answer")
            elif status == "CONFLICT":
                # 修复批次（任务 #89 修 2）：CONFLICT 不可解释放行（删除
                # conflicts_explained 豁免）；必须重新采集（修正断言/采集器
                # 问题）或重新理解源码，最终归 CONFIRMED 或确认采集器缺陷
                # 后重新验证。
                errors.append(
                    f"{bc_id}: reconciliation CONFLICT is an error "
                    "(CONFLICT 不可解释放行；必须重新采集（修正断言/采集器问题）"
                    "或重新理解源码，最终归 CONFIRMED 或确认采集器缺陷后重新验证)"
                )
            else:
                errors.append(
                    f"{bc_id}: reconciliation status is not an accepted verdict: {status!r}"
                )

    # Rule 4 - no high-risk data relation may keep an UNKNOWN persistence location.
    data_relation_rows = _read_required_csv(phase_dir, "data-relations.csv", errors)
    for row in data_relation_rows:
        if str(row.get("persistence_location", "")).strip().upper() != "UNKNOWN":
            continue
        feature_id = str(row.get("feature_id", "")).strip()
        row_risk = str(row.get("risk", row.get("impact", ""))).strip().lower()
        if row_risk == "high" or (feature_id and feature_id in high_risk_features):
            label = (
                row.get("relation_id") or feature_id or "<unnamed row>"
            )
            errors.append(
                f"high-risk data relation has an UNKNOWN persistence location: {label}"
            )

    # Rule 5 - every declared gap must be explicit (feature + reason).
    gaps = gmi.get("gaps")
    if not isinstance(gaps, list):
        gaps = []
    for gap in gaps:
        if not isinstance(gap, dict):
            errors.append("closure gaps[] entry is not an object")
            continue
        feature_id = str(gap.get("feature_id", "")).strip()
        reason = str(gap.get("reason", "")).strip()
        if not feature_id:
            errors.append("closure gap lacks a feature_id")
        elif not reason:
            errors.append(f"closure gap for {feature_id} lacks a reason")

    # Rule 6 - closure hash chain stays intact (anti-tamper, not relaxed).
    verify_gmi_artifact_hashes(phase_dir, gmi, errors)

    warnings.append(
        "Phase 2 validated through Gate 2 v2 "
        "(functional coverage + behavior contracts + reconciliation + explicit gaps)"
    )
    return errors, warnings



# ---------------------------------------------------------------------------
# Gate 3 v3（scaffold-v3 范式重算，#48）。
#
# 旧口径已随 scaffold v3 范式退役：advanced 四件套与 advanced-obligations、
# phase2_closure_sha256 九项旧锁绑定、phase2_asset_files、页面清单覆盖
# （inventory 行数/截图数/架构映射 one-to-one）、route/surface 注册表角色
# 交叉、HENV 设备与 HVER command 全量机制复核。controller 作为重算裁决层
# 独立复算（不信任 stage 报告自述）：
#   1) 功能承载面覆盖：feature-map 每个 verify_mode=RUNTIME feature 至少
#      一个非 container surface 有 ArkUI 载体（lock.surfaces[].route_or_mount
#      ∈ {route, modal@HOST}）；
#   2) 数据契约无孤儿：data-relations 语义对象（feature_id+data_object 双
#      非空）↔ lock.data_contracts[]（feature_id/data_object/interface 键）
#      双向闭合；
#   3) 冒烟链：信任 validate_stage3 的 rules.smoke_chain 状态，轻量复核
#      build-report PASS + HVER 包存在且 sealed；
#   4) 环境链：信任 rules.environment_chain 状态 + henv/hver 绑定。
# 闭包完整性（CLOSED/closure manifest/scaffold snapshot）沿用既有机制。
# ---------------------------------------------------------------------------
STAGE3_V3_INPUT_LOCK_SCHEMA = "scaffold-v3"
STAGE3_V3_REQUIRED_INPUTS = (
    "feature_map", "navigation_relations", "data_relations",
    "scope", "phase2_gate", "phase2_closure",
)
STAGE3_V3_CARRIER_KINDS = {"route", "modal"}
STAGE3_V3_MODAL_MOUNT_RE = re.compile(r"^modal@(.+)$")
STAGE3_V3_PASS_ATTESTATIONS = (
    "real_file_review", "contract_only", "dependency_review", "runtime_smoke",
)
STAGE3_V3_RULE_KEYS = (
    "surface_carrier_coverage", "data_contract_closure",
    "smoke_chain", "environment_chain",
)


def check_stage3_locked_path_records(value: Any, label: str, errors: list[str]) -> None:
    """Recursively verify every input-lock v3 record binding path + sha256."""
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
            check_stage3_locked_path_records(item, f"{label}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            check_stage3_locked_path_records(item, f"{label}[{index}]", errors)


def _load_stage3_v3_input(
    inputs: Any, key: str, errors: list[str], *, as_csv: bool
) -> Any:
    """Load the document frozen by inputs.<key> (JSON or CSV); fail closed."""
    empty: Any = [] if as_csv else {}
    record = inputs.get(key) if isinstance(inputs, dict) else None
    if not isinstance(record, dict):
        return empty
    path_value = record.get("path")
    if not isinstance(path_value, str) or not path_value:
        errors.append(f"Phase 3 inputs.{key}.path is missing or invalid")
        return empty
    try:
        if as_csv:
            return read_csv_rows(Path(path_value))
        return load_json(Path(path_value))
    except (ValueError, OSError) as exc:
        errors.append(f"Cannot load frozen Phase 3 inputs.{key}: {exc}")
        return empty


def index_stage3_v3_surfaces(surfaces: list[Any], errors: list[str]) -> dict[str, str]:
    """Normalize input-lock v3 surfaces[] into {surface_id: carrier_kind}."""
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
        raw_mount = surface.get("route_or_mount")
        if not isinstance(raw_mount, str) or not raw_mount.strip():
            errors.append(f"{label}: route_or_mount is missing or empty")
            continue
        normalized = raw_mount.strip()
        if normalized == "route" or normalized == "none":
            indexed[surface_id] = normalized
        elif STAGE3_V3_MODAL_MOUNT_RE.fullmatch(normalized) and STAGE3_V3_MODAL_MOUNT_RE.fullmatch(normalized).group(1).strip():  # noqa: E501
            indexed[surface_id] = "modal"
        else:
            errors.append(
                f"{label}: route_or_mount must be 'route', 'modal@HOST', or 'none'; "
                f"got {raw_mount!r}"
            )
    return indexed


def recompute_stage3_surface_carriers(
    feature_map: Any,
    surfaces_by_id: dict[str, str],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Rule 1 recompute: every RUNTIME feature is carried by a non-container UI surface."""
    features = feature_map.get("features") if isinstance(feature_map, dict) else None
    if not isinstance(features, list):
        errors.append("feature-map.json lacks a features array")
        features = []
    for feature in features:
        if not isinstance(feature, dict):
            errors.append("feature-map features contains a non-object entry")
            continue
        if str(feature.get("verify_mode", "")).strip().upper() != "RUNTIME":
            continue
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
            flag = surface.get("is_container")
            is_container = (
                flag if isinstance(flag, bool)
                else str(surface.get("kind", "")).strip().lower() == "container"
            )
            if is_container:
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
                # Interface divergence is deferred to the Leader (#48); a warning
                # must not bypass the four blocking rules.
                warnings.append(
                    f"{feature_id}: surface {surface_id} is not declared in the v3 input lock"
                )
        if not ui_surfaces:
            errors.append(
                f"{feature_id}: RUNTIME feature has no non-container UI surface to carry it"
            )
            continue
        if not any(
            surfaces_by_id.get(surface_id) in STAGE3_V3_CARRIER_KINDS
            for surface_id in ui_surfaces
        ):
            errors.append(
                f"{feature_id}: no non-container UI surface has an ArkUI carrier "
                f"(route or modal mount); surfaces={ui_surfaces}"
            )


def _stage3_v3_closure_is_pass(closure: Any) -> bool:
    """Frozen Phase 2 closure PASS judgment, layout-compatible.

    Legacy adapter closures carry final_verdict/evidence_chain_closed.
    gmi-native closures (generator=gmi_closure) carry no adapter verdict
    keys; per the init_scaffold v3 gate their PASS proof is a clean gmi
    gate (unmapped==0 and audit_discrepancy==0). Keep in sync with
    _v3_closure_is_pass in harmonyos-migration-scaffold validate_stage3.py.
    """
    if not isinstance(closure, dict):
        return False
    if closure.get("final_verdict") == "PASS" and closure.get("evidence_chain_closed") is True:
        return True
    if closure.get("generator") == "gmi_closure":
        gate = closure.get("gate") if isinstance(closure.get("gate"), dict) else {}
        return gate.get("unmapped") == 0 and gate.get("audit_discrepancy") == 0
    return False


def recompute_stage3_data_contract_closure(
    data_relations_rows: list[dict[str, str]],
    contracts: list[dict[str, Any]],
    errors: list[str],
) -> None:
    """Rule 2 recompute: semantic data objects and interface contracts close both ways."""
    semantic = {
        (row.get("feature_id", "").strip(), row.get("data_object", "").strip())
        for row in data_relations_rows
        if row.get("feature_id", "").strip() and row.get("data_object", "").strip()
    }
    declared: set[tuple[str, str]] = set()
    for position, contract in enumerate(contracts):
        label = f"data_contracts[{position}]"
        feature_id = ""
        for key in ("feature_id", "feature"):
            candidate = contract.get(key)
            if isinstance(candidate, str) and candidate.strip():
                feature_id = candidate.strip()
                break
        data_object = ""
        for key in ("data_object", "object"):
            candidate = contract.get(key)
            if isinstance(candidate, str) and candidate.strip():
                data_object = candidate.strip()
                break
        if not feature_id or not data_object:
            errors.append(f"{label}: data contract lacks feature_id/data_object identity")
            continue
        interface = ""
        for key in ("interface", "interface_symbol", "contract_symbol"):
            candidate = contract.get(key)
            if isinstance(candidate, str) and candidate.strip():
                interface = candidate.strip()
                break
        if not interface:
            errors.append(f"{label}: data contract lacks a non-empty interface declaration")
            continue
        if (feature_id, data_object) in declared:
            errors.append(
                f"Duplicate v3 data contract for feature={feature_id} data_object={data_object}"
            )
            continue
        declared.add((feature_id, data_object))
    uncovered = sorted(semantic - declared)
    if uncovered:
        errors.append(
            "Semantic data objects without an interface contract: "
            + ", ".join(f"{feature}/{obj}" for feature, obj in uncovered)
        )
    orphans = sorted(declared - semantic)
    if orphans:
        errors.append(
            "Data contracts orphaned outside data-relations: "
            + ", ".join(f"{feature}/{obj}" for feature, obj in orphans)
        )


def validate_phase3(
    run_dir: Path, scope: dict[str, Any], phase1_facts: dict[str, Any]
) -> tuple[list[str], list[str], str | None, str | None, str | None, str | None]:
    """Independently recheck the sealed Phase 3 result under the scaffold-v3 paradigm.

    Design note (batch 4 #87, surface-plan alignment review): the blueprint's
    per-surface ``native_component`` field (batch 3) is deliberately NOT a
    Gate 3 input here. Gate 3 judges carrier coverage, the closure snapshot,
    and work-order binding only; ``native_component`` is a blueprint
    recommendation already frozen and enforced inside the scaffold's own
    stage-03 gate, so re-consuming it here would blur the line between
    hard carrier constraints and blueprint advice. No controller-side
    consumption needed.
    """
    errors: list[str] = []
    warnings: list[str] = []
    phase_dir = run_dir / "phase-03-harmony-scaffold"
    required = (
        "stage-03-input-lock.json", "phase-manifest.json",
        "environments", "harmony-project", "verification",
        "scaffold-snapshot-manifest.json", "build-report.json",
        "stage-03-gate-report.json", "stage-03-closure-manifest.sha256", "CLOSED",
    )
    for name in required:
        candidate = phase_dir / name
        if not candidate.exists() or candidate.is_symlink():
            errors.append(f"Missing or unsafe Phase 3 artifact: {candidate}")

    try:
        input_lock = load_json(phase_dir / "stage-03-input-lock.json")
        phase_manifest = load_json(phase_dir / "phase-manifest.json")
        stage_report = load_json(phase_dir / "stage-03-gate-report.json")
        build_report = load_json(phase_dir / "build-report.json")
    except ValueError as exc:
        errors.append(str(exc))
        return errors, warnings, None, None, None, None

    # The closure snapshot covers every Phase 3 file except the final report, its manifest, and CLOSED.
    verify_exact_manifest._excluded_parts = {
        ".git", ".idea", ".hvigor", "build", "dist", "coverage", "node_modules",
        "oh_modules", "__pycache__", ".pytest_cache", "out",
    }
    verify_exact_manifest(
        phase_dir,
        "stage-03-closure-manifest.sha256",
        STAGE3_CLOSURE_EXACT_EXCLUDES,
        "Phase 3 closure manifest",
        errors,
    )
    verify_exact_manifest._excluded_parts = set()
    stage_report_path = phase_dir / "stage-03-gate-report.json"
    closed_path = phase_dir / "CLOSED"
    if stage_report_path.is_file() and closed_path.is_file():
        try:
            if closed_path.read_text(encoding="utf-8").strip() != sha256_file(stage_report_path):
                errors.append("Phase 3 CLOSED marker does not bind the current stage gate report")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"Cannot read Phase 3 CLOSED marker: {exc}")

    if phase_manifest.get("phase") != 3:
        errors.append("Phase 3 manifest does not identify phase 3")
    if phase_manifest.get("run_id") != scope.get("run_id") or input_lock.get("run_id") != scope.get("run_id"):
        errors.append("Phase 3 run identity differs from controller scope")

    # Resolve the immutable, controller-registered Phase 3 work order.
    work_order_id = str(phase_manifest.get("work_order_id") or input_lock.get("work_order_id") or "")
    work_order: dict[str, Any] = {}
    work_order_sha256: str | None = None
    phase3_ownership: dict[str, Any] = {}
    if not ID_RE.fullmatch(work_order_id):
        errors.append("Phase 3 lacks a safe registered Work-Order-ID")
    work_order_registry = read_csv_rows(run_dir / "controller" / "work-order-registry.csv")
    registry_matches = [
        row for row in work_order_registry
        if row.get("work_order_id") == work_order_id and row.get("phase") == "3"
    ]
    active_phase3_orders = [
        row for row in work_order_registry
        if row.get("phase") == "3" and row.get("status", "").upper() != "SUPERSEDED"
    ]
    if len(active_phase3_orders) != 1 or (
        active_phase3_orders and active_phase3_orders[0].get("work_order_id") != work_order_id
    ):
        errors.append("Controller must have exactly one active Phase 3 work order")
    if len(registry_matches) != 1:
        errors.append("Phase 3 work order is not uniquely registered")
    else:
        registry_row = registry_matches[0]
        work_order_path = safe_relative_path(
            run_dir, registry_row.get("relative_path", ""), "Phase 3 work order", errors
        )
        if work_order_path and work_order_path.is_file():
            try:
                work_order = load_json(work_order_path)
                work_order_sha256 = sha256_file(work_order_path)
            except ValueError as exc:
                errors.append(str(exc))
        if (
            registry_row.get("status") != "ISSUED"
            or registry_row.get("scope_sha256") != phase1_facts.get("scope_sha256")
            or registry_row.get("issued_by") != scope.get("ownership", {}).get("migration_controller_id")
            or work_order_sha256 != registry_row.get("work_order_sha256")
        ):
            errors.append("Registered Phase 3 work order is changed, unauthorized, or bound to another scope")

    if work_order:
        if (
            work_order.get("work_order_id") != work_order_id
            or work_order.get("phase") != 3
            or work_order.get("status") != "ISSUED"
            or work_order.get("run_id") != scope.get("run_id")
            or work_order.get("scope_sha256") != phase1_facts.get("scope_sha256")
            or work_order.get("issued_by") != scope.get("ownership", {}).get("migration_controller_id")
            or work_order.get("required_skill") != "harmonyos-migration-scaffold"
            or work_order.get("included_features") != scope.get("migration_scope", {}).get("included_features")
            or work_order.get("excluded_features") != scope.get("migration_scope", {}).get("excluded_features")
        ):
            errors.append("Phase 3 work-order identity or authority is invalid")
        phase3_ownership = work_order.get("ownership") if isinstance(work_order.get("ownership"), dict) else {}
        role_values: list[str] = []
        for key in STAGE3_ROLE_KEYS:
            value = phase3_ownership.get(key)
            if not isinstance(value, str) or not ACTOR_RE.fullmatch(value):
                errors.append(f"Phase 3 work order has invalid ownership.{key}")
            else:
                role_values.append(value)
        if len(role_values) != len(STAGE3_ROLE_KEYS) or len(role_values) != len(set(role_values)):
            errors.append("All six frozen Phase 3 actor IDs must be present and distinct")
        overlap = sorted(set(role_values) & actor_ids(scope.get("ownership", {})))
        if overlap:
            errors.append(f"Phase 3 actors overlap frozen Phase 1/2 actors: {overlap}")

        if input_lock.get("work_order_id") != work_order_id or phase_manifest.get("work_order_id") != work_order_id:
            errors.append("Phase 3 input lock/manifest does not cite the registered work order")
        if (
            input_lock.get("work_order_sha256") != work_order_sha256
            or phase_manifest.get("work_order_sha256") != work_order_sha256
        ):
            errors.append("Phase 3 input lock/manifest is bound to another work-order digest")
        if input_lock.get("ownership") != phase3_ownership or phase_manifest.get("ownership") != phase3_ownership:
            errors.append("Phase 3 frozen ownership differs from the controller work order")
        if (
            input_lock.get("included_feature_ids")
            != sorted(scope.get("migration_scope", {}).get("included_features", []))
            or input_lock.get("excluded_feature_ids")
            != sorted(scope.get("migration_scope", {}).get("excluded_features", []))
        ):
            errors.append("Phase 3 input lock feature scope differs from controller scope")

        # The v3 scope record binds the immutable controller scope snapshot.
        scope_lock = input_lock.get("inputs", {}).get("scope") if isinstance(input_lock.get("inputs"), dict) else None
        scope_snapshot = phase_dir / "inputs" / "controller-scope.json"
        if (
            not isinstance(scope_lock, dict)
            or not scope_snapshot.is_file()
            or sha256_file(scope_snapshot) != phase1_facts.get("scope_sha256")
        ):
            errors.append("Phase 3 scope snapshot is missing or does not bind the controller scope")

    # ---- Input lock v3: schema, required records, recursive hash binding ----
    if input_lock.get("schema_version") != STAGE3_V3_INPUT_LOCK_SCHEMA:
        errors.append(
            "Phase 3 input lock schema_version must be "
            f"{STAGE3_V3_INPUT_LOCK_SCHEMA!r}; got {input_lock.get('schema_version')!r}"
        )
    inputs = input_lock.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("Phase 3 input lock lacks the v3 inputs object")
        inputs = {}
    for key in STAGE3_V3_REQUIRED_INPUTS:
        record = inputs.get(key)
        if not isinstance(record, dict) or "path" not in record or "sha256" not in record:
            errors.append(f"Phase 3 input lock inputs.{key} must be a record with path and sha256")
    check_stage3_locked_path_records(input_lock, "input_lock", errors)

    # Frozen Phase 2 semantics (existing criteria): closure and gate must be PASS.
    phase2_gate_doc = _load_stage3_v3_input(inputs, "phase2_gate", errors, as_csv=False)
    if phase2_gate_doc.get("phase") != 2 or phase2_gate_doc.get("verdict") != "PASS":
        errors.append("Frozen Phase 2 controller gate is not PASS")
    phase2_closure_doc = _load_stage3_v3_input(inputs, "phase2_closure", errors, as_csv=False)
    if not _stage3_v3_closure_is_pass(phase2_closure_doc):
        errors.append("Frozen Phase 2 closure is not PASS")

    # ---- Rule 1 recompute: surface carrier coverage ----
    feature_map = _load_stage3_v3_input(inputs, "feature_map", errors, as_csv=False)
    surfaces = input_lock.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        errors.append("Phase 3 input lock lacks a non-empty surfaces array")
        surfaces = []
    surfaces_by_id = index_stage3_v3_surfaces(surfaces, errors)
    recompute_stage3_surface_carriers(feature_map, surfaces_by_id, errors, warnings)

    # ---- Rule 2 recompute: data-contract closure (no orphans either way) ----
    data_relations_rows = _load_stage3_v3_input(inputs, "data_relations", errors, as_csv=True)
    contracts_raw = input_lock.get("data_contracts")
    if not isinstance(contracts_raw, list):
        errors.append("Phase 3 input lock data_contracts must be an embedded array")
        contracts_raw = []
    contracts = [item for item in contracts_raw if isinstance(item, dict)]
    if len(contracts) != len(contracts_raw):
        errors.append("Phase 3 input lock data_contracts contains non-object entries")
    recompute_stage3_data_contract_closure(data_relations_rows, contracts, errors)

    # ---- Stage report consistency ----
    expected_architecture_lead = phase3_ownership.get("architecture_lead_id")
    expected_acceptance = phase3_ownership.get("architecture_acceptance_agent_id")
    henv_id = str(stage_report.get("henv_id") or "")
    verification_id = str(stage_report.get("verification_id") or "")
    if not ID_RE.fullmatch(henv_id):
        errors.append("Phase 3 gate report lacks a safe HENV-ID")
    if not ID_RE.fullmatch(verification_id):
        errors.append("Phase 3 gate report lacks a safe HVER-ID")
    if stage_report.get("phase") != 3 or stage_report.get("verdict") != "PASS":
        errors.append("Phase 3 gate report does not say PASS")
    if not ID_RE.fullmatch(str(stage_report.get("gate_id", ""))) or stage_report.get("run_id") != scope.get("run_id"):
        errors.append("Phase 3 gate report has an unsafe Gate-ID or wrong run identity")
    if (
        stage_report.get("reviewer_role") != "architecture-acceptance-agent"
        or stage_report.get("reviewer_id") != expected_acceptance
    ):
        errors.append("Phase 3 report was not issued by the frozen architecture acceptance agent")
    if stage_report.get("errors"):
        errors.append("Phase 3 gate report contains errors")
    rules = stage_report.get("rules") if isinstance(stage_report.get("rules"), dict) else {}
    for rule_key in STAGE3_V3_RULE_KEYS:
        rule = rules.get(rule_key)
        status = rule.get("status") if isinstance(rule, dict) else None
        if status != "PASS":
            errors.append(f"Phase 3 gate report rule {rule_key} is not PASS")
    attestations = stage_report.get("attestations") if isinstance(stage_report.get("attestations"), dict) else {}
    if any(attestations.get(name) is not True for name in STAGE3_V3_PASS_ATTESTATIONS):
        errors.append("Phase 3 acceptance report lacks one or more mandatory v3 attestations")
    input_lock_path = phase_dir / "stage-03-input-lock.json"
    if not input_lock_path.is_file() or stage_report.get("input_lock_sha256") != sha256_file(input_lock_path):
        errors.append("Phase 3 gate report references a different input lock")
    generation_path = phase_dir / "template-generation.json"
    if phase_manifest.get("template_generation_sha256") is not None and (
        not generation_path.is_file()
        or sha256_file(generation_path) != phase_manifest.get("template_generation_sha256")
    ):
        errors.append("Phase 3 ArkUI template provenance is invalid")
    if (
        phase_manifest.get("architecture_lead") != expected_architecture_lead
        or input_lock.get("locked_by") != expected_architecture_lead
    ):
        errors.append("Phase 3 manifest/input lock was not owned by the frozen architecture lead")

    # Ledger ownership is frozen by the work order; Gate 3 remains with the architecture lead.
    phase3_tasks = [row for row in read_csv_rows(run_dir / "controller" / "task-ledger.csv") if row.get("phase") == "3"]
    if (
        len(phase3_tasks) != 1
        or phase3_tasks[0].get("owner") != expected_architecture_lead
        or phase3_tasks[0].get("status") not in {"IN_PROGRESS", "PASS"}
    ):
        errors.append("Controller task ledger does not have the frozen Phase 3 owner and active task")

    controller_phase3_rework = [
        row for row in read_csv_rows(run_dir / "controller" / "rework-log.csv")
        if row.get("phase") == "3"
    ]
    open_controller_rework = [
        row for row in controller_phase3_rework
        if row.get("status", "").upper() != "CLOSED"
    ]
    if open_controller_rework:
        errors.append(f"Controller has open Phase 3 rework: {len(open_controller_rework)}")

    # ---- Smoke and environment chains: light recheck (mechanism verdicts stay
    # with validate_stage3's rules; the controller is the recompute judge, not
    # a copy of E's full mechanism validation). ----
    if build_report.get("status") != "PASS" or build_report.get("verification_id") != verification_id:
        errors.append("Phase 3 build report is not PASS for the selected HVER-ID")
    if build_report.get("henv_id") != henv_id:
        errors.append("Phase 3 build report references another HENV-ID")
    verification_dir = phase_dir / "verification" / verification_id
    if verification_dir.is_dir():
        verify_exact_manifest(
            verification_dir, "manifest.sha256", {"manifest.sha256", "COMMITTED"},
            "HVER manifest", errors,
        )
    else:
        errors.append(f"Selected HVER package is missing: {verification_dir}")
    committed_path = verification_dir / "COMMITTED"
    if committed_path.is_file():
        try:
            committed = committed_path.read_text(encoding="utf-8").strip()
            if not committed.startswith(f"{verification_id} PASS "):
                errors.append("HVER COMMITTED marker does not bind the selected passing verification")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"Cannot read HVER COMMITTED marker: {exc}")
    else:
        errors.append("Selected HVER package is not COMMITTED")

    # ---- Scaffold snapshot (existing mechanism): recompute the digest, bind
    # HVER/build/Gate 3 to it, and recheck the covered file set. ----
    try:
        verification_snapshot = load_json(verification_dir / "scaffold-snapshot-manifest.json")
        current_snapshot = load_json(phase_dir / "scaffold-snapshot-manifest.json")
        verification = load_json(verification_dir / "metadata.json")
    except ValueError as exc:
        errors.append(str(exc))
        verification_snapshot, current_snapshot, verification = {}, {}, {}

    snapshot_entries = current_snapshot.get("entries") if isinstance(current_snapshot.get("entries"), list) else []
    snapshot_paths: dict[str, Path] = {}
    canonical_entries: list[dict[str, Any]] = []
    for index, entry in enumerate(snapshot_entries):
        if not isinstance(entry, dict):
            errors.append(f"Scaffold snapshot entry {index} is not an object")
            continue
        relative = str(entry.get("path", ""))
        path = safe_relative_path(phase_dir, relative, "scaffold snapshot entry", errors)
        if relative in snapshot_paths:
            errors.append(f"Duplicate scaffold snapshot path: {relative}")
            continue
        if path and path.is_file():
            snapshot_paths[relative] = path
            if sha256_file(path) != entry.get("sha256") or path.stat().st_size != entry.get("size"):
                errors.append(f"Current scaffold file differs from snapshot: {relative}")
        canonical_entries.append(entry)
    canonical = json.dumps(canonical_entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    snapshot_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if current_snapshot.get("snapshot_sha256") != snapshot_digest:
        errors.append("Scaffold snapshot manifest digest is invalid")
    if current_snapshot.get("henv_id") != henv_id or current_snapshot.get("entry_count") != len(snapshot_entries):
        errors.append("Scaffold snapshot identity or entry count is invalid")
    if current_snapshot != verification_snapshot:
        errors.append("Current scaffold snapshot manifest differs from the sealed HVER snapshot")
    if (
        verification.get("source_snapshot_sha256") != snapshot_digest
        or build_report.get("source_snapshot_sha256") != snapshot_digest
        or stage_report.get("source_snapshot_sha256") != snapshot_digest
    ):
        errors.append("HVER, build report, or Gate 3 references another scaffold snapshot")

    excluded_value = current_snapshot.get("excluded_generated_parts")
    excluded_parts = set(excluded_value if isinstance(excluded_value, list) else [])
    if excluded_parts != STAGE3_SNAPSHOT_EXCLUDED_PARTS:
        errors.append("Scaffold snapshot uses an unauthorized generated-path exclusion set")
    expected_snapshot_paths: set[str] = set()
    project = phase_dir / "harmony-project"
    if project.is_dir():
        for path in project.rglob("*"):
            if any(part in {".git", ".idea", ".hvigor", "build", "dist", "coverage", "node_modules", "oh_modules", "__pycache__", ".pytest_cache", "out"} for part in PurePosixPath(path.relative_to(project).as_posix()).parts):
                continue
            if path.is_symlink():
                errors.append(f"Symbolic links are prohibited in HarmonyOS project: {path}")
                continue
            relative_project = path.relative_to(project)
            if any(part in STAGE3_SNAPSHOT_EXCLUDED_PARTS for part in relative_project.parts):
                continue
            if path.is_file():
                expected_snapshot_paths.add(path.relative_to(phase_dir).as_posix())
    expected_snapshot_paths.update(STAGE3_SNAPSHOT_REGISTRIES)
    expected_snapshot_paths.add(f"environments/{henv_id}/harmony-environment.json")
    if set(snapshot_paths) != expected_snapshot_paths:
        errors.append(
            f"Current scaffold snapshot file set differs; "
            f"missing={sorted(expected_snapshot_paths - set(snapshot_paths))[:5]}, "
            f"extra={sorted(set(snapshot_paths) - expected_snapshot_paths)[:5]}"
        )

    # ---- Rework mirror consistency (tamper detection) ----
    local_phase3_rework = read_csv_rows(phase_dir / "rework-tickets.csv")
    local_open_rework = [
        row for row in local_phase3_rework if row.get("status", "").upper() != "CLOSED"
    ]
    if local_open_rework:
        errors.append(f"Phase 3 has open local rework tickets: {len(local_open_rework)}")
    local_ids = [row.get("ticket_id", "") for row in local_phase3_rework]
    controller_ids = [row.get("rework_id", "") for row in controller_phase3_rework]
    if len(local_ids) != len(set(local_ids)) or len(controller_ids) != len(set(controller_ids)):
        errors.append("Phase 3 rework ledger or controller mirror contains duplicate Ticket-ID values")
    if set(local_ids) != set(controller_ids):
        errors.append("Phase 3 rework ledger and controller mirror contain different Ticket-ID sets")
    for local in local_phase3_rework:
        ticket_id = str(local.get("ticket_id", ""))
        problem_type = str(local.get("problem_type", "")).upper()
        route = STAGE3_REWORK_ROUTES.get(problem_type)
        if not ID_RE.fullmatch(ticket_id) or route is None:
            errors.append(f"Phase 3 rework ticket identity or type is invalid: {ticket_id!r}")
        else:
            expected_role, actor_key = route
            if (
                local.get("responsible_role") != expected_role
                or local.get("responsible_agent") != phase3_ownership.get(actor_key)
            ):
                errors.append(f"Phase 3 rework ticket differs from frozen routing: {ticket_id}")
        if (
            local.get("severity") not in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
            or local.get("opened_by") != expected_acceptance
            or local.get("confirmed_by") != expected_architecture_lead
            or local.get("status", "").upper() not in {"OPEN", "CLOSED"}
        ):
            errors.append(f"Phase 3 rework ticket authority or lifecycle is invalid: {ticket_id}")
        matches = [row for row in controller_phase3_rework if row.get("rework_id") == ticket_id]
        if len(matches) != 1:
            errors.append(f"Phase 3 rework ticket is not uniquely mirrored: {ticket_id}")
            continue
        mirrored = matches[0]
        expected_fields = {
            "created_at": local.get("opened_at", ""),
            "record_id": local.get("source_or_mapping_id", ""),
            "evidence_id": local.get("failed_verification_id", ""),
            "gate_rule": problem_type,
            "reason": local.get("notes", ""),
            "assigned_to": local.get("responsible_agent", ""),
        }
        if any(mirrored.get(field, "") != value for field, value in expected_fields.items()):
            errors.append(f"Controller rework mirror content differs: {ticket_id}")
        if not mirrored.get("completion_condition", ""):
            errors.append(f"Controller rework mirror lacks completion condition: {ticket_id}")
        if local.get("status", "").upper() == "CLOSED":
            if (
                local.get("closed_by") != expected_acceptance
                or mirrored.get("status") != "CLOSED"
                or mirrored.get("resolved_at") != local.get("closed_at")
                or mirrored.get("resolution_evidence_id")
                != local.get("correction_verification_id")
                or mirrored.get("reviewed_by") != expected_acceptance
            ):
                errors.append(f"Closed Phase 3 rework mirror differs: {ticket_id}")
        elif mirrored.get("status") != "REWORK":
            errors.append(f"Open Phase 3 rework mirror status differs: {ticket_id}")

    return (
        errors,
        warnings,
        henv_id if ID_RE.fullmatch(henv_id) else None,
        verification_id if ID_RE.fullmatch(verification_id) else None,
        str(expected_architecture_lead) if expected_architecture_lead else None,
        work_order_id if ID_RE.fullmatch(work_order_id) else None,
    )


# ==== stage4-v4 gate helpers (Gate 4 new rules) ====
# These recompute helpers mirror harmonyos-feature-implementation/scripts/
# validate_stage4.py (the first-pass judge) but are deliberately independent:
# the controller re-reads the same frozen artifacts and never trusts the
# stage report's self description.  Schema divergences against the G/H
# producers (work orders, replayer, surface-contract thin table) are
# defensively parsed and arbitrated at controller acceptance (#60).

STAGE4_V4_ASSERTION_TYPES = ("observable", "data", "persistence", "side_effect")
STAGE4_V4_STATUSES = ("PASS", "FAIL", "MANUAL_VERIFY_REQUIRED", "PLATFORM_LIMITATION")
STAGE4_V4_ARKTS_SUFFIX = ".ets"
STAGE4_V4_STUB_TODO_RE = re.compile(r"^\s*(?://|/?\*|\*)\s*(TODO|FIXME)\b", re.IGNORECASE)
STAGE4_V4_STUB_TOKEN_RE = re.compile(
    r"__(?:FILL|AUTO)(?:_[A-Z0-9_]+)?__"
    r"|\b(?:TBD|MOCK_ONLY|STUB_ONLY|FAKE_DATA|PLACEHOLDER)\b"
    r"|\bnot[ _-]?implemented\b|\bNotImplementedError\b",
    re.IGNORECASE,
)
STAGE4_V4_STUB_RETURN_RE = re.compile(
    r"\)\s*(?::[^{\n]*)?\{\s*(?://[^\n]*\n\s*)?return\s+(?:null|undefined)\s*;?\s*\}",
)
STAGE4_V4_STUB_EMPTY_RE = re.compile(r"\)\s*(?::[^{\n]*)?\{\s*\}")
STAGE4_V4_STUB_COMMENT_RE = re.compile(r"\)\s*(?::[^{\n]*)?\{\s*(?://[^\n]*\n\s*|\*[^\n]*\n\s*)*\}")
# v4 workspace artifact set (the 32-input-face layout was retired).
STAGE4_V4_REQUIRED_ARTIFACTS = (
    "stage-04-input-lock.json", "phase-manifest.json",
    "replay-results.csv", "surface-contract.csv", "implementation-declarations.csv",
    "environments/h4env-registry.csv", "harmony-project", "builds",
    "stage-04-gate-report.json", "stage-04-closure-manifest.sha256", "CLOSED",
)
# Frozen Phase 2/3 denominators recomputed from the run tree (canonical
# sources; the stage workspace snapshots must agree with these hashes).
STAGE4_V4_FROZEN_INPUTS = {
    "phase2_feature_map": "phase-02-android-inventory/feature-map.json",
    "phase2_behavior_contracts": "phase-02-android-inventory/behavior-contracts.csv",
    "phase2_data_relations": "phase-02-android-inventory/data-relations.csv",
    "phase2_reconciliation": "phase-02-android-inventory/reconciliation.csv",
    "phase3_input_lock": "phase-03-harmony-scaffold/stage-03-input-lock.json",
}


def stage4_v4_split_semantics(value: str) -> list[str]:
    items: list[str] = []
    for token in str(value or "").replace(";", ",").split(","):
        token = token.strip()
        if token and token not in items:
            items.append(token)
    return items


def stage4_v4_stub_scan(text: str) -> list[str]:
    """Static no-op/placeholder detection over one ArkTS source file."""
    findings: list[str] = []
    for line in text.splitlines():
        if STAGE4_V4_STUB_TODO_RE.match(line):
            findings.append(f"todo-marker: {line.strip()[:120]}")
    for match in STAGE4_V4_STUB_TOKEN_RE.finditer(text):
        findings.append(f"placeholder-token: {match.group(0)}")
    for match in STAGE4_V4_STUB_RETURN_RE.finditer(text):
        findings.append(f"null-return-stub: {match.group(0)[:120]}")
    for match in STAGE4_V4_STUB_EMPTY_RE.finditer(text):
        findings.append(f"empty-body-stub: {match.group(0)[:120]}")
    for match in STAGE4_V4_STUB_COMMENT_RE.finditer(text):
        findings.append(f"comment-only-stub: {match.group(0)[:120]}")
    return findings


def stage4_v4_load_denominators(run_dir: Path, errors: list[str]) -> dict[str, Any]:
    """Independently load the frozen Phase 2/3 denominators from the run tree."""
    features: dict[str, dict[str, Any]] = {}
    feature_map_path = run_dir / STAGE4_V4_FROZEN_INPUTS["phase2_feature_map"]
    try:
        feature_map = load_json(feature_map_path)
        rows = feature_map.get("features") if isinstance(feature_map, dict) else None
        if not isinstance(rows, list):
            raise ValueError("feature map lacks the features array")
        for entry in rows:
            if not isinstance(entry, dict):
                raise ValueError("feature map contains a non-object feature")
            feature_id = str(entry.get("feature_id", ""))
            if not feature_id or feature_id in features:
                raise ValueError(f"invalid or duplicate feature: {feature_id!r}")
            features[feature_id] = entry
    except (ValueError, OSError) as exc:
        errors.append(f"Gate 4 cannot load the frozen Phase 2 feature map: {exc}")

    behavior_by_feature: dict[str, list[dict[str, str]]] = {}
    try:
        behavior_rows = read_csv_rows(run_dir / STAGE4_V4_FROZEN_INPUTS["phase2_behavior_contracts"])
        seen_bc: set[str] = set()
        for row in behavior_rows:
            bc_id = str(row.get("bc_id", ""))
            if not bc_id or bc_id in seen_bc:
                errors.append(f"Phase 2 behavior contracts have an invalid/duplicate BC: {bc_id!r}")
                continue
            seen_bc.add(bc_id)
            behavior_by_feature.setdefault(str(row.get("feature_id", "")), []).append(row)
    except (ValueError, OSError) as exc:
        errors.append(f"Gate 4 cannot load the frozen behavior contracts: {exc}")

    try:
        data_relations = read_csv_rows(run_dir / STAGE4_V4_FROZEN_INPUTS["phase2_data_relations"])
    except (ValueError, OSError) as exc:
        errors.append(f"Gate 4 cannot load the frozen data relations: {exc}")
        data_relations = []
    reconciliation_path = run_dir / STAGE4_V4_FROZEN_INPUTS["phase2_reconciliation"]
    reconciliation = read_csv_rows(reconciliation_path) if reconciliation_path.is_file() else []

    data_contracts: list[dict[str, Any]] = []
    try:
        stage3_lock = load_json(run_dir / STAGE4_V4_FROZEN_INPUTS["phase3_input_lock"])
        raw = stage3_lock.get("data_contracts") if isinstance(stage3_lock, dict) else None
        if isinstance(raw, list):
            data_contracts = [item for item in raw if isinstance(item, dict)]
    except (ValueError, OSError) as exc:
        errors.append(f"Gate 4 cannot load the frozen Phase 3 input lock: {exc}")
    return {
        "features": features,
        "behavior_by_feature": behavior_by_feature,
        "data_relations": data_relations,
        "reconciliation": reconciliation,
        "data_contracts": data_contracts,
    }


def stage4_v4_replay_rows(phase_dir: Path, errors: list[str]) -> list[dict[str, str]]:
    try:
        rows = read_csv_rows(phase_dir / "replay-results.csv")
    except (ValueError, OSError) as exc:
        errors.append(f"Gate 4 cannot read replay-results.csv: {exc}")
        return []
    for index, row in enumerate(rows):
        assertion_type = str(row.get("assertion_type", "")).strip().lower()
        assertion_status = str(row.get("assertion_status", "")).strip().upper()
        if not str(row.get("bc_id", "")).strip():
            errors.append(f"replay-results row {index} lacks bc_id")
        if assertion_type not in STAGE4_V4_ASSERTION_TYPES:
            errors.append(f"replay-results row {index} has unknown assertion_type {assertion_type!r}")
        if assertion_status not in STAGE4_V4_STATUSES:
            errors.append(f"replay-results row {index} has unknown assertion_status {assertion_status!r}")
    return rows


def stage4_v4_decisions(phase_dir: Path, errors: list[str]) -> dict[tuple[str, str], dict[str, str]]:
    decisions: dict[tuple[str, str], dict[str, str]] = {}
    path = phase_dir / "decision-log.csv"
    if not path.is_file():
        return decisions
    try:
        rows = read_csv_rows(path)
    except (ValueError, OSError) as exc:
        errors.append(f"Gate 4 cannot read decision-log.csv: {exc}")
        return decisions
    for index, row in enumerate(rows):
        bc_id = str(row.get("bc_id", "")).strip()
        assertion_type = str(row.get("assertion_type", "")).strip().lower()
        decision = str(row.get("decision", "")).strip().upper()
        if (
            not bc_id
            or assertion_type not in STAGE4_V4_ASSERTION_TYPES
            or decision not in {"ACCEPTED", "REJECTED"}
            or not str(row.get("decided_by", "")).strip()
            or not str(row.get("decided_at", "")).strip()
        ):
            errors.append(f"decision-log row {index} is invalid")
            continue
        key = (bc_id, assertion_type)
        if key in decisions:
            errors.append(f"decision-log has duplicate adjudication for {bc_id}/{assertion_type}")
            continue
        decisions[key] = row
    return decisions


def recompute_stage4_runtime_assertions(
    replay_rows: list[dict[str, str]],
    decisions: dict[tuple[str, str], dict[str, str]],
    denominators: dict[str, Any],
    errors: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Rules 1+3 recompute: four-class PASS per RUNTIME BC, deviation queue.

    A behavioral FAIL can never be flipped (user correction 3): explanations
    may accompany the deviation queue but never convert FAIL into PASS.
    """
    features = denominators["features"]
    behavior_by_feature = denominators["behavior_by_feature"]
    runtime_features = sorted(
        feature_id for feature_id, entry in features.items()
        if str(entry.get("verify_mode", "")).upper() == "RUNTIME"
    )
    rows_by_bc: dict[str, list[dict[str, str]]] = {}
    for row in replay_rows:
        rows_by_bc.setdefault(str(row.get("bc_id", "")).strip(), []).append(row)

    runtime_bcs: list[str] = []
    for feature_id in runtime_features:
        runtime_bcs.extend(
            str(row.get("bc_id", "")).strip()
            for row in behavior_by_feature.get(feature_id, [])
        )
    runtime_bcs = sorted(set(runtime_bcs))

    counts = {"PASS": 0, "FAIL": 0, "MANUAL_VERIFY_REQUIRED": 0, "PLATFORM_LIMITATION": 0}
    failing: list[str] = []
    manual_queue: list[dict[str, Any]] = []
    deviations: list[dict[str, Any]] = []
    missing: list[str] = []
    for bc_id in runtime_bcs:
        rows = rows_by_bc.get(bc_id, [])
        if not rows:
            missing.append(bc_id)
            continue
        bc_ok = True
        for assertion_type in STAGE4_V4_ASSERTION_TYPES:
            typed = [
                row for row in rows
                if str(row.get("assertion_type", "")).strip().lower() == assertion_type
            ]
            if not typed:
                errors.append(f"{bc_id}: replay-results lacks assertion class {assertion_type!r}")
                bc_ok = False
                continue
            for row in typed:
                status = str(row.get("assertion_status", "")).strip().upper()
                counts[status] = counts.get(status, 0) + 1
                if status == "FAIL":
                    bc_ok = False
                elif status == "MANUAL_VERIFY_REQUIRED":
                    bc_ok = False
                    manual_queue.append({
                        "bc_id": bc_id,
                        "feature_id": str(row.get("feature_id", "")),
                        "assertion_type": assertion_type,
                        "evidence_ref": str(row.get("evidence_ref", "")),
                    })
                elif status == "PLATFORM_LIMITATION":
                    decision = decisions.get((bc_id, assertion_type))
                    deviations.append({
                        "bc_id": bc_id,
                        "feature_id": str(row.get("feature_id", "")),
                        "assertion_type": assertion_type,
                        "evidence_ref": str(row.get("evidence_ref", "")),
                        "decision": str(decision.get("decision", "")).upper() if decision else "PENDING",
                    })
                    if not decision or str(decision.get("decision", "")).upper() != "ACCEPTED":
                        bc_ok = False
        if not bc_ok:
            failing.append(bc_id)
    for bc_id in missing:
        errors.append(f"{bc_id}: verify_mode=RUNTIME behavior contract has no replay result")
    if manual_queue:
        errors.append(
            f"{len(manual_queue)} replay assertions are MANUAL_VERIFY_REQUIRED; "
            "the machine gate cannot count them as PASS"
        )
    total = len(runtime_bcs)
    rule_pass = total > 0 and not failing and not missing and not manual_queue
    return (
        {
            "status": "PASS" if rule_pass else "FAIL",
            "runtime_features": len(runtime_features),
            "runtime_bcs": total,
            "runtime_bcs_pass": total - len(set(failing)),
            "assertion_counts": counts,
            "failing_bcs": sorted(set(failing)),
            "manual_verify_queue": manual_queue,
        },
        deviations,
        manual_queue,
    )


def recompute_stage4_deviation_rule(
    deviations: list[dict[str, Any]], errors: list[str]
) -> dict[str, Any]:
    accepted = [item for item in deviations if item.get("decision") == "ACCEPTED"]
    pending = [item for item in deviations if item.get("decision") != "ACCEPTED"]
    for item in deviations:
        if item.get("decision") == "REJECTED":
            errors.append(
                "PLATFORM_DEVIATION was REJECTED by human adjudication and still blocks "
                f"the gate: {item.get('bc_id')}/{item.get('assertion_type')}"
            )
    if pending:
        errors.append(
            f"{len(pending)} PLATFORM_DEVIATION items lack an ACCEPTED human decision"
        )
    return {
        "status": "PASS" if not pending else "FAIL",
        "total": len(deviations),
        "accepted": len(accepted),
        "pending_or_rejected": len(pending),
        "items": deviations,
    }


def recompute_stage4_data_parity(
    phase_dir: Path,
    denominators: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Rule 2 recompute: semantic read/write parity + persistence coverage."""
    features = denominators["features"]
    try:
        declaration_rows = read_csv_rows(phase_dir / "implementation-declarations.csv")
    except (ValueError, OSError) as exc:
        errors.append(f"Gate 4 cannot read implementation-declarations.csv: {exc}")
        declaration_rows = []
    declarations: dict[str, dict[str, str]] = {}
    for index, row in enumerate(declaration_rows):
        feature_id = str(row.get("feature_id", "")).strip()
        if not feature_id:
            errors.append(f"implementation-declarations row {index} lacks feature_id")
            continue
        if feature_id in declarations:
            errors.append(f"implementation-declarations duplicate feature {feature_id}")
            continue
        declarations[feature_id] = row

    contract_keys: set[tuple[str, str]] = set()
    contract_ids: set[str] = set()
    android_persistence: dict[str, set[str]] = {}
    for contract in denominators["data_contracts"]:
        feature_id = str(contract.get("feature_id", ""))
        data_object = str(contract.get("data_object", ""))
        if feature_id and data_object:
            contract_keys.add((feature_id, data_object))
        if contract.get("object_id"):
            contract_ids.add(str(contract["object_id"]))
        for carrier in contract.get("android_persistence", []) or []:
            if data_object and str(carrier):
                android_persistence.setdefault(data_object, set()).add(str(carrier))
    for row in denominators["data_relations"]:
        data_object = str(row.get("data_object", "")).strip()
        location = str(row.get("persistence_location", "")).strip()
        kind = str(row.get("persistence_kind", "")).strip()
        if data_object and location and location != "<none>":
            android_persistence.setdefault(data_object, set()).add(f"{kind}:{location}")

    missing_side: list[str] = []
    extra_side: list[str] = []
    persistence_gaps: list[str] = []
    orphan_refs: list[str] = []
    compared = 0
    for feature_id in sorted(features):
        raw = features[feature_id].get("data_objects")
        raw = raw if isinstance(raw, dict) else {}
        android_reads = {str(item) for item in raw.get("reads", []) if str(item)}
        android_writes = {str(item) for item in raw.get("writes", []) if str(item)}
        declaration = declarations.get(feature_id)
        if declaration is None:
            if android_reads or android_writes:
                missing_side.append(f"{feature_id}: implementation declaration is missing")
            continue
        harmony_reads = set(stage4_v4_split_semantics(declaration.get("data_reads", "")))
        harmony_writes = set(stage4_v4_split_semantics(declaration.get("data_writes", "")))
        if android_reads != harmony_reads:
            detail = (
                f"{feature_id}: data read set differs "
                f"(android={sorted(android_reads)}, harmony={sorted(harmony_reads)})"
            )
            (extra_side if harmony_reads - android_reads else missing_side).append(detail)
        if android_writes != harmony_writes:
            detail = (
                f"{feature_id}: data write set differs "
                f"(android={sorted(android_writes)}, harmony={sorted(harmony_writes)})"
            )
            (extra_side if harmony_writes - android_writes else missing_side).append(detail)
        compared += 1
        for ref in stage4_v4_split_semantics(declaration.get("data_contract_refs", "")):
            token = ref.split(":", 1)[1] if ":" in ref else ref
            if (feature_id, token) not in contract_keys and token not in contract_ids:
                orphan_refs.append(f"{feature_id}: unknown data-contract ref {ref!r}")
        declared_persistence = {}
        for item in stage4_v4_split_semantics(declaration.get("harmony_persistence", "")):
            if "=" in item:
                obj, carrier = item.split("=", 1)
                declared_persistence[obj.strip()] = carrier.strip()
            else:
                declared_persistence[item.strip()] = ""
        for data_object in sorted(android_writes | android_reads):
            carriers = android_persistence.get(data_object)
            if carriers and data_object not in declared_persistence:
                persistence_gaps.append(
                    f"{feature_id}: Android persists {data_object!r} ({sorted(carriers)}) "
                    "but the Harmony declaration has no harmony_persistence entry"
                )
    for feature_id in sorted(set(declarations) - set(features)):
        extra_side.append(f"{feature_id}: declaration outside the frozen feature map")
    for detail in missing_side:
        errors.append(f"data parity: {detail}")
    for detail in extra_side:
        errors.append(f"data parity: {detail}")
    for detail in persistence_gaps:
        errors.append(f"data parity (persistence coverage): {detail}")
    for detail in orphan_refs:
        errors.append(f"data parity (contract closure): {detail}")
    ok = not (missing_side or extra_side or persistence_gaps or orphan_refs)
    return {
        "status": "PASS" if ok else "FAIL",
        "features_compared": compared,
        "android_persisted_objects": len(android_persistence),
        "missing_on_harmony": missing_side,
        "extra_on_harmony": extra_side,
        "persistence_gaps": persistence_gaps,
        "orphan_contract_refs": orphan_refs,
    }


def recompute_stage4_must_read_receipt(
    phase_dir: Path,
    denominators: dict[str, Any],
    work_order: dict[str, Any],
    declarations_by_feature: dict[str, dict[str, str]],
    errors: list[str],
) -> dict[str, Any]:
    """Rule 7 recompute (batch 2 #85): MUST_READ receipts + frozen probe.

    Mirrors harmonyos-feature-implementation validate_stage4.evaluate_must_read_receipt
    (single semantics, two independent implementations on purpose): every
    RUNTIME feature needs a non-empty consumed_source_refs receipt drawn from
    the work order's frozen must_read denominators; the frozen
    DebugSemanticProbe must match the work-order expected sha256. Orders
    without the probe binding keep the probe check dormant.
    """
    features = denominators["features"]
    manifest = work_order.get("feature_manifest") if isinstance(work_order, dict) else None
    manifest_by_feature: dict[str, dict[str, Any]] = {}
    if isinstance(manifest, list):
        for item in manifest:
            if isinstance(item, dict) and item.get("feature_id"):
                manifest_by_feature[str(item["feature_id"])] = item

    missing_receipts: list[str] = []
    fabricated: list[str] = []
    checked = 0
    for feature_id in sorted(features):
        if str(features[feature_id].get("verify_mode", "")).upper() != "RUNTIME":
            continue
        declaration = declarations_by_feature.get(feature_id)
        if declaration is None:
            continue
        checked += 1
        consumed = set(
            stage4_v4_split_semantics(declaration.get("consumed_source_refs", "")))
        if not consumed:
            missing_receipts.append(
                f"{feature_id}: RUNTIME feature has no consumed_source_refs "
                "receipt (implementation-declarations.csv)")
        must_read = manifest_by_feature.get(feature_id, {}).get("must_read")
        raw_sources = must_read.get("android_source_refs") if isinstance(must_read, dict) else None
        denominator = {str(item) for item in raw_sources} if isinstance(raw_sources, list) else set()
        if denominator and consumed - denominator:
            fabricated.append(
                f"{feature_id}: consumed_source_refs not in work-order "
                f"must_read.android_source_refs: {sorted(consumed - denominator)[:4]}")

    probe_failures: list[str] = []
    probe_binding = work_order.get("semantic_probe") if isinstance(work_order, dict) else None
    probe_status = "DORMANT"
    if isinstance(probe_binding, dict) and probe_binding.get("expected_sha256"):
        probe_path = phase_dir / "harmony-project" / "entry/src/main/ets/probe/DebugSemanticProbe.ets"
        if not probe_path.is_file():
            probe_failures.append(
                "frozen semantic probe missing: harmony-project/entry/src/main/ets/probe/DebugSemanticProbe.ets")
        elif sha256_file(probe_path) != probe_binding.get("expected_sha256"):
            probe_failures.append(
                "semantic probe hash differs from the work-order expected value")
        probe_status = "ENFORCED"

    for detail in missing_receipts:
        errors.append(f"must-read receipt: {detail}")
    for detail in fabricated:
        errors.append(f"must-read receipt: {detail}")
    for detail in probe_failures:
        errors.append(f"semantic probe: {detail}")
    return {
        "status": "PASS" if not (missing_receipts or fabricated or probe_failures) else "FAIL",
        "runtime_features_checked": checked,
        "missing_receipts": missing_receipts,
        "fabricated_receipts": fabricated,
        "probe_status": probe_status,
        "probe_failures": probe_failures,
    }


def recompute_stage4_surface_contract(
    phase_dir: Path,
    denominators: dict[str, Any],
    errors: list[str],
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    """The H thin table must cover every feature and be fully PASS."""
    features = denominators["features"]
    try:
        rows = read_csv_rows(phase_dir / "surface-contract.csv")
    except (ValueError, OSError) as exc:
        errors.append(f"Gate 4 cannot read surface-contract.csv: {exc}")
        rows = []
    by_feature: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows):
        feature_id = str(row.get("feature_id", "")).strip()
        if not feature_id:
            errors.append(f"surface-contract row {index} lacks feature_id")
            continue
        if feature_id in by_feature:
            errors.append(f"surface-contract duplicate feature row {feature_id}")
            continue
        by_feature[feature_id] = row
    problems: list[str] = []
    for feature_id in sorted(features):
        row = by_feature.get(feature_id)
        if row is None:
            problems.append(f"{feature_id}: no surface-contract row")
            continue
        if not stage4_v4_split_semantics(row.get("surfaces", "")):
            problems.append(f"{feature_id}: surface-contract surfaces column is empty")
        if str(row.get("entry_reachable", "")).strip().lower() != "yes":
            problems.append(f"{feature_id}: entry_reachable is not 'yes'")
        if not str(row.get("nav_pattern", "")).strip():
            problems.append(f"{feature_id}: nav_pattern is empty")
        if str(row.get("native_impl_check", "")).strip().upper() != "PASS":
            problems.append(f"{feature_id}: native_impl_check is not PASS")
    for feature_id in sorted(set(by_feature) - set(features)):
        problems.append(f"{feature_id}: surface-contract row outside the frozen feature map")
    for problem in problems:
        errors.append(f"surface-contract: {problem}")
    return {
        "status": "PASS" if not problems else "FAIL",
        "features_covered": len(by_feature),
        "feature_total": len(features),
        "problems": problems,
    }, by_feature


# Rule 6 (visual fidelity) shared constants: transparent hosts carry no UI of
# their own; the rule is conditionally activated by the Phase 2 baseline.
STAGE4_V4_VISUAL_VERDICTS = ("PASS", "VISUAL_GAP", "NO_BASELINE", "NO_DUMP")
STAGE4_V4_TRANSPARENT_KINDS = frozenset({"container", "reusable-component"})


def recompute_stage4_visual_fidelity(
    phase_dir: Path,
    run_dir: Path,
    denominators: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Rule 6 recompute: "UI may differ but not too much".

    Independently re-derives the stage4 verdict (never trusting the report
    self text): dormant (PASS + activated=false) while the Phase 2
    visual-memory baseline is absent; once present, every RUNTIME feature's
    host surface (kind outside the transparent set) must have a PASS row in
    visual-fidelity.csv.  VISUAL_GAP / NO_DUMP / missing rows / unknown
    verdicts fail the gate.
    """
    if not (run_dir / "phase-02-android-inventory" / "visual-memory.json").is_file():
        return {
            "status": "PASS",
            "activated": False,
            "reason": "no Phase 2 visual-memory baseline; rule dormant",
        }
    try:
        rows = read_csv_rows(phase_dir / "visual-fidelity.csv")
    except (ValueError, OSError) as exc:
        errors.append(f"Gate 4 cannot read visual-fidelity.csv: {exc}")
        rows = []
    by_surface: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows):
        surface_id = str(row.get("surface_id", "")).strip()
        verdict = str(row.get("verdict", "")).strip().upper()
        if not surface_id or surface_id in by_surface:
            errors.append(f"visual-fidelity row {index} lacks or duplicates surface_id")
            continue
        if verdict not in STAGE4_V4_VISUAL_VERDICTS:
            errors.append(
                f"visual-fidelity row {index} ({surface_id}) has an unknown verdict "
                f"{row.get('verdict', '')!r}"
            )
            continue
        by_surface[surface_id] = row
    features = denominators["features"]
    problems: list[str] = []
    host_surfaces = 0
    for feature_id in sorted(features):
        if str(features[feature_id].get("verify_mode", "")).upper() != "RUNTIME":
            continue
        raw_surfaces = features[feature_id].get("surfaces")
        for raw in raw_surfaces if isinstance(raw_surfaces, list) else []:
            if not isinstance(raw, dict):
                continue
            if str(raw.get("kind", "")).strip() in STAGE4_V4_TRANSPARENT_KINDS:
                continue
            host_surfaces += 1
            surface_id = str(raw.get("id", "")).strip()
            row = by_surface.get(surface_id)
            if row is None:
                problems.append(f"{feature_id}: host surface {surface_id!r} has no visual-fidelity row")
                continue
            verdict = str(row.get("verdict", "")).strip().upper()
            if verdict in ("VISUAL_GAP", "NO_DUMP"):
                problems.append(
                    f"{feature_id}: surface {surface_id} {verdict} — "
                    f"{(row.get('notes') or '')[:120]}"
                )
    for problem in problems:
        errors.append(f"visual-fidelity: {problem}")
    return {
        "status": "FAIL" if problems else "PASS",
        "activated": True,
        "host_surfaces": host_surfaces,
        "problems": problems,
    }


def recompute_stage4_source_confirm_floor(
    phase_dir: Path,
    denominators: dict[str, Any],
    declarations_by_feature: dict[str, dict[str, str]],
    surfaces_by_feature: dict[str, dict[str, str]],
    build_count: int,
    errors: list[str],
) -> dict[str, Any]:
    """Rule 4 recompute: the four SOURCE_CONFIRM floors per feature."""
    features = denominators["features"]
    project = phase_dir / "harmony-project"
    source_confirm = sorted(
        feature_id for feature_id, entry in features.items()
        if str(entry.get("verify_mode", "")).upper() == "SOURCE_CONFIRM"
    )
    floors = {"implementation_present": 0, "no_placeholder": 0, "source_traceable": 0, "buildable": 0}
    failures: list[dict[str, Any]] = []
    if not source_confirm:
        errors.append("feature map has no SOURCE_CONFIRM features; floor denominator must not be empty")
    for feature_id in source_confirm:
        declaration = declarations_by_feature.get(feature_id, {})
        surface_row = surfaces_by_feature.get(feature_id, {})
        refs: list[str] = []
        for source in (str(declaration.get("source_refs", "")), str(surface_row.get("notes", ""))):
            for item in stage4_v4_split_semantics(source):
                head = item.split(":", 1)[0]
                reference = head if head.endswith(STAGE4_V4_ARKTS_SUFFIX) else (
                    item if item.endswith(STAGE4_V4_ARKTS_SUFFIX) else ""
                )
                if reference and reference not in refs:
                    refs.append(reference)
        present: list[Path] = []
        for reference in refs:
            target = (project / reference).resolve()
            try:
                target.relative_to(project.resolve())
            except ValueError:
                errors.append(
                    f"{feature_id}: source reference escapes harmony-project: {reference!r}"
                )
                continue
            if target.is_file() and target.stat().st_size > 0:
                present.append(target)
        if present:
            floors["implementation_present"] += 1
        else:
            failures.append({
                "feature_id": feature_id, "floor": "implementation_present",
                "detail": f"no non-empty referenced ArkTS source (refs={refs[:5]})",
            })
        stub_findings: list[str] = []
        for target in present:
            if target.suffix == STAGE4_V4_ARKTS_SUFFIX:
                try:
                    text = target.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    stub_findings.append(f"{target}: unreadable ({exc})")
                    continue
                stub_findings.extend(
                    f"{target.relative_to(project).as_posix()}: {finding}"
                    for finding in stage4_v4_stub_scan(text)
                )
        if present and not stub_findings:
            floors["no_placeholder"] += 1
        else:
            failures.append({
                "feature_id": feature_id, "floor": "no_placeholder",
                "detail": "; ".join(stub_findings[:5]) or "no scannable source",
            })
        if surface_row and refs:
            floors["source_traceable"] += 1
        else:
            failures.append({
                "feature_id": feature_id, "floor": "source_traceable",
                "detail": "surface-contract row or implementation record lacks a feature->source reference",
            })
        if build_count > 0:
            floors["buildable"] += 1
        else:
            failures.append({
                "feature_id": feature_id, "floor": "buildable",
                "detail": "no final PASS HBUILD seals the smoke build",
            })
    for failure in failures:
        errors.append(
            f"source-confirm floor failed: {failure['feature_id']} "
            f"({failure['floor']}): {failure['detail']}"
        )
    return {
        "status": "PASS" if not failures and source_confirm else "FAIL",
        "features": len(source_confirm),
        "floors": floors,
        "failures": failures,
    }


def validate_phase4(
    run_dir: Path, scope: dict[str, Any], phase1_facts: dict[str, Any]
) -> tuple[list[str], list[str], list[str], list[str], str | None, str | None]:
    """Independently recheck the sealed Phase 4 result under the stage4-v4 paradigm.

    Gate 4 new rules (single v4 path; the legacy page-acceptance / migration-
    unit / 32-input-face / six-dimension verdict / HREV machinery is gone):

    1. runtime_assertions  - four assertion classes PASS per RUNTIME BC;
    2. data_parity         - semantic read/write set parity + persistence coverage;
    3. platform_deviations - PLATFORM_LIMITATION items need ACCEPTED human decisions,
                             behavioral FAIL never flips;
    4. source_confirm_floor- four minimum floors per SOURCE_CONFIRM feature;
    5. h4env_chain         - frozen environment chain + one PASS HBUILD per H4ENV.

    Plus: surface-contract thin table fully PASS, closure/input-lock hash
    chains tamper-proof, work-order/ledger authority retained.
    """
    errors: list[str] = []
    warnings: list[str] = []
    phase_dir = run_dir / "phase-04-harmony-implementation"
    for relative in STAGE4_V4_REQUIRED_ARTIFACTS:
        candidate = phase_dir / relative
        if not candidate.exists() or candidate.is_symlink():
            errors.append(f"Missing or unsafe Phase 4 artifact: {candidate}")
    try:
        phase_manifest = load_json(phase_dir / "phase-manifest.json")
        input_lock = load_json(phase_dir / "stage-04-input-lock.json")
        stage_report = load_json(phase_dir / "stage-04-gate-report.json")
    except ValueError as exc:
        errors.append(str(exc))
        return errors, warnings, [], [], None, None

    verify_phase4_closure(phase_dir, errors)
    stage_report_path = phase_dir / "stage-04-gate-report.json"
    closed_path = phase_dir / "CLOSED"
    if stage_report_path.is_file() and closed_path.is_file():
        try:
            if closed_path.read_bytes() != (sha256_file(stage_report_path) + "\n").encode("ascii"):
                errors.append("Phase 4 CLOSED marker does not bind the current gate report")
        except OSError as exc:
            errors.append(f"Cannot read Phase 4 CLOSED marker: {exc}")
    if any(path.is_file() and path.suffix.lower() == ".mp4" for path in phase_dir.rglob("*")):
        errors.append("MP4 is prohibited in Phase 4")
    for frozen_name in ("stage-04-input-lock.json", "phase-manifest.json"):
        frozen_path = phase_dir / frozen_name
        if frozen_path.is_file() and frozen_path.stat().st_mode & 0o222:
            errors.append(f"Frozen Phase 4 governance record is writable: {frozen_name}")

    # ---- Work order authority (retained mechanism) ----
    registry_rows = read_csv_rows(run_dir / "controller" / "work-order-registry.csv")
    work_order_id = str(phase_manifest.get("work_order_id") or input_lock.get("work_order_id") or "")
    active_phase4 = [
        row for row in registry_rows
        if row.get("phase") == "4" and row.get("status", "").upper() != "SUPERSEDED"
    ]
    matches = [row for row in registry_rows if row.get("phase") == "4" and row.get("work_order_id") == work_order_id]
    work_order: dict[str, Any] = {}
    work_order_path: Path | None = None
    work_order_sha256: str | None = None
    if not ID_RE.fullmatch(work_order_id):
        errors.append("Phase 4 lacks a safe registered Work-Order-ID")
    if len(active_phase4) != 1 or (active_phase4 and active_phase4[0].get("work_order_id") != work_order_id):
        errors.append("Controller must have exactly one active Phase 4 work order")
    if len(matches) != 1:
        errors.append("Phase 4 work order is not uniquely registered")
    else:
        row = matches[0]
        work_order_path = safe_relative_path(run_dir, row.get("relative_path", ""), "Phase 4 work order", errors)
        if work_order_path and work_order_path.is_file():
            try:
                work_order = load_json(work_order_path)
                work_order_sha256 = sha256_file(work_order_path)
            except ValueError as exc:
                errors.append(str(exc))
        if (
            row.get("relative_path") != f"controller/work-orders/{work_order_id}.json"
            or row.get("status") != "ISSUED"
            or row.get("scope_sha256") != phase1_facts.get("scope_sha256")
            or row.get("issued_by") != scope.get("ownership", {}).get("migration_controller_id")
            or row.get("work_order_sha256") != work_order_sha256
        ):
            errors.append("Registered Phase 4 work order is changed, unauthorized, or bound to another scope")

    phase4_ownership = work_order.get("ownership") if isinstance(work_order.get("ownership"), dict) else {}
    role_values: list[str] = []
    for key in STAGE4_ROLE_KEYS:
        value = phase4_ownership.get(key)
        if not isinstance(value, str) or not ACTOR_RE.fullmatch(value):
            errors.append(f"Phase 4 work order has invalid ownership.{key}")
        else:
            role_values.append(value)
    if len(role_values) != len(STAGE4_ROLE_KEYS) or len(role_values) != len(set(role_values)):
        errors.append("All four frozen Phase 4 actor IDs must be present and distinct")

    upstream_order_path: Path | None = None
    upstream_order: dict[str, Any] = {}
    upstream_relative = str(work_order.get("upstream_phase3_work_order_relative_path", ""))
    if upstream_relative:
        upstream_order_path = safe_relative_path(run_dir, upstream_relative, "upstream Phase 3 work order", errors)
        if upstream_order_path and upstream_order_path.is_file():
            try:
                upstream_order = load_json(upstream_order_path)
            except ValueError as exc:
                errors.append(str(exc))
    else:
        errors.append("Phase 4 work order lacks the upstream Phase 3 work-order path")
    phase3_ownership = upstream_order.get("ownership") if isinstance(upstream_order.get("ownership"), dict) else {}
    prior_actor_ids = actor_ids(scope.get("ownership", {})) | actor_ids(phase3_ownership)
    overlap = sorted(set(role_values) & prior_actor_ids)
    if overlap:
        errors.append(f"Phase 4 actors overlap frozen Phase 1-3 actors: {overlap}")
    if (
        work_order.get("work_order_id") != work_order_id
        or work_order.get("phase") != 4
        or work_order.get("status") != "ISSUED"
        or work_order.get("run_id") != scope.get("run_id")
        or work_order.get("scope_sha256") != phase1_facts.get("scope_sha256")
        or work_order.get("issued_by") != scope.get("ownership", {}).get("migration_controller_id")
        or work_order.get("required_skill") != "harmonyos-feature-implementation"
        or work_order.get("included_features") != scope.get("migration_scope", {}).get("included_features")
        or work_order.get("excluded_features") != scope.get("migration_scope", {}).get("excluded_features")
    ):
        errors.append("Phase 4 work-order identity, scope, or authority is invalid")
    if (
        not upstream_order_path
        or sha256_file(upstream_order_path) != work_order.get("upstream_phase3_work_order_sha256")
        or upstream_order.get("work_order_id") != work_order.get("upstream_phase3_work_order_id")
        or upstream_order.get("phase") != 3
    ):
        errors.append("Phase 4 work order is not bound to the registered Phase 3 work order")
    if (
        phase_manifest.get("work_order_id") != work_order_id
        or input_lock.get("work_order_id") != work_order_id
        or phase_manifest.get("work_order_sha256") != work_order_sha256
        or input_lock.get("work_order_sha256") != work_order_sha256
        or phase_manifest.get("ownership") != phase4_ownership
        or input_lock.get("ownership") != phase4_ownership
        or input_lock.get("locked_by") != phase4_ownership.get("implementation_lead_id")
        or phase_manifest.get("project_id") != scope.get("project_id")
        or phase_manifest.get("run_id") != scope.get("run_id")
        or input_lock.get("run_id") != scope.get("run_id")
    ):
        errors.append("Phase 4 manifest/input lock differs from the controller work order")

    gate_snapshot = safe_relative_path(
        run_dir,
        str(work_order.get("controller_gate3_snapshot_relative_path", "")),
        "controller-owned Gate 3 snapshot",
        errors,
    )
    if (
        not gate_snapshot
        or work_order.get("controller_gate3_snapshot_relative_path")
        != f"controller/work-orders/{work_order_id}.phase-03-gate-report.json"
        or sha256_file(gate_snapshot) != work_order.get("controller_gate3_sha256")
    ):
        errors.append("Controller-owned Gate 3 snapshot differs from the Phase 4 work order")
    else:
        try:
            frozen_gate = load_json(gate_snapshot)
            if (
                frozen_gate.get("phase") != 3
                or frozen_gate.get("verdict") != "PASS"
                or frozen_gate.get("scope_sha256") != phase1_facts.get("scope_sha256")
                or frozen_gate.get("errors")
            ):
                errors.append("Frozen controller Gate 3 snapshot is not a complete PASS")
        except ValueError as exc:
            errors.append(str(exc))

    # ---- Input-lock hash chain (retained tamper-proof mechanism, v4 face set) ----
    raw_inputs = input_lock.get("inputs")
    source_records: dict[Path, dict[str, Any]] = {}
    if not isinstance(raw_inputs, list):
        errors.append("Phase 4 input lock inputs must be an array")
        raw_inputs = []
    for index, record in enumerate(raw_inputs):
        if not isinstance(record, dict):
            errors.append(f"Phase 4 input record {index} is not an object")
            continue
        try:
            if set(record) != {"label", "source_path", "snapshot_path", "sha256", "size"} or not record.get("label"):
                raise ValueError("input record keys or label differ from the contract")
            source_value = Path(str(record.get("source_path", ""))).expanduser()
            snapshot_value = Path(str(record.get("snapshot_path", ""))).expanduser()
            if not source_value.is_absolute() or not snapshot_value.is_absolute():
                raise ValueError("source_path and snapshot_path must be absolute")
            source = source_value.resolve()
            snapshot = snapshot_value.resolve()
            source.relative_to(run_dir)
            snapshot.relative_to((phase_dir / "inputs" / "upstream").resolve())
            if source in source_records:
                raise ValueError("duplicate source path")
            if source_value.is_symlink() or snapshot_value.is_symlink() or not source.is_file() or not snapshot.is_file():
                raise ValueError("source or snapshot is missing/symbolic")
            digest = str(record.get("sha256", ""))
            if (
                not SHA256_RE.fullmatch(digest)
                or sha256_file(source) != digest
                or sha256_file(snapshot) != digest
                or source.stat().st_size != record.get("size")
            ):
                raise ValueError("source/snapshot hash or size differs")
            source_records[source] = record
        except (OSError, ValueError) as exc:
            errors.append(f"Invalid Phase 4 input record {index}: {exc}")

    expected_sources: dict[Path, str] = {}
    scope_path = (run_dir / "controller" / "scope.json").resolve()
    if scope_path.is_file():
        expected_sources[scope_path] = str(phase1_facts.get("scope_sha256"))
    if work_order_path:
        expected_sources[work_order_path.resolve()] = str(work_order_sha256)
    if gate_snapshot:
        expected_sources[gate_snapshot.resolve()] = str(work_order.get("controller_gate3_sha256"))
    if upstream_order_path:
        expected_sources[upstream_order_path.resolve()] = str(work_order.get("upstream_phase3_work_order_sha256"))
    # The v4 denominators must be pinned by hash in the work order inputs and
    # snapshotted into the workspace (recomputed from the canonical run tree).
    for digest_key, relative in STAGE4_V4_FROZEN_INPUTS.items():
        source = run_dir / relative
        digest = str(work_order.get(digest_key, ""))
        if not source.is_file():
            errors.append(f"Phase 4 work order input is missing from the run tree: {digest_key}")
            continue
        if not SHA256_RE.fullmatch(digest) or sha256_file(source) != digest:
            errors.append(f"Phase 4 work order input changed: {digest_key}")
            continue
        expected_sources[source.resolve()] = digest
    if set(source_records) != set(expected_sources):
        errors.append(
            "Phase 4 small-input snapshots differ from the work order; "
            f"missing={sorted(str(path) for path in set(expected_sources) - set(source_records))[:5]}, "
            f"extra={sorted(str(path) for path in set(source_records) - set(expected_sources))[:5]}"
        )
    for source, digest in expected_sources.items():
        record = source_records.get(source)
        if record and record.get("sha256") != digest:
            errors.append(f"Phase 4 input snapshot binds another digest: {source}")

    input_lock_path = phase_dir / "stage-04-input-lock.json"
    input_lock_sha256 = sha256_file(input_lock_path) if input_lock_path.is_file() else None
    if phase_manifest.get("input_lock_sha256") != input_lock_sha256:
        errors.append("Phase 4 manifest references another input lock")

    # ---- Rule 5a: H4ENV environment chain (pixel capture stays optional) ----
    env_rows = read_csv_rows(phase_dir / "environments" / "h4env-registry.csv")
    env_index = index_unique_rows(env_rows, "h4env_id", "H4ENV registry", errors)
    required_h4env_value = input_lock.get("required_h4env_ids")
    required_h4env_ids = set(required_h4env_value if isinstance(required_h4env_value, list) else [])
    if not required_h4env_ids or set(env_index) != required_h4env_ids:
        errors.append("Phase 4 H4ENV registry differs from the frozen required H4ENV set")
    environments: dict[str, dict[str, Any]] = {}
    for h4env_id in sorted(env_index):
        env_path = phase_dir / "environments" / h4env_id / "phase4-environment.json"
        try:
            environment = load_json(env_path)
            environments[h4env_id] = environment
            for key in ("source_android_env_id", "base_henv_id", "device_id"):
                if not str(environment.get(key, "")):
                    errors.append(f"{h4env_id}: H4ENV environment lacks {key}")
        except (ValueError, OSError) as exc:
            errors.append(f"{h4env_id}: {exc}")
    locked_h4envs = input_lock.get("h4envs")
    if not isinstance(locked_h4envs, list):
        errors.append("Phase 4 input lock h4envs must be an array")
        locked_h4envs = []
    locked_ids: set[str] = set()
    for record in locked_h4envs:
        if not isinstance(record, dict):
            errors.append("Phase 4 h4envs contains a non-object record")
            continue
        h4env_id = str(record.get("h4env_id", ""))
        relative = f"environments/{h4env_id}/phase4-environment.json"
        env_path = phase_dir / relative
        if (
            h4env_id in locked_ids
            or h4env_id not in environments
            or record.get("relative_path") != relative
            or not env_path.is_file()
            or record.get("sha256") != sha256_file(env_path)
        ):
            errors.append(f"Phase 4 input-lock H4ENV record differs: {h4env_id!r}")
            continue
        locked_ids.add(h4env_id)
    if set(locked_ids) != set(environments):
        errors.append("Phase 4 input-lock H4ENV records do not exactly cover frozen environments")

    # ---- Rule 5b: final HBUILD chain (one PASS build per required H4ENV) ----
    project = phase_dir / "harmony-project"
    source_snapshot_sha256, _ = phase4_project_snapshot(project, errors)
    build_ids_value = stage_report.get("build_ids")
    build_ids = build_ids_value if isinstance(build_ids_value, list) else []
    if len(build_ids) != len(set(build_ids)) or any(
        not isinstance(item, str) or not ID_RE.fullmatch(item) for item in build_ids
    ):
        errors.append("Phase 4 report has unsafe or duplicate final HBUILD-IDs")
        build_ids = []
    build_by_env: dict[str, str] = {}
    artifact_hashes: list[str] = []
    for build_id in sorted(build_ids):
        build_dir = phase_dir / "builds" / build_id
        verify_sealed_package(build_dir, build_id, "PASS", f"HBUILD {build_id}", errors)
        try:
            metadata = load_json(build_dir / "metadata.json")
            artifact_manifest = load_json(build_dir / "artifact-manifest.json")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        h4env_id = str(metadata.get("h4env_id", ""))
        environment = environments.get(h4env_id, {})
        if h4env_id in build_by_env:
            errors.append(f"More than one final HBUILD is selected for {h4env_id}")
        build_by_env[h4env_id] = build_id
        env_record = phase_dir / "environments" / h4env_id / "phase4-environment.json"
        env_record_sha = sha256_file(env_record) if env_record.is_file() else None
        if (
            metadata.get("hbuild_id") != build_id
            or metadata.get("status") != "PASS"
            or metadata.get("executed_by") != phase4_ownership.get("verification_executor_id")
            or metadata.get("input_lock_sha256") != input_lock_sha256
            or metadata.get("source_snapshot_sha256") != source_snapshot_sha256
            or h4env_id not in environments
            or not metadata.get("created_at")
            or env_record_sha is None
            or metadata.get("environment_sha256") != env_record_sha
        ):
            errors.append(f"{build_id}: build metadata, executor, or snapshot is invalid")
        if environment:
            validate_phase4_commands(
                build_dir,
                metadata.get("commands"),
                environment,
                ["TOOLCHAIN", "CLEAN_BUILD", "BUNDLE_CHECK", "SIGNING_CHECK"],
                f"HBUILD {build_id}",
                errors,
            )
        artifacts = artifact_manifest.get("artifacts") if isinstance(artifact_manifest.get("artifacts"), list) else []
        primary = metadata.get("primary_artifact") if isinstance(metadata.get("primary_artifact"), dict) else {}
        if metadata.get("artifact_count") != 1 or len(artifacts) != 1 or primary != artifacts[0]:
            errors.append(f"{build_id}: artifact manifest/count/primary artifact differs")
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                errors.append(f"{build_id}: artifact entry is not an object")
                continue
            sealed = safe_relative_path(
                build_dir, str(artifact.get("sealed_relative_path", "")), f"{build_id} artifact", errors
            )
            digest = str(artifact.get("sha256", ""))
            if (
                not sealed
                or not sealed.is_file()
                or not SHA256_RE.fullmatch(digest)
                or sha256_file(sealed) != digest
                or sealed.stat().st_size != artifact.get("size")
            ):
                errors.append(f"{build_id}: sealed HAP differs from the manifest")
            else:
                artifact_hashes.append(digest)
    if set(build_by_env) != set(environments) or not environments:
        errors.append("Final HBUILD set must contain exactly one PASS build per required H4ENV")
    h4env_rule = {
        "status": (
            "PASS"
            if set(build_by_env) == set(environments)
            and environments
            and not any("H4ENV" in message for message in errors)
            else "FAIL"
        ),
        "environments": sorted(environments),
        "required_h4env_ids": sorted(required_h4env_ids),
        "final_builds": sorted(build_ids),
    }

    # ---- Rules 1+3: runtime assertions with the PLATFORM_DEVIATION queue ----
    denominators = stage4_v4_load_denominators(run_dir, errors)
    replay_rows = stage4_v4_replay_rows(phase_dir, errors)
    decisions = stage4_v4_decisions(phase_dir, errors)
    runtime_rule, deviations, _manual = recompute_stage4_runtime_assertions(
        replay_rows, decisions, denominators, errors
    )
    deviation_rule = recompute_stage4_deviation_rule(deviations, errors)

    # ---- Rule 2: semantic data parity ----
    data_rule = recompute_stage4_data_parity(phase_dir, denominators, errors)

    # ---- Surface-contract thin table must be fully PASS ----
    surface_rule, surfaces_by_feature = recompute_stage4_surface_contract(
        phase_dir, denominators, errors
    )
    try:
        declaration_rows = read_csv_rows(phase_dir / "implementation-declarations.csv")
    except (ValueError, OSError):
        declaration_rows = []
    declarations_by_feature: dict[str, dict[str, str]] = {}
    for row in declaration_rows:
        feature_id = str(row.get("feature_id", "")).strip()
        if feature_id and feature_id not in declarations_by_feature:
            declarations_by_feature[feature_id] = row

    # ---- Rule 4: SOURCE_CONFIRM minimum floors ----
    source_rule = recompute_stage4_source_confirm_floor(
        phase_dir, denominators, declarations_by_feature, surfaces_by_feature,
        len(build_by_env), errors,
    )

    # ---- Rule 6: visual fidelity (dormant until the P2 baseline exists) ----
    visual_rule = recompute_stage4_visual_fidelity(
        phase_dir, run_dir, denominators, errors,
    )

    # ---- Rule 7 (batch 2 #85): MUST_READ receipts + frozen probe hash ----
    must_read_rule = recompute_stage4_must_read_receipt(
        phase_dir, denominators, work_order, declarations_by_feature, errors,
    )

    rules = {
        "runtime_assertions": runtime_rule,
        "data_parity": data_rule,
        "platform_deviations": deviation_rule,
        "source_confirm_floor": source_rule,
        "h4env_chain": h4env_rule,
        "visual_fidelity": visual_rule,
        "must_read_receipt": must_read_rule,
    }

    # ---- Attempt ledger: defensive hash-chain check when the chain exists ----
    attempt_local = phase_dir / "attempt-ledger.csv"
    if attempt_local.is_file():
        try:
            local_attempt_rows = read_csv_rows(attempt_local)
            controller_attempt_rows = read_csv_rows(run_dir / "controller" / "phase4-attempt-ledger.csv")
            if local_attempt_rows != controller_attempt_rows:
                errors.append("Phase 4 local attempt ledger differs from the controller anchor")
            validate_phase4_attempt_chain(controller_attempt_rows, errors)
        except (ValueError, OSError) as exc:
            errors.append(f"Phase 4 attempt ledger is unreadable: {exc}")

    # ---- Rework double ledger (retained mechanism) ----
    local_rework = read_csv_rows(phase_dir / "rework-tickets.csv") if (phase_dir / "rework-tickets.csv").is_file() else []
    controller_rework = [
        row for row in read_csv_rows(run_dir / "controller" / "rework-log.csv")
        if row.get("phase") == "4"
    ]
    local_ids = [row.get("ticket_id", "") for row in local_rework]
    controller_ids = [row.get("rework_id", "") for row in controller_rework]
    if (
        len(local_ids) != len(set(local_ids))
        or len(controller_ids) != len(set(controller_ids))
        or set(local_ids) != set(controller_ids)
    ):
        errors.append("Phase 4 rework ledger and controller mirror contain different or duplicate Ticket-IDs")
    allowed_responsible = prior_actor_ids | set(role_values)
    for local in local_rework:
        ticket_id = str(local.get("ticket_id", ""))
        if not ID_RE.fullmatch(ticket_id):
            errors.append(f"Phase 4 rework ticket identity is invalid: {ticket_id!r}")
            continue
        if str(local.get("responsible_agent", "")) not in allowed_responsible:
            errors.append(f"Phase 4 rework responsible agent is not frozen: {ticket_id}")
    if any(row.get("status", "").upper() != "CLOSED" for row in controller_rework):
        errors.append("Controller has open Phase 4 rework")

    # ---- Stage report consistency: the recomputed rules, never the self text ----
    report_rules = stage_report.get("rules") if isinstance(stage_report.get("rules"), dict) else {}
    for rule_key, recomputed in rules.items():
        reported = report_rules.get(rule_key)
        reported_status = reported.get("status") if isinstance(reported, dict) else None
        if reported_status != recomputed.get("status"):
            errors.append(
                f"Phase 4 gate report rule {rule_key} self-reports {reported_status!r} "
                f"but the controller recomputes {recomputed.get('status')!r}"
            )
    reported_surface = stage_report.get("surface_contract")
    reported_surface_status = (
        reported_surface.get("status") if isinstance(reported_surface, dict) else None
    )
    if reported_surface_status != surface_rule.get("status"):
        errors.append("Phase 4 gate report surface_contract status differs from the recompute")
    report_artifacts = stage_report.get("artifact_hashes")
    if not isinstance(report_artifacts, list) or sorted(report_artifacts) != sorted(artifact_hashes):
        errors.append("Phase 4 report artifact hashes differ from final HBUILD packages")
    if (
        stage_report.get("schema_version") != "stage4-v4"
        or stage_report.get("phase") != 4
        or stage_report.get("run_id") != scope.get("run_id")
        or stage_report.get("verdict") != "PASS"
        or stage_report.get("final_verdict") != "PASS"
        or stage_report.get("implementation_chain_closed") is not True
        or stage_report.get("reviewer_role") != "parity-acceptance-agent"
        or stage_report.get("reviewer_id") != phase4_ownership.get("parity_acceptance_agent_id")
        or stage_report.get("work_order_id") != work_order_id
        or stage_report.get("input_lock_sha256") != input_lock_sha256
        or stage_report.get("source_snapshot_sha256") != source_snapshot_sha256
        or stage_report.get("build_ids") != sorted(build_ids)
        or stage_report.get("errors") != []
    ):
        errors.append("Phase 4 final report identity, reviewer, snapshot, or verdict is invalid")

    # ---- Task ledger (retained mechanism) ----
    ledger_rows = read_csv_rows(run_dir / "controller" / "task-ledger.csv")
    phase3_tasks = [row for row in ledger_rows if row.get("phase") == "3"]
    phase4_tasks = [row for row in ledger_rows if row.get("phase") == "4"]
    if (
        len(phase3_tasks) != 1
        or phase3_tasks[0].get("status") != "PASS"
        or phase3_tasks[0].get("owner") != phase3_ownership.get("architecture_lead_id")
    ):
        errors.append("Controller task ledger does not retain the frozen Phase 3 PASS")
    if (
        len(phase4_tasks) != 1
        or phase4_tasks[0].get("status") not in {"IN_PROGRESS", "PASS"}
        or phase4_tasks[0].get("owner") != phase4_ownership.get("implementation_lead_id")
    ):
        errors.append("Controller task ledger does not have the assigned Phase 4 task")

    # ---- v4 report facts (same-unit BC rate; intent_pass_rate mixing retired) ----
    runtime_total = int(runtime_rule.get("runtime_bcs") or 0)
    runtime_pass = int(runtime_rule.get("runtime_bcs_pass") or 0)
    if runtime_total > 0:
        phase1_facts["runtime_bc_pass_rate"] = runtime_pass / runtime_total
        phase1_facts["runtime_bc_pass_rate_note"] = (
            f"replay PASS {runtime_pass} / RUNTIME behavior contracts {runtime_total}"
        )
    else:
        phase1_facts["runtime_bc_pass_rate"] = None
        phase1_facts["runtime_bc_pass_rate_note"] = (
            "no RUNTIME behavior contracts in the frozen feature map"
        )
    phase1_facts["persistence_consistency"] = (
        "MEASURED_PASS" if data_rule.get("status") == "PASS" else "MEASURED_FAIL"
    )
    phase1_facts["persistence_consistency_note"] = (
        f"semantic persistence coverage gaps: {len(data_rule.get('persistence_gaps', []))}"
    )
    phase1_facts["native_review_status"] = "PENDING"
    phase1_facts["native_review_status_note"] = (
        "awaiting the single post-Gate-4 human native-feel acceptance"
    )
    phase1_facts["platform_deviation_summary"] = {
        "total": deviation_rule.get("total"),
        "accepted": deviation_rule.get("accepted"),
        "pending_or_rejected": deviation_rule.get("pending_or_rejected"),
    }

    replay_evidence_refs = sorted({
        str(row.get("evidence_ref", "")) for row in replay_rows if str(row.get("evidence_ref", "")).strip()
    })
    return (
        errors,
        warnings,
        sorted(build_ids),
        replay_evidence_refs,
        str(phase4_ownership.get("implementation_lead_id") or "") or None,
        work_order_id if ID_RE.fullmatch(work_order_id) else None,
    )


def phase56_closure_excluded(relative: PurePosixPath, phase: int) -> bool:
    exact = STAGE5_CLOSURE_EXACT_EXCLUDES if phase == 5 else STAGE6_CLOSURE_EXACT_EXCLUDES
    if relative.as_posix() in exact or any(part in PHASE56_TRANSIENT_PARTS for part in relative.parts):
        return True
    if relative.suffix in {".tmp", ".pyc"} or relative.name.endswith(".lock"):
        return True
    return bool(
        phase == 5
        and relative.parts
        and relative.parts[0] == "harmony-project"
        and any(part in STAGE4_PROJECT_EXCLUDED_PARTS for part in relative.parts[1:])
    )


def verify_phase56_closure(workspace: Path, phase: int, errors: list[str]) -> dict[str, str]:
    manifest_name = f"stage-0{phase}-closure-manifest.sha256"
    manifest = workspace / manifest_name
    if not manifest.is_file() or manifest.is_symlink():
        errors.append(f"Phase {phase} closure manifest is missing or unsafe")
        return {}
    expected = parse_sha256_manifest(manifest, f"Phase {phase} closure manifest", errors)
    actual: dict[str, Path] = {}
    for path in workspace.rglob("*"):
        relative = PurePosixPath(path.relative_to(workspace).as_posix())
        if phase56_closure_excluded(relative, phase):
            continue
        if path.is_symlink():
            errors.append(f"Symbolic links are prohibited in Phase {phase} closure: {path}")
            continue
        if path.is_file():
            if path.suffix.lower() == ".mp4":
                errors.append(f"MP4 is prohibited in formal Phase {phase} evidence: {relative}")
            actual[relative.as_posix()] = path
    if set(expected) != set(actual):
        errors.append(
            f"Phase {phase} closure file set changed; "
            f"missing={sorted(set(expected) - set(actual))[:5]}, "
            f"extra={sorted(set(actual) - set(expected))[:5]}"
        )
    for relative in sorted(set(expected) & set(actual)):
        if sha256_file(actual[relative]) != expected[relative]:
            errors.append(f"Phase {phase} closure hash mismatch: {relative}")
    return expected


def verify_closed_marker(workspace: Path, phase: int, errors: list[str]) -> None:
    report = workspace / f"stage-0{phase}-gate-report.json"
    marker = workspace / "CLOSED"
    if not report.is_file() or report.is_symlink() or not marker.is_file() or marker.is_symlink():
        errors.append(f"Phase {phase} final report or CLOSED marker is missing/unsafe")
        return
    try:
        if marker.read_text(encoding="utf-8").strip() != sha256_file(report):
            errors.append(f"Phase {phase} CLOSED marker does not bind its final report")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"Cannot read Phase {phase} CLOSED marker: {exc}")


def json_string_array(value: str, label: str, errors: list[str], *, allow_empty: bool = True) -> list[str]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        errors.append(f"{label} is not a JSON string array")
        return []
    if (
        not isinstance(parsed, list) or (not allow_empty and not parsed)
        or any(not isinstance(item, str) or not item for item in parsed)
        or parsed != sorted(set(parsed))
    ):
        errors.append(f"{label} must be a sorted unique JSON string array")
        return []
    return parsed


def phase56_prior_actor_ids(
    run_dir: Path, scope: dict[str, Any], registry_rows: list[dict[str, str]], phase: int,
    errors: list[str],
) -> set[str]:
    actors = actor_ids(scope.get("ownership") if isinstance(scope.get("ownership"), dict) else {})
    for row in registry_rows:
        try:
            row_phase = int(str(row.get("phase", "0")))
        except ValueError:
            continue
        if row_phase >= phase or row.get("status", "").upper() == "SUPERSEDED":
            continue
        path = safe_relative_path(run_dir, row.get("relative_path", ""), f"Phase {row_phase} work order", errors)
        if path and path.is_file():
            try:
                order = load_json(path)
                ownership = order.get("ownership") if isinstance(order.get("ownership"), dict) else {}
                actors.update(actor_ids(ownership))
            except ValueError as exc:
                errors.append(str(exc))
    if phase > 4:
        feature_root = run_dir / "phase-04-harmony-implementation"
        for row in read_csv_rows(feature_root / "feature-work-order-registry.csv"):
            if row.get("status", "").upper() == "SUPERSEDED":
                continue
            relative = row.get("relative_path") or row.get("work_order_relative_path") or ""
            path = safe_relative_path(feature_root, relative, "Phase 4 feature work order", errors)
            if path and path.is_file():
                try:
                    order = load_json(path)
                    ownership = order.get("ownership") if isinstance(order.get("ownership"), dict) else {}
                    actors.update(actor_ids(ownership))
                except ValueError as exc:
                    errors.append(str(exc))
    return actors


def validate_phase56_work_order(
    run_dir: Path, scope: dict[str, Any], phase1_facts: dict[str, Any], phase: int,
    manifest: dict[str, Any], input_lock: dict[str, Any], role_keys: tuple[str, ...],
    expected_skill: str, errors: list[str],
) -> tuple[dict[str, Any], dict[str, Any], str | None, str | None]:
    registry_rows = read_csv_rows(run_dir / "controller" / "work-order-registry.csv")
    work_order_id = str(manifest.get("work_order_id") or input_lock.get("work_order_id") or "")
    if not work_order_id and isinstance(input_lock.get("work_order"), dict):
        work_order_id = str(input_lock["work_order"].get("work_order_id", ""))
    active = [
        row for row in registry_rows
        if row.get("phase") == str(phase) and row.get("status", "").upper() != "SUPERSEDED"
    ]
    matches = [row for row in active if row.get("work_order_id") == work_order_id]
    work_order: dict[str, Any] = {}
    work_order_sha256: str | None = None
    if not ID_RE.fullmatch(work_order_id) or len(active) != 1 or len(matches) != 1:
        errors.append(f"Controller must have exactly one active registered Phase {phase} work order")
        return work_order, {}, None, None
    registry = matches[0]
    path = safe_relative_path(run_dir, registry.get("relative_path", ""), f"Phase {phase} work order", errors)
    if path and path.is_file():
        try:
            work_order = load_json(path)
            work_order_sha256 = sha256_file(path)
        except ValueError as exc:
            errors.append(str(exc))
    if (
        registry.get("status") != "ISSUED"
        or registry.get("scope_sha256") != phase1_facts.get("scope_sha256")
        or registry.get("issued_by") != scope.get("ownership", {}).get("migration_controller_id")
        or registry.get("work_order_sha256") != work_order_sha256
    ):
        errors.append(f"Registered Phase {phase} work order is changed or unauthorized")
    ownership = work_order.get("ownership") if isinstance(work_order.get("ownership"), dict) else {}
    values = [ownership.get(key) for key in role_keys]
    prior = phase56_prior_actor_ids(run_dir, scope, registry_rows, phase, errors)
    if (
        work_order.get("schema_version") != "1.0"
        or work_order.get("work_order_id") != work_order_id
        or work_order.get("run_id") != scope.get("run_id")
        or work_order.get("phase") != phase
        or work_order.get("status") != "ISSUED"
        or work_order.get("issued_by") != scope.get("ownership", {}).get("migration_controller_id")
        or work_order.get("required_skill") != expected_skill
        or set(ownership) != set(role_keys)
        or any(not isinstance(value, str) or not ACTOR_RE.fullmatch(value) for value in values)
        or len(values) != len(set(values))
        or set(str(value) for value in values) & prior
        or work_order.get("forbidden_prior_actor_ids") != sorted(prior)
    ):
        errors.append(f"Phase {phase} work order identity, role separation, or authority is invalid")
    return work_order, ownership, work_order_sha256, work_order_id


def validate_frozen_file_record(
    run_dir: Path, record: Any, label: str, errors: list[str], *, require_live: bool = True,
) -> tuple[Path | None, Path | None]:
    if not isinstance(record, dict):
        errors.append(f"{label} record is not an object")
        return None, None
    live = (
        safe_relative_path(run_dir, str(record.get("relative_path", "")), f"{label} live input", errors)
        if require_live else None
    )
    snapshot = safe_relative_path(
        run_dir, str(record.get("snapshot_relative_path", "")), f"{label} controller snapshot", errors
    )
    digest = str(record.get("sha256", ""))
    if (
        not SHA256_RE.fullmatch(digest)
        or (require_live and (not live or not live.is_file() or sha256_file(live) != digest))
        or not snapshot or not snapshot.is_file() or sha256_file(snapshot) != digest
        or (require_live and live and snapshot and live.read_bytes() != snapshot.read_bytes())
    ):
        errors.append(f"{label} live bytes, controller snapshot, or declared hash differ")
    return live, snapshot


def verify_sealed_tree(directory: Path, package_id: str, label: str, errors: list[str]) -> dict[str, str]:
    expected = verify_exact_manifest(
        directory, "manifest.sha256", {"manifest.sha256", "COMMITTED"}, label, errors
    )
    marker = directory / "COMMITTED"
    manifest = directory / "manifest.sha256"
    if not marker.is_file() or marker.is_symlink() or not manifest.is_file():
        errors.append(f"{label} is not committed")
    else:
        try:
            value = marker.read_text(encoding="utf-8").strip()
            if not value.startswith(f"{package_id} ") or f"manifest_sha256={sha256_file(manifest)}" not in value:
                errors.append(f"{label} COMMITTED marker does not bind its manifest")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"Cannot read {label} COMMITTED marker: {exc}")
    if directory.exists():
        for path in (directory, *directory.rglob("*")):
            if path.stat().st_mode & 0o222:
                errors.append(f"{label} contains a writable sealed path: {path}")
                break
    return expected


def validate_phase5(
    run_dir: Path, scope: dict[str, Any], phase1_facts: dict[str, Any]
) -> tuple[list[str], list[str], str | None, str | None, str | None]:
    """Independently recheck the closed Phase 5 candidate and whole-app regression.

    DEPRECATED: retained for legacy run revalidation only
    """
    errors: list[str] = []
    warnings: list[str] = []
    phase_dir = run_dir / "phase-05-harmony-regression"
    required = (
        "stage-05-input-lock.json", "phase-manifest.json", "release-candidate-registry.csv",
        "flow-edge-registry.csv", "lifecycle-invariants.csv", "no-cross-flow.csv",
        "scenario-registry.csv", "scenario-acceptance.csv", "evidence-index.csv",
        "rework-tickets.csv", "inputs", "environments/h5env-registry.csv", "harmony-project",
        "release-candidates", "scenarios", "evidence", "reviews", "stage-05-gate-report.json",
        "stage-05-closure-manifest.sha256", "CLOSED",
    )
    for relative in required:
        candidate = phase_dir / relative
        if not candidate.exists() or candidate.is_symlink():
            errors.append(f"Missing or unsafe Phase 5 artifact: {candidate}")
    try:
        input_lock = load_json(phase_dir / "stage-05-input-lock.json")
        manifest = load_json(phase_dir / "phase-manifest.json")
        report = load_json(phase_dir / "stage-05-gate-report.json")
    except ValueError as exc:
        errors.append(str(exc))
        return errors, warnings, None, None, None

    verify_phase56_closure(phase_dir, 5, errors)
    verify_closed_marker(phase_dir, 5, errors)
    work_order, ownership, work_order_sha256, work_order_id = validate_phase56_work_order(
        run_dir, scope, phase1_facts, 5, manifest, input_lock, STAGE5_ROLE_KEYS,
        "harmonyos-system-regression", errors,
    )
    expected_permissions = {
        "source_modification_allowed": False,
        "new_feature_allowed": False,
        "mp4_allowed": False,
        "external_publish_allowed": False,
    }
    if work_order.get("permissions") != expected_permissions:
        errors.append("Phase 5 work order permissions do not prohibit source/new-feature/MP4/publishing")
    if (
        manifest.get("schema_version") != "1.0"
        or manifest.get("phase") != 5
        or manifest.get("run_id") != scope.get("run_id")
        or manifest.get("status") != "IN_PROGRESS"
        or manifest.get("work_order_id") != work_order_id
        or manifest.get("work_order_sha256") != work_order_sha256
        or manifest.get("ownership") != ownership
        or manifest.get("created_by") != ownership.get("regression_lead_id")
        or input_lock.get("schema_version") != "1.0"
        or input_lock.get("phase") != 5
        or input_lock.get("run_id") != scope.get("run_id")
        or input_lock.get("work_order_id") != work_order_id
        or input_lock.get("work_order_sha256") != work_order_sha256
        or input_lock.get("ownership") != ownership
        or input_lock.get("created_by") != ownership.get("regression_lead_id")
        or manifest.get("input_lock_sha256") != sha256_file(phase_dir / "stage-05-input-lock.json")
    ):
        errors.append("Phase 5 manifest/input lock identity, hashes, or ownership differ")

    order_inputs = work_order.get("inputs") if isinstance(work_order.get("inputs"), dict) else {}
    expected_input_keys = {
        "scope", "gate4_report", "phase4_work_order", "phase4_input_lock", "phase4_manifest",
        "phase4_report", "phase4_closure_manifest", "phase4_closed", "phase4_project",
        "phase4_final_builds",
    }
    if set(order_inputs) != expected_input_keys:
        errors.append("Phase 5 work order input key set differs")
    for key in sorted(expected_input_keys - {"phase4_project", "phase4_final_builds"}):
        validate_frozen_file_record(
            run_dir, order_inputs.get(key), f"Phase 5 {key}", errors,
            require_live=(key != "gate4_report"),
        )
    gate4_record = order_inputs.get("gate4_report")
    if isinstance(gate4_record, dict):
        gate4_snapshot = safe_relative_path(
            run_dir, str(gate4_record.get("snapshot_relative_path", "")), "Gate 4 snapshot", errors
        )
        if gate4_snapshot and gate4_snapshot.is_file():
            try:
                gate4 = load_json(gate4_snapshot)
                if gate4.get("phase") != 4 or gate4.get("verdict") != "PASS" or gate4.get("errors"):
                    errors.append("Phase 5 work order Gate 4 snapshot is not PASS")
            except ValueError as exc:
                errors.append(str(exc))

    project_record = order_inputs.get("phase4_project")
    project = phase_dir / "harmony-project"
    source_snapshot_sha256, source_entries = phase4_project_snapshot(project, errors)
    if (
        not isinstance(project_record, dict)
        or project_record.get("relative_path") != "phase-04-harmony-implementation/harmony-project"
        or project_record.get("snapshot_sha256") != source_snapshot_sha256
        or project_record.get("entry_count") != len(source_entries)
        or input_lock.get("phase4_source_snapshot_sha256") != source_snapshot_sha256
        or input_lock.get("phase4_source_entry_count") != len(source_entries)
    ):
        errors.append("Phase 5 project no longer equals the Gate 4 source snapshot")

    final_builds = order_inputs.get("phase4_final_builds")
    if not isinstance(final_builds, list) or not final_builds:
        errors.append("Phase 5 work order has no frozen final Phase 4 builds")
        final_builds = []
    seen_h4envs: set[str] = set()
    for build in final_builds:
        if not isinstance(build, dict):
            errors.append("Phase 5 final build record is not an object")
            continue
        h4env_id = str(build.get("h4env_id", ""))
        hbuild_id = str(build.get("hbuild_id", ""))
        if not ID_RE.fullmatch(h4env_id) or not ID_RE.fullmatch(hbuild_id) or h4env_id in seen_h4envs:
            errors.append(f"Phase 5 has an unsafe/duplicate frozen Phase 4 build: {hbuild_id}")
            continue
        metadata_path = safe_relative_path(
            run_dir, str(build.get("build_record_relative_path", "")), f"{hbuild_id} metadata", errors
        )
        if (
            not metadata_path or not metadata_path.is_file()
            or build.get("build_record_sha256") != sha256_file(metadata_path)
            or build.get("source_snapshot_sha256") != source_snapshot_sha256
        ):
            errors.append(f"Phase 5 frozen Phase 4 build metadata differs: {hbuild_id}")
        artifacts = build.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            errors.append(f"Phase 5 frozen Phase 4 build has no artifacts: {hbuild_id}")
        else:
            for item in artifacts:
                if not isinstance(item, dict):
                    errors.append(f"Invalid Phase 4 artifact record in {hbuild_id}")
                    continue
                path = safe_relative_path(
                    run_dir, str(item.get("relative_path", "")), f"{hbuild_id} artifact", errors
                )
                if (
                    not path or not path.is_file() or not SHA256_RE.fullmatch(str(item.get("sha256", "")))
                    or sha256_file(path) != item.get("sha256") or path.stat().st_size != item.get("size")
                ):
                    errors.append(f"Phase 5 frozen Phase 4 artifact bytes differ: {hbuild_id}")
        seen_h4envs.add(h4env_id)

    profile = work_order.get("release_profile") if isinstance(work_order.get("release_profile"), dict) else {}
    profile_snapshot = safe_relative_path(
        run_dir, str(profile.get("snapshot_relative_path", "")), "release profile snapshot", errors
    )
    raw_profile: dict[str, Any] = {}
    if profile_snapshot and profile_snapshot.is_file():
        try:
            raw_profile = load_json(profile_snapshot)
        except ValueError as exc:
            errors.append(str(exc))
    profile_keys = {
        "profile_id", "bundle_id", "version_name", "version_code", "target_api", "device_types",
        "build_mode", "signing_mode", "signing_identity", "primary_artifact_path",
        "candidate_artifact_paths",
    }
    if (
        not raw_profile or set(raw_profile) != profile_keys
        or profile.get("sha256") != (sha256_file(profile_snapshot) if profile_snapshot and profile_snapshot.is_file() else None)
        or any(profile.get(key) != raw_profile.get(key) for key in profile_keys)
    ):
        errors.append("Phase 5 release profile snapshot/public fields differ")
    authorization = work_order.get("signing_authorization")
    needs_auth = raw_profile.get("signing_mode") in {"LOCAL_PRODUCTION", "REMOTE"}
    if not isinstance(authorization, dict) or authorization.get("required") is not needs_auth or authorization.get("present") is not needs_auth:
        errors.append("Phase 5 signing authorization does not match signing mode")
    elif needs_auth:
        validate_frozen_file_record(run_dir, authorization, "Phase 5 signing authorization", errors, require_live=False)

    required_h5envs = work_order.get("required_h5env_ids")
    order_h5envs = work_order.get("h5envs")
    if (
        not isinstance(required_h5envs, list) or not required_h5envs
        or required_h5envs != sorted(set(required_h5envs)) or not isinstance(order_h5envs, list)
    ):
        errors.append("Phase 5 required H5ENV set is invalid")
        required_h5envs, order_h5envs = [], []
    registry_h5 = index_unique_rows(
        read_csv_rows(phase_dir / "environments" / "h5env-registry.csv"),
        "h5env_id", "Phase 5 H5ENV registry", errors,
    )
    order_h5_by_id = {
        str(item.get("h5env_id", "")): item for item in order_h5envs if isinstance(item, dict)
    }
    if set(registry_h5) != set(required_h5envs) or set(order_h5_by_id) != set(required_h5envs):
        errors.append("Phase 5 H5ENV registry/work order coverage differs")
    for h5env_id in required_h5envs:
        record = order_h5_by_id.get(h5env_id, {})
        snapshot = safe_relative_path(
            run_dir, str(record.get("snapshot_relative_path", "")), f"{h5env_id} controller snapshot", errors
        )
        row = registry_h5.get(h5env_id, {})
        local = safe_relative_path(phase_dir, row.get("relative_path", ""), f"{h5env_id} local environment", errors)
        if (
            record.get("required") is not True or row.get("required") != "true"
            or row.get("status") != "FROZEN" or row.get("frozen_by") != ownership.get("regression_lead_id")
            or row.get("base_h4env_id") != record.get("base_h4env_id")
            or not snapshot or not local or not snapshot.is_file() or not local.is_file()
            or record.get("sha256") != sha256_file(snapshot)
            or row.get("environment_sha256") != sha256_file(local)
            or snapshot.read_bytes() != local.read_bytes()
        ):
            errors.append(f"Phase 5 H5ENV snapshot/registry differs: {h5env_id}")

    candidate_rows = read_csv_rows(phase_dir / "release-candidate-registry.csv")
    active_candidates = [row for row in candidate_rows if row.get("status") == "SEALED"]
    if len(candidate_rows) != 1 or len(active_candidates) != 1:
        errors.append("Phase 5 must contain exactly one sealed Release-Candidate-ID")
        candidate_row: dict[str, str] = {}
    else:
        candidate_row = active_candidates[0]
    release_candidate_id = str(candidate_row.get("release_candidate_id", ""))
    candidate_record_path = safe_relative_path(
        phase_dir, candidate_row.get("relative_path", ""), "release candidate record", errors
    )
    candidate_dir = phase_dir / "release-candidates" / release_candidate_id
    candidate_record: dict[str, Any] = {}
    if ID_RE.fullmatch(release_candidate_id) and candidate_dir.is_dir() and not candidate_dir.is_symlink():
        package_entries = verify_sealed_tree(
            candidate_dir, release_candidate_id, f"Release candidate {release_candidate_id}", errors
        )
        manifest_path = candidate_dir / "manifest.sha256"
        if manifest_path.is_file() and candidate_row.get("candidate_manifest_sha256") != sha256_file(manifest_path):
            errors.append("Release candidate registry manifest hash differs")
        if candidate_record_path and candidate_record_path.is_file():
            try:
                candidate_record = load_json(candidate_record_path)
            except ValueError as exc:
                errors.append(str(exc))
        if "candidate-record.json" not in package_entries:
            errors.append("Release candidate package lacks candidate-record.json")
    else:
        errors.append("Release candidate package path/ID is unsafe or missing")
    candidate_artifacts = candidate_record.get("candidate_artifacts")
    if not isinstance(candidate_artifacts, list) or not candidate_artifacts:
        errors.append("Release candidate record has no artifacts")
        candidate_artifacts = []
    artifact_map: dict[str, str] = {}
    report_artifacts: list[dict[str, Any]] = []
    for item in candidate_artifacts:
        if not isinstance(item, dict):
            errors.append("Release candidate artifact record is not an object")
            continue
        relative = str(item.get("relative_path", ""))
        prefix = f"release-candidates/{release_candidate_id}/"
        local_relative = relative[len(prefix):] if relative.startswith(prefix) else ""
        path = safe_relative_path(candidate_dir, local_relative, "release candidate artifact", errors)
        digest = str(item.get("sha256", ""))
        if (
            not path or not path.is_file() or not SHA256_RE.fullmatch(digest)
            or sha256_file(path) != digest or path.stat().st_size != item.get("size")
        ):
            errors.append(f"Release candidate artifact bytes differ: {relative}")
        artifact_map[relative] = digest
        report_artifacts.append({"relative_path": relative, "sha256": digest, "size": item.get("size")})
    try:
        row_artifacts = json.loads(candidate_row.get("artifact_sha256s", ""))
    except json.JSONDecodeError:
        row_artifacts = None
    profile_projection = {
        key: raw_profile.get(key) for key in (
            "bundle_id", "version_name", "version_code", "target_api", "device_types",
            "build_mode", "signing_identity",
        )
    }
    if (
        candidate_record.get("release_candidate_id") != release_candidate_id
        or candidate_record.get("run_id") != scope.get("run_id")
        or candidate_record.get("work_order_id") != work_order_id
        or candidate_record.get("source_snapshot_sha256") != source_snapshot_sha256
        or candidate_record.get("built_by") != ownership.get("candidate_build_agent_id")
        or candidate_record.get("status") != "SEALED"
        or row_artifacts != artifact_map
        or candidate_row.get("source_snapshot_sha256") != source_snapshot_sha256
        or candidate_row.get("built_by") != ownership.get("candidate_build_agent_id")
        or candidate_row.get("artifact_count") != str(len(artifact_map))
        or any(candidate_record.get(key) != value for key, value in profile_projection.items())
        or any(
            candidate_row.get(key) != (
                json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                if key == "device_types" else str(value)
            )
            for key, value in profile_projection.items()
        )
    ):
        errors.append("Release candidate identity, source, owner, profile, or registry differs")

    parity_ids = {
        row.get("parity_id", "") for row in read_csv_rows(
            run_dir / "phase-04-harmony-implementation" / "parity-map.csv"
        ) if row.get("status") == "ACCEPTED"
    }
    included = set(scope.get("migration_scope", {}).get("included_features", []))
    flow_rows = read_csv_rows(phase_dir / "flow-edge-registry.csv")
    invariant_rows = read_csv_rows(phase_dir / "lifecycle-invariants.csv")
    no_cross_rows = read_csv_rows(phase_dir / "no-cross-flow.csv")
    flow_index = index_unique_rows(flow_rows, "flow_edge_id", "Phase 5 flow edges", errors)
    invariant_index = index_unique_rows(
        invariant_rows, "lifecycle_invariant_id", "Phase 5 invariants", errors
    )
    no_cross_index: dict[str, dict[str, str]] = {}
    feature_coverage: set[str] = set()
    for row in flow_rows:
        flow_id = row.get("flow_edge_id", "")
        envs = json_string_array(row.get("applicable_h5env_ids", ""), f"{flow_id}.H5ENV", errors, allow_empty=False)
        features = json_string_array(row.get("feature_ids", ""), f"{flow_id}.features", errors, allow_empty=False)
        basis = json_string_array(row.get("evidence_basis", ""), f"{flow_id}.basis", errors, allow_empty=False)
        if (
            row.get("from_parity_id") not in parity_ids or row.get("to_parity_id") not in parity_ids
            or not set(envs) <= set(required_h5envs) or not set(features) <= included
            or not basis or row.get("frozen_by") != ownership.get("regression_lead_id")
            or row.get("status") != "FROZEN" or not row.get("user_action")
        ):
            errors.append(f"Phase 5 flow edge is not frozen from real parity evidence: {flow_id}")
        feature_coverage.update(features)
    for row in invariant_rows:
        invariant_id = row.get("lifecycle_invariant_id", "")
        envs = json_string_array(row.get("applicable_h5env_ids", ""), f"{invariant_id}.H5ENV", errors, allow_empty=False)
        features = json_string_array(row.get("feature_ids", ""), f"{invariant_id}.features", errors, allow_empty=False)
        categories = json_string_array(
            row.get("required_command_categories", ""), f"{invariant_id}.commands", errors, allow_empty=False
        )
        if (
            not set(envs) <= set(required_h5envs) or not set(features) <= included or not categories
            or not row.get("evidence_basis") or not row.get("rule")
            or row.get("frozen_by") != ownership.get("regression_lead_id")
            or row.get("status") != "FROZEN"
        ):
            errors.append(f"Phase 5 lifecycle invariant is invalid: {invariant_id}")
        feature_coverage.update(features)
    for row in no_cross_rows:
        feature_id = row.get("feature_id", "")
        if feature_id in no_cross_index:
            errors.append(f"Duplicate NO_CROSS_FLOW Feature-ID: {feature_id}")
        no_cross_index[feature_id] = row
        if (
            feature_id not in included or not row.get("evidence_basis") or not row.get("reason")
            or row.get("frozen_by") != ownership.get("regression_lead_id")
            or row.get("status") != "FROZEN"
        ):
            errors.append(f"NO_CROSS_FLOW is not independently supported: {feature_id}")
        feature_coverage.add(feature_id)
    if feature_coverage != included or set(no_cross_index) & {
        feature for row in flow_rows + invariant_rows
        for feature in json_string_array(row.get("feature_ids", "[]"), "feature coverage", [], allow_empty=True)
    }:
        errors.append("Phase 5 flow/invariant/NO_CROSS_FLOW feature coverage is incomplete or contradictory")

    scenario_rows = read_csv_rows(phase_dir / "scenario-registry.csv")
    scenario_index = index_unique_rows(scenario_rows, "scenario_id", "Phase 5 scenarios", errors)
    covered_flows: set[str] = set()
    covered_invariants: set[str] = set()
    scenario_env_pairs: set[tuple[str, str]] = set()
    scenario_hashes: dict[str, str] = {}
    scenario_checkpoints: dict[str, set[str]] = {}
    for scenario_id, row in scenario_index.items():
        scenario_path = safe_relative_path(
            phase_dir, row.get("scenario_relative_path", ""), f"scenario {scenario_id}", errors
        )
        scenario: dict[str, Any] = {}
        recomputed_scenario_sha = ""
        if scenario_path and scenario_path.is_file():
            try:
                scenario = load_json(scenario_path)
                hash_value = scenario.pop("scenario_sha256", "")
                canonical = json.dumps(
                    scenario, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                )
                recomputed_scenario_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                scenario["scenario_sha256"] = hash_value
            except ValueError as exc:
                errors.append(str(exc))
        flows = json_string_array(row.get("flow_edge_ids", ""), f"{scenario_id}.flows", errors)
        invariants = json_string_array(
            row.get("lifecycle_invariant_ids", ""), f"{scenario_id}.invariants", errors
        )
        envs = json_string_array(
            row.get("applicable_h5env_ids", ""), f"{scenario_id}.H5ENV", errors, allow_empty=False
        )
        checkpoints = json_string_array(
            row.get("checkpoint_ids", ""), f"{scenario_id}.checkpoints", errors, allow_empty=False
        )
        row_sha = row.get("scenario_sha256", "")
        if (
            not scenario_path or not scenario_path.is_file() or not SHA256_RE.fullmatch(row_sha)
            or recomputed_scenario_sha != row_sha
            or scenario.get("scenario_id") != scenario_id
            or scenario.get("scenario_version") != row.get("scenario_version")
            or scenario.get("scenario_sha256") != row_sha
            or row.get("release_candidate_id") != release_candidate_id
            or row.get("frozen_by") != ownership.get("regression_lead_id")
            or row.get("status") != "FROZEN"
            or not set(flows) <= set(flow_index) or not set(invariants) <= set(invariant_index)
            or not set(envs) <= set(required_h5envs) or not (flows or invariants)
        ):
            errors.append(f"Phase 5 scenario identity/coverage is invalid: {scenario_id}")
        scenario_hashes[scenario_id] = row_sha
        scenario_checkpoints[scenario_id] = set(checkpoints)
        covered_flows.update(flows)
        covered_invariants.update(invariants)
        scenario_env_pairs.update((scenario_id, env) for env in envs)
    if covered_flows != set(flow_index) or covered_invariants != set(invariant_index):
        errors.append("Phase 5 scenarios do not exactly cover all flow edges and invariants")

    evidence_rows = read_csv_rows(phase_dir / "evidence-index.csv")
    active_evidence = [row for row in evidence_rows if row.get("status") == "SEALED"]
    evidence_index = index_unique_rows(active_evidence, "evidence_id", "Phase 5 evidence", errors)
    evidence_by_pair: dict[tuple[str, str], str] = {}
    candidate_manifest_sha = candidate_row.get("candidate_manifest_sha256", "")
    for evidence_id, row in evidence_index.items():
        pair = (row.get("scenario_id", ""), row.get("h5env_id", ""))
        if pair in evidence_by_pair:
            errors.append(f"Multiple active Phase 5 evidence packages for {pair}")
        evidence_by_pair[pair] = evidence_id
        expected_relative = f"evidence/{pair[1]}/{pair[0]}/{evidence_id}"
        directory = safe_relative_path(phase_dir, row.get("evidence_relative_path", ""), evidence_id, errors)
        metadata: dict[str, Any] = {}
        if directory and directory.is_dir():
            entries = verify_sealed_tree(directory, evidence_id, f"Regression evidence {evidence_id}", errors)
            if "metadata.json" not in entries:
                errors.append(f"Regression evidence lacks metadata: {evidence_id}")
            try:
                metadata = load_json(directory / "metadata.json")
            except ValueError as exc:
                errors.append(str(exc))
            manifest_path = directory / "manifest.sha256"
            if manifest_path.is_file() and row.get("evidence_manifest_sha256") != sha256_file(manifest_path):
                errors.append(f"Regression evidence manifest hash differs: {evidence_id}")
        if (
            pair not in scenario_env_pairs or row.get("evidence_relative_path") != expected_relative
            or row.get("scenario_version") != scenario_index.get(pair[0], {}).get("scenario_version")
            or row.get("scenario_sha256") != scenario_hashes.get(pair[0])
            or row.get("release_candidate_id") != release_candidate_id
            or row.get("candidate_manifest_sha256") != candidate_manifest_sha
            or row.get("executed_by") not in {
                ownership.get("journey_executor_id"), ownership.get("quality_agent_id")
            }
            or metadata.get("evidence_id") not in {None, evidence_id}
            or metadata.get("regression_evidence_id") not in {None, evidence_id}
            or metadata.get("scenario_id") != pair[0]
            or metadata.get("h5env_id") != pair[1]
            or metadata.get("release_candidate_id") != release_candidate_id
            or metadata.get("candidate_manifest_sha256") != candidate_manifest_sha
            or metadata.get("scenario_sha256") != scenario_hashes.get(pair[0])
        ):
            errors.append(f"Regression evidence identity/candidate/scenario differs: {evidence_id}")
        metadata_checkpoints = metadata.get("checkpoint_ids")
        if isinstance(metadata_checkpoints, list) and set(metadata_checkpoints) != scenario_checkpoints.get(pair[0], set()):
            errors.append(f"Regression evidence checkpoint coverage differs: {evidence_id}")
    if set(evidence_by_pair) != scenario_env_pairs:
        errors.append("Phase 5 lacks exactly one active evidence package per scenario/H5ENV")

    acceptance_rows = read_csv_rows(phase_dir / "scenario-acceptance.csv")
    active_reviews = [row for row in acceptance_rows if row.get("status") == "ACCEPTED"]
    review_by_evidence: dict[str, dict[str, str]] = {}
    for row in active_reviews:
        evidence_id = row.get("evidence_id", "")
        if evidence_id in review_by_evidence:
            errors.append(f"Multiple active Phase 5 reviews for evidence: {evidence_id}")
        review_by_evidence[evidence_id] = row
        path = safe_relative_path(phase_dir, row.get("review_relative_path", ""), "Phase 5 review", errors)
        review: dict[str, Any] = {}
        if path and path.is_file():
            try:
                review = load_json(path)
            except ValueError as exc:
                errors.append(str(exc))
        evidence = evidence_index.get(evidence_id, {})
        if (
            not path or not path.is_file() or row.get("review_sha256") != sha256_file(path)
            or row.get("reviewed_by") != ownership.get("system_acceptance_agent_id")
            or row.get("decision") != "ACCEPTED" or row.get("release_candidate_id") != release_candidate_id
            or row.get("candidate_manifest_sha256") != candidate_manifest_sha
            or row.get("scenario_id") != evidence.get("scenario_id")
            or row.get("h5env_id") != evidence.get("h5env_id")
            or review.get("evidence_id") not in {None, evidence_id}
            or review.get("reviewed_by") not in {None, ownership.get("system_acceptance_agent_id")}
            or review.get("decision") not in {None, "ACCEPTED"}
        ):
            errors.append(f"Phase 5 independent scenario review differs: {evidence_id}")
    if set(review_by_evidence) != set(evidence_index):
        errors.append("Phase 5 does not have exactly one accepted independent review per evidence")

    local_rework = read_csv_rows(phase_dir / "rework-tickets.csv")
    controller_rework = [
        row for row in read_csv_rows(run_dir / "controller" / "rework-log.csv")
        if row.get("phase") == "5"
    ]
    local_ids = [row.get("ticket_id", "") for row in local_rework]
    controller_ids = [row.get("rework_id", "") for row in controller_rework]
    if (
        len(local_ids) != len(set(local_ids)) or len(controller_ids) != len(set(controller_ids))
        or set(local_ids) != set(controller_ids)
        or any(row.get("status") != "CLOSED" for row in local_rework + controller_rework)
    ):
        errors.append("Phase 5 local/controller rework ledgers are not uniquely mirrored and closed")
    for local in local_rework:
        matches = [row for row in controller_rework if row.get("rework_id") == local.get("ticket_id")]
        if len(matches) != 1:
            continue
        mirror = matches[0]
        expected = {
            "created_at": local.get("opened_at", ""),
            "record_id": local.get("scenario_id", ""),
            "env_id": local.get("h5env_id", ""),
            "evidence_id": local.get("failed_evidence_id", ""),
            "gate_rule": local.get("problem_type", ""),
            "reason": local.get("reason", ""),
            "assigned_to": local.get("owner_id", ""),
            "completion_condition": local.get("completion_condition", ""),
            "resolved_at": local.get("closed_at", ""),
            "resolution_evidence_id": local.get("resolution_evidence_id", ""),
            "reviewed_by": local.get("closed_by", ""),
        }
        if any(mirror.get(key, "") != value for key, value in expected.items()):
            errors.append(f"Phase 5 controller rework mirror differs: {local.get('ticket_id')}")

    expected_report_identity = {
        "phase": 5,
        "run_id": scope.get("run_id"),
        "work_order_id": work_order_id,
        "verdict": "PASS",
        "final_verdict": "PASS",
        "reviewer_id": ownership.get("system_acceptance_agent_id"),
        "release_candidate_id": release_candidate_id,
        "source_snapshot_sha256": source_snapshot_sha256,
        "input_lock_sha256": sha256_file(phase_dir / "stage-05-input-lock.json"),
        "work_order_sha256": work_order_sha256,
    }
    if (
        any(report.get(key) != value for key, value in expected_report_identity.items())
        or report.get("candidate_artifacts") != sorted(report_artifacts, key=lambda item: item["relative_path"])
        or report.get("errors") != []
        or report.get("open_rework") not in {0, None}
        or report.get("closure_manifest_sha256")
        != sha256_file(phase_dir / "stage-05-closure-manifest.sha256")
    ):
        errors.append("Phase 5 final report identity, reviewer, candidate bytes, or verdict is invalid")
    for key, value in profile_projection.items():
        if report.get(key) != value:
            errors.append(f"Phase 5 final report candidate identity differs: {key}")
    counts = report.get("counts") if isinstance(report.get("counts"), dict) else {}
    expected_counts = {
        "flow_edges": len(flow_rows), "lifecycle_invariants": len(invariant_rows),
        "no_cross_flow": len(no_cross_rows), "scenarios": len(scenario_rows),
        "evidence": len(evidence_index), "reviews": len(review_by_evidence), "open_rework": 0,
    }
    if counts and any(counts.get(key) != value for key, value in expected_counts.items() if key in counts):
        errors.append("Phase 5 report counts differ from the sealed ledgers")

    ledger_rows = read_csv_rows(run_dir / "controller" / "task-ledger.csv")
    phase5_tasks = [row for row in ledger_rows if row.get("phase") == "5"]
    if (
        len(phase5_tasks) != 1 or phase5_tasks[0].get("status") not in {"IN_PROGRESS", "PASS"}
        or phase5_tasks[0].get("owner") != ownership.get("regression_lead_id")
    ):
        errors.append("Controller task ledger does not have the assigned Phase 5 task")
    return (
        errors, warnings,
        release_candidate_id if ID_RE.fullmatch(release_candidate_id) else None,
        str(ownership.get("regression_lead_id") or "") or None,
        work_order_id,
    )


def phase6_command_words(argv: Any) -> set[str]:
    if not isinstance(argv, list):
        return {"<invalid>"}
    words: set[str] = set()
    for index, token in enumerate(argv):
        if not isinstance(token, str) or not token:
            words.add("<invalid>")
            continue
        if token.startswith("{") and token.endswith("}"):
            continue
        value = Path(token).name if index == 0 else token
        value = value.strip().lower().replace("_", "-").lstrip("-").split("=", 1)[0]
        words.add(value)
    return words


def validate_phase6(
    run_dir: Path, scope: dict[str, Any], phase1_facts: dict[str, Any],
) -> tuple[list[str], list[str], str | None, str | None, str | None, str | None]:
    """Independently recheck byte-preserving delivery acceptance without external actions.

    DEPRECATED: retained for legacy run revalidation only
    """
    errors: list[str] = []
    warnings: list[str] = []
    phase_dir = run_dir / "phase-06-harmony-delivery"
    required = (
        "stage-06-input-lock.json", "phase-manifest.json", "candidate-custody-registry.csv",
        "delivery-smoke-index.csv", "material-snapshot-registry.csv", "rework-tickets.csv",
        "delivery-manifest.json", "inputs", "environments", "candidate-custody",
        "smoke-evidence", "materials", "stage-06-gate-report.json",
        "stage-06-closure-manifest.sha256", "CLOSED",
    )
    for relative in required:
        candidate_path = phase_dir / relative
        if not candidate_path.exists() or candidate_path.is_symlink():
            errors.append(f"Missing or unsafe Phase 6 artifact: {candidate_path}")
    try:
        input_lock = load_json(phase_dir / "stage-06-input-lock.json")
        manifest = load_json(phase_dir / "phase-manifest.json")
        report = load_json(phase_dir / "stage-06-gate-report.json")
        delivery_manifest = load_json(phase_dir / "delivery-manifest.json")
    except ValueError as exc:
        errors.append(str(exc))
        return errors, warnings, None, None, None, None

    verify_phase56_closure(phase_dir, 6, errors)
    verify_closed_marker(phase_dir, 6, errors)
    work_order, ownership, work_order_sha256, work_order_id = validate_phase56_work_order(
        run_dir, scope, phase1_facts, 6, manifest, input_lock, STAGE6_ROLE_KEYS,
        "harmonyos-delivery-acceptance", errors,
    )
    expected_permissions = {
        "rebuild": False, "resign": False, "upload": False, "send": False,
        "distribute": False, "store": False, "remote_signing": False, "publish": False,
    }
    if work_order.get("permissions") != expected_permissions:
        errors.append("Phase 6 work order does not explicitly prohibit every mutating/external action")
    if (
        manifest.get("phase") != 6 or manifest.get("status") != "IN_PROGRESS"
        or manifest.get("work_order_id") != work_order_id
        or manifest.get("ownership") != ownership
        or manifest.get("initialized_by") != ownership.get("delivery_lead_id")
        or input_lock.get("work_order", {}).get("work_order_id") != work_order_id
        or input_lock.get("work_order", {}).get("sha256") != work_order_sha256
        or manifest.get("release_candidate_id") != input_lock.get("release_candidate_id")
    ):
        errors.append("Phase 6 manifest/input lock identity, owner, or work order differs")

    order_inputs = work_order.get("inputs") if isinstance(work_order.get("inputs"), dict) else {}
    expected_input_keys = {
        "phase5_gate_report", "phase5_work_order", "phase5_input_lock",
        "phase5_closure_manifest", "phase5_closed", "phase5_release_candidate_registry",
    }
    if set(order_inputs) != expected_input_keys:
        errors.append("Phase 6 work order input key set differs")
    for key in sorted(expected_input_keys):
        validate_frozen_file_record(
            run_dir, order_inputs.get(key), f"Phase 6 {key}", errors, require_live=True
        )
    local_inputs = input_lock.get("phase5_inputs") if isinstance(input_lock.get("phase5_inputs"), dict) else {}
    if set(local_inputs) != expected_input_keys:
        errors.append("Phase 6 local input lock does not cover the exact Gate 5 chain")
    for key in sorted(expected_input_keys):
        local = local_inputs.get(key)
        order_record = order_inputs.get(key)
        if not isinstance(local, dict) or not isinstance(order_record, dict):
            continue
        frozen = safe_relative_path(
            phase_dir, str(local.get("frozen_relative_path", "")), f"Phase 6 frozen {key}", errors
        )
        if (
            local.get("sha256") != order_record.get("sha256")
            or not frozen or not frozen.is_file() or sha256_file(frozen) != local.get("sha256")
        ):
            errors.append(f"Phase 6 frozen local input differs: {key}")

    candidate = work_order.get("candidate") if isinstance(work_order.get("candidate"), dict) else {}
    release_candidate_id = str(candidate.get("release_candidate_id", ""))
    artifacts = candidate.get("artifacts")
    if not ID_RE.fullmatch(release_candidate_id) or not isinstance(artifacts, list) or not artifacts:
        errors.append("Phase 6 work order lacks a safe candidate and artifact set")
        artifacts = []
    expected_artifacts: dict[str, dict[str, Any]] = {}
    for item in artifacts:
        if not isinstance(item, dict):
            errors.append("Phase 6 candidate artifact record is not an object")
            continue
        relative = str(item.get("relative_path", ""))
        if not relative.startswith(f"release-candidates/{release_candidate_id}/artifacts/") or relative in expected_artifacts:
            errors.append(f"Unsafe/duplicate Phase 6 candidate artifact path: {relative}")
            continue
        path = safe_relative_path(
            run_dir / "phase-05-harmony-regression", relative, "Gate 5 candidate artifact", errors
        )
        digest = str(item.get("sha256", ""))
        if (
            not path or not path.is_file() or not SHA256_RE.fullmatch(digest)
            or sha256_file(path) != digest or path.stat().st_size != item.get("size")
        ):
            errors.append(f"Gate 5 candidate bytes changed before Phase 6: {relative}")
        expected_artifacts[relative] = item
    if (
        input_lock.get("release_candidate_id") != release_candidate_id
        or manifest.get("release_candidate_id") != release_candidate_id
        or candidate.get("candidate_registry_sha256")
        != sha256_file(run_dir / "phase-05-harmony-regression" / "release-candidate-registry.csv")
    ):
        errors.append("Phase 6 candidate ID/registry binding differs from Gate 5")
    candidate_identity = input_lock.get("candidate_identity") if isinstance(input_lock.get("candidate_identity"), dict) else {}
    for key in (
        "bundle_id", "version_name", "version_code", "target_api", "device_types",
        "build_mode", "signing_identity", "source_snapshot_sha256",
    ):
        if candidate.get(key) != candidate_identity.get(key):
            errors.append(f"Phase 6 candidate identity differs from input lock: {key}")

    locked_artifacts = input_lock.get("candidate_artifacts")
    if not isinstance(locked_artifacts, list) or len(locked_artifacts) != len(expected_artifacts):
        errors.append("Phase 6 input lock candidate artifact coverage differs")
        locked_artifacts = []
    for item in locked_artifacts:
        if not isinstance(item, dict):
            errors.append("Phase 6 locked candidate artifact is invalid")
            continue
        expected = expected_artifacts.get(str(item.get("relative_path", "")))
        frozen = safe_relative_path(
            phase_dir, str(item.get("frozen_relative_path", "")), "frozen Gate 5 candidate", errors
        )
        if (
            not expected or item.get("sha256") != expected.get("sha256")
            or item.get("size") != expected.get("size") or not frozen or not frozen.is_file()
            or sha256_file(frozen) != expected.get("sha256") or frozen.stat().st_size != expected.get("size")
        ):
            errors.append(f"Phase 6 frozen candidate copy differs: {item.get('relative_path')}")

    required_h6envs = work_order.get("required_h6env_ids")
    order_envs = work_order.get("h6envs")
    if (
        not isinstance(required_h6envs, list) or not required_h6envs
        or required_h6envs != sorted(set(required_h6envs)) or not isinstance(order_envs, list)
    ):
        errors.append("Phase 6 required H6ENV set is invalid")
        required_h6envs, order_envs = [], []
    env_by_id = {str(item.get("h6env_id", "")): item for item in order_envs if isinstance(item, dict)}
    if set(env_by_id) != set(required_h6envs):
        errors.append("Phase 6 H6ENV work-order coverage differs")
    for env_id in required_h6envs:
        record = env_by_id.get(env_id, {})
        snapshot = safe_relative_path(
            run_dir, str(record.get("snapshot_relative_path", "")), f"{env_id} controller snapshot", errors
        )
        local = phase_dir / "environments" / env_id / "environment.json"
        environment: dict[str, Any] = {}
        if local.is_file() and not local.is_symlink():
            try:
                environment = load_json(local)
            except ValueError as exc:
                errors.append(str(exc))
        if (
            record.get("required") is not True or not snapshot or not snapshot.is_file()
            or not local.is_file() or local.is_symlink() or record.get("sha256") != sha256_file(snapshot)
            or sha256_file(local) != record.get("sha256") or snapshot.read_bytes() != local.read_bytes()
            or environment.get("h6env_id") != env_id
            or environment.get("base_h5env_id") != record.get("base_h5env_id")
            or environment.get("install_artifact_relative_path") not in expected_artifacts
        ):
            errors.append(f"Phase 6 H6ENV snapshot/identity/install artifact differs: {env_id}")
        env_identity = environment.get("candidate_identity") if isinstance(environment.get("candidate_identity"), dict) else {}
        identity_projection = {
            "bundle_id": candidate_identity.get("bundle_id"),
            "version_name": candidate_identity.get("version_name"),
            "version_code": candidate_identity.get("version_code"),
            "target_api": candidate_identity.get("target_api"),
            "device_types": candidate_identity.get("device_types"),
            "build_mode": candidate_identity.get("build_mode"),
            "signing_fingerprint": candidate_identity.get("signing_identity"),
        }
        if env_identity != identity_projection:
            errors.append(f"Phase 6 H6ENV candidate identity differs: {env_id}")
        contracts = environment.get("command_contracts") if isinstance(environment.get("command_contracts"), dict) else {}
        expected_categories = {
            "DEVICE_CHECK", "INSTALL", "IDENTITY_QUERY", "LAUNCH", "SMOKE_ASSERT",
            "SCREENSHOT_CAPTURE", "UI_TREE_CAPTURE",
        }
        if set(contracts) != expected_categories:
            errors.append(f"Phase 6 H6ENV command categories differ: {env_id}")
        for category, contract in contracts.items():
            argv = contract.get("argv") if isinstance(contract, dict) else None
            words = phase6_command_words(argv)
            if words & PHASE6_PROHIBITED_COMMAND_WORDS or "<invalid>" in words:
                errors.append(f"Phase 6 H6ENV contains a prohibited command: {env_id}/{category}")

    custody_rows = read_csv_rows(phase_dir / "candidate-custody-registry.csv")
    active_custody = [row for row in custody_rows if row.get("status") == "SEALED"]
    if len(active_custody) != 1:
        errors.append("Phase 6 must have exactly one active Candidate-Custody-ID")
        custody_row: dict[str, str] = {}
    else:
        custody_row = active_custody[0]
    custody_id = str(custody_row.get("custody_id", ""))
    custody_dir = safe_relative_path(
        phase_dir, custody_row.get("relative_path", ""), "candidate custody", errors
    )
    custody: dict[str, Any] = {}
    if custody_dir and custody_dir.is_dir() and ID_RE.fullmatch(custody_id):
        verify_sealed_tree(custody_dir, custody_id, f"Candidate custody {custody_id}", errors)
        try:
            custody = load_json(custody_dir / "metadata.json")
        except ValueError as exc:
            errors.append(str(exc))
    custody_artifacts = custody.get("artifacts") if isinstance(custody.get("artifacts"), list) else []
    custody_by_gate5: dict[str, dict[str, Any]] = {
        str(item.get("gate5_relative_path", "")): item for item in custody_artifacts if isinstance(item, dict)
    }
    if (
        not ID_RE.fullmatch(custody_id) or custody.get("candidate_custody_id") != custody_id
        or custody.get("release_candidate_id") != release_candidate_id
        or custody.get("operation") != "BYTE_COPY_ONLY" or custody.get("rebuild_performed") is not False
        or custody.get("resign_performed") is not False or custody.get("status") != "SEALED"
        or custody.get("copied_by") != ownership.get("candidate_custody_agent_id")
        or set(custody_by_gate5) != set(expected_artifacts)
    ):
        errors.append("Phase 6 candidate custody identity, ownership, or byte-only operation differs")
    for relative, expected in expected_artifacts.items():
        item = custody_by_gate5.get(relative, {})
        path = (
            safe_relative_path(custody_dir, str(item.get("relative_path", "")), "custody artifact", errors)
            if custody_dir else None
        )
        if (
            item.get("sha256") != expected.get("sha256") or item.get("size") != expected.get("size")
            or not path or not path.is_file() or sha256_file(path) != expected.get("sha256")
            or path.stat().st_size != expected.get("size")
        ):
            errors.append(f"Candidate custody bytes differ from Gate 5: {relative}")

    smoke_rows = read_csv_rows(phase_dir / "delivery-smoke-index.csv")
    active_smoke = [row for row in smoke_rows if row.get("status") == "PASS"]
    smoke_by_env: dict[str, dict[str, str]] = {}
    for row in active_smoke:
        env_id = row.get("h6env_id", "")
        smoke_id = row.get("delivery_smoke_id", "")
        if env_id in smoke_by_env:
            errors.append(f"Multiple active Delivery-Smoke-IDs for {env_id}")
        smoke_by_env[env_id] = row
        directory = safe_relative_path(phase_dir, row.get("relative_path", ""), smoke_id, errors)
        metadata: dict[str, Any] = {}
        if directory and directory.is_dir() and ID_RE.fullmatch(smoke_id):
            entries = verify_sealed_tree(directory, smoke_id, f"Delivery smoke {smoke_id}", errors)
            for name in ("metadata.json", "command-records.json", "screenshot.png", "ui-tree.json"):
                if name not in entries:
                    errors.append(f"Delivery smoke {smoke_id} lacks {name}")
            try:
                metadata = load_json(directory / "metadata.json")
                validate_complete_png(directory / "screenshot.png")
                tree = json.loads((directory / "ui-tree.json").read_text(encoding="utf-8"))
                if tree in ({}, [], None, ""):
                    errors.append(f"Delivery smoke UI tree is empty: {smoke_id}")
                commands = json.loads((directory / "command-records.json").read_text(encoding="utf-8"))
                for command in commands if isinstance(commands, list) else []:
                    words = phase6_command_words(command.get("argv") if isinstance(command, dict) else None)
                    if words & PHASE6_PROHIBITED_COMMAND_WORDS or "<invalid>" in words:
                        errors.append(f"Delivery smoke contains prohibited command: {smoke_id}")
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                errors.append(f"Delivery smoke {smoke_id}: {exc}")
        if (
            env_id not in required_h6envs or not ID_RE.fullmatch(smoke_id)
            or row.get("candidate_custody_id") != custody_id
            or row.get("release_candidate_id") != release_candidate_id
            or row.get("executed_by") != ownership.get("candidate_validation_agent_id")
            or metadata.get("delivery_smoke_id") != smoke_id or metadata.get("h6env_id") != env_id
            or metadata.get("candidate_custody_id") != custody_id
            or metadata.get("release_candidate_id") != release_candidate_id
            or metadata.get("executed_by") != ownership.get("candidate_validation_agent_id")
            or metadata.get("status") != "PASS"
        ):
            errors.append(f"Phase 6 delivery smoke identity/owner/candidate differs: {smoke_id}")
    if set(smoke_by_env) != set(required_h6envs):
        errors.append("Phase 6 lacks exactly one active smoke package per required H6ENV")

    material_rows = read_csv_rows(phase_dir / "material-snapshot-registry.csv")
    active_materials = [row for row in material_rows if row.get("status") == "SEALED"]
    if len(active_materials) != 1:
        errors.append("Phase 6 must have exactly one active Material-Snapshot-ID")
        material_row: dict[str, str] = {}
    else:
        material_row = active_materials[0]
    material_id = str(material_row.get("material_snapshot_id", ""))
    material_dir = safe_relative_path(
        phase_dir, material_row.get("relative_path", ""), "material snapshot", errors
    )
    material: dict[str, Any] = {}
    if material_dir and material_dir.is_dir() and ID_RE.fullmatch(material_id):
        verify_sealed_tree(material_dir, material_id, f"Material snapshot {material_id}", errors)
        try:
            material = load_json(material_dir / "metadata.json")
        except ValueError as exc:
            errors.append(str(exc))
    if (
        material.get("material_snapshot_id") != material_id
        or material.get("candidate_custody_id") != custody_id
        or material.get("release_candidate_id") != release_candidate_id
        or material.get("created_by") != ownership.get("material_consistency_agent_id")
        or material.get("legal_conclusion") != "NOT_PERFORMED" or material.get("status") != "SEALED"
    ):
        errors.append("Phase 6 material snapshot identity, authority, or legal boundary differs")
    for source in material.get("source_evidence", []) if isinstance(material.get("source_evidence"), list) else []:
        if not isinstance(source, dict):
            errors.append("Phase 6 material source evidence is invalid")
            continue
        path = safe_relative_path(
            run_dir, str(source.get("relative_path", "")), "material source evidence", errors
        )
        if (
            not path or not path.is_file() or path.suffix.lower() == ".mp4"
            or sha256_file(path) != source.get("sha256") or path.stat().st_size != source.get("size")
        ):
            errors.append(f"Phase 6 material source evidence changed: {source.get('reference')}")

    smoke_ids = {env: row.get("delivery_smoke_id", "") for env, row in sorted(smoke_by_env.items())}
    external_actions = delivery_manifest.get("external_actions")
    if (
        delivery_manifest.get("phase") != 6
        or not ID_RE.fullmatch(str(delivery_manifest.get("delivery_manifest_id", "")))
        or delivery_manifest.get("release_candidate_id") != release_candidate_id
        or delivery_manifest.get("candidate_custody_id") != custody_id
        or delivery_manifest.get("delivery_smoke_ids") != smoke_ids
        or delivery_manifest.get("material_snapshot_id") != material_id
        or delivery_manifest.get("candidate_identity") != candidate_identity
        or delivery_manifest.get("created_by") != ownership.get("delivery_lead_id")
        or delivery_manifest.get("status") != "READY_FOR_ACCEPTANCE"
        or not isinstance(external_actions, dict) or any(value is not False for value in external_actions.values())
    ):
        errors.append("Phase 6 delivery manifest identity, coverage, owner, or external-action record differs")
    rollback = delivery_manifest.get("rollback") if isinstance(delivery_manifest.get("rollback"), dict) else {}
    if (
        rollback.get("owner_id") != ownership.get("delivery_lead_id")
        or not isinstance(rollback.get("conditions"), list) or not rollback.get("conditions")
        or not isinstance(rollback.get("steps"), list) or not rollback.get("steps")
    ):
        errors.append("Phase 6 rollback plan is incomplete or owned by another actor")
    delivery_files = delivery_manifest.get("delivery_files")
    if not isinstance(delivery_files, list) or len(delivery_files) != len(expected_artifacts):
        errors.append("Phase 6 delivery manifest file coverage differs from Gate 5")
        delivery_files = []
    for item in delivery_files:
        if not isinstance(item, dict):
            errors.append("Phase 6 delivery file record is invalid")
            continue
        expected = expected_artifacts.get(str(item.get("gate5_relative_path", "")))
        path = safe_relative_path(phase_dir, str(item.get("relative_path", "")), "delivery file", errors)
        if (
            not expected or item.get("sha256") != expected.get("sha256")
            or item.get("size") != expected.get("size") or not path or not path.is_file()
            or sha256_file(path) != expected.get("sha256") or path.stat().st_size != expected.get("size")
        ):
            errors.append(f"Phase 6 delivery file differs from Gate 5: {item.get('gate5_relative_path')}")

    local_rework = read_csv_rows(phase_dir / "rework-tickets.csv")
    controller_rework = [
        row for row in read_csv_rows(run_dir / "controller" / "rework-log.csv")
        if row.get("phase") == "6"
    ]
    local_ids = [row.get("ticket_id", "") for row in local_rework]
    controller_ids = [row.get("rework_id", "") for row in controller_rework]
    if (
        len(local_ids) != len(set(local_ids)) or len(controller_ids) != len(set(controller_ids))
        or set(local_ids) != set(controller_ids)
        or any(row.get("status") != "CLOSED" for row in local_rework + controller_rework)
    ):
        errors.append("Phase 6 local/controller rework ledgers are not uniquely mirrored and closed")
    for local in local_rework:
        matches = [row for row in controller_rework if row.get("rework_id") == local.get("ticket_id")]
        if len(matches) != 1:
            continue
        mirror = matches[0]
        expected = {
            "created_at": local.get("opened_at", ""), "record_id": local.get("record_id", ""),
            "env_id": local.get("h6env_id", ""), "evidence_id": local.get("record_id", ""),
            "gate_rule": "GATE6", "reason": local.get("reason", ""),
            "assigned_to": local.get("owner_id", ""),
            "completion_condition": local.get("completion_condition", ""),
            "resolved_at": local.get("closed_at", ""),
            "resolution_evidence_id": local.get("resolution_record_id", ""),
            "reviewed_by": local.get("closed_by", ""),
        }
        if any(mirror.get(key, "") != value for key, value in expected.items()):
            errors.append(f"Phase 6 controller rework mirror differs: {local.get('ticket_id')}")

    report_identity = {
        "phase": 6,
        "run_id": scope.get("run_id"),
        "work_order_id": work_order_id,
        "verdict": "PASS",
        "final_verdict": "PASS",
        "release_candidate_id": release_candidate_id,
        "candidate_custody_id": custody_id,
        "material_snapshot_id": material_id,
        "delivery_manifest_id": delivery_manifest.get("delivery_manifest_id"),
        "reviewer_id": ownership.get("delivery_acceptance_agent_id"),
    }
    if (
        any(report.get(key) != value for key, value in report_identity.items())
        or report.get("candidate_artifacts") != sorted(
            [
                {"relative_path": relative, "sha256": item.get("sha256"), "size": item.get("size")}
                for relative, item in expected_artifacts.items()
            ], key=lambda item: item["relative_path"],
        )
        or report.get("errors") != [] or report.get("open_rework") not in {0, None}
        or report.get("external_actions_performed") not in {False, None}
    ):
        errors.append("Phase 6 final report identity, reviewer, candidate bytes, or verdict is invalid")

    ledger_rows = read_csv_rows(run_dir / "controller" / "task-ledger.csv")
    phase6_tasks = [row for row in ledger_rows if row.get("phase") == "6"]
    if (
        len(phase6_tasks) != 1 or phase6_tasks[0].get("status") not in {"IN_PROGRESS", "PASS"}
        or phase6_tasks[0].get("owner") != ownership.get("delivery_lead_id")
    ):
        errors.append("Controller task ledger does not have the assigned Phase 6 task")
    return (
        errors, warnings,
        release_candidate_id if ID_RE.fullmatch(release_candidate_id) else None,
        str(delivery_manifest.get("delivery_manifest_id") or "") or None,
        str(ownership.get("delivery_lead_id") or "") or None,
        work_order_id,
    )


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Refusing to replace symbolic-link target: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def update_task_ledger(
    run_dir: Path,
    phase: int,
    verdict: str,
    errors: list[str],
    ownership: dict[str, Any],
    phase3_owner: str | None = None,
    phase4_owner: str | None = None,
    phase5_owner: str | None = None,
    phase6_owner: str | None = None,
) -> None:
    path = run_dir / "controller" / "task-ledger.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    target = str(phase)
    matches = [row for row in rows if row.get("phase") == target]
    if len(matches) != 1 or not fieldnames:
        raise ValueError(f"Task ledger has no unique phase {phase} row")
    matches[0]["status"] = verdict
    matches[0]["updated_at"] = utc_now()
    matches[0]["notes"] = "; ".join(errors[:3])
    for row in rows:
        if row.get("phase") == "1":
            row["owner"] = str(ownership.get("migration_controller_id", row.get("owner", "")))
        elif row.get("phase") == "2":
            row["owner"] = str(ownership.get("inventory_lead_id", row.get("owner", "")))
        elif row.get("phase") == "3" and phase3_owner:
            row["owner"] = phase3_owner
        elif row.get("phase") == "4" and phase4_owner:
            row["owner"] = phase4_owner
        elif row.get("phase") == "5" and phase5_owner:
            row["owner"] = phase5_owner
        elif row.get("phase") == "6" and phase6_owner:
            row["owner"] = phase6_owner
    if path.is_symlink():
        raise ValueError(f"Refusing symbolic-link task ledger: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
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


SKILL_FREEZE_SKILL_NAMES = (
    "android-harmony-migration-controller",
    "android-migration-inventory",
    "harmonyos-feature-implementation",
    "harmonyos-migration-scaffold",
)
SKILL_FREEZE_DIRS = ("scripts", "references", "assets", "evals", "security")
SKILL_FREEZE_ROOT_FILES = ("SKILL.md", "manifest.json")
SKILL_FREEZE_MANIFEST_RELATIVE = "controller/skill-freeze-manifest.sha256"
# TOOL_GAP semantics (batch 4 #87): hash drift is a tool gap, not a silent
# refresh. Single-sourced from _run_status so init_migration and the gate
# always print the same remedy.
SKILL_FREEZE_REMEDY = TOOL_GAP_REMEDY


def _skill_freeze_current_hashes(skills_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for skill_name in SKILL_FREEZE_SKILL_NAMES:
        skill_root = skills_root / skill_name
        if not skill_root.is_dir():
            continue
        for dir_name in SKILL_FREEZE_DIRS:
            base = skill_root / dir_name
            if not base.is_dir():
                continue
            for path in base.rglob("*"):
                # 字节码产物平台相关，绝不入冻结比对（与 init_migration 同款过滤）
                if "__pycache__" in path.parts or path.suffix == ".pyc":
                    continue
                if path.is_file() and not path.is_symlink():
                    hashes[f"{skill_name}/{path.relative_to(skill_root).as_posix()}"] = sha256_file(path)
        for file_name in SKILL_FREEZE_ROOT_FILES:
            target = skill_root / file_name
            if target.is_file() and not target.is_symlink():
                hashes[f"{skill_name}/{file_name}"] = sha256_file(target)
    return hashes


def verify_skill_freeze(run_root: Path | str, skills_root: Path | str | None = None) -> list[str]:
    """Verify the current skill tree against the run's frozen SHA-256 manifest.

    Returns a list of error strings; empty means the check passed. A missing freeze
    manifest (historical strict runs) only warns and is skipped. The skill root
    defaults to the skills directory containing this script and can be overridden
    via the ``skills_root`` parameter or the ``SKILL_FREEZE_SKILLS_ROOT`` env var.
    """
    errors: list[str] = []
    manifest_path = Path(run_root) / SKILL_FREEZE_MANIFEST_RELATIVE
    if not manifest_path.is_file():
        # A run whose run-manifest declares the freeze digest must not silently
        # skip verification when the manifest file itself disappeared.
        declared_freeze = None
        run_manifest_path = Path(run_root) / "run-manifest.json"
        if run_manifest_path.is_file():
            try:
                run_manifest_data = json.loads(run_manifest_path.read_text(encoding="utf-8"))
                if isinstance(run_manifest_data, dict):
                    declared_freeze = run_manifest_data.get("skill_freeze_manifest_sha256")
            except (OSError, json.JSONDecodeError):
                declared_freeze = None
        if declared_freeze:
            errors.append(
                "run manifest declares a skill freeze manifest but it is missing: "
                f"{manifest_path}"
            )
            return errors
        print(
            "WARNING: skill freeze manifest missing; skipping freeze verification "
            "(legacy run compatibility)",
            file=sys.stderr,
        )
        return errors
    override = skills_root if skills_root is not None else os.environ.get("SKILL_FREEZE_SKILLS_ROOT")
    root = Path(str(override)).expanduser() if override else Path(__file__).resolve().parents[2]
    if not root.is_dir():
        errors.append(f"skill freeze violated: {root}（skill 根目录不存在）；{SKILL_FREEZE_REMEDY}")
        return errors
    frozen: dict[str, str] = {}
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(f"skill freeze violated: {manifest_path}（清单不可读: {exc}）；{SKILL_FREEZE_REMEDY}")
        return errors
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        if "  " not in line:
            errors.append(f"skill freeze violated: 清单第 {number} 行格式非法；{SKILL_FREEZE_REMEDY}")
            continue
        digest, relative = line.split("  ", 1)
        if not SHA256_RE.fullmatch(digest) or relative in frozen:
            errors.append(f"skill freeze violated: 清单第 {number} 行条目非法；{SKILL_FREEZE_REMEDY}")
            continue
        frozen[relative] = digest
    current = _skill_freeze_current_hashes(root)
    for relative in sorted(frozen):
        if relative not in current:
            errors.append(f"skill freeze violated: {relative}（冻结文件缺失）；{SKILL_FREEZE_REMEDY}")
        elif current[relative] != frozen[relative]:
            errors.append(f"skill freeze violated: {relative}（哈希漂移）；{SKILL_FREEZE_REMEDY}")
    for relative in sorted(set(current) - set(frozen)):
        errors.append(f"skill freeze violated: {relative}（未登记的新增文件）；{SKILL_FREEZE_REMEDY}")
    return errors


def maybe_close_run_after_gate4(
    run_dir: Path, phase: int, verdict: str, wrote: bool, scope: dict[str, Any]
) -> None:
    """Close the run after an approved machine Gate 4 PASS (batch 4 #87).

    Extracted from main() so the TOOL_GAP lifecycle rule is unit-testable:
    phase 4 + verdict PASS + --write => run_status transitions to CLOSED,
    after which the skill trees may be revised and the freeze re-pinned via
    ``init_migration.py --refresh-freeze``. Any other combination is a no-op.
    """
    if phase == 4 and verdict == "PASS" and wrote:
        transition_run_status(
            run_dir,
            "CLOSED",
            decision_type="RUN_STATUS_TRANSITION",
            decision="CLOSED",
            rationale="Gate 4 machine PASS recorded (validate_gate --phase 4 --write)",
            decided_by=scope.get("ownership", {}).get(
                "migration_controller_id", "migration-controller-agent"
            ),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--phase", required=True, type=int, choices=(1, 2, 3, 4, 5, 6))
    parser.add_argument("--write", action="store_true", help="Update controller/gate-report.json")
    args = parser.parse_args()

    run_input = Path(args.run_dir).expanduser().absolute()
    if run_input.is_symlink():
        parser.error("Migration run must not be a symbolic link")
    run_dir = run_input.resolve()
    scope: dict[str, Any] = {}
    freeze_errors = verify_skill_freeze(run_dir)
    if freeze_errors:
        errors, warnings, baseline_env_id, facts = list(freeze_errors), [], None, {}
    else:
        try:
            scope = load_json(run_dir / "controller" / "scope.json")
            errors, warnings, baseline_env_id, facts = validate_phase1(run_dir, scope)
        except ValueError as exc:
            errors, warnings, baseline_env_id, facts = [str(exc)], [], None, {}

    if args.phase in {2, 3, 4, 5, 6} and not errors:
        phase_errors, phase_warnings = validate_phase2_gmi(run_dir, scope, baseline_env_id, facts)
        errors.extend(phase_errors)
        warnings.extend(phase_warnings)

    harmony_environment_id = None
    verification_id = None
    phase3_owner = None
    phase3_work_order_id = None
    if args.phase in {3, 4, 5, 6} and not errors:
        (
            phase_errors,
            phase_warnings,
            harmony_environment_id,
            verification_id,
            phase3_owner,
            phase3_work_order_id,
        ) = validate_phase3(run_dir, scope, facts)
        errors.extend(phase_errors)
        warnings.extend(phase_warnings)

    harmony_build_ids: list[str] = []
    harmony_evidence_ids: list[str] = []
    phase4_owner = None
    phase4_work_order_id = None
    if args.phase in {4, 5, 6} and not errors:
        (
            phase_errors,
            phase_warnings,
            harmony_build_ids,
            harmony_evidence_ids,
            phase4_owner,
            phase4_work_order_id,
        ) = validate_phase4(run_dir, scope, facts)
        errors.extend(phase_errors)
        warnings.extend(phase_warnings)

    release_candidate_id = None
    phase5_owner = None
    phase5_work_order_id = None
    if args.phase in {5, 6} and not errors:
        (
            phase_errors,
            phase_warnings,
            release_candidate_id,
            phase5_owner,
            phase5_work_order_id,
        ) = validate_phase5(run_dir, scope, facts)
        errors.extend(phase_errors)
        warnings.extend(phase_warnings)

    delivery_manifest_id = None
    phase6_owner = None
    phase6_work_order_id = None
    if args.phase == 6 and not errors:
        (
            phase_errors,
            phase_warnings,
            release_candidate_id,
            delivery_manifest_id,
            phase6_owner,
            phase6_work_order_id,
        ) = validate_phase6(run_dir, scope, facts)
        errors.extend(phase_errors)
        warnings.extend(phase_warnings)

    report = {
        "run_id": scope.get("run_id") if "scope" in locals() else None,
        "phase": args.phase,
        "verdict": "PASS" if not errors else "FAIL",
        "baseline_env_id": baseline_env_id,
        "harmony_environment_id": harmony_environment_id,
        "verification_id": verification_id,
        "phase3_work_order_id": phase3_work_order_id,
        "phase4_work_order_id": phase4_work_order_id,
        "phase5_work_order_id": phase5_work_order_id,
        "phase6_work_order_id": phase6_work_order_id,
        "release_candidate_id": release_candidate_id,
        "delivery_manifest_id": delivery_manifest_id,
        "harmony_build_ids": harmony_build_ids,
        "harmony_evidence_ids": harmony_evidence_ids,
        "scope_sha256": facts.get("scope_sha256"),
        "run_manifest_sha256": facts.get("run_manifest_sha256"),
        "source_revision": facts.get("source_revision"),
        "apk_sha256": facts.get("apk_sha256"),
        "runtime_bc_pass_rate": facts.get("runtime_bc_pass_rate", None if args.phase == 4 else 1.0),
        "runtime_bc_pass_rate_note": facts.get(
            "runtime_bc_pass_rate_note",
            "Phase 4 replay facts missing; runtime_bc_pass_rate unavailable"
            if args.phase == 4
            else "no Phase 4 replay facts; safe default"
        ),
        "persistence_consistency": facts.get("persistence_consistency", "NOT_MEASURED"),
        "native_review_status": facts.get("native_review_status", "PENDING"),
        "included_features": facts.get("included_features", []),
        "checked_at": utc_now(),
        "errors": errors,
        "warnings": warnings,
    }
    if args.write:
        try:
            atomic_json(run_dir / "controller" / "gate-report.json", report)
            update_task_ledger(
                run_dir,
                args.phase,
                report["verdict"],
                errors,
                scope.get("ownership", {}),
                phase3_owner,
                phase4_owner,
                phase5_owner,
                phase6_owner,
            )
            # TOOL_GAP freeze semantics (batch 4 #87): an approved-quality
            # machine Gate 4 PASS closes the run; afterwards the skill trees
            # may be revised and the freeze re-pinned via --refresh-freeze.
            maybe_close_run_after_gate4(run_dir, args.phase, report["verdict"], True, scope)
        except ValueError as exc:
            parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
