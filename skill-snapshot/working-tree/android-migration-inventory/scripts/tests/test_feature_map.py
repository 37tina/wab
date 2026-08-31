#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_feature_map -- Phase 2 新范式产物体系测试（surface-index / feature-map /
data-relations / 门禁替换）。

fixture 策略：
  * mini Android 项目复刻 Cresto 真实结构与符号（MainActivity setContent 外壳、
    fun BoxScope.NavContainer 带接收者、TodoSection 无页面后缀、@Dao/@Entity/
    MMKV 数据层），经真实工具链（analyze_static_pages → gmi → feature_map）
    生成产物后断言；
  * scope.json 与 page-features.csv 直接拷贝 legacy 真实运行数据
    （migration-runs/HOME-FULL-RUN1，只读参照）；
  * 错绑断言采用真实案例语义：NavContainer.kt 的行为不能绑 DetailActivity
    类 feature。

覆盖判据（任务书）：
  1. schema 校验（feature-map.json 全键/枚举/正式 surface-ID）
  2. file:line 可解析（含 --project 行号范围实校）
  3. coverage_gate 正反例
  4. is_container 判定（Activity 外壳/compose 壳 = container；容器页一律
     SOURCE_CONFIRM）
  5. 绑定校验拒绝错绑（显式映射 + 证据文件集合，禁止子串匹配兜底）
  6. verify_mode 分级（增删改/持久化 → RUNTIME；普通展示/容器 → SOURCE_CONFIRM）
  7. data-relations 扫描（Room 表 / MMKV key / 列枚举）
  8. gmi UNMAPPED 门禁废除 + 范围内功能覆盖门禁（正反例）
  9. closure 的 feature coverage 门禁（正反例；GAP 不再阻塞）
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../android-migration-inventory/scripts/tests
SKILL = HERE.parents[1]                          # .../android-migration-inventory
SCRIPTS = SKILL / "scripts"
ANALYZE = SCRIPTS / "analyze_static_pages.py"
GMI = SCRIPTS / "gmi.py"
FMAP = SCRIPTS / "feature_map.py"
CLOSURE = SCRIPTS / "gmi_closure.py"

REPO_ROOT = SKILL.parents[2]                     # 工作流仓库根（含 migration-runs/）
LEGACY_WS = REPO_ROOT / "migration-runs" / "HOME-FULL-RUN1" / "phase-02-android-inventory.legacy"
LEGACY_SCOPE = REPO_ROOT / "migration-runs" / "HOME-FULL-RUN1" / "controller" / "scope.json"

FEATURES = [
    "FEATURE-NAV-SHELL", "FEATURE-HOME-LIST", "FEATURE-HOME-SORT",
    "FEATURE-TODO-COMPLETE", "FEATURE-ROW-SWIPE", "FEATURE-GROUP-MANAGE",
    "FEATURE-TODO-CREATE", "FEATURE-TODO-REPEAT", "FEATURE-REMINDER-CONFIG",
    "FEATURE-TODO-DETAIL", "FEATURE-SELECTION-BATCH", "FEATURE-HOME-SEARCH",
]

# legacy inputs/page-features.csv 的真实映射子集（page_symbol,feature_id）：
# 覆盖容器壳/页面/sheet/共享组件四类，与 mini 项目符号一一对应。
PAGE_FEATURES_CSV = (
    "page_symbol,feature_id\n"
    "MainActivity,FEATURE-NAV-SHELL\n"
    "MainScreen,FEATURE-NAV-SHELL\n"
    "NavContainer,FEATURE-NAV-SHELL\n"
    "HomeScreen,FEATURE-HOME-LIST\n"
    "DetailActivity,FEATURE-TODO-DETAIL\n"
    "DetailScreen,FEATURE-TODO-DETAIL\n"
    "AddTodoSheet,FEATURE-TODO-CREATE\n"
    "GroupBottomSheet,FEATURE-GROUP-MANAGE\n"
)

MANIFEST_XML = (
    '<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
    'package="com.nevoit.cresto">'
    '<uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>'
    '<application>'
    '<activity android:name=".MainActivity">'
    '<intent-filter><action android:name="android.intent.action.MAIN"/>'
    '<category android:name="android.intent.category.LAUNCHER"/></intent-filter>'
    '</activity>'
    '<activity android:name=".feature.detail.DetailActivity"/>'
    '<receiver android:name=".reminder.ReminderReceiver"/>'
    '</application></manifest>'
)

MAIN_ACTIVITY = """package com.nevoit.cresto

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        setContent {
            MainScreen()
        }
    }
}
"""

MAIN_SCREEN = """package com.nevoit.cresto.feature.main

@Composable
fun MainScreen() {
    val currentRoute = rememberSaveable { mutableStateOf("home") }
    Box(modifier = Modifier.fillMaxSize()) {
        NavContainer(
            currentRoute = currentRoute,
            onOpenGroupBottomSheet = { }
        )
    }
}
"""

NAV_CONTAINER = """package com.nevoit.cresto.feature.main

@Composable
fun BoxScope.NavContainer(
    currentRoute: String,
    onOpenGroupBottomSheet: () -> Unit
) {
    when (currentRoute) {
        "home" -> HomeScreen()
        "detail" -> DetailScreen()
    }
}
"""

HOME_SCREEN = """package com.nevoit.cresto.feature.home

@Composable
fun BoxScope.HomeScreen() {
    LazyColumn {
        item {
            Text(text = "Todos")
            TodoSection()
        }
    }
}
"""

TODO_SECTION = """package com.nevoit.cresto.feature.home

@Composable
fun TodoSection() {
    Row {
        Text(text = "section row")
    }
}
"""

DETAIL_ACTIVITY = """package com.nevoit.cresto.feature.detail

class DetailActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        setContent {
            DetailScreen()
        }
    }
}
"""

DETAIL_SCREEN = """package com.nevoit.cresto.feature.detail

@Composable
fun DetailScreen() {
    Column {
        Text(text = "Detail")
        Checkbox(checked = false, onCheckedChange = { viewModel.toggle() })
    }
}
"""

ADD_TODO_SHEET = """package com.nevoit.cresto.feature.todo

@Composable
fun AddTodoSheet(onDone: (String) -> Unit) {
    Column {
        TextField(value = "", onValueChange = { })
        Button(onClick = { onDone("new todo") }) { Text(text = "Add") }
    }
}
"""

GROUP_BOTTOM_SHEET = """package com.nevoit.cresto.feature.group

@Composable
fun GroupBottomSheet() {
    Column {
        Text(text = "Group")
        Button(onClick = { viewModel.insertGroup("g") }) { Text(text = "New") }
    }
}
"""

TODO_VIEWMODEL = """package com.nevoit.cresto.data.todo

class TodoViewModel(
    application: Application
) : ViewModel(application) {
    fun insert(item: TodoItem) { dao.insertTodo(item) }
    fun delete(item: TodoItem) { dao.deleteTodo(item) }
}
"""

TODO_DAO = """package com.nevoit.cresto.data.todo

@Dao
interface TodoDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertTodo(item: TodoItem): Long

    @Delete
    suspend fun deleteTodo(item: TodoItem)

    @Query("SELECT * FROM todo_items ORDER BY pinned DESC")
    fun observeAll(): Flow<List<TodoItem>>

    @Query("DELETE FROM todo_items WHERE id = :id")
    suspend fun deleteById(id: Long)
}
"""

TODO_ITEM = """package com.nevoit.cresto.data.todo

@Entity(
    tableName = "todo_items",
    indices = [Index(value = ["isCompleted"])]
)
data class TodoItem(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val title: String,
    val isCompleted: Boolean = false
)
"""

SETTINGS_MANAGER = """package com.nevoit.cresto.feature.settings.util

object SettingsManager {
    private const val KEY_SORT_OPTION = "sortOption"
    private const val KEY_SORT_ORDER = "sortOrder"
    private val mmkv = MMKV.defaultMMKV()

    val sortOption: SortOption
        get() = SortOption.entries[mmkv.decodeInt(KEY_SORT_OPTION, 0)]

    fun setSortOption(option: SortOption) {
        mmkv.encode(KEY_SORT_OPTION, option.ordinal)
    }
}
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_mini_project(root: Path) -> Path:
    pkg = root / "app" / "src" / "main" / "java" / "com" / "nevoit" / "cresto"
    _write(root / "app" / "src" / "main" / "AndroidManifest.xml", MANIFEST_XML)
    _write(pkg / "MainActivity.kt", MAIN_ACTIVITY)
    _write(pkg / "feature" / "main" / "MainScreen.kt", MAIN_SCREEN)
    _write(pkg / "feature" / "main" / "NavContainer.kt", NAV_CONTAINER)
    _write(pkg / "feature" / "home" / "HomeScreen.kt", HOME_SCREEN)
    _write(pkg / "feature" / "home" / "TodoSection.kt", TODO_SECTION)
    _write(pkg / "feature" / "detail" / "DetailActivity.kt", DETAIL_ACTIVITY)
    _write(pkg / "feature" / "detail" / "DetailScreen.kt", DETAIL_SCREEN)
    _write(pkg / "feature" / "todo" / "AddTodoSheet.kt", ADD_TODO_SHEET)
    _write(pkg / "feature" / "group" / "GroupBottomSheet.kt", GROUP_BOTTOM_SHEET)
    _write(pkg / "data" / "todo" / "TodoViewModel.kt", TODO_VIEWMODEL)
    _write(pkg / "data" / "todo" / "TodoDao.kt", TODO_DAO)
    _write(pkg / "data" / "todo" / "TodoItem.kt", TODO_ITEM)
    _write(pkg / "feature" / "settings" / "util" / "SettingsManager.kt", SETTINGS_MANAGER)
    return root


def run_tool(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(script), *args],
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=300, check=False)


class FeatureMapFixture:
    """一次性构建共享 fixture：mini 项目 → analyze → gmi → feature_map。"""

    def __init__(self, base: Path) -> None:
        self.project = build_mini_project(base / "project")
        self.ws = base / "run"
        (self.ws / "inputs").mkdir(parents=True, exist_ok=True)
        _write(self.ws / "phase-manifest.json", json.dumps({
            "phase": 2, "status": "IN_PROGRESS",
            "android_project_root": str(self.project),
            "source_revision": "fixture", "included_features": FEATURES,
            "ownership": {"code_map_agent_id": "code-map-agent-1"},
        }))
        _write(self.ws / "inputs" / "page-features.csv", PAGE_FEATURES_CSV)
        # scope：优先拷贝 legacy 真实 scope（12 included features），
        # legacy 不存在时用 FEATURES 本地构造，保持测试可独立运行。
        if LEGACY_SCOPE.exists():
            scope = json.loads(LEGACY_SCOPE.read_text(encoding="utf-8"))
            scope["android"]["project_root"] = str(self.project)
            scope.setdefault("migration_scope", {})["included_features"] = FEATURES
            _write(self.ws / "controller" / "scope.json",
                   json.dumps(scope, ensure_ascii=False))
        else:
            _write(self.ws / "controller" / "scope.json", json.dumps({
                "migration_scope": {"included_features": FEATURES},
                "android": {"project_root": str(self.project)},
            }, ensure_ascii=False))

        self.analyze = run_tool(ANALYZE, "--workspace", str(self.ws),
                                "--analyzed-by", "code-map-agent-1")
        assert self.analyze.returncode == 0, self.analyze.stderr
        self.gmi = run_tool(GMI, "--project", str(self.project),
                            "--workspace", str(self.ws),
                            "--features", ",".join(FEATURES),
                            "--page-features", str(self.ws / "inputs" / "page-features.csv"))
        assert self.gmi.returncode == 0, self.gmi.stderr + self.gmi.stdout
        self.fmap = run_tool(FMAP, "--workspace", str(self.ws),
                             "--project", str(self.project))
        assert self.fmap.returncode == 0, self.fmap.stderr + self.fmap.stdout

    def surface_rows(self) -> list[dict[str, str]]:
        with open(self.ws / "static-analysis" / "surface-index.csv", encoding="utf-8") as h:
            return list(csv.DictReader(h))

    def feature_map(self) -> dict:
        return json.loads((self.ws / "feature-map.json").read_text(encoding="utf-8"))


_FX: FeatureMapFixture | None = None
_BASE: tempfile.TemporaryDirectory | None = None


def setUpModule() -> None:
    global _FX, _BASE
    _BASE = tempfile.TemporaryDirectory(prefix="feature-map-test-")
    _FX = FeatureMapFixture(Path(_BASE.name))


def tearDownModule() -> None:
    if _BASE is not None:
        _BASE.cleanup()


class SurfaceIndexClassificationTest(unittest.TestCase):
    """判据 4 + 分类防呆：先分类再登记，容器页/复用组件不进 pages.json。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = _FX.surface_rows()
        cls.by_symbol = {r["symbol"]: r for r in cls.rows}

    def test_activity_shells_are_containers(self) -> None:
        for sym in ("MainActivity", "DetailActivity"):
            row = self.by_symbol[sym]
            self.assertEqual(row["kind"], "container", f"{sym}: {row}")
            self.assertEqual(row["is_container"], "true")

    def test_compose_shell_is_container(self) -> None:
        # MainScreen 被 Activity host、仅承载 NavContainer、无业务文本 -> 壳
        self.assertEqual(self.by_symbol["MainScreen"]["kind"], "container")

    def test_receiver_compose_funs_are_discovered(self) -> None:
        # fun BoxScope.HomeScreen / fun BoxScope.NavContainer 必须被发现（receiver 正则）
        self.assertIn("HomeScreen", self.by_symbol)
        self.assertIn("NavContainer", self.by_symbol)

    def test_pages_and_sheets(self) -> None:
        self.assertEqual(self.by_symbol["HomeScreen"]["kind"], "page")
        self.assertEqual(self.by_symbol["DetailScreen"]["kind"], "page")
        self.assertEqual(self.by_symbol["AddTodoSheet"]["kind"], "sheet")
        self.assertEqual(self.by_symbol["GroupBottomSheet"]["kind"], "sheet")

    def test_suffix_less_composables_are_reusable_not_pages(self) -> None:
        # TodoSection 防呆：普通 Compose 函数不得当独立页面
        row = self.by_symbol["TodoSection"]
        self.assertEqual(row["kind"], "reusable-component")
        self.assertEqual(row["is_container"], "false")

    def test_non_ui_surfaces_present(self) -> None:
        self.assertEqual(self.by_symbol["TodoViewModel"]["kind"], "viewmodel")
        self.assertEqual(self.by_symbol["TodoDao"]["kind"], "repository")
        self.assertEqual(self.by_symbol["TodoItem"]["kind"], "data-object")
        self.assertEqual(self.by_symbol["SettingsManager"]["kind"], "data-object")
        self.assertEqual(self.by_symbol["ReminderReceiver"]["kind"], "system-capability")

    def test_reusable_components_are_not_runtime_page_targets(self) -> None:
        pages = json.loads((_FX.ws / "static-analysis" / "pages.json")
                           .read_text(encoding="utf-8"))["pages"]
        syms = {p["symbol"] for p in pages}
        self.assertNotIn("TodoSection", syms)
        self.assertNotIn("NavContainer", syms)


class FeatureMapSchemaTest(unittest.TestCase):
    """判据 1/2/3：schema、file:line 可解析、coverage_gate 正例。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fm = _FX.feature_map()
        cls.by_id = {f["feature_id"]: f for f in cls.fm["features"]}

    def test_schema_keys_and_enums(self) -> None:
        self.assertEqual(self.fm["schema_version"], 1)
        for f in self.fm["features"]:
            for key in ("feature_id", "name", "summary", "source_refs", "surfaces",
                        "data_objects", "risk_level", "verify_mode", "status"):
                self.assertIn(key, f)
            self.assertIn(f["verify_mode"], ("RUNTIME", "SOURCE_CONFIRM"))
            self.assertIn(f["risk_level"], ("high", "normal"))
            if f["risk_level"] == "high":
                self.assertEqual(f["verify_mode"], "RUNTIME")
            self.assertIsInstance(f["data_objects"]["writes"], list)
            self.assertIsInstance(f["data_objects"]["reads"], list)

    def test_source_refs_parseable_and_in_range(self) -> None:
        import re
        pat = re.compile(r"^([^:\s][^:]*\.[A-Za-z0-9]+):(\d+)$")
        for f in self.fm["features"]:
            for ref in f["source_refs"]:
                m = pat.match(ref)
                self.assertIsNotNone(m, f"bad ref {ref!r} in {f['feature_id']}")
                path = _FX.project / m.group(1)
                self.assertTrue(path.is_file(), f"missing file {ref}")
                total = path.read_text(encoding="utf-8").count("\n") + 1
                self.assertLessEqual(int(m.group(2)), total, f"line overflow {ref}")

    def test_surfaces_reference_official_ids(self) -> None:
        official = {r["surface_id"]: r for r in _FX.surface_rows()}
        all_kinds = {r["kind"] for r in official.values()}
        for f in self.fm["features"]:
            for s in f["surfaces"]:
                self.assertIn(s["id"], official, f"{f['feature_id']} -> {s['id']}")
                # kind/is_container 必须与 surface-index 完全一致（防篡改）
                self.assertEqual(s["kind"], official[s["id"]]["kind"])
                self.assertEqual(s["is_container"],
                                 official[s["id"]]["is_container"] == "true")
                self.assertIn(s["kind"], all_kinds)

    def test_coverage_gate_positive(self) -> None:
        gate = self.fm["coverage_gate"]
        self.assertTrue(gate["included_features_covered"])
        self.assertEqual(set(gate["included"]), set(FEATURES))
        self.assertEqual(gate["missing"], [])
        # 12 included 全有条目
        self.assertEqual(set(self.by_id), set(FEATURES))

    def test_binding_uses_explicit_mapping_only(self) -> None:
        # NAV-SHELL 显式映射了 MainActivity/MainScreen/NavContainer；绑定校验后
        # 三者都在（NavContainer.kt ∈ NAV-SHELL 证据：显式映射并入信任根）
        nav = self.by_id["FEATURE-NAV-SHELL"]
        bound = {s["id"].split("-")[1] for s in nav["surfaces"]}
        self.assertIn("MAINACTIVITY", bound)
        self.assertIn("NAVCONTAINER", bound)
        # HomeScreen 属 HOME-LIST，绝不允许串到 NAV-SHELL（子串匹配兜底禁令）
        self.assertNotIn("HOMESCREEN", bound)
        detail = self.by_id["FEATURE-TODO-DETAIL"]
        detail_bound = {s["id"].split("-")[1] for s in detail["surfaces"]}
        self.assertIn("DETAILSCREEN", detail_bound)
        self.assertIn("ADDTODOSHEET", {s["id"].split("-")[1]
                                       for s in self.by_id["FEATURE-TODO-CREATE"]["surfaces"]})

    def test_home_sort_pending_placeholder(self) -> None:
        # 无页面映射/无证据的行为型 feature（HOME-SORT）-> 占位条目待 LLM 补
        row = self.by_id["FEATURE-HOME-SORT"]
        self.assertEqual(row["status"], "PENDING_LLM_BINDING")


class VerifyModeTierTest(unittest.TestCase):
    """判据 6 + 容器死锁根治：verify_mode 分级。"""

    @classmethod
    def setUpClass(cls) -> None:
        fm = _FX.feature_map()
        cls.by_id = {f["feature_id"]: f for f in fm["features"]}

    def test_crud_features_are_runtime_high(self) -> None:
        # 增删改词根（create）+ sheet 绑定 -> RUNTIME/high
        create = self.by_id["FEATURE-TODO-CREATE"]
        self.assertEqual(create["verify_mode"], "RUNTIME")
        self.assertEqual(create["risk_level"], "high")
        group = self.by_id["FEATURE-GROUP-MANAGE"]
        self.assertEqual(group["verify_mode"], "RUNTIME")

    def test_container_only_feature_is_source_confirm(self) -> None:
        # NAV-SHELL 只绑容器壳与导航组件（MainActivity/MainScreen 均 container，
        # NavContainer 为组件）——无可操作页面 -> 一律 SOURCE_CONFIRM
        # （MainScreen/DetailActivity 死锁根治）
        nav = self.by_id["FEATURE-NAV-SHELL"]
        self.assertTrue(nav["surfaces"], "NAV-SHELL 应有绑定 surface")
        operable = [s for s in nav["surfaces"]
                    if s["kind"] in ("page", "sheet", "dialog", "menu", "settings")]
        self.assertEqual(operable, [], f"NAV-SHELL 不应绑可操作页面: {nav['surfaces']}")
        self.assertEqual(nav["verify_mode"], "SOURCE_CONFIRM")
        self.assertEqual(nav["risk_level"], "normal")

    def test_writes_force_runtime(self) -> None:
        for f in self.by_id.values():
            if f["data_objects"]["writes"]:
                self.assertEqual(f["verify_mode"], "RUNTIME",
                                 f"{f['feature_id']} has writes but not RUNTIME")


class DataRelationsTest(unittest.TestCase):
    """判据 7：data-relations 扫描与列枚举。"""

    @classmethod
    def setUpClass(cls) -> None:
        with open(_FX.ws / "data-relations.csv", encoding="utf-8") as h:
            cls.rows = list(csv.DictReader(h))

    def test_room_table_relations(self) -> None:
        room = [r for r in self.rows if r["persistence_kind"] == "room_table"]
        self.assertTrue(room, "应扫描到 room_table 关系")
        writes = {r["data_object"] for r in room if r["relation"] == "write" and r["data_object"]}
        reads = {r["data_object"] for r in room if r["relation"] == "read"}
        self.assertIn("todo_items", writes)          # @Insert/@Delete/@Query DELETE
        self.assertIn("todo_items", reads)           # @Query SELECT

    def test_mmkv_key_relations(self) -> None:
        mmkv = [r for r in self.rows if r["persistence_kind"] == "mmkv_key"]
        locations = {r["persistence_location"] for r in mmkv}
        self.assertIn("sortOption", locations)       # const val KEY_SORT_OPTION 字面量解析
        relations = {r["relation"] for r in mmkv}
        self.assertEqual(relations, {"read", "write"})

    def test_columns_and_enums(self) -> None:
        header = list(self.rows[0].keys())
        self.assertEqual(header, ["relation_id", "feature_id", "data_object",
                                  "relation", "persistence_kind",
                                  "persistence_location", "source_ref"])
        for r in self.rows:
            self.assertIn(r["relation"], ("read", "write"))
            self.assertIn(r["persistence_kind"],
                          ("room_table", "preference_key", "mmkv_key", "datastore_key",
                           "file", "content_provider", "unknown"))
            if r["feature_id"]:
                self.assertIn(r["feature_id"], FEATURES)


class BindingGuardTest(unittest.TestCase):
    """判据 5：绑定校验拒绝错绑（真实案例：NavContainer.kt 不能绑 Detail 类 feature）。"""

    def test_validate_rejects_cross_feature_surface_binding(self) -> None:
        fm = _FX.feature_map()
        nav_surface = next(
            s for f in fm["features"] if f["feature_id"] == "FEATURE-NAV-SHELL"
            for s in f["surfaces"] if "NAVCONTAINER" in s["id"])
        detail = next(f for f in fm["features"]
                      if f["feature_id"] == "FEATURE-TODO-DETAIL")
        # 恶意错绑：把 NAV-SHELL 的 NavContainer surface 塞进 DETAIL
        detail["surfaces"] = detail["surfaces"] + [dict(nav_surface)]
        # 补语义列使错误集中在绑定校验上（PENDING feature 用 HomeScreen 正式 ID 补齐）
        rows = _FX.surface_rows()
        home = next(r for r in rows if r["symbol"] == "HomeScreen")
        home_surface = {"id": home["surface_id"], "kind": home["kind"],
                        "is_container": home["is_container"] == "true"}
        home_ref = home["source_ref"]
        for f in fm["features"]:
            f["name"] = f["feature_id"]
            f["summary"] = "fixture"
            if f["status"] == "PENDING_LLM_BINDING":
                f["status"] = "OPEN"
                f["surfaces"] = [home_surface]
                f["source_refs"] = [home_ref]
        _write(_FX.ws / "feature-map.json", json.dumps(fm, ensure_ascii=False, indent=2))
        try:
            r = run_tool(FMAP, "--workspace", str(_FX.ws),
                         "--project", str(_FX.project), "--validate")
            self.assertEqual(r.returncode, 1,
                             f"错绑必须被拒绝 stdout={r.stdout}")
            combined = r.stdout + r.stderr
            self.assertIn("NavContainer", combined)
            self.assertIn("拒绝错绑", combined)
        finally:
            # 还原正例 feature-map，避免污染后续测试
            regen = run_tool(FMAP, "--workspace", str(_FX.ws),
                             "--project", str(_FX.project))
            assert regen.returncode == 0, regen.stderr + regen.stdout

    def test_validate_rejects_fabricated_surface_id(self) -> None:
        fm = _FX.feature_map()
        rows = _FX.surface_rows()
        home = next(r for r in rows if r["symbol"] == "HomeScreen")
        home_surface = {"id": home["surface_id"], "kind": home["kind"],
                        "is_container": home["is_container"] == "true"}
        home_ref = home["source_ref"]
        target = next(f for f in fm["features"]
                      if f["feature_id"] == "FEATURE-HOME-LIST")
        target["surfaces"] = target["surfaces"] + [{
            "id": "PAGE-HACKED-00000000", "kind": "page", "is_container": False}]
        for f in fm["features"]:
            f["name"] = f["feature_id"]
            f["summary"] = "fixture"
            if f["status"] == "PENDING_LLM_BINDING":
                f["status"] = "OPEN"
                f["surfaces"] = [home_surface]
                f["source_refs"] = [home_ref]
        _write(_FX.ws / "feature-map.json", json.dumps(fm, ensure_ascii=False, indent=2))
        try:
            r = run_tool(FMAP, "--workspace", str(_FX.ws), "--validate")
            self.assertEqual(r.returncode, 1)
            self.assertIn("不是 surface-index 正式 ID", r.stdout + r.stderr)
        finally:
            regen = run_tool(FMAP, "--workspace", str(_FX.ws),
                             "--project", str(_FX.project))
            assert regen.returncode == 0, regen.stderr + regen.stdout


class CoverageGateNegativeTest(unittest.TestCase):
    """判据 3 反例：缺条目/未补齐 -> --validate FAIL。"""

    def test_validate_fails_on_pending_and_missing_semantics(self) -> None:
        # 骨架（name/summary 空 + PENDING 占位）必须 FAIL（fail-closed 收口）
        r = run_tool(FMAP, "--workspace", str(_FX.ws), "--validate")
        self.assertEqual(r.returncode, 1)
        combined = r.stdout + r.stderr
        self.assertIn("PENDING_LLM_BINDING", combined)
        self.assertIn("name 为空", combined)

    def test_validate_fails_when_included_feature_has_no_entry(self) -> None:
        fm = _FX.feature_map()
        fm["features"] = [f for f in fm["features"]
                          if f["feature_id"] != "FEATURE-HOME-SORT"]
        fm["coverage_gate"]["included_features_covered"] = True  # 篡改声明值
        _write(_FX.ws / "feature-map.json", json.dumps(fm, ensure_ascii=False, indent=2))
        try:
            r = run_tool(FMAP, "--workspace", str(_FX.ws), "--validate")
            self.assertEqual(r.returncode, 1)
            self.assertIn("无条目", r.stdout + r.stderr)
        finally:
            regen = run_tool(FMAP, "--workspace", str(_FX.ws),
                             "--project", str(_FX.project))
            assert regen.returncode == 0, regen.stderr + regen.stdout


class GmiGateParadigmTest(unittest.TestCase):
    """判据 8：gmi 侧门禁替换（UNMAPPED 参考化 + 功能覆盖门禁）。"""

    def test_unmapped_no_longer_blocks_gmi(self) -> None:
        # gmi 输出中存在参考性 GAP（fixture 无 build.gradle 完整依赖等）
        self.assertIn("参考附件", _FX.gmi.stdout)
        self.assertNotIn("--allow-unmapped to accept", _FX.gmi.stdout)

    def test_gmi_fails_when_existing_feature_map_breaks_coverage(self) -> None:
        # workspace 已有 feature-map 且缺 included 条目 -> gmi exit 1（新门禁实校）
        with tempfile.TemporaryDirectory(prefix="gmi-gate-") as td:
            ws = Path(td) / "ws"
            shutil.copytree(_FX.ws, ws, ignore=shutil.ignore_patterns(
                "feature-map.json", "data-relations.csv", "static-analysis", "inputs",
                "controller", "phase-manifest.json"))
            _write(ws / "inputs" / "page-features.csv", PAGE_FEATURES_CSV)
            bad = {"features": [{"feature_id": "FEATURE-NAV-SHELL"}],
                   "coverage_gate": {"included_features_covered": True,
                                     "included": FEATURES, "covered": ["FEATURE-NAV-SHELL"],
                                     "missing": FEATURES[1:]}}
            _write(ws / "feature-map.json", json.dumps(bad, ensure_ascii=False))
            r = run_tool(GMI, "--project", str(_FX.project), "--workspace", str(ws),
                         "--features", ",".join(FEATURES),
                         "--page-features", str(ws / "inputs" / "page-features.csv"))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("feature coverage gate FAIL", r.stdout + r.stderr)


class ClosureFeatureCoverageTest(unittest.TestCase):
    """判据 9：closure 的功能覆盖门禁（GAP 不再阻塞 + 缺 feature-map 阻塞）。"""

    @staticmethod
    def _closure_ws(base: Path, *, scope: bool, fmap: str | None,
                    gap_row: bool) -> Path:
        ws = base / "closure-ws"
        _write(ws / "candidates" / "manifest.sha256", "0" * 64 + "  x.csv\n")
        ledger = "file,category,disposition,status,covering_candidates\n" \
                 "a.kt,source,IN_SCOPE,OK,CAND-CODE-0001\n"
        if gap_row:
            ledger += "b.kt,source,IN_SCOPE,GAP,\n"
        _write(ws / "coverage" / "coverage-ledger.csv", ledger)
        _write(ws / "runtime-evidence" / "audit-replay.csv",
               "page_id,symbol,replayed,recorded,discrepancy,note\n"
               "PAGE-LAUNCH,MainActivity,VISITED,VISITED,no,ok\n")
        _write(ws / "runtime-evidence" / "runtime-gate.csv",
               "page_id,symbol,status,evidence\n"
               "PAGE-LAUNCH,MainActivity,VISITED,PAGE-LAUNCH/ui.xml\n")
        _write(ws / "phase-2-report.md", "# report\n")
        if scope:
            _write(ws / "scope.json", json.dumps(
                {"migration_scope": {"included_features": ["FEATURE-A"]}}))
        if fmap is not None:
            _write(ws / "feature-map.json", fmap)
        return ws

    def test_gap_rows_no_longer_block_closure(self) -> None:
        # 新范式：coverage-ledger 的 GAP 行为参考信息，不阻塞（无 scope 时）
        with tempfile.TemporaryDirectory() as td:
            ws = self._closure_ws(Path(td), scope=False, fmap=None, gap_row=True)
            r = run_tool(CLOSURE, "--workspace", str(ws))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            closure = json.loads((ws / "phase-2-closure.json").read_text(encoding="utf-8"))
            self.assertEqual(closure["gate"]["unmapped"], 1)          # 实算保留
            self.assertFalse(closure["gate"]["feature_coverage"]["required"])

    def test_scope_without_feature_map_blocks_closure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = self._closure_ws(Path(td), scope=True, fmap=None, gap_row=False)
            r = run_tool(CLOSURE, "--workspace", str(ws))
            self.assertEqual(r.returncode, 1)
            self.assertIn("feature coverage gate FAIL", r.stdout + r.stderr)
            self.assertIn("feature-map.json 缺失", r.stdout + r.stderr)

    def test_broken_feature_map_blocks_closure(self) -> None:
        bad = json.dumps({"features": [], "coverage_gate": {
            "included_features_covered": True,
            "included": ["FEATURE-A"], "covered": [], "missing": ["FEATURE-A"]}})
        with tempfile.TemporaryDirectory() as td:
            ws = self._closure_ws(Path(td), scope=True, fmap=bad, gap_row=False)
            r = run_tool(CLOSURE, "--workspace", str(ws))
            self.assertEqual(r.returncode, 1)
            self.assertIn("feature coverage gate FAIL", r.stdout + r.stderr)

    def test_closed_feature_map_passes_closure(self) -> None:
        good = json.dumps({"features": [{"feature_id": "FEATURE-A"}],
                           "coverage_gate": {"included_features_covered": True,
                                             "included": ["FEATURE-A"],
                                             "covered": ["FEATURE-A"], "missing": []}})
        with tempfile.TemporaryDirectory() as td:
            ws = self._closure_ws(Path(td), scope=True, fmap=good, gap_row=True)
            r = run_tool(CLOSURE, "--workspace", str(ws))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            closure = json.loads((ws / "phase-2-closure.json").read_text(encoding="utf-8"))
            self.assertTrue(closure["gate"]["feature_coverage"]["ok"])
            self.assertEqual(closure["gate"]["unmapped"], 1)          # GAP 参考


class LegacyRealDataCompatTest(unittest.TestCase):
    """legacy 真实数据（只读参照）：scope/page-features/候选表 schema 兼容。"""

    def test_legacy_scope_included_features_used_by_fixture(self) -> None:
        if not LEGACY_SCOPE.exists():
            self.skipTest("legacy run data unavailable")
        scope = json.loads(LEGACY_SCOPE.read_text(encoding="utf-8"))
        included = scope["migration_scope"]["included_features"]
        self.assertEqual(len(included), 12)
        # fixture 的 FEATURES 与 legacy scope 完全一致（真实范围）
        self.assertEqual(set(FEATURES), set(included))

    def test_legacy_page_features_schema_parseable(self) -> None:
        legacy_csv = LEGACY_WS / "inputs" / "page-features.csv"
        if not legacy_csv.exists():
            self.skipTest("legacy page-features unavailable")
        with open(legacy_csv, encoding="utf-8-sig") as h:
            rows = list(csv.DictReader(h))
        self.assertTrue(rows)
        for r in rows:
            self.assertIn("page_symbol", r)
            self.assertIn("feature_id", r)
        # 真实案例符号在 legacy 映射体系中存在
        symbols = {r["page_symbol"] for r in rows}
        self.assertIn("DetailActivity", symbols)
        self.assertIn("MainScreen", symbols)
        self.assertIn("AddTodoSheet", symbols)
        # 教训记录：legacy 映射从未显式声明 NavContainer——这正是当年
        # NavContainer.kt 行为被兜底绑到 DetailActivity 的根源；新范式 fixture
        # 的 PAGE_FEATURES_CSV 显式补上 NavContainer -> FEATURE-NAV-SHELL。
        self.assertNotIn("NavContainer", symbols)

    def test_feature_map_validates_against_legacy_business_rules_schema(self) -> None:
        # collect_evidence 直接消费 legacy 真实 business-rules 表头
        if not (LEGACY_WS / "candidates" / "business-rules.candidates.csv").exists():
            self.skipTest("legacy candidates unavailable")
        sys.path.insert(0, str(SCRIPTS))
        import feature_map as fm  # noqa: PLC0415
        with open(LEGACY_WS / "candidates" / "business-rules.candidates.csv",
                  encoding="utf-8-sig") as h:
            rows = list(csv.DictReader(h))
        self.assertTrue(rows)
        parsed = [fm.parse_file_line(r["source_ref"]) for r in rows[:50]]
        self.assertTrue(all(p is not None for p in parsed),
                        "legacy source_ref 应全部可解析为 file:line")


if __name__ == "__main__":
    unittest.main()