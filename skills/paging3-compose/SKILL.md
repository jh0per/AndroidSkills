---
name: paging3-compose
description: Paging 3 with Jetpack Compose - network PagingSource with error logging and cancellation safety, refresh keys, duplicate filtering, Pager placement and cachedIn, combining selection without re-paging, LazyPagingItems in grids and staggered grids with skeleton/empty/error/append states, retry versus refresh, and auto-refresh when the network returns. Use when building or debugging an infinite list backed by Paging 3. (For a lightweight hand-rolled list state see compose-ui-practices.)
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Paging 3
  - PagingSource
  - LazyPagingItems
  - load states
  - retry
  - refresh
  - grid
---

# Paging 3 + Compose

Use Paging 3 for long server lists, especially with placeholders, Room caching (`RemoteMediator`) or
multiple consumers. For a bounded list with a "load more", the small `AppListState` in
`compose-ui-practices` is simpler.

## PagingSource

```kotlin
abstract class LoggingPagingSource<K : Any, T : Any>(private val logger: ErrorLogger) : PagingSource<K, T>() {
    protected abstract suspend fun loadPage(params: LoadParams<K>): LoadResult<K, T>

    final override suspend fun load(params: LoadParams<K>): LoadResult<K, T> = try {
        loadPage(params)
    } catch (e: CancellationException) {
        throw e                                          // never turn cancellation into an error state
    } catch (e: Exception) {
        logger.record(e.unwrapBackendException())        // log the original cause, not the wrapper
        LoadResult.Error(e)
    }
}

class OrdersPagingSource(private val api: OrdersApi, logger: ErrorLogger) : LoggingPagingSource<Int, Order>(logger) {
    private val seen = mutableSetOf<String>()            // backends with offset paging can return overlapping pages

    override suspend fun loadPage(params: LoadParams<Int>): LoadResult<Int, Order> {
        val page = params.key ?: 0
        val items = api.orders(page = page, size = params.loadSize).filter { seen.add(it.id) }
        return LoadResult.Page(
            data = items,
            prevKey = if (page > 0) page - 1 else null,
            nextKey = if (items.isEmpty()) null else page + 1,
        )
    }

    // Page-number sources: restart near the anchor. Offset sources that cannot resume: return null (refresh from start).
    override fun getRefreshKey(state: PagingState<Int, Order>): Int? =
        state.anchorPosition?.let { state.closestPageToPosition(it)?.prevKey?.plus(1) ?: state.closestPageToPosition(it)?.nextKey?.minus(1) }
}
```

- Enrich items (e.g. resolve preview URLs) in parallel inside `loadPage` with `coroutineScope { map { async { … } }.awaitAll() }`,
  each with its own timeout and fallback, so one slow item does not fail the page.
- Keep page size and `initialLoadSize` realistic (`PagingConfig(pageSize = 20, initialLoadSize = 40, prefetchDistance = 10)`).
- Wrap HTTP failures in typed exceptions (`NoConnectionException`, `ServerUnavailable`) so the UI can
  choose the message.

## Where the Pager lives

```kotlin
class OrdersViewModel(private val api: OrdersApi, private val logger: ErrorLogger) : ViewModel() {
    private val selected = MutableStateFlow<Set<String>>(emptySet())
    private var source: OrdersPagingSource? = null

    private val pages: Flow<PagingData<Order>> =
        Pager(PagingConfig(pageSize = 20)) { OrdersPagingSource(api, logger).also { source = it } }
            .flow
            .cachedIn(viewModelScope)                    // cache BEFORE combining with fast-changing state

    val items: Flow<PagingData<OrderRow>> = pages.combine(selected) { data, sel ->
        data.map { OrderRow(it, isSelected = it.id in sel) }   // selection changes do not re-page
    }

    fun toggle(id: String) = selected.update { if (id in it) it - id else it + id }
    fun invalidate() = source?.invalidate()              // e.g. after an upload completes
}
```

In Circuit presenters build the `Pager` inside `remember { }` and `cachedIn(rememberCoroutineScope())`
equivalently; never recreate the Pager on recomposition.

## UI

```kotlin
@Composable
fun OrdersGrid(items: LazyPagingItems<OrderRow>, onRetry: () -> Unit = items::retry) {
    val refresh = items.loadState.refresh
    PullToRefreshBox(isRefreshing = refresh is LoadState.Loading && items.itemCount > 0, onRefresh = items::refresh) {
        LazyVerticalGrid(GridCells.Adaptive(160.dp)) {
            when {
                refresh is LoadState.Loading && items.itemCount == 0 -> items(8) { OrderSkeleton() }
                refresh is LoadState.Error && items.itemCount == 0 ->
                    item(span = { GridItemSpan(maxLineSpan) }) { ErrorState(refresh.error, onRetry = items::refresh) }
                refresh is LoadState.NotLoading && items.itemCount == 0 && items.loadState.append.endOfPaginationReached ->
                    item(span = { GridItemSpan(maxLineSpan) }) { EmptyState() }
                else -> {
                    items(items.itemCount, key = items.itemKey { it.order.id }, contentType = items.itemContentType { "order" }) { i ->
                        items[i]?.let { OrderCard(it) } ?: OrderSkeleton()
                    }
                    when (val append = items.loadState.append) {
                        is LoadState.Loading -> item(span = { GridItemSpan(maxLineSpan) }) { AppendSpinner() }
                        is LoadState.Error -> item(span = { GridItemSpan(maxLineSpan) }) { RetryRow(onClick = items::retry) }
                        else -> Unit
                    }
                }
            }
        }
    }
}
```

- `retry()` re-attempts the failed load; `refresh()` reloads from the refresh key. Use retry for
  append errors and refresh for a failed first load (some layouts, e.g. staggered grids, only
  recover reliably with refresh).
- Always pass `key` and `contentType`.
- Error text: "no connection" for `NoConnectionException`, a product sentence otherwise; never a raw
  exception message.
- Staggered grids have no `fillParentMaxSize()`; measure the header (`onGloballyPositioned`) and give
  empty/error items `maxHeight - headerHeight - padding` so they centre.
- Pass the measured cell width to item content so image requests are sized
  (`ImageRequest.Builder(ctx).size(widthPx)`).

## Refresh when the network returns

```kotlin
@Composable
fun <T : Any> RefreshOnReconnect(connectivity: ConnectionChecker, items: LazyPagingItems<T>) {
    LaunchedEffect(connectivity, items) {
        connectivity.isOnline.collectLatest { online ->
            val refresh = items.loadState.refresh
            if (online && refresh is LoadState.Error && refresh.error is NoConnectionException) items.refresh()
        }
    }
}
```

`ConnectionChecker.isOnline` is a `callbackFlow` over `ConnectivityManager.registerDefaultNetworkCallback`
checking `NET_CAPABILITY_VALIDATED`.

## Local items merged with the server list

For optimistic items (uploads in progress), show local tiles before the paged list and remove a
local tile once its id appears in `snapshotFlow { items.itemSnapshotList.items }`. When the local
operation completes, debounce and call `refresh()` (or `invalidate()` on the source) so the server
version replaces it.

## Tests

- `PagingSource.load` with `TestPager` (paging-testing): first page, next page, end of list,
  error → `LoadResult.Error`, cancellation rethrown, duplicates filtered.
- ViewModel: `asSnapshot { scrollTo(index = 50) }` on the flow to assert loaded content.
