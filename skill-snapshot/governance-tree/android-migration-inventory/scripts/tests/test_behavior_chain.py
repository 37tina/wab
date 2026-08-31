# -*- coding: utf-8 -*-
"""test_behavior_chain -- gmi_runtime v5.0 行为链模式（--mode chain）单测。

覆盖（任务 #39 改造B，只测纯函数——与现有采集器测试策略一致，adb 副作用
执行器不在单测范围）：
  - operation_steps / result_assertions 解析（JSON-in-CSV：正常/空/坏 JSON）；
  - 结果断言判定正反例（text_visible / text_gone / persist_after_restart /
    未知 kind）；
  - 链状态分类矩阵（blocked 优先于断言矛盾：NAV_FAIL/STEPS_FAIL/ANR_BLOCKED/
    CHAIN_FAIL/CHAIN_PASS；收敛式重构批次1 #81：无断言 → INVALID_CONTRACT、
    全部 unsupported → UNSUPPORTED_ORACLE，degraded CHAIN_PASS 路径已删除）；
  - precondition 机制纯函数（#83：pre_state token 提取 / verify_precondition
    记录校验 / prepare_steps 可选列接口）；
  - feature-map.json 解析（#38 改造A 权威 schema：features[].surfaces[].id）
    与 BC 选择（RUNTIME 选中 / SOURCE_CONFIRM 排除 / unmapped / 缺文件降级）；
  - 证据瘦身格式（CHAIN_CSV_FIELDS 无 side-effect 四件套列；evidence 按
    bc_id 组织）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import gmi_runtime  # noqa: E402  模块级无副作用（纯函数/常量）


def _xml(*texts: str) -> str:
    """最小 uiautomator 风格 XML（带 bounds 的文本节点，供 ui_nodes 解析）。"""
    nodes = "".join(
        f'<node text="{t}" content-desc="" bounds="[10,{i * 100}][400,{i * 100 + 80}]" '
        f'class="android.widget.TextView" clickable="false"/>' for i, t in enumerate(texts))
    return f"<?xml version='1.0'?><hierarchy>{nodes}</hierarchy>"


def _bc(**kw) -> dict:
    row = {"bc_id": "BC-9001", "feature_id": "FEATURE-X", "page_ref": "PAGE-X",
           "evidence_class": "RUNTIME_REQUIRED", "data_state_change": "",
           "persistence_targets": "", "external_side_effects": ""}
    row.update(kw)
    return row


class ParseJsonColTest(unittest.TestCase):
    """JSON-in-CSV 解析：正常 / 空 / 坏 JSON / 非数组。"""

    def test_ok(self) -> None:
        raw = '[{"action":"tap","target":"新建待办"}]'
        self.assertEqual(gmi_runtime.parse_json_col(raw),
                         [{"action": "tap", "target": "新建待办"}])

    def test_empty_variants(self) -> None:
        for raw in ("", "   ", None):
            self.assertEqual(gmi_runtime.parse_json_col(raw or ""), [])

    def test_broken_json(self) -> None:
        self.assertEqual(gmi_runtime.parse_json_col("[{broken"), [])
        self.assertTrue(gmi_runtime.json_col_broken("[{broken"))

    def test_non_list(self) -> None:
        self.assertEqual(gmi_runtime.parse_json_col('{"a":1}'), [])
        self.assertTrue(gmi_runtime.json_col_broken('{"a":1}'))

    def test_broken_detection_negative(self) -> None:
        self.assertFalse(gmi_runtime.json_col_broken(""))
        self.assertFalse(gmi_runtime.json_col_broken("[]"))
        self.assertFalse(gmi_runtime.json_col_broken('[{"action":"tap"}]'))

    def test_parse_steps_and_assertions(self) -> None:
        bc = _bc(operation_steps='[{"action":"tap","target":"新建待办"},'
                                 '{"action":"input","target":"标题","value":"TEST-X"},'
                                 '{"action":"tap","target":"完成"}]',
                 result_assertions='[{"kind":"text_visible","value":"TEST-X"},'
                                   '{"kind":"persist_after_restart","value":"TEST-X"}]')
        steps = gmi_runtime.parse_chain_steps(bc)
        self.assertEqual([s["action"] for s in steps], ["tap", "input", "tap"])
        self.assertEqual(steps[1]["value"], "TEST-X")
        kinds = [a["kind"] for a in gmi_runtime.parse_chain_assertions(bc)]
        self.assertEqual(kinds, ["text_visible", "persist_after_restart"])

    def test_missing_columns_degrade(self) -> None:
        """无 operation_steps/result_assertions 列（A 明确不生成）-> 降级空。"""
        bc = _bc()
        self.assertEqual(gmi_runtime.parse_chain_steps(bc), [])
        self.assertEqual(gmi_runtime.parse_chain_assertions(bc), [])


class AssertionEvaluationTest(unittest.TestCase):
    """结果断言判定正反例（结果导向）。"""

    AFTER = _xml("全部", "买牛奶 TEST-X", "完成")
    RESTART = _xml("全部", "买牛奶 TEST-X")

    def test_text_visible_pass_and_fail(self) -> None:
        r = gmi_runtime.evaluate_chain_assertions(
            [{"kind": "text_visible", "value": "TEST-X"}], self.AFTER, "")
        self.assertEqual(r[0]["verdict"], "PASS")
        r = gmi_runtime.evaluate_chain_assertions(
            [{"kind": "text_visible", "value": "不存在的文本"}], self.AFTER, "")
        self.assertEqual(r[0]["verdict"], "FAIL")

    def test_text_visible_case_insensitive(self) -> None:
        r = gmi_runtime.evaluate_chain_assertions(
            [{"kind": "text_visible", "value": "test-x"}], self.AFTER, "")
        self.assertEqual(r[0]["verdict"], "PASS")

    def test_text_gone_pass_and_fail(self) -> None:
        r = gmi_runtime.evaluate_chain_assertions(
            [{"kind": "text_gone", "value": "新建待办"}], self.AFTER, "")
        self.assertEqual(r[0]["verdict"], "PASS")
        r = gmi_runtime.evaluate_chain_assertions(
            [{"kind": "text_gone", "value": "完成"}], self.AFTER, "")
        self.assertEqual(r[0]["verdict"], "FAIL")

    def test_persist_after_restart(self) -> None:
        ok = gmi_runtime.evaluate_chain_assertions(
            [{"kind": "persist_after_restart", "value": "TEST-X"}],
            self.AFTER, self.RESTART)
        self.assertEqual(ok[0]["verdict"], "PASS")
        gone = gmi_runtime.evaluate_chain_assertions(
            [{"kind": "persist_after_restart", "value": "TEST-X"}],
            self.AFTER, _xml("全部", "空列表"))
        self.assertEqual(gone[0]["verdict"], "FAIL")
        # restart_xml 缺失（重启失败/未做）= 未证实 -> FAIL（fail-closed）
        empty = gmi_runtime.evaluate_chain_assertions(
            [{"kind": "persist_after_restart", "value": "TEST-X"}], self.AFTER, "")
        self.assertEqual(empty[0]["verdict"], "FAIL")

    def test_unsupported_kind_not_fail(self) -> None:
        r = gmi_runtime.evaluate_chain_assertions(
            [{"kind": "db_query", "value": "x"}], self.AFTER, self.RESTART)
        self.assertEqual(r[0]["verdict"], "UNSUPPORTED")

    def test_empty_value_fails(self) -> None:
        r = gmi_runtime.evaluate_chain_assertions(
            [{"kind": "text_visible", "value": ""}], self.AFTER, "")
        self.assertEqual(r[0]["verdict"], "FAIL")


class ClassifyChainStatusTest(unittest.TestCase):
    """链状态分类矩阵（blocked 优先于断言矛盾）。"""

    PASS2 = [{"kind": "text_visible", "value": "X", "verdict": "PASS"},
             {"kind": "persist_after_restart", "value": "X", "verdict": "PASS"}]
    FAIL1 = [{"kind": "text_visible", "value": "X", "verdict": "FAIL"}]

    def test_nav_fail(self) -> None:
        status, _ = gmi_runtime.classify_chain_status(
            False, "anchors_tried=3", True, 0, 2, self.PASS2, True, False)
        self.assertEqual(status, "NAV_FAIL")

    def test_nav_anr_blocked(self) -> None:
        status, _ = gmi_runtime.classify_chain_status(
            False, "ANR_BLOCKED(collector-induced)", True, 0, 2, self.PASS2, True, False)
        self.assertEqual(status, "ANR_BLOCKED")

    def test_steps_fail_beats_assertions(self) -> None:
        """步骤中断优先于断言判定（采集受阻≠行为矛盾）。"""
        status, note = gmi_runtime.classify_chain_status(
            True, "", True, 1, 3, self.FAIL1, True, False)
        self.assertEqual(status, "STEPS_FAIL")
        self.assertIn("1/3", note)

    def test_restart_fail_beats_assertions(self) -> None:
        status, _ = gmi_runtime.classify_chain_status(
            True, "", True, 2, 2, self.FAIL1, False, True)
        self.assertEqual(status, "ANR_BLOCKED")

    def test_chain_fail(self) -> None:
        status, note = gmi_runtime.classify_chain_status(
            True, "", True, 2, 2, self.FAIL1, True, False)
        self.assertEqual(status, "CHAIN_FAIL")
        self.assertIn("text_visible=X", note)

    def test_chain_pass_full(self) -> None:
        status, note = gmi_runtime.classify_chain_status(
            True, "", True, 2, 2, self.PASS2, True, True)
        self.assertEqual((status, note), ("CHAIN_PASS", "ok"))

    def test_no_assertions_is_invalid_contract(self) -> None:
        """收敛式重构批次1（#81）：无断言 -> INVALID_CONTRACT，绝不 CHAIN_PASS。

        degraded:no_assertions 的 PASS 路径已彻底删除：RUNTIME 契约缺
        result_assertions 是契约不完整，不是可放行的降级。"""
        status, note = gmi_runtime.classify_chain_status(
            True, "", False, 0, 0, [], True, False)
        self.assertEqual(status, "INVALID_CONTRACT")
        self.assertIn("no result_assertions", note)
        self.assertNotIn("degraded", note)

    def test_all_unsupported_is_unsupported_oracle(self) -> None:
        """#81：全部断言 unsupported -> UNSUPPORTED_ORACLE，绝不 CHAIN_PASS。"""
        status, note = gmi_runtime.classify_chain_status(
            True, "", False, 0, 0,
            [{"kind": "db_query", "value": "x", "verdict": "UNSUPPORTED"}],
            True, False)
        self.assertEqual(status, "UNSUPPORTED_ORACLE")
        self.assertIn("unsupported", note)
        self.assertNotIn("degraded", note)

    def test_mixed_required_unsupported_is_unsupported_oracle(self) -> None:
        """#88 收紧：部分 unsupported（无 optional 标记）+ 部分 PASS ->
        UNSUPPORTED_ORACLE（归 GAP），绝不能以"部分验证"冒充成功。

        用户判定漏洞：文字变化验证了但持久化/副作用验证不了仍算成功，
        等于没验持久化却放行 CHAIN_PASS。required（默认）断言任一
        UNSUPPORTED -> 整链归 GAP。"""
        mixed = [{"kind": "text_visible", "value": "X", "verdict": "PASS"},
                 {"kind": "db_query", "value": "x", "verdict": "UNSUPPORTED"}]
        status, note = gmi_runtime.classify_chain_status(
            True, "", True, 2, 2, mixed, True, False)
        self.assertEqual(status, "UNSUPPORTED_ORACLE")
        self.assertIn("required assertions unsupported", note)
        self.assertIn("db_query", note)
        self.assertNotIn("degraded", note)

    def test_optional_unsupported_with_required_pass(self) -> None:
        """#88：显式 optional:true 的 UNSUPPORTED + required 全 PASS ->
        CHAIN_PASS + note 列出 skipped optional（optional 只豁免 UNSUPPORTED）。"""
        results = [{"kind": "text_visible", "value": "X", "verdict": "PASS",
                    "optional": "false"},
                   {"kind": "db_query", "value": "x", "verdict": "UNSUPPORTED",
                    "optional": "true"}]
        status, note = gmi_runtime.classify_chain_status(
            True, "", True, 2, 2, results, True, False)
        self.assertEqual(status, "CHAIN_PASS")
        self.assertIn("skipped optional", note)
        self.assertIn("db_query", note)

    def test_optional_fail_still_chain_fail(self) -> None:
        """#88：optional 断言 FAIL 不豁免 -> CHAIN_FAIL（optional 只豁免
        UNSUPPORTED，不豁免 FAIL——判 FAIL 是行为矛盾，与 optional 无关）。"""
        results = [{"kind": "text_visible", "value": "X", "verdict": "PASS"},
                   {"kind": "persist_after_restart", "value": "X",
                    "verdict": "FAIL", "optional": "true"}]
        status, note = gmi_runtime.classify_chain_status(
            True, "", True, 2, 2, results, True, False)
        self.assertEqual(status, "CHAIN_FAIL")
        self.assertIn("persist_after_restart=X", note)

    def test_optional_flag_passthrough_and_parsing(self) -> None:
        """#88：evaluate 透传 optional；解析接受 bool true / 字符串 true，
        其余（缺省/false/False/"no"）一律 required。"""
        r = gmi_runtime.evaluate_chain_assertions(
            [{"kind": "db_query", "value": "x", "optional": True},
             {"kind": "screenshot_diff", "value": "y", "optional": "true"},
             {"kind": "db_row_count", "value": "z"}], "<x/>", "<x/>")
        self.assertEqual([a["optional"] for a in r], ["true", "true", "false"])
        self.assertTrue(gmi_runtime.assertion_is_optional({"optional": True}))
        self.assertTrue(gmi_runtime.assertion_is_optional({"optional": "TRUE"}))
        self.assertFalse(gmi_runtime.assertion_is_optional({}))
        self.assertFalse(gmi_runtime.assertion_is_optional({"optional": False}))
        self.assertFalse(gmi_runtime.assertion_is_optional({"optional": "no"}))

    def test_all_assertions_unsupported_prescan(self) -> None:
        """执行前 fail-fast 预扫描：断言非空且全部 kind 未知。"""
        self.assertTrue(gmi_runtime.all_assertions_unsupported(
            [{"kind": "db_query", "value": "x"},
             {"kind": "screenshot_diff", "value": "y"}]))
        # 空 / 含支持 kind / kind 为空串 -> 不触发
        self.assertFalse(gmi_runtime.all_assertions_unsupported([]))
        self.assertFalse(gmi_runtime.all_assertions_unsupported(
            [{"kind": "text_visible", "value": "x"}]))
        self.assertFalse(gmi_runtime.all_assertions_unsupported(
            [{"kind": "text_visible", "value": "x"},
             {"kind": "db_query", "value": "y"}]))
        self.assertTrue(gmi_runtime.all_assertions_unsupported(
            [{"kind": "", "value": "x"}, {"kind": "db_query", "value": "y"}]))


class PreconditionTest(unittest.TestCase):
    """#83 precondition 机制纯函数：pre_state token 提取与记录校验。"""

    XML = _xml("设置", "语言", "中文", "English")

    def test_parse_tokens_from_equals_and_quotes(self) -> None:
        self.assertEqual(gmi_runtime.parse_pre_state_tokens("语言=中文"),
                         ["中文"])
        self.assertEqual(gmi_runtime.parse_pre_state_tokens("主题为『深色』模式"),
                         ["深色"])
        # 无分隔符/引号的整句不作为 token（避免整句逐字校验误伤链）
        self.assertEqual(gmi_runtime.parse_pre_state_tokens("当前处于设置页"), [])
        self.assertEqual(gmi_runtime.parse_pre_state_tokens(""), [])
        self.assertEqual(gmi_runtime.parse_pre_state_tokens(None or ""), [])

    def test_verify_precondition_ok(self) -> None:
        ok, note = gmi_runtime.verify_precondition("语言=中文", self.XML)
        self.assertTrue(ok)
        self.assertIn("verified", note)
        self.assertIn("中文", note)

    def test_verify_precondition_missing_token_fails(self) -> None:
        ok, note = gmi_runtime.verify_precondition("语言=日文", self.XML)
        self.assertFalse(ok)
        self.assertIn("missing on page", note)
        self.assertIn("日文", note)

    def test_verify_precondition_no_tokens_record_only(self) -> None:
        """无可校验 token -> 仅记录口径，不阻塞链（避免自然语言误伤）。"""
        ok, note = gmi_runtime.verify_precondition("冷启动后首次进入", self.XML)
        self.assertTrue(ok)
        self.assertIn("recorded", note)
        ok2, _ = gmi_runtime.verify_precondition("", self.XML)
        self.assertTrue(ok2)

    def test_prepare_steps_optional_column_interface(self) -> None:
        """prepare_steps 可选列接口：缺列/空 -> []；JSON 数组 -> 步骤序列。"""
        bc = _bc()
        self.assertEqual(gmi_runtime.parse_prepare_steps(bc), [])
        bc2 = _bc(prepare_steps='[{"action":"tap","target":"设置"}]')
        self.assertEqual(gmi_runtime.parse_prepare_steps(bc2),
                         [{"action": "tap", "target": "设置"}])

    def test_precondition_failed_in_blocked_status(self) -> None:
        """PRECONDITION_FAILED 属 blocked 集（reconcile 归 GAP，非 CONFLICT）。"""
        self.assertIn("PRECONDITION_FAILED", gmi_runtime.CHAIN_BLOCKED_STATUS)
        self.assertIn("INVALID_CONTRACT", gmi_runtime.CHAIN_BLOCKED_STATUS)
        self.assertIn("UNSUPPORTED_ORACLE", gmi_runtime.CHAIN_BLOCKED_STATUS)


class FeatureMapTest(unittest.TestCase):
    """feature-map.json 解析（#38 改造A 权威 schema）。"""

    def test_authoritative_schema(self) -> None:
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "feature-map.json").write_text(json.dumps({
                "features": [
                    {"feature_id": "FEATURE-TODO-CREATE", "verify_mode": "RUNTIME",
                     "surfaces": [{"id": "PAGE-HOME-1", "kind": "page",
                                   "is_container": False}]},
                    {"feature_id": "FEATURE-NAV-SHELL", "verify_mode": "SOURCE_CONFIRM",
                     "surfaces": [{"id": "PAGE-MAIN-1", "kind": "container",
                                   "is_container": True}]},
                ]}, ensure_ascii=False), encoding="utf-8")
            fm = gmi_runtime.load_feature_map(ws)
            self.assertFalse(fm["missing"])
            self.assertEqual(fm["runtime_features"], {"FEATURE-TODO-CREATE"})
            self.assertEqual(fm["source_confirm_features"], {"FEATURE-NAV-SHELL"})
            self.assertEqual(fm["pages_by_feature"]["FEATURE-TODO-CREATE"],
                             {"PAGE-HOME-1"})

    def test_missing_file(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            fm = gmi_runtime.load_feature_map(Path(td))
            self.assertTrue(fm["missing"])
            self.assertEqual(fm["runtime_features"], set())

    def test_tolerant_shapes(self) -> None:
        """容错形态：字符串 surfaces / 顶层 list。"""
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "feature-map.json").write_text(json.dumps({
                "features": [
                    {"feature_id": "F1", "verify_mode": "RUNTIME",
                     "surfaces": ["PAGE-A", "PAGE-B"]},
                    {"feature_id": "F2", "verify_mode": "SOURCE_CONFIRM",
                     "surfaces": []},
                ]}), encoding="utf-8")
            fm = gmi_runtime.load_feature_map(ws)
            self.assertEqual(fm["pages_by_feature"]["F1"], {"PAGE-A", "PAGE-B"})
            self.assertEqual(fm["source_confirm_features"], {"F2"})


class SelectChainBcsTest(unittest.TestCase):
    """BC 选择：RUNTIME 选中 / SOURCE_CONFIRM 排除 / unmapped / 缺文件降级。"""

    FMAP = {"runtime_features": {"FEATURE-A", "FEATURE-B"},
            "source_confirm_features": {"FEATURE-NAV"},
            "pages_by_feature": {}, "missing": False}

    def test_select_and_exclude(self) -> None:
        rows = [_bc(bc_id="BC-1", feature_id="FEATURE-A"),
                _bc(bc_id="BC-2", feature_id="FEATURE-NAV"),
                _bc(bc_id="BC-3", feature_id="FEATURE-B")]
        sel = gmi_runtime.select_chain_bcs(rows, self.FMAP)
        self.assertEqual([r["bc_id"] for r in sel["selected"]], ["BC-1", "BC-3"])
        self.assertEqual(len(sel["excluded"]), 1)
        self.assertIn("SOURCE_CONFIRM", sel["excluded"][0]["reason"])
        self.assertEqual(sel["unmapped"], [])

    def test_unmapped_fail_closed(self) -> None:
        rows = [_bc(bc_id="BC-1", feature_id="FEATURE-UNKNOWN")]
        sel = gmi_runtime.select_chain_bcs(rows, self.FMAP)
        self.assertEqual(sel["selected"], [])
        self.assertEqual(sel["unmapped"],
                         [{"bc_id": "BC-1", "feature_id": "FEATURE-UNKNOWN"}])

    def test_missing_map_fallback_to_evidence_class(self) -> None:
        fmap = {"runtime_features": set(), "source_confirm_features": set(),
                "pages_by_feature": {}, "missing": True}
        rows = [_bc(bc_id="BC-1", evidence_class="RUNTIME_REQUIRED"),
                _bc(bc_id="BC-2", evidence_class="STATIC_ONLY"),
                _bc(bc_id="BC-3", evidence_class="")]
        sel = gmi_runtime.select_chain_bcs(rows, fmap)
        self.assertTrue(sel["fallback"])
        self.assertEqual([r["bc_id"] for r in sel["selected"]], ["BC-1"])
        self.assertEqual(len(sel["excluded"]), 2)


class EvidenceSlimFormatTest(unittest.TestCase):
    """证据瘦身格式：结果导向，不再有四件套+side-effects 大包。"""

    def test_chain_csv_fields_shape(self) -> None:
        f = gmi_runtime.CHAIN_CSV_FIELDS
        for col in ("bc_id", "assertion_results", "assertions_passed",
                    "chain_status", "evidence_dir"):
            self.assertIn(col, f)
        # 旧页面模式四件套/side-effects 列不进链表（瘦身承诺）
        for legacy in ("before_evidence_ref", "after_evidence_ref",
                       "persistence_evidence_ref", "side_effect_evidence_ref"):
            self.assertNotIn(legacy, f)

    def test_evidence_organized_by_bc_id(self) -> None:
        self.assertEqual(gmi_runtime.chain_evidence_relpath("BC-0042"),
                         "runtime-evidence/evidence/chains/BC-0042")

    def test_blocked_status_constant(self) -> None:
        self.assertEqual(set(gmi_runtime.CHAIN_BLOCKED_STATUS),
                          {"NAV_FAIL", "STEPS_FAIL", "ANR_BLOCKED",
                           "UNRESOLVED_PAGE_REF", "INVALID_CONTRACT",
                           "UNSUPPORTED_ORACLE", "PRECONDITION_FAILED"})
        # reconcile 依赖：CHAIN_FAIL 不在 blocked 集（它构成行为矛盾）
        self.assertNotIn("CHAIN_FAIL", gmi_runtime.CHAIN_BLOCKED_STATUS)

    def test_assertion_kinds_contract(self) -> None:
        self.assertEqual(gmi_runtime.CHAIN_ASSERTION_KINDS,
                         ("text_visible", "text_gone", "persist_after_restart"))
        self.assertEqual(gmi_runtime.CHAIN_STEP_ACTIONS, ("tap", "input", "back"))


if __name__ == "__main__":
    unittest.main()