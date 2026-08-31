#!/usr/bin/env python3
"""Governed Phase 4 gate under the stage4-v4 paradigm (single path).

v4 blueprint (Gate 4 new rules, user corrections 3+4):

* functional consistency   -> judged strictly by machine
* data/state consistency   -> judged strictly by machine
* side-effect consistency  -> judged strictly by machine
* UI                       -> high visual-identity / information-structure
                             fidelity to the Android source; only
                             platform-standard interactions may be natively
                             re-expressed (structure comparison, no pixel
                             parity gate)
* platform-inherent gaps   -> PLATFORM_DEVIATION queue with human adjudication

The five machine rules evaluated here are:

1. ``runtime_assertions``   every verify_mode=RUNTIME feature's behavior
   contracts must have all four assertion classes (observable / data /
   persistence / side_effect) PASS in ``replay-results.csv``.  A FAIL on a
   behavioral assertion can never be flipped by any explanation.
2. ``data_parity``          semantic data-object read/write sets must be
   equivalent on both sides (Android side from the frozen Phase 2
   feature-map/reconciliation, Harmony side recomputed from the
   implementation declarations + Phase 3 data-contract references).
   Semantic equivalence only; physical carriers are never compared.
3. ``platform_deviations``  replay rows flagged PLATFORM_LIMITATION enter the
   PLATFORM_DEVIATION queue and require an explicit human ACCEPTED decision
   in ``decision-log.csv``.  ACCEPTED deviations accompany (never flip) the
   behavioral verdict; FAIL assertions stay FAIL regardless.
4. ``source_confirm_floor`` every verify_mode=SOURCE_CONFIRM feature must
   clear four floors: implementation present (non-empty shell), no no-op /
   placeholder stub (static ArkTS scan), source relation traceable
   (surface-contract or implementation record cites feature->source), and
   buildable (smoke build PASS via the final HBUILD chain).
5. ``h4env_chain``         the frozen H4ENV environment chain stays intact
   and exactly one PASS HBUILD exists per required environment; pixel
   capture categories remain optional.
6. ``visual_fidelity``     "UI may differ but not too much": the
   denominator is **every user-visible surface** in the frozen Phase 2
   feature map — surfaces whose ``kind`` is page / sheet / dialog,
   regardless of verify_mode (RUNTIME *or* SOURCE_CONFIRM).  Each such
   surface must have a PASS row in ``visual-fidelity.csv`` (structure
   comparison against the frozen Phase 2 visual-memory baseline) —
   text overlap >= 0.6, tree depth delta <= 2, all key interactive
   elements present.  A missing row or a VISUAL_GAP / NO_DUMP row on
   any visible surface fails the gate.  The rule is conditionally
   activated: without a Phase 2 ``visual-memory.json`` baseline it
   stays dormant (PASS with ``activated=false``); NO_BASELINE rows are
   Phase 2 responsibility and only counted, never failing the
   implementation side.

Additionally the surface-contract thin table must be fully PASS and the
closure / input-lock hash chains keep their tamper-proof semantics.

This file is the v4 single path: the legacy page-acceptance, migration-unit
triples, 32-input-face, six-dimension verdict, HREV self-report and
advanced-obligations machinery was removed (test migration is owned by the
stage4 test chain, see the work-order ledger).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from _common import (
    atomic_json,
    atomic_text,
    load_json,
    make_tree_read_only,
    read_csv,
    safe_relative_path,
    sha256_file,
    split_multi,
    utc_now,
    validate_actor,
    validate_id,
)
from _stage4_audit import closure_manifest_text, validate_hbuild


PHASE_NAME = "phase-04-harmony-implementation"
RUN_PHASE2 = "phase-02-android-inventory"
RUN_PHASE3 = "phase-03-harmony-scaffold"

# Workspace artifacts required by the v4 gate (thin set; the 32-input-face
# layout was retired together with the strict-only legacy records).
REQUIRED_WORKSPACE_ARTIFACTS = (
    "stage-04-input-lock.json",
    "phase-manifest.json",
    "replay-results.csv",
    "surface-contract.csv",
    "implementation-declarations.csv",
    "environments/h4env-registry.csv",
    "harmony-project",
    "builds",
    "stage-04-gate-report.json",
    "stage-04-closure-manifest.sha256",
    "CLOSED",
)
OPTIONAL_WORKSPACE_ARTIFACTS = (
    "decision-log.csv",
    "attempt-ledger.csv",
    "rework-tickets.csv",
    "rework-orders.csv",
    "dual-diff-results.csv",
)

# Frozen upstream denominators the gate recomputes from (never trusting the
# stage-04 self description).
FROZEN_FEATURE_MAP = f"{RUN_PHASE2}/feature-map.json"
FROZEN_BEHAVIOR_CONTRACTS = f"{RUN_PHASE2}/behavior-contracts.csv"
FROZEN_DATA_RELATIONS = f"{RUN_PHASE2}/data-relations.csv"
FROZEN_RECONCILIATION = f"{RUN_PHASE2}/reconciliation.csv"
FROZEN_STAGE3_INPUT_LOCK = f"{RUN_PHASE3}/stage-03-input-lock.json"

# H's replayer thin table (contract: bc_id/feature_id/assertion_type/
# assertion_status/evidence_ref).  Consumed defensively; schema divergences
# are arbitrated by the controller acceptance (#60).
REPLAY_ASSERTION_TYPES = ("observable", "data", "persistence", "side_effect")
REPLAY_STATUS_PASS = "PASS"
REPLAY_STATUS_FAIL = "FAIL"
REPLAY_STATUS_MANUAL = "MANUAL_VERIFY_REQUIRED"
REPLAY_STATUS_PLATFORM = "PLATFORM_LIMITATION"
REPLAY_ALLOWED_STATUSES = (
    REPLAY_STATUS_PASS, REPLAY_STATUS_FAIL, REPLAY_STATUS_MANUAL, REPLAY_STATUS_PLATFORM,
)
DECISION_ACCEPTED = "ACCEPTED"
DECISION_REJECTED = "REJECTED"

# Dual-machine differential results (batch 5 #91/#93): dual_verify.py's thin
# table.  Schema deliberately mirrors replay-results.csv (bc_id/feature_id/
# assertion_type) but carries its own verdict enum (MATCH/DIFF/MANUAL) and
# both-side observation columns, so it is consumed as an OPTIONAL, additional
# assertion source -- never as a replay-results.csv drop-in (the status
# columns differ).  Absent file keeps the rule dormant (PASS, activated=
# false, same pattern as visual_fidelity); any DIFF fails the gate.
DUAL_RESULTS_CSV = "dual-diff-results.csv"
DUAL_VERDICT_MATCH = "MATCH"
DUAL_VERDICT_DIFF = "DIFF"
DUAL_VERDICT_MANUAL = "MANUAL"
DUAL_ALLOWED_VERDICTS = (
    DUAL_VERDICT_MATCH, DUAL_VERDICT_DIFF, DUAL_VERDICT_MANUAL,
)
DUAL_REQUIRED_COLUMNS = ("bc_id", "feature_id", "assertion_type", "verdict")

# H's surface-contract thin table (feature_id/surfaces/entry_reachable/
# nav_pattern/native_impl_check/notes).
SURFACE_ENTRY_YES = "yes"
SURFACE_NATIVE_PASS = "PASS"

# Static ArkTS stub detection for the SOURCE_CONFIRM floor (rule 4b).
ARKTS_SUFFIX = ".ets"
STUB_TODO_RE = re.compile(r"^\s*(?://|/?\*|\*)\s*(TODO|FIXME)\b", re.IGNORECASE)
STUB_TOKEN_RE = re.compile(
    r"__(?:FILL|AUTO)(?:_[A-Z0-9_]+)?__"
    r"|\b(?:TBD|MOCK_ONLY|STUB_ONLY|FAKE_DATA|PLACEHOLDER)\b"
    r"|\bnot[ _-]?implemented\b|\bNotImplementedError\b",
    re.IGNORECASE,
)
STUB_RETURN_RE = re.compile(
    r"\)\s*(?::[^{\n]*)?\{\s*(?://[^\n]*\n\s*)?return\s+(?:null|undefined)\s*;?\s*\}",
)
STUB_EMPTY_BODY_RE = re.compile(r"\)\s*(?::[^{\n]*)?\{\s*\}")
STUB_COMMENT_ONLY_RE = re.compile(r"\)\s*(?::[^{\n]*)?\{\s*(?://[^\n]*\n\s*|\*[^\n]*\n\s*)*\}")

ROLE_KEYS = (
    "implementation_lead_id",
    "verification_executor_id",
    "parity_acceptance_agent_id",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def object_json(path: Path, label: str) -> dict[str, Any]:
    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def rows_optional(path: Path) -> list[dict[str, str]]:
    """Defensively read a CSV that the v4 chain may or may not produce."""
    if not path.is_file():
        return []
    return read_csv(path)


def split_semantic_list(value: str) -> list[str]:
    """Split a ';'-separated semantic list, dropping empties and duplicates."""
    items: list[str] = []
    for item in split_multi(value):
        token = item.strip()
        if token and token not in items:
            items.append(token)
    return items


# ---------------------------------------------------------------------------
# Frozen denominator loading (Phase 2 / Phase 3 originals, not snapshots)
# ---------------------------------------------------------------------------


def load_frozen_denominators(run_dir: Path) -> dict[str, Any]:
    """Load the frozen Phase 2/3 denominators the gate recomputes against."""
    feature_map_path = run_dir / FROZEN_FEATURE_MAP
    require(feature_map_path.is_file(), f"Phase 2 feature map is missing: {feature_map_path}")
    feature_map = object_json(feature_map_path, "Phase 2 feature map")
    features_raw = feature_map.get("features")
    require(isinstance(features_raw, list), "Phase 2 feature map lacks the features array")
    features: dict[str, dict[str, Any]] = {}
    for entry in features_raw:
        if not isinstance(entry, dict):
            raise ValueError("Phase 2 feature map contains a non-object feature")
        feature_id = str(entry.get("feature_id", ""))
        require(bool(feature_id) and feature_id not in features,
                f"Phase 2 feature map has an invalid or duplicate feature: {feature_id!r}")
        features[feature_id] = entry

    behavior_rows = read_csv(run_dir / FROZEN_BEHAVIOR_CONTRACTS)
    behavior_by_feature: dict[str, list[dict[str, str]]] = {}
    seen_bc: set[str] = set()
    for row in behavior_rows:
        bc_id = str(row.get("bc_id", ""))
        require(bool(bc_id) and bc_id not in seen_bc,
                f"Phase 2 behavior contracts have an invalid or duplicate BC: {bc_id!r}")
        seen_bc.add(bc_id)
        behavior_by_feature.setdefault(str(row.get("feature_id", "")), []).append(row)

    data_relations = read_csv(run_dir / FROZEN_DATA_RELATIONS)
    reconciliation = rows_optional(run_dir / FROZEN_RECONCILIATION)

    stage3_lock_path = run_dir / FROZEN_STAGE3_INPUT_LOCK
    require(stage3_lock_path.is_file(),
            f"Phase 3 input lock is missing: {stage3_lock_path}")
    stage3_lock = object_json(stage3_lock_path, "Phase 3 input lock")
    contracts_raw = stage3_lock.get("data_contracts")
    if not isinstance(contracts_raw, list):
        contracts_raw = []
    data_contracts = [item for item in contracts_raw if isinstance(item, dict)]

    return {
        "features": features,
        "behavior_by_feature": behavior_by_feature,
        "behavior_count": len(seen_bc),
        "data_relations": data_relations,
        "reconciliation": reconciliation,
        "data_contracts": data_contracts,
    }


def runtime_feature_ids(features: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(
        feature_id for feature_id, entry in features.items()
        if str(entry.get("verify_mode", "")).upper() == "RUNTIME"
    )


def source_confirm_feature_ids(features: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(
        feature_id for feature_id, entry in features.items()
        if str(entry.get("verify_mode", "")).upper() == "SOURCE_CONFIRM"
    )


def feature_data_objects(entry: dict[str, Any]) -> tuple[set[str], set[str]]:
    raw = entry.get("data_objects") if isinstance(entry.get("data_objects"), dict) else {}
    reads = {str(item) for item in raw.get("reads", []) if str(item)}
    writes = {str(item) for item in raw.get("writes", []) if str(item)}
    return reads, writes


# ---------------------------------------------------------------------------
# Rule 1 + Rule 3: runtime assertions with the PLATFORM_DEVIATION mechanism
# ---------------------------------------------------------------------------


def load_replay_results(workspace: Path, errors: list[str]) -> list[dict[str, str]]:
    """Defensively parse H's replay-results.csv thin table."""
    rows = read_csv(workspace / "replay-results.csv")
    for index, row in enumerate(rows):
        bc_id = str(row.get("bc_id", "")).strip()
        assertion_type = str(row.get("assertion_type", "")).strip().lower()
        assertion_status = str(row.get("assertion_status", "")).strip().upper()
        if not bc_id or not row.get("feature_id", "").strip():
            errors.append(f"replay-results row {index} lacks bc_id/feature_id")
            continue
        if assertion_type not in REPLAY_ASSERTION_TYPES:
            errors.append(
                f"replay-results row {index} has an unknown assertion_type "
                f"{row.get('assertion_type', '')!r} (expected one of {REPLAY_ASSERTION_TYPES})"
            )
        if assertion_status not in REPLAY_ALLOWED_STATUSES:
            errors.append(
                f"replay-results row {index} has an unknown assertion_status "
                f"{row.get('assertion_status', '')!r}"
            )
    return rows


def load_decision_log(workspace: Path, errors: list[str]) -> dict[tuple[str, str], dict[str, str]]:
    """Parse the human adjudication log for PLATFORM_DEVIATION items.

    Returns {(bc_id, assertion_type): row}; only the latest ACCEPTED/REJECTED
    row per key is authoritative and duplicates are reported as errors.
    """
    decisions: dict[tuple[str, str], dict[str, str]] = {}
    rows = rows_optional(workspace / "decision-log.csv")
    for index, row in enumerate(rows):
        bc_id = str(row.get("bc_id", "")).strip()
        assertion_type = str(row.get("assertion_type", "")).strip().lower()
        decision = str(row.get("decision", "")).strip().upper()
        if not bc_id or assertion_type not in REPLAY_ASSERTION_TYPES:
            errors.append(f"decision-log row {index} lacks a valid bc_id/assertion_type")
            continue
        if decision not in (DECISION_ACCEPTED, DECISION_REJECTED):
            errors.append(
                f"decision-log row {index} decision must be "
                f"{DECISION_ACCEPTED}/{DECISION_REJECTED}, got {decision!r}"
            )
            continue
        if not str(row.get("decided_by", "")).strip() or not str(row.get("decided_at", "")).strip():
            errors.append(f"decision-log row {index} lacks decided_by/decided_at")
            continue
        key = (bc_id, assertion_type)
        if key in decisions:
            errors.append(f"decision-log has duplicate adjudication for {bc_id}/{assertion_type}")
            continue
        decisions[key] = row
    return decisions


def evaluate_runtime_assertions(
    replay_rows: list[dict[str, str]],
    decisions: dict[tuple[str, str], dict[str, str]],
    denominators: dict[str, Any],
    errors: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Rules 1+3: per-BC four-class assertion verdict with the deviation queue.

    Returns ``(rule_result, deviations, manual_queue)``.  A FAIL on any
    behavioral assertion keeps the BC failing forever: explanations may
    accompany (via the deviation queue) but never flip the verdict.
    """
    features = denominators["features"]
    behavior_by_feature = denominators["behavior_by_feature"]
    runtime_features = runtime_feature_ids(features)

    rows_by_bc: dict[str, list[dict[str, str]]] = {}
    for row in replay_rows:
        rows_by_bc.setdefault(str(row.get("bc_id", "")).strip(), []).append(row)

    runtime_bcs: list[str] = []
    for feature_id in runtime_features:
        runtime_bcs.extend(
            str(row.get("bc_id", "")).strip()
            for row in behavior_by_feature.get(feature_id, [])
        )

    status_counts = {
        REPLAY_STATUS_PASS: 0, REPLAY_STATUS_FAIL: 0,
        REPLAY_STATUS_MANUAL: 0, REPLAY_STATUS_PLATFORM: 0,
    }
    failing_bcs: list[str] = []
    manual_queue: list[dict[str, Any]] = []
    deviations: list[dict[str, Any]] = []
    missing_replay: list[str] = []

    for bc_id in sorted(set(runtime_bcs)):
        rows = rows_by_bc.get(bc_id, [])
        if not rows:
            missing_replay.append(bc_id)
            continue
        bc_ok = True
        for assertion_type in REPLAY_ASSERTION_TYPES:
            typed = [
                row for row in rows
                if str(row.get("assertion_type", "")).strip().lower() == assertion_type
            ]
            if not typed:
                errors.append(
                    f"{bc_id}: replay-results lacks the required assertion class "
                    f"{assertion_type!r}"
                )
                bc_ok = False
                continue
            for row in typed:
                status = str(row.get("assertion_status", "")).strip().upper()
                status_counts[status] = status_counts.get(status, 0) + 1
                if status == REPLAY_STATUS_FAIL:
                    # User correction 3: a behavioral FAIL stays FAIL; no
                    # explanation, deviation entry, or human decision may
                    # convert it into a PASS.
                    bc_ok = False
                elif status == REPLAY_STATUS_MANUAL:
                    bc_ok = False
                    manual_queue.append({
                        "bc_id": bc_id,
                        "feature_id": str(row.get("feature_id", "")),
                        "assertion_type": assertion_type,
                        "evidence_ref": str(row.get("evidence_ref", "")),
                    })
                elif status == REPLAY_STATUS_PLATFORM:
                    decision = decisions.get((bc_id, assertion_type))
                    deviations.append({
                        "bc_id": bc_id,
                        "feature_id": str(row.get("feature_id", "")),
                        "assertion_type": assertion_type,
                        "evidence_ref": str(row.get("evidence_ref", "")),
                        "decision": (
                            str(decision.get("decision", "")).upper()
                            if decision else "PENDING"
                        ),
                        "decided_by": str(decision.get("decided_by", "")) if decision else "",
                        "decided_at": str(decision.get("decided_at", "")) if decision else "",
                        "rationale": str(decision.get("rationale", "")) if decision else "",
                    })
                    if not decision or str(decision.get("decision", "")).upper() != DECISION_ACCEPTED:
                        # Unadjudicated (or rejected) platform limitations do
                        # not satisfy the assertion class.
                        bc_ok = False
        if not bc_ok:
            failing_bcs.append(bc_id)

    for bc_id in missing_replay:
        errors.append(f"{bc_id}: verify_mode=RUNTIME behavior contract has no replay result")

    total = len(set(runtime_bcs))
    passed = total - len(set(failing_bcs))
    rule_pass = total > 0 and not failing_bcs and not missing_replay and not manual_queue
    rule = {
        "status": "PASS" if rule_pass else "FAIL",
        "runtime_features": len(runtime_features),
        "runtime_bcs": total,
        "runtime_bcs_pass": passed,
        "assertion_counts": dict(status_counts),
        "failing_bcs": sorted(set(failing_bcs)),
        "manual_verify_queue": manual_queue,
    }
    if not rule_pass and manual_queue:
        errors.append(
            f"{len(manual_queue)} replay assertions are MANUAL_VERIFY_REQUIRED; "
            "the machine gate cannot count them as PASS"
        )
    return rule, deviations, manual_queue


def evaluate_platform_deviations(
    deviations: list[dict[str, Any]], errors: list[str]
) -> dict[str, Any]:
    """Rule 3: every PLATFORM_LIMITATION item needs a human ACCEPTED decision."""
    accepted = [item for item in deviations if item.get("decision") == DECISION_ACCEPTED]
    pending = [item for item in deviations if item.get("decision") != DECISION_ACCEPTED]
    for item in deviations:
        if item.get("decision") == DECISION_REJECTED:
            errors.append(
                "PLATFORM_DEVIATION was REJECTED by human adjudication and still "
                f"blocks the gate: {item.get('bc_id')}/{item.get('assertion_type')}"
            )
    rule_pass = not pending
    if pending:
        errors.append(
            f"{len(pending)} PLATFORM_DEVIATION items lack an ACCEPTED human decision"
        )
    return {
        "status": "PASS" if rule_pass else "FAIL",
        "total": len(deviations),
        "accepted": len(accepted),
        "pending_or_rejected": len(pending),
        "items": deviations,
    }


# ---------------------------------------------------------------------------
# Optional dual-diff source (batch 5 #93): Gate 4 final consumption of the
# step-4 dual-machine differential output.  The differential itself runs
# entirely inside step 4 (dual_verify.py); this rule only re-judges the
# frozen CSV: any DIFF is a machine FAIL, MATCH/MANUAL pass this source
# (MANUAL rows are the dual-engine's human queue and are surfaced, not
# silently counted as MATCH).
# ---------------------------------------------------------------------------


def evaluate_dual_diff_results(workspace: Path, errors: list[str]) -> dict[str, Any]:
    """Optional consumption of dual-diff-results.csv (dual-machine A/B)."""
    dual_path = workspace / DUAL_RESULTS_CSV
    if not dual_path.is_file():
        return {
            "status": "PASS",
            "activated": False,
            "rows": 0,
            "match": 0,
            "diff": 0,
            "manual": 0,
            "diff_rows": [],
            "manual_rows": [],
        }
    rule: dict[str, Any] = {"activated": True}
    try:
        rows = read_csv(dual_path)
    except ValueError as exc:
        errors.append(f"{DUAL_RESULTS_CSV} is unreadable: {exc}")
        rule.update({"status": "FAIL", "rows": 0, "diff_rows": []})
        return rule
    if not rows:
        errors.append(f"{DUAL_RESULTS_CSV} is empty")
        rule.update({"status": "FAIL", "rows": 0, "diff_rows": []})
        return rule
    missing = [name for name in DUAL_REQUIRED_COLUMNS if name not in rows[0]]
    if missing:
        errors.append(f"{DUAL_RESULTS_CSV} lacks columns: {','.join(missing)}")
        rule.update({"status": "FAIL", "rows": len(rows), "diff_rows": []})
        return rule

    counts = {DUAL_VERDICT_MATCH: 0, DUAL_VERDICT_DIFF: 0, DUAL_VERDICT_MANUAL: 0}
    seen: set[tuple[str, str]] = set()
    diff_rows: list[str] = []
    manual_rows: list[str] = []
    parse_failed = False
    for index, row in enumerate(rows):
        bc_id = str(row.get("bc_id", "")).strip()
        category = str(row.get("assertion_type", "")).strip()
        verdict = str(row.get("verdict", "")).strip()
        if not bc_id or not str(row.get("feature_id", "")).strip():
            errors.append(f"{DUAL_RESULTS_CSV} row {index} lacks bc_id/feature_id")
            parse_failed = True
            continue
        if category not in REPLAY_ASSERTION_TYPES:
            errors.append(
                f"{DUAL_RESULTS_CSV} row {index} has an unknown assertion_type "
                f"{row.get('assertion_type', '')!r}"
            )
            parse_failed = True
            continue
        if (bc_id, category) in seen:
            errors.append(f"{DUAL_RESULTS_CSV} has duplicate {bc_id}/{category}")
            parse_failed = True
            continue
        seen.add((bc_id, category))
        if verdict not in DUAL_ALLOWED_VERDICTS:
            errors.append(
                f"{DUAL_RESULTS_CSV} {bc_id}/{category} has an unknown verdict "
                f"{row.get('verdict', '')!r}"
            )
            parse_failed = True
            continue
        counts[verdict] += 1
        if verdict == DUAL_VERDICT_DIFF:
            # User design: a dual DIFF (android vs harmony result drift) is a
            # machine FAIL; explanations may accompany but never flip it.
            if not (
                str(row.get("android_expected", "")).strip()
                and str(row.get("harmony_actual", "")).strip()
            ):
                errors.append(
                    f"dual diff: {bc_id}/{category} reports DIFF without both "
                    "side observations"
                )
                parse_failed = True
            diff_rows.append(f"{bc_id}/{category}")
        elif verdict == DUAL_VERDICT_MANUAL:
            manual_rows.append(f"{bc_id}/{category}")
    for item in diff_rows:
        errors.append(
            f"dual diff: {item} reports DIFF (android/harmony result drift)"
        )
    rule.update(
        {
            "status": "FAIL" if diff_rows or parse_failed else "PASS",
            "rows": len(rows),
            "match": counts[DUAL_VERDICT_MATCH],
            "diff": counts[DUAL_VERDICT_DIFF],
            "manual": counts[DUAL_VERDICT_MANUAL],
            "diff_rows": diff_rows,
            "manual_rows": manual_rows,
        }
    )
    return rule


# ---------------------------------------------------------------------------
# Rule 2: data semantic parity (semantic objects only, carriers never compared)
# ---------------------------------------------------------------------------


def evaluate_data_parity(
    workspace: Path,
    denominators: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Rule 2: semantic read/write set equivalence + persistence coverage.

    Android side: the frozen Phase 2 feature-map ``data_objects`` per feature
    (already reconciled by Phase 2's reconciliation engine) plus the frozen
    data-relations persistence kinds.  Harmony side: recomputed from the
    implementation declarations (data reads/writes, Phase 3 data-contract
    references, and the declared ``harmony_persistence`` carriers).
    """
    features = denominators["features"]
    declarations = index_declarations(workspace, errors)
    data_contracts = denominators["data_contracts"]

    contract_keys: set[tuple[str, str]] = set()
    android_persistence_by_object: dict[str, set[str]] = {}
    for contract in data_contracts:
        feature_id = str(contract.get("feature_id", ""))
        data_object = str(contract.get("data_object", ""))
        if feature_id and data_object:
            contract_keys.add((feature_id, data_object))
        for carrier in contract.get("android_persistence", []) or []:
            if data_object and str(carrier):
                android_persistence_by_object.setdefault(data_object, set()).add(str(carrier))

    # data-relations persistence declarations feed the Android-side carrier map
    for row in denominators["data_relations"]:
        data_object = str(row.get("data_object", "")).strip()
        location = str(row.get("persistence_location", "")).strip()
        kind = str(row.get("persistence_kind", "")).strip()
        if data_object and location and location != "<none>":
            android_persistence_by_object.setdefault(data_object, set()).add(f"{kind}:{location}")

    missing_on_harmony: list[str] = []
    extra_on_harmony: list[str] = []
    persistence_gaps: list[str] = []
    orphan_contract_refs: list[str] = []
    compared = 0

    for feature_id in sorted(features):
        android_reads, android_writes = feature_data_objects(features[feature_id])
        declaration = declarations.get(feature_id)
        if declaration is None:
            if android_reads or android_writes:
                missing_on_harmony.append(
                    f"{feature_id}: implementation declaration is missing"
                )
            continue
        harmony_reads = set(split_semantic_list(str(declaration.get("data_reads", ""))))
        harmony_writes = set(split_semantic_list(str(declaration.get("data_writes", ""))))
        if android_reads != harmony_reads:
            detail = (
                f"{feature_id}: data read set differs "
                f"(android={sorted(android_reads)}, harmony={sorted(harmony_reads)})"
            )
            (extra_on_harmony if harmony_reads - android_reads else missing_on_harmony).append(detail)
        if android_writes != harmony_writes:
            detail = (
                f"{feature_id}: data write set differs "
                f"(android={sorted(android_writes)}, harmony={sorted(harmony_writes)})"
            )
            (extra_on_harmony if harmony_writes - android_writes else missing_on_harmony).append(detail)
        compared += 1

        # Referenced Phase 3 data contracts must exist (no orphan references).
        for ref in split_semantic_list(str(declaration.get("data_contract_refs", ""))):
            token = ref.split(":", 1)[1] if ":" in ref else ref
            if (feature_id, token) not in contract_keys and ref not in {
                str(contract.get("object_id", "")) for contract in data_contracts
            }:
                orphan_contract_refs.append(f"{feature_id}: unknown data-contract ref {ref!r}")

        # Semantic persistence coverage: every Android-persisted object must
        # be declared on the Harmony side with some carrier (any carrier kind;
        # physical equivalence is explicitly not required).
        declared_persistence = {}
        for item in split_semantic_list(str(declaration.get("harmony_persistence", ""))):
            if "=" in item:
                obj, carrier = item.split("=", 1)
                declared_persistence[obj.strip()] = carrier.strip()
            else:
                declared_persistence[item.strip()] = ""
        for data_object in sorted(android_writes | android_reads):
            carriers = android_persistence_by_object.get(data_object)
            if carriers and data_object not in declared_persistence:
                persistence_gaps.append(
                    f"{feature_id}: Android persists {data_object!r} "
                    f"({sorted(carriers)}) but the Harmony declaration has no "
                    "harmony_persistence entry"
                )

    declared_features = set(declarations) - set(features)
    for feature_id in sorted(declared_features):
        extra_on_harmony.append(f"{feature_id}: declaration outside the frozen feature map")

    rule_pass = not (missing_on_harmony or extra_on_harmony or persistence_gaps or orphan_contract_refs)
    for detail in missing_on_harmony:
        errors.append(f"data parity: {detail}")
    for detail in extra_on_harmony:
        errors.append(f"data parity: {detail}")
    for detail in persistence_gaps:
        errors.append(f"data parity (persistence coverage): {detail}")
    for detail in orphan_contract_refs:
        errors.append(f"data parity (contract closure): {detail}")
    return {
        "status": "PASS" if rule_pass else "FAIL",
        "features_compared": compared,
        "android_persisted_objects": len(android_persistence_by_object),
        "missing_on_harmony": missing_on_harmony,
        "extra_on_harmony": extra_on_harmony,
        "persistence_gaps": persistence_gaps,
        "orphan_contract_refs": orphan_contract_refs,
    }


def index_declarations(workspace: Path, errors: list[str]) -> dict[str, dict[str, str]]:
    """Index implementation-declarations.csv by feature_id (defensive parse).

    批次 2 #85 read-receipt 列（consumed_bc_ids / consumed_source_refs /
    consumed_runtime_refs）：defensive 读取——列不在场按空处理，规则归
    evaluate_must_read_receipt（RUNTIME feature 空 consumed_source_refs
    = gate FAIL，机械化保证实施者读过 P2/Android 源码）。
    """
    rows = read_csv(workspace / "implementation-declarations.csv")
    declarations: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows):
        feature_id = str(row.get("feature_id", "")).strip()
        if not feature_id:
            errors.append(f"implementation-declarations row {index} lacks feature_id")
            continue
        if feature_id in declarations:
            errors.append(f"implementation-declarations has duplicate feature {feature_id}")
            continue
        declarations[feature_id] = row
    return declarations


# ---------------------------------------------------------------------------
# Rule 7 (batch 2 #85): MUST_READ read receipts + frozen probe hash
# ---------------------------------------------------------------------------

# implementation-declarations.csv read-receipt columns (batch 2 #85)
CONSUMED_COLUMNS = ("consumed_bc_ids", "consumed_source_refs",
                    "consumed_runtime_refs")
# Harmony-project probe file the Phase 4 implementer must never modify
# (expected hash rides on the controller work order; legacy orders without
# the binding keep the check dormant).
PROBE_RELATIVE_PATH = "entry/src/main/ets/probe/DebugSemanticProbe.ets"


def evaluate_must_read_receipt(
    workspace: Path,
    denominators: dict[str, Any],
    work_order: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Rule 7 (batch 2 #85): mechanical proof the implementer read P2/Android.

    - Every verify_mode=RUNTIME feature's implementation declaration must
      carry a non-empty ``consumed_source_refs`` receipt (empty -> gate
      error; reading the Android source is a hard prerequisite for
      behavioral equivalence, never self-attested).
    - Receipts must be subsets of the work order's frozen ``must_read``
      denominators (fabricated references fail closed).
    - The frozen DebugSemanticProbe must match the work order's expected
      sha256 (implementers may not tamper with the data probe).
    """
    features = denominators["features"]
    declarations = index_declarations(workspace, errors)
    manifest = work_order.get("feature_manifest") if isinstance(work_order, dict) else None
    manifest_by_feature: dict[str, dict[str, Any]] = {}
    if isinstance(manifest, list):
        for item in manifest:
            if isinstance(item, dict) and item.get("feature_id"):
                manifest_by_feature[str(item["feature_id"])] = item

    missing_receipts: list[str] = []
    fabricated: list[str] = []
    checked = 0
    for feature_id in runtime_feature_ids(features):
        declaration = declarations.get(feature_id)
        if declaration is None:
            # data_parity already reports the missing declaration; here we
            # only fail on missing receipts for declared features.
            continue
        checked += 1
        consumed_sources = set(
            split_semantic_list(str(declaration.get("consumed_source_refs", ""))))
        if not consumed_sources:
            missing_receipts.append(
                f"{feature_id}: RUNTIME feature has no consumed_source_refs "
                "receipt (implementation-declarations.csv)"
            )
        must_read = (manifest_by_feature.get(feature_id, {})
                     .get("must_read"))
        raw_sources = (must_read.get("android_source_refs")
                       if isinstance(must_read, dict) else None)
        denominator = (
            {str(item) for item in raw_sources}
            if isinstance(raw_sources, list) else set()
        )
        if denominator and consumed_sources - denominator:
            fabricated.append(
                f"{feature_id}: consumed_source_refs not in work-order "
                f"must_read.android_source_refs: "
                f"{sorted(consumed_sources - denominator)[:4]}"
            )

    probe_failures: list[str] = []
    probe_binding = (work_order.get("semantic_probe")
                     if isinstance(work_order, dict) else None)
    probe_status = "DORMANT"
    if isinstance(probe_binding, dict) and probe_binding.get("expected_sha256"):
        probe_path = workspace / "harmony-project" / PROBE_RELATIVE_PATH
        if not probe_path.is_file():
            probe_failures.append(
                f"frozen semantic probe missing: harmony-project/"
                f"{PROBE_RELATIVE_PATH}")
        else:
            actual = sha256_file(probe_path)
            if actual != probe_binding.get("expected_sha256"):
                probe_failures.append(
                    "semantic probe hash differs from the work-order "
                    "expected value (implementers must not modify "
                    f"{PROBE_RELATIVE_PATH})")
        probe_status = "ENFORCED"

    for detail in missing_receipts:
        errors.append(f"must-read receipt: {detail}")
    for detail in fabricated:
        errors.append(f"must-read receipt: {detail}")
    for detail in probe_failures:
        errors.append(f"semantic probe: {detail}")
    rule_pass = not (missing_receipts or fabricated or probe_failures)
    return {
        "status": "PASS" if rule_pass else "FAIL",
        "runtime_features_checked": checked,
        "missing_receipts": missing_receipts,
        "fabricated_receipts": fabricated,
        "probe_status": probe_status,
        "probe_failures": probe_failures,
    }


# ---------------------------------------------------------------------------
# Rule 4: SOURCE_CONFIRM minimum floor (four floors per feature)
# ---------------------------------------------------------------------------


def scan_arkts_stubs(text: str) -> list[str]:
    """Static no-op/placeholder detection over one ArkTS source file.

    Detection classes (any hit fails the no-placeholder floor):
    * TODO/FIXME marker comments;
    * placeholder tokens (TBD / MOCK_ONLY / STUB_ONLY / FAKE_DATA /
      PLACEHOLDER / __FILL__ / not-implemented);
    * functions whose whole body is a single ``return null|undefined``;
    * empty or comment-only function bodies.
    """
    findings: list[str] = []
    for line in text.splitlines():
        if STUB_TODO_RE.match(line):
            findings.append(f"todo-marker: {line.strip()[:120]}")
    for match in STUB_TOKEN_RE.finditer(text):
        findings.append(f"placeholder-token: {match.group(0)}")
    for match in STUB_RETURN_RE.finditer(text):
        findings.append(f"null-return-stub: {match.group(0)[:120]}")
    for match in STUB_EMPTY_BODY_RE.finditer(text):
        findings.append(f"empty-body-stub: {match.group(0)[:120]}")
    for match in STUB_COMMENT_ONLY_RE.finditer(text):
        findings.append(f"comment-only-stub: {match.group(0)[:120]}")
    return findings


def evaluate_source_confirm_floor(
    workspace: Path,
    denominators: dict[str, Any],
    surface_rows: list[dict[str, str]],
    final_build_ids: list[str],
    errors: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Rule 4: the four minimum floors for every SOURCE_CONFIRM feature."""
    features = denominators["features"]
    declarations = index_declarations(workspace, errors)
    project = workspace / "harmony-project"
    surfaces_by_feature: dict[str, dict[str, str]] = {}
    for index, row in enumerate(surface_rows):
        feature_id = str(row.get("feature_id", "")).strip()
        if not feature_id:
            errors.append(f"surface-contract row {index} lacks feature_id")
            continue
        if feature_id in surfaces_by_feature:
            errors.append(f"surface-contract has duplicate feature {feature_id}")
        surfaces_by_feature[feature_id] = row

    failures: list[dict[str, Any]] = []
    floors = {
        "implementation_present": 0,
        "no_placeholder": 0,
        "source_traceable": 0,
        "buildable": 0,
    }
    source_confirm = source_confirm_feature_ids(features)
    for feature_id in source_confirm:
        entry = features[feature_id]
        declaration = declarations.get(feature_id, {})
        surface_row = surfaces_by_feature.get(feature_id, {})

        # Floor a: implementation present (referenced files exist and are
        # non-empty shells; never trust a status string alone).
        refs = feature_source_refs(declaration, surface_row, entry)
        present_files: list[Path] = []
        for reference in refs:
            target = (project / reference).resolve()
            try:
                target.relative_to(project.resolve())
            except ValueError:
                errors.append(
                    f"{feature_id}: source reference escapes harmony-project: {reference!r}"
                )
                continue
            if target.is_file() and target.stat().st_size > 0:
                present_files.append(target)
        implementation_present = bool(present_files)
        if implementation_present:
            floors["implementation_present"] += 1
        else:
            failures.append({
                "feature_id": feature_id, "floor": "implementation_present",
                "detail": f"no non-empty referenced ArkTS source (refs={refs[:5]})",
            })

        # Floor b: static no-op/placeholder scan over the referenced sources.
        stub_findings: list[str] = []
        for target in present_files:
            if target.suffix == ARKTS_SUFFIX:
                stub_findings.extend(
                    f"{target.relative_to(project).as_posix()}: {finding}"
                    for finding in scan_arkts_stubs(
                        target.read_text(encoding="utf-8", errors="replace")
                    )
                )
        no_placeholder = implementation_present and not stub_findings
        if no_placeholder:
            floors["no_placeholder"] += 1
        else:
            failures.append({
                "feature_id": feature_id, "floor": "no_placeholder",
                "detail": "; ".join(stub_findings[:5]) or "no scannable source",
            })

        # Floor c: feature -> source traceability (surface contract or the
        # implementation record must cite a concrete source relation).
        traceable = bool(surface_row) and bool(refs)
        if traceable:
            floors["source_traceable"] += 1
        else:
            failures.append({
                "feature_id": feature_id, "floor": "source_traceable",
                "detail": "surface-contract row or implementation record lacks a feature->source reference",
            })

        # Floor d: buildable (the final smoke HBUILD chain covers the project
        # the feature sources live in).
        buildable = bool(final_build_ids)
        if buildable:
            floors["buildable"] += 1
        else:
            failures.append({
                "feature_id": feature_id, "floor": "buildable",
                "detail": "no final PASS HBUILD seals the smoke build",
            })

    rule_pass = not failures
    if not source_confirm:
        errors.append(
            "feature map has no SOURCE_CONFIRM features; the floor denominator "
            "must not be empty"
        )
        rule_pass = False
    for failure in failures:
        errors.append(
            f"source-confirm floor failed: {failure['feature_id']} "
            f"({failure['floor']}): {failure['detail']}"
        )
    floors_summary = {
        "status": "PASS" if rule_pass else "FAIL",
        "features": len(source_confirm),
        "floors": floors,
        "failures": failures,
    }
    return floors_summary, {feature_id: {} for feature_id in source_confirm}


def feature_source_refs(
    declaration: dict[str, str],
    surface_row: dict[str, str],
    entry: dict[str, Any],
) -> list[str]:
    """Collect harmony-project-relative source references for one feature."""
    refs: list[str] = []
    for source in (str(declaration.get("source_refs", "")), str(surface_row.get("notes", ""))):
        for item in split_semantic_list(source):
            reference = item.split(":", 1)[0] if item.split(":", 1)[0].endswith(ARKTS_SUFFIX) else (
                item if item.endswith(ARKTS_SUFFIX) else ""
            )
            if reference and reference not in refs:
                refs.append(reference)
    # Surfaces column of the thin table may carry comma/semicolon separated ids;
    # they are not source files, so only notes/declaration refs count here.
    return refs


# ---------------------------------------------------------------------------
# Surface-contract thin table (H) - full PASS requirement
# ---------------------------------------------------------------------------


def evaluate_surface_contract(
    surface_rows: list[dict[str, str]],
    denominators: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """The thin table must cover every feature and be fully PASS."""
    features = denominators["features"]
    rows_by_feature: dict[str, dict[str, str]] = {}
    for index, row in enumerate(surface_rows):
        feature_id = str(row.get("feature_id", "")).strip()
        if not feature_id:
            errors.append(f"surface-contract row {index} lacks feature_id")
            continue
        if feature_id in rows_by_feature:
            errors.append(f"surface-contract has duplicate feature row {feature_id}")
            continue
        rows_by_feature[feature_id] = row

    problems: list[str] = []
    for feature_id in sorted(features):
        row = rows_by_feature.get(feature_id)
        if row is None:
            problems.append(f"{feature_id}: no surface-contract row")
            continue
        surfaces = split_semantic_list(str(row.get("surfaces", "")))
        entry_reachable = str(row.get("entry_reachable", "")).strip().lower()
        nav_pattern = str(row.get("nav_pattern", "")).strip()
        native_impl = str(row.get("native_impl_check", "")).strip().upper()
        if not surfaces:
            problems.append(f"{feature_id}: surface-contract surfaces column is empty")
        if entry_reachable != SURFACE_ENTRY_YES:
            problems.append(f"{feature_id}: entry_reachable is {entry_reachable!r}, expected 'yes'")
        if not nav_pattern:
            problems.append(f"{feature_id}: nav_pattern is empty")
        if native_impl != SURFACE_NATIVE_PASS:
            problems.append(
                f"{feature_id}: native_impl_check is {native_impl!r}, expected PASS"
            )
    for feature_id in sorted(set(rows_by_feature) - set(features)):
        problems.append(f"{feature_id}: surface-contract row outside the frozen feature map")
    for problem in problems:
        errors.append(f"surface-contract: {problem}")
    return {
        "status": "PASS" if not problems else "FAIL",
        "features_covered": len(rows_by_feature),
        "feature_total": len(features),
        "problems": problems,
    }


# ---------------------------------------------------------------------------
# Rule 6: visual fidelity (structure comparison against Phase 2 visual-memory)
# ---------------------------------------------------------------------------

# Phase 2 visual-memory baseline (defensively consumed; schema owned by the
# inventory agent — surface_id / ui-tree digest / palette with aliases).
FROZEN_VISUAL_MEMORY = f"{RUN_PHASE2}/visual-memory.json"
VISUAL_FIDELITY_VERDICTS = ("PASS", "VISUAL_GAP", "NO_BASELINE", "NO_DUMP")
# Visible-surface denominator (fix 4b): every surface a user can see must
# carry a fidelity verdict, regardless of verify_mode.  Transparent hosts
# (container / reusable-component) carry no UI of their own and stay out of
# the denominator; any other unknown kind is counted for observability but
# never silently treated as visible.
VISIBLE_SURFACE_KINDS = frozenset({"page", "sheet", "dialog"})
TRANSPARENT_SURFACE_KINDS = frozenset({"container", "reusable-component"})


def evaluate_visual_fidelity(
    workspace: Path,
    run_dir: Path,
    denominators: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Rule 6: "UI may differ but not too much" (machine-judged structure
    comparison, not pixel parity).

    Conditionally activated: without the frozen Phase 2 visual-memory
    baseline the rule stays dormant (PASS + activated=false) so legacy
    runs keep closing.  Once the baseline exists, the denominator is
    every user-visible surface in the feature map (kind in
    VISIBLE_SURFACE_KINDS — page / sheet / dialog), across ALL features
    no matter the verify_mode (RUNTIME or SOURCE_CONFIRM): each must
    have a PASS row in visual-fidelity.csv.  A missing row, VISUAL_GAP,
    or NO_DUMP on any visible surface is a gate failure ("visual gap
    too large" / missing implementation evidence).
    NO_BASELINE rows are Phase 2 responsibility and only counted, never
    failing the implementation side.
    """
    memory_path = run_dir / FROZEN_VISUAL_MEMORY
    if not memory_path.is_file():
        return {
            "status": "PASS",
            "activated": False,
            "reason": "no Phase 2 visual-memory baseline; rule dormant",
        }

    rows = rows_optional(workspace / "visual-fidelity.csv")
    if not rows:
        errors.append(
            "visual-fidelity: Phase 2 visual-memory exists but "
            "visual-fidelity.csv is missing in the workspace"
        )
        return {
            "status": "FAIL",
            "activated": True,
            "reason": "visual-fidelity.csv missing",
            "counts": {},
        }

    by_surface: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows):
        surface_id = str(row.get("surface_id", "")).strip()
        verdict = str(row.get("verdict", "")).strip().upper()
        if not surface_id or surface_id in by_surface:
            errors.append(
                f"visual-fidelity row {index} lacks or duplicates surface_id"
            )
            continue
        if verdict not in VISUAL_FIDELITY_VERDICTS:
            errors.append(
                f"visual-fidelity row {index} ({surface_id}) has an unknown "
                f"verdict {row.get('verdict', '')!r}"
            )
            continue
        by_surface[surface_id] = row

    features = denominators["features"]
    counts = {verdict: 0 for verdict in VISUAL_FIDELITY_VERDICTS}
    problems: list[str] = []
    visible_surfaces = 0
    uncounted_kinds: dict[str, int] = {}
    for row in by_surface.values():
        verdict = str(row.get("verdict", "")).strip().upper()
        counts[verdict] = counts.get(verdict, 0) + 1
    for feature_id in sorted(features):
        entry = features[feature_id]
        raw_surfaces = entry.get("surfaces") if isinstance(entry.get("surfaces"), list) else []
        for raw in raw_surfaces:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind", "")).strip()
            if kind in TRANSPARENT_SURFACE_KINDS:
                continue  # transparent host: no UI of its own to compare
            if kind not in VISIBLE_SURFACE_KINDS:
                # Unknown kind: observed for auditability, never silently
                # counted as visible (nor failing the gate on its own).
                uncounted_kinds[kind or "<empty>"] = (
                    uncounted_kinds.get(kind or "<empty>", 0) + 1
                )
                continue
            visible_surfaces += 1
            row = by_surface.get(str(raw.get("id", "")).strip())
            if row is None:
                problems.append(
                    f"{feature_id}: user-visible surface {raw.get('id', '')!r} "
                    "has no visual-fidelity row"
                )
                continue
            verdict = str(row.get("verdict", "")).strip().upper()
            if verdict == "VISUAL_GAP":
                problems.append(
                    f"{feature_id}: surface {row.get('surface_id', '')} "
                    f"VISUAL_GAP — visual difference too large "
                    f"({(row.get('notes') or '')[:120]})"
                )
            elif verdict == "NO_DUMP":
                problems.append(
                    f"{feature_id}: surface {row.get('surface_id', '')} "
                    "NO_DUMP — replay layout evidence missing"
                )
    for problem in problems:
        errors.append(f"visual-fidelity: {problem}")
    return {
        "status": "FAIL" if problems else "PASS",
        "activated": True,
        "visible_surfaces": visible_surfaces,
        # legacy alias (pre-4b consumers); same value as visible_surfaces
        "host_surfaces": visible_surfaces,
        "uncounted_kinds": uncounted_kinds,
        "counts": counts,
        "problems": problems,
    }


# ---------------------------------------------------------------------------
# Rule 5: H4ENV environment chain + final HBUILD set
# ---------------------------------------------------------------------------


def evaluate_h4env_chain(
    workspace: Path,
    input_lock: dict[str, Any],

    errors: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Rule 5: registry/environment integrity (pixel capture stays optional)."""
    local_errors: list[str] = errors if errors is not None else []
    env_rows = read_csv(workspace / "environments" / "h4env-registry.csv")
    registry: dict[str, dict[str, str]] = {}
    for index, row in enumerate(env_rows):
        h4env_id = str(row.get("h4env_id", "")).strip()
        if not h4env_id or h4env_id in registry:
            local_errors.append(f"H4ENV registry row {index} is invalid or duplicate")
            continue
        registry[h4env_id] = row
    required_value = input_lock.get("required_h4env_ids")
    required_ids = set(required_value if isinstance(required_value, list) else [])
    if not required_ids or set(registry) != required_ids:
        local_errors.append(
            "Phase 4 H4ENV registry differs from the frozen required H4ENV set; "
            f"registry={sorted(registry)}, required={sorted(required_ids)}"
        )
    environments: dict[str, dict[str, Any]] = {}
    for h4env_id in sorted(registry):
        env_path = workspace / "environments" / h4env_id / "phase4-environment.json"
        if not env_path.is_file() or env_path.is_symlink():
            local_errors.append(f"H4ENV environment record is missing or unsafe: {h4env_id}")
            continue
        try:
            environment = object_json(env_path, f"H4ENV {h4env_id} environment")
        except ValueError as exc:
            local_errors.append(str(exc))
            continue
        environments[h4env_id] = environment
        for key in ("source_android_env_id", "base_henv_id", "device_id"):
            if not str(environment.get(key, "")):
                local_errors.append(f"{h4env_id}: environment lacks {key}")

    locked_h4envs = input_lock.get("h4envs")
    if not isinstance(locked_h4envs, list):
        local_errors.append("Phase 4 input lock h4envs must be an array")
        locked_h4envs = []
    locked_ids: set[str] = set()
    for record in locked_h4envs:
        if not isinstance(record, dict):
            local_errors.append("Phase 4 h4envs contains a non-object record")
            continue
        h4env_id = str(record.get("h4env_id", ""))
        relative = f"environments/{h4env_id}/phase4-environment.json"
        env_path = workspace / relative
        if (
            h4env_id in locked_ids
            or h4env_id not in environments
            or record.get("relative_path") != relative
            or not env_path.is_file()
            or record.get("sha256") != sha256_file(env_path)
        ):
            local_errors.append(f"Phase 4 input-lock H4ENV record differs: {h4env_id!r}")
            continue
        locked_ids.add(h4env_id)
    if set(locked_ids) != set(environments):
        local_errors.append(
            "Phase 4 input-lock H4ENV records do not exactly cover frozen environments"
        )

    base_count = len(local_errors)
    rule = {
        "status": "FAIL",  # finalized by finalize_h4env_status after the build set
        "environments": sorted(environments),
        "required_h4env_ids": sorted(required_ids),
        "_env_error_count": base_count,
    }

    return rule, environments


def finalize_h4env_status(rule: dict[str, Any], build_count: int, env_count: int) -> None:
    """Rule 5 final status: environment records intact AND one build per env."""
    environment_ok = rule.pop("_env_error_count", 0) == 0
    builds_ok = build_count == env_count and env_count > 0
    rule["final_build_count"] = build_count
    rule["status"] = "PASS" if environment_ok and builds_ok else "FAIL"


def collect_final_builds(
    workspace: Path,
    build_ids: list[str],
    environments: dict[str, dict[str, Any]],
    ownership: dict[str, str],
    input_lock_sha256: str,
    source_snapshot_sha256: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Validate the caller-selected final build set before the independent audit."""
    require(build_ids == sorted(set(build_ids)) and bool(build_ids),
            "--build-id values must be nonempty, sorted, and unique")
    builds: dict[str, dict[str, Any]] = {}
    build_by_environment: dict[str, str] = {}
    artifact_hashes: list[str] = []
    for build_id in build_ids:
        validate_id(build_id, "HBUILD-ID")
        directory = safe_relative_path(
            workspace, f"builds/{build_id}", f"HBUILD {build_id}"
        )
        require(directory.is_dir(), f"HBUILD directory is missing: {build_id}")
        metadata = object_json(directory / "metadata.json", f"HBUILD {build_id} metadata")
        h4env_id = validate_id(str(metadata.get("h4env_id", "")), f"{build_id} H4ENV-ID")
        require(h4env_id in environments and h4env_id not in build_by_environment,
                f"HBUILD set has an unknown or duplicate H4ENV: {h4env_id}")
        validated, artifact_sha256 = validate_hbuild(
            directory,
            build_id,
            environments[h4env_id],
            ownership["verification_executor_id"],
            input_lock_sha256,
            source_snapshot_sha256,
        )
        require(
            validated.get("h4env_id") == h4env_id
            and validated.get("environment_sha256")
            == sha256_file(workspace / "environments" / h4env_id / "phase4-environment.json"),
            f"HBUILD environment binding differs: {build_id}",
        )
        builds[build_id] = validated
        build_by_environment[h4env_id] = build_id
        artifact_hashes.append(artifact_sha256)
    require(set(build_by_environment) == set(environments),
            "Final HBUILD set must contain exactly one PASS build per required H4ENV")
    return builds, artifact_hashes


def project_snapshot_digest(project: Path) -> str:
    """Mirror of controller phase4_project_snapshot: identical exclusion set,
    entry shape, and canonical digest so both sides agree on one snapshot id."""
    entries: list[dict[str, Any]] = []
    for path in sorted(project.rglob("*")):
        if any(part in {
            ".git", ".idea", ".hvigor", "build", "dist", "coverage",
            "node_modules", "oh_modules", "__pycache__", ".pytest_cache",
        } for part in path.relative_to(project).parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        entries.append({
            "path": path.relative_to(project).as_posix(),
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        })
    entries.sort(key=lambda item: item["path"])
    canonical = json.dumps(entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Attempt ledger (defensive; kept for tamper-proofing when the chain exists)
# ---------------------------------------------------------------------------


ATTEMPT_LEDGER_FIELDS = [
    "execution_id", "parity_id", "evidence_id", "started_at", "executed_by",
    "previous_chain_sha256", "chain_sha256",
]


def validate_attempt_ledger_optional(workspace: Path, errors: list[str]) -> None:
    """When an attempt ledger exists, its hash chain must stay verifiable."""
    local_path = workspace / "attempt-ledger.csv"
    if not local_path.is_file():
        return
    rows = read_csv(local_path)
    previous = "0" * 64
    seen: set[str] = set()
    for row in rows:
        material = {field: row.get(field, "") for field in ATTEMPT_LEDGER_FIELDS[:-1]}
        expected = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if (
            set(row) != set(ATTEMPT_LEDGER_FIELDS)
            or not row.get("execution_id") or row["execution_id"] in seen
            or row.get("previous_chain_sha256") != previous
            or row.get("chain_sha256") != expected
        ):
            errors.append("Phase 4 attempt ledger hash chain is invalid")
            return
        seen.add(row["execution_id"])
        previous = expected


def open_rework_count(workspace: Path) -> int:
    rows = rows_optional(workspace / "rework-tickets.csv")
    return sum(1 for row in rows if str(row.get("status", "")).upper() != "CLOSED")


# ---------------------------------------------------------------------------
# Candidate report assembly
# ---------------------------------------------------------------------------


def build_candidate_report(
    workspace: Path,
    run_id: str | None,
    work_order_id: str | None,
    reviewer: str,
    input_lock_sha256: str,
    source_snapshot_sha256: str,
    build_ids: list[str],
    artifact_hashes: list[str],
    rules: dict[str, Any],
    surface_contract: dict[str, Any],
    deviations: dict[str, Any],
    source_confirm_floors: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    verdict = "PASS" if not errors and all(
        rule.get("status") == "PASS" for rule in rules.values()
    ) and surface_contract.get("status") == "PASS" else "FAIL"
    return {
        "schema_version": "stage4-v4",
        "phase": 4,
        "run_id": run_id,
        "work_order_id": work_order_id,
        "verdict": verdict,
        "final_verdict": verdict,
        "implementation_chain_closed": verdict == "PASS",
        "reviewer_role": "parity-acceptance-agent",
        "reviewer_id": reviewer,
        "reviewed_at": utc_now(),
        "input_lock_sha256": input_lock_sha256,
        "source_snapshot_sha256": source_snapshot_sha256,
        "build_ids": build_ids,
        "artifact_hashes": artifact_hashes,
        "rules": rules,
        "surface_contract": surface_contract,
        "deviations": deviations,
        "source_confirm_floors": source_confirm_floors,
        "counts": {
            "replay_rows": len(read_csv(workspace / "replay-results.csv")),
            "surface_contract_rows": len(read_csv(workspace / "surface-contract.csv")),
            "implementation_declarations": len(read_csv(workspace / "implementation-declarations.csv")),
            "open_rework": open_rework_count(workspace),
        },
        "errors": list(errors),
    }


def remove_candidate_outputs(paths: list[Path]) -> None:
    """Best-effort rollback for a failed pre-seal audit."""
    for path in reversed(paths):
        try:
            if path.exists() and path.is_file() and not path.is_symlink():
                path.chmod(0o600)
                path.unlink()
        except OSError:
            pass


def validate_upstream_bindings(
    run_dir: Path, input_lock: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Verify the input lock still binds the frozen controller work order."""
    work_order_id = str(input_lock.get("work_order_id", ""))
    require(bool(work_order_id), "Phase 4 input lock lacks work_order_id")
    work_order_path = run_dir / "controller" / "work-orders" / f"{work_order_id}.json"
    require(work_order_path.is_file(), f"Controller work order is missing: {work_order_path}")
    work_order_sha = sha256_file(work_order_path)
    require(
        input_lock.get("work_order_sha256") == work_order_sha,
        "Phase 4 input lock binds another work-order digest",
    )
    work_order = object_json(work_order_path, "Phase 4 work order")
    return work_order_id, work_order


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument(
        "--build-id", action="append", required=True,
        help="Final PASS HBUILD-ID; repeat once per required H4ENV",
    )
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--decision", required=True, choices=("PASS",))
    args = parser.parse_args()

    raw_workspace = Path(args.workspace).expanduser().absolute()
    candidate_paths: list[Path] = []
    try:
        require(not raw_workspace.is_symlink(), "Phase 4 workspace must not be a symbolic link")
        workspace = raw_workspace.resolve(strict=True)
        run_dir = workspace.parent
        for name in ("stage-04-gate-report.json", "stage-04-closure-manifest.sha256", "CLOSED"):
            require(not (workspace / name).exists(),
                    f"Phase 4 already has a final or partial closure artifact: {name}")
        reviewer = validate_actor(args.reviewer, "parity acceptance reviewer")

        for relative in REQUIRED_WORKSPACE_ARTIFACTS[:-3]:
            candidate = workspace / relative
            require(candidate.exists() and not candidate.is_symlink(),
                    f"Phase 4 artifact is missing or unsafe: {relative}")

        input_lock = object_json(workspace / "stage-04-input-lock.json", "Phase 4 input lock")
        phase_manifest = object_json(workspace / "phase-manifest.json", "Phase 4 manifest")
        ownership = input_lock.get("ownership") if isinstance(input_lock.get("ownership"), dict) else {}
        for key in ROLE_KEYS:
            require(bool(ownership.get(key)), f"Phase 4 input lock lacks ownership.{key}")
        require(reviewer == ownership.get("parity_acceptance_agent_id"),
                "Only the frozen parity acceptance agent may close Phase 4")
        work_order_id, work_order = validate_upstream_bindings(run_dir, input_lock)
        require(
            phase_manifest.get("work_order_id") == work_order_id
            and phase_manifest.get("run_id") == input_lock.get("run_id"),
            "Phase 4 manifest identity differs from the input lock",
        )

        errors: list[str] = []
        denominators = load_frozen_denominators(run_dir)
        replay_rows = load_replay_results(workspace, errors)
        decisions = load_decision_log(workspace, errors)

        # Rule 7 (batch 2 #85): MUST_READ receipts + frozen probe hash.
        must_read_rule = evaluate_must_read_receipt(
            workspace, denominators, work_order, errors
        )

        # Rules 1+3 (runtime assertions with the PLATFORM_DEVIATION queue).
        runtime_rule, deviations, _manual = evaluate_runtime_assertions(
            replay_rows, decisions, denominators, errors
        )
        deviation_rule = evaluate_platform_deviations(deviations, errors)

        # Optional dual-diff source (#93): step-4 dual-machine differential
        # output, judged here only as a final verdict (absent -> dormant).
        dual_rule = evaluate_dual_diff_results(workspace, errors)

        # Rule 2 (semantic data parity).
        data_rule = evaluate_data_parity(workspace, denominators, errors)

        # Rule 5 (environment chain) + final builds (needed by rule 4d).
        h4env_rule, environments = evaluate_h4env_chain(workspace, input_lock, errors)
        input_lock_path = workspace / "stage-04-input-lock.json"
        input_lock_sha256 = sha256_file(input_lock_path)
        project = workspace / "harmony-project"
        require(project.is_dir(), "Phase 4 harmony-project is missing")
        source_snapshot_sha256 = project_snapshot_digest(project)
        build_ids = sorted(args.build_id)
        builds, artifact_hashes = collect_final_builds(
            workspace, build_ids, environments, ownership,
            input_lock_sha256, source_snapshot_sha256,
        )
        finalize_h4env_status(h4env_rule, len(builds), len(environments))

        # Surface-contract thin table (H) must be fully PASS.
        surface_rows = read_csv(workspace / "surface-contract.csv")
        surface_rule = evaluate_surface_contract(surface_rows, denominators, errors)

        # Rule 4 (SOURCE_CONFIRM floors) after the build set is known.
        source_rule, _floors_detail = evaluate_source_confirm_floor(
            workspace, denominators, surface_rows, sorted(builds), errors
        )

        # Rule 6 (visual fidelity, conditionally activated by the Phase 2
        # visual-memory baseline; dormant = PASS with activated=false).
        visual_rule = evaluate_visual_fidelity(
            workspace, run_dir, denominators, errors
        )

        validate_attempt_ledger_optional(workspace, errors)
        if open_rework_count(workspace):
            errors.append(f"Phase 4 still has open rework: {open_rework_count(workspace)}")

        rules = {
            "runtime_assertions": runtime_rule,
            "data_parity": data_rule,
            "platform_deviations": deviation_rule,
            "dual_diff": dual_rule,
            "source_confirm_floor": source_rule,
            "h4env_chain": h4env_rule,
            "visual_fidelity": visual_rule,
            "must_read_receipt": must_read_rule,
        }
        report = build_candidate_report(
            workspace,
            str(input_lock.get("run_id") or phase_manifest.get("run_id")),
            work_order_id,
            reviewer,
            input_lock_sha256,
            source_snapshot_sha256,
            sorted(build_ids),
            artifact_hashes,
            rules,
            surface_rule,
            deviation_rule,
            source_rule,
            errors,
        )
        if report["verdict"] != "PASS":
            raise ValueError(
                "Stage-4 v4 rules are not all PASS: "
                + "; ".join(errors[:10])
            )

        report_path = workspace / "stage-04-gate-report.json"
        closure_path = workspace / "stage-04-closure-manifest.sha256"
        closed_path = workspace / "CLOSED"
        candidate_paths = [report_path, closure_path, closed_path]
        atomic_json(report_path, report)
        atomic_text(closure_path, closure_manifest_text(workspace))
        atomic_text(closed_path, sha256_file(report_path) + "\n")

        controller_validator = (
            Path(__file__).resolve().parents[2]
            / "android-harmony-migration-controller" / "scripts" / "validate_gate.py"
        )
        require(controller_validator.is_file(),
                f"Controller Gate 4 validator is missing: {controller_validator}")
        audit = subprocess.run(
            [
                sys.executable, str(controller_validator), "--run-dir", str(run_dir),
                "--phase", "4",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
            check=False,
        )
        if audit.returncode != 0:
            detail = audit.stderr.strip() or audit.stdout.strip()
            raise ValueError(f"Independent controller Gate 4 pre-seal audit failed: {detail[:4000]}")
        controller_report = json.loads(audit.stdout)
        require(isinstance(controller_report, dict) and controller_report.get("verdict") == "PASS"
                and not controller_report.get("errors"),
                "Independent controller Gate 4 pre-seal audit did not return PASS")

        make_tree_read_only(workspace)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as exc:
        remove_candidate_outputs(candidate_paths)
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
