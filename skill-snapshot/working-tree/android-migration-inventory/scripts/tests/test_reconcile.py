# -*- coding: utf-8 -*-
"""test_reconcile -- 对账引擎 reconcile.py 单测（Phase 2 新范式第 7 步）。

覆盖四态判定矩阵：
  CONFIRMED        源码声明 ↔ runtime 断言确认（含无声明 runtime-observed；
                   #81 后无 degraded 链路径）
  CONFLICT         源码说有变化/BC 期望有结果但实测断言 FAIL（含
                   SOURCE_CONFIRM 意外跑失败）
  SOURCE_CONFIRMED 容器页/纯展示（feature-map verify_mode 或 evidence_class
                   降级 STATIC_ONLY），不为证明"被访问过"硬跑
  GAP              runtime 没跑（有声明/无声明/unmapped）或链 blocked
                   （NAV_FAIL/STEPS_FAIL/ANR_BLOCKED/UNRESOLVED_PAGE_REF/
                   INVALID_CONTRACT/UNSUPPORTED_ORACLE/PRECONDITION_FAILED）
以及端到端 CLI（临时工作区 -> reconciliation.csv 列/退出码 0|1|2）。
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import reconcile  # noqa: E402


def _bc(bc_id: str, feature_id: str = "FEATURE-A", **kw) -> dict:
    row = {"bc_id": bc_id, "feature_id": feature_id, "page_ref": "PAGE-X",
           "evidence_class": "RUNTIME_REQUIRED",
           "data_state_change": "", "persistence_targets": "",
           "external_side_effects": "", "source_refs": "app/src/Foo.kt:12"}
    row.update(kw)
    return row


def _chain(bc_id: str, status: str, assertions=None, note: str = "ok",
           evidence: str = "") -> dict:
    return {"bc_id": bc_id, "chain_status": status, "note": note,
            "evidence_dir": evidence or
            f"runtime-evidence/evidence/chains/{bc_id}",
            "assertion_results": json.dumps(assertions or [], ensure_ascii=False)}


FMAP = {"runtime_features": {"FEATURE-A", "FEATURE-B"},
        "source_confirm_features": {"FEATURE-NAV"},
        "pages_by_feature": {}, "missing": False}

PASS_A = [{"kind": "text_visible", "value": "TEST-X", "verdict": "PASS"},
          {"kind": "persist_after_restart", "value": "TEST-X", "verdict": "PASS"}]
FAIL_A = [{"kind": "text_visible", "value": "TEST-X", "verdict": "FAIL"},
          {"kind": "persist_after_restart", "value": "TEST-X", "verdict": "PASS"}]


class FieldDeclaredTest(unittest.TestCase):
    """源码声明侧字段判定：无/无(...)/none 视为无声明。"""

    def test_no_value_tokens(self) -> None:
        for v in ("", "  ", "无", "无(引导流程数据不在范围)", "none", "N/A", "-",
                  "不适用"):
            self.assertFalse(reconcile.field_declared(v), repr(v))

    def test_real_declarations(self) -> None:
        for v in ("写入 preference: settings_dark_mode", "数据库 todo 表新增行",
                  "发送通知提醒"):
            self.assertTrue(reconcile.field_declared(v), repr(v))

    def test_declared_sides(self) -> None:
        d = reconcile.declared_sides(_bc(
            "BC-1", data_state_change="写库", persistence_targets="无",
            external_side_effects=""))
        self.assertEqual(d, {"data_state_change": True,
                             "persistence_targets": False,
                             "external_side_effects": False})


class VerifyModeTest(unittest.TestCase):
    """feature-map 优先 / 缺失降级 evidence_class。"""

    def test_feature_map_mode(self) -> None:
        self.assertEqual(reconcile.bc_verify_mode(
            _bc("BC-1", "FEATURE-A"), FMAP), ("RUNTIME", "FEATURE_MAP"))
        self.assertEqual(reconcile.bc_verify_mode(
            _bc("BC-1", "FEATURE-NAV"), FMAP), ("SOURCE_CONFIRM", "FEATURE_MAP"))
        self.assertEqual(reconcile.bc_verify_mode(
            _bc("BC-1", "FEATURE-??"), FMAP), ("", "FEATURE_MAP"))

    def test_fallback_mode(self) -> None:
        fmap = dict(FMAP, missing=True, runtime_features=set(),
                    source_confirm_features=set())
        self.assertEqual(reconcile.bc_verify_mode(
            _bc("BC-1", evidence_class="RUNTIME_REQUIRED"), fmap),
            ("RUNTIME", "EVIDENCE_CLASS_FALLBACK"))
        self.assertEqual(reconcile.bc_verify_mode(
            _bc("BC-1", evidence_class="STATIC_ONLY"), fmap),
            ("SOURCE_CONFIRM", "EVIDENCE_CLASS_FALLBACK"))


class ReconcileOneTest(unittest.TestCase):
    """四态判定矩阵（核心）。"""

    DECL = {"data_state_change": True, "persistence_targets": False,
            "external_side_effects": False}
    NO_DECL = {"data_state_change": False, "persistence_targets": False,
               "external_side_effects": False}

    def test_confirmed_declared_and_asserted(self) -> None:
        v, note, ev = reconcile.reconcile_one(
            _bc("BC-1", data_state_change="写库"), "RUNTIME", "FEATURE_MAP",
            _chain("BC-1", "CHAIN_PASS", PASS_A), self.DECL)
        self.assertEqual(v, "CONFIRMED")
        self.assertEqual(note, "declared & asserted")
        self.assertTrue(ev)

    def test_confirmed_runtime_observed_no_declaration(self) -> None:
        """源码无声明 + 实测 PASS -> CONFIRMED + note 标注（非 GAP）。"""
        v, note, _ = reconcile.reconcile_one(
            _bc("BC-1"), "RUNTIME", "FEATURE_MAP",
            _chain("BC-1", "CHAIN_PASS", PASS_A), self.NO_DECL)
        self.assertEqual(v, "CONFIRMED")
        self.assertIn("runtime-observed", note)

    def test_gap_invalid_contract_chain(self) -> None:
        """#81：无断言链（INVALID_CONTRACT）-> GAP 而非 CONFIRMED(degraded)。

        degraded CHAIN_PASS 路径已删除：契约不完整必须回修 BC。"""
        v, note, _ = reconcile.reconcile_one(
            _bc("BC-1", data_state_change="写库"), "RUNTIME", "FEATURE_MAP",
            _chain("BC-1", "INVALID_CONTRACT",
                   note="RUNTIME_REQUIRED contract has no result_assertions"),
            self.DECL)
        self.assertEqual(v, "GAP")
        self.assertIn("INVALID_CONTRACT", note)

    def test_gap_unsupported_oracle_chain(self) -> None:
        """#81：全断言无 oracle（UNSUPPORTED_ORACLE）-> GAP，绝不能 PASS。"""
        v, note, _ = reconcile.reconcile_one(
            _bc("BC-1", data_state_change="写库"), "RUNTIME", "FEATURE_MAP",
            _chain("BC-1", "UNSUPPORTED_ORACLE",
                   note="all assertion kinds unsupported: db_query"),
            self.DECL)
        self.assertEqual(v, "GAP")
        self.assertIn("UNSUPPORTED_ORACLE", note)

    def test_gap_precondition_failed_chain(self) -> None:
        """#83：前置校验失败（PRECONDITION_FAILED）-> GAP（非功能 FAIL）。"""
        v, note, _ = reconcile.reconcile_one(
            _bc("BC-1", data_state_change="写库"), "RUNTIME", "FEATURE_MAP",
            _chain("BC-1", "PRECONDITION_FAILED",
                   note="precondition unverified, missing on page: 中文"),
            self.DECL)
        self.assertEqual(v, "GAP")
        self.assertIn("PRECONDITION_FAILED", note)

    def test_degraded_note_chain_pass_not_special_cased(self) -> None:
        """#81：note 带 degraded 字样的历史 CHAIN_PASS 行不再有特殊加分路径
        （分支已删；verdict 仅由 chain_status 决定，此处仍 CONFIRMED 但
        note 不追加 degraded 标注）。"""
        v, note, _ = reconcile.reconcile_one(
            _bc("BC-1", data_state_change="写库"), "RUNTIME", "FEATURE_MAP",
            _chain("BC-1", "CHAIN_PASS", PASS_A,
                   note="degraded:no_assertions(nav+snapshot only)"), self.DECL)
        self.assertEqual(v, "CONFIRMED")
        self.assertEqual(note, "declared & asserted")

    def test_conflict_declared_effect_not_observed(self) -> None:
        v, note, ev = reconcile.reconcile_one(
            _bc("BC-1", data_state_change="写 preference X"), "RUNTIME",
            "FEATURE_MAP", _chain("BC-1", "CHAIN_FAIL", FAIL_A), self.DECL)
        self.assertEqual(v, "CONFLICT")
        self.assertIn("text_visible=TEST-X", note)
        self.assertTrue(ev)

    def test_conflict_without_declaration(self) -> None:
        """无源码声明 + 断言 FAIL -> 仍 CONFLICT（BC 期望未达成）。"""
        v, note, _ = reconcile.reconcile_one(
            _bc("BC-1"), "RUNTIME", "FEATURE_MAP",
            _chain("BC-1", "CHAIN_FAIL", FAIL_A), self.NO_DECL)
        self.assertEqual(v, "CONFLICT")
        self.assertIn("no source declaration", note)

    def test_conflict_unparseable_results(self) -> None:
        row = _chain("BC-1", "CHAIN_FAIL")
        row["assertion_results"] = "{broken"
        v, note, _ = reconcile.reconcile_one(
            _bc("BC-1", data_state_change="写库"), "RUNTIME", "FEATURE_MAP",
            row, self.DECL)
        self.assertEqual(v, "CONFLICT")
        self.assertIn("assertions failed", note)

    def test_source_confirmed_not_run_by_design(self) -> None:
        v, note, ev = reconcile.reconcile_one(
            _bc("BC-1", "FEATURE-NAV"), "SOURCE_CONFIRM", "FEATURE_MAP",
            None, self.DECL)
        self.assertEqual(v, "SOURCE_CONFIRMED")
        self.assertIn("not run by design", note)
        self.assertEqual(ev, "app/src/Foo.kt:12")  # 证据指向源码声明

    def test_source_confirmed_unexpected_fail_escalates(self) -> None:
        """SOURCE_CONFIRM 意外出现 CHAIN_FAIL 行 -> 升级 CONFLICT。"""
        v, note, _ = reconcile.reconcile_one(
            _bc("BC-1", "FEATURE-NAV"), "SOURCE_CONFIRM", "FEATURE_MAP",
            _chain("BC-1", "CHAIN_FAIL", FAIL_A), self.NO_DECL)
        self.assertEqual(v, "CONFLICT")
        self.assertIn("unexpected", note)

    def test_source_confirmed_unexpected_pass_stays(self) -> None:
        v, note, _ = reconcile.reconcile_one(
            _bc("BC-1", "FEATURE-NAV"), "SOURCE_CONFIRM", "FEATURE_MAP",
            _chain("BC-1", "CHAIN_PASS", PASS_A), self.NO_DECL)
        self.assertEqual(v, "SOURCE_CONFIRMED")
        self.assertIn("unexpected", note)

    def test_gap_not_run_declared(self) -> None:
        v, note, ev = reconcile.reconcile_one(
            _bc("BC-1", data_state_change="写库"), "RUNTIME", "FEATURE_MAP",
            None, self.DECL)
        self.assertEqual((v, ev), ("GAP", ""))
        self.assertIn("declared but chain not run", note)

    def test_gap_not_run_no_declaration(self) -> None:
        v, note, _ = reconcile.reconcile_one(
            _bc("BC-1"), "RUNTIME", "FEATURE_MAP", None, self.NO_DECL)
        self.assertEqual(v, "GAP")
        self.assertIn("no declaration and chain not run", note)

    def test_gap_unmapped_feature(self) -> None:
        v, note, _ = reconcile.reconcile_one(
            _bc("BC-1", "FEATURE-??"), "", "FEATURE_MAP", None, self.NO_DECL)
        self.assertEqual(v, "GAP")
        self.assertIn("unmapped", note)

    def test_gap_blocked_statuses(self) -> None:
        """链 blocked（采集受阻）-> GAP 而非 CONFLICT。"""
        for status in ("NAV_FAIL", "STEPS_FAIL", "ANR_BLOCKED",
                       "UNRESOLVED_PAGE_REF"):
            v, note, _ = reconcile.reconcile_one(
                _bc("BC-1", data_state_change="写库"), "RUNTIME", "FEATURE_MAP",
                _chain("BC-1", status, note="anchors_tried=3"), self.DECL)
            self.assertEqual(v, "GAP", status)
            self.assertIn(status, note)

    def test_gap_unknown_chain_status_fail_closed(self) -> None:
        v, note, _ = reconcile.reconcile_one(
            _bc("BC-1"), "RUNTIME", "FEATURE_MAP",
            _chain("BC-1", "SOMETHING_NEW"), self.NO_DECL)
        self.assertEqual(v, "GAP")
        self.assertIn("unknown chain_status", note)


class ReconcileCliTest(unittest.TestCase):
    """端到端 CLI：临时工作区 -> reconciliation.csv + 退出码。"""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.ws = Path(self._td.name)
        add_path = self.ws / "runtime-evidence"
        add_path.mkdir(parents=True)
        self._write_csv(
            self.ws / "behavior-contracts.csv",
            ["bc_id", "feature_id", "page_ref", "data_state_change",
             "persistence_targets", "external_side_effects", "evidence_class",
             "source_refs"],
            [
                ["BC-1", "FEATURE-A", "PAGE-X", "写库新增待办", "", "",
                 "RUNTIME_REQUIRED", "app/src/Foo.kt:12"],
                ["BC-2", "FEATURE-A", "PAGE-X", "", "", "",
                 "RUNTIME_REQUIRED", "app/src/Foo.kt:30"],
                ["BC-3", "FEATURE-NAV", "PAGE-MAIN", "无", "无", "无",
                 "STATIC_ONLY", "app/src/Main.kt:5"],
                ["BC-4", "FEATURE-B", "PAGE-Y", "写 preference X", "", "",
                 "RUNTIME_REQUIRED", "app/src/Bar.kt:7"],
            ])
        self._write_csv(
            add_path / "runtime-chains.csv",
            ["bc_id", "feature_id", "page_ref", "nav_status", "entry_anchor",
             "steps_total", "steps_ok", "assertions_total", "assertions_passed",
             "assertion_results", "chain_status", "note", "evidence_dir"],
            [
                ["BC-1", "FEATURE-A", "PAGE-X", "REACHED", "新建", "3", "3",
                 "2", "2",
                 json.dumps(PASS_A, ensure_ascii=False), "CHAIN_PASS", "ok",
                 "runtime-evidence/evidence/chains/BC-1"],
                ["BC-2", "FEATURE-A", "PAGE-X", "REACHED", "新建", "0", "0",
                 "0", "0", "[]", "INVALID_CONTRACT",
                 "RUNTIME_REQUIRED contract has no result_assertions",
                 "runtime-evidence/evidence/chains/BC-2"],
                ["BC-4", "FEATURE-B", "PAGE-Y", "NOT_REACHED", "", "1", "0",
                 "1", "0",
                 json.dumps(FAIL_A, ensure_ascii=False),
                 "STEPS_FAIL", "steps interrupted at 0/1",
                 "runtime-evidence/evidence/chains/BC-4"],
            ])
        (self.ws / "feature-map.json").write_text(json.dumps({
            "features": [
                {"feature_id": "FEATURE-A", "verify_mode": "RUNTIME",
                 "surfaces": [{"id": "PAGE-X", "kind": "page"}]},
                {"feature_id": "FEATURE-B", "verify_mode": "RUNTIME",
                 "surfaces": [{"id": "PAGE-Y", "kind": "page"}]},
                {"feature_id": "FEATURE-NAV", "verify_mode": "SOURCE_CONFIRM",
                 "surfaces": [{"id": "PAGE-MAIN", "kind": "container",
                               "is_container": True}]},
            ]}, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        self._td.cleanup()

    @staticmethod
    def _write_csv(path: Path, fields, rows) -> None:
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(fields)
            w.writerows(rows)

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "reconcile.py"), *args],
            capture_output=True, text=True, timeout=120)

    def test_end_to_end_matrix_and_columns(self) -> None:
        out_csv = self.ws / "reconciliation.csv"
        r = self._run("--workspace", str(self.ws), "--out", str(out_csv))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(out_csv, encoding="utf-8-sig") as f:
            rows = {row["bc_id"]: row for row in csv.DictReader(f)}
        # BC-1: 声明+断言全 PASS -> CONFIRMED
        self.assertEqual(rows["BC-1"]["verdict"], "CONFIRMED")
        # BC-2: 无断言链 INVALID_CONTRACT -> GAP（#81：绝不 CONFIRMED(degraded)）
        self.assertEqual(rows["BC-2"]["verdict"], "GAP")
        self.assertIn("INVALID_CONTRACT", rows["BC-2"]["note"])
        self.assertEqual(rows["BC-2"]["runtime_status"], "INVALID_CONTRACT")
        # BC-3: SOURCE_CONFIRM 未跑 -> SOURCE_CONFIRMED，证据=源码引用
        self.assertEqual(rows["BC-3"]["verdict"], "SOURCE_CONFIRMED")
        self.assertEqual(rows["BC-3"]["evidence_ref"], "app/src/Main.kt:5")
        self.assertEqual(rows["BC-3"]["runtime_status"], "")
        # BC-4: 链 blocked(STEPS_FAIL) -> GAP（不是 CONFLICT）
        self.assertEqual(rows["BC-4"]["verdict"], "GAP")
        self.assertIn("STEPS_FAIL", rows["BC-4"]["note"])
        self.assertEqual(rows["BC-4"]["runtime_status"], "STEPS_FAIL")
        # 核心列齐备（Gate 2 消费契约）
        for col in ("bc_id", "feature_id", "verdict", "evidence_ref", "note"):
            self.assertIn(col, rows["BC-1"])

    def test_exit_code_2_on_conflict(self) -> None:
        # BC-1 从 PASS 改 FAIL -> CONFIRMED 变 CONFLICT -> 退出码 2
        # （CSV 内 JSON 引号会被 csv 模块双写转义，故整表重写而非字符串替换）
        self._write_csv(
            self.ws / "runtime-evidence" / "runtime-chains.csv",
            ["bc_id", "feature_id", "page_ref", "nav_status", "entry_anchor",
             "steps_total", "steps_ok", "assertions_total", "assertions_passed",
             "assertion_results", "chain_status", "note", "evidence_dir"],
            [
                ["BC-1", "FEATURE-A", "PAGE-X", "REACHED", "新建", "3", "3",
                 "2", "1",
                 json.dumps(FAIL_A, ensure_ascii=False),
                 "CHAIN_FAIL", "assertions failed: text_visible=TEST-X",
                 "runtime-evidence/evidence/chains/BC-1"],
                ["BC-3", "FEATURE-NAV", "PAGE-MAIN", "NOT_REACHED", "", "0",
                 "0", "0", "0", "[]", "NAV_FAIL", "page not reached", ""],
            ])
        r = self._run("--workspace", str(self.ws))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("CONFLICT", r.stdout)
        # 接口契约（改造C 确认）：退出码 2 = "需要人工解释"信号而非终局失败，
        # reconciliation.csv 必须在退出前照常落盘（产出侧不硬拦）
        out_csv = self.ws / "reconciliation.csv"
        self.assertTrue(out_csv.exists())
        with open(out_csv, encoding="utf-8-sig") as f:
            rows = {row["bc_id"]: row for row in csv.DictReader(f)}
        self.assertEqual(rows["BC-1"]["verdict"], "CONFLICT")
        self.assertEqual(rows["BC-3"]["verdict"], "SOURCE_CONFIRMED")

    def test_exit_code_1_when_bc_missing(self) -> None:
        (self.ws / "behavior-contracts.csv").unlink()
        r = self._run("--workspace", str(self.ws))
        self.assertEqual(r.returncode, 1)

    def test_missing_runtime_chains_all_gap(self) -> None:
        (self.ws / "runtime-evidence" / "runtime-chains.csv").unlink()
        out_csv = self.ws / "reconciliation.csv"
        r = self._run("--workspace", str(self.ws), "--out", str(out_csv))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(out_csv, encoding="utf-8-sig") as f:
            rows = {row["bc_id"]: row for row in csv.DictReader(f)}
        self.assertEqual(rows["BC-1"]["verdict"], "GAP")
        self.assertEqual(rows["BC-3"]["verdict"], "SOURCE_CONFIRMED")

    def test_fallback_without_feature_map(self) -> None:
        """feature-map 缺失 -> evidence_class 降级（STATIC_ONLY->SOURCE_CONFIRMED）。"""
        (self.ws / "feature-map.json").unlink()
        out_csv = self.ws / "reconciliation.csv"
        r = self._run("--workspace", str(self.ws), "--out", str(out_csv))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(out_csv, encoding="utf-8-sig") as f:
            rows = {row["bc_id"]: row for row in csv.DictReader(f)}
        self.assertEqual(rows["BC-1"]["verdict"], "CONFIRMED")
        self.assertEqual(rows["BC-3"]["verdict"], "SOURCE_CONFIRMED")
        self.assertEqual(rows["BC-3"]["verify_side"], "EVIDENCE_CLASS_FALLBACK")


if __name__ == "__main__":
    unittest.main()