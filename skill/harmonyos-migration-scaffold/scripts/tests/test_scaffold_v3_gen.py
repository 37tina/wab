#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""init_scaffold v3（feature-semantic 范式）生成器最小单测。

覆盖（D 的边界内；F 会补全端到端测试面）：
1. data_contracts：object_id/symbol 规范化、语义对象聚合（空对象跳过、
   读写方向、android 持久化参考去重）、interface-only 契约文档；
2. load_feature_map：schema 校验（重复面/未知 kind/is_container 一致性/
   coverage 一致性）；
3. build_surface_plan：page→route / sheet+dialog→modal@host / container
   与 reusable-component→none；宿主三层推断；nav 边仅保留两端精确命中；
4. render_modal_shell / surface_lock_entries 的确定性形状；
5. HOME-FULL-RUN1 真实 Phase 2 产物集成断言（存在时运行，否则 skip）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
REPO_ROOT = SCRIPTS.parents[3]
REAL_RUN = REPO_ROOT / "migration-runs" / "HOME-FULL-RUN1"

sys.path.insert(0, str(SCRIPTS))

import data_contracts  # noqa: E402
import init_scaffold  # noqa: E402


def _spec_load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def feature_map(features: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "features": features,
        "coverage_gate": {
            "included_features_covered": True,
            "included": [f["feature_id"] for f in features],
            "covered": [], "missing": [],
        },
    }


def nav_row(cid: str, fr: str, to: str) -> dict:
    return {
        "candidate_id": cid, "from_page_id": fr, "from_page_symbol": "Sym",
        "trigger": "tap", "action": "nav", "to_page_id": to,
        "relation_type": "INTENT", "source_ref": "src.kt:1",
    }


class DataContractsTest(unittest.TestCase):
    def test_normalize_and_symbol(self) -> None:
        self.assertEqual(data_contracts.normalize_object_id("mmkv:sort_option"), "mmkv_sort_option")
        self.assertEqual(data_contracts.normalize_object_id("Todo Items"), "todo_items")
        self.assertEqual(data_contracts.repository_symbol("mmkv_sort_option"), "MmkvSortOptionRepository")
        self.assertEqual(data_contracts.repository_symbol("todo_items"), "TodoItemsRepository")

    def test_semantic_objects_aggregation(self) -> None:
        rows = [
            {"relation_id": "R1", "feature_id": "FEATURE-A", "data_object": "todo_items",
             "relation": "read", "persistence_kind": "room_table",
             "persistence_location": "todo_items", "source_ref": "a.kt:1"},
            {"relation_id": "R2", "feature_id": "", "data_object": "todo_items",
             "relation": "write", "persistence_kind": "room_table",
             "persistence_location": "todo_items", "source_ref": "a.kt:2"},
            {"relation_id": "R3", "feature_id": "", "data_object": "",
             "relation": "write", "persistence_kind": "room_table",
             "persistence_location": "<Insert>", "source_ref": "b.kt:3"},
            {"relation_id": "R4", "feature_id": "FEATURE-B", "data_object": "settings",
             "relation": "invalid_dir", "persistence_kind": "mmkv_key",
             "persistence_location": "color_mode", "source_ref": "c.kt:4"},
        ]
        objects, stats = data_contracts.semantic_objects(rows)
        self.assertEqual(stats["row_count"], 4)
        self.assertEqual(stats["rows_skipped_empty_object"], 1)
        self.assertEqual(stats["invalid_relations"], 1)
        self.assertEqual(sorted(objects), ["todo_items"])
        entry = objects["todo_items"]
        self.assertEqual(entry["directions"], {"read", "write"})
        self.assertEqual(entry["android_persistence"], {("room_table", "todo_items")})
        self.assertEqual(entry["feature_ids"], {"FEATURE-A"})
        self.assertEqual(entry["relation_ids"], ["R1", "R2"])

    def test_contract_document_is_interface_only(self) -> None:
        objects, _ = data_contracts.semantic_objects([
            {"relation_id": "R1", "feature_id": "FEATURE-A", "data_object": "todo_items",
             "relation": "read", "persistence_kind": "room_table",
             "persistence_location": "todo_items", "source_ref": "a.kt:1"},
        ])
        doc = data_contracts.contract_document(
            objects["todo_items"], "2026-08-30T00:00:00Z", "ab" * 32
        )
        self.assertTrue(doc["interface_only"])
        self.assertEqual(doc["semantics"]["directions"], ["read"])
        self.assertEqual(doc["android_reference_persistence"],
                         [{"kind": "room_table", "location": "todo_items"}])
        self.assertEqual(doc["source"]["data_relations_sha256"], "ab" * 32)

    def test_capability_seed(self) -> None:
        objects, _ = data_contracts.semantic_objects([
            {"relation_id": "R1", "feature_id": "FEATURE-A", "data_object": "todo_groups",
             "relation": "write", "persistence_kind": "room_table",
             "persistence_location": "todo_groups", "source_ref": "a.kt:1"},
        ])
        seed = data_contracts.capability_seed(objects["todo_groups"], "data-contracts/todo_groups.json")
        self.assertEqual(seed["capability_id"], "CAP-DATA-TODOGROUPSREPOSITORY")
        self.assertTrue(seed["interface_only"])
        self.assertEqual(seed["directions"], ["write"])


class LoadFeatureMapTest(unittest.TestCase):
    def _write(self, tmp: Path, data: dict) -> Path:
        path = tmp / "feature-map.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_ok(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as name:
            path = self._write(Path(name), feature_map([
                {"feature_id": "FEATURE-A", "surfaces": [
                    {"id": "PAGE-HOME-ABCD1234", "kind": "page", "is_container": False},
                    {"id": "PAGE-SHEET-DEAD5678", "kind": "sheet", "is_container": False},
                ]},
            ]))
            loaded = init_scaffold.load_feature_map(path)
            self.assertEqual(loaded["feature_count"], 1)
            self.assertEqual(loaded["surface_count"], 2)

    def _reject(self, data: dict, needle: str) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as name:
            path = self._write(Path(name), data)
            with self.assertRaises(ValueError) as ctx:
                init_scaffold.load_feature_map(path)
            self.assertIn(needle, str(ctx.exception))

    def test_duplicate_surface_rejected(self) -> None:
        surface = {"id": "PAGE-HOME-ABCD1234", "kind": "page", "is_container": False}
        self._reject(feature_map([
            {"feature_id": "FEATURE-A", "surfaces": [surface]},
            {"feature_id": "FEATURE-B", "surfaces": [dict(surface)]},
        ]), "Duplicate feature-map Surface-ID")

    def test_unknown_kind_rejected(self) -> None:
        self._reject(feature_map([
            {"feature_id": "FEATURE-A", "surfaces": [
                {"id": "PAGE-X-ABCD1234", "kind": "hologram", "is_container": False},
            ]},
        ]), "unknown surface kind")

    def test_container_flag_mismatch_rejected(self) -> None:
        self._reject(feature_map([
            {"feature_id": "FEATURE-A", "surfaces": [
                {"id": "PAGE-X-ABCD1234", "kind": "page", "is_container": True},
            ]},
        ]), "is_container must agree")

    def test_coverage_mismatch_rejected(self) -> None:
        data = feature_map([
            {"feature_id": "FEATURE-A", "surfaces": [
                {"id": "PAGE-X-ABCD1234", "kind": "page", "is_container": False},
            ]},
        ])
        data["coverage_gate"]["included"] = ["FEATURE-OTHER"]
        self._reject(data, "coverage_gate.included differs")


class SurfacePlanTest(unittest.TestCase):
    def _plan(self, features: list[dict], nav: list[dict]):

        loaded = {
            "features": [
                {"feature_id": f["feature_id"], "surfaces": f["surfaces"]} for f in features
            ],
            "included": [f["feature_id"] for f in features],
            "feature_count": len(features),
            "surface_count": sum(len(f["surfaces"]) for f in features),
        }
        return init_scaffold.build_surface_plan(loaded, nav)

    def test_page_route_container_none(self) -> None:
        plan = self._plan([
            {"feature_id": "FEATURE-A", "surfaces": [
                {"id": "PAGE-HOME-ABCD1234", "kind": "page", "is_container": False},
                {"id": "PAGE-MAIN-BEEF5678", "kind": "container", "is_container": True},
                {"id": "PAGE-ROW-CAFE9012", "kind": "reusable-component", "is_container": False},
            ]},
        ], [])
        self.assertEqual([r["surface_id"] for r in plan["routes"]], ["PAGE-HOME-ABCD1234"])
        self.assertEqual(plan["modals"], [])
        self.assertEqual(
            sorted(p["surface_id"] for p in plan["passthrough"]),
            ["PAGE-MAIN-BEEF5678", "PAGE-ROW-CAFE9012"],
        )
        self.assertEqual(
            {p["kind"]: p["reason"] for p in plan["passthrough"]}["container"],
            "transparent-container-host",
        )

    def test_modal_host_inference_layers(self) -> None:
        surfaces = [
            {"id": "PAGE-DETAIL-ABCD1111", "kind": "page", "is_container": False},
            {"id": "PAGE-HOME-EFAB2222", "kind": "page", "is_container": False},
            {"id": "PAGE-EDITSHEET-CD33333", "kind": "sheet", "is_container": False},
        ]
        # 层1：nav 显式边（from 必须是 page surface）。
        plan = self._plan(
            [{"feature_id": "FEATURE-X", "surfaces": surfaces}],
            [nav_row("C1", "PAGE-HOME-EFAB2222", "PAGE-EDITSHEET-CD33333")],
        )
        self.assertEqual(plan["modals"][0]["host_surface_id"], "PAGE-HOME-EFAB2222")
        self.assertEqual(plan["modals"][0]["mount_host_source"], "nav-explicit-edge")
        self.assertEqual(len(plan["edges"]), 1)
        # 层2：同 feature 恰一 page（无 nav 边时）。
        plan = self._plan([
            {"feature_id": "FEATURE-X", "surfaces": [
                {"id": "PAGE-DETAIL-ABCD1111", "kind": "page", "is_container": False},
                {"id": "PAGE-EDITSHEET-CD33333", "kind": "sheet", "is_container": False},
            ]},
        ], [])
        self.assertEqual(plan["modals"][0]["mount_host_source"], "feature-page")
        # 层3：多 page 无边 → 排序后首个路由面兜底。
        plan = self._plan(
            [{"feature_id": "FEATURE-X", "surfaces": surfaces}], []
        )
        self.assertEqual(plan["modals"][0]["host_surface_id"], "PAGE-DETAIL-ABCD1111")
        self.assertEqual(plan["modals"][0]["mount_host_source"], "fallback-sorted-first-route")

    def test_nav_edges_require_exact_surface_hit(self) -> None:
        plan = self._plan([
            {"feature_id": "FEATURE-X", "surfaces": [
                {"id": "PAGE-HOME-ABCD1234", "kind": "page", "is_container": False},
                {"id": "PAGE-SHEET-DEAD5678", "kind": "sheet", "is_container": False},
            ]},
        ], [
            nav_row("C1", "PAGE-HOME-ABCD1234", "PAGE-SHEET-DEAD5678"),
            nav_row("C2", "PAGE-HOME-ABCD1234", "PAGE-GHOST-9999ZZZZ"),
        ])
        self.assertEqual(len(plan["edges"]), 1)
        self.assertEqual(plan["skipped_nav_pages"], ["PAGE-GHOST-9999ZZZZ"])
        self.assertEqual(plan["stats"]["nav_pages_skipped"], 1)

    def test_modal_shell_render_and_lock_entries(self) -> None:
        plan = self._plan([
            {"feature_id": "FEATURE-X", "surfaces": [
                {"id": "PAGE-DETAIL-ABCD1111", "kind": "page", "is_container": False},
                {"id": "PAGE-EDITSHEET-CD33333", "kind": "sheet", "is_container": False},
                {"id": "PAGE-MAIN-BEEF5678", "kind": "container", "is_container": True},
            ]},
        ], [])
        modal = plan["modals"][0]
        self.assertEqual(modal["shell_symbol"], "ShellModalEditsheetCd33333")
        text = init_scaffold.render_modal_shell(
            modal["surface_id"], modal["shell_symbol"], modal["kind"], modal["host_surface_id"]
        )
        self.assertIn("@Component", text)
        self.assertIn("export struct ShellModalEditsheetCd33333", text)
        self.assertIn(".id('PAGE-EDITSHEET-CD33333')", text)
        self.assertIn("// Mount-Host: PAGE-DETAIL-ABCD1111", text)
        self.assertNotIn("NavDestination", text)  # 模态载体不独立路由
        entries = init_scaffold.surface_lock_entries(plan)
        by_id = {e["id"]: e for e in entries}
        self.assertEqual(by_id["PAGE-DETAIL-ABCD1111"]["route_or_mount"], "route")
        self.assertEqual(
            by_id["PAGE-EDITSHEET-CD33333"]["route_or_mount"],
            "modal@PAGE-DETAIL-ABCD1111",
        )
        self.assertEqual(by_id["PAGE-MAIN-BEEF5678"]["route_or_mount"], "none")
        self.assertTrue(by_id["PAGE-MAIN-BEEF5678"]["is_container"])
        self.assertEqual(by_id["PAGE-EDITSHEET-CD33333"]["shell_file"],
                         "entry/src/main/ets/pages/modals/ShellModalEditsheetCd33333.ets")


class RealRunIntegrationTest(unittest.TestCase):
    """HOME-FULL-RUN1 真实 Phase 2 产物（v3 输入 schema 权威参照）。"""

    def test_real_run_surface_plan(self) -> None:
        if not REAL_RUN.is_dir():
            self.skipTest(f"real run not present: {REAL_RUN}")
        fm_path = REAL_RUN / "phase-02-android-inventory" / "feature-map.json"
        nav_path = (
            REAL_RUN / "phase-02-android-inventory" / "candidates"
            / "navigation-relations.candidates.csv"
        )
        fm = init_scaffold.load_feature_map(fm_path)
        self.assertEqual(fm["feature_count"], 12)
        self.assertEqual(fm["surface_count"], 17)
        with nav_path.open("r", encoding="utf-8-sig", newline="") as handle:
            import csv
            nav = list(csv.DictReader(handle))
        plan = init_scaffold.build_surface_plan(fm, nav)
        # 17 面 = page2 路由 + sheet5/dialog1 模态 + container2/reusable7 透传。
        self.assertEqual(plan["stats"],
                         {"surface_count": 17, "route_count": 2, "modal_count": 6,
                          "passthrough_count": 9, "nav_row_count": 11,
                          "nav_edge_kept": 0, "nav_pages_skipped": 9})
        # 真实 nav 表页面哈希与 feature-map 不同轮次 → 精确交集为 0，
# 宿主全部走层2/层3 推断且来源透明记录。
        sources = {m["surface_id"]: m["mount_host_source"] for m in plan["modals"]}
        self.assertEqual(sources["PAGE-DETAILTIMEBOTTOMSHEET-BB5322B7"], "feature-page")
        self.assertEqual(len([s for s in sources.values() if s == "fallback-sorted-first-route"]), 5)
        entries = init_scaffold.surface_lock_entries(plan)
        self.assertEqual(len(entries), 17)
        self.assertEqual(sum(1 for e in entries if e["route_or_mount"] == "route"), 2)
        self.assertEqual(sum(1 for e in entries if e["route_or_mount"].startswith("modal@")), 6)
        self.assertEqual(sum(1 for e in entries if e["route_or_mount"] == "none"), 9)

    def test_real_run_data_contracts(self) -> None:
        if not REAL_RUN.is_dir():
            self.skipTest(f"real run not present: {REAL_RUN}")
        path = REAL_RUN / "phase-02-android-inventory" / "data-relations.csv"
        objects, stats = data_contracts.load_and_build(path)
        self.assertEqual(stats["row_count"], 156)
        self.assertEqual(stats["rows_skipped_empty_object"], 19)
        # 7 个语义对象；冒号对象规范化；settings 为纯读+写聚合。
        self.assertEqual(sorted(objects), [
            "mmkv_sort_option", "mmkv_sort_order", "repeat_rules",
            "settings", "sub_todo_items", "todo_groups", "todo_items",
        ])
        self.assertEqual(objects["mmkv_sort_option"]["repository_symbol"],
                         "MmkvSortOptionRepository")
        self.assertEqual(objects["settings"]["directions"], {"read", "write"})
        self.assertTrue(all(entry["directions"] for entry in objects.values()))


class SemanticProbeTest(unittest.TestCase):
    """批次 2 #85：DebugSemanticProbe 独立探针生成钩子。"""

    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory(prefix="probe-")
        self.root = Path(self.temp.name)
        ability = (self.root / "entry/src/main/ets/entryability")
        ability.mkdir(parents=True)
        (ability / "EntryAbility.ets").write_text(
            "import { UIAbility } from '@kit.AbilityKit';\n"
            "\n"
            "export default class EntryAbility extends UIAbility {\n"
            "  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {\n"
            "    console.log('onCreate');\n"
            "  }\n"
            "}\n",
            encoding="utf-8")
        self.objects = {
            "todo_items": {"object_id": "todo_items"},
            "sort_option": {"object_id": "sort_option"},
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_probe_files_generated_with_frozen_hash(self):
        result = data_contracts.write_semantic_probe(self.root, self.objects)
        probe = self.root / data_contracts.PROBE_RELATIVE_PATH
        registry = self.root / data_contracts.PROBE_REGISTRY_RELATIVE_PATH
        self.assertTrue(probe.is_file())
        self.assertTrue(registry.is_file())
        self.assertEqual(result["probe_sha256"],
                         data_contracts.sha256_file(probe))
        self.assertEqual(result["probe_keys"], ["sort_option", "todo_items"])
        probe_text = probe.read_text(encoding="utf-8")
        self.assertIn("SNAPSHOT", probe_text)
        self.assertIn(data_contracts.PROBE_HILOG_TAG, probe_text)
        self.assertIn(data_contracts.PROBE_SNAPSHOT_FILENAME, probe_text)

    def test_registry_carries_frozen_key_set(self):
        data_contracts.write_semantic_probe(self.root, self.objects)
        text = (self.root / data_contracts.PROBE_REGISTRY_RELATIVE_PATH
                ).read_text(encoding="utf-8")
        self.assertIn("'todo_items'", text)
        self.assertIn("'sort_option'", text)
        self.assertIn("registerProbe", text)
        self.assertIn("collectProbeSnapshot", text)

    def test_ability_wiring_idempotent(self):
        first = data_contracts.write_semantic_probe(self.root, self.objects)
        second = data_contracts.write_semantic_probe(self.root, self.objects)
        self.assertTrue(first["ability_wired"])
        self.assertFalse(second["ability_wired"])  # 幂等：不重复接线
        ability = (self.root / "entry/src/main/ets/entryability"
                   / "EntryAbility.ets").read_text(encoding="utf-8")
        self.assertEqual(ability.count("startSemanticProbe("), 1)
        self.assertIn("this.context.filesDir", ability)

    def test_probe_hash_stable_across_key_sets(self):
        # key 全集只进 registry；探针本体哈希与对象集无关（冻结口径稳定）
        data_contracts.write_semantic_probe(self.root, self.objects)
        hash_a = data_contracts.sha256_file(
            self.root / data_contracts.PROBE_RELATIVE_PATH)
        data_contracts.write_semantic_probe(
            self.root, {"extra_object": {"object_id": "extra_object"}})
        hash_b = data_contracts.sha256_file(
            self.root / data_contracts.PROBE_RELATIVE_PATH)
        self.assertEqual(hash_a, hash_b)


if __name__ == "__main__":
    unittest.main()