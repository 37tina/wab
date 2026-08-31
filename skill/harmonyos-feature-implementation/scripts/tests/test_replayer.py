#!/usr/bin/env python3
"""replayer.py 单元测试（无设备环境：FakeDriver 注入，跑断言判定逻辑、
四类分类/义务计算、防伪 foreground 路径与 CSV 格式）。"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import replayer  # noqa: E402
from replayer import (  # noqa: E402
    FAIL,
    MANUAL,
    NA,
    PASS,
    PLATFORM,
    SKIPPED,
    DeviceDriver,
    QueryResult,
    UiSnapshot,
    aggregate_verdict,
    assertion_obligations,
    classify_assertions,
    evaluate_data,
    evaluate_observable,
    evaluate_side_effect,
    extract_segments,
    locate_bounds_center,
    parse_json_column,
    parse_ui_dump,
    replay_bc,
    replay_workspace,
    select_replay_bcs,
    validate_results,
    verify_precondition_snapshot,
)

BUNDLE = "com.example.todo"
ABILITY = "EntryAbility"


class FakeDriver:
    """可编程假驱动：按脚本推进 UI/数据状态，可注入防伪故障。

    ui_texts 表示「操作后」稳定快照；locate 默认总能定位（模拟可点目标），
    missing_targets 中的目标返回 None（模拟找不到 → 步骤中断）。
    """

    def __init__(self, ui_texts=None, data=None, foreground=None,
                 notification=None, files=None, leave_foreground_at=None,
                 data_unavailable=False, missing_targets=None):
        self.ui_texts = list(ui_texts or [])
        self.data = dict(data or {})
        self.foreground = foreground if foreground is not None else BUNDLE
        self.notification = notification or ""
        self.files = set(files or [])
        self.leave_foreground_at = leave_foreground_at  # 步序号(1-based)后离开前台
        self.data_unavailable = data_unavailable
        self.missing_targets = set(missing_targets or [])
        self.step_count = 0
        self.force_stopped = 0

    # DeviceDriver 协议实现
    def foreground_bundle(self) -> str:
        return self.foreground

    def ui_snapshot(self) -> UiSnapshot:
        return UiSnapshot(raw=json.dumps(self.ui_texts), texts=self.ui_texts,
                          components=[])

    def locate(self, snapshot, target):
        return None if target in self.missing_targets else (100, 200)

    def tap(self, x, y):
        self.step_count += 1
        self._maybe_leave()

    def input_text(self, x, y, text):
        self.step_count += 1
        self._maybe_leave()

    def key_back(self):
        self.step_count += 1
        self._maybe_leave()

    def swipe(self, x1, y1, x2, y2):
        self.step_count += 1
        self._maybe_leave()

    def long_press(self, x, y):
        self.step_count += 1
        self._maybe_leave()

    def force_stop(self, bundle):
        self.force_stopped += 1

    def start_ability(self, bundle, ability):
        pass

    def query_notification(self, key):
        return QueryResult(True, key.lower() in self.notification.lower())

    def file_exists(self, device_path):
        return QueryResult(True, device_path in self.files)

    def export_app_data(self, bundle):
        return None if self.data_unavailable else dict(self.data)

    # 测试辅助
    def _maybe_leave(self):
        if (self.leave_foreground_at is not None
                and self.step_count >= self.leave_foreground_at):
            self.foreground = "com.other.app"


def write_csv_file(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def steps_json(steps):
    return json.dumps(steps, ensure_ascii=False)


def bc_row(bc_id="BC-TEST-01", feature_id="FEATURE-TODO-CREATE", **extra):
    row = {
        "bc_id": bc_id, "feature_id": feature_id,
        "page_ref": "PAGE-MAIN", "user_intent": "新增待办",
        "pre_state": "主页可见", "operation": "点新增，输入标题，保存",
        "data_state_change": "", "observable_result": "",
        "persistence_targets": "", "external_side_effects": "",
        "evidence_class": "RUNTIME_REQUIRED", "impact": "high",
        "source_refs": "app/src/x.kt:1",
        "operation_steps": "[]", "result_assertions": "[]",
    }
    row.update(extra)
    return row


class SegmentExtractionTest(unittest.TestCase):
    def test_v3_column_aliases(self):
        segments = extract_segments(bc_row(user_intent="意图", pre_state="前置",
                                           data_state_change="数据变化",
                                           persistence_targets="mmkv:k",
                                           external_side_effects="通知"))
        self.assertEqual(segments["intent"], "意图")
        self.assertEqual(segments["precondition"], "前置")
        self.assertEqual(segments["expected_state_change"], "数据变化")
        self.assertEqual(segments["persistence"], "mmkv:k")
        self.assertEqual(segments["side_effect"], "通知")
        self.assertEqual(segments["semantic_input"], "")  # v4 新列可选

    def test_v4_columns_preferred(self):
        segments = extract_segments(bc_row(
            intent="i", precondition="p", semantic_input="9/5",
            expected_state_change="e", persistence="y", side_effect="s"))
        self.assertEqual(segments["intent"], "i")
        self.assertEqual(segments["semantic_input"], "9/5")
        self.assertEqual(segments["persistence"], "y")

    def test_parse_json_column_broken(self):
        self.assertEqual(parse_json_column(""), [])
        self.assertEqual(parse_json_column("not-json"), [])
        self.assertTrue(replayer.json_column_broken("not-json"))
        self.assertFalse(replayer.json_column_broken(""))


class AssertionLogicTest(unittest.TestCase):
    def test_classify_and_obligations(self):
        buckets = classify_assertions([
            {"kind": "text_visible", "value": "9/5"},
            {"kind": "data_object", "object": "sort_option"},
            {"kind": "persist_after_restart", "value": "9/5"},
            {"kind": "notification", "key": "提醒"},
            {"kind": "weird_kind"},
        ])
        self.assertEqual(len(buckets["observable"]), 1)
        self.assertEqual(len(buckets["data"]), 1)
        self.assertEqual(len(buckets["persistence"]), 1)
        self.assertEqual(len(buckets["side_effect"]), 1)
        self.assertEqual(len(buckets["unknown"]), 1)

        segments = extract_segments(bc_row())
        obligations = assertion_obligations(segments, buckets)
        # 段全空但有断言 → assert；unknown 存在 → manual 兜底
        self.assertEqual(obligations["observable"], "manual")

        empty = assertion_obligations(
            {s: "" for s in replayer.SEVEN_SEGMENTS},
            {"observable": [], "data": [], "persistence": [],
             "side_effect": [], "unknown": []})
        self.assertEqual(set(empty.values()), {"none"})

    def test_obligation_segment_without_assertions_is_manual(self):
        obligations = assertion_obligations(
            extract_segments(bc_row(observable_result="列表过滤")),
            {"observable": [], "data": [], "persistence": [],
             "side_effect": [], "unknown": []})
        self.assertEqual(obligations["observable"], "manual")

    def test_observable_verdicts(self):
        snap = UiSnapshot(raw="[]", texts=["已完成 9/5"], components=[
            {"type": "Checkbox", "text": "买牛奶", "id": "cb1",
             "checked": "true", "visible": "true", "enabled": "true"}])
        self.assertEqual(evaluate_observable(
            {"kind": "text_visible", "value": "9/5"}, snap), PASS)
        self.assertEqual(evaluate_observable(
            {"kind": "text_visible", "value": "不存在"}, snap), FAIL)
        self.assertEqual(evaluate_observable(
            {"kind": "text_gone", "value": "不存在"}, snap), PASS)
        self.assertEqual(evaluate_observable(
            {"kind": "text_gone", "value": "9/5"}, snap), FAIL)
        self.assertEqual(evaluate_observable(
            {"kind": "component_state", "target": "买牛奶",
             "attr": "checked", "value": "true"}, snap), PASS)
        self.assertEqual(evaluate_observable(
            {"kind": "component_state", "target": "买牛奶",
             "attr": "checked", "value": "false"}, snap), FAIL)
        self.assertEqual(evaluate_observable(
            {"kind": "component_state", "target": "没有的",
             "attr": "checked", "value": "true"}, snap), FAIL)
        # 断言残缺 → FAIL（铁律：不解释）
        self.assertEqual(evaluate_observable(
            {"kind": "text_visible", "value": ""}, snap), FAIL)

    def test_data_verdicts(self):
        assertion = {"kind": "data_object", "object": "sort_option",
                     "op": "equals", "value": "截止日期"}
        self.assertEqual(evaluate_data(assertion,
                                       {"sort_option": "截止日期"}), PASS)
        self.assertEqual(evaluate_data(assertion,
                                       {"sort_option": "创建时间"}), FAIL)
        self.assertEqual(evaluate_data(assertion, {}), FAIL)
        # 自检接口缺失 → FAIL（实施义务，不降级）
        self.assertEqual(evaluate_data(assertion, None), FAIL)
        self.assertEqual(evaluate_data(
            {"kind": "data_object", "object": "k", "op": "not_exists"},
            {"other": 1}), PASS)
        self.assertEqual(evaluate_data(
            {"kind": "data_object", "object": "n", "op": "gt", "value": "2"},
            {"n": 5}), PASS)

    def test_side_effect_verdicts(self):
        driver = FakeDriver(notification="待办提醒：买牛奶",
                            files=["Documents/todo.csv"])
        self.assertEqual(evaluate_side_effect(
            {"kind": "notification", "key": "买牛奶"}, driver), PASS)
        self.assertEqual(evaluate_side_effect(
            {"kind": "notification", "key": "没有的"}, driver), FAIL)
        self.assertEqual(evaluate_side_effect(
            {"kind": "file_export", "path": "Documents/todo.csv"}, driver), PASS)
        # 无公开 API 的系统副作用 → MANUAL（不是 PASS）
        self.assertEqual(evaluate_side_effect(
            {"kind": "calendar", "value": "x"}, driver), MANUAL)
        self.assertEqual(evaluate_side_effect(
            {"kind": "clipboard", "value": "x"}, driver), MANUAL)
        # 未知 kind → MANUAL（保守进人工队列）
        self.assertEqual(evaluate_side_effect(
            {"kind": "future_thing"}, driver), MANUAL)

    def test_side_effect_platform_limitation(self):
        class NoQueryDriver(FakeDriver):
            def query_notification(self, key):
                raise replayer.DriverUnavailable("no anm")

            def file_exists(self, path):
                raise replayer.DriverUnavailable("no fs")

        driver = NoQueryDriver()
        self.assertEqual(evaluate_side_effect(
            {"kind": "notification", "key": "x"}, driver), PLATFORM)
        self.assertEqual(evaluate_side_effect(
            {"kind": "file_export", "path": "x"}, driver), PLATFORM)

    def test_aggregate_priority(self):
        # FAIL 最严（铁律），其后 MANUAL > PLATFORM > PASS > NA
        self.assertEqual(aggregate_verdict([PASS, FAIL, MANUAL]), FAIL)
        self.assertEqual(aggregate_verdict([PASS, MANUAL, PLATFORM]), MANUAL)
        self.assertEqual(aggregate_verdict([PASS, PLATFORM]), PLATFORM)
        self.assertEqual(aggregate_verdict([PASS, PASS]), PASS)
        self.assertEqual(aggregate_verdict([]), NA)
        self.assertEqual(replayer.replay_verdict_of(
            {"observable": PASS, "data": NA, "persistence": NA,
             "side_effect": MANUAL}), MANUAL)
        self.assertEqual(replayer.replay_verdict_of(
            {"observable": NA, "data": NA, "persistence": NA,
             "side_effect": NA}), NA)


class ParseUiDumpTest(unittest.TestCase):
    def test_parse_nested_tree(self):
        raw = json.dumps({
            "attributes": {"type": "Column"},
            "children": [
                {"attributes": {"type": "Text", "text": "待办",
                                "visible": "true"}},
                {"attributes": {"type": "Checkbox", "text": "买牛奶",
                                "checked": "true", "id": "cb1"},
                 "children": []},
            ]})
        snapshot = parse_ui_dump(raw)
        self.assertEqual(snapshot.texts, ["待办", "买牛奶"])
        self.assertTrue(snapshot.shows_text("买牛"))
        self.assertEqual(snapshot.component_attr("买牛奶", "checked"), "true")
        self.assertIsNone(snapshot.component_attr("没有", "checked"))

    def test_bad_json_falls_back_to_raw(self):
        snapshot = parse_ui_dump("plain 9/5 text")
        self.assertEqual(snapshot.texts, [])
        self.assertTrue(snapshot.shows_text("9/5"))  # raw 兜底

    def test_locate_bounds_center(self):
        raw = json.dumps({"attributes": {"type": "Button", "text": "新增",
                                         "bounds": [10, 20, 110, 220]}})
        self.assertEqual(locate_bounds_center(raw, "新增"), (60, 120))
        self.assertIsNone(locate_bounds_center(raw, "不存在"))


class SelectionTest(unittest.TestCase):
    def test_feature_map_selection(self):
        feature_map = {"runtime_features": {"FEATURE-A"},
                       "source_confirm_features": {"FEATURE-B"},
                       "missing": False}
        rows = [bc_row("BC-A1", "FEATURE-A"),
                bc_row("BC-B1", "FEATURE-B"),
                bc_row("BC-X1", "FEATURE-X")]
        selection = select_replay_bcs(rows, feature_map)
        self.assertEqual([r["bc_id"] for r in selection["selected"]], ["BC-A1"])
        self.assertEqual([r["bc_id"] for r in selection["skipped"]], ["BC-B1"])
        self.assertEqual([r["bc_id"] for r in selection["unmapped"]], ["BC-X1"])

    def test_fallback_evidence_class(self):
        selection = select_replay_bcs(
            [bc_row("BC-R", evidence_class="RUNTIME_REQUIRED"),
             bc_row("BC-S", evidence_class="STATIC_ONLY")],
            {"runtime_features": set(), "source_confirm_features": set(),
             "missing": True})
        self.assertTrue(selection["fallback"])
        self.assertEqual([r["bc_id"] for r in selection["selected"]], ["BC-R"])


class ReplayBcTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="replayer-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, driver, assertions, segments=None, steps=None):
        extra = {"result_assertions": steps_json(assertions)}
        extra.update(segments or {})
        bc = bc_row(**extra)
        steps = steps if steps is not None else [
            {"action": "tap", "target": "新增"}]
        return replay_bc(bc, steps, driver, BUNDLE, ABILITY,
                         self.root / "evidence")

    def test_all_pass_with_persistence(self):
        driver = FakeDriver(ui_texts=["已保存：买牛奶"],
                            data={"todo_count": "1"},
                            notification="待办提醒：买牛奶")
        row = self._run(driver, [
            {"kind": "text_visible", "value": "已保存：买牛奶"},
            {"kind": "data_object", "object": "todo_count",
             "op": "equals", "value": "1"},
            {"kind": "persist_after_restart", "value": "已保存：买牛奶"},
            {"kind": "notification", "key": "买牛奶"},
        ], segments={"persistence_targets": "mmkv:todos",
                     "external_side_effects": "通知"})
        self.assertEqual(row["observable_result"], PASS)
        self.assertEqual(row["data_result"], PASS)
        self.assertEqual(row["persistence_result"], PASS)
        self.assertEqual(row["side_effect_result"], PASS)
        self.assertEqual(row["replay_verdict"], PASS)
        # 批次 2 #85：prepare 冷复位 1 次 + persistence 重启 1 次 = 2
        self.assertEqual(driver.force_stopped, 2)
        self.assertEqual(row["precondition_status"], "ESTABLISHED")
        self.assertTrue((self.root / "evidence/chains/BC-TEST-01/replay"
                         / "assertions.json").exists())

    def test_assertion_fail_is_fail(self):
        driver = FakeDriver(ui_texts=["别的文案"], data={"todo_count": "0"})
        row = self._run(driver, [
            {"kind": "text_visible", "value": "已保存：买牛奶"},
            {"kind": "data_object", "object": "todo_count",
             "op": "equals", "value": "1"},
        ], segments={"persistence_targets": "mmkv:todos"})
        self.assertEqual(row["observable_result"], FAIL)
        self.assertEqual(row["data_result"], FAIL)
        self.assertEqual(row["persistence_result"], FAIL)  # 重验同样 FAIL
        self.assertEqual(row["replay_verdict"], FAIL)
        self.assertIn("observable=FAIL", row["fail_reason"])

    def test_steps_interrupted_fails_all(self):
        driver = FakeDriver(ui_texts=["别的"], missing_targets={"保存"})
        row = self._run(driver, [
            {"kind": "text_visible", "value": "已保存"},
        ], segments={"persistence_targets": "mmkv:k"}, steps=[
            {"action": "tap", "target": "新增"},
            {"action": "tap", "target": "保存"},
        ])
        self.assertEqual(row["steps_ok"], 1)
        self.assertEqual(row["steps_total"], 2)
        # 四类独立判定：有义务的类 FAIL；无义务的类保持 NA
        self.assertEqual(row["observable_result"], FAIL)
        self.assertEqual(row["persistence_result"], FAIL)
        self.assertEqual(row["data_result"], NA)       # BC 未声明数据义务
        self.assertEqual(row["side_effect_result"], NA)
        # 总判定 fail-closed：中断 → FAIL
        self.assertEqual(row["replay_verdict"], FAIL)
        self.assertIn("steps_interrupted", row["fail_reason"])
        self.assertIn("steps interrupted", row["note"])

    def test_no_steps_recorded_fails_closed(self):
        driver = FakeDriver(ui_texts=["新增"])
        row = self._run(driver, [], steps=[])
        self.assertEqual(row["replay_verdict"], FAIL)
        self.assertIn("no_harmony_steps", row["fail_reason"])
        self.assertIn("no harmony_steps", row["note"])

    def test_foreguard_left_target_app(self):
        driver = FakeDriver(ui_texts=["新增", "保存"],
                            leave_foreground_at=1)
        row = self._run(driver, [
            {"kind": "text_visible", "value": "保存"},
        ], segments={"observable_result": "保存按钮可见"},
        steps=[{"action": "tap", "target": "新增"}])
        # 防伪：点第一步后离开前台 → 步骤中断 → fail-closed
        self.assertEqual(row["replay_verdict"], FAIL)
        self.assertIn("foreground", (self.root / "evidence/chains/BC-TEST-01"
                                     / "replay/operations.log")
                      .read_text(encoding="utf-8"))

    def test_segment_without_assertions_goes_manual(self):
        driver = FakeDriver(ui_texts=["x"])
        row = self._run(driver, [], segments={
            "observable_result": "列表按日期重排"})  # 段非空、无断言
        self.assertEqual(row["observable_result"], MANUAL)
        self.assertEqual(row["replay_verdict"], MANUAL)

    def test_na_when_no_obligation(self):
        driver = FakeDriver(ui_texts=["x"])
        row = self._run(driver, [])  # 段全空、无断言 → 全 NA
        self.assertEqual(row["observable_result"], NA)
        self.assertEqual(row["side_effect_result"], NA)
        self.assertEqual(row["replay_verdict"], NA)

    def test_side_effect_manual_queue(self):
        driver = FakeDriver(ui_texts=["x"])
        row = self._run(driver, [
            {"kind": "calendar", "value": "写入日历"},
        ], segments={"external_side_effects": "日历"})
        self.assertEqual(row["side_effect_result"], MANUAL)
        self.assertEqual(row["replay_verdict"], MANUAL)


class PreconditionTest(unittest.TestCase):
    """批次 2 #85：prepare 阶段（reset → prepare_steps → verify）单测。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="replayer-pre-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, driver, assertions, segments=None, steps=None,
             prepare=None):
        extra = {"result_assertions": steps_json(assertions)}
        if prepare is not None:
            extra["prepare_steps"] = steps_json(prepare)
        extra.update(segments or {})
        bc = bc_row(**extra)
        steps = steps if steps is not None else [
            {"action": "tap", "target": "新增"}]
        return replay_bc(bc, steps, driver, BUNDLE, ABILITY,
                         self.root / "evidence")

    def _ops_log(self, bc_id="BC-TEST-01"):
        return (self.root / "evidence" / "chains" / bc_id / "replay"
                / "operations.log").read_text(encoding="utf-8")

    def test_verify_precondition_tokens_visible(self):
        snapshot = UiSnapshot(raw='["中文", "深色"]',
                              texts=["中文", "深色"], components=[])
        ok, note = verify_precondition_snapshot("语言=中文", snapshot)
        self.assertTrue(ok)
        self.assertIn("precondition verified", note)

    def test_verify_precondition_missing_token(self):
        snapshot = UiSnapshot(raw="[]", texts=["英文"], components=[])
        ok, note = verify_precondition_snapshot("语言=中文", snapshot)
        self.assertFalse(ok)
        self.assertIn("missing on page", note)
        self.assertIn("中文", note)

    def test_verify_precondition_no_tokens_records_only(self):
        snapshot = UiSnapshot(raw="[]", texts=[], components=[])
        ok, note = verify_precondition_snapshot("主页可见", snapshot)
        self.assertTrue(ok)  # 仅记录口径：自然语言不阻塞链
        self.assertIn("no machine-checkable tokens", note)

    def test_precondition_established_with_prepare_steps(self):
        driver = FakeDriver(ui_texts=["看板"])
        row = self._run(
            driver,
            [{"kind": "text_visible", "value": "看板"}],
            segments={"pre_state": "视图=看板"},
            prepare=[{"action": "tap", "target": "视图切换"}])
        self.assertEqual(row["precondition_status"], "ESTABLISHED")
        self.assertEqual(row["replay_verdict"], PASS)
        self.assertIn("[prep 1/1] ok", self._ops_log())

    def test_precondition_failed_goes_manual_queue(self):
        # pre_state token 在页面上不可见且无 prepare_steps 可修复
        # → 两次尝试（含冷复位重试）后 PRECONDITION_FAILED：
        # 四类一律 MANUAL（人工裁决队列），不算功能 FAIL。
        driver = FakeDriver(ui_texts=["英文列表"])
        row = self._run(
            driver,
            [{"kind": "text_visible", "value": "英文列表"},
             {"kind": "data_object", "object": "k", "op": "exists"}],
            segments={"pre_state": "语言=中文",
                      "data_state_change": "k 变化",
                      "persistence_targets": "mmkv:k",
                      "external_side_effects": "通知"})
        self.assertEqual(row["precondition_status"],
                         replayer.PRECONDITION_FAILED)
        self.assertEqual(row["replay_verdict"],
                         replayer.PRECONDITION_FAILED)
        self.assertEqual(row["observable_result"], MANUAL)
        self.assertEqual(row["data_result"], MANUAL)
        self.assertEqual(row["persistence_result"], MANUAL)
        self.assertEqual(row["side_effect_result"], MANUAL)
        self.assertIn("precondition_failed", row["fail_reason"])
        # 两次尝试：初始 + 冷复位重试 #1（prepare 段实测）
        self.assertIn("retry #1", self._ops_log())
        self.assertIn("PRECONDITION_FAILED", self._ops_log())

    def test_reset_failed_when_app_never_foreground(self):
        driver = FakeDriver(ui_texts=["x"], foreground="")
        row = self._run(driver, [], segments=None)
        self.assertEqual(row["precondition_status"],
                         replayer.PRECONDITION_FAILED)
        self.assertIn("reset", self._ops_log())

    def test_validate_accepts_precondition_failed_rows(self):
        out = self.root / "results.csv"
        write_csv_file(out, replayer.REPLAY_CSV_FIELDS, [
            {"bc_id": "BC-P1", "feature_id": "F", "verify_mode": "RUNTIME",
             "precondition_status": "PRECONDITION_FAILED",
             "steps_total": "2", "steps_ok": "0",
             "observable_result": "MANUAL_VERIFY_REQUIRED",
             "data_result": "MANUAL_VERIFY_REQUIRED",
             "persistence_result": "MANUAL_VERIFY_REQUIRED",
             "side_effect_result": "MANUAL_VERIFY_REQUIRED",
             "replay_verdict": "PRECONDITION_FAILED",
             "fail_reason": "precondition_failed",
             "evidence_dir": str(self.root / "evidence"),
             "note": "PRECONDITION_FAILED: token missing"},
        ])
        (self.root / "evidence").mkdir(parents=True, exist_ok=True)
        self.assertEqual(validate_results(out), [])


class HdcProbeChannelTest(unittest.TestCase):
    """DebugSemanticProbe 通道（批次 2 #85）：沙箱文件主通道 + hilog 退化。"""

    def test_export_app_data_hilog_fallback(self):
        driver = replayer.HdcDeviceDriver(bundle="com.example.todo")
        calls = []

        def fake_run(*args, timeout=30):
            calls.append(args)
            if args[:2] == ("file", "recv"):
                raise replayer.DriverUnavailable("recv failed")
            if args[:3] == ("shell", "hilog", "-x"):
                return ("08-30 21:00:00 I A0123/SemanticProbe "
                        "SNAPSHOT {\"todo_items\": [], \"_probe_ts\": 1}\n"
                        "08-30 21:00:01 I A0123/Other tag noise\n")
            return ""

        driver._run = fake_run
        data = driver.export_app_data("com.example.todo")
        self.assertEqual(data, {"todo_items": [], "_probe_ts": 1})
        # 主通道（file recv）先试，退化到 hilog
        self.assertEqual(calls[0][:2], ("file", "recv"))
        self.assertTrue(any(a[:3] == ("shell", "hilog", "-x")
                            for a in calls))

    def test_export_app_data_all_channels_down_returns_none(self):
        driver = replayer.HdcDeviceDriver(bundle="com.example.todo")

        def fake_run(*args, timeout=30):
            if args[:2] == ("file", "recv"):
                raise replayer.DriverUnavailable("recv failed")
            if args[:3] == ("shell", "hilog", "-x"):
                return "no probe lines here"
            return ""

        driver._run = fake_run
        self.assertIsNone(driver.export_app_data("com.example.todo"))

    def test_replay_data_json_channel_removed(self):
        # 旧通道退役：源码不再引用 replay-data.json 自答文件名
        source = (SCRIPTS / "replayer.py").read_text(encoding="utf-8")
        self.assertNotIn('"replay-data.json"', source)
        self.assertIn("semantic-probe.json", source)



class ReplayWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="replayer-ws-")
        self.root = Path(self.temp.name)
        self.bc_path = self.root / "behavior-contracts.csv"
        write_csv_file(self.bc_path, [
            "bc_id", "feature_id", "page_ref", "user_intent", "pre_state",
            "operation", "data_state_change", "business_computation_refs",
            "observable_result", "persistence_targets",
            "external_side_effects", "evidence_class", "impact",
            "source_refs", "operation_steps", "result_assertions"],
            [
                bc_row("BC-A1", "FEATURE-A",
                       result_assertions=steps_json(
                           [{"kind": "text_visible", "value": "已保存"}]),
                       observable_result="保存成功提示"),
                bc_row("BC-B1", "FEATURE-B"),
                bc_row("BC-X1", "FEATURE-X"),
            ])
        self.steps_path = self.root / "harmony-steps.csv"
        write_csv_file(self.steps_path,
                       ["bc_id", "feature_id", "steps", "notes"],
                       [{"bc_id": "BC-A1", "feature_id": "FEATURE-A",
                         "steps": steps_json(
                             [{"action": "tap", "target": "新增"}]),
                         "notes": ""}])
        self.feature_map = self.root / "feature-map.json"
        self.feature_map.write_text(json.dumps({
            "schema_version": 1,
            "features": [
                {"feature_id": "FEATURE-A", "verify_mode": "RUNTIME",
                 "surfaces": []},
                {"feature_id": "FEATURE-B", "verify_mode": "SOURCE_CONFIRM",
                 "surfaces": []},
            ],
            "coverage_gate": {"included_features_covered": True,
                              "included": ["FEATURE-A", "FEATURE-B"],
                              "covered": ["FEATURE-A", "FEATURE-B"],
                              "missing": []},
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_workspace_csv_format(self):
        driver = FakeDriver(ui_texts=["已保存"])
        out = self.root / "replay-results.csv"
        result = replay_workspace(
            self.bc_path, self.steps_path, self.feature_map, driver,
            BUNDLE, ABILITY, out, self.root / "evidence")
        rows = result["rows"]
        by_id = {r["bc_id"]: r for r in rows}
        self.assertEqual(by_id["BC-A1"]["replay_verdict"], PASS)
        self.assertEqual(by_id["BC-A1"]["observable_result"], PASS)
        self.assertEqual(by_id["BC-B1"]["replay_verdict"], SKIPPED)
        self.assertEqual(by_id["BC-X1"]["replay_verdict"], FAIL)  # unmapped
        self.assertEqual(result["stats"]["replayed"], 1)
        self.assertEqual(result["stats"]["skipped"], 1)
        self.assertEqual(result["stats"]["unmapped"], 1)
        # CSV 列契约（Gate 4 / I 代理消费面）
        with out.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(reader.fieldnames,
                             replayer.REPLAY_CSV_FIELDS)
            file_rows = list(reader)
        self.assertEqual(len(file_rows), 3)
        # validate 子命令通过
        self.assertEqual(validate_results(out), [])

    def test_missing_harmony_steps_fails_closed(self):
        driver = FakeDriver(ui_texts=["已保存"])
        out = self.root / "replay-results.csv"
        result = replay_workspace(
            self.bc_path, None, self.feature_map, driver,
            BUNDLE, ABILITY, out, self.root / "evidence")
        # BC-A1 无 steps 记录 → FAIL；BC-X1 unmapped → FAIL（fail-closed 共 2）
        self.assertEqual(result["stats"]["fail"], 2)
        self.assertIn("BC-A1", result["stats"]["missing_steps"])
        by_id = {r["bc_id"]: r for r in result["rows"]}
        self.assertEqual(by_id["BC-A1"]["replay_verdict"], FAIL)

    def test_validate_results_negative(self):
        out = self.root / "bad-results.csv"
        write_csv_file(out, replayer.REPLAY_CSV_FIELDS, [
            {"bc_id": "BC-1", "feature_id": "F", "verify_mode": "RUNTIME",
             "steps_total": "1", "steps_ok": "1",
             "observable_result": "PASS", "data_result": "PASS",
             "persistence_result": "PASS", "side_effect_result": "PASS",
             "replay_verdict": "FAIL", "fail_reason": "",
             "evidence_dir": "/nope", "note": ""},
            {"bc_id": "BC-2", "feature_id": "F", "verify_mode": "RUNTIME",
             "steps_total": "1", "steps_ok": "1",
             "observable_result": "WHATEVER", "data_result": "PASS",
             "persistence_result": "PASS", "side_effect_result": "PASS",
             "replay_verdict": "PASS", "fail_reason": "",
             "evidence_dir": "", "note": ""},
        ])
        errors = validate_results(out)
        self.assertTrue(any("fail_reason" in e for e in errors))
        self.assertTrue(any("observable_result" in e for e in errors))
        self.assertTrue(any("evidence_dir" in e for e in errors))


class CliDryRunTest(unittest.TestCase):
    def test_dry_run_reports_plan_without_device(self):
        with tempfile.TemporaryDirectory(prefix="replayer-cli-") as tmp:
            root = Path(tmp)
            bc_path = root / "bc.csv"
            fields = ["bc_id", "feature_id", "evidence_class",
                      "result_assertions"]
            row = bc_row("BC-1", "FEATURE-A",
                         evidence_class="RUNTIME_REQUIRED",
                         result_assertions=steps_json(
                             [{"kind": "text_visible", "value": "x"}]))
            write_csv_file(bc_path, fields,
                           [{f: row[f] for f in fields}])
            proc = __import__("subprocess").run(
                [sys.executable, str(SCRIPTS / "replayer.py"), "replay",
                 "--bc", str(bc_path), "--bundle", BUNDLE,
                 "--out", str(root / "r.csv"), "--dry-run"],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            self.assertEqual(report["selected"], ["BC-1"])
            self.assertFalse(report["plan"]["BC-1"]["has_steps"])


if __name__ == "__main__":
    unittest.main()