// Phase 4 business fill of the single frozen page surface
// PAGE-MAINACTIVITY-3FDE9431 (7 features share this surface; one
// implementation, per-feature FWO/receipts stay independent). Native
// blueprint (P3 surface-plan): Navigation title bar with menus sort toggle
// + Column(TextInput placeholder / Button) + List/LazyForEach rows
// (Checkbox + strikethrough title + close button) + empty-state Text.
// Behavior parity anchors: MainActivity.kt:61-158 / TodoRepository.kt.
// IDataSource / DataChangeListener are ambient ArkUI declarations.
import { displayList, getTodoRepository, SORT_COMPLETED_LAST, SORT_DEFAULT,
  Todo, TodoRepository } from '../../data/TodoRepository';

class TodoDataSource implements IDataSource {
  private items: Todo[] = [];
  private listeners: DataChangeListener[] = [];

  totalCount(): number {
    return this.items.length;
  }

  getData(index: number): Todo {
    return this.items[index];
  }

  registerDataChangeListener(listener: DataChangeListener): void {
    this.listeners.push(listener);
  }

  unregisterDataChangeListener(listener: DataChangeListener): void {
    this.listeners = this.listeners.filter((item: DataChangeListener): boolean => item !== listener);
  }

  reload(items: Todo[]): void {
    this.items = items;
    for (const listener of this.listeners) {
      listener.onDataReloaded();
    }
  }
}

@ComponentV2
struct TodoRowView {
  @Param todo: Todo = { id: 0, title: '', completed: false, createdAt: 0 };
  @Event onToggle: (id: number) => void = (id: number): void => {};
  @Event onDelete: (id: number) => void = (id: number): void => {};

  build() {
    Row() {
      Checkbox()
        .select(this.todo.completed)
        .accessibilityText('完成 ' + this.todo.title)
        .id('完成 ' + this.todo.title)
        .onChange((checked: boolean): void => {
          this.onToggle(this.todo.id);
        })
      Text(this.todo.title)
        .layoutWeight(1)
        .maxLines(1)
        .decoration({ type: this.todo.completed ? TextDecorationType.LineThrough : TextDecorationType.None })
      Button('✕')
        .accessibilityText('删除 ' + this.todo.title)
        .id('删除 ' + this.todo.title)
        .onClick((): void => {
          this.onDelete(this.todo.id);
        })
    }
    .width('100%')
    .padding({ top: 4, bottom: 4 })
  }
}

@ComponentV2
export struct ShellPageMainactivity3fde9431 {
  @Local input: string = '';
  @Local sortMode: number = SORT_DEFAULT;
  @Local empty: boolean = true;
  @Local ds: TodoDataSource = new TodoDataSource();
  private repo: TodoRepository = getTodoRepository();

  aboutToAppear(): void {
    this.repo.ensureLoaded(getContext(this));
    this.sortMode = this.repo.getSortMode();
    this.refresh();
  }

  refresh(): void {
    this.empty = this.repo.count() === 0;
    this.ds.reload(displayList(this.repo.list(), this.sortMode));
  }

  addTodo(): void {
    const title: string = this.input.trim();
    if (title === '') {
      return;
    }
    this.repo.create(title);
    this.input = '';
    this.repo.setInput('');
    this.refresh();
  }

  toggleSort(): void {
    const next: number = this.sortMode === SORT_DEFAULT ? SORT_COMPLETED_LAST : SORT_DEFAULT;
    this.sortMode = next;
    this.repo.setSortMode(next);
    this.refresh();
  }

  @Builder
  sortMenu() {
    Button(this.sortMode === SORT_DEFAULT ? '排序：默认' : '排序：完成置底')
      .fontSize(14)
      .onClick((): void => {
        this.toggleSort();
      })
  }

  build() {
    NavDestination() {
      Column() {
        Row() {
          TextInput({ text: this.input, placeholder: '输入待办标题' })
            .layoutWeight(1)
            .id('输入待办标题')
            .onChange((value: string): void => {
              this.input = value;
              this.repo.setInput(value);
            })
          Button('添加')
            .onClick((): void => {
              this.addTodo();
            })
        }
        .width('100%')
        .padding(16)

        if (this.empty) {
          Text('暂无待办')
            .fontSize(16)
            .padding({ top: 32 })
        } else {
          List() {
            LazyForEach(this.ds, (item: Todo) => {
              ListItem() {
                TodoRowView({
                  todo: item,
                  onToggle: (id: number): void => {
                    this.repo.toggle(id);
                    this.refresh();
                  },
                  onDelete: (id: number): void => {
                    this.repo.remove(id);
                    this.refresh();
                  },
                })
              }
            }, (item: Todo) => item.id.toString())
          }
          .width('100%')
          .layoutWeight(1)
        }
      }
      .width('100%')
      .height('100%')
    }
    .title(this.pageTitle)
    .menus(this.sortMenu)
    .hideBackButton(true)
    .id('PAGE-MAINACTIVITY-3FDE9431')
  }

  @Builder
  pageTitle() {
    Text('迷你待办')
      .fontSize(20)
      .fontWeight(FontWeight.Bold)
  }
}
