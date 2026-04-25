package com.example.localbookmarks.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.localbookmarks.data.Bookmark
import com.example.localbookmarks.data.BookmarkRepository
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class BookmarksViewModel(private val repository: BookmarkRepository) : ViewModel() {

    val bookmarks = repository.allBookmarks.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5000),
        initialValue = emptyList()
    )

    fun addSharedBookmark(url: String) {
        viewModelScope.launch {
            val newBookmark = Bookmark(
                title = "New Bookmark", // Ideally fetched from the web, simplified for now
                url = url,
                addingDatetime = System.currentTimeMillis(),
                comments = "",
                rating = 0
            )
            repository.insert(newBookmark)
        }
    }

    fun updateBookmark(bookmark: Bookmark) {
        viewModelScope.launch {
            repository.update(bookmark)
        }
    }

    fun deleteBookmark(bookmark: Bookmark) {
        viewModelScope.launch {
            repository.delete(bookmark)
        }
    }
}
