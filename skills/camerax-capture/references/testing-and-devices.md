# Testing a CameraX screen

Depth for `camerax-capture` Verification. General test setup (runners, dispatchers, Compose
tests) is in `android-testing`; the fail-first rule is `verification-discipline`.

## Layer 1: the fake session (JVM, fast)

The ViewModel depends on `CameraSession`, never on CameraX types it cannot fake. The fake lets a
test control timing and failure of every call.

```kotlin
class FakeCameraSession : CameraSession {
    override val surfaceRequest = MutableStateFlow<SurfaceRequest?>(null)
    val boundLenses = mutableListOf<Int>()
    val focusPoints = mutableListOf<Offset>()
    var torchOn = false
    var nextPhoto = CompletableDeferred<Uri>()          // test completes or fails it

    override suspend fun bind(appContext: Context, owner: LifecycleOwner, lensFacing: Int) {
        boundLenses += lensFacing
        awaitCancellation()
    }
    override suspend fun takePhoto(displayName: String): Uri = nextPhoto.await()
    override fun focusAt(surfacePoint: Offset) { focusPoints += surfacePoint }
    override fun scaleZoom(factor: Float) = Unit
    override fun setTorch(on: Boolean) { torchOn = on }
}

@Test fun shutterDisabledWhileCapturing() = runTest {
    val session = FakeCameraSession()
    val vm = CameraViewModel(session, StandardTestDispatcher(testScheduler))
    vm.onShutter()
    runCurrent()
    assertThat(vm.state.value.shutterEnabled).isFalse()
    vm.onShutter()                                         // second tap must not start a second capture
    session.nextPhoto.complete(Uri.parse("content://media/external/images/media/1"))
    runCurrent()
    assertThat(vm.state.value.shutterEnabled).isTrue()
    assertThat(vm.state.value.lastPhoto).isNotNull()
}
```

Cover at least: in-flight guard, `ImageCaptureException` mapped to an error state (complete the
deferred exceptionally), lens switch, torch hidden when the lens has no flash, permission denied
state. Break the guard once and watch the first test fail.

`Uri.parse` needs Robolectric or a tiny `Uri` wrapper on the JVM; pick whichever the project
already uses.

## Layer 2: analyzer logic without ImageProxy

Split the analyzer into a thin adapter (owns `ImageProxy`, calls `close()`) and pure logic that
takes a `Bitmap`, a byte array or a small `Frame` interface you own:

```kotlin
interface Frame : AutoCloseable { val rotationDegrees: Int; fun toBitmap(): Bitmap }

class ImageProxyFrame(private val proxy: ImageProxy) : Frame {
    override val rotationDegrees get() = proxy.imageInfo.rotationDegrees
    override fun toBitmap() = proxy.toBitmap()
    override fun close() = proxy.close()
}
```

- Test the logic with fixture images (a QR code PNG, an empty frame, a rotated frame).
- Test the adapter with a fake `Frame` that counts `close()` calls: exactly one on success, on a
  detector failure and on an exception thrown by the logic. Delete the `close()` once and watch
  this test fail; that missing call is the bug that freezes real scanners.
- Implementing `ImageProxy` directly in a fake is possible but its method set changes between
  CameraX versions; the `Frame` seam is cheaper to maintain. `androidx.camera:camera-testing`
  ships fakes for CameraX internals; check its current API before building on it.

## Layer 3: emulator instrumented test

- AVD with the back camera set to `VirtualScene` (a moving 3D room) and front `Emulated`.
- `@get:Rule val permissions = GrantPermissionRule.grant(Manifest.permission.CAMERA)`.
- Bind on the main thread (`bindToLifecycle` requires it) to a `TestLifecycleOwner` in `RESUMED`,
  take a photo through the real `CameraXSession`, then query MediaStore by `DISPLAY_NAME` and
  assert one row with a non-zero size.
- `@After`: `provider.unbindAll()` and delete the inserted row, or the next test sees a busy camera
  or a duplicate name.
- First camera open on a cold CI emulator is slow; use a generous explicit timeout on the first
  await, never `Thread.sleep`.
- This layer proves wiring (binding, permissions, MediaStore), not image quality, focus or
  rotation. Say so in the report.

## Layer 4: real device (mandatory)

Run on at least one real phone; add a low-end or older device when the screen binds three or
more use cases. Report each row as PASS/FAIL/NOT RUN.

| # | Scenario | Expect |
|---|---|---|
| 1 | Open screen, deny then grant `CAMERA` | Rationale, then preview without restart |
| 2 | Photo in portrait, landscape, upside-down (activity free and locked) | Gallery image upright each time |
| 3 | Tap to focus at a corner, pinch zoom to max and back | Focus lands where tapped; zoom clamps |
| 4 | Torch on back lens; switch to front | Torch turns off, button hidden or screen flash |
| 5 | Home during preview, return; rotate during preview | Preview resumes, no black screen, no crash |
| 6 | Another camera app opened while ours is in background | Ours recovers on return |
| 7 | Scanner: hold a code still for 5 s | One result, one navigation, no freeze |
| 8 | Record video with and without `RECORD_AUDIO`, rotate mid-way | Plays back, correct orientation, sound only when granted |
| 9 | Rapid double tap on shutter | One file |
| 10 | Split screen / resize on a tablet or foldable | Viewfinder not stretched, capture still upright |

Watch logcat for `CameraX` / `Camera2CameraImpl` errors and for `ImageAnalysis` warnings about
unclosed images while running the matrix.
