---
name: oauth-browser-login
description: OAuth 2.0 / OpenID Connect login on Android through the browser - Custom Tabs with PKCE via AppAuth or a provider SDK, redirect handling with custom schemes or verified App Links, secure token storage and refresh, attaching tokens only to your API hosts, 401 handling, browser fallbacks, and logging out of a web session with a callback activity. Use when adding OAuth/OIDC login, fixing token refresh, or handling web logout.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - OAuth 2.0
  - OpenID Connect
  - PKCE
  - AppAuth
  - Custom Tabs
  - App Links
  - token refresh
  - web logout
---

# OAuth / OIDC login through the browser

For Firebase/Google sign-in see `firebase-auth`. This skill is for an external identity provider
(Auth0, Okta, Keycloak, Cognito, your own OIDC server).

## Flow

1. Authorization Code + **PKCE** in a Custom Tab (never a WebView: it can read the password and many
   IdPs block it).
2. Redirect back to the app via a verified App Link (`https://` + `autoVerify`) or a custom scheme
   unique to the app.
3. Exchange the code for tokens, store them encrypted, request `offline_access` for a refresh token.
4. Attach the access token only to your API hosts; refresh on expiry; force re-login when refresh fails.

Use a maintained library (AppAuth-Android, or the provider's SDK) for PKCE, state and nonce handling;
do not hand-roll them.

## Configuration

Client id, issuer/domain, audience and scopes are **build configuration**, not source constants:

```kotlin
android {
    defaultConfig {
        buildConfigField("String", "AUTH_ISSUER", "\"${config("auth.issuer")}\"")
        buildConfigField("String", "AUTH_CLIENT_ID", "\"${config("auth.clientId")}\"")
        manifestPlaceholders["authRedirectScheme"] = config("auth.redirectScheme") ?: "com.example.app.auth"
    }
}
```

Different build types/flavours use different clients (dev/staging/prod). Public client ids are not
secrets, but keeping them out of source keeps environments switchable and repos clean.

## Repository shape (provider-SDK example)

```kotlin
class AuthRepositoryImpl(
    private val appContext: Context,
    private val config: AuthConfig,
    private val storage: SecureCredentialsStore,       // encrypted with a Keystore-backed key
) : AuthRepository, TokenProvider {

    override suspend fun logIn(activity: Activity): Unit = withContext(Dispatchers.Main) {
        val credentials = try {
            provider.login(activity, scheme = config.scheme, scope = "openid profile email offline_access", audience = config.audience)
        } catch (e: AuthCancelledException) {
            return@withContext                          // the person closed the tab: silent, not an error
        }
        storage.save(credentials)
    }

    override suspend fun token(): String? = storage.validOrRefreshed()?.accessToken   // refreshes and re-saves
    override fun isLoggedIn(): Boolean = storage.hasValidCredentials()

    override suspend fun logOut(activity: Activity) = withContext(Dispatchers.Main) {
        runCatching { provider.logout(activity, scheme = config.scheme, federated = false) }
        storage.clear()                                 // clear locally even if the web logout failed
    }
}
```

- Login and logout need an **Activity** context; never the application context.
- Treat a cancelled tab as a no-op.
- `TokenProvider` is an interface in the networking module; the auth module implements it, so
  networking never depends on the auth SDK.

## Attaching tokens

Ktor:

```kotlin
install(Auth) {
    bearer {
        loadTokens { tokenProvider.token()?.let { BearerTokens(it, "") } }
        refreshTokens { tokenProvider.forceRefresh()?.let { BearerTokens(it, "") } ?: run { session.signOut(); null } }
        sendWithoutRequest { it.url.host in apiHosts }   // allowlist: never send tokens to CDNs/images
    }
}
```

OkHttp: an `Interceptor` that adds the header only for allowlisted hosts plus an `Authenticator`
that refreshes on 401 once and gives up (returns null) if the request already carried the fresh
token. Do not `runBlocking` a slow network refresh inside an interceptor without a mutex: concurrent
requests will all refresh. Add the header in **one** place, not in both an interceptor and each
repository call. Image loaders get their own client without the auth interceptor.

## Browser fallbacks

Some devices default to a browser that cannot host Custom Tabs. Resolve the default `ACTION_VIEW`
handler (`PackageManager.ResolveInfoFlags` on API 33+); if it is known-broken or none supports
Custom Tabs (`CustomTabsClient.getPackageName`), restrict the picker to a list of compatible
browsers or fall back to a plain `ACTION_VIEW`. Catch `ActivityNotFoundException` and show a
"no browser available" message. Add `<queries>` for `android.intent.action.VIEW` / `https` and the
Custom Tabs service in the manifest (package visibility, API 30+).

## Logging out of a web session

When a separate web session must be ended (shop, help centre), open the IdP/site logout URL in a
Custom Tab with a return URL to the app, and resume a coroutine when the redirect lands:

```kotlin
object WebLogout {
    private var pending: CancellableContinuation<Unit>? = null

    suspend fun logOut(context: Context, logoutUrl: Uri) = withContext(Dispatchers.Main.immediate) {
        suspendCancellableCoroutine { cont ->
            pending = cont
            cont.invokeOnCancellation { pending = null }
            val url = logoutUrl.buildUpon().appendQueryParameter("returnTo", "com.example.app://logout-done").build()
            runCatching { CustomTabsIntent.Builder().build().launchUrl(context, url) }
                .onFailure { context.startActivity(Intent(Intent.ACTION_VIEW, url).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
        }
    }
    internal fun onReturned() { pending?.resume(Unit); pending = null }
}

class LogoutReturnActivity : Activity() {          // exported, translucent, finishes immediately
    override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState); WebLogout.onReturned(); finish() }
}
```

Add a timeout around the suspension; a person may never come back from the tab.

## Account state

- Clear every per-account cache (memory holders, DB rows, prefs keyed by account) on logout.
- On a 401 that survives refresh, sign out and route to login with a message; never loop.
- On process restart, decide the start destination only after `isLoggedIn()` resolves.

## Tests

Fake `TokenProvider` in repository tests; test that tokens go only to allowlisted hosts, refresh
happens once under concurrent 401s, and a failed refresh signs out.
