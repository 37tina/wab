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
  // ---- colors (light + dark variants; sources annotated inline) ----
  static readonly colors: Record<string, string> = {
    background: '#FEFBFF',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:70
    backgroundDark: '#1B1B1F',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:34
    pageBackground: '#F3EDF7',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:87
    pageBackgroundDark: '#211F26',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:51
    surface: '#FCF7FF',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:88
    surfaceDark: '#292730',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:52
    elevatedSurface: '#FCF7FF',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:89
    elevatedSurfaceDark: '#302E38',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:53
    onBackground: '#1B1B1F',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:71
    onBackgroundDark: '#E3E2E6',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:35
    onBackgroundVariant: '#44464F',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:75
    onBackgroundVariantDark: '#C5C6D0',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:39
    onPrimary: '#FFFFFF',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:58
    onPrimaryDark: '#002D6E',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:22
    primary: '#0058CA',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:57
    primaryDark: '#B0C6FF',  // app/src/main/java/com/capyreader/app/ui/theme/colorschemes/TachiyomiColorScheme.kt:21
    scrim: '#66000000',  // platform-default
    scrimDark: '#66000000',  // platform-default
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
