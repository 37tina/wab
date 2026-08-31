package com.minitodo.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * 极简待办仓库：内存态为唯一事实源，变更即整体写回 SharedPreferences。
 *
 * 持久化形态（供运行时数据探针读取验证）：
 * - minitodo_prefs / todos      : JSON 数组字符串，元素 {id, title, completed, createdAt}
 * - minitodo_prefs / sort_mode  : 0=默认（添加序） 1=完成置底
 */
class TodoRepository(context: Context) {

    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun loadTodos(): List<Todo> {
        val raw = prefs.getString(KEY_TODOS, null) ?: return emptyList()
        return try {
            val array = JSONArray(raw)
            buildList {
                for (i in 0 until array.length()) {
                    val obj = array.getJSONObject(i)
                    add(
                        Todo(
                            id = obj.getLong("id"),
                            title = obj.getString("title"),
                            completed = obj.getBoolean("completed"),
                            createdAt = obj.getLong("createdAt"),
                        )
                    )
                }
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    fun saveTodos(todos: List<Todo>) {
        val array = JSONArray()
        for (todo in todos) {
            array.put(
                JSONObject()
                    .put("id", todo.id)
                    .put("title", todo.title)
                    .put("completed", todo.completed)
                    .put("createdAt", todo.createdAt)
            )
        }
        prefs.edit().putString(KEY_TODOS, array.toString()).apply()
    }

    fun loadSortMode(): Int = prefs.getInt(KEY_SORT, SORT_DEFAULT)

    fun saveSortMode(mode: Int) {
        prefs.edit().putInt(KEY_SORT, mode).apply()
    }

    companion object {
        const val PREFS_NAME = "minitodo_prefs"
        const val KEY_TODOS = "todos"
        const val KEY_SORT = "sort_mode"
        const val SORT_DEFAULT = 0
        const val SORT_COMPLETED_LAST = 1
    }
}