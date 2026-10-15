---
name: navigation3-compose
description: Jetpack Navigation 3 for Compose and Compose Multiplatform apps - the app owns a serializable NavKey back stack, NavDisplay with saveable state and ViewModel decorators, entryProvider per feature module composed through Koin, type-safe arguments into MVI ViewModels, returning results, dialogs and bottom sheets as scenes, list-detail with Material adaptive scene strategies, deep links to a synthetic back stack, conditional (auth) flows, and a migration path from Navigation Compose. Use when a project is on Navigation 3 or has decided to move to it; for projects on Navigation Compose keep compose-mvi-viewmodel, and for Circuit keep circuit-screen.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Navigation 3
  - NavDisplay
  - NavKey
  - back stack
  - entryProvider
  - scenes
  - SceneStrategy
  - list-detail
  - deep links
  - Koin
  - Compose Multiplatform
  - migration from Navigation Compose
---

# Navigation 3

Navigation 3 flips the model: **you own the back stack** (a `SnapshotStateList<NavKey>`),
`NavDisplay` renders whatever is on top, and layouts with several visible entries (list-detail,
dialogs over content) are `Scene`s. Do not introduce it into an app that is happy on Navigation
Compose; migrate when you need multi-pane scenes, a stack you can inspect/test, or you already
hit `NavController` limits. The official Navigation 3 recipes cover individual patterns; this
skill is the set of decisions that keep them consistent with the rest of this toolkit.

## Prerequisites

- `androidx.navigation3:navigation3-runtime` and `navigation3-ui` 1.0+; `androidx.lifecycle:lifecycle-viewmodel-navigation3`
  for ViewModel scoping; `androidx.compose.material3.adaptive:adaptive-navigation3` for
  list-detail/supporting-pane strategies. In KMP use the JetBrains artifacts of the same names
  and check they are at the same API level.
- `kotlinx.serialization` plugin: every key is `@Serializable`, so the stack survives process death.
- Decorator names changed between the alphas and 1.0 (`rememberSavedStateNavEntryDecorator` →
  `rememberSaveableStateHolderNavEntryDecorator`, scene setup folded into `NavDisplay`); read the
  installed version's `NavDisplay` signature before writing the wiring below.

## Step 1: keys and the stack

```kotlin
@Serializable data object HomeKey : NavKey
@Serializable data class DetailKey(val itemId: String) : NavKey
@Serializable data class EditKey(val itemId: String?) : NavKey      // null = create

@Composable
fun AppNav(startKey: NavKey = HomeKey) {
    val backStack = rememberNavBackStack(startKey)         // saveable; keys must be @Serializable
    NavDisplay(
        backStack = backStack,
        onBack = { backStack.removeLastOrNull() },
        entryDecorators = listOf(
            rememberSaveableStateHolderNavEntryDecorator(),
            rememberViewModelStoreNavEntryDecorator(),        // ViewModel per entry, cleared on pop
        ),
        entryProvider = appEntryProvider(backStack),
    )
}
```

- Keys carry **ids**, never models or callbacks. Feature modules define their own keys in a
  small `:feature:x:api` (or the shared routes module from `android-multimodule`); nobody else
  constructs another feature's screen.
- One `Navigator` object wraps the list so screens never see `MutableList`:

```kotlin
class Navigator(private val stack: NavBackStack<NavKey>) {
    fun push(key: NavKey) { if (stack.lastOrNull() != key) stack.add(key) }
    fun pop(): Boolean = stack.size > 1 && stack.removeLastOrNull() != null
    fun popTo(key: NavKey, inclusive: Boolean = false) { while (stack.size > 1 && stack.last() != key) stack.removeLast(); if (inclusive) pop() }
    fun replaceTop(key: NavKey) { stack.removeLastOrNull(); stack.add(key) }
    fun replaceAll(vararg keys: NavKey) { stack.clear(); stack.addAll(keys) }
}
```

  Guard against double taps (`push` ignores an identical top) and against popping the root.

## Step 2: entries per feature, composed in the app

```kotlin
// feature module
fun EntryProviderBuilder<NavKey>.detailEntries(navigator: Navigator) {
    entry<DetailKey> { key ->
        val viewModel = koinViewModel<DetailViewModel> { parametersOf(key.itemId) }
        DetailRoute(viewModel, onEdit = { navigator.push(EditKey(key.itemId)) }, onBack = navigator::pop)
    }
}

// app module
@Composable fun appEntryProvider(stack: NavBackStack<NavKey>) = entryProvider {
    val navigator = remember(stack) { Navigator(stack) }
    homeEntries(navigator); detailEntries(navigator); editEntries(navigator)
}
```

- Arguments reach the ViewModel through Koin `parametersOf`, not through a `SavedStateHandle`
  route parser; the ViewModel is scoped to the entry by the decorator, so `itemId` is stable for
  its life. Screens stay the `Route`/`Screen` split from `compose-mvi-viewmodel`: the Route
  binds state and navigation lambdas, the Screen is previewable.
- Navigation effects from a ViewModel are still one-shot `Effect`s collected by the Route and
  turned into `navigator` calls; the ViewModel never holds the stack.

## Step 3: results, dialogs, sheets, panes

- **Results**: the result flows through shared state, not the stack: a `ResultStore` singleton
  (Koin) keyed by the requesting entry's id, or the shared repository the next screen reads. For
  "pick one then return", push the picker with the requester's key and have it `popTo(requester)`
  after writing to the store; the requester observes the store.
- **Dialogs**: `entry<ConfirmDeleteKey>(metadata = DialogSceneStrategy.dialog()) { … }` with
  `sceneStrategy = DialogSceneStrategy()` on the display; the content below stays composed.
- **Bottom sheets**: a custom `SceneStrategy` that renders the top entry in `ModalBottomSheet`
  when its metadata says so; dismissing calls `onBack`. Keep it in `:core:ui` so every feature
  uses the same sheet.
- **List-detail / supporting pane**: `ListDetailSceneStrategy` with
  `ListDetailSceneStrategy.listPane()`/`detailPane()` metadata; the list entry stays on the stack
  under the detail entry, so a phone shows one pane and a tablet two, from the same stack.
  Strategies compose: `DialogSceneStrategy<NavKey>() then ListDetailSceneStrategy<NavKey>()`.
- Predictive back and transitions: `NavDisplay(transitionSpec, popTransitionSpec,
  predictivePopTransitionSpec)`; per-entry overrides via `NavDisplay.transitionSpec(...)`
  metadata. No `BackHandler` that pops (`predictive-back`).

## Step 4: deep links and conditional flows

- Deep link → **synthetic back stack**: parse the URI (validate every segment,
  `android-app-security`), then `replaceAll(HomeKey, DetailKey(id))` so back from the detail lands
  on Home, not on the launcher. Parsing lives in one `DeepLinkParser` with unit tests; the
  Activity's `onNewIntent` calls the same parser.
- Auth: the stack starts at `LoginKey` or `HomeKey` depending on session state from a
  `SessionRepository`, decided once in the composition root; on logout `replaceAll(LoginKey)`.
  Do not guard every entry with an `if (loggedIn)`.
- Multiple top-level tabs: one `NavBackStack` per tab in a `Map<TabKey, NavBackStack>`, saved
  with `rememberSaveable`, and the displayed stack switches with the tab; back on a non-root tab
  stack pops it, back on a root goes to the first tab, then exits.

## Step 5: migrating from Navigation Compose

1. Replace route strings/`@Serializable` routes with `NavKey`s one for one; keep names.
2. Replace `NavHost` with `NavDisplay`; convert each `composable<Route>` to `entry<Key>`; replace
   `navController.navigate(x)`/`popBackStack()` with `navigator.push/pop`.
3. `hiltViewModel`/`koinViewModel` calls stay; add the ViewModel decorator so scoping matches.
4. Deep links: Navigation Compose's `navDeepLink` has no equivalent; implement the parser (Step 4).
5. Tests: the stack is a plain list, so navigation tests become `assertEquals(listOf(HomeKey, DetailKey("1")), backStack)`.
   Keep one instrumented smoke test that a cold start plus a deep link renders the right screen.

## Checklist

- [ ] Keys are `@Serializable` and carry ids only; features expose keys, not screens.
- [ ] One `Navigator` wrapper; no composable mutates the list directly; root cannot be popped.
- [ ] Saveable state and ViewModel decorators installed; ViewModel args via `parametersOf`.
- [ ] Results go through shared state; dialogs/sheets/panes are scenes with metadata.
- [ ] Deep links build a synthetic stack through one tested parser, also from `onNewIntent`.
- [ ] No manual `BackHandler` pops; predictive pop spec set.
