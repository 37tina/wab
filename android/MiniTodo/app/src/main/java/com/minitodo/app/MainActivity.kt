package com.minitodo.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val repository = TodoRepository(this)
        setContent {
            MiniTodoApp(repository)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MiniTodoApp(repository: TodoRepository) {
    val todos = remember { mutableStateListOf<Todo>().apply { addAll(repository.loadTodos()) } }
    var sortMode by remember { mutableIntStateOf(repository.loadSortMode()) }
    var input by remember { mutableStateOf("") }

    fun persist() = repository.saveTodos(todos.toList())

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("迷你待办") },
                actions = {
                    TextButton(
                        onClick = {
                            sortMode =
                                if (sortMode == TodoRepository.SORT_DEFAULT) TodoRepository.SORT_COMPLETED_LAST
                                else TodoRepository.SORT_DEFAULT
                            repository.saveSortMode(sortMode)
                        }
                    ) {
                        Text(if (sortMode == TodoRepository.SORT_DEFAULT) "排序：默认" else "排序：完成置底")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .padding(16.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it },
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("输入待办标题") },
                    singleLine = true
                )
                Spacer(Modifier.width(8.dp))
                Button(
                    onClick = {
                        val title = input.trim()
                        if (title.isEmpty()) return@Button
                        val now = System.currentTimeMillis()
                        todos.add(Todo(id = now, title = title, completed = false, createdAt = now))
                        input = ""
                        persist()
                    }
                ) {
                    Text("添加")
                }
            }
            Spacer(Modifier.height(12.dp))
            if (todos.isEmpty()) {
                Text("暂无待办", modifier = Modifier.padding(top = 32.dp))
            } else {
                LazyColumn {
                    items(displayList(todos, sortMode), key = { it.id }) { todo ->
                        TodoRow(
                            todo = todo,
                            onToggle = {
                                val index = todos.indexOfFirst { it.id == todo.id }
                                if (index >= 0) {
                                    todos[index] = todos[index].copy(completed = !todos[index].completed)
                                    persist()
                                }
                            },
                            onDelete = {
                                todos.removeAll { it.id == todo.id }
                                persist()
                            }
                        )
                    }
                }
            }
        }
    }
}

private fun displayList(list: List<Todo>, mode: Int): List<Todo> =
    if (mode == TodoRepository.SORT_COMPLETED_LAST) list.sortedBy { it.completed } else list

@Composable
private fun TodoRow(todo: Todo, onToggle: () -> Unit, onDelete: () -> Unit) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
    ) {
        Checkbox(
            checked = todo.completed,
            onCheckedChange = { onToggle() },
            modifier = Modifier.semantics { contentDescription = "完成 ${todo.title}" }
        )
        Text(
            todo.title,
            modifier = Modifier.weight(1f),
            textDecoration = if (todo.completed) TextDecoration.LineThrough else null
        )
        IconButton(
            onClick = onDelete,
            modifier = Modifier.semantics { contentDescription = "删除 ${todo.title}" }
        ) {
            Text("✕")
        }
    }
}