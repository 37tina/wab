// Phase 4 data layer (FEAT impl-lead-minitodo-r1). Implements the four
// Phase 3 data-contract objects (todos / sort_mode / input_state /
// todo_title) on @ohos.data.preferences (B6 mapping; physical carrier is
// free, semantics are frozen): prefs minitodo_prefs/todos = JSON array of
// {id,title,completed,createdAt}, minitodo_prefs/sort_mode = int. In-memory
// list is the single source of truth; every mutation writes the whole list
// back and flushes (parity with TodoRepository.kt apply()).
import { preferences } from '@kit.ArkData';
import { registerProbe } from '../probe/SemanticProbeRegistry';

export interface Todo {
  id: number;
  title: string;
  completed: boolean;
  createdAt: number;
}

interface ScalarSnapshot {
  value: number | string | boolean;
}

export const SORT_DEFAULT: number = 0;
export const SORT_COMPLETED_LAST: number = 1;

const PREFS_NAME: string = 'minitodo_prefs';
const KEY_TODOS: string = 'todos';
const KEY_SORT: string = 'sort_mode';

export function displayList(list: Todo[], mode: number): Todo[] {
  if (mode !== SORT_COMPLETED_LAST) {
    return list;
  }
  const copy: Todo[] = list.slice();
  copy.sort((a: Todo, b: Todo): number => a.completed === b.completed ? 0 : (a.completed ? 1 : -1));
  return copy;
}

export class TodoRepository {
  private prefs: preferences.Preferences | null = null;
  private todos: Todo[] = [];
  private sortMode: number = SORT_DEFAULT;
  private input: string = '';

  ensureLoaded(context: Context): void {
    if (this.prefs !== null) {
      return;
    }
    const options: preferences.Options = { name: PREFS_NAME };
    this.prefs = preferences.getPreferencesSync(context, options);
    this.restore();
  }

  restore(): void {
    if (this.prefs === null) {
      return;
    }
    const raw: preferences.ValueType = this.prefs.getSync(KEY_TODOS, '');
    this.todos = decodeTodos(raw as string);
    this.sortMode = this.prefs.getSync(KEY_SORT, SORT_DEFAULT) as number;
  }

  list(): Todo[] {
    return this.todos;
  }

  count(): number {
    return this.todos.length;
  }

  get(id: number): Todo | null {
    for (const item of this.todos) {
      if (item.id === id) {
        return item;
      }
    }
    return null;
  }

  set(list: Todo[]): void {
    this.todos = list.slice();
    this.persistTodos();
  }

  create(title: string): Todo {
    const now: number = Date.now();
    const item: Todo = { id: now, title: title, completed: false, createdAt: now };
    this.todos.push(item);
    this.persistTodos();
    return item;
  }

  setCompleted(id: number, completed: boolean): boolean {
    for (let i = 0; i < this.todos.length; i++) {
      if (this.todos[i].id === id) {
        const updated: Todo = {
          id: this.todos[i].id, title: this.todos[i].title,
          completed: completed, createdAt: this.todos[i].createdAt,
        };
        this.todos[i] = updated;
        this.persistTodos();
        return true;
      }
    }
    return false;
  }

  toggle(id: number): boolean {
    const current: Todo | null = this.get(id);
    if (current === null) {
      return false;
    }
    return this.setCompleted(id, !current.completed);
  }

  remove(id: number): boolean {
    const before: number = this.todos.length;
    this.todos = this.todos.filter((item: Todo): boolean => item.id !== id);
    if (this.todos.length !== before) {
      this.persistTodos();
      return true;
    }
    return false;
  }

  getSortMode(): number {
    return this.sortMode;
  }

  setSortMode(mode: number): void {
    this.sortMode = mode;
    if (this.prefs !== null) {
      this.prefs.putSync(KEY_SORT, mode);
      this.prefs.flush();
    }
  }

  getInput(): string {
    return this.input;
  }

  setInput(value: string): void {
    this.input = value;
  }

  lastTitle(): string {
    if (this.todos.length === 0) {
      return '';
    }
    return this.todos[this.todos.length - 1].title;
  }

  private persistTodos(): void {
    if (this.prefs !== null) {
      this.prefs.putSync(KEY_TODOS, JSON.stringify(this.todos));
      this.prefs.flush();
    }
  }
}

function decodeTodos(raw: string): Todo[] {
  if (raw === '') {
    return [];
  }
  try {
    const parsed: object = JSON.parse(raw) as object;
    if (!Array.isArray(parsed)) {
      return [];
    }
    const rows: object[] = parsed as object[];
    const out: Todo[] = [];
    for (const row of rows) {
      const record: Record<string, object> = row as Record<string, object>;
      const item: Todo = {
        id: Number(record['id']),
        title: String(record['title']),
        completed: Boolean(record['completed']),
        createdAt: Number(record['createdAt']),
      };
      out.push(item);
    }
    return out;
  } catch (err) {
    return [];
  }
}

function scalar(value: number | string | boolean): ScalarSnapshot {
  const snapshot: ScalarSnapshot = { value: value };
  return snapshot;
}

function wireProbe(repo: TodoRepository): void {
  registerProbe('todos', (): object => repo.list().slice());
  registerProbe('sort_mode', (): object => scalar(repo.getSortMode()));
  registerProbe('input_state', (): object => scalar(repo.getInput()));
  registerProbe('todo_title', (): object => scalar(repo.lastTitle()));
}

let instance: TodoRepository | null = null;

export function getTodoRepository(): TodoRepository {
  if (instance === null) {
    instance = new TodoRepository();
    wireProbe(instance);
  }
  return instance;
}
