package app.learnmarks

import app.learnmarks.data.ExportFile
import app.learnmarks.data.OutboxEntity
import app.learnmarks.data.OutboxPlan
import app.learnmarks.data.OutboxRules
import app.learnmarks.data.Repository
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class OutboxRulesTest {
    private fun op(base: String?, new: String?, kind: String = "set_field") =
        OutboxEntity("op1", "bookmark", "b1", kind, "status", base, new, null, 4, "t")

    @Test
    fun firstChangeRecordsTheLaptopValueAsBase() {
        val plan = OutboxRules.setField(null, "to_learn", "in_progress") { base -> op(base, "in_progress") }
        assertEquals("to_learn", (plan as OutboxPlan.Insert).op.baseValue)
    }

    @Test
    fun noChangeRecordsNothing() {
        assertEquals(OutboxPlan.Nothing, OutboxRules.setField(null, "saved", "saved") { op(it, "saved") })
    }

    @Test
    fun secondChangeMovesTargetAndKeepsOriginalBase() {
        val plan = OutboxRules.setField(op("to_learn", "in_progress"), "in_progress", "learned") { op(it, "learned") }
        val updated = (plan as OutboxPlan.Update).op
        assertEquals("to_learn", updated.baseValue)
        assertEquals("learned", updated.newValue)
    }

    @Test
    fun changingBackToTheLaptopValueCancelsThePendingChange() {
        val plan = OutboxRules.setField(op("to_learn", "in_progress"), "in_progress", "to_learn") { op(it, "to_learn") }
        assertEquals(OutboxPlan.Delete("op1"), plan)
    }

    @Test
    fun addThenRemoveCancelsOut() {
        val add = op(null, "topic1", "add_link")
        assertEquals(OutboxPlan.Delete("op1"), OutboxRules.link(add, "remove_link") { add })
        assertEquals(OutboxPlan.Nothing, OutboxRules.link(add, "add_link") { add })
        assertTrue(OutboxRules.link(null, "add_link") { add } is OutboxPlan.Insert)
    }
}

class FtsQueryTest {
    @Test
    fun wordsBecomePrefixTermsAndOperatorsAreStripped() {
        assertEquals("kv* cache*", Repository.ftsQuery("KV cache"))
        assertEquals("rag* or*", Repository.ftsQuery("\"rag\" OR -"))
        assertNull(Repository.ftsQuery("  \" * ) "))
        assertEquals("context* kv*", Repository.ftsQuery("context ≠ kv"))
    }
}

class ExportFileTest {
    private val id1 = "11111111-1111-4111-8111-111111111111"
    private val id2 = "22222222-2222-4222-8222-222222222222"
    private val topic = "33333333-3333-4333-8333-333333333333"
    private val tag = "44444444-4444-4444-8444-444444444444"

    @Test
    fun readsAnExportAndSkipsBadRows() {
        val json = """
        {"format":"learnmarks","version":1,"exported_at":"2026-10-11T00:00:00Z",
         "groups":[],
         "topics":[{"id":"$topic","name":"RAG","color":"#EFD98A","level":"intermediate","group_id":"missing","sort_order":1000}],
         "tags":[{"id":"$tag","name":"rag"}],
         "bookmarks":[
           {"id":"$id1","url":"https://twitter.com/carol/status/201?s=20","title":"RAG pipelines","date_saved":"2026-09-24",
            "status":"to_learn","priority":3,"version":4,"topics":[{"topic_id":"$topic","sort_order":2000}],"tag_ids":["$tag","nope"]},
           {"id":"$id2","url":"javascript:alert(1)","title":"bad"},
           {"id":"not-a-uuid","url":"https://x.com/a/status/1"}
         ]}"""
        val s = ExportFile.parse(json)
        assertEquals(1, s.bookmarks.size)
        assertEquals(2, s.skipped)
        val b = s.bookmarks.single()
        assertEquals("x:status:201", b.canonicalUrl)
        assertEquals(4, b.serverVersion)
        assertEquals(3, b.priority)
        assertNull(s.topics.single().groupId) // unknown group dropped
        assertEquals(1, s.topicLinks.size)
        assertEquals(1, s.tagLinks.size) // unknown tag id ignored
    }

    @Test
    fun rejectsOtherFiles() {
        assertThrows(ExportFile.Invalid::class.java) { ExportFile.parse("{not json") }
        assertThrows(ExportFile.Invalid::class.java) { ExportFile.parse("""{"tracks":[]}""") }
        assertThrows(ExportFile.Invalid::class.java) { ExportFile.parse("""{"format":"learnmarks","version":2}""") }
        assertThrows(ExportFile.Invalid::class.java) { ExportFile.parse("[1,2]") }
    }
}
