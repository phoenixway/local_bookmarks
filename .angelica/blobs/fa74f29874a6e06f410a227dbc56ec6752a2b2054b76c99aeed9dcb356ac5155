package com.example.localbookmarks

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import com.example.localbookmarks.data.Bookmark
import com.example.localbookmarks.data.BookmarkDatabase
import com.example.localbookmarks.data.BookmarkRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.jsoup.Jsoup

class ShareReceiverActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (intent?.action == Intent.ACTION_SEND && "text/plain" == intent.type) {
            handleShareIntent(intent)
        } else {
            finish()
        }
    }

    private fun handleShareIntent(intent: Intent) {
        intent.getStringExtra(Intent.EXTRA_TEXT)?.let { sharedText ->
            val url = extractUrl(sharedText)
            if (url != null) {
                CoroutineScope(Dispatchers.IO).launch {
                    val db = BookmarkDatabase.getDatabase(applicationContext)
                    val repository = BookmarkRepository(db.bookmarkDao())

                    val title = try {
                        Jsoup.connect(url).get().title()
                    } catch (e: Exception) {
                        // Fallback to URL if title fetching fails
                        url
                    }

                    val bookmark = Bookmark(
                        title = title,
                        url = url,
                        addingDatetime = System.currentTimeMillis(),
                        comments = "",
                        rating = 0
                    )
                    repository.insert(bookmark)

                    withContext(Dispatchers.Main) {
                        Toast.makeText(applicationContext, "Bookmark added: $title", Toast.LENGTH_SHORT).show()
                        finish() // Finish after toast is shown
                    }
                }
            } else {
                 Toast.makeText(this, "No URL found in shared text", Toast.LENGTH_SHORT).show()
                 finish()
            }
        } ?: finish() // Finish if sharedText is null
    }

    private fun extractUrl(text: String): String? {
        val urlRegex = "(?i)\\b((?:https?|ftp)://[\\w/.-]+(?:\\?[^\\s]*)?)".toRegex()
        return urlRegex.find(text)?.value
    }
}
