---
name: local-persistence
description: Local storage for Android and Kotlin Multiplatform apps - Room 3 (androidx.room3) with KSP and the bundled SQLite driver, DAO and transaction rules, schema export, idempotent migrations and migration tests, how Room 2.x differs and how to move a project to Room 3, DataStore Preferences in common code over a platform path provider, on-disk contracts with installed builds, and a local-first repository with best-effort cloud sync. Use when adding a table, a DAO, a preference or a migration, when upgrading Room, or when building offline/sync behaviour.
metadata:
  last-updated: '2026-11-14'
  keywords:
  - Room 3
  - androidx.room3
  - Room KMP
  - KSP
  - SQLiteDriver
  - DataStore
  - SQLite
  - migrations
  - MigrationTestHelper
  - schema export
  - offline-first
  - sync
---

# Local persistence

Database files and preference files are a contract with every installed build: a name, a column
or a key changes only with a migration and a test that reads what the shipped build wrote. Room
code here targets **Room 3** (`androidx.room3`). HTTP belongs to `ktor-api-client`, file locations
on iOS to `kmp-ios-interop`, test dispatchers to `android-testing`.

## Prerequisites

- Read the version catalog first. `androidx.room3:room3-*` is Room 3 and this file applies as
  written. `androidx.room:room-*` is Room 2.x: use [references/room2.md](references/room2.md) and
  keep the project on its line. Moving to Room 3 is its own change, never part of a feature.
- Room 3 generates Kotlin through **KSP only** and is coroutine-first: a DAO function is `suspend`
  or returns a `Flow`. A blocking one fails every non-Android target ("Only suspend functions are
  allowed in DAOs…") while the Android target still compiles it, so an Android-only build does
  not catch it.
- A `SQLiteDriver` is mandatory. Use `BundledSQLiteDriver` everywhere, so that every platform and
  every OS version runs the same SQLite.
- There is no `SupportSQLiteDatabase`, `Cursor` or executor: migrations and callbacks are
  `suspend` and receive a `SQLiteConnection`.

## Room 3

```kotlin
@Database(entities = [NoteEntity::class], version = 8, exportSchema = true)
@ConstructedBy(AppDatabaseConstructor::class)
abstract class AppDatabase : RoomDatabase() {
    abstract fun noteDao(): NoteDao
    companion object { const val FILE_NAME = "app.db" }
}

// Room generates the actuals; this is the one legitimate expect in the app.
@Suppress("KotlinNoActualForExpect")
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
    @Query("DELETE FROM notes") suspend fun deleteAll()
    @Transaction suspend fun replaceAll(notes: List<NoteEntity>) { deleteAll(); notes.forEach { upsert(it) } }
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
            .addMigrations(MIGRATION_7_8)
            .build()
    }
    override fun database() = instance
}
// iOS: Room.databaseBuilder<AppDatabase>(name = documentsPath(AppDatabase.FILE_NAME)) with the same
// chain; Dispatchers.IO needs `import kotlinx.coroutines.IO` there.
```

Gradle (aliases are yours; the coordinates are `androidx.room3:room3-runtime`, `room3-compiler`,
`room3-testing`, the plugin `androidx.room3`, and `androidx.sqlite:sqlite-bundled`):

```kotlin
plugins { alias(libs.plugins.ksp); alias(libs.plugins.room3) }
room3 { schemaDirectory("$projectDir/schemas") }   // commit the JSON so migrations are diffable in review
kotlin {
    compilerOptions { freeCompilerArgs.add("-Xexpect-actual-classes") }   // the generated actual object
    sourceSets.commonMain.dependencies {
        implementation(libs.room3.runtime)
        implementation(libs.sqlite.bundled)
    }
}
dependencies {
    add("kspAndroid", libs.room3.compiler)
    add("kspIosArm64", libs.room3.compiler)
    add("kspIosSimulatorArm64", libs.room3.compiler)
    // JVM tests of the Android target: the Android artifact has no desktop SQLite binary.
    add("androidHostTestImplementation", libs.sqlite.bundled.jvm)   // androidx.sqlite:sqlite-bundled-jvm
}
```

- Several DAOs in one unit of work: `db.withWriteTransaction { … }` (`androidx.room3`). It rolls
  back when the block throws. Inside one DAO, `@Transaction` on a function with a body.
- `fallbackToDestructiveMigration(dropAllTables = true)` is acceptable only before the first
  public release. After that, every version bump ships a migration and a migration test.
- Converters are `@ColumnTypeConverter` functions in a class listed in `@ColumnTypeConverters`.
  Read enums with `entries.find`, never `valueOf`: a value from a newer build must not crash.
- Exclude KSP output (`/build/generated/`) from detekt and ktlint.

```kotlin
// WRONG: Room 2 habits.
import androidx.room.Dao
@Query("SELECT * FROM notes") fun all(): List<NoteEntity>     // blocking: fails on iOS, blocks a thread on Android
override fun migrate(db: SupportSQLiteDatabase) { … }
@TypeConverter fun toKind(value: String): NoteKind = …
db.withTransaction { … }
// RIGHT
import androidx.room3.Dao
@Query("SELECT * FROM notes") suspend fun all(): List<NoteEntity>
override suspend fun migrate(connection: SQLiteConnection) { … }
@ColumnTypeConverter fun toKind(value: String): NoteKind = …
db.withWriteTransaction { … }
```

### Testing DAOs

Queries run against real SQLite in `commonTest`, on the JVM and on the iOS simulator:

```kotlin
@Test fun `a body rewrite does not reorder the list`() = runTest {
    val db = Room.inMemoryDatabaseBuilder<AppDatabase>().setDriver(BundledSQLiteDriver()).build()
    try {
        val dao = db.noteDao()
        dao.upsert(note("old", updatedAt = 1)); dao.upsert(note("new", updatedAt = 2))
        dao.replaceBody("old", "rewritten")
        assertEquals(listOf("new", "old"), dao.observeAll().first().map { it.id })
    } finally { db.close() }
}
```

`UnsatisfiedLinkError: no sqliteJni` in a JVM test means the `sqlite-bundled-jvm` line above is
missing. Repository and sync tests use a hand-written fake DAO; DAO tests never do.

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
    override suspend fun migrate(connection: SQLiteConnection) {
        connection.addColumnIfMissing("notes", "pinned", "INTEGER NOT NULL DEFAULT 0")
    }
}
private fun SQLiteConnection.addColumnIfMissing(table: String, column: String, definition: String) {
    val exists = prepare("PRAGMA table_info($table)").use { statement ->
        val nameIndex = statement.getColumnNames().indexOf("name")
        generateSequence { if (statement.step()) statement.getText(nameIndex) else null }.any { it == column }
    }
    if (!exists) execSQL("ALTER TABLE $table ADD COLUMN $column $definition")   // import androidx.sqlite.execSQL
}
```

Idempotent steps make a migration safe to re-run after a crash mid-migration. Prefer
`@AutoMigration` for simple changes. Every migration has a test that runs it against the exported
schema with `MigrationTestHelper` and then runs it a second time:
[references/migration-tests.md](references/migration-tests.md) has the test, where it can live
(not in a JVM test of the Android target) and how it finds the schema folder. See it fail once:
delete one statement from the migration and the validation must turn red.

## Uploads and other work queues in Room

A status table (`path PK, status, remote_id, retry_count, updated_at`) observed as a Flow is the UI's
source of truth for background work; WorkManager does the work and updates rows. Insert only if
absent; enqueue only when idle.

## Checklist

- [ ] The catalog was read: the code uses the Room line the project is on, and only one.
- [ ] Every DAO function is `suspend` or returns a `Flow`; the database is built with a driver.
- [ ] The schema JSON for the new version is committed; file names, table names and keys of
      shipped builds are unchanged or migrated.
- [ ] A version bump has a migration, the migration is idempotent, and its test was seen red.
- [ ] DAO tests ran on the JVM and on the iOS simulator; unrun ones are reported as NOT_RUN.
- [ ] A failed network call cannot undo or block a local write.
