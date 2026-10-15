---
name: predictive-back
description: Back navigation that is correct and animated on Android 13+ - enabling predictive back in the manifest, BackHandler versus PredictiveBackHandler versus NavigationBackHandler (androidx.navigationevent), one back-handler owner per screen, progress-driven transitions, Navigation Compose/Navigation 3 and ViewPager/tab dispatcher scoping, dialogs and sheets, interop with Activities and Fragments, unsaved-changes interception, and testing back with the gesture. Use when adding or fixing back handling, migrating from onBackPressed, enabling predictive back, or when a back gesture closes the wrong thing. Do not use for the unsaved-changes dialog itself (see unsaved-changes-recovery).
metadata:
  last-updated: '2026-10-15'
  keywords:
  - predictive back
  - BackHandler
  - PredictiveBackHandler
  - NavigationBackHandler
  - navigationevent
  - OnBackPressedDispatcher
  - enableOnBackInvokedCallback
  - back gesture
  - Navigation Compose
  - Navigation 3
---

# Predictive back

## Prerequisites

- `android:enableOnBackInvokedCallback="true"` on `<application>` (or per activity). Android 16
  (API 36) turns it on for apps targeting 36; until then it is opt-in. Without it the system
  falls back to `onBackPressed` and no predictive animation runs.
- `androidx.activity` 1.9+ for `PredictiveBackHandler`; Navigation Compose 2.8+ and Navigation 3
  animate the back stack themselves; `androidx.navigationevent` 1.0+ for `NavigationBackHandler`
  with progress and multi-handler scoping.

## Step 1: who owns back on this screen

Exactly one handler decides what back does on a visible screen (`architecture-guard-tests` can
enforce "one back-handler setup"). Decision order:

| Situation | Use |
|---|---|
| Pop a navigation back stack | nothing: `NavHost`/`NavDisplay` already handles and animates it |
| Close an in-screen state (search mode, selection, expanded panel) | `BackHandler(enabled = inSearchMode) { exitSearch() }` |
| Animate the close with the gesture progress | `PredictiveBackHandler(enabled) { progress -> … }` or `NavigationBackHandler` |
| Intercept to ask about unsaved changes | `BackHandler(enabled = isDirty) { showDiscardDialog() }` (`unsaved-changes-recovery`) |
| Activity/Fragment code | `onBackPressedDispatcher.addCallback(owner) { }`; never override `onBackPressed()` |

`enabled` must be a real state read, not `true`: a handler that is always enabled swallows the
system back and breaks predictive back for the whole app.

## Step 2: handlers

```kotlin
// RIGHT: enabled follows state; the last composed enabled handler wins, so put it in the screen that owns the state
BackHandler(enabled = state.isSelecting) { onIntent(Intent.ClearSelection) }
```

```kotlin
// RIGHT: progress-driven; the gesture can be cancelled
PredictiveBackHandler(enabled = state.panelOpen) { progress: Flow<BackEventCompat> ->
    try {
        progress.collect { event -> panelOffset.snapTo(event.progress) }   // follow the finger
        panelOffset.animateTo(1f); onIntent(Intent.ClosePanel)             // committed
    } catch (e: CancellationException) {
        panelOffset.animateTo(0f); throw e                                 // user swiped back in
    }
}
```

```kotlin
// WRONG: two always-on handlers on one screen; which one runs depends on composition order
BackHandler { navController.popBackStack() }
BackHandler { viewModel.onBack() }
```

- Progress collection: `collect` must not suspend on anything else; rethrow `CancellationException`.
- Screen-level transitions: Navigation Compose 2.8+ uses `popExitTransition` with the gesture
  automatically; Navigation 3 `NavDisplay` takes `predictivePopTransitionSpec`. Do not add a
  `PredictiveBackHandler` that pops the stack: it fights the host's own animation.

## Step 3: dispatcher scoping (tabs, pagers, nested hosts)

- Compose: each `NavHost`/`NavDisplay` installs its own handler; the innermost composed and
  enabled one wins. A nested host whose stack is at root must **not** be enabled, or back is
  swallowed; `NavHost` handles this; a custom pager needs `BackHandler(enabled = pagerState.currentPage != 0)`.
- `androidx.navigationevent`: `NavigationBackHandler` with an `isBackEnabled` state and a
  `NavigationEventDispatcherOwner` per pager page/tab so the system sees one dispatcher chain
  (activity → tab → page). Registering two `NavigationBackHandler`s in one scope throws; keep one
  per owner.
- Dialogs and `ModalBottomSheet`: they own back while shown (a `ComponentDialog` has its own
  dispatcher); do not add a screen `BackHandler` to dismiss them, use their `onDismissRequest`.
- Fragments: `requireActivity().onBackPressedDispatcher.addCallback(viewLifecycleOwner, enabled) { }`;
  `FragmentManager` already pops with predictive animation when `enableOnBackInvokedCallback` is set.

## Step 4: system animations and interop

- Cross-activity and back-to-home animations come from the system once the manifest flag is set
  and no always-enabled callback is registered. Check by swiping slowly on the root screen: the
  home screen must peek through behind the shrinking app window.
- Custom in-app transitions on Android 13: progress events need API 34; on 33 you get only the
  start/commit, so the code path must handle `progress` never emitting.
- `WebView` back (`canGoBack()`): a `BackHandler(enabled = canGoBack)` that calls `goBack()`.

## Verification

1. Settings → Developer options → "Predictive back animations" (Android 13/14) then swipe slowly
   from both edges on every screen type: list, detail, search mode, selection mode, dialog,
   sheet, pager, WebView. The animation must start, follow, and cancel on swipe-back-in.
2. Compose test: `Espresso.pressBack()` or `activityRule.scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }`
   with the state set, assert the in-screen state closed and the route did not pop; then with the
   state clear, assert the route popped.
3. Guard test: no `onBackPressed()` override, no `BackHandler {` without `enabled =` outside an
   allow-list.

## Checklist

- [ ] `enableOnBackInvokedCallback` set; no `onBackPressed()` overrides remain.
- [ ] Each screen has at most one enabled back owner, and `enabled` follows state.
- [ ] Navigation hosts animate pops themselves; no handler pops the stack manually.
- [ ] Progress handlers handle cancellation and the API 33 no-progress case.
- [ ] Nested hosts, pagers, dialogs and sheets scope their handlers.
- [ ] Verified with the slow gesture on every screen type, both edges.
