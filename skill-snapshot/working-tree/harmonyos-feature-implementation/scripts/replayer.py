#!/usr/bin/env python3
"""Phase 4 v4（feature-semantic 范式）七段断言重放器。

核心机制（用户修正 1+2+5）：双端行为验证 = 同一份 BC 七段共享
（intent / precondition / semantic_input / expected_state_change /
observable_result / persistence / side_effect），同意图异路径——
android_steps / harmony_steps 各自独立，路径自由，**只验结果断言**。
本工具是 Harmony 侧重放器：按实施者记录的 harmony_steps 在真机上
重放操作序列，然后对七段中的四类可机器验证断言独立判定。

收敛式重构批次 2（#85，借 LLMigrate preparation 思想）：每条 BC 重放前
执行 prepare 阶段——reset（应用冷复位到干净态：force-stop + start +
等待就绪）→ prepare（执行 BC.prepare_steps 可选列，与批次 1 Android 侧
gmi_runtime 同构）→ verify precondition（pre_state token 校验，token
提取复用 inventory/gmi_runtime.parse_pre_state_tokens——跨 skill import
共享同一提取语义，不复制双份实现）；verify 失败 → 冷复位重试一次 →
仍失败 PRECONDITION_FAILED（终态，四类断言一律 MANUAL_VERIFY_REQUIRED
进 Gate 4 人工队列，不算功能 FAIL——前置无法建立≠实现缺陷）。

实跑回移植（HOME-FULL-RUN1 全量轮 D1-D9 修复，replayer_p4.py 验证有效）：
    D1 bounds 字符串形态 "[x1,y1][x2,y2]"；D2 aa dump -l mission-list
    前台解析；D3 long_press；D4 swipe target 语义定位 + direction；
    D5 locate id/key 兜底；D6/D8 定位失败刷新重试 + 数据等待（冷启动
    数据渲染晚于 UI 稳定判定——空态也稳定）；D7 dump 落盘竞态（dump 后
    sleep 0.8s + 内容校验重试）；D9 每链前冷复位（链间状态泄漏互染）。

DebugSemanticProbe 独立探针（替代 replay-data.json 自答，批次 2 #85）：
    data 断言的数据出口不再信任应用侧自报的 replay-data.json——改由
    Phase 3 scaffold 生成、哈希冻结（P4 实施者禁改）的 DebugSemanticProbe
    常驻探针产出：周期采样全部 data-contract 语义对象（未接线 → null），
    双通道输出（沙箱文件 semantic-probe.json + hilog tag SemanticProbe）。
    replayer 优先 hdc file recv 沙箱文件，失败退化 hilog -x 缓冲抓取。

四类断言判定（每类独立，对应七段）：
    observable  页面可见结果（文本存在/消失/组件状态）——uitest dumpLayout
                快照判定，机器可验；
    data        数据状态变化（语义对象级，应用侧自检接口/导出数据快照，
                不比物理存储）——机器可验；
    persistence 杀进程重启后断言重验（aa force-stop + aa start + 重验
                observable/data）——机器可验；
    side_effect 系统副作用（通知/文件导出等——hdc shell 查询对应系统
                服务）——机器可验；无公开 API 可查的 → MANUAL_VERIFY_
                REQUIRED（不是 PASS，进 Gate 4 人工裁决队列）。

判定铁律（用户修正 3 精神）：
    - 断言 FAIL 就是 FAIL，重放器无权解释、无权降级、无权改写；
    - 平台无法执行某断言（系统无对应能力）→ PLATFORM_LIMITATION
      （进 Gate 4 PLATFORM_DEVIATION 队列，不是 PASS）；
    - 操作序列未走通（steps interrupted）→ 四类断言一律 FAIL
      （fail-closed：操作未完成则结果断言不可信，Phase 4 语义下
      实施者声称的路径走不通即实施缺陷）。

防伪（沿用 Phase 2 采集器实战经验，HOME-FULL-RUN1）：
    - foreground 校验铁律：每步操作后校验前台仍是目标应用（伪访问/
      伪 ANR 防护——dumpsys 级前台判定，见 attempts/patch_pseudo_anr_v4）；
    - 稳定性双确认：after/restart 快照两次 dump 一致才进入断言评估
      （避免动画中间态被误判 FAIL）；
    - 重启重验前强制前台校验 + 冷启动 settle。

输入：
    --bc            behavior-contracts.csv（Phase 2 权威产物；七段从列
                    别名映射，兼容 v3 列名与 v4 semantic_input 新列）
    --harmony-steps harmony-steps.csv（实施者记录的真实操作序列：
                    bc_id,feature_id,steps(JSON),notes）；缺省回退 BC
                    内嵌 harmony_steps 列（JSON-in-CSV）
    --feature-map   feature-map.json（verify_mode 分母；RUNTIME 才重放，
                    SOURCE_CONFIRM 标 SKIPPED_SOURCE_CONFIRM）
    --device/--hdc  目标设备（hdc 真机驱动；无设备环境下单测注入
                    FakeDriver 跑判定逻辑，本文件设备驱动为接口实现，
                    dump 解析细节标注 TODO 联调校正）

输出：
    <out>/replay-results.csv（列见 REPLAY_CSV_FIELDS）
    <evidence-root>/chains/<bc>/replay/{operations.log, assertions.json,
    ui-after.json, ui-restart.json, data-after.json, data-restart.json,
    side-effects.json}（证据引用，供 Gate 4 抽查）

用法：
    replay   执行重放（需设备或注入驱动；--dry-run 仅校验输入与断言分类）
    validate 校验已有 replay-results.csv 的格式/枚举/证据目录完整性
             （Gate 4 / I 代理可先行消费的只读检查）
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from _common import atomic_json, read_csv, write_csv

# ----------------------------------------------------------------------------
# 跨 skill 共享 import（批次 2 #85）：pre_state token 提取与 Android 侧
# gmi_runtime 共享同一实现（避免双份语义漂移）。gmi_runtime 为纯函数库，
# import 无设备副作用；找不到时 fail-fast（不静默降级到本地复制版）。
# ----------------------------------------------------------------------------
_GMI_SCRIPTS = (Path(__file__).resolve().parents[2]
                / "android-migration-inventory" / "scripts")
if not (_GMI_SCRIPTS / "gmi_runtime.py").is_file():
    raise ImportError(
        "shared precondition module not found: "
        f"{_GMI_SCRIPTS / 'gmi_runtime.py'} (android-migration-inventory "
        "skill must sit beside harmonyos-feature-implementation)")
if str(_GMI_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_GMI_SCRIPTS))
from gmi_runtime import parse_pre_state_tokens  # noqa: E402

# ============================================================================
# 七段定义与 BC 列别名映射（G 代理 #56 的 semantic_input 可选列 + 既有 v3 列）
# ============================================================================

SEVEN_SEGMENTS = (
    "intent",               # 用户意图（共享，双端同一）
    "precondition",         # 前置状态（共享）
    "semantic_input",       # 语义输入（共享；v4 新列，可选）
    "expected_state_change",  # 期望数据/状态变化（共享）
    "observable_result",    # 期望页面可见结果（共享）
    "persistence",          # 持久化期望（共享）
    "side_effect",          # 系统副作用期望（共享）
)

# 每段允许的 BC CSV 列别名（按优先级；首个非空命中生效）
SEGMENT_ALIASES: Dict[str, tuple] = {
    "intent": ("intent", "user_intent"),
    "precondition": ("precondition", "pre_state"),
    "semantic_input": ("semantic_input",),
    "expected_state_change": ("expected_state_change", "data_state_change"),
    "observable_result": ("observable_result",),
    "persistence": ("persistence", "persistence_targets",
                    "persistence_expectation"),
    "side_effect": ("side_effect", "external_side_effects",
                    "side_effect_expectation"),
}

# ============================================================================
# 断言分类（result_assertions JSON-in-CSV；与 android 侧 chain 断言同构扩展）
# ============================================================================

OBSERVABLE_KINDS = frozenset({"text_visible", "text_gone", "component_state"})
DATA_KINDS = frozenset({"data_object"})
PERSISTENCE_KINDS = frozenset({"persist_after_restart", "persist_data_after_restart"})
SIDE_EFFECT_KINDS = frozenset({
    "notification", "calendar", "file_export", "clipboard",
    "system_setting", "share",
})

ASSERTION_CATEGORY = {
    **{kind: "observable" for kind in OBSERVABLE_KINDS},
    **{kind: "data" for kind in DATA_KINDS},
    **{kind: "persistence" for kind in PERSISTENCE_KINDS},
    **{kind: "side_effect" for kind in SIDE_EFFECT_KINDS},
}

# 段 → 断言类别的义务映射（段非空即有验证义务）
SEGMENT_OBLIGATION = {
    "observable_result": "observable",
    "expected_state_change": "data",
    "persistence": "persistence",
    "side_effect": "side_effect",
}

# 单元格取值枚举（四类断言 + 总判定；Gate 4 / I 代理契约）
PASS = "PASS"
FAIL = "FAIL"
MANUAL = "MANUAL_VERIFY_REQUIRED"
PLATFORM = "PLATFORM_LIMITATION"
NA = "NOT_APPLICABLE"
SKIPPED = "SKIPPED_SOURCE_CONFIRM"
# 批次 2 #85：前置状态无法建立（reset + prepare_steps + verify 两次尝试
# 均失败）——不算功能 FAIL；四类断言一律 MANUAL（人工裁决队列），
# 归 Gate 4 MANUAL_TAKEOVER。
PRECONDITION_FAILED = "PRECONDITION_FAILED"

CATEGORY_VERDICTS = (PASS, FAIL, MANUAL, PLATFORM, NA)
REPLAY_VERDICTS = (PASS, FAIL, MANUAL, PLATFORM, NA, SKIPPED,
                   PRECONDITION_FAILED)
# precondition 阶段状态（CSV precondition_status 列枚举）
PRECONDITION_STATUSES = (
    "ESTABLISHED",           # reset+prepare+verify 通过
    "PRECONDITION_FAILED",   # 两次尝试均失败（终态，人工队列）
    "RESET_FAILED",          # 冷复位本身失败（设备/应用启动问题）
    "SKIPPED_NO_STEPS",      # 无 harmony_steps（未进入 prepare 阶段）
    "SKIPPED_BROKEN_COLUMN", # JSON 列损坏（未进入 prepare 阶段）
)

# 聚合优先级：FAIL 最严（铁律），其后人工、平台、通过、不适用
_AGG_ORDER = {FAIL: 0, MANUAL: 1, PLATFORM: 2, PASS: 3, NA: 4}

REPLAY_CSV_FIELDS = [
    "bc_id", "feature_id", "verify_mode",
    "precondition_status", "steps_total", "steps_ok",
    "observable_result", "data_result",
    "persistence_result", "side_effect_result",
    "replay_verdict", "fail_reason", "evidence_dir", "note",
]

# side_effect kind → 机器可验性（无公开 hdc 查询 API 的进人工队列）
SIDE_EFFECT_QUERYABILITY: Dict[str, str] = {
    "notification": "queryable",     # anm dump / 通知服务查询
    "file_export": "queryable",      # hdc shell ls + file recv
    "calendar": "manual",            # 日历提供者无公开 hdc 查询 API
    "clipboard": "manual",           # 剪贴板无稳定公开读接口
    "system_setting": "manual",      # 系统设置项 hdc 查询覆盖有限
    "share": "manual",               # 分享面板属系统 UI，事后不可查
}

HARMONY_STEP_ACTIONS = frozenset({"tap", "input", "back", "swipe",
                                  "long_press"})

# ----------------------------------------------------------------------------
# DebugSemanticProbe 探针通道契约（批次 2 #85；生成侧在 scaffold 的
# data_contracts.write_semantic_probe，此处只约定消费端读取契约）
# ----------------------------------------------------------------------------
PROBE_SNAPSHOT_FILENAME = "semantic-probe.json"   # 沙箱 files/ 下文件名
PROBE_HILOG_TAG = "SemanticProbe"                 # hilog tag
PROBE_HILOG_SNAPSHOT_MARK = "SNAPSHOT"            # 快照行前缀标记
# 探针冻结文件在 harmony-project 内的路径（Gate 4 哈希校验对象；
# 与 scaffold data_contracts.PROBE_RELATIVE_PATH 保持一致）
PROBE_RELATIVE_PATH = "entry/src/main/ets/probe/DebugSemanticProbe.ets"


# ============================================================================
# BC 加载与七段提取
# ============================================================================

def load_bc_rows(path: Path) -> List[Dict[str, str]]:
    rows = read_csv(path)
    for row in rows:
        bc_id = (row.get("bc_id") or "").strip()
        if not bc_id:
            raise ValueError(f"behavior-contracts row without bc_id: {path}")
    return rows


def extract_segments(bc: Dict[str, str]) -> Dict[str, str]:
    """BC CSV 行 → 七段文本（列别名映射；intent/precondition 等下兼容 v3）。"""
    segments: Dict[str, str] = {}
    for segment, aliases in SEGMENT_ALIASES.items():
        value = ""
        for alias in aliases:
            raw = (bc.get(alias) or "").strip()
            if raw:
                value = raw
                break
        segments[segment] = value
    return segments


def parse_json_column(raw: str) -> List[Dict[str, str]]:
    """CSV 单元格 JSON 数组 → list[dict]；空/坏 JSON/非数组 → []。"""
    value = (raw or "").strip()
    if not value:
        return []
    try:
        data = json.loads(value)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def json_column_broken(raw: str) -> bool:
    """列非空但无法解析为 JSON 数组（显式暴露，不静默降级）。"""
    value = (raw or "").strip()
    if not value:
        return False
    try:
        data = json.loads(value)
    except Exception:
        return True
    return not isinstance(data, list)


def load_harmony_steps(path: Optional[Path], bc_rows: List[Dict[str, str]]
                       ) -> Dict[str, List[Dict[str, str]]]:
    """harmony_steps 装配：独立 CSV（bc_id,feature_id,steps,notes）优先，
    回退 BC 内嵌 harmony_steps 列（JSON-in-CSV）。未知 action 保留并在
    执行时按 unsupported 处理（fail-closed，不静默跳过）。"""
    steps_map: Dict[str, List[Dict[str, str]]] = {}
    for row in bc_rows:
        embedded = parse_json_column(row.get("harmony_steps", ""))
        if embedded:
            steps_map[(row.get("bc_id") or "").strip()] = embedded
    if path is not None:
        for row in read_csv(path):
            bc_id = (row.get("bc_id") or "").strip()
            if not bc_id:
                raise ValueError(f"harmony-steps row without bc_id: {path}")
            steps_map[bc_id] = parse_json_column(row.get("steps", ""))
    return steps_map


def load_feature_map(path: Optional[Path]) -> Dict[str, Any]:
    """读 feature-map.json（Phase 2 权威 schema，与 gmi_runtime 同构容忍）。

    返回 {"runtime_features": set, "source_confirm_features": set,
          "missing": bool}。缺失 → {"missing": True}，重放选择降级
    evidence_class=RUNTIME_REQUIRED（legacy 兼容，fail-closed 不静默排除）。
    """
    result: Dict[str, Any] = {"runtime_features": set(),
                              "source_confirm_features": set(),
                              "missing": True}
    if path is None or not Path(path).exists():
        return result
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return result
    features = data.get("features") if isinstance(data, dict) else data
    if isinstance(features, dict):
        features = [{"feature_id": key, **(value if isinstance(value, dict) else {})}
                    for key, value in features.items()]
    if not isinstance(features, list):
        return result
    for feature in features:
        if not isinstance(feature, dict):
            continue
        fid = str(feature.get("feature_id") or feature.get("id") or "").strip()
        if not fid:
            continue
        mode = str(feature.get("verify_mode") or "").strip().upper().replace("-", "_")
        if mode == "RUNTIME":
            result["runtime_features"].add(fid)
        elif mode in ("SOURCE_CONFIRM", "SOURCECONFIRM"):
            result["source_confirm_features"].add(fid)
    result["missing"] = False
    return result


def select_replay_bcs(bc_rows: List[Dict[str, str]], feature_map: Dict[str, Any]
                      ) -> Dict[str, Any]:
    """重放选择：RUNTIME feature 的 BC 选中；SOURCE_CONFIRM 排除
    （SKIPPED_SOURCE_CONFIRM，静态确认即可，不占机器重放分母）；
    feature 不在 map → unmapped（fail-closed，绝不静默当作排除）。
    feature-map 缺失 → 降级 evidence_class=RUNTIME_REQUIRED。"""
    selected: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    unmapped: List[Dict[str, str]] = []
    if feature_map.get("missing"):
        for row in bc_rows:
            evidence = (row.get("evidence_class") or "").strip().upper()
            if evidence == "RUNTIME_REQUIRED":
                selected.append(row)
            else:
                skipped.append({**row, "_skip_reason":
                                f"evidence_class={evidence or '(empty)'} (fallback)"})
        return {"selected": selected, "skipped": skipped, "unmapped": unmapped,
                "fallback": True}
    runtime = feature_map["runtime_features"]
    source_confirm = feature_map["source_confirm_features"]
    for row in bc_rows:
        fid = (row.get("feature_id") or "").strip()
        if fid in runtime:
            selected.append(row)
        elif fid in source_confirm:
            skipped.append({**row, "_skip_reason": "verify_mode=SOURCE_CONFIRM"})
        else:
            unmapped.append(row)
    return {"selected": selected, "skipped": skipped, "unmapped": unmapped,
            "fallback": False}


# ============================================================================
# 断言义务计算（段非空即有义务；义务存在而断言缺失 → MANUAL，不静默 PASS）
# ============================================================================

def classify_assertions(assertions: List[Dict[str, str]]
                        ) -> Dict[str, List[Dict[str, str]]]:
    """断言列表按四类分桶；未知 kind 归 unknown（保守 → 该类 MANUAL）。"""
    buckets: Dict[str, List[Dict[str, str]]] = {
        "observable": [], "data": [], "persistence": [], "side_effect": [],
        "unknown": [],
    }
    for assertion in assertions:
        kind = (assertion.get("kind") or "").strip()
        buckets[ASSERTION_CATEGORY.get(kind, "unknown")].append(assertion)
    return buckets


def assertion_obligations(segments: Dict[str, str],
                          buckets: Dict[str, List[Dict[str, str]]]
                          ) -> Dict[str, str]:
    """四类义务 → {PASS-able/需要覆盖/不适用} 三态：
    - "none"   段空且无该类断言 → NOT_APPLICABLE；
    - "assert" 段非空或无该类断言 → 正常机器判定；
    - "manual" 段非空但无机器断言（含 unknown kind 兜底）→ 该类
      MANUAL_VERIFY_REQUIRED（BC 语义义务存在，机器断言未覆盖，不静默放行）。
    """
    obligations: Dict[str, str] = {}
    for segment, category in SEGMENT_OBLIGATION.items():
        segment_filled = bool(segments.get(segment, "").strip())
        has_assertions = bool(buckets[category])
        has_unknown = bool(buckets["unknown"])
        if not segment_filled and not has_assertions:
            obligations[category] = "none"
        elif segment_filled and not has_assertions:
            obligations[category] = "manual"
        else:
            # 段空但断言存在 → 机器判定；unknown kind 一律拉到 manual 兜底
            obligations[category] = "manual" if has_unknown else "assert"
    return obligations


# ============================================================================
# 设备驱动接口（Protocol）：真机 hdc 实现留联调 TODO；测试注入 FakeDriver
# ============================================================================

class DriverUnavailable(RuntimeError):
    """设备能力不可用（无法连接/系统无对应服务）→ PLATFORM_LIMITATION 判级。"""


class UiSnapshot:
    """uitest dumpLayout 快照的语义视图（texts + 组件状态行）。

    components: [{"type","text","id","visible","enabled","checked"}]；
    解析容错：缺字段按空值处理，不抛异常。
    """

    def __init__(self, raw: str, texts: List[str],
                 components: List[Dict[str, str]]):
        self.raw = raw
        self.texts = texts
        self.components = components

    def shows_text(self, value: str) -> bool:
        """文本可见判定（与 android 侧 _xml_shows 同构：大小写不敏感子串
        + raw 兜底），供 text_visible/text_gone。"""
        if not value:
            return False
        lowered = value.lower()
        for text in self.texts:
            if lowered in text.lower():
                return True
        return lowered in (self.raw or "").lower()

    def component_attr(self, target: str, attr: str) -> Optional[str]:
        """语义定位组件（text/id 子串匹配）→ 属性值；找不到 → None。"""
        lowered = target.lower()
        for component in self.components:
            if lowered in (component.get("text") or "").lower() or \
                    lowered in (component.get("id") or "").lower():
                return (component.get(attr) or "").strip()
        return None


class QueryResult:
    """副作用查询结果（机器可验类）。"""

    def __init__(self, supported: bool, matched: bool, detail: str = ""):
        self.supported = supported  # False → 设备/系统无此查询能力
        self.matched = matched      # supported 时：查询值是否匹配期望
        self.detail = detail


class DeviceDriver(Protocol):
    """重放驱动最小接口（hdc 真机 / 测试 Fake 双实现）。

    真机命令映射（HdcDeviceDriver）：
        foreground_bundle  hdc shell aa dump -l（解析前台 ability 所属包）
        ui_snapshot        hdc shell uitest dumpLayout -p <tmp> + file recv
        tap/input_text     hdc shell uitest uiInput click/inputText
        key_back           hdc shell uitest uiInput keyEvent Back
        swipe              hdc shell uitest uiInput swipe
        force_stop         hdc shell aa force-stop <bundle>
        start_ability      hdc shell aa start -b <bundle> -a <ability>
        query_notification hdc shell anm dump（通知服务查询）
        file_exists        hdc shell ls <path>
        export_app_data    应用侧自检接口（见 implementation-guidelines-v4）
    """

    def foreground_bundle(self) -> str: ...

    def ui_snapshot(self) -> UiSnapshot: ...

    def locate(self, snapshot: UiSnapshot, target: str
               ) -> Optional[tuple]:
        """语义目标 → 中心坐标 (cx, cy)；找不到 → None。"""

    def tap(self, x: int, y: int) -> None: ...

    def input_text(self, x: int, y: int, text: str) -> None: ...

    def key_back(self) -> None: ...

    def swipe(self, x1: int, y1: int, x2: int, y2: int) -> None: ...

    def long_press(self, x: int, y: int) -> None: ...

    def force_stop(self, bundle: str) -> None: ...

    def start_ability(self, bundle: str, ability: str) -> None: ...

    def query_notification(self, key: str) -> QueryResult: ...

    def file_exists(self, device_path: str) -> QueryResult: ...

    def export_app_data(self, bundle: str) -> Optional[Dict[str, Any]]: ...


class HdcDeviceDriver:
    """hdc 真机驱动（接口完整实现；dump 解析细节留联调 TODO 标注）。

    无设备环境下 connect() 即抛 DriverUnavailable；重放层把它转译为
    PLATFORM_LIMITATION/流程错误，绝不伪造 PASS。
    """

    def __init__(self, hdc: str = "hdc", serial: str = "",
                 bundle: str = "", ability: str = "", settle: float = 1.5):
        self.hdc = hdc
        self.serial = serial
        self.bundle = bundle
        self.ability = ability
        self.settle = settle

    # ---- 基础执行 ----

    def _run(self, *args: str, timeout: int = 30) -> str:
        argv = [self.hdc]
        if self.serial:
            argv += ["-t", self.serial]
        argv += list(args)
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise DriverUnavailable(f"hdc failed: {exc}") from exc
        if proc.returncode != 0:
            raise DriverUnavailable(
                f"hdc exit {proc.returncode}: {' '.join(args[:6])}")
        return proc.stdout or ""

    def connect(self) -> None:
        # TODO(device-联调): 真机部署时确认 hdc list targets 含 serial。
        out = self._run("list", "targets")
        if "[Empty]" in out or not out.strip():
            raise DriverUnavailable("no hdc targets connected")

    # ---- 防伪：前台校验 ----

    def foreground_bundle(self) -> str:
        # D2(HOME-FULL-RUN1 回移植)：实测 `aa dump -l` 为 mission-list 格式：
        #   Mission ID #42  mission name #[#com.nevoit.cresto:entry:EntryAbility] ...
        #     bundle name [com.nevoit.cresto]
        #     state #FOREGROUND   app state #FOREGROUND
        # 解析：定位含 "state #FOREGROUND" 的 AbilityRecord 块，回溯取最近
        # "bundle name [xxx]"。找不到 → 空串（调用方 fail-closed）。
        out = self._run("shell", "aa", "dump", "-l")
        current_bundle = ""
        for line in out.splitlines():
            stripped = line.strip()
            match = re.search(r"bundle name \[([^\]]+)\]", stripped)
            if match:
                current_bundle = match.group(1)
                continue
            if "state #FOREGROUND" in stripped and current_bundle:
                return current_bundle
        return ""

    # ---- UI 快照 ----

    def ui_snapshot(self) -> UiSnapshot:
        remote = "/data/local/tmp/replay_ui.json"
        local = Path(remote).name
        # D7(HOME-FULL-RUN1 回移植)：dumpLayout 返回 ≠ 文件已落盘——recv 前
        # 等待 + 内容校验（坏文件/空文件重试一次；连续两次坏 → 抛
        # DriverUnavailable 走 fail-closed）
        raw = ""
        for _attempt in (1, 2):
            self._run("shell", "uitest", "dumpLayout", "-p", remote)
            time.sleep(0.8)
            try:
                self._run("file", "recv", remote, local)
            finally:
                self._run("shell", "rm", "-f", remote)
            try:
                raw = Path(local).read_text(encoding="utf-8",
                                            errors="replace")
            except OSError:
                raw = ""
            if "attributes" in raw and len(raw) > 200:
                break
            time.sleep(0.6)
        try:
            if not ("attributes" in raw and len(raw) > 200):
                raise DriverUnavailable(
                    "ui dump stale/empty after retries")
            return parse_ui_dump(raw)
        finally:
            Path(local).unlink(missing_ok=True)

    def locate(self, snapshot: UiSnapshot, target: str) -> Optional[tuple]:
        # TODO(device-联调): 从 dumpLayout JSON 的 bounds 属性取中心坐标；
        # 当前实现从 raw JSON 正则抽取目标文本节点的 bounds。
        return locate_bounds_center(snapshot.raw, target)

    # ---- 输入 ----

    def tap(self, x: int, y: int) -> None:
        self._run("shell", "uitest", "uiInput", "click", str(x), str(y))
        time.sleep(self.settle)

    def input_text(self, x: int, y: int, text: str) -> None:
        self._run("shell", "uitest", "uiInput", "inputText",
                  str(x), str(y), text)
        time.sleep(self.settle)

    def key_back(self) -> None:
        self._run("shell", "uitest", "uiInput", "keyEvent", "Back")
        time.sleep(self.settle)

    def swipe(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self._run("shell", "uitest", "uiInput", "swipe",
                  str(x1), str(y1), str(x2), str(y2))
        time.sleep(self.settle)

    def long_press(self, x: int, y: int) -> None:
        # D3(HOME-FULL-RUN1 回移植)：uitest uiInput longClick
        # （LongPressGesture 450ms 阈值）
        self._run("shell", "uitest", "uiInput", "longClick",
                  str(x), str(y))
        time.sleep(self.settle)

    # ---- 进程生命周期（persistence 重验） ----

    def force_stop(self, bundle: str) -> None:
        self._run("shell", "aa", "force-stop", bundle)

    def start_ability(self, bundle: str, ability: str) -> None:
        self._run("shell", "aa", "start", "-b", bundle, "-a", ability)
        time.sleep(self.settle * 2)  # 冷启动 settle（防伪：启动未完成不评估）

    # ---- 副作用查询 ----

    def query_notification(self, key: str) -> QueryResult:
        # TODO(device-联调): anm dump 输出格式联调；当前解析按通知标题/
        # 内容子串匹配（key 语义：通知包含的关键文本）。
        try:
            out = self._run("shell", "anm", "dump", "--recent")
        except DriverUnavailable:
            return QueryResult(False, False, "anm query unsupported")
        return QueryResult(True, key.lower() in out.lower(), "anm dump")

    def file_exists(self, device_path: str) -> QueryResult:
        try:
            out = self._run("shell", "ls", "-l", device_path)
        except DriverUnavailable:
            return QueryResult(False, False, "ls unsupported")
        return QueryResult(True, "No such file" not in out, "ls -l")

    def export_app_data(self, bundle: str) -> Optional[Dict[str, Any]]:
        """DebugSemanticProbe 独立探针通道（批次 2 #85，替代 replay-data.json
        自答——旧通道已删除）。

        探针由 Phase 3 scaffold 生成、哈希冻结（P4 实施者禁改），周期采样
        全部 data-contract 语义对象（未接线对象 → null）。双通道读取：
            A（主）hdc file recv 沙箱文件 semantic-probe.json
              （5557 模拟器实测物理路径：/data/app/el2/100/base/<bundle>/
               haps/entry/files/——Stage 模型 entry HAP 的 filesDir 映射；
               旧直挂路径 /files/ 一并探测兼容）；
            B（退化）hdc shell hilog -x 缓冲 dump + 本地过滤 tag
              SemanticProbe 的 SNAPSHOT 行取最后一条。
        两通道均失败 → None（data 断言 FAIL，fail-closed：探针缺失=实施
        缺陷，不降级、不放行）。
        """
        # 通道 A：沙箱文件（两个候选物理路径按实测优先级探测）
        base = f"/data/app/el2/100/base/{bundle}"
        candidates = (
            f"{base}/haps/entry/files/{PROBE_SNAPSHOT_FILENAME}",
            f"{base}/files/{PROBE_SNAPSHOT_FILENAME}",
        )
        local = PROBE_SNAPSHOT_FILENAME
        data: Optional[Dict[str, Any]] = None
        for remote in candidates:
            try:
                self._run("file", "recv", remote, local)
                loaded = json.loads(
                    Path(local).read_text(encoding="utf-8"))
            except (DriverUnavailable, OSError, json.JSONDecodeError):
                loaded = None
            finally:
                Path(local).unlink(missing_ok=True)
            if isinstance(loaded, dict):
                data = loaded
                break
        if data is not None:
            return data
        # 通道 B：hilog 缓冲抓取（文件被占用/未写入时的退化路径）
        try:
            out = self._run("shell", "hilog", "-x", timeout=20)
        except DriverUnavailable:
            return None
        for line in reversed(out.splitlines()):
            if PROBE_HILOG_TAG not in line:
                continue
            marker = line.find(PROBE_HILOG_SNAPSHOT_MARK)
            if marker < 0:
                continue
            payload = line[marker + len(PROBE_HILOG_SNAPSHOT_MARK):].strip()
            start = payload.find("{")
            if start < 0:
                continue
            try:
                fallback = json.loads(payload[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(fallback, dict):
                return fallback
        return None


# ============================================================================
# UI dump 解析（纯函数，可单测）
# ============================================================================

def parse_ui_dump(raw: str) -> UiSnapshot:
    """uitest dumpLayout JSON → 语义视图。

    容错树遍历：任意嵌套 {attributes:{...}, children:[...]}；提取非空
    text 与组件状态行（type/text/id/visible/enabled/checked）。
    坏 JSON → 空 texts/components + raw 保留（shows_text 仍有 raw 兜底）。
    """
    texts: List[str] = []
    components: List[Dict[str, str]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            attrs = node.get("attributes")
            if isinstance(attrs, dict):
                component = {
                    "type": str(attrs.get("type", "")),
                    "text": str(attrs.get("text", "")),
                    "id": str(attrs.get("id", "") or attrs.get("key", "")),
                    "visible": str(attrs.get("visible", "")),
                    "enabled": str(attrs.get("enabled", "")),
                    "checked": str(attrs.get("checked", "")),
                }
                if component["text"]:
                    texts.append(component["text"])
                components.append(component)
            children = node.get("children")
            if isinstance(children, list):
                for child in children:
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    try:
        data = json.loads(raw)
    except Exception:
        data = None
    if data is not None:
        walk(data)
    return UiSnapshot(raw, texts, components)


def _bounds_center(bounds: Any) -> Optional[tuple]:
    """D1(HOME-FULL-RUN1 回移植)：bounds → 中心坐标；兼容两种实测形态：
    - list [x1, y1, x2, y2]（规范形态）
    - 字符串 "[x1,y1][x2,y2]"（真机 dumpLayout 实测形态）
    无法解析 → None。"""
    if isinstance(bounds, list) and len(bounds) == 4:
        try:
            return ((int(bounds[0]) + int(bounds[2])) // 2,
                    (int(bounds[1]) + int(bounds[3])) // 2)
        except (TypeError, ValueError):
            return None
    if isinstance(bounds, str):
        match = re.match(
            r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
            bounds.strip())
        if match:
            x1, y1, x2, y2 = (int(match.group(i)) for i in range(1, 5))
            return ((x1 + x2) // 2, (y1 + y2) // 2)
    return None


def locate_bounds_center(raw: str, target: str) -> Optional[tuple]:
    """从 dump JSON 文本抽目标节点 bounds → 中心坐标（hdc 驱动用）。"""
    lowered = target.lower()
    try:
        data = json.loads(raw)
    except Exception:
        return None

    def walk(node: Any) -> Optional[tuple]:
        if isinstance(node, dict):
            attrs = node.get("attributes")
            if isinstance(attrs, dict):
                # D5(HOME-FULL-RUN1 回移植)：语义定位 = text 子串优先，
                # id/key 子串兜底（TextInput 等无 text 组件靠 id 定位；
                # 与 android 侧语义定位同构）
                text = str(attrs.get("text", ""))
                if text and lowered in text.lower():
                    center = _bounds_center(attrs.get("bounds"))
                    if center is not None:
                        return center
                node_id = str(attrs.get("id", "") or attrs.get("key", ""))
                if node_id and lowered in node_id.lower():
                    center = _bounds_center(attrs.get("bounds"))
                    if center is not None:
                        return center
            children = node.get("children")
            if isinstance(children, list):
                for child in children:
                    found = walk(child)
                    if found:
                        return found
        elif isinstance(node, list):
            for child in node:
                found = walk(child)
                if found:
                    return found
        return None

    return walk(data)


# ============================================================================
# 断言判定（纯函数；每类独立判定）
# ============================================================================

def evaluate_observable(assertion: Dict[str, str], snapshot: UiSnapshot
                        ) -> str:
    """observable 判定：text_visible / text_gone / component_state。
    value/target 缺失 → FAIL（断言残缺不是不适用，铁律不解释）。"""
    kind = (assertion.get("kind") or "").strip()
    value = (assertion.get("value") or "").strip()
    if kind == "text_visible":
        return PASS if value and snapshot.shows_text(value) else FAIL
    if kind == "text_gone":
        return PASS if value and not snapshot.shows_text(value) else FAIL
    if kind == "component_state":
        target = (assertion.get("target") or "").strip()
        attr = (assertion.get("attr") or "").strip()
        if not target or not attr or not value:
            return FAIL
        actual = snapshot.component_attr(target, attr)
        if actual is None:
            return FAIL
        return PASS if actual.lower() == value.lower() else FAIL
    return FAIL  # 未知 kind 已在分类层拉 manual；此处防御性 FAIL


def _data_object_matches(assertion: Dict[str, str],
                         data: Dict[str, Any]) -> bool:
    """data 断言语义比较（对象级，不比物理存储）：
    {"kind":"data_object","object":name,"op":equals|contains|exists|
     not_exists|gt|lt,"value":v}。object 缺失 → False。"""
    obj = (assertion.get("object") or "").strip()
    op = (assertion.get("op") or "equals").strip().lower()
    value = assertion.get("value")
    if not obj or obj not in data:
        return op == "not_exists"
    actual = data[obj]
    if op == "equals":
        return str(actual) == str(value)
    if op == "contains":
        return str(value) in str(actual)
    if op == "exists":
        return True
    if op == "not_exists":
        return False
    if op in ("gt", "lt"):
        try:
            number = float(actual)
            bound = float(value)
        except (TypeError, ValueError):
            return False
        return number > bound if op == "gt" else number < bound
    return False


def evaluate_data(assertion: Dict[str, str],
                  data: Optional[Dict[str, Any]]) -> str:
    """data 判定：语义对象快照比较。data=None（应用未提供自检接口）→
    FAIL（自检接口是实施者规约义务，缺失=实施缺陷，不降级、不放行）。"""
    if data is None:
        return FAIL
    return PASS if _data_object_matches(assertion, data) else FAIL


def evaluate_side_effect(assertion: Dict[str, str], driver: DeviceDriver
                         ) -> str:
    """side_effect 判定：
    - 查询能力表 manual 类（无公开 API）→ MANUAL_VERIFY_REQUIRED；
    - queryable 类：驱动查询 supported=False → PLATFORM_LIMITATION；
      查询成功按 expect 匹配 → PASS/FAIL；
    - 未知 kind → MANUAL_VERIFY_REQUIRED（保守进人工队列，不放行）。"""
    kind = (assertion.get("kind") or "").strip()
    queryability = SIDE_EFFECT_QUERYABILITY.get(kind)
    if queryability is None:
        return MANUAL
    if queryability == "manual":
        return MANUAL
    expect = (assertion.get("expect") or "present").strip().lower()
    try:
        if kind == "notification":
            result = driver.query_notification(assertion.get("key", ""))
        elif kind == "file_export":
            result = driver.file_exists(assertion.get("path", ""))
        else:
            return MANUAL
    except DriverUnavailable:
        return PLATFORM
    if not result.supported:
        return PLATFORM
    matched = result.matched
    wanted = expect != "absent"
    return PASS if matched == wanted else FAIL


def aggregate_verdict(verdicts: List[str]) -> str:
    """类内聚合：FAIL > MANUAL > PLATFORM > PASS > NA（空列表 → NA）。"""
    if not verdicts:
        return NA
    return sorted(verdicts, key=lambda v: _AGG_ORDER.get(v, 1))[0]


def replay_verdict_of(categories: Dict[str, str]) -> str:
    """四类结果 → replay_verdict（NOT_APPLICABLE 占多数时仍按最严非 NA
    判定；全部 NA → NA——BC 无可验断言的定性交 Gate 4，不越权）。"""
    values = [v for v in categories.values() if v != NA]
    if not values:
        return NA
    return sorted(values, key=lambda v: _AGG_ORDER.get(v, 1))[0]


# ============================================================================
# 重放执行（driver 注入；防伪三件套）
# ============================================================================

def stable_ui_snapshot(driver: DeviceDriver, tries: int = 3,
                       interval: float = 1.0) -> UiSnapshot:
    """稳定性双确认：两次快照 texts 集合一致才采用（动画中间态防护；
    Phase 2 采集器实战）。不一致重试；穷尽 → 返回最后一次（判定照常，
    fail-closed 由断言结果体现）。"""
    last = driver.ui_snapshot()
    for _ in range(max(0, tries - 1)):
        time.sleep(interval)
        current = driver.ui_snapshot()
        if set(current.texts) == set(last.texts):
            return current
        last = current
    return last


def check_foreground(driver: DeviceDriver, bundle: str, ops_log: List[str],
                     phase: str) -> bool:
    """foreground 校验铁律（伪访问防护）：前台非目标 bundle → 记日志返回
    False（调用方按步骤失败处理 → fail-closed）。"""
    try:
        foreground = driver.foreground_bundle()
    except DriverUnavailable:
        ops_log.append(f"[fg:{phase}] foreground query unavailable")
        return False
    ok = bundle in foreground if foreground else False
    ops_log.append(f"[fg:{phase}] foreground={foreground or '(empty)'} "
                   f"target={bundle} -> {'ok' if ok else 'LEFT'}")
    return ok


# ============================================================================
# prepare 阶段（批次 2 #85，借 LLMigrate preparation 思想；与批次 1
# Android 侧 gmi_runtime execute_behavior_chain 的 prepare 段同构）：
#   reset（冷复位到干净态）→ prepare（BC.prepare_steps 可选列）→
#   verify（pre_state token 校验，token 提取共享 gmi_runtime 实现）
# ============================================================================

def verify_precondition_snapshot(pre_state: str,
                                 snapshot: UiSnapshot) -> tuple:
    """precondition 记录校验（纯函数，可单测）。返回 (ok, note)。

    token 提取共享 android 侧 gmi_runtime.parse_pre_state_tokens（同一
    pre_state 文本双端提取出同一 token 集）；可见性判定用鸿蒙
    UiSnapshot.shows_text（与 android _xml_shows 同构：大小写不敏感子串
    + raw 兜底）。提取不出 token → ok=True（仅记录口径，不阻塞链——
    自然语言 pre_state 无法机械校验时不误伤，note 记录原文供人审）。
    """
    tokens = parse_pre_state_tokens(pre_state)
    if not tokens:
        return True, ("pre_state recorded (no machine-checkable tokens): "
                      f"{(pre_state or '(empty)')[:60]}")
    missing = [t for t in tokens if not snapshot.shows_text(t)]
    if missing:
        return False, ("precondition unverified, missing on page: "
                       + ";".join(missing[:4])
                       + f" (tokens: {';'.join(tokens[:4])})")
    return True, "precondition verified: " + ";".join(tokens[:4])


def cold_reset_app(driver: DeviceDriver, bundle: str, ability: str,
                   ops_log: List[str]) -> bool:
    """D9 式链前冷复位（HOME-FULL-RUN1 实测：外部 shell 的 force-stop 偶发
    静默失败，链间状态泄漏互染——上一链可能停留在 sheet/详情页等中间态）。

    force-stop → 停顿 → start（自带冷启动 settle）→ 前台校验 → 稳定快照。
    返回 False = 复位失败（应用未回到前台，调用方按 RESET_FAILED 处理）。
    """
    ops_log.append(f"[reset] cold reset: force-stop {bundle} -> start")
    try:
        driver.force_stop(bundle)
        time.sleep(1.5)
        driver.start_ability(bundle, ability)
    except DriverUnavailable as exc:
        ops_log.append(f"[reset] driver unavailable: {exc}")
        return False
    if not check_foreground(driver, bundle, ops_log, "reset"):
        ops_log.append("[reset] foreground check failed after cold reset")
        return False
    try:
        stable_ui_snapshot(driver)
    except DriverUnavailable as exc:
        ops_log.append(f"[reset] post-reset snapshot failed: {exc}")
        return False
    return True


def execute_prepare_steps(driver: DeviceDriver,
                          prep_steps: List[Dict[str, str]],
                          bundle: str, ops_log: List[str]) -> bool:
    """执行 BC.prepare_steps（与 android 侧同 schema：action/target/value）。

    失败即中止并返回 False（按 precondition 失败处理重试）。与
    execute_steps 分离：prepare 的目标是为 precondition 铺路，不承担
    结果断言义务；步骤日志前缀 prep#。"""
    total = len(prep_steps)
    snapshot = stable_ui_snapshot(driver)
    for index, step in enumerate(prep_steps):
        action = (step.get("action") or "").strip().lower()
        target = (step.get("target") or "").strip()
        value = (step.get("value") or "").strip()
        if action == "tap":
            position = locate_with_refresh(driver, snapshot, target,
                                           ops_log)
            if position is None:
                ops_log.append(f"[prep {index + 1}/{total}] target not "
                               f"found: '{target}'")
                return False
            driver.tap(*position)
            note = f"tap '{target}'"
        elif action == "input":
            if not target or not value:
                ops_log.append(f"[prep {index + 1}/{total}] input missing "
                               "target/value")
                return False
            position = locate_with_refresh(driver, snapshot, target,
                                           ops_log)
            if position is None:
                ops_log.append(f"[prep {index + 1}/{total}] input field "
                               f"not found: '{target}'")
                return False
            driver.input_text(position[0], position[1], value)
            note = f"input '{target}' <- '{value[:24]}'"
        elif action == "back":
            driver.key_back()
            note = "back"
        else:
            ops_log.append(f"[prep {index + 1}/{total}] unsupported "
                           f"prepare action: '{action}'")
            return False
        snapshot = stable_ui_snapshot(driver)
        if not check_foreground(driver, bundle, ops_log,
                                f"prep {index + 1}"):
            ops_log.append(f"[prep {index + 1}/{total}] ABORT: foreground "
                           "left target app after " + action)
            return False
        ops_log.append(f"[prep {index + 1}/{total}] ok: {note}")
    return True


def establish_precondition(bc: Dict[str, str], driver: DeviceDriver,
                           bundle: str, ability: str,
                           ops_log: List[str]) -> tuple:
    """每条 BC 重放前的 prepare 阶段（批次 2 #85）。

    流程（两次尝试）：cold reset → prepare_steps（若有）→ verify
    precondition（pre_state token 校验）；verify 失败 → 冷复位重试一次 →
    仍失败 → PRECONDITION_FAILED（终态，归人工/MANUAL_TAKEOVER 队列）。
    返回 (precondition_status, note)。status ∈ PRECONDITION_STATUSES。
    """
    segments = extract_segments(bc)
    pre_state = segments.get("precondition", "")
    prep_steps = parse_json_column(bc.get("prepare_steps", ""))
    if prep_steps:
        ops_log.append(f"[prepare] prepare_steps declared: "
                       f"{len(prep_steps)} step(s)")
    last_fail = "precondition not established"
    for attempt in (1, 2):
        if attempt == 2:
            ops_log.append("[prepare] retry #1: cold restart + re-prepare")
        if not cold_reset_app(driver, bundle, ability, ops_log):
            last_fail = "cold reset failed (app not foreground after start)"
            continue
        if not execute_prepare_steps(driver, prep_steps, bundle, ops_log):
            # execute_prepare_steps 已把细节写 ops_log；这里保留失败摘要
            last_fail = f"prepare_steps interrupted (attempt {attempt})"
            continue
        snapshot = stable_ui_snapshot(driver)
        ok, note = verify_precondition_snapshot(pre_state, snapshot)
        ops_log.append(f"[prepare] {note}")
        if ok:
            return "ESTABLISHED", note
        last_fail = note
    return PRECONDITION_FAILED, last_fail


def locate_with_refresh(driver: DeviceDriver, snapshot: UiSnapshot,
                        target: str, ops_log: List[str]) -> Optional[tuple]:
    """D6+D8(HOME-FULL-RUN1 回移植)：定位失败时刷新快照重试——冷启动后
    列表渲染晚于首次稳定判定（空态也稳定），单快照会漏掉后渲染组件；
    数据等待（2s/3s 两档）后再刷新定位。"""
    position = driver.locate(snapshot, target)
    if position is None:
        for wait in (2.0, 3.0):
            time.sleep(wait)
            refreshed = stable_ui_snapshot(driver)
            position = driver.locate(refreshed, target)
            if position is not None:
                ops_log.append(f"[retry] locate '{target}' ok after "
                               f"{wait}s data-wait refresh")
                return position
    return position


def execute_steps(driver: DeviceDriver, steps: List[Dict[str, str]],
                  bundle: str, ops_log: List[str]) -> tuple:
    """执行 harmony_steps（同意图异路径：只负责把操作走通，不解释结果）。

    返回 (steps_ok, steps_total)。步骤失败即中止（链式操作依赖前序状态）。
    每步后 foreground 校验（防伪）。D3/D4 扩展：long_press 与 swipe 的
    target 语义定位（direction=left/right 基于目标行中心水平滑 400px）。
    """
    total = len(steps)
    snapshot = stable_ui_snapshot(driver)

    for index, step in enumerate(steps):
        action = (step.get("action") or "").strip().lower()
        target = (step.get("target") or "").strip()
        value = (step.get("value") or "").strip()
        note = ""
        if action == "tap":
            position = locate_with_refresh(driver, snapshot, target,
                                           ops_log)
            if position is None:
                ops_log.append(f"[step {index + 1}/{total}] tap target not "
                               f"found: '{target}'")
                return index, total
            driver.tap(*position)
            note = f"tap '{target}' @({position[0]},{position[1]})"
        elif action == "input":
            if not target or not value:
                ops_log.append(f"[step {index + 1}/{total}] input missing "
                               "target/value")
                return index, total
            position = locate_with_refresh(driver, snapshot, target,
                                           ops_log)
            if position is None:
                ops_log.append(f"[step {index + 1}/{total}] input field not "
                               f"found: '{target}'")
                return index, total
            driver.input_text(position[0], position[1], value)
            note = f"input '{target}' <- '{value[:24]}'"
        elif action == "back":
            driver.key_back()
            note = "back"
        elif action == "long_press":
            # D3：uitest uiInput longClick（LongPressGesture 450ms 阈值）
            position = locate_with_refresh(driver, snapshot, target,
                                           ops_log)
            if position is None:
                ops_log.append(f"[step {index + 1}/{total}] long_press "
                               f"target not found: '{target}'")
                return index, total
            driver.long_press(*position)
            note = f"long_press '{target}' @({position[0]},{position[1]})"
        elif action == "swipe":
            # D4：支持 target 语义定位 + direction（left/right），基于目标
            # 行 bounds 中心水平滑 400px；绝对坐标 start/end 原语义保留。
            direction = (step.get("direction") or "").strip().lower()
            if direction and target:
                position = locate_with_refresh(driver, snapshot, target,
                                               ops_log)
                if position is None:
                    ops_log.append(f"[step {index + 1}/{total}] swipe "
                                   f"target not found: '{target}'")
                    return index, total
                cx, cy = position
                span = 400
                if direction == "left":
                    x1, y1, x2, y2 = (cx + span // 2, cy,
                                      cx - span // 2, cy)
                elif direction == "right":
                    x1, y1, x2, y2 = (cx - span // 2, cy,
                                      cx + span // 2, cy)
                else:
                    ops_log.append(f"[step {index + 1}/{total}] swipe bad "
                                   f"direction: '{direction}'")
                    return index, total
            else:
                try:
                    start = step.get("start", "")
                    end = step.get("end", "")
                    x1, y1 = [int(p) for p in str(start).split(",")]
                    x2, y2 = [int(p) for p in str(end).split(",")]
                except (ValueError, AttributeError):
                    ops_log.append(f"[step {index + 1}/{total}] swipe bad "
                                   "start/end")
                    return index, total
            driver.swipe(x1, y1, x2, y2)
            note = f"swipe ({x1},{y1})->({x2},{y2})"
        else:
            ops_log.append(f"[step {index + 1}/{total}] unsupported action: "
                           f"'{action}'")
            return index, total
        snapshot = stable_ui_snapshot(driver)
        if not check_foreground(driver, bundle, ops_log,
                                f"step {index + 1}"):
            ops_log.append(f"[step {index + 1}/{total}] ABORT: foreground "
                           "left target app after " + action)
            return index, total
        ops_log.append(f"[step {index + 1}/{total}] ok: {note}")
    return total, total


def replay_bc(bc: Dict[str, str], steps: List[Dict[str, str]],
              driver: DeviceDriver, bundle: str, ability: str,
              evidence_root: Path) -> Dict[str, Any]:
    """单条 BC 重放（四类独立判定 + 证据落盘）。

    流程（批次 2 #85 加入 prepare 阶段）：prepare（reset 冷复位 →
    prepare_steps → verify precondition，两次尝试）→ steps 执行 →
    after 快照 → observable/data 判定 →（有 persistence 义务时）
    force-stop + start + 前台校验 → restart 快照 → persistence 重验 →
    side_effect 逐条查询 → 聚合。PRECONDITION_FAILED → 四类一律 MANUAL
    （人工裁决队列），replay_verdict=PRECONDITION_FAILED（终态）。
    """
    bc_id = (bc.get("bc_id") or "").strip()
    feature_id = (bc.get("feature_id") or "").strip()
    segments = extract_segments(bc)
    assertions = parse_json_column(bc.get("result_assertions", ""))
    buckets = classify_assertions(assertions)
    obligations = assertion_obligations(segments, buckets)

    ev_dir = evidence_root / "chains" / bc_id / "replay"
    ev_dir.mkdir(parents=True, exist_ok=True)
    ops_log: List[str] = [f"[bc] {bc_id} feature={feature_id} bundle={bundle}"]

    row: Dict[str, Any] = dict.fromkeys(REPLAY_CSV_FIELDS, "")
    row.update({"bc_id": bc_id, "feature_id": feature_id,
                "verify_mode": "RUNTIME",
                "precondition_status": "",
                "steps_total": len(steps), "steps_ok": 0,
                "evidence_dir": str(ev_dir)})
    detail: Dict[str, Any] = {"bc_id": bc_id, "feature_id": feature_id,
                              "categories": {}, "assertions": []}

    # 步骤中断 → 四类一律 FAIL（fail-closed，铁律）
    broken_columns = (json_column_broken(bc.get("result_assertions", "")) or
                      json_column_broken(bc.get("harmony_steps", "")) or
                      json_column_broken(bc.get("prepare_steps", "")))

    steps_ok, steps_total = 0, len(steps)
    ui_after: Optional[UiSnapshot] = None
    data_after: Optional[Dict[str, Any]] = None
    ui_restart: Optional[UiSnapshot] = None
    data_restart: Optional[Dict[str, Any]] = None
    precondition_failed = False
    precondition_note = ""

    if broken_columns:
        ops_log.append("[abort] broken JSON column (result_assertions/"
                       "harmony_steps/prepare_steps) -> FAIL all")
        steps_ok = -1
        row["precondition_status"] = "SKIPPED_BROKEN_COLUMN"
    elif not steps:
        ops_log.append("[abort] no harmony_steps recorded -> FAIL all")
        steps_ok = -1
        row["precondition_status"] = "SKIPPED_NO_STEPS"
    else:
        # ---- prepare 阶段（批次 2 #85）：reset → prepare_steps → verify ----
        precondition_status, precondition_note = establish_precondition(
            bc, driver, bundle, ability, ops_log)
        row["precondition_status"] = precondition_status
        if precondition_status == PRECONDITION_FAILED:
            precondition_failed = True
            ops_log.append("[abort] PRECONDITION_FAILED after retry -> "
                           "four classes MANUAL (human queue)")
        else:
            steps_ok, steps_total = execute_steps(driver, steps, bundle,
                                                  ops_log)
            if steps_ok < steps_total:
                ops_log.append(f"[abort] steps interrupted at "
                               f"{steps_ok}/{steps_total} -> FAIL all")
            else:
                ui_after = stable_ui_snapshot(driver)
                data_after = driver.export_app_data(bundle)

    row["steps_ok"] = max(steps_ok, 0)
    interrupted = (steps_ok != steps_total or broken_columns or not steps
                   or precondition_failed)

    # ---- observable ----
    if obligations["observable"] == "none":
        row["observable_result"] = NA
    elif precondition_failed:
        row["observable_result"] = MANUAL
    elif interrupted or ui_after is None:
        row["observable_result"] = FAIL
    elif obligations["observable"] == "manual":
        row["observable_result"] = MANUAL
    else:
        verdicts = []
        for assertion in buckets["observable"]:
            verdict = evaluate_observable(assertion, ui_after)
            verdicts.append(verdict)
            detail["assertions"].append(
                {"category": "observable", **assertion, "verdict": verdict})
        row["observable_result"] = aggregate_verdict(verdicts) \
            if verdicts else MANUAL

    # ---- data ----
    if obligations["data"] == "none":
        row["data_result"] = NA
    elif precondition_failed:
        row["data_result"] = MANUAL
    elif interrupted:
        row["data_result"] = FAIL
    elif obligations["data"] == "manual":
        row["data_result"] = MANUAL
    else:
        verdicts = []
        for assertion in buckets["data"]:
            verdict = evaluate_data(assertion, data_after)
            verdicts.append(verdict)
            detail["assertions"].append(
                {"category": "data", **assertion, "verdict": verdict})
        row["data_result"] = aggregate_verdict(verdicts) \
            if verdicts else MANUAL

    # ---- persistence（义务 = persistence 段非空或有 persist 断言） ----
    needs_restart = (obligations["persistence"] != "none")
    if not needs_restart:
        row["persistence_result"] = NA
    elif precondition_failed:
        row["persistence_result"] = MANUAL
    elif interrupted:
        row["persistence_result"] = FAIL
    else:
        driver.force_stop(bundle)
        driver.start_ability(bundle, ability)
        if not check_foreground(driver, bundle, ops_log, "restart"):
            row["persistence_result"] = FAIL
            ops_log.append("[restart] foreground check failed after restart")
        else:
            ui_restart = stable_ui_snapshot(driver)
            data_restart = driver.export_app_data(bundle)
            verdicts = []
            # 显式 persist 断言（restart 快照/数据上评估）
            for assertion in buckets["persistence"]:
                kind = assertion.get("kind", "")
                if kind == "persist_after_restart":
                    verdict = evaluate_observable(
                        {"kind": "text_visible",
                         "value": assertion.get("value", "")}, ui_restart)
                else:  # persist_data_after_restart
                    verdict = evaluate_data(assertion, data_restart)
                verdicts.append(verdict)
                detail["assertions"].append(
                    {"category": "persistence", **assertion,
                     "verdict": verdict})
            # 隐式义务：重启后重验正向 observable/data 断言（任务定义：
            # persistence = 杀进程重启后断言重验 observable/data）
            for assertion in buckets["observable"]:
                if assertion.get("kind") == "text_visible":
                    verdict = evaluate_observable(assertion, ui_restart)
                    verdicts.append(verdict)
                    detail["assertions"].append(
                        {"category": "persistence", "kind": "recheck_"
                         + assertion.get("kind", ""),
                         "value": assertion.get("value", ""),
                         "verdict": verdict})
            for assertion in buckets["data"]:
                verdict = evaluate_data(assertion, data_restart)
                verdicts.append(verdict)
                detail["assertions"].append(
                    {"category": "persistence", "kind": "recheck_data_object",
                     "object": assertion.get("object", ""),
                     "verdict": verdict})
            if not verdicts:
                row["persistence_result"] = MANUAL  # 段非空无断言（manual 义务）
            else:
                row["persistence_result"] = aggregate_verdict(verdicts)

    # ---- side_effect ----
    if obligations["side_effect"] == "none":
        row["side_effect_result"] = NA
    elif precondition_failed:
        row["side_effect_result"] = MANUAL
    elif interrupted:
        row["side_effect_result"] = FAIL
    elif obligations["side_effect"] == "manual":
        row["side_effect_result"] = MANUAL
    else:
        verdicts = []
        side_queries: List[Dict[str, Any]] = []
        for assertion in buckets["side_effect"]:
            verdict = evaluate_side_effect(assertion, driver)
            verdicts.append(verdict)
            side_queries.append({**assertion, "verdict": verdict})
            detail["assertions"].append(
                {"category": "side_effect", **assertion, "verdict": verdict})
        row["side_effect_result"] = aggregate_verdict(verdicts) \
            if verdicts else MANUAL
        atomic_json(ev_dir / "side-effects.json", side_queries)

    # ---- 聚合与证据 ----
    # 铁律补充：操作序列未走通（中断/无记录/坏 JSON 列）→ 总判定强制
    # FAIL（fail-closed），四类单元格仍按各自义务独立记录
    # （有义务 → FAIL，无义务 → NOT_APPLICABLE），供 Gate 4 分列消费。
    # 批次 2 #85：precondition 建立失败 → 总判定 PRECONDITION_FAILED
    # （终态，归人工/MANUAL_TAKEOVER 队列，不算功能 FAIL）。
    categories = {key: row[f"{key}_result"]
                  for key in ("observable", "data", "persistence",
                              "side_effect")}
    row["replay_verdict"] = (PRECONDITION_FAILED if precondition_failed
                             else FAIL if interrupted
                             else replay_verdict_of(categories))
    fails = [f"{cat}={verdict}" for cat, verdict in categories.items()
             if verdict == FAIL]
    if interrupted:
        if precondition_failed:
            reason = "precondition_failed"
        elif not steps and not broken_columns:
            reason = "no_harmony_steps"
        elif broken_columns:
            reason = "broken_json_column"
        else:
            reason = (f"steps_interrupted_at_{max(steps_ok, 0)}_of_"
                      f"{steps_total}")
        fails.append(reason)
    row["fail_reason"] = "; ".join(fails) if fails else ""
    if interrupted:
        if precondition_failed:
            row["note"] = f"PRECONDITION_FAILED: {precondition_note[:120]}"
        elif broken_columns:
            row["note"] = ("broken JSON column (result_assertions/"
                           "harmony_steps/prepare_steps)")
        elif not steps:
            row["note"] = "no harmony_steps recorded for this BC"
        else:
            row["note"] = (f"steps interrupted at {max(steps_ok, 0)}/"
                           f"{steps_total}")
    detail["categories"] = categories
    detail["replay_verdict"] = row["replay_verdict"]
    detail["precondition_status"] = row["precondition_status"]

    (ev_dir / "operations.log").write_text(
        "\n".join(ops_log) + "\n", encoding="utf-8")
    for name, snapshot in (("ui-after.json", ui_after),
                           ("ui-restart.json", ui_restart)):
        if snapshot is not None:
            atomic_json(ev_dir / name,
                        {"texts": snapshot.texts,
                         "components": snapshot.components})
    for name, data in (("data-after.json", data_after),
                       ("data-restart.json", data_restart)):
        if data is not None:
            atomic_json(ev_dir / name, data)
    atomic_json(ev_dir / "assertions.json", detail)
    return row


def replay_workspace(bc_path: Path, harmony_steps_path: Optional[Path],
                     feature_map_path: Optional[Path], driver: DeviceDriver,
                     bundle: str, ability: str, out_path: Path,
                     evidence_root: Path) -> Dict[str, Any]:
    """整批重放入口（CLI/测试共用）：选择 → 逐条重放 → 写 CSV。
    unmapped feature（feature_id 不在 map）→ 该 BC 整行 FAIL
    （fail-closed：映射缺失是上游缺陷，重放器不静默吞）。"""
    bc_rows = load_bc_rows(bc_path)
    steps_map = load_harmony_steps(harmony_steps_path, bc_rows)
    feature_map = load_feature_map(feature_map_path)
    selection = select_replay_bcs(bc_rows, feature_map)

    rows: List[Dict[str, Any]] = []
    for bc in selection["selected"]:
        bc_id = (bc.get("bc_id") or "").strip()
        steps = steps_map.get(bc_id, [])
        rows.append(replay_bc(bc, steps, driver, bundle, ability,
                              evidence_root))
    for bc in selection["skipped"]:
        row: Dict[str, Any] = dict.fromkeys(REPLAY_CSV_FIELDS, "")
        row.update({
            "bc_id": (bc.get("bc_id") or "").strip(),
            "feature_id": (bc.get("feature_id") or "").strip(),
            "verify_mode": "SOURCE_CONFIRM",
            "observable_result": NA, "data_result": NA,
            "persistence_result": NA, "side_effect_result": NA,
            "replay_verdict": SKIPPED,
            "note": bc.get("_skip_reason", ""),
            "evidence_dir": "",
        })
        rows.append(row)
    for bc in selection["unmapped"]:
        row = dict.fromkeys(REPLAY_CSV_FIELDS, "")
        row.update({
            "bc_id": (bc.get("bc_id") or "").strip(),
            "feature_id": (bc.get("feature_id") or "").strip(),
            "verify_mode": "UNMAPPED",
            "observable_result": FAIL, "data_result": FAIL,
            "persistence_result": FAIL, "side_effect_result": FAIL,
            "replay_verdict": FAIL,
            "fail_reason": "feature_id not in feature-map (fail-closed)",
            "evidence_dir": "",
        })
        rows.append(row)

    rows.sort(key=lambda r: r["bc_id"])
    write_csv(out_path, REPLAY_CSV_FIELDS, rows)
    stats = {
        "total": len(rows),
        "replayed": len(selection["selected"]),
        "skipped": len(selection["skipped"]),
        "unmapped": len(selection["unmapped"]),
        "fallback_selection": selection["fallback"],
        "fail": sum(1 for r in rows if r["replay_verdict"] == FAIL),
        "manual": sum(1 for r in rows if r["replay_verdict"] == MANUAL),
        "platform": sum(1 for r in rows if r["replay_verdict"] == PLATFORM),
        "pass": sum(1 for r in rows if r["replay_verdict"] == PASS),
        "precondition_failed": sum(
            1 for r in rows
            if r["replay_verdict"] == PRECONDITION_FAILED),
        "missing_steps": sorted(
            (bc.get("bc_id", "") for bc in selection["selected"]
             if not steps_map.get((bc.get("bc_id") or "").strip(), []))),
    }
    return {"rows": rows, "stats": stats}


# ============================================================================
# validate 子命令（Gate 4 / I 代理可先行消费的只读格式检查）
# ============================================================================

def validate_results(path: Path) -> List[str]:
    """校验 replay-results.csv：列齐全、枚举合法、BC 唯一、FAIL 行必有
    fail_reason、evidence_dir 引用存在（非 SKIPPED 行）。返回错误清单。"""
    errors: List[str] = []
    try:
        rows = read_csv(path)
    except ValueError as exc:
        return [str(exc)]
    if not rows:
        return ["replay-results.csv is empty"]
    header = set(rows[0].keys())
    missing = [f for f in REPLAY_CSV_FIELDS if f not in header]
    if missing:
        errors.append(f"missing columns: {','.join(missing)}")
    seen: set = set()
    for row in rows:
        bc_id = (row.get("bc_id") or "").strip()
        if not bc_id:
            errors.append("row without bc_id")
            continue
        if bc_id in seen:
            errors.append(f"duplicate bc_id: {bc_id}")
        seen.add(bc_id)
        verdict = (row.get("replay_verdict") or "").strip()
        if verdict not in REPLAY_VERDICTS:
            errors.append(f"{bc_id}: bad replay_verdict {verdict!r}")
        for category in ("observable", "data", "persistence", "side_effect"):
            value = (row.get(f"{category}_result") or "").strip()
            if value not in CATEGORY_VERDICTS:
                errors.append(f"{bc_id}: bad {category}_result {value!r}")
        # 批次 2 #85：precondition_status 列（重放行必填且合法；SKIPPED/
        # UNMAPPED 行不要求）
        pre_status = (row.get("precondition_status") or "").strip()
        verify_mode = (row.get("verify_mode") or "").strip()
        if verify_mode == "RUNTIME" and verdict not in (SKIPPED,):
            if pre_status not in PRECONDITION_STATUSES:
                errors.append(
                    f"{bc_id}: bad precondition_status {pre_status!r} "
                    f"(expected one of {PRECONDITION_STATUSES})")
        if verdict == PRECONDITION_FAILED and pre_status != PRECONDITION_FAILED:
            errors.append(
                f"{bc_id}: replay_verdict=PRECONDITION_FAILED but "
                f"precondition_status={pre_status!r}")
        if verdict == FAIL and not (row.get("fail_reason") or "").strip():
            errors.append(f"{bc_id}: FAIL without fail_reason")
        # UNMAPPED 行（上游映射缺陷）与 SKIPPED 行不产生重放证据目录
        if verdict not in (SKIPPED,) and \
                (row.get("verify_mode") or "").strip() != "UNMAPPED":
            evidence = (row.get("evidence_dir") or "").strip()
            if not evidence:
                errors.append(f"{bc_id}: missing evidence_dir")
            elif not Path(evidence).exists():
                errors.append(f"{bc_id}: evidence_dir not found: {evidence}")
    return errors


# ============================================================================
# CLI
# ============================================================================

def build_driver(args: argparse.Namespace) -> DeviceDriver:
    driver = HdcDeviceDriver(hdc=args.hdc, serial=args.device,
                             bundle=args.bundle, ability=args.ability)
    driver.connect()
    return driver


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="replayer.py",
        description="Phase 4 v4 七段断言重放器（Harmony 侧，只验结果断言）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_replay = sub.add_parser(
        "replay", help="执行重放（需设备；--dry-run 仅校验输入与分类）")
    p_replay.add_argument("--bc", required=True, type=Path)
    p_replay.add_argument("--harmony-steps", type=Path, default=None)
    p_replay.add_argument("--feature-map", type=Path, default=None)
    p_replay.add_argument("--bundle", required=True)
    p_replay.add_argument("--ability", default="EntryAbility")
    p_replay.add_argument("--device", default="")
    p_replay.add_argument("--hdc", default="hdc")
    p_replay.add_argument("--out", required=True, type=Path,
                          help="replay-results.csv 输出路径")
    p_replay.add_argument("--evidence-root", type=Path, default=None,
                          help="证据根目录（缺省 <out>/../evidence）")
    p_replay.add_argument("--bc-filter", default="",
                          help="只重放指定 bc_id（逗号分隔；调试用）")
    p_replay.add_argument("--dry-run", action="store_true",
                          help="无设备：仅校验输入/断言分类/义务计算")

    p_validate = sub.add_parser("validate", help="校验 replay-results.csv")
    p_validate.add_argument("--results", required=True, type=Path)

    args = parser.parse_args(argv)

    if args.command == "validate":
        errors = validate_results(args.results)
        if errors:
            for error in errors:
                print(f"[replayer] ERROR {error}", file=sys.stderr)
            return 1
        print("[replayer] validate ok")
        return 0

    bc_rows = load_bc_rows(args.bc)
    if args.bc_filter:
        wanted = {b.strip() for b in args.bc_filter.split(",") if b.strip()}
        bc_rows = [r for r in bc_rows
                   if (r.get("bc_id") or "").strip() in wanted]
    steps_map = load_harmony_steps(args.harmony_steps, bc_rows)
    feature_map = load_feature_map(args.feature_map)
    selection = select_replay_bcs(bc_rows, feature_map)
    buckets_summary = {}
    for bc in selection["selected"]:
        segments = extract_segments(bc)
        buckets = classify_assertions(
            parse_json_column(bc.get("result_assertions", "")))
        buckets_summary[(bc.get("bc_id") or "").strip()] = {
            "obligations": assertion_obligations(segments, buckets),
            "assertion_counts": {k: len(v) for k, v in buckets.items()},
            "has_steps": bool(steps_map.get(
                (bc.get("bc_id") or "").strip(), [])),
            "prepare_steps": len(parse_json_column(
                bc.get("prepare_steps", ""))),
            "pre_state_tokens": parse_pre_state_tokens(
                segments.get("precondition", "")),
        }

    if args.dry_run:
        report = {
            "selected": [bc.get("bc_id") for bc in selection["selected"]],
            "skipped": [bc.get("bc_id") for bc in selection["skipped"]],
            "unmapped": [bc.get("bc_id") for bc in selection["unmapped"]],
            "fallback_selection": selection["fallback"],
            "plan": buckets_summary,
        }
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0

    evidence_root = args.evidence_root or args.out.parent / "evidence"
    try:
        driver = build_driver(args)
    except DriverUnavailable as exc:
        print(f"[replayer] device unavailable: {exc}", file=sys.stderr)
        return 2
    result = replay_workspace(
        args.bc, args.harmony_steps, args.feature_map, driver,
        args.bundle, args.ability, args.out, evidence_root)
    print(json.dumps({"stats": result["stats"],
                      "out": str(args.out)}, ensure_ascii=False, indent=1))
    return 0 if result["stats"]["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())