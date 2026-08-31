#!/usr/bin/env python3
"""Run lifecycle status machine backing the TOOL_GAP freeze semantics (batch 4 #87).

Design note (why the status lives in ``controller/run-status.json`` and not in
``run-manifest.json``): android-migration-inventory fail-closes any run whose
run-manifest hash drifts after the Phase 1 PASS, i.e. the run manifest is
immutable once the run is live. The controller therefore keeps the lifecycle
marker in its own file. ``controller/run-status.json`` carries:

- ``run_status``: one of INIT / IN_MIGRATION / CLOSED;
- ``updated_at`` / ``history``: audit trail (each transition is also appended
  to controller/decision-log.csv).

Semantics:

- ``INIT``         run created, no phase work order issued yet;
- ``IN_MIGRATION`` first specialist work order issued (phase >= 2);
- ``CLOSED``       terminal — Gate 4 machine PASS (validate_gate --phase 4
                  --write) or an explicit TOOL_GAP disposal
                  (``init_migration.py --close-run``).

The status decides whether ``init_migration.py --refresh-freeze`` may silently
re-pin the skill-freeze manifest: refreshing is allowed only while the run has
not started (INIT) or has already finished (CLOSED). A run in IN_MIGRATION
whose frozen skill hashes drifted must surface as a TOOL_GAP error — the only
sanctioned exit is: close/void the run, fix the skill, start a new run.

Historical runs without the file are classified by inference
(read_run_status): Gate 4 PASS -> CLOSED, any issued work order ->
IN_MIGRATION, otherwise INIT. The inference is deliberately conservative.
"""

from __future__ import annotations

import csv
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

RUN_STATUS_VALUES = ("INIT", "IN_MIGRATION", "CLOSED")
RUN_STATUS_RELATIVE = "controller/run-status.json"

# Legal forward transitions; CLOSED is terminal.
_TRANSITIONS = {
    "INIT": {"IN_MIGRATION", "CLOSED"},
    "IN_MIGRATION": {"CLOSED"},
    "CLOSED": set(),
}

TOOL_GAP_REMEDY = (
    "TOOL_GAP：正式 run（IN_MIGRATION）期间 Skill 冻结不允许静默刷新。"
    "处置路径：终止/关闭本 run（init_migration.py --close-run 或走完 Gate 4）→ "
    "登记 skill-bug-ledger 台账并修复 Skill → 重新开 run。"
    "refresh-freeze 仅在 run_status 为 INIT（尚未开始）或 CLOSED（已结束）时允许。"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_run_id(run_dir: Path) -> str:
    path = run_dir / "run-manifest.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read run-manifest.json: {exc}") from exc
    if not isinstance(value, dict) or not value.get("run_id"):
        raise ValueError("run-manifest.json is not a valid run manifest")
    return str(value["run_id"])


def _has_issued_work_order(run_dir: Path) -> bool:
    orders = run_dir / "controller" / "work-orders"
    if not orders.is_dir():
        return False
    return any(
        re.fullmatch(r"WO-PHASE-0[2-6]-[A-Z0-9]+\.json", entry.name)
        for entry in orders.iterdir()
        if entry.is_file()
    )


def _gate4_passed(run_dir: Path) -> bool:
    gate_path = run_dir / "controller" / "gate-report.json"
    try:
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(gate, dict) and gate.get("phase") == 4 and gate.get("verdict") == "PASS"


def read_run_status(run_dir: Path | str) -> str:
    """Return the run status, inferring one when run-status.json is absent."""
    run_dir = Path(run_dir)
    status_path = run_dir / RUN_STATUS_RELATIVE
    if status_path.is_file():
        try:
            record = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            record = None
        if isinstance(record, dict) and record.get("run_status") in RUN_STATUS_VALUES:
            return record["run_status"]
    if _gate4_passed(run_dir):
        return "CLOSED"
    if _has_issued_work_order(run_dir):
        return "IN_MIGRATION"
    return "INIT"


def _ensure_status_file(run_dir: Path, run_id: str, status: str) -> None:
    """Materialise run-status.json if absent (e.g. inferred historical run)."""
    status_path = run_dir / RUN_STATUS_RELATIVE
    if status_path.is_file():
        return
    record = {"run_id": run_id, "run_status": status, "updated_at": utc_now(), "history": []}
    descriptor, temp_name = tempfile.mkstemp(prefix=".run-status.", suffix=".tmp", dir=status_path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, status_path)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass


def _append_decision(
    run_dir: Path, run_id: str, decision_type: str, decision: str, rationale: str, decided_by: str
) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    decision_id = f"DEC-{stamp}-{uuid.uuid4().hex[:6].upper()}"
    log_path = run_dir / "controller" / "decision-log.csv"
    with log_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [decision_id, utc_now(), decision_type, run_id, "", decision, rationale, decided_by, ""]
        )
    return decision_id


def transition_run_status(
    run_dir: Path | str,
    new_status: str,
    *,
    decision_type: str = "RUN_STATUS_TRANSITION",
    decision: str = "",
    rationale: str = "",
    decided_by: str = "migration-controller-agent",
    allow_reentrant: bool = True,
) -> str:
    """Atomically advance run_status; returns the recorded decision id.

    ``allow_reentrant=True`` permits an already-satisfied target (the phased
    writers may fire more than once, e.g. Gate 4 rechecked after CLOSE). Any
    illegal backward transition raises ValueError regardless. Only
    ``controller/run-status.json`` is mutated; run-manifest.json stays
    immutable after the Phase 1 PASS by design.
    """
    if new_status not in RUN_STATUS_VALUES:
        raise ValueError(f"Unknown run status: {new_status}")
    run_dir = Path(run_dir)
    run_id = _load_run_id(run_dir)
    current = read_run_status(run_dir)
    if new_status == current:
        if allow_reentrant:
            _ensure_status_file(run_dir, run_id, current)
            return ""
        raise ValueError(f"Run status is already {current}")
    if new_status not in _TRANSITIONS[current]:
        raise ValueError(
            f"Illegal run status transition {current} -> {new_status}; "
            f"legal transitions: INIT -> IN_MIGRATION -> CLOSED"
        )
    status_path = run_dir / RUN_STATUS_RELATIVE
    try:
        record = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        record = {"run_id": run_id, "run_status": current, "updated_at": None, "history": []}
    if not isinstance(record, dict):
        record = {"run_id": run_id, "run_status": current, "updated_at": None, "history": []}
    history = record.get("history") if isinstance(record.get("history"), list) else []
    history.append({"from": current, "to": new_status, "at": utc_now(), "why": rationale or decision_type})
    record.update({"run_id": run_id, "run_status": new_status, "updated_at": utc_now(), "history": history})
    descriptor, temp_name = tempfile.mkstemp(prefix=".run-status.", suffix=".tmp", dir=status_path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, status_path)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass
    return _append_decision(
        run_dir,
        run_id,
        decision_type,
        decision or f"RUN_STATUS_{new_status}",
        rationale or f"run_status transitioned to {new_status}",
        decided_by,
    )


def assert_refresh_freeze_allowed(run_dir: Path | str) -> str:
    """Gate --refresh-freeze on the run status; returns the status on success."""
    status = read_run_status(run_dir)
    if status == "IN_MIGRATION":
        raise ValueError(
            "refusing --refresh-freeze: run is IN_MIGRATION (work orders issued, "
            "run not closed). " + TOOL_GAP_REMEDY
        )
    return status
