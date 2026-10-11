package app.learnmarks.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.learnmarks.data.PendingOp
import app.learnmarks.sync.SyncEngine
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val WHEN = DateTimeFormatter.ofPattern("d MMM, HH:mm").withZone(ZoneId.systemDefault())

private fun fmt(iso: String?): String = iso?.let { runCatching { WHEN.format(Instant.parse(it)) }.getOrNull() } ?: "never"

@Composable
fun SyncScreen() {
    val repo = LocalRepo.current
    val engine = LocalSync.current
    val c = LocalLm.current
    val scope = rememberCoroutineScope()
    val state by repo.syncState().collectAsStateWithLifecycle(null)
    val pending by repo.pendingOps().collectAsStateWithLifecycle(emptyList())
    val log by repo.syncLog().collectAsStateWithLifecycle(emptyList())
    val run by engine.state.collectAsStateWithLifecycle()
    val paired by engine.paired.collectAsStateWithLifecycle()
    val loadExport = rememberExportLoader()
    val waiting = pending.filter { it.op.state == "pending" }
    val needsLaptop = pending.filter { it.op.state == "conflict" }
    val refused = pending.filter { it.op.state == "rejected" }

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Lbl("USB sync · laptop")
            Text("Plug in. Sync.", style = Type.heading, color = c.ink, modifier = Modifier.padding(top = 4.dp))
        }

        item {
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(c.inverse).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Lbl("Last sync · ${fmt(state?.lastSuccessAt)}", Modifier.weight(1f), color = c.inverseMuted)
                    Pill(
                        when (run) { is SyncEngine.State.Running -> "Syncing"; is SyncEngine.State.Failed -> "Failed"; is SyncEngine.State.Done -> "Done"; else -> if (paired) "Paired" else "Not paired" },
                        c.inverse, c.onInverse, c.inverseMuted,
                    )
                }
                Text(
                    when (val r = run) {
                        is SyncEngine.State.Running -> r.step
                        is SyncEngine.State.Done -> r.summary
                        is SyncEngine.State.Failed -> r.message
                        SyncEngine.State.Idle -> if (!paired) "Pair this phone with the laptop to start syncing."
                        else state?.lastResult ?: "Connect the cable, start the session on the laptop, then tap Sync Now."
                    },
                    style = Type.title.copy(fontSize = 17.sp, lineHeight = 23.sp), color = c.onInverse,
                )
                Text("${waiting.size} waiting to send · data from ${state?.lastSnapshotSource ?: "nowhere yet"}",
                    style = Type.meta, color = c.onInverse.copy(alpha = 0.8f))
                if (paired) {
                    LmButton(
                        if (run is SyncEngine.State.Running) "Syncing…" else "Sync Now",
                        { scope.launch { engine.syncNow() } },
                        enabled = run !is SyncEngine.State.Running,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }

        if (!paired) item { PairCard(engine) }

        if (needsLaptop.isNotEmpty()) {
            item { SectionHeader("Needs a decision on the laptop", "${needsLaptop.size}") }
            items(needsLaptop, key = { it.op.opId }) { PendingRow(it) }
        }
        if (refused.isNotEmpty()) {
            item { SectionHeader("Refused by the laptop", "${refused.size}") }
            items(refused, key = { it.op.opId }) { p ->
                PendingRow(p) { scope.launch { repo.dropOp(p.op.opId) } }
            }
        }
        item { SectionHeader("Waiting to send", "${waiting.size}") }
        if (waiting.isEmpty()) item { Text("Nothing waiting. Changes you make on this phone appear here until they're synced.", style = Type.bodySmall, color = c.soft) }
        items(waiting, key = { it.op.opId }) { PendingRow(it) }

        item {
            Card(Modifier.fillMaxWidth(), padding = 16.dp) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Lbl("No cable? Use a file")
                    Text(
                        "On the laptop press Download export, copy the file to this phone and load it here. " +
                            "Your waiting changes are kept; they still need USB sync to reach the laptop.",
                        style = Type.bodySmall, color = c.soft,
                    )
                    LmButton("Load laptop export", loadExport, modifier = Modifier.fillMaxWidth())
                    if (paired) LmButton("Unpair this phone", { engine.unpair() }, modifier = Modifier.fillMaxWidth())
                }
            }
        }
        if (log.isNotEmpty()) {
            item { SectionHeader("History") }
            items(log, key = { it.id }) { entry ->
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                    Text(fmt(entry.at), style = Type.meta, color = c.muted, modifier = Modifier.width(96.dp))
                    Text(entry.summary, style = Type.bodySmall, color = c.sub)
                }
            }
        }
    }
}

@Composable
private fun PairCard(engine: SyncEngine) {
    val c = LocalLm.current
    val scope = rememberCoroutineScope()
    var code by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    Card(Modifier.fillMaxWidth(), padding = 16.dp) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Lbl("Pair with laptop · once")
            Text(
                "1. Connect the cable (USB debugging on).\n2. On the laptop: USB sync → Start USB sync session, then Pair a phone.\n3. Type the code shown there.",
                style = Type.bodySmall, color = c.soft,
            )
            OutlinedTextField(
                code, { code = it.uppercase().take(12); error = null }, Modifier.fillMaxWidth(),
                label = { Text("Pairing code", style = Type.bodySmall) }, placeholder = { Text("ABCD-EFGH", style = Type.bodySmall) },
                singleLine = true, textStyle = Type.headingMono.copy(fontSize = 20.sp), shape = RoundedCornerShape(12.dp),
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters, autoCorrectEnabled = false),
            )
            error?.let { Text(it, style = Type.bodySmall, color = c.warnInk) }
            LmButton(if (busy) "Pairing…" else "Pair", {
                busy = true
                scope.launch {
                    engine.pair(code).onFailure { error = it.message ?: "Pairing failed" }
                    busy = false
                }
            }, dark = true, enabled = !busy && code.count { it.isLetterOrDigit() } >= 8, modifier = Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun PendingRow(p: PendingOp, onRemove: (() -> Unit)? = null) {
    val c = LocalLm.current
    val o = p.op
    val what = when (o.op) {
        "set_field" -> when (o.field) {
            "status" -> "status · ${STATUS_LABEL[o.baseValue] ?: o.baseValue} → ${STATUS_LABEL[o.newValue] ?: o.newValue}"
            "priority" -> "priority · ${PRIORITY_LABEL[o.baseValue?.toIntOrNull()]} → ${PRIORITY_LABEL[o.newValue?.toIntOrNull()]}"
            "description" -> "takeaway edited"
            else -> "${o.field} changed"
        }
        "add_link" -> "added ${if (o.field == "topics") "topic" else "tag"} ${p.targetName ?: ""}"
        "remove_link" -> "removed ${if (o.field == "topics") "topic" else "tag"} ${p.targetName ?: ""}"
        "create_bookmark" -> "new bookmark · saved on phone"
        "create_tag" -> "new tag"
        else -> o.op
    }
    val label = when (o.state) { "conflict" -> "Decide on laptop"; "rejected" -> "Refused"; else -> "Pending" }
    val warn = o.state == "conflict" || o.state == "rejected"
    Card(Modifier.fillMaxWidth(), padding = 12.dp) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(p.title ?: "(removed on the laptop)", style = Type.title.copy(fontSize = 14.sp), color = c.ink, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(what, style = Type.meta, color = c.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Spacer(Modifier.width(10.dp))
                if (warn) Pill(label, c.warnBg, c.warnInk, c.warnLine) else Pill(label, c.todoBg, c.todoInk, c.todoLine)
            }
            if (o.state != "pending" && o.lastError != null) Text(o.lastError, style = Type.bodySmall, color = c.soft)
            if (onRemove != null) Text("REMOVE FROM PHONE", style = Type.label, color = c.ink,
                modifier = Modifier.clickable(onClick = onRemove).padding(vertical = 8.dp))
        }
    }
}

