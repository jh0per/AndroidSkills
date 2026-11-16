# Parcelable screens

For a project on an older Circuit, where `Screen` is `Parcelable` on Android, and for a project
on current Circuit that keeps some screens `Parcelable`. New screens in a current project are
serialized (`SKILL.md`).

## Which Circuit is it

Open the Android declaration of `com.slack.circuit.runtime.screen.Screen`:

| Declaration | Meaning |
|---|---|
| `interface Screen : CircuitSaveable, Parcelable` | older release: every screen must be `Parcelable` on Android, and the platform saves it as is |
| `interface Screen : CircuitSaveable` | current release: a plain screen is not saveable by itself; serialize it, or implement `ParcelableScreen` |

After an upgrade across that change a `@Parcelize` screen that implements plain `Screen` stops
compiling for Android with `No 'Parcelable' supertype`. Either move it to `@Serializable` and the
saver list, or change its supertype to `ParcelableScreen` and keep the rest of this page.

## Older release

```kotlin
@CommonParcelize            // or @Parcelize in an Android-only app
data class DetailScreen(val itemId: String) : Screen
```

Host: `rememberSaveableBackStack(root = HomeScreen)`, `rememberCircuitNavigator(backStack =
backStack, onRootPop = { … }, enableBackHandler = true)` and `NavigableCircuitContent(navigator,
backStack)`. The back-handler rule of `SKILL.md` applies here too.

## Current release, Parcelable kept

```kotlin
@CommonParcelize
data class DetailScreen(val itemId: String) : ParcelableScreen   // just a Screen outside Android
```

Circuit's default saver passes `Parcelable` values through, so a project with only such screens
sets no saver. Next to serialized screens, combine the two (see `references/state-restoration.md`).
A screen that is neither `Parcelable` nor claimed by a saver fails when state is saved, not when
it is opened.

## Multiplatform parcelize shim

Screens declared in `commonMain` need a marker that the parcelize compiler plugin treats as
`@Parcelize` for the Android compilation only. No expect/actual is needed:

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
In a module on `com.android.kotlin.multiplatform.library` apply
`org.jetbrains.kotlin.plugin.parcelize` the same way: the shim above is unchanged there.

## R8

`@Parcelize` already keeps `CREATOR`. If restore after process death fails on a minified build, add
`-keepnames class com.example.app.**Screen` (names only), never `{ *; }` (see
`android-release-signing`). Process-death restore is where a missing rule shows up.
