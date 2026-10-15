---
name: compose-mvi-viewmodel
description: Build a Compose or Compose Multiplatform feature with MVI on an AndroidX ViewModel (immutable State, sealed Intent, optional one-shot Effect, reduce helper), Koin injection, Navigation Compose, a Route/Screen split and unit tests. The default screen pattern for any project that does not already use Circuit; use when adding a screen, form, list or dashboard.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - MVI
  - ViewModel
  - Navigation Compose
  - Koin
  - unidirectional data flow
  - State
  - Intent
  - Effect
---

# Compose MVI feature on ViewModel

The default screen pattern. It needs no presentation framework beyond AndroidX lifecycle, which is
multiplatform (`org.jetbrains.androidx.lifecycle:lifecycle-viewmodel-compose` in KMP,
`androidx.lifecycle:lifecycle-viewmodel-compose` on Android). If the project already uses Circuit,
follow `circuit-screen` instead; do not mix the two in one app.

## Contract

```kotlin
// presentation/orders/OrdersContract.kt
@Immutable
data class OrdersState(
    val tab: OrdersTab = OrdersTab.OVERVIEW,
    val items: ImmutableList<OrderRow> = persistentListOf(),   // kotlinx-collections-immutable for stability
    val loading: Boolean = false,
    val error: String? = null,
    val draftQuery: String = "",                               // form state lives here, not in the composable
)

sealed interface OrdersIntent {
    data class SelectTab(val tab: OrdersTab) : OrdersIntent
    data object Refresh : OrdersIntent
    data class UpdateQuery(val value: String) : OrdersIntent
    data object SubmitSearch : OrdersIntent
}

sealed interface OrdersEffect {                // one-shot: navigation, snackbar
    data class OpenOrder(val id: String) : OrdersEffect
}
```

## ViewModel

```kotlin
class OrdersViewModel(
    private val loadOrders: LoadOrdersUseCase,
    private val search: SearchOrdersUseCase,
) : ViewModel() {
    private val _state = MutableStateFlow(OrdersState())
    val state: StateFlow<OrdersState> = _state.asStateFlow()

    private val _effects = Channel<OrdersEffect>(Channel.BUFFERED)
    val effects: Flow<OrdersEffect> = _effects.receiveAsFlow()

    init { onIntent(OrdersIntent.Refresh) }

    fun onIntent(intent: OrdersIntent) {
        when (intent) {
            is OrdersIntent.SelectTab -> reduce { it.copy(tab = intent.tab) }
            OrdersIntent.Refresh -> refresh()
            is OrdersIntent.UpdateQuery -> reduce { it.copy(draftQuery = intent.value) }
            OrdersIntent.SubmitSearch -> submitSearch()
        }
    }

    private fun refresh() = viewModelScope.launch {
        reduce { it.copy(loading = true, error = null) }
        loadOrders()
            .onSuccess { rows -> reduce { it.copy(loading = false, items = rows.toImmutableList()) } }
            .onFailure { e -> reduce { it.copy(loading = false, error = e.message) } }
    }

    private inline fun reduce(f: (OrdersState) -> OrdersState) = _state.update(f)
}
```

Use cases are small operator-invoke classes over repository interfaces:

```kotlin
class LoadOrdersUseCase(private val repository: OrdersRepository) {
    suspend operator fun invoke(): Result<List<OrderRow>> = repository.orders()
}
```

## Route / Screen split

```kotlin
@Composable
fun OrdersRoute(onOpenOrder: (String) -> Unit, viewModel: OrdersViewModel = koinViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(viewModel) {
        viewModel.effects.collect { effect ->
            when (effect) { is OrdersEffect.OpenOrder -> onOpenOrder(effect.id) }
        }
    }
    OrdersScreen(state = state, onIntent = viewModel::onIntent)
}

@Composable
fun OrdersScreen(state: OrdersState, onIntent: (OrdersIntent) -> Unit, modifier: Modifier = Modifier) {
    // stateless: previews and screenshot tests render this directly
}
```

## Navigation (Navigation Compose, type-safe routes)

```kotlin
@Serializable data object OrdersRoute
@Serializable data class OrderDetailRoute(val id: String)      // ids only, never large payloads

NavHost(navController, startDestination = OrdersRoute) {
    composable<OrdersRoute> { OrdersRoute(onOpenOrder = { navController.navigate(OrderDetailRoute(it)) }) }
    composable<OrderDetailRoute> { entry -> OrderDetailRoute(id = entry.toRoute<OrderDetailRoute>().id, onBack = navController::navigateUp) }
}
```

The ViewModel reads its arguments from `SavedStateHandle.toRoute<OrderDetailRoute>()`. Navigation is
decided by the ViewModel (an Effect) or passed in as callbacks; the stateless Screen never holds the
`NavController`.

## Koin

```kotlin
val networkModule = module { single { buildApi(get()) } }
val dataModule = module { single<OrdersRepository> { OrdersRepositoryImpl(get()) } }
val domainModule = module { factory { LoadOrdersUseCase(get()) }; factory { SearchOrdersUseCase(get()) } }
val presentationModule = module { viewModel { OrdersViewModel(get(), get()) } }   // or viewModelOf(::OrdersViewModel)
// Compose: koinViewModel<OrdersViewModel>() from koin-compose-viewmodel (multiplatform)
```

## Rules

- Never construct a ViewModel as a default parameter (`vm: X = X()`) and never give it its own
  `CoroutineScope(Dispatchers.Main)`: use `koinViewModel()`/`viewModel()` and `viewModelScope`.
- Heavy work (bitmap loops, parsing, ML) runs on `Dispatchers.Default`/`IO`, never on Main.
- Every user-facing string goes in resources and is read with `stringResource()`; no hard-coded
  copy in any language.
- Avoid `AlertDialog`s with text fields: prefer inline forms, bottom sheets or a full screen, with
  the form state owned by the ViewModel.
- Small composables, state hoisted; previews use the stateless `Screen`.
- Insets: respect `Scaffold` padding and never apply the same inset twice; a FAB must clear the
  navigation bar under gesture navigation, on foldables and in multi-window. Keep edge-to-edge.
- No deprecated Material 3 APIs; check new choices against current Android guidance.
- Monetised apps: do not show ads until the purchase state has resolved (see `play-billing`).

## Tests

```kotlin
class OrdersViewModelTest {
    @get:Rule val mainRule = MainDispatcherRule()   // sets Dispatchers.Main to a TestDispatcher

    @Test fun `refresh fills the list`() = runTest {
        val vm = OrdersViewModel(LoadOrdersUseCase(FakeOrdersRepository(rows = listOf(row("1")))), SearchOrdersUseCase(FakeOrdersRepository()))
        vm.state.test {
            assertEquals(1, awaitUntil { !it.loading && it.items.isNotEmpty() }.items.size)
            cancelAndIgnoreRemainingEvents()
        }
    }
}
```

Use hand-written fakes for repositories; Turbine for flows. See `android-testing` for dispatcher
rules.

## Conventions from large apps

- **No fat base ViewModel.** Injecting billing, analytics and network services into a base class
  makes every test set up the world. Compose behaviour with small delegates
  (`class X(private val paywall: PaywallDelegate) : ViewModel(), PaywallDelegate by paywall`).
- **Dispatchers through an interface** so tests replace all of them at once:

```kotlin
interface DispatcherProvider {
    val main: CoroutineDispatcher get() = Dispatchers.Main
    val io: CoroutineDispatcher get() = Dispatchers.IO
    val default: CoroutineDispatcher get() = Dispatchers.Default
}
class DefaultDispatcherProvider : DispatcherProvider          // Koin single
```

- **One-shot effects** through `Channel(Channel.BUFFERED).receiveAsFlow()`, collected with
  `repeatOnLifecycle`/`LaunchedEffect`. A `MutableSharedFlow()` without buffer suspends the emitter or
  drops events nobody is collecting.
- **Text in state** as a `UiText` (resource id + args, or raw), resolved in the UI (see `localization`).
- **App-wide events** (signed out, content shared) through one `SharedFlow` event registry with
  typed filters, collected in `viewModelScope`; not through broadcasts.
- **Large arguments** (documents) never in `SavedStateHandle`/navigation args: pass an id
  (see `unsaved-changes-recovery`).
- Constructor parameters for screen arguments: `viewModel { (id: String) -> DetailViewModel(id, get()) }`
  with `koinViewModel { parametersOf(id) }`, or `SavedStateHandle.toRoute<T>()`.

## Checklist

- [ ] `State` is immutable and complete (loading, error, content); `Intent` is sealed; one-shot
      `Effect`s go through a buffered `Channel`, not a bare `SharedFlow`.
- [ ] ViewModel created by `koinViewModel()`/`viewModel()`, work in `viewModelScope`, heavy work
      off Main; screen arguments arrive as ids via `parametersOf`/`toRoute`.
- [ ] `Route` binds state, effects and navigation; `Screen` is stateless and has a preview per
      meaningful state.
- [ ] Strings from resources, spacing and colours from tokens, insets applied once, FAB clears the
      navigation bar under gesture navigation.
- [ ] No deprecated Material 3 APIs; Circuit not mixed in.
- [ ] ViewModel test per intent path with `MainDispatcherRule`, fakes and Turbine; it was seen
      failing once.
- [ ] `./gradlew verify` green (`gradle-quality-gate`).
