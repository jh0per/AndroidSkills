---
name: fonts-management
description: Fonts in Compose and KMP apps - one brand typeface applied to every Material type role, a generated font registry shared with other clients, downloading fonts on demand with SHA-256 verification and atomic writes, per-family availability state, priority download queues with background prefetch, variable fonts on Android and iOS, and never substituting a different face for document text. Use when adding fonts, a font picker, downloadable fonts, or fixing text that renders in the wrong face.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - fonts
  - typography
  - downloadable fonts
  - variable fonts
  - SHA-256
  - font registry
---

# Fonts

## UI typography

- One brand family applied to **all 15** Material roles; a role left untouched stays in the platform
  face. Load it from the same bundled file the rest of the app uses, not a second copy in resources.

```kotlin
fun Typography.withFontFamily(family: FontFamily) = copy(
    displayLarge = displayLarge.copy(fontFamily = family), displayMedium = displayMedium.copy(fontFamily = family),
    displaySmall = displaySmall.copy(fontFamily = family), headlineLarge = headlineLarge.copy(fontFamily = family),
    headlineMedium = headlineMedium.copy(fontFamily = family), headlineSmall = headlineSmall.copy(fontFamily = family),
    titleLarge = titleLarge.copy(fontFamily = family), titleMedium = titleMedium.copy(fontFamily = family),
    titleSmall = titleSmall.copy(fontFamily = family), bodyLarge = bodyLarge.copy(fontFamily = family),
    bodyMedium = bodyMedium.copy(fontFamily = family), bodySmall = bodySmall.copy(fontFamily = family),
    labelLarge = labelLarge.copy(fontFamily = family), labelMedium = labelMedium.copy(fontFamily = family),
    labelSmall = labelSmall.copy(fontFamily = family),
)
```

- UI text scales with the system font size; user content rendered to a fixed layout (print
  preview, a shared card) does not.

## Content fonts: never substitute

For user-chosen fonts in content that must render identically on every client (web, iOS, server):

- A font is identified by an open family name, not an enum; unknown names survive load/save.
- A missing face renders **no glyphs** (or a placeholder box) rather than a substitute face, which
  would change metrics, line breaks and layout. Show a "font loading/unavailable" state instead.
- The seam answers `FontFamily?`; `null` is a real answer.

```kotlin
interface PlatformFontSupport {                       // CompositionLocal, no default
    fun fontFamilyFor(font: ContentFont): FontFamily?
    fun textMeasurer(): TextMeasurer                  // for rasterising outside composition
    val revision: StateFlow<Int>                      // bumps when a font arrives, so text recomposes
}
```

## One registry for every client

Generate the font registry (family, faces, weight, style, axes, file name, size, sha256, licence)
and the bundled assets from one script for Android, iOS, web and server. Never hand-edit the
generated Kotlin file or copy a family in manually. The generator writes nothing unless every
family resolves (directory, axes and licence found).

## Downloaded fonts

```kotlin
sealed interface FontAvailability {
    data object Bundled : FontAvailability
    data class Downloaded(val faces: List<FontFace>) : FontAvailability
    data object Fetching : FontAvailability
    data class Unavailable(val reason: String) : FontAvailability
}

fun ensureAvailable(family: String) {
    if (family in bundled) return
    when (availability.value[family]) { is FontAvailability.Downloaded, FontAvailability.Fetching, is FontAvailability.Unavailable -> return; else -> Unit }
    availability.update { it + (family to FontAvailability.Fetching) }   // the state itself is the idempotency guard
    scope.launch { resolve(family) }
}

private suspend fun fetchFace(family: String, face: ManifestFace): FontFace? {
    val bytes = (api.download(face.url) as? ApiResult.Success)?.value ?: return fail(family, "download failed")
    if (sha256Hex(bytes) != face.sha256) return fail(family, "checksum mismatch")   // never cached, never rendered
    return store.save(familySlug(family), face.file, bytes) ?: fail(family, "store failed")
}
```

- All faces of a family must succeed; one bad face fails the family.
- Verify the checksum **before** writing. A mismatch is not cached and not retried this session;
  `retryFailed()` clears failures (e.g. on reconnect).
- Load the manifest once behind a `Mutex`.
- File safety: slugs and file names match strict patterns (`[a-z0-9-]+`, no separators, no leading
  dot) so a manifest cannot write outside the font directory. Write to `name.part`, then rename.
- Store in persistent app storage (`filesDir/fonts`; iOS `Application Support`), not a cache
  directory the OS may purge.
- SHA-256 in KMP: a pure-Kotlin implementation tested against the FIPS vectors, or a platform seam.

## Priority queue with background prefetch

When many fonts may be needed (a font picker, a catalogue grid), download the ones on screen first:

```kotlin
class PriorityDownloader<K : Any>(private val scope: CoroutineScope, private val fetch: suspend (K) -> Boolean) {
    private val seq = AtomicInteger()
    private val queue = ConcurrentHashMap<K, Int>()
    private val states = ConcurrentHashMap<K, MutableStateFlow<DownloadState>>()
    private var job: Job? = null

    fun request(keys: List<K>): Map<K, StateFlow<DownloadState>> {
        keys.asReversed().forEach { queue[it] = seq.incrementAndGet() }    // the newest request wins
        pump()
        return keys.associateWith { k -> states.getOrPut(k) { MutableStateFlow(DownloadState.Pending) } }
    }

    private fun pump() {
        if (job?.isActive == true) return
        job = scope.launch {
            while (isActive) {
                val key = queue.maxByOrNull { it.value }?.key ?: break
                val ok = try { fetch(key) } catch (e: CancellationException) { throw e } catch (e: Exception) { false }
                states.getOrPut(key) { MutableStateFlow(DownloadState.Pending) }.value = if (ok) DownloadState.Cached else DownloadState.Failed
                queue.remove(key)
            }
        }
    }
}
enum class DownloadState { Pending, Cached, Failed }
```

Within a family, order faces by need: requested styles first, then Regular, Bold, Italic, Bold
Italic. A background prefetch of the remaining catalogue pauses while foreground requests run and
stops after repeated failures. If storage is cleared at runtime, resync the states.

## Variable fonts

Expand a variable face into weight entries (W100–W900):

- Android: `Font(file, weight = FontWeight(w))` derives the variation from the weight.
- iOS/Skia: pass `variationSettings = FontVariation.Settings(FontVariation.weight(w), FontVariation.italic(…))`
  explicitly and give each weight a unique identity; Skia caches by identity and otherwise renders
  every weight the same.

## Prebundling

A Gradle task can download the default font set into assets at build time (with a blocklist and a
generated index containing per-family alphabet coverage). Write it with `@OutputDirectory` and do
network work only in `@TaskAction` (see `gradle-build-setup`).

## Tests

- Registry generator output is fresh (a test regenerates and diffs).
- Checksum mismatch → Unavailable, nothing written.
- Path-escaping names rejected.
- Instrumented: a downloaded (non-bundled) family renders, served from a local test server via
  `adb reverse tcp:<port> tcp:<port>`; a skipped test is not evidence.
