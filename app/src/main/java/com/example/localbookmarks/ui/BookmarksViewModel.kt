package com.example.localbookmarks.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.localbookmarks.data.Bookmark
import com.example.localbookmarks.data.BookmarkRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.jsoup.Jsoup
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

class BookmarksViewModel(private val repository: BookmarkRepository) : ViewModel() {

    private val _searchQuery = MutableStateFlow("")
    val searchQuery = _searchQuery.asStateFlow()

    fun onSearchQueryChange(query: String) {
        _searchQuery.value = query
    }

    private var deleteJob: Job? = null

    private val _bookmarkPendingDeletion = MutableStateFlow<Bookmark?>(null)
    val bookmarkPendingDeletion = _bookmarkPendingDeletion.asStateFlow()

    val bookmarks = combine(
        repository.allBookmarks,
        _searchQuery,
        _bookmarkPendingDeletion
    ) { bookmarks, query, pending ->
        val filteredBookmarks = if (query.isBlank()) {
            bookmarks
        } else {
            val queryTags = query.split(" ").filter { it.isNotBlank() }
            bookmarks.filter {
                queryTags.all { queryTag ->
                    it.title.contains(queryTag, ignoreCase = true) ||
                    it.url.contains(queryTag, ignoreCase = true) ||
                    it.comments.contains(queryTag, ignoreCase = true) ||
                    it.tags.any { tag -> tag.contains(queryTag, ignoreCase = true) }
                }
            }
        }
        val nonPendingBookmarks = if (pending != null) filteredBookmarks.filter { it.id != pending.id } else filteredBookmarks
        nonPendingBookmarks
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5000),
        initialValue = emptyList()
    )

    fun addSharedBookmark(url: String) {
        viewModelScope.launch {
            var pageTitle = "New Bookmark"
            try {
                pageTitle = withContext(Dispatchers.IO) {
                    val document = Jsoup.connect(url)
                        .userAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                        .timeout(10000)
                        .get()
                    document.title().takeIf { it.isNotBlank() } ?: url
                }
            } catch (e: Exception) {
                e.printStackTrace()
                pageTitle = url // Fallback to URL instead of "New Bookmark"
            }

            val newBookmark = Bookmark(
                title = pageTitle,
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
        deleteJob?.cancel()
        _bookmarkPendingDeletion.value = bookmark
        deleteJob = viewModelScope.launch {
            delay(7000) // 7 seconds
            _bookmarkPendingDeletion.value?.let {
                repository.delete(it)
            }
            _bookmarkPendingDeletion.value = null
        }
    }

    fun undoDelete() {
        deleteJob?.cancel()
        _bookmarkPendingDeletion.value = null
    }

    fun confirmDelete() {
        deleteJob?.cancel()
        viewModelScope.launch {
            _bookmarkPendingDeletion.value?.let {
                repository.delete(it)
            }
            _bookmarkPendingDeletion.value = null
        }
    }
}
