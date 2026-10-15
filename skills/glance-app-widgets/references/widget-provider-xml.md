# appwidget-provider XML, sizing and configuration

## Full provider file

```xml
<!-- res/xml/app_tasks_widget_info.xml -->
<appwidget-provider xmlns:android="http://schemas.android.com/apk/res/android"
    android:description="@string/app_tasks_widget_description"
    android:initialLayout="@layout/glance_default_loading_layout"
    android:previewLayout="@layout/app_tasks_widget_preview"
    android:previewImage="@drawable/app_tasks_widget_preview"
    android:targetCellWidth="3"
    android:targetCellHeight="2"
    android:minWidth="@dimen/app_tasks_widget_min_width"
    android:minHeight="@dimen/app_tasks_widget_min_height"
    android:minResizeWidth="@dimen/app_tasks_widget_min_resize_width"
    android:minResizeHeight="@dimen/app_tasks_widget_min_resize_height"
    android:maxResizeWidth="@dimen/app_tasks_widget_max_resize_width"
    android:maxResizeHeight="@dimen/app_tasks_widget_max_resize_height"
    android:resizeMode="horizontal|vertical"
    android:updatePeriodMillis="0"
    android:widgetCategory="home_screen"
    android:widgetFeatures="reconfigurable|configuration_optional"
    android:configure="com.example.app.widget.AppTasksWidgetConfigureActivity" />
```

| Attribute | API | Rule |
|---|---|---|
| `targetCellWidth/Height` | 31+ | Default size in grid cells; the main sizing input on modern launchers. |
| `minWidth/minHeight` | all | Fallback default size for older launchers; keep it consistent with the target cells. Put values in `dimens.xml`. |
| `minResizeWidth/Height` | all | Smallest size where the smallest layout is still readable. Without it the widget cannot shrink below the default. |
| `maxResizeWidth/Height` | 31+ | Cap only when a larger layout would be empty space; lists and grids usually leave it open. |
| `resizeMode` | all | `horizontal|vertical` unless a layout truly cannot change on one axis. |
| `previewLayout` | 31+ | Scalable XML preview that follows theme and dynamic colour; preferred over a static image. |
| `previewImage` | all | PNG/drawable fallback for API < 31. |
| `description` | 31+ | One line shown in the picker. |
| `updatePeriodMillis` | all | Clamped to >= 30 min; wakes the device; prefer `0` + worker/app-driven updates. |
| `widgetFeatures` | 31+ | `reconfigurable` lets the user reopen the configure activity; `configuration_optional` skips it on add and uses defaults. |
| `initialLayout` | all | Glance ships `glance_default_loading_layout`. |

Cell-to-dp rule of thumb for `min*` values on phones: n cells is about `73n - 16` dp wide
and `118n - 16` dp tall in portrait; check on a tablet too, cells are larger there.

## Breakpoints for SizeMode.Responsive

Pick sizes the layout actually changes at, not every cell combination. Typical set:

| Breakpoint | Layout |
|---|---|
| ~110 x 110 dp (2x2 small phone) | single value or next item, icon action |
| ~250 x 110 dp (4x1 / 3x2) | title bar + one or two rows, or text beside image |
| ~250 x 250 dp (4x3+) | full list or grid with title bar |

Preview each breakpoint with `@Preview(widthDp, heightDp)` and test it (`testing.md`).

## Configuration activity

Use only when the widget is meaningless without a choice (which account, which list). With
`configuration_optional`, ship sensible defaults and let the user reconfigure later.

```kotlin
class AppTasksWidgetConfigureActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val appWidgetId = intent?.extras?.getInt(AppWidgetManager.EXTRA_APPWIDGET_ID,
            AppWidgetManager.INVALID_APPWIDGET_ID) ?: AppWidgetManager.INVALID_APPWIDGET_ID
        // Back press or crash before confirming must cancel the add.
        setResult(RESULT_CANCELED, Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId))
        if (appWidgetId == AppWidgetManager.INVALID_APPWIDGET_ID) { finish(); return }

        enableEdgeToEdge()
        setContent { AppTheme { ListPicker(onPicked = { listId -> confirm(appWidgetId, listId) }) } }
    }

    private fun confirm(appWidgetId: Int, listId: Long) = lifecycleScope.launch {
        val glanceId = GlanceAppWidgetManager(this@AppTasksWidgetConfigureActivity).getGlanceIdBy(appWidgetId)
        updateAppWidgetState(this@AppTasksWidgetConfigureActivity, glanceId) { it[ListIdKey] = listId }
        AppTasksWidget().update(this@AppTasksWidgetConfigureActivity, glanceId)
        setResult(RESULT_OK, Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId))
        finish()
    }
}
```

```xml
<activity android:name=".widget.AppTasksWidgetConfigureActivity" android:exported="true">
    <intent-filter><action android:name="android.appwidget.action.APPWIDGET_CONFIGURE" /></intent-filter>
</activity>
```

Common mistakes:

- Returning `RESULT_OK` without the `EXTRA_APPWIDGET_ID` extra, or never setting
  `RESULT_CANCELED` first: the launcher keeps a ghost widget.
- Saving state but not calling `update()`: the widget shows defaults until the next refresh.
- Treating the configure activity as trusted input: it is exported; validate the widget id
  belongs to this app's provider (`AppWidgetManager.getAppWidgetInfo(id)?.provider`).
