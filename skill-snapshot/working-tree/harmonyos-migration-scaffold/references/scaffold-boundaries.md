# Scaffold boundaries

## Module truth

The starting tree comes from the locked ArkUI Stage template. Keep its `AppScope`, root build profile, `entry` module, entry Ability, main page profile, and hvigor configuration as real project files. Architecture work may extend these files, but it must not replace the project with an unrelated sample or leave template tokens unresolved.

Every module registry row cites a real module directory and build configuration inside `harmony-project/`. Record its layer, feature IDs, and declared module dependencies. `dependency-policy.json` defines allowed layer edges and forbidden placeholder/contract tokens.

The Phase 3 gate verifies ID validity, file existence, allowed dependency directions, and absence of cycles. The acceptance agent separately attests that the registry matches actual build configuration and imports.

## Asset landing plans

`asset-registry.csv` must exactly cover the real Phase 2 assets and preserve their archive paths, hashes, types, and Feature/Page/State associations. Each `READY` row is created by the frozen architecture lead and points to an existing registered module plus a safe future path below that module's `src/main/resources/`. Target paths are unique, and resource symbols are unique within a module.

The registry is architectural placement only. Do not add copied assets, conversions, recreations, visual-token maps, or an asset policy during Phase 3; Phase 4 consumes the frozen public-UI foundation and defines its own implementation policy.

## Native UI foundation

Phase 3 is not "an empty shell that launches"; it establishes the HarmonyOS-native UI base. The bundled template ships deterministic foundation components under `entry/src/main/ets/foundation/`:

- `AppNavigationShell.ets` — `Navigation` + `NavPathStack` routing shell with a route-registry placeholder.
- `AppTabsShell.ets` — bottom `Tabs` shell.
- `AppTopBar.ets` — top bar with native back behavior.
- `AppDialogs.ets` — `CustomDialog` / `bindSheet` shells.
- `AppListShell.ets` — `List` + `LazyForEach` shell with empty/loading slots.

Rules:

- When semantically applicable, navigation, bottom tabs, top bars, back behavior, Dialog/Sheet, and long lists must be built on these ArkUI-native carriers. Hand-drawing a bottom bar, a custom navigation stack, or a bespoke dialog/sheet/list chassis from scratch is prohibited.
- The native skeleton (route graph + page shells) is generated deterministically from the Phase 2 semantic structure (`candidates/navigation-relations.candidates.csv` + `behavior-contracts.csv`, when present); LLM free-form invention of navigation structure is prohibited. Missing inputs fall back to the pre-2.1 input-only flow.
- Foundation components are pure shells: no ViewModels, business state, requests, persistence, fake data, or business callbacks. The no-business-logic red line applies to them exactly as to page shells.
- Foundation components may only be referenced by page/surface shells and other foundation components during Phase 3.

## Page and surface shells

A page shell contains only:

- a blank content area carried by the native foundation (`Navigation`/`NavPathStack`, `Tabs`, `AppTopBar`, Dialog/Sheet shells, `List`/`LazyForEach`) when the Android carrier semantics call for it;
- a page-level navigation bar only when the Android page actually had one, and only via the native top-bar foundation;
- literal Feature-ID, Page-ID, Page-Shell-ID, and Route-ID or Surface-Shell-ID metadata;
- minimum route registration, opening, and back behavior needed by smoke tests.

It must not contain business components, ViewModels, domain models, requests, persistence, fake/mock data, business state, timers, business validation, or business buttons.

`ROUTE_PAGE` requires real route registration and runtime smoke success. A matching emulator screenshot is mandatory in legacy `strict` runs; in 2.1 `native-adaptive` runs it is an optional diagnostic — presence triggers the full structural-integrity check, absence yields a warning only. `VISUAL_SURFACE` requires a real component/surface file and instantiation smoke success, with the same screenshot rule; it must come from a test-only harness without creating a fake production route. A documentation-only mapping is invalid.

## Public UI

`public-ui-registry.csv` must cover color, typography, spacing, theme, page container, loading shell, empty shell, error shell, and responsive rules. Every row cites a real file. The loading, empty, and error shell symbols must not appear in business page/surface shell files during Phase 3.

## Capability contracts

Every seeded capability requirement must have one real contract file and symbol. Contracts may contain interface/type/enum/error declarations. They may not contain concrete adapter classes, I/O, SDK calls, network/storage operations, fake data, or implemented business methods.

If compilation would otherwise require an implementation, defer wiring; do not create a no-op production adapter and call it an interface.

Every `ADVANCED_SIDE_EFFECT` requirement originates from the frozen Phase 2 advanced inventory. Its contract must retain the originating Side-Effect-ID as `source_requirement_ref`. Dynamic surfaces and scenario tests remain in `advanced-obligations.json` for Phase 4 and do not justify fake Phase 3 routes or adapters.
