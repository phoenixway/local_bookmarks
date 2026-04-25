package com.example.localbookmarks.data

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "bookmarks")
data class Bookmark(
    @PrimaryKey(autoGenerate = true) val id: Int = 0,
    val title: String,
    val url: String,
    val addingDatetime: Long,
    val comments: String,
    val rating: Int // 0 to 5 stars
)
