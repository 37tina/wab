"""Minimal fail-open hardening cases for validate_gate.

Covers exactly two hardening cases:
1. D-5 (Gate 2 v2 form, task #40): a RUNTIME_REQUIRED behavior contract with
   no reconciliation row must produce an error, not a warning.
2. D-7 (main fallback, v4 form — task #59): a --phase 4 report whose facts
   lack the runtime_bc_pass_rate key (v4 取代已退役的 intent_pass_rate，
   同单位 BC 通过率) must surface None with an explicit note instead of
   a historical 1.0 default. The fixture reaches that state through the
   skill-freeze fail-closed path (run manifest declares a freeze digest but
   the manifest file is missing).
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import validate_gate  # noqa: E402


class RuntimeRequiredHardeningTest(unittest.TestCase):
    """Fix 1 (D-5, Gate 2 v2): RUNTIME_REQUIRED without reconciliation errors."""

    def test_runtime_required_without_reconciliation_row_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "RUN-D5"
            phase2 = run_dir / "phase-02-android-inventory"
            phase2.mkdir(parents=True)
            (phase2 / "phase-2-closure.json").write_text(
                json.dumps({"generator": "gmi_closure"}), encoding="utf-8"
            )
            # Minimal closure/manifest objects; unrelated checks will add their
            # own errors, which does not matter for this assertion.
            (phase2 / "closure-report.json").write_text("{}", encoding="utf-8")
            (phase2 / "phase-manifest.json").write_text("{}", encoding="utf-8")
            (phase2 / "behavior-contracts.csv").write_text(
                "bc_id,feature_id,page_id,page_ref,source_refs,evidence_class,impact\n"
                "BC-001,F-1,PAGE-XYZ,PAGE-XYZ,Foo.kt:10,RUNTIME_REQUIRED,high\n",
                encoding="utf-8",
            )
            # Reconciliation covers a different contract: BC-001 stays
            # unreconciled and must fail closed.
            (phase2 / "reconciliation.csv").write_text(
                "bc_id,status,reason\nBC-OTHER,CONFIRMED,\n",
                encoding="utf-8",
            )
            scope = {
                "run_id": "RUN-D5",
                "ownership": {},
                "migration_scope": {"included_features": ["F-1"]},
            }
            errors, warnings = validate_gate.validate_phase2_gmi(
                run_dir, scope, None, {"scope_sha256": "a" * 64}
            )
            self.assertTrue(
                any(
                    "RUNTIME_REQUIRED contract has no reconciliation row" in item
                    for item in errors
                ),
                errors,
            )
            self.assertFalse(
                any("RUNTIME_REQUIRED" in item for item in warnings),
                warnings,
            )


class IntentPassRateFallbackTest(unittest.TestCase):
    """Fix 2 (D-7, v4 form): phase-4 reports never surface a default 1.0 BC rate."""

    def test_phase4_missing_facts_report_none_instead_of_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "RUN-D7"
            (run_dir / "controller").mkdir(parents=True)
            (run_dir / "run-manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": "RUN-D7",
                        "skill_freeze_manifest_sha256": "f" * 64,
                    }
                ),
                encoding="utf-8",
            )
            # No controller/skill-freeze-manifest.sha256: the declared freeze
            # digest is missing, so main() must fail closed with empty facts.
            argv = [
                "validate_gate.py",
                "--run-dir",
                str(run_dir),
                "--phase",
                "4",
            ]
            buffer = io.StringIO()
            old_argv = sys.argv
            sys.argv = argv
            try:
                with contextlib.redirect_stdout(buffer):
                    exit_code = validate_gate.main()
            finally:
                sys.argv = old_argv
            report = json.loads(buffer.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertEqual(report["verdict"], "FAIL")
            # v4（任务 #59）：intent_pass_rate 已退役，报告面承载同单位 BC
            # 通过率的键是 runtime_bc_pass_rate——facts 缺失时必须显式 None
            # + 说明性 note，绝不回退默认 1.0。
            self.assertNotIn("intent_pass_rate", report)
            self.assertIsNone(report["runtime_bc_pass_rate"])
            self.assertIn(
                "runtime_bc_pass_rate unavailable", report["runtime_bc_pass_rate_note"]
            )
            self.assertTrue(
                any(
                    "run manifest declares a skill freeze manifest but it is missing"
                    in item
                    for item in report["errors"]
                ),
                report["errors"],
            )


if __name__ == "__main__":
    unittest.main()