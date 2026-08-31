"""Gate 4 对 dual-diff-results.csv 的可选消费单测（任务 #93）。

背景：dual_verify.py（#91/#92）产出 dual-diff-results.csv，其 schema 与
replay-results.csv 同族但不同列（verdict ∈ MATCH/DIFF/MANUAL 而非
assertion_status ∈ PASS/FAIL/...），因此不能作为 replay-results.csv 的
drop-in 被 load_replay_results 消费——validate_stage4 以独立可选规则
evaluate_dual_diff_results 消费之（batch 5 #93 最小适配）。

正反例：
  - 文件不存在 → 规则休眠（PASS, activated=False），不产生任何 error
    （现有 replay-results 消费链行为完全不变）；
  - 全 MATCH（含 MANUAL 行）→ PASS，MANUAL 行进 manual_rows 仅展示；
  - 任一 DIFF → FAIL + error（双侧实测缺失的 DIFF 再加一条 error）；
  - 坏 verdict 枚举 / 缺列 / 空 / 重复 bc×type → FAIL + error。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import validate_stage4 as gate  # noqa: E402


DUAL_FIELDS = [
    "bc_id", "feature_id", "assertion_type", "verdict",
    "android_expected", "harmony_actual", "evidence_refs", "note",
]


def _write_dual(workspace: Path, rows: list[dict]) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    lines = [",".join(DUAL_FIELDS)]
    for row in rows:
        lines.append(",".join(str(row.get(field, "")) for field in DUAL_FIELDS))
    (workspace / "dual-diff-results.csv").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def _match(bc_id: str = "BC-1", category: str = "observable") -> dict:
    return {
        "bc_id": bc_id, "feature_id": "F-1", "assertion_type": category,
        "verdict": "MATCH", "android_expected": "x", "harmony_actual": "x",
        "evidence_refs": "a;b", "note": "dual-source",
    }


class DualDiffGateConsumptionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_absent_file_keeps_rule_dormant(self) -> None:
        errors: list[str] = []
        rule = gate.evaluate_dual_diff_results(self.workspace, errors)
        self.assertEqual(rule["status"], "PASS")
        self.assertFalse(rule["activated"])
        self.assertEqual(errors, [])

    def test_all_match_with_manual_passes(self) -> None:
        rows = [_match("BC-1", cat) for cat in
                ("observable", "data", "persistence", "side_effect")]
        manual = _match("BC-2", "side_effect")
        manual["verdict"] = "MANUAL"
        manual["note"] = "dual-source no public api"
        _write_dual(self.workspace, rows + [manual])
        errors: list[str] = []
        rule = gate.evaluate_dual_diff_results(self.workspace, errors)
        self.assertEqual(rule["status"], "PASS")
        self.assertTrue(rule["activated"])
        self.assertEqual(rule["match"], 4)
        self.assertEqual(rule["manual"], 1)
        self.assertEqual(rule["diff"], 0)
        self.assertEqual(rule["manual_rows"], ["BC-2/side_effect"])
        self.assertEqual(errors, [])

    def test_any_diff_fails_with_error(self) -> None:
        rows = [_match("BC-1", "observable")]
        diff = _match("BC-1", "data")
        diff.update({
            "verdict": "DIFF",
            "android_expected": "locale=en",
            "harmony_actual": "locale=zh",
        })
        _write_dual(self.workspace, rows + [diff])
        errors: list[str] = []
        rule = gate.evaluate_dual_diff_results(self.workspace, errors)
        self.assertEqual(rule["status"], "FAIL")
        self.assertEqual(rule["diff"], 1)
        self.assertEqual(rule["diff_rows"], ["BC-1/data"])
        self.assertTrue(any("BC-1/data" in item and "DIFF" in item
                            for item in errors))

    def test_diff_without_both_side_observations_adds_error(self) -> None:
        diff = _match("BC-9", "persistence")
        diff.update({"verdict": "DIFF", "android_expected": "",
                     "harmony_actual": "locale=zh"})
        _write_dual(self.workspace, [diff])
        errors: list[str] = []
        rule = gate.evaluate_dual_diff_results(self.workspace, errors)
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("without both side observations" in item
                            for item in errors))

    def test_bad_verdict_enum_fails(self) -> None:
        row = _match()
        row["verdict"] = "PASS"  # replay 枚举混入 dual 文件 → 拒绝
        _write_dual(self.workspace, [row])
        errors: list[str] = []
        rule = gate.evaluate_dual_diff_results(self.workspace, errors)
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("unknown verdict" in item for item in errors))

    def test_missing_column_fails(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "dual-diff-results.csv").write_text(
            "bc_id,feature_id,assertion_type\nBC-1,F-1,observable\n",
            encoding="utf-8")
        errors: list[str] = []
        rule = gate.evaluate_dual_diff_results(self.workspace, errors)
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("lacks columns" in item for item in errors))

    def test_duplicate_bc_and_category_fails(self) -> None:
        _write_dual(self.workspace, [_match(), _match()])
        errors: list[str] = []
        rule = gate.evaluate_dual_diff_results(self.workspace, errors)
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(any("duplicate" in item for item in errors))

    def test_empty_file_fails(self) -> None:
        # 空文件被 _common.read_csv 拒绝（no header）→ unreadable 分支，
        # 同样 fail-closed。
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "dual-diff-results.csv").write_text("", encoding="utf-8")
        errors: list[str] = []
        rule = gate.evaluate_dual_diff_results(self.workspace, errors)
        self.assertEqual(rule["status"], "FAIL")
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()