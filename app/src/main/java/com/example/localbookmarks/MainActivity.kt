package com.example.localbookmarks

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.example.localbookmarks.data.BookmarkDatabase
import com.example.localbookmarks.data.BookmarkRepository
import com.example.localbookmarks.ui.BookmarksScreen
import com.example.localbookmarks.ui.BookmarksViewModel
import com.example.localbookmarks.ui.theme.LocalBookmarksTheme

class MainActivity : ComponentActivity() {

    private val db by lazy { BookmarkDatabase.getDatabase(this) }
    private val repository by lazy { BookmarkRepository(db.bookmarkDao()) }

    private val viewModel: BookmarksViewModel by viewModels {
        object : ViewModelProvider.Factory {
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                if (modelClass.isAssignableFrom(BookmarksViewModel::class.java)) {
                    @Suppress("UNCHECKED_CAST")
                    return BookmarksViewModel(repository) as T
                }
                throw IllegalArgumentException("Unknown ViewModel class")
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            LocalBookmarksTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    BookmarksScreen(viewModel = viewModel)
                }
            }
        }
    }
}
