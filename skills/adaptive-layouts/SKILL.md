---
name: adaptive-layouts
description: Make a Compose app work on phones, foldables, tablets, desktop windows and multi-window - width-first decisions from currentWindowAdaptiveInfo and WindowSizeClass breakpoints (never device type or orientation), NavigationSuiteScaffold, ListDetailPaneScaffold and SupportingPaneScaffold with their back behaviour, Navigation 3 list-detail scenes, foldable table-top and book postures, state that survives resize and configuration changes, removing orientation and resizeableActivity locks (Android 16 ignores them on large screens at targetSdk 36), reading-width caps, keyboard, mouse and stylus basics, multi-device previews, and verification on a resizable emulator. Use when a screen must adapt to window size, when raising targetSdk to 36, when adding a second pane or a navigation rail, or when a layout breaks on a tablet, foldable or in split screen. Do not use for choosing Material components or tokens (see material3-guidelines) or for Navigation 3 wiring itself (see navigation3-compose).
metadata:
  last-updated: '2026-10-15'
  keywords:
  - adaptive layout
  - large screens
  - window size class
  - currentWindowAdaptiveInfo
  - NavigationSuiteScaffold
  - ListDetailPaneScaffold
  - SupportingPaneScaffold
  - ListDetailSceneStrategy
  - foldable
  - tabletop posture
  - WindowInfoTracker
  - multi-window
  - targetSdk 36
  - screenOrientation
  - resizeableActivity
  - keyboard and mouse
---

# Adaptive layouts

The rule: **layout follows the current window's width, nothing else.** Not the device model, not
`isTablet`, not orientation, not the physical display size. A phone in landscape, a tablet in a
third of a split screen and a desktop window dragged narrow are the same problem. Every screen
works at every width from about 320dp up, survives being resized while open, and gets a
deliberate wide layout (more columns, a second pane, or a capped reading column) instead of a
stretched phone UI. Neighbours: `material3-guidelines` owns which component and which canonical
layout (breakpoint table, margins); `compose-ui-practices` owns general screen rules;
`navigation3-compose` owns the back stack and scene wiring; `edge-to-edge-insets` owns insets,
including cutouts and the hinge; `predictive-back` owns back gestures in general.

## Prerequisites

- `androidx.compose.material3.adaptive:adaptive`, `adaptive-layout`, `adaptive-navigation`
  (pane scaffolds) and `androidx.compose.material3:material3-adaptive-navigation-suite`
  (`NavigationSuiteScaffold`). Use the BOM or check the current stable release; several APIs are
  `@ExperimentalMaterial3AdaptiveApi` and their signatures moved between 1.0, 1.1 and 1.2. Read the
  installed signature before writing a call.
- `androidx.window:window` 1.4+ for `WindowSizeClass.isWidthAtLeastBreakpoint(...)`; the older
  `windowWidthSizeClass` enum-style getter is deprecated.
- Navigation 3 projects: `adaptive-navigation3` provides `ListDetailSceneStrategy` and
  `SupportingPaneSceneStrategy`; use those instead of the pane scaffolds.
- Compose Multiplatform: the JetBrains `material3-adaptive` artifacts expose the same
  `currentWindowAdaptiveInfo()`; posture and `WindowInfoTracker` are Android-only.
- Platform fact: at `targetSdk` 36, on displays with smallest width ≥ 600dp, Android 16 ignores
  `screenOrientation`, `resizeableActivity="false"`, `minAspectRatio`/`maxAspectRatio` and
  `setRequestedOrientation()`. Games (`android:appCategory="game"`) are exempt. A per-app opt-out
  property exists only for API 36 and goes away at the next level; do not rely on it.

Breakpoints (window width, dp): compact < 600 ≤ medium < 840 ≤ expanded < 1200 ≤ large < 1600 ≤
extra-large. Only use large/extra-large when the screen has a real layout for them.

## Step 1: inventory

```bash
grep -rnE 'screenOrientation|resizeableActivity|AspectRatio|setRequestedOrientation|configChanges' --include=AndroidManifest.xml --include=*.kt .
grep -rnE 'isTablet|smallestScreenWidthDp|screenWidthDp|Configuration.ORIENTATION|orientation ==|DisplayMetrics|widthPixels|getRealSize|defaultDisplay' --include=*.kt .
find . -type d \( -name 'values-sw600dp*' -o -name 'values-land' -o -name 'layout-land' \)
grep -rnE 'NavigationBar\(|NavigationRail\(|ListDetailPaneScaffold|SupportingPaneScaffold|NavigationSuiteScaffold|currentWindowAdaptiveInfo' --include=*.kt .
```

Record per screen: what it shows at 360dp, 700dp and 1280dp today, which hits above drive it,
and which list/detail pairs exist (tap row → full-screen detail). Those pairs are the candidates
for a second pane.

## Step 2: one source of window facts

Read the window class once, near the root, and pass decisions (not the class) down.

```kotlin
// RIGHT: window width, read once, mapped to a product decision.
enum class AppPaneMode { Single, Dual }

@Composable
fun rememberAppPaneMode(): AppPaneMode {
    val sizeClass = currentWindowAdaptiveInfo().windowSizeClass
    return if (sizeClass.isWidthAtLeastBreakpoint(WindowSizeClass.WIDTH_DP_EXPANDED_LOWER_BOUND)) AppPaneMode.Dual
    else AppPaneMode.Single
}
```

```kotlin
// WRONG: device and orientation proxies. A tablet in split screen is "a tablet" but 500dp wide;
// a phone in landscape is "landscape" but has no room for two panes.
val isTablet = LocalContext.current.resources.getBoolean(R.bool.is_tablet)
val twoPane = isTablet || LocalConfiguration.current.orientation == ORIENTATION_LANDSCAPE
```

- Height matters only for height-bound decisions (hide a header, move a toolbar) and only as a
  second check; `isHeightAtLeastBreakpoint` exists for that.
- Inside a pane, decide from the pane's own constraints (`BoxWithConstraints`, `GridCells.Adaptive`),
  not from the window: a 1280dp window gives a detail pane maybe 700dp.
- Never read `DisplayMetrics` or the display size (it lies in multi-window), and delete
  `values-sw600dp` layout booleans: they are device-type checks in disguise.

## Step 3: navigation chrome

```kotlin
// RIGHT: bar on compact, rail on medium/expanded, chosen from the window, labels always present.
NavigationSuiteScaffold(
    navigationSuiteItems = {
        AppTab.entries.forEach { tab ->
            item(
                selected = tab == current,
                onClick = { onTab(tab) },
                icon = { Icon(tab.icon, contentDescription = null) },
                label = { Text(stringResource(tab.label)) },
            )
        }
    },
) { AppTabContent(current) }
```

```kotlin
// WRONG: hand-rolled switch on orientation; a 600dp portrait foldable gets a bottom bar far from
// the thumb, and a phone in landscape loses 80dp of height to it anyway.
if (orientation == ORIENTATION_LANDSCAPE) Row { NavigationRail { … }; Content() }
else Scaffold(bottomBar = { NavigationBar { … } }) { Content() }
```

- Override the type only for a product reason, via `layoutType =
  NavigationSuiteScaffoldDefaults.calculateFromAdaptiveInfo(currentWindowAdaptiveInfo())` and then
  adjusting the result. Screens that hide the bar (full-screen player) hide it through the
  scaffold's state API in the installed version, not by removing the scaffold.
- Each tab keeps its own back stack and scroll state across the bar→rail switch (resize must not
  reset the tab).

## Step 4: list-detail and supporting pane

Navigation 3 → scene strategies (4b); otherwise `NavigableListDetailPaneScaffold` (4a). Never both.

### 4a: pane scaffold

```kotlin
// RIGHT: navigator holds a saveable key; the scaffold owns back between panes.
@Composable
fun MailScreen(state: MailUiState, onIntent: (MailIntent) -> Unit) {
    val navigator = rememberListDetailPaneScaffoldNavigator<String>()   // key must be saveable
    val scope = rememberCoroutineScope()
    NavigableListDetailPaneScaffold(
        navigator = navigator,
        listPane = {
            AnimatedPane {
                MailList(
                    items = state.items,
                    selectedId = navigator.currentDestination?.contentKey,   // highlight in dual mode
                    onOpen = { id -> scope.launch { navigator.navigateTo(ListDetailPaneScaffoldRole.Detail, id) } },
                )
            }
        },
        detailPane = {
            AnimatedPane {
                navigator.currentDestination?.contentKey?.let { MailDetail(it) } ?: MailEmptyDetail()
            }
        },
    )
}
```

```kotlin
// WRONG: selection in a plain remember and a manual BackHandler that always pops the screen.
// Rotation or resize loses the open item; on a tablet back closes the whole screen instead of the detail.
var selected by remember { mutableStateOf<Mail?>(null) }
BackHandler { onIntent(MailIntent.Close) }
```

Back behaviour (`defaultBackBehavior`): `PopUntilScaffoldValueChange` (default) skips history
entries that do not change what is visible, so back on a two-pane tablet leaves the screen
instead of cycling through every previously opened item. Use `PopUntilContentChange` only when
the product wants back to walk through previously viewed items. Without the `Navigable…`
variant you must wire `BackHandler(navigator.canNavigateBack()) { scope.launch { navigator.navigateBack() } }`
yourself; prefer the variant, which also supports predictive back.

- The content key is an id (`String`/`Long`/Parcelable), never the full model; the detail loads
  through its ViewModel so it survives process death.
- `SupportingPaneScaffold` / `NavigableSupportingPaneScaffold` has the same shape with `mainPane`
  and `supportingPane` and `SupportingPaneScaffoldRole.Supporting`.

### 4b: Navigation 3 scenes

Wiring (`rememberListDetailSceneStrategy`, `listPane(detailPlaceholder = …)`, `detailPane()`,
`extraPane()` metadata) is in `navigation3-compose`. The adaptive rules on top of it:

- Back is just `backStack.removeLastOrNull()`; in two-pane mode popping the detail leaves the list
  with its placeholder. If the product wants back to leave the screen there, pop both keys in
  `onBack` when the pane mode is `Dual`.
- The detail screen must not show its own up arrow when it is side by side with the list. Derive
  that from the same directive the strategy uses (`directive.maxHorizontalPartitions > 1`) and
  pass `showUp` into the detail; do not re-derive from window width with a different breakpoint.
- Full-screen detail on phones (bars hidden, immersive) must turn that off when shown as a pane.
- Opening item B while A is shown replaces the detail key instead of stacking A, B, C:
  `if (backStack.last() is MailKey) backStack.removeLastOrNull(); backStack.add(MailKey(id))`.

## Step 5: content width and grids

```kotlin
// RIGHT: reading text capped and centred; the background still fills the window.
Box(Modifier.fillMaxSize(), contentAlignment = Alignment.TopCenter) {
    ArticleBody(Modifier.widthIn(max = 640.dp).fillMaxWidth().padding(horizontal = 16.dp))
}
```

```kotlin
// WRONG: 1600dp lines of body text; nobody can track a line that long.
ArticleBody(Modifier.fillMaxWidth().padding(16.dp))
```

- Collections: `LazyVerticalGrid(GridCells.Adaptive(minSize = 180.dp))` (or the staggered
  variant) instead of `LazyColumn` when items are cards; keep `LazyColumn` with a width cap for
  text rows such as settings and messages.
- Forms and dialogs: cap at about 560–640dp; a full-width text field on a 1280dp window is a bug.
- Compose 1.11 adds experimental `Grid`, `FlexBox` and `mediaQuery`; adopt only with the owner's
  explicit OK to take an experimental API (see `references/input-and-devices.md`).

## Step 6: foldables

- Prefer `currentWindowAdaptiveInfo().windowPosture`: `isTabletop` and `hingeList` cover most
  needs in Compose. Use `WindowInfoTracker.getOrCreate(activity).windowLayoutInfo(activity)` and
  `FoldingFeature` (`state == HALF_OPENED`, `orientation` HORIZONTAL = table-top, VERTICAL = book,
  `isSeparating`, `bounds`) when you need the fold's exact bounds.
- Table-top: media or camera on the top half, controls below the fold. Book: two panes split at
  the hinge, never content under a separating hinge.
- Folding/unfolding is a resize plus maybe a recreation (Step 7). Details: `references/foldables.md`.

## Step 7: state survival and manifest locks

- UI state that matters (selected item, scroll position, open tab, draft text) lives in a
  ViewModel (`SavedStateHandle` for ids) or `rememberSaveable`. Plain `remember` is fine only for
  values derived from those.
- Do not add `android:configChanges="orientation|screenSize|…"` to hide lost state; it skips the
  recreation that would expose a bug that process death will still trigger. Projects that already
  declare it for Compose must still pass the process-death check below.
- Delete `screenOrientation="portrait"`, `resizeableActivity="false"` and aspect-ratio caps. They
  are already ignored on large screens at `targetSdk` 36 and produce letterboxing everywhere else.
  A camera or video capture screen that truly needs a fixed orientation handles rotation of its
  own preview instead.
- Split screen: an unfocused Activity is paused but visible; keep playback running in `STARTED`.

## Step 8: input beyond touch

Keyboard, mouse, trackpad and stylus are standard on tablets, ChromeOS and desktop windowing.
Minimum bar: every action reachable with Tab/arrows and Enter, visible focus, Escape closes
dialogs, hover states on clickable surfaces, right-click opens the same menu as long-press, and
text selectable where users copy it. Shortcuts, hover icons, drag and drop and stylus are in
`references/input-and-devices.md`.

## Scope guards

- Games and true kiosk apps may keep an orientation lock; say so in the change description.
- Wear OS, TV and Auto have their own layout systems; this skill is phones-to-desktop windows.
- Do not add a second pane to a screen whose detail is media that needs the full window; cap
  width or grid it instead.

## Verification (fail first)

1. Previews: a shared multi-preview so every screen renders at compact, medium and expanded:

```kotlin
@PreviewScreenSizes            // phone, phone landscape, foldable, tablet, desktop
@PreviewFontScale
annotation class AppAdaptivePreviews
```

   If the project has screenshot tests, record the baseline **before** the change, then diff;
   do not overwrite baselines without a human looking at the diff.
2. Tests: `DeviceConfigurationOverride(DeviceConfigurationOverride.ForcedSize(DpSize(1280.dp, 800.dp)))`
   in a Compose UI test asserts both panes exist; the same test at 400dp asserts one.
   `StateRestorationTester` proves the selected item survives recreation.
3. Manual, on the **Resizable** emulator profile (or `adb shell wm size 2560x1600` /
   `adb shell wm size reset`): open a detail, switch phone → foldable → tablet → desktop while
   it is open; enter split screen and drag the divider; with "Don't keep activities" on, background
   and return. State, scroll and selection must survive every step.
4. Break it once: temporarily read `orientation` instead of width, and confirm a step above
   fails (portrait tablet or landscape phone). A check that never failed proves nothing
   (`verification-discipline`).

## Report format (audit mode)

```
Screen | 360dp | 700dp | 1280dp | Locks/proxies found | Fix | Verified by
MailScreen | ok | stretched list | stretched list | isTablet bool | list-detail scaffold | test + resizable emu
```

## Checklist

- [ ] No layout decision reads device type, orientation, display metrics or `values-sw600dp` booleans.
- [ ] Window class read once near the root and mapped to named decisions.
- [ ] Top-level navigation uses `NavigationSuiteScaffold`; labels present; tab state survives the switch.
- [ ] List/detail pairs use a navigable pane scaffold or Navigation 3 scene strategy, with back
      behaviour chosen deliberately and no up arrow on a side-by-side detail.
- [ ] Text, forms and dialogs capped in width; card collections use adaptive grid cells.
- [ ] No `screenOrientation`, `resizeableActivity="false"` or aspect-ratio caps outside documented exceptions.
- [ ] Selection, scroll and drafts survive resize, fold/unfold and process death.
- [ ] Keyboard, mouse and focus basics pass on a resizable emulator with a hardware keyboard.
- [ ] Multi-size previews or screenshot tests cover compact, medium and expanded.
