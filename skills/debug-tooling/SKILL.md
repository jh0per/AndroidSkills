---
name: debug-tooling
description: Debug-only tooling for Android apps - HTTP inspector with a no-op release artifact, logging gated on build type, Timber trees that forward to crash reporting, a hidden debug menu opened by gesture or key sequence, mock repository overrides by delegation, StrictMode and LeakCanary, Compose recomposition diagnostics, and keeping all of it out of release builds. Use when adding developer tooling, investigating network or performance problems, or reviewing what ships in a release build.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - debug menu
  - HTTP inspector
  - Timber
  - StrictMode
  - LeakCanary
  - recomposition
  - debugImplementation
---

# Debug tooling

Rule zero: nothing in this skill ships active in a release build. Use `debugImplementation`
modules, no-op release artifacts, or `if (BuildConfig.DEBUG)` at the composition root, and check
the release APK.

## HTTP inspection

```kotlin
dependencies {
    debugImplementation(libs.chucker)                 // com.github.chuckerteam.chucker:library
    releaseImplementation(libs.chucker.noop)          // library-no-op: same API, does nothing
}
// OkHttp engine config: addInterceptor(ChuckerInterceptor(context)) unconditionally (no-op in release)
```

- `HttpLoggingInterceptor.Level.BODY`, Ktor `Logging` and image-loader debug loggers only when
  `BuildConfig.DEBUG`; always redact `Authorization` and cookies.
- Never log request bodies that contain personal data even in debug builds shared with testers.

## Logging

```kotlin
class App : Application() {
    override fun onCreate() {
        super.onCreate()
        if (BuildConfig.DEBUG) Timber.plant(Timber.DebugTree()) else Timber.plant(CrashReportingTree())
    }
}

class CrashReportingTree : Timber.Tree() {
    override fun isLoggable(tag: String?, priority: Int) = priority >= Log.WARN
    override fun log(priority: Int, tag: String?, message: String, t: Throwable?) {
        FirebaseCrashlytics.getInstance().log("${tag.orEmpty()}: $message")
        if (t != null && priority >= Log.ERROR) FirebaseCrashlytics.getInstance().recordException(t)
    }
}
```

Unwrap wrapper exceptions (e.g. a `BackendException(original)`) before recording, so crash groups
point at the real cause. Disable crash collection in debug builds.

## Hidden debug menu

A `:debug-menu` module added with `debugImplementation` (or included only in an internal flavour).
Open it with something a tester can do and a user will not stumble on:

```kotlin
// Pointer-count sequence: tap with 1, 2, 3, 2, 1 fingers within a time window.
class GestureSequenceLauncher(private val sequence: List<Int> = listOf(1, 2, 3, 2, 1), private val open: () -> Unit) {
    private val taps = ArrayDeque<Int>()
    private var maxPointers = 0
    fun onTouchEvent(event: MotionEvent) {
        maxPointers = maxOf(maxPointers, event.pointerCount)
        if (event.actionMasked == MotionEvent.ACTION_UP) {
            taps.addLast(maxPointers); maxPointers = 0
            while (taps.size > sequence.size) taps.removeFirst()
            if (taps.toList() == sequence) { taps.clear(); open() }
        }
    }
}
// In the debug Activity wrapper: override dispatchTouchEvent → launcher.onTouchEvent(ev); return super...
// Alternative trigger: a volume-key sequence in onKeyDown, or a debug notification / app shortcut.
```

Menu contents that pay off: environment switch (with restart), feature-flag overrides, clear
caches/DB/prefs, show current tokens' expiry (never the token), copy push token, force crash,
trigger ANR, toggle mock responses, open the HTTP inspector, app/version/commit info.

## Mock overrides by delegation

Override one call, delegate the rest to the real implementation:

```kotlin
internal class OrdersRepositoryDebug(
    private val real: OrdersRepositoryImpl,
    private val menu: DebugSettings,
) : OrdersRepository by real {
    override suspend fun orders(page: Int): List<Order> = when (menu.ordersMock) {
        MockMode.Off -> real.orders(page)
        MockMode.Empty -> emptyList()
        MockMode.ServerError -> throw ServerUnavailableException()
        MockMode.Slow -> { delay(5_000); real.orders(page) }
    }
}

// debug source set only
val DebugOverridesModule = module {
    single { OrdersRepositoryImpl(get(), get()) }
    single<OrdersRepository> { OrdersRepositoryDebug(get(), get()) }
}
// startKoin { allowOverride(true); modules(prodModules + DebugOverridesModule) }  // explicit, debug only
```

Put the override module in `src/debug/` so release cannot load it; rely on explicit
`allowOverride(true)` rather than accidental module order.

## Runtime diagnostics (debug only)

- **StrictMode** in `Application.onCreate`: `detectDiskReads/Writes/Network` with `penaltyLog()`
  (or `penaltyDeath()` on CI instrumented runs) and VM policy `detectLeakedClosableObjects`.
- **LeakCanary**: `debugImplementation` only; it installs itself.
- **Compose**: Layout Inspector recomposition counts; compiler reports
  (`-PcomposeCompilerReports=true`, see `gradle-build-setup`) to find unstable parameters; use
  immutable collections or `@Immutable`/`@Stable` and stable lambdas.
- **Performance**: Baseline Profiles + Macrobenchmark for startup and scrolling, measured on a
  release-like build on a real device.

## Verify release is clean

```bash
./gradlew :app:assembleRelease
unzip -l app/build/outputs/apk/release/app-release.apk | grep -iE 'chucker|leakcanary|debugmenu' || echo "clean"
aapt2 dump xmltree --file AndroidManifest.xml app-release.apk | grep -i debug
```

A grep that returns nothing proves something only if the same grep finds the class in the debug
APK (control; see `verification-discipline`).

## Internal tools in release builds (when you must)

Sometimes support or QA needs tooling on store builds. Then:

- Gate it by a **server-enforced allowlist** (remote config list of internal accounts, checked again
  by the backend for any privileged call), not by a hidden gesture alone.
- When disabled, every hook is a no-op (interceptors return `chain.proceed(request)` immediately).
- Useful contents: environment switch (prod/staging/feature environments rewriting the API host,
  then restart with ProcessPhoenix), per-endpoint delay and fault injection, feature-flag and
  experiment overrides read by the flag layer (`analytics-feature-flags`), currency/locale override,
  design-system gallery, and a screenshot overlay tool (a reference image over the screen with
  adjustable alpha).

## Proving crash reporting works

Collection disabled in debug, so verify the release pipeline deliberately: a debug-only intent extra
sets a one-shot flag, the next launch enables collection and throws a distinctive exception type,
and the flag is consumed. Check the report arrives deobfuscated. This proves the pipeline without
polluting release data.

## Startup hygiene

Heavy `Application.onCreate` (many SDKs, DB init, prefetches) delays first frame. Initialise lazily
or through App Startup, keep only what the first screen needs on the main thread, and measure with
Macrobenchmark. If WorkManager is initialised manually, remove its startup provider from the
manifest. Create the Room database before or lazily within DI, never in two places.
