---
name: compose-canvas-gestures
description: Build an interactive Compose canvas (whiteboard, diagram, annotation, floor plan, map overlay) - one viewport gesture detector with hit testing instead of per-item click handlers, coordinate frames, gesture phases with baselines captured once, pinch takeover, snapping, selection chrome that shares geometry with input, modal tool sessions, and a store with undo/redo history. Use when working on drag, resize, rotate, pinch-zoom, selection, hit testing or undo on a Compose canvas. Do not use for scrolling lists or simple draggable cards (a plain draggable modifier is enough there).
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Compose canvas
  - gestures
  - pointerInput
  - hit testing
  - drag
  - resize
  - rotate
  - pinch zoom
  - undo redo
  - whiteboard
---

# Compose canvas gestures

## The one rule

Exactly **one** scene-gesture `pointerInput` lives on the viewport. Items, selection grips and
tool handles are drawings, not gesture recognisers. Ownership is resolved by hit-testing at the
first down, never by racing to consume events. Toolbar buttons stay ordinary controls.

No per-item `pointerInput`, `clickable` or `draggable` competing with the viewport detector.

## Coordinate frames

| Frame | Origin | Unit |
|---|---|---|
| Viewport | node carrying `pointerInput` | physical px |
| Board | measured board top-left | physical px |
| Scene | board top-left | scene units |
| Item-local | item top-left, counter-rotated about its centre | scene units |

```text
scene    = (viewport - boardTopLeft) / (density * zoom)
viewport = scene * (density * zoom) + boardTopLeft
```

- `PointerInputChange.position` is viewport-local. Convert with
  `boardCoords.localPositionOf(viewportCoords, position)`.
- Geometry helpers take scene units; never divide by zoom a second time inside one.
- Counter-rotate resize deltas into item-local space before applying them.
- Hit slop is defined in screen dp and converted to scene units, so its physical reach does not
  shrink when zoomed.

## Hit testing

Order: selected item's grips → its rotate knob → item bodies top to bottom → empty board.
While a modal tool is open (crop, lasso, measure), a modal hit test replaces it (tool handles →
tool target → empty board).

- Hit-test **measured** geometry: the laid-out centre via `localPositionOf` plus untransformed
  layout size, rotation stored separately. Never `boundsInRoot()`/`boundsInParent()`: ancestor
  clipping truncates them. Do not recompute from the model; text can lay out larger than its box.
- Keep a projection registry keyed by item id; prune removed ids. Selection drawing and
  hit-testing read the **same** projection and the same `gripCentre`/`knobCentre` functions;
  changing one without the other creates invisible input drift.
- Z-order: highest index wins, ties by later paint order. If paint order changes, feed the same
  order to both paths.
- Grip hit areas must reach 48dp even when the drawn handle is small.

## Gesture detector shape

```kotlin
internal suspend fun PointerInputScope.detectSceneGestures(
    resolveTarget: (Offset) -> HitTarget,
    oneFingerOwner: (HitTarget) -> Owner,             // View (pan) or Target (move/resize/rotate)
    onTap: (HitTarget) -> Unit,
    onDoubleTap: (HitTarget) -> Unit,
    targetDrag: TargetDragHandler,                    // onStart / onDrag(totalDelta) / onEnd / onCancel
    viewTransform: ViewTransformHandler,              // onTransform(centroid, pan, zoom)
) {
    awaitEachGesture {
        val down = awaitFirstDown(requireUnconsumed = false)
        val target = resolveTarget(down.position)     // resolved once, retained for the session
        val session = TouchSession(target, oneFingerOwner(target), viewConfiguration.touchSlop, targetDrag, viewTransform)
        while (true) {
            val pressed = awaitPointerEvent().changes.filter { it.pressed }
            when {
                pressed.isEmpty() -> break
                pressed.size == 1 -> session.oneFinger(pressed.single())
                else -> session.twoFingers(pressed.take(2))     // ignore pointers beyond two
            }
        }
        session.finish()
        // if the session never passed slop: same target within 300 ms and slop → onDoubleTap, else onTap
    }
}
```

Inside the session:

- Read movement with `positionChangeIgnoreConsumed()`; consumed changes otherwise report zero.
- The frame that first passes touch slop **establishes the baseline**; it does not apply the
  accumulated pre-slop movement.
- Capture pivot, start angle and start bounds **once** at start. Each move computes
  `start + totalDelta`, never `current + increment`. Snapping never becomes the next baseline.
- **1 → 2 fingers:** cancel/revert the partial item edit, close its transaction, start the view
  transform. **2 → 1:** keep panning the view until every pointer lifts; never resume the item
  drag. Compare pinch spans only for the same pointer ids.
- Values the detector needs from composition are read through `rememberUpdatedState`; a suspended
  `pointerInput` coroutine does not restart on recomposition. Key `pointerInput` on the store, not
  on changing values.

| Target | One finger | Two fingers |
|---|---|---|
| Empty board / unselected item | pan; tap selects/deselects | pan/zoom |
| Selected item | move | revert partial drag, pan/zoom |
| Grip / rotate knob | resize / rotate | revert partial drag, pan/zoom |
| Modal tool handle | adjust the tool | revert partial adjustment, pan/zoom |

## Store and history

All scene mutations go through one store that owns undo history; composables render state and
call store actions; geometry stays in pure functions.

```kotlin
data class UndoState<T>(
    val past: ImmutableList<T> = persistentListOf(),
    val present: T,
    val presentSnapshot: T? = null,      // state at gesture start; intermediate frames are not history
    val future: ImmutableList<T> = persistentListOf(),
)
```

- A tap never opens history. A drag opens a transaction at start and closes it at end: **one drag,
  one undo step**, and only if something changed.
- Modal tool drags open no transaction; Apply commits one change, Cancel discards the session. The
  tool session is excluded from saved scenes and undo.
- Session state (zoom, pan, selection) is not part of "unsaved changes"; compare scenes with
  session fields stripped (`unsaved-changes-recovery`).
- Redux-style alternative: actions → reducer → `UndoState`, with a `submit` flag on actions that
  should create a history entry and a logging middleware in debug.

## Viewport

- Keep an explicit `panOffset` and `zoom`; no scroll containers. Clamp pan so a minimum part of the
  board stays visible. One fit-padding constant for automatic fit and the Fit action. Fit resets
  pan; setting 100% zoom alone does not.
- The inner board clips the scene; the outer frame does not clip selection chrome. Item layout
  reserves no space for grips.
- Place the rotate knob above the item, else below, else inside the top edge, deciding from the
  visible scene rectangle; drawing and hit-testing receive the same rectangle.

## Resize and snapping

- Corner handles preserve aspect ratio; side handles change one axis. The opposite pivot stays fixed
  in screen space.
- Unrotated resize clamps to the board; rotated resize skips the clamp.
- Snap on visual bounds, board guides before item guides, candidates computed from the gesture
  start. A drawn guide must coincide with the actual snapped edge.
- Use a float tolerance (~0.001) for pivot arithmetic in tests.

## History details that matter

- **Submit semantics.** Every edit action carries `submit: Boolean`. Drag frames, slider moves and
  keystrokes dispatch `submit = false` (render only); release/blur dispatches one `submit = true`
  that records history. No command is recorded when the committed value equals the last committed
  one.
- **Inverse from the last committed snapshot.** On a submitted action, build the undo action from
  the last *committed* model (not the last rendered frame), and restore that snapshot on undo/redo.
- **Coalesce text editing.** An interceptor in front of the store forwards per-character edits as
  `submit = false` and keeps the latest as pending; it flushes one `submit = true` on blur or when any
  other action arrives. An empty result removes the text item.
- **Transactions for tool sheets** (Cancel/Apply): `begin()`, `hasChanges()`, `discard()`, `commit()`;
  while open, undo/redo only covers the session.
- **Cap the history** (e.g. 100 entries) and drop the oldest; commands that capture full model copies
  otherwise grow memory without bound. Keep history contracts in a pure-Kotlin module and unit-test
  them in isolation (record, undo, redo, discard, cap).
- Validate numbers in reducers: NaN/Infinity must never enter the model.

## Capture and export

- Screenshots of what is on screen: `PixelCopy.request(window, bounds, bitmap, …)` with bounds from
  `LayoutCoordinates.boundsInWindow()`; `View.draw()` fails on hardware bitmaps. In Compose tests,
  `captureToImage()`.
- Exports render offscreen from the model (`GraphicsLayer.toImageBitmap()` or a `Canvas` over a
  bitmap), never by screenshotting the screen; selection chrome is never part of an export.

## Tests that protect this

| Test | Protects |
|---|---|
| Hit-test unit tests | target order, modal tool, apply/cancel history |
| Pinch instrumented test | staggered second finger reverts drag and zooms |
| Gesture ownership test | pan vs select, one undo per drag |
| Projection test | full-bleed and rotated measured geometry, removal |
| Selection chrome test | drawn grip centres equal hit geometry |
| Snap guide test | rendered edges equal guides |

Multi-touch needs instrumented `performTouchInput` with pointer ids (see `android-testing`);
`adb shell input` cannot do it. Verify overflow with unclipped `LayoutCoordinates` or pixels.

## Checklist

- [ ] One `pointerInput` on the viewport; no item-level gesture modifiers.
- [ ] Target resolved once at first down; baselines captured once; `start + totalDelta` everywhere.
- [ ] Drawing and hit-testing share one projection and one geometry function per handle.
- [ ] One drag = one undo entry; taps and modal tool drags record nothing until commit.
- [ ] Session state excluded from saved scenes and dirty checks.
- [ ] Pinch takeover and multi-touch covered by instrumented tests.
