// Design tokens generated deterministically by init_scaffold (emit_theme_layer) from the
// Phase 2 visual memory: /Users/rainyday/Desktop/finale/migration-runs/MIG-20260831T052941Z-07D28A/phase-02-android-inventory/visual-memory.json
// Palette basis: global (1 swatches); every color token annotates its source
// swatch name inline. Slots without palette data fall back to
// platform defaults and are annotated as platform-default.
// Typography: visual-memory has no font-size data
// (text_sizes.available=false: uiautomator dump carries no font-size attribute (Compose nodes expose no textSize); Phase 3 theme layer should derive sizes from design tokens / Phase 4 visual walkthrough)
// values follow the platform standard ladder in fp units.
// Spacing/radius: platform standard ladders (uiautomator key_bounds carries
// bounds only, no corner-radius attribute; radius values follow platform
// guidance scaled to key_bounds control sizes).

export class AppTheme {
  // ---- colors (light + dark variants; sources annotated inline) ----
  static readonly colors: Record<string, string> = {
    background: '#FFFFFF',  // platform-default
    pageBackground: '#F1F3F5',  // platform-default
    surface: '#FFFFFF',  // platform-default
    elevatedSurface: '#FFFFFF',  // platform-default
    onBackground: '#182431',  // platform-default
    onBackgroundVariant: '#6B7280',  // platform-default
    onPrimary: '#FFFFFF',  // platform-default
    primary: '#007DFF',  // platform-default
    scrim: '#66000000',  // platform-default
    backgroundDark: '#000000',  // inverted:platform-default
    pageBackgroundDark: '#0A0C0E',  // inverted:platform-default
    surfaceDark: '#000000',  // inverted:platform-default
    elevatedSurfaceDark: '#000000',  // inverted:platform-default
    onBackgroundDark: '#CEDAE7',  // inverted:platform-default
    onBackgroundVariantDark: '#7F8694',  // inverted:platform-default
    onPrimaryDark: '#000000',  // inverted:platform-default
    primaryDark: '#007DFF',  // platform-default
    scrimDark: '#66FFFFFF',  // inverted:platform-default
  }

  // ---- gradients (none in visual memory) ----
  static readonly gradients: Record<string, string[]> = { accentTokens: [] }

  // ---- typography ladder (fp) ----
  static readonly typography: Record<string, number> = {
    display: 32,
    title: 24,
    subtitle: 20,
    body: 16,
    caption: 12,
  }

  // ---- spacing ladder (vp) ----
  static readonly spacing: Record<string, number> = {
    xs: 4,
    s: 8,
    m: 12,
    l: 16,
    xl: 24,
  }

  // ---- radius ladder (vp) ----
  static readonly radius: Record<string, number> = {
    card: 12,
    sheet: 16,
    button: 20,
  }
}
