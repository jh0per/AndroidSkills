---
name: design-system-module
description: Build a Compose design-system module - spacing, size, colour and typography tokens mapped onto a Material 3 theme, reusable components with loading states, skeleton placeholders with shimmer, a tinted Lottie loader, multi-device previews, global error/success message hosts, theming an embedded library from host tokens, and system bar styling under edge-to-edge. Use when creating or extending the shared UI module, adding a token or component, or adding loading/skeleton states.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - design system
  - theme
  - tokens
  - skeleton
  - shimmer
  - Lottie
  - previews
  - edge-to-edge
---

# Design-system module

One module (`:core:ui`) owns tokens, theme and shared components. Feature modules consume roles
and components; they never define colours, type or spacing of their own. Component choice follows
`material3-guidelines`; reuse rules follow `compose-ui-practices`.

## Tokens

```kotlin
// Raw palette: only the theme reads these
internal object Palette {
    val Primary500 = Color(0xFF1F6FEB); val Primary700 = Color(0xFF0B4FB3)
    val Error500 = Color(0xFFD32F2F); val Success500 = Color(0xFF2E7D32)
    val Gray50 = Color(0xFFF7F8FA); val Gray900 = Color(0xFF14161A)
}

// Semantic spacing: names describe relationships, not screens
@Immutable data class AppSpacing(
    val inline: Dp = 4.dp, val control: Dp = 8.dp, val item: Dp = 12.dp,
    val content: Dp = 16.dp, val section: Dp = 24.dp, val screen: Dp = 32.dp,
)
val LocalAppSpacing = staticCompositionLocalOf { AppSpacing() }

// Extra roles Material does not have
@Immutable data class AppExtendedColors(val success: Color, val onSuccess: Color, val warning: Color, val onWarning: Color)
val LocalAppExtendedColors = staticCompositionLocalOf<AppExtendedColors> { error("AppTheme not applied") }

object AppTheme {
    val spacing: AppSpacing @Composable get() = LocalAppSpacing.current
    val extendedColors: AppExtendedColors @Composable get() = LocalAppExtendedColors.current
}

@Composable
fun AppTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val scheme = if (darkTheme) AppDarkScheme else AppLightScheme     // every role filled, both schemes
    CompositionLocalProvider(
        LocalAppSpacing provides AppSpacing(),
        LocalAppExtendedColors provides if (darkTheme) DarkExtended else LightExtended,
    ) {
        MaterialTheme(colorScheme = scheme, typography = AppTypography, shapes = AppShapes, content = content)
    }
}
```

Typography: one `Typography(...)` that applies the brand `FontFamily` to all 15 roles, with
`platformStyle = PlatformTextStyle(includeFontPadding = false)` and an explicit `lineHeightStyle`
so text aligns the same on every API level. Avoid a second, product-named type scale alongside
Material's; if product names are needed, alias Material roles.

## Components

- Wrap Material components only to add product policy: `AppPrimaryButton(text, onClick, loading = false, enabled = true)`
  shows a spinner in place of the label, keeps its width, and ignores clicks while loading.
- Every component takes `modifier: Modifier = Modifier` as the first optional parameter and
  forwards it to the root (enforce with the Compose detekt/ktlint rules).
- App bar defaults (height, content padding) live in one `AppTopBarDefaults` object.
- Components that draw text name their colour or sit inside a `Surface`.

## Skeletons with shimmer

Apply the placeholder to the **real** content so no separate skeleton layout is needed:

```kotlin
fun Modifier.placeholder(
    visible: Boolean,
    color: Color = Color.Unspecified,
    shape: Shape = RoundedCornerShape(4.dp),
    shimmer: Boolean = true,
): Modifier = composed {
    val base = color.takeOrElse { MaterialTheme.colorScheme.surfaceContainerHighest }
    val alpha by animateFloatAsState(if (visible) 1f else 0f, label = "placeholder")
    val progress = if (visible && shimmer) {
        rememberInfiniteTransition(label = "shimmer").animateFloat(
            0f, 1f, infiniteRepeatable(tween(1700, delayMillis = 200), RepeatMode.Restart), label = "p",
        ).value
    } else 0f
    drawWithContent {
        if (alpha < 0.99f) drawContent()                 // content fades in as the placeholder fades out
        if (alpha > 0.01f) {
            val outline = shape.createOutline(size, layoutDirection, this)
            drawOutline(outline, base, alpha = alpha)
            if (shimmer) {
                val x = size.width * (progress * 2f - 0.5f)
                drawOutline(outline, Brush.linearGradient(listOf(Color.Transparent, Color.White.copy(alpha = 0.35f), Color.Transparent),
                    start = Offset(x - size.width / 2, 0f), end = Offset(x + size.width / 2, size.height)), alpha = alpha)
            }
        }
    }
}
// Text("…", Modifier.placeholder(visible = state.title == null))
```

Also hide placeholder content from accessibility while visible (`Modifier.semantics { invisibleToUser() }`
or `clearAndSetSemantics {}` with a "Loading" description on the container).

## Loading tiers

| Situation | Indicator |
|---|---|
| First load of a screen/list | skeletons (placeholder modifier) |
| Appending a page | small spinner row |
| An action in progress | button `loading = true` |
| Blocking full-screen work | centered spinner with text, only when nothing else can be shown |

A brand Lottie spinner can be tinted at runtime instead of shipping one JSON per colour:

```kotlin
@Composable
fun AppLoader(modifier: Modifier = Modifier, color: Color = MaterialTheme.colorScheme.primary) {
    val composition by rememberLottieComposition(LottieCompositionSpec.RawRes(R.raw.loader))
    val dynamic = rememberLottieDynamicProperties(
        rememberLottieDynamicProperty(LottieProperty.COLOR_FILTER, keyPath = arrayOf("**")) {
            PorterDuffColorFilter(color.toArgb(), PorterDuff.Mode.SRC_ATOP)
        },
    )
    LottieAnimation(composition, modifier.defaultMinSize(48.dp), iterations = LottieConstants.IterateForever, dynamicProperties = dynamic)
}
```

Respect "remove animations": show a static frame when `Settings.Global.ANIMATOR_DURATION_SCALE` is 0.

## Global messages

A single `MessageBus` (Koin single) exposes `SharedFlow<UserMessage>`; state holders call
`showError(throwable)` / `showMessage(textRes)`. The root composable hosts the `SnackbarHost`(s),
padded above bottom bars and the navigation inset. State holders never own snackbar state. Map
errors to product sentences in one place (`ErrorMessages.of(throwable)`), and log the original
cause, not the wrapper.

## Previews

```kotlin
@Preview(name = "phone", device = Devices.PIXEL_7)
@Preview(name = "small", device = "spec:width=360dp,height=640dp,dpi=320")
@Preview(name = "dark", uiMode = Configuration.UI_MODE_NIGHT_YES)
@Preview(name = "font 200%", fontScale = 2f)
annotation class AppPreviews

@AppPreviews @Composable private fun PrimaryButtonPreview() = AppTheme { AppPrimaryButton("Continue", onClick = {}) }
```

## Theming an embedded library

If a library module has its own theme object, build it from host tokens once and provide it via
the library's `CompositionLocal`/parameter, so the library never hard-codes colours:
`ChatTheme(colors = ChatColors(accent = scheme.primary, …), typography = ChatTypography(body = AppTypography.bodyMedium, …))`.

## System bars

With `enableEdgeToEdge()` (default on targetSdk 35+), do not set `window.statusBarColor`/
`navigationBarColor` (ignored on 35+). Draw your own background behind the bars and control icon
contrast with `enableEdgeToEdge(SystemBarStyle.auto(lightScrim, darkScrim))` or
`WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = …` when a screen's
top colour changes; key it on the colour so it updates, not `LaunchedEffect(Unit)`.

## Lint rules for the module

Add the Compose rules for detekt or ktlint (`io.nlopez.compose.rules`): modifier parameter
present and first-optional, `CompositionLocal` allowlist, no emitting content and returning values,
lambda parameters in restartable effects, preview visibility.

## Theme details that prevent real bugs

- Fill **every** Material 3 role in both schemes, including `surfaceContainerLowest…Highest`,
  `surfaceBright/Dim`, `inverse*`, `outline*`, `secondaryContainer` (chips) and
  `surfaceContainerLow` (bottom sheets). Unset roles fall back to the library's purple.
- Provide `LocalContentColor provides colorScheme.onBackground` at the theme root; outside a `Surface`
  the default is black, which hides text in dark mode.
- Separate **fill** and **ink** tokens for the accent: a bright brand fill is often ~2:1 as text; a
  darkened ink variant reaches 4.5:1.
- Raw colours are allowed in exactly three places: the theme palette, document/content colours, and
  scrims/ink over imagery (identical in both modes). Guard it (`architecture-guard-tests`).
- Appearance setting (System/Light/Dark): an app-scoped controller above navigation exposes a
  `StateFlow`, defaults to System, loads from DataStore, updates state before persisting.

## Dialogs and notices

```kotlin
@Composable
fun AppDialog(
    title: String, confirmLabel: String, onConfirm: () -> Unit, onDismiss: () -> Unit,
    dismissLabel: String? = stringResource(R.string.action_cancel),
    destructive: Boolean = false,
    neutralLabel: String? = null, onNeutral: (() -> Unit)? = null,
    body: (@Composable () -> Unit)? = null,
) = AlertDialog(
    onDismissRequest = onDismiss,
    title = { Text(title) },
    text = body?.let { { Box(Modifier.verticalScroll(rememberScrollState())) { it() } } },   // large font scales
    confirmButton = { TextButton(onConfirm) { Text(confirmLabel, color = if (destructive) MaterialTheme.colorScheme.error else Color.Unspecified) } },
    dismissButton = {
        Row {
            if (neutralLabel != null && onNeutral != null) TextButton(onNeutral) { Text(neutralLabel) }   // e.g. "Discard", away from the thumb
            dismissLabel?.let { TextButton(onDismiss) { Text(it) } }
        }
    },
)
```

- Inline notice card for things a person must act on: title, body, optional action slot, optional
  dismiss with a required, localized label; accent styling, not error red, for advisory notices.
- One message host mounted once at the root; failures styled with `errorContainer`, confirmations
  with `inverseSurface`; short duration, no action.
- Skeleton shimmer animated in the draw phase (`drawBehind` reading an animated value) so it does not
  recompose every frame.

## Splash and launcher icon

- Use the platform splash: API 31+ `windowSplashScreenBackground` + `windowSplashScreenAnimatedIcon`;
  below 31 a `windowBackground` layer-list (colour + centred mark). No second timed splash screen in
  Compose. (androidx core-splashscreen is an alternative that unifies both.)
- One vector serves as adaptive launcher foreground, monochrome (themed) icon and splash icon. Keep
  the mark inside the safe zone: about 66dp diameter in the 108dp canvas, so circular masks do not
  clip it.
