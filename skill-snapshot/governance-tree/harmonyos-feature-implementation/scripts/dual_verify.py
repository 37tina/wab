#!/usr/bin/env python3
"""双机行为差分引擎（任务 #91，用户设计升级：Phase 4 第 4 步从"单端
Harmony 验证"升级为"双机行为差分"）。

核心范式（用户设计原话要点，严格执行）：
    Android 模拟器和鸿蒙模拟器先恢复到同一个**语义前置状态**，然后
    Android 按 android_steps（BC.operation_steps）执行、Harmony 按
    harmony_steps 执行、两边分别采集结果、**机器直接 A/B 对比**。
    比较的不是点击路径，而是四类结果：observable result / semantic
    data / persistence / side effect。
    例：Android 切英文 → locale=en → 重启仍 en；Harmony 切英文 →
    locale=zh → **DIFF 直接 FAIL**。
    **双机比较功能结果，不做 UI 像素 A/B**（UI 仍按视觉记忆+蓝图验收）。
    Gate 4 不参与差分（只最终判定）——差分在本引擎内部完成。

架构（两侧执行器 → 采集 → 对比 → DIFF 报告）：

    ┌─ Android 侧（跨 skill subprocess 复用，不改 inventory 代码）─┐
    │ gmi_runtime.py --mode chain   链执行：链前冷复位 + pre_state   │
    │ (临时 workspace 单链过滤)       校验 + android_steps 执行 +     │
    │                               before/after/restart UI 快照      │
    │ android_data_probe.py          数据采集：链后 restart 时点语义  │
    │                               状态（prefs / SQLite 表，只读）   │
    └──────────────┬─────────────────────────────────────────────────┘
                   ↓ SideObservation（语义观测，统一模型）
    ┌─ Harmony 侧（同 skill 内直接 import replayer.replay_bc）─────┐
    │ replayer.py                   链执行：cold reset + prepare +   │
    │ (FakeDriver 可注入单测)        precondition 校验 + harmony_steps│
    │                               + after/restart 快照 + 探针数据  │
    └──────────────┬─────────────────────────────────────────────────┘
                   ↓ SideObservation
    ┌─ 四类 A/B 对比器（纯函数 compare_dual）──────────────────────┐
    │ observable  语义级文本集合/锚点可见性对比（不做像素）          │
    │ data        probe JSON 逐 key 对比（prefs/表行数/关键字段）    │
    │ persistence 两侧 data-restart 对比 + 互相确认（X==X'?）        │
    │ side_effect 两侧副作用注册对比（无公开 API 的侧 MANUAL）       │
    └──────────────┬─────────────────────────────────────────────────┘
                   ↓ 每类 MATCH | DIFF | MANUAL + 差异明细
    dual-diff-results.csv（格式对齐 replay-results.csv，note 标
    dual-source，Gate 4 兼容消费）

语义前置对齐口径（重要注释，#92 seed 机制详化前生效）：
    两侧执行器各自内部执行 precondition 流程（gmi_runtime 链前
    _cold_restart + verify_precondition；replayer establish_precondition
    冷复位 + prepare_steps + pre_state token 校验）。调用前确保两侧
    seed 一致的机制（显式 seed 重置）不在本次范围——本版以
    **"两侧均冷启动（force-stop + 冷启动复位）+ 各自 pre_state 校验
    通过"** 为对齐口径：冷启动清掉内存态、pre_state 校验确认两侧从
    契约声明的同一语义前置出发。任一侧 precondition 未建立 → 该 BC
    四类一律 MANUAL（precondition_unaligned，进人工队列，不算 DIFF——
    前置无法对齐≠行为差异，与 replayer PRECONDITION_FAILED 语义同构）。

oracle cache 骨架（#92 详化，本版留接口）：
    --oracle-cache-dir 下按 (bc_id + APK sha + seed sha + BC 行 sha)
    四元组的 sha256 存 Android 侧语义观测 JSON；cache 命中时跳过
    Android 真机执行直接读缓存（Android 侧是行为基准 oracle，跨轮
    稳定可复用）；--no-cache 强制重跑并覆写。Harmony 侧是被验证方，
    每轮真跑，不缓存。

判定铁律（与 replayer/gmi_runtime 同精神）：
    - 双机差分 FAIL 语义 = DIFF（两侧行为结果漂移）；无法机器对比
      （采集受阻/无公开查询 API/键映射缺口）= MANUAL，绝不静默 MATCH；
    - 任一侧操作序列未走通 → 四类 MANUAL（execution_incomplete）：
      差分的前提是两侧都执行完成；单侧未完成的 FAIL 由该侧自己的
      验证器（runtime-chains.csv / replay-results.csv）负责，本引擎
      不重复裁决、不臆断；
    - observable 不做像素对比（平台 chrome 文本差异记 note 不判 DIFF）。

用法：
    verify   双机差分主流程（需两侧设备；--dry-run 仅校验输入与计划）
    validate 校验 dual-diff-results.csv 格式（Gate 4 / I 代理只读检查）
"""

from __future__ import annotations

import argparse
import csv as _csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from _common import atomic_json, read_csv, write_csv

# ----------------------------------------------------------------------------
# 跨 skill 共享 import（与 replayer.py 同款手法，只调用不修改）：
# - gmi_runtime（android-migration-inventory）：ui_text_set 解析 Android
#   uiautomator XML（文本集合口径两侧同构）；
# - replayer（本 skill）：replay_bc 整链执行 + 证据落盘。
# gmi_runtime 为纯函数库顶层 import 安全（replayer 已 import 其
# parse_pre_state_tokens 验证）；找不到时 fail-fast。
# ----------------------------------------------------------------------------
_THIS_SCRIPTS = Path(__file__).resolve().parent
_GMI_SCRIPTS = _THIS_SCRIPTS.parents[1] / "android-migration-inventory" / "scripts"
if not (_GMI_SCRIPTS / "gmi_runtime.py").is_file():
    raise ImportError(
        "shared android-side module not found: "
        f"{_GMI_SCRIPTS / 'gmi_runtime.py'} (android-migration-inventory "
        "skill must sit beside harmonyos-feature-implementation)")
for _p in (str(_THIS_SCRIPTS), str(_GMI_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import replayer  # noqa: E402  (本 skill，Harmony 侧执行器)
from replayer import (  # noqa: E402
    MANUAL as H_MANUAL,
    extract_segments,
    parse_json_column,
)
from gmi_runtime import ui_text_set  # noqa: E402  (Android XML→文本集合)

# ============================================================================
# 常量与 CSV 契约
# ============================================================================

# 四类断言（对齐 replayer SEGMENT_OBLIGATION / gmi chain 断言类）
CATEGORIES = ("observable", "data", "persistence", "side_effect")

# 差分判定枚举（用户设计：MATCH | DIFF | MANUAL；DIFF 即差分 FAIL 语义）
MATCH = "MATCH"
DIFF = "DIFF"
MANUAL = "MANUAL"

DUAL_CSV_FIELDS = [
    "bc_id", "feature_id", "assertion_type",
    "verdict",              # MATCH | DIFF | MANUAL
    "android_expected",     # Android 实测（基准 oracle）
    "harmony_actual",       # Harmony 实测（被验证方）
    "evidence_refs",        # 两侧证据目录（; 分隔）
    "note",                 # 固定标 dual-source + 差异明细
]
DUAL_NOTE_TAG = "dual-source"

# CSV 单元格样本上限（差异明细可读性；全文在证据 JSON）
_CELL_SAMPLE_LIMIT = 12

# Android chain 侧"链执行完成"状态（结果可比）；blocked 状态差分不可判定
_ANDROID_BLOCKED = {
    "NAV_FAIL", "STEPS_FAIL", "ANR_BLOCKED", "UNRESOLVED_PAGE_REF",
    "INVALID_CONTRACT", "UNSUPPORTED_ORACLE", "PRECONDITION_FAILED",
}
_ANDROID_PRECONDITION_FAILED = "PRECONDITION_FAILED"

# oracle cache schema（#92 详化；本版 v1：语义观测 + 采集元数据）
ORACLE_CACHE_SCHEMA = "dual-verify-oracle-cache/1"
# seed 对齐口径常量（#92 前的缺省：两侧冷启动 + pre_state 校验通过）
DEFAULT_SEED_ID = "cold-reset-v1"

# Android data probe 的语义取值形态标记（表行数口径）
_TABLE_COUNT_MARK = "__rows__"


# ============================================================================
# SideObservation：两侧统一的语义观测模型（纯 dict，可 JSON 序列化进 cache）
# ============================================================================

def make_observation(
    side: str,
    bc_id: str,
    feature_id: str,
    *,
    executed: bool,
    precondition_ok: bool,
    blocked_reason: str = "",
    texts_after: Optional[List[str]] = None,
    texts_restart: Optional[List[str]] = None,
    data_after: Optional[Dict[str, Any]] = None,
    data_restart: Optional[Dict[str, Any]] = None,
    anchor_assertions: Optional[List[Dict[str, str]]] = None,
    side_effect_verdicts: Optional[List[Dict[str, str]]] = None,
    data_access_mode: str = "",
    evidence_dir: str = "",
    note: str = "",
) -> Dict[str, Any]:
    """构造统一的语义观测（两侧执行器输出、对比器输入）。

    字段口径：
    - texts_after/restart：该侧 after/restart 稳定快照的可见文本集合
      （语义级；Android=ui_text_set(ui.xml)，Harmony=ui-after.json texts）；
    - data_after/restart：该侧语义数据状态（Android=data probe JSON 的
      preferences/tables 归一视图；Harmony=DebugSemanticProbe 对象 dict）；
    - anchor_assertions：该侧结果断言及单侧判定（kind/value/object/
      verdict）；
    - side_effect_verdicts：该侧副作用断言注册及单侧判定；
    - executed：操作序列是否完整走通（差分前提）；
    - precondition_ok：语义前置是否建立（对齐前提）。
    """
    return {
        "side": side,
        "bc_id": bc_id,
        "feature_id": feature_id,
        "executed": executed,
        "precondition_ok": precondition_ok,
        "blocked_reason": blocked_reason,
        "texts_after": list(texts_after or []),
        "texts_restart": list(texts_restart or []),
        "data_after": data_after if data_after is not None else {},
        "data_restart": data_restart if data_restart is not None else {},
        "anchor_assertions": list(anchor_assertions or []),
        "side_effect_verdicts": list(side_effect_verdicts or []),
        "data_access_mode": data_access_mode,
        "evidence_dir": evidence_dir,
        "note": note,
    }


# ============================================================================
# 对比上下文（纯函数：BC 行 → 锚点域/数据域/四类义务）
# ============================================================================

def _extract_data_keys_from_segment(segment: str) -> List[str]:
    """expected_state_change 自然语言段提取 k=v / k：v 形态的左侧键名。

    保守口径：仅取显式 `key=value` / `key：value` 的左侧标识符，且右侧
    有机器可校验 token（与 parse_pre_state_tokens 的保守精神一致）——
    提取不出就返回空（数据域退回断言声明 + 交集兜底）。
    """
    keys: List[str] = []
    text = (segment or "").strip()
    for chunk in text.replace("；", ";").replace("，", ",").split(";"):
        for piece in chunk.split(","):
            piece = piece.strip()
            if not piece or "=" not in piece and "：" not in piece \
                    and ":" in piece.replace("：", ""):
                continue
            if "=" not in piece and "：" not in piece and ":" not in piece:
                continue
            head = piece.replace("：", "=").split("=", 1)[0].strip()
            if head and replayer.parse_pre_state_tokens(piece):
                keys.append(head)
    return keys


def build_compare_context(bc: Dict[str, str]) -> Dict[str, Any]:
    """BC 行 → 差分对比上下文（纯函数，可单测）。

    - text_anchors：observable 锚点（text_visible/text_gone 断言 value；
      空 → observable 退化为全集合语义对比，集合不等判 MANUAL）；
    - data_keys：data/persistence 对比键域（data_object/persist_data
      断言 object + expected_state_change 显式键值声明；空 → 交集域
      兜底：两侧 data 顶层键交集）；
    - persist_text_anchors：persistence 文本锚点（persist_after_restart
      断言 value）；
    - obligations：四类义务 bool（段非空或有该类断言）。
    """
    segments = extract_segments(bc)
    assertions = parse_json_column(bc.get("result_assertions", ""))
    buckets = replayer.classify_assertions(assertions)

    text_anchors = [
        (a.get("value") or "").strip()
        for a in buckets["observable"]
        if (a.get("kind") or "").strip() in ("text_visible", "text_gone")
        and (a.get("value") or "").strip()
    ]
    persist_text_anchors = [
        (a.get("value") or "").strip()
        for a in buckets["persistence"]
        if (a.get("kind") or "").strip() == "persist_after_restart"
        and (a.get("value") or "").strip()
    ]
    data_keys = [
        (a.get("object") or "").strip()
        for a in buckets["data"] + buckets["persistence"]
        if (a.get("object") or "").strip()
    ]
    data_keys += _extract_data_keys_from_segment(
        segments.get("expected_state_change", ""))
    data_keys = list(dict.fromkeys(k for k in data_keys if k))

    obligations = {}
    for segment, category in replayer.SEGMENT_OBLIGATION.items():
        obligations[category] = bool(
            segments.get(segment, "").strip() or buckets[category])
    return {
        "text_anchors": list(dict.fromkeys(text_anchors)),
        "persist_text_anchors": list(dict.fromkeys(persist_text_anchors)),
        "data_keys": data_keys,
        "obligations": obligations,
    }


# ============================================================================
# 语义取值与宽松比较（纯函数）
# ============================================================================

def lookup_semantic_value(data: Dict[str, Any], key: str) -> Optional[Any]:
    """统一语义查找（两侧 data 视图 → key 的值；找不到 → None）。

    支持形态（兼容两侧模型）：
    - 直接键：{"sort_order": "date"}（Harmony probe 对象 / Android prefs）；
    - "prefs.<name>"：Android preferences 段；
    - "count:<table>"：表行数口径；
    - 表名直接命中：行对象数组 → {"__rows__": N}（表行数语义值）。
    """
    if not isinstance(data, dict) or not key:
        return None
    if key in data:
        value = data[key]
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return {_TABLE_COUNT_MARK: len(value)}
        return value
    if key.startswith("prefs.") and isinstance(data.get("preferences"), dict):
        return data["preferences"].get(key[len("prefs."):])
    if key.startswith("count:") and isinstance(data.get("tables"), dict):
        rows = data["tables"].get(key[len("count:"):])
        return {_TABLE_COUNT_MARK: len(rows)} if isinstance(rows, list) else None
    if isinstance(data.get("tables"), dict) and key in data["tables"]:
        rows = data["tables"][key]
        return {_TABLE_COUNT_MARK: len(rows)} if isinstance(rows, list) else None
    if isinstance(data.get("preferences"), dict) and key in data["preferences"]:
        return data["preferences"][key]
    return None


def _normalize_scalar(value: Any) -> str:
    """宽松归一：bool→1/0；str 保留原文（trim）；None→空串。"""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return ""
    return str(value).strip()


def loose_equal(a: Any, b: Any) -> bool:
    """语义宽松相等（与 android_data_probe 值比较语义同构）：
    str vs number 宽松数值比较（"1"==1）；bool 与 1/0 语义相等；
    dict 逐 key 归一比较；其余 str() 相等。"""
    if isinstance(a, dict) or isinstance(b, dict):
        if not (isinstance(a, dict) and isinstance(b, dict)):
            return False
        if set(a.keys()) != set(b.keys()):
            return False
        return all(loose_equal(a[k], b[k]) for k in a)
    na, nb = _normalize_scalar(a), _normalize_scalar(b)
    if na == nb:
        return True
    try:
        return float(na) == float(nb)
    except (TypeError, ValueError):
        return False


def _texts_show(texts: List[str], value: str) -> bool:
    """文本集合可见性（与两侧 _xml_shows/shows_text 同构：大小写不敏感
    子串匹配）。"""
    if not value:
        return False
    lowered = value.lower()
    return any(lowered in (t or "").lower() for t in texts)


def _compact(value: Any) -> str:
    """CSV 单元格紧凑序列化（差异明细可读 + 稳定排序）。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _sample(items: List[str], limit: int = _CELL_SAMPLE_LIMIT) -> List[str]:
    return items[:limit]


def _diff_row(bc_id: str, feature_id: str, category: str, verdict: str,
              android_expected: Any, harmony_actual: Any,
              evidence_refs: str, note: str) -> Dict[str, str]:
    row = dict.fromkeys(DUAL_CSV_FIELDS, "")
    row.update({
        "bc_id": bc_id,
        "feature_id": feature_id,
        "assertion_type": category,
        "verdict": verdict,
        "android_expected": _compact(android_expected),
        "harmony_actual": _compact(harmony_actual),
        "evidence_refs": evidence_refs,
        "note": f"{DUAL_NOTE_TAG}; {note}",
    })
    return row


# ============================================================================
# 四类 A/B 对比器（纯函数；每类独立判定 MATCH | DIFF | MANUAL；
# 每类结果带 android_view / harmony_actual 双侧实测视图供 CSV 消费）
# ============================================================================

def compare_observable(android_obs: Dict[str, Any],
                       harmony_obs: Dict[str, Any],
                       context: Dict[str, Any]) -> Dict[str, Any]:
    """observable 对比：语义级文本集合/锚点可见性（不做像素）。

    判定表：
    - 有锚点：逐锚点双端可见性对比，任一不一致 → DIFF（明细 anchor +
      两侧可见性）；全部一致 → MATCH；
    - 无锚点：两侧 after 文本集合全对比——相等 → MATCH；不等 →
      MANUAL（无语义锚点无法机器裁决哪侧是正确口径；平台 chrome 文本
      差异不允许机器臆断为行为差异，集合差异记明细供人工）。
    """
    a_texts = android_obs.get("texts_after") or []
    h_texts = harmony_obs.get("texts_after") or []
    a_only = sorted(set(a_texts) - set(h_texts))
    h_only = sorted(set(h_texts) - set(a_texts))
    set_diff = {"android_only": _sample(a_only),
                "harmony_only": _sample(h_only),
                "android_only_count": len(a_only),
                "harmony_only_count": len(h_only)}
    anchors = context.get("text_anchors") or []
    android_view: Dict[str, Any] = {"texts_after": _sample(a_texts)}
    harmony_view: Dict[str, Any] = {"texts_after": _sample(h_texts)}
    if not anchors:
        android_view["mode"] = harmony_view["mode"] = "set-compare"
        if not a_only and not h_only:
            return {"verdict": MATCH,
                    "android_view": android_view, "harmony_view": harmony_view,
                    "detail": {"mode": "set-equal", "set_diff": set_diff}}
        return {"verdict": MANUAL,
                "android_view": {**android_view, "set_diff": set_diff},
                "harmony_view": {**harmony_view, "set_diff": set_diff},
                "detail": {"mode": "no-anchor-set-differs",
                           "set_diff": set_diff}}

    anchor_results = []
    any_diff = False
    for anchor in anchors:
        a_vis = _texts_show(a_texts, anchor)
        h_vis = _texts_show(h_texts, anchor)
        differs = a_vis != h_vis
        any_diff = any_diff or differs
        anchor_results.append(
            {"anchor": anchor, "android": "visible" if a_vis else "gone",
             "harmony": "visible" if h_vis else "gone",
             "result": "DIFF" if differs else "match"})
        android_view[f"anchor:{anchor}"] = "visible" if a_vis else "gone"
        harmony_view[f"anchor:{anchor}"] = "visible" if h_vis else "gone"
    return {"verdict": DIFF if any_diff else MATCH,
            "android_view": android_view, "harmony_view": harmony_view,
            "detail": {"anchors": anchor_results, "set_diff": set_diff}}


def _resolve_data_keys(android_obs: Dict[str, Any],
                       harmony_obs: Dict[str, Any],
                       context: Dict[str, Any]) -> List[str]:
    """数据对比键域：声明域优先；空则两侧 data 顶层键交集兜底。"""
    declared = context.get("data_keys") or []
    if declared:
        return list(declared)
    a_data = android_obs.get("data_after") or {}
    h_data = harmony_obs.get("data_after") or {}
    return sorted(set(a_data.keys()) & set(h_data.keys()))


def _compare_data_views(a_data: Dict[str, Any], h_data: Dict[str, Any],
                        keys: List[str]) -> Dict[str, Any]:
    """逐 key 对比核心（data-after 与 data-restart 共用）。

    逐 key：双端取值均命中 → 宽松比较，不等 → DIFF；单端缺失 →
    DIFF（契约键在该端不存在=行为差异，fail-closed）；双端均缺失 →
    DIFF（missing_on_both，fail-closed：声明键两遍都拿不到=不可信）。
    """
    key_results = []
    any_diff = False
    for key in keys:
        a_value = lookup_semantic_value(a_data, key)
        h_value = lookup_semantic_value(h_data, key)
        if a_value is None and h_value is None:
            result, reason = "DIFF", "missing_on_both"
        elif a_value is None:
            result, reason = "DIFF", "missing_on_android"
        elif h_value is None:
            result, reason = "DIFF", "missing_on_harmony"
        elif loose_equal(a_value, h_value):
            result, reason = "match", "equal"
        else:
            result, reason = "DIFF", "value_mismatch"
        any_diff = any_diff or (result == "DIFF")
        key_results.append({"key": key, "android": a_value,
                            "harmony": h_value, "result": result,
                            "reason": reason})
    return {"any_diff": any_diff, "keys": key_results}


def compare_data(android_obs: Dict[str, Any], harmony_obs: Dict[str, Any],
                 context: Dict[str, Any]) -> Dict[str, Any]:
    """data 对比：语义数据状态逐 key（prefs/表行数/关键字段）。

    判定表（fail-closed，采集受阻≠行为矛盾）：
    - Android 探针采集受阻（access_mode 空/DENIED，TOOL_GAP 级）→
      MANUAL（android_probe_unavailable）；
    - 键域为空 → MANUAL（无契约声明且两侧键无交集，机器不裁决）；
    - 逐 key 对比（见 _compare_data_views）任一 DIFF → DIFF。
    """
    a_data = android_obs.get("data_after") or {}
    h_data = harmony_obs.get("data_after") or {}
    access = (android_obs.get("data_access_mode") or "").strip()
    if access in ("", "DENIED"):
        return {"verdict": MANUAL,
                "android_view": {"access_mode": access or "(none)"},
                "harmony_view": {"keys": _sample(sorted(h_data.keys()))},
                "detail": {"reason": "android_probe_unavailable",
                           "access_mode": access or "(none)"}}
    keys = _resolve_data_keys(android_obs, harmony_obs, context)
    if not keys:
        return {"verdict": MANUAL,
                "android_view": {"keys": _sample(sorted(a_data.keys()))},
                "harmony_view": {"keys": _sample(sorted(h_data.keys()))},
                "detail": {"reason": "no-declared-data-domain",
                           "android_keys": _sample(sorted(a_data.keys())),
                           "harmony_keys": _sample(sorted(h_data.keys()))}}
    result = _compare_data_views(a_data, h_data, keys)
    android_view = {k["key"]: k["android"] for k in result["keys"]}
    harmony_view = {k["key"]: k["harmony"] for k in result["keys"]}
    return {"verdict": DIFF if result["any_diff"] else MATCH,
            "android_view": android_view, "harmony_view": harmony_view,
            "detail": {"keys": result["keys"]}}


def compare_persistence(android_obs: Dict[str, Any],
                        harmony_obs: Dict[str, Any],
                        context: Dict[str, Any]) -> Dict[str, Any]:
    """persistence 对比：两侧 restart 语义状态互相确认（A 重启后=X 且
    H 重启后=X'，X==X'?）+ persist 文本锚点双端 restart 可见性。

    判定表：
    - 无持久化义务（段空且无 persist/data 断言且无数据域）→ MATCH
      （no-obligation；对齐 replayer NOT_APPLICABLE 语义）；
    - 义务存在：
      - persist 文本锚点 restart 可见性不一致 → DIFF；
      - restart 数据逐 key 对比（同 data 规则）任一 DIFF → DIFF；
      - 任一侧 restart 数据视图缺失（采集层）或探针不可用 → MANUAL；
      - 全一致 → MATCH。
    """
    obligations = context.get("obligations") or {}
    data_keys = context.get("data_keys") or []
    has_data_domain = bool(data_keys or
                           (android_obs.get("data_restart") or {})
                           or (harmony_obs.get("data_restart") or {}))
    if not obligations.get("persistence") and not has_data_domain:
        return {"verdict": MATCH, "android_view": {"obligation": "none"},
                "harmony_view": {"obligation": "none"},
                "detail": {"reason": "no-obligation"}}

    a_texts_restart = android_obs.get("texts_restart") or []
    h_texts_restart = harmony_obs.get("texts_restart") or []
    android_view: Dict[str, Any] = {}
    harmony_view: Dict[str, Any] = {}
    anchor_results = []
    any_diff = False
    for anchor in context.get("persist_text_anchors") or []:
        a_vis = _texts_show(a_texts_restart, anchor)
        h_vis = _texts_show(h_texts_restart, anchor)
        differs = a_vis != h_vis
        any_diff = any_diff or differs
        anchor_results.append(
            {"anchor": anchor, "android": "visible" if a_vis else "gone",
             "harmony": "visible" if h_vis else "gone",
             "result": "DIFF" if differs else "match"})
        android_view[f"restart:{anchor}"] = "visible" if a_vis else "gone"
        harmony_view[f"restart:{anchor}"] = "visible" if h_vis else "gone"

    manual_reason = ""
    data_detail: Dict[str, Any] = {}
    if has_data_domain or data_keys:
        a_restart = android_obs.get("data_restart")
        h_restart = harmony_obs.get("data_restart")
        a_missing = not isinstance(a_restart, dict) or not a_restart
        h_missing = not isinstance(h_restart, dict) or not h_restart
        if a_missing and h_missing:
            manual_reason = "restart-data-missing-both"
        elif a_missing:
            manual_reason = "restart-data-missing-android"
        elif h_missing:
            manual_reason = "restart-data-missing-harmony"
        else:
            sub = compare_data(
                {**android_obs, "data_after": a_restart},
                {**harmony_obs, "data_after": h_restart}, context)
            data_detail = sub["detail"]
            android_view.update(sub["android_view"])
            harmony_view.update(sub["harmony_view"])
            if sub["verdict"] == DIFF:
                any_diff = True
            elif sub["verdict"] == MANUAL:
                manual_reason = "restart-data-manual:" + json.dumps(
                    sub["detail"], ensure_ascii=False)[:60]
    if any_diff:
        verdict = DIFF
    elif manual_reason:
        verdict = MANUAL
    else:
        verdict = MATCH
    if verdict == MANUAL and manual_reason:
        android_view["blocked"] = harmony_view["blocked"] = manual_reason
    detail: Dict[str, Any] = {"persist_anchors": anchor_results}
    if data_detail:
        detail["restart_data"] = data_detail
    return {"verdict": verdict, "android_view": android_view,
            "harmony_view": harmony_view, "detail": detail}


def compare_side_effect(android_obs: Dict[str, Any],
                        harmony_obs: Dict[str, Any],
                        context: Dict[str, Any]) -> Dict[str, Any]:
    """side_effect 对比：两侧副作用注册（断言+单侧判定）对比。

    判定表：
    - 无副作用义务 → MATCH（no-obligation）；
    - 义务存在：
      - 同 kind 断言双端注册齐全 → 单侧判定一致 → MATCH / 不一致 →
        DIFF（expected=Android 实测，actual=Harmony 实测）；
      - 仅一端有注册 → MANUAL（另一端无机器观测：gmi chain 断言集
        不含 side_effect kind / 无公开 hdc 查询 API）；
      - 双端均无注册 → MANUAL（两侧均无公开 API，人工裁决）；
      - 双端判定含 MANUAL/PLATFORM（单侧即人工态）→ MANUAL。
    """
    obligations = context.get("obligations") or {}
    if not obligations.get("side_effect"):
        return {"verdict": MATCH, "android_view": {"obligation": "none"},
                "harmony_view": {"obligation": "none"},
                "detail": {"reason": "no-obligation"}}
    a_reg = {(a.get("kind") or ""): (a.get("verdict") or "")
             for a in android_obs.get("side_effect_verdicts") or []
             if a.get("kind")}
    h_reg = {(a.get("kind") or ""): (a.get("verdict") or "")
             for a in harmony_obs.get("side_effect_verdicts") or []
             if a.get("kind")}
    android_view: Dict[str, Any] = dict(a_reg)
    harmony_view: Dict[str, Any] = dict(h_reg)
    if not a_reg and not h_reg:
        return {"verdict": MANUAL, "android_view": android_view,
                "harmony_view": harmony_view,
                "detail": {"reason":
                           "no-machine-registration-on-either-side",
                           "note": "无公开查询 API 的副作用进人工队列"}}
    common = sorted(set(a_reg.keys()) & set(h_reg.keys()))
    only_a = sorted(set(a_reg.keys()) - set(h_reg.keys()))
    only_h = sorted(set(h_reg.keys()) - set(a_reg.keys()))
    results = []
    any_diff = False
    any_manual = False
    for kind in common:
        a_v, h_v = a_reg[kind], h_reg[kind]
        if H_MANUAL in (a_v, h_v) or "PLATFORM_LIMITATION" in (a_v, h_v):
            any_manual = True
            results.append({"kind": kind, "android": a_v, "harmony": h_v,
                            "result": "manual"})
            continue
        differs = a_v != h_v
        any_diff = any_diff or differs
        results.append({"kind": kind, "android": a_v, "harmony": h_v,
                        "result": "DIFF" if differs else "match"})
    if any_diff:
        verdict = DIFF
    elif any_manual or only_a or only_h:
        verdict = MANUAL
    else:
        verdict = MATCH
    return {"verdict": verdict, "android_view": android_view,
            "harmony_view": harmony_view,
            "detail": {"kinds": results, "android_only": only_a,
                       "harmony_only": only_h}}


# ============================================================================
# compare_dual：顶层守卫 + 四类分派（纯函数主体）
# ============================================================================

def compare_dual(android_obs: Optional[Dict[str, Any]],
                 harmony_obs: Optional[Dict[str, Any]],
                 context: Optional[Dict[str, Any]] = None
                 ) -> Dict[str, Any]:
    """双机四类 A/B 对比主入口（纯函数）。

    顶层守卫（优先级从高到低，任一命中四类一律 MANUAL）：
    1. 任一侧观测缺失（None/空，执行器异常）→ side-error；
    2. 任一侧 precondition 未建立 → precondition-unaligned（语义前置
       没对齐，差分无意义，人工队列，不算 DIFF）；
    3. 任一侧操作序列未走通 → execution-incomplete（单侧 FAIL 由该侧
       验证器负责，本引擎不重复裁决）。

    返回 {"rows": [四行 DUAL_CSV_FIELDS],
          "verdicts": {category: MATCH|DIFF|MANUAL},
          "diff_count": N, "blocked": str}。
    """
    if context is None:
        context = {"text_anchors": [], "persist_text_anchors": [],
                   "data_keys": [], "obligations": {}}
    reference = harmony_obs or android_obs or {}
    bc_id = (reference.get("bc_id") or "").strip()
    feature_id = (reference.get("feature_id") or "").strip()
    evidence_refs = ";".join(filter(None, [
        (android_obs or {}).get("evidence_dir", ""),
        (harmony_obs or {}).get("evidence_dir", "")]))

    def _manual_all(reason: str) -> Dict[str, Any]:
        rows = [_diff_row(bc_id, feature_id, cat, MANUAL,
                          {"error": reason}, {"error": reason},
                          evidence_refs, reason)
                for cat in CATEGORIES]
        return {"rows": rows,
                "verdicts": {cat: MANUAL for cat in CATEGORIES},
                "diff_count": 0, "blocked": reason}

    for side, obs in (("android", android_obs), ("harmony", harmony_obs)):
        if not isinstance(obs, dict) or not obs:
            return _manual_all(f"side-error:{side}: observation missing")
    for side, obs in (("android", android_obs), ("harmony", harmony_obs)):
        if not obs.get("precondition_ok"):
            return _manual_all(
                "precondition-unaligned:" + side + ": "
                + (obs.get("blocked_reason")
                   or "precondition not established"))
    for side, obs in (("android", android_obs), ("harmony", harmony_obs)):
        if not obs.get("executed"):
            return _manual_all(
                "execution-incomplete:" + side + ": "
                + (obs.get("blocked_reason") or "steps interrupted"))

    comparators = {
        "observable": compare_observable,
        "data": compare_data,
        "persistence": compare_persistence,
        "side_effect": compare_side_effect,
    }
    rows: List[Dict[str, str]] = []
    verdicts: Dict[str, str] = {}
    diff_count = 0
    for category, comparator in comparators.items():
        result = comparator(android_obs, harmony_obs, context)
        verdict = result["verdict"]
        verdicts[category] = verdict
        diff_count += 1 if verdict == DIFF else 0
        note_parts: List[str] = []
        if category == "observable":
            set_diff = (result.get("detail") or {}).get("set_diff") or {}
            if set_diff.get("android_only_count") or \
                    set_diff.get("harmony_only_count"):
                note_parts.append(
                    f"text-set-diff android_only="
                    f"{set_diff.get('android_only_count', 0)} harmony_only="
                    f"{set_diff.get('harmony_only_count', 0)} "
                    "(chrome diff recorded, not pixel compare)")
        if verdict == MANUAL:
            note_parts.append(_compact(result.get("detail") or {})[:180])
        note = "; ".join(note_parts) if note_parts else "ok"
        rows.append(_diff_row(bc_id, feature_id, category, verdict,
                              result.get("android_view", {}),
                              result.get("harmony_view", {}),
                              evidence_refs, note))
    return {"rows": rows, "verdicts": verdicts,
            "diff_count": diff_count, "blocked": ""}


# ============================================================================
# Harmony 侧执行器（同 skill import replayer.replay_bc；FakeDriver 可注入）
# ============================================================================

def run_harmony_side(bc: Dict[str, str], steps: List[Dict[str, str]],
                     driver: Any, bundle: str, ability: str,
                     evidence_root: Path) -> Dict[str, Any]:
    """Harmony 侧链执行 + 观测归一（调用 replayer.replay_bc，不修改）。

    证据落 evidence_root/chains/<bc>/replay/（与 replayer 约定一致）；
    观测从 replay_bc 返回行 + 证据目录归一。executed 口径：precondition
    ESTABLISHED 且 steps 全走通；PRECONDITION_FAILED → precondition_ok
    =False（差分 MANUAL 队列，不占 DIFF）。
    """
    row = replayer.replay_bc(bc, steps, driver, bundle, ability,
                             evidence_root)
    ev_dir = Path(row.get("evidence_dir") or "")

    def _load_json(name: str) -> Any:
        try:
            return json.loads((ev_dir / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    ui_after = _load_json("ui-after.json") or {}
    ui_restart = _load_json("ui-restart.json") or {}
    assertions_detail = _load_json("assertions.json") or {}
    data_after = _load_json("data-after.json")
    data_restart = _load_json("data-restart.json")

    pre_status = (row.get("precondition_status") or "").strip()
    precondition_ok = pre_status == "ESTABLISHED"
    steps_total = int(row.get("steps_total") or 0)
    steps_ok = int(row.get("steps_ok") or 0)
    executed = (precondition_ok and steps_total > 0
                and steps_ok == steps_total)
    blocked = "" if executed else (
        pre_status if not precondition_ok
        else f"steps_interrupted_at_{steps_ok}_of_{steps_total}")

    all_assertions = [a for a in (assertions_detail.get("assertions") or [])
                      if isinstance(a, dict)]
    anchor_assertions = [
        {"kind": a.get("kind", ""), "value": a.get("value", ""),
         "object": a.get("object", ""), "verdict": a.get("verdict", "")}
        for a in all_assertions]
    side_effect_verdicts = [
        {"kind": a.get("kind", ""), "verdict": a.get("verdict", "")}
        for a in all_assertions
        if (a.get("category") or "") == "side_effect"]

    return make_observation(
        "harmony", (bc.get("bc_id") or "").strip(),
        (bc.get("feature_id") or "").strip(),
        executed=executed, precondition_ok=precondition_ok,
        blocked_reason=blocked,
        texts_after=ui_after.get("texts") or [],
        texts_restart=ui_restart.get("texts") or [],
        data_after=data_after if isinstance(data_after, dict) else {},
        data_restart=data_restart if isinstance(data_restart, dict) else {},
        anchor_assertions=anchor_assertions,
        side_effect_verdicts=side_effect_verdicts,
        data_access_mode="probe",  # Harmony DebugSemanticProbe 常驻探针
        evidence_dir=str(ev_dir),
        note=str(row.get("note") or "")[:160],
    )


# ============================================================================
# Android 侧执行器（Protocol：subprocess 实现 + 测试 Fake 注入）
# ============================================================================

class AndroidExecutor(Protocol):
    """Android 侧执行器最小接口：单 BC → 语义观测。"""

    def run(self, bc: Dict[str, str]) -> Dict[str, Any]: ...


class AndroidChainExecutor:
    """subprocess 调 gmi_runtime --mode chain（复用 inventory 既有链执行
    能力：链前冷复位 + precondition 校验 + android_steps 执行 + 三点
    快照），再补 android_data_probe 数据采集（gmi_runtime 未接线探针，
    本引擎在链后 restart 时点外部补采——持久化语义下 restart probe 是
    after 落盘结果的保守代理，见模块 docstring）。

    单链重放：gmi_runtime CLI 无 bc-filter，本执行器以**临时 workspace**
    实现（过滤后的 behavior-contracts.csv + symlink candidates/feature-
    map）——不改 gmi_runtime（红线），其输出解析走既有 CSV/证据文件。

    Android 侧 android_steps 即 BC.operation_steps 列（gmi_runtime 既有
    语义：操作序列驱动）。
    """

    def __init__(self, project: Optional[Path], package: str,
                 serial: str, activity: str = "MainActivity",
                 android_workspace: Optional[Path] = None,
                 bc_fields: Optional[List[str]] = None,
                 probe_cli: Optional[Path] = None,
                 gmi_cli: Optional[Path] = None,
                 stay: float = 2.0, timeout: int = 1800):
        self.project = Path(project) if project else None
        self.package = package
        self.serial = serial
        self.activity = activity
        self.android_workspace = (Path(android_workspace)
                                  if android_workspace else None)
        self.bc_fields = bc_fields or []
        self.probe_cli = Path(probe_cli) if probe_cli \
            else _GMI_SCRIPTS / "android_data_probe.py"
        self.gmi_cli = Path(gmi_cli) if gmi_cli \
            else _GMI_SCRIPTS / "gmi_runtime.py"
        self.stay = stay
        self.timeout = timeout

    # ---- 临时 workspace（单链过滤，不触碰源 workspace）----

    def _build_temp_workspace(self, bc: Dict[str, str]) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="dual-android-ws-"))
        fields = list(self.bc_fields) if self.bc_fields else list(bc.keys())
        for key in bc:  # 防御：行键必须全在表头（write_csv 严格模式）
            if key not in fields:
                fields.append(key)
        write_csv(tmp / "behavior-contracts.csv", fields, [bc])
        if self.android_workspace:
            for name in ("candidates", "feature-map.json"):
                src = self.android_workspace / name
                if src.exists() and not (tmp / name).exists():
                    (tmp / name).symlink_to(src)
        return tmp

    # ---- 链输出解析（gmi_runtime 既有产物，只读）----

    @staticmethod
    def _read_chain_row(ws: Path, bc_id: str) -> Dict[str, str]:
        try:
            chains = read_csv(ws / "runtime-evidence" / "runtime-chains.csv")
        except ValueError:
            return {}
        for row in chains:
            if (row.get("bc_id") or "").strip() == bc_id:
                return row
        return {}

    @staticmethod
    def _texts_of(xml_path: Path) -> List[str]:
        try:
            raw = xml_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        return sorted(ui_text_set(raw))

    @staticmethod
    def _parse_assertions(raw: str) -> List[Dict[str, Any]]:
        try:
            data = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def _run_probe(self, out_path: Path, objects: str) -> Dict[str, Any]:
        argv = [sys.executable, str(self.probe_cli),
                "--package", self.package, "--device", self.serial,
                "--out", str(out_path)]
        if objects:
            argv += ["--objects", objects]
        try:
            subprocess.run(argv, capture_output=True, text=True, timeout=300)
        except (subprocess.TimeoutExpired, OSError):
            return {}
        try:
            return json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def run(self, bc: Dict[str, str]) -> Dict[str, Any]:
        if self.project is None:
            raise ValueError(
                "AndroidChainExecutor requires --android-project when "
                "oracle cache misses (fail-fast, no silent fallback)")
        bc_id = (bc.get("bc_id") or "").strip()
        feature_id = (bc.get("feature_id") or "").strip()
        tmp_ws = self._build_temp_workspace(bc)
        argv = [sys.executable, str(self.gmi_cli),
                "--project", str(self.project),
                "--workspace", str(tmp_ws),
                "--package", self.package,
                "--activity", self.activity,
                "--serial", self.serial,
                "--stay", str(self.stay),
                "--mode", "chain"]
        try:
            subprocess.run(argv, capture_output=True, text=True,
                           timeout=self.timeout)
        except (subprocess.TimeoutExpired, OSError):
            pass  # 链执行失败 → chain row 缺失 → blocked 口径
        chain = self._read_chain_row(tmp_ws, bc_id)
        status = (chain.get("chain_status") or "").strip()
        ev_dir = tmp_ws / "runtime-evidence" / "evidence" / "chains" / bc_id

        precondition_ok = status != _ANDROID_PRECONDITION_FAILED
        executed = bool(status) and status not in _ANDROID_BLOCKED
        blocked = "" if executed else (status or "chain-not-executed")

        # data probe：链后 restart 时点外部补采（模块 docstring 口径）
        objects = ",".join(build_compare_context(bc)["data_keys"])
        probe = self._run_probe(tmp_ws / "data-restart.json", objects)
        assertions = self._parse_assertions(chain.get("assertion_results"))

        return make_observation(
            "android", bc_id, feature_id,
            executed=executed, precondition_ok=precondition_ok,
            blocked_reason=blocked,
            texts_after=self._texts_of(ev_dir / "after" / "ui.xml"),
            texts_restart=self._texts_of(ev_dir / "restart" / "ui.xml"),
            data_after=probe if probe else {},
            data_restart=probe if probe else {},
            anchor_assertions=assertions,
            side_effect_verdicts=[
                {"kind": a.get("kind", ""), "verdict": a.get("verdict", "")}
                for a in assertions
                if (a.get("kind") or "") in replayer.SIDE_EFFECT_KINDS],
            data_access_mode=str(probe.get("access_mode", "")),
            evidence_dir=str(ev_dir),
            note=(chain.get("note") or "")[:160],
        )


# ============================================================================
# oracle cache（骨架，#92 详化；Android 侧语义观测复用）
# ============================================================================

def bc_row_sha(bc: Dict[str, str]) -> str:
    """BC 行规范化内容 sha256（列序无关：sorted key + 值 trim）。"""
    canonical = json.dumps(
        {k: (v or "").strip() for k, v in bc.items()},
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def oracle_cache_key(bc: Dict[str, str], apk_sha: str, seed_sha: str) -> str:
    """四元组 cache 键：sha256(bc_id | apk_sha | seed_sha | bc_row_sha)。"""
    raw = "|".join([(bc.get("bc_id") or "").strip(),
                    (apk_sha or "").strip(), (seed_sha or "").strip(),
                    bc_row_sha(bc)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def seed_sha_of(seed: str) -> str:
    return hashlib.sha256((seed or "").encode("utf-8")).hexdigest()


def load_oracle_cache(cache_dir: Path, key: str) -> Optional[Dict[str, Any]]:
    """cache 读取：schema 校验失败/文件缺失 → None（视为 miss）。"""
    path = Path(cache_dir) / f"{key}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) \
            or data.get("schema") != ORACLE_CACHE_SCHEMA:
        return None
    observation = data.get("observation")
    return observation if isinstance(observation, dict) else None


def store_oracle_cache(cache_dir: Path, key: str,
                       observation: Dict[str, Any],
                       meta: Optional[Dict[str, Any]] = None) -> None:
    """cache 写入（原子写；键输入登记进 key_inputs 供 #92 审计）。"""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    record = {"schema": ORACLE_CACHE_SCHEMA,
              "captured_at": (meta or {}).get("captured_at", ""),
              "key_inputs": (meta or {}).get("key_inputs", {}),
              "observation": observation}
    atomic_json(cache_dir / f"{key}.json", record)


# ============================================================================
# 主流程 + CSV/CLI
# ============================================================================

def select_dual_bcs(bc_rows: List[Dict[str, str]],
                    bc_filter: str) -> List[Dict[str, str]]:
    """差分 BC 选择：--bc-filter 指定集（逗号分隔）；空过滤器=全量。"""
    if not (bc_filter or "").strip():
        return bc_rows
    wanted = {b.strip() for b in bc_filter.split(",") if b.strip()}
    return [r for r in bc_rows if (r.get("bc_id") or "").strip() in wanted]


def verify_dual(args: argparse.Namespace) -> int:
    bc_rows = replayer.load_bc_rows(Path(args.bc))
    selected = select_dual_bcs(bc_rows, args.bc_filter)
    if not selected:
        print("[dual] no BC selected (empty filter result)", file=sys.stderr)
        return 2
    steps_map = replayer.load_harmony_steps(
        Path(args.harmony_steps) if args.harmony_steps else None, bc_rows)

    cache_dir = Path(args.oracle_cache_dir)
    evidence_root = Path(args.workspace) / "evidence" / "dual"
    if not args.dry_run:
        evidence_root.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        plan = {}
        for bc in selected:
            bc_id = (bc.get("bc_id") or "").strip()
            context = build_compare_context(bc)
            plan[bc_id] = {
                "harmony_steps": len(steps_map.get(bc_id, [])),
                "obligations": context["obligations"],
                "text_anchors": context["text_anchors"],
                "data_keys": context["data_keys"],
                "oracle_cache_key": oracle_cache_key(
                    bc, args.apk_sha,
                    seed_sha_of(args.seed or DEFAULT_SEED_ID))[:16],
            }
        print(json.dumps({"selected": list(plan), "plan": plan,
                          "oracle_cache_dir": str(cache_dir)},
                         ensure_ascii=False, indent=1))
        return 0

    android_executor: AndroidExecutor = AndroidChainExecutor(
        project=Path(args.android_project) if args.android_project else None,
        package=args.package, serial=args.android_device,
        activity=args.android_activity,
        android_workspace=Path(args.android_workspace)
        if args.android_workspace else None,
        bc_fields=bc_csv_fields(Path(args.bc)))
    # harmony 驱动注入点（真机 HdcDeviceDriver；测试 FakeDriver 可经
    # args.harmony_driver 注入，与 replayer FakeDriver 测试同构）
    harmony_driver = getattr(args, "harmony_driver", None)
    if harmony_driver is None:
        try:
            harmony_driver = replayer.build_driver(argparse.Namespace(
                hdc=args.hdc, device=args.harmony_device,
                bundle=args.bundle, ability=args.ability))
        except replayer.DriverUnavailable as exc:
            print(f"[dual] harmony device unavailable: {exc}",
                  file=sys.stderr)
            return 2

    seed = args.seed or DEFAULT_SEED_ID
    rows_out: List[Dict[str, str]] = []
    stats = {"bc_total": len(selected), "cells": 0, "match": 0,
             "diff": 0, "manual": 0, "cache_hit": 0, "cache_miss": 0,
             "bc_with_diff": 0}
    for bc in selected:
        bc_id = (bc.get("bc_id") or "").strip()
        context = build_compare_context(bc)
        key = oracle_cache_key(bc, args.apk_sha, seed_sha_of(seed))
        android_obs = None if args.no_cache else \
            load_oracle_cache(cache_dir, key)
        if android_obs is not None:
            stats["cache_hit"] += 1
        else:
            stats["cache_miss"] += 1
            if not args.android_project or not args.package:
                print(f"[dual] BC {bc_id}: oracle cache miss and android "
                      "executor not configured (--android-project / "
                      "--package required)", file=sys.stderr)
                return 2
            android_obs = android_executor.run(bc)
            store_oracle_cache(cache_dir, key, android_obs, {
                "key_inputs": {"bc_id": bc_id, "apk_sha": args.apk_sha,
                               "seed": seed,
                               "bc_row_sha": bc_row_sha(bc)}})
        harmony_obs = run_harmony_side(
            bc, steps_map.get(bc_id, []), harmony_driver,
            args.bundle, args.ability, evidence_root)
        result = compare_dual(android_obs, harmony_obs, context)
        rows_out.extend(result["rows"])
        for verdict in result["verdicts"].values():
            stats["cells"] += 1
            if verdict == MATCH:
                stats["match"] += 1
            elif verdict == DIFF:
                stats["diff"] += 1
            else:
                stats["manual"] += 1
        stats["bc_with_diff"] += 1 if result["diff_count"] else 0

    rows_out.sort(key=lambda r: (r["bc_id"], r["assertion_type"]))
    write_csv(Path(args.out), DUAL_CSV_FIELDS, rows_out)
    print(json.dumps({"stats": stats, "out": str(args.out)},
                     ensure_ascii=False, indent=1))
    return 1 if stats["diff"] else 0


def bc_csv_fields(bc_path: Path) -> List[str]:
    """读 BC CSV 表头（临时 workspace 保留全列）。"""
    with open(bc_path, encoding="utf-8-sig", newline="") as handle:
        reader = _csv.reader(handle)
        return next(reader)


def validate_results(path: Path) -> List[str]:
    """校验 dual-diff-results.csv：列齐全、枚举合法、BC×类型唯一、
    note 含 dual-source 标、DIFF 行双侧实测非空。返回错误清单
    （Gate 4 / I 代理只读检查）。"""
    errors: List[str] = []
    try:
        rows = read_csv(path)
    except ValueError as exc:
        return [str(exc)]
    if not rows:
        return ["dual-diff-results.csv is empty"]
    header = set(rows[0].keys())
    missing = [f for f in DUAL_CSV_FIELDS if f not in header]
    if missing:
        errors.append(f"missing columns: {','.join(missing)}")
    seen: set = set()
    for row in rows:
        bc_id = (row.get("bc_id") or "").strip()
        category = (row.get("assertion_type") or "").strip()
        if not bc_id:
            errors.append("row without bc_id")
            continue
        if category not in CATEGORIES:
            errors.append(f"{bc_id}: bad assertion_type {category!r}")
            continue
        if (bc_id, category) in seen:
            errors.append(
                f"duplicate bc_id+assertion_type: {bc_id}/{category}")
        seen.add((bc_id, category))
        verdict = (row.get("verdict") or "").strip()
        if verdict not in (MATCH, DIFF, MANUAL):
            errors.append(f"{bc_id}/{category}: bad verdict {verdict!r}")
        if DUAL_NOTE_TAG not in (row.get("note") or ""):
            errors.append(
                f"{bc_id}/{category}: note missing '{DUAL_NOTE_TAG}' tag")
        if verdict == DIFF and not (
                (row.get("android_expected") or "").strip()
                and (row.get("harmony_actual") or "").strip()):
            errors.append(
                f"{bc_id}/{category}: DIFF without both side observations")
    return errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dual_verify.py",
        description="双机行为差分引擎：两侧同步执行（Android 按 "
                    "android_steps / Harmony 按 harmony_steps）+ 语义前置"
                    "对齐 + 四类结果 A/B 对比 + DIFF 报告")
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="双机差分主流程")
    p_verify.add_argument("--bc", required=True, type=Path,
                          help="behavior-contracts.csv（两侧共享同一契约）")
    p_verify.add_argument("--harmony-steps", type=Path, default=None,
                          help="harmony-steps.csv（缺省回退 BC 内嵌列）")
    p_verify.add_argument("--android-device", default="emulator-5554")
    p_verify.add_argument("--harmony-device", default="127.0.0.1:5557")
    p_verify.add_argument("--workspace", required=True, type=Path,
                          help="phase-04 workspace（差分证据根）")
    p_verify.add_argument("--bc-filter", default="",
                          help="只差分指定 bc_id（逗号分隔）")
    p_verify.add_argument("--out", required=True, type=Path,
                          help="dual-diff-results.csv 输出路径")
    p_verify.add_argument("--oracle-cache-dir", type=Path,
                          default=Path("evidence/oracle-cache"),
                          help="Android 侧 oracle cache 目录")
    p_verify.add_argument("--no-cache", action="store_true",
                          help="强制重跑 Android 侧并覆写 cache")
    p_verify.add_argument("--android-project", default="",
                          help="Android 源码根（gmi_runtime --project）")
    p_verify.add_argument("--android-workspace", default="",
                          help="phase-02 workspace（Page-ID 映射来源）")
    p_verify.add_argument("--android-activity", default="MainActivity")
    p_verify.add_argument("--package", default="",
                          help="Android 应用包名（链执行/data probe）")
    p_verify.add_argument("--bundle", required=True, help="Harmony 包名")
    p_verify.add_argument("--ability", default="EntryAbility")
    p_verify.add_argument("--hdc", default="hdc")
    p_verify.add_argument("--apk-sha", default="",
                          help="APK sha256（oracle cache 键；缺省弱化键）")
    p_verify.add_argument("--seed", default="",
                          help="seed 标识（#92 详化；缺省 cold-reset-v1）")
    p_verify.add_argument("--dry-run", action="store_true",
                          help="无设备：仅校验输入与差分计划")

    p_validate = sub.add_parser("validate", help="校验 dual-diff-results.csv")
    p_validate.add_argument("--results", required=True, type=Path)

    args = parser.parse_args(argv)
    if args.command == "validate":
        errors = validate_results(args.results)
        if errors:
            for error in errors:
                print(f"[dual] ERROR {error}", file=sys.stderr)
            return 1
        print("[dual] validate ok")
        return 0
    return verify_dual(args)


if __name__ == "__main__":
    raise SystemExit(main())
