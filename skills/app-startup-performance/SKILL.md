---
name: app-startup-performance
description: Measure and improve Android app startup and runtime performance with evidence - Macrobenchmark for cold/warm startup and scroll jank, Baseline and Startup Profiles with the baselineprofile Gradle plugin, reportFullyDrawn, lazy initialisation and App Startup, main-thread and Koin startup hygiene, Perfetto/system tracing with custom trace sections, JankStats, memory and allocation checks, ANR triage, and a before/after report format. Use when startup feels slow, frames drop, an ANR or jank report arrives, before a release that adds SDKs, or when asked to "make the app faster". Do not use for Compose recomposition audits (see compose-performance-audit) or for build speed (see gradle-build-setup).
metadata:
  last-updated: '2026-10-15'
  keywords:
  - app startup
  - cold start
  - Macrobenchmark
  - Baseline Profiles
  - Startup Profiles
  - reportFullyDrawn
  - Perfetto
  - system tracing
  - JankStats
  - ANR
  - memory
  - performance regression
---

# App startup and runtime performance

Rule zero: a performance claim without a number from a release build on a real device is an
opinion. Measure, change one thing, measure again, keep the numbers in the PR.

## Prerequisites

- A `release`-like build variant with R8 enabled and a debug-signed, `debuggable=false`
  `benchmark` variant (or `nonMinifiedRelease` from the baseline-profile plugin) for measuring.
  Never profile a debuggable build; ART runs it unoptimised.
- A physical device, screen on, charged, airplane mode off only if the start path needs network
  (and then the backend is a local mock). Emulators give directional numbers only.

## Step 1: measure before touching anything

Add `:benchmark` (com.android.test) with `androidx.benchmark.macro.junit4`:

```kotlin
@RunWith(AndroidJUnit4::class)
class StartupBenchmark {
    @get:Rule val rule = MacrobenchmarkRule()

    @Test fun coldStartupNone() = startup(CompilationMode.None())
    @Test fun coldStartupBaselineProfile() = startup(CompilationMode.Partial(BaselineProfileMode.Require))

    private fun startup(mode: CompilationMode) = rule.measureRepeated(
        packageName = "com.example.app",
        metrics = listOf(StartupTimingMetric(), FrameTimingMetric()),
        compilationMode = mode,
        startupMode = StartupMode.COLD,
        iterations = 10,
    ) {
        pressHome()
        startActivityAndWait()
        device.wait(Until.hasObject(By.res("home_list")), 5_000)   // first screen fully drawn
    }
}
```

Record `timeToInitialDisplayMs` and `timeToFullDisplayMs` (median, P90). `timeToFullDisplay`
exists only if the app calls `reportFullyDrawn()`; add it where the first screen has its real
data (`ReportDrawnWhen { state is Content }` in Compose).

Also capture one system trace of the cold start (`Macrobenchmark` saves `.perfetto-trace` files;
or Android Studio Profiler → System Trace) and keep it next to the numbers.

## Step 2: Baseline and Startup Profiles

```kotlin
// baselineprofile module (com.android.test + androidx.baselineprofile)
@get:Rule val rule = BaselineProfileRule()
@Test fun generate() = rule.collect(packageName = "com.example.app", includeInStartupProfile = true) {
    pressHome(); startActivityAndWait()
    device.wait(Until.hasObject(By.res("home_list")), 5_000)
    device.findObject(By.res("home_list")).fling(Direction.DOWN)   // critical journeys only
}
```

- App module: `androidx.baselineprofile` plugin + `implementation(libs.androidx.profileinstaller)`;
  regenerate with `./gradlew :app:generateBaselineProfile` when startup code changes, and commit
  `src/release/generated/baselineProfiles/*.txt`. CI checks the file is not older than N releases.
- Prove it works: the `Partial(Require)` benchmark must be faster than `None`; if not, the profile
  is not installed (check `ProfileVerifier.getCompilationStatusAsync()` in a debug screen) or the
  journey does not cover the start path.
- Libraries ship their own profiles; a Compose app without an app profile still benefits, so the
  app profile only needs **your** classes' journeys.

## Step 3: cut startup work

Read the trace from `bindApplication` to the first `Choreographer#doFrame`. Typical offenders and
the fix:

| Found in trace | Do |
|---|---|
| SDK init in `Application.onCreate` (analytics, ads, crash reporting with sync upload) | `androidx.startup` `Initializer` with dependencies, or lazy `by lazy`/`Koin` `createdAtStart = false`; defer non-critical SDKs to after first frame on `Dispatchers.Default` |
| Koin start taking >50 ms | no `createdAtStart`, no eager `get()` in module DSL, no reflection-heavy `single { }` bodies; wrap `startKoin` in `trace("startKoin")` to see it in the trace |
| `SharedPreferences`/DataStore read on main before first frame | read on IO and show a skeleton; a value needed before first frame (theme, locale) lives in a tiny synchronous store read once |
| Room `openHelper` on main | first query off main; `WAL` default; no migrations on the start path (`local-persistence`) |
| Content providers from libraries (`<provider android:initOrder>`) | remove via `tools:node="remove"` and initialise explicitly |
| Big `MainActivity.onCreate` setContent tree | first screen composes a skeleton; heavy work behind `LaunchedEffect`; avoid `BoxWithConstraints` at the root |
| Font loading / `Typeface.createFromAsset` on main | `FontFamily` with `Font(..., loadingStrategy = FontLoadingStrategy.Async)` or preload on IO (`fonts-management`) |
| `Splash` custom activity + second activity | one activity, `SplashScreen` API with `setKeepOnScreenCondition` tied to real readiness (max ~1 s) |

Each removal gets its own benchmark run; keep the ones that move the median by more than the
noise (run the unchanged build twice to learn the noise).

## Step 4: runtime jank and memory

- Scroll benchmark with `FrameTimingMetric` on the main list; `frameDurationCpuMs` P90 < 16 ms
  on a mid-range device, `frameOverrunMs` P99 near 0. In production, `JankStats` with
  `PerformanceMetricsState` tags (screen name, loading) reported to your performance tracer.
- Custom trace sections around suspicious work: `trace("decode-thumbnail") { … }` from
  `androidx.tracing`; they show in Perfetto and in Macrobenchmark `TraceSectionMetric`.
- Memory: Android Studio Profiler heap dump after navigating back out of the heavy screen; the
  screen's ViewModel and bitmaps must be gone. `LeakCanary` in debug (`debug-tooling`).
  Allocation churn in draw/scroll paths: look for `Path()`, `Paint()`, `String.format` per frame
  (`compose-performance-audit`).
- ANRs: `adb bugreport` or Play Console ANR stack; the main thread stack tells you what blocked,
  the other threads tell you what it waited for (locks, binder calls, `runBlocking`). Common
  causes: `runBlocking` on main, synchronous SDK init in a `BroadcastReceiver`, `Room` on main,
  content provider queries on main, `SharedPreferences.commit()`.

## Step 5: guard against regression

- Macrobenchmark runs on a dedicated device in CI (self-hosted or Firebase Test Lab) on a nightly
  schedule, publishing medians; a PR check compares against the last `main` and fails on a >10 %
  startup regression.
- Startup budget in the repo docs: TTID and TTFD targets per device class, measured by that job.
- New SDK policy: adding a dependency that runs at startup needs a before/after benchmark in the PR.

## Report format

```markdown
## Performance: <what changed>
Device: <model, Android version>, build: <variant, commit>
| Metric | Before (median / P90) | After (median / P90) | Change |
| timeToInitialDisplay | | | |
| timeToFullDisplay | | | |
| frameDurationCpu (home scroll) | | | |
Trace: <path or link>. Noise (two runs of the same build): <ms>.
Changes: <one line each>. Not done: <what and why>.
```

## Checklist

- [ ] Numbers come from a non-debuggable, R8-enabled build on a real device, with noise measured.
- [ ] `reportFullyDrawn` reflects real readiness; TTFD is tracked, not only TTID.
- [ ] Baseline Profile generated from the real journeys, committed, and verified faster than `None`.
- [ ] No synchronous SDK, Koin eager singletons, disk IO or Room on main before first frame.
- [ ] Scroll P90 frame time measured on the main list; JankStats reports from production.
- [ ] Regression job exists and the PR carries the before/after table.
