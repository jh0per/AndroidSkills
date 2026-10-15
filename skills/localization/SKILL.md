---
name: localization
description: Localizing Android and Compose Multiplatform apps - string resources (Android res and Compose Resources), plurals, escaping pitfalls, reading the device or per-app locale correctly, Accept-Language on API calls, localizing server errors from stable codes, per-app language settings, keeping document data unlocalized, translation lint in CI, and testing in more than one language. Use when adding strings or languages, fixing untranslated or mis-rendered text, or wiring locale-aware networking.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - localization
  - i18n
  - string resources
  - plurals
  - per-app language
  - Accept-Language
  - Compose Resources
---

# Localization

## Strings

- Every user-facing string is a resource: Android `res/values*/strings.xml` or Compose Resources
  `composeResources/values*/strings.xml` in KMP. The default (`values`) language is the reviewed
  source; missing keys fall back to it.
- Counts use **plurals**, never `"%d days"` in a plain string:

```xml
<plurals name="days_left">
    <item quantity="one">%1$d day left</item>
    <item quantity="other">%1$d days left</item>
</plurals>
```

```kotlin
Text(pluralStringResource(Res.plurals.days_left, days, days))          // Compose Resources
Text(pluralStringResource(R.plurals.days_left, days, days))            // Android
```

  Languages with few/many forms (e.g. Slavic languages) need every quantity filled.
- Positional args (`%1$s`) always, so translators can reorder.
- **Compose Resources do not unescape `\'`.** Use the typographic apostrophe (’) or check the
  rendered output; guard with a test that fails on `\'`/`\"` in Compose resource files.
- Pin the generated class package: `compose.resources { packageOfResClass = "com.example.app.resources" }`.
- `@Composable` default arguments may call `stringResource`; they resolve in the caller's composition.
- Strings needed outside composition (messages built in coroutines) use `getString(Res.string.x)`
  (suspend) in KMP or a `Context`-backed provider on Android, injected behind an interface so tests
  need no resource environment.
- A UI text type for state holders:

```kotlin
sealed interface UiText {
    data class Raw(val value: String) : UiText
    class Res(@StringRes val id: Int, vararg val args: Any) : UiText
    @Composable fun asString(): String = when (this) { is Raw -> value; is Res -> stringResource(id, *args) }
    fun asString(context: Context): String = when (this) { is Raw -> value; is Res -> context.getString(id, *args) }   // spread!
}
```

## What not to localize

Values stored as user data or sent to a server (user-entered names, pre-filled captions,
enum wire names) stay language-neutral; otherwise the phone's language leaks into shared data.

## Reading the locale

```kotlin
class AndroidDeviceLocale(private val app: Context) : DeviceLocale {
    override fun languageTag(): String =
        if (Build.VERSION.SDK_INT >= 33) {
            app.getSystemService(LocaleManager::class.java).applicationLocales.takeIf { !it.isEmpty }?.get(0)?.toLanguageTag()
                ?: app.resources.configuration.locales[0].toLanguageTag()
        } else {
            app.resources.configuration.locales[0].toLanguageTag()
        }
}
```

Never `Resources.getSystem()`: it cannot see a per-app language. iOS: `NSLocale.preferredLanguages.first`.

## Per-app language

- Declare supported languages in `res/xml/locales_config.xml` and `android:localeConfig`
  (API 33+ shows the setting in system Settings).
- Switch in-app with `AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags("de"))`
  (persists, recreates activities).
- If language can change in-app, disable language splits so all languages ship:
  `bundle { language { enableSplit = false } }`.

## Server communication

- Send `Accept-Language` on every request, computed per request from a lambda (the language can
  change while the HTTP client singleton lives): `"de-DE, de;q=0.9"`; omit the header when empty.
- The server localizes content; **errors travel as stable codes** and are worded on the client:

```kotlin
sealed interface FailureReason {
    data object NoConnection : FailureReason
    data object SignInRequired : FailureReason
    data object PayloadTooLarge : FailureReason
    data class AsTheServerPutIt(val message: String) : FailureReason   // last-resort fallback
}
fun reasonFor(code: String?): FailureReason? = when (code) {
    "UNAUTHORIZED" -> FailureReason.SignInRequired
    "PAYLOAD_TOO_LARGE" -> FailureReason.PayloadTooLarge
    else -> null
}
interface FailureMessages { suspend fun say(reason: FailureReason): String }
```

  Status-only guesses are route-specific (a 404 means "photo gone" only on one endpoint); keep them
  next to that call, not in the global mapper.

## OTA strings and translation management

- If copy comes over the air, see `analytics-feature-flags` (lookup chain, init order, pre-release
  gating).
- Normalise locale folder names between the TMS and Android (`in` vs `id` for Indonesian,
  `nb`/`nn`/`no` for Norwegian).
- A Gradle task (cacheable inputs) fails CI on: broken `%` specifiers, iOS-style `%@`, mismatched
  placeholders versus the default language, empty plural items, `\'` in Compose resources.
- A "hard-coded strings" ratchet: a script counts string literals in UI files per file against a
  baseline that may only go down.

## Layout

- Test with long translations (German), RTL (Arabic/Hebrew: `start`/`end`, mirrored icons with
  `autoMirrored`), and 200% font scale.
- Never size text containers to English.
- Dates, numbers and currency via `DateTimeFormatter`/`NumberFormat` with the current locale, never
  string concatenation.

## Tests

- Run UI/instrumented tests in at least one non-default language (see the locale-aware runner in
  `android-testing`); a suite that only passes in English hides hard-coded strings.
- Screenshot tests resolve expected text from resources, not literals.
