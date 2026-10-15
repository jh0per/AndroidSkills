# Analysis coordinates, rotation and the ML Kit hand-off

Depth for `camerax-capture` Steps 3, 5 and 6. Model choice, client lifecycle and unsupported-device
fallbacks are in `on-device-ml`.

## What the analyzer receives

- The buffer is in **sensor orientation**. `proxy.imageInfo.rotationDegrees` says how far to
  rotate it to be upright for the current `targetRotation`. ImageAnalysis does not rotate pixels
  unless you call `setOutputImageRotationEnabled(true)` on the builder (costs CPU per frame).
- `proxy.width/height` are what the device chose, not what you asked for. Size work by the real
  values; emulators often give 640x480.
- `proxy.cropRect` is the region that matches the other use cases when they share a `ViewPort`
  (below); otherwise it is the full buffer.
- ML Kit, given `InputImage.fromMediaImage(image, rotationDegrees)`, returns boxes in the
  **upright** image space: width and height swap when rotation is 90 or 270.

## Map a result box to the viewfinder

Pick one approach per screen:

1. **Shared viewport**: bind with a `UseCaseGroup` and a `ViewPort` so preview, analysis and
   capture agree on the visible crop. Then "inside the visible area" means "inside `cropRect`".
2. **`CameraController` + `PreviewView` + `MlKitAnalyzer(…, COORDINATE_SYSTEM_VIEW_REFERENCED, …)`**:
   results arrive in view coordinates; no maths. Only works with the controller, which calls the
   analyzer's `updateTransform`.
3. **Manual fill-center mapping** (`CameraXViewfinder` + manually bound use cases):

```kotlin
fun android.graphics.Rect.toViewfinder(
    uprightW: Int, uprightH: Int, viewW: Float, viewH: Float, mirrored: Boolean,
): androidx.compose.ui.geometry.Rect {
    val scale = maxOf(viewW / uprightW, viewH / uprightH)           // fill = crop the longer side
    val dx = (viewW - uprightW * scale) / 2f
    val dy = (viewH - uprightH * scale) / 2f
    var l = left * scale + dx
    var r = right * scale + dx
    if (mirrored) { val ml = viewW - r; r = viewW - l; l = ml }     // front lens preview is mirrored
    return androidx.compose.ui.geometry.Rect(l, top * scale + dy, r, bottom * scale + dy)
}
```

- `uprightW/H` = `proxy.width/height`, swapped when `rotationDegrees` is 90 or 270.
- Analysis and preview must have the same aspect ratio for this to line up; request the same
  `AspectRatioStrategy` for both, or use approach 1.
- The overlay is a `Canvas` drawn over the viewfinder from a `StateFlow` of mapped boxes; publish
  an empty list when a frame has no results so stale boxes do not linger (`compose-canvas-gestures`).

## Scanner behaviour

- Debounce: act on a code only after it appears in N consecutive frames, or once per value.
- After a successful scan that navigates away, `clearAnalyzer()` first; otherwise the next frame
  triggers a second navigation.
- Keep a slow detector from piling up: `STRATEGY_KEEP_ONLY_LATEST` plus closing the frame only when
  the detector finishes means at most one frame is in flight. Do not add your own queue.
- Heavy models: request a lower analysis resolution rather than resizing every bitmap.

## Capture rotation with a locked activity

When the activity is locked to portrait, the display never rotates, so the default
`targetRotation` is always portrait. Feed device orientation in yourself:

```kotlin
class CaptureRotation(context: Context, private val onRotation: (Int) -> Unit) : OrientationEventListener(context) {
    override fun onOrientationChanged(orientation: Int) {
        if (orientation == ORIENTATION_UNKNOWN) return
        onRotation(
            when (orientation) {
                in 45 until 135 -> Surface.ROTATION_270
                in 135 until 225 -> Surface.ROTATION_180
                in 225 until 315 -> Surface.ROTATION_90
                else -> Surface.ROTATION_0
            },
        )
    }
}
// Composable: DisposableEffect(Unit) { val l = CaptureRotation(context) { session.setTargetRotation(it) }; l.enable(); onDispose { l.disable() } }
// Session:    imageCapture.targetRotation = it; analysis.targetRotation = it; videoCapture.targetRotation = it
```

- Rotate the on-screen icons with the same value so the UI matches the captured orientation.
- With a freely rotating activity the default is already correct; adding the listener as well
  makes the two disagree during the rotation animation. Choose one.
- Foldables and tablets: the sensor may be mounted landscape relative to the natural
  orientation. Never hard-code "portrait = 90"; always use `rotationDegrees` and `targetRotation`.
