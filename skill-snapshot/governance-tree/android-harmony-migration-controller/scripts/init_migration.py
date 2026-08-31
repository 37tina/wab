#!/usr/bin/env python3
"""Create an immutable controller workspace for one migration run.

Run creation mode (default):
  init_migration.py --output <dir> --project-root <dir> --project-name <name>

Skill-freeze refresh mode (governance lightening, task #40):
  init_migration.py --refresh-freeze <run-dir> [--note <rationale>] [--decided-by <actor>]

Run close mode (TOOL_GAP freeze semantics, batch 4 #87):
  init_migration.py --close-run <run-dir> --note <rationale> [--decided-by <actor>]

The refresh mode replaces the former manual three-step revision (recompute the
skill-freeze manifest, update run-manifest.json, append a decision-log row)
with one command and prints the required Gate recheck hint. Refreshing is only
legal while the run has not started (run_status INIT) or has finished
(run_status CLOSED); an IN_MIGRATION run is refused with the TOOL_GAP remedy
(close the run, fix the skill, start a new run).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from _run_status import assert_refresh_freeze_allowed, transition_run_status


SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = SKILL_ROOT.parent
ASSETS = SKILL_ROOT / "assets"

# Skills frozen for the entire run. Their scripts, references, assets, evals,
# security trees plus SKILL.md and manifest.json are hashed at run init time;
# validate_gate.py / audit_delivery.py re-hash and compare at every entry.
FROZEN_SKILLS = (
    "android-harmony-migration-controller",
    "android-migration-inventory",
    "harmonyos-migration-scaffold",
    "harmonyos-feature-implementation",
)
FROZEN_SKILL_DIRS = ("scripts", "references", "assets", "evals", "security")
FROZEN_SKILL_FILES = ("SKILL.md", "manifest.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_skill_freeze_manifest() -> tuple[str, str]:
    """Hash every frozen skill file and return (manifest text, manifest sha256).

    Each line follows sha256sum style: `<sha256>  <skill-name>/<path relative to
    the skill root>`, sorted by path. The manifest itself is hashed so that
    run-manifest.json pins the whole snapshot with one digest.
    """
    entries: list[tuple[str, Path]] = []
    for skill_name in FROZEN_SKILLS:
        skill_root = SKILLS_ROOT / skill_name
        for directory_name in FROZEN_SKILL_DIRS:
            directory = skill_root / directory_name
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*")):
                # 字节码产物平台相关，绝不入冻结清单（否则跨机校验必败）
                if "__pycache__" in path.parts or path.suffix == ".pyc":
                    continue
                if path.is_file():
                    entries.append((f"{skill_name}/{path.relative_to(skill_root).as_posix()}", path))
        for file_name in FROZEN_SKILL_FILES:
            path = skill_root / file_name
            if path.is_file():
                entries.append((f"{skill_name}/{file_name}", path))

    entries.sort(key=lambda entry: entry[0])
    lines = [f"{sha256_of_file(path)}  {key}" for key, path in entries]
    manifest_text = "\n".join(lines) + "\n"
    manifest_digest = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    return manifest_text, manifest_digest


def slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").upper()
    return normalized[:32] or "PROJECT"


def render_template(name: str, replacements: dict[str, str]) -> str:
    """Replace placeholders as parsed JSON values so Windows paths remain escaped."""
    value = json.loads((ASSETS / name).read_text(encoding="utf-8"))

    def replace(item: object) -> object:
        if isinstance(item, dict):
            return {key: replace(child) for key, child in item.items()}
        if isinstance(item, list):
            return [replace(child) for child in item]
        if isinstance(item, str):
            for key, replacement in replacements.items():
                item = item.replace(key, replacement)
        return item

    return json.dumps(replace(value), ensure_ascii=False, indent=2)


def refresh_skill_freeze(run_dir: Path, note: str, decided_by: str) -> int:
    """One-shot skill-freeze revision: recompute, repin, and log (task #40).

    Replaces the manual three-step revision (recompute the freeze manifest,
    update run-manifest.json, append a decision-log row) with a single
    command. The revision is recorded in controller/decision-log.csv and the
    caller must re-run validate_gate.py afterwards (hint printed).
    """
    run_input = run_dir
    if run_input.is_symlink():
        raise ValueError("Migration run must not be a symbolic link")
    run_dir = run_input.resolve()
    run_manifest_path = run_dir / "run-manifest.json"
    if not run_dir.is_dir() or not run_manifest_path.is_file():
        raise ValueError(f"Not a migration run directory: {run_dir}")
    try:
        manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read run-manifest.json: {exc}") from exc
    if not isinstance(manifest, dict) or not manifest.get("run_id"):
        raise ValueError("run-manifest.json has no run_id; refusing to refresh")

    # TOOL_GAP freeze semantics (batch 4 #87): a run that is already in
    # migration must never silently re-pin its skill freeze. Only INIT (not
    # started) and CLOSED (finished) runs may refresh.
    assert_refresh_freeze_allowed(run_dir)

    # 1) recompute the skill-freeze manifest over the live skill trees
    freeze_text, freeze_digest = build_skill_freeze_manifest()
    freeze_path = run_dir / "controller" / "skill-freeze-manifest.sha256"
    if not freeze_path.is_file():
        raise ValueError(f"skill-freeze-manifest.sha256 is missing: {freeze_path}")

    # 2) repin the freeze manifest (it is sealed read-only at init time)
    os.chmod(freeze_path, 0o644)
    try:
        freeze_path.write_text(freeze_text, encoding="utf-8")
    finally:
        os.chmod(freeze_path, 0o444)

    # 3) update run-manifest.json with the new freeze digest
    previous_digest = manifest.get("skill_freeze_manifest_sha256")
    manifest["skill_freeze_manifest_sha256"] = freeze_digest
    run_manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 4) append the revision to the controller decision log
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    decision_id = f"DEC-{stamp}-{uuid.uuid4().hex[:6].upper()}"
    rationale = note.strip() or "skill freeze manifest refreshed after approved skill revision"
    decision_log = run_dir / "controller" / "decision-log.csv"
    with decision_log.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                decision_id,
                utc_now(),
                "SKILL_FREEZE_REFRESH",
                manifest.get("run_id", ""),
                "",
                "REFRESHED",
                rationale,
                decided_by,
                "",
            ]
        )

    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "decision_id": decision_id,
                "previous_skill_freeze_manifest_sha256": previous_digest,
                "skill_freeze_manifest_sha256": freeze_digest,
            },
            ensure_ascii=False,
        )
    )
    print(
        "Gate recheck required: re-run "
        f"python {Path(__file__).with_name('validate_gate.py').name} "
        f"--run-dir {run_dir} --phase <current-phase> --write"
    )
    return 0


def close_run(run_dir_input: Path, note: str, decided_by: str) -> int:
    """Close a run without a Gate 4 PASS (TOOL_GAP disposal, batch 4 #87).

    Marks the run as CLOSED so that the skill trees may be revised and the
    freeze manifest re-pinned with --refresh-freeze. The disposal is recorded
    in controller/decision-log.csv; a rationale (--note) is mandatory because
    closing an in-migration run voids its remaining phases.
    """
    if run_dir_input.is_symlink():
        raise ValueError("Migration run must not be a symbolic link")
    run_dir = run_dir_input.resolve()
    run_manifest_path = run_dir / "run-manifest.json"
    if not run_dir.is_dir() or not run_manifest_path.is_file():
        raise ValueError(f"Not a migration run directory: {run_dir}")
    rationale = note.strip()
    if not rationale:
        raise ValueError("--note <rationale> is required with --close-run (TOOL_GAP disposal must be justified)")
    decision_id = transition_run_status(
        run_dir,
        "CLOSED",
        decision_type="RUN_DISPOSAL",
        decision="CLOSED",
        rationale=rationale,
        decided_by=decided_by,
    )
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "run_status": "CLOSED",
                "decision_id": decision_id or None,
            },
            ensure_ascii=False,
        )
    )
    print(
        "Run closed; the skill trees may now be revised and the freeze "
        f"manifest re-pinned via --refresh-freeze {run_dir}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Directory that will contain migration runs")
    parser.add_argument("--project-root", help="Absolute or relative Android project root")
    parser.add_argument("--project-name")
    parser.add_argument("--run-id", help="Optional explicit run ID; must not already exist")
    parser.add_argument(
        "--refresh-freeze",
        metavar="RUN_DIR",
        help="One-shot skill-freeze revision for an existing run (task #40)",
    )
    parser.add_argument(
        "--note",
        default="",
        help="Rationale recorded in the decision log (used with --refresh-freeze)",
    )
    parser.add_argument(
        "--decided-by",
        default="migration-controller-agent",
        help="Actor recorded in the decision log (used with --refresh-freeze)",
    )
    parser.add_argument(
        "--close-run",
        metavar="RUN_DIR",
        help="Close a run without Gate 4 PASS (TOOL_GAP disposal, batch 4 #87); requires --note",
    )
    args = parser.parse_args()

    if args.close_run:
        if any((args.output, args.project_root, args.project_name, args.run_id, args.refresh_freeze)):
            parser.error("--close-run cannot be combined with other modes")
        try:
            return close_run(
                Path(args.close_run).expanduser(), args.note, args.decided_by
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))

    if args.refresh_freeze:
        if any((args.output, args.project_root, args.project_name, args.run_id)):
            parser.error("--refresh-freeze cannot be combined with run creation arguments")
        try:
            return refresh_skill_freeze(
                Path(args.refresh_freeze).expanduser(), args.note, args.decided_by
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))

    missing = [
        flag
        for flag, value in (
            ("--output", args.output),
            ("--project-root", args.project_root),
            ("--project-name", args.project_name),
        )
        if not value
    ]
    if missing:
        parser.error(f"Run creation requires: {', '.join(missing)} (or pass --refresh-freeze)")

    project_root = Path(args.project_root).expanduser().resolve()
    if not project_root.is_dir():
        parser.error(f"Android project root does not exist: {project_root}")

    output_input = Path(args.output).expanduser().absolute()
    if output_input.is_symlink():
        parser.error("Output root must not be a symbolic link")
    output_root = output_input.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"MIG-{stamp}-{uuid.uuid4().hex[:6].upper()}"
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{2,79}", run_id):
        parser.error("Run ID may contain only uppercase letters, numbers, dot, underscore, and hyphen")

    final_dir = output_root / run_id
    if final_dir.exists():
        parser.error(f"Run already exists; overwrite is prohibited: {final_dir}")

    created_at = utc_now()
    replacements = {
        "__RUN_ID__": run_id,
        "__PROJECT_ID__": slug(args.project_name),
        "__PROJECT_ROOT__": str(project_root),
        "__CREATED_AT__": created_at,
    }

    with tempfile.TemporaryDirectory(prefix=f".{run_id}-", dir=output_root) as temp_name:
        temp_dir = Path(temp_name)
        controller = temp_dir / "controller"
        controller.mkdir()

        scope_text = render_template("scope.template.json", replacements)
        json.loads(scope_text)
        (controller / "scope.json").write_text(scope_text + "\n", encoding="utf-8")

        for source, target in (
            ("task-ledger.template.csv", "task-ledger.csv"),
            ("decision-log.template.csv", "decision-log.csv"),
            ("rework-log.template.csv", "rework-log.csv"),
            ("work-order-registry.template.csv", "work-order-registry.csv"),
            ("evidence-anchor-registry.template.csv", "evidence-anchor-registry.csv"),
            ("phase4-attempt-ledger.template.csv", "phase4-attempt-ledger.csv"),
            ("team-execution-registry.template.csv", "team-execution-registry.csv"),
        ):
            shutil.copyfile(ASSETS / source, controller / target)

        gate_text = render_template("gate-report.template.json", replacements)
        json.loads(gate_text)
        (controller / "gate-report.json").write_text(gate_text + "\n", encoding="utf-8")

        # Run-time skill freeze: snapshot the four skill trees as a read-only
        # sha256sum-style manifest. validate_gate.py and audit_delivery.py
        # re-hash the live skill trees against this manifest at every entry.
        freeze_text, freeze_digest = build_skill_freeze_manifest()
        freeze_path = controller / "skill-freeze-manifest.sha256"
        freeze_path.write_text(freeze_text, encoding="utf-8")
        os.chmod(freeze_path, 0o444)

        manifest = {
            "run_id": run_id,
            "project_id": replacements["__PROJECT_ID__"],
            "project_root": str(project_root),
            "created_at": created_at,
            "controller_skill": "android-harmony-migration-controller",
            "status": "IN_PROGRESS",
            "skill_freeze_manifest_sha256": freeze_digest,
        }
        (temp_dir / "run-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        # TOOL_GAP freeze semantics (batch 4 #87): INIT -> IN_MIGRATION
        # (first phase-2+ work order) -> CLOSED (Gate 4 PASS or disposal).
        # Kept OUTSIDE run-manifest.json on purpose: inventory fail-closes
        # any run whose run-manifest hash drifts after the Phase 1 PASS.
        (controller / "run-status.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_status": "INIT",
                    "updated_at": created_at,
                    "history": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        temp_dir.rename(final_dir)

    print(json.dumps({"run_id": run_id, "run_dir": str(final_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
