#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gate 3 v3（唯一路径）新四规则的单元与轻量集成测试。

覆盖（正反例）：
1. 功能承载面覆盖：RUNTIME feature 缺 ArkUI 载体拒 / 全有载体通过 / modal@HOST 通过；
2. 数据契约无孤儿：语义对象缺 interface 拒 / 孤儿契约拒 / 双向闭合通过；
3. 冒烟保留：必需类别（构建/安装/启动）覆盖判定的正反例（机制重链路沿用
   既有 run_verification 消费链基线，见 test_stage3_workflow.py 整改后的用例）；
4. 环境链保留：HENV 注册表 FROZEN/环境哈希/预检 PASS 的轻量正反例；
另含：input-lock v3 结构防御解析、CLI 唯一路径（无 --paradigm）分发。

与 D 的 test_scaffold_v3_gen.py 并存不冲突；本文件不依赖 init_scaffold v3。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

SCAFFOLD_SCRIPTS = HERE.parent
VALIDATOR = SCAFFOLD_SCRIPTS / "validate_stage3.py"

ACCEPTANCE_AGENT = "acc-agent-1"
TOOLCHAIN_AGENT = "toolchain-agent-1"
ARCH_LEAD = "arch-lead-1"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_cli(expect: int, *args: str | Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, str(VALIDATOR), *[str(arg) for arg in args]],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode != expect:
        raise AssertionError(
            f"Expected exit {expect}, got {completed.returncode}\nARGS: {args}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


class ValidatorMixin:
    validator = None

    @classmethod
    def setUpClass(cls) -> None:
        if cls.validator is None:
            load_module("_common", SCAFFOLD_SCRIPTS / "_common.py")
            cls.validator = load_module("validate_stage3_under_test", VALIDATOR)


class TestRouteOrMountParsing(ValidatorMixin, unittest.TestCase):
    def test_legal_values(self) -> None:
        errors: list[str] = []
        self.assertEqual("route", self.validator.parse_v3_route_or_mount("route", "s", errors))
        self.assertEqual("none", self.validator.parse_v3_route_or_mount("none", "s", errors))
        self.assertEqual(
            "modal", self.validator.parse_v3_route_or_mount("modal@PAGE-MAIN-1", "s", errors)
        )
        self.assertEqual([], errors)

    def test_illegal_values(self) -> None:
        for bad in ("modal@", "modal@ ", "popup", "Route", "", None, 3):
            errors: list[str] = []
            self.assertEqual(
                "", self.validator.parse_v3_route_or_mount(bad, "s[0]", errors), bad
            )
            self.assertTrue(errors, f"expected error for {bad!r}")


class TestSurfaceCarrierCoverage(ValidatorMixin, unittest.TestCase):
    @staticmethod
    def feature_map_entry(verify_mode: str, surfaces: list[dict]) -> dict:
        return {
            "feature_id": "FEATURE-X",
            "verify_mode": verify_mode,
            "surfaces": surfaces,
        }

    @staticmethod
    def blueprinted_plan(*surface_ids: str) -> dict:
        """合规 blueprint surface-plan（#89 修 3 正例 fixture）。"""
        return {
            "routes": [
                {
                    "surface_id": surface_id,
                    "preserve": {"policy": "UI_FIDELITY=HIGH", "texts": ["示例"]},
                    "native_component": "Navigation+NavPathStack+List/Scroll",
                    "native_carrier": "route：Navigation 路由节点（独立页面，NavDestination 承载）",
                }
                for surface_id in surface_ids
            ],
            "modals": [],
            "passthrough": [{"surface_id": "PAGE-CONTAINER-1", "kind": "container"}],
        }

    def test_runtime_feature_with_route_carrier_passes(self) -> None:
        feature_map = {
            "features": [self.feature_map_entry("RUNTIME", [
                {"id": "PAGE-A", "kind": "page", "is_container": False},
            ])]
        }
        errors: list[str] = []
        warnings: list[str] = []
        counts = self.validator.validate_v3_surface_carriers(
            feature_map, {"PAGE-A": "route"}, self.blueprinted_plan("PAGE-A"),
            errors, warnings,
        )
        self.assertEqual([], errors)
        self.assertEqual([], warnings)
        self.assertEqual(1, counts["runtime_features_carried"])

    def test_runtime_feature_with_modal_mount_passes(self) -> None:
        feature_map = {
            "features": [self.feature_map_entry("RUNTIME", [
                {"id": "PAGE-SHEET", "kind": "sheet", "is_container": False},
            ])]
        }
        errors: list[str] = []
        counts = self.validator.validate_v3_surface_carriers(
            feature_map, {"PAGE-SHEET": "modal"}, self.blueprinted_plan("PAGE-SHEET"),
            errors, [],
        )
        self.assertEqual([], errors)
        self.assertEqual(1, counts["runtime_features_carried"])

    def test_runtime_feature_with_none_carrier_is_rejected(self) -> None:
        feature_map = {
            "features": [self.feature_map_entry("RUNTIME", [
                {"id": "PAGE-A", "kind": "page", "is_container": False},
            ])]
        }
        errors: list[str] = []
        self.validator.validate_v3_surface_carriers(
            feature_map, {"PAGE-A": "none"}, self.blueprinted_plan("PAGE-A"),
            errors, [],
        )
        self.assertEqual(1, len(errors))
        self.assertIn("no non-container UI surface has an ArkUI carrier", errors[0])
        self.assertIn("FEATURE-X", errors[0])

    def test_runtime_feature_with_only_container_surfaces_is_rejected(self) -> None:
        feature_map = {
            "features": [self.feature_map_entry("RUNTIME", [
                {"id": "PAGE-HOST", "kind": "container", "is_container": True},
            ])]
        }
        errors: list[str] = []
        self.validator.validate_v3_surface_carriers(
            feature_map, {"PAGE-HOST": "route"}, self.blueprinted_plan(),
            errors, [],
        )
        self.assertEqual(1, len(errors))
        self.assertIn("has no non-container UI surface to carry it", errors[0])

    def test_runtime_feature_without_surfaces_is_rejected(self) -> None:
        feature_map = {"features": [self.feature_map_entry("RUNTIME", [])]}
        errors: list[str] = []
        self.validator.validate_v3_surface_carriers(
            feature_map, {}, self.blueprinted_plan(), errors, []
        )
        self.assertTrue(any("declares no surfaces" in error for error in errors))

    def test_source_confirm_feature_without_carrier_is_not_rejected(self) -> None:
        feature_map = {
            "features": [self.feature_map_entry("SOURCE_CONFIRM", [
                {"id": "PAGE-B", "kind": "page", "is_container": False},
            ])]
        }
        errors: list[str] = []
        counts = self.validator.validate_v3_surface_carriers(
            feature_map, {"PAGE-B": "none"}, self.blueprinted_plan("PAGE-B"),
            errors, [],
        )
        self.assertEqual([], errors)
        self.assertEqual(0, counts["runtime_features"])

    def test_undeclared_surface_downgrades_to_warning(self) -> None:
        feature_map = {
            "features": [
                self.feature_map_entry("RUNTIME", [
                    {"id": "PAGE-DECLARED", "kind": "page", "is_container": False},
                    {"id": "PAGE-EXTRA", "kind": "reusable-component", "is_container": False},
                ]),
            ]
        }
        errors: list[str] = []
        warnings: list[str] = []
        self.validator.validate_v3_surface_carriers(
            feature_map, {"PAGE-DECLARED": "route"}, self.blueprinted_plan("PAGE-DECLARED"),
            errors, warnings,
        )
        self.assertEqual([], errors)
        self.assertTrue(
            any("PAGE-EXTRA" in warning and "not declared" in warning for warning in warnings)
        )

    def test_container_fallback_via_kind_field(self) -> None:
        # is_container 缺失时回退 kind == container 判定
        feature_map = {
            "features": [self.feature_map_entry("RUNTIME", [
                {"id": "PAGE-HOST", "kind": "container"},
                {"id": "PAGE-A", "kind": "page"},
            ])]
        }
        errors: list[str] = []
        self.validator.validate_v3_surface_carriers(
            feature_map, {"PAGE-A": "route", "PAGE-HOST": "route"},
            self.blueprinted_plan("PAGE-A", "PAGE-HOST"), errors, [],
        )
        self.assertEqual([], errors)


class TestBlueprintFields(ValidatorMixin, unittest.TestCase):
    """#89 修 3：承载面覆盖规则的 blueprint 三字段扩展（不新增规则条数）。"""

    COMPLETE_ROUTE = {
        "surface_id": "PAGE-A",
        "preserve": {"policy": "UI_FIDELITY=HIGH", "texts": ["待办"], "palette": []},
        "native_component": "Navigation+NavPathStack+List/Scroll",
        "native_carrier": "route：Navigation 路由节点（独立页面，NavDestination 承载）",
    }
    COMPLETE_MODAL = {
        "surface_id": "PAGE-SHEET",
        "preserve": {"policy": "UI_FIDELITY=HIGH", "content_descs": ["关闭"]},
        "native_component": "bindSheet(detents MEDIUM/LARGE)",
        "native_carrier": "modal@PAGE-A：以 bindSheet/CustomDialog 模态挂载于宿主页面 PAGE-A",
    }

    def test_all_three_fields_present_passes(self) -> None:
        errors: list[str] = []
        counts = self.validator.check_v3_blueprint_fields(
            {
                "routes": [dict(self.COMPLETE_ROUTE)],
                "modals": [dict(self.COMPLETE_MODAL)],
                "passthrough": [{"surface_id": "PAGE-HOST", "kind": "container"}],
            },
            errors,
        )
        self.assertEqual([], errors)
        self.assertEqual(2, counts["user_visible_surfaces"])
        self.assertEqual(2, counts["blueprint_complete_surfaces"])

    def test_missing_preserve_fails(self) -> None:
        route = dict(self.COMPLETE_ROUTE)
        del route["preserve"]
        errors: list[str] = []
        self.validator.check_v3_blueprint_fields({"routes": [route], "modals": []}, errors)
        self.assertEqual(1, len(errors))
        self.assertIn("PAGE-A", errors[0])
        self.assertIn("preserve", errors[0])
        self.assertIn("regenerate the surface-plan", errors[0])

    def test_missing_native_component_fails(self) -> None:
        route = dict(self.COMPLETE_ROUTE)
        del route["native_component"]
        errors: list[str] = []
        self.validator.check_v3_blueprint_fields({"routes": [route], "modals": []}, errors)
        self.assertEqual(1, len(errors))
        self.assertIn("native_component", errors[0])

    def test_blank_native_carrier_fails(self) -> None:
        modal = dict(self.COMPLETE_MODAL, native_carrier="   ")
        errors: list[str] = []
        self.validator.check_v3_blueprint_fields({"routes": [], "modals": [modal]}, errors)
        self.assertEqual(1, len(errors))
        self.assertIn("native_carrier", errors[0])
        self.assertIn("PAGE-SHEET", errors[0])

    def test_empty_preserve_object_fails(self) -> None:
        route = dict(self.COMPLETE_ROUTE, preserve={})
        errors: list[str] = []
        self.validator.check_v3_blueprint_fields({"routes": [route], "modals": []}, errors)
        self.assertEqual(1, len(errors))
        self.assertIn("preserve", errors[0])

    def test_passthrough_without_fields_is_ignored(self) -> None:
        """passthrough（container/组件）无 UI：缺字段不影响。"""
        errors: list[str] = []
        counts = self.validator.check_v3_blueprint_fields(
            {
                "routes": [dict(self.COMPLETE_ROUTE)],
                "modals": [],
                "passthrough": [
                    {"surface_id": "PAGE-HOST", "kind": "container"},
                    {"surface_id": "WIDGET-1", "kind": "reusable-component"},
                ],
            },
            errors,
        )
        self.assertEqual([], errors)
        self.assertEqual(1, counts["user_visible_surfaces"])
        self.assertEqual(1, counts["blueprint_complete_surfaces"])

    def test_absent_or_unreadable_plan_fails_without_waiver(self) -> None:
        """surface-plan 缺失/不可读（含旧产物无文件）→ FAIL，无豁免。"""
        for bad in (None, {}, "not-a-plan"):
            errors: list[str] = []
            counts = self.validator.check_v3_blueprint_fields(bad, errors)
            self.assertEqual(1, len(errors), bad)
            self.assertIn("surface-plan.json is missing or unreadable", errors[0])
            self.assertIn("regenerate the surface-plan", errors[0])
            self.assertEqual(0, counts["user_visible_surfaces"])

    def test_legacy_plan_without_blueprint_fields_fails(self) -> None:
        """旧产物（批次 3 之前，routes 项无 blueprint 字段）→ 同样 FAIL。"""
        legacy_route = {"surface_id": "PAGE-A", "kind": "page", "route_id": "PAGE-A"}
        errors: list[str] = []
        self.validator.check_v3_blueprint_fields(
            {"routes": [legacy_route], "modals": [], "passthrough": []}, errors
        )
        self.assertEqual(1, len(errors))
        self.assertIn("PAGE-A", errors[0])
        for field in ("preserve", "native_component", "native_carrier"):
            self.assertIn(field, errors[0])

    def test_blueprint_errors_fail_rule_one_via_carrier_validator(self) -> None:
        """blueprint 缺失计入规则 1（塞进承载面覆盖，不新增规则条数）。"""
        feature_map = {
            "features": [
                {
                    "feature_id": "FEATURE-X",
                    "verify_mode": "RUNTIME",
                    "surfaces": [{"id": "PAGE-A", "kind": "page", "is_container": False}],
                }
            ]
        }
        errors: list[str] = []
        self.validator.validate_v3_surface_carriers(
            feature_map, {"PAGE-A": "route"},
            {"routes": [{"surface_id": "PAGE-A"}], "modals": [], "passthrough": []},
            errors, [],
        )
        self.assertTrue(
            any("lacks a non-empty blueprint field" in error for error in errors)
        )


class TestDataContractClosure(ValidatorMixin, unittest.TestCase):
    SEMANTIC = {("FEATURE-A", "todo_items"), ("FEATURE-B", "mmkv:sort_option")}

    @staticmethod
    def contract(feature: str, obj: str, interface: str = "ITodoStore") -> dict:
        return {"feature_id": feature, "data_object": obj, "interface": interface}

    def test_closed_both_ways_passes(self) -> None:
        errors: list[str] = []
        counts = self.validator.validate_v3_data_contracts(
            self.SEMANTIC,
            [
                self.contract("FEATURE-A", "todo_items"),
                self.contract("FEATURE-B", "mmkv:sort_option"),
            ],
            errors,
        )
        self.assertEqual([], errors)
        self.assertEqual(2, counts["semantic_data_objects"])
        self.assertEqual(0, counts["uncovered"])
        self.assertEqual(0, counts["orphans"])

    def test_uncovered_semantic_object_is_rejected(self) -> None:
        errors: list[str] = []
        self.validator.validate_v3_data_contracts(
            self.SEMANTIC, [self.contract("FEATURE-A", "todo_items")], errors
        )
        self.assertEqual(1, len(errors))
        self.assertIn("without an interface contract", errors[0])
        self.assertIn("FEATURE-B/mmkv:sort_option", errors[0])

    def test_orphan_contract_is_rejected(self) -> None:
        errors: list[str] = []
        self.validator.validate_v3_data_contracts(
            self.SEMANTIC,
            [
                self.contract("FEATURE-A", "todo_items"),
                self.contract("FEATURE-B", "mmkv:sort_option"),
                self.contract("FEATURE-C", "ghost_table"),
            ],
            errors,
        )
        self.assertEqual(1, len(errors))
        self.assertIn("orphaned outside data-relations", errors[0])
        self.assertIn("FEATURE-C/ghost_table", errors[0])

    def test_empty_interface_declaration_is_rejected(self) -> None:
        errors: list[str] = []
        self.validator.validate_v3_data_contracts(
            self.SEMANTIC,
            [
                self.contract("FEATURE-A", "todo_items"),
                self.contract("FEATURE-B", "mmkv:sort_option", interface="  "),
            ],
            errors,
        )
        self.assertTrue(any("lacks a non-empty interface declaration" in e for e in errors))

    def test_duplicate_contract_key_is_rejected(self) -> None:
        errors: list[str] = []
        self.validator.validate_v3_data_contracts(
            self.SEMANTIC,
            [
                self.contract("FEATURE-A", "todo_items"),
                self.contract("FEATURE-A", "todo_items", interface="IOther"),
                self.contract("FEATURE-B", "mmkv:sort_option"),
            ],
            errors,
        )
        self.assertTrue(any("Duplicate v3 data contract" in e for e in errors))

    def test_semantic_rows_with_blank_fields_are_not_objects(self) -> None:
        rows = [
            {"feature_id": "FEATURE-A", "data_object": "todo_items"},
            {"feature_id": "", "data_object": "todo_items"},      # <Insert>/<Update> 类
            {"feature_id": "FEATURE-A", "data_object": ""},       # 泛化 DAO 位置
            {"feature_id": "", "data_object": ""},
        ]
        self.assertEqual({("FEATURE-A", "todo_items")}, self.validator.semantic_data_objects(rows))

    def test_load_contracts_from_csv_file_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "data-contracts.csv"
            csv_path.write_text(
                "feature_id,data_object,interface\n"
                "FEATURE-A,todo_items,ITodoStore\n"
                "FEATURE-B,mmkv:sort_option,ISortStore\n",
                encoding="utf-8",
            )
            lock = {"data_contracts": {"path": str(csv_path), "sha256": "unlocked"}}
            errors: list[str] = []
            contracts = self.validator.load_v3_data_contracts(lock, errors)
            self.assertEqual([], errors)
            self.assertEqual(2, len(contracts))

    def test_load_contracts_rejects_missing_file(self) -> None:
        lock = {"data_contracts": {"path": "/nonexistent/contracts.csv", "sha256": "x"}}
        errors: list[str] = []
        contracts = self.validator.load_v3_data_contracts(lock, errors)
        self.assertEqual([], contracts)
        self.assertTrue(any("Cannot load v3 data-contracts" in e for e in errors))


class TestV3InputLockStructure(ValidatorMixin, unittest.TestCase):
    def test_legacy_schema_version_is_rejected(self) -> None:
        errors: list[str] = []
        view = self.validator.validate_v3_input_lock({"schema_version": "gmi-1"}, errors)
        # #48 裁定：E 的比较串已对齐 D 的字面值 'scaffold-v3'。
        self.assertTrue(
            any("requires input-lock schema_version 'scaffold-v3'" in e for e in errors)
        )
        self.assertEqual({}, view["inputs"])

    def test_missing_required_input_keys_reported_individually(self) -> None:
        lock = {
            "schema_version": "v3",
            "inputs": {"feature_map": {"path": "/tmp/fm.json", "sha256": "x"}},
            "surfaces": [{"surface_id": "PAGE-A", "route_or_mount": "route"}],
            "data_contracts": [],
        }
        errors: list[str] = []
        self.validator.validate_v3_input_lock(lock, errors)
        for key in (
            "navigation_relations", "data_relations", "scope", "phase2_gate", "phase2_closure",
        ):
            self.assertTrue(
                any(f"inputs.{key}" in e for e in errors), f"missing report for {key}"
            )
        self.assertFalse(any("inputs.feature_map" in e for e in errors))

    def test_lock_surface_identifier_fallbacks(self) -> None:
        errors: list[str] = []
        indexed = self.validator.index_v3_lock_surfaces(
            [
                {"surface_id": "PAGE-A", "route_or_mount": "route"},
                {"id": "PAGE-B", "route_or_mount": "modal@PAGE-A"},
                {"page_id": "PAGE-C", "route_or_mount": "none"},
            ],
            errors,
        )
        self.assertEqual([], errors)
        self.assertEqual({"PAGE-A": "route", "PAGE-B": "modal", "PAGE-C": "none"}, indexed)

    def test_locked_path_hash_mismatch_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = (Path(tmp) / "feature-map.json").resolve()
            target.write_text("{}", encoding="utf-8")
            lock = {"inputs": {"feature_map": {
                "path": str(target), "sha256": "0" * 64,
            }}}
            errors: list[str] = []
            self.validator.check_locked_path_records(lock, "input_lock", errors)
            self.assertEqual(1, len(errors))
            self.assertIn("has changed", errors[0])


class TestSmokeCategoryCoverage(ValidatorMixin, unittest.TestCase):
    BASE_COUNTS = {
        "TOOLCHAIN": 1, "CLEAN_BUILD": 1, "BUNDLE_CHECK": 1, "SIGNING_CHECK": 1,
        "INSTALL": 1, "LAUNCH": 1, "DEVICE": 1, "ROUTE_SMOKE": 1, "SCREENSHOT_CAPTURE": 1,
    }

    def test_full_smoke_pipeline_passes(self) -> None:
        errors: list[str] = []
        self.validator.check_v3_smoke_category_coverage(
            dict(self.BASE_COUNTS),
            {"DEVICE": {"DEV-1"}, "BUNDLE_CHECK": {"DEV-1"}, "INSTALL": {"DEV-1"},
             "LAUNCH": {"DEV-1"}, "ROUTE_SMOKE": {"DEV-1"}},
            {"DEV-1"},
            errors,
        )
        self.assertEqual([], errors)

    def test_missing_install_category_is_rejected(self) -> None:
        counts = dict(self.BASE_COUNTS)
        counts["INSTALL"] = 0
        errors: list[str] = []
        self.validator.check_v3_smoke_category_coverage(counts, {}, {"DEV-1"}, errors)
        self.assertTrue(any("lacks command category: INSTALL" in e for e in errors))

    def test_duplicate_clean_build_is_rejected(self) -> None:
        counts = dict(self.BASE_COUNTS)
        counts["CLEAN_BUILD"] = 2
        errors: list[str] = []
        self.validator.check_v3_smoke_category_coverage(counts, {}, {"DEV-1"}, errors)
        self.assertTrue(any("exactly one CLEAN_BUILD" in e for e in errors))

    def test_launch_device_coverage_gap_is_rejected(self) -> None:
        errors: list[str] = []
        self.validator.check_v3_smoke_category_coverage(
            dict(self.BASE_COUNTS),
            {"INSTALL": {"DEV-1", "DEV-2"}, "LAUNCH": {"DEV-1"}, "DEVICE": {"DEV-1", "DEV-2"},
             "BUNDLE_CHECK": {"DEV-1", "DEV-2"}, "ROUTE_SMOKE": {"DEV-1", "DEV-2"}},
            {"DEV-1", "DEV-2"},
            errors,
        )
        self.assertTrue(any("LAUNCH device coverage differs" in e for e in errors))


class TestEnvironmentChain(ValidatorMixin, unittest.TestCase):
    @staticmethod
    def build_env_workspace(root: Path, frozen: bool = True, preflight_pass: bool = True) -> Path:
        workspace = root / "ws"
        env_dir = workspace / "environments" / "HENV-001"
        env_dir.mkdir(parents=True)
        environment = {
            "devices": [
                {"device_id": "DEV-1", "required": True, "serial": "emulator-5554"},
            ],
        }
        env_path = env_dir / "harmony-environment.json"
        env_path.write_text(json.dumps(environment), encoding="utf-8")
        registry = workspace / "environments" / "henv-registry.csv"
        digest = sha256_bytes(env_path.read_bytes()) if frozen else "0" * 64
        registry.write_text(
            "henv_id,status,environment_sha256\n"
            f"HENV-001,{'FROZEN' if frozen else 'ACTIVE'},{digest}\n",
            encoding="utf-8",
        )
        verification = workspace / "verification" / "HVER-001"
        verification.mkdir(parents=True)
        preflight = {
            "verdict": "PASS" if preflight_pass else "FAIL",
            "henv_id": "HENV-001",
            "environment_sha256": digest if frozen else None,
        }
        (verification / "deveco-preflight-report.json").write_text(
            json.dumps(preflight), encoding="utf-8"
        )
        return workspace

    def test_frozen_henv_with_passing_preflight_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.build_env_workspace(Path(tmp))
            errors: list[str] = []
            environment, devices, required, env_path = self.validator.validate_v3_environment_chain(
                workspace, "HENV-001", workspace / "verification" / "HVER-001", errors
            )
            self.assertEqual([], errors)
            self.assertEqual({"DEV-1"}, required)
            self.assertTrue(env_path.is_file())

    def test_unfrozen_henv_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.build_env_workspace(Path(tmp), frozen=False)
            errors: list[str] = []
            self.validator.validate_v3_environment_chain(
                workspace, "HENV-001", workspace / "verification" / "HVER-001", errors
            )
            self.assertTrue(any("HENV is not frozen" in e for e in errors))

    def test_failing_preflight_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.build_env_workspace(Path(tmp), preflight_pass=False)
            errors: list[str] = []
            self.validator.validate_v3_environment_chain(
                workspace, "HENV-001", workspace / "verification" / "HVER-001", errors
            )
            self.assertTrue(any("preflight is not PASS" in e for e in errors))

    def test_environment_without_required_device_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.build_env_workspace(Path(tmp))
            env_path = workspace / "environments" / "HENV-001" / "harmony-environment.json"
            environment = {"devices": [{"device_id": "DEV-9", "required": False}]}
            env_path.write_text(json.dumps(environment), encoding="utf-8")
            digest = sha256_bytes(env_path.read_bytes())
            registry = workspace / "environments" / "henv-registry.csv"
            registry.write_text(
                "henv_id,status,environment_sha256\n"
                f"HENV-001,FROZEN,{digest}\n",
                encoding="utf-8",
            )
            errors: list[str] = []
            self.validator.validate_v3_environment_chain(
                workspace, "HENV-001", workspace / "verification" / "HVER-001", errors
            )
            self.assertTrue(any("no required device" in e for e in errors))


class TestCliSolePath(unittest.TestCase):
    """CLI 唯一路径：无 --paradigm 参数，v3 直接生效。"""

    def test_paradigm_flag_no_longer_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [sys.executable, str(VALIDATOR), "--workspace", tmp,
                 "--henv-id", "HENV-001", "--verification-id", "HVER-001",
                 "--reviewer", "acc-1", "--decision", "INCOMPLETE",
                 "--paradigm", "v3"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("unrecognized arguments", completed.stderr)

    def test_empty_workspace_reports_v3_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = run_cli(
                1, "--workspace", tmp, "--henv-id", "HENV-001",
                "--verification-id", "HVER-001", "--reviewer", "acc-1",
                "--decision", "INCOMPLETE",
            )
            report = json.loads(completed.stdout)
            self.assertEqual("v3", report["paradigm"])
            self.assertEqual("INCOMPLETE", report["verdict"])
            self.assertTrue(
                any("Cannot load stage-03-input-lock.json" in e for e in report["errors"])
            )
            for rule in report["rules"].values():
                self.assertEqual("FAIL", rule["status"])

    def test_invalid_henv_id_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [sys.executable, str(VALIDATOR), "--workspace", tmp,
                 "--henv-id", "bad id with spaces", "--verification-id", "HVER-001",
                 "--reviewer", "acc-1", "--decision", "INCOMPLETE"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(2, completed.returncode)


class TestGateReportIntegration(unittest.TestCase):
    """轻量集成：规则 1/2 在真实 CLI 路径上通过，冒烟/环境链因缺包而 FAIL。"""

    @staticmethod
    def build_v3_workspace(
        root: Path,
        *,
        orphan_contract: bool = False,
        drop_blueprint_field: str | None = None,
        write_surface_plan: bool = True,
    ) -> Path:
        workspace = root / "ws"
        inputs = workspace / "inputs"
        inputs.mkdir(parents=True)
        (inputs / "phase-1-scope.snapshot.json").write_text("{}", encoding="utf-8")

        feature_map = {
            "features": [
                {
                    "feature_id": "FEATURE-LOGIN",
                    "verify_mode": "RUNTIME",
                    "surfaces": [
                        {"id": "PAGE-LOGIN", "kind": "page", "is_container": False},
                    ],
                },
                {
                    "feature_id": "FEATURE-SHELL",
                    "verify_mode": "SOURCE_CONFIRM",
                    "surfaces": [
                        {"id": "PAGE-HOST", "kind": "container", "is_container": True},
                    ],
                },
            ],
        }
        (inputs / "feature-map.json").write_text(
            json.dumps(feature_map, ensure_ascii=False), encoding="utf-8"
        )
        (inputs / "phase-02-navigation-relations.csv").write_text(
            "from_page_id,to_page_id\n", encoding="utf-8"
        )
        (inputs / "phase-02-data-relations.csv").write_text(
            "relation_id,feature_id,data_object,relation\n"
            "REL-1,FEATURE-LOGIN,account_store,read\n"
            "REL-2,,<Insert>,write\n",
            encoding="utf-8",
        )
        (inputs / "phase-1-scope.json").write_text(
            json.dumps({"migration_scope": {}}), encoding="utf-8"
        )
        (inputs / "phase-02-gate-report.json").write_text(
            json.dumps({"phase": 2, "verdict": "PASS"}), encoding="utf-8"
        )
        (inputs / "phase-2-closure.json").write_text(
            json.dumps({"final_verdict": "PASS", "evidence_chain_closed": True}),
            encoding="utf-8",
        )
        contracts = [
            {"feature_id": "FEATURE-LOGIN", "data_object": "account_store",
             "interface": "IAccountStore"},
        ]
        if orphan_contract:
            contracts.append(
                {"feature_id": "FEATURE-GHOST", "data_object": "ghost_db",
                 "interface": "IGhost"}
            )
        lock = {
            "schema_version": "scaffold-v3",
            "inputs": {
                key: {
                    "path": str((workspace / "inputs" / name).resolve()),
                    "sha256": sha256_bytes((workspace / "inputs" / name).read_bytes()),
                }
                for key, name in (
                    ("feature_map", "feature-map.json"),
                    ("navigation_relations", "phase-02-navigation-relations.csv"),
                    ("data_relations", "phase-02-data-relations.csv"),
                    ("scope", "phase-1-scope.json"),
                    ("phase2_gate", "phase-02-gate-report.json"),
                    ("phase2_closure", "phase-2-closure.json"),
                )
            },
            "surfaces": [
                {"surface_id": "PAGE-LOGIN", "route_or_mount": "route"},
                {"surface_id": "PAGE-HOST", "route_or_mount": "none"},
            ],
            "data_contracts": contracts,
        }
        (workspace / "stage-03-input-lock.json").write_text(
            json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (workspace / "phase-manifest.json").write_text(
            json.dumps({
                "phase": 3,
                "run_id": "RUN-TEST",
                "ownership": {
                    "architecture_lead_id": ARCH_LEAD,
                    "toolchain_agent_id": TOOLCHAIN_AGENT,
                    "architecture_acceptance_agent_id": ACCEPTANCE_AGENT,
                },
            }),
            encoding="utf-8",
        )
        # #89 修 3：surface-plan blueprint 三字段进入规则 1 校验。
        if write_surface_plan:
            login_blueprint = {
                "surface_id": "PAGE-LOGIN",
                "preserve": {"policy": "UI_FIDELITY=HIGH", "texts": ["登录"]},
                "native_component": "Navigation+NavPathStack+List/Scroll",
                "native_carrier": "route：Navigation 路由节点（独立页面，NavDestination 承载）",
            }
            if drop_blueprint_field:
                login_blueprint.pop(drop_blueprint_field, None)
            (workspace / "surface-plan.json").write_text(
                json.dumps(
                    {
                        "routes": [login_blueprint],
                        "modals": [],
                        # passthrough（container）无 UI：不需要 blueprint 字段。
                        "passthrough": [{"surface_id": "PAGE-HOST", "kind": "container"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        return workspace

    def test_rules_one_and_two_pass_on_real_cli_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.build_v3_workspace(Path(tmp))
            completed = run_cli(
                1, "--workspace", str(workspace), "--henv-id", "HENV-001",
                "--verification-id", "HVER-001", "--reviewer", ACCEPTANCE_AGENT,
                "--decision", "INCOMPLETE",
            )
            report = json.loads(completed.stdout)
            self.assertEqual("PASS", report["rules"]["surface_carrier_coverage"]["status"])
            self.assertEqual("PASS", report["rules"]["data_contract_closure"]["status"])
            self.assertEqual(1, report["counts"]["runtime_features"])
            self.assertEqual(1, report["counts"]["runtime_features_carried"])
            self.assertEqual(1, report["counts"]["semantic_data_objects"])
            self.assertEqual(1, report["counts"]["data_contracts"])
            # 冒烟/环境链因未提供验证包必然 FAIL（由既有消费链基线另行覆盖）
            self.assertEqual("FAIL", report["rules"]["smoke_chain"]["status"])
            self.assertEqual("FAIL", report["rules"]["environment_chain"]["status"])

    def test_missing_blueprint_field_fails_rule_one_on_real_cli_path(self) -> None:
        """#89 修 3：用户可见 surface 缺任一 blueprint 字段 → 规则 1 FAIL。"""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.build_v3_workspace(
                Path(tmp), drop_blueprint_field="preserve"
            )
            completed = run_cli(
                1, "--workspace", str(workspace), "--henv-id", "HENV-001",
                "--verification-id", "HVER-001", "--reviewer", ACCEPTANCE_AGENT,
                "--decision", "INCOMPLETE",
            )
            report = json.loads(completed.stdout)
            self.assertEqual("FAIL", report["rules"]["surface_carrier_coverage"]["status"])
            self.assertTrue(
                any(
                    "PAGE-LOGIN" in e and "preserve" in e
                    and "lacks a non-empty blueprint field" in e
                    for e in report["errors"]
                ),
                report["errors"],
            )
            self.assertTrue(
                any("regenerate the surface-plan" in e for e in report["errors"]),
                report["errors"],
            )

    def test_absent_surface_plan_fails_rule_one_without_waiver(self) -> None:
        """#89 修 3：无 surface-plan（旧产物）→ 规则 1 FAIL，无豁免。"""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.build_v3_workspace(Path(tmp), write_surface_plan=False)
            completed = run_cli(
                1, "--workspace", str(workspace), "--henv-id", "HENV-001",
                "--verification-id", "HVER-001", "--reviewer", ACCEPTANCE_AGENT,
                "--decision", "INCOMPLETE",
            )
            report = json.loads(completed.stdout)
            self.assertEqual("FAIL", report["rules"]["surface_carrier_coverage"]["status"])
            self.assertTrue(
                any(
                    "surface-plan.json is missing or unreadable" in e
                    for e in report["errors"]
                ),
                report["errors"],
            )

    def test_orphan_contract_fails_rule_two_on_real_cli_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.build_v3_workspace(Path(tmp), orphan_contract=True)
            completed = run_cli(
                1, "--workspace", str(workspace), "--henv-id", "HENV-001",
                "--verification-id", "HVER-001", "--reviewer", ACCEPTANCE_AGENT,
                "--decision", "INCOMPLETE",
            )
            report = json.loads(completed.stdout)
            self.assertEqual("FAIL", report["rules"]["data_contract_closure"]["status"])
            self.assertTrue(
                any("orphaned outside data-relations" in e for e in report["errors"])
            )

    def test_tampered_locked_input_fails_hash_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.build_v3_workspace(Path(tmp))
            target = workspace / "inputs" / "feature-map.json"
            target.write_text(
                json.dumps({"features": []}), encoding="utf-8"
            )
            completed = run_cli(
                1, "--workspace", str(workspace), "--henv-id", "HENV-001",
                "--verification-id", "HVER-001", "--reviewer", ACCEPTANCE_AGENT,
                "--decision", "INCOMPLETE",
            )
            report = json.loads(completed.stdout)
            self.assertTrue(any("has changed" in e for e in report["errors"]))

    def test_reviewer_mismatch_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.build_v3_workspace(Path(tmp))
            completed = subprocess.run(
                [sys.executable, str(VALIDATOR), "--workspace", str(workspace),
                 "--henv-id", "HENV-001", "--verification-id", "HVER-001",
                 "--reviewer", "someone-else", "--decision", "INCOMPLETE"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("architecture_acceptance_agent_id", completed.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)