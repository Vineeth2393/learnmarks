package app.learnmarks.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController

@Composable
fun SearchScreen(nav: NavHostController) {
    val repo = LocalRepo.current
    val c = LocalLm.current
    var text by rememberSaveable { mutableStateOf("") }
    var statuses by rememberSaveable { mutableStateOf(setOf<String>()) }
    var sources by rememberSaveable { mutableStateOf(setOf<String>()) }
    val flow = remember(text, statuses, sources) { repo.search(text, statuses, sources) }
    val results by flow.collectAsStateWithLifecycle(emptyList())
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { focus.requestFocus() }

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            OutlinedTextField(
                value = text, onValueChange = { text = it },
                modifier = Modifier.fillMaxWidth().focusRequester(focus),
                placeholder = { Text("Titles, takeaways, topics, tags…", style = Type.body) },
                leadingIcon = { Icon(LmIcons.search, null, tint = c.muted) },
                singleLine = true, shape = RoundedCornerShape(14.dp), textStyle = Type.body,
            )
        }
        item {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (s in STATUSES) ToggleChip(STATUS_LABEL[s]!!, s in statuses, { statuses = statuses.toggle(s) })
                for (p in listOf("x", "linkedin")) ToggleChip(PLATFORM_LABEL[p]!!, p in sources, { sources = sources.toggle(p) })
            }
        }
        item {
            Lbl(
                when {
                    text.isBlank() && statuses.isEmpty() && sources.isEmpty() -> "Newest first · works offline"
                    results.size >= 200 -> "First 200 matches"
                    else -> "${results.size} found"
                }
            )
        }
        if (results.isEmpty() && text.isNotBlank()) item {
            Text("Nothing matches. Every word must match the start of a word in a title, takeaway, topic or tag.", style = Type.body, color = c.soft)
        }
        items(results, key = { it.b.id }) { BookmarkRow(it, onClick = { nav.navigate("bookmark/${it.b.id}") }) }
    }
}

fun <T> Set<T>.toggle(v: T): Set<T> = if (v in this) this - v else this + v
