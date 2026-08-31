# -*- coding: utf-8 -*-
"""test_data_probe -- android_data_probe（任务 #82，Oracle 数据探针）单测。

覆盖（fixture 驱动，与现有采集器测试策略一致——设备侧 adb 副作用执行器
不在单测范围，探测路径经打桩验证分支）：
  - SharedPreferences XML 解析：全类型节点 / 未知节点保留 / 坏 XML 异常；
  - MMKV 二进制解析：varint KV 流 roundtrip / 覆盖语义 / 头部跳过 /
    脏区截断防御 / 真实 Cresto mmkv.default fixture（16KB）；
  - MMKV 值启发式：bool / int / str / hex 兜底；
  - sqlite3 -json 输出解析：fixture 样例 / 坏 JSON / 非零退出 /
    行截断标记 / 危险表名拒绝；
  - data 断言判定（集成契约核心）：四种 kind 正反例 + fail-closed 分层
    （采集受阻 -> UNSUPPORTED；数据在但不匹配 -> FAIL）+ key 寻址语法；
  - TOOL_GAP 路径：adb 不可达 -> DENIED 报告仍产出 + 退出码 3；
  - 真实 fixture 结构完整性（锁住 android-data-probe/1 schema）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import android_data_probe as adp  # noqa: E402  模块级无副作用（纯函数/常量）

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def encode_varint(value: int) -> bytes:
    """测试自备 varint 编码器（独立实现，交叉验证被测解码器）。"""
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def build_mmkv(pairs, header: bytes = b"\x00" * 8, tail: bytes = b"") -> bytes:
    """构造 MMKV 文件：header(8) + KV 流 + 可选尾部脏区。"""
    body = bytearray()
    for key, val in pairs:
        kb = key.encode("ascii") if isinstance(key, str) else key
        vb = val if isinstance(val, bytes) else \
            encode_varint(val) if isinstance(val, int) else val.encode("utf-8")
        body += encode_varint(len(kb)) + kb + encode_varint(len(vb)) + vb
    return header + bytes(body) + tail


class TestSharedPrefsParse(unittest.TestCase):
    def test_sample_fixture_all_types(self):
        xml = (FIXTURES / "shared_prefs_sample.xml").read_text(encoding="utf-8")
        kv = adp.parse_shared_prefs_xml(xml)
        self.assertIs(kv["night_mode"], True)
        self.assertEqual(kv["max_items"], 42)
        self.assertEqual(kv["last_sync_ms"], 1788006648365)
        self.assertEqual(kv["scale_factor"], 1.5)
        self.assertEqual(kv["locale_tag"], "zh-CN")
        self.assertEqual(kv["empty_note"], "")
        self.assertEqual(kv["pinned_filter"], ["work", "home"])

    def test_unknown_node_kept_as_raw(self):
        xml = ("<map><weird name=\"k\" value=\"7\" /></map>")
        kv = adp.parse_shared_prefs_xml(xml)
        self.assertEqual(kv["k"], {"_raw_type": "weird", "value": "7"})

    def test_broken_xml_raises(self):
        with self.assertRaises(Exception):
            adp.parse_shared_prefs_xml("<map><string name=")


class TestMmkvParse(unittest.TestCase):
    def test_roundtrip_bool_int_str(self):
        data = build_mmkv([
            ("flag_on", b"\x01"),
            ("flag_off", b"\x00"),
            ("count", 300),                       # varint 多字节（300 -> 0xAC 0x02）
            ("name", "待办事项".encode("utf-8")),  # UTF-8 字符串值
        ])
        final, pairs = adp.parse_mmkv_binary(data)
        self.assertEqual(len(pairs), 4)
        self.assertIs(final["flag_on"], True)
        self.assertIs(final["flag_off"], False)
        self.assertEqual(final["count"], 300)
        self.assertEqual(final["name"], "待办事项")

    def test_override_semantics_last_write_wins(self):
        data = build_mmkv([
            ("sort_order", b"\x00"),
            ("sort_order", b"\x01"),
            ("sort_option", b"\x01"),
            ("sort_option", b"\x01"),
        ])
        final, pairs = adp.parse_mmkv_binary(data)
        self.assertEqual(len(pairs), 4)      # 原始对全保留（审计）
        self.assertIs(final["sort_order"], True)   # 后写覆盖先写
        self.assertIs(final["sort_option"], True)

    def test_header_skipped(self):
        # 实测布局：[0..7] 头（actualSize/crc，full-write 后可为 0）从 8 起是 KV 流
        data = build_mmkv([("k", b"\x01")], header=b"\x00\x00\x00\x00\xff\xee\xdd\xcc")
        final, _ = adp.parse_mmkv_binary(data)
        self.assertIs(final["k"], True)

    def test_dirty_tail_truncates_stream(self):
        # 预分配区脏尾：KV 流后接不可打印字节，解析应在流尾停止
        dirty = bytes([0x00, 0xFF, 0xFE, 0x81, 0x02, 0x00])
        data = build_mmkv([("a", b"\x01"), ("b", 7)], tail=dirty)
        final, pairs = adp.parse_mmkv_binary(data)
        self.assertEqual(len(pairs), 2)
        self.assertIs(final["a"], True)
        self.assertEqual(final["b"], 7)

    def test_real_cresto_fixture(self):
        # 真实 Cresto mmkv.default（16KB，2026-08-30 模拟器实拉）
        data = (FIXTURES / "mmkv_default_sample.bin").read_bytes()
        final, pairs = adp.parse_mmkv_binary(data)
        self.assertEqual(len(pairs), 6)          # raw 6 对
        self.assertEqual(len(final), 4)          # 覆盖后 4 键
        self.assertIs(final["is_first_run"], False)
        self.assertIs(final["sort_order"], True)     # 两写：false -> true
        self.assertIs(final["sort_option"], True)
        self.assertEqual(final["last_update_check_at"], 1788006648365)

    def test_empty_and_garbage_files(self):
        self.assertEqual(adp.parse_mmkv_binary(b"\x00" * 8)[1], [])
        self.assertEqual(adp.parse_mmkv_binary(b"")[1], [])
        # 纯脏数据（无有效 KV）
        garbage = bytes(range(256)) * 4
        final, pairs = adp.parse_mmkv_binary(garbage)
        self.assertEqual(pairs, [])


class TestMmkvValueHeuristics(unittest.TestCase):
    def test_bool_int_str_hex(self):
        self.assertIs(adp.decode_mmkv_value(b"\x01"), True)
        self.assertIs(adp.decode_mmkv_value(b"\x00"), False)
        self.assertEqual(adp.decode_mmkv_value(encode_varint(123456789)), 123456789)
        self.assertEqual(adp.decode_mmkv_value(b"v1.2.3"), "v1.2.3")
        self.assertEqual(adp.decode_mmkv_value(b""), "")
        # 截断 varint（只有 continuation 位无终止）且非合法 UTF-8 -> hex 兜底
        # 注：MMKV 无类型元数据，恰好构成合法 varint 的二进制会按 int 解读
        # （格式本质限制），故用必然非法的字节验证兜底路径。
        self.assertEqual(adp.decode_mmkv_value(b"\x80\x80"),
                         "hex:8080")


class TestSqliteJsonParse(unittest.TestCase):
    """sqlite3 -json 输出解析（经 dump_sqlite_table，打桩 _run 免环境依赖）。"""

    def setUp(self):
        self._original_run = adp._run

    def tearDown(self):
        adp._run = self._original_run

    def _stub(self, stdout=b"", returncode=0, stderr=b""):
        def fake_run(argv, timeout):
            return subprocess.CompletedProcess(argv, returncode, stdout, stderr)
        adp._run = fake_run

    def test_real_fixture_output(self):
        text = (FIXTURES / "sqlite_json_todo_items.txt").read_bytes()
        self._stub(stdout=text)
        with TemporaryDirectory() as tmp:
            out = adp.dump_sqlite_table("sqlite3", Path(tmp) / "t.db",
                                        "todo_items", 200, 10)
        self.assertFalse(out["truncated"])
        rows = out["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], 1)
        self.assertEqual(rows[0]["isCompleted"], 1)
        self.assertIsNone(rows[0]["groupId"])

    def test_empty_table(self):
        self._stub(stdout=b"")
        with TemporaryDirectory() as tmp:
            out = adp.dump_sqlite_table("sqlite3", Path(tmp) / "t.db",
                                        "todo_groups", 200, 10)
        self.assertEqual(out["rows"], [])
        self.assertFalse(out["truncated"])

    def test_truncation_flag(self):
        two = json.dumps([{"id": 1}, {"id": 2}]).encode()
        self._stub(stdout=two)
        with TemporaryDirectory() as tmp:
            out = adp.dump_sqlite_table("sqlite3", Path(tmp) / "t.db",
                                        "t", 1, 10)   # max_rows=1，2 行返回
        self.assertTrue(out["truncated"])
        self.assertEqual(len(out["rows"]), 1)

    def test_nonzero_exit_reports_error(self):
        self._stub(returncode=1, stderr=b"no such table: x")
        with TemporaryDirectory() as tmp:
            out = adp.dump_sqlite_table("sqlite3", Path(tmp) / "t.db",
                                        "t", 10, 10)
        self.assertEqual(out["rows"], [])
        self.assertIn("no such table", out["error"])

    def test_broken_json_reports_error(self):
        self._stub(stdout=b"{not-json")
        with TemporaryDirectory() as tmp:
            out = adp.dump_sqlite_table("sqlite3", Path(tmp) / "t.db",
                                        "t", 10, 10)
        self.assertIn("unparseable", out["error"])

    def test_unsafe_table_name_rejected(self):
        out = adp.dump_sqlite_table("sqlite3", Path("/tmp/x.db"),
                                    't"; DROP TABLE x;--', 10, 10)
        self.assertIn("unsafe table name", out["error"])


class TestDataAssertions(unittest.TestCase):
    """data_equals / data_persists / data_changed 判定 + key 寻址（集成契约核心）。"""

    @classmethod
    def setUpClass(cls):
        cls.after = json.loads(
            (FIXTURES / "data_probe_cresto_sample.json").read_text(encoding="utf-8"))
        cls.before = json.loads(json.dumps(cls.after))
        cls.before["preferences"]["sort_order"] = False
        cls.before["tables"]["todo_items"] = []
        cls.restart = cls.after   # 模拟持久化成功（值相同）

    def _eval(self, assertions, before=None, after=None, restart="default"):
        return adp.evaluate_data_assertions(
            assertions,
            self.before if before is None else before,
            self.after if after is None else after,
            self.restart if restart == "default" else restart)

    def test_data_equals_bool_semantics(self):
        (r,) = self._eval([{"kind": "data_equals", "key": "prefs.sort_order",
                            "value": "true"}])
        self.assertEqual(r["verdict"], "PASS")

    def test_data_equals_mismatch_fails_with_actual(self):
        (r,) = self._eval([{"kind": "data_equals", "key": "prefs.sort_order",
                            "value": "false"}])
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("True", r["note"])

    def test_count_and_row_and_exists_addressing(self):
        results = self._eval([
            {"kind": "data_equals", "key": "count:todo_items", "value": "1"},
            {"kind": "data_equals", "key": "row:todo_items[id=1].isCompleted",
             "value": "1"},
            {"kind": "data_equals", "key": "row:todo_items[id=1].dueDate",
             "value": "2026-09-05"},
            {"kind": "data_equals",
             "key": "exists:todo_items[isCompleted=1]", "value": "true"},
            {"kind": "data_equals", "key": "count:todo_groups", "value": "0"},
        ])
        self.assertTrue(all(r["verdict"] == "PASS" for r in results),
                        [r for r in results if r["verdict"] != "PASS"])

    def test_row_match_string_loose_number(self):
        # SQLite TEXT 列 vs 断言值：字符串精确；数值列宽松比较
        results = self._eval([
            {"kind": "data_equals", "key": "row:todo_items[id=1].flag",
             "value": 0},
            {"kind": "data_equals",
             "key": "exists:todo_items[dueDate=2026-09-05]", "value": "true"},
        ])
        self.assertTrue(all(r["verdict"] == "PASS" for r in results))

    def test_data_persists_uses_restart_state(self):
        (r,) = self._eval([{"kind": "data_persists", "key": "prefs.sort_order",
                            "value": "true"}])
        self.assertEqual(r["verdict"], "PASS")

    def test_data_persists_missing_restart_unsupported(self):
        # fail-closed 分层：restart 文件缺失/DENIED -> 采集受阻，非行为矛盾
        (r,) = self._eval([{"kind": "data_persists", "key": "prefs.sort_order",
                            "value": "true"}], restart=None)
        self.assertEqual(r["verdict"], "UNSUPPORTED")
        self.assertIn("restart-state unreadable", r["note"])

    def test_data_changed_pass_and_fail(self):
        results = self._eval([
            {"kind": "data_changed", "key": "prefs.sort_order", "value": ""},
            {"kind": "data_changed", "key": "prefs.is_first_run", "value": ""},
        ])
        self.assertEqual(results[0]["verdict"], "PASS")   # False -> True
        self.assertEqual(results[1]["verdict"], "FAIL")   # 两点相同

    def test_data_changed_missing_side_unsupported(self):
        (r,) = self._eval([{"kind": "data_changed", "key": "prefs.sort_order",
                            "value": ""}], before=None, after={})
        self.assertEqual(r["verdict"], "UNSUPPORTED")

    def test_unknown_key_and_kind(self):
        results = self._eval([
            {"kind": "data_equals", "key": "prefs.missing_key", "value": "x"},
            {"kind": "data_equals", "key": "garbage key !!", "value": "x"},
            {"kind": "data_equals", "key": "count:not_probed", "value": "0"},
            {"kind": "magic_assert", "key": "prefs.sort_order", "value": "1"},
        ])
        self.assertTrue(all(r["verdict"] == "UNSUPPORTED" for r in results))

    def test_denied_state_resolves_unsupported(self):
        denied = {"schema": adp.SCHEMA_VERSION, "access_mode": "DENIED",
                  "preferences": {}, "tables": {}}
        (r,) = self._eval([{"kind": "data_equals", "key": "prefs.x",
                            "value": "1"}], before=denied, after=denied,
                          restart=denied)
        self.assertEqual(r["verdict"], "UNSUPPORTED")


class TestToolGapAndDeniedPath(unittest.TestCase):
    """adb 不可达 -> DENIED 报告仍产出（TOOL_GAP 显式，不崩溃不伪造）。"""

    def test_denied_report_written_and_exit_3(self):
        calls = {"n": 0}

        def dead_execout(adb, serial, shell_args, timeout):
            calls["n"] += 1
            return None

        original = adp._adb_execout
        adp._adb_execout = dead_execout
        try:
            with TemporaryDirectory() as tmp:
                out = Path(tmp) / "probe.json"
                rc = adp.main(["--package", "com.nevoit.cresto",
                              "--device", "emulator-5554",
                              "--out", str(out)])
                self.assertEqual(rc, 3)
                self.assertTrue(out.exists())
                report = json.loads(out.read_text(encoding="utf-8"))
                self.assertEqual(report["access_mode"], "DENIED")
                self.assertEqual(report["preferences"], {})
                self.assertEqual(report["tables"], {})
                self.assertTrue(any(g["store"] == "*" for g in report["tool_gaps"]))
        finally:
            adp._adb_execout = original

    def test_allow_denied_flag_returns_zero(self):
        def dead_execout(adb, serial, shell_args, timeout):
            return None

        original = adp._adb_execout
        adp._adb_execout = dead_execout
        try:
            with TemporaryDirectory() as tmp:
                out = Path(tmp) / "probe.json"
                rc = adp.main(["--package", "com.nevoit.cresto",
                              "--device", "emulator-5554",
                              "--out", str(out), "--allow-denied"])
                self.assertEqual(rc, 0)
        finally:
            adp._adb_execout = original

    def test_invalid_package_rejected(self):
        with self.assertRaises(SystemExit):
            adp.main(["--package", "bad pkg!!", "--out", "/tmp/x.json"])


class TestRealFixtureIntegrity(unittest.TestCase):
    """锁住真实 Cresto 探针输出样例的 schema（android-data-probe/1）。"""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(
            (FIXTURES / "data_probe_cresto_sample.json").read_text(encoding="utf-8"))

    def test_schema_fields(self):
        r = self.report
        self.assertEqual(r["schema"], "android-data-probe/1")
        self.assertEqual(r["package"], "com.nevoit.cresto")
        self.assertEqual(r["device"], "emulator-5554")
        self.assertEqual(r["access_mode"], "run-as")
        self.assertIn("captured_at", r)

    def test_real_preferences_content(self):
        prefs = self.report["preferences"]
        self.assertIs(prefs["is_first_run"], False)
        self.assertIs(prefs["sort_order"], True)
        self.assertIs(prefs["sort_option"], True)
        self.assertEqual(prefs["last_update_check_at"], 1788006648365)

    def test_real_tables_content(self):
        tables = self.report["tables"]
        self.assertEqual(set(tables),
                         {"todo_items", "todo_groups", "repeat_rules",
                          "sub_todo_items"})
        (row,) = tables["todo_items"]
        self.assertEqual(row["id"], 1)
        self.assertEqual(row["isCompleted"], 1)
        self.assertIsNone(row["deletedAt"])

    def test_stores_and_gaps_audit(self):
        statuses = {s["store"]: s["status"] for s in self.report["stores"]}
        self.assertEqual(statuses["mmkv:mmkv.default"], "READ")
        self.assertEqual(statuses["sqlite:todo_database"], "READ")
        self.assertEqual(
            statuses["datastore:GlanceAppWidgetManager-com.nevoit.cresto.preferences_pb"],
            "TOOL_GAP")
        reasons = " ".join(g["reason"] for g in self.report["tool_gaps"])
        self.assertIn("DataStore", reasons)
        self.assertIn("MISSING_IN_DB", reasons)   # settings_prefs 显式缺口


if __name__ == "__main__":
    unittest.main()