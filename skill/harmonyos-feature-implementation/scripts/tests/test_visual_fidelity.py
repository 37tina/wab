#!/usr/bin/env python3
"""visual-fidelity（Gate 4 第 6 条）单元测试。

覆盖：surface_contract.py 的结构对比三指标计算 / 色板辅线 /
visual-memory 防御性加载 / fidelity 子命令端到端；validate_stage4.py
的规则 6（条件激活、可见面判定、NO_BASELINE 容忍）。

修 4b：denominator = feature-map 中 kind ∈ page/sheet/dialog 的全部
用户可见 surface（不分 verify_mode）——RUNTIME-only 达标而
SOURCE_CONFIRM surface 缺结果行 → FAIL；全可见 surface 达标 → PASS。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import surface_contract as sc  # noqa: E402
import validate_stage4 as v4   # noqa: E402


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

GOOD_DUMP = json.dumps({
    "attributes": {"type": "Navigation"},
    "children": [
        {"attributes": {"type": "Tabs"},
         "children": [
             {"attributes": {"type": "TabContent"},
              "children": [{"attributes": {"type": "Text", "text": "首页"}}]},
             {"attributes": {"type": "TabContent"},
              "children": [{"attributes": {"type": "Text", "text": "已完成"}}]},
         ]},
        {"attributes": {"type": "List"},
         "children": [
             {"attributes": {"type": "ListItem"},
              "children": [{"attributes": {"type": "Text", "text": "买牛奶"}}]},
         ]},
        {"attributes": {"type": "Button", "text": "新建待办"},
         "children": []},
    ],
})

GAPPY_DUMP = json.dumps({
    "attributes": {"type": "Column"},
    "children": [
        {"attributes": {"type": "Text", "text": "买牛奶 提醒一次"}},  # 命中基准
        {"attributes": {"type": "Text", "text": "完全不同的内容"}},
        {"attributes": {"type": "Text", "text": "还有一个文本"}},
        {"attributes": {"type": "Text", "text": "再来一个文本"}},
        {"attributes": {"type": "Text", "text": "以及第五个文本"}},
    ],
})


def baseline(**overrides):
    base = {
        "visible_texts": ["首页", "已完成", "买牛奶", "新建待办"],
        "component_types": ["Navigation", "Tabs", "List", "Button"],
        "depth": 3,  # GOOD_DUMP 树最大深度（Navigation=0 → Text=3）
        "key_elements": ["@Tabs", {"type": "Button", "text": "新建待办"}, "@List"],
        "palette": ["#673AB7"],
    }
    base.update(overrides)
    return base


def memory_file(tmp: Path, surfaces=None) -> Path:
    path = tmp / "visual-memory.json"
    path.write_text(json.dumps({"surfaces": surfaces if surfaces is not None else [
        {"surface_id": "PAGE-HOME-X",
         "ui_tree": {
             "visible_texts": ["首页", "已完成", "买牛奶", "新建待办"],
             "component_types": ["Navigation", "Tabs", "List", "Button"],
             "depth": 4,
             "key_elements": ["@Tabs", "@List", {"text": "新建待办"}],
         },
         "palette": ["#673AB7"]},
    ]}, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# compute_visual_fidelity
# ---------------------------------------------------------------------------

class ComputeFidelityTest(unittest.TestCase):
    def test_pass_when_structure_matches(self) -> None:
        result = sc.compute_visual_fidelity(GOOD_DUMP, baseline())
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["text_overlap"], 1.0)
        self.assertEqual(result["depth_delta"], 0)
        self.assertEqual(result["key_elements_hit"], 3)
        self.assertFalse(result["missing_key_elements"])

    def test_visual_gap_when_text_overlap_below_threshold(self) -> None:
        # 基准 4 条文本，鸿蒙侧只命中 1 条 → 0.25 < 0.6
        result = sc.compute_visual_fidelity(GAPPY_DUMP, baseline())
        self.assertEqual(result["verdict"], "VISUAL_GAP")
        self.assertEqual(result["text_overlap"], 0.25)
        self.assertIn("text_overlap", result["notes"])

    def test_visual_gap_when_depth_delta_exceeds(self) -> None:
        result = sc.compute_visual_fidelity(
            GOOD_DUMP, baseline(depth=8))  # |3-8|=5 > 2
        self.assertEqual(result["verdict"], "VISUAL_GAP")
        self.assertEqual(result["depth_delta"], 5)
        self.assertIn("depth_delta", result["notes"])

    def test_visual_gap_when_key_element_missing(self) -> None:
        result = sc.compute_visual_fidelity(
            GOOD_DUMP, baseline(key_elements=["@Tabs", "@Swiper", "@Chart"]))
        self.assertEqual(result["verdict"], "VISUAL_GAP")
        self.assertEqual(result["key_elements_hit"], 1)
        self.assertEqual(result["key_elements_total"], 3)
        self.assertIn("@Swiper", result["missing_key_elements"])

    def test_key_element_text_declaration_matches_substring(self) -> None:
        result = sc.compute_visual_fidelity(
            GOOD_DUMP, baseline(key_elements=[{"text": "新建"}]))  # 子串命中
        self.assertEqual(result["verdict"], "PASS")

    def test_no_baseline_when_all_metrics_missing(self) -> None:
        result = sc.compute_visual_fidelity(GOOD_DUMP, baseline(
            visible_texts=[], component_types=[], depth=None, key_elements=[]))
        self.assertEqual(result["verdict"], "NO_BASELINE")

    def test_no_dump_when_snapshot_empty_or_bad(self) -> None:
        for raw in ("", "not-json{"):
            result = sc.compute_visual_fidelity(raw, baseline())
            self.assertEqual(result["verdict"], "NO_DUMP")

    def test_hue_distance_recorded_but_never_fails_verdict(self) -> None:
        # 色板完全互补（紫 vs 黄绿，hue 距离 ~180）→ 只记录，verdict 仍 PASS
        result = sc.compute_visual_fidelity(
            GOOD_DUMP, baseline(), impl_palette=["#C8E600"])
        self.assertEqual(result["verdict"], "PASS")
        self.assertIsNotNone(result["hue_distance"])
        self.assertGreater(result["hue_distance"], 100)
        self.assertIn("recorded only", result["notes"])

    def test_thresholds_overridable(self) -> None:
        # 只调 text_overlap 阈值：0.25 < 默认 0.6 → GAP；≥ 自定义 0.2 → PASS
        # （depth 对齐 1、key_elements 置空以隔离单维度）
        result = sc.compute_visual_fidelity(
            GAPPY_DUMP, baseline(depth=1, key_elements=[]),
            min_text_overlap=0.2)
        self.assertEqual(result["verdict"], "PASS")
        result_strict = sc.compute_visual_fidelity(
            GAPPY_DUMP, baseline(depth=1, key_elements=[]))
        self.assertEqual(result_strict["verdict"], "VISUAL_GAP")
        # depth 阈值同样可覆盖：|1-5|=4 > 默认 2，放宽到 4 → PASS
        result_depth = sc.compute_visual_fidelity(
            GAPPY_DUMP, baseline(depth=5, key_elements=[]),
            min_text_overlap=0.2, max_depth_delta=4)
        self.assertEqual(result_depth["verdict"], "PASS")


class DumpTreeTest(unittest.TestCase):
    def test_parse_dump_tree_counts_and_depth(self) -> None:
        tree = sc.parse_dump_tree(GOOD_DUMP)
        self.assertEqual(tree["max_depth"], 3)
        self.assertIn("Tabs", tree["types"])
        self.assertTrue(tree["has_nodes"])

    def test_bad_json_yields_empty_tree(self) -> None:
        tree = sc.parse_dump_tree("{broken")
        self.assertFalse(tree["has_nodes"])
        self.assertEqual(tree["max_depth"], 0)


class HueDistanceTest(unittest.TestCase):
    def test_hex_hue_values(self) -> None:
        self.assertAlmostEqual(sc._hex_hue("#FF0000"), 0.0)
        self.assertAlmostEqual(sc._hex_hue("#00FF00"), 120.0)
        self.assertAlmostEqual(sc._hex_hue("#0000FF"), 240.0)
        self.assertIsNone(sc._hex_hue("red"))
        self.assertIsNone(sc._hex_hue("#12345"))  # 长度非法

    def test_alpha_prefix_stripped(self) -> None:
        self.assertAlmostEqual(sc._hex_hue("#80FF0000"), 0.0)

    def test_circular_distance(self) -> None:
        # hue 12° vs 348°（红两侧）→ 环形距离 24，不是 336
        distance = sc._hue_distance(["#FF3300"], ["#FF0033"])
        self.assertIsNotNone(distance)
        self.assertLess(distance, 30)
        self.assertGreater(distance, 15)


# ---------------------------------------------------------------------------
# load_visual_memory（#75 接口防御性消费）
# ---------------------------------------------------------------------------

class LoadVisualMemoryTest(unittest.TestCase):
    def test_canonical_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = memory_file(Path(tmp))
            baselines = sc.load_visual_memory(path)
        self.assertIn("PAGE-HOME-X", baselines)
        entry = baselines["PAGE-HOME-X"]
        self.assertEqual(entry["depth"], 4)
        self.assertEqual(len(entry["key_elements"]), 3)
        self.assertEqual(entry["palette"], ["#673AB7"])

    def test_alias_fields_tolerated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "visual-memory.json"
            path.write_text(json.dumps({"surfaces": [{
                "id": "PAGE-ALT",
                "uiTree": {"texts": ["待办"], "types": ["Tabs"],
                           "max_depth": 5, "anchors": ["@Tabs"]},
                "colors": ["#112233"],
            }]}, ensure_ascii=False), encoding="utf-8")
            baselines = sc.load_visual_memory(path)
        entry = baselines["PAGE-ALT"]
        self.assertEqual(entry["visible_texts"], ["待办"])
        self.assertEqual(entry["depth"], 5)
        self.assertEqual(entry["key_elements"], ["@Tabs"])
        self.assertEqual(entry["palette"], ["#112233"])

    def test_flat_surface_without_tree_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "visual-memory.json"
            path.write_text(json.dumps({"surfaces": [{
                "surface_id": "PAGE-FLAT",
                "visible_texts": ["文本"],
                "depth": 2,
            }]}), encoding="utf-8")
            baselines = sc.load_visual_memory(path)
        self.assertEqual(baselines["PAGE-FLAT"]["visible_texts"], ["文本"])

    def test_bad_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "visual-memory.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                sc.load_visual_memory(path)


# ---------------------------------------------------------------------------
# fidelity 子命令端到端
# ---------------------------------------------------------------------------

class FidelityCliTest(unittest.TestCase):
    def test_end_to_end_generate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            feature_map = root / "feature-map.json"
            feature_map.write_text(json.dumps({
                "features": [{
                    "feature_id": "FEATURE-HOME-LIST",
                    "verify_mode": "RUNTIME",
                    "surfaces": [{"id": "PAGE-HOME-X", "kind": "page"}],
                }],
                "coverage_gate": {"included": ["FEATURE-HOME-LIST"]},
            }), encoding="utf-8")
            memory = memory_file(root)
            dumps = root / "dumps"
            dumps.mkdir()
            (dumps / "PAGE-HOME-X.json").write_text(GOOD_DUMP,
                                                    encoding="utf-8")
            out = root / "visual-fidelity.csv"
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "surface_contract.py"),
                 "fidelity", "--feature-map", str(feature_map),
                 "--visual-memory", str(memory),
                 "--dumps-dir", str(dumps), "--out", str(out)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            summary = json.loads(proc.stdout)
            self.assertEqual(summary["counts"]["PASS"], 1)
            rows = sc.read_csv(out)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["verdict"], "PASS")
            self.assertEqual(rows[0]["feature_id"], "FEATURE-HOME-LIST")

    def test_missing_dump_marks_no_dump(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            feature_map = root / "feature-map.json"
            feature_map.write_text(json.dumps({
                "features": [{"feature_id": "F1", "verify_mode": "RUNTIME",
                              "surfaces": [{"id": "PAGE-HOME-X",
                                            "kind": "page"}]}],
            }), encoding="utf-8")
            memory = memory_file(root)
            dumps = root / "dumps"
            dumps.mkdir()
            out = root / "visual-fidelity.csv"
            result = sc.generate_visual_fidelity(
                feature_map, memory, dumps, out)
            self.assertEqual(result["counts"]["NO_DUMP"], 1)


# ---------------------------------------------------------------------------
# validate_stage4 规则 6（条件激活）
# ---------------------------------------------------------------------------

def stage4_denominators():
    """最小 denominators fixture（features + verify_mode + surfaces）。"""
    return {
        "features": {
            "FEATURE-HOME-LIST": {
                "feature_id": "FEATURE-HOME-LIST",
                "verify_mode": "RUNTIME",
                "surfaces": [
                    {"id": "PAGE-HOME-X", "kind": "page"},
                    {"id": "CONT-HOST", "kind": "container"},
                ],
            },
            "FEATURE-STATIC": {
                "feature_id": "FEATURE-STATIC",
                "verify_mode": "SOURCE_CONFIRM",
                "surfaces": [{"id": "PAGE-STATIC", "kind": "page"}],
            },
        },
    }


class Rule6DormantTest(unittest.TestCase):
    def test_dormant_without_phase2_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase-02-android-inventory").mkdir()
            rule = v4.evaluate_visual_fidelity(
                root / "ws", root, stage4_denominators(), [])
        self.assertEqual(rule["status"], "PASS")
        self.assertFalse(rule["activated"])


class Rule6ActiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.phase2 = self.root / "phase-02-android-inventory"
        self.phase2.mkdir()
        (self.phase2 / "visual-memory.json").write_text("{}", encoding="utf-8")
        self.ws = self.root / "ws"
        self.ws.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_fidelity(self, rows):
        sc.write_csv(self.ws / "visual-fidelity.csv",
                     sc.VISUAL_FIDELITY_FIELDS, rows)

    @staticmethod
    def pass_row(surface_id: str, feature_id: str, verdict: str = "PASS") -> dict:
        """一条最小合规 visual-fidelity 行（修 4b 测试用）。"""
        return {
            "surface_id": surface_id, "feature_id": feature_id,
            "text_overlap": "1.0", "depth_delta": "0",
            "key_elements_hit": "3", "key_elements_total": "3",
            "missing_key_elements": "", "hue_distance": "10",
            "verdict": verdict, "notes": "",
        }

    def test_pass_when_all_visible_surfaces_pass(self) -> None:
        # 修 4b：分母 = 全部用户可见 surface（不分 verify_mode）
        self.write_fidelity([
            self.pass_row("PAGE-HOME-X", "FEATURE-HOME-LIST"),
            self.pass_row("PAGE-STATIC", "FEATURE-STATIC"),
        ])
        errors: list = []
        rule = v4.evaluate_visual_fidelity(
            self.ws, self.root, stage4_denominators(), errors)
        self.assertEqual(rule["status"], "PASS")
        self.assertTrue(rule["activated"])
        self.assertEqual(rule["visible_surfaces"], 2)  # container 透明不计
        self.assertEqual(rule["host_surfaces"], 2)     # 兼容别名同值
        self.assertFalse(errors)

    def test_fail_on_visual_gap(self) -> None:
        self.write_fidelity([
            {
                "surface_id": "PAGE-HOME-X", "feature_id": "FEATURE-HOME-LIST",
                "text_overlap": "0.25", "depth_delta": "5",
                "key_elements_hit": "0", "key_elements_total": "3",
                "missing_key_elements": "@Tabs;@List",
                "hue_distance": "n/a", "verdict": "VISUAL_GAP",
                "notes": "text_overlap 0.25 < 0.60",
            },
            self.pass_row("PAGE-STATIC", "FEATURE-STATIC"),
        ])
        errors: list = []
        rule = v4.evaluate_visual_fidelity(
            self.ws, self.root, stage4_denominators(), errors)
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("VISUAL_GAP" in e for e in errors))

    def test_fail_on_no_dump(self) -> None:
        self.write_fidelity([
            {
                "surface_id": "PAGE-HOME-X", "feature_id": "FEATURE-HOME-LIST",
                "text_overlap": "n/a", "depth_delta": "n/a",
                "key_elements_hit": "0", "key_elements_total": "3",
                "missing_key_elements": "", "hue_distance": "n/a",
                "verdict": "NO_DUMP", "notes": "dump missing",
            },
            self.pass_row("PAGE-STATIC", "FEATURE-STATIC"),
        ])
        errors: list = []
        rule = v4.evaluate_visual_fidelity(
            self.ws, self.root, stage4_denominators(), errors)
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("NO_DUMP" in e for e in errors))

    def test_no_baseline_tolerated_phase2_responsibility(self) -> None:
        self.write_fidelity([
            {
                "surface_id": "PAGE-HOME-X", "feature_id": "FEATURE-HOME-LIST",
                "text_overlap": "n/a", "depth_delta": "n/a",
                "key_elements_hit": "0", "key_elements_total": "0",
                "missing_key_elements": "", "hue_distance": "n/a",
                "verdict": "NO_BASELINE", "notes": "baseline ui-tree empty",
            },
            self.pass_row("PAGE-STATIC", "FEATURE-STATIC"),
        ])
        errors: list = []
        rule = v4.evaluate_visual_fidelity(
            self.ws, self.root, stage4_denominators(), errors)
        self.assertEqual(rule["status"], "PASS")  # 不惩罚实现侧
        self.assertEqual(rule["counts"]["NO_BASELINE"], 1)

    def test_fail_when_csv_missing_with_baseline_present(self) -> None:
        errors: list = []
        rule = v4.evaluate_visual_fidelity(
            self.ws, self.root, stage4_denominators(), errors)
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("visual-fidelity.csv is missing" in e
                            for e in errors))

    def test_fail_when_visible_row_missing(self) -> None:
        self.write_fidelity([{
            "surface_id": "PAGE-OTHER", "feature_id": "",
            "text_overlap": "1.0", "depth_delta": "0",
            "key_elements_hit": "0", "key_elements_total": "0",
            "missing_key_elements": "", "hue_distance": "n/a",
            "verdict": "PASS", "notes": "",
        }])
        errors: list = []
        rule = v4.evaluate_visual_fidelity(
            self.ws, self.root, stage4_denominators(), errors)
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("no visual-fidelity row" in e for e in errors))

    def test_unknown_verdict_rejected(self) -> None:
        self.write_fidelity([{
            "surface_id": "PAGE-HOME-X", "feature_id": "FEATURE-HOME-LIST",
            "text_overlap": "1.0", "depth_delta": "0",
            "key_elements_hit": "0", "key_elements_total": "0",
            "missing_key_elements": "", "hue_distance": "n/a",
            "verdict": "MAYBE", "notes": "",
        }])
        errors: list = []
        rule = v4.evaluate_visual_fidelity(
            self.ws, self.root, stage4_denominators(), errors)
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("unknown verdict" in e for e in errors))

    def test_source_confirm_surface_missing_row_fails(self) -> None:
        # 修 4b 反转：SOURCE_CONFIRM feature 的用户可见 surface 也必须有
        # visual-fidelity 结果行——RUNTIME-only 达标不再够过 Gate。
        self.write_fidelity([self.pass_row("PAGE-HOME-X",
                                           "FEATURE-HOME-LIST")])
        errors: list = []
        rule = v4.evaluate_visual_fidelity(
            self.ws, self.root, stage4_denominators(), errors)
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any(
            "PAGE-STATIC" in e and "no visual-fidelity row" in e
            for e in errors))

    def test_source_confirm_surface_visual_gap_fails(self) -> None:
        # SOURCE_CONFIRM surface 不达标（VISUAL_GAP）同样 FAIL
        self.write_fidelity([
            self.pass_row("PAGE-HOME-X", "FEATURE-HOME-LIST"),
            self.pass_row("PAGE-STATIC", "FEATURE-STATIC", "VISUAL_GAP"),
        ])
        errors: list = []
        rule = v4.evaluate_visual_fidelity(
            self.ws, self.root, stage4_denominators(), errors)
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("VISUAL_GAP" in e for e in errors))

    def test_denominator_covers_sheet_and_dialog_kinds(self) -> None:
        # kind ∈ page/sheet/dialog 全部计入分母（含 SOURCE_CONFIRM 侧）
        denominators = {
            "features": {
                "FEATURE-RUNTIME": {
                    "feature_id": "FEATURE-RUNTIME",
                    "verify_mode": "RUNTIME",
                    "surfaces": [
                        {"id": "PAGE-HOME-X", "kind": "page"},
                        {"id": "SHEET-ADD", "kind": "sheet"},
                        {"id": "DLG-CONFIRM", "kind": "dialog"},
                        {"id": "CONT-HOST", "kind": "container"},
                        {"id": "COMP-ROW", "kind": "reusable-component"},
                    ],
                },
            },
        }
        self.write_fidelity([
            self.pass_row("PAGE-HOME-X", "FEATURE-RUNTIME"),
            self.pass_row("SHEET-ADD", "FEATURE-RUNTIME"),
            self.pass_row("DLG-CONFIRM", "FEATURE-RUNTIME"),
        ])
        errors: list = []
        rule = v4.evaluate_visual_fidelity(
            self.ws, self.root, denominators, errors)
        self.assertEqual(rule["status"], "PASS")
        self.assertEqual(rule["visible_surfaces"], 3)  # page+sheet+dialog
        self.assertFalse(errors)

    def test_unknown_kind_counted_but_not_in_denominator(self) -> None:
        # 未知 kind（非白名单也非透明）：可观测不计分母、不 FAIL
        denominators = {
            "features": {
                "FEATURE-RUNTIME": {
                    "feature_id": "FEATURE-RUNTIME",
                    "verify_mode": "RUNTIME",
                    "surfaces": [
                        {"id": "PAGE-HOME-X", "kind": "page"},
                        {"id": "WIDGET-NEW", "kind": "widget"},
                    ],
                },
            },
        }
        self.write_fidelity([self.pass_row("PAGE-HOME-X",
                                           "FEATURE-RUNTIME")])
        errors: list = []
        rule = v4.evaluate_visual_fidelity(
            self.ws, self.root, denominators, errors)
        self.assertEqual(rule["status"], "PASS")
        self.assertEqual(rule["visible_surfaces"], 1)
        self.assertEqual(rule["uncounted_kinds"], {"widget": 1})
        self.assertFalse(errors)


if __name__ == "__main__":
    unittest.main()