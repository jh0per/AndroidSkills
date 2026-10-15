# Keyboard, mouse, stylus and experimental adaptive APIs

## Keyboard

- Clickable/toggleable modifiers and Material components are focusable already; custom
  `pointerInput` controls are not. Add `Modifier.focusable()` plus `onKeyEvent` for Enter/Space, or
  better, build them from `clickable`.
- Focus must be visible: Material components draw a focus indication; custom surfaces use
  `indication` from `clickable` or draw a ring on `onFocusChanged`.
- Shortcuts at the screen level, not per item:

```kotlin
Modifier.onPreviewKeyEvent { e ->
    if (e.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
    when {
        e.isCtrlPressed && e.key == Key.N -> { onIntent(AppIntent.Compose); true }
        e.isCtrlPressed && e.key == Key.F -> { onIntent(AppIntent.Search); true }
        e.key == Key.Escape && state.selectionMode -> { onIntent(AppIntent.ClearSelection); true }
        else -> false
    }
}
```

- Advertise shortcuts in the system helper (Meta+/) by overriding
  `Activity.onProvideKeyboardShortcuts` with a `KeyboardShortcutGroup`.
- Enter in a single-line field submits (`KeyboardOptions(imeAction = ImeAction.Send)` +
  `KeyboardActions`); Shift+Enter for a newline in multi-line chat inputs is a product decision,
  document it (`compose-text-input`).
- Hardware keyboard means no IME on screen: never rely on the IME being visible to show a submit
  button.

## Mouse and trackpad

- Hover: `Modifier.hoverable(interactionSource)` and read `collectIsHoveredAsState()`; Material
  components already show hover state.
- Pointer icon: `Modifier.pointerHoverIcon(PointerIcon.Hand)` on custom clickable surfaces,
  `PointerIcon.Text` over custom text editors.
- Right-click: the same menu as long-press. Detect `PointerButton.Secondary` in `pointerInput`
  (`awaitPointerEvent().buttons.isSecondaryPressed`) or use the context-menu support of the
  installed Compose version.
- Scroll wheel and trackpad scroll work on lazy lists out of the box; horizontal carousels must
  also respond to Shift+wheel, which `horizontalScroll`/`LazyRow` do.
- Text the user may copy (addresses, codes, messages) sits in a `SelectionContainer`.
- Drag and drop between apps in split screen: `Modifier.dragAndDropSource` /
  `dragAndDropTarget`; outgoing content URIs need read grants (`android-app-security`).

## Stylus

- Recent Compose text fields accept stylus handwriting on Android 14+ without extra code; check
  the installed Compose release notes before claiming support.
- Drawing surfaces read `PointerType.Stylus`, pressure and tilt from `PointerInputChange`;
  palm rejection means ignoring `PointerType.Touch` while a stylus is down
  (`compose-canvas-gestures` owns the gesture code).
- Low-latency ink: the `androidx.ink` libraries; only for real drawing products.

## Experimental adaptive APIs (Compose 1.11)

Use only after the project owner accepts an experimental API; each needs an opt-in annotation.

- `mediaQuery { … }` / `derivedMediaQuery { … }` evaluate a condition over `UiMediaScope`
  (`windowWidth`, `windowHeight`, `windowPosture`, `pointerPrecision`, `keyboardKind`,
  `hasCamera`, `hasMicrophone`, `viewingDistance`). Enabled by setting
  `ComposeUiFlags.isMediaQueryIntegrationEnabled = true` in `Application.onCreate` before any
  composition. Use `derivedMediaQuery` for width/height conditions so every pixel of a resize
  does not recompose. Compare against `WindowSizeClass.WIDTH_DP_*_LOWER_BOUND` constants, never
  invented numbers.
- `pointerPrecision` is the only sanctioned way to change target sizes for fine pointers; without
  it keep 48dp targets everywhere.
- `Grid` (a non-lazy two-dimensional layout configured from the available constraints) replaces a
  `Column` of repeated cards when the count is small and fixed; lazy collections stay
  `LazyVerticalGrid`.
- `FlexBox` wraps and distributes items like CSS flexbox; use it for chip rows and toolbars that
  reflow, where `FlowRow` is not enough.

Without these APIs, everything in the skill works with `currentWindowAdaptiveInfo()`,
`BoxWithConstraints` and the lazy grids.

## Desktop windowing and ChromeOS checks

- Tablets on Android 15+ can run apps in free-form desktop windows (developer option or OEM
  setting); a window can be any size, including shorter than it is wide at 500dp.
- Title bar overlaps: in desktop windows the caption bar is an inset (`WindowInsets.captionBar`);
  `safeDrawing` includes it (`edge-to-edge-insets`).
- Activity restarts on resize unless the app handles the change; resizing a desktop window
  continuously is the harshest state-survival test available.
