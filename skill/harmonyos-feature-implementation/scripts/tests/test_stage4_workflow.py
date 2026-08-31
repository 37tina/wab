#!/usr/bin/env python3
"""Minimal full-chain test for governed Phase 4 and controller Gate 4."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1]
BUNDLE = HERE.parents[2]
CONTROLLER = BUNDLE / "android-harmony-migration-controller"
STAGE3_TESTS = BUNDLE / "harmonyos-migration-scaffold" / "scripts" / "tests"
sys.path.insert(0, str(STAGE3_TESTS))

from phase2_fixture import (  # noqa: E402
    build_closed_phase2,
    record_human_approval,
    record_team_receipt,
    write_csv,
)
from test_stage3_workflow import (  # noqa: E402
    create_project_and_registries,
    freeze_environment,
    initialize_phase3,
    issue_phase3,
    read_csv,
    verification_plan,
)


FAKE = (STAGE3_TESTS / "fake_harmony.py").resolve()


def run_cmd(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["ANDROID_HARMONY_TEST_FIXTURES"] = "1"
    completed = subprocess.run(
        list(args), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, env=environment,
    )
    if completed.returncode != expect:
        raise AssertionError(
            f"Expected exit {expect}, got {completed.returncode}\nCOMMAND: {args}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close_stage3(root: Path) -> Path:
    run_dir, _ = build_closed_phase2(root, runtime_container_host="SOURCE_CONFIRM")
    order = issue_phase3(run_dir)
    workspace = initialize_phase3(run_dir, order)
    create_project_and_registries(workspace)
    # #48 分歧修复已落地：D 的 input-lock 原生（绝对路径 + scaffold-v3 +
    # data_contracts 展开键位）直接喂 Gate 3，原 adapt_input_lock_for_gate3
    # 适配层已随 scaffold 侧一并拆除。
    freeze_environment(workspace, root / "henv.json")
    plan = root / "stage3-plan.json"
    plan.write_text(
        json.dumps(verification_plan("HVER-001", "HSCREEN-LOGIN", "STAGE4"), indent=2) + "\n",
        encoding="utf-8",
    )
    run_cmd(
        sys.executable, str(BUNDLE / "harmonyos-migration-scaffold" / "scripts" / "run_verification.py"),
        "--workspace", str(workspace), "--plan", str(plan),
    )
    run_cmd(
        sys.executable, str(BUNDLE / "harmonyos-migration-scaffold" / "scripts" / "validate_stage3.py"),
        "--workspace", str(workspace), "--henv-id", "HENV-001",
        "--verification-id", "HVER-001", "--reviewer", "architecture-acceptance-1",
        "--decision", "PASS", "--attest-real-file-review", "--attest-placeholder-boundaries",
        "--attest-contract-only", "--attest-dependency-review", "--attest-runtime-smoke",
        "--attest-screenshot-review",
    )
    run_cmd(
        sys.executable, str(CONTROLLER / "scripts" / "validate_gate.py"),
        "--run-dir", str(run_dir), "--phase", "3", "--write",
    )
    record_human_approval(run_dir, 3, "HREV-PHASE-03-FEATURE")
    phase3_receipts = [
        ("architecture_lead_id", "architecture-lead-1", "TASK-P3-ARCH", workspace / "architecture-map.csv"),
        ("toolchain_agent_id", "toolchain-agent-1", "TASK-P3-TOOL", workspace / "verification" / "HVER-001" / "COMMITTED"),
        ("navigation_agent_id", "navigation-agent-1", "TASK-P3-NAV", workspace / "route-registry.csv"),
        ("public_ui_agent_id", "public-ui-agent-1", "TASK-P3-UI", workspace / "public-ui-registry.csv"),
        ("capability_contract_agent_id", "capability-agent-1", "TASK-P3-CAP", workspace / "capability-contracts.csv"),
        ("architecture_acceptance_agent_id", "architecture-acceptance-1", "TASK-P3-ACCEPT", workspace / "stage-03-gate-report.json"),
    ]
    for role_key, actor_id, task_id, artifact in phase3_receipts:
        record_team_receipt(run_dir, order, role_key, actor_id, task_id, artifact)
    return run_dir


def category_contracts(scope: dict[str, object]) -> dict[str, dict[str, object]]:
    executable = str(FAKE)
    executable_sha = sha256(FAKE)
    environment = scope["environments"][0]  # type: ignore[index]
    serial = "fixture-001"
    bundle = "com.example.fixture"
    network = str(environment["network_profile"])  # type: ignore[index]
    permissions = str(environment["permissions_profile"])  # type: ignore[index]
    values = {
        "TOOLCHAIN": (["toolchain"], "TOOLCHAIN_OK"),
        "CLEAN_BUILD": (["build", "{ARTIFACT}"], "BUILD_OK"),
        "BUNDLE_CHECK": (["bundle", serial, bundle], "BUNDLE_OK"),
        "SIGNING_CHECK": (["signing", bundle], "SIGNING_OK"),
        "DEVICE_CHECK": (["device", serial], "DEVICE_OK"),
        "CLEAN_INSTALL": (["install", serial, bundle, "{ARTIFACT}"], "INSTALL_OK"),
        "SEED_RESET": (["seed-reset", serial, bundle], "SEED_RESET_OK"),
        "NETWORK_PROFILE": (["network-profile", serial, network], "NETWORK_PROFILE_OK"),
        "PERMISSION_PROFILE": (
            ["permission-profile", serial, bundle, permissions], "PERMISSION_PROFILE_OK"
        ),
        "LAUNCH": (["launch", serial, bundle, "EntryAbility"], "LAUNCH_OK"),
        "NAVIGATE": (["navigate", serial, bundle, "ROUTE-LOGIN"], "NAVIGATE_OK"),
        "BUSINESS_ASSERT": (
            ["business-assert", serial, bundle, "ROUTE-LOGIN", "{ASSERTIONS}"],
            "BUSINESS_ASSERT_OK",
        ),
        "SCREENSHOT_CAPTURE": (
            ["screenshot", serial, bundle, "ROUTE-LOGIN", "{SCREENSHOT}"],
            "SCREENSHOT_OK",
        ),
        "UITEST_SNAPSHOT_CAPTURE": (
            ["uitest-snapshot", serial, bundle, "ROUTE-LOGIN", "{TEST_HAP}", "{UITEST_RESULT}"],
            "UITEST_SNAPSHOT_OK"
        ),
    }
    # native-adaptive 模式下像素采集两类非必需（validate_gate 的 required 集合恰好等于
    # 类别集，多了也算 differs）——fixture 与 scope 模板默认（native-adaptive）对齐
    mode = str(scope.get("migration_scope", {}).get("visual_parity_mode") or "strict")
    if mode == "native-adaptive":
        values.pop("SCREENSHOT_CAPTURE", None)
        values.pop("UITEST_SNAPSHOT_CAPTURE", None)
    return {
        category: {
            "resolved_executable": executable,
            "executable_sha256": executable_sha,
            "required_argv_tokens": required,
            "success_output_contains": [success],
            "error_output_contains": ["Error:", "Failed:", "Failure:"],
        }
        for category, (required, success) in values.items()
    }


def phase4_environment(run_dir: Path, target: Path) -> None:
    scope = json.loads((run_dir / "controller" / "scope.json").read_text(encoding="utf-8"))
    value = {
        "h4env_id": "H4ENV-001",
        "source_android_env_id": "ENV-001",
        "base_henv_id": "HENV-001",
        "device_id": "HDEVICE-001",
        "device_serial": "fixture-001",
        "bundle_name": "com.example.fixture",
        "created_by": "implementation-lead-4",
        "required": True,
        "device_selector_tokens": ["--serial", "fixture-001"],
        "category_contracts": category_contracts(scope),
        "comparison": {
            # 与冻结的 Android 环境分辨率 byte-identical（init 的 H4ENV resolution 校验强制一致）
            "screenshot_width": 1080,
            "screenshot_height": 2400,
            "content_bounds": [0, 0, 1080, 2400],
            "geometry_tolerance_px": 2,
            "excluded_platform_regions": [],
        },
    }
    target.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def build_plan(target: Path, build_id: str) -> None:
    executable = str(FAKE)
    value = {
        "hbuild_id": build_id,
        "h4env_id": "H4ENV-001",
        "executed_by": "verification-executor-4",
        "commands": [
            {"command_id": "H4CMD-BUILD-TOOL", "category": "TOOLCHAIN", "cwd": ".",
             "argv": [executable, "toolchain"]},
            {"command_id": "H4CMD-BUILD-CLEAN", "category": "CLEAN_BUILD", "cwd": ".",
             "argv": [executable, "build", "--artifact", "{ARTIFACT}"]},
            {"command_id": "H4CMD-BUILD-BUNDLE", "category": "BUNDLE_CHECK", "cwd": ".",
             "argv": [executable, "bundle", "--serial", "fixture-001", "--bundle", "com.example.fixture"]},
            {"command_id": "H4CMD-BUILD-SIGN", "category": "SIGNING_CHECK", "cwd": ".",
             "argv": [executable, "signing", "--bundle", "com.example.fixture"]},
        ],
        "artifact_paths": ["build/app.hap"],
    }
    target.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def state_plan(
    target: Path,
    parity_id: str,
    implemented_by: str,
    steps: Path,
    *,
    evidence_id: str,
    build_id: str,
    supersedes_evidence_id: str = "",
    test_hap_path: str = "uitest-test.hap",
) -> None:
    executable = str(FAKE)
    serial = "fixture-001"
    bundle = "com.example.fixture"
    commands = [
        ("DEVICE_CHECK", [executable, "device", "--serial", serial]),
        ("CLEAN_INSTALL", [executable, "install", "--serial", serial, "--bundle", bundle,
                           "--artifact", "{ARTIFACT}"]),
        ("SEED_RESET", [executable, "seed-reset", "--serial", serial, "--bundle", bundle]),
        ("NETWORK_PROFILE", [executable, "network-profile", "--serial", serial,
                             "--profile", "normal"]),
        ("PERMISSION_PROFILE", [executable, "permission-profile", "--serial", serial,
                                "--bundle", bundle, "--profile", "fresh-install"]),
        ("LAUNCH", [executable, "launch", "--serial", serial, "--bundle", bundle,
                    "--ability", "EntryAbility"]),
        ("NAVIGATE", [executable, "navigate", "--serial", serial, "--bundle", bundle,
                      "--target", "ROUTE-LOGIN"]),
        ("BUSINESS_ASSERT", [executable, "business-assert", "--serial", serial,
                             "--bundle", bundle, "--target", "ROUTE-LOGIN",
                             "--parity", parity_id, "--build", build_id,
                             "--env", "H4ENV-001", "--output", "{ASSERTIONS}"]),
        ("SCREENSHOT_CAPTURE", [executable, "screenshot", "--serial", serial,
                                "--bundle", bundle, "--target", "ROUTE-LOGIN",
                                "--output", "{SCREENSHOT}", "--width", "1080", "--height", "2400"]),
        ("UITEST_SNAPSHOT_CAPTURE", [executable, "uitest-snapshot", "--serial", serial,
                                     "--bundle", bundle, "--target", "ROUTE-LOGIN",
                                     "--test-hap", "{TEST_HAP}",
                                     "--output", "{UITEST_RESULT}"]),
    ]
    value = {
        "evidence_id": evidence_id,
        "parity_id": parity_id,
        "hbuild_id": build_id,
        "h4env_id": "H4ENV-001",
        "test_hap_path": test_hap_path,
        "supersedes_evidence_id": supersedes_evidence_id,
        "implemented_by": implemented_by,
        "executed_by": "verification-executor-4",
        "steps_file": str(steps),
        "commands": [
            {"command_id": f"H4CMD-STATE-{number:02d}", "category": category,
             "cwd": ".", "argv": argv}
            for number, (category, argv) in enumerate(commands, start=1)
        ],
        "assertions": [
            {"assertion_id": "ASSERT-VISUAL", "kind": "VISUAL_STATE", "expected": "visible"},
            {"assertion_id": "ASSERT-BUSINESS", "kind": "BUSINESS_RESULT", "expected": "login-ready",
             "subject_ids": ["BR-AUTH-NONE", "DATA-AUTH-NONE", "SYS-AUTH-NONE", "SDK-AUTH-NONE"]},
            {"assertion_id": "ASSERT-INTERACTION", "kind": "INTERACTION", "expected": "tap-ready"},
            {"assertion_id": "ASSERT-ANDROID-OBSERVABLE", "kind": "ANDROID_EXPECTED_OBSERVABLE",
             "expected": "Login form is visible", "subject_ids": ["INV-AUTH-LOGIN-DEFAULT"]},
        ],
    }
    target.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class Stage4WorkflowTest(unittest.TestCase):

    @unittest.skip(
        "TODO(#60-phase4-v4): 待 v4 实跑链验证——Phase 4 实跑是下一阶段。"
        "v4 工单（issue_phase4_work_order v3 按功能签发）与 init（v4 输入面"
        "7 类核心产物）已就绪，但本链夹具仍缺：phase2_fixture 产出 "
        "runtime-evidence/runtime-chains.csv（v4 工单输入⑤）与 Gate 4 "
        "工作区夹具（replay-results.csv / surface-contract.csv / "
        "implementation-declarations.csv，validate_stage4 v4 五条判定输入）。"
        "旧页面工单链（issue_page/capability_work_order + parity-map + "
        "visual-elements）已随 v4 整体退役，本测试体已按 v4 产物结构重写。"
        "Controller Gate 3 recompute 链仍由 "
        "test_close_stage3_controller_gate3_recompute 真实覆盖。"
    )
    def test_full_stage4_and_controller_gate4_detect_post_close_tamper(self) -> None:
        with tempfile.TemporaryDirectory(prefix="harmony-stage4-skill-test-") as temp_name:
            root = Path(temp_name)
            run_dir = close_stage3(root)
            issued = run_cmd(
                sys.executable, str(CONTROLLER / "scripts" / "issue_phase4_work_order.py"),
                "--run-dir", str(run_dir), "--issued-by", "migration-controller-1",
                "--implementation-lead-id", "implementation-lead-4",
                "--visual-asset-agent-id", "visual-asset-agent-4",
                "--verification-executor-id", "verification-executor-4",
                "--parity-acceptance-agent-id", "parity-acceptance-4",
            )
            phase4_order = Path(json.loads(issued.stdout)["work_order"])
            env_config = root / "h4env.json"
            phase4_environment(run_dir, env_config)
            initialized = run_cmd(
                sys.executable, str(SKILL / "scripts" / "init_implementation.py"),
                "--run-dir", str(run_dir), "--work-order", str(phase4_order),
                "--implementation-lead", "implementation-lead-4",
                "--environment-config", str(env_config),
            )
            workspace = Path(json.loads(initialized.stdout)["workspace"])

            # v4 产物结构断言（按功能组织实施，不再有页面/能力工单）：
            dispatch = json.loads((workspace / "feature-dispatch.json").read_text(encoding="utf-8"))
            self.assertTrue(dispatch["dispatch"])
            with (workspace / "surface-contracts.csv").open(encoding="utf-8", newline="") as stream:
                surface_rows = list(csv.DictReader(stream))
            self.assertEqual(len(dispatch["dispatch"]), len(surface_rows))
            lock = json.loads((workspace / "stage-04-input-lock.json").read_text(encoding="utf-8"))
            self.assertEqual("2.0", lock["schema_version"])

            # 实施/Gate 4/replayer 实跑链（v4 五条判定 + controller Gate 4 +
            # 闭包后 tamper 检测）待下一阶段夹具就绪后补全：
            #   run_build → capture_state → replayer → surface_contract 回填 →
            #   validate_stage4 → validate_gate --phase 4 → 篡改 source 后
            #   expect=1。
            raise unittest.SkipTest("v4 Gate 4 实跑链待下一阶段解锁")

    def test_close_stage3_controller_gate3_recompute(self) -> None:
        """#48-B：close_stage3 链尾的 controller Gate 3 v3 重算（真实断言）。

        Phase 4 工单旧输入（advanced-obligations.json）修复前，全链 tamper
        测试保持 skip；此处固化 controller --phase 3 --write 的恢复：
        重算 PASS + ledger 写入 + 闭包篡改检测。
        """
        with tempfile.TemporaryDirectory(prefix="harmony-stage4-skill-test-") as temp_name:
            root = Path(temp_name)
            run_dir = close_stage3(root)
            gate3 = run_cmd(
                sys.executable, str(CONTROLLER / "scripts" / "validate_gate.py"),
                "--run-dir", str(run_dir), "--phase", "3", "--write",
            )
            report = json.loads(gate3.stdout)
            self.assertEqual(report["verdict"], "PASS", report["errors"][:5])
            self.assertEqual(report["harmony_environment_id"], "HENV-001")
            self.assertEqual(report["verification_id"], "HVER-001")
            ledger = {
                row["phase"]: row
                for row in csv.DictReader(
                    (run_dir / "controller" / "task-ledger.csv").read_text().splitlines()
                )
            }
            self.assertEqual(ledger["3"]["status"], "PASS")
            self.assertEqual(ledger["3"]["owner"], "architecture-lead-1")

            workspace = run_dir / "phase-03-harmony-scaffold"
            shell = next((workspace / "harmony-project").rglob("ShellPageLogin.ets"))
            shell.chmod(0o644)
            shell.write_text(
                shell.read_text(encoding="utf-8") + "// post-closure tamper\n",
                encoding="utf-8",
            )
            run_cmd(
                sys.executable, str(CONTROLLER / "scripts" / "validate_gate.py"),
                "--run-dir", str(run_dir), "--phase", "3", expect=1,
            )


if __name__ == "__main__":
    unittest.main()
