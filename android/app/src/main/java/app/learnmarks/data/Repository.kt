package app.learnmarks.data

import androidx.room.withTransaction
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

/**
 * Everything the screens read and every change they make goes through here.
 *
 * Each phone change updates the tables (so the UI shows it at once), records an outbox op with
 * the value it replaced, and refreshes the search index — all in one transaction (DESIGN §7).
 */
class Repository(private val db: AppDatabase) {
    private val lib = db.library()
    private val outbox = db.outbox()
    private val sync = db.sync()

    // ---------- reads ----------

    fun statusCounts(): Flow<Map<String, Int>> = lib.statusCounts().map { rows -> rows.associate { it.status to it.n } }
    fun continueItem() = lib.continueItem()
    fun byStatus(status: String, limit: Int = 5) = lib.byStatus(status, limit)
    fun recent(limit: Int = 8) = lib.recent(limit)
    fun groups() = lib.groups()
    fun topicsWithCounts() = lib.topicsWithCounts()
    fun topics() = lib.topics()
    fun topic(id: String) = lib.topic(id)
    fun topicBookmarks(topicId: String) = lib.topicBookmarks(topicId)
    fun bookmark(id: String) = lib.bookmark(id)
    fun topicsOf(id: String) = lib.topicsOf(id)
    fun tagsOf(id: String) = lib.tagsOf(id)
    fun tags() = lib.tags()
    fun pendingOps() = outbox.described()
    fun pendingCount() = outbox.count()
    fun syncState() = sync.state()
    fun syncLog() = sync.recentLog(10)

    suspend fun positionIn(topicId: String, bookmarkId: String, order: Double) = lib.positionIn(topicId, bookmarkId, order)

    fun search(text: String, statuses: Set<String>, sources: Set<String>): Flow<List<BookmarkItem>> {
        val match = ftsQuery(text)
        return lib.search(
            match = match ?: "", anyText = match == null,
            statuses = statuses.toList(), anyStatus = statuses.isEmpty(),
            sources = sources.toList(), anySource = sources.isEmpty(),
        )
    }

    suspend fun findByUrl(url: String): BookmarkEntity? =
        try { lib.byCanonical(Canonical.canonicalize(url).canonicalUrl) } catch (_: Canonical.InvalidUrl) { null }

    // ---------- device ----------

    suspend fun ensureDevice(): SyncStateEntity =
        sync.stateNow() ?: SyncStateEntity(deviceId = UUID.randomUUID().toString()).also { sync.upsertState(it) }

    // ---------- edits to existing bookmarks ----------

    suspend fun setStatus(id: String, status: String) = edit(id) { b ->
        lib.setStatus(id, status, now())
        setFieldOp(b, "status", b.status, status)
    }

    suspend fun setPriority(id: String, priority: Int) = edit(id) { b ->
        lib.setPriority(id, priority)
        setFieldOp(b, "priority", b.priority.toString(), priority.toString())
    }

    suspend fun setDescription(id: String, text: String?) = edit(id) { b ->
        val value = text?.trim()?.take(2000)?.ifEmpty { null }
        lib.setDescription(id, value)
        setFieldOp(b, "description", b.description, value)
    }

    suspend fun addTopic(id: String, topicId: String) = edit(id) { b ->
        lib.insertTopicLinks(listOf(BookmarkTopicEntity(id, topicId, lib.maxOrder(topicId) + 1000.0)))
        linkOp(b, "add_link", "topics", topicId)
    }

    suspend fun removeTopic(id: String, topicId: String) = edit(id) { b ->
        lib.deleteTopicLink(id, topicId)
        linkOp(b, "remove_link", "topics", topicId)
    }

    suspend fun addTag(id: String, name: String) = edit(id) { b ->
        val tag = tagFor(name) ?: return@edit
        lib.insertTagLinks(listOf(BookmarkTagEntity(id, tag.id)))
        linkOp(b, "add_link", "tags", tag.id)
    }

    suspend fun removeTag(id: String, tagId: String) = edit(id) { b ->
        lib.deleteTagLink(id, tagId)
        linkOp(b, "remove_link", "tags", tagId)
    }

    /** Wraps an edit: one transaction, then either refresh a phone-created bookmark's create op or record the op. */
    private suspend fun edit(id: String, block: suspend (BookmarkEntity) -> Unit) = db.withTransaction {
        val b = lib.bookmarkNow(id) ?: return@withTransaction
        block(b)
        if (b.serverVersion == 0) refreshCreatePayload(id)
        reindex(listOf(id))
    }

    private suspend fun setFieldOp(b: BookmarkEntity, field: String, current: String?, new: String?) {
        if (b.serverVersion == 0) return // still a pending create; its payload is refreshed instead
        val existing = outbox.findPending(b.id, "set_field", field)
        apply(OutboxRules.setField(existing, current, new) { base ->
            op("bookmark", b.id, "set_field", field, base, new, null, b.serverVersion)
        })
    }

    private suspend fun linkOp(b: BookmarkEntity, op: String, field: String, target: String) {
        if (b.serverVersion == 0) return
        val existing = outbox.findLinkOp(b.id, field, target)
        apply(OutboxRules.link(existing, op) { op("bookmark", b.id, op, field, null, target, null, b.serverVersion) })
    }

    private suspend fun apply(plan: OutboxPlan) = when (plan) {
        is OutboxPlan.Insert -> outbox.insert(plan.op)
        is OutboxPlan.Update -> outbox.upsert(plan.op)
        is OutboxPlan.Delete -> outbox.delete(plan.opId)
        OutboxPlan.Nothing -> Unit
    }

    /** Existing tag with that name, or a new phone-only tag queued as create_tag. */
    private suspend fun tagFor(raw: String): TagEntity? {
        val name = raw.split(Regex("\\s+")).joinToString(" ").trim().take(60)
        if (name.isEmpty()) return null
        lib.tagByName(name)?.let { return it }
        val tag = TagEntity(UUID.randomUUID().toString(), name, localOnly = true)
        lib.upsertTags(listOf(tag))
        val payload = JsonObject(mapOf("id" to JsonPrimitive(tag.id), "name" to JsonPrimitive(name))).toString()
        outbox.insert(op("tag", tag.id, "create_tag", null, null, null, payload, 0))
        return tag
    }

    // ---------- phone-created bookmarks (Share-to-save, Add) ----------

    sealed interface CreateResult {
        data class Created(val id: String) : CreateResult
        data class AlreadySaved(val existing: BookmarkEntity) : CreateResult
        data class Invalid(val message: String) : CreateResult
    }

    data class NewBookmark(
        val url: String,
        val title: String?,
        val status: String = "saved",
        val priority: Int = 2,
        val description: String? = null,
        val topicIds: List<String> = emptyList(),
        val tagNames: List<String> = emptyList(),
    )

    suspend fun create(input: NewBookmark): CreateResult = db.withTransaction {
        val c = try { Canonical.canonicalize(input.url) } catch (e: Canonical.InvalidUrl) {
            return@withTransaction CreateResult.Invalid(e.message ?: "Invalid link")
        }
        lib.byCanonical(c.canonicalUrl)?.let { return@withTransaction CreateResult.AlreadySaved(it) }
        val id = UUID.randomUUID().toString()
        val at = now()
        lib.upsertBookmark(
            BookmarkEntity(
                id = id, url = c.cleanUrl, canonicalUrl = c.canonicalUrl,
                title = input.title?.trim()?.take(300)?.ifEmpty { null } ?: Canonical.defaultTitle(c),
                sourcePlatform = c.sourcePlatform, authorHandle = c.authorHandle, dateSaved = LocalDate.now().toString(),
                description = input.description?.trim()?.take(2000)?.ifEmpty { null }, status = input.status,
                priority = input.priority, statusChangedAt = at, createdAt = at, serverVersion = 0,
            )
        )
        lib.insertTopicLinks(input.topicIds.distinct().map { BookmarkTopicEntity(id, it, lib.maxOrder(it) + 1000.0) })
        lib.insertTagLinks(input.tagNames.mapNotNull { tagFor(it) }.map { BookmarkTagEntity(id, it.id) }.distinct())
        outbox.insert(op("bookmark", id, "create_bookmark", null, null, null, "{}", 0))
        refreshCreatePayload(id)
        reindex(listOf(id))
        CreateResult.Created(id)
    }

    /** Throw away a bookmark that was saved on this phone and never reached the laptop. */
    suspend fun discardLocal(id: String) = db.withTransaction {
        val b = lib.bookmarkNow(id) ?: return@withTransaction
        if (b.serverVersion != 0) return@withTransaction
        lib.deleteTopicLinksOf(id)
        lib.deleteTagLinksOf(id)
        lib.deleteBookmark(id)
        outbox.deleteFor(id)
        lib.deleteFts(listOf(id))
    }

    private suspend fun refreshCreatePayload(id: String) {
        val b = lib.bookmarkNow(id) ?: return
        val existing = outbox.findPending(id, "create_bookmark", null) ?: return
        val topicLinks = db.query("SELECT topicId FROM bookmark_topics WHERE bookmarkId = ?", arrayOf(id)).use { c ->
            buildList { while (c.moveToNext()) add(c.getString(0)) }
        }
        val tagIds = db.query("SELECT tagId FROM bookmark_tags WHERE bookmarkId = ?", arrayOf(id)).use { c ->
            buildList { while (c.moveToNext()) add(c.getString(0)) }
        }
        val payload = JsonObject(
            mapOf(
                "id" to JsonPrimitive(b.id), "url" to JsonPrimitive(b.url), "title" to JsonPrimitive(b.title),
                "date_saved" to JsonPrimitive(b.dateSaved), "status" to JsonPrimitive(b.status),
                "priority" to JsonPrimitive(b.priority),
                "description" to (b.description?.let { JsonPrimitive(it) } ?: JsonNull),
                "topic_ids" to JsonArray(topicLinks.map { JsonPrimitive(it) }),
                "tag_ids" to JsonArray(tagIds.map { JsonPrimitive(it) }),
            )
        ).toString()
        outbox.upsert(existing.copy(payload = payload))
    }

    // ---------- laptop snapshot (export file now; USB sync in Phase 4) ----------

    data class LoadResult(val bookmarks: Int, val topics: Int, val skipped: Int, val pendingKept: Int)

    /**
     * Replace the laptop's data with [snap], keep everything created on this phone, then re-apply
     * every pending change on top so nothing done on the phone is lost.
     */
    suspend fun loadSnapshot(snap: Snapshot, source: String): LoadResult = db.withTransaction {
        lib.clearSyncedTopicLinks()
        lib.clearSyncedTagLinks()
        lib.clearSyncedBookmarks()
        lib.clearTopics()
        lib.clearGroups()
        lib.clearSyncedTags()

        lib.upsertGroups(snap.groups)
        lib.upsertTopics(snap.topics)
        lib.upsertTags(snap.tags)
        lib.upsertBookmarks(snap.bookmarks)
        lib.insertTopicLinks(snap.topicLinks)
        lib.insertTagLinks(snap.tagLinks)
        lib.dropDanglingTopicLinks()
        lib.dropDanglingTagLinks()

        val pending = outbox.allNow()
        for (op in pending) reapply(op)

        lib.clearFts()
        lib.insertAllFts()

        val state = ensureDevice()
        val at = now()
        sync.upsertState(state.copy(lastSnapshotAt = at, lastSnapshotSource = source))
        val result = LoadResult(snap.bookmarks.size, snap.topics.size, snap.skipped, pending.size)
        sync.log(SyncLogEntity(at = at, kind = "file_load",
            summary = "Loaded ${result.bookmarks} bookmarks and ${result.topics} topics from $source" +
                (if (result.skipped > 0) " (${result.skipped} skipped)" else "") +
                (if (pending.isNotEmpty()) "; kept ${pending.size} pending phone changes" else "")))
        result
    }

    private suspend fun reapply(op: OutboxEntity) {
        if (op.entity != "bookmark" || op.op == "create_bookmark" || op.state != "pending") return
        lib.bookmarkNow(op.entityId) ?: return // gone from the laptop: kept in the outbox for Phase 4 to resolve
        when (op.op) {
            "set_field" -> when (op.field) {
                "status" -> lib.setStatus(op.entityId, op.newValue ?: "saved", op.createdAt)
                "priority" -> lib.setPriority(op.entityId, op.newValue?.toIntOrNull() ?: 2)
                "description" -> lib.setDescription(op.entityId, op.newValue)
            }
            "add_link" -> when (op.field) {
                "topics" -> op.newValue?.let { lib.insertTopicLinks(listOf(BookmarkTopicEntity(op.entityId, it, lib.maxOrder(it) + 1000.0))) }
                "tags" -> op.newValue?.let { lib.insertTagLinks(listOf(BookmarkTagEntity(op.entityId, it))) }
            }
            "remove_link" -> when (op.field) {
                "topics" -> op.newValue?.let { lib.deleteTopicLink(op.entityId, it) }
                "tags" -> op.newValue?.let { lib.deleteTagLink(op.entityId, it) }
            }
        }
        lib.dropDanglingTopicLinks()
        lib.dropDanglingTagLinks()
    }

    // ---------- USB sync (DESIGN §8–9; the network part is in sync/SyncEngine) ----------

    /** Pending ops in the order the laptop should see them: new tags, new bookmarks, then edits. */
    suspend fun opsToPush(): List<OutboxEntity> {
        val rank = mapOf("create_tag" to 0, "create_bookmark" to 1)
        return outbox.allNow().sortedWith(compareBy<OutboxEntity> { rank[it.op] ?: 2 }.thenBy { it.createdAt }.thenBy { it.opId })
    }

    data class PushTally(var applied: Int = 0, var merged: Int = 0, var conflicts: Int = 0, var rejected: Int = 0)

    /** Applies the laptop's answer for each op. Ops are removed only once the laptop has taken them. */
    suspend fun applyPushResults(results: List<JsonObject>, tally: PushTally) = db.withTransaction {
        for (r in results) {
            val opId = (r["op_id"] as? JsonPrimitive)?.content ?: continue
            val op = outbox.byId(opId) ?: continue
            val result = (r["result"] as? JsonPrimitive)?.content
            val canonical = (r["canonical_id"] as? JsonPrimitive)?.content
            when (result) {
                "applied", "noop", "merged", "resolved" -> {
                    if (canonical != null && canonical != op.entityId) {
                        if (op.op == "create_tag") remapTag(op.entityId, canonical) else remapBookmark(op.entityId, canonical)
                    }
                    outbox.delete(opId)
                    if (result == "merged") tally.merged++ else tally.applied++
                }
                "conflict" -> {
                    outbox.mark(opId, "conflict", "Changed on both devices — choose on the laptop's USB sync page")
                    tally.conflicts++
                }
                else -> {
                    outbox.mark(opId, "rejected", (r["error"] as? JsonPrimitive)?.content ?: "The laptop couldn't apply this change")
                    tally.rejected++
                }
            }
        }
    }

    /** The laptop merged a phone-created bookmark into one it already had: follow it there. */
    private suspend fun remapBookmark(old: String, new: String) {
        lib.deleteTopicLinksOf(old)
        lib.deleteTagLinksOf(old)
        lib.deleteBookmark(old)
        lib.deleteFts(listOf(old))
        outbox.retargetEntity(old, new)
    }

    private suspend fun remapTag(old: String, new: String) {
        lib.retargetTagLinks(old, new)
        lib.deleteLinksForTag(old)
        lib.deleteTagById(old)
        outbox.retargetTagValue(old, new)
    }

    /** One page from /sync/v1/pull, applied atomically. */
    suspend fun applyPullPage(page: JsonObject): Int = db.withTransaction {
        var n = 0
        fun JsonElement?.str() = (this as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content
        fun JsonElement?.num() = (this as? JsonPrimitive)?.content?.toDoubleOrNull() ?: 0.0
        fun JsonObject.deleted() = (this["deleted"] as? JsonPrimitive)?.content == "true"
        fun list(key: String) = (page[key] as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }

        for (g in list("groups")) {
            val id = g["id"].str() ?: continue
            if (g.deleted()) { lib.ungroup(id); lib.deleteGroupById(id) }
            else lib.upsertGroups(listOf(TopicGroupEntity(id, g["name"].str() ?: "", g["sort_order"].num())))
            n++
        }
        for (t in list("topics")) {
            val id = t["id"].str() ?: continue
            if (t.deleted()) { lib.deleteLinksForTopic(id); lib.deleteTopicById(id) }
            else lib.upsertTopics(listOf(TopicEntity(id, t["name"].str() ?: "", t["description"].str(), t["color"].str() ?: "#D9D9DC",
                t["group_id"].str(), t["sort_order"].num(), t["level"].str())))
            n++
        }
        for (t in list("tags")) {
            val id = t["id"].str() ?: continue
            if (t.deleted()) { lib.deleteLinksForTag(id); lib.deleteTagById(id) }
            else lib.upsertTags(listOf(TagEntity(id, t["name"].str() ?: "", localOnly = false)))
            n++
        }
        for (b in list("bookmarks")) {
            val id = b["id"].str() ?: continue
            n++
            lib.deleteTopicLinksOf(id)
            lib.deleteTagLinksOf(id)
            if (b.deleted()) {
                lib.deleteBookmark(id)
                lib.deleteFts(listOf(id))
                continue
            }
            val c = try { Canonical.forItem(b["url"].str(), b["title"].str()) } catch (_: Canonical.InvalidUrl) { continue }
            lib.upsertBookmark(BookmarkEntity(
                id = id, url = c.cleanUrl, canonicalUrl = c.canonicalUrl, title = b["title"].str() ?: Canonical.defaultTitle(c),
                sourcePlatform = b["source_platform"].str() ?: c.sourcePlatform, authorHandle = b["author_handle"].str(),
                dateSaved = b["date_saved"].str() ?: LocalDate.now().toString(), description = b["description"].str(),
                status = b["status"].str() ?: "saved", priority = b["priority"].num().toInt().coerceIn(1, 3),
                statusChangedAt = b["status_changed_at"].str() ?: "", createdAt = b["created_at"].str() ?: "",
                serverVersion = b["version"].num().toInt().coerceAtLeast(1),
            ))
            val links = (b["topics"] as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }
            lib.insertTopicLinks(links.mapNotNull { l -> l["topic_id"].str()?.let { BookmarkTopicEntity(id, it, l["sort_order"].num()) } })
            lib.insertTagLinks((b["tag_ids"] as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.content }.map { BookmarkTagEntity(id, it) })
        }
        n
    }

    /** After the last page: put pending phone changes back on top, tidy links, rebuild search. */
    suspend fun finishPull(cursor: Long, summary: String) = db.withTransaction {
        for (op in outbox.allNow()) reapply(op)
        lib.dropDanglingTopicLinks()
        lib.dropDanglingTagLinks()
        lib.clearFts()
        lib.insertAllFts()
        val state = ensureDevice()
        val at = now()
        sync.upsertState(state.copy(pullCursor = cursor, lastSuccessAt = at, lastSnapshotAt = at,
            lastSnapshotSource = "USB sync", lastResult = summary, lastError = null))
        sync.log(SyncLogEntity(at = at, kind = "usb_sync", summary = summary))
    }

    suspend fun recordSyncFailure(message: String) {
        val state = ensureDevice()
        sync.upsertState(state.copy(lastError = message, lastResult = "failed"))
        sync.log(SyncLogEntity(at = now(), kind = "usb_sync", summary = "Failed: $message"))
    }

    suspend fun pullCursor(): Long = ensureDevice().pullCursor

    /** Drop a change the laptop refused (shown with its reason on the Sync screen). */
    suspend fun dropOp(opId: String) = outbox.delete(opId)

    fun opToJson(op: OutboxEntity): JsonObject = JsonObject(buildMap {
        put("op_id", JsonPrimitive(op.opId))
        put("entity", JsonPrimitive(op.entity))
        put("entity_id", JsonPrimitive(op.entityId))
        put("op", JsonPrimitive(op.op))
        put("base_version", JsonPrimitive(op.baseVersion))
        put("client_time", JsonPrimitive(op.createdAt))
        op.field?.let { put("field", JsonPrimitive(it)) }
        put("base_value", op.baseValue?.let { JsonPrimitive(it) } ?: JsonNull)
        put("new_value", op.newValue?.let { JsonPrimitive(it) } ?: JsonNull)
        op.payload?.let { put("payload", kotlinx.serialization.json.Json.parseToJsonElement(it)) }
    })

    // ---------- helpers ----------

    private suspend fun reindex(ids: List<String>) {
        lib.deleteFts(ids)
        lib.insertFts(ids)
    }

    private fun op(entity: String, id: String, op: String, field: String?, base: String?, new: String?, payload: String?, version: Int) =
        OutboxEntity(UUID.randomUUID().toString(), entity, id, op, field, base, new, payload, version, now())

    private fun now(): String = Instant.now().toString()

    companion object {
        /** Free text → FTS4 query: every word must match, as a prefix. Quotes and operators are stripped. */
        fun ftsQuery(text: String): String? {
            val words = Regex("[\\p{L}\\p{N}_]+").findAll(text).map { it.value }.take(12).toList()
            // Lower-cased so OR / AND / NOT / NEAR are words, never FTS operators.
            return if (words.isEmpty()) null else words.joinToString(" ") { "${it.lowercase()}*" }
        }
    }
}
