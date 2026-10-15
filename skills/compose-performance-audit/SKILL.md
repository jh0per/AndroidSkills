---
name: compose-performance-audit
description: Audit Compose and Compose Multiplatform UI code for rendering performance and fix only what a trace or measurement supports - phase deferral of state reads (lambdas, graphicsLayer, offset), backwards writes, remember keys and derivedStateOf misuse, stability and strong skipping without cargo-cult @Immutable, lazy layout keys/contentType/scope guards, effects and side-effect hygiene, allocation-free drawing with drawWithCache, Modifier.Node instead of composed, and recomposition counting with Layout Inspector and compiler reports. Use when a screen stutters, a list scrolls badly, a composable recomposes in a loop, or when reviewing UI code for performance. Do not use for startup time or ANRs (see app-startup-performance).
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Jetpack Compose
  - performance
  - recomposition
  - stability
  - strong skipping
  - derivedStateOf
  - lazy layouts
  - contentType
  - graphicsLayer
  - drawWithCache
  - Modifier.Node
  - Layout Inspector
  - compiler reports
---

# Compose performance audit

Audit, then fix. An audit lists findings with the rule, the file:line, and the evidence
(recomposition count, frame time, allocation) and proposes the fix; it changes nothing. A fix
PR changes one category at a time and shows the metric before and after
(`app-startup-performance` has the Macrobenchmark and report format).

## Prerequisites

- Measure on a release-like build (R8 on, non-debuggable). Debug builds recompose and allocate
  differently; Layout Inspector counts are from debug but still useful for **relative** findings.
- Strong skipping is on by default since Kotlin 2.0.20 / Compose compiler 2.0.20; check the
  project's Kotlin version before reasoning about stability.
- Compiler reports for the module under audit: `composeCompiler { reportsDestination = layout.buildDirectory.dir("compose_reports") }`
  (`gradle-build-setup`), then read `*-composables.txt` for `restartable skippable` and
  `*-classes.txt` for `unstable`.

## Audit workflow

1. Reproduce: name the gesture or state change that stutters and record a system trace or
   Layout Inspector recomposition counts for it. "Looks slow" is not a finding.
2. Scan **every** composable, modifier chain and lazy item model on the hot path against the
   categories below; do not stop at the first hit.
3. For each finding, write: category, location, evidence, fix, and the scope guard that says the
   fix applies (several rules apply only to lazy layouts or large data sets).
4. Fix in order of measured impact, not in file order; re-measure after each category.

## 1. State reads and phases

- **Defer reads** of fast-changing state (scroll offset, animation values, drag position) past
  composition: `Modifier.offset { IntOffset(x, 0) }`, `Modifier.graphicsLayer { alpha = a.value }`,
  `Modifier.drawBehind { }`, and lambda parameters (`progress: () -> Float`) into children.

```kotlin
// WRONG: every scroll pixel recomposes the whole header
Header(modifier = Modifier.offset(y = -scrollState.value.dp))
// RIGHT: read in layout phase only
Header(modifier = Modifier.offset { IntOffset(0, -scrollState.value) })
```

- **Backwards writes**: a state read in composition and written later in the same pass (or in
  layout/draw after being read) loops recomposition. Writes belong in event callbacks or effects.
- **`remember` keys**: every value the calculation captures is a key, or the remembered value
  goes stale; conversely do not `remember { mutableStateOf(x) }` only to assign it at the top of
  composition.
- **`derivedStateOf`** only when a fast-changing input maps to a slow-changing output
  (`listState.firstVisibleItemIndex > 0`). Not for `list.size`, not for simple getters, not for
  combining two already-slow states. Prefer a synchronous `derivedStateOf` over
  `snapshotFlow` + `produceState` for UI-only derivations.
- Repeated reads of the same `State` in a block: read once into a local.

## 2. Stability and skipping (the scope guard matters)

- Under strong skipping, flat `data class`es of `val` primitives/Strings are stable already and
  lambdas are memoised. **Do not** add `@Immutable`/`@Stable` or swap `List` for
  `ImmutableList` as a reflex; skipping is not free (every parameter is compared).
- Add `@Immutable` only when the compiler report says `unstable` **and** the composable is
  recomposing measurably because of it (Layout Inspector count rising on an unrelated change).
- Remove `@Immutable` from models with large nested collections that feed lazy layouts when the
  trace shows time in `equals`; leave every other annotation alone.
- Prefer making a composable cheap over forcing it to skip: move work out, split the composable
  so the changing part is small.

## 3. Lazy layouts

Rules here apply to `LazyColumn`/`LazyRow`/grids/`Pager` only; never flag a `Column` with a
`forEach` of ten items (and conversely, use a `Column` for bounded small lists).

- `key = { it.id }` with a primitive key and `contentType` for every item type; without keys,
  insertions recompose and re-animate the whole visible range.
- No `list.indexOf(item)` inside items (`itemsIndexed`), no `CompositionLocal` lookups per item
  that the parent can pass down, no `collectAsStateWithLifecycle()` per item (collect once above).
- Selection state as `Set<Id>` in one `MutableState`, not `mutableStateListOf`, so each item does
  one `contains`.
- Impressions and analytics: not in `LaunchedEffect(Unit)` of an item (prefetch composes items
  before they are visible); use `Modifier.onVisibilityChanged` (Compose 1.9+) or viewport checks.
- `sharedElement`/`sharedBounds` on list items only when visible.
- `contentPadding` instead of outer padding; `Modifier.animateItem()` only on lists that mutate.

## 4. Effects and threading

- Nothing with side effects runs in a composable body; `SideEffect` for sync publication,
  `LaunchedEffect`/`DisposableEffect` for the rest. Never a `LaunchedEffect` for synchronous
  work, never a `DisposableEffect` with an empty `onDispose`.
- `rememberUpdatedState` for callbacks captured by long-running effects; `Dispatchers.IO` via
  `withContext` inside effects for blocking work; no `Handler.postDelayed` (use `delay`).
- Listeners and receivers registered once per screen in a `DisposableEffect`, not per item.
- `collectAsStateWithLifecycle()` for flows that cost something while backgrounded;
  `collectAsState()` for cheap in-memory `StateFlow`s and in common KMP code.

## 5. Layout and drawing

- `onGloballyPositioned` is a recomposition trigger on every layout pass; use `onPlaced`,
  `onLayoutRectChanged`, or a custom `Layout` that positions both the anchor and the floating
  content. `BoxWithConstraints`/`SubcomposeLayout` out of hot paths and lazy items.
- Decorative drawing: `Modifier.drawBehind`/`drawWithCache` on the existing node, not a
  `Canvas` or `Box` wrapper; cache `Path`, `Brush`, `Paint` in `drawWithCache`; `Path.rewind()`
  over `reset()` per frame; `RuntimeShader` remembered, uniforms set in draw.
- Images: Coil `AsyncImage` with a size, not `Image(bitmap)` decoded at full resolution
  (`media-storage`); downsample thumbnails.
- `Modifier.composed { }` → `ModifierNodeElement` + `Modifier.Node` for any modifier used in a
  list or animated; `requireLayoutCoordinates()` on demand inside the node.

## 6. Verify

- Layout Inspector recomposition counts before/after for the reproduced gesture; the count for
  unchanged siblings should be 0.
- `FrameTimingMetric` Macrobenchmark for the scroll or animation; P90 `frameDurationCpuMs` is
  the number in the PR.
- A guard test for conventions that regress silently: lazy `items` calls without `key` in the
  feature modules (`architecture-guard-tests`), `onGloballyPositioned` outside an allow-list.

## Report format (audit mode)

```markdown
## Compose performance audit: <screen>
Repro: <gesture>; device/build: <…>; baseline: <frame P90 / recomposition counts>
| # | Category | Location | Evidence | Fix | Scope guard |
Not flagged on purpose: <e.g. @Immutable left on small models, Column with 6 children>
```

## Checklist

- [ ] Every finding has evidence (trace, count or allocation), not only a pattern match.
- [ ] Fast-changing reads are deferred to layout/draw; no backwards writes.
- [ ] No reflexive `@Immutable`/`ImmutableList`; stability changes are backed by the compiler report.
- [ ] Lazy items have keys and contentType; no per-item collection, locals lookup or impression effects.
- [ ] Drawing allocations cached; `composed` modifiers migrated where hot.
- [ ] Before/after frame times in the PR.
