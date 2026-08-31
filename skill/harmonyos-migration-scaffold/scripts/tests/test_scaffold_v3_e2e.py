#!/usr/bin/env python3
"""Phase 3 paradigm v3 (feature-semantic) end-to-end tests — tasks #47/#52.

覆盖三层：
1. init_scaffold v3 单路径干跑正例（fixture 三形态 feature 的骨架计划断言）；
2. validate_stage3 v3 四条规则的函数级正反例（快速、稳定）；
3. Gate 3 全链 e2e（init → freeze → run_verification → PASS）。

#48 分歧修复已落地（D/E/机制脚本对齐，适配层已拆除）：
- D 的 input-lock inputs.*.path/snapshot_path 原生输出绝对规范路径；
- D 的 data_contracts[] 按 (feature, object) 组合展开，原生含 E 的消费键
  {feature_id, data_object, interface}；
- E 的 input-lock schema_version 比较串对齐 'scaffold-v3'；
- run_verification 的 mapping_type/target_kind 接受 v3 值（ROUTE/MODAL）
  与旧值（ROUTE_PAGE/VISUAL_SURFACE）归并并存；
- D 的 architecture-map page_shell_id 原生输出大写 ID（PSHELL-<SURFACE-ID>）。
D 的原始产出直接喂 Gate 3 应 PASS（原分歧固化测试已翻转断言）。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from phase2_fixture import CONTROLLER_SKILL, build_closed_phase2  # noqa: E402

SKILL = HERE.parents[1]
SCAFFOLD_SCRIPTS = SKILL / "scripts"


def load_validate_stage3():
    spec = importlib.util.spec_from_file_location(
        "validate_stage3_module_under_test", SCAFFOLD_SCRIPTS / "validate_stage3.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_cmd(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(args), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if completed.returncode != expect:
        raise AssertionError(
            f"Expected exit {expect}, got {completed.returncode}\nCOMMAND: {args}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def issue_phase3_v3(run_dir: Path) -> Path:
    issued = run_cmd(
        sys.executable, str(CONTROLLER_SKILL / "scripts" / "issue_phase3_work_order.py"),
        "--run-dir", str(run_dir), "--issued-by", "migration-controller-1",
        "--architecture-lead-id", "architecture-lead-1",
        "--toolchain-agent-id", "toolchain-agent-1",
        "--navigation-agent-id", "navigation-agent-1",
        "--public-ui-agent-id", "public-ui-agent-1",
        "--capability-contract-agent-id", "capability-agent-1",
        "--architecture-acceptance-agent-id", "architecture-acceptance-1",
    )
    return Path(json.loads(issued.stdout)["work_order"])


def init_scaffold_v3(
    run_dir: Path, work_order: Path, *, dry_run: bool = False
) -> dict:
    argv = [
        sys.executable, str(SCAFFOLD_SCRIPTS / "init_scaffold.py"),
        "--run-dir", str(run_dir), "--work-order", str(work_order),
        "--architecture-lead", "architecture-lead-1",
    ]
    if dry_run:
        argv.append("--dry-run")
    completed = run_cmd(*argv)
    return json.loads(completed.stdout)



def verification_plan_v3(verification_id: str, suffix: str) -> dict:
    """v3 冒烟计划：机制级类别齐全，target 直接使用 v3 值（ROUTE）。

    #48 对齐后 run_verification 的 mapping_type/target_kind 接受 v3 值
    （ROUTE/MODAL）与旧值归并并存，architecture-map 无需任何改写。
    """
    executable = str(HERE / "fake_harmony.py")
    result_path = f"build/results/route-{suffix}.json"
    screenshot_path = f"build/screenshots/HSCREEN-{suffix}.png"

    def cmd(command_id: str, category: str, argv: list[str], **extra):
        return {
            "command_id": command_id, "category": category, "cwd": ".",
            "argv": argv, **extra,
        }

    return {
        "verification_id": verification_id,
        "henv_id": "HENV-001",
        "executed_by": "toolchain-agent-1",
        "commands": [
            cmd(f"CMD-{suffix}-TOOLCHAIN", "TOOLCHAIN", [executable, "toolchain"]),
            cmd(
                f"CMD-{suffix}-DEVICE", "DEVICE",
                [executable, "device", "--serial", "fixture-001"],
                device_id="HDEVICE-001",
            ),
            cmd(
                f"CMD-{suffix}-BUNDLE", "BUNDLE_CHECK",
                [executable, "bundle", "--serial", "fixture-001",
                 "--bundle", "com.example.fixture"],
                device_id="HDEVICE-001",
            ),
            cmd(
                f"CMD-{suffix}-SIGNING", "SIGNING_CHECK",
                [executable, "signing", "--bundle", "com.example.fixture"],
            ),
            cmd(
                f"CMD-{suffix}-BUILD", "CLEAN_BUILD",
                [executable, "build", "--artifact", "build/app.hap"],
            ),
            cmd(
                f"CMD-{suffix}-INSTALL", "INSTALL",
                [executable, "install", "--serial", "fixture-001",
                 "--artifact", "build/app.hap"],
                device_id="HDEVICE-001",
            ),
            cmd(
                f"CMD-{suffix}-LAUNCH", "LAUNCH",
                [executable, "launch", "--serial", "fixture-001",
                 "--bundle", "com.example.fixture", "--ability", "EntryAbility"],
                device_id="HDEVICE-001",
            ),
            cmd(
                f"CMD-{suffix}-SMOKE", "ROUTE_SMOKE",
                [executable, "smoke", "--serial", "fixture-001",
                 "--bundle", "com.example.fixture", "--kind", "ROUTE",
                 "--target", "PAGE-LOGIN", "--page", "PAGE-LOGIN",
                 "--shell", "PSHELL-PAGE-LOGIN", "--result", result_path],
                device_id="HDEVICE-001", target_kind="ROUTE",
                target_id="PAGE-LOGIN", page_id="PAGE-LOGIN",
                page_shell_id="PSHELL-PAGE-LOGIN",
                result_output_path=result_path,
            ),
            cmd(
                f"CMD-{suffix}-SMOKE-THEME", "ROUTE_SMOKE",
                [executable, "smoke", "--serial", "fixture-001",
                 "--bundle", "com.example.fixture", "--kind", "ROUTE",
                 "--target", "PAGE-SETTINGS-THEME", "--page", "PAGE-SETTINGS-THEME",
                 "--shell", "PSHELL-PAGE-SETTINGS-THEME",
                 "--result", f"build/results/route-theme-{suffix}.json"],
                device_id="HDEVICE-001", target_kind="ROUTE",
                target_id="PAGE-SETTINGS-THEME", page_id="PAGE-SETTINGS-THEME",
                page_shell_id="PSHELL-PAGE-SETTINGS-THEME",
                result_output_path=f"build/results/route-theme-{suffix}.json",
            ),
            cmd(
                f"CMD-{suffix}-SMOKE-SHEET", "ROUTE_SMOKE",
                [executable, "smoke", "--serial", "fixture-001",
                 "--bundle", "com.example.fixture", "--kind", "MODAL",
                 "--target", "ShellModalAuthAccountSheet", "--page", "PAGE-LOGIN",
                 "--shell", "PSHELL-PAGE-LOGIN",
                 "--result", f"build/results/surface-sheet-{suffix}.json"],
                device_id="HDEVICE-001", target_kind="MODAL",
                target_id="ShellModalAuthAccountSheet", page_id="PAGE-LOGIN",
                page_shell_id="PSHELL-PAGE-LOGIN",
                result_output_path=f"build/results/surface-sheet-{suffix}.json",
            ),
            cmd(
                f"CMD-{suffix}-SCREEN", "SCREENSHOT_CAPTURE",
                [executable, "screenshot", "--serial", "fixture-001",
                 "--target", "PAGE-LOGIN", "--output", screenshot_path,
                 "--width", "1080", "--height", "2400"],
                device_id="HDEVICE-001", screenshot_id=f"HSCREEN-{suffix}",
                target_kind="ROUTE", target_id="PAGE-LOGIN",
                page_id="PAGE-LOGIN", page_shell_id="PSHELL-PAGE-LOGIN",
                feature_ids=["FEATURE-AUTH"],
                smoke_command_id=f"CMD-{suffix}-SMOKE",
                output_path=screenshot_path,
            ),
            cmd(
                f"CMD-{suffix}-SCREEN-THEME", "SCREENSHOT_CAPTURE",
                [executable, "screenshot", "--serial", "fixture-001",
                 "--target", "PAGE-SETTINGS-THEME",
                 "--output", f"build/screenshots/HSCREEN-{suffix}-THEME.png",
                 "--width", "1080", "--height", "2400"],
                device_id="HDEVICE-001", screenshot_id=f"HSCREEN-{suffix}-THEME",
                target_kind="ROUTE", target_id="PAGE-SETTINGS-THEME",
                page_id="PAGE-SETTINGS-THEME", page_shell_id="PSHELL-PAGE-SETTINGS-THEME",
                feature_ids=["FEATURE-SETTINGS-THEME"],
                smoke_command_id=f"CMD-{suffix}-SMOKE-THEME",
                output_path=f"build/screenshots/HSCREEN-{suffix}-THEME.png",
            ),
            cmd(
                f"CMD-{suffix}-SCREEN-SHEET", "SCREENSHOT_CAPTURE",
                [executable, "screenshot", "--serial", "fixture-001",
                 "--target", "ShellModalAuthAccountSheet",
                 "--output", f"build/screenshots/HSCREEN-{suffix}-SHEET.png",
                 "--width", "1080", "--height", "2400"],
                device_id="HDEVICE-001", screenshot_id=f"HSCREEN-{suffix}-SHEET",
                target_kind="MODAL", target_id="ShellModalAuthAccountSheet",
                page_id="PAGE-LOGIN", page_shell_id="PSHELL-PAGE-LOGIN",
                feature_ids=["FEATURE-AUTH"],
                smoke_command_id=f"CMD-{suffix}-SMOKE-SHEET",
                output_path=f"build/screenshots/HSCREEN-{suffix}-SHEET.png",
            ),
        ],
        "artifact_paths": ["build/app.hap"],
    }


def register_v3_route_for_verification(workspace: Path) -> None:
    """模拟 navigation agent 完成 PAGE-LOGIN 的路由注册（链路必要步骤）。

    v3 的 init 只拷贝空 route-registry 模板（注册由 Phase 3 agent 完成，
    与 legacy 链的 create_project_and_registries 同理）；run_verification
    的 ROUTE_SMOKE target 身份要求 registry 有对应行。#48 对齐后
    architecture-map 的 mapping_type 保持 D 的 v3 原值（ROUTE），无需
    任何改写（原分歧适配 adapt_architecture_map_for_run_verification
    已拆除）。
    """
    import csv as csv_module

    registry_path = workspace / "route-registry.csv"
    with registry_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv_module.DictReader(handle)
        registry_fields = list(reader.fieldnames or [])
    registry_rows = [
        {
            "route_id": "PAGE-LOGIN", "page_id": "PAGE-LOGIN",
            "page_shell_id": "PSHELL-PAGE-LOGIN", "harmony_module_id": "HMOD-ENTRY",
            "route_pattern": "/login", "registry_file": "entry/src/Routes.ets",
            "registry_symbol": "LoginRouteRegistry",
            "page_shell_file": "entry/src/main/ets/pages/shells/ShellPageLogin.ets",
            "feature_ids": "FEATURE-AUTH", "created_by": "navigation-agent-1",
            "status": "READY", "notes": "v3 e2e route registration",
        },
        {
            "route_id": "PAGE-SETTINGS-THEME", "page_id": "PAGE-SETTINGS-THEME",
            "page_shell_id": "PSHELL-PAGE-SETTINGS-THEME",
            "harmony_module_id": "HMOD-ENTRY",
            "route_pattern": "/settings-theme", "registry_file": "entry/src/Routes.ets",
            "registry_symbol": "SettingsThemeRouteRegistry",
            "page_shell_file": "entry/src/main/ets/pages/shells/ShellPageSettingsTheme.ets",
            "feature_ids": "FEATURE-SETTINGS-THEME", "created_by": "navigation-agent-1",
            "status": "READY", "notes": "v3 e2e route registration",
        },
    ]
    with registry_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv_module.DictWriter(handle, fieldnames=registry_fields)
        writer.writeheader()
        writer.writerows(registry_rows)

    # modal 承载面登记（surface-registry，键 = surface_shell_id 组件符号，
    # page_id/page_shell_id 为其挂载宿主页）。
    surface_registry_path = workspace / "surface-registry.csv"
    with surface_registry_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv_module.DictReader(handle)
        surface_fields = list(reader.fieldnames or [])
    surface_rows = [
        {
            "surface_shell_id": "ShellModalAuthAccountSheet",
            "page_id": "PAGE-LOGIN", "page_shell_id": "PSHELL-PAGE-LOGIN",
            "harmony_module_id": "HMOD-ENTRY", "surface_kind": "sheet",
            "surface_file": "entry/src/main/ets/pages/modals/ShellModalAuthAccountSheet.ets",
            "surface_symbol": "ShellModalAuthAccountSheet",
            "feature_ids": "FEATURE-AUTH", "created_by": "navigation-agent-1",
            "status": "READY", "notes": "v3 e2e modal carrier registration",
        },
    ]
    with surface_registry_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv_module.DictWriter(handle, fieldnames=surface_fields)
        writer.writeheader()
        writer.writerows(surface_rows)


def close_v3_workspace(workspace: Path, root: Path) -> dict:
    """freeze + run_verification + Gate 3 v3 PASS（复用 legacy 机制级构造）。"""
    from test_stage3_workflow import freeze_environment

    # v3 模板排除 oh-package-lock.json5；lock 由构建侧产生（此处模拟
    # toolchain agent 的最小 lock，与旧链 create_project_and_registries 一致）。
    (workspace / "harmony-project" / "oh-package-lock.json5").write_text(
        "{ lockfileVersion: 3 }\n", encoding="utf-8"
    )
    register_v3_route_for_verification(workspace)
    freeze_environment(workspace, root / "henv.json")
    plan = root / "verification-plan.json"
    plan.write_text(
        json.dumps(verification_plan_v3("HVER-V3-001", "V3"), indent=2) + "\n",
        encoding="utf-8",
    )
    run_cmd(
        sys.executable, str(SCAFFOLD_SCRIPTS / "run_verification.py"),
        "--workspace", str(workspace), "--plan", str(plan),
    )
    validation = run_cmd(
        sys.executable, str(SCAFFOLD_SCRIPTS / "validate_stage3.py"),
        "--workspace", str(workspace), "--henv-id", "HENV-001",
        "--verification-id", "HVER-V3-001",
        "--reviewer", "architecture-acceptance-1",
        "--decision", "PASS",
        "--attest-real-file-review", "--attest-contract-only",
        "--attest-dependency-review", "--attest-runtime-smoke",
    )
    return json.loads(validation.stdout)


class ScaffoldV3DryRunTest(unittest.TestCase):
    """init_scaffold v3 单路径：干跑计划与 fixture 三形态一一对应。"""

    def test_dry_run_green_baseline_surface_plan(self) -> None:
        with tempfile.TemporaryDirectory(prefix="v3-dry-run-") as temp:
            root = Path(temp)
            run_dir, _ = build_closed_phase2(
                root, runtime_container_host="SOURCE_CONFIRM"
            )
            document = init_scaffold_v3(run_dir, issue_phase3_v3(run_dir), dry_run=True)
            self.assertTrue(document["dry_run"])
            self.assertEqual(document["paradigm"], "feature-semantic")
            self.assertEqual(
                document["input_lock"]["inputs"]["feature_map"]["feature_count"], 3
            )
            stats = document["surface_plan"]["stats"]
            # 4 surfaces = 2 page routes + 1 sheet modal + 1 container passthrough。
            self.assertEqual(
                (stats["surface_count"], stats["route_count"],
                 stats["modal_count"], stats["passthrough_count"]),
                (4, 2, 1, 1),
            )
            # nav 最小行两端命中 surface 清单：边保留、无 skipped。
            self.assertEqual(stats["nav_edge_kept"], 1)
            self.assertEqual(stats["nav_pages_skipped"], 0)
            modals = document["surface_plan"]["modals"]
            self.assertEqual(len(modals), 1)
            self.assertEqual(modals[0]["surface_id"], "PAGE-AUTH-ACCOUNT-SHEET")
            self.assertEqual(modals[0]["host_surface_id"], "PAGE-LOGIN")
            self.assertEqual(modals[0]["mount_host_source"], "nav-explicit-edge")
            passthrough = document["surface_plan"]["passthrough"]
            self.assertEqual(
                (passthrough[0]["surface_id"], passthrough[0]["kind"]),
                ("PAGE-MAIN-HOST", "container"),
            )
            # 数据契约（#48 裁定）：data_contracts 按 (feature, object) 组合
            # 展开，含 E 消费键 {feature_id, data_object, interface}；孤儿
            # 开关行（settings，feature_ids 为空）无组合、不进展开数组
            # （capability_seeds 仍如实聚合，见 test_stage3_workflow 断言）。
            contracts = {
                (item["feature_id"], item["data_object"]): item["interface"]
                for item in document["data_contracts_index"]
            }
            self.assertEqual(
                contracts,
                {
                    ("FEATURE-AUTH", "account_profile"): "AccountProfileRepository",
                    ("FEATURE-AUTH", "mmkv:session_token"): "MmkvSessionTokenRepository",
                    ("FEATURE-SETTINGS-THEME", "mmkv:theme_mode"): "MmkvThemeModeRepository",
                },
            )
            lock = document["input_lock"]
            self.assertEqual(lock["schema_version"], "scaffold-v3")
            self.assertEqual(
                lock["included_feature_ids"],
                ["FEATURE-AUTH", "FEATURE-NAV-HOST", "FEATURE-SETTINGS-THEME"],
            )

    def test_dry_run_default_fixture_keeps_container_runtime(self) -> None:
        """默认 fixture（RUNTIME+container-only）不改 init 行为（init 不读 verify_mode）。"""
        with tempfile.TemporaryDirectory(prefix="v3-default-") as temp:
            root = Path(temp)
            run_dir, _ = build_closed_phase2(root)
            document = init_scaffold_v3(run_dir, issue_phase3_v3(run_dir), dry_run=True)
            self.assertEqual(document["surface_plan"]["stats"]["passthrough_count"], 1)


class Gate3RuleUnitTest(unittest.TestCase):
    """Gate 3 v3 四条规则：函数级正反例（不依赖完整链，锁定规则语义）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = load_validate_stage3()

    def _green_feature_map(self):
        return {
            "features": [
                {
                    "feature_id": "FEATURE-AUTH", "verify_mode": "RUNTIME",
                    "surfaces": [
                        {"id": "PAGE-LOGIN", "kind": "page", "is_container": False},
                        {"id": "PAGE-AUTH-ACCOUNT-SHEET", "kind": "sheet", "is_container": False},
                    ],
                },
                {
                    "feature_id": "FEATURE-NAV-HOST", "verify_mode": "SOURCE_CONFIRM",
                    "surfaces": [{"id": "PAGE-MAIN-HOST", "kind": "container", "is_container": True}],
                },
                {
                    "feature_id": "FEATURE-SETTINGS-THEME", "verify_mode": "SOURCE_CONFIRM",
                    "surfaces": [{"id": "PAGE-SETTINGS-THEME", "kind": "page", "is_container": False}],
                },
            ]
        }

    def _green_surface_plan(self):
        """合规 blueprint surface-plan（#89 修 3：规则 1 消费三字段）。"""
        return {
            "routes": [
                {
                    "surface_id": "PAGE-LOGIN",
                    "preserve": {"policy": "UI_FIDELITY=HIGH"},
                    "native_component": "Navigation+NavPathStack+List/Scroll",
                    "native_carrier": "route：Navigation 路由节点",
                },
                {
                    "surface_id": "PAGE-SETTINGS-THEME",
                    "preserve": {"policy": "UI_FIDELITY=HIGH"},
                    "native_component": "Navigation+NavPathStack+List/Scroll",
                    "native_carrier": "route：Navigation 路由节点",
                },
            ],
            "modals": [
                {
                    "surface_id": "PAGE-AUTH-ACCOUNT-SHEET",
                    "preserve": {"policy": "UI_FIDELITY=HIGH"},
                    "native_component": "bindSheet(detents MEDIUM/LARGE)",
                    "native_carrier": "modal@PAGE-LOGIN：bindSheet 模态挂载",
                },
            ],
            "passthrough": [{"surface_id": "PAGE-MAIN-HOST", "kind": "container"}],
        }

    def test_rule1_positive_carrier_coverage(self) -> None:
        errors: list[str] = []
        warnings: list[str] = []
        surfaces_by_id = {
            "PAGE-LOGIN": "route",
            "PAGE-AUTH-ACCOUNT-SHEET": "modal",
            "PAGE-MAIN-HOST": "none",
            "PAGE-SETTINGS-THEME": "route",
        }
        counts = self.validator.validate_v3_surface_carriers(
            self._green_feature_map(), surfaces_by_id,
            self._green_surface_plan(), errors, warnings,
        )
        self.assertEqual(errors, [])
        self.assertEqual(counts["runtime_features"], 1)
        self.assertEqual(counts["runtime_features_carried"], 1)

    def test_rule1_negative_container_only_runtime_feature(self) -> None:
        """容器规则：RUNTIME feature 只有 container surface → fail-closed。"""
        feature_map = self._green_feature_map()
        feature_map["features"][1]["verify_mode"] = "RUNTIME"
        errors: list[str] = []
        counts = self.validator.validate_v3_surface_carriers(
            feature_map,
            {"PAGE-LOGIN": "route", "PAGE-MAIN-HOST": "none"},
            self._green_surface_plan(), errors, [],
        )
        self.assertTrue(
            any("no non-container UI surface" in error for error in errors), errors
        )
        self.assertEqual(counts["runtime_features_carried"], 1)

    def test_rule1_negative_runtime_surface_without_carrier(self) -> None:
        """RUNTIME feature 的非容器 surface 全部无载体（route_or_mount=none）→ 报错。"""
        feature_map = {
            "features": [
                {
                    "feature_id": "FEATURE-AUTH", "verify_mode": "RUNTIME",
                    "surfaces": [{"id": "PAGE-LOGIN", "kind": "page", "is_container": False}],
                }
            ]
        }
        errors: list[str] = []
        self.validator.validate_v3_surface_carriers(
            feature_map, {"PAGE-LOGIN": "none"},
            {
                "routes": [{
                    "surface_id": "PAGE-LOGIN",
                    "preserve": {"policy": "UI_FIDELITY=HIGH"},
                    "native_component": "Navigation+NavPathStack+List/Scroll",
                    "native_carrier": "route：Navigation 路由节点",
                }],
                "modals": [], "passthrough": [],
            },
            errors, [],
        )
        self.assertTrue(
            any("no non-container UI surface has an ArkUI carrier" in e for e in errors),
            errors,
        )

    def test_rule2_positive_closure_and_orphan_row_semantics(self) -> None:
        """规则 2 正例：语义对象全覆盖且无孤儿契约；孤儿开关行不进语义对象集。"""
        rows = [  # fixture data-relations 形态（含孤儿开关行）
            {"feature_id": "FEATURE-AUTH", "data_object": "mmkv:session_token"},
            {"feature_id": "FEATURE-AUTH", "data_object": "account_profile"},
            {"feature_id": "FEATURE-SETTINGS-THEME", "data_object": "mmkv:theme_mode"},
            {"feature_id": "", "data_object": "settings"},  # 孤儿开关参数行
        ]
        semantic = self.validator.semantic_data_objects(rows)
        self.assertEqual(len(semantic), 3)
        self.assertNotIn(("", "settings"), semantic)
        contracts = [
            {"feature_id": "FEATURE-AUTH", "data_object": "mmkv:session_token",
             "interface": "MmkvSessionTokenRepository"},
            {"feature_id": "FEATURE-AUTH", "data_object": "account_profile",
             "interface": "AccountProfileRepository"},
            {"feature_id": "FEATURE-SETTINGS-THEME", "data_object": "mmkv:theme_mode",
             "interface": "MmkvThemeModeRepository"},
        ]
        errors: list[str] = []
        counts = self.validator.validate_v3_data_contracts(semantic, contracts, errors)
        self.assertEqual(errors, [])
        self.assertEqual(counts["uncovered"], 0)
        self.assertEqual(counts["orphans"], 0)

    def test_rule2_negative_uncovered_and_orphan(self) -> None:
        """规则 2 反例：双向 fail-closed（uncovered + orphaned contract）。"""
        semantic = {("FEATURE-AUTH", "mmkv:session_token")}
        contracts = [
            {"feature_id": "FEATURE-AUTH", "data_object": "account_profile",
             "interface": "AccountProfileRepository"},  # 不在语义集 → 孤儿
        ]
        errors: list[str] = []
        counts = self.validator.validate_v3_data_contracts(semantic, contracts, errors)
        self.assertTrue(
            any("Semantic data objects without an interface contract" in e for e in errors),
            errors,
        )
        self.assertTrue(
            any("Data contracts orphaned outside data-relations" in e for e in errors),
            errors,
        )
        self.assertEqual(counts["uncovered"], 1)
        self.assertEqual(counts["orphans"], 1)

    def test_rule2_negative_missing_interface_declaration(self) -> None:
        semantic = {("FEATURE-AUTH", "mmkv:session_token")}
        contracts = [
            {"feature_id": "FEATURE-AUTH", "data_object": "mmkv:session_token",
             "interface": ""},
        ]
        errors: list[str] = []
        self.validator.validate_v3_data_contracts(semantic, contracts, errors)
        self.assertTrue(
            any("lacks a non-empty interface declaration" in e for e in errors), errors
        )

    def test_rule3_positive_and_negative_category_coverage(self) -> None:
        required = {"HDEVICE-001"}
        green_counts = {
            "TOOLCHAIN": 1, "CLEAN_BUILD": 1, "BUNDLE_CHECK": 1,
            "SIGNING_CHECK": 1, "INSTALL": 1, "LAUNCH": 1,
        }
        green_devices = {
            "INSTALL": {"HDEVICE-001"}, "LAUNCH": {"HDEVICE-001"},
            "BUNDLE_CHECK": {"HDEVICE-001"}, "DEVICE": {"HDEVICE-001"},
        }
        errors: list[str] = []
        self.validator.check_v3_smoke_category_coverage(
            green_counts, green_devices, required, errors
        )
        self.assertEqual(errors, [])
        bad_counts = dict(green_counts, TOOLCHAIN=2)  # singleton 类别出现两次
        bad_counts.pop("SIGNING_CHECK")  # 必需类别缺失
        bad_devices = dict(green_devices, LAUNCH=set())  # 设备覆盖缺失
        errors = []
        self.validator.check_v3_smoke_category_coverage(
            bad_counts, bad_devices, required, errors
        )
        joined = "\n".join(errors)
        self.assertIn("lacks command category: SIGNING_CHECK", joined)
        self.assertIn("exactly one TOOLCHAIN command", joined)
        self.assertIn("LAUNCH device coverage differs", joined)

    def test_rule4_negative_unfrozen_henv(self) -> None:
        with tempfile.TemporaryDirectory(prefix="v3-rule4-") as temp:
            workspace = Path(temp)
            (workspace / "environments").mkdir()
            (workspace / "environments" / "henv-registry.csv").write_text(
                "henv_id,status,environment_sha256\nHENV-001,FROZEN,"
                + "0" * 64 + "\n",
                encoding="utf-8",
            )
            henv_dir = workspace / "environments" / "HENV-001"
            henv_dir.mkdir()
            (henv_dir / "harmony-environment.json").write_text("{}", encoding="utf-8")
            verification_dir = workspace / "verification" / "HVER-X"
            verification_dir.mkdir(parents=True)
            errors: list[str] = []
            self.validator.validate_v3_environment_chain(
                workspace, "HENV-001", verification_dir, errors
            )
            joined = "\n".join(errors)
            self.assertIn("HENV has changed", joined)  # 哈希与注册表不一致
            self.assertIn("preflight", joined.lower())  # 预检报告缺失
            self.assertIn("no required device", joined)


@unittest.skipUnless(
    (SCAFFOLD_SCRIPTS / "validate_stage3.py").is_file()
    and "validate_stage3_v3" in (SCAFFOLD_SCRIPTS / "validate_stage3.py").read_text(encoding="utf-8"),
    "validate_stage3 v3 entry is not available yet (agent E)",
)
class Gate3V3EndToEndTest(unittest.TestCase):
    """Gate 3 v3 全链 e2e：D 产物 + E 校验 + 分歧证据。"""

    def test_full_gate3_pass_with_raw_d_output(self) -> None:
        """#48 对齐后翻转：D 原始产出（无任何适配）直接过 Gate 3 全链。"""
        with tempfile.TemporaryDirectory(prefix="v3-gate3-e2e-") as temp:
            root = Path(temp)
            run_dir, _ = build_closed_phase2(
                root, runtime_container_host="SOURCE_CONFIRM"
            )
            init = init_scaffold_v3(run_dir, issue_phase3_v3(run_dir))
            workspace = Path(init["workspace"])
            report = close_v3_workspace(workspace, root)
            self.assertEqual(report["verdict"], "PASS", report)
            rules = report["rules"]
            self.assertEqual(rules["surface_carrier_coverage"]["status"], "PASS")
            self.assertEqual(rules["data_contract_closure"]["status"], "PASS")
            self.assertEqual(rules["smoke_chain"]["status"], "PASS")
            self.assertEqual(rules["environment_chain"]["status"], "PASS")
            self.assertTrue((workspace / "CLOSED").is_file())

    def test_raw_d_output_passes_gate3_alignment(self) -> None:
        """D 的原始 input-lock 直接喂 E：#48 对齐后应 PASS（原分歧证据测试翻转）。

        断言对齐三处原生形态：inputs.*.path 绝对规范、data_contracts 含
        E 的消费键（feature_id/data_object/interface）、schema_version
        'scaffold-v3' 与 E 的比较串一致。
        """
        with tempfile.TemporaryDirectory(prefix="v3-divergence-") as temp:
            root = Path(temp)
            run_dir, _ = build_closed_phase2(
                root, runtime_container_host="SOURCE_CONFIRM"
            )
            init = init_scaffold_v3(run_dir, issue_phase3_v3(run_dir))
            workspace = Path(init["workspace"])
            lock = json.loads(
                (workspace / "stage-03-input-lock.json").read_text(encoding="utf-8")
            )
            # 对齐 1：D 原生输出绝对规范路径（E 的 canonical 校验直接通过）。
            for key in ("feature_map", "navigation_relations", "data_relations"):
                self.assertTrue(
                    Path(lock["inputs"][key]["path"]).is_absolute(), key
                )
            # 对齐 2：D 的 data_contracts 键位原生含 E 的消费键。
            contract = lock["data_contracts"][0]
            for key in ("feature_id", "data_object", "interface"):
                self.assertIn(key, contract)
            # 对齐 3：schema_version 原生 'scaffold-v3'（E 已对齐同字面值）。
            self.assertEqual(lock["schema_version"], "scaffold-v3")
            # D 原始产出直接跑 Gate 3：全链 PASS（原 TODO(#48) 注释解除）。
            # （route-registry 注册是链路必要步骤（模拟 navigation agent），
            # 与 input-lock 分歧无关。）
            (workspace / "harmony-project" / "oh-package-lock.json5").write_text(
                "{ lockfileVersion: 3 }\n", encoding="utf-8"
            )
            register_v3_route_for_verification(workspace)
            from test_stage3_workflow import freeze_environment

            freeze_environment(workspace, root / "henv.json")
            plan = root / "plan.json"
            plan.write_text(
                json.dumps(verification_plan_v3("HVER-DIV-001", "DIV"), indent=2)
                + "\n",
                encoding="utf-8",
            )
            run_cmd(
                sys.executable, str(SCAFFOLD_SCRIPTS / "run_verification.py"),
                "--workspace", str(workspace), "--plan", str(plan),
            )
            completed = run_cmd(
                sys.executable, str(SCAFFOLD_SCRIPTS / "validate_stage3.py"),

                "--workspace", str(workspace), "--henv-id", "HENV-001",
                "--verification-id", "HVER-DIV-001",
                "--reviewer", "architecture-acceptance-1",
                "--decision", "PASS",
                "--attest-real-file-review", "--attest-contract-only",
                "--attest-dependency-review", "--attest-runtime-smoke",
            )
            report = json.loads(completed.stdout)
            self.assertEqual(report["verdict"], "PASS", report)
            self.assertEqual(
                report["rules"]["data_contract_closure"]["status"], "PASS"
            )
            self.assertTrue((workspace / "CLOSED").is_file())


if __name__ == "__main__":
    unittest.main()