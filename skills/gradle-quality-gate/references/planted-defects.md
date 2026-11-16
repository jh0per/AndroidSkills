# Seeing each part of the gate fail

A part of the gate is trusted after it has been seen failing for the reason it exists
(`verification-discipline`). Plant the defects below, run `./gradlew verify --continue`, and
compare the failed tasks with the right-hand column. Then remove every defect, search the tree
for the marker you used in their names, and run the gate green again.

Plant defects that still compile. A compile error stops the tasks that depend on the
compilation, and their silence then proves nothing. The module names are those of the AGP 9
layout ([agp9-split.md](agp9-split.md)); with one module read `:app` for both.

| Part | Defect | Must fail |
|---|---|---|
| Unit tests | `assertEquals(1, 2)` in a new test in `commonTest` | `:composeApp:testAndroidHostTest` |
| ktlint | `val  x = 1` (two spaces), once in `commonMain`, `iosMain`, the application module and the root `build.gradle.kts` | the ktlint task of each of the four |
| detekt, plain | `try { … } catch (e: Exception) { }` in `commonMain`, `iosMain` and the application module | `:composeApp:detekt`, `:androidApp:detekt` |
| detekt, type resolution | `fun f(s: String?) = s!!.length`, and `CoroutineScope(Dispatchers.Default)` in a function | `:composeApp:detektAndroidMain`, `:androidApp:detektDebug`, and **not** the plain tasks |
| Lint, error | `view.setRenderEffect(null)` with `minSdk` below 31, in the application module and in the library's `androidMain`; `val s = mutableStateOf(1)` in a composable in `commonMain` | `:androidApp:lintDebug`, with all three in its report |
| Lint, warning (with `warningsAsErrors`) | `Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP` | `:androidApp:lintDebug` |
| Debug build | a file `src/androidMain/resources/META-INF/<name>` in the library whose path equals a file inside a dependency's jar (list them with `unzip -l` on the debug APK) | `:androidApp:mergeDebugJavaResource`, and no other task of the gate |
| Instrumented sources | a call to a function that does not exist, in the instrumented source set (a compile error on purpose: nothing else depends on that compilation) | the task that assembles the instrumented tests |
| Manifest check | the forbidden or unlisted permission in the source manifest; for an exact list also an extra line in the list | `:androidApp:check<Variant>…`, both times |

## Reading the result

- Open each report, do not count failed tasks. The type-resolution row is proven by a finding
  that is in the report of the second detekt task and absent from the report of the first.
- A row whose task stays green is a finding about the gate. Lint that stays green on the
  library row means the library has no lint model; detekt that stays green on `commonMain` in
  the type-resolution row means the task reads only `androidMain`.
- The ktlint report folder also holds the reports of the format tasks. Read the ones of the
  `…Check` tasks.
- The debug-build row is the reason `assembleDebug` is in the gate: everything else stays green
  while the application cannot be packaged.
