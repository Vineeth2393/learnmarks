package app.learnmarks.sync

import android.content.Context
import android.os.Build
import app.learnmarks.data.Repository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.longOrNull
import java.util.UUID

/**
 * Sync Now (DESIGN §8):
 *   session → push pending ops (in batches) → apply results → pull pages since the cursor
 *   → re-apply what's still pending → ack → finish.
 *
 * Every step is safe to interrupt: ops leave the outbox only after the laptop answered for them,
 * each pull page is applied in one transaction, and the cursor moves only after a page is stored.
 */
class SyncEngine(context: Context, private val repo: Repository) {
    private val tokens = TokenStore(context)
    private val client = SyncClient({ tokens.get() })
    private val appVersion = runCatching {
        context.packageManager.getPackageInfo(context.packageName, 0).versionName
    }.getOrNull() ?: "?"
    private val mutex = Mutex()

    sealed interface State {
        data object Idle : State
        data class Running(val step: String) : State
        data class Done(val summary: String) : State
        data class Failed(val message: String) : State
    }

    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state
    private val _paired = MutableStateFlow(tokens.get() != null)
    val paired: StateFlow<Boolean> = _paired

    suspend fun pair(code: String): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            val device = repo.ensureDevice()
            val name = listOfNotNull(Build.MANUFACTURER?.replaceFirstChar { it.uppercase() }, Build.MODEL).distinct().joinToString(" ")
            tokens.set(client.pair(code.trim(), device.deviceId, name.take(80)))
            _paired.value = true
        }
    }

    fun unpair() {
        tokens.clear()
        _paired.value = false
    }

    suspend fun syncNow() = withContext(Dispatchers.IO) {
        if (!mutex.tryLock()) return@withContext
        var session: String? = null
        try {
            if (tokens.get() == null) throw SyncClient.SyncError("Pair this phone with the laptop first.")
            _state.value = State.Running("Connecting to the laptop…")
            client.status()
            session = client.startSession(appVersion)

            // 1. Push everything waiting on the phone.
            val ops = repo.opsToPush()
            val tally = Repository.PushTally()
            for ((i, batch) in ops.chunked(200).withIndex()) {
                _state.value = State.Running("Sending changes ${i * 200 + 1}–${i * 200 + batch.size} of ${ops.size}…")
                val results = client.push(session, UUID.randomUUID().toString(), batch.map { repo.opToJson(it) })
                repo.applyPushResults(results, tally)
            }

            // 2. Pull what changed on the laptop, page by page.
            var cursor = repo.pullCursor()
            var received = 0
            while (true) {
                _state.value = State.Running("Receiving updates… $received so far")
                val page = client.pull(session, cursor)
                received += repo.applyPullPage(page)
                cursor = (page["next_seq"] as? JsonPrimitive)?.longOrNull ?: cursor
                if ((page["has_more"] as? JsonPrimitive)?.content != "true") break
            }

            // 3. Re-apply anything still pending, remember where we got to, tell the laptop.
            val summary = buildString {
                append(if (ops.isEmpty()) "Nothing to send" else "Sent ${ops.size}: ${tally.applied} applied")
                if (tally.merged > 0) append(", ${tally.merged} merged")
                if (tally.conflicts > 0) append(", ${tally.conflicts} need a decision on the laptop")
                if (tally.rejected > 0) append(", ${tally.rejected} refused")
                append(" · received $received updates")
            }
            repo.finishPull(cursor, summary)
            client.ack(session, cursor)
            client.finish(session, if (tally.conflicts + tally.rejected > 0) "partial" else "success", null)
            _state.value = State.Done(summary)
        } catch (e: Exception) {
            val message = e.message ?: "Sync failed"
            if (e is SyncClient.SyncError && e.status == 401) unpair()
            session?.let { runCatching { client.finish(it, "failed", message) } }
            repo.recordSyncFailure(message)
            _state.value = State.Failed(message)
        } finally {
            mutex.unlock()
        }
    }
}
