package com.example.localbookmarks.ui

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.localbookmarks.data.Bookmark
import kotlinx.coroutines.launch
import org.jsoup.Jsoup
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BookmarksScreen(viewModel: BookmarksViewModel) {
    val bookmarks by viewModel.bookmarks.collectAsState()
    val searchQuery by viewModel.searchQuery.collectAsState()

    var editingBookmark by remember { mutableStateOf<Bookmark?>(null) }
    val context = LocalContext.current

    val snackbarHostState = remember { SnackbarHostState() }
    val bookmarkPendingDeletion by viewModel.bookmarkPendingDeletion.collectAsState()

    LaunchedEffect(bookmarkPendingDeletion) {
        if (bookmarkPendingDeletion != null) {
            val result =
                snackbarHostState.showSnackbar(
                    message = "Bookmark deleted",
                    actionLabel = "Undo",
                    duration = SnackbarDuration.Long,
                )

            if (result == SnackbarResult.ActionPerformed) {
                viewModel.undoDelete()
            }
        }
    }

    BackHandler(enabled = searchQuery.isNotBlank()) {
        viewModel.onSearchQueryChange("")
    }

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        snackbarHost = { SnackbarHost(hostState = snackbarHostState) },
        contentWindowInsets = WindowInsets(0.dp),
    ) {
        Box(modifier = Modifier.fillMaxSize()) {
            Column(modifier = Modifier.fillMaxSize()) {
                SearchBar(
                    query = searchQuery,
                    onQueryChange = viewModel::onSearchQueryChange,
                    onClear = { viewModel.onSearchQueryChange("") },
                )

                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding =
                        PaddingValues(
                            start = 16.dp,
                            end = 16.dp,
                            bottom = 20.dp,
                        ),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    items(bookmarks, key = { it.id }) { bookmark ->
                        BookmarkCard(
                            bookmark = bookmark,
                            onClick = {
                                try {
                                    val intent =
                                        Intent(
                                            Intent.ACTION_VIEW,
                                            Uri.parse(bookmark.url),
                                        )
                                    context.startActivity(intent)
                                } catch (e: Exception) {
                                    // Ignore if no app can handle the URL
                                }
                            },
                            onEdit = { editingBookmark = bookmark },
                            onDelete = { viewModel.deleteBookmark(bookmark) },
                            onRatingChange = { newRating ->
                                viewModel.updateBookmark(
                                    bookmark.copy(rating = newRating),
                                )
                            },
                            onTagClick = { tag ->
                                viewModel.onSearchQueryChange(tag)
                            },
                        )
                    }
                }
            }

            if (editingBookmark != null) {
                EditBookmarkDialog(
                    bookmark = editingBookmark!!,
                    onDismiss = { editingBookmark = null },
                    onSave = { updated ->
                        viewModel.updateBookmark(updated)
                        editingBookmark = null
                    },
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SearchBar(
    query: String,
    onQueryChange: (String) -> Unit,
    onClear: () -> Unit,
) {
    Surface(
        modifier =
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 14.dp)
                .shadow(
                    elevation = 6.dp,
                    shape = RoundedCornerShape(28.dp),
                    clip = false,
                ),
        shape = RoundedCornerShape(28.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 4.dp,
    ) {
        TextField(
            value = query,
            onValueChange = onQueryChange,
            modifier =
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = 56.dp),
            placeholder = {
                Text(
                    text = "Search bookmarks or tags",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            },
            leadingIcon = {
                Icon(
                    imageVector = Icons.Default.Search,
                    contentDescription = "Search",
                    tint = MaterialTheme.colorScheme.primary,
                )
            },
            trailingIcon = {
                if (query.isNotBlank()) {
                    IconButton(onClick = onClear) {
                        Icon(
                            imageVector = Icons.Default.Clear,
                            contentDescription = "Clear search",
                        )
                    }
                }
            },
            singleLine = true,
            shape = RoundedCornerShape(28.dp),
            colors =
                TextFieldDefaults.colors(
                    focusedContainerColor = MaterialTheme.colorScheme.surface,
                    unfocusedContainerColor = MaterialTheme.colorScheme.surface,
                    disabledContainerColor = MaterialTheme.colorScheme.surface,
                    focusedIndicatorColor = Color.Transparent,
                    unfocusedIndicatorColor = Color.Transparent,
                    disabledIndicatorColor = Color.Transparent,
                    cursorColor = MaterialTheme.colorScheme.primary,
                ),
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun BookmarkCard(
    bookmark: Bookmark,
    onClick: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
    onRatingChange: (Int) -> Unit,
    onTagClick: (String) -> Unit,
) {
    val cardShape = RoundedCornerShape(24.dp)

    val dateFormat =
        remember {
            SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault())
        }

    val dateString =
        remember(bookmark.addingDatetime) {
            dateFormat.format(Date(bookmark.addingDatetime))
        }

    val host =
        remember(bookmark.url) {
            try {
                Uri.parse(bookmark.url).host?.removePrefix("www.") ?: bookmark.url
            } catch (e: Exception) {
                bookmark.url
            }
        }

    Card(
        modifier =
            Modifier
                .fillMaxWidth()
                .shadow(
                    elevation = 5.dp,
                    shape = cardShape,
                    clip = false,
                ).clickable(onClick = onClick),
        shape = cardShape,
        colors =
            CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface,
            ),
        border =
            BorderStroke(
                width = 1.dp,
                color = MaterialTheme.colorScheme.surfaceVariant,
            ),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Column(
            modifier =
                Modifier
                    .fillMaxWidth()
                    .padding(18.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Top,
            ) {
                Column(
                    modifier =
                        Modifier
                            .weight(1f)
                            .padding(end = 8.dp),
                ) {
                    Text(
                        text = bookmark.title.ifBlank { "Untitled bookmark" },
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurface,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )

                    Spacer(modifier = Modifier.height(6.dp))

                    Surface(
                        shape = RoundedCornerShape(50),
                        color = MaterialTheme.colorScheme.primaryContainer,
                    ) {
                        Text(
                            text = host,
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onPrimaryContainer,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier =
                                Modifier.padding(
                                    horizontal = 10.dp,
                                    vertical = 5.dp,
                                ),
                        )
                    }
                }

                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    IconButton(
                        onClick = onEdit,
                        modifier = Modifier.size(38.dp),
                        colors =
                            IconButtonDefaults.iconButtonColors(
                                containerColor = MaterialTheme.colorScheme.surfaceVariant,
                                contentColor = MaterialTheme.colorScheme.onSurfaceVariant,
                            ),
                    ) {
                        Icon(
                            imageVector = Icons.Default.Edit,
                            contentDescription = "Edit",
                            modifier = Modifier.size(19.dp),
                        )
                    }

                    IconButton(
                        onClick = onDelete,
                        modifier = Modifier.size(38.dp),
                        colors =
                            IconButtonDefaults.iconButtonColors(
                                containerColor = MaterialTheme.colorScheme.errorContainer,
                                contentColor = MaterialTheme.colorScheme.onErrorContainer,
                            ),
                    ) {
                        Icon(
                            imageVector = Icons.Default.Delete,
                            contentDescription = "Delete",
                            modifier = Modifier.size(19.dp),
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            Text(
                text = bookmark.url,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )

            if (bookmark.comments.isNotBlank()) {
                Spacer(modifier = Modifier.height(12.dp))

                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.7f),
                ) {
                    Text(
                        text = bookmark.comments,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(12.dp),
                    )
                }
            }

            if (bookmark.tags.isNotEmpty()) {
                Spacer(modifier = Modifier.height(12.dp))

                FlowRow(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    bookmark.tags.forEach { tag ->
                        SuggestionChip(
                            onClick = { onTagClick(tag) },
                            label = {
                                Text(
                                    text = tag,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            },
                            shape = RoundedCornerShape(50),
                            colors =
                                SuggestionChipDefaults.suggestionChipColors(
                                    containerColor = MaterialTheme.colorScheme.secondaryContainer,
                                    labelColor = MaterialTheme.colorScheme.onSecondaryContainer,
                                ),
                            border = null,
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(14.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Surface(
                    shape = CircleShape,
                    color = MaterialTheme.colorScheme.surfaceVariant,
                ) {
                    Text(
                        text = dateString,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier =
                            Modifier.padding(
                                horizontal = 10.dp,
                                vertical = 6.dp,
                            ),
                    )
                }

                Spacer(modifier = Modifier.weight(1f))

                RatingBar(
                    rating = bookmark.rating,
                    onRatingChange = onRatingChange,
                )
            }
        }
    }
}

@Composable
fun RatingBar(
    rating: Int,
    onRatingChange: (Int) -> Unit,
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        for (i in 1..5) {
            Icon(
                imageVector =
                    if (i <= rating) {
                        Icons.Filled.Star
                    } else {
                        Icons.Outlined.Star
                    },
                contentDescription = "Star $i",
                tint =
                    if (i <= rating) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.55f)
                    },
                modifier =
                    Modifier
                        .size(23.dp)
                        .clickable { onRatingChange(i) },
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EditBookmarkDialog(
    bookmark: Bookmark,
    onDismiss: () -> Unit,
    onSave: (Bookmark) -> Unit,
) {
    var title by remember { mutableStateOf(bookmark.title) }
    var comments by remember { mutableStateOf(bookmark.comments) }
    var tags by remember { mutableStateOf(bookmark.tags.joinToString(", ")) }

    val coroutineScope = rememberCoroutineScope()
    var isFetching by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Edit Bookmark") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    OutlinedTextField(
                        value = title,
                        onValueChange = { title = it },
                        label = { Text("Title") },
                        singleLine = true,
                        modifier = Modifier.weight(1f),
                    )

                    IconButton(
                        onClick = {
                            if (bookmark.url.isNotBlank()) {
                                isFetching = true

                                coroutineScope.launch {
                                    try {
                                        val fetchedTitle =
                                            kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                                                val document =
                                                    Jsoup
                                                        .connect(bookmark.url)
                                                        .userAgent(
                                                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " +
                                                                "AppleWebKit/537.36 (KHTML, like Gecko) " +
                                                                "Chrome/120.0.0.0 Safari/537.36",
                                                        ).timeout(5000)
                                                        .get()

                                                document
                                                    .title()
                                                    .takeIf { it.isNotBlank() }
                                                    ?: bookmark.url
                                            }

                                        if (fetchedTitle.isNotBlank()) {
                                            title = fetchedTitle
                                        }
                                    } catch (e: Exception) {
                                        // Ignore error and keep old title
                                    } finally {
                                        isFetching = false
                                    }
                                }
                            }
                        },
                        enabled = !isFetching,
                    ) {
                        if (isFetching) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(24.dp),
                                strokeWidth = 2.dp,
                            )
                        } else {
                            Icon(
                                imageVector = Icons.Default.Refresh,
                                contentDescription = "Reload Title",
                            )
                        }
                    }
                }

                OutlinedTextField(
                    value = comments,
                    onValueChange = { comments = it },
                    label = { Text("Comments") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 3,
                )

                OutlinedTextField(
                    value = tags,
                    onValueChange = { tags = it },
                    label = { Text("Tags (comma-separated)") },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onSave(
                        bookmark.copy(
                            title = title,
                            comments = comments,
                            tags = tags.split(",").map { it.trim() }.filter { it.isNotEmpty() },
                        ),
                    )
                },
            ) {
                Text("Save")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        },
    )
}
