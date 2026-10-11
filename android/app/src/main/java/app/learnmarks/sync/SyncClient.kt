package app.learnmarks.sync

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.IOException
import java.net.ConnectException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL

/**
 * The laptop's device API (/sync/v1), reached at 127.0.0.1:8765 — a port that `adb reverse`
 * forwards over the USB cable. There is no other address: without the cable nothing connects.
 */
class SyncClient(private val token: () -> String?, private val base: String = "http://127.0.0.1:8765/sync/v1") {

    class SyncError(message: String, val status: Int = 0) : IOException(message)

    fun pair(code: String, deviceId: String, deviceName: String): String =
        call("POST", "/pair", obj("code" to code, "device_id" to deviceId, "device_name" to deviceName), auth = false)
            .jsonObject["device_token"]!!.jsonPrimitive.content

    fun status(): JsonObject = call("GET", "/status").jsonObject

    fun startSession(appVersion: String): String =
        call("POST", "/sessions", obj("transport" to "adb_tunnel", "app_version" to appVersion, "protocol_version" to PROTOCOL))
            .jsonObject["session_id"]!!.jsonPrimitive.content

    fun push(sessionId: String, batchId: String, ops: List<JsonObject>): List<JsonObject> {
        val body = JsonObject(mapOf("session_id" to JsonPrimitive(sessionId), "batch_id" to JsonPrimitive(batchId),
            "ops" to kotlinx.serialization.json.JsonArray(ops)))
        val results = call("POST", "/push", body).jsonObject["results"] as kotlinx.serialization.json.JsonArray
        return results.map { it.jsonObject }
    }

    fun pull(sessionId: String, since: Long, limit: Int = 500): JsonObject =
        call("GET", "/pull?since=$since&limit=$limit&session_id=$sessionId").jsonObject

    fun ack(sessionId: String, seq: Long) {
        call("POST", "/ack", obj("session_id" to sessionId, "acked_seq" to seq))
    }

    fun finish(sessionId: String, outcome: String, error: String?) {
        call("POST", "/sessions/$sessionId/finish", obj("outcome" to outcome, "error" to error?.take(500)))
    }

    private fun call(method: String, path: String, body: JsonObject? = null, auth: Boolean = true): JsonElement {
        val conn = (URL(base + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 5_000
            readTimeout = 60_000
            setRequestProperty("Accept", "application/json")
            if (auth) token()?.let { setRequestProperty("Authorization", "Bearer $it") }
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
            }
        }
        try {
            if (body != null) conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val code = conn.responseCode
            val text = (if (code in 200..299) conn.inputStream else conn.errorStream)?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
            if (code !in 200..299) throw SyncError(problem(text) ?: "The laptop answered $code", code)
            return if (text.isBlank()) JsonObject(emptyMap()) else Json.parseToJsonElement(text)
        } catch (e: ConnectException) {
            throw SyncError(NOT_CONNECTED)
        } catch (e: SocketTimeoutException) {
            throw SyncError("The laptop stopped answering. Check the cable and try again.")
        } finally {
            conn.disconnect()
        }
    }

    private fun problem(text: String): String? = runCatching {
        val o = Json.parseToJsonElement(text).jsonObject
        val title = o["title"]?.jsonPrimitive?.contentOrNull
        val detail = o["detail"]?.jsonPrimitive?.contentOrNull
        listOfNotNull(title, detail).joinToString(". ").ifBlank { null }
    }.getOrNull()

    private fun obj(vararg pairs: Pair<String, Any?>) = JsonObject(pairs.associate { (k, v) ->
        k to when (v) {
            null -> kotlinx.serialization.json.JsonNull
            is Number -> JsonPrimitive(v)
            is Boolean -> JsonPrimitive(v)
            else -> JsonPrimitive(v.toString())
        }
    })

    companion object {
        const val PROTOCOL = 1
        const val NOT_CONNECTED = "Can't reach the laptop. Connect the cable and press “Start USB sync session” on the laptop first."
    }
}
