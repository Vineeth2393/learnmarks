package app.learnmarks.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import app.learnmarks.data.BookmarkEntity
import app.learnmarks.data.Canonical
import app.learnmarks.data.Repository
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** The "Add" tab: paste a link and save it on the phone. */
@Composable
fun AddScreen(nav: NavHostController) {
    val snack = LocalSnack.current
    Column(Modifier.fillMaxSize()) {
        QuickSaveForm(
            initialUrl = "", sharedText = null, urlEditable = true,
            onSaved = { id -> snack("Saved · reaches the laptop at the next USB sync"); nav.navigate("bookmark/$id") },
            onOpenExisting = { id -> nav.navigate("bookmark/$id") },
            onCancel = null,
        )
    }
}

/** Title suggestion from shared text: the words around the link, if any (LinkedIn shares often include them). */
fun suggestTitle(sharedText: String?, url: String?): String? {
    val t = sharedText ?: return null
    val rest = (if (url != null) t.replace(url, " ") else t).lines().map { it.trim() }.firstOrNull { it.length >= 8 } ?: return null
    return rest.take(120)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun QuickSaveForm(
    initialUrl: String,
    sharedText: String?,
    urlEditable: Boolean,
    onSaved: (String) -> Unit,
    onOpenExisting: (String) -> Unit,
    onCancel: (() -> Unit)?,
) {
    val repo = LocalRepo.current
    val c = LocalLm.current
    val scope = rememberCoroutineScope()
    val topics by repo.topics().collectAsStateWithLifecycle(emptyList())

    var url by rememberSaveable { mutableStateOf(initialUrl) }
    var title by rememberSaveable { mutableStateOf(suggestTitle(sharedText, initialUrl.ifEmpty { null }) ?: "") }
    var picked by rememberSaveable { mutableStateOf(listOf<String>()) }
    var tags by rememberSaveable { mutableStateOf("") }
    var status by rememberSaveable { mutableStateOf("saved") }
    var takeaway by rememberSaveable { mutableStateOf("") }
    var existing by remember { mutableStateOf<BookmarkEntity?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    val parsed = remember(url) { runCatching { Canonical.canonicalize(url) }.getOrNull() }
    LaunchedEffect(url) {
        delay(200)
        existing = if (parsed != null) repo.findByUrl(url) else null
    }

    LazyColumn(Modifier.fillMaxWidth(), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            Row {
                Text("Save to learnmarks", style = Type.title.copy(fontFamily = Mono, fontSize = 15.sp), color = c.ink, modifier = Modifier.weight(1f))
                if (onCancel != null) Text("CANCEL", style = Type.label, color = c.muted, modifier = Modifier.clickable(onClick = onCancel).padding(6.dp))
            }
        }
        item {
            if (urlEditable) {
                OutlinedTextField(
                    url, { url = it.trim(); error = null }, Modifier.fillMaxWidth(),
                    label = { Text("Link", style = Type.bodySmall) }, placeholder = { Text("Paste a link from X or LinkedIn", style = Type.bodySmall) },
                    singleLine = true, textStyle = Type.meta.copy(fontSize = 13.sp), shape = RoundedCornerShape(12.dp),
                )
            }
            Column(
                Modifier.fillMaxWidth().padding(top = if (urlEditable) 8.dp else 0.dp).clip(RoundedCornerShape(12.dp)).background(c.surface)
                    .border(1.dp, c.line, RoundedCornerShape(12.dp)).padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                if (!urlEditable) Text(url, style = Type.meta, color = c.soft, maxLines = 1, overflow = TextOverflow.Ellipsis)
                val e = existing
                when {
                    url.isBlank() -> Text("Paste a link to check it", style = Type.meta, color = c.muted)
                    parsed == null -> Text("Not a link that can be saved (http/https only)", style = Type.meta, color = c.warnInk)
                    e != null -> Row {
                        Text("Already saved · ${STATUS_LABEL[e.status]}", style = Type.meta, color = c.warnInk, modifier = Modifier.weight(1f))
                        Text("Open it →", style = Type.title.copy(fontSize = 13.sp), color = c.ink, modifier = Modifier.clickable { onOpenExisting(e.id) })
                    }
                    else -> Text("✓ ${PLATFORM_LABEL[parsed.sourcePlatform]} post · not saved yet", style = Type.meta, color = c.doneInk)
                }
            }
        }
        item {
            OutlinedTextField(
                title, { title = it.take(300) }, Modifier.fillMaxWidth(), label = { Text("Title", style = Type.bodySmall) },
                placeholder = { Text(parsed?.let { Canonical.defaultTitle(it) } ?: "What is it about?", style = Type.bodySmall) },
                textStyle = Type.body, shape = RoundedCornerShape(12.dp), maxLines = 3,
            )
        }
        if (topics.isNotEmpty()) item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Lbl("Topics")
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (t in topics) ToggleChip(t.name, t.id in picked, {
                        picked = if (t.id in picked) picked - t.id else picked + t.id
                    }, leading = c.pastel(t.color))
                }
            }
        }
        item {
            OutlinedTextField(
                tags, { tags = it.take(200) }, Modifier.fillMaxWidth(), label = { Text("Tags (comma separated)", style = Type.bodySmall) },
                placeholder = { Text("kv-cache, vllm", style = Type.bodySmall) }, singleLine = true, textStyle = Type.body,
                shape = RoundedCornerShape(12.dp),
            )
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Lbl("Status")
                Segmented(listOf("saved" to "Saved", "to_learn" to "To learn", "in_progress" to "Doing", "learned" to "Learned"), status, { status = it })
            }
        }
        item {
            OutlinedTextField(
                takeaway, { takeaway = it.take(2000) }, Modifier.fillMaxWidth(), label = { Text("Takeaway (optional)", style = Type.bodySmall) },
                placeholder = { Text("Why did you save this?", style = Type.bodySmall) }, textStyle = Type.body,
                shape = RoundedCornerShape(12.dp), minLines = 2,
            )
        }
        error?.let { item { Text(it, style = Type.bodySmall, color = c.warnInk) } }
        item {
            LmButton(
                if (busy) "Saving…" else "Save · syncs over USB later",
                onClick = {
                    busy = true
                    scope.launch {
                        val r = repo.create(
                            Repository.NewBookmark(
                                url = url, title = title, status = status, description = takeaway,
                                topicIds = picked, tagNames = tags.split(',', ';').map { it.trim() }.filter { it.isNotEmpty() },
                            )
                        )
                        busy = false
                        when (r) {
                            is Repository.CreateResult.Created -> onSaved(r.id)
                            is Repository.CreateResult.AlreadySaved -> { existing = r.existing; error = "This post is already saved." }
                            is Repository.CreateResult.Invalid -> error = r.message
                        }
                    }
                },
                dark = true, enabled = !busy && parsed != null && existing == null, modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}
