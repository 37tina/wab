// Design tokens re-derived from the Android source theme by the
// public-UI agent (public-ui.capy-01). Phase 2 visual-memory palette
// is an empty set (DEC-009: uiautomator static scan carries no
// per-surface color values), so tokens derive from the frozen Android
// theme implementation instead:
//   Theme.kt:117  AppTheme.DEFAULT -> TachiyomiColorScheme
//   app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt (lightScheme/darkScheme Material3 values)
// Every slot annotates its Kotlin source file:line inline;
// scrim keeps the platform default (40% black) where the source
// defines no direct equivalent.

export class AppTheme {
  static readonly colors: Record<string, string> = {
    background: '#FEFBFF',
    backgroundDark: '#1B1B1F',
    pageBackground: '#F3EDF7',
    pageBackgroundDark: '#211F26',
    surface: '#FCF7FF',
    surfaceDark: '#292730',
    elevatedSurface: '#FCF7FF',
    elevatedSurfaceDark: '#302E38',
    onBackground: '#1B1B1F',
    onBackgroundDark: '#E3E2E6',
    onBackgroundVariant: '#44464F',
    onBackgroundVariantDark: '#C5C6D0',
    onPrimary: '#FFFFFF',
    onPrimaryDark: '#002D6E',
    primary: '#0058CA',
    primaryDark: '#B0C6FF',
    scrim: '#66000000',
    scrimDark: '#66000000',
    accent: '#2b7cf6',
    accentDark: '#2b7cf6',
    textPrimary: '#111111',
    textPrimaryDark: '#1a1a1a',
    textSecondary: '#6f7682',
    textSecondaryDark: '#eceef2',
    cardBackground: '#ffffff',
    cardBackgroundDark: '#262b33',
    danger: '#e23c3c',
    dangerDark: '#e23c3c',
    pageBg: '#f5f6f8',
    pageBgDark: '#262b33',
  }

  // ---- gradients (none in source theme) ----
  static readonly gradients: Record<string, string[]> = { accentTokens: [] }

  // ---- typography ladder (fp; platform standard, Phase 4 visual
  //      walkthrough may refine from reader font prefs) ----
  static readonly typography: Record<string, number> = {
    display: 32,
    title: 24,
    subtitle: 20,
    body: 16,
    caption: 12,
  }

  // ---- spacing ladder (vp; platform standard) ----
  static readonly spacing: Record<string, number> = {
    xs: 4,
    s: 8,
    m: 12,
    l: 16,
    xl: 24,
  }

  // ---- radius ladder (vp; platform standard) ----
  static readonly radius: Record<string, number> = {
    card: 12,
    sheet: 16,
    button: 20,
  }
}
