# Phase gates

The single equivalence standard for all four phases is the Core equivalence contract:

> UI structure and interaction may be adapted to HarmonyOS native conventions, but user intent, stored data, business computation, state transitions, observable results, persistence and side effects must remain semantically equivalent.

## Phase 1: freeze what migrates

Pass only when:

- Android project root exists, is at the exact declared clean Git commit, and has no untracked changes.
- The APK is structurally valid and its declared SHA-256 matches; app version, build, application ID, and build variant are frozen.
- The migration scope is frozen as four explicit sets: included/excluded feature scope, data scope, key business capabilities, and allowed platform substitutions (each substitution declares `capability`, `reason`, and `native_equivalence_allowed`).
- Included feature scope is non-empty and exclusions are explicit; key business capabilities and allowed platform substitutions are declared (native-adaptive runs).
- HarmonyOS target and the visual parity mode (`strict` or `native-adaptive`) are explicit; runs missing the mode field are treated as legacy `strict`.
- Every environment has the required account, seed data, network, emulator, API, locale, theme, timezone, and permission fields. Resolution and density DPI are recorded as reproducibility metadata for experiments only; they are never a quality condition of this gate.
- Exactly one `ENV-ID` is the baseline.
- Android CLI is mandatory and Layout Inspector is prohibited.
- Every frozen controller and Phase 2 actor ID is valid and distinct.
- No pending confirmation remains and an immutable Phase 2 work order is issued only after this gate passes.

## Phase 2: functional semantics and migration navigation

Pass only when:

- Phase 1 still passes.
- Every included feature has at least one Behavior Contract; every externally observable intent and key business branch identifiable in the source maps to exactly one Behavior Contract or has an explicit exclusion reason; every contract cites Android source `file:line`.
- Every high-impact Behavior Contract (`impact=high`, evidence class `RUNTIME_REQUIRED`) has 100% runtime evidence: a complete before/after state pair executed on the baseline environment, with a valid audit and closure chain.
- The Phase 2 closure report exists and says `PASS`.
- `evidence_chain_closed` is `true`.
- The baseline `ENV-ID` matches the controller scope.
- The final reviewer role is `coverage-checker-agent`.
- There are no critical open rechecks or critical pending confirmations.
- The inventory, Behavior Contract table, evidence index, and evidence directory exist.
- The coverage ledger exactly covers every included Feature-ID and applicable environment.
- Inventory and evidence lifecycle records are finalized as `REVIEWED` and `ACCEPTED`.
- Every active row declares either `["NONE_FOUND"]` or real Asset-IDs; every real asset is reviewed, referenced, archived, hashed, and covered exactly by the asset-package manifest and marker.
- `closure-manifest.sha256` and `CLOSED` bind every returned file; the controller recomputes the snapshot and rejects later writes.

The gate covers the full `included_features` set. If the user changes scope, freeze a new scope decision and issue a new work order before rerunning Phase 2.

## Phase 3: HarmonyOS native skeleton

Pass only when:

- Phase 1 and Phase 2 still satisfy their gates.
- A uniquely registered, immutable Phase 3 work order was issued by the frozen controller from Gate 2 `PASS`.
- Its six actor IDs are valid, mutually distinct, and different from all Phase 1/2 actors; actual creators, executor, lead, and reviewer match those assignments.
- `stage-03-input-lock.json` still matches the work order, frozen controller scope, Gate 2 snapshot, Phase 2 closure report/manifest/marker, reviewed inventory, acceptance/evidence indexes, both evidence-anchor records, and all three dependency/capability catalogs.
- The HENV freezes all nine category-specific executable paths and hashes, required argument tokens, success markers, and error markers; the selected HVER contains the actually executed preflight.
- The Phase 3 gate report says `PASS` and was issued by the frozen architecture acceptance agent.
- The report identifies one frozen `HENV-ID`, one sealed passing `HVER-ID`, the reviewed source snapshot, and built artifact hashes.
- The HVER `manifest.sha256` exactly covers its package, `COMMITTED` identifies that passing HVER, and every recorded log and evidence hash still matches.
- Architecture-map row count equals the frozen inventory row count.
- `asset-registry.csv` exactly covers the Phase 2 asset inventory with frozen hashes, scope links, safe module-local targets, unique symbols, explicit migration decisions, and READY status.
- Every in-scope feature has a module landing, and every requirement has a real shell or contract landing.
- Clean build creates or changes a structurally valid HAP; installation, launch, and route/surface smoke checks pass on all required devices.
- Every route/surface smoke result was generated by its recorded command into a new output path and exactly binds the frozen serial, bundle, route/surface, page, and shell.
- Current scaffold files and build artifacts still match the sealed snapshot and HVER hashes.
- No local or controller Phase 3 rework remains open, and no business implementation is present.
- `stage-03-closure-manifest.sha256` exactly covers the complete closed workspace, and `CLOSED` binds the final Stage 3 report.

Per-shell PNG evidence and human visual inspection are optional diagnostics in this phase; they are not pass conditions. They may be used to spot-check the native skeleton but never block or gate the phase.

Phase 3 does not authorize business implementation by itself; it only opens the next phase for a separately issued work order.

## Phase 4: native implementation plus behavior-equivalence verification

Pass only when:

- Phases 1–3 still pass under read-only controller revalidation.
- A uniquely registered Phase 4 work order was issued by the frozen controller from Gate 3 `PASS`; its four actors are mutually distinct and do not reuse a Phase 1–3 actor.
- `stage-04-input-lock.json` and its copied snapshots exactly match the work order, scope, immutable Gate 3 snapshot, Phase 2 closure/inventory/evidence/asset chain, Phase 3 closure/scaffold/registries, upstream Phase 3 work order, and every frozen HENV.
- Key-feature intent pass rate is 100%: every unique `RUNTIME_REQUIRED` Behavior Contract that must be verified has exactly one `PASS` verdict produced by the behavior comparator, and the denominator is non-zero. Dual-end click paths may differ; all applicable stored data, business computation, state transitions, observable results, persistence, and side effects must match.
- Data, state, persistence, and side-effect consistency are verified against the Behavior Contracts for every implemented feature.
- No placeholder, stub, or unfinished implementation remains in any delivered feature.
- Exactly one final HAP build succeeds from the exact current source snapshot on each required environment, and the HAP installs and launches successfully.
- Asset migration exactly covers the Phase 2/3 asset chain, and capability implementation exactly covers Phase 3 contracts.
- Local and controller Phase 4 rework ledgers contain the same closed tickets and fields; any non-closed ticket blocks the gate.
- The final report contains both `verdict: PASS` and `final_verdict: PASS`, identifies the frozen reviewer, work order, input lock, builds, source snapshot, artifact hashes, and exact counts.
- `stage-04-closure-manifest.sha256` exactly covers the closed workspace except the report, manifest, marker, locks/staging, caches, and generated project output; `CLOSED` contains the final report SHA-256.

"Native feel" is not a machine Gate 4 condition. It is accepted by exactly one human acceptance after Gate 4 (native-feel acceptance checklist); the machine Gate may record `native_review_status=PENDING`, and delivery requires that review to become `APPROVED`.

## Deprecated

`validate_phase5` / `validate_phase6` and their gate criteria are deprecated and no longer part of the four-phase model; they remain in the codebase only for legacy compatibility and will be removed in a future cleanup.
