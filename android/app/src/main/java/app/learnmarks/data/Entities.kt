package app.learnmarks.data

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Fts4
import androidx.room.Index
import androidx.room.PrimaryKey

/*
 * Local copy of the laptop's data (DESIGN §7).
 *
 * The tables hold what the phone *shows*: the laptop's last snapshot with this phone's own
 * pending changes applied on top. Every phone change is also written to `outbox`, together
 * with the value it replaced, until USB sync (Phase 4) hands it to the laptop. When a new
 * snapshot arrives, pending changes are re-applied on top of it, so they are never lost.
 */

@Entity(tableName = "bookmarks", indices = [Index("canonicalUrl"), Index("status"), Index("dateSaved")])
data class BookmarkEntity(
    @PrimaryKey val id: String,
    val url: String,
    val canonicalUrl: String,
    val title: String,
    val sourcePlatform: String,
    val authorHandle: String?,
    val dateSaved: String, // YYYY-MM-DD
    val description: String?,
    val status: String,
    val priority: Int,
    val statusChangedAt: String,
    val createdAt: String,
    /** Version on the laptop when last synced; 0 = created on this phone, not yet on the laptop. */
    val serverVersion: Int,
)

@Entity(tableName = "topic_groups")
data class TopicGroupEntity(
    @PrimaryKey val id: String,
    val name: String,
    val sortOrder: Double,
)

@Entity(tableName = "topics", indices = [Index("groupId")])
data class TopicEntity(
    @PrimaryKey val id: String,
    val name: String,
    val description: String?,
    val color: String,
    val groupId: String?,
    val sortOrder: Double,
    val level: String?,
)

@Entity(tableName = "tags")
data class TagEntity(
    @PrimaryKey val id: String,
    val name: String,
    /** Created on this phone and not yet on the laptop. */
    val localOnly: Boolean = false,
)

@Entity(tableName = "bookmark_topics", primaryKeys = ["bookmarkId", "topicId"], indices = [Index("topicId")])
data class BookmarkTopicEntity(
    val bookmarkId: String,
    val topicId: String,
    val sortOrder: Double,
)

@Entity(tableName = "bookmark_tags", primaryKeys = ["bookmarkId", "tagId"], indices = [Index("tagId")])
data class BookmarkTagEntity(
    val bookmarkId: String,
    val tagId: String,
)

/** One pending phone change (DESIGN §7–8). Removed only after the laptop acknowledges it. */
@Entity(tableName = "outbox", indices = [Index("entityId")])
data class OutboxEntity(
    @PrimaryKey val opId: String,
    val entity: String, // bookmark | tag
    val entityId: String,
    val op: String, // set_field | add_link | remove_link | create_bookmark | create_tag
    val field: String?, // status | priority | description | topics | tags
    val baseValue: String?, // value on the laptop before this change (set_field)
    val newValue: String?, // new value (set_field) or linked id (add_link/remove_link)
    val payload: String?, // JSON for create_* ops
    val baseVersion: Int,
    val createdAt: String,
    val state: String = "pending", // pending | in_flight | conflict | rejected
    val attempts: Int = 0,
    val lastError: String? = null,
)

@Entity(tableName = "sync_state")
data class SyncStateEntity(
    @PrimaryKey val id: Int = 1,
    val deviceId: String,
    val pullCursor: Long = 0,
    val lastSnapshotAt: String? = null, // when laptop data was last loaded (file or sync)
    val lastSnapshotSource: String? = null,
    val lastSuccessAt: String? = null,
    val lastResult: String? = null,
    val lastError: String? = null,
)

@Entity(tableName = "sync_log")
data class SyncLogEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val at: String,
    val kind: String, // file_load | usb_sync
    val summary: String,
)

/** Offline full-text index over everything a search should find. Rebuilt for touched rows. */
@Fts4(notIndexed = ["bookmarkId"])
@Entity(tableName = "bookmark_fts")
data class BookmarkFts(
    @PrimaryKey @ColumnInfo(name = "rowid") val rowId: Int? = null,
    val bookmarkId: String,
    val title: String,
    val description: String,
    val url: String,
    val author: String,
    val topics: String,
    val tags: String,
)
