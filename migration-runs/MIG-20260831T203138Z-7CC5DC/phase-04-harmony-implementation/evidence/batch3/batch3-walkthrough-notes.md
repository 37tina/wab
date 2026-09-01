# Batch 3 walkthrough evidence (impl-lead.capy-01 R5, 2026-09-01)

## DC-1 fix (CDATA -> CDSECT) — VERIFIED
- Root cause confirmed: @ohos.xml emits CDATA sections as EventType CDSECT(=5),
  not TEXT; RssParser never accumulated description text -> empty summary ->
  reader "(no content)".
- Fix: RssParser.ets accumulates TEXT **and** CDSECT into currentText;
  stripHtml upgraded (block-tag spacing + entity decode, multi-line-safe
  char scan, no regex /s needed).
- Device proof: opened Ars article "The Bentley Supersports..." -> reader body
  shows "It's the lightest Bentley in 85 years." (dc1-reader-layout.json).
  Feed https://feeds.arstechnica.com/arstechnica/index is a CDATA feed.

## PD-1 (read/unread dot direction, Android contract) — VERIFIED
- List rows: unread = solid ●, read = hollow ○ (first row Bentley read -> ○,
  others ●; see b3-restart-dark-kept.png).
- Reader bottom bar flipped to same direction: unread ● / read ○
  (was inverted in batch 2 build).
- Extra fix: LazyForEach key now includes read/starred so rows re-render
  after status changes (batch2 build kept stale dots until filter switch).

## FEAT-SETTINGS — VERIFIED on device
- BC-0018: sidebar Settings -> PAGE-SETTINGSSCREEN; Display/General sections.
- BC-0019: Theme -> Dark: prefs app_theme=DARK/theme_mode=dark +
  setColorMode immediate; b3-settings-dark.png (dark) & restart kept
  (b3-restart-dark-kept.png).
- BC-0020: Sort order -> Oldest first: prefs article_list_sort_order=
  OLDEST_FIRST; on return list re-queried ASC (first row changed to oldest
  article "Cities terminate Flock contracts..."; bc0020-oldest-first-list.png).
- BC-0021: reader 'Aa' -> Article style panel (Small/Medium/Large +
  Align left/center) -> prefs article_font_size/article_title_text_alignment;
  Large applied live to body text.
- Probe: settings provider now emits real values:
  {"app_theme":"SYSTEM|DARK","theme_mode":"system|dark",
   "article_list_sort_order":"NEWEST_FIRST|OLDEST_FIRST",
   "article_font_size":"...","article_title_text_alignment":"..."}

## FEAT-LOCAL-PERSISTENCE (BC-0017) — VERIFIED
- Cold restart (force-stop + aa start): no Add Account first screen, Ars feed
  still listed, article rows + read state identical (Bentley ○ kept).
- Data survived install -r as well.

## TOOL_GAP / notes for 4B
- uinput on this SDK: text input is `uinput -K -t` (NO `-T -t`); Back key (2)
  closes bindSheet if focus not in TextInput — used IME-collapse via Back only
  after focusing the input; TextInput now also has enterKeyType Done +
  onSubmit as deterministic submit path.
- Text.accessibilityText confirmed absent from dumpLayout; all anchors used
  visible text.
- Enter keycodes (221/66/13) did NOT trigger onSubmit on this emulator IME;
  button tap after IME collapse is the reliable path.
- dumpLayout -J returns wrong (status-bar-only) window while IME is up; use -p.
- Sheet TextInput center is (660,2091) full-screen; Add=(962,2301).
