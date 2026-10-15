---
name: android-app-security
description: Audit and harden an Android app's attack surface - exported components and intent filters, Intent redirection and PendingIntent flags, deep-link and result-contract input validation, custom signature permissions and caller verification for services and providers, FileProvider and content URI grants, WebView hardening, network security config and certificate pinning policy, secrets and token storage with Keystore, backup rules, task hijacking, StrictMode unsafe-intent detection, and a report format for findings. Use when reviewing a manifest or IPC code, adding a deep link, exported component, WebView or file sharing, storing credentials, or preparing a security review. Do not use for server-side auth or for Play policy declarations (see account-compliance).
metadata:
  last-updated: '2026-10-15'
  keywords:
  - security
  - AndroidManifest
  - exported components
  - Intent redirection
  - PendingIntent
  - deep links
  - signature permission
  - FileProvider
  - WebView
  - network security config
  - certificate pinning
  - Keystore
  - backup rules
  - StrictMode
---

# Android app security

Two modes: **audit** (read, trace, report; change nothing) and **harden** (apply the fixes below,
one component at a time, with a test or a reproducible manual probe per fix). Say which mode you
are in. Findings are claims until you traced a real path from an attacker-controlled input to
the effect; report only traced paths.

## Step 1: enumerate the surface

```bash
# merged manifest, not the module's source manifest: libraries add components
./gradlew :app:processReleaseMainManifest && cat app/build/intermediates/merged_manifest/release/AndroidManifest.xml
```

For each `<activity>`, `<service>`, `<receiver>`, `<provider>` record: `exported`, intent
filters, permission, `grantUriPermissions`, and what the handler does with the incoming
`Intent`/URI. Anything exported without a reason is a finding. Then grep the code:

- `getIntent()`, `intent.extras`, `getParcelableExtra`, `onNewIntent`, `startActivity(intent.getParcelableExtra(…))`
- `PendingIntent.get*`, `Intent.createChooser`
- `WebView`, `addJavascriptInterface`, `loadUrl`, `shouldOverrideUrlLoading`
- `FileProvider`, `grantUriPermission`, `FLAG_GRANT_*`
- `SharedPreferences`, `DataStore`, `Cipher`, `KeyGenParameterSpec`, token/secret names
- `allowBackup`, `dataExtractionRules`, `networkSecurityConfig`, `usesCleartextTraffic`

## Step 2: components and Intents

- `android:exported` is explicit on every component with an intent filter (required since API 31)
  and `false` unless another app must start it. Launcher activity, deep-link activity, FCM
  service and share targets are the usual legitimate `true`s.
- **Intent redirection**: never forward an `Intent` taken from another app's extras to
  `startActivity`/`startService`/`setResult` as-is. Rebuild it or sanitize it:

```kotlin
// RIGHT
val forwarded = IntentSanitizer.Builder()
    .allowComponent(ComponentName(this, DetailActivity::class.java))
    .allowAction(Intent.ACTION_VIEW)
    .allowDataWithAuthority("app.example.com")
    .allowExtra("item_id", String::class.java)
    .build()
    .sanitizeByFiltering(IntentCompat.getParcelableExtra(intent, "next", Intent::class.java) ?: return)
startActivity(forwarded)
```

```kotlin
// WRONG: any app can make your (trusted, maybe privileged) process launch a non-exported activity or a content:// URI it has no access to
startActivity(intent.getParcelableExtra("next"))
```

- Deep links and App Links: treat every path/query parameter as untrusted. Validate the id
  format, resolve it through the normal repository (which applies auth), and never put a URL to
  load or a file path in a deep link. Use `autoVerify` App Links for `https`; a custom scheme can
  be claimed by any app.
- `onNewIntent` runs the same validation as `onCreate`; a warm activity is the common bypass.
- Result contracts: validate `ActivityResult` data as you would a deep link; `RESULT_OK` from a
  third-party activity proves nothing.
- Broadcasts: in-process events go through a Flow, not a broadcast. Sending
  a broadcast with data? Set the package or protect it with a signature permission. Receiving?
  `exported=false` or require a permission; `RECEIVER_NOT_EXPORTED` for runtime registration (API 33+).
- Task hijacking: launcher activity gets `android:taskAffinity=""` and
  `launchMode="singleTask"` only when needed; do not expose sensitive screens as `singleInstance`
  with an empty affinity.
- Debug builds: `StrictMode.VmPolicy.Builder().detectUnsafeIntentLaunch().penaltyLog()` (API 31+)
  catches redirection at runtime (`debug-tooling`).

## Step 3: PendingIntents

- `FLAG_IMMUTABLE` by default (required to declare one on API 31+). `FLAG_MUTABLE` only when the
  receiver must fill in fields (direct reply, chooser callback), and then combine with an explicit
  component and `FLAG_UPDATE_CURRENT`; on API 34+ an implicit mutable intent is rejected.
- Never wrap an Intent that came from another app in a PendingIntent.
- Notifications: `TaskStackBuilder` or explicit activity; the content intent carries ids, not
  payloads.

## Step 4: permissions and caller verification

- Custom permission for IPC between your own apps: `protectionLevel="signature"`; on API 33+
  `knownSigner` lists partner certificates. Declare it in every app that uses it with the same
  name and level (first-installer wins otherwise).
- Services and providers that return data: check the caller, not just the permission:

```kotlin
override fun onBind(intent: Intent): IBinder = binder
// inside the Binder method, on the binder thread:
val uid = Binder.getCallingUid()
val pkgs = packageManager.getPackagesForUid(uid).orEmpty()
require(pkgs.any { packageManager.hasSigningCertificate(it, trustedSha256, PackageManager.CERT_INPUT_SHA256) }) { "untrusted caller" }
```

  Do not trust `getCallingPackage()` strings alone; verify the signing certificate.
- Runtime permissions: request in context with a rationale, handle "don't ask again" by linking to
  settings, and never request more than the feature in front of the user needs
  (`media-storage` and `push-notifications` show the flows).

## Step 5: files, providers and WebView

- Share files only through `FileProvider` with `<paths>` scoped to one subdirectory, temporary
  `FLAG_GRANT_READ_URI_PERMISSION` on the share Intent, never `file://` URIs or world-readable
  files. A `ContentProvider` you write validates `uri.pathSegments` (reject `..`), uses parameter
  binding for every query, and is `exported=false` unless it is the product.
- WebView: `javaScriptEnabled` only for pages you control; `allowFileAccess=false`,
  `allowContentAccess=false`, `allowFileAccessFromFileURLs=false`; `addJavascriptInterface` only
  for your own origin, checked in `shouldOverrideUrlLoading`/`onPageStarted` against an
  allow-list of hosts; never load an attacker-supplied URL into a WebView with an interface. OAuth
  never runs in a WebView (`oauth-browser-login`). Enable Safe Browsing (default) and
  `WebViewAssetLoader` for local content.
- Clipboard: sensitive values copied with `ClipDescription.EXTRA_IS_SENSITIVE` (API 33+).

## Step 6: network and secrets

- `res/xml/network_security_config.xml`: `cleartextTrafficPermitted="false"`; debug-only
  `debug-overrides` for a proxy CA; never add user CAs to release. Pinning is a product
  decision: it needs a rotation plan, a backup pin and an expiry; without those it is an outage
  waiting to happen, so leave it out and say why.
- Tokens and secrets at rest: app-private storage is already per-app sandboxed. Encrypt tokens
  with an AES-GCM key from `AndroidKeyStore` (`KeyGenParameterSpec`, `setUserAuthenticationRequired`
  only for step-up flows) when the threat model includes rooted devices or backups.
  `EncryptedSharedPreferences` (security-crypto) is deprecated; do not add it to new code. No
  secrets in `BuildConfig` or `strings.xml`: a client secret in the APK is public
  (`android-release-signing` covers build-time values).
- Logging: no tokens, emails or request bodies in production logs; redact in the Ktor logger
  (`ktor-api-client`), strip `Log.d/v` with R8 `-assumenosideeffects` or a `Timber` tree per build.
- Backups: `android:dataExtractionRules` (API 31+) + `fullBackupContent` excluding token files and
  databases with session data; otherwise a device-to-device transfer copies the session.

## Step 7: verify and report

- Each fix has a probe that **failed before** the fix: an `adb shell am start -n … --es next …`
  redirection attempt, a `content query --uri …` from the shell, `adb shell am broadcast` to a
  receiver, a `curl` through a MITM proxy that must be refused.
- Add a guard test (`architecture-guard-tests`) for the merged manifest: no exported component
  outside an allow-list; no `FLAG_MUTABLE` outside allow-listed files.
- `./gradlew :app:lintRelease` with the security checks enabled (`ExportedReceiver`,
  `UnsafeIntentLaunch`, `SetJavaScriptEnabled`, `TrustAllX509TrustManager`, `UnsafeProtectedBroadcastReceiver`
  at `error`).

Audit report format (nothing else in the output):

```markdown
## Findings
| # | Severity | Component / file:line | Issue | Attack path (traced) | Fix |
## Verified safe
- <component>: <why it is fine>
## Not checked
- <area>: <reason>
```

Severity: **High** = another app can read data, act as the user or run code; **Medium** = needs
user interaction or a specific device state; **Low** = hardening with no traced exploit.

## Checklist

- [ ] Every component has explicit `exported`; the exported list is justified in the report.
- [ ] No Intent from extras is forwarded without `IntentSanitizer` or reconstruction.
- [ ] All `PendingIntent`s are `FLAG_IMMUTABLE` or justified `FLAG_MUTABLE` with explicit component.
- [ ] Deep links, `onNewIntent` and activity results validate every parameter.
- [ ] IPC with other apps uses signature/`knownSigner` permission plus certificate check.
- [ ] Files leave the app only via `FileProvider`; WebView has no interface on foreign origins.
- [ ] Cleartext disabled; secrets not in the APK; backup rules exclude session data.
- [ ] Each fix has a probe that failed before it; lint security checks are errors.
