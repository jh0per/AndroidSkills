---
name: views-compose-interop
description: Working in a hybrid Android app with Fragments, XML/DataBinding and Jetpack Compose - Compose screens hosted in fragments, Compose controls inside XML (AbstractComposeView), Views inside Compose (AndroidView), theme bridging, Jetpack Navigation with SafeArgs and safe navigation from ViewModels, one-shot events collected with repeatOnLifecycle, deep links deferred until the app is ready, large state across process death, and an incremental migration plan. Use when touching a Fragment/XML codebase, adding Compose to it, or migrating screens.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Views
  - XML layouts
  - Fragments
  - ComposeView
  - AndroidView
  - SafeArgs
  - deep links
  - migration
---

# Views ↔ Compose interop and migration

## Strategy

- New screens in Compose; existing screens migrate when they are substantially changed, not in a
  big-bang rewrite.
- Shared widgets exist once per toolkit during migration (View version and Compose version) with the
  same tokens; the View version is deleted when its last XML user is gone.
- Leaf-first: replace small controls inside XML with Compose (`AbstractComposeView`), then whole
  screens, then navigation.
- Keep one design-system source of truth: colours/dimens in XML resources read by the Compose theme,
  or Compose tokens with XML mirrors generated from them, never two hand-maintained copies.

## Compose screen in a Fragment

```kotlin
abstract class ComposeFragment<VM : ViewModel> : Fragment() {
    protected abstract val viewModel: VM
    @Composable protected abstract fun Screen(viewModel: VM)

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?) =
        ComposeView(requireContext()).apply {
            setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnViewTreeLifecycleDestroyed)
            setContent { AppTheme { Screen(viewModel) } }
        }
}

class OrdersFragment : ComposeFragment<OrdersViewModel>() {
    override val viewModel: OrdersViewModel by viewModel()            // Koin; or by viewModels()
    @Composable override fun Screen(viewModel: OrdersViewModel) = OrdersRoute(viewModel)
}
```

- Get the ViewModel with the delegate, not by reflecting on generic superclasses (breaks with
  intermediate generics and R8).
- Keep base fragments thin: no injected billing/analytics/network services in a base class. Use
  composition (delegates) for cross-cutting behaviour.
- Insets: use foundation `WindowInsets` APIs, not the deprecated Accompanist insets.

## Compose control inside XML

```kotlin
class ComposeSlider @JvmOverloads constructor(context: Context, attrs: AttributeSet? = null, defStyle: Int = 0) :
    AbstractComposeView(context, attrs, defStyle) {
    var value by mutableFloatStateOf(0f)
    var range by mutableStateOf(0f..1f)
    var onValueChange: ((Float) -> Unit)? = null

    @Composable override fun Content() {
        if (isInEditMode) return                                       // layout preview
        AppTheme { Slider(value = value.coerceIn(range), onValueChange = { onValueChange?.invoke(it) }, valueRange = range) }
    }
    override fun onDetachedFromWindow() { super.onDetachedFromWindow(); onValueChange = null }
}
```

Inside a custom View, a `ComposeView` child can render state from `StateFlow`s with `collectAsState()`.

## View inside Compose

```kotlin
AndroidView(
    factory = { ctx -> PlayerView(ctx).apply { useController = false } },
    update = { view -> view.player = player },
    onRelease = { view -> view.player = null },
    modifier = Modifier.fillMaxWidth(),
)
```

In lazy lists use the `onReset` parameter to reuse views; never create heavy views per recomposition.

## Navigation (Jetpack Navigation + SafeArgs)

```kotlin
fun NavController.navigateSafe(directions: NavDirections, options: NavOptions? = null) {
    // Double taps otherwise crash with "action … unknown from the current destination".
    if (currentDestination?.getAction(directions.actionId) != null) navigate(directions, options)
}

sealed interface NavCommand {
    data class To(val directions: NavDirections, val options: NavOptions? = null) : NavCommand
    data object Back : NavCommand
    data class PopTo(@IdRes val destination: Int, val inclusive: Boolean) : NavCommand
}
```

The ViewModel exposes `navigation: Flow<NavCommand>` from a `Channel(BUFFERED)`; the fragment collects:

```kotlin
viewLifecycleOwner.lifecycleScope.launch {
    viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.navigation.collect { command ->
            when (command) {
                is NavCommand.To -> findNavController().navigateSafe(command.directions, command.options)
                NavCommand.Back -> findNavController().navigateUp()
                is NavCommand.PopTo -> findNavController().popBackStack(command.destination, command.inclusive)
            }
        }
    }
}
```

- One-shot events: `Channel(Channel.BUFFERED).receiveAsFlow()`, collected with `repeatOnLifecycle`.
  A `MutableSharedFlow()` without buffer suspends the emitter or drops events with no collector;
  `launchWhenResumed` is deprecated. `LiveData<Event<T>>` wrappers are legacy.
- Fragment results (`setFragmentResultListener`) for returning values (e.g. after a paywall).
- Back: `OnBackPressedCallback` registered with the view lifecycle; with predictive back (API 34+),
  enable `android:enableOnBackInvokedCallback="true"` and avoid overriding `onBackPressed`.

## Deep links

```kotlin
sealed interface DeepLink {
    data class Screen(val directions: NavDirections) : DeepLink
    data class Content(val id: String) : DeepLink
    data class External(val url: String) : DeepLink
}

class DeepLinkHandler(private val parser: DeepLinkParser) {
    private val _pending = MutableStateFlow<DeepLink?>(null)
    val pending: StateFlow<DeepLink?> = _pending.asStateFlow()
    fun handle(uri: Uri) { _pending.value = parser.parse(uri) }
    fun consume(): DeepLink? = _pending.getAndUpdate { null }
}
```

- Store the link as **pending** and consume it once the app is ready (auth resolved, config loaded,
  main screen shown). Handle both `onCreate` intent and `onNewIntent`.
- Attribution SDKs may re-deliver the last link on every open; remember the last handled link.
- No `runBlocking` in link handling.
- Verified App Links: `autoVerify="true"` + `assetlinks.json` on the domain; test with
  `adb shell pm get-app-links <package>`.

## Large state across process death

The Bundle (and Binder transactions) are limited to roughly 1 MB; large payloads in arguments or
`onSaveInstanceState` crash with `TransactionTooLargeException`. Keep an id in the Bundle and the
payload in memory, writing it to a file in `onSaveInstanceState` and restoring lazily from that
file (falling back to the autosave draft). Apply the same rule to Compose navigation arguments.
Test with "Don't keep activities" and `adb shell am kill <package>` while backgrounded.

## Checklist for a migrated screen

1. Same ViewModel, now exposing `StateFlow<State>` (convert `LiveData` with `asFlow()` if needed).
2. Stateless composable + previews; strings/dimens reused from resources.
3. Navigation still via the NavController commands; no NavController inside the composable.
4. Old layout, binding adapters and View widgets removed when unused.
5. Screenshot/UI test updated; TalkBack order checked.
