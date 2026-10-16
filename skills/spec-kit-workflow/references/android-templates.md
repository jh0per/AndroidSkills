# Android template overrides

Copy `.specify/templates/plan-template.md` and `tasks-template.md` into
`.specify/templates/overrides/` and replace the sections below. Keep every other section and every
placeholder the commands rely on (for example the `__SPECKIT_COMMAND_*__` tokens) untouched, so
upgrades stay mergeable.

## plan-template.md: Technical Context defaults

```markdown
**Language/Version**: Kotlin <2.x>, JDK toolchain <17|21>, AGP <version>
**Primary Dependencies**: Compose (Multiplatform), AndroidX ViewModel, Koin, Ktor, Room KMP,
DataStore, Navigation Compose <or Navigation 3> (from gradle/libs.versions.toml; new ones need research.md entry)
**Storage**: Room KMP / DataStore / files via path provider / N/A
**Testing**: kotlin.test + kotlinx-coroutines-test + Turbine in commonTest; Ktor MockEngine;
Robolectric for Android-only units; Compose UI tests (runComposeUiTest / createComposeRule);
instrumented tests only for platform APIs
**Target Platform**: Android minSdk <N> / targetSdk <N>; iOS <N>+ (KMP) or N/A
**Project Type**: mobile-app (Gradle multi-module)
**Performance Goals**: cold start to first content < <N> ms on <device class>; no frame > 16 ms in list scroll
**Constraints**: offline-capable <yes/no>; edge-to-edge; 200% font scale; APK/AAB size budget <N> MB
**Scale/Scope**: <screens touched>, <modules touched>
```

## plan-template.md: Source Code section

Replace the three options with one Gradle layout and keep only the modules this feature touches:

```text
settings.gradle.kts                     # include(":feature:orders")
build-logic/                            # convention plugins; no per-module build logic
core/
├── data/src/commonMain/kotlin/com/example/app/data/          # repositories, Room, DataStore
├── data/src/commonTest/kotlin/...                            # repository tests with fakes
├── network/src/commonMain/kotlin/com/example/app/network/    # Ktor client, DTOs
└── testing/src/commonMain/kotlin/com/example/app/testing/    # shared fakes, MainDispatcherRule
feature/orders/
├── src/commonMain/kotlin/com/example/app/orders/   # OrdersViewModel, OrdersState/Intent/Effect, OrdersUi
├── src/commonTest/kotlin/com/example/app/orders/   # ViewModel tests, runComposeUiTest Ui tests
├── src/androidMain/kotlin/...                      # platform seams, previews
└── src/androidInstrumentedTest/kotlin/...          # only what needs a device
app/src/main/kotlin/com/example/app/                # composition root, navigation graph
iosApp/                                             # Swift entry point (KMP)
```

Android-only projects use `src/main`, `src/test`, `src/androidTest` instead of the KMP source sets.

## tasks-template.md: Tests and Path Conventions

Replace the "Tests are OPTIONAL" line and the Path Conventions block:

```markdown
**Tests**: REQUIRED by the constitution (Test-First). Inside each user story, test tasks come first,
cite the scenario or FR they prove, and must be seen failing before the implementation task starts.

## Path Conventions
- Gradle modules: `feature/<name>/`, `core/<name>/`, `app/`
- KMP source sets: `src/commonMain`, `src/commonTest`, `src/androidMain`, `src/androidUnitTest`,
  `src/androidInstrumentedTest`, `src/iosMain`
- Android-only modules: `src/main`, `src/test`, `src/androidTest`
- Paths must be full from the repo root and include the package directories
```

Add to the Polish phase:

```markdown
- [ ] TXXX Run `./gradlew verify` and the iOS tests (`:feature:<name>:iosSimulatorArm64Test`) or record NOT_RUN
- [ ] TXXX Device check: rotation, process death (`adb shell am kill`), offline, 200% font, TalkBack
- [ ] TXXX Update spec.md/plan.md for every deviation found during implementation
```

## Foundational phase examples for Android

```markdown
- [ ] T004 Register :feature:<name> in settings.gradle.kts and apply the feature convention plugin
- [ ] T005 [P] Domain model and repository interface in core/data/src/commonMain/...
- [ ] T006 [P] Fake repository recording calls in core/testing/src/commonMain/...
- [ ] T007 Room entity + DAO + migration test (if storage changes) in core/data/...
- [ ] T008 Route key and navigation entry in app/... (no screen content yet)
- [ ] T009 Koin module for the feature and a DI graph test that resolves it
```
