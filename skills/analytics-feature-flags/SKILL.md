---
name: analytics-feature-flags
description: Product instrumentation for Android apps - interface-segregated analytics with typed events, consent handling, crash-reporting keys and breadcrumbs, performance traces, remote-config feature flags gated by app version and locale with debug overrides, A/B test groups, staged-rollout-aware force update, and over-the-air strings with resource fallback. Use when adding events, flags, experiments, force-update logic or remotely managed copy.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - analytics
  - feature flags
  - remote config
  - A/B testing
  - force update
  - consent
  - crash reporting
---

# Analytics, feature flags and remote config

## Analytics: one implementation, narrow interfaces

```kotlin
interface CheckoutEvents { fun checkoutStarted(itemCount: Int); fun checkoutCompleted(orderId: String, durationMs: Long) }
interface BillingEvents { fun paywallShown(source: String); fun purchaseCompleted(productId: String, trial: Boolean) }
interface Analytics : CheckoutEvents, BillingEvents { fun setUserId(id: String?); fun setConsent(granted: Boolean) }

class FirebaseAnalyticsImpl(private val firebase: FirebaseAnalytics) : Analytics {
    override fun checkoutStarted(itemCount: Int) = log("checkout_started", "item_count" to itemCount)
    // …
    private fun log(name: String, vararg params: Pair<String, Any?>) = firebase.logEvent(name, bundleOf(*params))
}

// Koin: one instance, injected by slice
val analyticsModule = module {
    single<Analytics> { FirebaseAnalyticsImpl(get()) }
    factory<CheckoutEvents> { get<Analytics>() }
    factory<BillingEvents> { get<Analytics>() }
}
```

- State holders depend on their slice only; fakes in tests are tiny and record calls.
- Event and parameter names are constants in one place, snake_case, within the provider's limits
  (Firebase: 40-char names, 100-char string values, 25 params).
- Multiple providers (product analytics, attribution, marketing) sit behind the same interfaces in a
  composite implementation; the app never calls SDKs directly.
- **Consent:** collection is enabled only when `consent && !debugBuild` (or a dedicated debug
  property), never `!debug || consent`. Persist consent and apply it before the first event
  (`setAnalyticsCollectionEnabled`, consent mode v2 settings for ads/analytics storage).
- **Never** log tokens, emails, free text or full URLs with query parameters.
- Low-memory and other diagnostics: `onTrimMemory(RUNNING_CRITICAL/COMPLETE)` → record counts of heavy
  objects as crash keys or a non-fatal, not as product analytics.
- Share target attribution: `Intent.createChooser(send, title, pendingIntent.intentSender)` with a
  receiver reading `Intent.EXTRA_CHOSEN_COMPONENT`; the `PendingIntent` must be `FLAG_MUTABLE` on API
  31+ so the system can add the extra.

## Crash reporting

- Wrap the crash SDK behind an interface (`ErrorReporter.record(t)`, `setKey`, `log`) so unit tests
  never initialise Firebase.
- Set a custom key for the current screen and for the operation in progress; log breadcrumbs on
  save/restore of critical state.
- Record unwrapped causes; group by the real exception.
- Performance traces for multi-step operations (checkout started → order confirmed) with named
  start/stop and attributes.

## Feature flags

```kotlin
data class FeatureConfig(val key: String, val enabled: Boolean, val minVersion: String? = null, val locales: List<String>? = null)

class FeatureFlags(
    private val remote: () -> List<FeatureConfig>,
    private val overrides: DebugOverrides,          // debug menu wins, debug builds only
    private val appVersion: String,                 // without "-debug"/branch suffixes
    private val locale: () -> String,
) {
    fun isEnabled(key: String, default: Boolean = false): Boolean {
        overrides.feature(key)?.let { return it }
        val config = remote().firstOrNull { it.key == key } ?: return default
        val versionOk = config.minVersion?.let { compareVersions(appVersion, it) >= 0 } ?: true
        val localeOk = config.locales?.contains(locale()) ?: true
        return config.enabled && versionOk && localeOk
    }
}

fun compareVersions(a: String, b: String): Int {                // segment by segment: "2.0" > "1.10.0"
    val x = a.substringBefore('-').split('.').map { it.toIntOrNull() ?: 0 }
    val y = b.substringBefore('-').split('.').map { it.toIntOrNull() ?: 0 }
    for (i in 0 until maxOf(x.size, y.size)) {
        val d = x.getOrElse(i) { 0 } - y.getOrElse(i) { 0 }
        if (d != 0) return d
    }
    return 0
}
```

- Remote values are JSON parsed into typed configs; unknown keys are ignored so the backend can add
  flags safely; malformed JSON falls back to defaults (log it).
- Defaults are compiled in (`setDefaultsAsync(R.xml.remote_config_defaults)`); the app must work
  offline on first launch.
- Fetch interval 0 only in debug; production respects throttling. Activate at a safe moment (start
  of session), not mid-screen, so UI does not change under the person.
- Never compare versions by stripping dots and parsing an integer.
- One mapping per flag key, table-tested: copy-pasted getters reading the wrong key are a classic bug.
- Read through a single helper (`getStringOrNull(key)`) instead of repeated try/catch blocks.

## A/B tests

- Groups are strings from remote config (`control`, `treatment`, or `a/b/c`); map them to enums with a
  default; debug overrides first.
- Log exposure (the user actually saw the variant) as an event or user property, once per session.
- Keep experiment code removable: one branch point per experiment, deleted when it concludes.

## Force update

```kotlin
data class ForceUpdate(val blockedVersions: List<String>, val productionVersions: List<String>, val soft: Boolean)

/** Block only versions listed as blocked AND not currently served in production (staged rollouts). */
fun mustUpdate(current: String, rule: ForceUpdate): Boolean {
    val v = current.substringBefore('-')
    return v in rule.blockedVersions && v !in rule.productionVersions
}
```

Prefer Play's in-app updates API (`AppUpdateManager`, `IMMEDIATE` for hard, `FLEXIBLE` for soft) to
send people to the update; fall back to the store listing.

## Over-the-air strings

- Initialise the OTA SDK right after `super.onCreate()` in `Application`, update translations on
  activity start/resume.
- Lookup chain for server-driven labels: OTA value → bundled resource by key name → a readable
  fallback. Never show raw keys.
- Normalise locale aliases (e.g. Norwegian `nb`/`nn` → `no`, Indonesian `in` vs `id`) consistently
  between the TMS and Android resource folders.
- Pre-release translations only in debug/internal builds.
- If the language is switchable in-app, ship all languages: `bundle { language { enableSplit = false } }`,
  and declare `locales_config.xml` for per-app language settings (API 33+), using
  `AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags(tag))`.

### Translation lint task

Fail CI on broken translations (broken `%` specifiers, iOS-style `%@`, empty plural items, missing
placeholders compared with the default locale). See `gradle-build-setup` for writing the task with
proper `@InputDirectory`/`@Input` properties so it is cacheable.

## Tests

- Flags: table tests over version/locale/override combinations.
- Analytics: fakes per slice assert the event and parameters for a user action.
- Force update: blocked vs production-served versions, suffixes stripped.
