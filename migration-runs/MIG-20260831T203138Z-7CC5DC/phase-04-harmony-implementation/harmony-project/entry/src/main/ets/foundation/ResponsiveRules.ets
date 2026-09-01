// Foundation (Phase 3 native UI base): responsive-layout rule declarations.
//
// Pure declarations, no business logic. Phase 3 freezes the breakpoint
// ladder (compact/medium/expanded, HarmonyOS default widths in vp) and the
// grid columns used by adaptive containers; Phase 4 consumes these tokens
// when wiring adaptive layouts. Registered by public-ui.capy-01
// (RT-P3-0002) to complete the nine public-UI foundation categories.

export class ResponsiveRules {
  // Breakpoint ladder (vp widths; ArkUI default breakpoints).
  static readonly breakpoints: Record<string, number> = {
    compact: 600,
    medium: 840,
    expanded: 1440,
  };
  // Grid column counts per breakpoint.
  static readonly gridColumns: Record<string, number> = {
    compact: 4,
    medium: 8,
    expanded: 12,
  };
  // Pane behavior: list/detail adaptation for wide screens
  // (Android w600dp table use the two-pane Articles layout).
  static readonly twoPaneMinWidthVp: number = 840;
}
