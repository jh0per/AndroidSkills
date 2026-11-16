# The gate with the AGP 9 layout: application module plus KMP library module

AGP 9 does not allow the Kotlin Multiplatform plugin next to `com.android.application`
(`gradle-build-setup`). The code then lives in a module on
`com.android.kotlin.multiplatform.library` (`:composeApp` here), and a thin application module on
AGP's built-in Kotlin packages it (`:androidApp`). Compared with the single-module gate in
`SKILL.md`, three things change: the task names, how lint reaches the library, and detekt with
type resolution in the application module.

## Task names

| Single module (`SKILL.md`) | With this layout |
|---|---|
| `:app:testDebugUnitTest` | `:composeApp:testAndroidHostTest` runs `commonTest` on the JVM (needs `withHostTestBuilder { }` in the `android { }` block). Add `:androidApp:testDebugUnitTest` when that module gets its first test. |
| `:app:ktlintCheck` | `:composeApp:ktlintCheck`, `:androidApp:ktlintCheck`, and `:ktlintCheck` for the root scripts |
| `:app:detekt` | `:composeApp:detekt`, `:androidApp:detekt` |
| `:app:detektAndroidDebug` | `:composeApp:detektAndroidMain`, and `:androidApp:detektDebug`, which you assemble (below) |
| `:app:lintDebug` | `:androidApp:lintDebug`, once the library applies the lint plugin (below) |
| `:app:assembleDebug` | `:androidApp:assembleDebug` |
| `:app:assembleDebugAndroidTest` | `:composeApp:assembleAndroidDeviceTest` (needs `withDeviceTestBuilder { }`); run on a device with `connectedAndroidDeviceTest` |
| `:app:check<Variant>…` | `:androidApp:check<Variant>…`: the merged manifest belongs to the application |

```kotlin
tasks.register("verify") {
    group = "verification"
    dependsOn(
        ":composeApp:testAndroidHostTest",
        ":composeApp:ktlintCheck", ":androidApp:ktlintCheck", ":ktlintCheck",
        ":composeApp:detekt", ":composeApp:detektAndroidMain",
        ":androidApp:detekt", ":androidApp:detektDebug",
        ":androidApp:lintDebug",
        ":androidApp:assembleDebug",
        ":androidApp:checkDebugNoAdvertisingId",
        ":composeApp:assembleAndroidDeviceTest",   // once instrumented tests exist
    )
}
```

## Lint: give the library a lint model

```toml
# gradle/libs.versions.toml
android-lint = { id = "com.android.lint", version.ref = "agp" }
```

```kotlin
// composeApp/build.gradle.kts
plugins {
    alias(libs.plugins.kotlin.multiplatform)
    alias(libs.plugins.android.kotlin.multiplatform.library)
    alias(libs.plugins.android.lint)     // without it :androidApp:lintDebug does not read this module
}
```

Keep `checkDependencies = true` in the application. Measured with one planted error in the
library's `androidMain` (a call above `minSdk`) and one in `commonMain` (an unremembered
`mutableStateOf` in a composable): without the plugin the application's lint reported
"No issues found"; with it, both. Compose's own lint checks run on `commonMain` this way.

## detekt in the library

```kotlin
detekt {
    buildUponDefaultConfig = true
    allRules = true
    config.setFrom(rootProject.files("config/detekt/detekt.yml"))
    // The plain task knows no types, so it can read the iOS source sets on any host.
    source.setFrom(files("src/commonMain/kotlin", "src/commonTest/kotlin", "src/androidMain/kotlin",
        "src/iosMain/kotlin", "src/iosTest/kotlin"))
}

tasks.withType<io.gitlab.arturbosch.detekt.Detekt>().configureEach {
    exclude { it.file.absolutePath.contains("/build/generated/") }
    if (name == "detektAndroidMain") {
        setSource(files("src/commonMain/kotlin", "src/commonTest/kotlin", "src/androidMain/kotlin"))
    }
}
```

`detektAndroidMain` is the task with type resolution. Left alone it reads only `androidMain`:
a not-null assertion on a nullable value planted in `commonMain` passed until the sources were
listed as above. `configureEach` with a name test needs no `afterEvaluate`.

## detekt with type resolution in the application module

The stable detekt line (plugin `io.gitlab.arturbosch.detekt`) registers its Android tasks through
a variant API that AGP 9 no longer has, and only next to the Kotlin Android plugin, which
built-in Kotlin does not apply. The application module gets the plain `detekt` task and no
task with type resolution. Assemble the missing one from the variant API that exists:

```kotlin
val detektExtension = extensions.getByType<io.gitlab.arturbosch.detekt.extensions.DetektExtension>()

androidComponents {
    onVariants(selector().withName("debug")) { variant ->
        tasks.register<io.gitlab.arturbosch.detekt.Detekt>("detektDebug") {
            description = "Runs detekt with type resolution on the debug variant."
            setSource(detektExtension.source)
            classpath.setFrom(
                variant.compileClasspath,
                files(sdkComponents.bootClasspath),
                tasks.named<JavaCompile>("compileDebugJavaWithJavac").flatMap { it.destinationDirectory },
            )
            config.setFrom(detektExtension.config)
            buildUponDefaultConfig = detektExtension.buildUponDefaultConfig
            allRules = detektExtension.allRules
            reports {
                // The plain task writes detekt.<ext> into the same folder.
                listOf(xml, html, txt, sarif, md).forEach { report ->
                    report.outputLocation.set(detektExtension.reportsDir.resolve("$name.${report.type.extension}"))
                }
            }
        }
    }
}
```

It works with the configuration cache. The pre-release of the next detekt line (plugin
`dev.detekt`) lists support for built-in Kotlin in its release notes; that was read, not run.
Prefer the stable line until the next one is released, and move earlier only if type resolution
starts to report false findings.

## What this gate does not do

- **It does not compile iOS code.** ktlint and the plain detekt task read `iosMain`; no task in
  the list compiles it, and lint does not see it. After a change there, or in common code that
  iOS uses differently, run `./gradlew :composeApp:iosSimulatorArm64Test` on a Mac and report it
  separately (`kmp-ios-interop`).
- It does not run instrumented tests: `verifyOnDevice` in `SKILL.md` does, on a device.
