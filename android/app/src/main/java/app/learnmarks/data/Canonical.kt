package app.learnmarks.data

import java.net.URLDecoder
import java.net.URLEncoder

/**
 * URL canonicalisation for duplicate detection (DESIGN §4.1).
 *
 * A line-by-line port of backend/learnmarks/services/canonical.py. Both are tested against
 * shared/url-cases.json, so the phone and the laptop always agree on what "the same post" is.
 */
object Canonical {
    const val MAX_URL_LENGTH = 2048

    private val X_HOSTS = setOf("x.com", "twitter.com", "fxtwitter.com", "vxtwitter.com", "fixupx.com")
    private val TRACKING = setOf("s", "t", "ref", "ref_src", "ref_url", "si", "fbclid", "gclid", "igshid", "mc_cid", "mc_eid")
    private val RESERVED_X = setOf("i", "home", "search", "explore", "settings", "messages", "notifications")

    private val X_STATUS = Regex("^/(?:([A-Za-z0-9_]{1,15})|i(?:/web)?)/status(?:es)?/(\\d{1,25})(?:/|$)")
    private val LI_URN = Regex("urn:li:(activity|share|ugcPost):(\\d{6,25})")
    private val LI_SLUG = Regex("-(activity|share|ugcPost)-(\\d{6,25})-")
    private val BARE_DOMAIN = Regex("^[\\w.-]+\\.[a-z]{2,}(/|$)", RegexOption.IGNORE_CASE)

    // RFC 3986, appendix B: scheme, authority, path, query, fragment.
    private val URI_PARTS = Regex("^(?:([^:/?#]+):)?(?://([^/?#]*))?([^?#]*)(?:\\?([^#]*))?(?:#(.*))?$")

    class InvalidUrl(message: String) : IllegalArgumentException(message)

    data class Result(
        val canonicalUrl: String,
        val sourcePlatform: String, // x | linkedin | other
        val authorHandle: String?,
        val cleanUrl: String,
    )

    fun canonicalize(raw: String?): Result {
        var url = (raw ?: "").trim()
        if (url.isEmpty()) throw InvalidUrl("URL is empty")
        if (url.length > MAX_URL_LENGTH) throw InvalidUrl("URL is longer than $MAX_URL_LENGTH characters")
        if (!url.contains("://") && BARE_DOMAIN.containsMatchIn(url)) url = "https://$url"

        val m = URI_PARTS.matchEntire(url) ?: throw InvalidUrl("Not a URL")
        val scheme = (m.groups[1]?.value ?: "").lowercase()
        if (scheme != "http" && scheme != "https") throw InvalidUrl("Only http and https links can be saved")
        val netloc = m.groups[2]?.value
        val (hostname, port) = splitNetloc(netloc ?: "")
        if (hostname.isNullOrEmpty()) throw InvalidUrl("URL has no host")
        if (url.any { it.isWhitespace() }) throw InvalidUrl("URL contains spaces")
        val path = m.groups[3]?.value ?: ""
        val query = m.groups[4]?.value ?: ""
        val fragment = m.groups[5]?.value ?: ""

        val host = stripHost(hostname)
        var clean = "$scheme://$hostname${if (port != null) ":$port" else ""}${path.ifEmpty { "/" }}"
        if (query.isNotEmpty()) clean += "?$query"
        if (fragment.isNotEmpty()) clean += "#$fragment"

        if (host in X_HOSTS) {
            val sm = X_STATUS.find(path)
            if (sm != null) {
                var handle = sm.groups[1]?.value
                if (handle != null && handle.lowercase() in RESERVED_X) handle = null
                return Result("x:status:${sm.groupValues[2]}", "x", handle, clean)
            }
            return Result(generic(host, path, query), "x", null, clean)
        }
        if (host == "linkedin.com" || host.endsWith(".linkedin.com")) {
            val decoded = unquote(path)
            val lm = LI_URN.find(decoded) ?: LI_SLUG.find(decoded)
            if (lm != null) {
                val kind = if (lm.groupValues[1] == "activity") "activity" else lm.groupValues[1].lowercase()
                return Result("linkedin:$kind:${lm.groupValues[2]}", "linkedin", null, clean)
            }
            return Result(generic("linkedin.com", path, query), "linkedin", null, clean)
        }
        return Result(generic(host, path, query), "other", null, clean)
    }

    /** Duplicate key for a checklist item without a link: its title, ignoring case and spacing (same as the backend). */
    fun noteKey(title: String): String = "note:" + title.lowercase().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")

    /** A link is canonicalised as usual; an item without a link is identified by its title. */
    fun forItem(url: String?, title: String?): Result {
        if (!url.isNullOrBlank()) return canonicalize(url)
        val t = (title ?: "").trim()
        if (t.isEmpty()) throw InvalidUrl("Give a link, or a title for a checklist item without one")
        return Result(noteKey(t), "other", null, "")
    }

    fun defaultTitle(r: Result): String = when (r.sourcePlatform) {
        "x" -> if (r.authorHandle != null) "X post by @${r.authorHandle}" else "X post"
        "linkedin" -> "LinkedIn post"
        else -> splitNetloc(URI_PARTS.matchEntire(r.cleanUrl)?.groups?.get(2)?.value ?: "").first ?: "Link"
    }

    /** First http(s) link in shared text, e.g. "Look at this https://x.com/a/status/1 via @x". */
    fun firstUrl(text: String?): String? =
        Regex("https?://[^\\s<>\"']+", RegexOption.IGNORE_CASE).find(text ?: "")?.value?.trimEnd('.', ',', ')', ']', '!', '?')

    private fun splitNetloc(netloc: String): Pair<String?, Int?> {
        if (netloc.isEmpty()) return null to null
        val hostPort = netloc.substringAfterLast('@')
        if (hostPort.startsWith("[")) { // IPv6 literal
            val end = hostPort.indexOf(']')
            if (end < 0) return null to null
            val port = hostPort.substring(end + 1).removePrefix(":").toIntOrNull()
            return hostPort.substring(1, end).lowercase() to port
        }
        val colon = hostPort.lastIndexOf(':')
        if (colon >= 0) {
            val port = hostPort.substring(colon + 1)
            return hostPort.substring(0, colon).lowercase().ifEmpty { null } to port.toIntOrNull()
        }
        return hostPort.lowercase().ifEmpty { null } to null
    }

    private fun stripHost(hostname: String): String {
        var host = hostname.lowercase().trimEnd('.')
        for (prefix in listOf("www.", "mobile.", "m.")) {
            if (host.startsWith(prefix)) host = host.removePrefix(prefix)
        }
        return host
    }

    private fun generic(host: String, rawPath: String, query: String): String {
        var path = rawPath.ifEmpty { "/" }.replace(Regex("/{2,}"), "/")
        if (path.length > 1) path = path.trimEnd('/')
        val params = query.split('&')
            .filter { it.isNotEmpty() }
            .map { part ->
                val eq = part.indexOf('=')
                if (eq < 0) unquotePlus(part) to "" else unquotePlus(part.substring(0, eq)) to unquotePlus(part.substring(eq + 1))
            }
            .filter { (k, _) -> !k.lowercase().startsWith("utm_") && k.lowercase() !in TRACKING }
            .sortedWith(compareBy<Pair<String, String>> { it.first }.thenBy { it.second })
        val q = params.joinToString("&") { (k, v) -> "${quotePlus(k)}=${quotePlus(v)}" }
        return "url:$host$path" + if (q.isNotEmpty()) "?$q" else ""
    }

    private fun unquote(s: String): String =
        try { URLDecoder.decode(s.replace("+", "%2B"), Charsets.UTF_8) } catch (_: IllegalArgumentException) { s }

    private fun unquotePlus(s: String): String =
        try { URLDecoder.decode(s, Charsets.UTF_8) } catch (_: IllegalArgumentException) { s }

    // Python's quote_plus: like URLEncoder, but keeps "~" and encodes "*".
    private fun quotePlus(s: String): String =
        URLEncoder.encode(s, Charsets.UTF_8).replace("*", "%2A").replace("%7E", "~")
}
