---
name: kmp-ios-interop
description: Adding or maintaining the iOS target of a Kotlin Multiplatform + Compose Multiplatform app - the iOS composition root, Swift-owned native SDKs behind callback bridges converted to suspend functions, honest placeholder seams, framework and Xcode build-phase setup, Room/DataStore/file locations on iOS, Kotlin/Native gotchas, iosTest and XCUITest smoke tests. Use when working on iosMain, the Xcode project, or a seam that must work on both platforms.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Kotlin Multiplatform
  - iOS
  - Swift interop
  - Kotlin/Native
  - Xcode
  - composition root
  - XCUITest
---

# KMP: the iOS side

## Ownership boundary

- **Swift owns native SDKs** (Firebase, StoreKit 2, Sign in with Apple, UserNotifications) behind
  callback protocols with Objective-C-friendly types.
- **Kotlin `iosMain` owns** coroutines, Flow, Compose and Koin: it turns the callbacks into suspend
  functions and registers implementations of the common seams.
- No `suspend`, `Flow` or `@Composable` crosses into Swift-facing types. Swift cannot implement a
  seam that has composable members; keep those seams Kotlin-side and give them a plain bridge.

## Bridges

```kotlin
// iosMain: Swift implements this. Plain types only.
interface NotificationAuthBridge {
    fun current(completion: (Boolean) -> Unit)       // may be called on any thread, exactly once
    fun request(completion: (Boolean) -> Unit)
}

internal suspend fun awaitAnswer(call: ((Boolean) -> Unit) -> Unit): Boolean =
    suspendCancellableCoroutine { cont ->
        val answered = AtomicInt(0)                    // kotlin.concurrent; a double completion must not crash
        call { value -> if (answered.compareAndSet(0, 1) && cont.isActive) cont.resume(value) }
    }
```

```swift
final class NotificationAuth: NotificationAuthBridge {
    func current(completion: @escaping (KotlinBoolean) -> Void) {
        UNUserNotificationCenter.current().getNotificationSettings { s in
            let allowed: [UNAuthorizationStatus] = [.authorized, .provisional, .ephemeral]
            completion(KotlinBoolean(value: allowed.contains(s.authorizationStatus)))
        }
    }
    func request(completion: @escaping (KotlinBoolean) -> Void) {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in
            self.current(completion: completion)       // read the settings back; do not trust `granted`
        }
    }
}
```

Every bridge documents four things: cancellation, single completion, calling thread, lifetime.
Bridges with listeners (auth state, transactions) also define how they are disposed.

Test each bridge in `iosTest`: true/false answers, a second completion ignored, completion from a
background queue, a cancelled caller dropping a late answer, a bridge that never answers timing out
(`withTimeoutOrNull`).

## Composition root

```kotlin
@Suppress("FunctionName")
fun MainViewController(notifications: NotificationAuthBridge /*, other bridges */): UIViewController {
    if (KoinPlatform.getKoinOrNull() == null) initKoin(platformModules = listOf(iosPlatformModule(notifications)))
    val koin = KoinPlatform.getKoin()
    return ComposeUIViewController {
        CompositionLocalProvider(                      // the same set of locals MainActivity provides
            LocalPlatformImageSupport provides koin.get(),
            LocalNotificationPermission provides koin.get(),
            LocalPlatformBillingSupport provides UnavailableBilling,
        ) { App() }
    }
}
```

```swift
struct ComposeHost: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> UIViewController { MainViewControllerKt.MainViewController(notifications: NotificationAuth()) }
    func updateUIViewController(_ vc: UIViewController, context: Context) {}
}
// ContentView: ComposeHost().ignoresSafeArea()   // Compose owns the insets
```

## Honest placeholders

Seams not yet built on iOS get stubs that say so: sign-in throws "not available", billing reports
`available = false`, on-device ML answers `Unsupported`, gallery save answers `Failed`. Collect them
in one file (`IosPendingSeams.kt`) with the task that replaces each. Never return fake success.

## Gradle and Xcode

```kotlin
kotlin {
    listOf(iosArm64(), iosSimulatorArm64()).forEach {
        it.binaries.framework { baseName = "ComposeApp"; isStatic = true }   // static: Compose resources travel with the framework
    }
}
dependencies {
    add("kspIosArm64", libs.room.compiler)
    add("kspIosSimulatorArm64", libs.room.compiler)
}
compose.resources { packageOfResClass = "com.example.app.resources" }      // stable Res package
```

Xcode target:

- Run Script phase before compile: `cd "$SRCROOT/.." && ./gradlew :composeApp:embedAndSignAppleFrameworkForXcode`
  (export `ANDROID_HOME` with a default: Gradle configures the whole build, Android included).
- `FRAMEWORK_SEARCH_PATHS = $(SRCROOT)/../composeApp/build/xcode-frameworks/$(CONFIGURATION)/$(SDK_NAME)`,
  `OTHER_LDFLAGS = -framework ComposeApp`, `ENABLE_USER_SCRIPT_SANDBOXING = NO`.
- Generated assets shared with Android: a folder reference in the Xcode project.

## Files on iOS

| Data | Location |
|---|---|
| Room database, DataStore files | `Documents/` (`NSDocumentDirectory`) beside each other |
| Downloaded fonts and other re-fetchable but required assets | `Application Support/` |
| Throwaway cache | `Caches/` only if losing it is harmless; iOS purges it, and a "cached" flag will then lie |

## Kotlin/Native gotchas

- No `java.*` in common code or tests: `kotlinx.io.IOException`, a pure-Kotlin SHA-256, `kotlin.concurrent.AtomicInt/AtomicReference`.
- Koin's `GlobalContext` is JVM-only; use `KoinPlatform`.
- Back-ticked test names cannot contain commas on Native.
- `@JvmInline` needs an explicit `kotlin.jvm.JvmInline` import in common code.
- Skia needs font bytes up front; variable fonts need explicit `FontVariation.Settings` per weight
  and a unique identity per weight (see `fonts-management`).
- Check the **resolved** dependency graph (`./gradlew :composeApp:dependencies`) for Compose/Material
  versions; a comment in the catalog is not evidence.

## Tests

```bash
./gradlew :composeApp:iosSimulatorArm64Test           # commonTest + iosTest on a simulator
xcodebuild -project iosApp/iosApp.xcodeproj -scheme iosApp \
  -destination 'platform=iOS Simulator,name=iPhone 16' CODE_SIGNING_ALLOWED=NO test
```

XCUITest smoke: launch with `-AppleLanguages (en) -AppleLocale en_US`, find elements by Compose
`testTag` exposed to accessibility (`app.descendants(matching: .any)["tag"]`), attach screenshots
with `lifetime = .keepAlways`. Prove each new test can fail with a deliberate defect once.

If CI has no macOS runner, report iOS results as local evidence, not CI-proven.
