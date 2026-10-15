---
name: android-multimodule
description: Structure a multi-module Android/Compose app - api/impl module split, feature modules that navigate through a shared routes module, one networking module per backend service, dependency inversion so features never see Room or SDKs, Koin module composition across modules, embedding an internal library (including from a git submodule) through a dependencies interface and a two-way messenger, and interactor base classes. Use when adding a module, splitting a growing app, embedding a library module, or untangling module dependencies.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - multi-module
  - module graph
  - convention plugins
  - dependency inversion
  - Koin
  - feature modules
  - git submodule
---

# Multi-module Android app

Modules are a cost (build config, wiring, visibility). Add them for a real boundary: independent
ownership, reuse, build time, or a dependency you need to hide. For the build configuration of
each module use convention plugins (`gradle-build-setup`).

## Module graph

```text
:app                          composition root: Application, Activity, Koin startup, adapters for feature interfaces
:core:routes                  navigation keys/routes only (no logic). Every feature depends on it,
                              so features navigate to each other without depending on each other
:core:ui                      design system (see design-system-module)
:core:localisation            strings shared by features
:core:domain-api              tiny: Interactor base classes, Result types (coroutines + paging only)
:core:data-api                in-memory state holders shared across features (DataHolder<T>)
:core:network                 HTTP client, auth token provider interface, shared DTOs
:core:network:errors          pure Kotlin: NoConnectionException, BackendException hierarchy
:core:network:connectivity    ConnectionChecker + client plugin
:core:network:service-<name>  one per backend service: Repository + RepositoryImpl + response DTOs
:feature:<name>               screen(s): state holder + Ui + Koin module
:feature:<name>-logic         use cases without UI, reused by several screens
:debug-menu                   debugImplementation only (see debug-tooling)
```

Rules:

- Dependencies point inward: feature → core; never feature → feature, never core → feature.
- A pure-Kotlin errors module lets UI modules check `is NoConnectionException` without depending on
  the HTTP client.
- Service modules depend only on `:core:network` and the HTTP library; DTOs stay there, mapping to
  domain/UI models happens in the logic or a `mappers` module.
- Each module has one Koin module (`val OrdersModule = module { … }`), composed with `includes(...)`;
  `:app` lists the top-level modules in `startKoin`.
- `nonTransitiveRClass=true`; import shared strings explicitly
  (`import com.example.core.localisation.R.string as Strings`).

## Dependency inversion at module edges

A feature declares what it needs as an interface; `:app` implements it over Room, the SDK or
another feature. The feature never sees Room entities or SDK types.

```kotlin
// :feature:uploads
interface UploadStatusSource {
    fun uploadsByStatus(status: UploadStatus): Flow<ImmutableList<UploadItem>>
}

// :app
val UploadsAdapters = module {
    factory<UploadStatusSource> {
        val dao = get<UploadDao>()
        object : UploadStatusSource {
            override fun uploadsByStatus(status: UploadStatus) =
                dao.observeByStatus(status.name).map { rows -> rows.map { it.toItem() }.toImmutableList() }
        }
    }
}
```

The same applies to auth: `:core:network` defines `interface TokenProvider { suspend fun token(): String? }`
and `:app` implements it with the auth SDK, so networking never depends on the SDK.

## Interactor bases (optional)

Use when many use cases need loading flags, timeouts and Result wrapping:

```kotlin
abstract class Interactor<in P, R> {
    private val running = MutableStateFlow(0)
    val inProgress: Flow<Boolean> = running.map { it > 0 }.distinctUntilChanged()

    suspend operator fun invoke(params: P, timeout: Duration = 5.minutes): Result<R> {
        running.update { it + 1 }
        return try {
            Result.success(withTimeout(timeout) { doWork(params) })
        } catch (e: CancellationException) {
            throw e                                    // runCatching would swallow cancellation
        } catch (e: Exception) {
            Result.failure(e)
        } finally {
            running.update { it - 1 }
        }
    }
    protected abstract suspend fun doWork(params: P): R
}

/** Observes a flow for the latest params; invoke() is non-suspending. */
abstract class SubjectInteractor<P : Any, T> {
    private val params = MutableSharedFlow<P>(replay = 1, extraBufferCapacity = 1, onBufferOverflow = BufferOverflow.DROP_OLDEST)
    val flow: Flow<T> = params.distinctUntilChanged().flatMapLatest { createObservable(it) }.distinctUntilChanged()
    operator fun invoke(p: P) { params.tryEmit(p) }
    protected abstract fun createObservable(params: P): Flow<T>
}
```

Do not wrap trivial repository calls in interactors just for symmetry.

## Shared in-memory state

```kotlin
open class DataHolder<T>(initial: T) {
    private val state = MutableStateFlow(initial)
    val flow: StateFlow<T> = state.asStateFlow()
    val value: T get() = state.value
    fun update(f: (T) -> T) = state.update(f)
}
class PickedUploadHolder : DataHolder<PickedUpload?>(null)   // registered as a Koin single
```

Holders are process memory: anything that must survive process death also goes to persistence.

## Embedding an internal library (e.g. a chat or support SDK)

The library exposes a small API and receives host data through an interface:

```kotlin
// library
interface ChatSdkDependencies {
    fun currentUser(): Flow<ChatUser?>
    fun theme(): ChatTheme                        // host tokens mapped to the library's theme
    fun initialState(): ChatState?                // restore after recreation
}

class ChatMessenger {                            // host ⇄ library without the library knowing host features
    private val _events = MutableSharedFlow<ChatEvent>(extraBufferCapacity = 16)
    val events: SharedFlow<ChatEvent> = _events.asSharedFlow()
    internal var dispatch: ((ChatAction) -> Unit)? = null
    fun send(action: ChatAction) { dispatch?.invoke(action) }        // host → library
    internal fun emit(event: ChatEvent) { _events.tryEmit(event) }   // library → host
}
sealed interface ChatEvent {
    data class OpenOrderRequested(val orderId: String) : ChatEvent       // the host owns the orders feature
    data class ShowError(val error: Throwable) : ChatEvent
    data object BackClicked : ChatEvent
}
```

- The library depends only on its own modules, never back on host modules; a back-dependency
  creates a cycle in product terms even when Gradle allows it.
- Do not give an event flow `replay = 1` unless late subscribers should re-receive the last event;
  for one-shot events that re-delivery is a bug.
- The host collects library events in a lifecycle-aware scope (Activity/ViewModel), not in a
  `MainScope()` launched from `Application.onCreate`.
- Theme bridging: provide the library's theme through a `CompositionLocal` built from host tokens.

### From a git submodule

```kotlin
// settings.gradle.kts
include(":chat")
project(":chat").projectDir = file("libs/chat/chat")
include(":chat:models")                           // nested path resolves inside libs/chat/chat/models
include(":chat-sample")
project(":chat-sample").projectDir = file("libs/chat/app")
```

- The submodule's own `libs.versions.toml`/build logic is ignored by the host; keep versions in
  sync or share the catalog. Project paths must be unique across host and submodule.
- CI must init submodules (`git submodule update --init --recursive`) with credentials allowed to
  read the library repository (see `android-ci-distribution`).
- Prefer publishing the library to a Maven repository once its API is stable; submodules couple
  release cycles.

## Navigation across modules

- Route/screen keys live in `:core:routes`; features depend on that module only.
- Web destinations (cart, help) are routes too, handled by a starter that opens Custom Tabs with
  the toolbar colour and falls back to `ACTION_VIEW` on `ActivityNotFoundException`.
- Programmatic navigation requests from non-UI code go through a `SharedFlow<Route>` that the
  Activity collects; prefer returning navigation as an effect from the state holder.
- Choose the start destination after the auth check resolves; render nothing (or a splash) until
  then rather than flashing the wrong screen.

## Checklist for a new module

1. Which boundary does it protect, and who owns it?
2. Apply the convention plugin; set `namespace`.
3. Expose one Koin module; register it where the app composes features.
4. Interfaces for anything it needs from outside; no Room/SDK types in its API.
5. Add it to the Koin graph test and the CI gate.
