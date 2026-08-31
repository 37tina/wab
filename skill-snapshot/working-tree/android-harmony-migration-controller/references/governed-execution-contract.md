# Governed execution contract

- `input_files: file-backed fixture`: Android project, frozen APK, scope, environments, specialist work orders, canonical stage reports, and worker receipts.
- `owner`: Android-Harmony Migration Maintainers.
- `review cadence`: every release and after any gate, work-order, role, or completion-claim change.
- `output contract`: one immutable migration run whose canonical Gate 1-4 reports and `audit_delivery.py` verdict are `PASS`, or one explicit `BLOCKED` result naming the failed check, evidence path, owner, and repair entry.
- `rollback boundary`: never rewrite source baselines, sealed evidence, old work orders, or closed reports. Revert only package-source changes through version control; supersede run artifacts with new IDs.

## Run-time skill freeze

- Freeze scope: after run initialization, all four skills (`android-harmony-migration-controller`, `android-migration-inventory`, `harmonyos-migration-scaffold`, `harmonyos-feature-implementation`) are frozen for the entire run, covering every file under `scripts/`, `references/`, `assets/`, `evals/`, `security/` plus `SKILL.md` and `manifest.json`. The frozen snapshot is `controller/skill-freeze-manifest.sha256` inside the run directory, and its digest is registered in `run-manifest.json` as `skill_freeze_manifest_sha256`.
- Prohibition: during a run, no role (controller, specialist, worker, or human) may modify any skill directory, Gate script, Gate criteria, or registry content inside the skills. Work-order, team-execution, and evidence registries under the run directory are still maintained by the existing controller scripts; what is forbidden is manual out-of-band rewriting of skill sources and validators.
- Defect handling: when a skill defect is discovered mid-run, the only lawful path is to append a record to the append-only skill bug ledger (`skill-bug-ledger.csv`, initialized from `assets/skill-bug-ledger.template.csv`), void the current run, fix the skill outside any live run, and then open a new run whose freeze snapshot captures the fix. Editing the frozen skill in place is never allowed.
- Enforcement: `validate_gate.py` and `audit_delivery.py` re-hash the live skill trees and compare them against `controller/skill-freeze-manifest.sha256` at every entry point. Any drift (changed, added, or missing file) is an immediate `FAIL`, with the error directing the operator to record the defect in the ledger, void the run, fix, and start a new run. Historical strict runs without a freeze manifest follow the legacy compatibility path and do not fail for missing 2.1 artifacts.

## Claim boundary

Skill governance reports prove package structure and regression coverage only. They never prove that an app migrated, built, ran, or preserved behavior. Only canonical migration scripts may grant a phase verdict. Provider telemetry, real CodeArts task authentication, independent blind review, and real-device runs remain `missing evidence` until their own artifacts exist.

## Routing boundary

Own full-workflow orchestration, phase transition, rework routing, and delivery audit. Hand Phase 2-only discovery to `$android-migration-inventory`, Phase 3-only scaffold work to `$harmonyos-migration-scaffold`, and authorized Phase 4 implementation to `$harmonyos-feature-implementation`. Never perform their specialist work under the controller identity.
