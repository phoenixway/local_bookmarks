package com.example.localbookmarks.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(entities = [Bookmark::class], version = 3, exportSchema = false)
@TypeConverters(Converters::class)
abstract class BookmarkDatabase : RoomDatabase() {

    abstract fun bookmarkDao(): BookmarkDao

    companion object {
        @Volatile
        private var INSTANCE: BookmarkDatabase? = null

        private val MIGRATION_1_3 = object : Migration(1, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                val existingColumns = mutableSetOf<String>()
                db.query("PRAGMA table_info(bookmarks)").use { cursor ->
                    val nameIndex = cursor.getColumnIndex("name")
                    while (cursor.moveToNext()) {
                        existingColumns += cursor.getString(nameIndex)
                    }
                }

                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `bookmarks_new` (
                        `id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                        `title` TEXT NOT NULL,
                        `url` TEXT NOT NULL,
                        `addingDatetime` INTEGER NOT NULL,
                        `comments` TEXT NOT NULL DEFAULT '',
                        `rating` INTEGER NOT NULL DEFAULT 0,
                        `tags` TEXT NOT NULL DEFAULT ''
                    )
                    """.trimIndent()
                )

                val commentsProjection = if ("comments" in existingColumns) "comments" else "''"
                val ratingProjection = if ("rating" in existingColumns) "rating" else "0"
                val tagsProjection = if ("tags" in existingColumns) "tags" else "''"
                val addingDatetimeProjection =
                    if ("addingDatetime" in existingColumns) "addingDatetime" else "0"
                val titleProjection = if ("title" in existingColumns) "title" else "''"
                val urlProjection = if ("url" in existingColumns) "url" else "''"

                db.execSQL(
                    """
                    INSERT INTO `bookmarks_new` (`id`, `title`, `url`, `addingDatetime`, `comments`, `rating`, `tags`)
                    SELECT `id`, $titleProjection, $urlProjection, $addingDatetimeProjection, $commentsProjection, $ratingProjection, $tagsProjection
                    FROM `bookmarks`
                    """.trimIndent()
                )

                db.execSQL("DROP TABLE `bookmarks`")
                db.execSQL("ALTER TABLE `bookmarks_new` RENAME TO `bookmarks`")
            }
        }

        fun getDatabase(context: Context): BookmarkDatabase {
            return INSTANCE ?: synchronized(this) {
                val MIGRATION_2_3 = object : Migration(2, 3) {
                    override fun migrate(db: SupportSQLiteDatabase) {
                        db.execSQL("ALTER TABLE bookmarks ADD COLUMN tags TEXT NOT NULL DEFAULT ''")
                    }
                }

                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    BookmarkDatabase::class.java,
                    "bookmark_database"
                )
                    .addMigrations(MIGRATION_1_3)
                    .addMigrations(MIGRATION_2_3)
                    .build()
                INSTANCE = instance
                instance
            }
        }
    }
}
