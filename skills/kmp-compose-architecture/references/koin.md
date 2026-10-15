# Koin wiring for a KMP / Compose app

## Module layout

```kotlin
val appModules = listOf(appModule, dataModule, homeModule, detailModule, profileModule)

fun initKoin(platformModules: List<Module> = emptyList(), config: KoinAppDeclaration = {}) =
    startKoin { config(); modules(appModules + platformModules) }

// Android: Application.onCreate → initKoin(platformModules = listOf(androidPlatformModule(this, buildValues)))
// iOS: MainViewController → initKoin(platformModules = listOf(iosPlatformModule()))
```

```kotlin
val appModule = module {
    // The only app-wide scope. Work launched here survives leaving a screen.
    @Suppress("InjectDispatcher")
    single<CoroutineScope> { CoroutineScope(SupervisorJob() + Dispatchers.Default) }
}

val dataModule = module {
    single { SessionStore(authClient = get(), appScope = get()) }
    single { NotesRepository(dao = get<DatabaseProvider>().database().noteDao()) }
    // Exists only for its side effect: build it eagerly.
    single(createdAtStart = true) { StartupClaimer(client = get(), session = get()) }
}

val homeModule = module {
    factory { LoadHomeUseCase(repository = get()) }          // optional: only when it adds logic
    viewModel { HomeViewModel(repository = get(), imageLoader = get()) }
    // Circuit projects register presenter/ui factories here instead: see the circuit-screen skill.
}

fun androidPlatformModule(appContext: Context, values: AndroidBuildValues) = module {
    single<HttpClientEngine> { OkHttp.create() }
    single<DatabaseProvider> { AndroidDatabaseProvider(appContext) }
    single<DataStorePathProvider> { AndroidDataStorePathProvider(appContext) }
    single<AuthClient> { AndroidAuthClient(appContext, webClientId = values.webClientId) }
    single<ImageLoader> { appImageLoader(appContext, get()) }
}
```

- Compose: `koinViewModel<HomeViewModel>()` (artifact `koin-compose-viewmodel`, multiplatform).
- Several implementations collected with `getAll<T>()`: register each as
  `single { Impl() } bind T::class`. `single<T> { … }` repeated across modules overwrites one key.
- Multi-module variant: each feature module exposes `val FeatureModule = module { … }` and composes
  its own dependencies with `includes(OtherModule)`.

## Graph test

Boot the real modules with fakes for every platform seam, without the global `startKoin`, and
always close Koin (module singletons otherwise leak between tests).

```kotlin
class KoinGraphTest {
    @Test fun `every registered definition resolves`() {
        val koin = koinApplication { modules(appModules + fakePlatformModule()) }.koin
        try { assertEveryDefinitionResolves(koin) } finally { koin.close() }
    }
}

fun assertEveryDefinitionResolves(koin: Koin) {
    assertNotNull(koin.get<SessionStore>())
    assertNotNull(koin.get<HttpClient>())
    assertNotNull(koin.get<HomeViewModel>())
    // one line per ViewModel / state holder; Circuit apps also resolve every screen (circuit-screen)
}

fun fakePlatformModule(appScope: CoroutineScope = TestScope()) = module {
    single<CoroutineScope> { appScope }
    single<HttpClientEngine> { MockEngine { respondOk() } }
    single<ImageLoader> { NoOpImageLoader }
    single<DatabaseProvider> { FakeDatabaseProvider() }
    // one fake per platform seam
}
```

Koin also ships `verify()` (`koinApplication { … }.verify()` / `module.verify()`), which checks
constructor parameters statically; the resolve test above additionally proves runtime wiring.

Reuse `assertEveryDefinitionResolves` from an Android instrumented test with the *real* platform
module, so the production adapters are also proven to resolve.
