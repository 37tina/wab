#!/usr/bin/env python3
"""v4 Phase 4 initialization reachability tests (task #59 rewrite).

v4 语义（G 的 init_implementation.py v4 重写后唯一路径）：

1. ``test_v4_main_initializes_feature_dispatch``
   构造 v4 七类核心产物夹具（feature-map / 17 列 behavior-contracts 含
   semantic_input / data-relations / reconciliation / runtime-chains /
   gmi 闭包 / Phase 3 骨架 16 项 / H4ENV），以真实（未打补丁）的
   ``build_feature_manifest`` 口径冻结工单 feature_manifest，跑通
   ``main()`` 并断言 v4 产出面：feature-dispatch.json（按功能分派）、
   surface-contracts.csv（薄表骨架）、implementation-ledger.csv、
   schema 2.0 输入锁（feature_manifest/feature_dispatch/surface_contracts
   哈希绑定）与 H4ENV 落盘。仅 stub 设备/外部子进程依赖：
   - ``init_implementation.subprocess.run``：只读 Gate 3 recheck 子进程；
   - ``init_implementation.validate_environment_config``：跳过工具链/
     可执行文件哈希绑定，结构等价归一化。
   输入锁/闭包/快照/注册表/工单绑定校验全部真实执行。

2. ``test_v4_single_path_retires_native_and_exempt_machinery``
   AST 级守护：旧机制（gmi_exempt_input_keys 豁免集、gmi_native_layout
   探测、compile_native_behavior_contracts / compile_page_contracts /
   publish_page_contracts 页面合同编译、prepare_uitest_probe 探针生成、
   page-contract-registry 页面范式产物）在 init_implementation.py 中
   不复存在；v4 锚点（STAGE4_INPUT_RELATIVES 16 键、BC_SEMANTIC_COLUMNS
   七段子集含 semantic_input、main 内 build_feature_manifest 防御性
   重算）必须在场。

3. ``test_stage4_input_relatives_identical_in_init_and_controller_issue``
   防漂移（原 17e 的 v4 继任）：init_implementation.py 与 controller
   issue_phase4_work_order.py 的 STAGE4_INPUT_RELATIVES / BC_SEMANTIC_COLUMNS
   必须字典级（AST 字面量）完全一致，防止任何一侧单方改动输入面导致
   签发/初始化级联断裂。
"""

from __future__ import annotations

import ast
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
SKILL_ROOT = SCRIPTS.parent
SKILLS_ROOT = SKILL_ROOT.parent
CONTROLLER_ISSUE_PATH = (
    SKILLS_ROOT / "android-harmony-migration-controller" / "scripts" / "issue_phase4_work_order.py"
)
sys.path.insert(0, str(SCRIPTS))

import init_implementation as init_impl  # noqa: E402


FIXTURE_ROOT = Path("/tmp/f4-v4-fix")

LEAD = "impl-lead"
CONTROLLER_ACTOR = "controller-lead"
H4ENV_ID = "H4ENV-EMU01"
BASE_HENV_ID = "HENV-EMU01"
FEATURE_ID = "FEATURE-HOME"

# v4 七段结构必需列（表头 fail-closed 子集；semantic_input 为 v4 新增）
BC_V4_HEADER = [
    "bc_id", "feature_id", "page_ref", "user_intent", "pre_state",
    "operation", "data_state_change", "business_computation_refs",
    "observable_result", "persistence_targets", "external_side_effects",
    "evidence_class", "impact", "source_refs",
    "operation_steps", "result_assertions",
    "semantic_input",
]


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, header: list[str], rows: list[list[object]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        for row in rows or []:
            writer.writerow(row)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_v4_run(root: Path) -> tuple[Path, Path, Path]:
    """Build a minimal but genuinely verified v4 run fixture.

    Everything ``main()`` verifies through its real (unpatched) code path is
    constructed for real: the 7-class Phase 2 fact space (① feature-map /
    ② 17-column behavior contracts with semantic_input / ③ data-relations /
    ④ reconciliation / ⑤ runtime-chains + gmi closure), the Phase 3 scaffold
    closure (16 registry/input inputs, exact closure manifest, snapshot),
    and the controller work order whose feature_manifest is frozen through
    the genuine ``build_feature_manifest`` (so the defensive recompute in
    main() compares like-for-like).
    """

    run_dir = root / "run-v4"
    phase2 = run_dir / "phase-02-android-inventory"
    phase3 = run_dir / "phase-03-harmony-scaffold"
    controller = run_dir / "controller"

    # ---------------- phase-02: 7-class v4 fact space ----------------------
    _write_json(phase2 / "feature-map.json", {
        "schema_version": 1,
        "coverage_gate": {"included_features_covered": True, "included": [FEATURE_ID]},
        "features": [{
            "feature_id": FEATURE_ID,
            "name": "home",
            "summary": "home list with persisted seed",
            "source_refs": ["feature/home/HomeScreen.kt"],
            "surfaces": [
                {"id": "PAGE-HOME", "kind": "page", "is_container": False},
                {"id": "SHEET-ADD", "kind": "sheet", "is_container": False},
            ],
            "data_objects": {"writes": ["mmkv:home_seed"], "reads": []},
            "risk_level": "high",
            "verify_mode": "RUNTIME",
            "status": "OPEN",
        }],
    })
    _write_csv(
        phase2 / "behavior-contracts.csv",
        BC_V4_HEADER,
        [[
            "BC-HOME-LOAD", FEATURE_ID, "PAGE-HOME", "see the home list",
            "app launched", "launch", "home seed persisted", "",
            "home list visible", "mmkv:home_seed", "none",
            "RUNTIME_REQUIRED", "high", "feature/home/HomeScreen.kt",
            '[{"action": "launch", "target": "home"}]',
            '[{"kind": "text_visible", "value": "home"}]',
            "启动应用进入首页，在新建表单输入标题 TEST-X 后返回列表",
        ]],
    )
    _write_csv(
        phase2 / "data-relations.csv",
        ["relation_id", "feature_id", "data_object", "relation"],
        [["REL-HOME-1", FEATURE_ID, "mmkv:home_seed", "write"]],
    )
    _write_csv(
        phase2 / "reconciliation.csv",
        ["bc_id", "feature_id", "verdict"],
        [["BC-HOME-LOAD", FEATURE_ID, "CONFIRMED"]],
    )
    _write_csv(
        phase2 / "runtime-evidence" / "runtime-chains.csv",
        ["bc_id", "feature_id", "chain_status"],
        [["BC-HOME-LOAD", FEATURE_ID, "PASS"]],
    )
    _write_json(phase2 / "phase-2-closure.json", {
        "generator": "gmi_closure",
        "gate": {"unmapped": 0, "audit_discrepancy": 0},
    })
    # run 根同步副本（gmi 闭包链盖章形态；init 消费 workspace 内权威份）
    _write_json(run_dir / "phase-2-closure.json", {
        "generator": "gmi_closure",
        "gate": {"unmapped": 0, "audit_discrepancy": 0},
    })

    # ---------------- phase-03: scaffold closure (16 inputs) ---------------
    project_file = phase3 / "harmony-project" / "entry" / "src" / "main" / "ets" / "pages" / "Home.ets"
    _write_text(project_file, "// frozen scaffold page shell\n")

    entries = [{
        "path": "harmony-project/entry/src/main/ets/pages/Home.ets",
        "sha256": _sha256(project_file),
        "size": project_file.stat().st_size,
    }]
    canonical = json.dumps(entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    _write_json(phase3 / "scaffold-snapshot-manifest.json", {
        "entries": entries,
        "entry_count": len(entries),
        "snapshot_sha256": init_impl.sha256_text(canonical),
        "excluded_generated_parts": [],
    })

    _write_json(phase3 / "stage-03-input-lock.json", {"schema_version": "1.0"})
    _write_csv(phase3 / "module-registry.csv", ["harmony_module_id", "status"], [["HM-ENTRY", "READY"]])
    _write_csv(
        phase3 / "route-registry.csv",
        ["route_id", "status", "page_id", "harmony_module_id"],
        [["ROUTE-HOME", "READY", "PAGE-HOME", "HM-ENTRY"]],
    )
    _write_csv(phase3 / "surface-registry.csv", ["surface_shell_id", "surface_kind", "status"])
    _write_csv(
        phase3 / "capability-contracts.csv",
        ["capability_requirement_id", "capability_contract_id", "status"],
    )

    henv_file = phase3 / "environments" / BASE_HENV_ID / "harmony-environment.json"
    _write_json(henv_file, {"henv_id": BASE_HENV_ID})
    _write_csv(
        phase3 / "environments" / "henv-registry.csv",
        ["henv_id", "status", "environment_sha256"],
        [[BASE_HENV_ID, "FROZEN", _sha256(henv_file)]],
    )

    snapshot_sha = json.loads(
        (phase3 / "scaffold-snapshot-manifest.json").read_text(encoding="utf-8")
    )["snapshot_sha256"]
    gate_report = {
        "phase": 3,
        "verdict": "PASS",
        "errors": [],
        "source_snapshot_sha256": snapshot_sha,
    }
    _write_json(phase3 / "stage-03-gate-report.json", gate_report)
    _write_text(
        phase3 / "stage-03-closure-manifest.sha256",
        init_impl.closure_manifest_text(
            phase3,
            exact_excludes=init_impl.PHASE3_CLOSURE_EXCLUDES,
            directory_excludes=init_impl.P3_GENERATED_DIR_EXCLUDES,
        ),
    )
    _write_text(phase3 / "CLOSED", _sha256(phase3 / "stage-03-gate-report.json") + "\n")

    # ---------------- controller ------------------------------------------
    _write_json(controller / "scope.json", {
        "run_id": "RUN-V4-FIX",
        "project_id": "PROJ-V4-FIX",
        "migration_scope": {
            "visual_parity_mode": "native-adaptive",
            "included_features": [FEATURE_ID],
            "excluded_features": [],
        },
        "environments": [{"env_id": "ENV-ANDROID-1", "resolution": "1080x2340"}],
        "ownership": {"migration_controller_id": CONTROLLER_ACTOR},
    })
    _write_json(controller / "gate-report.json", gate_report)
    _write_json(controller / "gate-snapshots" / "gate3.json", gate_report)

    _write_json(
        controller / "work-orders" / "WO-P3-SCAFFOLD.json",
        {"work_order_id": "WO-P3-SCAFFOLD", "phase": 3, "ownership": {"scaffold_lead_id": "scaffold-lead-1"}},
    )
    wo3_path = controller / "work-orders" / "WO-P3-SCAFFOLD.json"
    wo3_sha = _sha256(wo3_path)

    scope_sha = _sha256(controller / "scope.json")
    gate_sha = _sha256(controller / "gate-report.json")
    henv_sha = _sha256(henv_file)

    # feature_manifest 按真实口径冻结（main() 的防御性重算随后逐字节比对）
    feature_manifest, shared_data_relation_ids = init_impl.build_feature_manifest(
        phase2 / "feature-map.json",
        phase2 / "behavior-contracts.csv",
        phase2 / "data-relations.csv",
        phase2 / "reconciliation.csv",
        phase2 / "runtime-evidence" / "runtime-chains.csv",
        [FEATURE_ID],
    )

    work_order: dict[str, object] = {
        "work_order_id": "WO-P4-V4",
        "run_id": "RUN-V4-FIX",
        "phase": 4,
        "status": "ISSUED",
        "issued_by": CONTROLLER_ACTOR,
        "scope_relative_path": "controller/scope.json",
        "scope_sha256": scope_sha,
        "required_skill": "harmonyos-feature-implementation",
        "business_implementation_allowed": True,
        "mp4_allowed": False,
        "included_features": [FEATURE_ID],
        "excluded_features": [],
        "ownership": {
            "implementation_lead_id": LEAD,
            "visual_asset_agent_id": "asset-agent",
            "verification_executor_id": "verify-exec",
            "parity_acceptance_agent_id": "parity-agent",
        },
        "upstream_phase3_work_order_relative_path": "controller/work-orders/WO-P3-SCAFFOLD.json",
        "upstream_phase3_work_order_id": "WO-P3-SCAFFOLD",
        "upstream_phase3_work_order_sha256": wo3_sha,
        "controller_gate3_snapshot_relative_path": "controller/gate-snapshots/gate3.json",
        "controller_gate3_sha256": gate_sha,
        "feature_manifest": feature_manifest,
        "shared_data_relation_ids": shared_data_relation_ids,
        "phase3_henvs": [{
            "henv_id": BASE_HENV_ID,
            "relative_path": f"phase-03-harmony-scaffold/environments/{BASE_HENV_ID}/harmony-environment.json",
            "sha256": henv_sha,
        }],
    }
    for digest_key, relative in init_impl.STAGE4_INPUT_RELATIVES.items():
        source = run_dir / relative
        assert source.is_file(), f"missing v4 input: {relative}"
        work_order[digest_key] = _sha256(source)
        work_order[digest_key.removesuffix("_sha256") + "_relative_path"] = relative

    wo4_path = controller / "work-orders" / "WO-P4-V4.json"
    _write_json(wo4_path, work_order)
    _write_csv(
        controller / "work-order-registry.csv",
        ["work_order_id", "phase", "status", "relative_path", "scope_sha256",
         "work_order_sha256", "issued_by"],
        [
            ["WO-P3-SCAFFOLD", "3", "ISSUED", "controller/work-orders/WO-P3-SCAFFOLD.json",
             "", wo3_sha, CONTROLLER_ACTOR],
            ["WO-P4-V4", "4", "ISSUED", "controller/work-orders/WO-P4-V4.json",
             scope_sha, _sha256(wo4_path), CONTROLLER_ACTOR],
        ],
    )

    h4env_path = root / "h4env-emu01.json"
    _write_json(h4env_path, {
        "h4env_id": H4ENV_ID,
        "source_android_env_id": "ENV-ANDROID-1",
        "base_henv_id": BASE_HENV_ID,
        "device_id": "HDEVICE-EMU01",
        "created_by": LEAD,
        "required": True,
        "comparison": {
            "screenshot_width": 1080,
            "screenshot_height": 2340,
            "content_bounds": [0, 0, 1080, 2340],
            "geometry_tolerance_px": 2,
        },
    })
    return run_dir, wo4_path, h4env_path


def _fake_validate_environment_config(config_path, scope_envs, base_henvs, henv_rows, lead, frozen_at):
    """Structure-equivalent normalization; skips toolchain/executable binding."""

    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    return {
        "h4env_id": config["h4env_id"],
        "source_android_env_id": config["source_android_env_id"],
        "base_henv_id": config["base_henv_id"],
        "device_id": config["device_id"],
        "device_serial": "emulator-5554",
        "bundle_name": "com.example.fix",
        "created_by": lead,
        "required": True,
        "frozen_at": frozen_at,
        "device_selector_tokens": ["emulator-5554"],
        "category_contracts": {},
        "comparison": config["comparison"],
        "business_profile": {},
        "base_henv_sha256": "",
        "base_application": {},
        "base_toolchain": {},
        "emulator": {},
    }


class NativePhase4InitTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self._reset_fixture_root()
        FIXTURE_ROOT.mkdir(parents=True)

    @staticmethod
    def _reset_fixture_root() -> None:
        # main() freezes parts of its output tree read-only (0444/0555);
        # restore write permission top-down so rmtree can actually unlink.
        if FIXTURE_ROOT.is_dir():
            for current, dirnames, _filenames in os.walk(FIXTURE_ROOT):
                for name in dirnames:
                    os.chmod(Path(current) / name, 0o755)
            os.chmod(FIXTURE_ROOT, 0o755)
        shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)

    def tearDown(self) -> None:
        self._reset_fixture_root()

    def test_v4_main_initializes_feature_dispatch(self) -> None:
        run_dir, work_order_path, h4env_path = _build_v4_run(FIXTURE_ROOT)
        phase_dir = run_dir / "phase-04-harmony-implementation"

        argv = [
            "init_implementation.py",
            "--run-dir", str(run_dir),
            "--work-order", str(work_order_path),
            "--implementation-lead", LEAD,
            "--environment-config", str(h4env_path),
        ]
        recheck_stub = Mock(returncode=0, stdout="", stderr="")

        with patch.object(sys, "argv", argv), \
                patch.object(init_impl.subprocess, "run", return_value=recheck_stub), \
                patch.object(init_impl, "validate_environment_config",
                             side_effect=_fake_validate_environment_config), \
                redirect_stdout(io.StringIO()):
            return_code = init_impl.main()

        self.assertEqual(0, return_code)

        # v4 功能分派表：per-feature 语义分派（verify_mode/BC/数据/surfaces）
        dispatch = json.loads(
            (phase_dir / "feature-dispatch.json").read_text(encoding="utf-8")
        )
        self.assertEqual(1, dispatch["schema_version"])
        self.assertEqual("WO-P4-V4", dispatch["work_order_id"])
        self.assertEqual(1, len(dispatch["dispatch"]))
        entry = dispatch["dispatch"][0]
        self.assertEqual(FEATURE_ID, entry["feature_id"])
        self.assertEqual("RUNTIME", entry["verify_mode"])
        self.assertEqual(["BC-HOME-LOAD"], entry["bc_ids"])
        self.assertEqual(["BC-HOME-LOAD"], entry["runtime_bc_ids"])
        self.assertEqual(["REL-HOME-1"], entry["data_relation_ids"])
        self.assertEqual(["mmkv:home_seed"], entry["data_writes"])
        # surfaces 透传 feature-map 原始对象（薄表侧才抽 id 数组）
        self.assertEqual(
            [
                {"id": "PAGE-HOME", "kind": "page", "is_container": False},
                {"id": "SHEET-ADD", "kind": "sheet", "is_container": False},
            ],
            entry["surfaces"],
        )
        self.assertEqual("NOT_STARTED", entry["status"])
        self.assertEqual([], entry["harmony_steps"])

        # v4 surface-contracts 薄表骨架：per-feature 一行，实施结论列留空
        with (phase_dir / "surface-contracts.csv").open(encoding="utf-8", newline="") as stream:
            surface_rows = list(csv.DictReader(stream))
        self.assertEqual(1, len(surface_rows))
        self.assertEqual(FEATURE_ID, surface_rows[0]["feature_id"])
        self.assertEqual(
            '["PAGE-HOME","SHEET-ADD"]', surface_rows[0]["surfaces"]
        )
        for column in ("entry_reachable", "nav_pattern", "native_impl_check", "notes"):
            self.assertEqual("", surface_rows[0][column])

        # v4 实施账本：per-feature NOT_STARTED 行 + verify_mode 摘要
        with (phase_dir / "implementation-ledger.csv").open(encoding="utf-8", newline="") as stream:
            ledger_rows = list(csv.DictReader(stream))
        self.assertEqual(1, len(ledger_rows))
        self.assertEqual(FEATURE_ID, ledger_rows[0]["feature_id"])
        self.assertEqual("NOT_STARTED", ledger_rows[0]["status"])
        self.assertIn("verify_mode=RUNTIME", ledger_rows[0]["notes"])

        # schema 2.0 输入锁：v4 冻结件三绑定 + 16 类产物输入 + H4ENV
        lock = json.loads(
            (phase_dir / "stage-04-input-lock.json").read_text(encoding="utf-8")
        )
        self.assertEqual("2.0", lock["schema_version"])
        self.assertEqual("WO-P4-V4", lock["work_order_id"])
        self.assertEqual(
            json.loads((work_order_path).read_text(encoding="utf-8"))["feature_manifest"],
            lock["feature_manifest"],
        )
        self.assertEqual("feature-dispatch.json", lock["feature_dispatch"]["relative_path"])
        self.assertEqual(
            _sha256(phase_dir / "feature-dispatch.json"), lock["feature_dispatch"]["sha256"]
        )
        self.assertEqual("surface-contracts.csv", lock["surface_contracts"]["relative_path"])
        self.assertEqual(
            list(init_impl.SURFACE_CONTRACT_FIELDS), lock["surface_contracts"]["fields"]
        )
        self.assertEqual([H4ENV_ID], lock["required_h4env_ids"])
        self.assertEqual(1, len(lock["h4envs"]))
        locked_labels = {record["label"] for record in lock["inputs"]}
        self.assertEqual(
            {key.removesuffix("_sha256") for key in init_impl.STAGE4_INPUT_RELATIVES},
            {label for label in locked_labels if label.startswith("phase2_") or label.startswith("phase3_")},
        )

        # H4ENV 落盘 + phase-manifest 绑定 v4 冻结件哈希
        h4env_file = phase_dir / "environments" / H4ENV_ID / "phase4-environment.json"
        self.assertTrue(h4env_file.is_file())
        manifest = json.loads((phase_dir / "phase-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("IN_PROGRESS", manifest["status"])
        self.assertEqual(_sha256(phase_dir / "feature-dispatch.json"), manifest["feature_dispatch_sha256"])
        self.assertEqual(_sha256(phase_dir / "surface-contracts.csv"), manifest["surface_contracts_sha256"])

        # 旧页面范式产物不得再出现（v4 删旧不留双路径）
        for retired in (
            "page-contract-registry.csv", "page-contracts", "parity-map.csv",
            "visual-elements.csv", "page-implementation-ledger.csv",
            "migration-unit-contracts", "arkts-page-plans",
            "ui-test-snapshot-generation-manifest.json",
        ):
            self.assertFalse((phase_dir / retired).exists(), f"retired artifact reappeared: {retired}")

    def test_v4_single_path_retires_native_and_exempt_machinery(self) -> None:
        source_path = SCRIPTS / "init_implementation.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))

        # 1. 旧机制标识符整体退役（赋值/函数/引用任何形式）
        assigned = {
            node.targets[0].id
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        }
        functions = {
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        referenced = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        retired_names = {
            "gmi_exempt_input_keys", "gmi_native_layout",
            "compile_native_behavior_contracts", "compile_page_contracts",
            "publish_page_contracts", "prepare_uitest_probe",
            "validate_asset_chain", "validate_android_evidence",
            "validate_conversion_contracts", "gmi_phase2_gate_equivalent",
        }
        self.assertEqual(set(), assigned & retired_names)
        self.assertEqual(set(), functions & retired_names)
        self.assertEqual(set(), referenced & retired_names)

        # 2. 旧页面范式产物字符串不再写出
        source = source_path.read_text(encoding="utf-8")
        for retired_artifact in (
            '"page-contract-registry.csv"', '"page-contracts"', '"parity-map.csv"',
            '"visual-elements.csv"', '"page-implementation-ledger.csv"',
        ):
            self.assertNotIn(retired_artifact, source)

        # 3. v4 锚点在场：16 键输入面 + BC 七段子集（10 必需列）+
        #    semantic_input 为 v4 可选列（跨版本兼容：v3 冻结产物表头可缺）
        self.assertEqual(16, len(init_impl.STAGE4_INPUT_RELATIVES))
        self.assertNotIn(
            "semantic_input",
            init_impl.BC_SEMANTIC_COLUMNS,
        )
        self.assertEqual(10, len(init_impl.BC_SEMANTIC_COLUMNS))
        self.assertEqual(("semantic_input",), init_impl.BC_OPTIONAL_V4_COLUMNS)

        # 4. main() 内防御性重算 feature_manifest（工单冻结值双侧一致的
        #    单一真相源），且以 fail-closed 比对（!= 即 raise ValueError）
        main_fn = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        main_names = {node.id for node in ast.walk(main_fn) if isinstance(node, ast.Name)}
        self.assertIn("build_feature_manifest", main_names)
        self.assertIn("feature_manifest", main_names)

    def test_stage4_input_relatives_identical_in_init_and_controller_issue(self) -> None:
        """防漂移（v4 继任原 17e）：init_implementation.py 与 controller
        issue_phase4_work_order.py 的 STAGE4_INPUT_RELATIVES /
        BC_SEMANTIC_COLUMNS 必须字面量级完全一致，防止任何一侧单方改动
        输入面导致签发/初始化级联断裂。"""

        def extract_dict_literal(tree: ast.Module, name: str) -> dict[str, str]:
            match = next(
                (
                    node for node in ast.walk(tree)
                    if isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == name
                    and isinstance(node.value, ast.Dict)
                ),
                None,
            )
            self.assertIsNotNone(match, f"{name} not found")
            result: dict[str, str] = {}
            for key, value in zip(match.value.keys, match.value.values):
                self.assertIsInstance(key, ast.Constant)
                self.assertIsInstance(value, ast.Constant)
                result[key.value] = value.value
            return result

        def extract_tuple_literal(tree: ast.Module, name: str) -> tuple[str, ...]:
            match = next(
                (
                    node for node in ast.walk(tree)
                    if isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == name
                    and isinstance(node.value, (ast.Tuple, ast.List))
                ),
                None,
            )
            self.assertIsNotNone(match, f"{name} not found")
            return tuple(
                item.value for item in match.value.elts if isinstance(item, ast.Constant)
            )

        init_tree = ast.parse(
            (SCRIPTS / "init_implementation.py").read_text(encoding="utf-8"),
            "init_implementation.py",
        )
        issue_tree = ast.parse(
            CONTROLLER_ISSUE_PATH.read_text(encoding="utf-8"),
            "issue_phase4_work_order.py",
        )
        init_relatives = extract_dict_literal(init_tree, "STAGE4_INPUT_RELATIVES")
        issue_relatives = extract_dict_literal(issue_tree, "STAGE4_INPUT_RELATIVES")
        self.assertEqual(
            init_relatives, issue_relatives,
            "STAGE4_INPUT_RELATIVES drifted between init_implementation.py and "
            "issue_phase4_work_order.py",
        )
        init_columns = extract_tuple_literal(init_tree, "BC_SEMANTIC_COLUMNS")
        issue_columns = extract_tuple_literal(issue_tree, "BC_SEMANTIC_COLUMNS")
        self.assertEqual(init_columns, issue_columns)
        # semantic_input 为两树同步的 v4 可选列（不在必需子集；缺列兼容 v3 冻结产物）
        init_optional = extract_tuple_literal(init_tree, "BC_OPTIONAL_V4_COLUMNS")
        issue_optional = extract_tuple_literal(issue_tree, "BC_OPTIONAL_V4_COLUMNS")
        self.assertEqual(init_optional, issue_optional)
        self.assertIn("semantic_input", init_optional)


class MustReadManifestTest(unittest.TestCase):
    """批次 2 #85：feature_manifest 每项的 MUST_READ 段聚合口径。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mustread-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_must_read_segments_aggregated(self):
        p2 = self.root / "p2"
        _write_json(p2 / "feature-map.json", {
            "schema_version": 1,
            "coverage_gate": {"included_features_covered": True,
                              "included": [FEATURE_ID]},
            "features": [{
                "feature_id": FEATURE_ID,
                "name": "home",
                "source_refs": ["feature/home/HomeScreen.kt"],
                "surfaces": [{"id": "PAGE-HOME", "kind": "page",
                              "is_container": False}],
                "data_objects": {"writes": ["mmkv:home_seed"], "reads": []},
                "risk_level": "high", "verify_mode": "RUNTIME",
                "status": "OPEN",
            }],
        })
        _write_csv(
            p2 / "behavior-contracts.csv", BC_V4_HEADER,
            [[
                "BC-HOME-LOAD", FEATURE_ID, "PAGE-HOME", "intent",
                "pre", "op", "change", "", "obs", "mmkv:k", "none",
                "RUNTIME_REQUIRED", "high",
                "feature/home/HomeScreen.kt;feature/home/SortMenu.kt:15",
                "[]", "[]", "语义输入",
            ]],
        )
        _write_csv(p2 / "data-relations.csv",
                   ["relation_id", "feature_id", "data_object", "relation"],
                   [["REL-HOME-1", FEATURE_ID, "mmkv:home_seed", "write"],
                    ["REL-SHARED", "", "app:lang", "read"]])
        _write_csv(p2 / "reconciliation.csv",
                   ["bc_id", "feature_id", "verdict"],
                   [["BC-HOME-LOAD", FEATURE_ID, "CONFIRMED"]])
        _write_csv(p2 / "runtime-chains.csv",
                   ["bc_id", "feature_id", "chain_status", "evidence_dir"],
                   [["BC-HOME-LOAD", FEATURE_ID, "PASS",
                     "evidence/chains/BC-HOME-LOAD"]])
        _write_csv(p2 / "surface-registry.csv",
                   ["surface_shell_id", "page_id", "feature_ids", "status"],
                   [["ShellPageHome", "PAGE-HOME", FEATURE_ID, "READY"]])

        manifest, shared = init_impl.build_feature_manifest(
            p2 / "feature-map.json",
            p2 / "behavior-contracts.csv",
            p2 / "data-relations.csv",
            p2 / "reconciliation.csv",
            p2 / "runtime-chains.csv",
            [FEATURE_ID],
            p2 / "surface-registry.csv",
        )
        self.assertEqual(shared, ["REL-SHARED"])
        must_read = manifest[0]["must_read"]
        # 六段齐备（批次 2 #85 契约）
        self.assertEqual(
            sorted(must_read),
            ["android_source_refs", "behavior_contract_ids",
             "data_relations", "p3_surface_plan",
             "runtime_evidence_refs", "visual_memory_surface"])
        self.assertEqual(must_read["behavior_contract_ids"],
                         ["BC-HOME-LOAD"])
        self.assertEqual(must_read["android_source_refs"],
                         ["feature/home/HomeScreen.kt",
                          "feature/home/SortMenu.kt:15"])
        self.assertEqual(
            must_read["runtime_evidence_refs"],
            ["phase-02-android-inventory/runtime-evidence/"
             "evidence/chains/BC-HOME-LOAD"])
        self.assertEqual(must_read["data_relations"],
                         ["REL-HOME-1", "REL-SHARED"])  # 含共享对象
        self.assertEqual(must_read["visual_memory_surface"],
                         ["PAGE-HOME"])
        self.assertEqual(must_read["p3_surface_plan"], ["ShellPageHome"])


if __name__ == "__main__":
    unittest.main()
