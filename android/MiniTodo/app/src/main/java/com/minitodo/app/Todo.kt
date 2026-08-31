package com.minitodo.app

/** 待办数据项 */
data class Todo(
    val id: Long,
    val title: String,
    val completed: Boolean,
    val createdAt: Long,
)