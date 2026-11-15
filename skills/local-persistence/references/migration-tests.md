# Migration tests with Room 3

One test per migration. It creates the database at the old version from the exported schema,
writes rows with SQL, runs the migration, lets Room validate the result against the new schema
JSON, checks the data, and runs the migration a second time.

## Where the test can live

`MigrationTestHelper` comes from `androidx.room3:room3-testing`, and its constructor differs per
platform:

| Test source set | Constructor | Notes |
|---|---|---|
| `iosTest` (and other native) | `schemaDirectoryPath: String, fileName: String, driver, databaseClass` | Runs on the simulator from the host; call `finished()` after each test |
| Android instrumented | `instrumentation, file, driver, databaseClass` | Reads the schemas from the test APK's assets; a JUnit rule |
| A `jvm()` target's test | `schemaDirectoryPath: Path, databasePath: Path, driver, databaseClass` | A JUnit rule |
| JVM test of the **Android** target | none usable | It resolves the Android artifact, whose helper needs `Instrumentation` |

An app with Android and iOS targets therefore tests migrations in `iosTest` on the simulator, on
every machine that runs the gate, and optionally again as an instrumented test. Add
`room3-testing` to that source set only.

## The test (iosTest)

```kotlin
@OptIn(ExperimentalForeignApi::class)                           // for toKString()
class MigrationTest {
    private val helper = MigrationTestHelper(
        schemaDirectoryPath = checkNotNull(getenv("ROOM_SCHEMAS_DIR")?.toKString()) { "ROOM_SCHEMAS_DIR is not set" },
        fileName = NSTemporaryDirectory() + NSUUID().UUIDString + ".db",
        driver = BundledSQLiteDriver(),
        databaseClass = AppDatabase::class,
    )
    @AfterTest fun close() = helper.finished()

    @Test fun migrate7To8KeepsRowsAndIsSafeToRepeat() = runTest {
        helper.createDatabase(7).use { old ->                   // DAOs expect the newest schema: SQL only
            old.execSQL("INSERT INTO notes (id, title, updated_at, body) VALUES ('a', 'Title', 1, 'Body')")
        }
        helper.runMigrationsAndValidate(8, listOf(MIGRATION_7_8)).use { migrated ->   // validates against 8.json
            val pinned = migrated.prepare("SELECT pinned FROM notes WHERE id = 'a'").use { check(it.step()); it.getLong(0) }
            assertEquals(0L, pinned)
            MIGRATION_7_8.migrate(migrated)                     // a second run after a crash must not fail
        }
    }
}
```

Imports that are easy to miss: `androidx.room3.testing.MigrationTestHelper`,
`androidx.sqlite.execSQL`, `kotlinx.cinterop.toKString`, `platform.posix.getenv`.

## How the test finds the schema folder

The helper reads `<schemaDirectoryPath>/<qualified name of the database class>/<version>.json`
from the host file system, which is the layout the Gradle plugin exports. Pass the folder through
the environment of the test task. The simulator process is started by `simctl`, which forwards
only variables with the `SIMCTL_CHILD_` prefix and strips it:

```kotlin
tasks.withType<org.jetbrains.kotlin.gradle.targets.native.tasks.KotlinNativeTest>().configureEach {
    environment("SIMCTL_CHILD_ROOM_SCHEMAS_DIR", layout.projectDirectory.dir("schemas").asFile.absolutePath)
}
```

Without the prefix the variable does not arrive and the `checkNotNull` above says so, which is
why the message is there.

## Rules

- The schema JSON of **every** shipped version stays in the repository. `createDatabase(7)` needs
  `7.json`; a deleted file cannot be regenerated from the current code.
- Insert rows with literal SQL written in the test. A helper shared with production code would
  migrate together with the bug.
- Make the test fail once before trusting it: delete one statement from the migration and
  `runMigrationsAndValidate` must throw. A migration test that has never been red may be testing
  an empty database.
- A chain test (`createDatabase(oldest shipped)` then every migration in order) catches a
  migration that only works from its direct predecessor. Add it once there are three versions.
- Validation compares the schema, not the data. Assert the values that the migration was written
  to preserve or to fill in.
