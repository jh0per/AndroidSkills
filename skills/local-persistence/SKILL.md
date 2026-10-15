---
name: local-persistence
description: Local storage for Android and Kotlin Multiplatform apps - Room KMP with the bundled SQLite driver, DataStore Preferences in common code over a platform path provider, on-disk contracts with installed builds, schema export and migrations, and a local-first repository with best-effort cloud sync. Use when adding a table, a preference, a migration, or offline/sync behaviour.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Room KMP
  - DataStore
  - SQLite
  - migrations
  - schema export
  - offline-first
  - sync
---

# Local persistence

## Room KMP

```kotlin
@Database(entities = [NoteEntity::class], version = 3, exportSchema = true)
@ConstructedBy(AppDatabaseConstructor::class)
abstract class AppDatabase : RoomDatabase() {
    abstract fun noteDao(): NoteDao
    companion object { const val FILE_NAME = "app.db" }
}

// Room generates the actuals; this is the one legitimate expect in the app.
@Suppress("NO_ACTUAL_FOR_EXPECT", "KotlinNoActualForExpect")
expect object AppDatabaseConstructor : RoomDatabaseConstructor<AppDatabase> {
    override fun initialize(): AppDatabase
}

interface DatabaseProvider { fun database(): AppDatabase }   // platform seam via Koin
```

```kotlin
@Entity(tableName = "notes")
data class NoteEntity(
    @PrimaryKey val id: String,
    @ColumnInfo(name = "cloud_id") val cloudId: String? = null,
    val title: String,
    @ColumnInfo(name = "updated_at") val updatedAt: Long,
    @ColumnInfo(name = "body") val body: String,
    @ColumnInfo(name = "pinned") val pinned: Boolean = false,
)

@Dao interface NoteDao {
    @Query("SELECT * FROM notes ORDER BY updated_at DESC") fun observeAll(): Flow<List<NoteEntity>>
    @Query("SELECT * FROM notes WHERE id = :id") suspend fun findById(id: String): NoteEntity?
    @Upsert suspend fun upsert(note: NoteEntity)
    @Query("UPDATE notes SET cloud_id = :cloudId WHERE id = :id") suspend fun linkCloudId(id: String, cloudId: String)
    // A maintenance rewrite touches only its column, so it does not reorder a list sorted by updated_at.
    @Query("UPDATE notes SET body = :body WHERE id = :id") suspend fun replaceBody(id: String, body: String)
    @Query("DELETE FROM notes WHERE id = :id") suspend fun delete(id: String)
}
```

```kotlin
class AndroidDatabaseProvider(private val appContext: Context) : DatabaseProvider {
    @Suppress("InjectDispatcher")
    private val instance by lazy {
        Room.databaseBuilder<AppDatabase>(
            context = appContext,
            name = appContext.getDatabasePath(AppDatabase.FILE_NAME).absolutePath,
        )
            .setDriver(BundledSQLiteDriver())
            .setQueryCoroutineContext(Dispatchers.IO)
            .addMigrations(/* MIGRATION_2_3, … */)
            .build()
    }
    override fun database() = instance
}
// iOS: Room.databaseBuilder<AppDatabase>(name = documentsPath(AppDatabase.FILE_NAME)) with the same chain.
```

Gradle:

```kotlin
plugins { alias(libs.plugins.ksp); alias(libs.plugins.room) }
room { schemaDirectory("$projectDir/schemas") }   // commit the JSON so migrations are diffable in review
dependencies {
    add("kspAndroid", libs.room.compiler)
    add("kspIosArm64", libs.room.compiler)
    add("kspIosSimulatorArm64", libs.room.compiler)
}
```

- `fallbackToDestructiveMigration` is acceptable only before the first public release. After that,
  every version bump ships a migration and a migration test against the exported schema.
- Exclude KSP output (`/build/generated/`) from detekt and ktlint.
- JVM tests use a fake DAO; real SQLite behaviour is covered by an instrumented or iOS-simulator test.

## DataStore Preferences in common code

```kotlin
interface DataStorePathProvider { fun pathFor(name: String): String }   // absolute path incl. ".preferences_pb"

internal fun openPreferences(paths: DataStorePathProvider, name: String, scope: CoroutineScope? = null): DataStore<Preferences> {
    val file = { paths.pathFor(name).toPath() }
    return if (scope == null) PreferenceDataStoreFactory.createWithPath(produceFile = file)
    else PreferenceDataStoreFactory.createWithPath(scope = scope, produceFile = file)
}

private const val THEME_FILE = "settings_prefs"            // on-disk contract: never rename
private val themeKey = stringPreferencesKey("theme_mode")    // on-disk contract: never rename

class DataStoreAppearanceStore(paths: DataStorePathProvider, scope: CoroutineScope? = null) : AppearanceStore {
    private val store = openPreferences(paths, THEME_FILE, scope)
    override suspend fun load(): ThemeMode? =
        store.data.first()[themeKey]?.let { s -> ThemeMode.entries.find { it.name == s } }   // find, not valueOf
    override suspend fun save(mode: ThemeMode) { store.edit { it[themeKey] = mode.name } }
}

class AndroidDataStorePathProvider(private val context: Context) : DataStorePathProvider {
    // Same location the Android `preferencesDataStore` delegate uses, so installed data survives.
    override fun pathFor(name: String) = context.preferencesDataStoreFile(name).absolutePath
}
class IosDataStorePathProvider(private val dir: String = documentsPath("datastore")) : DataStorePathProvider {
    override fun pathFor(name: String) = "$dir/$name.preferences_pb"
}
```

- Each store is a Koin `single`: DataStore allows **one active instance per file**.
- Read enums with `entries.find`, so an unknown value from a newer build reads as null instead of crashing.
- Decide per store whether it is keyed by **device** (UI hints) or by **account** (account-specific
  notices); signing out should not reset what the person holding the phone has learned.
- Three states, not two, for "seen" flags: unknown (still loading), unseen, seen. Collapsing unknown
  into unseen flashes onboarding at everyone who already dismissed it.

### Pin file names and keys with a test

File names and keys are a contract with every installed build. Write the literals in the test,
never import them from production code:

```kotlin
class PreferenceFilesTest {
    private val filesDir = Files.createTempDirectory("files-").toFile()
    private val paths = AndroidDataStorePathProvider(FakeContext(filesDir))
    private val lifetime = SupervisorJob()
    private val scope = CoroutineScope(Dispatchers.IO + lifetime)
    @AfterTest fun cleanup() { runBlocking { lifetime.cancelAndJoin() }; filesDir.deleteRecursively() }

    @Test fun `a value written by the shipped build is still read`() = runBlocking {
        leaveFileFromShippedBuild("settings_prefs") { it[stringPreferencesKey("theme_mode")] = "Dark" }
        assertEquals(ThemeMode.Dark, DataStoreAppearanceStore(paths, scope).load())
    }
    @Test fun `files live where the shipped build put them`() {
        assertEquals(File(filesDir, "datastore/settings_prefs.preferences_pb").absolutePath, paths.pathFor("settings_prefs"))
    }
    // Write with a separate DataStore and cancel its scope before the store under test opens the file.
}
```

Legacy note: `EncryptedSharedPreferences` is deprecated. For secrets prefer DataStore plus a
Keystore-backed key, or avoid storing secrets at all. If an existing app stores JSON in prefs,
keep a mapper that still reads the legacy format.

## Local-first repository + sync

Save locally first; the cloud is best effort; a failed cloud call never undoes a local edit.

```kotlin
class NotesRepository(private val dao: NoteDao, private val newId: () -> String, private val now: () -> Long) {
    fun observe() = dao.observeAll().map { rows -> rows.map(NoteEntity::toSummary) }
    suspend fun save(id: String?, title: String, body: Body): String {
        val noteId = id ?: newId()
        val cloudId = id?.let { dao.findById(it)?.cloudId }           // keep the cloud link
        dao.upsert(body.toEntity(noteId, title, cloudId, now()))
        return noteId
    }
}

class SyncEngine(private val local: NotesRepository, private val cloud: CloudNotesApi, private val session: SessionStore) {
    val lastProblem = MutableStateFlow<SyncProblem?>(null)
    suspend fun pushLocal(localId: String) {
        if (!session.signedIn) return
        val row = local.find(localId) ?: return
        val updated = row.cloudId?.let { cloud.update(it, row) }
        val result = if (updated == null || updated.isNotFound()) cloud.create(row) else updated   // 404 → recreate
        when (result) {
            is ApiResult.Success -> if (row.cloudId != result.value.id) local.linkCloudId(localId, result.value.id)
            is ApiResult.Failure -> lastProblem.value = SyncProblem.Failed(result.error.message)
        }
    }
    suspend fun pushUnsynced(max: Int = 5) =                          // oldest first, bounded per pass
        local.observe().first().filter { it.cloudId == null }.sortedBy { it.updatedAt }.take(max).forEach { pushLocal(it.id) }
}

fun mergeEntries(local: List<Summary>, cloud: List<CloudSummary>): List<Entry> {   // pure, unit-tested
    val linked = local.mapNotNull { it.cloudId }.toSet()
    return (local.map { Entry.fromLocal(it) } + cloud.filterNot { it.id in linked }.map { Entry.fromCloud(it) })
        .sortedByDescending { it.updatedAt }
}
```

- After a local save succeeds and is reported, launch the push in the **app scope** so leaving the
  screen does not cancel it.
- One item that cannot sync must not stop the others; report the refusal that a person can act on
  (e.g. "this note is too large") by name, and say the local copy is safe.
- An unavailable optional endpoint (limits, budgets) is not a refusal; behave as before.
- Delete locally first, then in the cloud.
- Distinguish **empty** from **loading**: wait for both local and cloud replies before saying a
  library is empty.

## Migrations that survive partial failures

```kotlin
val MIGRATION_7_8 = object : Migration(7, 8) {
    override fun migrate(db: SupportSQLiteDatabase) {
        addColumnIfMissing(db, "notes", "pinned", "INTEGER NOT NULL DEFAULT 0")
    }
}
private fun addColumnIfMissing(db: SupportSQLiteDatabase, table: String, column: String, definition: String) {
    val exists = db.query("PRAGMA table_info($table)").use { c ->
        val nameIndex = c.getColumnIndexOrThrow("name"); generateSequence { if (c.moveToNext()) c.getString(nameIndex) else null }.any { it == column }
    }
    if (!exists) db.execSQL("ALTER TABLE $table ADD COLUMN $column $definition")
}
```

Idempotent steps make a migration safe to re-run after a crash mid-migration. Test each migration
with `MigrationTestHelper` against the exported schema. Prefer `@AutoMigration` for simple changes.

## Uploads and other work queues in Room

A status table (`path PK, status, remote_id, retry_count, updated_at`) observed as a Flow is the UI's
source of truth for background work; WorkManager does the work and updates rows. Insert only if
absent; enqueue only when idle.
