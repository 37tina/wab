"""Gate 4 新规则 must_read_receipt 单测（收敛式重构批次 2 #85）。

正反例：
  - RUNTIME feature 无 consumed_source_refs 回执 → gate FAIL（error）；
  - 回执必须是工单 must_read.android_source_refs 子集（编造引用 FAIL）；
  - DebugSemanticProbe 哈希与工单 expected_sha256 不一致 → FAIL；
  - 工单无探针绑定（旧 run）→ probe 校验 DORMANT（向后兼容）。
"""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import validate_stage4 as gate  # noqa: E402


def _write_declarations(workspace: Path, rows: list[dict]) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    fields = ["feature_id", "data_reads", "data_writes",
              "harmony_persistence", "source_refs",
              "consumed_bc_ids", "consumed_source_refs",
              "consumed_runtime_refs"]
    with (workspace / "implementation-declarations.csv").open(
            "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def _denominators(verify_mode: str = "RUNTIME") -> dict:
    return {
        "features": {
            "FEATURE-X": {"verify_mode": verify_mode,
                          "data_objects": {"reads": [], "writes": []}},
        },
        "behavior_by_feature": {},
        "behavior_count": 0,
        "data_relations": [],
        "reconciliation": [],
        "data_contracts": [],
    }


def _work_order(must_read_sources=None, probe_expected=None) -> dict:
    return {
        "feature_manifest": [{
            "feature_id": "FEATURE-X",
            "verify_mode": "RUNTIME",
            "must_read": {
                "behavior_contract_ids": ["BC-1"],
                "android_source_refs": must_read_sources
                if must_read_sources is not None
                else ["app/src/Home.kt:1", "app/src/Sort.kt:15"],
                "runtime_evidence_refs": [
                    "phase-02-android-inventory/runtime-evidence/"
                    "evidence/chains/BC-1"],
                "data_relations": [],
                "visual_memory_surface": [],
                "p3_surface_plan": [],
            },
        }],
        "semantic_probe": {
            "expected_sha256": probe_expected,
        } if probe_expected else None,
    }


class MustReadReceiptRuleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mrr-")
        self.root = Path(self.temp.name)
        self.workspace = self.root / "ws"

    def tearDown(self):
        self.temp.cleanup()

    def _evaluate(self, declarations, denominators=None, work_order=None):
        _write_declarations(self.workspace, declarations)
        errors: list[str] = []
        rule = gate.evaluate_must_read_receipt(
            self.workspace,
            denominators or _denominators(),
            work_order or _work_order(),
            errors,
        )
        return rule, errors

    def test_positive_runtime_feature_with_receipt(self):
        rule, errors = self._evaluate([{
            "feature_id": "FEATURE-X",
            "consumed_source_refs": "app/src/Home.kt:1",
        }])
        self.assertEqual(rule["status"], "PASS")
        self.assertEqual(errors, [])
        self.assertEqual(rule["probe_status"], "DORMANT")

    def test_negative_runtime_feature_without_receipt(self):
        rule, errors = self._evaluate([{
            "feature_id": "FEATURE-X",
            "consumed_source_refs": "",
        }])
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("no consumed_source_refs receipt" in e
                            for e in errors))

    def test_negative_missing_declaration_column_set(self):
        # declarations 缺 consumed 列（旧格式）→ 视为空回执 → FAIL
        rule, errors = self._evaluate([{
            "feature_id": "FEATURE-X",
            # 无 consumed_source_refs 键
        }])
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("no consumed_source_refs receipt" in e
                            for e in errors))

    def test_negative_fabricated_receipt(self):
        rule, errors = self._evaluate([{
            "feature_id": "FEATURE-X",
            "consumed_source_refs": "made/up/File.kt:999",
        }])
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("not in work-order must_read" in e
                            for e in errors))

    def test_source_confirm_feature_not_forced(self):
        rule, errors = self._evaluate(
            [{"feature_id": "FEATURE-X", "consumed_source_refs": ""}],
            denominators=_denominators("SOURCE_CONFIRM"))
        self.assertEqual(rule["status"], "PASS")

    def test_probe_hash_enforced_and_mismatch(self):
        probe = (self.workspace / "harmony-project"
                 / "entry/src/main/ets/probe/DebugSemanticProbe.ets")
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("// frozen probe\n", encoding="utf-8")
        import hashlib
        real_hash = hashlib.sha256(probe.read_bytes()).hexdigest()

        # 一致 → ENFORCED PASS
        rule, errors = self._evaluate(
            [{"feature_id": "FEATURE-X",
              "consumed_source_refs": "app/src/Home.kt:1"}],
            work_order=_work_order(probe_expected=real_hash))
        self.assertEqual(rule["probe_status"], "ENFORCED")
        self.assertEqual(rule["status"], "PASS")

        # 不一致（实施者篡改探针）→ FAIL
        rule, errors = self._evaluate(
            [{"feature_id": "FEATURE-X",
              "consumed_source_refs": "app/src/Home.kt:1"}],
            work_order=_work_order(probe_expected="0" * 64))
        self.assertEqual(rule["probe_status"], "ENFORCED")
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("probe hash differs" in e for e in errors))

    def test_probe_missing_file_fails(self):
        rule, errors = self._evaluate(
            [{"feature_id": "FEATURE-X",
              "consumed_source_refs": "app/src/Home.kt:1"}],
            work_order=_work_order(probe_expected="0" * 64))
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("probe missing" in e for e in errors))


if __name__ == "__main__":
    unittest.main()