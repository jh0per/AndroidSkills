---
name: architecture-guard-tests
description: Write source-level guard tests that keep an Android/KMP codebase from drifting - exactly one owner for a behaviour (one list-state owner, one snackbar host, one back-handler setup), banned APIs and patterns, colours and strings only where allowed, ratchets that only go down, on-disk and wire contracts, manifest and build invariants - each paired with a control proving the matcher can fail. Use when a convention keeps being broken, after fixing a bug that a convention would have prevented, or when consolidating duplicated code.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - architecture tests
  - guard tests
  - banned APIs
  - ratchet
  - conventions
  - static checks
---

# Architecture guard tests

Running tests check behaviour. Some defects are about **how many owners** a behaviour has, or about
a pattern appearing at all, which no runtime test can count. Guard tests read the source tree.

## When to write one

- A convention was broken twice (two pull-to-refresh implementations, a second snackbar host).
- A bug's root cause was a pattern (`\'` in Compose resources, a trailing-lambda overload that
  installs no back handler, `Dispatchers.Unconfined` inside `runTest`).
- A consolidation just happened and must stay consolidated.

Prefer a lint rule (detekt custom rule, Android Lint check) when the pattern is syntactic and the
team already maintains rules; use a small script/test when it spans files, resources or manifests.

## Shapes

| Guard | Asserts |
|---|---|
| One owner | exactly one file contains `PullToRefreshBox(`, one `SnackbarHost(`, one load-more derivation |
| Banned API | no `SubcomposeAsyncImage`, no `Resources.getSystem()`, no `GlobalScope` in production sources |
| Required form | navigator created with `enableBackHandler = true`; strict dispatcher owner enabled |
| Allowed places | raw `Color(0x…)` only in listed files, each with a reason ("theme", "user content", "over imagery") |
| Named colours | every `Text(` in state views passes `color =` |
| Ratchet | per-file count of hard-coded UI strings ≤ baseline; the baseline file may only decrease |
| One word | a product term is spelled one way across clients (string keys, UI text, docs) |
| Contracts | DataStore file names/keys, DB file name, notification channel id equal pinned literals |
| Build invariants | app and library modules agree on compileSdk/minSdk; libraries hold no applicationId/signing; no signing values assigned in tracked files |
| Wire | every key the server requires is always written by the client DTO (derived from the server schema) |

## Implementation (Kotlin unit test over sources)

```kotlin
class SingleOwnerGuardTest {
    private val root = File("src")                                   // module-relative in Gradle tests
    private fun kotlinFiles() = root.walkTopDown().filter { it.extension == "kt" && "/build/" !in it.path }

    /** Strip comments first: explanations often quote the forbidden form. */
    private fun code(file: File) = file.readText()
        .replace(Regex("/\\*.*?\\*/", RegexOption.DOT_MATCHES_ALL), "")
        .replace(Regex("//[^\n]*"), "")

    private fun owners(pattern: Regex) = kotlinFiles().filter { pattern.containsMatchIn(code(it)) }.map { it.name }.toList()

    @Test fun `pull to refresh has one owner`() {
        assertEquals(listOf("AppListSurface.kt"), owners(Regex("""\bPullToRefreshBox\s*\(""")))
    }

    @Test fun `control - the matcher finds a call`() {                // proves the regex can match at all
        assertTrue(Regex("""\bPullToRefreshBox\s*\(""").containsMatchIn("PullToRefreshBox (isRefreshing = x)"))
    }
}
```

Ratchet:

```kotlin
@Test fun `hard-coded strings only go down`() {
    val baseline = File("guards/hardcoded-strings-baseline.txt").readLines().associate { it.substringBefore('=') to it.substringAfter('=').toInt() }
    val current = uiFiles().associate { it.path to Regex("""Text\(\s*"[^"]+"""").findAll(code(it)).count() }
    val worse = current.filter { (path, n) -> n > (baseline[path] ?: 0) }
    assertTrue("New hard-coded strings: $worse (move them to resources)", worse.isEmpty())
}
```

When counts drop, update the baseline in the same change.

## Rules

- **Every guard has a control**: a test (or a fixture) proving the matcher fires on the forbidden
  form. A regex that never matches passes forever (`verification-discipline`).
- Strip comments and string literals before matching where relevant.
- Failure messages say what to do ("use AppListSurface instead"), not only what was found.
- Keep guards fast and in the normal unit-test gate, so they run before every push.
- Delete a guard when the thing it protects is removed; stale guards teach people to ignore them.
- Guards complement review; they check that a choice was made (a colour named), not that it is right.
