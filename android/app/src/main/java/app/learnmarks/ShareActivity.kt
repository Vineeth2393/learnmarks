package app.learnmarks

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.padding
import app.learnmarks.data.Canonical
import app.learnmarks.ui.LearnmarksTheme
import app.learnmarks.ui.LocalLm
import app.learnmarks.ui.LocalRepo
import app.learnmarks.ui.QuickSaveForm
import app.learnmarks.ui.Type

/**
 * Share-to-save (DESIGN §7): X, LinkedIn or a browser shares text containing a link; a sheet
 * opens over that app, the bookmark is saved on the phone and queued for the next USB sync.
 */
class ShareActivity : ComponentActivity() {
    @OptIn(ExperimentalMaterial3Api::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val repo = (application as LearnmarksApp).repository
        val text = listOfNotNull(intent.getStringExtra(Intent.EXTRA_TEXT), intent.getStringExtra(Intent.EXTRA_SUBJECT)).joinToString("\n")
        val url = Canonical.firstUrl(text)

        setContent {
            LearnmarksTheme {
                CompositionLocalProvider(LocalRepo provides repo) {
                    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
                    ModalBottomSheet(onDismissRequest = { finish() }, sheetState = sheet, containerColor = LocalLm.current.canvas) {
                        if (url == null) {
                            Text("No link found in what was shared.", style = Type.body, color = LocalLm.current.ink,
                                modifier = Modifier.padding(24.dp).navigationBarsPadding())
                        } else {
                            QuickSaveForm(
                                initialUrl = url, sharedText = text, urlEditable = false,
                                onSaved = {
                                    Toast.makeText(this@ShareActivity, "Saved · syncs over USB later", Toast.LENGTH_SHORT).show()
                                    finish()
                                },
                                onOpenExisting = { id ->
                                    startActivity(Intent(this@ShareActivity, MainActivity::class.java).putExtra(MainActivity.EXTRA_OPEN, id)
                                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP))
                                    finish()
                                },
                                onCancel = { finish() },
                            )
                        }
                    }
                }
            }
        }
    }
}
