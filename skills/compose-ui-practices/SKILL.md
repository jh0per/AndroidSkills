---
name: compose-ui-practices
description: Rules for building Compose / Compose Multiplatform UI with Material 3 - component reuse before creation, theme tokens and colour roles, 48dp touch targets, inset and scroll ownership with edge-to-edge, one list-state owner with pull-to-refresh and load-more, readable text in both themes, snackbars versus persistent notices, adaptive layouts and accessibility. Use when creating or changing any screen, component, list, dialog, sheet or theme.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Jetpack Compose
  - Material 3
  - touch targets
  - tokens
  - window insets
  - lists
  - snackbar
  - accessibility
---

# Compose UI practices

Which Material component to use, colour/type/shape roles and adaptive layouts are in
`material3-guidelines`; this skill covers how a codebase keeps UI consistent.

## Reuse before you write

Before writing UI, search all UI roots for an existing owner and record one of: **reuse unchanged**,
**extend an existing primitive**, or **create a missing primitive** (with its owner and consumers).
A second implementation of the same responsibility is a defect.

- Shared primitives include bars, scaffolds, sheet/dialog frames, action rows, empty/error/loading
  views, choice controls, tabs and section containers, not just buttons.
- Screens compose primitives. A screen may own its unique content layout; it may not copy a shared
  control's dimensions, semantics, inset handling or states.
- Prefer slots and small explicit variants. Do not grow a universal toolbar with unrelated boolean
  flags.
- Start from the Material component. Wrap it only to add product policy or repeated behaviour; a
  custom replacement needs a demonstrated limitation.
- Extract a shared assembly when a **second real consumer** appears, migrate both, delete the old
  code in the same change. An unused wrapper is not consolidation.
- Keep a short component registry (file + responsibility) in the repo docs and update it when an
  owner moves.

## Theme and tokens

Layers: reference values → semantic roles → component defaults → screen composition. Callers pick
roles (`MaterialTheme.colorScheme.onSurfaceVariant`, `AppSpacing.sectionGap`), never raw numbers.

- Fill **every** Material 3 colour role your components use in both light and dark schemes; an
  unfilled role falls back to the library's default purple.
- No OS dynamic colour or per-screen themes unless that is a product decision.
- Apply the brand typeface to every M3 typography role in one place.
- Accent fills are often not readable as text ink; define an accessible ink role for text buttons.
- Colours and sizes that belong to user content (a tag colour, a map marker, a chart series) are
  **data**, not theme tokens, and must not follow the OS
  font scale. Chrome must support font scaling.
- Legitimate literals: content coordinates, image ratios, algorithm constants, 0. Do not tokenise
  every number.
- Every user-facing string is a resource (`stringResource` / Compose Resources), in every language
  you ship.

## A component that draws text names its colour

`LocalContentColor` defaults to **black** outside a `Surface`. An empty-state heading placed in a
bare `Box` is invisible on a dark theme while the line below it, which named a colour, looks fine.
Any shared component that draws text sets `color =` explicitly or sits inside a `Surface`. Guard it
with a screenshot test that measures contrast (see `android-testing`).

## Touch targets and semantics

- Reserve **48dp × 48dp** for every interactive element; the glyph can be smaller. Prevent
  overlapping expanded targets. (Web: 24 CSS px floor; iOS: 44pt.)
- `Tab(text = { … })` and `Tab(icon = …)` get Material's 48dp layout; the content-lambda overload
  `Tab { Text(…) }` measures what you hand it (often ~20dp). Measure in an instrumented test rather
  than trusting a comment.
- Label icon-only controls (`contentDescription`); do not duplicate descriptions on decorative icons
  inside an already-labelled button.
- Two panes of one screen → a `ScrollableTabRow`/`PrimaryScrollableTabRow` (content-sized,
  start-aligned). Filtering a set → choice/filter chips. Two chips stretched to half the width each
  is neither.
- Every shared interactive component defines default, focused, pressed, disabled, selected and busy
  states; a busy action cannot be triggered twice. Dialogs and sheets define back/dismiss and return
  focus to the invoker.
- One dominant action per surface; destructive actions use a distinct role and a confirmation.
- Offer **one** way to dismiss a notice (a labelled button), not also a tiny close icon.

## Insets and scrolling

Enable edge-to-edge. Each surface owns its inset exactly once:

| Surface | Owns |
|---|---|
| Root | horizontal safe-drawing only; no blanket vertical padding |
| Top bar / header | status-bar inset inside its own background |
| Bottom navigation bar | navigation-bar inset (M3 `NavigationBar` does it) |
| Content + FAB | bottom bar height including the live navigation inset |
| Full-bleed hero | draws behind the status bar; its back control sits in the safe area |
| Forms | IME padding |
| Modal sheets | their own window insets; verify before adding more |

- Insets respect ancestor consumption (`consumeWindowInsets`); never apply the same inset twice.
- For each new surface, name the **inset owner** and the **scroll owner** in the plan.
- The only back/dismiss action must never scroll out of reach; do not bury required navigation in a
  scrolling column.
- Pan/zoom canvases keep an explicit offset instead of scroll containers.

## Lists: one owner for loading, error, empty, refresh and paging

```kotlin
@Immutable sealed interface AppListState<out T> {
    data object Loading : AppListState<Nothing>
    data class Error(val message: String) : AppListState<Nothing>
    data class Content<out T>(val items: T, val hasMore: Boolean = false, val loadingMore: Boolean = false) : AppListState<T>
}

@Composable
fun <T> AppListSurface(
    state: AppListState<T>, onRetry: () -> Unit,
    loading: @Composable () -> Unit, empty: @Composable (T) -> Unit, content: @Composable (AppListState.Content<T>) -> Unit,
    modifier: Modifier = Modifier, isEmpty: (T) -> Boolean = { false },
    refreshing: Boolean = false, onRefresh: (() -> Unit)? = null,
) = AppRefreshable(refreshing, onRefresh, modifier) {
    when (state) {
        AppListState.Loading -> loading()
        is AppListState.Error -> AppErrorState(state.message, onRetry = onRetry)
        is AppListState.Content -> if (isEmpty(state.items)) empty(state.items) else content(state)
    }
}

@Composable
fun AppRefreshable(refreshing: Boolean, onRefresh: (() -> Unit)?, modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    if (onRefresh == null) { Box(modifier.fillMaxSize()) { content() }; return }
    PullToRefreshBox(isRefreshing = refreshing, onRefresh = onRefresh, modifier = modifier.fillMaxSize()) { content() }
}

@Composable
fun LoadMoreWhenNearEnd(state: LazyGridState, hasMore: Boolean, loadedCount: Int, onLoadMore: () -> Unit, prefetch: Int = 6) {
    val nearEnd by remember(state, prefetch) {
        derivedStateOf {
            val info = state.layoutInfo
            val last = info.visibleItemsInfo.lastOrNull()?.index ?: return@derivedStateOf false
            info.totalItemsCount > 0 && last >= info.totalItemsCount - prefetch
        }
    }
    LaunchedEffect(nearEnd, hasMore, loadedCount) { if (nearEnd && hasMore) onLoadMore() }
}
```

- This file is the **only** place `PullToRefreshBox` and end-of-list detection live. New list
  screens supply skeleton, empty sentence and grid; they do not write their own `when` over states.
- Emptiness is a predicate the screen passes, because "nothing here yet" and "your search matched
  nothing" are different sentences.
- Loading and empty are different: never show "empty" before the data source has answered.
- List cells are cheap: no subcomposition per item, stable keys, `@Immutable`/immutable collections
  in state, image models that are cacheable. Verify scroll performance on a **release** build on a
  real device.
- Search runs on the server after a debounce; storefront reads are bounded and paged.

## Messages

- A snackbar is for transient confirmation ("Saved"). One queue per screen.
- Never use a snackbar for a problem the person must act on: when it times out, the only statement
  of the problem disappears. Use an inline notice card or a dialog.
- Error text says what happened and what to do, in product words; never raw codes or vendor names.
- One word for one destination across the app (and across platforms). A rename must reach every
  string, hint and test; grep for the old word.

## Adaptive layout

- Centralise breakpoint decisions (`WindowSizeClass`). Decide explicitly whether wide windows get
  more columns or a second pane; at `targetSdk` 36+ orientation locks are ignored on large screens,
  so a wide window must still read well.
- When tools move into a sheet on compact widths, keep their meaning and order.
- Overlays (hint cards) are placed over the content, not inserted above it, so dismissing them does not
  re-layout and re-fit the content.

## Completion

Inspect each changed screen on a device or emulator: compact and wide, long text, 200% font scale,
light and dark, gesture navigation, keyboard/TalkBack focus, disabled and loading states, rotation.
Remove replaced implementations and update the component registry.
