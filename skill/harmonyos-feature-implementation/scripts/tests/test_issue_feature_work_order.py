"""issue_feature_work_order.py 单测（收敛式重构批次 2 #85）。

Feature 工单是 Phase 4 唯一实施路径（旧 stub 报错逻辑已反转）：
签发 → must_read 段聚合 → semantic_probe expected hash 绑定 →
implementation-ledger owner 校验与回写 → registry 登记 → 幂等阻断。
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import issue_feature_work_order as fwo  # noqa: E402

FEATURE_ID = "FEATURE-HOME"
BUNDLE_LEAD = "impl-lead-x"


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def build_workspace(root: Path) -> Path:
    workspace = root / "phase-04-harmony-implementation"
    upstream = workspace / "inputs/upstream"
    upstream.mkdir(parents=True, exist_ok=True)

    (workspace / "feature-dispatch.json").write_text(json.dumps({
        "schema_version": 1,
        "work_order_id": "WO-P4-TEST",
        "shared_data_relation_ids": ["REL-SHARED"],
        "dispatch": [{
            "feature_id": FEATURE_ID,
            "verify_mode": "RUNTIME",
            "risk_level": "high",
            "work_order_id": "",
            "owner_id": "",
            "bc_ids": ["BC-HOME-LOAD"],
            "runtime_bc_ids": ["BC-HOME-LOAD"],
            "data_reads": [],
            "data_writes": ["mmkv:home_seed"],
            "data_relation_ids": ["REL-HOME-1"],
            "surfaces": [{"id": "PAGE-HOME", "kind": "page"}],
            "harmony_steps": [],
            "status": "NOT_STARTED",
        }],
    }), encoding="utf-8")

    (workspace / "stage-04-input-lock.json").write_text(
        json.dumps({"work_order_id": "WO-P4-TEST"}), encoding="utf-8")

    _write_csv(
        upstream / "06-phase2_behavior_contracts.csv",
        ["bc_id", "feature_id", "source_refs"],
        [["BC-HOME-LOAD", FEATURE_ID,
          "feature/home/HomeScreen.kt;feature/home/SortMenu.kt:15"]])
    _write_csv(
        upstream / "09-phase2_runtime_chains.csv",
        ["bc_id", "feature_id", "chain_status", "evidence_dir"],
        [["BC-HOME-LOAD", FEATURE_ID, "PASS",
          "evidence/chains/BC-HOME-LOAD"]])
    (upstream / "05-phase2_feature_map.json").write_text(json.dumps({
        "features": [{"feature_id": FEATURE_ID, "verify_mode": "RUNTIME"}],
    }), encoding="utf-8")
    _write_csv(
        upstream / "18-phase3_surface_registry.csv",
        ["surface_shell_id", "page_id", "feature_ids"],
        [["ShellPageHome", "PAGE-HOME", FEATURE_ID]])

    # 探针本体（expected hash 绑定对象）
    probe = (workspace / "harmony-project"
             / "entry/src/main/ets/probe/DebugSemanticProbe.ets")
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text("// frozen probe body\n", encoding="utf-8")

    # implementation-ledger（owner 必须先填，fail-closed）
    _write_csv(
        workspace / "implementation-ledger.csv",
        ["feature_id", "work_order_id", "feature_owner_id", "ui_agent_id",
         "business_data_agent_id", "native_capability_agent_id", "status"],
        [[FEATURE_ID, "", "owner-1", "ui-1", "data-1", "cap-1",
          "NOT_STARTED"]])
    return workspace


class IssueFeatureWorkOrderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fwo-")
        self.workspace = build_workspace(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def _run_cli(self, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "issue_feature_work_order.py"),
             "--workspace", str(self.workspace),
             "--issued-by", BUNDLE_LEAD, *extra],
            capture_output=True, text=True)

    def test_issue_single_feature_order(self):
        proc = self._run_cli("--feature-id", FEATURE_ID)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        issued = report["issued"][0]
        counts = issued["must_read_counts"]
        # 六段 must_read 全部聚合
        self.assertEqual(counts["behavior_contract_ids"], 1)
        self.assertEqual(counts["android_source_refs"], 2)
        self.assertEqual(counts["runtime_evidence_refs"], 1)
        self.assertEqual(counts["data_relations"], 2)  # feature 1 + shared 1
        self.assertEqual(counts["visual_memory_surface"], 1)
        self.assertEqual(counts["p3_surface_plan"], 1)
        self.assertTrue(issued["semantic_probe_bound"])

        # 工单本体：probe expected hash = 探针文件真实哈希
        order_path = (self.workspace
                      / "feature-work-orders"
                      / f"{issued['work_order_id']}.json")
        order = json.loads(order_path.read_text(encoding="utf-8"))
        import hashlib
        expected = hashlib.sha256(
            (self.workspace / "harmony-project"
             / "entry/src/main/ets/probe/DebugSemanticProbe.ets")
            .read_bytes()).hexdigest()
        self.assertEqual(order["semantic_probe"]["expected_sha256"],
                         expected)
        self.assertTrue(order["semantic_probe"]["immutable"])
        self.assertEqual(order["ownership"]["feature_owner_id"], "owner-1")
        # consumed_* 回执契约（Gate 4 消费面）
        self.assertIn("consumed_source_refs",
                      order["read_receipt_contract"])

        # registry 登记 + ledger 回写
        with (self.workspace / "feature-work-order-registry.csv").open(
                encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["feature_id"], FEATURE_ID)
        with (self.workspace / "implementation-ledger.csv").open(
                encoding="utf-8") as stream:
            ledger = list(csv.DictReader(stream))
        self.assertEqual(ledger[0]["work_order_id"],
                         issued["work_order_id"])
        self.assertEqual(ledger[0]["status"], "IN_PROGRESS")

    def test_reissue_blocked_until_superseded(self):
        first = self._run_cli("--feature-id", FEATURE_ID)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self._run_cli("--feature-id", FEATURE_ID)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("already active", second.stderr)

    def test_missing_ledger_owner_fails_closed(self):
        # owner 列空 → fail-closed（不发明默认 actor）
        ledger = self.workspace / "implementation-ledger.csv"
        _write_csv(
            ledger,
            ["feature_id", "work_order_id", "feature_owner_id",
             "ui_agent_id", "business_data_agent_id",
             "native_capability_agent_id", "status"],
            [[FEATURE_ID, "", "", "", "", "", "NOT_STARTED"]])
        proc = self._run_cli("--feature-id", FEATURE_ID)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("feature_owner_id", proc.stderr)

    def test_old_stub_error_message_retired(self):
        # 旧 stub 的拒绝报错与 parser.error 路径已删除（docstring 的历史
        # 说明不算残留路径）
        source = (SCRIPTS / "issue_feature_work_order.py").read_text(
            encoding="utf-8")
        body = source.split('"""', 2)[2]  # docstring 之后的部分
        self.assertNotIn("obsolete", body)
        self.assertNotIn("Reject obsolete", source)


if __name__ == "__main__":
    unittest.main()