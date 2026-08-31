"""TOOL_GAP run-freeze semantics for batch 4 (#87).

Covers the run lifecycle status machine end to end:
- CLI positive/negative cases: --refresh-freeze allowed on INIT and CLOSED,
  refused with the TOOL_GAP remedy while IN_MIGRATION;
- the full status chain INIT -> IN_MIGRATION (work-order issuance point)
  -> CLOSED (Gate 4 PASS point via maybe_close_run_after_gate4);
- historical-run inference for manifests created before run_status existed;
- the freeze drift error text now carries the TOOL_GAP remedy.
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

from _run_status import (  # noqa: E402

    TOOL_GAP_REMEDY,
    assert_refresh_freeze_allowed,
    read_run_status,
    transition_run_status,
)
from validate_gate import maybe_close_run_after_gate4, verify_skill_freeze  # noqa: E402


def sha256_of(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


class RunStatusFixture:
    """Minimal run directory: run-manifest + run-status + freeze manifest + log.

    run_status deliberately lives in controller/run-status.json — NOT in
    run-manifest.json — because android-migration-inventory fail-closes any
    run whose run-manifest hash drifts after the Phase 1 PASS.
    """

    @staticmethod
    def build(root: Path, run_id: str = "TEST-RUN") -> Path:
        run_dir = root / run_id
        controller = run_dir / "controller"
        controller.mkdir(parents=True)
        (run_dir / "run-manifest.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "project_id": "TEST",
                    "project_root": str(root),
                    "created_at": "2026-08-31T00:00:00Z",
                    "controller_skill": "android-harmony-migration-controller",
                    "status": "IN_PROGRESS",
                    "skill_freeze_manifest_sha256": "0" * 64,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (controller / "run-status.json").write_text(
            json.dumps(
                {"run_id": run_id, "run_status": "INIT", "updated_at": "2026-08-31T00:00:00Z", "history": []},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (controller / "skill-freeze-manifest.sha256").write_text("", encoding="utf-8")
        (controller / "decision-log.csv").write_text(
            "decision_id,created_at,decision_type,scope,baseline_env_id,decision,"
            "rationale,decided_by,supersedes_id\n",
            encoding="utf-8",
        )
        return run_dir


class ReadRunStatusTest(unittest.TestCase):
    def test_declared_status_is_returned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = RunStatusFixture.build(Path(tmp))
            status_path = run_dir / "controller" / "run-status.json"
            for value in ("INIT", "IN_MIGRATION", "CLOSED"):
                record = json.loads(status_path.read_text(encoding="utf-8"))
                record["run_status"] = value
                status_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
                self.assertEqual(read_run_status(run_dir), value)

    def test_historical_run_inference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = RunStatusFixture.build(root)
            (run_dir / "controller" / "run-status.json").unlink()
            # no work order, no gate -> INIT
            self.assertEqual(read_run_status(run_dir), "INIT")
            # issued work order -> IN_MIGRATION
            orders = run_dir / "controller" / "work-orders"
            orders.mkdir()
            (orders / "WO-PHASE-02-ABC123DEF456.json").write_text("{}", encoding="utf-8")
            self.assertEqual(read_run_status(run_dir), "IN_MIGRATION")
            # Gate 4 PASS outranks the work orders -> CLOSED
            (run_dir / "controller" / "gate-report.json").write_text(
                json.dumps({"phase": 4, "verdict": "PASS"}), encoding="utf-8"
            )
            self.assertEqual(read_run_status(run_dir), "CLOSED")

    def test_run_manifest_stays_untouched_by_transitions(self) -> None:
        """run-manifest.json is immutable after Phase 1 (inventory contract)."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = RunStatusFixture.build(Path(tmp))
            manifest_path = run_dir / "run-manifest.json"
            before = manifest_path.read_bytes()
            transition_run_status(run_dir, "IN_MIGRATION")
            maybe_close_run_after_gate4(run_dir, 4, "PASS", True, {})
            self.assertEqual(manifest_path.read_bytes(), before)


class TransitionTest(unittest.TestCase):
    def test_full_chain_and_illegal_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = RunStatusFixture.build(Path(tmp))
            self.assertEqual(read_run_status(run_dir), "INIT")
            # INIT -> IN_MIGRATION (work-order issuance point)
            transition_run_status(
                run_dir, "IN_MIGRATION",
                decision_type="RUN_STATUS_TRANSITION",
                rationale="first specialist work order issued",
            )
            self.assertEqual(read_run_status(run_dir), "IN_MIGRATION")
            # backward transition refused
            with self.assertRaises(ValueError):
                transition_run_status(run_dir, "INIT")
            # IN_MIGRATION -> CLOSED (Gate 4 PASS point)
            maybe_close_run_after_gate4(
                run_dir, 4, "PASS", True, {"ownership": {"migration_controller_id": "c1"}}
            )
            self.assertEqual(read_run_status(run_dir), "CLOSED")
            # CLOSED is terminal
            with self.assertRaises(ValueError):
                transition_run_status(run_dir, "IN_MIGRATION")
            # decision log recorded the two transitions
            log = (run_dir / "controller" / "decision-log.csv").read_text(encoding="utf-8")
            self.assertEqual(log.count("RUN_STATUS_TRANSITION"), 2)
            self.assertIn("RUN_STATUS_IN_MIGRATION", log)
            self.assertIn("CLOSED", log)
            self.assertIn("Gate 4 machine PASS", log)

    def test_gate4_close_point_requires_pass_and_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for phase, verdict, wrote, expected in (
                (4, "PASS", True, "CLOSED"),
                (4, "FAIL", True, "IN_MIGRATION"),
                (3, "PASS", True, "IN_MIGRATION"),
                (4, "PASS", False, "IN_MIGRATION"),
            ):
                with self.subTest(phase=phase, verdict=verdict, wrote=wrote):
                    run_dir = RunStatusFixture.build(Path(tmp), f"RUN-{phase}-{verdict}-{wrote}")
                    transition_run_status(run_dir, "IN_MIGRATION")
                    maybe_close_run_after_gate4(run_dir, phase, verdict, wrote, {})
                    self.assertEqual(read_run_status(run_dir), expected)

    def test_reentrant_close_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = RunStatusFixture.build(Path(tmp))
            transition_run_status(run_dir, "IN_MIGRATION")
            maybe_close_run_after_gate4(run_dir, 4, "PASS", True, {})
            maybe_close_run_after_gate4(run_dir, 4, "PASS", True, {})
            self.assertEqual(read_run_status(run_dir), "CLOSED")


class RefreshFreezeGateTest(unittest.TestCase):
    def test_assert_refresh_allowed_by_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = RunStatusFixture.build(root)
            self.assertEqual(assert_refresh_freeze_allowed(run_dir), "INIT")
            transition_run_status(run_dir, "IN_MIGRATION")
            with self.assertRaises(ValueError) as ctx:
                assert_refresh_freeze_allowed(run_dir)
            self.assertIn("TOOL_GAP", str(ctx.exception))
            transition_run_status(run_dir, "CLOSED")
            self.assertEqual(assert_refresh_freeze_allowed(run_dir), "CLOSED")


class RefreshFreezeCliTest(unittest.TestCase):
    """Real CLI: --refresh-freeze accepted on INIT/CLOSED, refused on IN_MIGRATION."""

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "init_migration.py"), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_positive_and_negative_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "project").mkdir()
            created = self.run_cli(
                "--output", str(root / "runs"),
                "--project-root", str(root / "project"),
                "--project-name", "Demo",
                "--run-id", "TOOLGAP-RUN",
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            run_dir = root / "runs" / "TOOLGAP-RUN"
            status_record = json.loads(
                (run_dir / "controller" / "run-status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status_record.get("run_status"), "INIT")
            # run-manifest stays free of lifecycle fields (inventory immutability)
            manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
            self.assertNotIn("run_status", manifest)

            # INIT: refresh allowed
            ok = self.run_cli("--refresh-freeze", str(run_dir))
            self.assertEqual(ok.returncode, 0, ok.stderr)

            # IN_MIGRATION: refresh refused with the TOOL_GAP remedy
            sys.path.insert(0, str(SCRIPTS))
            transition_run_status(run_dir, "IN_MIGRATION")
            refused = self.run_cli("--refresh-freeze", str(run_dir))
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("TOOL_GAP", refused.stderr)
            self.assertIn("refresh-freeze", refused.stderr)

            # close-run requires --note; with --note it closes the run
            missing_note = self.run_cli("--close-run", str(run_dir))
            self.assertNotEqual(missing_note.returncode, 0)
            closed = self.run_cli(
                "--close-run", str(run_dir),
                "--note", "batch 4 test disposal",
            )
            self.assertEqual(closed.returncode, 0, closed.stderr)
            self.assertEqual(read_run_status(run_dir), "CLOSED")

            # CLOSED: refresh allowed again
            ok2 = self.run_cli("--refresh-freeze", str(run_dir))
            self.assertEqual(ok2.returncode, 0, ok2.stderr)


class FreezeDriftTextTest(unittest.TestCase):
    """verify_skill_freeze drift errors must carry the TOOL_GAP remedy."""

    def test_drifted_file_reports_toolgap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills" / "android-harmony-migration-controller"
            (skill / "scripts").mkdir(parents=True)
            target = skill / "scripts" / "validate_gate.py"
            target.write_text("print('frozen')\n", encoding="utf-8")
            run_dir = root / "RUN"
            (run_dir / "controller").mkdir(parents=True)
            (run_dir / "controller" / "skill-freeze-manifest.sha256").write_text(
                f"{sha256_of(target)}  android-harmony-migration-controller/scripts/validate_gate.py\n",
                encoding="utf-8",
            )
            target.write_text("print('tampered')\n", encoding="utf-8")
            errors = verify_skill_freeze(run_dir, skills_root=root / "skills")
            self.assertTrue(errors)
            self.assertTrue(any("TOOL_GAP" in item for item in errors))
            self.assertTrue(any("skill-bug-ledger" in item for item in errors))


if __name__ == "__main__":
    unittest.main()