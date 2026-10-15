---
name: glance-app-widgets
description: Build home-screen app widgets with Jetpack Glance - GlanceAppWidget and GlanceAppWidgetReceiver, the appwidget-provider XML (targetCellWidth/Height, minResize, resizeMode, previewLayout and generated previews, updatePeriodMillis limits), SizeMode Single/Responsive/Exact and canonical layouts, GlanceTheme with dynamic colour, loading data in provideGlance, refresh with WorkManager and update()/updateAll(), per-widget state with PreferencesGlanceStateDefinition, actions (actionStartActivity with a deep link, actionRunCallback, ActionParameters), RemoteViews limits (no arbitrary Compose, child counts, bitmap memory), configuration activities, accessibility, and tests with runGlanceAppWidgetUnitTest plus a launcher check. Use when adding or fixing a home-screen widget, its picker preview, refresh schedule or click handling. Do not use for in-app Compose UI (see compose-ui-practices), background job design (see long-running-jobs) or notifications (see push-notifications).
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Glance
  - app widget
  - home screen widget
  - GlanceAppWidget
  - GlanceAppWidgetReceiver
  - appwidget-provider
  - SizeMode
  - GlanceTheme
  - RemoteViews
  - actionRunCallback
  - widget preview
  - runGlanceAppWidgetUnitTest
---

# Glance app widgets

A widget is a **RemoteViews snapshot of data the app already has**, not a second app: it renders
from local storage, never waits on the network, and every tap either opens the app at a
destination or runs a short callback that writes state and calls `update()`. Glance code looks
like Compose but is a different API that compiles to RemoteViews; Compose-only APIs do not work
inside it. Neighbours: `long-running-jobs` and WorkManager scheduling details, `local-persistence`
(the repository the widget reads), `design-system-module` / `material3-guidelines` (app theme),
`push-notifications` (a push that should also refresh the widget calls `updateAll`).

## Prerequisites

- Dependencies: `androidx.glance:glance-appwidget` and `androidx.glance:glance-material3`; for
  IDE previews `glance-preview` + `glance-appwidget-preview`; for unit tests
  `glance-appwidget-testing` (test scope). Use one version for all Glance artifacts; 1.1.x is the
  floor, check the current stable release before pinning (generated picker previews need 1.2+).
- Platform facts: `targetCellWidth/Height`, `maxResizeWidth/Height`, `previewLayout`,
  `description`, `widgetFeatures` and rounded corners exist from API 31; below that the launcher
  uses `minWidth/minHeight` and `previewImage`. Generated previews (`setWidgetPreview`) need
  API 35 and are rate-limited by the system. `updatePeriodMillis` below 30 minutes is clamped to
  30 minutes; 0 disables it.
- RemoteViews budget: `Box`/`Row`/`Column` take at most 10 children; all bitmaps in one widget
  update share a memory cap of about 1.5 x screen pixels x 4 bytes. Exceeding either fails the
  whole widget into the error layout.

## Step 1: inventory

1. Find existing widgets: `<receiver>` entries with `android.appwidget.provider` metadata in the
   merged manifest, classes extending `GlanceAppWidgetReceiver` or `AppWidgetProvider`.
2. For each widget write down: data source (repository / DataStore / Room), refresh trigger
   (app event, push, periodic worker), size range in cells, click targets and where each goes.
3. Decide the layout class from the canonical set before writing code
   (`references/canonical-layouts.md`): text, list, grid, image plus text, toolbar. A widget
   that needs a chart, gestures, text input or animation is the wrong product; show a snapshot
   image or a summary and deep link into the app.

## Step 2: declare the widget

Receiver, provider XML, widget class. The full XML attribute table, sizing rules and the
configuration activity are in `references/widget-provider-xml.md`.

```kotlin
class AppTasksWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = AppTasksWidget()
    override fun onEnabled(context: Context) = AppWidgetRefreshWorker.schedule(context)   // first instance
    override fun onDisabled(context: Context) = AppWidgetRefreshWorker.cancel(context)    // last removed
}
```

```xml
<receiver android:name=".widget.AppTasksWidgetReceiver" android:exported="true">
    <intent-filter><action android:name="android.appwidget.action.APPWIDGET_UPDATE" /></intent-filter>
    <meta-data android:name="android.appwidget.provider" android:resource="@xml/app_tasks_widget_info" />
</receiver>
```

- `exported="true"` is required: the launcher process sends the update broadcast. The receiver
  holds no other logic; work goes to the widget class or a worker.
- `android:initialLayout="@layout/glance_default_loading_layout"` (shipped by Glance) and
  `android:updatePeriodMillis="0"` unless a 30-minute floor is genuinely enough.

## Step 3: sizes and layouts

| SizeMode | Use when | Cost |
|---|---|---|
| `SizeMode.Single` | one fixed layout that only stretches (a 2x1 shortcut) | cheapest |
| `SizeMode.Responsive(setOf(...))` | 2-4 distinct layouts at known breakpoints; the launcher swaps without waking the app | each size composed and held by the host |
| `SizeMode.Exact` | layout depends on precise size (image crops, grid column count) | recomposes on every resize |

Default to `Responsive` with breakpoints that match the canonical layouts (for example
`DpSize(110.dp, 110.dp)`, `DpSize(250.dp, 110.dp)`, `DpSize(250.dp, 250.dp)`); read
`LocalSize.current` in the content and branch on it.

```kotlin
// RIGHT: branch on size, every branch fits the RemoteViews budget.
@Composable
private fun AppTasksContent(tasks: List<AppTask>) {
    val size = LocalSize.current
    Scaffold(titleBar = { TitleBar(startIcon = ImageProvider(R.drawable.ic_app), title = "Tasks") }) {
        when {
            tasks.isEmpty() -> EmptyState()
            size.width < 250.dp -> NextTask(tasks.first())
            else -> LazyColumn { items(tasks, itemId = { it.id }) { TaskRow(it) } }   // id: Long
        }
    }
}
```

```kotlin
// WRONG: Compose UI imports compile in a Glance file and crash or render nothing at runtime.
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
Text("Tasks", modifier = Modifier.padding(8.dp))
// RIGHT: androidx.glance.text.Text, GlanceModifier.padding(8.dp)
```

- Only `androidx.glance.*` composables and `GlanceModifier` render. Compose runtime APIs
  (`remember`, `collectAsState`, `LaunchedEffect`, `key`) are fine; `Modifier`, Material
  components, `Canvas`, `LazyColumn` from foundation, `AsyncImage` and custom layouts are not.
- Lists: `androidx.glance.appwidget.lazy.LazyColumn` / `LazyVerticalGrid` with a stable `itemId`.
  Never a `Column` of N rows (10-children limit and no scrolling).
- Root: `GlanceModifier.fillMaxSize().appWidgetBackground().background(GlanceTheme.colors.widgetBackground)`
  and `.cornerRadius(android.R.dimen.system_app_widget_background_radius)` on API 31+; or the
  Glance `Scaffold`, which does this for you.

## Step 4: theme

```kotlin
// RIGHT: system dynamic colour on 12+, the app palette as fallback, light and dark.
provideContent {
    GlanceTheme(colors = if (Build.VERSION.SDK_INT >= 31) GlanceTheme.colors else AppWidgetColors) {
        AppTasksContent(tasks)
    }
}
// AppWidgetColors = ColorProviders(light = AppLightColorScheme, dark = AppDarkColorScheme) (glance-material3)
```

```kotlin
// WRONG: fixed colours ignore dark mode and the wallpaper palette; text vanishes on one of them.
Text("Tasks", style = TextStyle(color = ColorProvider(Color.Black)))
// RIGHT: TextStyle(color = GlanceTheme.colors.onSurface)
```

Reuse the app's `ColorScheme` objects from the design system module; do not invent widget-only
colours. Fonts: only system families (`FontFamily.SansSerif`, `FontFamily("sans-serif-medium")`).

## Step 5: data, state and refresh

`provideGlance` runs in a short-lived session (a worker): read local data, then call
`provideContent`. No network, no unbounded waits; slow work in it shows the loading layout
forever or times out.

```kotlin
// RIGHT: read the local cache; a worker refreshes the cache and calls updateAll.
override suspend fun provideGlance(context: Context, id: GlanceId) {
    val repo = AppWidgetEntryPoint.tasksRepository(context)
    val initial = repo.cachedTasks()                      // Room/DataStore read, milliseconds
    provideContent {
        val tasks by repo.observeTasks().collectAsState(initial)
        GlanceTheme { AppTasksContent(tasks) }
    }
}
```

```kotlin
// WRONG: network in provideGlance; offline or slow means a stuck widget.
override suspend fun provideGlance(context: Context, id: GlanceId) {
    val tasks = api.fetchTasks()
    provideContent { AppTasksContent(tasks) }
}
```

- Refresh: the app's repository writes, then `AppTasksWidget().updateAll(context)`. A
  `PeriodicWorkRequest` (minimum 15 minutes, unique name, network constraint) refreshes the
  cache when nothing else does; scheduled in `onEnabled`, cancelled in `onDisabled`
  (`long-running-jobs` for worker rules). Never a `while(true) { delay() }` in the session.
- Per-instance state (which list a configured widget shows, a toggled filter):
  `override val stateDefinition = PreferencesGlanceStateDefinition`, read with
  `currentState<Preferences>()`, write with `updateAppWidgetState(context, glanceId) { it[key] = v }`
  **followed by** `AppTasksWidget().update(context, glanceId)`. Without the `update` call nothing
  redraws. App-wide data stays in the app's repository, not in widget state.
- Clean up per-instance state and files in the receiver's `onDeleted`.

## Step 6: actions

```kotlin
private val TaskIdKey = ActionParameters.Key<String>("task_id")

// Open the app at a destination: explicit intent with a deep-link URI the nav graph already handles.
GlanceModifier.clickable(actionStartActivity(
    Intent(Intent.ACTION_VIEW, "app://example.com/tasks/${task.id}".toUri(), context, MainActivity::class.java)
))

// Short work without opening the app: callback writes, then updates.
CheckBox(checked = task.done, onCheckedChange = actionRunCallback<ToggleTaskAction>(actionParametersOf(TaskIdKey to task.id.toString())))

class ToggleTaskAction : ActionCallback {
    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) {
        val id = parameters[TaskIdKey] ?: return
        AppWidgetEntryPoint.tasksRepository(context).toggle(id)    // local write, fast
        AppTasksWidget().update(context, glanceId)
    }
}
```

- Deep links from a widget go through the same validation and back-stack rules as any other
  entry (`navigation3-compose`, `android-app-security`); pass ids, never payloads.
- Lambda `onClick = { ... }` only runs while the session is alive; use it for trivial UI state.
  Anything that writes data uses `actionRunCallback`; anything long (upload, sync) enqueues a
  worker from the callback.
- Do not wrap `PendingIntent`s yourself; Glance builds them immutable.

## Step 7: images, accessibility, previews

- Images: `ImageProvider(R.drawable.x)` for icons; bitmaps decoded at the rendered size (Coil or
  `BitmapFactory` with `inSampleSize`), never full-resolution photos. Sum bitmap bytes against the
  cap above when a list or grid shows several.
- `Image(contentDescription = ...)` is required for meaning-bearing images, `null` for decoration;
  icon-only buttons (`SquareIconButton`, `CircleIconButton`) need `contentDescription`. Tap targets
  at least 48dp. Text sizes in `sp` via `TextStyle(fontSize = ...)`, verified at the largest font scale.
- IDE previews: `@OptIn(ExperimentalGlancePreviewApi::class) @Preview(widthDp = ..., heightDp = ...)`
  on the content composable at each breakpoint. Picker previews: `previewLayout` (XML layout) on
  API 31+, `previewImage` fallback; generated previews via `providePreview` in the widget and
  `GlanceAppWidgetManager.setWidgetPreviews(...)` at a quiet moment (after login, on app update),
  never on every data change.

## Scope guards

- `widgetCategory="keyguard"` (lock screen / hub placement) is offered only by some devices and
  OS versions; add it only when the product asks and you test it there. Wear OS tiles are not
  covered by this skill.
- Views-based `AppWidgetProvider` widgets: leave them unless the task is a migration; do not mix
  RemoteViews code into a Glance widget.

## Verification (fail first)

1. Unit test the content with `runGlanceAppWidgetUnitTest` (details in `references/testing.md`):
   set size and state, `provideComposable { ... }`, assert text and click actions. Make it fail
   once (wrong breakpoint, missing empty state) before trusting it (`verification-discipline`).
2. Launcher check on a device or emulator: add the widget from the picker, resize through every
   breakpoint, toggle dark mode and wallpaper (dynamic colour), tap every target, kill the app
   process and confirm the widget still renders and taps still work. `adb shell dumpsys appwidget`
   shows instances and their provider.
3. Data path: change data in the app and confirm the widget updates without opening it; turn on
   airplane mode and confirm the widget shows cached data, not the loading layout.
4. Remove the last instance and check `onDisabled` cancelled the periodic worker
   (`adb shell dumpsys jobscheduler | grep <package>`).

## Checklist

- [ ] Receiver exported with `APPWIDGET_UPDATE` and provider metadata; XML sets target cells,
      min sizes, `resizeMode`, `previewLayout`/`previewImage`, `description`.
- [ ] `updatePeriodMillis="0"` or a justified 30+ minutes; periodic refresh is a unique worker
      tied to `onEnabled`/`onDisabled`.
- [ ] `provideGlance` reads only local data; no network or long work inside the session.
- [ ] Only `androidx.glance.*` composables and `GlanceModifier`; lists are lazy with `itemId`;
      no container exceeds 10 children; bitmaps sized to the view.
- [ ] Colours come from `GlanceTheme.colors`; dynamic colour on 12+, app palette fallback.
- [ ] Every state write is followed by `update()`/`updateAll()`; `onDeleted` cleans state.
- [ ] Taps open a validated deep link or run an `ActionCallback`; no custom `PendingIntent`.
- [ ] Content descriptions on images and icon buttons; 48dp targets; large font checked.
- [ ] Unit tests per breakpoint and empty state; launcher check across sizes, themes, process death.
