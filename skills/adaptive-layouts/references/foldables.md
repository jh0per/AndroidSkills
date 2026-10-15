# Foldables: postures, hinge and fold events

## Which API

| Need | Use |
|---|---|
| "Is the device half-open on a table?" in Compose | `currentWindowAdaptiveInfo().windowPosture.isTabletop` |
| Hinge rectangles to avoid placing content under | `windowPosture.hingeList` (each `HingeInfo` has `bounds`, `isSeparating`, `isOccluding`, `isVertical`, `isFlat`) |
| Raw fold state outside Compose, or exact `FoldingFeature` fields | `WindowInfoTracker.getOrCreate(activity).windowLayoutInfo(activity)` |
| Pane scaffolds splitting at the hinge | default `calculatePaneScaffoldDirective(adaptiveInfo)` already avoids separating hinges |

`FoldingFeature` fields: `state` (`FLAT` / `HALF_OPENED`), `orientation` (`HORIZONTAL` fold line =
table-top when half-open, `VERTICAL` = book), `isSeparating`, `occlusionType`, `bounds`.

## Table-top media screen

```kotlin
@Composable
fun AppPlayerScreen(state: PlayerUiState, onIntent: (PlayerIntent) -> Unit) {
    val posture = currentWindowAdaptiveInfo().windowPosture
    val hinge = posture.hingeList.firstOrNull { it.isSeparating && !it.isVertical }
    if (posture.isTabletop && hinge != null) {
        val hingeTopDp = with(LocalDensity.current) { hinge.bounds.top.toDp() }
        Column(Modifier.fillMaxSize()) {
            AppVideoSurface(Modifier.height(hingeTopDp).fillMaxWidth())     // above the fold
            AppPlayerControls(state, onIntent, Modifier.weight(1f))           // below the fold
        }
    } else {
        Box(Modifier.fillMaxSize()) {
            AppVideoSurface(Modifier.fillMaxSize())
            AppPlayerControls(state, onIntent, Modifier.align(Alignment.BottomCenter))
        }
    }
}
```

Hinge bounds are in window coordinates; if the composable is not at the window origin, convert
with `onGloballyPositioned { it.boundsInWindow() }` before subtracting.

## Flow version (Activity / ViewModel-free code)

```kotlin
lifecycleScope.launch {
    repeatOnLifecycle(Lifecycle.State.STARTED) {
        WindowInfoTracker.getOrCreate(this@AppPlayerActivity)
            .windowLayoutInfo(this@AppPlayerActivity)
            .map { info -> info.displayFeatures.filterIsInstance<FoldingFeature>().firstOrNull() }
            .distinctUntilChanged()
            .collect { fold -> postureState.value = fold.toAppPosture() }
    }
}
```

Collect in `STARTED`, not `RESUMED`: a split-screen window that is not focused still has to react.

## Rules

- Never assume "foldable" from a device model or from a 600dp+ width; read the feature.
- A `FLAT` fold with `isSeparating == false` is a normal screen; do not split at it.
- Book posture plus a separating vertical hinge: two panes split at the hinge, nothing interactive
  under it.
- Unfold/fold changes the window size class mid-task; the open item and scroll position must
  survive (see Step 7 of the skill).
- Test with the emulator foldable profiles (Pixel Fold-type, 7.6" foldable) and the extended-controls
  posture slider; the Resizable profile switches between phone, foldable, tablet and desktop sizes
  but is not a substitute for posture testing.
