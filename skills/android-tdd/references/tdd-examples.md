# TDD examples by layer

Each example is one red → green step. Setup helpers (`MainDispatcherRule`, `awaitUntil`,
`testMockEngine`) are in `android-testing`.

## Contract suite: the fake and the real implementation pass the same tests

```kotlin
// core/testing/src/commonMain/.../OrdersRepositoryContract.kt (core:testing has kotlin-test and coroutines-test in commonMain)
abstract class OrdersRepositoryContract {
    abstract fun TestScope.newRepository(serverOrders: List<Order>): OrdersRepository

    @Test fun `refresh then observe returns server orders`() = runTest {
        val repo = newRepository(listOf(order("1"), order("2")))
        repo.refresh()
        assertEquals(listOf("1", "2"), repo.observe().first().map { it.id })
    }

    @Test fun `observe before refresh is empty`() = runTest {
        assertEquals(emptyList(), newRepository(listOf(order("1"))).observe().first())
    }
}

// core/testing/src/commonTest/.../FakeOrdersRepositoryTest.kt
class FakeOrdersRepositoryTest : OrdersRepositoryContract() {
    override fun TestScope.newRepository(serverOrders: List<Order>) = FakeOrdersRepository(serverOrders)
}

// core/data/src/commonTest/.../DefaultOrdersRepositoryTest.kt
class DefaultOrdersRepositoryTest : OrdersRepositoryContract() {
    override fun TestScope.newRepository(serverOrders: List<Order>) = DefaultOrdersRepository(
        api = OrdersApi(httpClient(testMockEngine { respondJson(serverOrders.toDto()) })),
        store = InMemoryOrdersStore(),
    )
}
```

When the real repository gets a new behaviour, add the test to the contract first; the fake fails
too, and is fixed in the same change.

## Pure Kotlin: reducer

```kotlin
// red
@Test fun `LoadMore appends next page and keeps selection`() {
    val before = OrdersState(items = listOf(order("a")), selectedId = "a")
    val after = reduce(before, OrdersEvent.PageLoaded(listOf(order("b"))))
    assertEquals(listOf("a", "b"), after.items.map { it.id })
    assertEquals("a", after.selectedId)
}
// green: add the PageLoaded branch to reduce(); nothing else
```

## ViewModel: effect

```kotlin
@Test fun `submit success - navigates back once`() = runTest {
    val vm = EditOrderViewModel(FakeOrdersRepository(), clock = FixedClock(t0))
    vm.effects.test {
        vm.onIntent(EditOrderIntent.Submit)
        assertEquals(EditOrderEffect.NavigateBack, awaitItem())
        expectNoEvents()                                   // double navigation is the usual bug
    }
}
```

## Repository: error mapping with MockEngine

```kotlin
@Test fun `401 on refresh - surfaces SessionExpired, not a generic error`() = runTest {
    val repo = DefaultOrdersRepository(OrdersApi(httpClient(testMockEngine { respondError(HttpStatusCode.Unauthorized) })), InMemoryOrdersStore())
    val error = assertFailsWith<AppError.SessionExpired> { repo.refresh() }
    assertEquals("orders", error.origin)
}
```

Assert **which** failure; `assertFails { }` passes on a serialization crash too.

## Compose UI: shared test for the stateless Ui (KMP)

```kotlin
// feature/orders/src/commonTest/... ; dependency: compose.uiTest (org.jetbrains.compose.ui:ui-test)
@OptIn(ExperimentalTestApi::class)
class OrdersUiTest {
    @Test fun `offline state shows notice and keeps items clickable`() = runComposeUiTest {
        val intents = mutableListOf<OrdersIntent>()
        setContent { AppTheme { OrdersUi(OrdersState(items = listOf(order("1")), isOffline = true), onIntent = { intents += it }) } }
        onNodeWithText("Offline").assertIsDisplayed()
        onNodeWithTag("order-1").performClick()
        assertEquals(listOf<OrdersIntent>(OrdersIntent.Open("1")), intents)
    }
}
```

Android-only modules use `createComposeRule()` with Robolectric in `test`, or in `androidTest` when
real rendering matters. Text from resources, not literals, if the suite runs in other locales.

## Process death: SavedStateHandle

```kotlin
@Test fun `typed note survives process death`() = runTest {
    val saved = SavedStateHandle()
    EditOrderViewModel(FakeOrdersRepository(), saved).onIntent(EditOrderIntent.NoteChanged("call me"))
    val restored = EditOrderViewModel(FakeOrdersRepository(), SavedStateHandle(saved.keys().associateWith { saved.get<Any?>(it) }))
    assertEquals("call me", restored.state.value.note)
}
```

## Room migration (Android host test)

```kotlin
@Test fun `migrate 3 to 4 keeps orders and adds status default`() {
    helper.createDatabase(DB, 3).use { it.execSQL("INSERT INTO orders(id, title) VALUES ('1', 'A')") }
    helper.runMigrationsAndValidate(DB, 4, true, MIGRATION_3_4).use { db ->
        db.query("SELECT status FROM orders WHERE id = '1'").use { c -> c.moveToFirst(); assertEquals("NEW", c.getString(0)) }
    }
}
```

## Characterisation test before touching legacy code

```kotlin
@Test fun `current behaviour - price rounds half down`() {     // wrong per FR-004; pinned until the fix
    assertEquals("1.24", LegacyPriceFormatter().format(1.245))
}
```

Then write the FR-004 test (`rounds half up`), see it fail, flip the characterisation test in the
same commit as the fix.
