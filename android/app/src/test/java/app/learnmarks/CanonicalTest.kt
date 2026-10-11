package app.learnmarks

import app.learnmarks.data.Canonical
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import java.io.File

/** Runs the same vectors as backend/tests/test_canonical.py (learnmarks/shared/url-cases.json). */
class CanonicalTest {
    private val cases = Json.parseToJsonElement(File(System.getProperty("urlCases")!!).readText()).jsonObject

    @Test
    fun validUrlsMatchTheBackend() {
        val valid = cases["valid"]!!.jsonArray
        check(valid.size > 10)
        for (c in valid) {
            val o = c.jsonObject
            val input = o["in"]!!.jsonPrimitive.content
            val r = Canonical.canonicalize(input)
            assertEquals("canonical of $input", o["canonical"]!!.jsonPrimitive.content, r.canonicalUrl)
            assertEquals("platform of $input", o["platform"]!!.jsonPrimitive.content, r.sourcePlatform)
            val handle = o["handle"]!!.let { if (it is JsonNull) null else it.jsonPrimitive.content }
            assertEquals("handle of $input", handle, r.authorHandle)
        }
    }

    @Test
    fun invalidUrlsAreRejected() {
        for (c in cases["invalid"]!!.jsonArray) {
            val input = c.jsonPrimitive.content
            assertThrows("should reject “$input”", Canonical.InvalidUrl::class.java) { Canonical.canonicalize(input) }
        }
    }

    @Test
    fun defaultTitles() {
        assertEquals("X post by @kmeanskaran", Canonical.defaultTitle(Canonical.canonicalize("https://x.com/kmeanskaran/status/1")))
        assertEquals("X post", Canonical.defaultTitle(Canonical.canonicalize("https://x.com/i/status/1")))
        assertEquals("LinkedIn post", Canonical.defaultTitle(Canonical.canonicalize("https://www.linkedin.com/feed/update/urn:li:activity:7245123456789012345")))
        assertEquals("blog.example.com", Canonical.defaultTitle(Canonical.canonicalize("https://blog.example.com/a")))
    }

    @Test
    fun checklistItemsAreKeyedByTitle() {
        // Must match backend note_key(): "note:" + " ".join(title.lower().split())
        assertEquals("note:two sum", Canonical.forItem("", "  Two   SUM ").canonicalUrl)
        assertEquals("", Canonical.forItem(null, "Two Sum").cleanUrl)
        assertEquals("x:status:1", Canonical.forItem("https://x.com/a/status/1", "ignored").canonicalUrl)
        assertThrows(Canonical.InvalidUrl::class.java) { Canonical.forItem("", "  ") }
    }

    @Test
    fun firstUrlInSharedText() {
        assertEquals("https://x.com/a/status/1", Canonical.firstUrl("Worth reading https://x.com/a/status/1."))
        assertEquals(
            "https://www.linkedin.com/posts/jane_rag-activity-7245123456789012345-AbCd?utm_source=share",
            Canonical.firstUrl("Great post by Jane\nhttps://www.linkedin.com/posts/jane_rag-activity-7245123456789012345-AbCd?utm_source=share"),
        )
        assertEquals(null, Canonical.firstUrl("no link here"))
    }
}
