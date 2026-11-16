---
name: circuit-screen
description: Scaffold or modify a screen built with Slack Circuit (Screen, State with eventSink, sealed Event, Presenter + Factory, Ui + Factory) in Compose or Compose Multiplatform, register it in Koin, save the navigation stack with serialized screen keys so it survives process death, and test the presenter with circuit-test, including state across recreation. Use only in projects that already depend on Circuit (check for com.slack.circuit in the version catalog), when adding a screen, wiring the navigation host or debugging lost state after rotation or process death; for projects without it use compose-mvi-viewmodel.
metadata:
  last-updated: '2026-11-16'
  keywords:
  - Circuit
  - Slack Circuit
  - Presenter
  - Ui
  - circuit-test
  - CircuitSaver
  - rememberRetained
  - process death
  - state restoration
  - Compose Multiplatform
---

# Circuit screen

Applies only when the project already uses Circuit. Do not introduce Circuit into a project that
uses ViewModels/Navigation Compose; follow `compose-mvi-viewmodel` there.

```text
Screen (navigation key) → Presenter.present() → immutable State(eventSink)
                                               ↓                ↑
                                              Ui ─── Event ─────┘
```

One sealed event type per screen. The presenter owns orchestration and navigation through
`Navigator`; the Ui never navigates. A screen with an existing state owner (e.g. a canvas store
retained by its presenter) may let its Ui call that store directly: do not copy a large model
into Circuit state just to imitate other screens.

## Prerequisites

- Look at the Android declaration of `com.slack.circuit.runtime.screen.Screen` first. In current
  Circuit it is not `Parcelable`, and the stack is saved through a `CircuitSaver`: this page.
  In older releases it extends `Parcelable`; a project that stays there, or that keeps
  Parcelable screens after an upgrade, follows `references/parcelable-screens.md`.
- Serialized screens need `com.slack.circuit:circuit-serialization`,
  `org.jetbrains.kotlinx:kotlinx-serialization-core` and the Kotlin serialization compiler plugin
  (`org.jetbrains.kotlin.plugin.serialization`), all through the version catalog.

## Files for a new feature `detail`

```kotlin
// ui/detail/DetailScreen.kt
@Serializable               // the key is saved with the stack; see "Saving the stack"
data class DetailScreen(val itemId: String) : Screen

@Immutable
data class DetailState(
    val title: String,
    val content: AppListState<DetailContent>,
    val refreshing: Boolean,
    val eventSink: (DetailEvent) -> Unit,
) : CircuitUiState

sealed interface DetailEvent {
    data object BackClicked : DetailEvent
    data object RetryClicked : DetailEvent
    data object RefreshRequested : DetailEvent
    data class RelatedClicked(val id: String) : DetailEvent
}
```

```kotlin
class DetailPresenter(
    private val screen: DetailScreen,
    private val navigator: Navigator,
    private val repository: DetailRepository,
) : Presenter<DetailState> {

    @Composable
    override fun present(): DetailState {
        var content by rememberRetained { mutableStateOf<AppListState<DetailContent>>(AppListState.Loading) }
        var attempt by rememberRetained { mutableIntStateOf(0) }
        var refreshTrigger by rememberRetained { mutableIntStateOf(0) }
        var refreshing by rememberRetained { mutableStateOf(false) }

        LaunchedEffect(attempt) { content = repository.load(screen.itemId).toListState() }
        LaunchedEffect(refreshTrigger) {
            if (refreshTrigger == 0) return@LaunchedEffect
            refreshing = true
            content = repository.load(screen.itemId).toListState()
            refreshing = false
        }

        return DetailState(title = "…", content = content, refreshing = refreshing) { event ->
            handleEvent(event, onRetry = { attempt++ }, onRefresh = { refreshTrigger++ })
        }
    }

    // Pulled out of present() to keep cyclomatic complexity under the detekt limit.
    private fun handleEvent(event: DetailEvent, onRetry: () -> Unit, onRefresh: () -> Unit) {
        when (event) {
            DetailEvent.BackClicked -> navigator.pop()
            DetailEvent.RetryClicked -> onRetry()
            DetailEvent.RefreshRequested -> onRefresh()
            is DetailEvent.RelatedClicked -> navigator.goTo(DetailScreen(event.id))
        }
    }

    class Factory(private val repository: DetailRepository) : Presenter.Factory {
        override fun create(screen: Screen, navigator: Navigator, context: CircuitContext): Presenter<*>? =
            if (screen is DetailScreen) DetailPresenter(screen, navigator, repository) else null
    }
}

class DetailUiFactory : Ui.Factory {
    override fun create(screen: Screen, context: CircuitContext): Ui<*>? =
        if (screen is DetailScreen) ui<DetailState> { state, modifier -> DetailUi(state, modifier) } else null
}
```

Register in Koin with `bind`, never `single<Presenter.Factory>`:

```kotlin
val detailModule = module {
    single { DetailPresenter.Factory(repository = get()) } bind Presenter.Factory::class
    single { DetailUiFactory() } bind Ui.Factory::class
}
```

Assemble Circuit once from everything registered, and give it the saver with the list of screens:

```kotlin
// Every screen that can be on the stack. `subclass` is kotlinx.serialization.modules.subclass.
internal val savedScreens: List<CircuitSerializerRegistration> = listOf(
    CircuitSerializerRegistration { it.subclass(HomeScreen::class) },
    CircuitSerializerRegistration { it.subclass(DetailScreen::class) },
)

val circuitModule = module {
    single<Circuit> {
        Circuit.Builder()
            .addPresenterFactories(getAll<Presenter.Factory>())
            .addUiFactories(getAll<Ui.Factory>())
            .setCircuitSaver(SerializableCircuitSaver(savedScreens))
            .build()
    }
}
```

Then add the screen to the Koin graph test (see `kmp-compose-architecture`), which for Circuit also
proves every screen has a presenter and a ui and is in `savedScreens`:

```kotlin
val circuit = koin.get<Circuit>()
val navigator = FakeNavigator(HomeScreen)
val saver = assertNotNull(circuit.circuitSaver)
for (screen in listOf(HomeScreen, DetailScreen("id"), ProfileScreen)) {
    assertNotNull(circuit.presenter(screen, navigator), "no presenter for $screen")
    assertNotNull(circuit.ui(screen), "no ui for $screen")
    saver.save(screen)                                   // throws for a screen that is not listed
}
// Control: a @Serializable screen that is not listed must fail.
assertFailsWith<IllegalArgumentException> { saver.save(UnlistedScreen) }
```

## Saving the stack

```kotlin
CircuitCompositionLocals(circuit) {                      // provides the saver set on Circuit
    val navStack = rememberSaveableNavStack(root = HomeScreen)
    val navigator = rememberCircuitNavigator(
        navStack = navStack,
        onRootPop = { /* a presenter popped the root */ },
        enableBackHandler = true,                        // see below
    )
    NavigableCircuitContent(navigator = navigator, navStack = navStack)
}
```

| Event | Stack and screen keys | `rememberRetained` state |
|---|---|---|
| Configuration change (the Activity is recreated) | kept | kept |
| Android process death, app reopened | restored | lost |
| iOS process ends, app reopened | lost: the app starts from the root | lost |

- **`enableBackHandler = true` is not optional.** `rememberCircuitNavigator` has an overload
  without that parameter, and a call that omits the argument resolves to it: no back handler is
  installed, and the system back leaves the app from any screen. At the root the handler is off
  by design, so the system handles back there.
- **A screen missing from `savedScreens` crashes the app when state is saved**, which on Android
  is when the app leaves the foreground: `IllegalArgumentException: Unable to save class …`. It
  does not fail when the screen is opened. The graph test above is the guard.
- **A saved stack that names a screen the app no longer lists is dropped whole** (when that
  screen is the current one or below it): the app starts from the root, nothing is thrown. An
  update that removes a screen meets this.
- **State that must survive process death goes through the data layer** (see
  `kmp-compose-architecture`), on iOS including "where the user was". `rememberRetained` covers
  recreation only; its overload with an explicit `key` is deprecated in favour of `retain`.
- Circuit's reflective saver (`circuit-serialization-reflect`) needs no list but is JVM-only: not
  for a project with an iOS target.
- Run the process-death check on the minified build once (see `android-release-signing`): it is
  where a missing keep rule shows up.

How to test a saved stack, how to run the process-death check by hand, and why a JVM test on
Android cannot read a saved stack back: `references/state-restoration.md`.

## Rules that bite

- **Paging/"load more" requests:** use a `Channel<Unit>(Channel.CONFLATED)` collected in one
  `LaunchedEffect(Unit)`, not a counter key: a keyed effect restarts and can cancel a load in flight.
  A failed next page keeps the items already shown and does not advance the offset.
- **Intercepting system back** (e.g. "save changes?"): use the navigation-event back handler that
  Circuit itself uses and route it to the same event the on-screen back control sends.
- Keep navigation keys small: ids and flags, never byte arrays or large lists.

## Presenter tests (circuit-test)

```kotlin
private fun presenter(
    screen: DetailScreen = DetailScreen("a"),
    navigator: FakeNavigator = FakeNavigator(screen),
    repository: FakeDetailRepository = FakeDetailRepository(),
) = DetailPresenter(screen, navigator, repository)

private suspend fun ReceiveTurbine<DetailState>.awaitUntil(p: (DetailState) -> Boolean): DetailState {
    var s = awaitItem(); while (!p(s)) s = awaitItem(); return s
}

@Test fun `retry reloads after a failure`() = runTest {
    val repository = FakeDetailRepository(result = ApiResult.Failure(ApiError.Network("offline")))
    presenter(repository = repository).test {
        val failed = awaitUntil { it.content is AppListState.Error }
        repository.result = ApiResult.Success(sampleDetail())
        failed.eventSink(DetailEvent.RetryClicked)
        awaitUntil { it.content is AppListState.Content }
        assertEquals(2, repository.loadCount)
        cancelAndIgnoreRemainingEvents()
    }
}

@Test fun `back pops`() = runTest {
    val navigator = FakeNavigator(DetailScreen("a"))
    presenter(navigator = navigator).test {
        awaitItem().eventSink(DetailEvent.BackClicked)
        navigator.awaitPop()
        cancelAndIgnoreRemainingEvents()
    }
}
```

State across recreation: present twice with one retained registry. The control is the same test
with a fresh registry in the second block.

```kotlin
@Test fun `retained state comes back when the interface is rebuilt`() = runTest {
    val registry = RetainedStateRegistry()
    presenter().test(LocalRetainedStateRegistry provides registry) {
        awaitUntil { it.content is AppListState.Content }
        registry.saveAll()                               // what the platform does before a rebuild
        cancelAndIgnoreRemainingEvents()
    }
    presenter().test(LocalRetainedStateRegistry provides registry) {
        assertTrue(awaitItem().content is AppListState.Content)   // no Loading first
        cancelAndIgnoreRemainingEvents()
    }
}
// Control: give the second block `RetainedStateRegistry()` and its first item is Loading again.
```

- Hand-written fakes that record calls (`loadCount`, `lastRequest`) beat mocking libraries here.
- A captured state object never changes. To assert "nothing changed", use `expectNoEvents()`;
  re-reading an old state passes against any presenter.
- Every dispatcher the presenter touches must come from `testScheduler` (see `android-testing`).
- JVM presenter tests on Android need `testOptions { unitTests.isReturnDefaultValues = true }`.
- Test-only convenience readers belong in test-private extension properties, not production state.

## Checklist

- [ ] The screen is `@Serializable`, has its line in `savedScreens`, and is in the graph test.
- [ ] Presenter and Ui factories are registered with `bind`; the graph test resolves both.
- [ ] The host passes `enableBackHandler = true`; system back was pressed on a second-level screen.
- [ ] State that must outlive the process is in the data layer, not in `rememberRetained`.
- [ ] Presenter tests cover events, navigation and, for retained state, recreation with its control.
- [ ] After a change to saving: process death was checked on a device, started with the launcher intent.
