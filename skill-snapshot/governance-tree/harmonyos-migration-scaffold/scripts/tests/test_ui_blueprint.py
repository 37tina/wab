#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 蓝图层（收敛式重构批次 3 #86）单测。

覆盖：
1. map_native_component 纯函数映射规则表：三 Tab 主页 / 普通页 / sheet /
   dialog / menu / container / reusable-component 各形态；
2. attach_ui_blueprint：surface-plan 三段六字段挂载、preserve 非空、
   custom_allowed 默认 no + 自绘类 yes 通道、visual-memory 缺失退化；
3. data_contracts.derive_required_operations：静态基表 / mmkv KV 缺省 /
   directions 退化 / BC 佐证并集 / 规范序；
4. HOME-FULL-RUN1 真实产物冒烟（存在时运行，否则 skip）：17 surface 全部
   有 native_component + preserve 非空；7 个语义对象全部有非空操作集。
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


COMPONENT_TABS = "Navigation+NavPathStack+Tabs(barPosition=End)+List+LazyForEach"
COMPONENT_PLAIN = "Navigation+NavPathStack+List/Scroll"
COMPONENT_SHEET = "bindSheet(detents MEDIUM/LARGE)"
COMPONENT_DIALOG = "CustomDialog/bindMenu"
COMPONENT_MENU = "bindMenu"
COMPONENT_NONE = "none (透传)"

THREE_TAB_DESCS = ["展开", "排序", "添加新待办事项", "待办事项", "日历视图", "进展"]


class MapNativeComponentTest(unittest.TestCase):
    """映射规则表（kind × 特征 → native_component）纯函数断言。"""

    def test_page_with_three_tab_descs_maps_to_bottom_tabs(self) -> None:
        hints = {
            "class_histogram": {"ComposeView": 1, "TextView": 6},
            "content_descs": THREE_TAB_DESCS,
        }
        self.assertEqual(init_scaffold.map_native_component("page", hints), COMPONENT_TABS)

    def test_page_with_bottom_navigation_class_maps_to_tabs(self) -> None:
        hints = {"class_histogram": {"BottomNavigationView": 1}, "content_descs": ["无"]}
        self.assertEqual(init_scaffold.map_native_component("page", hints), COMPONENT_TABS)

    def test_page_with_two_tab_hits_stays_plain(self) -> None:
        # 命中 2 个 Tab 特征词 < TAB_HINT_MIN_HITS(3)，不触发底栏 Tabs。
        hints = {"class_histogram": {"TextView": 3}, "content_descs": ["待办事项", "日历视图"]}
        self.assertEqual(init_scaffold.map_native_component("page", hints), COMPONENT_PLAIN)

    def test_plain_page(self) -> None:
        hints = {"class_histogram": {"TextView": 8, "EditText": 2}, "content_descs": ["返回", "更多"]}
        self.assertEqual(init_scaffold.map_native_component("page", hints), COMPONENT_PLAIN)

    def test_sheet_dialog_menu(self) -> None:
        self.assertEqual(init_scaffold.map_native_component("sheet", {}), COMPONENT_SHEET)
        self.assertEqual(init_scaffold.map_native_component("dialog", {}), COMPONENT_DIALOG)
        self.assertEqual(init_scaffold.map_native_component("menu", {}), COMPONENT_MENU)

    def test_passthrough_kinds(self) -> None:
        self.assertEqual(init_scaffold.map_native_component("container", {}), COMPONENT_NONE)
        self.assertEqual(
            init_scaffold.map_native_component("reusable-component", {}), COMPONENT_NONE
        )

    def test_none_hints_degrade_to_plain_page(self) -> None:
        self.assertEqual(init_scaffold.map_native_component("page", None), COMPONENT_PLAIN)
        self.assertEqual(init_scaffold.map_native_component("page", {}), COMPONENT_PLAIN)

    def test_class_histogram_takes_priority_over_descs(self) -> None:
        # 导航容器类优先命中（即使 descs 不含 Tab 词）。
        hints = {"class_histogram": {"TabLayout": 1}, "content_descs": ["无"]}
        self.assertEqual(init_scaffold.map_native_component("page", hints), COMPONENT_TABS)


def _mini_plan() -> dict:
    return init_scaffold.build_surface_plan(
        {
            "features": [
                {
                    "feature_id": "FEATURE-X",
                    "surfaces": [
                        {"id": "PAGE-HOME-ABCD1234", "kind": "page", "is_container": False},
                        {"id": "PAGE-EDITSHEET-CD33333", "kind": "sheet", "is_container": False},
                        {"id": "PAGE-ROW-CAFE9012", "kind": "reusable-component", "is_container": False},
                    ],
                }
            ],
            "included": ["FEATURE-X"],
        },
        [],
    )


def _mini_visual_memory() -> dict:
    return {
        "surfaces": [
            {
                "surface_id": "PAGE-HOME-ABCD1234",
                "kind": "page",
                "ui_tree_summary": {
                    "node_count": 51,
                    "depth_max": 15,
                    "class_histogram": {"View": 32, "TextView": 6, "ComposeView": 1},
                    "visible_texts": ["已完成", "全部", "未分组"],
                    "content_descs": THREE_TAB_DESCS,
                },
            },
            {
                "surface_id": "PAGE-EDITSHEET-CD33333",
                "kind": "sheet",
                "ui_tree_summary": {
                    "node_count": 19,
                    "depth_max": 9,
                    "class_histogram": {"TextView": 3, "Button": 2},
                    "visible_texts": ["自定义提醒"],
                    "content_descs": ["无"],
                },
            },
        ],
        "global_palette": {
            "background_colors": [
                {"name": "LightPalette.background", "hex": "#FFFFFF"},
                {"name": "LightPalette.pageBackground", "hex": "#F3F4F6"},
            ],
            "theme_colors": [{"name": "LightPalette.onPrimary", "hex": "#FFFFFF"}],
        },
    }


class AttachUiBlueprintTest(unittest.TestCase):
    BLUEPRINT_FIELDS = (
        "android_structure", "preserve", "native_carrier",
        "native_component", "custom_allowed", "reason", "matched_rule",
    )

    def test_all_three_sections_get_blueprint_fields(self) -> None:
        plan = _mini_plan()
        summary = init_scaffold.attach_ui_blueprint(plan, _mini_visual_memory())
        items = (
            plan["routes"] + plan["modals"] + plan["passthrough"]
        )
        self.assertEqual(len(items), 3)
        for item in items:
            for field in self.BLUEPRINT_FIELDS:
                self.assertIn(field, item, f"{item['surface_id']} missing {field}")
            self.assertTrue(item["native_component"])
            self.assertTrue(item["preserve"]["policy"] == "UI_FIDELITY=HIGH")
        home = plan["routes"][0]
        self.assertEqual(home["native_component"], COMPONENT_TABS)
        self.assertEqual(home["matched_rule"], init_scaffold.RULE_PAGE_TABS)
        self.assertIn("添加新待办事项", home["android_structure"])  # FAB 特征入描述
        self.assertIn("ComposeView 宿主", home["android_structure"])
        sheet = plan["modals"][0]
        self.assertEqual(sheet["native_component"], COMPONENT_SHEET)
        self.assertIn("bindSheet", sheet["native_carrier"])
        row = plan["passthrough"][0]
        self.assertEqual(row["native_component"], COMPONENT_NONE)
        self.assertEqual(row["custom_allowed"], "no")
        self.assertEqual(row["reason"], "")
        self.assertEqual(summary["stats"]["blueprinted_surface_count"], 3)
        self.assertEqual(summary["stats"]["visual_memory_covered_surface_count"], 2)
        self.assertEqual(plan["stats"]["ui_blueprint_surface_count"], 3)
        self.assertEqual(plan["ui_blueprint"]["policy"], "UI_FIDELITY=HIGH")

    def test_preserve_lists_texts_descs_palette(self) -> None:
        plan = _mini_plan()
        init_scaffold.attach_ui_blueprint(plan, _mini_visual_memory())
        home = plan["routes"][0]
        self.assertIn("已完成", home["preserve"]["texts"])
        self.assertIn("待办事项", home["preserve"]["content_descs"])
        palette_names = [p["name"] for p in home["preserve"]["palette"]]
        self.assertIn("LightPalette.pageBackground", palette_names)
        # "无" 是占位 desc，不进 preserve。
        sheet = plan["modals"][0]
        self.assertEqual(sheet["preserve"]["content_descs"], [])
        # 未覆盖 surface（row）preserve 退化但 note 非空。
        row = plan["passthrough"][0]
        self.assertTrue(row["preserve"]["note"])

    def test_custom_draw_class_allows_custom(self) -> None:
        plan = _mini_plan()
        vm = _mini_visual_memory()
        vm["surfaces"][0]["ui_tree_summary"]["class_histogram"]["SurfaceView"] = 1
        init_scaffold.attach_ui_blueprint(plan, vm)
        home = plan["routes"][0]
        self.assertEqual(home["custom_allowed"], "yes")
        self.assertIn("SurfaceView", home["reason"])

    def test_degrades_without_visual_memory(self) -> None:
        plan = _mini_plan()
        summary = init_scaffold.attach_ui_blueprint(plan, None)
        for item in plan["routes"] + plan["modals"] + plan["passthrough"]:
            self.assertIn("visual-memory", item["android_structure"])
            self.assertTrue(item["native_component"])  # 映射仍成立（kind 驱动）
            self.assertTrue(item["preserve"]["note"])  # 退化说明非空
        self.assertEqual(
            summary["stats"]["visual_memory_covered_surface_count"], 0
        )

    def test_tabs_owner_arbitration_between_pages(self) -> None:
        # 两个 page 共享同一快照证据（Phase 2 BC after 截图为主页状态）：
        # 底栏 Tabs 唯一持有者按主入口命名标记（HOME）仲裁给 PAGE-HOME，
        # 另一 page 降级普通页并在结构描述中登记仲裁。
        plan = init_scaffold.build_surface_plan(
            {
                "features": [
                    {
                        "feature_id": "FEATURE-X",
                        "surfaces": [
                            {"id": "PAGE-DETAIL-ABCD1111", "kind": "page", "is_container": False},
                            {"id": "PAGE-HOME-EFAB2222", "kind": "page", "is_container": False},
                        ],
                    }
                ],
                "included": ["FEATURE-X"],
            },
            [],
        )
        vm = {
            "surfaces": [
                {
                    "surface_id": sid,
                    "ui_tree_summary": {
                        "node_count": 51,
                        "class_histogram": {"TextView": 6},
                        "visible_texts": ["已完成"],
                        "content_descs": THREE_TAB_DESCS,
                    },
                }
                for sid in ("PAGE-DETAIL-ABCD1111", "PAGE-HOME-EFAB2222")
            ],
        }
        summary = init_scaffold.attach_ui_blueprint(plan, vm)
        by_id = {r["surface_id"]: r for r in plan["routes"]}
        self.assertEqual(by_id["PAGE-HOME-EFAB2222"]["native_component"], COMPONENT_TABS)
        self.assertEqual(by_id["PAGE-HOME-EFAB2222"]["matched_rule"], init_scaffold.RULE_PAGE_TABS)
        self.assertEqual(by_id["PAGE-DETAIL-ABCD1111"]["native_component"], COMPONENT_PLAIN)
        self.assertIn("PAGE-HOME-EFAB2222", by_id["PAGE-DETAIL-ABCD1111"]["android_structure"])
        arbitration = summary["tabs_owner_arbitration"]
        self.assertEqual(arbitration["tabs_owner_surface_id"], "PAGE-HOME-EFAB2222")
        self.assertEqual(
            arbitration["tab_feature_page_ids"],
            ["PAGE-DETAIL-ABCD1111", "PAGE-HOME-EFAB2222"],
        )

    def test_long_random_texts_filtered_from_preserve(self) -> None:
        plan = _mini_plan()
        vm = _mini_visual_memory()
        vm["surfaces"][1]["ui_tree_summary"]["visible_texts"] = [
            "x" * 100,  # 超长随机串（seed 数据噪声）不进 preserve
            "提醒时间",
        ]
        init_scaffold.attach_ui_blueprint(plan, vm)
        sheet = plan["modals"][0]
        self.assertEqual(sheet["preserve"]["texts"], ["提醒时间"])


class RequiredOperationsTest(unittest.TestCase):
    def _entry(self, raw_name: str, directions=("read", "write")) -> dict:
        return {
            "object_id": data_contracts.normalize_object_id(raw_name),
            "raw_name": raw_name,
            "repository_symbol": "XRepository",
            "directions": set(directions),
            "android_persistence": set(),
            "feature_ids": set(),
            "relation_ids": [],
            "source_refs": [],
        }

    def test_base_table_full_sets(self) -> None:
        cases = {
            "todo_items": ["create", "update", "setCompleted", "delete", "restore", "list"],
            # 输出按 OPERATIONS_CANONICAL_ORDER 规范序。
            "todo_groups": ["create", "update", "delete", "list", "rename", "reorder"],
            "settings": ["get", "set", "reset"],
            "repeat_rules": ["create", "update", "delete", "list", "get"],
            "sub_todo_items": ["create", "update", "delete", "list"],
        }
        for raw_name, expected in cases.items():
            result = data_contracts.derive_required_operations(self._entry(raw_name), None)
            self.assertEqual(result["operations"], expected, raw_name)
            self.assertEqual(result["evidence"]["base_rule"], "static-table")

    def test_mmkv_prefix_gets_kv_default(self) -> None:
        result = data_contracts.derive_required_operations(
            self._entry("mmkv:sort_option"), None
        )
        self.assertEqual(result["operations"], ["get", "set"])
        self.assertEqual(result["evidence"]["base_rule"], "mmkv-kv-default")

    def test_unknown_object_directions_fallback(self) -> None:
        result = data_contracts.derive_required_operations(
            self._entry("event_log"), None
        )
        self.assertEqual(result["operations"], ["list", "get", "set"])
        self.assertEqual(result["evidence"]["base_rule"], "directions-fallback")

    def test_bc_evidence_union_and_registration(self) -> None:
        bcs = [
            {
                "bc_id": "BC-DEL-01",
                "operation": "侧滑删除待办",
                "data_state_change": "todo_items.deletedAt 软删除",
                "persistence_targets": "todo_items",
                "source_refs": "TodoItem.kt:52",
            },
            {
                "bc_id": "BC-RESTORE-01",
                "operation": "撤销删除恢复待办",
                "data_state_change": "todo_items 恢复",
                "persistence_targets": "",
                "source_refs": "TodoItem.kt:60",
            },
            {
                "bc_id": "BC-OTHER-99",
                "operation": "与该对象无关的操作",
                "data_state_change": "别的东西",
                "persistence_targets": "other_object",
                "source_refs": "Other.kt:1",
            },
        ]
        result = data_contracts.derive_required_operations(self._entry("todo_items"), bcs)
        # 基表已含 delete/restore；BC 只登记佐证，不引入词表外操作。
        self.assertEqual(
            result["operations"],
            ["create", "update", "setCompleted", "delete", "restore", "list"],
        )
        self.assertEqual(result["evidence"]["bc_ids"], ["BC-DEL-01", "BC-RESTORE-01"])
        self.assertEqual(result["evidence"]["bc_derived_ops"], [])

    def test_bc_verb_adds_operation_missing_from_base(self) -> None:
        # settings 基表无 list；BC 文本含"查询"应并入 list（规范序输出）。
        bcs = [
            {
                "bc_id": "BC-SET-01",
                "operation": "打开设置查询当前排序",
                "data_state_change": "settings 读取 sort_option",
                "persistence_targets": "settings",
                "source_refs": "SettingsManager.kt:25",
            },
        ]
        result = data_contracts.derive_required_operations(self._entry("settings"), bcs)
        self.assertEqual(result["operations"], ["list", "get", "set", "reset"])
        self.assertEqual(result["evidence"]["bc_derived_ops"], ["list"])

    def test_attach_and_contract_document_output(self) -> None:
        objects, _ = data_contracts.semantic_objects([
            {"relation_id": "R1", "feature_id": "FEATURE-A", "data_object": "todo_items",
             "relation": "read", "persistence_kind": "room_table",
             "persistence_location": "todo_items", "source_ref": "a.kt:1"},
        ])
        attached = data_contracts.attach_required_operations(objects, None)
        self.assertEqual(attached["attached_object_count"], 1)
        doc = data_contracts.contract_document(
            objects["todo_items"], "2026-08-31T00:00:00Z", "ab" * 32
        )
        self.assertIn("required_operations", doc)
        self.assertIn("required_operations_evidence", doc)
        self.assertIn("setCompleted", doc["required_operations"])

    def test_load_and_build_with_bc_path_optional(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            relations = tmp / "data-relations.csv"
            relations.write_text(
                "relation_id,feature_id,data_object,relation,persistence_kind,"
                "persistence_location,source_ref\n"
                "R1,FEATURE-A,todo_items,read,room_table,todo_items,a.kt:1\n",
                encoding="utf-8",
            )
            objects, stats = data_contracts.load_and_build(relations)
            self.assertEqual(stats["required_operations_attached"], 1)
            bc = tmp / "behavior-contracts.csv"
            bc.write_text(
                "bc_id,feature_id,page_ref,user_intent,pre_state,operation,"
                "data_state_change,business_computation_refs,observable_result,"
                "persistence_targets,external_side_effects,evidence_class,impact,"
                "source_refs,operation_steps,result_assertions\n"
                "BC-DEL-01,FEATURE-A,P1,intent,pre,侧滑删除,软删除,,结果,"
                "todo_items,,RUNTIME_REQUIRED,high,a.kt:9,,\n",
                encoding="utf-8",
            )
            objects2, _ = data_contracts.load_and_build(relations, bc)
            self.assertEqual(
                objects2["todo_items"]["required_operations"]["evidence"]["bc_ids"],
                ["BC-DEL-01"],
            )


class RealRunIntegrationTest(unittest.TestCase):
    """HOME-FULL-RUN1 真实 Phase 2 产物冒烟（验证标准 2/3）。"""

    def _load_real(self):
        if not REAL_RUN.is_dir():
            self.skipTest(f"real run not present: {REAL_RUN}")
        phase2 = REAL_RUN / "phase-02-android-inventory"
        fm = init_scaffold.load_feature_map(phase2 / "feature-map.json")
        vm = json.loads(
            (phase2 / "visual-memory.json").read_text(encoding="utf-8")
        )
        return phase2, fm, vm

    def test_real_run_17_surfaces_blueprint_complete(self) -> None:
        import csv

        phase2, fm, vm = self._load_real()
        with (phase2 / "candidates" / "navigation-relations.candidates.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as handle:
            nav = list(csv.DictReader(handle))
        plan = init_scaffold.build_surface_plan(fm, nav)
        summary = init_scaffold.attach_ui_blueprint(plan, vm, {"available": True})
        items = plan["routes"] + plan["modals"] + plan["passthrough"]
        self.assertEqual(len(items), 17)
        for item in items:
            self.assertTrue(item["native_component"], item["surface_id"])
            self.assertIn(item["custom_allowed"], ("yes", "no"))
            preserve = item["preserve"]
            self.assertTrue(
                preserve["texts"] or preserve["content_descs"] or preserve["palette"]
                or preserve["note"],
                f"{item['surface_id']} preserve 全空",
            )
        # 主页 = 三 Tab 特征 → 底栏 Tabs 组合（仲裁唯一持有者）。
        home = next(r for r in plan["routes"] if "HOMESCREEN" in r["surface_id"])
        self.assertEqual(home["native_component"], COMPONENT_TABS)
        self.assertEqual(home["matched_rule"], init_scaffold.RULE_PAGE_TABS)
        # 详情页与主页共享同一 BC after 快照（Phase 2 证据限制）：Tab 特征
        # 词同样命中，但底栏 Tabs 唯一持有者按主入口标记仲裁给 HOMESCREEN，
        # DETAILSCREEN 降级普通页并登记仲裁。
        detail = next(r for r in plan["routes"] if "DETAILSCREEN" in r["surface_id"])
        self.assertEqual(detail["native_component"], COMPONENT_PLAIN)
        self.assertIn("HOMESCREEN", detail["android_structure"])
        arbitration = plan["ui_blueprint"]["tabs_owner_arbitration"]
        self.assertEqual(arbitration["tabs_owner_surface_id"], "PAGE-HOMESCREEN-D6AAF3AA")
        self.assertEqual(len(arbitration["tab_feature_page_ids"]), 2)
        # 5 sheet + 1 dialog 全部模态原生组合。
        for modal in plan["modals"]:
            expected = (
                COMPONENT_SHEET if modal["kind"] == "sheet" else COMPONENT_DIALOG
            )
            self.assertEqual(modal["native_component"], expected)
        self.assertEqual(summary["stats"]["blueprinted_surface_count"], 17)

    def test_real_run_data_contracts_all_have_operations(self) -> None:
        phase2, _, _ = self._load_real()
        objects, stats = data_contracts.load_and_build(
            phase2 / "data-relations.csv", phase2 / "behavior-contracts.csv"
        )
        self.assertEqual(len(objects), 7)  # 7 个语义对象契约（+index.json 共 8 文件）
        for object_id, entry in objects.items():
            ops = entry["required_operations"]["operations"]
            self.assertTrue(ops, f"{object_id} 操作集为空")
            self.assertIn(entry["required_operations"]["evidence"]["base_rule"],
                          ("static-table", "mmkv-kv-default", "directions-fallback"))
        todo = objects["todo_items"]["required_operations"]
        self.assertIn("setCompleted", todo["operations"])
        self.assertTrue(todo["evidence"]["bc_ids"])  # 有 BC 佐证
        self.assertEqual(stats["required_operations_attached"], 7)


if __name__ == "__main__":
    unittest.main()