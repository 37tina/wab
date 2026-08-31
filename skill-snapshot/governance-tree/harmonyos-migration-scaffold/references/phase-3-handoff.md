# Phase 3 handoff: HarmonyOS-native UI foundation

Phase 3 is repositioned from "a runnable empty shell" to **the HarmonyOS-native UI foundation**: the navigation fabric, surface carriers, and shell discipline on which Phase 4 implements behavior-equivalent business logic.

## Core equivalence contract (shared)

> UI structure and interaction may be adapted to HarmonyOS native conventions, but user intent, stored data, business computation, state transitions, observable results, persistence and side effects must remain semantically equivalent.

Phase 3 may adapt structure/interaction to native conventions; the six business dimensions remain untouched until Phase 4 behavior verification.

## Upstream inputs (from Phase 2, hash-locked)

1. **Frozen closure chain** — `phase-2-closure.json`, `closure-report.json`, `closure-manifest.sha256`, inventory, evidence index, acceptance registry, asset package (unchanged contract, see [input-mapping-contract.md](input-mapping-contract.md)).
2. **Semantic structure (2.1, consumed when present)**:
   - `candidates/navigation-relations.candidates.csv` — page-to-page relations (`candidate_id, from_page_id, from_page_symbol, trigger, action, to_page_id, relation_type, source_ref`). This is the deterministic seed of the native route graph.
   - `behavior-contracts.csv` — one Behavior Contract per externally observable intent (`bc_id, feature_id, page_ref, user_intent, ...`). Phase 3 uses it only to confirm shell/landing coverage per page; it never implements a BC.
   - Missing semantic inputs are not an error: `init_scaffold.py main_gmi` falls back to the pre-2.1 input-only flow and records the fallback in `stage-03-input-lock.json`.

## Deterministic outputs (what Phase 3 must produce)

- **Native route graph** (`route-graph.json`) — nodes for every frozen Page-ID reachable in the navigation relations, directed edges carrying the original `relation_type`/`trigger`/`source_ref`, and one shell plan per node. No LLM-invented topology; every edge traces to a Phase 2 `source_ref`.
- **Page-shell seeds** — one ArkTS shell per route-graph node, containing only blank content, identity literals (Feature-ID/Page-ID/Page-Shell-ID), and foundation composition. Registered later by the navigation agent; seeds never register fake routes.
- **Foundation base** (`entry/src/main/ets/foundation/`) — `AppNavigationShell` (Navigation + NavPathStack + route-registry placeholder), `AppTabsShell` (bottom Tabs), `AppTopBar` (top bar + back), `AppDialogs` (CustomDialog / bindSheet), `AppListShell` (List + LazyForEach with empty/loading slots). These are the only permitted carriers for navigation chrome; drawing bottom bars, navigation stacks, or dialog/sheet chassis from scratch is prohibited.
- **Registries** — module/route/surface/public-UI/architecture/capability/asset registries as before; every row cites a real file.
- **Machine evidence** — build/install/launch and route/surface smoke from the frozen command line. Per-shell PNG evidence is an **optional diagnostic** in 2.1 `native-adaptive` runs (presence → full structural-integrity validation; absence → warning only) and remains mandatory in legacy `strict` runs.

## Red lines (unchanged)

- No ViewModels, business state, requests, persistence, fake/mock data, real adapters, or business buttons anywhere in Phase 3 output — foundation components included.
- No route for a non-routable surface; carriers (Dialog, Sheet, overlay, widget, external) keep their carrier kind.
- Models never approve or close Phase 3; the controller recomputes Gate 3 and stops at `WAITING_HUMAN_REVIEW`.

## Downstream handoff (to Phase 4)

- Phase 4 receives the sealed Phase 3 workspace: native route graph, shell seeds, foundation components, registries, and the frozen Phase 2 inputs — including `behavior-contracts.csv`, which remains the unit of truth for behavior verification (`RUNTIME_REQUIRED` BCs need dual-end equivalence evidence in Phase 4).
- Phase 4 implements business behavior inside the native foundation; it may not replace foundation carriers with custom chrome, may not restructure the route graph topology, and may not weaken the six equivalence dimensions.
- Advanced obligations and asset landing plans transfer unchanged; Phase 4 owns their implementation and evidence.
