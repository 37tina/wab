#!/usr/bin/env python3
"""Build one real, closed Phase 1/2 fixture for Phase 3 integration tests."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCAFFOLD_SKILL = HERE.parents[1]
BUNDLE = SCAFFOLD_SKILL.parent
CONTROLLER_SKILL = BUNDLE / "android-harmony-migration-controller"
INVENTORY_SKILL = BUNDLE / "android-migration-inventory"
FAKE_ANDROID = INVENTORY_SKILL / "scripts" / "tests" / "fake_android.py"


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(args), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if completed.returncode != expect:
        raise AssertionError(
            f"Expected exit {expect}, got {completed.returncode}\nCOMMAND: {args}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record_human_approval(run_dir: Path, phase: int, review_id: str) -> None:
    review_input = run_dir / "controller" / f"phase-{phase:02d}-review-input.json"
    review_input.write_text(
        json.dumps({"coverage": {}, "exceptions": [], "top_risks": []}) + "\n",
        encoding="utf-8",
    )
    run(
        sys.executable, str(CONTROLLER_SKILL / "scripts" / "generate_review_summary.py"),
        "--run-dir", str(run_dir), "--phase", str(phase),
        "--gate-report", str(run_dir / "controller" / "gate-report.json"),
        "--input", str(review_input),
    )
    run(
        sys.executable, str(CONTROLLER_SKILL / "scripts" / "record_human_review.py"),
        "--run-dir", str(run_dir), "--phase", str(phase),
        "--gate-report", str(run_dir / "controller" / "gate-report.json"),
        "--review-id", review_id,
        "--reviewer", "fixture-human-reviewer",
        "--decision", "APPROVED",
    )


def record_team_receipt(
    run_dir: Path,
    work_order: Path,
    role_key: str,
    actor_id: str,
    platform_task_id: str,
    artifact: Path,
) -> None:
    run(
        sys.executable,
        str(CONTROLLER_SKILL / "scripts" / "record_team_execution.py"),
        "--run-dir", str(run_dir),
        "--work-order", work_order.relative_to(run_dir).as_posix(),
        "--role-key", role_key,
        "--actor-id", actor_id,
        "--platform-task-id", platform_task_id,
        "--started-at", "2026-08-24T10:00:00Z",
        "--ended-at", "2026-08-24T10:05:00Z",
        "--terminal-task-state", "SUCCEEDED",
        "--artifact", artifact.relative_to(run_dir).as_posix(),
    )


def build_closed_phase2(
    root: Path,
    *,
    orphan_toggle: bool = True,
    runtime_container_host: str = "RUNTIME",
) -> tuple[Path, Path]:
    """Run the real Phase 1/2 scripts and return (run_dir, scope_path).

    v3 链范式（#47/#52）：
    - ``orphan_toggle``：data-relations.csv 是否包含一行故意孤儿场景的
      开关参数行（feature_id 为空的 mmkv toggle，供 Gate 3 规则 2 的
      孤儿语义与 data_contracts 聚合测试消费；孤儿行不是语义对象）。
    - ``runtime_container_host``：FEATURE-NAV-HOST（仅 container surface）
      的 verify_mode。默认 "RUNTIME"（任务书原样——Gate 3 规则 1 的
      容器反例形态）；传 "SOURCE_CONFIRM" 得到全绿基线形态（迁移后
      需要 Gate 3 PASS 的链使用）。
    """
    project = root / "android-project"
    (project / "app" / "src" / "main").mkdir(parents=True)
    source_lines = [f"// fixture line {number}" for number in range(1, 31)]
    source_lines[9] = "fun renderLogin() = Unit"
    (project / "app" / "Login.kt").write_text("\n".join(source_lines) + "\n", encoding="utf-8")
    (project / "settings.gradle").write_text("rootProject.name='Fixture'\n", encoding="utf-8")
    (project / "app" / "build.gradle").write_text(
        "plugins { id 'com.android.application' }\n", encoding="utf-8"
    )
    (project / "app" / "src" / "main" / "AndroidManifest.xml").write_text(
        '<manifest package="com.example.fixture"><application /></manifest>\n',
        encoding="utf-8",
    )
    asset_source = project / "app" / "src" / "main" / "res" / "drawable" / "login_logo.svg"
    asset_source.parent.mkdir(parents=True)
    asset_source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32">'
        '<circle cx="16" cy="16" r="14" fill="#3367D6"/></svg>\n',
        encoding="utf-8",
    )
    run("git", "init", "-q", str(project))
    run("git", "-C", str(project), "config", "user.email", "fixture@example.invalid")
    run("git", "-C", str(project), "config", "user.name", "Fixture")
    run("git", "-C", str(project), "add", ".")
    run("git", "-C", str(project), "commit", "-q", "-m", "fixture baseline")
    revision = run("git", "-C", str(project), "rev-parse", "HEAD").stdout.strip()

    apk = root / "fixture.apk"
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"binary-manifest-fixture")
        archive.writestr("classes.dex", b"dex\n035\x00fixture")

    created = run(
        sys.executable,
        str(CONTROLLER_SKILL / "scripts" / "init_migration.py"),
        "--output", str(root / "runs"),
        "--project-root", str(project),
        "--project-name", "Fixture",
        "--run-id", "MIG-STAGE3-TEST",
    )
    run_dir = Path(json.loads(created.stdout)["run_dir"])
    scope_path = run_dir / "controller" / "scope.json"
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    scope["android"].update(
        {
            "source_revision": revision,
            "source_revision_kind": "git-commit",
            "apk_path": str(apk),
            "apk_sha256": sha256(apk),
            "application_id": "com.example.fixture",
            "app_version": "1.0.0",
            "app_build": "100",
            "build_variant": "debug",
        }
    )
    scope["target"]["sdk_or_api_target"] = "API-TEST"
    # v3 链范式：三个 included feature 对应 feature-map 的三种范式形态——
    # RUNTIME 双 surface（page+sheet）/ RUNTIME 仅容器 surface / SOURCE_CONFIRM。
    scope["migration_scope"]["included_features"] = [
        "FEATURE-AUTH", "FEATURE-NAV-HOST", "FEATURE-SETTINGS-THEME",
    ]
    scope["migration_scope"]["excluded_features"] = []
    # 模板默认值为 __FILL__ 占位（validate_stage4 拒绝未解析占位符），必须覆盖为真实值
    scope["migration_scope"]["key_business_capabilities"] = ["CAP-AUTH-SIGNIN"]
    scope["migration_scope"]["allowed_platform_substitutions"] = []
    scope["ownership"] = {
        "migration_controller_id": "migration-controller-1",
        "inventory_lead_id": "inventory-lead-1",
        "code_map_agent_id": "code-map-agent-1",
        "runtime_state_agent_ids": ["runtime-state-agent-1"],
        "business_rule_agent_id": "business-rule-agent-1",
        "data_dependency_agent_id": "data-dependency-agent-1",
        "evidence_administrator_id": "evidence-administrator-1",
        "coverage_checker_id": "coverage-checker-1",
    }
    scope["pending_confirmations"] = []
    scope["tool_policy"]["apk_analyzer_bin"] = str(FAKE_ANDROID)
    scope["environments"][0].update(
        {
            "account_id": "ACCOUNT-TEST",
            "account_role": "USER",
            "seed_data_id": "SEED-AUTH-01",
            "seed_reset_ref": "docs/seed-auth.md",
            "network_conditions_ref": "normal-network-profile",
            "network_toggle_available": True,
            "emulator_model": "Pixel-Test",
            "device_serial": "emulator-5554",
            "resolution": "1080x2400",
            "density_dpi": 420,
            "android_api_level": 35,
            "orientation": "portrait",
        }
    )
    scope_path.write_text(json.dumps(scope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    run(
        sys.executable, str(CONTROLLER_SKILL / "scripts" / "validate_gate.py"),
        "--run-dir", str(run_dir), "--phase", "1", "--write",
    )
    record_human_approval(run_dir, 1, "HREV-PHASE-01-SCAFFOLD")
    issued = run(
        sys.executable, str(CONTROLLER_SKILL / "scripts" / "issue_phase2_work_order.py"),
        "--run-dir", str(run_dir), "--issued-by", "migration-controller-1",
    )
    phase2_work_order = Path(json.loads(issued.stdout)["work_order"])
    initialized = run(
        sys.executable, str(INVENTORY_SKILL / "scripts" / "init_inventory.py"),
        "--run-dir", str(run_dir), "--scope", str(scope_path),
        "--work-order", str(phase2_work_order), "--frozen-by", "inventory-lead-1",
        "--android-bin", str(FAKE_ANDROID),
    )
    workspace = Path(json.loads(initialized.stdout)["workspace"])
    asset_mapping = root / "asset-mapping.json"
    asset_mapping.write_text(json.dumps({
        "schema_version": 1,
        "assets": [{
            "asset_id": "ASSET-AUTH-LOGO",
            "source_path": "app/src/main/res/drawable/login_logo.svg",
            "source_sha256": sha256(asset_source),
            "asset_type": "VECTOR_IMAGE",
            "feature_ids": ["FEATURE-AUTH"],
            "page_ids": ["PAGE-LOGIN"],
            "state_ids": ["STATE-DEFAULT"],
            "notes": "Real asset fixture",
        }],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run(
        sys.executable, str(INVENTORY_SKILL / "scripts" / "archive_assets.py"),
        "--workspace", str(workspace), "--mapping", str(asset_mapping),
        "--archived-by", "code-map-agent-1",
    )
    run(
        sys.executable, str(INVENTORY_SKILL / "scripts" / "attest_environment.py"),
        "--workspace", str(workspace), "--env-id", "ENV-001",
        "--inventory-lead-id", "inventory-lead-1", "--account-ready", "--seed-ready",
        "--network-ready", "--permissions-ready", "--notes", "fixture ready",
    )

    steps = root / "login-steps.md"
    steps.write_text("1. Launch the signed-out app.\n2. Observe the login form.\n", encoding="utf-8")
    # v3 链范式：每个 included feature 一条独立 evidence（build_inventory
    # 要求 Evidence-ID 与 inventory 行一一对应，禁止一证多行）。
    feature_inventory_ids = {
        "FEATURE-AUTH": "INV-AUTH-LOGIN-DEFAULT",
        "FEATURE-NAV-HOST": "INV-NAVHOST-LOGIN-DEFAULT",
        "FEATURE-SETTINGS-THEME": "INV-THEME-LOGIN-DEFAULT",
    }
    evidence_ids: dict[str, str] = {}
    for feature_id, inventory_id in feature_inventory_ids.items():
        captured = run(
            sys.executable, str(INVENTORY_SKILL / "scripts" / "capture_state.py"),
            "--workspace", str(workspace), "--inventory-id", inventory_id,
            "--feature-id", feature_id, "--page-id", "PAGE-LOGIN",
            "--state-id", "STATE-DEFAULT", "--env-id", "ENV-001", "--steps", str(steps),
            "--issued-by", "evidence-administrator-1", "--captured-by", "runtime-state-agent-1",
            "--launch", "--android-bin", str(FAKE_ANDROID), "--adb-bin", str(FAKE_ANDROID),
        )
        evidence_ids[feature_id] = json.loads(captured.stdout)["evidence_id"]
    for anchor_evidence_id in evidence_ids.values():
        run(
            sys.executable, str(CONTROLLER_SKILL / "scripts" / "anchor_phase2_evidence.py"),
            "--run-dir", str(run_dir), "--evidence-id", anchor_evidence_id,
            "--anchored-by", "migration-controller-1",
        )

    claims = [
        {
            "inventory_id": "INV-AUTH-LOGIN-DEFAULT",
            "feature_id": "FEATURE-AUTH",
            "feature_name": "Authentication",
            "page_id": "PAGE-LOGIN",
            "page_name": "Login",
            "state_id": "STATE-DEFAULT",
            "state_name": "Default",
            "env_id": "ENV-001",
            "evidence_id": evidence_ids["FEATURE-AUTH"],
            "entry_condition": "App opened while signed out",
            "action_summary": "Open login",
            "expected_observable": "Login form is visible",
            "actual_observable": "Login form is visible",
            "code_refs": ["app/Login.kt:10"],
            "business_rule_refs": ["BR-AUTH-NONE"],
            "data_dependency_refs": ["DATA-AUTH-NONE"],
            "system_capability_refs": ["SYS-AUTH-NONE"],
            "third_party_dependency_refs": ["SDK-AUTH-NONE"],
            "asset_ids": ["ASSET-AUTH-LOGO"],
            "responsible_agent": "runtime-state-agent-1",
            "row_status": "CAPTURED",
        },
        {
            # v3 链范式：容器宿主 feature 与 SOURCE_CONFIRM feature 的
            # inventory 行（page 复用 fixture 唯一 active 页 PAGE-LOGIN，
            # 满足 validate_evidence 的 feature/environment state-row 门禁）。
            "inventory_id": "INV-NAVHOST-LOGIN-DEFAULT",
            "feature_id": "FEATURE-NAV-HOST",
            "feature_name": "Navigation host",
            "page_id": "PAGE-LOGIN",
            "page_name": "Login",
            "state_id": "STATE-DEFAULT",
            "state_name": "Default",
            "env_id": "ENV-001",
            "evidence_id": evidence_ids["FEATURE-NAV-HOST"],
            "entry_condition": "Host tab bar visible",
            "action_summary": "Switch host tab",
            "expected_observable": "Tab content visible",
            "actual_observable": "Tab content visible",
            "code_refs": ["app/Login.kt:11"],
            "business_rule_refs": ["BR-NAVHOST-NONE"],
            "data_dependency_refs": ["DATA-NAVHOST-NONE"],
            "system_capability_refs": ["SYS-NAVHOST-NONE"],
            "third_party_dependency_refs": ["SDK-NAVHOST-NONE"],
            "asset_ids": ["NONE_FOUND"],
            "responsible_agent": "runtime-state-agent-1",
            "row_status": "CAPTURED",
        },
        {
            "inventory_id": "INV-THEME-LOGIN-DEFAULT",
            "feature_id": "FEATURE-SETTINGS-THEME",
            "feature_name": "Theme setting",
            "page_id": "PAGE-LOGIN",
            "page_name": "Login",
            "state_id": "STATE-DEFAULT",
            "state_name": "Default",
            "env_id": "ENV-001",
            "evidence_id": evidence_ids["FEATURE-SETTINGS-THEME"],
            "entry_condition": "Settings row visible",
            "action_summary": "Open theme row",
            "expected_observable": "Theme options listed",
            "actual_observable": "Theme options listed",
            "code_refs": ["app/Login.kt:12"],
            "business_rule_refs": ["BR-THEME-NONE"],
            "data_dependency_refs": ["DATA-THEME-NONE"],
            "system_capability_refs": ["SYS-THEME-NONE"],
            "third_party_dependency_refs": ["SDK-THEME-NONE"],
            "asset_ids": ["NONE_FOUND"],
            "responsible_agent": "runtime-state-agent-1",
            "row_status": "CAPTURED",
        },
    ]
    claims_path = workspace / "claims" / "auth.json"
    claims_path.write_text(json.dumps(claims, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run(
        sys.executable, str(INVENTORY_SKILL / "scripts" / "build_inventory.py"),
        "--workspace", str(workspace), "--claims", str(claims_path),
    )

    write_csv(
        workspace / "coverage-ledger.csv",
        [
            "feature_id", "feature_name", "applicable_env_ids", "code_mapped",
            "runtime_states_captured", "business_rules_mapped", "data_dependencies_mapped",
            "status", "owner", "notes",
        ],
        [
            {
                "feature_id": "FEATURE-AUTH", "feature_name": "Authentication",
                "applicable_env_ids": '["ENV-001"]', "code_mapped": "true",
                "runtime_states_captured": "true", "business_rules_mapped": "true",
                "data_dependencies_mapped": "true", "status": "COMPLETE",
                "owner": "inventory-lead-1", "notes": "Fixture coverage",
            },
            {
                "feature_id": "FEATURE-NAV-HOST", "feature_name": "Navigation host",
                "applicable_env_ids": '["ENV-001"]', "code_mapped": "true",
                "runtime_states_captured": "true", "business_rules_mapped": "true",
                "data_dependencies_mapped": "true", "status": "COMPLETE",
                "owner": "inventory-lead-1", "notes": "Container host coverage",
            },
            {
                "feature_id": "FEATURE-SETTINGS-THEME", "feature_name": "Theme setting",
                "applicable_env_ids": '["ENV-001"]', "code_mapped": "true",
                "runtime_states_captured": "true", "business_rules_mapped": "true",
                "data_dependencies_mapped": "true", "status": "COMPLETE",
                "owner": "inventory-lead-1", "notes": "Source-confirm coverage",
            },
        ],
    )
    write_csv(
        workspace / "catalogs" / "code-map.csv",
        [
            "code_ref", "feature_id", "page_id", "state_candidate_id", "component_type",
            "symbol", "file_path", "line", "coverage_disposition", "owner", "status", "notes",
        ],
        [
            {
                "code_ref": "app/Login.kt:10", "feature_id": "FEATURE-AUTH",
                "page_id": "PAGE-LOGIN", "state_candidate_id": "STATE-DEFAULT",
                "component_type": "function", "symbol": "renderLogin", "file_path": "app/Login.kt",
                "line": "10", "coverage_disposition": "IN_SCOPE", "owner": "code-map-agent-1",
                "status": "VERIFIED", "notes": "Runtime correlated",
            },
            {
                "code_ref": "app/Login.kt:11", "feature_id": "FEATURE-NAV-HOST",
                "page_id": "PAGE-LOGIN", "state_candidate_id": "STATE-DEFAULT",
                "component_type": "function", "symbol": "renderLogin", "file_path": "app/Login.kt",
                "line": "11", "coverage_disposition": "IN_SCOPE", "owner": "code-map-agent-1",
                "status": "VERIFIED", "notes": "Host tab correlated",
            },
            {
                "code_ref": "app/Login.kt:12", "feature_id": "FEATURE-SETTINGS-THEME",
                "page_id": "PAGE-LOGIN", "state_candidate_id": "STATE-DEFAULT",
                "component_type": "function", "symbol": "renderLogin", "file_path": "app/Login.kt",
                "line": "12", "coverage_disposition": "IN_SCOPE", "owner": "code-map-agent-1",
                "status": "VERIFIED", "notes": "Theme row correlated",
            }
        ],
    )
    write_csv(
        workspace / "catalogs" / "business-rules.csv",
        [
            "business_rule_id", "feature_id", "page_id", "state_id", "condition", "outcome",
            "code_refs", "test_refs", "owner", "status", "notes",
        ],
        [
            {
                "business_rule_id": "BR-AUTH-NONE", "feature_id": "FEATURE-AUTH",
                "page_id": "PAGE-LOGIN", "state_id": "STATE-DEFAULT", "condition": "NONE_FOUND",
                "outcome": "NO_RULE_BEYOND_VISIBLE_STATE", "code_refs": '["app/Login.kt:10"]',
                "test_refs": "[]", "owner": "business-rule-agent-1", "status": "VERIFIED",
                "notes": "Explicit no-rule audit",
            },
            {
                "business_rule_id": "BR-NAVHOST-NONE", "feature_id": "FEATURE-NAV-HOST",
                "page_id": "PAGE-LOGIN", "state_id": "STATE-DEFAULT", "condition": "NONE_FOUND",
                "outcome": "NO_RULE_BEYOND_VISIBLE_STATE", "code_refs": '["app/Login.kt:11"]',
                "test_refs": "[]", "owner": "business-rule-agent-1", "status": "VERIFIED",
                "notes": "Explicit no-rule audit",
            },
            {
                "business_rule_id": "BR-THEME-NONE", "feature_id": "FEATURE-SETTINGS-THEME",
                "page_id": "PAGE-LOGIN", "state_id": "STATE-DEFAULT", "condition": "NONE_FOUND",
                "outcome": "NO_RULE_BEYOND_VISIBLE_STATE", "code_refs": '["app/Login.kt:12"]',
                "test_refs": "[]", "owner": "business-rule-agent-1", "status": "VERIFIED",
                "notes": "Explicit no-rule audit",
            },
        ],
    )
    write_csv(
        workspace / "catalogs" / "data-dependencies.csv",
        [
            "data_dependency_id", "feature_id", "dependency_type", "name", "direction",
            "source_ref", "sensitive", "migration_risk", "owner", "status", "notes",
        ],
        [
            {
                "data_dependency_id": "DATA-AUTH-NONE", "feature_id": "FEATURE-AUTH",
                "dependency_type": "NONE", "name": "NONE_FOUND", "direction": "NONE",
                "source_ref": "app/Login.kt:10", "sensitive": "false", "migration_risk": "none",
                "owner": "data-dependency-agent-1", "status": "VERIFIED", "notes": "No dependency",
            },
            {
                "data_dependency_id": "DATA-NAVHOST-NONE", "feature_id": "FEATURE-NAV-HOST",
                "dependency_type": "NONE", "name": "NONE_FOUND", "direction": "NONE",
                "source_ref": "app/Login.kt:11", "sensitive": "false", "migration_risk": "none",
                "owner": "data-dependency-agent-1", "status": "VERIFIED", "notes": "No dependency",
            },
            {
                "data_dependency_id": "DATA-THEME-NONE", "feature_id": "FEATURE-SETTINGS-THEME",
                "dependency_type": "NONE", "name": "NONE_FOUND", "direction": "NONE",
                "source_ref": "app/Login.kt:12", "sensitive": "false", "migration_risk": "none",
                "owner": "data-dependency-agent-1", "status": "VERIFIED", "notes": "No dependency",
            },
        ],
    )
    write_csv(
        workspace / "catalogs" / "system-capabilities.csv",
        [
            "system_capability_id", "feature_id", "capability_type", "name",
            "permission_or_api", "source_ref", "migration_risk", "owner", "status", "notes",
        ],
        [
            {
                "system_capability_id": "SYS-AUTH-NONE", "feature_id": "FEATURE-AUTH",
                "capability_type": "NONE", "name": "NONE_FOUND", "permission_or_api": "NONE",
                "source_ref": "app/Login.kt:10", "migration_risk": "none",
                "owner": "data-dependency-agent-1", "status": "VERIFIED", "notes": "No capability",
            },
            {
                "system_capability_id": "SYS-NAVHOST-NONE", "feature_id": "FEATURE-NAV-HOST",
                "capability_type": "NONE", "name": "NONE_FOUND", "permission_or_api": "NONE",
                "source_ref": "app/Login.kt:11", "migration_risk": "none",
                "owner": "data-dependency-agent-1", "status": "VERIFIED", "notes": "No capability",
            },
            {
                "system_capability_id": "SYS-THEME-NONE", "feature_id": "FEATURE-SETTINGS-THEME",
                "capability_type": "NONE", "name": "NONE_FOUND", "permission_or_api": "NONE",
                "source_ref": "app/Login.kt:12", "migration_risk": "none",
                "owner": "data-dependency-agent-1", "status": "VERIFIED", "notes": "No capability",
            },
        ],
    )
    write_csv(
        workspace / "catalogs" / "third-party-dependencies.csv",
        [
            "third_party_dependency_id", "feature_id", "name", "version", "purpose",
            "source_ref", "data_shared", "migration_risk", "owner", "status", "notes",
        ],
        [
            {
                "third_party_dependency_id": "SDK-AUTH-NONE", "feature_id": "FEATURE-AUTH",
                "name": "NONE_FOUND", "version": "NONE", "purpose": "NONE",
                "source_ref": "app/Login.kt:10", "data_shared": "false", "migration_risk": "none",
                "owner": "data-dependency-agent-1", "status": "VERIFIED", "notes": "No SDK",
            },
            {
                "third_party_dependency_id": "SDK-NAVHOST-NONE", "feature_id": "FEATURE-NAV-HOST",
                "name": "NONE_FOUND", "version": "NONE", "purpose": "NONE",
                "source_ref": "app/Login.kt:11", "data_shared": "false", "migration_risk": "none",
                "owner": "data-dependency-agent-1", "status": "VERIFIED", "notes": "No SDK",
            },
            {
                "third_party_dependency_id": "SDK-THEME-NONE", "feature_id": "FEATURE-SETTINGS-THEME",
                "name": "NONE_FOUND", "version": "NONE", "purpose": "NONE",
                "source_ref": "app/Login.kt:12", "data_shared": "false", "migration_risk": "none",
                "owner": "data-dependency-agent-1", "status": "VERIFIED", "notes": "No SDK",
            },
        ],
    )

    static = workspace / "static-analysis"
    static_artifacts = {
        "project-index.json": {
            "schema_version": 1, "source_revision": revision, "generated_by": "code-map-agent-1",
        },
        "pages.json": {"schema_version": 1, "pages": [{
            "page_id": "PAGE-LOGIN", "symbol": "LoginActivity",
            "kinds": ["ACTIVITY"],
            "candidate_feature_ids": ["FEATURE-AUTH"],
        }]},
        "components.json": {"schema_version": 1, "components": [{
            "component_id": "COMP-LOGIN-ROOT", "page_id": "PAGE-LOGIN",
            "resource_id": "login", "text": "Login", "type": "TextView", "attributes": {},
        }]},
        "events.json": {"schema_version": 1, "events": []},
        "transitions.json": {"schema_version": 1, "transitions": []},
        "state-candidates.json": {"schema_version": 1, "states": [{
            "state_id": "STATE-DEFAULT", "page_id": "PAGE-LOGIN",
        }]},
        "runtime-tasks.json": {"schema_version": 1, "tasks": [{
            "task_id": "RTASK-PAGE-LOGIN", "task_type": "VERIFY_PAGE_DEFAULT_STATE",
            "subject_id": "PAGE-LOGIN", "page_id": "PAGE-LOGIN",
        }]},
        "advanced-analysis.json": {
            "schema_version": 1, "dynamic_risks": [], "side_effects": [], "scenarios": [],
        },
    }
    for name, value in static_artifacts.items():
        (static / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    (static / "code-map.candidates.csv").write_text("code_ref\n", encoding="utf-8")
    static_names = sorted([*static_artifacts, "code-map.candidates.csv"])
    (static / "manifest.sha256").write_text(
        "".join(f"{sha256(static / name)}  {name}\n" for name in static_names), encoding="utf-8"
    )
    (static / "COMMITTED").write_text(sha256(static / "manifest.sha256") + "\n", encoding="utf-8")
    (workspace / "runtime-observations.json").write_text(json.dumps({
        "schema_version": 1,
        "observations": [
            {
                "observation_id": "OBS-PAGE-LOGIN", "subject_type": "PAGE",
                "subject_id": "PAGE-LOGIN", "page_id": "PAGE-LOGIN", "env_id": "ENV-001",
                "before_evidence_id": "", "after_evidence_id": evidence_ids["FEATURE-AUTH"],
                "locator_field": "", "locator_value": "", "locator_occurrence": 0,
            },
            {
                "observation_id": "OBS-STATE-LOGIN-DEFAULT", "subject_type": "STATE",
                "subject_id": "STATE-DEFAULT", "page_id": "PAGE-LOGIN", "env_id": "ENV-001",
                "before_evidence_id": "", "after_evidence_id": evidence_ids["FEATURE-AUTH"],
                "locator_field": "", "locator_value": "", "locator_occurrence": 0,
            },
            {
                "observation_id": "OBS-COMP-LOGIN", "subject_type": "COMPONENT",
                "subject_id": "COMP-LOGIN-ROOT", "page_id": "PAGE-LOGIN", "env_id": "ENV-001",
                "before_evidence_id": "", "after_evidence_id": evidence_ids["FEATURE-AUTH"],
                "locator_field": "", "locator_value": "", "locator_occurrence": 0,
            },
        ],
    }, indent=2) + "\n", encoding="utf-8")

    # 新范式 Gate 2 五件套（#41 起为 validate_gate --phase 2 消费；#47/#52 升级
    # 为 v3 链范式完整形态——三种 feature 形态 + BC v2 列 + 孤儿开关行 +
    # navigation-relations 最小行）。注意：必须在 validate_evidence（旧链
    # 闭包快照）之前写入，否则 Phase 3 的 immutability 检查视为闭包后新增文件。
    write_csv(workspace / "behavior-contracts.csv", [
        # BC 列结构（v4 17 列，任务 #59 与 G 的 build_behavior_contracts.py
        # BC_FIELDS 对齐）：旧 16 列全部保留，尾部追加 v4 七段结构新增的
        # semantic_input（语义输入描述；DictReader 兼容，缺值仅警告不阻断）。
        "bc_id", "feature_id", "page_ref", "user_intent", "pre_state",
        "operation", "data_state_change", "business_computation_refs",
        "observable_result", "persistence_targets", "external_side_effects",
        "evidence_class", "impact", "source_refs",
        "operation_steps", "result_assertions",
        "semantic_input",
    ], [
        {
            "bc_id": "BC-FIXTURE-1", "feature_id": "FEATURE-AUTH",
            "page_ref": "PAGE-LOGIN", "user_intent": "login",
            "pre_state": "logged out", "operation": "tap login",
            "data_state_change": "session token stored",
            "business_computation_refs": "",
            "observable_result": "home visible", "persistence_targets": "session",
            "external_side_effects": "none", "evidence_class": "RUNTIME_REQUIRED",
            "impact": "high", "source_refs": "app/Login.kt:10",
            "operation_steps": '[{"action": "tap", "target": "login"}]',
            "result_assertions": '[{"kind": "text_visible", "value": "home"}]',
            "semantic_input": "在登录表单输入账号 fixture-auth 并点击登录",
        },
        {
            # 容器宿主 feature 的 BC：page_ref 仍必须解析到 inventory 页面
            # （PAGE-LOGIN 是 fixture 唯一 active inventory Page-ID）。
            "bc_id": "BC-FIXTURE-2", "feature_id": "FEATURE-NAV-HOST",
            "page_ref": "PAGE-LOGIN", "user_intent": "switch host tab",
            "pre_state": "home tab active", "operation": "tap tab",
            "data_state_change": "none", "business_computation_refs": "",
            "observable_result": "tab content visible", "persistence_targets": "",
            "external_side_effects": "none", "evidence_class": "RUNTIME_REQUIRED",
            "impact": "normal", "source_refs": "app/Login.kt:11",
            "operation_steps": '[{"action": "tap", "target": "tab"}]',
            "result_assertions": '[{"kind": "text_visible", "value": "tab"}]',
            "semantic_input": "点击宿主容器底部 tab 切换到目标分页",
        },
        {
            # SOURCE_CONFIRM feature 的 BC：静态确认链（无需 runtime 对账行）。
            "bc_id": "BC-FIXTURE-3", "feature_id": "FEATURE-SETTINGS-THEME",
            "page_ref": "PAGE-LOGIN", "user_intent": "view theme setting",
            "pre_state": "settings open", "operation": "open theme row",
            "data_state_change": "none", "business_computation_refs": "",
            "observable_result": "theme options listed",
            "persistence_targets": "mmkv:theme_mode",
            "external_side_effects": "none", "evidence_class": "STATIC_ONLY",
            "impact": "normal", "source_refs": "app/Login.kt:12",
            "operation_steps": '[{"action": "tap", "target": "theme"}]',
            "result_assertions": '[{"kind": "text_visible", "value": "theme"}]',
            "semantic_input": "在设置列表中点击主题选项行",
        },
    ])
    write_csv(workspace / "reconciliation.csv", [
        "bc_id", "feature_id", "page_ref", "verify_side",
        "verdict", "evidence_ref", "runtime_status", "note",
    ], [
        {
            "bc_id": "BC-FIXTURE-1", "feature_id": "FEATURE-AUTH",
            "page_ref": "PAGE-LOGIN", "verify_side": "FEATURE_MAP",
            "verdict": "CONFIRMED", "evidence_ref": "chains/BC-FIXTURE-1",
            "runtime_status": "CHAIN_PASS", "note": "",
        },
        {
            "bc_id": "BC-FIXTURE-2", "feature_id": "FEATURE-NAV-HOST",
            "page_ref": "PAGE-LOGIN", "verify_side": "FEATURE_MAP",
            "verdict": "CONFIRMED", "evidence_ref": "chains/BC-FIXTURE-2",
            "runtime_status": "CHAIN_PASS", "note": "",
        },
    ])
    # data-relations v3：真实 7 列 schema（HOME-FULL-RUN1 权威）+ 旧 5 列键
    # 全保留（direction/risk 供 validate_gate 规则 4 等旧消费方读取）。
    data_relation_rows = [
        {
            "relation_id": "REL-FIX-0001", "feature_id": "FEATURE-AUTH",
            "data_object": "mmkv:session_token", "relation": "write",
            "direction": "write", "persistence_kind": "mmkv_key",
            "persistence_location": "SettingsManager.session_token",
            "risk": "high", "source_ref": "app/Login.kt:10",
        },
        {
            "relation_id": "REL-FIX-0002", "feature_id": "FEATURE-AUTH",
            "data_object": "account_profile", "relation": "read",
            "direction": "read", "persistence_kind": "room_table",
            "persistence_location": "account_profile",
            "risk": "normal", "source_ref": "app/Login.kt:11",
        },
        {
            "relation_id": "REL-FIX-0003", "feature_id": "FEATURE-SETTINGS-THEME",
            "data_object": "mmkv:theme_mode", "relation": "write",
            "direction": "write", "persistence_kind": "mmkv_key",
            "persistence_location": "SettingsManager.theme_mode",
            "risk": "normal", "source_ref": "app/Login.kt:12",
        },
    ]
    if orphan_toggle:
        # 故意孤儿场景的开关参数：feature_id 为空的 mmkv toggle 写入。
        # 真实 run 中孤儿行是常态（泛化 DAO/settings 行未绑定 feature）；
        # Gate 3 规则 2 的语义对象集要求 feature_id+data_object 双非空，
        # 因此孤儿行不构成语义对象，也不得让契约层产生孤儿契约。
        data_relation_rows.append(
            {
                "relation_id": "REL-FIX-0004", "feature_id": "",
                "data_object": "settings", "relation": "write",
                "direction": "write", "persistence_kind": "mmkv_key",
                "persistence_location": "demo_mode_enabled",
                "risk": "normal", "source_ref": "app/Login.kt:13",
            }
        )
    write_csv(
        workspace / "data-relations.csv",
        [
            "relation_id", "feature_id", "data_object", "relation", "direction",
            "persistence_kind", "persistence_location", "risk", "source_ref",
        ],
        data_relation_rows,
    )
    # navigation-relations 最小行：PAGE-LOGIN → sheet surface 的显式跳转边
    # （main_v3 的 nav-explicit-edge 宿主推断输入；两端命中 surface 清单）。
    write_csv(
        workspace / "candidates" / "navigation-relations.candidates.csv",
        [
            "candidate_id", "from_page_id", "from_page_symbol", "to_page_id",
            "trigger", "action", "relation_type", "source_ref",
        ],
        [
            {
                "candidate_id": "NAV-CAND-001", "from_page_id": "PAGE-LOGIN",
                "from_page_symbol": "LoginActivity",
                "to_page_id": "PAGE-AUTH-ACCOUNT-SHEET",
                "trigger": "tap account avatar", "action": "open account sheet",
                "relation_type": "OPEN_SHEET", "source_ref": "app/Login.kt:10",
            }
        ],
    )
    # feature-map.json v3：三种范式形态各一——RUNTIME 双 surface（page+sheet）、
    # RUNTIME 仅 container surface（容器规则素材）、SOURCE_CONFIRM。
    # 旧键（verify_mode/risk/risk_level/source_refs/name/status）保留给旧消费方。
    (workspace / "feature-map.json").write_text(json.dumps({
        "schema_version": 1,
        "coverage_gate": {
            "included_features_covered": True,
            "included": [
                "FEATURE-AUTH", "FEATURE-NAV-HOST", "FEATURE-SETTINGS-THEME",
            ],
        },
        "features": [
            {
                "feature_id": "FEATURE-AUTH", "name": "auth",
                "summary": "login with persisted session and account sheet",
                "source_refs": ["app/Login.kt:10"],
                "surfaces": [
                    {"id": "PAGE-LOGIN", "kind": "page", "is_container": False},
                    {"id": "PAGE-AUTH-ACCOUNT-SHEET", "kind": "sheet", "is_container": False},
                ],
                "data_objects": {
                    "writes": ["mmkv:session_token"], "reads": ["account_profile"],
                },
                "risk_level": "high", "risk": "high", "verify_mode": "RUNTIME",
                "status": "OPEN",
                "_verify_mode_reason": "session persistence - migration-prone",
            },
            {
                "feature_id": "FEATURE-NAV-HOST", "name": "navigation host",
                "summary": "container-only host surface for tab navigation",
                "source_refs": ["app/Login.kt:11"],
                "surfaces": [
                    {"id": "PAGE-MAIN-HOST", "kind": "container", "is_container": True},
                ],
                "data_objects": {"writes": [], "reads": []},
                "risk_level": "normal", "risk": "normal",
                "verify_mode": runtime_container_host,
                "status": "OPEN",
                "_verify_mode_reason": (
                    "container host only (transparent passthrough; no own shell)"
                ),
            },
            {
                "feature_id": "FEATURE-SETTINGS-THEME", "name": "theme setting",
                "summary": "static theme preference row, source confirmed",
                "source_refs": ["app/Login.kt:12"],
                "surfaces": [
                    {"id": "PAGE-SETTINGS-THEME", "kind": "page", "is_container": False},
                ],
                "data_objects": {"writes": ["mmkv:theme_mode"], "reads": []},
                "risk_level": "normal", "risk": "normal",
                "verify_mode": "SOURCE_CONFIRM",
                "status": "OPEN",
                "_verify_mode_reason": "pure display of persisted preference",
            },
        ],
    }, ensure_ascii=False), encoding="utf-8")
    (workspace / "phase-2-closure.json").write_text(json.dumps({
        "generator": "gmi_closure",
        # gate 键双写：audit_discrepancy（单数，init_scaffold v3/main_v3 与
        # 真实 gmi run 的判定键）+ audit_discrepancies（旧 #41 键，保留）。
        "gate": {"visited": 3, "pages_total": 4, "audit_discrepancy": 0,
                 "audit_discrepancies": 0, "coverage_gaps": 0, "unmapped": 0},
        # validate_stage3 v3 的闭包快照判定键（Frozen Phase 2 closure is not PASS）。
        "final_verdict": "PASS",
        "evidence_chain_closed": True,
        "gaps": [], "conflicts_explained": [],
        "artifact_hashes": {
            "candidates_dir_sha256": "", "coverage_ledger_sha256": "",
            "runtime_evidence_dir_sha256": "",
            "behavior_contracts_sha256": sha256(workspace / "behavior-contracts.csv"),
            "phase2_report_sha256": "",
            "reconciliation_sha256": sha256(workspace / "reconciliation.csv"),
        },
    }, ensure_ascii=False), encoding="utf-8")
    run(
        sys.executable, str(INVENTORY_SKILL / "scripts" / "validate_evidence.py"),
        "--workspace", str(workspace), "--reviewer", "coverage-checker-1", "--decision", "PASS",
        "--attest-visual-review", "--attest-source-runtime-crosscheck",
    )
    run(
        sys.executable, str(CONTROLLER_SKILL / "scripts" / "validate_gate.py"),
        "--run-dir", str(run_dir), "--phase", "2", "--write",
    )
    # v3 布局盖章（#47/#52）：必须在 human review 绑定 gate-report 之前完成，
    # 否则 review/工单哈希链与 init_scaffold v3 的三方一致前置互相矛盾。
    _stamp_v3_run_layout(run_dir)
    record_human_approval(run_dir, 2, "HREV-PHASE-02-SCAFFOLD")
    phase2_receipts = [
        ("inventory_lead_id", "inventory-lead-1", "TASK-P2-LEAD", workspace / "phase-manifest.json"),
        ("code_map_agent_id", "code-map-agent-1", "TASK-P2-CODE", workspace / "static-analysis" / "COMMITTED"),
        ("runtime_state_agent_ids", "runtime-state-agent-1", "TASK-P2-RUNTIME", workspace / "evidence-index.csv"),
        ("business_rule_agent_id", "business-rule-agent-1", "TASK-P2-RULE", workspace / "catalogs" / "business-rules.csv"),
        ("data_dependency_agent_id", "data-dependency-agent-1", "TASK-P2-DATA", workspace / "catalogs" / "data-dependencies.csv"),
        ("evidence_administrator_id", "evidence-administrator-1", "TASK-P2-EVIDENCE", workspace / "evidence-index.csv"),
        ("coverage_checker_id", "coverage-checker-1", "TASK-P2-COVERAGE", workspace / "closure-report.json"),
    ]
    for role_key, actor_id, task_id, artifact in phase2_receipts:
        record_team_receipt(run_dir, phase2_work_order, role_key, actor_id, task_id, artifact)
    return run_dir, scope_path


def _stamp_v3_run_layout(run_dir: Path) -> Path:
    """v3 布局盖章（内部步骤，真实 gmi run 收尾形态）。

    init_scaffold v3 单路径的前置是三方一致的冻结闭包（对齐真实
    HOME-FULL-RUN1 布局）：
      1. workspace 的 phase-2-closure.json 规范化后落到 run 根；
      2. run-manifest.json 盖 phase2_closure_gate 章（== closure.gate）；
      3. controller/gate-report.json 的 gate 字段与冻结 closure 对齐。
    只动 run 根与 controller 层文件，不改 workspace（Phase 2 闭包快照
    不可变面不受影响）。调用时机：validate_gate --write 之后、
    record_human_approval(2) 之前（review/工单绑定最终 gate-report）。
    """
    workspace = run_dir / "phase-02-android-inventory"
    closure = json.loads(
        (workspace / "phase-2-closure.json").read_text(encoding="utf-8")
    )
    closure["gate"].setdefault("audit_discrepancy", 0)
    closure["workspace"] = str(workspace)
    closure_text = json.dumps(closure, ensure_ascii=False, indent=2) + "\n"
    run_root_closure = run_dir / "phase-2-closure.json"
    run_root_closure.write_text(closure_text, encoding="utf-8")

    manifest_path = run_dir / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["phase2_closure_gate"] = closure["gate"]
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    gate_report_path = run_dir / "controller" / "gate-report.json"
    report = json.loads(gate_report_path.read_text(encoding="utf-8"))
    report["phase"] = 2
    report["verdict"] = "PASS"
    report["gate"] = closure["gate"]
    gate_report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return run_root_closure


def enable_v3_paradigm(run_dir: Path) -> Path:
    """幂等入口：v3 布局已在 build_closed_phase2 内盖章时直接返回。

    build_closed_phase2 现在默认产出 v3 布局（#52：v3 唯一路径）；本函数
    仅为旧调用形态保留——重复调用不重复盖章（gate-report 哈希不能再变，
    否则破坏已绑定的 human review / 工单哈希链）。
    """
    run_root_closure = run_dir / "phase-2-closure.json"
    if run_root_closure.is_file():
        return run_root_closure
    return _stamp_v3_run_layout(run_dir)
