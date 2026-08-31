#!/usr/bin/env python3
"""dual_verify.py 单元测试（无设备环境：FakeDriver/Fake 执行器注入）。

覆盖（任务 #91 验收口径）：
- compare_dual 纯函数正反例：四类 MATCH/DIFF/MANUAL 各形态 + 文本集合
  对比 + probe JSON 逐 key 对比 + 顶层守卫三态；
- 语义查找/宽松比较（prefs./count: 前缀、表行数口径、bool/数字宽松）；
- oracle cache：命中跳过 Android 执行、--no-cache 语义、键漂移 miss、
  schema 损坏 miss；
- FakeDriver 双侧模拟端到端：Android Fake 执行器 + replayer FakeDriver
  （真 replay_bc）→ compare_dual → dual-diff-results.csv → validate。
"""

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

import dual_verify  # noqa: E402
import replayer  # noqa: E402
from dual_verify import (  # noqa: E402
    DIFF,
    MANUAL,
    MATCH,
    AndroidChainExecutor,
    build_compare_context,
    bc_row_sha,
    compare_data,
    compare_dual,
    compare_observable,
    compare_persistence,
    compare_side_effect,
    load_oracle_cache,
    lookup_semantic_value,
    loose_equal,
    make_observation,
    oracle_cache_key,
    run_harmony_side,
    seed_sha_of,
    store_oracle_cache,
    validate_results,
    verify_dual,
)
from replayer import QueryResult, UiSnapshot  # noqa: E402

BUNDLE = "com.example.todo"
ABILITY = "EntryAbility"


# ---------------------------------------------------------------------------
# 测试工具
# ---------------------------------------------------------------------------

def android_obs(**overrides):
    """基准 Android 观测（executed + precondition 通过 + 完整数据）。"""
    base = dict(
        executed=True, precondition_ok=True,
        texts_after=["Settings", "Language", "English", "保存"],
        texts_restart=["Settings", "Language", "English", "保存"],
        data_after={"preferences": {"locale": "en",
                                    "sort_order": "date"},
                    "tables": {"todo_items": [{"id": 1},
                                              {"id": 2}]}},
        data_restart={"preferences": {"locale": "en",
                                      "sort_order": "date"},
                      "tables": {"todo_items": [{"id": 1},
                                                {"id": 2}]}},
        data_access_mode="run-as",
        evidence_dir="evidence/dual/android",
    )
    base.update(overrides)
    return make_observation("android", "BC-TEST-01", "FEATURE-TEST",
                            **base)


def harmony_obs(**overrides):
    """基准 Harmony 观测（与 Android 语义一致 → 四类应 MATCH）。"""
    base = dict(
        executed=True, precondition_ok=True,
        texts_after=["Settings", "Language", "English", "保存"],
        texts_restart=["Settings", "Language", "English", "保存"],
        data_after={"locale": "en", "sort_order": "date",
                    "todo_items": {"__rows__": 2}},
        data_restart={"locale": "en", "sort_order": "date",
                      "todo_items": {"__rows__": 2}},
        data_access_mode="probe",
        evidence_dir="evidence/dual/harmony",
    )
    base.update(overrides)
    return make_observation("harmony", "BC-TEST-01", "FEATURE-TEST",
                            **base)


def full_context(**overrides):
    """基准对比上下文：文本锚点 + 数据键域 + 四类义务全开。"""
    context = {
        "text_anchors": ["English"],
        "persist_text_anchors": ["English"],
        "data_keys": ["locale", "sort_order", "todo_items"],
        "obligations": {"observable": True, "data": True,
                        "persistence": True, "side_effect": True},
    }
    context.update(overrides)
    return context


def bc_row(bc_id="BC-TEST-01", feature_id="FEATURE-TEST", **extra):
    row = {
        "bc_id": bc_id, "feature_id": feature_id,
        "page_ref": "PAGE-MAIN", "user_intent": "切换语言为英文",
        "pre_state": "设置页可见", "operation": "点语言，选 English",
        "expected_state_change": "locale=en",
        "observable_result": "界面显示 English",
        "persistence": "重启后仍为 English",
        "side_effect": "无",
        "evidence_class": "RUNTIME_REQUIRED",
        "operation_steps": json.dumps(
            [{"action": "tap", "target": "Language"},
             {"action": "tap", "target": "English"}]),
        "result_assertions": json.dumps([
            {"kind": "text_visible", "value": "English"},
            {"kind": "data_object", "object": "locale", "op": "equals",
             "value": "en"},
            {"kind": "persist_after_restart", "value": "English"},
        ]),
        "harmony_steps": json.dumps(
            [{"action": "tap", "target": "Language"},
             {"action": "tap", "target": "English"}]),
    }
    row.update(extra)
    return row


class FakeDriver:
    """replayer 设备协议假驱动（与 test_replayer 同构，可编程）。"""

    def __init__(self, ui_texts=None, data=None, foreground=BUNDLE,
                 notification="", files=None, missing_targets=None):
        self.ui_texts = list(ui_texts or [])
        self.data = dict(data or {})
        self.foreground = foreground
        self.notification = notification
        self.files = set(files or [])
        self.missing_targets = set(missing_targets or [])

    def foreground_bundle(self):
        return self.foreground

    def ui_snapshot(self):
        return UiSnapshot(raw=json.dumps(self.ui_texts),
                          texts=self.ui_texts, components=[])

    def locate(self, snapshot, target):
        return None if target in self.missing_targets else (100, 200)

    def tap(self, x, y):
        pass

    def input_text(self, x, y, text):
        pass

    def key_back(self):
        pass

    def swipe(self, x1, y1, x2, y2):
        pass

    def long_press(self, x, y):
        pass

    def force_stop(self, bundle):
        pass

    def start_ability(self, bundle, ability):
        pass

    def query_notification(self, key):
        return QueryResult(True, key.lower() in self.notification.lower())

    def file_exists(self, device_path):
        return QueryResult(True, device_path in self.files)

    def export_app_data(self, bundle):
        return dict(self.data)


class FakeAndroidExecutor:
    """Android 侧假执行器（Protocol 实现；run 计数供 cache 断言）。"""

    def __init__(self, observation):
        self.observation = observation
        self.calls = 0

    def run(self, bc):
        self.calls += 1
        return self.observation


class FakeExecutorFactory:
    """替换 dual_verify.AndroidChainExecutor 的可调用工厂（记录实例）。"""

    def __init__(self, observation):
        self.observation = observation
        self.instance = FakeAndroidExecutor(observation)

    def __call__(self, **kwargs):
        return self.instance


def write_csv_file(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# observable 对比（语义级文本集合/锚点可见性；不做像素）
# ---------------------------------------------------------------------------

class ObservableCompareTest(unittest.TestCase):
    def test_anchor_visibility_match(self):
        result = compare_observable(android_obs(), harmony_obs(),
                                    full_context())
        self.assertEqual(result["verdict"], MATCH)

    def test_anchor_visibility_diff_locale_example(self):
        # 用户设计例：Android 切英文 → English 可见；Harmony 切英文
        # → 仍是中文 → 锚点可见性矛盾 → DIFF
        result = compare_observable(
            android_obs(texts_after=["Settings", "Language", "English"]),
            harmony_obs(texts_after=["设置", "语言", "简体中文"]),
            full_context())
        self.assertEqual(result["verdict"], DIFF)
        anchors = result["detail"]["anchors"]
        self.assertEqual(anchors[0]["android"], "visible")
        self.assertEqual(anchors[0]["harmony"], "gone")
        self.assertEqual(anchors[0]["result"], "DIFF")

    def test_no_anchor_set_equal_match(self):
        context = full_context(text_anchors=[])
        result = compare_observable(android_obs(), harmony_obs(), context)
        self.assertEqual(result["verdict"], MATCH)

    def test_no_anchor_set_differs_manual(self):
        # 无锚点 + 集合不等 → MANUAL（机器不裁决 chrome 差异）
        context = full_context(text_anchors=[])
        result = compare_observable(
            android_obs(), harmony_obs(
                texts_after=["Settings", "Language", "English", "保存",
                             "ArkUI 附加文本"],
                texts_restart=["Settings", "Language", "English", "保存",
                               "ArkUI 附加文本"]),
            context)
        self.assertEqual(result["verdict"], MANUAL)
        self.assertIn("no-anchor-set-differs", result["detail"]["mode"])

    def test_chrome_text_diff_not_diff_when_anchors_match(self):
        # 锚点一致但 chrome 文本集合不同 → 仍 MATCH（不做像素 A/B）
        result = compare_observable(
            android_obs(), harmony_obs(
                texts_after=["Settings", "Language", "English", "保存",
                             "系统状态栏"],
                texts_restart=[]),
            full_context())
        self.assertEqual(result["verdict"], MATCH)


# ---------------------------------------------------------------------------
# data 对比（probe JSON 逐 key：prefs/表行数/关键字段）
# ---------------------------------------------------------------------------

class DataCompareTest(unittest.TestCase):
    def test_keys_match(self):
        result = compare_data(android_obs(), harmony_obs(), full_context())
        self.assertEqual(result["verdict"], MATCH)

    def test_value_mismatch_diff(self):
        result = compare_data(
            android_obs(), harmony_obs(
                data_after={"locale": "zh", "sort_order": "date",
                            "todo_items": {"__rows__": 2}},
                data_restart={}),
            full_context())
        self.assertEqual(result["verdict"], DIFF)
        keys = {k["key"]: k for k in result["detail"]["keys"]}
        self.assertEqual(keys["locale"]["reason"], "value_mismatch")

    def test_missing_on_harmony_diff(self):
        result = compare_data(
            android_obs(), harmony_obs(
                data_after={"sort_order": "date"},
                data_restart={}),
            full_context())
        self.assertEqual(result["verdict"], DIFF)
        keys = {k["key"]: k for k in result["detail"]["keys"]}
        self.assertEqual(keys["locale"]["reason"], "missing_on_harmony")

    def test_missing_on_android_diff(self):
        result = compare_data(
            android_obs(data_after={"preferences": {}}),
            harmony_obs(), full_context())
        self.assertEqual(result["verdict"], DIFF)

    def test_probe_denied_manual(self):
        # 采集受阻（run-as/root 皆不可用）≠ 行为矛盾 → MANUAL
        result = compare_data(android_obs(data_access_mode="DENIED"),
                              harmony_obs(), full_context())
        self.assertEqual(result["verdict"], MANUAL)
        self.assertEqual(result["detail"]["reason"],
                         "android_probe_unavailable")

    def test_no_declared_domain_fallback_intersection(self):
        # 无声明域 → 交集兜底：两侧顶层键交集逐 key 对比
        context = full_context(data_keys=[])
        result = compare_data(
            android_obs(data_after={"locale": "en",
                                    "android_only_pref": "x"}),
            harmony_obs(data_after={"locale": "en",
                                    "harmony_only_obj": "y"},
                        data_restart={}),
            context)
        self.assertEqual(result["verdict"], MATCH)  # 交集 {locale} 一致

    def test_no_domain_no_intersection_manual(self):
        context = full_context(data_keys=[])
        result = compare_data(
            android_obs(data_after={"preferences": {"a": 1}}),
            harmony_obs(data_after={"b": 1}, data_restart={}),
            context)
        self.assertEqual(result["verdict"], MANUAL)
        self.assertEqual(result["detail"]["reason"],
                         "no-declared-data-domain")


# ---------------------------------------------------------------------------
# persistence 对比（两侧 restart 互相确认 X==X'）
# ---------------------------------------------------------------------------

class PersistenceCompareTest(unittest.TestCase):
    def test_restart_consistent_match(self):
        result = compare_persistence(android_obs(), harmony_obs(),
                                     full_context())
        self.assertEqual(result["verdict"], MATCH)

    def test_restart_data_mismatch_diff(self):
        # 例：Android 重启后 locale=en（X=en）；Harmony 重启后 locale=zh
        # （X'=zh）→ X != X' → DIFF
        result = compare_persistence(
            android_obs(),
            harmony_obs(data_restart={"locale": "zh",
                                      "sort_order": "date",
                                      "todo_items": {"__rows__": 2}}),
            full_context())
        self.assertEqual(result["verdict"], DIFF)

    def test_persist_anchor_restart_visibility_diff(self):
        result = compare_persistence(
            android_obs(),
            harmony_obs(texts_restart=["Settings", "简体中文"]),
            full_context())
        self.assertEqual(result["verdict"], DIFF)

    def test_no_obligation_match(self):
        context = full_context(obligations={"persistence": False},
                               data_keys=[], persist_text_anchors=[])
        result = compare_persistence(
            android_obs(data_after={}, data_restart={}),
            harmony_obs(data_after={}, data_restart={}), context)
        self.assertEqual(result["verdict"], MATCH)
        self.assertEqual(result["detail"]["reason"], "no-obligation")

    def test_restart_data_missing_one_side_manual(self):
        result = compare_persistence(
            android_obs(data_restart={}),
            harmony_obs(), full_context())
        self.assertEqual(result["verdict"], MANUAL)


# ---------------------------------------------------------------------------
# side_effect 对比（注册对比；无公开 API 侧 MANUAL）
# ---------------------------------------------------------------------------

class SideEffectCompareTest(unittest.TestCase):
    def test_no_obligation_match(self):
        context = full_context(obligations={"side_effect": False})
        result = compare_side_effect(android_obs(), harmony_obs(), context)
        self.assertEqual(result["verdict"], MATCH)

    def test_no_registration_either_side_manual(self):
        result = compare_side_effect(android_obs(), harmony_obs(),
                                     full_context())
        self.assertEqual(result["verdict"], MANUAL)
        self.assertEqual(result["detail"]["reason"],
                         "no-machine-registration-on-either-side")

    def test_registration_only_one_side_manual(self):
        android = android_obs(side_effect_verdicts=[
            {"kind": "notification", "verdict": "PASS"}])
        result = compare_side_effect(android, harmony_obs(),
                                     full_context())
        self.assertEqual(result["verdict"], MANUAL)

    def test_same_kind_same_verdict_match(self):
        android = android_obs(side_effect_verdicts=[
            {"kind": "notification", "verdict": "PASS"}])
        harmony = harmony_obs(side_effect_verdicts=[
            {"kind": "notification", "verdict": "PASS"}])
        result = compare_side_effect(android, harmony, full_context())
        self.assertEqual(result["verdict"], MATCH)

    def test_same_kind_different_verdict_diff(self):
        android = android_obs(side_effect_verdicts=[
            {"kind": "notification", "verdict": "PASS"}])
        harmony = harmony_obs(side_effect_verdicts=[
            {"kind": "notification", "verdict": "FAIL"}])
        result = compare_side_effect(android, harmony, full_context())
        self.assertEqual(result["verdict"], DIFF)

    def test_single_side_manual_verdict_propagates_manual(self):
        android = android_obs(side_effect_verdicts=[
            {"kind": "file_export", "verdict": "PASS"}])
        harmony = harmony_obs(side_effect_verdicts=[
            {"kind": "file_export",
             "verdict": "MANUAL_VERIFY_REQUIRED"}])
        result = compare_side_effect(android, harmony, full_context())
        self.assertEqual(result["verdict"], MANUAL)


# ---------------------------------------------------------------------------
# compare_dual 顶层（守卫三态 + 四类分派 + 用户 locale 例）
# ---------------------------------------------------------------------------

class CompareDualTopTest(unittest.TestCase):
    def test_all_match(self):
        # side_effect：义务存在但两侧均无机器注册 → MANUAL（人工队列，
        # 设计口径：无公开查询 API 的副作用不机器放行）
        android = android_obs(side_effect_verdicts=[
            {"kind": "notification", "verdict": "PASS"}])
        harmony = harmony_obs(side_effect_verdicts=[
            {"kind": "notification", "verdict": "PASS"}])
        result = compare_dual(android, harmony, full_context())
        self.assertEqual(result["verdicts"], {
            "observable": MATCH, "data": MATCH,
            "persistence": MATCH, "side_effect": MATCH})
        self.assertEqual(result["diff_count"], 0)
        self.assertEqual(len(result["rows"]), 4)
        for row in result["rows"]:
            self.assertIn("dual-source", row["note"])

    def test_all_match_with_side_effect_manual(self):
        result = compare_dual(android_obs(), harmony_obs(), full_context())
        self.assertEqual(result["verdicts"], {
            "observable": MATCH, "data": MATCH,
            "persistence": MATCH, "side_effect": MANUAL})

    def test_locale_example_diff(self):
        # 用户设计原例：Android 切英文成功（locale=en 重启仍 en），
        # Harmony 切英文失败（locale=zh）→ DIFF 直接 FAIL
        harmony = harmony_obs(
            texts_after=["设置", "语言", "简体中文"],
            texts_restart=["设置", "语言", "简体中文"],
            data_after={"locale": "zh"},
            data_restart={"locale": "zh"})
        result = compare_dual(android_obs(), harmony, full_context())
        self.assertEqual(result["verdicts"]["observable"], DIFF)
        self.assertEqual(result["verdicts"]["data"], DIFF)
        self.assertEqual(result["verdicts"]["persistence"], DIFF)
        self.assertEqual(result["diff_count"], 3)
        for row in result["rows"][:3]:
            self.assertTrue(row["android_expected"])
            self.assertTrue(row["harmony_actual"])

    def test_side_error_manual_all(self):
        result = compare_dual(None, harmony_obs(), full_context())
        self.assertEqual(set(result["verdicts"].values()), {MANUAL})
        self.assertIn("side-error:android",
                      result["rows"][0]["note"])

    def test_precondition_unaligned_manual_all(self):
        harmony = harmony_obs(precondition_ok=False,
                              blocked_reason="PRECONDITION_FAILED")
        result = compare_dual(android_obs(), harmony, full_context())
        self.assertEqual(set(result["verdicts"].values()), {MANUAL})
        self.assertIn("precondition-unaligned:harmony",
                      result["rows"][0]["note"])
        # 前置未对齐不算 DIFF（人工队列语义）
        self.assertEqual(result["diff_count"], 0)

    def test_execution_incomplete_manual_all(self):
        android = android_obs(executed=False,
                              blocked_reason="STEPS_FAIL")
        result = compare_dual(android, harmony_obs(), full_context())
        self.assertEqual(set(result["verdicts"].values()), {MANUAL})
        self.assertIn("execution-incomplete:android",
                      result["rows"][0]["note"])


# ---------------------------------------------------------------------------
# 语义查找与宽松比较
# ---------------------------------------------------------------------------

class SemanticsTest(unittest.TestCase):
    def test_lookup_direct_key(self):
        self.assertEqual(lookup_semantic_value({"locale": "en"}, "locale"),
                         "en")

    def test_lookup_prefs_prefix(self):
        data = {"preferences": {"locale": "en"}}
        self.assertEqual(
            lookup_semantic_value(data, "prefs.locale"), "en")

    def test_lookup_count_prefix_table_rows(self):
        data = {"tables": {"todo_items": [{"id": 1}, {"id": 2}]}}
        self.assertEqual(
            lookup_semantic_value(data, "count:todo_items"),
            {"__rows__": 2})

    def test_lookup_table_name_rows_view(self):
        data = {"tables": {"todo_items": [{"id": 1}]}}
        self.assertEqual(lookup_semantic_value(data, "todo_items"),
                         {"__rows__": 1})

    def test_lookup_missing_returns_none(self):
        self.assertIsNone(lookup_semantic_value({}, "nope"))
        self.assertIsNone(lookup_semantic_value({}, ""))

    def test_loose_equal_numeric_string(self):
        self.assertTrue(loose_equal("1", 1))
        self.assertTrue(loose_equal(1.0, "1"))
        self.assertFalse(loose_equal("1", "2"))

    def test_loose_equal_bool_int(self):
        self.assertTrue(loose_equal(True, 1))
        self.assertTrue(loose_equal(False, 0))
        self.assertTrue(loose_equal(False, "0"))

    def test_loose_equal_dict_recursive(self):
        self.assertTrue(loose_equal({"a": 1}, {"a": "1"}))
        self.assertFalse(loose_equal({"a": 1}, {"a": 1, "b": 2}))


# ---------------------------------------------------------------------------
# 对比上下文构建（BC 行 → 锚点/数据域/义务）
# ---------------------------------------------------------------------------

class ContextTest(unittest.TestCase):
    def test_context_from_bc_row(self):
        context = build_compare_context(bc_row())
        self.assertEqual(context["text_anchors"], ["English"])
        self.assertEqual(context["persist_text_anchors"], ["English"])
        self.assertIn("locale", context["data_keys"])  # 断言 object
        self.assertIn("locale", context["data_keys"])  # 段键值声明
        self.assertTrue(all(context["obligations"].values()))

    def test_context_no_obligation(self):
        row = bc_row(result_assertions="[]", observable_result="",
                     expected_state_change="", persistence="",
                     side_effect="")
        context = build_compare_context(row)
        self.assertEqual(context["text_anchors"], [])
        self.assertEqual(context["data_keys"], [])
        self.assertFalse(any(context["obligations"].values()))

    def test_data_keys_from_segment_kv(self):
        row = bc_row(result_assertions="[]",
                     expected_state_change="locale=en;sort_order=date")
        context = build_compare_context(row)
        self.assertIn("locale", context["data_keys"])
        self.assertIn("sort_order", context["data_keys"])


# ---------------------------------------------------------------------------
# oracle cache
# ---------------------------------------------------------------------------

class OracleCacheTest(unittest.TestCase):
    def test_store_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            obs = android_obs()
            key = oracle_cache_key(bc_row(), "a" * 64,
                                   seed_sha_of("cold-reset-v1"))
            store_oracle_cache(cache_dir, key, obs, {
                "key_inputs": {"bc_id": "BC-TEST-01"}})
            loaded = load_oracle_cache(cache_dir, key)
            self.assertEqual(loaded["texts_after"], obs["texts_after"])
            self.assertEqual(loaded["data_after"], obs["data_after"])

    def test_key_drift_on_apk_sha_change(self):
        bc = bc_row()
        k1 = oracle_cache_key(bc, "a" * 64, seed_sha_of("s"))
        k2 = oracle_cache_key(bc, "b" * 64, seed_sha_of("s"))
        self.assertNotEqual(k1, k2)

    def test_key_drift_on_bc_row_change(self):
        k1 = oracle_cache_key(bc_row(), "a" * 64, seed_sha_of("s"))
        k2 = oracle_cache_key(bc_row(expected_state_change="locale=zh"),
                              "a" * 64, seed_sha_of("s"))
        self.assertNotEqual(k1, k2)

    def test_load_missing_returns_none(self):
        self.assertIsNone(
            load_oracle_cache(Path(tempfile.mkdtemp()), "nope"))

    def test_load_bad_schema_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"schema": "other/1", "observation": {}}',
                            encoding="utf-8")
            self.assertIsNone(load_oracle_cache(Path(tmp), "bad"))

    def test_bc_row_sha_stable_regardless_of_column_order(self):
        sha1 = bc_row_sha({"a": "1", "b": "2"})
        sha2 = bc_row_sha({"b": "2", "a": "1"})
        self.assertEqual(sha1, sha2)


# ---------------------------------------------------------------------------
# Harmony 侧执行器归一（replayer.replay_bc + 证据目录 → 观测）
# ---------------------------------------------------------------------------

class HarmonySideTest(unittest.TestCase):
    def test_run_harmony_side_normalizes_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_root = Path(tmp) / "evidence"
            driver = FakeDriver(
                ui_texts=["设置", "语言", "English"],
                data={"locale": "en"})
            obs = run_harmony_side(bc_row(), json.loads(
                bc_row()["harmony_steps"]), driver, BUNDLE, ABILITY,
                evidence_root)
            self.assertTrue(obs["precondition_ok"])
            self.assertTrue(obs["executed"])
            self.assertEqual(obs["texts_after"], ["设置", "语言",
                                                  "English"])
            self.assertEqual(obs["data_after"], {"locale": "en"})
            self.assertTrue(obs["evidence_dir"])

    def test_run_harmony_side_steps_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_root = Path(tmp) / "evidence"
            driver = FakeDriver(
                ui_texts=["设置"], missing_targets={"English"})
            obs = run_harmony_side(bc_row(), json.loads(
                bc_row()["harmony_steps"]), driver, BUNDLE, ABILITY,
                evidence_root)
            self.assertTrue(obs["precondition_ok"])
            self.assertFalse(obs["executed"])
            self.assertIn("steps_interrupted", obs["blocked_reason"])


# ---------------------------------------------------------------------------
# Android 侧执行器纯解析段（不跑 subprocess）
# ---------------------------------------------------------------------------

class AndroidExecutorParsingTest(unittest.TestCase):
    def test_read_chain_row_missing_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                AndroidChainExecutor._read_chain_row(Path(tmp), "BC-X"),
                {})

    def test_read_chain_row_selects_bc(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            ev = ws / "runtime-evidence"
            ev.mkdir()
            write_csv_file(ev / "runtime-chains.csv",
                           ["bc_id", "chain_status"],
                           [{"bc_id": "BC-A", "chain_status": "CHAIN_PASS"},
                            {"bc_id": "BC-B", "chain_status": "NAV_FAIL"}])
            self.assertEqual(
                AndroidChainExecutor._read_chain_row(ws, "BC-B")[
                    "chain_status"], "NAV_FAIL")

    def test_texts_of_extracts_text_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "ui.xml"
            xml.write_text(
                '<?xml version="1.0"?><hierarchy>'
                '<node text="Settings" content-desc="" bounds="[0,0][1,1]"/>'
                '<node text="" content-desc="Language" bounds="[0,0][1,1]"/>'
                "</hierarchy>", encoding="utf-8")
            texts = AndroidChainExecutor._texts_of(xml)
            self.assertIn("Settings", texts)
            self.assertIn("Language", texts)  # desc 兜底（ui_nodes 口径）

    def test_texts_of_missing_file(self):
        self.assertEqual(
            AndroidChainExecutor._texts_of(Path("/nonexistent/ui.xml")), [])

    def test_parse_assertions_tolerates_bad_json(self):
        self.assertEqual(AndroidChainExecutor._parse_assertions("bad"), [])
        self.assertEqual(AndroidChainExecutor._parse_assertions(""), [])

    def test_temp_workspace_single_bc_filtered(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_ws = Path(tmp) / "phase02"
            (source_ws / "candidates").mkdir(parents=True)
            (source_ws / "candidates" / "inventory.candidates.csv") \
                .write_text("page_id\nPAGE-MAIN\n", encoding="utf-8")
            executor = AndroidChainExecutor(
                project=Path("/android/project"), package="com.a",
                serial="emulator-5554", android_workspace=source_ws,
                bc_fields=["bc_id", "feature_id", "operation_steps"])
            ws = executor._build_temp_workspace(bc_row())
            rows = list(csv.DictReader(
                (ws / "behavior-contracts.csv").open(encoding="utf-8")))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["bc_id"], "BC-TEST-01")
            # candidates 以 symlink 复用（Page-ID 映射不复制）
            self.assertTrue(
                (ws / "candidates" / "inventory.candidates.csv").exists())

    def test_run_without_project_fails_fast(self):
        executor = AndroidChainExecutor(project=None, package="com.a",
                                        serial="emulator-5554")
        with self.assertRaises(ValueError):
            executor.run(bc_row())


# ---------------------------------------------------------------------------
# 双侧端到端（Fake Android 执行器 + replayer FakeDriver → CSV → validate）
# ---------------------------------------------------------------------------

class DualEndToEndTest(unittest.TestCase):
    def _prepare(self, tmp, harmony_driver, android_observation):
        bc_path = Path(tmp) / "behavior-contracts.csv"
        fields = list(bc_row().keys())
        write_csv_file(bc_path, fields, [bc_row()])
        workspace = Path(tmp) / "phase-04-ws"
        out = Path(tmp) / "dual-diff-results.csv"
        return bc_path, workspace, out, android_observation, harmony_driver

    def test_end_to_end_match_and_csv_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            bc_path, workspace, out, _, _ = self._prepare(
                tmp, None, None)
            driver = FakeDriver(ui_texts=["设置", "语言", "English"],
                                data={"locale": "en"})
            evidence_root = workspace / "evidence" / "dual"
            harmony = run_harmony_side(
                bc_row(), json.loads(bc_row()["harmony_steps"]),
                driver, BUNDLE, ABILITY, evidence_root)
            android = make_observation(
                "android", "BC-TEST-01", "FEATURE-TEST",
                executed=True, precondition_ok=True,
                texts_after=["设置", "语言", "English"],
                texts_restart=["设置", "语言", "English"],
                data_after={"locale": "en"}, data_restart={"locale": "en"},
                data_access_mode="run-as",
                evidence_dir="evidence/dual/android")
            result = compare_dual(android, harmony,
                                  build_compare_context(bc_row()))
            rows = result["rows"]
            dual_verify.write_csv = dual_verify.write_csv  # 保持引用
            from _common import write_csv as _wc
            _wc(out, dual_verify.DUAL_CSV_FIELDS, rows)
            self.assertEqual(validate_results(out), [])
            verdicts = {r["assertion_type"]: r["verdict"] for r in rows}
            self.assertEqual(verdicts["observable"], MATCH)
            self.assertEqual(verdicts["data"], MATCH)

    def test_end_to_end_locale_diff_detected(self):
        # 用户设计例端到端：Harmony 切语言失败 → observable/data/
        # persistence 三类 DIFF
        with tempfile.TemporaryDirectory() as tmp:
            bc_path, workspace, out, _, _ = self._prepare(
                tmp, None, None)
            driver = FakeDriver(ui_texts=["设置", "语言", "简体中文"],
                                data={"locale": "zh"})
            evidence_root = workspace / "evidence" / "dual"
            harmony = run_harmony_side(
                bc_row(), json.loads(bc_row()["harmony_steps"]),
                driver, BUNDLE, ABILITY, evidence_root)
            android = make_observation(
                "android", "BC-TEST-01", "FEATURE-TEST",
                executed=True, precondition_ok=True,
                texts_after=["设置", "语言", "English"],
                texts_restart=["设置", "语言", "English"],
                data_after={"locale": "en"}, data_restart={"locale": "en"},
                data_access_mode="run-as",
                evidence_dir="evidence/dual/android")
            result = compare_dual(android, harmony,
                                  build_compare_context(bc_row()))
            self.assertEqual(result["verdicts"]["observable"], DIFF)
            self.assertEqual(result["verdicts"]["data"], DIFF)
            # DIFF 行双侧实测必须非空（validate 规则）
            for row in result["rows"]:
                if row["verdict"] == DIFF:
                    self.assertTrue(row["android_expected"])
                    self.assertTrue(row["harmony_actual"])

    def test_verify_dual_cache_hit_skips_android(self):
        # CLI 级：cache 命中时不调 Android 执行器（Fake 替身计数=0）
        with tempfile.TemporaryDirectory() as tmp:
            obs = android_obs()
            bc_path, workspace, out, _, _ = self._prepare(tmp, None, obs)
            cache_dir = Path(tmp) / "oracle-cache"
            args = argparse_ns(bc_path, workspace, out, cache_dir)
            args.harmony_driver = FakeDriver(
                ui_texts=obs["texts_after"], data=obs["data_after"])
            bc = replayer.load_bc_rows(bc_path)[0]
            key = dual_verify.oracle_cache_key(
                bc, args.apk_sha,
                seed_sha_of(dual_verify.DEFAULT_SEED_ID))
            store_oracle_cache(cache_dir, key, obs, {})
            factory = FakeExecutorFactory(obs)
            original = dual_verify.AndroidChainExecutor
            dual_verify.AndroidChainExecutor = factory
            try:
                rc = verify_dual(args)
            finally:
                dual_verify.AndroidChainExecutor = original
            self.assertEqual(factory.instance.calls, 0)  # cache 命中未执行
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            self.assertEqual(validate_results(out), [])

    def test_verify_dual_no_cache_forces_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = android_obs()
            bc_path, workspace, out, _, _ = self._prepare(tmp, None, obs)
            cache_dir = Path(tmp) / "oracle-cache"
            args = argparse_ns(bc_path, workspace, out, cache_dir,
                               no_cache=True)
            args.harmony_driver = FakeDriver(
                ui_texts=obs["texts_after"], data=obs["data_after"])
            bc = replayer.load_bc_rows(bc_path)[0]
            key = dual_verify.oracle_cache_key(
                bc, args.apk_sha,
                seed_sha_of(dual_verify.DEFAULT_SEED_ID))
            store_oracle_cache(cache_dir, key, obs, {})
            factory = FakeExecutorFactory(obs)
            original = dual_verify.AndroidChainExecutor
            dual_verify.AndroidChainExecutor = factory
            original_run_harmony = dual_verify.run_harmony_side

            def fake_harmony(bc_, steps, driver_, bundle, ability, root):
                return make_observation(
                    "harmony", bc_.get("bc_id", ""), "FEATURE-TEST",
                    executed=True, precondition_ok=True,
                    texts_after=obs["texts_after"],
                    texts_restart=obs["texts_restart"],
                    data_after=obs["data_after"],
                    data_restart=obs["data_restart"],
                    data_access_mode="probe")

            dual_verify.run_harmony_side = fake_harmony
            try:
                rc = verify_dual(args)
            finally:
                dual_verify.AndroidChainExecutor = original
                dual_verify.run_harmony_side = original_run_harmony
            self.assertEqual(factory.instance.calls, 1)  # --no-cache 重跑
            self.assertEqual(rc, 0)

    def test_verify_dual_diff_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = android_obs()
            bc_path, workspace, out, _, _ = self._prepare(tmp, None, obs)
            args = argparse_ns(bc_path, workspace, out,
                               Path(tmp) / "oracle-cache")
            args.harmony_driver = object()  # run_harmony_side 已被替身
            # Harmony 侧行为漂移（locale=zh）→ DIFF → 退出码 1
            drifted = make_observation(
                "harmony", "BC-TEST-01", "FEATURE-TEST",
                executed=True, precondition_ok=True,
                texts_after=["设置", "简体中文"],
                texts_restart=["设置", "简体中文"],
                data_after={"locale": "zh"}, data_restart={"locale": "zh"},
                data_access_mode="probe")
            factory = FakeExecutorFactory(obs)
            original = dual_verify.AndroidChainExecutor
            dual_verify.AndroidChainExecutor = factory
            original_run_harmony = dual_verify.run_harmony_side
            dual_verify.run_harmony_side = \
                lambda *a, **k: drifted
            try:
                rc = verify_dual(args)
            finally:
                dual_verify.AndroidChainExecutor = original
                dual_verify.run_harmony_side = original_run_harmony
            self.assertEqual(rc, 1)
            rows = list(csv.DictReader(out.open(encoding="utf-8")))
            verdicts = {r["assertion_type"]: r["verdict"] for r in rows}
            self.assertEqual(verdicts["observable"], DIFF)
            self.assertEqual(verdicts["data"], DIFF)
            self.assertEqual(validate_results(out), [])


def argparse_ns(bc_path, workspace, out, cache_dir, no_cache=False):
    import argparse
    return argparse.Namespace(
        bc=bc_path, harmony_steps=None,
        android_device="emulator-5554", harmony_device="127.0.0.1:5557",
        workspace=workspace, bc_filter="", out=out,
        oracle_cache_dir=cache_dir, no_cache=no_cache,
        android_project="/android/project",
        android_workspace="", android_activity="MainActivity",
        package="com.example.todo", bundle=BUNDLE, ability=ABILITY,
        hdc="hdc", apk_sha="", seed="", dry_run=False)


if __name__ == "__main__":
    unittest.main()