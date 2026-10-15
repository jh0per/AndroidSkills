---
name: media-storage
description: Images and files on Android - saving to the shared gallery with MediaStore (IS_PENDING, deterministic names, cleanup on failure), sharing a gallery content URI, photo picker and camera capture contracts, bounded bitmap decoding with inSampleSize, size-budgeted re-encoding that respects alpha, Coil 3 image loading, and WorkManager uploads. Use when saving, sharing, picking, capturing, decoding, uploading or displaying images.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - MediaStore
  - photo picker
  - camera capture
  - bitmap decoding
  - Coil
  - WorkManager
  - FileProvider
---

# Media and storage

## Save to the gallery (MediaStore)

Two seams: a **writer** that needs only a `Context` (Koin), and a **permission asker** that needs an
Activity (CompositionLocal).

```kotlin
class AndroidDeviceGallery(context: Context, private val io: CoroutineDispatcher = Dispatchers.IO) : DeviceGallery {
    private val resolver = context.contentResolver

    override suspend fun save(picture: SaveablePicture): SaveResult = withContext(io) {
        val name = galleryFileName(picture.id, picture.mimeType)
        if (existingUri(name) != null) return@withContext SaveResult.AlreadySaved     // idempotent
        writeNew(name, picture)
    }

    private fun writeNew(name: String, picture: SaveablePicture): SaveResult {
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, name)
            put(MediaStore.Images.Media.MIME_TYPE, picture.mimeType)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/$ALBUM")
                put(MediaStore.Images.Media.IS_PENDING, 1)              // invisible to other apps while writing
            }
        }
        val uri = runCatching { resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) }.getOrNull()
            ?: return SaveResult.Failed(SaveFailure.Unwritable)
        try {
            resolver.openOutputStream(uri)?.use { it.write(picture.bytes) } ?: throw IOException("no stream")
        } catch (e: IOException) {
            resolver.delete(uri, null, null)                            // never leave a partial file that looks valid
            return SaveResult.Failed(if (e.isOutOfSpace()) SaveFailure.NoSpace else SaveFailure.Unwritable)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            resolver.update(uri, ContentValues().apply { put(MediaStore.Images.Media.IS_PENDING, 0) }, null, null)
        }
        return SaveResult.Saved(uri)
    }
}

/** Derived from the picture's own id, not the clock: MediaStore de-duplicates by renaming ("x (1).png"). */
fun galleryFileName(id: String, mimeType: String): String =
    "app-" + id.replace(Regex("[^A-Za-z0-9_-]"), "_") + extensionFor(mimeType)
```

- Save into the shared `Pictures/<Album>` collection, never the app-private directory, where nobody
  can find the file and an uninstall deletes it.
- Declare `WRITE_EXTERNAL_STORAGE` with `android:maxSdkVersion="28"` and ask for it **at the save**,
  only on API ≤ 28. On API 29+ the permission seam answers "granted" without prompting.
- `existingUri(name)`: query `DISPLAY_NAME = ? AND RELATIVE_PATH LIKE ?`.
- Prove it on a device: an instrumented test writes through the real MediaStore, reads the bytes
  back, saves again and asserts `AlreadySaved` with exactly one file. Clean up by name prefix,
  because a failed run leaves `name (1).png` behind.

## Share

Share the gallery's own `content://` URI after saving, rather than an invisible cache copy behind a
`FileProvider`; the person who shares to another app can then also find the file.

```kotlin
val send = Intent(Intent.ACTION_SEND).apply {
    type = mimeType
    putExtra(Intent.EXTRA_STREAM, uri)
    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
}
context.startActivity(Intent.createChooser(send, null).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
```

## Pick and capture

- Photo picker: `rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia())` with
  `PickVisualMediaRequest(ImageOnly)`; `PickMultipleVisualMedia(max)` for ordered multi-select.
  No storage permission needed.
- Camera: `ActivityResultContracts.TakePicture()` into a MediaStore or `FileProvider` URI created
  before launch. A custom contract should override `getSynchronousResult` to fail fast when no
  camera app resolves the intent.
- Validate picked input before upload: MIME type, byte size and **decoded pixel count**
  (dimensions via `inJustDecodeBounds`), and tell the person which limit was exceeded.

## Bounded decoding

Never decode a camera photo at full size for display.

```kotlin
fun decodedSize(bytes: ByteArray): IntSize? {
    val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, o)
    return if (o.outWidth <= 0 || o.outHeight <= 0) null else IntSize(o.outWidth, o.outHeight)
}

/** Power-of-two sampling so the longest side is at most maxSide (default 2048). */
fun decodePreview(bytes: ByteArray, maxSide: Int = 2048): Bitmap? {
    val longest = decodedSize(bytes)?.let { maxOf(it.width, it.height).toLong() } ?: return null
    var sample = 1
    while ((longest + sample - 1) / sample > maxSide) sample *= 2
    return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })
}
```

- Keep the original encoded bytes for saving/exporting; the bounded bitmap is for display.
- `remember(image) { decodePreview(image.bytes) }` in composables; decode off the main thread for
  large inputs.
- Test with a 4032×3024 fixture: bounded result dimensions, allocation at least an order of
  magnitude smaller, alpha preserved, odd panoramas, invalid bytes → null/placeholder.
- On API 28+ `ImageDecoder` with `setTargetSize` is an alternative; keep one policy per call site.

## Re-encoding to a budget

When images are attached to uploads:

- Cap the longest side (e.g. 2048 px); skip re-encoding when already within the cap so a second
  save is free; discard a re-encode that came back **larger**.
- **Alpha chooses the format.** A cut-out with transparency gets a lossless encoding (PNG or
  `WEBP_LOSSLESS`); a lossy format that drops the channel returns a white box where the transparency was.
- Do the encode on `Dispatchers.Default`, and when the result is adopted back into editable state,
  only replace the element if it still holds the picture that was encoded.

## Coil 3

```kotlin
fun appImageLoader(context: PlatformContext, engine: HttpClientEngine): ImageLoader =
    ImageLoader.Builder(context)
        .components { add(KtorNetworkFetcherFactory(httpClient = { HttpClient(engine) })) }  // shares the engine, not the authed client
        .build()
```

- Build one loader in common code; each platform passes only its context. Register it in Koin;
  tests use a no-op loader.
- Public image URLs never carry the API bearer. Private images use short-lived signed URLs or bytes
  fetched through the authenticated repository, never a bearer-required URL handed to Coil.
- Resolve relative thumbnail URLs before the state reaches render-only UI. Cache-bust with a
  version query parameter instead of TTL tuning.
- In lazy lists use `AsyncImage` with the placeholder drawn as a layer underneath; ban
  `SubcomposeAsyncImage` (subcomposition per cell) with a detekt `ForbiddenImport`.

## Background uploads (WorkManager)

```kotlin
class UploadWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params), KoinComponent {
    private val uploader: Uploader by inject()
    override suspend fun doWork(): Result {
        if (runAttemptCount >= MAX_ATTEMPTS) return Result.failure()      // return it, do not fall through
        val uri = inputData.getString(KEY_URI)?.toUri() ?: return Result.failure()
        return when (uploader.upload(uri)) {
            UploadOutcome.Done -> Result.success()
            UploadOutcome.Transient -> Result.retry()
            UploadOutcome.Permanent -> Result.failure()
        }
    }
}
```

Enqueue with `setConstraints(Constraints(requiredNetworkType = NetworkType.CONNECTED))`,
exponential backoff, and unique work names per item to avoid duplicates.
