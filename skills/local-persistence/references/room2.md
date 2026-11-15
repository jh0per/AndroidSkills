# Room 2.x projects, and moving one to Room 3

`SKILL.md` is written for Room 3 (`androidx.room3`). A project whose catalog has
`androidx.room:room-*` is on Room 2.x. Keep it there until the move is planned as its own change;
everything in `SKILL.md` that is not Room API (DataStore, on-disk contracts, local-first sync,
idempotent migrations, work queues) applies unchanged.

## What differs on Room 2.x

| Topic | Room 2.x (`androidx.room`, multiplatform since 2.7) | Room 3 (`androidx.room3`) |
|---|---|---|
| Artifacts | `androidx.room:room-runtime`, `room-compiler`, `room-testing` | `androidx.room3:room3-runtime`, `room3-compiler`, `room3-testing` |
| Gradle plugin, schema block | `androidx.room`, `room { schemaDirectory(…) }` | `androidx.room3`, `room3 { schemaDirectory(…) }` |
| Imports | `androidx.room.*` | `androidx.room3.*` |
| Code generation | KSP, or kapt on Android-only modules | KSP only, Kotlin output only |
| DAO functions | `suspend` or `Flow` in common code; blocking, `LiveData`, Rx and `Cursor` on Android | `suspend` or `Flow`; a blocking function still compiles for Android only; other reactive types need a `room3-*` converter artifact; no `Cursor` |
| Driver | optional on Android (falls back to SupportSQLite), required elsewhere | always required |
| Migration | `override fun migrate(connection: SQLiteConnection)`; `migrate(db: SupportSQLiteDatabase)` exists on Android only | `override suspend fun migrate(connection: SQLiteConnection)` |
| Callbacks (`onCreate`, `onOpen`) | `SupportSQLiteDatabase` or `SQLiteConnection` | `suspend`, `SQLiteConnection` only |
| Converters | `@TypeConverter`, `@TypeConverters`, `addTypeConverter` | `@ColumnTypeConverter`, `@ColumnTypeConverters`, `addColumnTypeConverter` |
| Transaction outside a DAO | `withTransaction { }` on Android; `useWriterConnection { it.immediateTransaction { } }` in common code | `withWriteTransaction { }`, `withReadTransaction { }` |
| Threads | executors or `setQueryCoroutineContext` | `setQueryCoroutineContext` only |
| Table observers | `InvalidationTracker.Observer` or `createFlow()` | `createFlow()` only |

## Room 2.x forms of the snippets in SKILL.md

The database, entity and DAO declarations are the same with `androidx.room` imports; the builder
chain is the same too. The migration is not `suspend`:

```kotlin
val MIGRATION_7_8 = object : Migration(7, 8) {
    // With a driver set (`setDriver(BundledSQLiteDriver())`) Room calls this overload. The
    // `migrate(db: SupportSQLiteDatabase)` one is Android-only and is not called then.
    override fun migrate(connection: SQLiteConnection) {
        connection.addColumnIfMissing("notes", "pinned", "INTEGER NOT NULL DEFAULT 0")
    }
}
```

`addColumnIfMissing` is the helper from `SKILL.md`: it uses only `androidx.sqlite`, which both
lines share. An Android-only module that has no driver keeps the SupportSQLite form:

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

Do not mix the two in one database: once a driver is set, a migration that overrides only the
SupportSQLite overload does nothing useful. Check which overload each existing migration
overrides before adding a driver to an Android app.

## Moving a project from Room 2.x to Room 3

Plan it as one change with nothing else in it. Order:

1. **Before touching the build**, add a test that opens a database file written by the shipped
   build (copy one from a device, or create it with the shipped schema JSON) and reads a row
   through a DAO. It is the test that will tell you whether the move kept the on-disk contract.
2. Catalog: replace the `androidx.room` artifacts and plugin with the `androidx.room3` ones;
   remove kapt for Room if it was used. Rename `room { }` to `room3 { }`.
3. Imports: `androidx.room.` → `androidx.room3.` across the module.
4. Make every remaining blocking DAO function `suspend`, even where the Android build would
   still accept it; replace `LiveData` and Rx return types with `Flow`, or add the matching
   `room3-*` converter artifact.
5. Migrations and callbacks: add `suspend`, take a `SQLiteConnection`, replace `db.execSQL` with
   `connection.execSQL` (`import androidx.sqlite.execSQL`) and `Cursor` loops with
   `prepare(sql).use { statement -> … }`.
6. Rename converters to `@ColumnTypeConverter` / `@ColumnTypeConverters`.
7. Replace `withTransaction { }` with `withWriteTransaction { }`; remove executor configuration.
8. Code that must keep a `SupportSQLiteDatabase` (a third-party library that takes one) goes
   through `androidx.room3:room3-sqlite-wrapper`; treat it as temporary.
9. Run the test from step 1 and every migration test. Do not bump the schema version in the same
   change: a version bump plus a library move makes a failure impossible to attribute.

Keep the exported schema JSON files and the database file name exactly as they were: installed
builds depend on both.
