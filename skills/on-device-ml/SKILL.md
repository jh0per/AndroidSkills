---
name: on-device-ml
description: On-device ML on Android with ML Kit and LiteRT (TensorFlow Lite) - selfie and subject segmentation (background blur, portrait effects), unbundled versus bundled models, coroutine await, threading, mask scaling and alpha application, client lifecycle, unsupported-device fallback to a server path, and tests. Use when adding segmentation, labelling, detection or any on-device inference.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - ML Kit
  - segmentation
  - LiteRT
  - TensorFlow Lite
  - on-device inference
  - model download
  - server fallback
---

# On-device ML

## Pick the model delivery

| Option | Size cost | Availability |
|---|---|---|
| ML Kit **unbundled** (`play-services-mlkit-*`) | ~0 in APK, downloaded by Play services | needs Play services; may be "not yet downloaded" |
| ML Kit **bundled** (`com.google.mlkit:*`) | model in APK (MBs) | works offline immediately |
| LiteRT/TFLite custom model | your model in APK or downloaded | full control, you own pre/post-processing |

Unbundled models can be unavailable: the seam must answer **Unsupported** and the product must
offer the alternative (e.g. server-side processing), not crash or spin. Request the module install
with `ModuleInstallClient` if you want to prompt the download early.

## Seam

```kotlin
// common
sealed interface SegmentationResult {
    data class Done(val pngWithAlpha: ByteArray) : SegmentationResult
    data object Unsupported : SegmentationResult      // offer the server path
    data class Failed(val message: String) : SegmentationResult
}
interface ImageSegmenter { suspend fun segment(image: ByteArray): SegmentationResult }
```

## Selfie segmentation (Android)

```kotlin
class MlKitImageSegmenter : ImageSegmenter {
    override suspend fun segment(image: ByteArray): SegmentationResult = withContext(Dispatchers.Default) {
        val bitmap = decodePreview(image) ?: return@withContext SegmentationResult.Failed("Unreadable image")
        val segmenter = Segmentation.getClient(
            SelfieSegmenterOptions.Builder().setDetectorMode(SelfieSegmenterOptions.SINGLE_IMAGE_MODE).build(),
        )
        try {
            val mask = segmenter.process(InputImage.fromBitmap(bitmap, 0)).await()   // kotlinx-coroutines-play-services
            SegmentationResult.Done(applyMask(bitmap, mask, threshold = 0.5f).encodePng())
        } catch (e: MlKitException) {
            if (e.errorCode == MlKitException.UNAVAILABLE) SegmentationResult.Unsupported else SegmentationResult.Failed(e.message.orEmpty())
        } finally {
            segmenter.close()
        }
    }
}

fun applyMask(src: Bitmap, mask: SegmentationMask, threshold: Float): Bitmap {
    val w = src.width; val h = src.height
    val pixels = IntArray(w * h).also { src.getPixels(it, 0, w, 0, 0, w, h) }
    val confidence = FloatArray(mask.width * mask.height).also { mask.buffer.rewind(); mask.buffer.asFloatBuffer().get(it) }
    for (y in 0 until h) {
        val my = (y * mask.height / h).coerceIn(0, mask.height - 1)
        for (x in 0 until w) {
            val mx = (x * mask.width / w).coerceIn(0, mask.width - 1)
            val c = confidence[my * mask.width + mx]
            val alpha = if (c >= threshold) 255 else 0           // or (c * 255) for soft edges
            pixels[y * w + x] = (pixels[y * w + x] and 0x00FFFFFF) or (alpha shl 24)
        }
    }
    return Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888).apply { setPixels(pixels, 0, w, 0, 0, w, h) }
}
```

Subject segmentation (`play-services-mlkit-subject-segmentation`) returns a foreground bitmap or
confidence mask directly and handles non-person subjects; prefer it for objects.

## Rules

- Never run inference or per-pixel loops on Main; never build ViewModels or scopes by hand to do it
  (use `viewModelScope` or the screen's own scope).
- Decode bounded (≤2048 px) before inference; models work at low resolution and full-size bitmaps
  waste memory. Scale the mask to the **output** size, not the input preview, when saving.
- Close detectors/segmenters (`close()`) or reuse one per screen lifetime.
- Keep alpha through the rest of the pipeline: encode masked output losslessly (PNG/WebP lossless).
- Bill and label work by **where it runs**: on-device is free and private; server fallback may cost
  credits and must be explicit to the person.
- Mark tests that need the real model with an annotation (e.g. `@RequiresOnDeviceModel`)
  and exclude them on CI emulators that lack Play services modules.

## LiteRT sketch

```kotlin
val interpreter = Interpreter(loadModelFile(context, "model.tflite"), Interpreter.Options().apply {
    setNumThreads(4)
    // addDelegate(GpuDelegate()) when supported; fall back to CPU on failure
})
val input = ByteBuffer.allocateDirect(1 * H * W * 3 * 4).order(ByteOrder.nativeOrder())
// fill normalised floats, run, post-process; interpreter.close() when done
```

Keep the model file uncompressed in the APK (`androidResources { noCompress += "tflite" }`).

## Tests

- Unit-test mask application with synthetic masks (all zero, all one, half split, non-square sizes).
- Instrumented test on a real device with a fixture photo: output has transparent background pixels
  and opaque subject pixels at known coordinates.

## Make sure the model is actually there

Checking that Play services exists is not enough: an unbundled model may not be downloaded yet, and
the segmenter then fails at first use. Prepare explicitly and cache the answer:

```kotlin
suspend fun prepareOnDevice(): Boolean = cachedReady ?: withContext(io) {
    if (Build.VERSION.SDK_INT < MIN_SDK || !playServicesAvailable()) return@withContext false
    try {
        val client = ModuleInstall.getClient(context)
        val segmenter = SubjectSegmentation.getClient(options)
        if (client.areModulesAvailable(segmenter).await().areModulesAvailable()) return@withContext true
        // Request the download; completion arrives through an InstallStatusListener passed to the request
        // (setListener), so wait for STATE_COMPLETED there (with a timeout) before answering true.
        client.installModules(ModuleInstallRequest.newBuilder().addApi(segmenter).setListener(listener).build()).await()
        awaitCompleted(listener, timeout = 60.seconds)
    } catch (e: ApiException) {
        false
    }
}.also { cachedReady = it }
```

The UI calls `prepareOnDevice()` when the tool appears; `null` = checking (button disabled), `true` =
enabled, `false` = offer the server path. Use separate injected dispatchers for install (IO) and
inference (Default). `Unsupported` is permanent (route to the alternative); `Failed` is retryable
and must not silently turn into an upsell.
