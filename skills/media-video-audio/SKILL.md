---
name: media-video-audio
description: Video and audio in Android apps with Media3 - ExoPlayer lifecycle and pooling for muted looping previews, a single shared SimpleCache with the right data-source chain, audio focus, range looping, timeline thumbnails with MediaMetadataRetriever, waveform/histogram rendering, trim range controls, Media3 Transformer transcoding wrapped in coroutines, and background download workers. Use when adding playback, previews, trimming, thumbnails, transcoding or media downloads.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Media3
  - ExoPlayer
  - SimpleCache
  - audio focus
  - thumbnails
  - waveform
  - Transformer
  - trim
---

# Video and audio (Media3)

## Players

- One `ExoPlayer` per visible surface; release every player you create. A small registry that
  tracks created players and releases them together (`releaseAll()` on screen dispose) prevents leaks
  in feeds that show many previews.
- Muted looping previews: `volume = 0f`, `repeatMode = REPEAT_MODE_ALL`, `playWhenReady = true`, and
  pause when off screen (`LifecycleResumeEffect` / `DisposableEffect`).
- Remove listeners **before** `release()`; never touch a player after release.
- Wait for readiness with a `Player.Listener` (`onPlaybackStateChanged(STATE_READY)`) wrapped in
  `suspendCancellableCoroutine`, not a polling loop.
- Audible playback takes audio focus: `setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MUSIC).build(), /* handleAudioFocus = */ true)`.
- Loop a sub-range with `ClippingMediaSource`/`MediaItem.ClippingConfiguration` instead of seeking from
  a timer. Report position for UI with a ticker at frame rate (~16–33 ms) only while playing.
- Debug-only `EventLogger`.

```kotlin
@Composable
fun VideoPreview(uri: Uri, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val player = remember(uri) {
        ExoPlayer.Builder(context).setMediaSourceFactory(DefaultMediaSourceFactory(MediaCache.dataSourceFactory(context))).build().apply {
            setMediaItem(MediaItem.fromUri(uri)); volume = 0f; repeatMode = Player.REPEAT_MODE_ALL; playWhenReady = true; prepare()
        }
    }
    LifecycleResumeEffect(player) { player.play(); onPauseOrDispose { player.pause() } }
    DisposableEffect(player) { onDispose { player.release() } }
    PlayerSurface(player = player, modifier = modifier)          // media3-ui-compose; or AndroidView { PlayerView(it) }
}
```

## Cache

```kotlin
@OptIn(UnstableApi::class)
object MediaCache {
    @Volatile private var cache: SimpleCache? = null
    // Exactly one SimpleCache per directory per process, or it throws.
    fun get(context: Context): SimpleCache = cache ?: synchronized(this) {
        cache ?: SimpleCache(File(context.cacheDir, "media"), LeastRecentlyUsedCacheEvictor(100L * 1024 * 1024),
            StandaloneDatabaseProvider(context)).also { cache = it }
    }
    fun dataSourceFactory(context: Context): DataSource.Factory {
        val upstream = DefaultDataSource.Factory(context, DefaultHttpDataSource.Factory())   // handles file:// AND http(s)
        return CacheDataSource.Factory().setCache(get(context)).setUpstreamDataSourceFactory(upstream)
            .setFlags(CacheDataSource.FLAG_IGNORE_CACHE_ON_ERROR)
    }
}
```

Use a `DefaultDataSource` as upstream (it routes local and remote URIs); an HTTP-only factory fails
on local files. Authenticated media: set headers on `DefaultHttpDataSource.Factory().setDefaultRequestProperties(...)`
only for your own hosts.

## Timeline thumbnails

```kotlin
suspend fun timelineFrames(context: Context, uri: Uri, count: Int, heightPx: Int): List<Bitmap> = withContext(Dispatchers.IO) {
    val retriever = MediaMetadataRetriever()
    try {
        retriever.setDataSource(context, uri)
        val durationUs = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)!!.toLong() * 1000
        val step = durationUs / count
        (0 until count).mapNotNull { i ->
            ensureActive()
            if (Build.VERSION.SDK_INT >= 27) {
                retriever.getScaledFrameAtTime(i * step, MediaMetadataRetriever.OPTION_CLOSEST_SYNC, heightPx * 2, heightPx)
            } else {
                retriever.getFrameAtTime(i * step, MediaMetadataRetriever.OPTION_CLOSEST_SYNC)?.let { full ->
                    Bitmap.createScaledBitmap(full, full.width * heightPx / full.height, heightPx, true).also { if (it !== full) full.recycle() }
                }
            }
        }
    } finally {
        retriever.release()                                     // always release; it holds native decoders
    }
}
```

- Respect `METADATA_KEY_VIDEO_ROTATION` when scaling frames for a strip.
- Show the first frame in every slot immediately, then replace progressively.
- `OPTION_CLOSEST_SYNC` is fast; `OPTION_CLOSEST` is exact but decodes from the previous keyframe.
- Number of thumbnails: `max(minCount, ceil(stripWidth / frameWidth))`.

## Waveform / histogram

Server-provided or decoded amplitudes compressed to the bar count by block averaging, normalised to
the max, drawn in a Compose `Canvas` with played bars in the accent colour:

```kotlin
fun compress(samples: FloatArray, bars: Int): FloatArray {
    if (samples.isEmpty() || bars <= 0) return FloatArray(bars)
    val block = (samples.size / bars).coerceAtLeast(1)          // guard: fewer samples than bars
    val out = FloatArray(bars) { b ->
        val from = b * block
        if (from >= samples.size) 0f else samples.copyOfRange(from, minOf(from + block, samples.size)).average().toFloat()
    }
    val max = out.maxOrNull()?.takeIf { it > 0f } ?: return out
    return FloatArray(bars) { out[it] / max }
}
```

## Trim control (voice notes, clips for sharing)

A trim range view has: start/end thumbs with ≥48dp touch targets, a minimum and maximum duration, a
playback pointer, dimmed regions outside the range, and haptic feedback at limits. Emit range changes
continuously for preview (`submit = false`) and once on release for history (see
`compose-canvas-gestures`). In a View-based screen, a Compose waveform can live inside the custom view
via `ComposeView` reading `StateFlow`s with `collectAsState()`.

## Transcoding with Transformer

```kotlin
@OptIn(UnstableApi::class)
suspend fun transcode(context: Context, input: Uri, output: File, removeAudio: Boolean): Boolean =
    withContext(Dispatchers.Main) {                              // Transformer needs a Looper thread
        suspendCancellableCoroutine { cont ->
            val transformer = Transformer.Builder(context)
                .setVideoMimeType(MimeTypes.VIDEO_H264)
                .addListener(object : Transformer.Listener {
                    override fun onCompleted(composition: Composition, result: ExportResult) { if (cont.isActive) cont.resume(true) }
                    override fun onError(composition: Composition, result: ExportResult, e: ExportException) { if (cont.isActive) cont.resume(false) }
                })
                .build()
            cont.invokeOnCancellation { transformer.cancel() }
            val item = EditedMediaItem.Builder(MediaItem.fromUri(input)).setRemoveAudio(removeAudio).build()
            transformer.start(item, output.path)
        }
    }
```

- Check preconditions (e.g. cached output already exists) **before** suspending; never resume a
  continuation twice.
- Use it to produce seekable/normalised local copies (H.264, constant frame rate) for scrubbing.
- Heavy compositions (multi-track export with text and effects) are often better rendered on a
  server; then track the job with push plus a polling fallback and download the result.

## Downloads

- WorkManager `CoroutineWorker` with `enqueueUniqueWork(mediaId, ExistingWorkPolicy.KEEP, …)` and a
  network constraint; long downloads call `setForeground` (Android 14 requires a foreground service
  type such as `dataSync`).
- Save user-visible results through MediaStore (`media-storage`), not `DownloadManager` into public
  directories.

## Tests

Unit-test pure helpers (compress, frame count, range clamping). Instrumented tests on a real device
with a short fixture video for thumbnail extraction and transcoding; emulators often lack hardware
codecs and can mislead.
