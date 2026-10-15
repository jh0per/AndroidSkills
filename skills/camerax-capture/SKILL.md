---
name: camerax-capture
description: In-app camera with CameraX in Jetpack Compose - deciding when a capture intent or the photo picker is enough, dependencies (camera-core, camera-camera2, camera-lifecycle, camera-compose CameraXViewfinder versus PreviewView in AndroidView, camera-video), one owner that binds use cases to a lifecycle, Preview/ImageCapture/ImageAnalysis/VideoCapture combinations and their limits, ImageAnalysis backpressure and closing every ImageProxy on a background executor, target rotation, tap-to-focus, pinch zoom, flash and torch, saving to MediaStore, CAMERA and RECORD_AUDIO permissions, ML Kit hand-off, rebinding and leak bugs, a fake camera seam for tests, and real-device verification. Use when adding a viewfinder, photo or video capture screen, barcode/document scanner or any live camera frame analysis. Do not use for one-off photos the system camera can take or for picking existing media (see media-storage), for playback and transcoding (see media-video-audio), or for model choice and inference (see on-device-ml).
metadata:
  last-updated: '2026-10-15'
  keywords:
  - CameraX
  - camera
  - CameraXViewfinder
  - PreviewView
  - ProcessCameraProvider
  - ImageCapture
  - ImageAnalysis
  - VideoCapture
  - ImageProxy
  - tap to focus
  - zoom
  - torch
  - barcode scanner
  - camera-compose
---

# CameraX capture in Compose

The camera is a process-wide resource with one owner: a single session object (held by the
screen's ViewModel) creates the use cases once, binds them to the screen's `LifecycleOwner` from
one `LaunchedEffect`, and unbinds when that effect leaves. Composables only draw the
`SurfaceRequest` and forward gestures. Saving files and the photo picker belong to `media-storage`,
recording playback/transcode to `media-video-audio`, model choice and inference to `on-device-ml`,
and the permission UX to `runtime-permissions`.

## Decide first: do you need a camera at all?

| Need | Use | Camera code |
|---|---|---|
| Pick an existing photo/video | Photo picker (`PickVisualMedia`), `media-storage` | none, no permission |
| One photo for an avatar, receipt, attachment | `ActivityResultContracts.TakePicture()` into a pre-created URI, `media-storage` | none; no permission unless the manifest declares `CAMERA` |
| One short video clip | `ActivityResultContracts.CaptureVideo()` | none |
| Live preview, custom UI, overlay, scanning, continuous capture, in-app recording | CameraX (this skill) | yes |

A camera built for one photo buys a permission prompt, device bugs and tests for nothing. State
the row before writing code. (Declaring `CAMERA` makes `ACTION_IMAGE_CAPTURE` require the grant.)

## Prerequisites

- One version ref for all `androidx.camera` artifacts (check the current stable release);
  `CameraXViewfinder` needs 1.5.0+, `ProcessCameraProvider.awaitInstance` 1.4.0+.

```toml
[libraries]
androidx-camera-core      = { module = "androidx.camera:camera-core",      version.ref = "camerax" }
androidx-camera-camera2   = { module = "androidx.camera:camera-camera2",   version.ref = "camerax" } # the HAL backend; without it no camera opens
androidx-camera-lifecycle = { module = "androidx.camera:camera-lifecycle", version.ref = "camerax" }
androidx-camera-compose   = { module = "androidx.camera:camera-compose",   version.ref = "camerax" }
androidx-camera-video     = { module = "androidx.camera:camera-video",     version.ref = "camerax" } # only with VideoCapture
# androidx.camera:camera-view (PreviewView, LifecycleCameraController), camera-mlkit-vision (MlKitAnalyzer): only if used
```

- Manifest: `CAMERA`; `RECORD_AUDIO` only if videos have sound; `<uses-feature
  android:name="android.hardware.camera.any" android:required="false"/>` so camera-less devices
  can install, then check `provider.hasCamera(selector)` at runtime.
- Viewfinder choice: **`CameraXViewfinder`** (camera-compose) in Compose-first apps: it is a
  real composable, handles rotation/scale, and gives a `CoordinateTransformer` for gestures.
  **`PreviewView` in `AndroidView`** only when you need `LifecycleCameraController` (the
  all-in-one controller) or are on a CameraX version without camera-compose (`views-compose-interop`).

## Step 1: inventory

1. Grep `bindToLifecycle`, `unbindAll`, `ProcessCameraProvider`, `PreviewView`, `setAnalyzer`,
   `takePicture`, `prepareRecording`. Binding calls must live in one class.
2. Per analyzer: executor, where `close()` happens, and whether async work outlives it.
3. Per screen: the use cases bound together (Step 4), lenses, and whether the activity is locked
   to portrait (then capture rotation comes from an `OrientationEventListener`, Step 6).

## Step 2: one owner binds, the composable only draws

Put CameraX behind a small interface (the test seam, see `references/testing-and-devices.md`); the real
implementation owns the use cases. The ViewModel owns the session and closes it in `onCleared`.

```kotlin
interface CameraSession {
    val surfaceRequest: StateFlow<SurfaceRequest?>
    suspend fun bind(appContext: Context, owner: LifecycleOwner, lensFacing: Int) // suspends until cancelled
    suspend fun takePhoto(displayName: String): Uri
    fun focusAt(surfacePoint: Offset)
    fun scaleZoom(factor: Float)
    fun setTorch(on: Boolean)
}

class CameraXSession(private val resolver: ContentResolver) : CameraSession, Closeable {
    private val _surfaceRequest = MutableStateFlow<SurfaceRequest?>(null)
    override val surfaceRequest = _surfaceRequest.asStateFlow()
    private val preview = Preview.Builder().build().apply { setSurfaceProvider { _surfaceRequest.value = it } }
    private val imageCapture = ImageCapture.Builder()
        .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY).build()
    private val ioExecutor = Executors.newSingleThreadExecutor()
    private var camera: Camera? = null

    override suspend fun bind(appContext: Context, owner: LifecycleOwner, lensFacing: Int) {
        val provider = ProcessCameraProvider.awaitInstance(appContext)
        val selector = CameraSelector.Builder().requireLensFacing(lensFacing).build()
        provider.unbindAll()
        camera = provider.bindToLifecycle(owner, selector, preview, imageCapture)
        try { awaitCancellation() } finally { provider.unbindAll(); camera = null }
    }

    override fun close() = ioExecutor.shutdown()
    // takePhoto, focusAt, scaleZoom, setTorch: Steps 6 and 7
}
```

```kotlin
// RIGHT: binding keyed on the owner and lens; leaves composition -> finally -> unbindAll.
@Composable
fun CameraScreen(viewModel: CameraViewModel, modifier: Modifier = Modifier) {
    val appContext = LocalContext.current.applicationContext
    val owner = LocalLifecycleOwner.current
    val lens by viewModel.lensFacing.collectAsStateWithLifecycle()
    LaunchedEffect(owner, lens) { viewModel.session.bind(appContext, owner, lens) }
    val request by viewModel.session.surfaceRequest.collectAsStateWithLifecycle()
    request?.let { CameraXViewfinder(surfaceRequest = it, modifier = modifier.fillMaxSize()) }
}
```

```kotlin
// WRONG: rebinds on every recomposition, creates new use cases each time, holds an Activity in a singleton.
@Composable
fun CameraScreen() {
    val context = LocalContext.current
    val provider = ProcessCameraProvider.getInstance(context).get()   // blocks the main thread
    provider.bindToLifecycle(LocalLifecycleOwner.current, DEFAULT_BACK_CAMERA, Preview.Builder().build())
}
```

- Pass `applicationContext` to the process-singleton provider. Never store a `LifecycleOwner`,
  `Activity` or `PreviewView` in a ViewModel field.
- Bind in one place only (not `onCreate` *and* Compose). The lifecycle closes the camera at
  `ON_STOP` and reopens it at `ON_START`; no manual rebind.
- Switching lens = changing the `LaunchedEffect` key; the old effect's `finally` unbinds first.

## Step 3: viewfinder details

- The viewfinder crops (fill-center), so analysis/capture frames show more than the user sees;
  overlays must map coordinates (`references/coordinates-and-rotation.md`).
- `PreviewView` via `AndroidView`: set `preview.surfaceProvider = view.surfaceProvider` once in
  `factory`, never in `update` (runs on every recomposition).
- Viewfinder draws edge-to-edge; controls sit in `safeDrawing` (`edge-to-edge-insets`).

## Step 4: use case combinations

| Bound together | Status |
|---|---|
| Preview + ImageCapture | safe on every device |
| Preview + ImageAnalysis (+ ImageCapture) | safe; analysis resolution may be lowered |
| Preview + VideoCapture (+ ImageCapture) | widely supported; quality may fall back |
| Preview + ImageCapture + ImageAnalysis + VideoCapture | device-dependent: may fail or share streams at lower quality |

- `bindToLifecycle` throws `IllegalArgumentException` for an unsupported combination. Catch it,
  drop the least important use case (usually analysis during recording) and tell the UI.
- Bind only what the current mode (photo/video) needs; rebind on mode change.
- Sizes go through `ResolutionSelector` (the old `setTargetResolution`/`setTargetAspectRatio` are
  deprecated). You may not get what you asked for: read `imageProxy.width/height`.
- Video recording (Recorder, quality fallback, audio, events): `references/video-recording.md`.

## Step 5: ImageAnalysis

```kotlin
private val analysisExecutor = Executors.newSingleThreadExecutor()
private val analysis = ImageAnalysis.Builder()
    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)   // drop stale frames, never queue
    .setResolutionSelector(ResolutionSelector.Builder().setResolutionStrategy(ResolutionStrategy(
        Size(1280, 720), ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER)).build())
    .build()
```

```kotlin
// RIGHT: frame closed only after the async detector is done; rotation passed through.
@OptIn(ExperimentalGetImage::class)
fun startScanning(scanner: BarcodeScanner, onCodes: (List<String>) -> Unit) =
    analysis.setAnalyzer(analysisExecutor) { proxy ->
        val media = proxy.image ?: return@setAnalyzer proxy.close()
        scanner.process(InputImage.fromMediaImage(media, proxy.imageInfo.rotationDegrees))
            .addOnSuccessListener { codes -> onCodes(codes.mapNotNull { it.rawValue }) }
            .addOnCompleteListener { proxy.close() }
    }
```

```kotlin
// WRONG: closes the buffer while ML Kit still reads it, ignores rotation, and runs on the main thread.
analysis.setAnalyzer(ContextCompat.getMainExecutor(context)) { proxy ->
    scanner.process(InputImage.fromMediaImage(proxy.image!!, 0))
    proxy.close()
}
```

- **Every** `ImageProxy` is closed exactly once on every path. A missed `close()` stalls analysis
  after a few frames while the preview keeps running: "the scanner works once".
- Never keep an `ImageProxy` past the callback; copy pixels (`proxy.toBitmap()`) and close.
- Results reach UI via a `StateFlow`; on close, `clearAnalyzer()` and shut the executor down.
- ML Kit: `MlKitAnalyzer` (camera-mlkit-vision) closes frames for you; with manually bound use
  cases use `COORDINATE_SYSTEM_ORIGINAL` (view-referenced coordinates need `CameraController`).
  Client lifecycle and fallbacks: `on-device-ml`.

## Step 6: capture, rotation and saving

```kotlin
override suspend fun takePhoto(displayName: String): Uri = suspendCancellableCoroutine { cont ->
    val values = ContentValues().apply {
        put(MediaStore.MediaColumns.DISPLAY_NAME, displayName)
        put(MediaStore.MediaColumns.MIME_TYPE, "image/jpeg")
        if (Build.VERSION.SDK_INT >= 29) put(MediaStore.MediaColumns.RELATIVE_PATH, "Pictures/App")
    }
    val options = ImageCapture.OutputFileOptions
        .Builder(resolver, MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values).build()
    imageCapture.takePicture(options, ioExecutor, object : ImageCapture.OnImageSavedCallback {
        override fun onImageSaved(result: ImageCapture.OutputFileResults) {
            val uri = result.savedUri
            if (uri != null) cont.resume(uri) else cont.resumeWithException(IllegalStateException("no uri"))
        }
        override fun onError(e: ImageCaptureException) = cont.resumeWithException(e)
    })
}
```

- Naming, duplicates and failed-entry cleanup follow `media-storage` (API ≤ 28 needs
  `WRITE_EXTERNAL_STORAGE` with `maxSdkVersion="28"`). Private captures (ID card) go to a
  `File` in `cacheDir`, not the gallery. Disable the shutter while a capture is in flight.
- **Rotation**: EXIF/output orientation follows `targetRotation`. If the activity rotates
  freely, the default (display rotation at bind) is right. If it is locked to portrait, update
  `imageCapture.targetRotation` (and `analysis`/`videoCapture`) from an `OrientationEventListener`
  (`references/coordinates-and-rotation.md`); otherwise landscape photos come out sideways.

## Step 7: focus, zoom, flash, torch

```kotlin
// Composable: CameraXViewfinder(surfaceRequest = it, coordinateTransformer = transformer, modifier = Modifier
//   .pointerInput(Unit) { detectTapGestures { with(transformer) { session.focusAt(it.transform()) } } }
//   .pointerInput(Unit) { detectTransformGestures { _, _, zoom, _ -> session.scaleZoom(zoom) } })
// where transformer = remember { MutableCoordinateTransformer() }

override fun focusAt(surfacePoint: Offset) {
    val res = _surfaceRequest.value?.resolution ?: return
    val point = SurfaceOrientedMeteringPointFactory(res.width.toFloat(), res.height.toFloat())
        .createPoint(surfacePoint.x, surfacePoint.y)
    camera?.cameraControl?.startFocusAndMetering(
        FocusMeteringAction.Builder(point).setAutoCancelDuration(3, TimeUnit.SECONDS).build())
}

override fun scaleZoom(factor: Float) {
    val cam = camera ?: return
    val zoom = cam.cameraInfo.zoomState.value ?: return
    cam.cameraControl.setZoomRatio((zoom.zoomRatio * factor).coerceIn(zoom.minZoomRatio, zoom.maxZoomRatio))
}
```

- Raw tap offsets are view coordinates; without the transformer focus lands in the wrong place.
- Zoom/focus futures fail with `OperationCanceledException` when a newer call supersedes them
  mid-pinch; normal, not an error.
- Torch: `cameraControl.enableTorch(on)` only if `cameraInfo.hasFlashUnit()`; reflect
  `cameraInfo.torchState`, not your own boolean. Flash for stills: `imageCapture.flashMode`
  (`FLASH_MODE_AUTO/ON/OFF`). Front lenses usually have no flash unit; hide the button, or use
  `FLASH_MODE_SCREEN` with a screen-flash implementation. Re-read `cameraInfo` per lens.

## Step 8: permissions

- Gate the whole viewfinder composable (and so the binding effect) on `CAMERA`; rationale,
  permanent denial and the settings link are `runtime-permissions`.
- Ask `RECORD_AUDIO` when the user starts recording with sound; if denied, record silently.
  No storage permission for MediaStore writes on API 29+.

## Scope guards

- Camera2 interop, manual ISO/exposure, extensions (night, bokeh), concurrent cameras: out of
  scope; treat as a separate design task and check device support first.
- KMP: CameraX stays in `androidMain` behind `CameraSession`; iOS uses AVFoundation (`kmp-ios-interop`).

## Verification (fail first)

1. ViewModel tests against a `FakeCameraSession` (`references/testing-and-devices.md`): in-flight
   shutter guard, `ImageCaptureException` state, lens switch. Remove the guard once and watch the
   test fail (`verification-discipline`).
2. Analyzer logic tested on bitmaps, not `ImageProxy`; a test that the frame is closed on the
   error path fails when you delete the `close()`.
3. Emulator test (virtual scene, `GrantPermissionRule`): bind, capture, assert the MediaStore row.
4. **Real device is mandatory**: emulators hide focus, torch, rotation and combination bugs. Run
   the device matrix in `references/testing-and-devices.md` and report which rows ran.

## Checklist

- [ ] The "do we need a camera" row is stated; capture intent/picker was ruled out for a reason.
- [ ] All `androidx.camera` artifacts share one version; `camera-camera2` is present.
- [ ] One class binds/unbinds, from one `LaunchedEffect` keyed on owner (+ lens/mode), unbinding
      in `finally`; no `Activity`, `LifecycleOwner` or `PreviewView` held by a ViewModel.
- [ ] Bound use-case set is per mode; unsupported combination is caught with a fallback.
- [ ] Analysis uses `STRATEGY_KEEP_ONLY_LATEST`, a background executor, passes `rotationDegrees`,
      and closes every `ImageProxy` after async work completes.
- [ ] Capture rotation is correct with the activity locked and unlocked.
- [ ] Focus uses the viewfinder's coordinate transformer; torch/flash gated on `hasFlashUnit()`.
- [ ] `CAMERA` gates the viewfinder; `RECORD_AUDIO` only for recording with sound.
- [ ] Fake-seam tests failed once; real-device matrix run and reported.
