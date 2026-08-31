# -*- coding: utf-8 -*-
"""test_closure_hardening -- 第一/二轮最小修复的回归测试。

第一轮覆盖：
  修复 1（D-6）: gmi_closure.py 对 coverage-ledger.csv / audit-replay.csv /
      runtime-gate.csv 缺失或无数据行 fail-closed（exit 1，错误注明文件名）；
      phase-2-report.md 缺失同样阻塞。
  修复 4/5（P0-2）: gate_basis VISITED 文字动态生成；verdict 依据 closure gate。
第二轮（任务 #14）覆盖：
  修复 14a: adapter inventory.csv evidence_id 改 NONE_ 前缀行唯一占位。
  修复 14b: evidence-index.csv 补 relative_path / metadata_sha256 列。
  修复 14c: gate_basis 不再含与实际判定矛盾的 ">=80%" 字样。
  修复 14d: gmi_runtime.build_feature_coverage_rows 生成 runtime-feature-coverage.csv。
  附带断言（第一轮修复 2/3）: closure gate.unmapped 实算；artifact_hashes 新键。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
GMI_CLOSURE = SCRIPTS / "gmi_closure.py"
GMI_ADAPTER = SCRIPTS / "gmi_phase3_adapter.py"


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, timeout=120)


def make_closure_workspace(root: Path) -> Path:
    """最小合法 gmi 工作区：三件门禁 CSV 齐备且有数据行 + manifest + report。"""
    ws = root / "gmi-ws"
    _write(ws / "candidates" / "manifest.sha256", "0" * 64 + "  x.csv\n")
    _write(ws / "coverage" / "coverage-ledger.csv",
           "file,category,disposition,status,covering_candidates\n"
           "a.kt,source,IN_SCOPE,OK,CAND-CODE-0001\n")
    _write(ws / "runtime-evidence" / "audit-replay.csv",
           "page_id,symbol,replayed,recorded,discrepancy,note\n"
           "PAGE-LAUNCH,MainActivity,VISITED,VISITED,no,ok\n")
    _write(ws / "runtime-evidence" / "runtime-gate.csv",
           "page_id,symbol,status,evidence\n"
           "PAGE-LAUNCH,MainActivity,VISITED,PAGE-LAUNCH/ui.xml\n")
    _write(ws / "phase-2-report.md", "# phase-2 report\nP / VISITED / NOT_ENTERED\n")
    return ws


class GmiClosureFailClosedTest(unittest.TestCase):
    """修复 1：缺失/空数据 fail-closed；齐全时闭包成功。"""

    def test_closure_ok_when_inputs_complete(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = make_closure_workspace(Path(td))
            r = _run(GMI_CLOSURE, "--workspace", str(ws))
            self.assertEqual(r.returncode, 0, r.stderr)
            closure = json.loads((ws / "phase-2-closure.json").read_text(encoding="utf-8"))
            # 修复 2：unmapped 来自 ledger 实算（无 GAP 行 -> 0）
            self.assertEqual(closure["gate"]["unmapped"], 0)
            # 修复 3：artifact_hashes 新增两键；BC 缺失记空串，report 记实哈希
            hashes = closure["artifact_hashes"]
            self.assertIn("behavior_contracts_sha256", hashes)
            self.assertEqual(hashes["behavior_contracts_sha256"], "")
            self.assertTrue(hashes["phase2_report_sha256"])

    def _assert_blocked(self, ws: Path, needle: str) -> None:
        r = _run(GMI_CLOSURE, "--workspace", str(ws))
        self.assertEqual(r.returncode, 1, f"expected exit 1, got {r.returncode}\n{r.stdout}")
        combined = r.stdout + r.stderr
        self.assertIn("CLOSURE BLOCKED", combined)
        self.assertIn(needle, combined)

    def test_missing_audit_replay_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = make_closure_workspace(Path(td))
            (ws / "runtime-evidence" / "audit-replay.csv").unlink()
            self._assert_blocked(ws, "audit-replay.csv")

    def test_empty_runtime_gate_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = make_closure_workspace(Path(td))
            _write(ws / "runtime-evidence" / "runtime-gate.csv",
                   "page_id,symbol,status,evidence\n")  # 仅 header，无数据行
            self._assert_blocked(ws, "runtime-gate.csv")

    def test_missing_coverage_ledger_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = make_closure_workspace(Path(td))
            (ws / "coverage" / "coverage-ledger.csv").unlink()
            self._assert_blocked(ws, "coverage-ledger.csv")

    def test_missing_phase2_report_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = make_closure_workspace(Path(td))
            (ws / "phase-2-report.md").unlink()
            self._assert_blocked(ws, "phase-2-report.md")


def make_adapter_workspace(root: Path, visited: int, pages_total: int) -> Path:
    """最小可运行 adapter 工作区：closure(gate 达标与否由参数决定) + report + 证据目录。"""
    ws = root / f"adapter-ws-{visited}-{pages_total}"
    gate = {"unmapped": 0, "audit_discrepancy": 0,
            "visited": visited, "pages_total": pages_total}
    closure = {"generator": "gmi_closure", "workspace": str(ws),
               "closure_at": "2026-08-29T00:00:00Z", "gate": gate,
               "artifact_hashes": {}}
    _write(ws / "phase-2-closure.json", json.dumps(closure, ensure_ascii=False))
    _write(ws / "phase-2-report.md", "# phase-2 report\n")
    _write(ws / "candidates" / "inventory.candidates.csv",
           "feature_id,page_id,state_id,state_expression\n"
           "TODO-LIST,PAGE-MAINACTIVITY-9E8FBE45,STATE-1,DEFAULT\n")
    _write(ws / "runtime-evidence" / "runtime-feature-coverage.csv",
           "feature,status,evidence_hits\nTODO-LIST,VISITED,PAGE-LAUNCH:MainActivity\n")
    # 真实证据目录（14b fail-closed 前置：feature 证据目录必须含 ui.xml）
    _write(ws / "runtime-evidence" / "PAGE-LAUNCH" / "ui.xml",
           "<?xml version='1.0'?><hierarchy>fixture</hierarchy>")
    return ws


class AdapterVerdictFromClosureGateTest(unittest.TestCase):
    """修复 4/5：verdict 与 gate_basis 依据 closure gate 真实数字。"""

    def test_pass_and_dynamic_gate_basis(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # 17/21 恰好复现历史写死值 80.95%，用于验证公式等价
            ws = make_adapter_workspace(root, visited=17, pages_total=21)
            out = root / "run"
            r = _run(GMI_ADAPTER, "--workspace", str(ws), "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            p2 = out / "phase-02-android-inventory"
            self.assertEqual(
                json.loads((p2 / "page-gate-report.json").read_text(encoding="utf-8"))["machine_verdict"],
                "PASS")
            cr = json.loads((p2 / "closure-report.json").read_text(encoding="utf-8"))
            self.assertEqual(cr["final_verdict"], "PASS")
            self.assertTrue(cr["evidence_chain_closed"])
            gate_report = json.loads((out / "controller" / "gate-report.json").read_text(encoding="utf-8"))
            self.assertEqual(gate_report["verdict"], "PASS")
            # 修复 4/14c：动态 VISITED 数字 + 如实达标描述（不再含 ">=80%" 阈值字样）
            basis = gate_report["gate_basis"][-1]
            self.assertIn("VISITED 17/21=80.95%", basis)
            self.assertNotIn(">=80%", basis)

            # 修复 14a：inventory evidence_id 全部为 NONE_ 前缀行唯一占位
            inv_lines = (p2 / "inventory.csv").read_text(encoding="utf-8").splitlines()
            inv_rows = [line.split(",") for line in inv_lines[1:]]
            ev_col = inv_lines[0].split(",").index("evidence_id")
            for row in inv_rows:
                self.assertTrue(row[ev_col].startswith("NONE_"), row)
            self.assertEqual(inv_rows[0][ev_col],
                             "NONE_GMI-TODO-LIST-PAGE-MAINACTIVITY-9E8FBE45")

            # 修复 14b：evidence-index 含 relative_path / metadata_sha256 且语义正确
            import csv as _csv
            with open(p2 / "evidence-index.csv", encoding="utf-8") as f:
                ev_index = list(_csv.DictReader(f))
            self.assertTrue(ev_index)
            ui = ws / "runtime-evidence" / "PAGE-LAUNCH" / "ui.xml"
            import hashlib as _hl
            expected = _hl.sha256(ui.read_bytes()).hexdigest()
            for row in ev_index:
                self.assertEqual(row["status"], "ACCEPTED")
                self.assertTrue(row["relative_path"].startswith("runtime-evidence/"))
                self.assertEqual(row["metadata_sha256"], expected)
                self.assertEqual(row["evidence_id"],
                                 "NONE_GMI-TODO-LIST-PAGE-MAINACTIVITY-9E8FBE45")

    def test_gate_basis_numbers_follow_closure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = make_adapter_workspace(root, visited=5, pages_total=10)
            out = root / "run"
            r = _run(GMI_ADAPTER, "--workspace", str(ws), "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            gate_report = json.loads((out / "controller" / "gate-report.json").read_text(encoding="utf-8"))
            basis = gate_report["gate_basis"][-1]
            self.assertIn("VISITED 5/10=", basis)
            self.assertNotIn("17/21", basis)

    def test_bad_gate_refuses_pass(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # visited=0：无任何运行访问证据 -> 拒绝合成 PASS
            ws = make_adapter_workspace(root, visited=0, pages_total=21)
            r = _run(GMI_ADAPTER, "--workspace", str(ws), "--out", str(root / "run"))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("不达标", r.stderr + r.stdout)
            self.assertFalse((root / "run" / "phase-02-android-inventory"
                              / "page-gate-report.json").exists())


class GmiRuntimeFeatureCoverageTest(unittest.TestCase):
    """修复 14d：build_feature_coverage_rows 从 gate 行派生 feature 口径覆盖表。"""

    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(SCRIPTS))
        import gmi_runtime  # noqa: PLC0415  模块级无副作用（纯函数/常量）
        cls.rt = gmi_runtime

    def test_feature_coverage_derivation(self) -> None:
        page_id_map = {
            "PAGE-MAINACTIVITY-9E8FBE45": "PAGE-MAINACTIVITY-9E8FBE45",
            "MainActivity": "PAGE-MAINACTIVITY-9E8FBE45",
            "PAGE-CALENDARSCREEN-D064976F": "PAGE-CALENDARSCREEN-D064976F",
            "CalendarScreen": "PAGE-CALENDARSCREEN-D064976F",
            "PAGE-ABOUTSCREEN-431B1933": "PAGE-ABOUTSCREEN-431B1933",
            "AboutScreen": "PAGE-ABOUTSCREEN-431B1933",
            "PAGE-SHARESCREEN-0A0B0C0D": "PAGE-SHARESCREEN-0A0B0C0D",
            "ShareScreen": "PAGE-SHARESCREEN-0A0B0C0D",
        }
        feat_by_pid = {
            "PAGE-MAINACTIVITY-9E8FBE45": "TODO-LIST",
            "PAGE-CALENDARSCREEN-D064976F": "CALENDAR-VIEW",
            "PAGE-ABOUTSCREEN-431B1933": "SETTINGS-CORE",
            "PAGE-SHARESCREEN-0A0B0C0D": "SHARE-TODO",
        }
        gate_rows = [
            {"page_id": "PAGE-LAUNCH", "symbol": "MainActivity", "status": "VISITED"},
            {"page_id": "STEP-01-CalendarScreen", "symbol": "CalendarScreen", "status": "VISITED"},
            {"page_id": "", "symbol": "AboutScreen", "status": "NOT_ENTERED"},
            {"page_id": "STEP-02-ShareScreen", "symbol": "ShareScreen", "status": "EXITED"},
            # 标签文本不是页面符号，无法映射 -> 不产生 feature 行
            {"page_id": "TAB-x", "symbol": "待办事项", "status": "VISITED"},
        ]
        rows = self.rt.build_feature_coverage_rows(gate_rows, page_id_map, feat_by_pid)
        by_feat = {r["feature"]: r for r in rows}
        self.assertEqual(by_feat["TODO-LIST"]["status"], "VISITED")
        self.assertEqual(by_feat["TODO-LIST"]["evidence_hits"], "PAGE-LAUNCH:MainActivity")
        self.assertEqual(by_feat["CALENDAR-VIEW"]["status"], "VISITED")
        self.assertIn("STEP-01-CalendarScreen:CalendarScreen",
                      by_feat["CALENDAR-VIEW"]["evidence_hits"])
        self.assertEqual(by_feat["SETTINGS-CORE"]["status"], "NOT_ENTERED")
        self.assertEqual(by_feat["SETTINGS-CORE"]["evidence_hits"], "")
        # 仅 EXITED（无 VISITED）的 feature 记 EXITED，且不产出证据目录
        self.assertEqual(by_feat["SHARE-TODO"]["status"], "EXITED")
        self.assertEqual(by_feat["SHARE-TODO"]["evidence_hits"], "")
        self.assertNotIn("待办事项", by_feat)
        # 表头字段与 adapter 消费一致
        self.assertEqual(self.rt.FEATURE_COVERAGE_FIELDS,
                         ["feature", "status", "evidence_hits"])


if __name__ == "__main__":
    unittest.main()