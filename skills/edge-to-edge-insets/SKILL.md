---
name: edge-to-edge-insets
description: Make a Compose or Compose Multiplatform app edge-to-edge and fix inset bugs - enableEdgeToEdge and the Android 15/16 enforcement, exactly one inset owner per surface, Scaffold innerPadding versus imePadding without double padding, IME handling for forms (adjustResize, fitInside rulers), list contentPadding, FABs above the navigation bar, system bar icon contrast and scrims, full-screen dialogs, and a fail-first verification on a 3-button and a gesture device. Use when content is hidden behind the status/navigation bar or keyboard, when a screen has excess padding, when adding a screen with a text field, or when raising targetSdk to 35+.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - edge-to-edge
  - window insets
  - enableEdgeToEdge
  - targetSdk 35
  - IME
  - imePadding
  - safeDrawing
  - system bars
  - Scaffold innerPadding
  - navigation bar contrast
---

# Edge-to-edge and window insets

Compose rules of thumb for the rest of UI work are in `compose-ui-practices`; this skill is the
deep dive for insets. Do not use it for Views/XML-only screens (use `WindowCompat` +
`ViewCompat.setOnApplyWindowInsetsListener` there) or for Wear OS.

## Prerequisites

- Compose Foundation 1.6+ (`WindowInsets` modifiers), Material 3 (`Scaffold` consumes insets
  for its own bars). `WindowInsetsRulers` / `Modifier.fitInside` need Compose UI 1.9+.
- Know the platform rules: with `targetSdk` 35 the system draws edge-to-edge **whether or not
  you call `enableEdgeToEdge()`**; the `windowOptOutEdgeToEdgeEnforcement` attribute is a
  temporary escape and is removed for apps targeting SDK 36. Treat edge-to-edge as mandatory.

## Step 1: inventory

1. List every `Activity`. Each must call `enableEdgeToEdge()` **before** `setContent` (the
   `androidx.activity` one, not a hand-rolled `WindowCompat.setDecorFitsSystemWindows(window, false)`;
   the Activity version also sets system bar icon colours for you).
2. For every Activity with text input, the manifest entry needs
   `android:windowSoftInputMode="adjustResize"`. Without it the IME inset is never reported and
   no modifier can fix the covered field.
3. For every screen, write down the **inset owner** of each edge (see table) before changing
   code. Two owners for the same edge is the root cause of almost every "too much padding" bug;
   zero owners is the root cause of every "hidden behind the bar" bug.

| Surface | Owns |
|---|---|
| `Scaffold` | status/navigation insets for its bars; passes the rest as `innerPadding` |
| Top app bar, `NavigationBar`, `NavigationRail`, `ModalBottomSheet`, drawer sheets (M3) | their own inset; add nothing around them |
| Scrollable content | `contentPadding = innerPadding`, never `Modifier.padding(innerPadding)` on the list |
| Form / text input | IME, exactly once (`imePadding` or `fitInside(Ime)`) |
| Full-bleed hero or map | draws behind the status bar; its controls sit in `safeDrawing` |
| Root without a Scaffold | `safeDrawingPadding()` or a `windowInsetsPadding` of a specific side |

## Step 2: apply insets, one method per edge

```kotlin
// RIGHT: Scaffold owns the bars; the list owns scrolling under them.
Scaffold(topBar = { TopAppBar(title = { Text(title) }) }) { innerPadding ->
    LazyColumn(
        modifier = Modifier.fillMaxSize().consumeWindowInsets(innerPadding),
        contentPadding = innerPadding,          // first/last item scroll under the bars, not behind them
    ) { /* items */ }
}
```

```kotlin
// RIGHT: no Scaffold; one modifier on the root, children add nothing.
Box(Modifier.fillMaxSize().safeDrawingPadding()) {
    Button(onClick = onContinue, modifier = Modifier.align(Alignment.BottomCenter)) { Text("Continue") }
}
```

```kotlin
// WRONG: the Column pads for the bars and so does the Scaffold → double top/bottom padding.
Scaffold { innerPadding ->
    Column(Modifier.padding(innerPadding).systemBarsPadding()) { /* ... */ }
}
```

- `consumeWindowInsets(innerPadding)` after applying `innerPadding` tells descendants the inset
  is handled; without it a nested `imePadding()`/`navigationBarsPadding()` pads again.
- Need the size of a bar (a scrim, a custom header)? Use `Modifier.windowInsetsTopHeight(WindowInsets.statusBars)`,
  not a hard-coded `24.dp`.
- Horizontal insets exist (display cutouts in landscape, hinge): use `safeDrawing`, not only
  `systemBars`, on roots that reach the screen edges.

## Step 3: the IME

Pick **one** of these per form; mixing two is the double-padding bug.

```kotlin
// RIGHT (Compose UI 1.9+): rulers, no jank from the padding animation and immune to who consumed what.
Scaffold { innerPadding ->
    Column(
        Modifier.padding(innerPadding).consumeWindowInsets(innerPadding)
            .fitInside(WindowInsetsRulers.Ime.current)
            .verticalScroll(rememberScrollState()),
    ) { /* fields */ }
}
```

```kotlin
// RIGHT: Scaffold's default contentWindowInsets excludes the IME, so imePadding adds it once.
Scaffold { innerPadding ->
    Column(
        Modifier.padding(innerPadding).consumeWindowInsets(innerPadding)
            .imePadding()                      // BEFORE verticalScroll, or the scroll range ignores it
            .verticalScroll(rememberScrollState()),
    ) { /* fields */ }
}
```

```kotlin
// WRONG: contentWindowInsets = safeDrawing already includes the IME, and imePadding adds it again.
Scaffold(contentWindowInsets = WindowInsets.safeDrawing) { innerPadding ->
    Column(Modifier.padding(innerPadding).imePadding().verticalScroll(rememberScrollState())) { }
}
```

- Fixed bottom action (Save) over a scrolling form: put the button in `Scaffold(bottomBar = …)`
  with `Modifier.imePadding()` on the bar, or make the whole column scroll; never both.
- Focused field under the keyboard: `Modifier.bringIntoViewRequester` is rarely needed; a column
  that scrolls and has the IME inset applied scrolls the focused field into view by itself.
- `LazyColumn` chat/comment screens: `contentPadding` includes the IME via
  `WindowInsets.ime.asPaddingValues()` **or** the list has `imePadding()`, not both; add
  `Modifier.imeNestedScroll()` if the keyboard should follow the scroll gesture.
- Compose Multiplatform/iOS: the same `WindowInsets.ime` works; `adjustResize` is Android-only.

## Step 4: system bars and scrims

- Light/dark icons are handled by `enableEdgeToEdge()`; only when the project uses the
  `WindowCompat` path must the theme set `isAppearanceLightStatusBars`/`…NavigationBars` to
  `!darkTheme` in a `SideEffect`. Never hard-code a status bar colour in `themes.xml` for API 35+;
  it is ignored.
- 3-button navigation gets a translucent system scrim by default
  (`isNavigationBarContrastEnforced`). If a bottom bar already provides contrast, set
  `window.isNavigationBarContrastEnforced = false` (API 29+) in the Activity so the bar colour
  reaches the bottom edge. Keep the default when content scrolls under the bar with no scrim.
- Content scrolling behind the status bar needs a protection scrim (a gradient `Spacer` of
  `statusBars` height drawn **after** the content) so icons stay legible on photos.

## Step 5: dialogs, sheets, full-screen content

- A `Dialog` is only edge-to-edge when `DialogProperties(usePlatformDefaultWidth = false,
  decorFitsSystemWindows = false)`; then its content applies `safeDrawingPadding()` like a root.
- `ModalBottomSheet` handles the navigation bar; its content still needs `imePadding()` when it
  holds a text field.
- Full-screen players and image viewers: hide bars with `WindowInsetsControllerCompat.hide(systemBars())`
  and `systemBarsBehavior = BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE`; restore in `DisposableEffect`.

## Verification (fail first)

1. Run on a **gesture-nav** device and a **3-button** device (or toggle in Settings), light and
   dark theme, portrait and landscape with a cutout. Screenshots of first and last list items,
   every FAB, and every form with the keyboard open.
2. Break it on purpose once: remove `enableEdgeToEdge()` or `adjustResize` and confirm your
   screenshot check actually catches the covered field. A check that never failed proves nothing
   (`verification-discipline`).
3. Instrumented test for forms: focus the field, `performTextInput`, assert the submit button is
   `assertIsDisplayed()` with the IME shown (`isImeVisible` via `WindowInsets.isImeVisible`).

## Checklist

- [ ] Every `Activity` calls `enableEdgeToEdge()` before `setContent`.
- [ ] Every Activity with text input has `adjustResize` in the manifest.
- [ ] Each edge of each screen has exactly one inset owner, named in the change description.
- [ ] Lists receive insets through `contentPadding`; FABs sit inside a `Scaffold` or have
      `safeDrawingPadding()`.
- [ ] Every text field has one IME owner: `fitInside(Ime)` **or** `imePadding()` **or** inherited
      `contentWindowInsets`, never two.
- [ ] Full-screen dialogs set `decorFitsSystemWindows = false`.
- [ ] Verified on gesture and 3-button navigation, both themes, keyboard open.
