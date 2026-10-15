---
name: ktor-api-client
description: Set up or change a Ktor HTTP client for an Android or Kotlin Multiplatform app - engine seam, JSON config, bearer auth restricted to the API origin with refresh-once on 401, a single safeApiCall/ApiResult error mapper, optional retry/cache/connectivity plugins, and MockEngine tests in virtual time. Use when adding an endpoint, changing auth or error handling, or debugging network behaviour.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Ktor
  - HTTP client
  - bearer auth
  - token refresh
  - error mapping
  - MockEngine
  - connectivity
---

# Ktor API client

One client, one error mapper, one place where the token is attached.

## Client

```kotlin
val appJson = Json { ignoreUnknownKeys = true; explicitNulls = false }

fun appHttpClient(
    engine: HttpClientEngine,                       // OkHttp on Android, Darwin on iOS, MockEngine in tests
    apiOrigin: String,                              // build-time value, never a user setting
    logRequests: Boolean = false,                   // true only in debug builds
    languageTag: () -> String = { "" },             // a function: picks up a locale change at runtime
    tokenProvider: suspend (forceRefresh: Boolean) -> String?,
): HttpClient {
    val apiHost = Url(apiOrigin).host
    return HttpClient(engine) {
        expectSuccess = false                       // safeApiCall maps statuses itself
        install(ContentNegotiation) { json(appJson) }
        install(Auth) {
            bearer {
                loadTokens { tokenProvider(false)?.let { BearerTokens(it, null) } }
                refreshTokens { tokenProvider(true)?.let { BearerTokens(it, null) } } // Ktor retries a 401 once
                // Only our API gets the token. Presigned storage/CDN URLs must not.
                sendWithoutRequest { it.url.host.equals(apiHost, ignoreCase = true) }
            }
        }
        if (logRequests) install(Logging) {
            level = LogLevel.INFO
            sanitizeHeader { it.equals(HttpHeaders.Authorization, ignoreCase = true) }
        }
        defaultRequest {
            url(apiOrigin)
            contentType(ContentType.Application.Json)
            languageTag().takeIf { it.isNotBlank() }?.let { header(HttpHeaders.AcceptLanguage, it) }
        }
    }
}
```

Release builds talk TLS only. Debug builds may point at a LAN/emulator host
(`http://10.0.2.2:<port>` from the emulator) through `local.properties` or `-P`, never through UI.

## Result type and the single mapper

```kotlin
sealed interface ApiResult<out T> {
    data class Success<T>(val value: T) : ApiResult<T>
    data class Failure(val error: ApiError) : ApiResult<Nothing>
}

sealed interface ApiError {
    val message: String
    val reason: FailureReason?                     // from the server's stable error code only
    data class Unauthorized(override val message: String, override val reason: FailureReason?) : ApiError
    data class Network(override val message: String, override val reason: FailureReason? = FailureReason.NoConnection) : ApiError
    data class Validation(override val message: String, override val reason: FailureReason?) : ApiError
    data class Conflict(override val message: String, val code: String?, override val reason: FailureReason?) : ApiError
    data class Server(val status: Int, val code: String?, override val message: String, override val reason: FailureReason?) : ApiError
}

@Serializable data class ApiErrorEnvelope(val statusCode: Int? = null, val code: String? = null, val message: String? = null)

@Suppress("TooGenericExceptionCaught")
suspend inline fun <reified T> safeApiCall(session: SessionStore?, request: () -> HttpResponse): ApiResult<T> {
    val response = try { request() }
        catch (e: CancellationException) { throw e }                // never swallow cancellation
        catch (e: Exception) { return ApiResult.Failure(ApiError.Network(e.message.orEmpty())) }

    if (response.status.isSuccess()) return try { ApiResult.Success(response.body<T>()) }
        catch (e: CancellationException) { throw e }
        catch (_: Exception) { ApiResult.Failure(ApiError.Server(response.status.value, null, "", FailureReason.UnreadableResponse)) }

    val envelope = runCatching { appJson.decodeFromString<ApiErrorEnvelope>(response.bodyAsText()) }.getOrDefault(ApiErrorEnvelope())
    val message = envelope.message ?: "Request failed (${response.status.value})"
    val reason = reasonFor(envelope.code)
    return ApiResult.Failure(when (response.status.value) {
        401 -> { session?.markUnauthorized(); ApiError.Unauthorized(message, reason) } // survived the refresh → sign out
        400 -> ApiError.Validation(message, reason)
        409 -> ApiError.Conflict(message, envelope.code, reason)
        else -> ApiError.Server(response.status.value, envelope.code, message, reason)
    })
}
```

Repositories call `safeApiCall<Dto>(session) { client.get("/v1/items/$id") }` and may localise with
an extension such as `.inWords(messages)` that swaps `message` for a translated sentence when
`reason` is known. Derive the reason from the server's stable code, never from the HTTP status: a
status says what happened to the transport, not whose fault it was.

## Optional plugins (Android-only apps)

```kotlin
install(HttpRequestRetry) {
    retryOnServerErrors(maxRetries = 3)
    retryOnExceptionIf { _, cause -> cause !is NoConnectionException }
    exponentialDelay()
}
install(HttpCache) { publicStorage(FileStorage(File(context.cacheDir, "http"))) }
install(ConnectivityPlugin)   // throws NoConnectionException in HttpSendPipeline.Before when offline
```

- Gate verbose logging (and OkHttp `HttpLoggingInterceptor.Level.BODY`) on debug builds.
- Debug-only inspectors (e.g. Chucker) use the library's no-op artifact in release.
- Retrofit/OkHttp apps follow the same shape: one interceptor attaches auth for the API host only,
  one mapper turns responses into a sealed result.

## Wire-format rules

- **Print the bytes.** `kotlinx.serialization` omits properties equal to their default. A server
  that requires a key to be *present* rejects `rotation = 0` as if it were missing. Before trusting
  a DTO, print `appJson.encodeToString(dto)` and compare with the server schema. Use
  `@EncodeDefault` (or `encodeDefaults = true` on a dedicated Json) for required keys.
- Write a cross-boundary test: take a complete valid payload, delete each key in turn, record which
  ones the server/schema refuses, and assert the client always writes those keys. Validate the
  baseline payload first; an invalid baseline makes every removal look required.
- Unknown fields must survive a read/write round trip if the client edits documents it does not
  fully understand.
- Never put large binary payloads in JSON without a budget; check the server's request-size limit
  before sending and report a refusal by name instead of surfacing an HTTP error.

## Tests

Run `MockEngine` on the test scheduler. Its default dispatcher is a real I/O dispatcher, which puts a
wall clock back into `runTest` and produces hangs that look like flakes:

```kotlin
fun TestScope.testMockEngine(handler: MockRequestHandler): MockEngine =
    MockEngine(MockEngineConfig().apply {
        dispatcher = UnconfinedTestDispatcher(testScheduler)
        addHandler(handler)
    })
```

Cover: success decode, unreadable body, error envelope → typed error, 401 refresh then success,
401 surviving refresh → session cleared, token never sent to a foreign host, cancellation rethrown.

## Connectivity

```kotlin
fun ConnectivityManager.isOnline(): Flow<Boolean> = callbackFlow {
    val active = mutableSetOf<Network>()          // Wi-Fi → mobile handover can send onLost without a new onAvailable
    val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
            if (caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) active += network else active -= network
            trySend(active.isNotEmpty())
        }
        override fun onLost(network: Network) { active -= network; trySend(active.isNotEmpty()) }
    }
    trySend(activeNetwork?.let { getNetworkCapabilities(it)?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) } == true)
    registerNetworkCallback(NetworkRequest.Builder().addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).build(), callback)
    awaitClose { unregisterNetworkCallback(callback) }
}.distinctUntilChanged()
```

- An OkHttp interceptor that fails fast offline must throw an `IOException` subclass
  (`class NoConnectionException : IOException()`); other exception types crash the call.
- A Ktor plugin that checks connectivity receives the checker through its config, not from a global
  service locator.
- Use the online flow to auto-retry a failed first load when the network returns, not to block
  requests (the check can be wrong; the request is the truth).
- Never put tokens or full URLs with query strings into analytics or crash keys.

## Checklist

- [ ] One `HttpClient` from Koin with the engine behind a seam; no second client in a feature.
- [ ] Bearer attached only to the API origin; refresh runs once per 401 and signs out on refresh
      failure; tokens never appear in logs, analytics or crash keys.
- [ ] Every call goes through `safeApiCall` and returns `ApiResult`; UI words errors from stable
      codes (`localization`), never from exception messages.
- [ ] JSON config ignores unknown keys and has explicit nulls policy; DTOs stay in the network
      module and are mapped to domain models.
- [ ] Timeouts, retry and cache plugins are deliberate per endpoint class, not global defaults.
- [ ] `MockEngine` tests cover success, each mapped error, 401→refresh→retry, and offline; they
      run in virtual time and were seen failing once.
- [ ] Printed the real wire bytes for one new endpoint before trusting the serializer
      (`verification-discipline`).
