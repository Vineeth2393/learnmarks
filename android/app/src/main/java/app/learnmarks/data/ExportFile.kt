package app.learnmarks.data

import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull

/**
 * Reads a "Download export" file from the web app (Learnmarks format v1) as the laptop's
 * snapshot. Treated as untrusted input: shape, sizes and values are checked, bad rows skipped.
 */
data class Snapshot(
    val groups: List<TopicGroupEntity>,
    val topics: List<TopicEntity>,
    val tags: List<TagEntity>,
    val bookmarks: List<BookmarkEntity>,
    val topicLinks: List<BookmarkTopicEntity>,
    val tagLinks: List<BookmarkTagEntity>,
    val skipped: Int,
    val exportedAt: String?,
)

object ExportFile {
    const val MAX_BYTES = 20 * 1024 * 1024
    private val ID = Regex("^[0-9a-f-]{36}$")
    private val COLOR = Regex("^#[0-9A-Fa-f]{6}$")
    private val DATE = Regex("^\\d{4}-\\d{2}-\\d{2}$")
    private val STATUSES = setOf("saved", "to_learn", "in_progress", "learned")
    private val LEVELS = setOf("beginner", "intermediate", "advanced", "any")

    class Invalid(message: String) : IllegalArgumentException(message)

    fun parse(text: String): Snapshot {
        val root = try {
            Json.parseToJsonElement(text)
        } catch (e: SerializationException) {
            throw Invalid("This file isn't valid JSON.")
        } as? JsonObject ?: throw Invalid("Expected a JSON object.")
        if (root.str("format") != "learnmarks") throw Invalid("This isn't a Learnmarks export. Use “Download export” in the web app.")
        if (root["version"]?.let { (it as? JsonPrimitive)?.intOrNull } != 1) throw Invalid("Unsupported export version.")

        var skipped = 0
        val groups = root.list("groups").mapNotNull { g ->
            val id = g.str("id")?.takeIf { ID.matches(it) } ?: return@mapNotNull null
            TopicGroupEntity(id, g.str("name")?.take(80) ?: return@mapNotNull null, g.num("sort_order"))
        }
        val groupIds = groups.map { it.id }.toSet()
        val topics = root.list("topics").mapNotNull { t ->
            val id = t.str("id")?.takeIf { ID.matches(it) } ?: return@mapNotNull null
            TopicEntity(
                id = id, name = t.str("name")?.take(80) ?: return@mapNotNull null,
                description = t.str("description")?.take(2000),
                color = t.str("color")?.takeIf { COLOR.matches(it) } ?: "#D9D9DC",
                groupId = t.str("group_id")?.takeIf { it in groupIds },
                sortOrder = t.num("sort_order"), level = t.str("level")?.takeIf { it in LEVELS },
            )
        }
        val topicIds = topics.map { it.id }.toSet()
        val tags = root.list("tags").mapNotNull { t ->
            val id = t.str("id")?.takeIf { ID.matches(it) } ?: return@mapNotNull null
            TagEntity(id, t.str("name")?.take(60) ?: return@mapNotNull null)
        }
        val tagIds = tags.map { it.id }.toSet()

        val bookmarks = mutableListOf<BookmarkEntity>()
        val topicLinks = mutableListOf<BookmarkTopicEntity>()
        val tagLinks = mutableListOf<BookmarkTagEntity>()
        for (b in root.list("bookmarks")) {
            val id = b.str("id")?.takeIf { ID.matches(it) }
            val c = try { Canonical.forItem(b.str("url"), b.str("title")) } catch (_: Canonical.InvalidUrl) { null }
            if (id == null || c == null) { skipped++; continue }
            val status = b.str("status")?.takeIf { it in STATUSES } ?: "saved"
            bookmarks += BookmarkEntity(
                id = id, url = c.cleanUrl, canonicalUrl = c.canonicalUrl,
                title = b.str("title")?.take(300)?.ifBlank { null } ?: Canonical.defaultTitle(c),
                sourcePlatform = b.str("source_platform")?.takeIf { it in setOf("x", "linkedin", "other") } ?: c.sourcePlatform,
                authorHandle = b.str("author_handle")?.take(100) ?: c.authorHandle,
                dateSaved = b.str("date_saved")?.takeIf { DATE.matches(it) } ?: "1970-01-01",
                description = b.str("description")?.take(2000),
                status = status,
                priority = (b.field("priority") as? JsonPrimitive)?.intOrNull?.takeIf { it in 1..3 } ?: 2,
                statusChangedAt = b.str("status_changed_at") ?: "",
                createdAt = b.str("created_at") ?: "",
                serverVersion = ((b.field("version") as? JsonPrimitive)?.intOrNull ?: 1).coerceAtLeast(1),
            )
            for (l in b.list("topics")) {
                val tid = l.str("topic_id")?.takeIf { it in topicIds } ?: continue
                topicLinks += BookmarkTopicEntity(id, tid, l.num("sort_order"))
            }
            for (t in (b.field("tag_ids") as? JsonArray).orEmpty()) {
                val tid = (t as? JsonPrimitive)?.content?.takeIf { it in tagIds } ?: continue
                tagLinks += BookmarkTagEntity(id, tid)
            }
        }
        return Snapshot(groups, topics, tags, bookmarks, topicLinks, tagLinks, skipped, root.str("exported_at"))
    }

    private fun JsonElement.field(key: String): JsonElement? = (this as? JsonObject)?.get(key)

    private fun JsonElement.str(key: String): String? =
        ((this as? JsonObject)?.get(key) as? JsonPrimitive)?.takeIf { it !is JsonNull && it.isString }?.content

    private fun JsonElement.num(key: String): Double =
        ((this as? JsonObject)?.get(key) as? JsonPrimitive)?.doubleOrNull ?: 0.0

    private fun JsonElement.list(key: String): List<JsonElement> =
        ((this as? JsonObject)?.get(key) as? JsonArray).orEmpty()
}
