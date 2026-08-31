# Observable consistency contract

Phase 4 is a native implementation guided by Behavior Contracts, not a pixel-level redesign. `migration-unit-contracts.json` is generated from the frozen Phase 2 Behavior Contracts/static analysis and the accepted Phase 3 mapping. The governing standard is the Core equivalence contract:

> UI structure and interaction may be adapted to HarmonyOS native conventions, but user intent, stored data, business computation, state transitions, observable results, persistence and side effects must remain semantically equivalent.

## Non-waivable dimensions

The implementation agent must preserve all six behavior-equivalence dimensions of the Core equivalence contract:

- stored_data: every stored record, field, and dataset remains semantically equivalent;
- business_computation: every business rule, calculation, and derived result remains equivalent;
- state_transition: every state transition, with its entry condition and action, remains equivalent;
- observable_result: every user-observable result of a behavior remains semantically equivalent;
- persistence: persistence expectations across restarts, sessions, and re-entry remain equivalent;
- side_effect: every side effect (system capability, notification, sync, import/export, rollback, ...) remains equivalent.

User intent, feature/entry completeness, and the semantic content of business assets are likewise non-waivable. The agent may not delete, merge, replace, hide, or compress any behavioral item merely because a simpler Harmony implementation is available: no missing control, lost business branch, altered data result, broken transition, or omitted side effect.

## Native adaptation boundary

UI structure, carriers (page, dialog, sheet, bottom bar, navigation), geometry, and interaction flows may be adapted to HarmonyOS native conventions using ArkUI native components. Visual and geometric differences against the Android source are therefore permitted and are not gate criteria; "native feel" is judged by the single human acceptance after Gate 4, not by pixel or geometry comparison. Content-bearing text and brand assets keep semantic consistency, while platform chrome and decorative icons may use Harmony-native implementations.

Harmony-native APIs and architecture are encouraged behind the observable boundary. They may improve internal state management, lifecycle handling, performance, accessibility, or platform integration, provided the six behavior dimensions remain equivalent.

## Machine enforcement

`capture_state.py` computes assertion verdicts from `actual`, `expected`, and a frozen operator. An external command's `status: PASS` is never authoritative. The state plan must bind every expected observable result to its Behavior Contract BC-ID and must cover all applicable non-waivable dimensions of the contract.

Required events and transitions must appear in raw operation traces containing the executed action and before/after snapshots; a self-declared ID array is rejected. Dual-end click paths may differ, but the compared stored data, computation, state transitions, observable results, persistence, and side effects must match. Local validation and controller Gate 4 independently recompute the verification set from Phase 2/3 artifacts, so editing the contract and its hash files together does not bypass the gate.

Automatic correction is limited to one initial execution plus two repair executions per migration unit. Every execution is controller-anchored before commands run. When the budget is exhausted, stop changing code and emit a grouped error report for the later human-assisted repair stage.
