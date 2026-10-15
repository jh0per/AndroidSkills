---
name: circuit-screen
description: Scaffold or modify a screen built with Slack Circuit (Screen, State with eventSink, sealed Event, Presenter + Factory, Ui + Factory) in Compose or Compose Multiplatform, register it in Koin, and test the presenter with circuit-test. Use only in projects that already depend on Circuit (check for com.slack.circuit in the version catalog); for projects without it use compose-mvi-viewmodel.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Circuit
  - Slack Circuit
  - Presenter
  - Ui
  - circuit-test
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

## Files for a new feature `detail`

```kotlin
// ui/detail/DetailScreen.kt
@CommonParcelize            // or @Parcelize in an Android-only app
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

Assemble Circuit once from everything registered:

```kotlin
val circuitModule = module {
    single<Circuit> {
        Circuit.Builder()
            .addPresenterFactories(getAll<Presenter.Factory>())
            .addUiFactories(getAll<Ui.Factory>())
            .build()
    }
}
```

Then add the screen to the Koin graph test (see `kmp-compose-architecture`), which for Circuit also
proves every screen has a presenter and a ui:

```kotlin
val circuit = koin.get<Circuit>()
val navigator = FakeNavigator(HomeScreen)
for (screen in listOf(HomeScreen, DetailScreen("id"), ProfileScreen)) {
    assertNotNull(circuit.presenter(screen, navigator), "no presenter for $screen")
    assertNotNull(circuit.ui(screen), "no ui for $screen")
}
```

R8: keep Parcelable `CREATOR`s and screen classes (`-keep class com.example.app.**Screen { *; }`).
Process-death restore is where a missing rule shows up.

## Rules that bite

- **Paging/"load more" requests:** use a `Channel<Unit>(Channel.CONFLATED)` collected in one
  `LaunchedEffect(Unit)`, not a counter key: a keyed effect restarts and can cancel a load in flight.
  A failed next page keeps the items already shown and does not advance the offset.
- **App host:** `rememberSaveableBackStack(root = HomeScreen)` +
  `rememberCircuitNavigator(backStack = backStack, onRootPop = { … })` +
  `NavigableCircuitContent`. Use the named-argument overload; the trailing-lambda form may not
  install a back handler.
- **Intercepting system back** (e.g. "save changes?"): use the navigation-event back handler that
  Circuit itself uses and route it to the same event the on-screen back control sends.
- Keep navigation keys small: ids and flags, never byte arrays or large lists.

## Multiplatform parcelize shim

Circuit's `Screen` is `Parcelable` on Android. Screens declared in `commonMain` need a marker that
the parcelize compiler plugin treats as `@Parcelize` for the Android compilation only. No
expect/actual is needed:

```kotlin
// commonMain/com/example/app/CommonParcelize.kt
@Target(AnnotationTarget.CLASS)
@Retention(AnnotationRetention.BINARY)
annotation class CommonParcelize
```

```kotlin
// composeApp/build.gradle.kts, inside kotlin { }
targets.configureEach {
    if (platformType == KotlinPlatformType.androidJvm) {
        compilations.configureEach {
            compileTaskProvider.configure {
                compilerOptions {
                    freeCompilerArgs.addAll(
                        "-P",
                        "plugin:org.jetbrains.kotlin.parcelize:additionalAnnotation=com.example.app.CommonParcelize",
                    )
                }
            }
        }
    }
}
```

Apply `kotlin-parcelize` after the Android application plugin, without another Kotlin version.

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

- Hand-written fakes that record calls (`loadCount`, `lastRequest`) beat mocking libraries here.
- A captured state object never changes. To assert "nothing changed", use `expectNoEvents()`;
  re-reading an old state passes against any presenter.
- Every dispatcher the presenter touches must come from `testScheduler` (see `android-testing`).
- JVM presenter tests on Android need `testOptions { unitTests.isReturnDefaultValues = true }`.
- Test-only convenience readers belong in test-private extension properties, not production state.
