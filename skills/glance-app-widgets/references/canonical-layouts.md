# Canonical widget layouts

Pick one per widget; mixing patterns in one widget is how layouts break the RemoteViews budget.
All examples assume `GlanceTheme` and `SizeMode.Responsive` breakpoints from
`widget-provider-xml.md`.

| Layout | Content | Small (2x2) | Large (4x3+) |
|---|---|---|---|
| Text | one headline value, quote, status | value + label | value + secondary line + action |
| List | tasks, messages, feed rows | first item + count | `LazyColumn` with title bar and add action |
| Grid | photos, shortcuts, devices | 2x2 tiles | `LazyVerticalGrid(GridCells.Adaptive(...))` |
| Image plus text | article, recipe, product | image with scrim + title | image beside title and body |
| Toolbar | search entry + quick actions | one icon button | search field look-alike + 3-4 icon buttons |

## Text

```kotlin
@Composable
fun AppStatusContent(title: String, value: String) {
    Column(
        GlanceModifier.fillMaxSize().padding(16.dp).appWidgetBackground()
            .background(GlanceTheme.colors.widgetBackground).cornerRadius(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(title, style = TextStyle(color = GlanceTheme.colors.onSurfaceVariant, fontSize = 14.sp), maxLines = 1)
        Text(value, style = TextStyle(color = GlanceTheme.colors.onSurface, fontSize = 32.sp, fontWeight = FontWeight.Medium), maxLines = 2)
    }
}
```

`maxLines` on every `Text`: widgets never scroll text, so unbounded text clips mid-line.

## List

```kotlin
LazyColumn(GlanceModifier.fillMaxSize().cornerRadius(16.dp)) {
    items(tasks, itemId = { it.id }) { task ->
        Row(
            GlanceModifier.fillMaxWidth().height(56.dp).padding(horizontal = 12.dp)
                .background(GlanceTheme.colors.secondaryContainer)
                .clickable(openTask(task.id)),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            CheckBox(checked = task.done, onCheckedChange = actionRunCallback<ToggleTaskAction>(
                actionParametersOf(TaskIdKey to task.id.toString())))
            Text(task.title, GlanceModifier.defaultWeight(), maxLines = 1,
                style = TextStyle(color = GlanceTheme.colors.onSecondaryContainer))
        }
    }
}
```

Empty and error states are separate branches, not an empty `LazyColumn`: an icon, one line of
text and an action that opens the app.

## Grid

`LazyVerticalGrid(gridCells = GridCells.Fixed(n))` supports a small fixed number of columns
(up to 5); `GridCells.Adaptive(minSize)` needs API 31+. Tile images are decoded to the tile size,
and the sum over visible tiles stays under the bitmap cap.

## Image plus text

- Image fills a `Box`; a gradient scrim drawable sits on top; text sits on the scrim with
  `onSurface`-on-scrim colours that pass contrast in both themes.
- `ContentScale.Crop` on the image; aspect ratio decided per breakpoint, not by the source photo.
- Remote images: download and downscale in the worker, store a file, give the widget
  `ImageProvider(bitmap)` decoded from that file. Never load a URL inside `provideContent`.

## Toolbar

- Icon buttons (`SquareIconButton`, `CircleIconButton`) each with `contentDescription` and a 48dp
  minimum target; at most 4 actions at the largest size.
- The "search field" is a clickable `Row` that opens the app's search screen; widgets cannot take
  text input.
