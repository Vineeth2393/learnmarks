package app.learnmarks.data

import androidx.room.Dao
import androidx.room.Embedded
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

/** A bookmark plus what lists need to show next to it. */
data class BookmarkItem(
    @Embedded val b: BookmarkEntity,
    val topicName: String?,
    val topicColor: String?,
    val tagNames: String?,
    /** Has changes on this phone that the laptop hasn't received yet. */
    val pending: Boolean,
)

data class TopicWithCounts(
    @Embedded val t: TopicEntity,
    val total: Int,
    val learned: Int,
    val inProgress: Int,
    val toLearn: Int,
)

data class LinkedTopic(
    @Embedded val t: TopicEntity,
    val linkOrder: Double,
)

data class StatusCount(val status: String, val n: Int)

/** A pending change with the names needed to describe it. */
data class PendingOp(
    @Embedded val op: OutboxEntity,
    val title: String?,
    val targetName: String?,
)

private const val ITEM_COLUMNS = """
    b.*,
    (SELECT t.name FROM bookmark_topics bt JOIN topics t ON t.id = bt.topicId
      WHERE bt.bookmarkId = b.id ORDER BY t.sortOrder LIMIT 1) AS topicName,
    (SELECT t.color FROM bookmark_topics bt JOIN topics t ON t.id = bt.topicId
      WHERE bt.bookmarkId = b.id ORDER BY t.sortOrder LIMIT 1) AS topicColor,
    (SELECT group_concat(g.name, ', ') FROM bookmark_tags x JOIN tags g ON g.id = x.tagId
      WHERE x.bookmarkId = b.id) AS tagNames,
    EXISTS (SELECT 1 FROM outbox o WHERE o.entityId = b.id) AS pending
"""

@Dao
interface LibraryDao {
    // ---------- reads ----------

    @Query("SELECT status, COUNT(*) AS n FROM bookmarks GROUP BY status")
    fun statusCounts(): Flow<List<StatusCount>>

    @Query("SELECT $ITEM_COLUMNS FROM bookmarks b WHERE b.status = 'in_progress' ORDER BY b.statusChangedAt DESC LIMIT 1")
    fun continueItem(): Flow<BookmarkItem?>

    @Query("SELECT $ITEM_COLUMNS FROM bookmarks b WHERE b.status = :status ORDER BY b.priority DESC, b.dateSaved DESC LIMIT :limit")
    fun byStatus(status: String, limit: Int): Flow<List<BookmarkItem>>

    @Query("SELECT $ITEM_COLUMNS FROM bookmarks b ORDER BY b.dateSaved DESC, b.createdAt DESC LIMIT :limit")
    fun recent(limit: Int): Flow<List<BookmarkItem>>

    @Query("SELECT * FROM topic_groups ORDER BY sortOrder")
    fun groups(): Flow<List<TopicGroupEntity>>

    @Query(
        """SELECT t.*,
             COUNT(b.id) AS total,
             COALESCE(SUM(b.status = 'learned'), 0) AS learned,
             COALESCE(SUM(b.status = 'in_progress'), 0) AS inProgress,
             COALESCE(SUM(b.status = 'to_learn'), 0) AS toLearn
           FROM topics t
           LEFT JOIN bookmark_topics bt ON bt.topicId = t.id
           LEFT JOIN bookmarks b ON b.id = bt.bookmarkId
           GROUP BY t.id ORDER BY (SELECT g.sortOrder FROM topic_groups g WHERE g.id = t.groupId) IS NULL, (SELECT g.sortOrder FROM topic_groups g WHERE g.id = t.groupId), t.sortOrder, t.name COLLATE NOCASE"""
    )
    fun topicsWithCounts(): Flow<List<TopicWithCounts>>

    @Query("SELECT * FROM topics WHERE id = :id")
    fun topic(id: String): Flow<TopicEntity?>

    @Query("SELECT $ITEM_COLUMNS FROM bookmarks b JOIN bookmark_topics l ON l.bookmarkId = b.id WHERE l.topicId = :topicId ORDER BY l.sortOrder, b.id")
    fun topicBookmarks(topicId: String): Flow<List<BookmarkItem>>

    @Query("SELECT * FROM bookmarks WHERE id = :id")
    fun bookmark(id: String): Flow<BookmarkEntity?>

    @Query("SELECT * FROM bookmarks WHERE id = :id")
    suspend fun bookmarkNow(id: String): BookmarkEntity?

    @Query("SELECT t.*, l.sortOrder AS linkOrder FROM topics t JOIN bookmark_topics l ON l.topicId = t.id WHERE l.bookmarkId = :id ORDER BY t.sortOrder")
    fun topicsOf(id: String): Flow<List<LinkedTopic>>

    @Query("SELECT g.* FROM tags g JOIN bookmark_tags x ON x.tagId = g.id WHERE x.bookmarkId = :id ORDER BY g.name COLLATE NOCASE")
    fun tagsOf(id: String): Flow<List<TagEntity>>

    /** 1-based place of a bookmark in a topic's learning order. */
    @Query("SELECT COUNT(*) + 1 FROM bookmark_topics WHERE topicId = :topicId AND (sortOrder < :order OR (sortOrder = :order AND bookmarkId < :bookmarkId))")
    suspend fun positionIn(topicId: String, bookmarkId: String, order: Double): Int

    @Query("SELECT * FROM tags ORDER BY name COLLATE NOCASE")
    fun tags(): Flow<List<TagEntity>>

    @Query("SELECT * FROM tags WHERE name = :name COLLATE NOCASE LIMIT 1")
    suspend fun tagByName(name: String): TagEntity?

    // Grouped by track (in track order), then the topic's own order — same as the web dashboard.
    @Query("SELECT t.* FROM topics t ORDER BY (SELECT g.sortOrder FROM topic_groups g WHERE g.id = t.groupId) IS NULL, (SELECT g.sortOrder FROM topic_groups g WHERE g.id = t.groupId), t.sortOrder, t.name COLLATE NOCASE")
    fun topics(): Flow<List<TopicEntity>>

    @Query("SELECT * FROM bookmarks WHERE canonicalUrl = :canonical LIMIT 1")
    suspend fun byCanonical(canonical: String): BookmarkEntity?

    @Query(
        """SELECT $ITEM_COLUMNS FROM bookmarks b
           WHERE (:anyText OR b.id IN (SELECT bookmarkId FROM bookmark_fts WHERE bookmark_fts MATCH :match))
             AND (:anyStatus OR b.status IN (:statuses))
             AND (:anySource OR b.sourcePlatform IN (:sources))
           ORDER BY b.dateSaved DESC, b.createdAt DESC LIMIT 200"""
    )
    fun search(
        match: String, anyText: Boolean,
        statuses: List<String>, anyStatus: Boolean,
        sources: List<String>, anySource: Boolean,
    ): Flow<List<BookmarkItem>>

    @Query("SELECT COUNT(*) FROM bookmarks")
    suspend fun bookmarkCount(): Int

    // ---------- writes ----------

    @Upsert suspend fun upsertBookmark(b: BookmarkEntity)
    @Upsert suspend fun upsertBookmarks(b: List<BookmarkEntity>)
    @Upsert suspend fun upsertGroups(g: List<TopicGroupEntity>)
    @Upsert suspend fun upsertTopics(t: List<TopicEntity>)
    @Upsert suspend fun upsertTags(t: List<TagEntity>)

    @Insert(onConflict = OnConflictStrategy.IGNORE) suspend fun insertTopicLinks(l: List<BookmarkTopicEntity>)
    @Insert(onConflict = OnConflictStrategy.IGNORE) suspend fun insertTagLinks(l: List<BookmarkTagEntity>)

    @Query("DELETE FROM bookmark_topics WHERE bookmarkId = :bookmarkId AND topicId = :topicId")
    suspend fun deleteTopicLink(bookmarkId: String, topicId: String)

    @Query("DELETE FROM bookmark_tags WHERE bookmarkId = :bookmarkId AND tagId = :tagId")
    suspend fun deleteTagLink(bookmarkId: String, tagId: String)

    @Query("SELECT COALESCE(MAX(sortOrder), 0) FROM bookmark_topics WHERE topicId = :topicId")
    suspend fun maxOrder(topicId: String): Double

    @Query("UPDATE bookmarks SET status = :status, statusChangedAt = :at WHERE id = :id")
    suspend fun setStatus(id: String, status: String, at: String)

    @Query("UPDATE bookmarks SET priority = :priority WHERE id = :id")
    suspend fun setPriority(id: String, priority: Int)

    @Query("UPDATE bookmarks SET description = :description WHERE id = :id")
    suspend fun setDescription(id: String, description: String?)

    @Query("DELETE FROM bookmarks WHERE id = :id")
    suspend fun deleteBookmark(id: String)

    @Query("DELETE FROM bookmark_topics WHERE bookmarkId = :id")
    suspend fun deleteTopicLinksOf(id: String)

    @Query("DELETE FROM bookmark_tags WHERE bookmarkId = :id")
    suspend fun deleteTagLinksOf(id: String)

    // Snapshot replacement keeps rows created on this phone (serverVersion = 0 / localOnly).
    @Query("DELETE FROM bookmark_topics WHERE bookmarkId IN (SELECT id FROM bookmarks WHERE serverVersion > 0)")
    suspend fun clearSyncedTopicLinks()
    @Query("DELETE FROM bookmark_tags WHERE bookmarkId IN (SELECT id FROM bookmarks WHERE serverVersion > 0)")
    suspend fun clearSyncedTagLinks()
    @Query("DELETE FROM bookmarks WHERE serverVersion > 0")
    suspend fun clearSyncedBookmarks()
    @Query("DELETE FROM topics")
    suspend fun clearTopics()
    @Query("DELETE FROM topic_groups")
    suspend fun clearGroups()
    @Query("DELETE FROM tags WHERE localOnly = 0")
    suspend fun clearSyncedTags()
    @Query("DELETE FROM bookmark_topics WHERE topicId NOT IN (SELECT id FROM topics)")
    suspend fun dropDanglingTopicLinks()
    @Query("DELETE FROM bookmark_tags WHERE tagId NOT IN (SELECT id FROM tags)")
    suspend fun dropDanglingTagLinks()

    // ---------- sync (DESIGN §8) ----------

    @Query("DELETE FROM topics WHERE id = :id") suspend fun deleteTopicById(id: String)
    @Query("DELETE FROM topic_groups WHERE id = :id") suspend fun deleteGroupById(id: String)
    @Query("DELETE FROM tags WHERE id = :id") suspend fun deleteTagById(id: String)
    @Query("DELETE FROM bookmark_topics WHERE topicId = :topicId") suspend fun deleteLinksForTopic(topicId: String)
    @Query("DELETE FROM bookmark_tags WHERE tagId = :tagId") suspend fun deleteLinksForTag(tagId: String)
    @Query("UPDATE OR IGNORE bookmark_tags SET tagId = :new WHERE tagId = :old") suspend fun retargetTagLinks(old: String, new: String)
    @Query("UPDATE topics SET groupId = NULL WHERE groupId = :groupId") suspend fun ungroup(groupId: String)

    // ---------- full-text index ----------

    @Query("DELETE FROM bookmark_fts")
    suspend fun clearFts()

    @Query("DELETE FROM bookmark_fts WHERE bookmarkId IN (:ids)")
    suspend fun deleteFts(ids: List<String>)

    @Query(
        """INSERT INTO bookmark_fts (bookmarkId, title, description, url, author, topics, tags)
           SELECT b.id, b.title, COALESCE(b.description, ''), b.url, COALESCE(b.authorHandle, ''),
             COALESCE((SELECT group_concat(t.name, ' ') FROM bookmark_topics l JOIN topics t ON t.id = l.topicId WHERE l.bookmarkId = b.id), ''),
             COALESCE((SELECT group_concat(g.name, ' ') FROM bookmark_tags x JOIN tags g ON g.id = x.tagId WHERE x.bookmarkId = b.id), '')
           FROM bookmarks b WHERE b.id IN (:ids)"""
    )
    suspend fun insertFts(ids: List<String>)

    @Query(
        """INSERT INTO bookmark_fts (bookmarkId, title, description, url, author, topics, tags)
           SELECT b.id, b.title, COALESCE(b.description, ''), b.url, COALESCE(b.authorHandle, ''),
             COALESCE((SELECT group_concat(t.name, ' ') FROM bookmark_topics l JOIN topics t ON t.id = l.topicId WHERE l.bookmarkId = b.id), ''),
             COALESCE((SELECT group_concat(g.name, ' ') FROM bookmark_tags x JOIN tags g ON g.id = x.tagId WHERE x.bookmarkId = b.id), '')
           FROM bookmarks b"""
    )
    suspend fun insertAllFts()
}

@Dao
interface OutboxDao {
    @Query("SELECT * FROM outbox ORDER BY createdAt, opId")
    fun all(): Flow<List<OutboxEntity>>

    @Query("SELECT * FROM outbox ORDER BY createdAt, opId")
    suspend fun allNow(): List<OutboxEntity>

    @Query("SELECT COUNT(*) FROM outbox")
    fun count(): Flow<Int>

    @Query(
        """SELECT o.*, COALESCE(b.title, g.name) AS title,
             COALESCE((SELECT name FROM topics WHERE id = o.newValue), (SELECT name FROM tags WHERE id = o.newValue)) AS targetName
           FROM outbox o LEFT JOIN bookmarks b ON b.id = o.entityId LEFT JOIN tags g ON g.id = o.entityId
           ORDER BY o.createdAt, o.opId"""
    )
    fun described(): Flow<List<PendingOp>>

    @Query("SELECT * FROM outbox WHERE entityId = :entityId AND op = :op AND field IS :field AND state = 'pending' LIMIT 1")
    suspend fun findPending(entityId: String, op: String, field: String?): OutboxEntity?

    @Query("SELECT * FROM outbox WHERE entityId = :entityId AND field = :field AND newValue = :target AND op IN ('add_link', 'remove_link') AND state = 'pending' LIMIT 1")
    suspend fun findLinkOp(entityId: String, field: String, target: String): OutboxEntity?

    @Insert suspend fun insert(op: OutboxEntity)
    @Upsert suspend fun upsert(op: OutboxEntity)

    @Query("DELETE FROM outbox WHERE opId = :opId")
    suspend fun delete(opId: String)

    @Query("DELETE FROM outbox WHERE entityId = :entityId")
    suspend fun deleteFor(entityId: String)

    @Query("SELECT * FROM outbox WHERE opId = :opId")
    suspend fun byId(opId: String): OutboxEntity?

    @Query("UPDATE outbox SET state = :state, lastError = :error, attempts = attempts + 1 WHERE opId = :opId")
    suspend fun mark(opId: String, state: String, error: String?)

    @Query("UPDATE outbox SET entityId = :new WHERE entityId = :old")
    suspend fun retargetEntity(old: String, new: String)

    @Query("UPDATE outbox SET newValue = :new WHERE field = 'tags' AND newValue = :old")
    suspend fun retargetTagValue(old: String, new: String)
}

@Dao
interface SyncDao {
    @Query("SELECT * FROM sync_state WHERE id = 1")
    fun state(): Flow<SyncStateEntity?>

    @Query("SELECT * FROM sync_state WHERE id = 1")
    suspend fun stateNow(): SyncStateEntity?

    @Upsert suspend fun upsertState(s: SyncStateEntity)

    @Insert suspend fun log(entry: SyncLogEntity)

    @Query("SELECT * FROM sync_log ORDER BY id DESC LIMIT :limit")
    fun recentLog(limit: Int): Flow<List<SyncLogEntity>>
}
