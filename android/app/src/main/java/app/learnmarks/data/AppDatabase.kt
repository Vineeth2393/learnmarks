package app.learnmarks.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [
        BookmarkEntity::class, TopicGroupEntity::class, TopicEntity::class, TagEntity::class,
        BookmarkTopicEntity::class, BookmarkTagEntity::class, OutboxEntity::class,
        SyncStateEntity::class, SyncLogEntity::class, BookmarkFts::class,
    ],
    version = 1,
    exportSchema = true,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun library(): LibraryDao
    abstract fun outbox(): OutboxDao
    abstract fun sync(): SyncDao

    companion object {
        fun open(context: Context): AppDatabase =
            // App-private storage, excluded from cloud backup (res/xml/data_extraction_rules.xml).
            Room.databaseBuilder(context, AppDatabase::class.java, "learnmarks.db").build()
    }
}
