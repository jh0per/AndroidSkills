---
name: android-testing
description: Testing Android and KMP apps - coroutine test dispatchers and virtual time, Turbine tests for ViewModels and other state holders, Ktor MockEngine, hand-written fakes, Compose instrumented tests with real platform seams, screenshot capture with contrast assertions, touch-target and multi-touch tests, locale-aware runners, and triaging a whole suite failing on one device. Use when writing or fixing tests, chasing a flaky test, or adding UI verification.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - testing
  - coroutines test
  - Turbine
  - Robolectric
  - Compose UI test
  - screenshot test
  - fakes
  - flaky tests
---

# Android testing

This skill is the test machinery. The test-first loop that uses it is `android-tdd`.

## Pyramid

| Layer | Where | What |
|---|---|---|
| Pure domain, geometry, mappers, merge functions | `commonTest` / `test` | plain JUnit/kotlin.test |
| Repositories, ViewModels, other state holders | `commonTest` / `test` | fakes + Turbine + MockEngine, virtual time |
| DI graph | `commonTest` | resolve every definition and screen (see `kmp-compose-architecture`) |
| On-disk contracts | `androidUnitTest` | pinned DataStore names/keys, Room migrations |
| Rendering, touch, platform APIs | `androidInstrumentedTest` | Compose rule, real seams, device |
| Same common tests on iOS | `iosSimulatorArm64Test` | report as local evidence if CI lacks macOS |

## Virtual time: every dispatcher from `testScheduler`

One real dispatcher anywhere in the graph puts a wall clock back into `runTest`, and the test
fails on somebody else's busy machine.

```kotlin
@Test fun x() = runTest {
    val appScope = CoroutineScope(UnconfinedTestDispatcher(testScheduler))   // not Dispatchers.Unconfined
    val engine = testMockEngine { respond("""{"id":"1"}""", headers = jsonHeaders) }
    // ...
}

fun TestScope.testMockEngine(handler: MockRequestHandler): MockEngine =
    MockEngine(MockEngineConfig().apply {
        dispatcher = UnconfinedTestDispatcher(testScheduler)   // MockEngine's default is a real I/O dispatcher
        addHandler(handler)
    })
```

- Inject dispatchers (`ioDispatcher: CoroutineDispatcher = Dispatchers.IO`) so tests can replace them;
  enable detekt `InjectDispatcher`.
- ViewModel tests replace `Dispatchers.Main` (`viewModelScope` uses it):

  ```kotlin
  class MainDispatcherRule(val dispatcher: TestDispatcher = UnconfinedTestDispatcher()) : TestWatcher() {
      override fun starting(description: Description) = Dispatchers.setMain(dispatcher)
      override fun finished(description: Description) = Dispatchers.resetMain()
  }
  ```
- After fixing the pattern in one file, grep for it everywhere; a lesson applied to one call site is
  not a fix.

## Flake triage: hang or deadline?

A test failing with Turbine's `No value produced in 3s` can be a slow machine or a hang. Raise the
timeout to 30s once: if it still fails, it is a hang (a real dispatcher or a missing emission), so
revert the timeout and find it. If a scheduling change makes an unrelated test fail, suspect that it
made a real race visible; write a test that **forces** that order (hold a request, act, release it).

## ViewModel and state-holder tests

```kotlin
@get:Rule val mainRule = MainDispatcherRule()

@Test fun `load more appends`() = runTest {
    val repository = FakeOrdersRepository(pages = listOf(page("a", "b"), page("c")))
    val vm = OrdersViewModel(repository)
    vm.state.test {                          // Turbine
        awaitUntil { it.items.size == 2 }
        vm.onIntent(OrdersIntent.LoadMore)
        awaitUntil { it.items.size == 3 }
        cancelAndIgnoreRemainingEvents()
    }
}

suspend fun <T> ReceiveTurbine<T>.awaitUntil(p: (T) -> Boolean): T { var s = awaitItem(); while (!p(s)) s = awaitItem(); return s }
```

Circuit projects test presenters the same way with `presenter.test { }` from circuit-test (see
`circuit-screen`).

- A captured state snapshot never changes; asserting on it again proves nothing. To assert that
  nothing changed, use `expectNoEvents()`.
- Assert **which** failure surfaced, not only that something failed; otherwise the test passes on an
  unrelated exception thrown earlier.
- Prefer hand-written fakes that record calls (`loadCount`, `lastRequest`) over mocking frameworks.
- If a path cannot be unit-tested because one step needs a device (e.g. rasterising a thumbnail),
  make that step fail on its own (`try` around it) so the rest of the operation is reachable, which
  is usually also the better product behaviour.

## JVM tests touching Android classes

`testOptions { unitTests.isReturnDefaultValues = true }` so Compose/runtime logging does not throw
"not mocked" and mask the real failure. Robolectric is an option for Android-only modules; keep
KMP state-holder tests on plain JVM.

## Compose instrumented tests

```kotlin
@get:Rule val compose = createComposeRule()

fun ComposeContentTestRule.setAppContent(content: @Composable () -> Unit) = setContent {
    val context = LocalContext.current
    CompositionLocalProvider(
        LocalPlatformImageSupport provides AndroidPlatformImageSupport(),
        LocalPlatformFontSupport provides remember(context) { AndroidPlatformFontSupport(context) },
    ) { AppTheme { content() } }
}
```

- A Compose rule takes `setContent` **once**. Vary state through `mutableStateOf` inside that one
  composition to capture several variants.
- Render the stateless `XUi(state)` with a hand-built state; no network.
- Tests that install process-global hooks reset them in `@After`.
- Debug-only `ui-test-manifest` supplies the empty activity: `debugImplementation(libs.androidx.compose.ui.test.manifest)`.
- Pin `espresso-core`/`androidx.test` forward if an old transitive version calls APIs removed in
  new Android releases.

### Screenshots that assert something

A screenshot test that only saves images stays green while text is unreadable. Capture **and**
measure:

```kotlin
private fun save(name: String, expectReadableText: String? = null) {
    val bitmap = compose.onRoot().captureToImage().asAndroidBitmap()
    File(outputDir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    expectReadableText?.let { assertReadableNode(compose.onNodeWithText(it), label = name) }
}
```

`ContrastAssertions.kt` in this folder computes WCAG contrast: the most common colour in the band
is the background, the colour furthest in luminance is the ink, and the ratio must be ≥ 3:1. Skip
bands that are photographs. Resolve expected text from resources so the test runs in any locale.

Pull images with:

```bash
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest
adb install -r -t app/build/outputs/apk/debug/app-debug.apk
adb install -r -t app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk   # install BOTH
adb shell am instrument -w -e class com.example.app.ui.HomeScreenshotTest com.example.app.test/androidx.test.runner.AndroidJUnitRunner
adb pull /sdcard/Android/data/com.example.app/files/screenshots ./screenshots
```

Then look at them. For rendering regressions assert pixels or measured unclipped coordinates;
clipped `boundsInRoot` cannot prove overflow.

### Touch targets

```kotlin
val node = compose.onNodeWithText(label).fetchSemanticsNode()
val h = with(compose.density) { node.size.height.toDp() }
assertTrue("\"$label\" is ${h.value.toInt()}dp tall, below 48dp", h >= 48.dp)
```

### Multi-touch

`adb shell input` has no multi-touch. Use `performTouchInput` with pointer ids, including fingers
arriving on different frames:

```kotlin
onNodeWithTag("element").performTouchInput {
    val c = center
    down(0, c); repeat(3) { moveTo(0, Offset(c.x - 15f * (it + 1), c.y)) }   // first finger starts a drag
    down(1, Offset(c.x + 40f, c.y))                                         // second finger joins late
    repeat(10) { val s = 40f + 22f * (it + 1); moveTo(0, Offset(c.x - s, c.y)); moveTo(1, Offset(c.x + s, c.y)) }
    up(0); up(1)
}
// assert: zoom changed, element position unchanged
```

### Locale-aware runner

```kotlin
class LocaleAwareRunner : AndroidJUnitRunner() {
    override fun onStart() {
        val tag = InstrumentationRegistry.getArguments().getString("uiLocale")
        if (!tag.isNullOrBlank() && Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            targetContext.getSystemService(LocaleManager::class.java).applicationLocales = LocaleList.forLanguageTags(tag)
        }
        super.onStart()
    }
}
// defaultConfig { testInstrumentationRunner = "com.example.app.LocaleAwareRunner" }
// ./gradlew connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.uiLocale=de-DE
```

A suite that only passes in one language is a common hidden failure; run at least one other locale
in CI. Mark hardware-dependent tests with an annotation and exclude via `notAnnotation`.

## When a whole suite fails on one device

Forty failures with `No compose hierarchies found` plus a hanging `adb devices`, a refused
uninstall and package-not-found in logcat are **one** symptom: a wedged device. Run one test on a
second device or emulator before reading code. Reboot fixes it; waking, unlocking and disabling
animations usually do not.

For tests that keep the screen on, use a window flag in the test activity; do not change device
security settings. Use a disposable emulator with `-read-only` for throwaway sessions.

## Robolectric and Room DAO tests

```kotlin
class EmptyApplication : Application()      // shared from a test-tools module; skips the real app's SDK init

@RunWith(AndroidJUnit4::class)
@Config(application = EmptyApplication::class, manifest = Config.NONE)
class OrdersDaoTest {
    private lateinit var db: AppDatabase
    @Before fun setUp() {
        db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext(), AppDatabase::class.java)
            .allowMainThreadQueries().build()
    }
    @After fun tearDown() = db.close()
    @Test fun `upsert then observe`() = runTest {
        db.orders().upsert(order("1"))
        db.orders().observeAll().test { assertEquals(listOf("1"), awaitItem().map { it.id }); cancelAndIgnoreRemainingEvents() }
    }
}
```

- `testOptions { unitTests.isIncludeAndroidResources = true }` for Robolectric resources.
- Migration tests: `MigrationTestHelper` against the exported schemas, one test per migration.
- A dispatcher rule that also exposes a `DispatcherProvider` returning the test dispatcher, injected
  into the class under test; never call `Dispatchers.setMain` in both the rule and `@Before`.
- Organise slow suites (Robolectric, serialization corpora) so they can be run separately, but keep
  them in the gate.
- Use `runTest` everywhere; not `runBlocking` with Turbine.
- Wrap static SDK singletons (crash reporting, analytics) in injected interfaces so unit tests never
  initialise them, instead of try/catch guards inside the wrapper.
- Instrumented suites: `execution = "ANDROIDX_TEST_ORCHESTRATOR"` + `clearPackageData` isolates tests
  that share process state.

## Emulator housekeeping

- Disposable sessions: `emulator -avd <name> -read-only` (no snapshot writes, parallel instances).
- Reclaim AVD disk: with the emulator stopped, delete the Quick Boot snapshot and compact the qcow2
  user data (`qemu-img convert -O qcow2`); apps and accounts survive. Never delete arbitrary AVD
  directories.
