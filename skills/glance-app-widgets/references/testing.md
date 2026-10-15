# Testing Glance widgets

## Unit tests (glance-appwidget-testing)

Runs the composable through Glance's translator on the JVM (Robolectric for a `Context` when the
content reads resources). Test the content composable, not `provideGlance`: pass data in as
parameters so the test controls it.

```kotlin
@RunWith(RobolectricTestRunner::class)
class AppTasksWidgetContentTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()

    @Test fun smallSize_showsOnlyNextTask() = runGlanceAppWidgetUnitTest {
        setContext(context)
        setAppWidgetSize(DpSize(110.dp, 110.dp))
        provideComposable { AppTasksContent(listOf(task("Buy milk"), task("Call Ana"))) }

        onNode(hasText("Buy milk")).assertExists()
        onNode(hasText("Call Ana")).assertDoesNotExist()
    }

    @Test fun emptyList_showsEmptyState() = runGlanceAppWidgetUnitTest {
        setContext(context)
        setAppWidgetSize(DpSize(250.dp, 250.dp))
        provideComposable { AppTasksContent(emptyList()) }
        onNode(hasText("No tasks")).assertExists()
    }

    @Test fun rowAndCheckbox_areClickable() = runGlanceAppWidgetUnitTest {
        setContext(context)
        setAppWidgetSize(DpSize(250.dp, 250.dp))
        provideComposable { AppTasksContent(listOf(task("Buy milk", id = 7))) }
        onAllNodes(hasClickAction()).assertCountEquals(2)   // row + checkbox
    }
}
```

- `setState(prefs)` seeds `currentState<Preferences>()` when the content reads Glance state.
- Matchers live in `androidx.glance.testing.unit` / `androidx.glance.appwidget.testing.unit`:
  `hasText`, `hasContentDescription`, `hasClickAction`, and action-specific matchers such as
  `hasStartActivityClickAction` and `hasRunCallbackClickAction` (check the names against the
  version you use).
- Fail first: change a breakpoint or remove the empty-state branch and confirm a test goes red.
- `ActionCallback`s are plain classes: test `onAction` with a fake repository and assert the
  write; the `update()` call is verified on the launcher.

## Launcher verification

1. Install, long-press home, add the widget from the picker; the picker preview must match
   the real widget's look in both themes.
2. Resize through each breakpoint; screenshot each. Rotate; check a tablet or a large-screen
   emulator for cell sizes.
3. Dark mode on/off and a wallpaper change: dynamic colours must update without reopening the app.
4. `adb shell am force-stop com.example.app`, then tap each target: the widget must still respond.
5. Change data in the app, go home: the widget reflects it. Airplane mode: cached data shows.
6. `adb shell dumpsys appwidget` lists instances and providers; `adb logcat -s GlanceAppWidget`
   shows composition errors (for example too many children) that otherwise appear only as the
   generic error layout.
