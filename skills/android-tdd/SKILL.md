---
name: android-tdd
description: Test-driven development for Android and KMP - the red-green-refactor loop with Gradle commands that run one test fast, a test list written from acceptance scenarios, picking the lowest layer that can observe the behaviour (pure Kotlin, ViewModel with Turbine, repository with fakes and MockEngine, Room/Robolectric, Compose UI with runComposeUiTest or createComposeRule, instrumented only for platform APIs), seams for time, dispatchers and IDs, fakes with shared contract tests instead of mocks, regression-test-first bug fixes and characterisation tests for legacy code. Use when implementing a feature or fix test-first, when asked for TDD or red-green-refactor, when a task says "test first", or when code is hard to test. Do not use for test infrastructure details such as dispatchers rules, screenshot contrast checks or device triage (see android-testing) or for writing the spec (see spec-driven-development).
metadata:
  last-updated: '2026-10-16'
  keywords:
  - TDD
  - test-driven development
  - red green refactor
  - test first
  - fakes
  - regression test
  - characterization tests
  - Compose UI test
  - KMP tests
---

# Test-driven development for Android and KMP

Write the test that fails, make it pass with the least code, then clean up while it stays green.
The loop only works when one test runs in seconds, so most of this skill is about choosing the
layer and the seam. `android-testing` owns the test machinery (dispatcher rules, Turbine helpers,
Robolectric setup, screenshot checks); `spec-driven-development` supplies the acceptance scenarios
that become the test list; `verification-discipline` says why a test you never saw fail proves
nothing.

## Prerequisites

- Find the fast commands before the first test and write them down for the session:

  | Module type | One test class | Whole module |
  |---|---|---|
  | Android app/library | `./gradlew :feature:orders:testDebugUnitTest --tests "*OrdersViewModelTest"` | `:feature:orders:testDebugUnitTest` |
  | KMP (JVM or Android host target) | `./gradlew :feature:orders:jvmTest --tests "*OrdersViewModelTest"` (or `testAndroidHostTest`/`testDebugUnitTest`, per `./gradlew :feature:orders:tasks --group verification`) | `:feature:orders:allTests` |
  | KMP iOS | `./gradlew :feature:orders:iosSimulatorArm64Test` (macOS only) | same |
  | Instrumented | `./gradlew :app:connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=com.example.app.OrdersScreenTest` | `connectedDebugAndroidTest` |

  `--tests` takes a class or method pattern: `--tests "*OrdersViewModelTest.offline*"`.
- `kotlin.test`, `kotlinx-coroutines-test` and Turbine in the test source set; shared fakes in a
  `:core:testing` module (`commonMain` there, so every module's tests can use them).
- Keep the Gradle daemon warm and configuration cache on; a 40 s loop kills TDD faster than any
  bad habit.

## The loop

1. **Test list.** Before code, write the behaviours as test names, one per acceptance scenario,
   edge case and error path (`spec-driven-development` step 2). Start with the simplest one that
   forces real code, not with the hardest.
2. **Red.** Write one test. Run it. It must fail **for the reason you expect**: an assertion
   message that names the missing behaviour. A compile error is red, but make it compile (empty
   function, `TODO()` replaced by a wrong value) and see the assertion fail before going green.
3. **Green.** The least code that passes: a hard-coded value is fine if the next test on the list
   will force the general version. Run the one test, then the class.
4. **Refactor.** With everything green, remove duplication, rename, extract. Run the module's tests
   after each step. No new behaviour in this step; a refactor that needs a test change is not one.
5. **Repeat** from the list. Add new cases to the list as you discover them; do not chase them now.
6. **Gate.** When the list is done, run the module's whole suite and the project gate
   (`./gradlew verify`, see `gradle-quality-gate`).

Commit at green. Small commits make "which change broke it" a one-step question.

## Pick the lowest layer that can see the behaviour

| Behaviour | Layer | Source set |
|---|---|---|
| Rules, mapping, validation, formatting, reducers | plain Kotlin test | `commonTest` / `test` |
| Screen behaviour: intents → state/effects, loading, errors, offline | ViewModel/state-holder + fakes + Turbine | `commonTest` / `test` |
| Network contract, error mapping, retry/refresh | repository/client + Ktor `MockEngine` | `commonTest` |
| SQL, migrations, DataStore keys | Room in-memory / Robolectric | `androidUnitTest` / `test` |
| What is shown, enabled, announced; clicks call the right intent | stateless `XUi(state, onIntent)` UI test | `commonTest` (KMP) or `androidUnitTest` with Robolectric, else `androidTest` |
| Permissions, camera, notifications, real IME, multi-window | instrumented on a device | `androidInstrumentedTest` / `androidTest` |

Most scenarios end in the second row. If a scenario seems to need a device, find the decision
inside it ("show rationale when denied once") and test that decision in a ViewModel; leave only the
platform call for the device.

## Seams that make the first test possible

Anything the test cannot control must come in through the constructor:

```kotlin
class OrdersViewModel(
    private val repository: OrdersRepository,          // interface; fake in tests
    private val clock: Clock,                          // not Clock.System inside the class
    private val ids: () -> String = { Uuid.random().toString() },
    private val dispatchers: AppDispatchers,           // not Dispatchers.IO inside the class
) : ViewModel()
```

- Time, randomness, IDs, dispatchers, connectivity, feature flags, locale: injected.
- Static SDKs (analytics, crash reporting) behind an interface (`android-testing`).
- Android classes stay out of ViewModels: `Context` → a small interface (`StringProvider`,
  `PermissionChecker`) with an Android implementation.

When the first test needs ten collaborators, the class has too many jobs; split before testing.

## Fakes, not mocks, with a contract

```kotlin
class FakeOrdersRepository : OrdersRepository {
    val stored = MutableStateFlow<List<Order>>(emptyList())
    var failNextRefresh: Throwable? = null
    var refreshCount = 0; private set
    override fun observe(): Flow<List<Order>> = stored
    override suspend fun refresh() {
        refreshCount++
        failNextRefresh?.let { failNextRefresh = null; throw it }
    }
}
```

A fake that drifts from the real implementation makes every test lie. Run one abstract contract
suite against both; see `references/tdd-examples.md` for the pattern. Mocking frameworks are for
the rare third-party type you cannot wrap.

## Bugs: regression test first

1. Reproduce the report as a failing test at the lowest layer that shows it.
2. Run it on the current code: it must fail with the reported symptom (wrong value, crash), not
   with a setup error.
3. Fix. Test passes. Run the class and module.
4. Name the test after the symptom (``fun `refresh after logout does not show old orders`()``).

If you cannot make it fail, you have not found the bug; do not ship a fix for a guess.

## Legacy code

Code without tests is changed in this order: characterisation tests that pin today's behaviour
(assert what it does, even if wrong, and mark wrong ones `// current behaviour, see FR-004`), then
introduce a seam with the smallest safe edit (extract interface, pass a parameter with a default),
then TDD the change. Do not refactor and change behaviour in the same step.

## RIGHT / WRONG

```kotlin
// WRONG: written after the code, asserts what the code happens to do, never seen red
@Test fun test1() = runTest { val vm = OrdersViewModel(repo); assertNotNull(vm.state.value) }

// RIGHT: named after the scenario, asserts the observable outcome, seen failing first
@Test fun `offline - shows cached orders with offline notice`() = runTest {
    repository.stored.value = listOf(order("1"))
    repository.failNextRefresh = IOException("offline")
    vm.state.test {
        val s = awaitUntil { !it.isLoading }
        assertEquals(listOf("1"), s.items.map { it.id })
        assertTrue(s.isOffline)
        cancelAndIgnoreRemainingEvents()
    }
}
```
Why: `assertNotNull` passes on any implementation; the scenario test fails until FR-003 exists.

```kotlin
// WRONG: instrumented test for a decision
@Test fun showsRationale() { /* launch activity, deny permission via UiAutomator, find text */ }

// RIGHT: the decision in the ViewModel; the device test only checks the platform hand-off
@Test fun `denied once - shows rationale`() = runTest {
    vm.onIntent(CameraIntent.PermissionResult(granted = false, shouldShowRationale = true))
    assertEquals(PermissionUi.Rationale, vm.state.value.permission)
}
```
Why: the JVM test runs in a second and on every CI run; the device test is slow and flaky.

```kotlin
// WRONG: verifying calls on a mock instead of outcomes
verify(repo, times(1)).refresh()

// RIGHT: assert what the user sees; check call counts only when the count is the requirement
assertEquals(1, repository.refreshCount)   // FR-006: pull to refresh triggers exactly one request
```
Why: interaction tests break on every refactor and pass when the result is wrong.

## Scope guards

- TDD the logic, not the layout. Pixel layout, colours and animation are checked by previews,
  screenshot tests and device checks (`android-testing`), not by asserting modifiers.
- Spikes to learn an API are throwaway; delete them and TDD the real code.
- Generated code (Room DAOs, serializers) is tested through behaviour (round-trip, migration), not
  line by line.
- Do not delete, skip or `@Ignore` a red test to reach green; fix the code or the test's wrong
  expectation and say which.

## Report format

```
Test list: 7 (5 done, 2 deferred: see spec Clarifications)
Red seen:  7/7 (assertion failures, not compile errors)
Layer:     5 commonTest, 1 androidUnitTest (Room migration), 1 instrumented (camera hand-off)
Commands:  ./gradlew :feature:orders:allTests PASS · ./gradlew verify PASS · iosSimulatorArm64Test NOT_RUN (no macOS)
Seams added: Clock, AppDispatchers in OrdersViewModel
```

## Checklist

- [ ] Test list written from scenarios and edge cases before production code.
- [ ] Every new test was seen failing with the expected assertion before it passed.
- [ ] Each test at the lowest layer that can observe the behaviour; device tests only for platform APIs.
- [ ] Time, IDs, dispatchers and platform services injected; no `Clock.System`/`Dispatchers.IO` inside.
- [ ] Fakes shared from a testing module and covered by a contract suite that also runs on the real implementation.
- [ ] Bug fixes have a regression test that failed on the old code.
- [ ] Refactor steps changed no behaviour; module suite and `./gradlew verify` green at the end.
