# -*- coding: utf-8 -*-
"""test_build_bc -- build_behavior_contracts.py 十字段强制完整单测
（收敛式重构批次1，任务 #81）。

覆盖：
  - RUNTIME_REQUIRED 行十字段（user_intent / pre_state / semantic_input /
    operation_steps / data_state_change / observable_result /
    persistence_targets / external_side_effects / result_assertions /
    source_refs）缺值 → INVALID_CONTRACT 错误；
  - external_side_effects 空时可写 NONE 占位（大小写不敏感）也算填；
  - STATIC_ONLY 行不强制（保持宽松）；
  - 骨架生成路径 skeleton_mode 豁免（语义列留空待 LLM 分片填充是设计内）；
  - 端到端 CLI --validate：空字段 RUNTIME_REQUIRED BC → 退出非零。
"""
from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import build_behavior_contracts as bbc  # noqa: E402


PAGE_IDS = {"PAGE-X", "PAGE-Y"}


def _row(**kw) -> dict:
    """合法完整的 RUNTIME_REQUIRED 行（十字段全填）。"""
    row = {
        "bc_id": "BC-0001", "feature_id": "FEATURE-A", "page_ref": "PAGE-X",
        "user_intent": "新建待办", "pre_state": "语言=中文",
        "operation": "点击新建并输入标题",
        "data_state_change": "todo 表新增一行",
        "business_computation_refs": "",
        "observable_result": "列表出现 TEST-X",
        "persistence_targets": "Room:todo",
        "external_side_effects": "NONE",
        "evidence_class": "RUNTIME_REQUIRED", "impact": "high",
        "source_refs": "app/src/Foo.kt:12",
        "operation_steps": '[{"action":"tap","target":"新建"}]',
        "result_assertions": '[{"kind":"text_visible","value":"TEST-X"}]',
        "semantic_input": "输入标题 TEST-X",
    }
    row.update(kw)
    return row


class MandatoryTenFieldsTest(unittest.TestCase):
    """RUNTIME_REQUIRED 十字段强制完整（--validate 收口路径）。"""

    def test_complete_runtime_required_row_passes(self) -> None:
        errors = bbc.validate_bc_rows([_row()], ["FEATURE-A"], PAGE_IDS)
        self.assertEqual(errors, [])

    def test_each_empty_field_is_invalid_contract(self) -> None:
        fields = ["user_intent", "pre_state", "semantic_input",
                  "operation_steps", "data_state_change", "observable_result",
                  "persistence_targets", "external_side_effects",
                  "result_assertions", "source_refs"]
        for col in fields:
            row = _row(bc_id="BC-0001")
            row[col] = ""
            errors = bbc.validate_bc_rows([row], ["FEATURE-A"], PAGE_IDS)
            hit = [e for e in errors if "INVALID_CONTRACT" in e and col in e]
            self.assertTrue(hit, f"{col} 空值应报 INVALID_CONTRACT：{errors}")

    def test_none_placeholder_counts_as_filled(self) -> None:
        for v in ("NONE", "none", "None"):
            errors = bbc.validate_bc_rows(
                [_row(external_side_effects=v)], ["FEATURE-A"], PAGE_IDS)
            self.assertEqual(
                [e for e in errors if "external_side_effects" in e], [],
                f"占位 {v!r} 不应报错：{errors}")

    def test_static_only_row_not_enforced(self) -> None:
        """STATIC_ONLY 行十字段不强制（保持宽松）。"""
        row = _row(evidence_class="STATIC_ONLY", impact="normal",
                   user_intent="", pre_state="", semantic_input="",
                   operation_steps="", result_assertions="",
                   data_state_change="", observable_result="",
                   persistence_targets="", external_side_effects="")
        errors = bbc.validate_bc_rows([row], ["FEATURE-A"], PAGE_IDS)
        self.assertEqual([e for e in errors if "INVALID_CONTRACT" in e], [])

    def test_skeleton_mode_exempts_mandatory_fields(self) -> None:
        """骨架生成路径豁免（语义列留空待 LLM 分片填充是设计内）。"""
        row = _row(user_intent="", pre_state="", semantic_input="",
                   operation_steps="", result_assertions="",
                   data_state_change="", observable_result="",
                   persistence_targets="", external_side_effects="")
        errors = bbc.validate_bc_rows([row], [], PAGE_IDS, skeleton_mode=True)
        self.assertEqual(errors, [])

    def test_mandatory_field_list_is_exactly_ten(self) -> None:
        self.assertEqual(len(bbc.RUNTIME_REQUIRED_MANDATORY_FIELDS), 10)
        self.assertEqual(set(bbc.RUNTIME_REQUIRED_MANDATORY_FIELDS), {
            "user_intent", "pre_state", "semantic_input", "operation_steps",
            "data_state_change", "observable_result", "persistence_targets",
            "external_side_effects", "result_assertions", "source_refs"})


class ValidateCliTest(unittest.TestCase):
    """端到端 CLI：空字段 RUNTIME_REQUIRED BC → --validate 退出非零。"""

    def _build_ws(self, tmp: str) -> Path:
        ws = Path(tmp)
        cands = ws / "candidates"
        cands.mkdir(parents=True)
        (ws / "scope.json").write_text(
            '{"migration_scope": {"included_features": ["FEATURE-A"]}}',
            encoding="utf-8")
        with open(cands / "inventory.candidates.csv", "w",
                  encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["page_id", "feature_id", "source_ref",
                        "state_expression", "entry_condition"])
            w.writerow(["PAGE-X", "FEATURE-A", "app/src/Foo.kt:12", "", ""])
        return ws

    def test_validate_fails_on_empty_runtime_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = self._build_ws(tmp)
            out = ws / "behavior-contracts.csv"
            bad = _row(pre_state="", semantic_input="",
                       result_assertions="", observable_result="")
            with open(out, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=bbc.BC_FIELDS)
                w.writeheader()
                w.writerow(bad)
            r = subprocess.run(
                [sys.executable, str(SCRIPTS / "build_behavior_contracts.py"),
                 "--workspace", str(ws), "--validate"],
                capture_output=True, text=True, timeout=60)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("INVALID_CONTRACT", r.stdout)
            self.assertIn("pre_state", r.stdout)

    def test_validate_passes_on_complete_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = self._build_ws(tmp)
            out = ws / "behavior-contracts.csv"
            with open(out, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=bbc.BC_FIELDS)
                w.writeheader()
                w.writerow(_row())
            r = subprocess.run(
                [sys.executable, str(SCRIPTS / "build_behavior_contracts.py"),
                 "--workspace", str(ws), "--validate"],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("validate OK", r.stdout)


if __name__ == "__main__":
    unittest.main()

class OptionalAssertionBanTest(unittest.TestCase):
    """提交前自检 2-A：RUNTIME_REQUIRED 断言不得标记 optional:true（P2 侧全 required）。"""

    BASE = {
        "bc_id": "BC-OPT-1", "feature_id": "FEATURE-AUTH", "page_ref": "PAGE-LOGIN",
        "user_intent": "u", "pre_state": "p", "semantic_input": "s",
        "operation": "tap", "operation_steps": '[{"action":"tap","target":"x"}]',
        "data_state_change": "d", "observable_result": "o",
        "persistence_targets": "t", "external_side_effects": "NONE",
        "result_assertions": '[{"kind":"text_visible","value":"ok"}]',
        "evidence_class": "RUNTIME_REQUIRED", "impact": "high",
        "source_refs": "app/Login.kt:10", "business_computation_refs": "",
    }

    def test_optional_true_rejected(self):
        row = dict(self.BASE)
        row["result_assertions"] = (
            '[{"kind":"text_visible","value":"ok"},'
            ' {"kind":"persist_after_restart","value":"ok","optional":true}]')
        errs = bbc.validate_bc_rows([row], ["FEATURE-AUTH"], {"PAGE-LOGIN"}, False)
        self.assertTrue(any("optional:true" in e and "INVALID_CONTRACT" in e for e in errs), errs)

    def test_optional_string_true_rejected(self):
        row = dict(self.BASE)
        row["result_assertions"] = (
            '[{"kind":"text_visible","value":"ok","optional":"True"}]')
        errs = bbc.validate_bc_rows([row], ["FEATURE-AUTH"], {"PAGE-LOGIN"}, False)
        self.assertTrue(any("optional:true" in e for e in errs), errs)

    def test_clean_assertions_unaffected(self):
        errs = bbc.validate_bc_rows([dict(self.BASE)], ["FEATURE-AUTH"], {"PAGE-LOGIN"}, False)
        self.assertEqual([e for e in errs if "optional" in e], [])
