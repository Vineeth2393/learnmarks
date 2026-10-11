package app.learnmarks.ui

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun BookmarkScreen(nav: NavHostController, id: String) {
    val repo = LocalRepo.current
    val c = LocalLm.current
    val snack = LocalSnack.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val bookmark by repo.bookmark(id).collectAsStateWithLifecycle(null)
    val topics by repo.topicsOf(id).collectAsStateWithLifecycle(emptyList())
    val tags by repo.tagsOf(id).collectAsStateWithLifecycle(emptyList())
    val allTopics by repo.topics().collectAsStateWithLifecycle(emptyList())
    val pendingHere by remember(id) { repo.pendingOps().map { ops -> ops.count { it.op.entityId == id } } }.collectAsStateWithLifecycle(0)
    val b = bookmark

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 18.dp, end = 18.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { nav.popBackStack() }) { Icon(LmIcons.back, "Back", tint = c.ink) }
                Lbl(topics.firstOrNull()?.t?.name ?: "Bookmark", Modifier.weight(1f))
            }
        }
        if (b == null) {
            item { Text("This bookmark is no longer on this phone.", style = Type.body, color = c.soft) }
            return@LazyColumn
        }

        item {
            Card(Modifier.fillMaxWidth(), padding = 18.dp) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Lbl(if (b.url.isBlank()) "Checklist item" else "Reading note · ${PLATFORM_LABEL[b.sourcePlatform]} post", Modifier.weight(1f))
                        StatusPill(b.status)
                    }
                    Text(b.title, style = Type.heading.copy(fontSize = 23.sp, lineHeight = 27.sp), color = c.ink)
                    Text(listOfNotNull(b.authorHandle?.let { "@$it" }, "saved ${b.dateSaved}").joinToString(" · "), style = Type.meta, color = c.soft)
                    TakeawayEditor(b.description) { text -> scope.launch { repo.setDescription(id, text) } }
                }
            }
        }

        if (b.serverVersion == 0 || pendingHere > 0) item {
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.todoBg).border(1.dp, c.todoLine, RoundedCornerShape(12.dp)).padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                PendingDot()
                Spacer(Modifier.width(10.dp))
                Text(
                    if (b.serverVersion == 0) "Saved on this phone. It reaches the laptop at the next USB sync."
                    else "Changed on this phone ($pendingHere). It reaches the laptop at the next USB sync.",
                    style = Type.bodySmall, color = c.todoInk, modifier = Modifier.weight(1f),
                )
            }
        }

        item {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Lbl("Learning status")
                for (s in STATUSES) {
                    val on = b.status == s
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .heightIn(min = 48.dp)
                            .clip(RoundedCornerShape(12.dp))
                            .background(if (on) c.inverse else c.surface)
                            .border(1.dp, if (on) c.inverse else c.line, RoundedCornerShape(12.dp))
                            .clickable(role = Role.RadioButton) { scope.launch { repo.setStatus(id, s) } }
                            .semantics { selected = on }
                            .padding(horizontal = 14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box(Modifier.size(10.dp).clip(CircleShape).border(1.5.dp, if (on) c.onInverse else c.sub, CircleShape)
                            .background(if (on) c.onInverse else androidx.compose.ui.graphics.Color.Transparent))
                        Spacer(Modifier.width(12.dp))
                        Text(STATUS_LABEL[s]!!, style = Type.body.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal),
                            color = if (on) c.onInverse else c.ink)
                    }
                }
            }
        }

        item {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Lbl("Priority")
                Segmented(listOf(1 to "Low", 2 to "Medium", 3 to "High"), b.priority, { p -> scope.launch { repo.setPriority(id, p) } })
            }
        }

        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Lbl("Topics")
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (lt in topics) RemovableChip(lt.t.name, c.pastel(lt.t.color)) { scope.launch { repo.removeTopic(id, lt.t.id) } }
                    var open by remember { mutableStateOf(false) }
                    Box {
                        ToggleChip("+ Add topic", false, { open = true })
                        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                            val linked = topics.map { it.t.id }.toSet()
                            for (t in allTopics.filter { it.id !in linked }) {
                                DropdownMenuItem(text = { Text(t.name, style = Type.body) }, onClick = {
                                    open = false
                                    scope.launch { repo.addTopic(id, t.id) }
                                })
                            }
                        }
                    }
                }
            }
        }

        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Lbl("Tags")
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (t in tags) RemovableChip(t.name, null) { scope.launch { repo.removeTag(id, t.id) } }
                }
                var draft by remember { mutableStateOf("") }
                OutlinedTextField(
                    value = draft, onValueChange = { draft = it.take(60) }, singleLine = true,
                    placeholder = { Text("Add a tag", style = Type.bodySmall) }, textStyle = Type.body,
                    shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth(),
                    trailingIcon = {
                        if (draft.isNotBlank()) Text("Add", style = Type.title, color = c.ink,
                            modifier = Modifier.clickable { val name = draft; draft = ""; scope.launch { repo.addTag(id, name) } }.padding(12.dp))
                    },
                    keyboardActions = androidx.compose.foundation.text.KeyboardActions(onDone = {
                        if (draft.isNotBlank()) { val name = draft; draft = ""; scope.launch { repo.addTag(id, name) } }
                    }),
                    keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(imeAction = androidx.compose.ui.text.input.ImeAction.Done),
                )
            }
        }

        if (b.url.isNotBlank()) item {
            LmButton("Open on ${PLATFORM_LABEL[b.sourcePlatform]}", {
                try {
                    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(b.url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                } catch (_: ActivityNotFoundException) {
                    snack("No app can open this link")
                }
            }, dark = true, icon = LmIcons.external, modifier = Modifier.fillMaxWidth())
        }
        if (b.url.isNotBlank()) item { Text("Needs internet only to open the post.", style = Type.meta, color = c.muted, modifier = Modifier.fillMaxWidth()) }

        if (b.serverVersion == 0) item {
            LmButton("Discard (not on the laptop yet)", {
                scope.launch { repo.discardLocal(id); nav.popBackStack(); snack("Discarded") }
            }, modifier = Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun TakeawayEditor(current: String?, onSave: (String?) -> Unit) {
    val c = LocalLm.current
    var editing by remember { mutableStateOf(false) }
    var draft by remember(current) { mutableStateOf(current ?: "") }
    Box(Modifier.fillMaxWidth().padding(top = 4.dp)) {
        if (!editing) {
            Column(Modifier.fillMaxWidth().clickable { editing = true }.padding(vertical = 6.dp)) {
                Text(current ?: "No takeaway yet. Tap to add why you saved this.", style = Type.body.copy(fontSize = 16.sp, lineHeight = 23.sp),
                    color = if (current == null) c.muted else c.sub)
                Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(LmIcons.edit, null, tint = c.muted, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(6.dp))
                    Lbl("Edit takeaway")
                }
            }
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                val focus = remember { FocusRequester() }
                LaunchedEffect(Unit) { focus.requestFocus() }
                OutlinedTextField(draft, { draft = it.take(2000) }, Modifier.fillMaxWidth().focusRequester(focus),
                    textStyle = Type.body, minLines = 3, shape = RoundedCornerShape(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LmButton("Save", { onSave(draft); editing = false }, dark = true, modifier = Modifier.weight(1f))
                    LmButton("Cancel", { draft = current ?: ""; editing = false }, modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun RemovableChip(text: String, swatch: androidx.compose.ui.graphics.Color?, onRemove: () -> Unit) {
    val c = LocalLm.current
    Row(
        Modifier.clip(CircleShape).background(c.surface).border(1.dp, c.lineStrong, CircleShape).padding(start = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (swatch != null) {
            Box(Modifier.size(10.dp).clip(RoundedCornerShape(3.dp)).background(swatch))
            Spacer(Modifier.width(7.dp))
        }
        Text(text, style = Type.bodySmall, color = c.ink)
        IconButton(onClick = onRemove, modifier = Modifier.size(40.dp)) { Icon(LmIcons.close, "Remove $text", tint = c.muted, modifier = Modifier.size(14.dp)) }
    }
}

