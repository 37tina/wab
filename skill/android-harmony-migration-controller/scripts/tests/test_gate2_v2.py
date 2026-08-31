"""Gate 2 v2 rule tests (task #40): coverage + contracts + reconciliation + gaps.

Covers the six PASS rules of the rewritten validate_phase2_gmi with positive
and negative fixture cases (mock feature-map.json / reconciliation.csv /
data-relations.csv / closure), the always-error CONFLICT policy (#89 fix 2:
conflicts_explained no longer waives), the removal
of the strict legacy validate_phase2 path, the task-mandate approval source,
and the --refresh-freeze governance lightening command.
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import init_migration  # noqa: E402
import issue_phase2_work_order  # noqa: E402
import validate_gate  # noqa: E402


SCOPE_FEATURES = ["F-AUTH", "F-PAY"]


def write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def build_run(
    root: Path,
    *,
    run_name: str = "RUN-G2V2",
    scope_features: list[str] | None = None,
    features: list[dict] | None = None,
    bc_rows: list[dict[str, str]] | None = None,
    recon_rows: list[dict[str, str]] | None = None,
    data_rows: list[dict[str, str]] | None = None,
    closure_extra: dict | None = None,
    impact: str = "high",
    tamper_hashes: dict[str, str] | None = None,
    drop: set[str] | None = None,
) -> tuple[Path, dict]:
    """Build a minimal Gate 2 v2 workspace (A/B products mocked as fixtures)."""
    run_dir = root / run_name
    phase2 = run_dir / "phase-02-android-inventory"
    phase2.mkdir(parents=True)
    drop = drop or set()

    # A's product: feature-map.json
    if "feature-map.json" not in drop:
        mapped = features if features is not None else [
            {"feature_id": "F-AUTH"}, {"feature_id": "F-PAY"},
        ]
        (phase2 / "feature-map.json").write_text(
            json.dumps({"features": mapped}), encoding="utf-8"
        )

    # shared product: behavior-contracts.csv
    contracts = bc_rows if bc_rows is not None else [
        {
            "bc_id": "BC-AUTH-1", "feature_id": "F-AUTH", "page_ref": "PAGE-LOGIN",
            "source_refs": "LoginActivity.kt:42", "evidence_class": "RUNTIME_REQUIRED",
            "impact": impact,
        },
        {
            "bc_id": "BC-PAY-1", "feature_id": "F-PAY", "page_ref": "PAGE-PAY",
            "source_refs": "PayActivity.kt:7", "evidence_class": "RUNTIME_REQUIRED",
            "impact": impact,
        },
    ]
    write_csv(
        phase2 / "behavior-contracts.csv",
        ["bc_id", "feature_id", "page_ref", "source_refs", "evidence_class", "impact"],
        contracts,
    )

    # B's product: reconciliation.csv
    # （批次1 #81：runtime_status 列为 Gate 2 新规则判定输入——
    # INVALID_CONTRACT/UNSUPPORTED_ORACLE → error；旧 fixture 缺省为空。）
    if "reconciliation.csv" not in drop:
        reconciliation = recon_rows if recon_rows is not None else [
            {"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""},
            {"bc_id": "BC-PAY-1", "verdict": "SOURCE_CONFIRMED", "note": ""},
        ]
        write_csv(
            phase2 / "reconciliation.csv",
            ["bc_id", "verdict", "note", "runtime_status"],
            reconciliation,
        )

    # A's product: data-relations.csv
    if "data-relations.csv" not in drop:
        relations = data_rows if data_rows is not None else []
        write_csv(
            phase2 / "data-relations.csv",
            ["relation_id", "feature_id", "persistence_location", "risk"],
            relations,
        )

    # hash-chain targets referenced by the gmi closure artifact_hashes
    (phase2 / "candidates").mkdir(exist_ok=True)
    (phase2 / "candidates" / "phase-2-completeness.csv").write_text(
        "page_symbol,status,hint\n", encoding="utf-8"
    )
    (phase2 / "coverage").mkdir(exist_ok=True)
    (phase2 / "coverage" / "coverage-ledger.csv").write_text(
        "page_id,status\n", encoding="utf-8"
    )
    (phase2 / "runtime-evidence").mkdir(exist_ok=True)
    (phase2 / "runtime-evidence" / "evidence-index.csv").write_text(
        "evidence_id,page_id\n", encoding="utf-8"
    )
    (phase2 / "phase-2-report.md").write_text("# phase 2 report\n", encoding="utf-8")

    closure: dict = {
        "generator": "gmi_closure",
        "artifact_hashes": {
            "candidates_dir_sha256": validate_gate.gmi_directory_digest(
                phase2 / "candidates"
            ),
            "coverage_ledger_sha256": validate_gate.sha256_file(
                phase2 / "coverage" / "coverage-ledger.csv"
            ),
            "runtime_evidence_dir_sha256": validate_gate.gmi_directory_digest(
                phase2 / "runtime-evidence"
            ),
            "behavior_contracts_sha256": validate_gate.sha256_file(
                phase2 / "behavior-contracts.csv"
            ),
            "phase2_report_sha256": validate_gate.sha256_file(
                phase2 / "phase-2-report.md"
            ),
        },
    }
    if closure_extra:
        closure.update(closure_extra)
    if tamper_hashes:
        closure["artifact_hashes"].update(tamper_hashes)
    (phase2 / "phase-2-closure.json").write_text(
        json.dumps(closure), encoding="utf-8"
    )

    scope = {
        "run_id": run_name,
        "ownership": {},
        "migration_scope": {
            "included_features": scope_features
            if scope_features is not None
            else list(SCOPE_FEATURES)
        },
    }
    return run_dir, scope


def validate(run_dir: Path, scope: dict) -> tuple[list[str], list[str]]:
    return validate_gate.validate_phase2_gmi(run_dir, scope, None, {"scope_sha256": "a" * 64})


class GreenPathTest(unittest.TestCase):
    def test_all_six_rules_satisfied_yields_no_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(Path(tmp))
            errors, warnings = validate(run_dir, scope)
            self.assertEqual([], errors)
            self.assertTrue(warnings)


class Rule1FunctionalCoverageTest(unittest.TestCase):
    def test_scope_feature_missing_from_feature_map_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                scope_features=["F-AUTH", "F-PAY", "F-PROFILE"],
                features=[{"feature_id": "F-AUTH"}, {"feature_id": "F-PAY"}],
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("missing from feature-map.json: F-PROFILE" in item for item in errors),
                errors,
            )

    def test_full_coverage_produces_no_feature_map_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(Path(tmp))
            errors, _ = validate(run_dir, scope)
            self.assertFalse(
                any("feature-map.json" in item for item in errors), errors
            )

    def test_missing_feature_map_file_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(Path(tmp), drop={"feature-map.json"})
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("feature-map.json" in item for item in errors), errors
            )


class Rule2ContractCompletenessTest(unittest.TestCase):
    def test_feature_without_contract_row_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                bc_rows=[
                    {
                        "bc_id": "BC-AUTH-1", "feature_id": "F-AUTH",
                        "page_ref": "PAGE-LOGIN", "source_refs": "LoginActivity.kt:42",
                        "evidence_class": "RUNTIME_REQUIRED",
                    },
                ],
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("no behavior contract row: F-PAY" in item for item in errors),
                errors,
            )

    def test_every_feature_with_one_row_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(Path(tmp))
            errors, _ = validate(run_dir, scope)
            self.assertFalse(
                any("behavior contract row" in item for item in errors), errors
            )


class Rule3HighRiskReconciliationTest(unittest.TestCase):
    def test_confirmed_source_confirmed_and_reasoned_gap_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[
                    {"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""},
                    {"bc_id": "BC-PAY-1", "verdict": "GAP", "note": "emulator payment sandbox cannot reach production PSP"},
                ],
            )
            errors, _ = validate(run_dir, scope)
            self.assertEqual([], errors)

    def test_runtime_required_without_reconciliation_row_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[{"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""}],
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any(
                    "BC-PAY-1: RUNTIME_REQUIRED contract has no reconciliation row" in item
                    for item in errors
                ),
                errors,
            )

    def test_reasonless_gap_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[
                    {"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""},
                    {"bc_id": "BC-PAY-1", "verdict": "GAP", "note": "   "},
                ],
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("BC-PAY-1: reconciliation GAP lacks a reason" in item for item in errors),
                errors,
            )

    def test_unknown_status_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[
                    {"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""},
                    {"bc_id": "BC-PAY-1", "verdict": "MAYBE", "note": "x"},
                ],
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("not an accepted verdict" in item for item in errors), errors
            )

    def test_conflict_without_explanation_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[
                    {"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""},
                    {"bc_id": "BC-PAY-1", "verdict": "CONFLICT", "note": ""},
                ],
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any(
                    "BC-PAY-1: reconciliation CONFLICT is an error" in item
                    for item in errors
                ),
                errors,
            )
            self.assertTrue(
                any("重新采集" in item for item in errors),
                errors,
            )

    def test_conflict_with_explanation_is_still_an_error(self) -> None:
        """#89 修 2：conflicts_explained 有解释也不再放行（一律 error）。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[
                    {"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""},
                    {"bc_id": "BC-PAY-1", "verdict": "CONFLICT", "note": ""},
                ],
                closure_extra={
                    "conflicts_explained": [
                        {
                            "bc_id": "BC-PAY-1",
                            "explanation": "runtime shows redirect flow, source shows direct flow; PSP A/B config difference accepted",
                        }
                    ]
                },
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any(
                    "BC-PAY-1: reconciliation CONFLICT is an error" in item
                    for item in errors
                ),
                errors,
            )

    def test_conflict_explanation_without_text_still_blocks(self) -> None:
        """解释为空白同样 error（CONFLICT 分支已不再消费解释字段）。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[
                    {"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""},
                    {"bc_id": "BC-PAY-1", "verdict": "CONFLICT", "note": ""},
                ],
                closure_extra={
                    "conflicts_explained": [{"bc_id": "BC-PAY-1", "explanation": "  "}]
                },
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("reconciliation CONFLICT is an error" in item for item in errors),
                errors,
            )

    def test_no_conflict_rows_are_unaffected(self) -> None:
        """#89 修 2：无 CONFLICT（CONFIRMED/GAP 有理由）→ 不产生新 error。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[
                    {"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""},
                    {"bc_id": "BC-PAY-1", "verdict": "GAP", "note": "sandbox unreachable"},
                ],
                closure_extra={
                    "conflicts_explained": [
                        {"bc_id": "BC-OTHER-9", "explanation": "investigation note"}
                    ]
                },
            )
            errors, _ = validate(run_dir, scope)
            self.assertEqual([], errors)

    def test_missing_reconciliation_file_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(Path(tmp), drop={"reconciliation.csv"})
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("reconciliation.csv" in item for item in errors), errors
            )

    def test_legacy_status_reason_columns_still_consumed(self) -> None:
        """reconcile.py's formal columns are verdict/note; status/reason alias."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(Path(tmp), drop={"reconciliation.csv"})
            phase2 = run_dir / "phase-02-android-inventory"
            write_csv(
                phase2 / "reconciliation.csv",
                ["bc_id", "status", "reason"],
                [
                    {"bc_id": "BC-AUTH-1", "status": "CONFIRMED", "reason": ""},
                    {"bc_id": "BC-PAY-1", "status": "GAP", "reason": "blocked by sandbox"},
                ],
            )
            # the fixture hash chain already covers a reconciliation-free state;
            # rebuild is unnecessary because reconciliation.csv is not hashed.
            errors, _ = validate(run_dir, scope)
            self.assertEqual([], errors)

    def test_reconcile_exit_code_semantics_map_to_gate_verdicts(self) -> None:
        """B's blocked collections are GAP (reasoned); CHAIN_FAIL is CONFLICT."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[
                    {"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""},
                    # ANR_BLOCKED distilled to a reasoned GAP on B's side
                    {"bc_id": "BC-PAY-1", "verdict": "GAP", "note": "ANR_BLOCKED: emulator payment page blocked"},
                ],
            )
            errors, _ = validate(run_dir, scope)
            self.assertEqual([], errors)

    def test_non_runtime_required_row_is_not_reconciled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                bc_rows=[
                    {
                        "bc_id": "BC-AUTH-1", "feature_id": "F-AUTH",
                        "page_ref": "PAGE-LOGIN", "source_refs": "LoginActivity.kt:42",
                        "evidence_class": "RUNTIME_REQUIRED",
                    },
                    {
                        "bc_id": "BC-PAY-1", "feature_id": "F-PAY",
                        "page_ref": "PAGE-PAY", "source_refs": "PayActivity.kt:7",
                        "evidence_class": "SOURCE_ONLY",
                    },
                ],
                recon_rows=[{"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""}],
            )
            errors, _ = validate(run_dir, scope)
            self.assertEqual([], errors)

    # ---- 收敛式重构批次1（任务 #81）：Gate 2 对齐 --------------------------
    # RUNTIME_REQUIRED 契约的 reconciliation 出现 INVALID_CONTRACT /
    # UNSUPPORTED_ORACLE → error（不是 GAP 宽容）；PRECONDITION_FAILED 仍按
    # 有 reason 的 GAP 宽容（#83 采集环境问题，可修后重跑）。

    def test_invalid_contract_gap_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[
                    {"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""},
                    {"bc_id": "BC-PAY-1", "verdict": "GAP",
                     "note": "chain blocked (INVALID_CONTRACT)",
                     "runtime_status": "INVALID_CONTRACT"},
                ],
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any(
                    "BC-PAY-1: reconciliation INVALID_CONTRACT" in item
                    for item in errors
                ),
                errors,
            )

    def test_unsupported_oracle_gap_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[
                    {"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""},
                    {"bc_id": "BC-PAY-1", "verdict": "GAP",
                     "note": "chain blocked (UNSUPPORTED_ORACLE)",
                     "runtime_status": "UNSUPPORTED_ORACLE"},
                ],
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any(
                    "BC-PAY-1: reconciliation UNSUPPORTED_ORACLE" in item
                    for item in errors
                ),
                errors,
            )

    def test_precondition_failed_gap_stays_tolerated(self) -> None:
        """PRECONDITION_FAILED（#83）不触发新 error：有 reason 的 GAP 宽容。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[
                    {"bc_id": "BC-AUTH-1", "verdict": "CONFIRMED", "note": ""},
                    {"bc_id": "BC-PAY-1", "verdict": "GAP",
                     "note": "precondition unverified, missing on page: 中文",
                     "runtime_status": "PRECONDITION_FAILED"},
                ],
            )
            errors, _ = validate(run_dir, scope)
            self.assertEqual([], errors)


class Rule4DataUnknownsTest(unittest.TestCase):
    def test_unknown_persistence_on_high_risk_row_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                data_rows=[
                    {
                        "relation_id": "REL-1", "feature_id": "F-PAY",
                        "persistence_location": "UNKNOWN", "risk": "high",
                    },
                ],
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any(
                    "high-risk data relation has an UNKNOWN persistence location: REL-1" in item
                    for item in errors
                ),
                errors,
            )

    def test_unknown_persistence_on_high_risk_feature_via_feature_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                features=[
                    {"feature_id": "F-AUTH"},
                    {"feature_id": "F-PAY", "risk": "high"},
                ],
                data_rows=[
                    {
                        "relation_id": "REL-2", "feature_id": "F-PAY",
                        "persistence_location": "UNKNOWN", "risk": "",
                    },
                ],
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("UNKNOWN persistence location: REL-2" in item for item in errors),
                errors,
            )

    def test_unknown_persistence_on_low_risk_row_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                data_rows=[
                    {
                        "relation_id": "REL-3", "feature_id": "F-AUTH",
                        "persistence_location": "UNKNOWN", "risk": "low",
                    },
                ],
            )
            errors, _ = validate(run_dir, scope)
            self.assertEqual([], errors)

    def test_known_persistence_on_high_risk_row_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                data_rows=[
                    {
                        "relation_id": "REL-4", "feature_id": "F-PAY",
                        "persistence_location": "DataStore:session.json", "risk": "high",
                    },
                ],
            )
            errors, _ = validate(run_dir, scope)
            self.assertEqual([], errors)

    def test_missing_data_relations_file_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(Path(tmp), drop={"data-relations.csv"})
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("data-relations.csv" in item for item in errors), errors
            )


class Rule5ExplicitGapsTest(unittest.TestCase):
    def test_unexplained_gap_without_reason_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                closure_extra={"gaps": [{"feature_id": "F-PAY", "reason": ""}]},
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("closure gap for F-PAY lacks a reason" in item for item in errors),
                errors,
            )

    def test_gap_without_feature_id_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                closure_extra={"gaps": [{"reason": "something unexplained"}]},
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("closure gap lacks a feature_id" in item for item in errors),
                errors,
            )

    def test_explicit_gap_with_feature_and_reason_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                closure_extra={
                    "gaps": [
                        {
                            "feature_id": "F-PAY",
                            "reason": "PSP sandbox unreachable from emulator; contract reconciled as GAP",
                        }
                    ]
                },
            )
            errors, _ = validate(run_dir, scope)
            self.assertEqual([], errors)

    def test_absent_gaps_field_does_not_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(Path(tmp))
            errors, _ = validate(run_dir, scope)
            self.assertEqual([], errors)


class Rule6HashChainTest(unittest.TestCase):
    def test_tampered_candidates_hash_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp), tamper_hashes={"candidates_dir_sha256": "b" * 64}
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("artifact hash mismatch: candidates_dir_sha256" in item for item in errors),
                errors,
            )

    def test_tampered_behavior_contract_hash_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp), tamper_hashes={"behavior_contracts_sha256": "c" * 64}
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("artifact hash mismatch: behavior_contracts_sha256" in item for item in errors),
                errors,
            )

    def test_declared_digest_with_deleted_target_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(Path(tmp))
            (run_dir / "phase-02-android-inventory" / "phase-2-report.md").unlink()
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("artifact hash mismatch: phase2_report_sha256" in item for item in errors),
                errors,
            )

    def test_missing_or_non_gmi_closure_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(Path(tmp))
            phase2 = run_dir / "phase-02-android-inventory"
            (phase2 / "phase-2-closure.json").write_text(
                json.dumps({"generator": "other"}), encoding="utf-8"
            )
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("not a gmi closure" in item for item in errors), errors
            )

    def test_missing_artifact_hashes_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(Path(tmp), closure_extra={"artifact_hashes": {}})
            errors, _ = validate(run_dir, scope)
            self.assertTrue(
                any("artifact_hashes is missing or empty" in item for item in errors),
                errors,
            )


class LegacyStrictRemovalTest(unittest.TestCase):
    """The strict legacy path is deleted, not merely bypassed (task #40)."""

    def test_legacy_symbols_are_gone(self) -> None:
        for name in (
            "validate_phase2",
            "validate_phase2_assets",
            "verify_closure_snapshot",
            "closure_paths",
        ):
            self.assertFalse(hasattr(validate_gate, name), name)

    def test_no_visit_ratio_or_audit_or_candidate_checks_remain(self) -> None:
        # The green fixture has no runtime-gate.csv, no audit-replay.csv, no
        # candidates manifest, no asset package, no closure-report chain —
        # Gate 2 v2 must still pass it.
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(Path(tmp))
            phase2 = run_dir / "phase-02-android-inventory"
            for absent in (
                "runtime-evidence/runtime-gate.csv",
                "runtime-evidence/audit-replay.csv",
                "candidates/manifest.sha256",
                "asset-package",
                "closure-report.json",
                "closure-manifest.sha256",
                "CLOSED",
                "phase-manifest.json",
                "inventory.csv",
            ):
                self.assertFalse((phase2 / absent).exists(), absent)
            errors, _ = validate(run_dir, scope)
            self.assertEqual([], errors)

    def test_no_visit_or_audit_error_messages_remain(self) -> None:
        # The old checks are identified by the error messages they emitted;
        # none of those strict verdicts may survive anywhere in the gate.
        source = Path(validate_gate.__file__).read_text(encoding="utf-8")
        for banned in (
            "no VISITED page",
            "audit replay reports",
            "fully replay-consistent",
            "silently missing entries",
            "candidates manifest",
            "asset package entry drifted",
            "does not have the assigned Phase 2 task",
            "asset inventory contains unreferenced assets",
        ):
            self.assertNotIn(banned, source, banned)


class TaskMandateApprovalTest(unittest.TestCase):
    """issue_phase2_work_order accepts the task mandate as approval source."""

    def make_run(self, root: Path) -> Path:
        run_dir = root / "RUN-MANDATE"
        controller = run_dir / "controller"
        controller.mkdir(parents=True)
        scope = {
            "run_id": "RUN-MANDATE",
            "ownership": {"migration_controller_id": "controller-001"},
            "environments": [{"env_id": "ENV-001", "is_baseline": True}],
            "android": {"apk_sha256": "a" * 64},
            "migration_scope": {"included_features": []},
        }
        scope_path = controller / "scope.json"
        scope_path.write_text(json.dumps(scope) + "\n", encoding="utf-8")
        # batch 4 (#87): issuing the first work order advances run_status, so
        # the fixture needs the files init_migration always creates. The
        # lifecycle marker lives in controller/run-status.json (NOT in
        # run-manifest.json, which must stay immutable after the Phase 1 PASS).
        (run_dir / "run-manifest.json").write_text(
            json.dumps({"run_id": "RUN-MANDATE"}) + "\n", encoding="utf-8"
        )
        (controller / "run-status.json").write_text(
            json.dumps(
                {"run_id": "RUN-MANDATE", "run_status": "INIT", "updated_at": None, "history": []}
            )
            + "\n",
            encoding="utf-8",
        )
        (controller / "decision-log.csv").write_text(
            "decision_id,created_at,decision_type,scope,baseline_env_id,decision,"
            "rationale,decided_by,supersedes_id\n",
            encoding="utf-8",
        )
        gate_path = controller / "gate-report.json"
        gate_path.write_text(
            json.dumps(
                {
                    "run_id": "RUN-MANDATE",
                    "phase": 1,
                    "verdict": "PASS",
                    "scope_sha256": hashlib.sha256(scope_path.read_bytes()).hexdigest(),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (controller / "task-ledger.csv").write_text(
            "task_id,phase,task,owner,status,depends_on,updated_at,notes\n"
            "TASK-PHASE-01,1,scope,controller-001,PASS,,,\n"
            "TASK-PHASE-02,2,inventory,inventory-001,IN_PROGRESS,,,\n",
            encoding="utf-8",
        )
        (controller / "work-order-registry.csv").write_text(
            "work_order_id,phase,relative_path,scope_sha256,work_order_sha256,issued_at,issued_by,status\n",
            encoding="utf-8",
        )
        return run_dir

    def run_issuer(self, run_dir: Path, *extra: str) -> tuple[str, str]:
        argv = [
            "issuer", "--run-dir", str(run_dir), "--issued-by", "controller-001", *extra
        ]
        stdout, stderr = io.StringIO(), io.StringIO()

        def recheck(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess([], 0, stdout="{}", stderr="")

        with mock.patch.object(sys, "argv", argv), mock.patch.object(
            issue_phase2_work_order.subprocess, "run", side_effect=recheck
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            issue_phase2_work_order.main()
        return stdout.getvalue(), stderr.getvalue()

    def test_task_mandate_issues_without_human_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self.make_run(Path(tmp))
            stdout, _ = self.run_issuer(run_dir, "--approval-source", "task-mandate")
            result = json.loads(stdout.strip().splitlines()[0])
            work_order = json.loads(
                (run_dir / result["work_order"]).read_text(encoding="utf-8")
            )
            self.assertEqual("task-mandate", work_order["approval_source"])
            self.assertIsNone(work_order["human_review_id"])
            self.assertEqual("task-mandate", work_order["mandate_ref"])
            # batch 4 (#87): the first issued work order moves the run into
            # IN_MIGRATION, locking the skill freeze against silent refresh.
            status_record = json.loads(
                (run_dir / "controller" / "run-status.json").read_text(encoding="utf-8")
            )
            self.assertEqual("IN_MIGRATION", status_record.get("run_status"))

    def test_task_mandate_records_explicit_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self.make_run(Path(tmp))
            stdout, _ = self.run_issuer(
                run_dir, "--approval-source", "task-mandate",
                "--mandate-ref", "task-40-governance-lightening",
            )
            result = json.loads(stdout.strip().splitlines()[0])
            work_order = json.loads(
                (run_dir / result["work_order"]).read_text(encoding="utf-8")
            )
            self.assertEqual("task-40-governance-lightening", work_order["mandate_ref"])

    def test_human_source_still_requires_sealed_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self.make_run(Path(tmp))
            stderr = io.StringIO()
            argv = ["issuer", "--run-dir", str(run_dir), "--issued-by", "controller-001"]

            def recheck(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
                return subprocess.CompletedProcess([], 0, stdout="{}", stderr="")

            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                issue_phase2_work_order.subprocess, "run", side_effect=recheck
            ), contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit):
                    issue_phase2_work_order.main()
            self.assertIn("human approval", stderr.getvalue().lower())


class RefreshFreezeTest(unittest.TestCase):
    """init_migration --refresh-freeze performs the one-shot revision."""

    def make_run(self, root: Path) -> Path:
        run_dir = root / "RUN-FREEZE"
        controller = run_dir / "controller"
        controller.mkdir(parents=True)
        (controller / "decision-log.csv").write_text(
            "decision_id,created_at,decision_type,scope,baseline_env_id,decision,"
            "rationale,decided_by,supersedes_id\n",
            encoding="utf-8",
        )
        (controller / "skill-freeze-manifest.sha256").write_text(
            "0000  old\n", encoding="utf-8"
        )
        (run_dir / "run-manifest.json").write_text(
            json.dumps({"run_id": "RUN-FREEZE", "skill_freeze_manifest_sha256": "0" * 64}),
            encoding="utf-8",
        )
        return run_dir

    def test_refresh_freeze_updates_manifest_and_logs_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self.make_run(Path(tmp))
            fake_digest = "d" * 64
            with mock.patch.object(
                init_migration,
                "build_skill_freeze_manifest",
                return_value=("ffff  android-harmony-migration-controller/SKILL.md\n", fake_digest),
            ), contextlib.redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(0, init_migration.refresh_skill_freeze(
                    run_dir, "skill scripts revised by task #40", "agent-c"
                ))
            manifest = json.loads(
                (run_dir / "run-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(fake_digest, manifest["skill_freeze_manifest_sha256"])
            self.assertIn(
                fake_digest, captured.getvalue()
            )  # Gate recheck hint context printed
            with (run_dir / "controller" / "decision-log.csv").open(
                r"r", encoding="utf-8", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(1, len(rows))
            self.assertEqual("SKILL_FREEZE_REFRESH", rows[0]["decision_type"])
            self.assertEqual("RUN-FREEZE", rows[0]["scope"])
            self.assertEqual("REFRESHED", rows[0]["decision"])
            self.assertEqual("skill scripts revised by task #40", rows[0]["rationale"])
            self.assertEqual("agent-c", rows[0]["decided_by"])
            self.assertEqual(
                "ffff  android-harmony-migration-controller/SKILL.md\n",
                (run_dir / "controller" / "skill-freeze-manifest.sha256").read_text(
                    encoding="utf-8"
                ),
            )
            # the freeze file stays sealed read-only
            self.assertFalse(
                (run_dir / "controller" / "skill-freeze-manifest.sha256").stat().st_mode & 0o222
            )

    def test_refresh_freeze_rejects_non_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                init_migration.refresh_skill_freeze(Path(tmp) / "nope", "", "agent-c")


if __name__ == "__main__":
    unittest.main()
    def test_high_impact_gap_with_reason_warns_but_passes(self) -> None:
        """提交前自检 3-A：high-impact GAP 带 reason 放行（方案允许）但进 warnings。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[
                    {"bc_id": "BC-AUTH-1", "verdict": "GAP",
                     "note": "采集器工具问题，无法稳定输入"},
                ],
            )
            errors, warnings = validate(run_dir, scope)
            self.assertFalse(
                any("BC-AUTH-1" in item for item in errors), errors)
            self.assertTrue(
                any(
                    "BC-AUTH-1: high-impact RUNTIME contract resolved as GAP"
                    in item for item in warnings
                ),
                warnings,
            )

    def test_normal_impact_gap_with_reason_no_warning(self) -> None:
        """normal impact 的 GAP 不触发 high 可见性 warning（最小噪音）。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, scope = build_run(
                Path(tmp),
                recon_rows=[
                    {"bc_id": "BC-AUTH-1", "verdict": "GAP", "note": "x"},
                ],
                impact="normal",
            )
            errors, warnings = validate(run_dir, scope)
            self.assertFalse(any("high-impact" in w for w in warnings), warnings)
