---
name: kmp-compose-architecture
description: Architecture rules for a Kotlin Multiplatform + Compose Multiplatform app (Android first, iOS optional) built on Koin, Ktor, Room KMP and DataStore, with any unidirectional presentation pattern (ViewModel MVI or Circuit). Use when planning a feature, adding a package or module, wiring a platform API into common code, or reviewing whether a change respects layer boundaries.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Kotlin Multiplatform
  - Compose Multiplatform
  - architecture
  - Koin
  - Ktor
  - Room KMP
  - DataStore
  - layer boundaries
---

# KMP + Compose app architecture

A single-module-first architecture that scales: packages own responsibilities, platform APIs sit
behind plain interfaces, and every screen follows the same unidirectional pattern.

## Stack

| Concern | Choice |
|---|---|
| Language/UI | Kotlin Multiplatform, Compose Multiplatform, Material 3 |
| Presentation | One unidirectional pattern per app: state holder → immutable State → Ui → events. ViewModel MVI (`compose-mvi-viewmodel`, works in KMP via the multiplatform lifecycle ViewModel) or, if the project already uses it, Circuit (`circuit-screen`) |
| Navigation | One back stack owner: Navigation Compose (multiplatform) or the presentation framework's own navigator |
| DI | Koin; repositories and state holders wired at the composition root |
| Network/JSON | Ktor (OkHttp on Android, Darwin on iOS) + kotlinx.serialization (see `ktor-api-client`) |
| Persistence | Room KMP + bundled SQLite; DataStore Preferences in common code (see `local-persistence`) |
| Images | Coil 3 `AsyncImage`, one `ImageLoader` built in common code |
| Verification | JVM state-holder/repository tests, the same `commonTest` on an iOS simulator, Android instrumented tests |

Versions live in `gradle/libs.versions.toml`, never in docs. Do not add a second navigation
framework, a base ViewModel/presenter class, a generic use-case layer or a factory framework "for
consistency". Detect what the project already uses before applying any pattern; never introduce
Circuit or switch navigation libraries as a side effect of a feature.

## Package layout (one Gradle module to start)

```text
commonMain/com/example/app/
  domain/              pure models and state transitions; no UI, no data imports
  data/
    api/               transport, wire DTOs, error mapping
    auth/              session and auth flows
    db/                Room entities, DAOs, database seam
    repo/              repositories, sync, hand-offs between screens
    prefs/             preference contracts + DataStore implementations
  ui/
    theme/             colour, type, spacing, shape tokens
    components/        reusable controls, shared chrome, state views
    <feature>/         state holder (ViewModel/presenter) + State/Intent + Ui per feature
  di/                  Koin modules, navigation assembly
androidMain/           entry points + Android implementations of seams
iosMain/               iOS composition root + implementations
commonTest/            domain, repository, state-holder and DI tests
androidInstrumentedTest/  real rendering, touch and platform integration
```

Split packages by responsibility **before** adding Gradle modules. A new module needs evidence: a
measured build-time problem, independent reuse, a new platform target, or a boundary the single
module cannot protect. "We added a screen" is not a reason. (Large teams with ~50 modules usually
pay for it in build config; see `gradle-build-setup` for convention plugins if you go there.)

## Dependency direction

```text
Ui ── Event ──▶ State holder ──▶ Repository / platform seam ──▶ HTTP / DAO / OS API
 ▲                  │
 └──── State ◀──────┘
```

- Render-only UI consumes state and emits events. It never calls the network, a DAO or the navigator
  directly (navigation is an effect/callback decided by the state holder).
- State holders (ViewModels or presenters) orchestrate repositories, app-scoped controllers and platform seams.
- Repositories own HTTP/DAO work. Screens never query Room or issue requests directly.
- Domain code owns state transitions; UI calls domain actions instead of mutating fields.
- Geometry and math helpers stay pure (no Compose runtime) so they are trivially unit-testable.
- No Android or iOS API in `commonMain`. No cross-feature internal imports; move shared behaviour
  to its lowest legitimate owner instead of creating cycles.

## Platform seams: interfaces, not expect/actual

Expose platform functionality as a **plain interface in common code** and provide the
implementation from the platform module:

- Through **Koin** when no Activity or composition is needed (HTTP engine, auth client, gallery
  writer, database provider, DataStore path provider).
- Through a **`staticCompositionLocalOf`** when the seam needs `@Composable` members or an
  Activity (image picker, billing flow, permission prompts).
- When both are needed, the Activity provides the *Koin* instance to the CompositionLocal so there
  is exactly one object.

```kotlin
// commonMain
interface PlatformImageSupport {
    @Composable fun rememberImagePicker(onPicked: (PickedImage) -> Unit): ImagePicker
    fun decodeImage(image: PickedImage, maxSide: Int? = null): ImageBitmap?
}
val LocalPlatformImageSupport = staticCompositionLocalOf<PlatformImageSupport> {
    error("PlatformImageSupport not provided: wrap the root in CompositionLocalProvider")
}

// androidMain, MainActivity.onCreate
setContent {
    CompositionLocalProvider(
        LocalPlatformImageSupport provides GlobalContext.get().get<PlatformImageSupport>(),
        LocalPlatformBillingSupport provides AndroidPlatformBillingSupport(),
    ) { App() }
}
```

Reserve `expect/actual` for generated code that requires it (Room's `RoomDatabaseConstructor`).
Do not copy that exception for ordinary adapters: interfaces are fakeable in `commonTest`,
`expect/actual` is not.

**Build values:** Android adapters never read `BuildConfig` or the app's `R` directly. Read them
once next to the `Application`, put them in a small `AndroidBuildValues` data class, and hand each
adapter only its own value. Library modules cannot see the app's `BuildConfig`, and this keeps
adapters testable. The API origin is a build-time value, never a runtime user setting.

## State and lifetimes

- Screen state that must survive configuration change lives in the state holder (a ViewModel, or
  `rememberRetained` in Circuit); `rememberSaveable` only for small UI-local values.
- Process-death-critical state goes through the data layer (Room/DataStore), not retained state.
- Coroutines follow the owning lifecycle. One app-wide `CoroutineScope(SupervisorJob() + Default)`
  in Koin for work that must outlive a screen (sync push after a save, session refresh).
- App-scoped controllers only for state that genuinely outlives a screen (session, preferences,
  sync). No mutable global content state.
- Large payloads (file bytes) never travel in navigation arguments/keys; use a one-shot
  hand-off holder in the data layer that the next screen consumes once.

## Koin wiring

See `references/koin.md`. Key rules:

- `viewModel { }`/`viewModelOf(::X)` for ViewModels, `factory { }` for stateless use cases, `single` for
  repositories and stores.
- When several implementations of one interface must all be collected with `getAll()`, register each
  with `single { Impl() } bind Interface::class`; repeating `single<Interface> { … }` overwrites one key.
  (Circuit factories are the common case: see `circuit-screen`.)
- One `KoinGraphTest` resolves the whole graph, including every ViewModel, with a fake platform module.
- Each DataStore file is a Koin `single`: DataStore allows one active instance per file.

## Planning checklist for a feature

1. Name the affected surfaces and the component owners you will reuse (see `compose-ui-practices`).
2. Name the state owner, effect lifetimes and allowed imports for each new class.
3. Name the inset owner and scroll owner for every new surface.
4. List platform seams touched; prefer extending an existing interface over adding a new one.
5. Record debt you are deliberately not fixing; existing violations are not precedent.

## Completion

Run the full gate (`gradle-quality-gate`), inspect changed UI on a device at compact and wide sizes
with large font scale and both themes, remove replaced code, and report unrun checks explicitly.
A green build does not prove architecture compliance unless a rule actually enforces the boundary.
