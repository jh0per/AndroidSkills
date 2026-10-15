# VideoCapture and Recorder

Depth for `camerax-capture` Step 4. Needs `androidx.camera:camera-video` at the same version as
the other camera artifacts. Playback, trimming and transcoding of the result belong to
`media-video-audio`.

## Build once, in the session

```kotlin
private val recorder = Recorder.Builder()
    .setQualitySelector(QualitySelector.from(Quality.FHD, FallbackStrategy.lowerQualityOrHigherThan(Quality.SD)))
    .build()
private val videoCapture = VideoCapture.Builder(recorder)
    .setMirrorMode(MirrorMode.MIRROR_MODE_ON_FRONT_ONLY)   // selfie video looks like the preview
    .build()
private var recording: Recording? = null
```

- Always give the `QualitySelector` a fallback. A bare `Quality.UHD` on a device without it fails
  the bind or the recording, depending on version.
- To show only qualities the lens supports, query
  `Recorder.getVideoCapabilities(camera.cameraInfo).getSupportedQualities(DynamicRange.SDR)` after
  binding; it differs between front and back lenses.
- Video mode binds `Preview + VideoCapture` (optionally `ImageCapture` for stills). Leave
  `ImageAnalysis` out while recording unless you checked the combination on low-end devices.

## Start, observe, stop

```kotlin
fun startRecording(context: Context, displayName: String, withAudio: Boolean, onEvent: (RecordingUiEvent) -> Unit) {
    check(recording == null) { "already recording" }
    val values = ContentValues().apply {
        put(MediaStore.MediaColumns.DISPLAY_NAME, displayName)
        put(MediaStore.MediaColumns.MIME_TYPE, "video/mp4")
        if (Build.VERSION.SDK_INT >= 29) put(MediaStore.MediaColumns.RELATIVE_PATH, "Movies/App")
    }
    val output = MediaStoreOutputOptions.Builder(context.contentResolver, MediaStore.Video.Media.EXTERNAL_CONTENT_URI)
        .setContentValues(values)
        .build()
    val pending = recorder.prepareRecording(context, output)
        .let { if (withAudio && hasAudioPermission(context)) it.withAudioEnabled() else it } // keep the returned value
    recording = pending.start(ContextCompat.getMainExecutor(context)) { event ->
        when (event) {
            is VideoRecordEvent.Start -> onEvent(RecordingUiEvent.Started)
            is VideoRecordEvent.Status -> onEvent(RecordingUiEvent.Progress(event.recordingStats.recordedDurationNanos))
            is VideoRecordEvent.Finalize -> {
                recording = null
                onEvent(
                    if (event.hasError()) RecordingUiEvent.Failed(event.error, event.outputResults.outputUri)
                    else RecordingUiEvent.Saved(event.outputResults.outputUri),
                )
            }
        }
    }
}

fun stopRecording() { recording?.stop() }   // the result arrives later as Finalize, not here
```

Rules the code encodes:

- Builder-style calls on `PendingRecording` (`withAudioEnabled()`, `asPersistentRecording()`)
  must be chained or reassigned. Calling `pending.withAudioEnabled()` on its own line and then
  `pending.start(…)` is the classic silent-video bug.
- `withAudioEnabled()` requires `RECORD_AUDIO` at call time and throws `SecurityException`
  without it. Check right before calling, not only at screen entry; the user can revoke it in
  between.
- UI state comes from events. "Recording" starts at `VideoRecordEvent.Start`, not when the
  button is tapped; the file exists only after `Finalize`.
- `Finalize` with an error can still carry a usable file (for example a size or duration limit
  was reached, or the source became inactive). Branch on `event.error` codes such as
  `ERROR_FILE_SIZE_LIMIT_REACHED`, `ERROR_SOURCE_INACTIVE`, `ERROR_INSUFFICIENT_STORAGE`,
  `ERROR_NO_VALID_DATA`, and delete the MediaStore row only when no valid data was written.
- Only one active `Recording` per `Recorder`. Guard the start button, and null the reference in
  `Finalize` so `pause()`/`resume()`/`stop()` are never sent to a finished recording.

## Lifecycle interaction

- Unbinding `VideoCapture` (lens switch, mode change, leaving the screen, `ON_STOP`) ends the
  recording with `ERROR_SOURCE_INACTIVE`. Decide what that means for the product (keep the
  partial file, or warn before switching) and test it.
- `asPersistentRecording()` (experimental opt-in) keeps a recording alive across a rebind, for
  example a lens switch mid-recording. Use it only when that feature is required, and verify on a
  real device.
- Long recordings are foreground work in the user's hands; do not try to continue recording
  from a background service with CameraX lifecycle binding.
- Set `setFileSizeLimit` / `setDurationLimitMillis` on the output options builder when the
  upload path has a limit, rather than trimming afterwards.

## Verify

- Record 10 s with audio, 10 s without permission (audio denied), and with the device rotated
  mid-recording; play each file back and check orientation and sound.
- Press Home while recording; confirm the UI shows the partial-file outcome you chose.
- On a low-end device, bind your video-mode set and check no `IllegalArgumentException` and the
  quality you report matches `getSupportedQualities`.
