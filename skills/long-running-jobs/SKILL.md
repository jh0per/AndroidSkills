---
name: long-running-jobs
description: Client side of server jobs that take seconds to minutes (report generation, media transcoding, imports, batch processing) - validating input against the server's advertised policy, presigned versus multipart uploads without leaking the bearer, creating a job and polling with backoff and a deadline, push notification with polling fallback, cancelling client polling without cancelling the job, account-change guards, downloading results, and one-shot hand-off of bytes between screens. Use when uploading files, starting server jobs, polling status, or exporting results.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - file upload
  - presigned URL
  - multipart
  - job polling
  - backoff
  - background jobs
  - download
---

# Long-running server jobs

## 1. Validate before uploading

Read the server's advertised upload policy (allowed MIME types, max bytes, max decoded pixels,
upload methods) and check locally first: MIME, byte size, and **decoded dimensions** via
`inJustDecodeBounds`. Return a typed rejection the UI words ("file is larger than 25 MB"), not a
generic error after a wasted upload. Re-encode to a budget when appropriate (`media-storage`).

## 2. Upload

```kotlin
suspend fun upload(bytes: ByteArray, mime: String, policy: UploadPolicy): ApiResult<AssetId> = when {
    policy.presigned -> {
        val target = safeApiCall<PresignedTarget>(session) { client.post("/v1/uploads") { setBody(UploadRequest(mime, bytes.size)) } }
            .valueOr { return it }
        // Signed URL: send ONLY the headers the server specified; never our bearer.
        safeApiCall<Unit>(null) {
            client.put(target.url) { headers.clear(); target.headers.forEach { (k, v) -> header(k, v) }; setBody(bytes) }
        }.valueOr { return it }
        safeApiCall<VerifyResponse>(session) { client.post("/v1/uploads/${target.id}/verify") }
            .map { check(it.uploaded) ; target.assetId }
    }
    policy.multipart -> safeApiCall(session) {
        client.submitFormWithBinaryData("/v1/assets", formData {
            append("file", bytes, Headers.build { append(HttpHeaders.ContentType, mime); append(HttpHeaders.ContentDisposition, "filename=\"upload\"") })
        })
    }
    else -> ApiResult.Failure(ApiError.Server(0, "NO_UPLOAD_METHOD", "Upload is not available", null))   // fail loudly, never guess a path
}
```

- The bearer plugin is scoped to the API host (`ktor-api-client`), so a presigned PUT cannot carry it.
- Large files from `content://` URIs: copy to app cache first if the upload may outlive the URI
  grant (background work), then upload from the file.
- Background uploads: WorkManager unique work per file, Room row with status
  (IDLE/UPLOADING/COMPLETE/ERROR) that the UI observes, `setForeground` for large files, real
  progress via `setProgress` (see `media-storage`).

## 3. Create the job, then poll with backoff

```kotlin
suspend fun awaitResult(jobId: String, onProgress: (JobProgress) -> Unit): ApiResult<JobOutcome> {
    var waited = 0L
    var delayMs = 2_000L
    while (waited < 120_000L) {
        delay(delayMs); waited += delayMs; delayMs = (delayMs + 1_000L).coerceAtMost(5_000L)
        val job = safeApiCall<JobDto>(session) { client.get("/v1/jobs/$jobId") }.valueOr { return it }
        onProgress(JobProgress(job.status, job.progress))
        when (job.status) {
            "DONE" -> return download(job.result!!).map { JobOutcome.Done(job.result.assetId, it) }
            "FAILED", "CANCELLED" -> return ApiResult.Success(JobOutcome.Failed(job.error))
        }
    }
    return ApiResult.Success(JobOutcome.TimedOut(jobId))   // the server job keeps running
}
```

- Poll in the screen's scope: leaving the screen cancels **client** polling only. Never send a
  cancel to the server because the person navigated away.
- A timeout is an outcome ("still working; we'll let you know / check your library"), not an error.
- Before each step, confirm the job still belongs to the current account; stop if the account
  changed while polling.
- After a job that costs credits finishes, refresh the balance.

## 4. Push with polling fallback

For jobs that outlive the screen, register for a push ("result ready") and keep polling while the
screen is open; whichever arrives first wins, the other is ignored (dedupe by job id). Persist the
pending job id so the result can be offered after process death or on the next launch
(`push-notifications`). Measure the end-to-end time with a performance trace.

## 5. Download the result

- If the API returns a signed download URL, fetch it **without** the bearer; if the result is
  served by the API itself, with it.
- Save to the gallery or share through MediaStore (`media-storage`), not `DownloadManager` into
  public directories.
- Verify the result is not byte-identical to the input when that would indicate a server mix-up
  (useful in smoke tests).

## 6. Hand-off between screens

Large results (image bytes) never travel in navigation arguments. Use a one-shot holder:

```kotlin
class OneShotHandoff<T : Any> {
    private val pending = AtomicReference<T?>(null)
    fun offer(value: T) { pending.set(value) }
    fun take(): T? = pending.getAndSet(null)          // consumed exactly once
}
// Koin single; offer() before navigate(); the destination calls take() in LaunchedEffect(Unit).
```

If the destination may be restored after process death, persist the payload (file/DB) and pass its id.

## 7. Server-produced downloads

Heavy outputs (PDF statements, data exports, transcoded media) are often produced server-side:
create the job with the chosen format and options, track it as above, then download. Gate premium
options by entitlement before creating the job and return to the same flow after the paywall with
a navigation result. Offer share and save from the finished file; a share prompt cannot tell you
whether the person actually shared.

## Tests

- Validation: each rejection reason, boundary sizes.
- Upload: presigned path sends no `Authorization` header (assert on the MockEngine request), verify
  failure surfaces, no advertised method fails loudly.
- Polling: done, failed, cancelled, timeout returns `TimedOut` with the id, account change stops
  polling; use the test scheduler so delays are virtual (`android-testing`).
