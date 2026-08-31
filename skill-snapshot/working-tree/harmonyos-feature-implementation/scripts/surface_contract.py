#!/usr/bin/env python3
"""Phase 4 v4（feature-semantic 范式）薄表工具：surface-contract.csv。

功能承载面薄表（每 included feature 一行）：
    feature_id / surfaces / entry_reachable / nav_pattern /
    native_impl_check / notes

native_impl_check（用户修正 5）：静态扫描 ArkTS 源码，判定是否**明显
用错平台模式**——只判模式用错，不做像素比较。规则 = 自造信号命中
且原生反证缺失 → FAIL：

    R1 bottom-bar-diy     手搓底栏（非 Tabs）：底部容器 + tab 切换状态 +
                          ≥2 个 onClick，同文件无 Tabs/TabContent
    R2 nav-stack-diy      自绘导航栈（非 Navigation）：页面栈状态名 +
                          条件渲染切页，且工程级无 Navigation/NavPathStack
    R3 dialog-diy         自造弹层底盘（非 CustomDialog/bindSheet）：
                          弹层可见状态 + Stack/overlay/position/offset +
                          半透明遮罩信号，同文件无原生弹层 API
    R4 switch-diy         自绘开关（非 Toggle）：开关状态 + Circle 滑块 +
                          animateTo，同文件无 Toggle
    R5 picker-diy         自造选择器（非 Select/DatePicker/TimePicker/
                          TextPicker）：picker 命名 + List 滚轮模拟，同文件
                          无原生 Picker 族
    R6 back-diy           自造返回（非系统返回/NavPathStack）：边缘滑动手势
                          自管返回，且工程级无 Navigation（有 Navigation 时
                          降为 WARNING，不 FAIL——避免误伤正常手势）

豁免登记（implementation-guidelines-v4 规约）：自定义实现只有在原生
组件不能表达需求时才允许，必须在**源码注释** `// native-exception(<rule>):`
<理由> 登记（机器可查、可审计），或在生成后于 notes 列人工补记；
有代码级豁免标记的文件不触发对应规则 FAIL，记 exempted note。

entry_reachable：surface 承载面注册证据（Phase 3 surface-plan.json 的
route/modal/none 三态 + 工程注册事实：main_pages.json 页面路径或
surface_id 出现在 ArkTS 源码）。container 为透明宿主（无自有入口），
按 transparent 计 PASS。

nav_pattern：记录性字段——feature surfaces 的 kind 签名 + 工程级
Tabs/Navigation 使用证据（如 "page+sheet[tabs+navigation]"）。

子命令：
    generate  生成 surface-contract.csv（--feature-map 必需；
              --surface-plan 可选，缺省按工程源码降级判定）
    check     校验已有 surface-contract.csv：每 included feature 恰好一行
              且 entry_reachable / native_impl_check 全 PASS（Gate 4 前置
              只读检查，供 I 代理消费）；枚举/一致性非法即报错。
    fidelity  生成 visual-fidelity.csv（Gate 4 第 6 条输入）：鸿蒙
              dumpLayout 快照 vs Phase 2 visual-memory 基准的结构
              对比三指标（text_overlap / depth_delta / key_elements）
              + 色板辅线 hue_distance；行级 verdict PASS / VISUAL_GAP /
              NO_BASELINE / NO_DUMP。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from _common import read_csv, write_csv

SURFACE_CONTRACT_FIELDS = [
    "feature_id", "surfaces", "entry_reachable", "nav_pattern",
    "native_impl_check", "notes",
]

ENTRY_VERDICTS = ("PASS", "FAIL")
NATIVE_VERDICTS = ("PASS", "FAIL")

# surface kind → nav_pattern token（container 透明不产 token）
KIND_TOKENS = {
    "page": "page", "sheet": "sheet", "dialog": "dialog",
    "menu": "menu", "settings": "page",
}
TRANSPARENT_KINDS = frozenset({"container", "reusable-component"})
MODAL_KINDS = frozenset({"sheet", "dialog", "menu"})

NATIVE_EXCEPTION_MARK = "native-exception"

# ============================================================================
# native_impl_check 静态扫描规则（信号 + 原生反证；多信号同文件命中才 FAIL）
# ============================================================================


class NativeRule:
    """一条「明显用错平台模式」规则：signals 全组命中 + 反证缺失 → FAIL。"""

    def __init__(self, rule_id: str, name: str, signals: List[str],
                 absence: List[str], project_absence: Optional[List[str]] = None,
                 warning_only: bool = False, min_onclick: int = 0):
        self.rule_id = rule_id
        self.name = name
        self.signals = [re.compile(p, re.IGNORECASE) for p in signals]
        self.absence = [re.compile(p, re.IGNORECASE) for p in absence]
        # 工程级反证（任一文件出现即整体豁免该规则）
        self.project_absence = ([re.compile(p, re.IGNORECASE)
                                 for p in project_absence]
                                if project_absence else [])
        self.warning_only = warning_only
        self.min_onclick = min_onclick

    def check_file(self, content: str) -> Optional[str]:
        """单文件判定：返回 None=不触发 / 'FAIL' / 'WARNING'。"""
        if NATIVE_EXCEPTION_MARK.lower() in content.lower():
            return None  # 代码级豁免登记（含任何 native-exception 注释）
        for pattern in self.signals:
            if not pattern.search(content):
                return None
        if self.min_onclick and \
                len(re.findall(r"onClick", content)) < self.min_onclick:
            return None
        for pattern in self.absence:
            if pattern.search(content):
                return None  # 原生反证存在 → 该文件用了原生模式
        return "WARNING" if self.warning_only else "FAIL"

    def project_clears(self, all_contents: List[str]) -> bool:
        """工程级原生反证：任一文件出现即豁免（如 R2/R6 的 Navigation）。"""
        return any(p.search(text) for text in all_contents for p in
                   self.project_absence)


NATIVE_RULES: List[NativeRule] = [
    NativeRule(
        "R1", "bottom-bar-diy(手搓底栏,非Tabs)",
        signals=[r"\b(Row|Flex)\s*\(", r"currentTab|tabIndex|currentIndex|"
                                       r"selectedIndex|activeTab"],
        absence=[r"\bTabs\s*\(", r"\bTabContent\s*\(", r"barPosition"],
        min_onclick=2,
    ),
    NativeRule(
        "R2", "nav-stack-diy(自绘导航栈,非Navigation)",
        signals=[r"pageStack|navStack|routeStack|currentPage|screenStack",
                 r"if\s*\(\s*this\."],
        absence=[r"\bNavigation\s*\(", r"NavPathStack", r"navDestination"],
        project_absence=[r"\bNavigation\s*\(", r"NavPathStack"],
        # 工程任何地方用了 Navigation → 本文件只记 WARNING（状态命名可能
        # 只是巧合，如面包屑 currentPage）；工程级完全没有原生导航才 FAIL
        warning_only=True,
    ),
    NativeRule(
        "R3", "dialog-diy(自造弹层底盘,非CustomDialog/bindSheet)",
        signals=[r"sheetVisible|dialogVisible|showSheet|showDialog|"
                 r"maskVisible|isShowDialog|bottomSheet",
                 r"\bStack\s*\(|\.overlay\s*\(|\.position\s*\(|\.offset\s*\(",
                 r"opacity\s*\(|#[0-9a-f]{8}\b"],
        absence=[r"@CustomDialog|CustomDialog\s*\(", r"bindSheet",
                 r"bindContentCover", r"promptAction", r"AlertDialog",
                 r"ActionSheet", r"showToast"],
    ),
    NativeRule(
        "R4", "switch-diy(自绘开关,非Toggle)",
        signals=[r"switchOn|isToggled|toggleState|switchValue",
                 r"\bCircle\s*\(", r"animateTo"],
        absence=[r"\bToggle\s*\(", r"ToggleType"],
    ),
    NativeRule(
        "R5", "picker-diy(自造选择器,非Select/Picker族)",
        signals=[r"customPicker|wheelPicker|scrollPicker|pickerList",
                 r"\bList\s*\("],
        absence=[r"\bSelect\s*\(", r"DatePicker", r"TimePicker",
                 r"TextPicker", r"\bMenu\s*\("],
    ),
    NativeRule(
        "R6", "back-diy(自造返回,非系统返回/NavPathStack)",
        signals=[r"PanGesture", r"edgeBack|swipeBack|manualBack"],
        absence=[r"NavPathStack"],
        project_absence=[r"\bNavigation\s*\(", r"NavPathStack"],
        warning_only=True,  # 手势用途广泛，仅工程级无 Navigation 时升级 FAIL
    ),
]


def collect_arkts_sources(project: Path) -> Dict[str, str]:
    """收集工程 ArkTS 源码（entry/src/main/ets 下 **/*.ets）。"""
    root = project / "entry" / "src" / "main" / "ets"
    if not root.exists():
        root = project  # 扁平 fixture 兼容（直接给源码目录）
    sources: Dict[str, str] = {}
    for path in sorted(root.rglob("*.ets")):
        try:
            sources[str(path.relative_to(project))] = \
                path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return sources


def scan_native_impl(sources: Dict[str, str]) -> Dict[str, Any]:
    """工程级扫描：逐规则逐文件判定。

    返回 {"verdict": PASS|FAIL, "findings": [{"rule","name","file","level"}],
    "warnings": [...], "exempted": [file...]}。
    R6 warning_only：工程级无 Navigation/NavPathStack 时升级为 FAIL
    （此时整个工程都绕开了原生导航，属于明显模式用错）。
    """
    contents = list(sources.values())
    findings: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    exempted: List[str] = []
    for rule in NATIVE_RULES:
        project_native = rule.project_clears(contents)
        for rel, content in sources.items():
            level = rule.check_file(content)
            if level is None:
                if NATIVE_EXCEPTION_MARK.lower() in content.lower():
                    exempted.append(rel)
                continue
            if level == "WARNING":
                if not project_native:
                    level = "FAIL"  # 工程级反证缺失 → 升级
                else:
                    warnings.append({"rule": rule.rule_id,
                                     "name": rule.name, "file": rel})
                    continue
            findings.append({"rule": rule.rule_id, "name": rule.name,
                             "file": rel, "level": level})
    verdict = "FAIL" if any(f["level"] == "FAIL" for f in findings) else "PASS"
    return {"verdict": verdict, "findings": findings, "warnings": warnings,
            "exempted": sorted(set(exempted))}


def native_notes(scan: Dict[str, Any]) -> str:
    """扫描结果 → notes 摘要（R1:file;R3:file / WARNING:... / exempted:...）。"""
    parts = [f"{f['rule']}:{f['file']}" for f in scan["findings"]
             if f["level"] == "FAIL"]
    parts += [f"WARN-{w['rule']}:{w['file']}" for w in scan["warnings"]]
    parts += [f"exempted:{f}" for f in scan["exempted"]]
    return ";".join(parts)


# ============================================================================
# visual-fidelity（Gate 4 第 6 条支撑）：结构对比法 + 色板辅线
#
# 用户需求："UI 方面可以有差距但是不能差距太大" → 最小机器可判机制：
# 鸿蒙侧 uitest dumpLayout 的 UI 树 vs Phase 2 visual-memory 的基准
# ui-tree 摘要，三指标判定（阈值常量可配）：
#     text_overlap   可见文本集合重合度 ≥ 0.6（子串包含、大小写不敏感）
#     depth_delta    组件层级深度差 ≤ 2 层（树最大深度差的绝对值）
#     key_elements   关键交互元素存在性（底部导航/主按钮/列表结构）全在
# 色板对照为辅线：主题色 hue 环形距离仅记录（宽容差默认 60°），不参与
# verdict——允许原生化带来的取色差异。
#
# 行级 verdict：PASS / VISUAL_GAP（任一可判指标越阈）/ NO_BASELINE
# （Phase 2 基准缺失——不惩罚实现侧）/ NO_DUMP（实现侧证据缺失）。
# Gate 4 第 6 条消费：RUNTIME feature 的宿主 surface 必须 PASS；
# VISUAL_GAP / NO_DUMP → "差距太大/证据缺失" FAIL。
# ============================================================================

VISUAL_FIDELITY_FIELDS = [
    "surface_id", "feature_id", "text_overlap", "depth_delta",
    "key_elements_hit", "key_elements_total", "missing_key_elements",
    "hue_distance", "verdict", "notes",
]
VISUAL_FIDELITY_VERDICTS = ("PASS", "VISUAL_GAP", "NO_BASELINE", "NO_DUMP")

# 默认阈值（CLI 可覆盖；Gate 4 消费方与此处保持同源常量）
DEFAULT_MIN_TEXT_OVERLAP = 0.6
DEFAULT_MAX_DEPTH_DELTA = 2
DEFAULT_MAX_HUE_DISTANCE = 60  # 辅线宽容差（度），仅记录性

# visual-memory 防御性字段别名（#75 接口约定：以 surface_id/ui-tree 摘要/
# 色板为主名，别名兜底；正式 schema 由 Leader 统一后收敛）
_MEMORY_SURFACE_ID_KEYS = ("surface_id", "id")
_MEMORY_TREE_KEYS = ("ui_tree", "uiTree", "tree")
_MEMORY_TEXTS_KEYS = ("visible_texts", "texts")
_MEMORY_TYPES_KEYS = ("component_types", "types")
_MEMORY_DEPTH_KEYS = ("depth", "max_depth", "ui_tree_depth")
_MEMORY_KEYS_KEYS = ("key_elements", "anchors", "key_interactive_elements")
_MEMORY_PALETTE_KEYS = ("palette", "colors", "theme_palette")


def _first_value(mapping: Any, keys: tuple) -> Any:
    """防御性取值：按别名序列取第一个存在且非空的字段。"""
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value:
            return value
    return None


def normalize_text(value: str) -> str:
    """文本规范化：去首尾空白 + 压内部连续空白（比较前统一）。"""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _texts_overlap(base_texts: List[str], dump_texts: List[str]) -> Optional[float]:
    """基准文本集合在 dump 侧的重合度（None = 基准为空不可判）。

    命中定义：规范化后大小写不敏感的**双向子串包含**——基准 '新建待办'
    命中 dump '新建待办 按钮'；dump '首页 Tab' 也命中基准 '首页'（两侧
    各自可能拼合了相邻文本，包含式比全等更宽容）。
    分母 = 基准文本数（基准是 Phase 2 冻结的还原义务来源）。
    """
    base = [normalize_text(t) for t in base_texts if normalize_text(t)]
    if not base:
        return None
    dumped = [normalize_text(t).lower() for t in dump_texts
              if normalize_text(t)]
    hits = 0
    for text in base:
        lowered = text.lower()
        if any(lowered in dump_text or dump_text in lowered
               for dump_text in dumped):
            hits += 1
    return hits / len(base)


def parse_dump_tree(raw: str) -> Dict[str, Any]:
    """uitest dumpLayout JSON → {"texts", "types", "max_depth"}。

    容错树遍历（与 replayer.parse_ui_dump 同构）：任意嵌套
    {attributes:{...}, children:[...]}；坏 JSON → 空结果（NO_DUMP 判级）。
    """
    texts: List[str] = []
    types: List[str] = []

    def walk(node: Any, depth: int) -> int:
        max_depth = depth
        if isinstance(node, dict):
            attrs = node.get("attributes")
            if isinstance(attrs, dict):
                component_type = str(attrs.get("type", "") or "")
                text = str(attrs.get("text", "") or "")
                if component_type:
                    types.append(component_type)
                if text:
                    texts.append(text)
            children = node.get("children")
            if isinstance(children, list):
                for child in children:
                    max_depth = max(max_depth, walk(child, depth + 1))
        elif isinstance(node, list):
            for child in node:
                max_depth = max(max_depth, walk(child, depth))
        return max_depth

    try:
        data = json.loads(raw) if raw else None
    except (ValueError, TypeError):
        data = None
    max_depth = walk(data, 0) if data is not None else 0
    return {"texts": texts, "types": types, "max_depth": max_depth,
            "has_nodes": bool(texts or types)}


def _key_element_hit(element: Any, dump: Dict[str, Any]) -> bool:
    """关键交互元素存在性判定。

    支持三种声明（visual-memory 侧可混用）：
        {"type": "Tabs"}          组件类型匹配（大小写不敏感）
        {"text": "新建"}          可见文本匹配（子串、大小写不敏感）
        "@Tabs" / "新建"          字符串：@ 前缀 = 类型，否则 = 文本
    dict 同时给 type/text 时任一命中即算在。
    """
    lowered_types = {t.lower() for t in dump["types"]}
    lowered_texts = [normalize_text(t).lower() for t in dump["texts"]
                     if normalize_text(t)]
    if isinstance(element, dict):
        wanted_type = normalize_text(str(element.get("type") or ""))
        wanted_text = normalize_text(str(element.get("text") or ""))
        if wanted_type and wanted_type.lower() in lowered_types:
            return True
        if wanted_text:
            return any(wanted_text.lower() in text or text in wanted_text.lower()
                       for text in lowered_texts)
        return False
    token = normalize_text(str(element or ""))
    if not token:
        return False
    if token.startswith("@"):
        return token[1:].lower() in lowered_types
    lowered = token.lower()
    return any(lowered in text or text in lowered for text in lowered_texts)


def _hex_hue(color: str) -> Optional[float]:
    """'#RRGGBB' / '#AARRGGBB' → HSV hue（度）；坏值 → None。"""
    token = normalize_text(color).lstrip("#")
    if len(token) == 8:
        token = token[2:]  # 丢 alpha
    if len(token) != 6:
        return None
    try:
        r = int(token[0:2], 16) / 255.0
        g = int(token[2:4], 16) / 255.0
        b = int(token[4:6], 16) / 255.0
    except ValueError:
        return None
    max_c, min_c = max(r, g, b), min(r, g, b)
    if max_c == min_c:
        return 0.0  # 灰色无色相，取 0
    delta = max_c - min_c
    if max_c == r:
        hue = 60.0 * (((g - b) / delta) % 6)
    elif max_c == g:
        hue = 60.0 * (((b - r) / delta) + 2)
    else:
        hue = 60.0 * (((r - g) / delta) + 4)
    return hue


def _hue_distance(base_palette: List[str], impl_palette: List[str]
                  ) -> Optional[int]:
    """两色板间最小 hue 环形距离（度）；任一侧无有效色 → None。

    辅线指标：宽通道（两侧各取全部有效色求最小环形距离），只记录不判级。
    """
    base_hues = [h for h in (_hex_hue(c) for c in base_palette)
                 if h is not None]
    impl_hues = [h for h in (_hex_hue(c) for c in impl_palette)
                 if h is not None]
    if not base_hues or not impl_hues:
        return None
    best = 360.0
    for b_hue in base_hues:
        for i_hue in impl_hues:
            diff = abs(b_hue - i_hue) % 360.0
            best = min(best, diff, 360.0 - diff)
    return round(best)


def compute_visual_fidelity(dump_raw: str, baseline: Dict[str, Any],
                            impl_palette: Optional[List[str]] = None,
                            min_text_overlap: float = DEFAULT_MIN_TEXT_OVERLAP,
                            max_depth_delta: int = DEFAULT_MAX_DEPTH_DELTA
                            ) -> Dict[str, Any]:
    """单 surface 视觉保真度计算（结构对比三指标 + 色板辅线）。

    baseline（防御性归一后的基准）: {"visible_texts","component_types",
    "depth","key_elements","palette"}，字段可缺（缺 = 该指标不可判）。
    返回 {"verdict","text_overlap","depth_delta","key_elements_hit",
    "key_elements_total","missing_key_elements","hue_distance","notes"}。
    """
    dump = parse_dump_tree(dump_raw or "")
    base_texts = [normalize_text(str(t)) for t in baseline.get("visible_texts") or []]
    base_texts = [t for t in base_texts if t]
    base_depth = baseline.get("depth")
    base_depth = int(base_depth) if isinstance(base_depth, (int, float)) else None
    key_elements = [k for k in baseline.get("key_elements") or [] if k]
    base_palette = [str(c) for c in baseline.get("palette") or [] if c]

    # 基准三指标全缺 → 基准本身不可用（Phase 2 责任，不惩罚实现侧）
    if not base_texts and base_depth is None and not key_elements:
        return {"verdict": "NO_BASELINE", "text_overlap": None,
                "depth_delta": None, "key_elements_hit": 0,
                "key_elements_total": 0, "missing_key_elements": [],
                "hue_distance": None, "notes": "baseline ui-tree empty"}

    if not dump["has_nodes"]:
        return {"verdict": "NO_DUMP", "text_overlap": None,
                "depth_delta": None, "key_elements_hit": 0,
                "key_elements_total": len(key_elements),
                "missing_key_elements": [str(k) for k in key_elements],
                "hue_distance": _hue_distance(base_palette,
                                              impl_palette or []),
                "notes": "dump empty or unparsable"}

    reasons: List[str] = []

    overlap = _texts_overlap(base_texts, dump["texts"])
    if overlap is not None and overlap < min_text_overlap:
        reasons.append(
            f"text_overlap {overlap:.2f} < {min_text_overlap:.2f}")

    depth_delta: Optional[int] = None
    if base_depth is not None:
        depth_delta = abs(dump["max_depth"] - base_depth)
        if depth_delta > max_depth_delta:
            reasons.append(
                f"depth_delta {depth_delta} > {max_depth_delta}")

    missing: List[str] = []
    if key_elements:
        for element in key_elements:
            if not _key_element_hit(element, dump):
                missing.append(json.dumps(element, ensure_ascii=False)
                               if isinstance(element, dict) else str(element))
        if missing:
            reasons.append(f"missing key elements: {','.join(missing)}")

    hue = _hue_distance(base_palette, impl_palette or [])
    hue_note = ""
    if hue is not None and hue > DEFAULT_MAX_HUE_DISTANCE:
        hue_note = f"hue_distance {hue} > {DEFAULT_MAX_HUE_DISTANCE} (recorded only)"

    return {
        "verdict": "VISUAL_GAP" if reasons else "PASS",
        "text_overlap": round(overlap, 2) if overlap is not None else None,
        "depth_delta": depth_delta,
        "key_elements_hit": len(key_elements) - len(missing),
        "key_elements_total": len(key_elements),
        "missing_key_elements": missing,
        "hue_distance": hue,
        "notes": "; ".join(reasons + ([hue_note] if hue_note else [])),
    }


def load_visual_memory(path: Path) -> Dict[str, Dict[str, Any]]:
    """防御性读 visual-memory.json → {surface_id: 归一化基准}。

    兼容结构：{"surfaces": [{"surface_id"|"id", "ui_tree"|平铺, "palette"}]}
    （#75 的正式 schema 未冻结前按别名兜底；分歧由 Leader 统一）。
    坏文件 → ValueError（fail-closed，让生成方先修基准）。
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"visual-memory.json unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("visual-memory.json must be an object")
    raw_surfaces = data.get("surfaces")
    if not isinstance(raw_surfaces, list):
        raw_surfaces = [data] if "surface_id" in data or "id" in data else []

    baselines: Dict[str, Dict[str, Any]] = {}
    for raw in raw_surfaces:
        if not isinstance(raw, dict):
            continue
        surface_id = _first_value(raw, _MEMORY_SURFACE_ID_KEYS)
        surface_id = normalize_text(str(surface_id or ""))
        if not surface_id:
            continue
        tree = _first_value(raw, _MEMORY_TREE_KEYS)
        if not isinstance(tree, dict):
            tree = raw  # 平铺兜底（字段直接挂在 surface 对象上）
        baselines[surface_id] = {
            "visible_texts": [str(t) for t in
                              (_first_value(tree, _MEMORY_TEXTS_KEYS) or [])],
            "component_types": [str(t) for t in
                                (_first_value(tree, _MEMORY_TYPES_KEYS) or [])],
            "depth": _first_value(tree, _MEMORY_DEPTH_KEYS),
            "key_elements": list(_first_value(tree, _MEMORY_KEYS_KEYS) or []),
            "palette": [str(c) for c in
                        (_first_value(raw, _MEMORY_PALETTE_KEYS) or
                         _first_value(tree, _MEMORY_PALETTE_KEYS) or [])],
        }
    return baselines


def generate_visual_fidelity(feature_map_path: Path, memory_path: Path,
                             dumps_dir: Path, out_path: Path,
                             impl_palette: Optional[List[str]] = None,
                             min_text_overlap: float = DEFAULT_MIN_TEXT_OVERLAP,
                             max_depth_delta: int = DEFAULT_MAX_DEPTH_DELTA
                             ) -> Dict[str, Any]:
    """生成 visual-fidelity.csv：每基准 surface 一行（三指标 + verdict）。

    dumps_dir 约定：<surface_id>.json = 该 surface 重放时的 dumpLayout
    快照；缺文件 → NO_DUMP 行（实现侧证据缺失，Gate 4 消费时 FAIL）。
    """
    feature_map = load_feature_map(feature_map_path)
    baselines = load_visual_memory(memory_path)
    owner: Dict[str, str] = {}
    for feature in feature_map["features"]:
        for surface in feature["surfaces"]:
            if surface["id"]:
                owner.setdefault(surface["id"], feature["feature_id"])

    rows: List[Dict[str, str]] = []
    counts = {"PASS": 0, "VISUAL_GAP": 0, "NO_BASELINE": 0, "NO_DUMP": 0}
    for surface_id in sorted(baselines):
        baseline = baselines[surface_id]
        dump_path = dumps_dir / f"{surface_id}.json"
        dump_raw = ""
        dump_state = "ok"
        if dump_path.is_file():
            try:
                dump_raw = dump_path.read_text(encoding="utf-8",
                                               errors="replace")
            except OSError:
                dump_state = "unreadable"
        else:
            dump_state = "missing"
        result = compute_visual_fidelity(
            dump_raw, baseline, impl_palette,
            min_text_overlap, max_depth_delta)
        if dump_state != "ok" and result["verdict"] != "NO_BASELINE":
            result["verdict"] = "NO_DUMP"
            result["notes"] = (f"dump {dump_state}; " +
                               (result["notes"] or "")).strip("; ")
        counts[result["verdict"]] = counts.get(result["verdict"], 0) + 1

        def fmt(value: Any) -> str:
            return "n/a" if value is None else str(value)

        rows.append({
            "surface_id": surface_id,
            "feature_id": owner.get(surface_id, ""),
            "text_overlap": fmt(result["text_overlap"]),
            "depth_delta": fmt(result["depth_delta"]),
            "key_elements_hit": str(result["key_elements_hit"]),
            "key_elements_total": str(result["key_elements_total"]),
            "missing_key_elements": ";".join(result["missing_key_elements"]),
            "hue_distance": fmt(result["hue_distance"]),
            "verdict": result["verdict"],
            "notes": result["notes"][:200],
        })
    write_csv(out_path, VISUAL_FIDELITY_FIELDS, rows)
    return {"rows": len(rows), "counts": counts, "out": str(out_path)}


# ============================================================================
# feature-map / surface-plan 加载
# ============================================================================

def load_feature_map(path: Path) -> Dict[str, Any]:
    """读 feature-map.json（Phase 2 权威 schema；结构对齐 scaffold v3）。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("feature-map.json must be an object")
    features = data.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("feature-map.json features must be a non-empty array")
    coverage = data.get("coverage_gate") or {}
    included = [str(x) for x in (coverage.get("included") or [])]
    normalized: List[Dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError("feature-map features[] entries must be objects")
        fid = str(feature.get("feature_id") or "").strip()
        if not fid:
            raise ValueError("feature-map feature without feature_id")
        surfaces = []
        for surface in feature.get("surfaces") or []:
            if isinstance(surface, dict):
                surfaces.append({
                    "id": str(surface.get("id") or "").strip(),
                    "kind": str(surface.get("kind") or "").strip(),
                })
            else:
                surfaces.append({"id": str(surface).strip(), "kind": ""})
        normalized.append({"feature_id": fid, "surfaces": surfaces,
                           "verify_mode": str(
                               feature.get("verify_mode") or "").strip()})
    if included and sorted(included) != sorted(f["feature_id"]
                                               for f in normalized):
        raise ValueError("feature-map coverage_gate.included differs from "
                         "features[] ids")
    return {"features": normalized,
            "included": included or [f["feature_id"] for f in normalized]}


def load_surface_plan(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    """读 Phase 3 surface-plan.json（可选；缺省 None → 源码降级判定）。"""
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


# ============================================================================
# entry_reachable 判定（surface 承载面注册证据）
# ============================================================================

def registered_pages(project: Path) -> List[str]:
    """main_pages.json 注册的页面路径列表（HarmonyOS 路由注册表）。"""
    candidates = [
        project / "entry" / "src" / "main" / "resources" / "base" /
        "profile" / "main_pages.json",
        project / "src" / "main" / "resources" / "base" / "profile" /
        "main_pages.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, list):
            return [str(x) for x in data]
        if isinstance(data, dict) and isinstance(data.get("pages"), list):
            return [str(x) for x in data["pages"]]
    return []


def surface_registration_evidence(surface_id: str, kind: str, plan: Optional[
        Dict[str, Any]], pages: List[str], sources: Dict[str, str]
                                  ) -> Dict[str, Any]:
    """单 surface 承载证据 → {"verdict", "detail"}。

    优先级：surface-plan 三态（route/modal@host/none）→ 工程注册事实
    （main_pages.json 含 shell 路径 / surface_id 出现在源码 / modal 挂载
    API 存在）。container/reusable-component = 透明宿主 → PASS。
    无法建立任何证据 → FAIL（fail-closed，Gate 4 阻断项）。
    """
    if kind in TRANSPARENT_KINDS or kind == "":
        return {"verdict": "PASS", "detail": "transparent-host" if kind else
                f"unclassified:{surface_id}"}

    in_sources = any(surface_id in content for content in sources.values())
    detail_parts: List[str] = []

    if plan is not None:
        route = next((r for r in plan.get("routes", [])
                      if r.get("surface_id") == surface_id), None)
        modal = next((m for m in plan.get("modals", [])
                      if m.get("surface_id") == surface_id), None)
        if route is not None:
            # main_pages.json 注册路径相对 src（"pages/shells/X"），plan 的
            # shell_file 相对工程根（"entry/src/main/ets/pages/shells/X.ets"）
            # → 用 basename stem 匹配（注册名工程内唯一）
            stem = Path(str(route.get("shell_file") or "")).stem
            if stem and any(stem in page for page in pages):
                return {"verdict": "PASS",
                        "detail": f"route:{stem} registered in main_pages"}
            if in_sources:
                return {"verdict": "PASS",
                        "detail": f"route:{surface_id} present in sources"}
            detail_parts.append("route shell not registered")
        elif modal is not None:
            host = modal.get("host_surface_id")
            if not host:
                detail_parts.append("modal host UNRESOLVED")
            if in_sources:
                return {"verdict": "PASS",
                        "detail": f"modal@{host or '?'} present in sources"}
            has_mount_api = any(
                re.search(r"bindSheet|bindContentCover|@CustomDialog",
                          content) for content in sources.values())
            if host and has_mount_api:
                return {"verdict": "PASS",
                        "detail": f"modal@{host} mount api present"}
            detail_parts.append("modal mount evidence missing")
        elif in_sources:
            return {"verdict": "PASS", "detail": "present in sources"}
        else:
            detail_parts.append("not in surface-plan")

    # surface-plan 缺失 → 纯源码证据降级
    if in_sources:
        return {"verdict": "PASS", "detail": "present in sources"}
    if kind in MODAL_KINDS:
        has_mount_api = any(re.search(r"bindSheet|bindContentCover|"
                                      r"@CustomDialog", content)
                            for content in sources.values())
        if has_mount_api:
            return {"verdict": "PASS", "detail": "modal mount api present"}
    return {"verdict": "FAIL",
            "detail": "; ".join(detail_parts) or "no registration evidence"}


def nav_pattern_of(surfaces: List[Dict[str, str]], sources: Dict[str, str]
                   ) -> str:
    """记录性字段：kind 签名 + 工程级 Tabs/Navigation 证据。"""
    tokens = sorted({KIND_TOKENS[s["kind"]] for s in surfaces
                     if s["kind"] in KIND_TOKENS})
    joined = "+".join(tokens) if tokens else "none"
    evidence: List[str] = []
    all_text = "\n".join(sources.values())
    if re.search(r"\bTabs\s*\(", all_text):
        evidence.append("tabs")
    if re.search(r"\bNavigation\s*\(", all_text) or \
            "NavPathStack" in all_text:
        evidence.append("navigation")
    suffix = f"[{'+'.join(evidence)}]" if evidence else ""
    return joined + suffix


# ============================================================================
# generate / check
# ============================================================================

def generate_contract(feature_map_path: Path, project: Path,
                      out_path: Path,
                      surface_plan_path: Optional[Path] = None) -> Dict[str, Any]:
    """生成 surface-contract.csv：每 included feature 一行。"""
    feature_map = load_feature_map(feature_map_path)
    plan = load_surface_plan(surface_plan_path)
    sources = collect_arkts_sources(project)
    pages = registered_pages(project)
    scan = scan_native_impl(sources)

    rows: List[Dict[str, str]] = []
    per_surface_details: Dict[str, List[str]] = {}
    for feature in feature_map["features"]:
        fid = feature["feature_id"]
        surfaces = [s for s in feature["surfaces"] if s["id"]]
        verdicts = []
        details: List[str] = []
        for surface in surfaces:
            evidence = surface_registration_evidence(
                surface["id"], surface["kind"], plan, pages, sources)
            verdicts.append(evidence["verdict"])
            details.append(f"{surface['id']}:{evidence['detail']}")
        entry = "PASS" if verdicts and all(v == "PASS" for v in verdicts) \
            else "FAIL"
        if not surfaces:
            entry = "FAIL"
            details.append("no surfaces bound")
        per_surface_details[fid] = details
        rows.append({
            "feature_id": fid,
            "surfaces": ";".join(
                f"{s['id']}({s['kind']})" for s in surfaces),
            "entry_reachable": entry,
            "nav_pattern": nav_pattern_of(surfaces, sources),
            "native_impl_check": scan["verdict"],
            "notes": native_notes(scan),
        })
    rows.sort(key=lambda r: r["feature_id"])
    write_csv(out_path, SURFACE_CONTRACT_FIELDS, rows)
    return {"rows": rows, "scan": scan,
            "surface_details": per_surface_details,
            "source_count": len(sources)}


def check_contract(path: Path, feature_map_path: Optional[Path] = None
                   ) -> List[str]:
    """校验 surface-contract.csv（Gate 4 前置只读检查）：
    1. 列齐全、枚举合法、feature_id 唯一；
    2. included feature 恰好一行（缺行/多行/多写行都 FAIL）；
    3. entry_reachable 与 native_impl_check 全 PASS；
    4. surfaces 非空（有 bound surface 才有薄表意义）。
    """
    errors: List[str] = []
    try:
        rows = read_csv(path)
    except ValueError as exc:
        return [str(exc)]
    if not rows:
        return ["surface-contract.csv is empty"]
    header = set(rows[0].keys())
    missing = [f for f in SURFACE_CONTRACT_FIELDS if f not in header]
    if missing:
        errors.append(f"missing columns: {','.join(missing)}")

    seen: Dict[str, int] = {}
    for row in rows:
        fid = (row.get("feature_id") or "").strip()
        if not fid:
            errors.append("row without feature_id")
            continue
        seen[fid] = seen.get(fid, 0) + 1
        entry = (row.get("entry_reachable") or "").strip()
        if entry not in ENTRY_VERDICTS:
            errors.append(f"{fid}: bad entry_reachable {entry!r}")
        elif entry != "PASS":
            errors.append(f"{fid}: entry_reachable={entry}")
        native = (row.get("native_impl_check") or "").strip()
        if native not in NATIVE_VERDICTS:
            errors.append(f"{fid}: bad native_impl_check {native!r}")
        elif native != "PASS":
            errors.append(f"{fid}: native_impl_check={native} "
                          f"(notes: {(row.get('notes') or '').strip()[:80]})")
        if not (row.get("surfaces") or "").strip():
            errors.append(f"{fid}: empty surfaces")
        if not (row.get("nav_pattern") or "").strip():
            errors.append(f"{fid}: empty nav_pattern")
    for fid, count in seen.items():
        if count > 1:
            errors.append(f"duplicate feature_id rows: {fid} x{count}")

    if feature_map_path is not None:
        feature_map = load_feature_map(feature_map_path)
        for fid in feature_map["included"]:
            if fid not in seen:
                errors.append(f"included feature missing row: {fid}")
        for fid in seen:
            if fid not in feature_map["included"]:
                errors.append(f"extra feature row not included: {fid}")
    return errors


# ============================================================================
# CLI
# ============================================================================

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="surface_contract.py",
        description="Phase 4 v4 功能承载面薄表（surface-contract.csv）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate", help="生成 surface-contract.csv")
    p_gen.add_argument("--feature-map", required=True, type=Path)
    p_gen.add_argument("--project", required=True, type=Path,
                       help="HarmonyOS 工程根（entry/src/main/ets）")
    p_gen.add_argument("--surface-plan", type=Path, default=None,
                       help="Phase 3 surface-plan.json（可选，缺省源码降级）")
    p_gen.add_argument("--out", required=True, type=Path)

    p_check = sub.add_parser("check", help="校验 surface-contract.csv")
    p_check.add_argument("--contract", required=True, type=Path)
    p_check.add_argument("--feature-map", type=Path, default=None)

    p_fid = sub.add_parser(
        "fidelity", help="生成 visual-fidelity.csv（Gate 4 第 6 条输入）")
    p_fid.add_argument("--feature-map", required=True, type=Path)
    p_fid.add_argument("--visual-memory", required=True, type=Path,
                       help="Phase 2 visual-memory.json（#75 产出）")
    p_fid.add_argument("--dumps-dir", required=True, type=Path,
                       help="目录：<surface_id>.json 为重放 dumpLayout 快照")
    p_fid.add_argument("--impl-colors", default=None,
                       help="实现侧主题色列表（'#RRGGBB,#RRGGBB'，辅线可选）")
    p_fid.add_argument("--min-text-overlap", type=float,
                       default=DEFAULT_MIN_TEXT_OVERLAP)
    p_fid.add_argument("--max-depth-delta", type=int,
                       default=DEFAULT_MAX_DEPTH_DELTA)
    p_fid.add_argument("--out", required=True, type=Path)

    args = parser.parse_args(argv)

    if args.command == "generate":
        result = generate_contract(args.feature_map, args.project,
                                   args.out, args.surface_plan)
        summary = {
            "rows": len(result["rows"]),
            "source_count": result["source_count"],
            "native_impl_check": result["scan"]["verdict"],
            "findings": result["scan"]["findings"],
            "warnings": result["scan"]["warnings"],
            "entry_fail": [r["feature_id"] for r in result["rows"]
                           if r["entry_reachable"] == "FAIL"],
            "out": str(args.out),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0

    if args.command == "fidelity":
        impl_palette = [c.strip() for c in args.impl_colors.split(",")
                        if c.strip()] if args.impl_colors else None
        summary = generate_visual_fidelity(
            args.feature_map, args.visual_memory, args.dumps_dir,
            args.out, impl_palette, args.min_text_overlap,
            args.max_depth_delta)
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0

    errors = check_contract(args.contract, args.feature_map)
    if errors:
        for error in errors:
            print(f"[surface-contract] ERROR {error}", file=sys.stderr)
        return 1
    print("[surface-contract] check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())