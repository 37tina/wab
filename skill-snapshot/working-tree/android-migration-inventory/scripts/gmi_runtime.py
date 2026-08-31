# -*- coding: utf-8 -*-
"""gmi_runtime -- 运行时复核桥 v5.0（行为链范式）：BC 操作序列驱动 + 结果断言。

v5.0 --mode chain（新范式默认，第 6/7 步授权重写）：
  - 只对高风险行为跑真机，验证行为链（如"新增 X → 列表出现 X → 杀进程 →
    重启 → X 还在"）；证据重点是结果，不是截图数量；
  - 输入：feature-map.json（#38 改造A 产物，verify_mode=RUNTIME 的功能；
    features[].surfaces[].id = 正式 PAGE-ID）+ behavior-contracts.csv
    （可选扩展列 operation_steps / result_assertions，JSON-in-CSV；
    收敛式重构批次1（#81）：RUNTIME 链无 result_assertions →
    INVALID_CONTRACT（链不执行，直接标记）；全部断言 kind 未知 →
    UNSUPPORTED_ORACLE（归 GAP）。degraded CHAIN_PASS 路径已彻底删除：
    无断言/无可用 oracle 的链绝不能 PASS；
    收紧性修复（#88）：混合断言收紧——required 断言（默认全部）任一
    UNSUPPORTED → 整链 UNSUPPORTED_ORACLE（归 GAP）；仅断言 JSON 显式
    "optional": true 才允许 UNSUPPORTED 跳过（optional 只豁免
    UNSUPPORTED，不豁免 FAIL））；
  - 容器页/纯展示（verify_mode=SOURCE_CONFIRM）完全不跑——旧"45 页全部
    VISITED"死锁根治；
  - 证据瘦身：每条链 = 操作日志 + 断言判定 + before/after/restart 三点关键
    快照（按 bc_id 组织，不再按 page_id 采四件套+side-effects 大包）；
  - 输出 runtime-evidence/runtime-chains.csv（断言逐条 PASS/FAIL）供
    reconcile.py 对账（CONFIRMED/CONFLICT/SOURCE_CONFIRMED/GAP）；
  - 实战能力全部保留：跳板级联导航/图标兜底（小特征集 min_new_hits）/
    伪 ANR 防护（TTL 降频 + --compressed + ANR 预算 + 分类为采集器诱发）/
    稳定性双确认（_dump_stable for_evidence）/foreground∈pkg 防假访问/
    persistence = force-stop 重启后重验证（persist_after_restart 断言）。
  - --mode pages 保留旧页面模式（v4.2 VISITED 采集）兼容，不再是默认。

v4.2（2.1.1）：Page-ID 精确映射 + 证据索引（--mode pages 模式）。
2.1.1 修正（替代已证明失败的 page_token 字符串大小写归一化路线）：
  - behavior-contracts.csv.page_ref 直接使用 GMI 候选表正式 Page-ID；
  - runtime 候选通过候选 manifest（candidates/inventory.candidates.csv）中的
    明确映射（page_id <-> page symbol）解析 Page-ID；
  - 高影响过滤 = Page-ID 精确集合匹配；过滤集为空或恒 0 命中一律报错退出；
  - 任一 RUNTIME_REQUIRED BC 无法映射 Page-ID -> UNRESOLVED_PAGE_REF，退出非零，
    绝不静默切换全页模式后当作正式 PASS；
  - --no-high-impact-only 仅作调试开关保留（全页采集）。
新增产出 behavior-evidence-index.csv（每个 RUNTIME_REQUIRED BC 一行）：
  bc_id,page_ref,before_evidence_ref,after_evidence_ref,
  persistence_evidence_ref,side_effect_evidence_ref,audit_ref,status
证据齐备->COMPLETE；缺失按项记 MISSING_*，status 绝不为 COMPLETE。

用法：
  python gmi_runtime.py --project <root> --workspace <out> --package <pkg>
        [--activity MainActivity] [--serial emulator-5554]
        [--auto]                  # 级联自动路由（主页→入口标签）
        [--high-impact-only | --no-high-impact-only]  # 默认开启：只跑 RUNTIME_REQUIRED
        [--entry-labels "标签;标签2"]   # 主页入口（tab）标签；缺省读 navigation-relations
        [--full-bfs]              # 可选：全页 BFS 级联探索（默认关闭）
        [--all-screenshots]       # 可选：非高影响页也存 screenshot.png（默认只存 ui.xml）
        [--max-hops 80] [--stay 2.0] [--back-after]
        [--visits "文本:秒;文本2:2"]     # 或手工序列（保留，叠加高影响过滤）
        [--grant-perms]           # 自动 pm grant manifest 权限 + 重启
        [--compare]               # 截图差分 + UI 文本 Jaccard（截图缺失时只算文本）
        [--verbose]

产出 runtime-evidence/<page_id>/ui.xml (+ screenshot.png 仅高影响/显式开启时)
     evidence-index.csv (哈希) + runtime-gate.csv (VISITED/NOT_ENTERED)
     behavior-evidence-index.csv (BC 级证据索引，2.1.1)
     compare.csv (差分) + route-hints.csv (未达页路由建议)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess

import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def run(cmd: List[str], timeout: int = 40) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:  # noqa
        return f"__ERR__{e}"


def adb(serial: str, *args: str) -> str:
    return run(["adb", "-s", serial, *args])


def sha256f(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_csv(p: Path) -> List[Dict[str, str]]:
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(p: Path, fields: List[str], rows: List[Dict[str, Any]]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# --- 2.1.1 行为契约（behavior-contracts.csv）：Page-ID 精确映射 ---------------
_FORMAL_PAGE_ID = re.compile(r"^PAGE-[A-Z0-9]+(?:-[0-9A-F]{8})?$")


def load_behavior_contracts(workspace: Path) -> List[Dict[str, str]]:
    for p in (workspace / "behavior-contracts.csv",
              workspace / "candidates" / "behavior-contracts.csv"):
        if p.exists():
            return read_csv(p)
    return []


def build_page_id_map(cands_dir: Path) -> Dict[str, str]:
    """候选 manifest 映射：page symbol / 非正式引用 -> 正式 Page-ID。

    来源 candidates/inventory.candidates.csv（GMI 候选表）：
      page_id 为正式 Page-ID；expected_observable "<Symbol> displayed"
      提供符号列；符号为空时从 page_id 自身反推。
    """
    m: Dict[str, str] = {}
    for r in read_csv(cands_dir / "inventory.candidates.csv"):
        pid = (r.get("page_id") or "").strip()
        if not pid:
            continue
        m.setdefault(pid, pid)
        mo = re.match(r"^\s*(\S+)\s+displayed\s*$", r.get("expected_observable") or "")
        sym = mo.group(1) if mo else ""
        if not sym and pid.startswith("PAGE-"):
            body = pid[len("PAGE-"):]
            h = re.search(r"-[0-9A-F]{8}$", body)
            sym = body[:h.start()] if h else body
            sym = sym.capitalize()
        if sym:
            m.setdefault(sym, pid)
    return m


def resolve_page_ref(page_ref: str, page_id_map: Dict[str, str]) -> str:
    """把 BC page_ref 解析成正式 Page-ID；无法映射返回空串。
    精确匹配：正式 Page-ID 本身 / 候选表符号；不做任何大小写归一化猜测。"""
    v = (page_ref or "").strip()
    if not v:
        return ""
    return page_id_map.get(v, "")


def resolve_required_scope(bc_rows: List[Dict[str, str]],
                           page_id_map: Dict[str, str]) -> Dict[str, Any]:
    """RUNTIME_REQUIRED BC -> 正式 Page-ID 精确集合（+ 未解析条目清单）。"""
    pages: set = set()
    unresolved: List[Dict[str, str]] = []
    for r in bc_rows:
        if (r.get("evidence_class") or "").upper() != "RUNTIME_REQUIRED":
            continue
        ref = (r.get("page_ref") or "").strip()
        pid = resolve_page_ref(ref, page_id_map)
        if pid:
            pages.add(pid)
        else:
            unresolved.append({"bc_id": r.get("bc_id", ""), "page_ref": ref})
    return {"pages": pages, "unresolved": unresolved}


def required_bc_rows(bc_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [r for r in bc_rows
            if (r.get("evidence_class") or "").upper() == "RUNTIME_REQUIRED"]


def make_hi_predicate(scope: Optional[Dict[str, Any]], page_id_map: Dict[str, str]):
    """is_high_impact(name)：name（候选符号/标签）能否解析为正式 Page-ID 且属于
    RUNTIME_REQUIRED 精确集合。scope=None（过滤未激活/调试全页）时恒真。"""
    if scope is None:
        return lambda name: True
    want = scope["pages"]

    def _f(name: str) -> bool:
        pid = resolve_page_ref(name or "", page_id_map)
        return bool(pid) and pid in want
    return _f


BEHAVIOR_EVIDENCE_FIELDS = ["bc_id", "page_ref", "before_evidence_ref", "after_evidence_ref",
                            "persistence_evidence_ref", "side_effect_evidence_ref",
                            "audit_ref", "status"]


# --- 2.1.2 BC 级证据采集器（最小实现，补 behavior-evidence/<pid>/ 生成方缺口）-------
# 目录结构（与 build_behavior_evidence_index 消费口径一致）：
#   runtime-evidence/behavior-evidence/<正式Page-ID>/before/        进入态快照(复制主证据)
#   runtime-evidence/behavior-evidence/<正式Page-ID>/after/         操作后快照(no-op dwell)
#   runtime-evidence/behavior-evidence/<正式Page-ID>/persistence/   force-stop 重启后证据
#   runtime-evidence/behavior-evidence/<正式Page-ID>/side-effects/  dumpsys 外部副作用探针
#   runtime-evidence/behavior-evidence/<正式Page-ID>/capture-manifest.txt  采集元数据
# 导航与到达判定与 gmi_audit 重放口径同构（anchor_for + page-fields 标签），
# 并附加"新增特征"约束（命中特征必须不在点击前 UI 中）防止跨页特征污染产生假 VISITED。

def load_pf_label_map(ws: Path, strings: Dict[str, str]) -> Dict[str, List[str]]:
    """page-fields field_label(+strings 翻译) -> 页面特征集（与 gmi_audit 同构）。"""
    out: Dict[str, List[str]] = {}
    for r in read_csv(ws / "candidates" / "page-fields.candidates.csv"):
        sym = (r.get("page_symbol") or "").strip()
        lbl = (r.get("field_label") or "").strip()
        if not sym or not lbl:
            continue
        for l in dict.fromkeys([lbl, strings.get(lbl, "")]):
            if l and len(l) <= 40 and "%" not in l[:1]:
                out.setdefault(sym, []).append(l)
    return out


def build_pid_symbol_map(cands_dir: Path) -> Dict[str, str]:
    """正式 Page-ID -> 候选表正式符号（expected_observable 的 "<Symbol> displayed"）。"""
    out: Dict[str, str] = {}
    for r in read_csv(cands_dir / "inventory.candidates.csv"):
        pid = (r.get("page_id") or "").strip()
        if not pid:
            continue
        mo = re.match(r"^\s*(\S+)\s+displayed\s*$", r.get("expected_observable") or "")
        if mo and pid not in out:
            out[pid] = mo.group(1)
    return out


def page_audit_features(sym: str, strings: Dict[str, str],
                        pf_labels: Dict[str, List[str]]) -> List[str]:
    """审计特征全集（anchor_for + page-fields），与 gmi_audit 重放口径同构。"""
    feats = list(dict.fromkeys(anchor_for(sym, strings) + pf_labels.get(sym, [])))
    return [f for f in feats if f]


# --- 2.1.2 ANR 适配（任务 #34：检测恢复 + 放慢节奏 + 证据纯净 + ANR_BLOCKED）---
ANR_MARKERS = ("没有响应", "无响应", "isn't responding", "not responding")
ANR_WAIT_BUTTONS = ("等待", "WAIT", "Wait")
ANR_CLOSE_MARKERS = ("关闭应用", "关闭它", "CLOSE APP")
_TAP_SETTLE = 2.5   # tap 后等待（降低主线程压力）
_BACK_SETTLE = 2.0  # BACK 后等待
_ANR_EVENTS: List[str] = []  # 采集会话 ANR 事件（会话末写 anr-events.log）


def _log_anr(msg: str) -> None:
    # 任务 #35 定性：采集器诱发伪 ANR（uiautomator dump 导出 Compose 语义树
    # 阻塞主线程、arm 翻译模拟器放大，系统误判输入无响应）；app 实际正常
    # （用户现场确认）。不作为 app 动态风险/缺陷记录。
    _ANR_EVENTS.append(
        f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg} "
        "classification=collector-induced")


def _is_anr(xml: str) -> bool:
    return bool(xml) and any(m in xml for m in ANR_MARKERS)


def _wait_app_ready(serial: str, pkg: str, tries: int = 12) -> bool:
    """等待目标包回到前台（force-stop 重启/ANR 重建后；每轮 2.5s）。"""
    for _ in range(tries):
        time.sleep(2.5)
        fg = run(["adb", "-s", serial, "shell", "dumpsys", "activity",
                  "activities"], timeout=20)
        m = re.search(r"topResumedActivity=.*?u0 (\S+)", fg)
        if m and pkg in m.group(1):
            return True
    return False


def _handle_anr(serial: str, xml: str, pkg: str, act: str, ctx: str) -> bool:
    """ANR 对话框恢复：优先点'等待'；恢复失败 force-stop+am start 重建会话。
    返回是否恢复（恢复后调用方需重新 dump）。"""
    _log_anr(f"DETECT ctx={ctx} action=click-wait")
    tgt = None
    for b in ANR_WAIT_BUTTONS:
        tgt = find_click(xml, b)
        if tgt:
            break
    if tgt:
        adb(serial, "shell", "input", "tap", str(tgt["cx"]), str(tgt["cy"]))
        time.sleep(5.0)
        probe = _dump_xml(serial)
        if probe and not _is_anr(probe):
            _log_anr(f"RECOVER ctx={ctx} action=wait-click ok")
            return True
        _log_anr(f"RECOVER-FAIL ctx={ctx} action=wait-click")
    _log_anr(f"RECOVER ctx={ctx} action=force-stop-relaunch")
    adb(serial, "shell", "am", "force-stop", pkg)
    time.sleep(2.0)
    adb(serial, "shell", "am", "start", "-n", f"{pkg}/.{act}")
    ok = _wait_app_ready(serial, pkg)
    _log_anr(f"RECOVER ctx={ctx} action=relaunch ok={ok}")
    return ok


def _dump_stable(serial: str, pkg: str, act: str, ctx: str,
                 for_evidence: bool = False, anr_budget: List[int] = None) -> str:
    """ANR 感知 + 稳定性确认的 dump：
    - ANR 对话框：恢复（预算内，默认 2 次）后重 dump；超预算返回空串（上层记 ANR_BLOCKED）；
    - for_evidence=True（采证）：连续两次 dump 文本集合一致才返回（页面静止）；
      返回的 xml 保证不含 ANR 对话框（证据纯净性）。"""
    budget = anr_budget if anr_budget is not None else [2]
    for _ in range(3):
        xml = _dump_xml(serial, force=True, plain=for_evidence)
        if not xml:
            return ""
        if _is_anr(xml):
            if budget[0] <= 0:
                _log_anr(f"BLOCK ctx={ctx} budget-exhausted "
                         "(collector-induced pseudo-ANR)")
                return ""
            budget[0] -= 1
            if not _handle_anr(serial, xml, pkg, act, ctx):
                return ""
            continue
        if not for_evidence:
            return xml
        xml2 = _dump_xml(serial, force=True, plain=True)
        if xml2 and not _is_anr(xml2) and ui_text_set(xml) == ui_text_set(xml2):
            return xml
    return ""


def _reached_by_features(feats: List[str], before_text: str, after_text: str,
                         in_pkg: bool, launch_texts: set,
                         min_new_hits: int = 1) -> bool:
    """到达判定（fail-closed，与 audit 同构 + 新增特征约束）。
    - feats 非空：要求 in_pkg 且「新增命中特征数」(命中 after 且不在 before) >= min_new_hits；
      anchor 点击 min_new_hits=1，fallback 盲点点击 min_new_hits=2（烟测证明对话框等
      瞬态 UI 恰好新增命中 1 个宽泛 strings 词，须从严）；
    - feats 为空（如 HomeScreen，审计口径 page_features 恒命中）：
      要求 in_pkg 且 after 非空且与主页指纹相近（防止任意页误判为主页级页面）。"""
    if not in_pkg:
        return False
    if feats:
        new_hits = [f for f in feats if f in after_text and f not in before_text]
        return len(new_hits) >= max(1, min_new_hits)
    if not after_text or len(after_text) < 200:
        return False
    return jaccard(ui_text_set(after_text), launch_texts) >= 0.6


_DUMP_STATE: Dict[str, Any] = {"last_ts": 0.0, "cache_ts": 0.0,
                               "cache_xml": "", "compressed_ok": None}


def _dump_xml(serial: str, retries: int = 2, force: bool = False,
              plain: bool = False) -> str:
    """轻量稳健 UI dump（任务 #35 预防优先：降频 + 轻量模式）：
    - 2s TTL 缓存：非 force 且缓存新鲜时直接复用（减少对 app 主线程压测）；
    - 全量 dump 之间强制 >=1.5s 间隔；
    - plain=False 且 compressed 可用时优先 `uiautomator dump --compressed`
      （更轻量；首次探测，失败/空树则记不可用并全程 plain）；
      采证路径（for_evidence）应传 plain=True 保真；
    - rm 设备端旧文件防缓存；失败（含 'null root node'）pkill uiautomator 重试。"""
    now = time.time()
    if not force and _DUMP_STATE["cache_xml"] and \
            now - _DUMP_STATE["cache_ts"] < 2.0:
        return _DUMP_STATE["cache_xml"]
    gap = now - _DUMP_STATE["last_ts"]
    if gap < 1.5:
        time.sleep(1.5 - gap)
    fell_back_plain = False  # 本次调用内 compressed 空/失败后降级 plain
    for attempt in range(retries + 1):
        use_compressed = (not plain) and not fell_back_plain and \
            (_DUMP_STATE["compressed_ok"] is not False)
        args = ["adb", "-s", serial, "shell", "uiautomator", "dump"]
        if use_compressed:
            args.append("--compressed")
        args.append("/sdcard/ui.xml")
        adb(serial, "shell", "rm", "-f", "/sdcard/ui.xml")
        out = run(args, timeout=30)
        dump_ok = ("__ERR__" not in out) and ("dumped" in out)
        if not dump_ok:
            if use_compressed:
                if _DUMP_STATE["compressed_ok"] is None:
                    _DUMP_STATE["compressed_ok"] = False
                fell_back_plain = True  # 本次降级 plain 重试
                continue
            adb(serial, "shell", "pkill", "-f", "uiautomator")
            time.sleep(2.0 if attempt else 1.0)
            continue
        r = adb(serial, "pull", "/sdcard/ui.xml", "/tmp/_gmi_dump.xml")
        if "__ERR__" not in r:
            try:
                tx = Path("/tmp/_gmi_dump.xml").read_text(encoding="utf-8",
                                                          errors="replace")
                if len(tx) >= 100 and "<node" in tx:
                    if use_compressed and _DUMP_STATE["compressed_ok"] is None:
                        _DUMP_STATE["compressed_ok"] = True
                    _DUMP_STATE.update(last_ts=time.time(), cache_ts=time.time(),
                                       cache_xml=tx)
                    return tx
                if use_compressed:
                    # 空/异常树：本次降级 plain 重试（冷启动白屏期 compressed
                    # 可能空树；不改全局可用性记录）
                    if _DUMP_STATE["compressed_ok"] is None:
                        _DUMP_STATE["compressed_ok"] = None  # 保持探测态
                    fell_back_plain = True
                    continue
            except Exception:
                pass
        time.sleep(1.0)
    _DUMP_STATE["last_ts"] = time.time()
    return ""


def _clickable_anchors(xml: str, feats: List[str]) -> List[str]:
    """当前 UI 上可点击的特征（保序去重）。"""
    out: List[str] = []
    for f in feats:
        if f and find_click(xml, f) and f not in out:
            out.append(f)
    return out


def _long_text_fallback_targets(xml: str, min_len: int = 12, limit: int = 3) -> List[Dict[str, Any]]:
    """兜底导航目标：长可点文本节点（列表条目通常比按钮文本长，通用启发式）。"""
    out = []
    for n in ui_nodes(xml):
        if len(n["label"]) >= min_len and n not in out:
            out.append(n)
    return out[:limit]


def _icon_fallback_targets(xml: str, feats: List[str], limit: int = 3) -> List[Dict[str, Any]]:
    """图标按钮兜底目标：无文本 clickable 节点（tap_targets 机制）。
    优先级：1) 与页面特征锚点同水平带(|dy|<80px)的图标（入口图标常与相关
    文本控件同行，如 FolderChipButton 与分组 chips 同 y）；2) 远离屏幕垂直
    中心者（导航控件在上下边缘，列表内容在中部）。仅取前 limit 个，
    从严判定由调用方负责（>=2 新增命中）。"""
    nodes = [x for x in tap_targets(xml) if not x["label"]]
    if not nodes:
        return []
    band_cys = [n["cy"] for f in feats for n in [find_click(xml, f)] if n]
    same_band, others = [], []
    for x in nodes:
        (same_band if any(abs(x["cy"] - cy) < 80 for cy in band_cys) else others).append(x)
    if not others:
        return same_band[:limit]
    max_y = max(n["cy"] for n in nodes)
    center = max_y / 2
    others.sort(key=lambda n: abs(n["cy"] - center), reverse=True)
    return (same_band + others)[:limit]


def _nav_attempt(serial: str, pkg: str, act: str, out_dir: Path, pid: str, sym: str,
                 feats: List[str], launch_texts: set, stay: float,
                 jumps: Optional[List[Dict[str, Any]]] = None, depth: int = 3,
                 max_anchors: int = 5, max_fallbacks: int = 2,
                 anr_budget: Optional[List[int]] = None) -> Dict[str, Any]:
    """从当前 UI 尝试导航到达 pid（受限 DFS，depth<=3 借道已验证跳板页）。
    成功时设备停在目标页并返回 {reached: True, anchor, fallback, xml}；
    失败时恢复（BACK/bring_to_front/_back_to_home）并返回 {reached: False, note}。
    尝试顺序：
      1) 目标页特征锚点（len 降序，最多 max_anchors）；
      2) depth>1 时借道跳板页（jumps 里入口锚在当前 UI 可点的已验证页，
         最多 2 个：重放其入口 -> 递归本函数 depth-1）；
      3) 长文本条目兜底（最多 max_fallbacks，判定从严 >=2 新增命中）。"""

    def _fg_in_pkg() -> bool:
        fg = run(["adb", "-s", serial, "shell", "dumpsys", "activity",
                  "activities"], timeout=20)
        m = re.search(r"topResumedActivity=.*?u0 (\S+)", fg)
        return bool(m) and pkg in m.group(1)

    budget = anr_budget if anr_budget is not None else [2]
    before_text = _dump_stable(serial, pkg, act, f"nav:{sym or pid}",
                               anr_budget=budget)
    if not before_text:
        return {"reached": False, "anchor": "", "fallback": False,
                "note": "ANR_BLOCKED(collector-induced)", "xml": ""}
    if not _fg_in_pkg():
        bring_to_front(serial, pkg, act)
        before_text = _dump_stable(serial, pkg, act, f"nav:{sym or pid}",
                                   anr_budget=budget)
    if not before_text:
        return {"reached": False, "anchor": "", "fallback": False,
                "note": "ANR_BLOCKED(collector-induced)", "xml": ""}
    # already-on-page short-circuit: when every feature anchor of the target
    # surface is already visible in the current dump, the surface is reached
    # by definition (e.g. home-screen chains start on the home screen; the
    # new-hit delta below can never fire from an already-satisfied page).
    if feats and all(_xml_shows(before_text, f) for f in feats):
        return {"reached": True, "anchor": "(already-on-page)",
                "fallback": False, "xml": before_text}
    anchors = sorted(_clickable_anchors(before_text, feats), key=len, reverse=True)
    tried = 0
    for anchor in anchors[:max_anchors]:
        tgt = find_click(before_text, anchor)
        if not tgt:
            continue
        tried += 1
        adb(serial, "shell", "input", "tap", str(tgt["cx"]), str(tgt["cy"]))
        time.sleep(stay + _TAP_SETTLE)
        probe = _dump_stable(serial, pkg, act, f"probe:{sym or pid}",
                             anr_budget=budget)
        ok = bool(probe) and _fg_in_pkg() and _reached_by_features(
            feats, before_text, probe, True, launch_texts, min_new_hits=1)
        if ok and probe:
            return {"reached": True, "anchor": anchor, "fallback": False, "xml": probe}
        adb(serial, "shell", "input", "keyevent", "4")
        time.sleep(_BACK_SETTLE)
        if not _fg_in_pkg():
            bring_to_front(serial, pkg, act)
            before_text = _dump_stable(serial, pkg, act, f"nav:{sym or pid}",
                                       anr_budget=budget)
    # 借道跳板页（受限 DFS：入口锚在当前 UI 可点的已验证页，最多 2 个）
    if jumps and depth > 1:
        hops = 0
        for j in jumps:
            if hops >= 2:
                break
            tgt = find_click(before_text, j["anchor"])
            if not tgt or j["pid"] == pid:
                continue
            hops += 1
            adb(serial, "shell", "input", "tap", str(tgt["cx"]), str(tgt["cy"]))
            time.sleep(stay + _TAP_SETTLE)
            probe = _dump_stable(serial, pkg, act, f"jump:{j['pid']}",
                                 anr_budget=budget)
            mid_ok = bool(probe) and _fg_in_pkg() and _reached_by_features(
                j["feats"], before_text, probe, True, launch_texts, min_new_hits=1)
            if not mid_ok:
                adb(serial, "shell", "input", "keyevent", "4")
                time.sleep(_BACK_SETTLE)
                continue
            sub = _nav_attempt(serial, pkg, act, out_dir, pid, sym, feats,
                               launch_texts, stay, jumps=jumps, depth=depth - 1,
                               max_anchors=max_anchors, max_fallbacks=max_fallbacks,
                               anr_budget=budget)
            if sub.get("reached"):
                sub["via"] = j["pid"]
                return sub
            _back_to_home(serial, pkg, act, out_dir, launch_texts)
            before_text = _dump_xml(serial) or before_text
    # 长文本条目兜底（从严判定：>=2 新增命中）
    fallback_used = False
    for tnode in _long_text_fallback_targets(before_text, limit=max_fallbacks):
        fallback_used = True
        adb(serial, "shell", "input", "tap", str(tnode["cx"]), str(tnode["cy"]))
        time.sleep(stay + _TAP_SETTLE)
        probe = _dump_stable(serial, pkg, act, f"fbprobe:{sym or pid}",
                             anr_budget=budget)
        _mh = 1 if len(feats) <= 5 else 2  # 小特征集单命中高置信(子串遮蔽后
        # 真实新增常仅 1 个,如 GroupBottomSheet '新建组'); 宽特征集维持 2 防假阳性
        ok = bool(probe) and _fg_in_pkg() and _reached_by_features(
            feats, before_text, probe, True, launch_texts, min_new_hits=_mh)
        if ok and probe:
            return {"reached": True, "anchor": tnode["label"][:24],
                    "fallback": True, "xml": probe}
        adb(serial, "shell", "input", "keyevent", "4")
        time.sleep(_BACK_SETTLE)
        if not _fg_in_pkg():
            bring_to_front(serial, pkg, act)
            before_text = _dump_stable(serial, pkg, act, f"nav:{sym or pid}",
                                       anr_budget=budget)
            if not before_text:
                return {"reached": False, "anchor": "", "fallback": fallback_used,
                        "note": "ANR_BLOCKED(collector-induced)", "xml": ""}
    # 图标按钮兜底（无 text/content-desc 的入口，如 FolderChipButton；边缘优先；
    # 从严判定 >=2 新增命中）
    for inode in _icon_fallback_targets(before_text, feats, limit=3):
        fallback_used = True
        adb(serial, "shell", "input", "tap", str(inode["cx"]), str(inode["cy"]))
        time.sleep(stay + _TAP_SETTLE)
        probe = _dump_stable(serial, pkg, act, f"iconprobe:{sym or pid}",
                             anr_budget=budget)
        _mh = 1 if len(feats) <= 5 else 2  # 小特征集单命中高置信(子串遮蔽后
        # 真实新增常仅 1 个,如 GroupBottomSheet '新建组'); 宽特征集维持 2 防假阳性
        ok = bool(probe) and _fg_in_pkg() and _reached_by_features(
            feats, before_text, probe, True, launch_texts, min_new_hits=_mh)
        if ok and probe:
            return {"reached": True, "anchor": f"icon@({inode['cx']},{inode['cy']})",
                    "fallback": True, "xml": probe}
        adb(serial, "shell", "input", "keyevent", "4")
        time.sleep(_BACK_SETTLE)
        if not _fg_in_pkg():
            bring_to_front(serial, pkg, act)
            before_text = _dump_stable(serial, pkg, act, f"nav:{sym or pid}",
                                       anr_budget=budget)
            if not before_text:
                return {"reached": False, "anchor": "", "fallback": fallback_used,
                        "note": "ANR_BLOCKED(collector-induced)", "xml": ""}
    note = f"anchors_tried={tried} fallback={fallback_used} feats={len(feats)}"
    return {"reached": False, "anchor": "", "fallback": fallback_used,
            "note": note, "xml": ""}


def _back_to_home(serial: str, pkg: str, act: str, out_dir: Path,
                  launch_texts: set, max_back: int = 3) -> str:
    """BACK 回主页基准（主页判定 = 与基准指纹 jaccard>=0.6 且 in_pkg）。"""
    for _ in range(max_back):
        cur = _dump_xml(serial)
        if cur:
            fg = run(["adb", "-s", serial, "shell", "dumpsys", "activity",
                    "activities"], timeout=20)
            m = re.search(r"topResumedActivity=.*?u0 (\S+)", fg)
            in_pkg = bool(m) and pkg in m.group(1)
            if in_pkg and jaccard(ui_text_set(cur), launch_texts) >= 0.6:
                return cur
        adb(serial, "shell", "input", "keyevent", "4")
        time.sleep(1.2)
    bring_to_front(serial, pkg, act)
    return _dump_xml(serial)


def _full_probe(serial: str, dirpath: Path, pkg: str, act: str = "MainActivity",
                ctx: str = "") -> Dict[str, Any]:
    """稳健页面快照（ANR 感知 + 稳定双 dump 保证证据纯净）：
    _dump_stable(for_evidence=True) + screencap + foreground 组件。
    写 <dirpath>/{ui.xml,screenshot.png}；返回 ev 兼容记录（含 xml）。"""
    dirpath.mkdir(parents=True, exist_ok=True)
    xml = _dump_stable(serial, pkg, act, ctx or dirpath.name, for_evidence=True)
    if not xml:  # ANR_BLOCKED 或 dump 故障：不采证（证据纯净性优先）
        _log_anr(f"EVIDENCE-SKIP ctx={ctx or dirpath.name}")
        return {"page_id": dirpath.name, "tag": dirpath.parent.name,
                "ui_sha256": "", "png_sha256": "", "foreground": "",
                "in_pkg": False, "screen_resolution": "",
                "screen_density": "", "xml": ""}
    (dirpath / "ui.xml").write_text(xml or "", encoding="utf-8")
    adb(serial, "shell", "screencap", "-p", "/sdcard/sc.png")
    adb(serial, "pull", "/sdcard/sc.png", str(dirpath / "screenshot.png"))
    fg = run(["adb", "-s", serial, "shell", "dumpsys", "activity",
              "activities"], timeout=20)
    m = re.search(r"topResumedActivity=.*?u0 (\S+)", fg)
    fg_comp = m.group(1) if m else ""
    return {
        "page_id": dirpath.name, "tag": dirpath.parent.name,
        "ui_sha256": sha256f(dirpath / "ui.xml") if (dirpath / "ui.xml").exists() else "",
        "png_sha256": sha256f(dirpath / "screenshot.png") if (dirpath / "screenshot.png").exists() else "",
        "foreground": fg_comp, "in_pkg": pkg in fg_comp,
        "screen_resolution": "", "screen_density": "",
        "xml": xml or "",
    }


def _capture_side_effects(serial: str, pkg: str, se_dir: Path) -> List[str]:
    """外部副作用探针（文本证据）：dumpsys alarm / notification + 采集清单。"""
    se_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for name, args in (("dumpsys-alarm.txt", ("alarm",)),
                       ("dumpsys-notification.txt", ("notification",))):
        out = adb(serial, "shell", "dumpsys", *args)
        p = se_dir / name
        p.write_text(out, encoding="utf-8", errors="replace")
        files.append(name)
    (se_dir / "manifest.txt").write_text(
        "side-effect probes: adb shell dumpsys alarm|notification\n"
        f"package: {pkg}\ncaptured_at: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n",
        encoding="utf-8")
    files.append("manifest.txt")
    return files


def _write_capture_manifest(be_dir: Path, pid: str, sym: str, bc_ids: List[str],
                            anchor: str, fallback: bool) -> None:
    (be_dir / "capture-manifest.txt").write_text(
        f"page_id: {pid}\nsymbol: {sym}\nbc_ids: {';'.join(bc_ids) or '(none)'}\n"
        f"entry_anchor: {anchor} (fallback={'yes' if fallback else 'no'})\n"
        "capture_mode:\n"
        "  before       = copy of runtime-evidence/<pid>/ gate evidence at entry\n"
        "  after        = no-op dwell snapshot (BC operation replay NOT automated; see SKILL 2.1)\n"
        "  persistence  = am force-stop + relaunch + re-navigation snapshots\n"
        "  side-effects = dumpsys alarm/notification text probes\n"
        f"captured_at: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n",
        encoding="utf-8")


def capture_behavior_evidence(serial: str, pkg: str, act: str, out_dir: Path,
                              ws: Path, project: Path,
                              hi_scope: Dict[str, Any],
                              page_id_map: Dict[str, str],
                              bc_rows: List[Dict[str, str]],
                              ev: List[Dict[str, Any]],
                              gate_rows: List[Dict[str, Any]],
                              stay: float, verbose: bool = False) -> Dict[str, Any]:
    """RUNTIME_REQUIRED 页面级证据采集（behavior-evidence/<pid>/ 生成方）。

    对 hi_scope['pages'] 每个正式 Page-ID：
      1) 锚点级联导航（特征锚点 + 长文本兜底，到达判定与 audit 同构）；
      2) 到达 -> 主证据快照(=gate/audit 依据) + before/after/persistence/side-effects 四类证据；
      3) 未达 -> NOT_ENTERED gate 行（fail-closed，绝不记假 VISITED）。
    返回 {visited, not_entered, details} 由调用方打印；gate/ev 行就地追加。"""
    import shutil
    strings = load_strings(project)
    pf_labels = load_pf_label_map(ws, strings)
    pid_sym = build_pid_symbol_map(ws / "candidates")
    bcs_by_pid: Dict[str, List[str]] = {}
    for r in required_bc_rows(bc_rows):
        pid = resolve_page_ref((r.get("page_ref") or "").strip(), page_id_map)
        if pid:
            bcs_by_pid.setdefault(pid, []).append(r.get("bc_id", ""))

    # 基准净化：force-stop + 冷启动（烟测证明 am start 不清栈，任务栈残留会把
    # PAGE-HOME-BASE 采到非主页）；预清理可能挂起的 uiautomator 服务。
    adb(serial, "shell", "am", "force-stop", pkg)
    time.sleep(2.0)
    adb(serial, "shell", "am", "start", "-n", f"{pkg}/.{act}")
    _wait_app_ready(serial, pkg)  # 冷启动就绪轮询（每轮 2.5s，最多 12 轮）
    time.sleep(2.5)               # 首帧稳定等待（Compose 首帧后再 dump）
    base_xml = ""
    for _ in range(6):            # UI 内容就绪循环（冷启动白屏期 dump 可能空树）
        base_xml = _dump_stable(serial, pkg, act, "home-base")
        if base_xml and len(ui_nodes(base_xml)) >= 3:
            break
        time.sleep(2.5)
    if not base_xml:
        raise SystemExit("[behavior-capture] 主页基准 dump 不可用（uiautomator 故障），"
                         "fail-closed 拒绝采集")
    launch_texts = ui_text_set(base_xml)

    pending = sorted(hi_scope["pages"])
    feats_by_pid = {p: page_audit_features(pid_sym.get(p, ""), strings, pf_labels)
                    for p in pending}
    details: List[Dict[str, str]] = []
    verified: List[Dict[str, Any]] = []  # 已验证入口（跳板重放注册表）

    anr_budget_by_pid: Dict[str, List[int]] = {p: [2] for p in hi_scope["pages"]}

    def _nav_current(pid: str, sym: str, feats: List[str]) -> Dict[str, Any]:
        return _nav_attempt(serial, pkg, act, out_dir, pid, sym, feats,
                            launch_texts, stay, jumps=verified, depth=3,
                            anr_budget=anr_budget_by_pid.get(pid))

    rounds = 0
    while pending and rounds < 2 * len(hi_scope["pages"]) + 4:
        rounds += 1
        progressed = False
        # 轮首基准化：上一页 persistence 重启后停在主页，但仍显式回归基准
        _back_to_home(serial, pkg, act, out_dir, launch_texts)
        for pid in list(pending):
            sym = pid_sym.get(pid, "")
            feats = feats_by_pid.get(pid, [])
            nav = _nav_current(pid, sym, feats)
            if not nav["reached"]:
                gate_rows.append({"page_id": pid, "symbol": sym,
                                  "status": "NOT_ENTERED",
                                  "evidence": "(see route-hints)"})
                details.append({"page_id": pid, "symbol": sym, "status": "NOT_ENTERED",
                                "note": nav.get("note", "")})
                pending.remove(pid)
                _back_to_home(serial, pkg, act, out_dir, launch_texts)
                continue
            # 到达：主证据快照（gate/audit 依据；_full_probe 防缓存+ANR 纯净+稳定双 dump）
            snap = _full_probe(serial, out_dir / pid, pkg, act, ctx=f"gate:{pid}")
            if not snap["in_pkg"] or len(snap["xml"]) < 200:
                gate_rows.append({"page_id": pid, "symbol": sym,
                                  "status": "NOT_ENTERED",
                                  "evidence": "(foreground left pkg / empty dump / ANR)"})
                details.append({"page_id": pid, "symbol": sym, "status": "NOT_ENTERED",
                                "note": "foreground left pkg / empty dump / ANR at capture"})
                pending.remove(pid)
                _back_to_home(serial, pkg, act, out_dir, launch_texts)
                continue
            ev.append({k: v for k, v in snap.items() if k != "xml"})
            gate_rows.append({"page_id": pid, "symbol": sym, "status": "VISITED",
                              "evidence": f"{pid}/ui.xml"})
            be = out_dir / "behavior-evidence" / pid
            before_dir = be / "before"
            before_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(out_dir / pid / "ui.xml", before_dir / "ui.xml")
            if (out_dir / pid / "screenshot.png").exists():
                shutil.copy(out_dir / pid / "screenshot.png",
                            before_dir / "screenshot.png")
            # after：no-op dwell 快照（BC operation 不自动重放，见 capture-manifest）
            _full_probe(serial, be / "after", pkg, act, ctx=f"after:{pid}")
            # persistence：force-stop 重启 + 借道跳板重导航（ANR 适配：就绪轮询加长）
            adb(serial, "shell", "am", "force-stop", pkg)
            time.sleep(2.0)
            adb(serial, "shell", "am", "start", "-n", f"{pkg}/.{act}")
            _wait_app_ready(serial, pkg)
            _full_probe(serial, be / "persistence" / "01-restarted-home", pkg,
                        act, ctx=f"persistence1:{pid}")
            re_nav = _nav_current(pid, sym, feats)
            if re_nav["reached"]:
                _full_probe(serial, be / "persistence" / "02-reentered-page", pkg,
                            act, ctx=f"persistence2:{pid}")
                entry_note = "reentered"
            else:
                entry_note = "reenter-failed(home evidence retained)"
            # side-effects：dumpsys 探针
            _capture_side_effects(serial, pkg, be / "side-effects")
            _write_capture_manifest(be, pid, sym, bcs_by_pid.get(pid, []),
                                    nav.get("anchor", ""), bool(nav.get("fallback")))
            verified.append({"pid": pid, "sym": sym, "feats": feats,
                             "anchor": nav.get("anchor", ""),
                             "fallback": bool(nav.get("fallback"))})
            details.append({"page_id": pid, "symbol": sym, "status": "VISITED",
                            "note": (f"anchor={nav.get('anchor', '')[:24]}"
                                     f" via={nav.get('via', '-')} persistence={entry_note}")})
            pending.remove(pid)
            progressed = True
            break  # 每页采集含 force-stop（终态主页），无级联上下文可保
        if not progressed:
            break
    # 轮次耗尽仍未达的页面（保持 fail-closed 语义）
    for pid in list(pending):
        sym = pid_sym.get(pid, "")
        gate_rows.append({"page_id": pid, "symbol": sym, "status": "NOT_ENTERED",
                          "evidence": "(rounds exhausted; see route-hints)"})
        details.append({"page_id": pid, "symbol": sym, "status": "NOT_ENTERED",
                        "note": "nav rounds exhausted"})
        pending.remove(pid)
    _back_to_home(serial, pkg, act, out_dir, launch_texts)
    # ANR 动态风险证据落盘（会话级事件日志：时间/上下文/恢复动作）
    if _ANR_EVENTS:
        header = ("# classification: collector-induced pseudo-ANR "
                  "(uiautomator dump exports the Compose semantics tree on the "
                  "app main thread; arm-translated emulator amplifies latency; "
                  "system misjudges input unresponsive). App itself confirmed "
                  "healthy by on-site user. NOT an app defect/dynamic risk.\n")
        (out_dir / "anr-events.log").write_text(
            header + "\n".join(_ANR_EVENTS) + "\n", encoding="utf-8")
        print(f"[behavior-capture] ANR events={len(_ANR_EVENTS)} "
              f"-> {out_dir / 'anr-events.log'}")
    visited = [d for d in details if d["status"] == "VISITED"]
    not_entered = [d for d in details if d["status"] == "NOT_ENTERED"]
    if verbose or True:
        for d in details:
            print(f"[behavior-capture] {d['status']:11} {d['page_id'][:44]:46} {d['note'][:60]}")
    return {"visited": len(visited), "not_entered": len(not_entered), "details": details}


def build_behavior_evidence_index(ws: Path, out_dir: Path,
                                  bc_rows: List[Dict[str, str]],
                                  page_id_map: Dict[str, str],
                                  gate_rows: List[Dict[str, Any]]) -> int:
    """采集完成后生成 behavior-evidence-index.csv（fail-closed）。

    每个 RUNTIME_REQUIRED BC 一行，绑定采集到的证据引用：
      before_evidence_ref        = <页面证据目录>/before/ （进入态快照）
      after_evidence_ref         = <页面证据目录>/after/  （操作后快照）
      persistence_evidence_ref   = <页面证据目录>/persistence/ （重启后证据）
      side_effect_evidence_ref   = <页面证据目录>/side-effects/
      audit_ref                  = runtime-evidence/audit-replay.csv
    齐备->status=COMPLETE；否则按缺失项记 MISSING_*（绝不写 COMPLETE）。
    任一 required BC 证据不齐 -> 返回 1（主流程据此非零退出）。
    """
    ev_root = out_dir / "behavior-evidence"
    ev_root.mkdir(parents=True, exist_ok=True)
    visited_pids = {g.get("page_id", "") for g in gate_rows if g.get("status") == "VISITED"}
    symbol_by_pid: Dict[str, str] = {g.get("page_id", ""): g.get("symbol", "")
                                     for g in gate_rows if g.get("page_id")}
    pid_by_symbol: Dict[str, str] = {v: k for k, v in symbol_by_pid.items() if v}
    audit_ref = "runtime-evidence/audit-replay.csv"
    rows: List[Dict[str, str]] = []
    for r in required_bc_rows(bc_rows):
        bc_id = (r.get("bc_id") or "").strip()
        ref = (r.get("page_ref") or "").strip()
        pid = resolve_page_ref(ref, page_id_map)
        if not pid:
            rows.append({"bc_id": bc_id, "page_ref": ref, "audit_ref": "",
                         "status": "MISSING_PAGE_REF"})
            continue
        sym = symbol_by_pid.get(pid, "")
        runtime_pid = pid if pid in visited_pids else pid_by_symbol.get(sym, "")
        if not runtime_pid or runtime_pid not in visited_pids:
            rows.append({"bc_id": bc_id, "page_ref": pid, "audit_ref": audit_ref,
                         "status": "NOT_VISITED"})
            continue
        base = f"runtime-evidence/behavior-evidence/{pid}"
        sub = {"before": "before", "after": "after", "persistence": "persistence",
               "side_effect": "side-effects"}
        refs, miss = {}, []
        for key, name in sub.items():
            d = ev_root / pid / name
            vals = sorted(f.name for f in d.iterdir()) if d.is_dir() else []
            refs[key] = f"{base}/{name}/" + ";".join(vals) if vals else ""
            if not vals:
                miss.append(f"MISSING_{key.upper()}_EVIDENCE")
        row = {"bc_id": bc_id, "page_ref": pid,
               "before_evidence_ref": refs["before"], "after_evidence_ref": refs["after"],
               "persistence_evidence_ref": refs["persistence"],
               "side_effect_evidence_ref": refs["side_effect"],
               "audit_ref": audit_ref}
        row["status"] = "COMPLETE" if not miss else ";".join(miss)
        rows.append(row)
    write_csv(out_dir / "behavior-evidence-index.csv", BEHAVIOR_EVIDENCE_FIELDS, rows)
    incomplete = [r for r in rows if r["status"] != "COMPLETE"]
    print(f"[behavior-evidence] index rows={len(rows)} complete={len(rows) - len(incomplete)} "
          f"incomplete={len(incomplete)} -> {out_dir / 'behavior-evidence-index.csv'}")
    for r in incomplete[:20]:
        print(f"   {r['bc_id'][:16]:18} page_ref={r['page_ref'][:40]:42} status={r['status']}")
    return 1 if incomplete else 0


# ============================================================================
# v5.0 行为链模式（--mode chain，新范式默认）
# 范式（第 6/7 步）：只对高风险行为跑真机验证行为链，证据重点是结果断言；
# 容器页/纯展示（verify_mode=SOURCE_CONFIRM）完全不跑。复用全部实战能力。
# ============================================================================

CHAIN_CSV_FIELDS = [
    "bc_id", "feature_id", "page_ref",
    "nav_status", "entry_anchor",
    "steps_total", "steps_ok",
    "assertions_total", "assertions_passed",
    "assertion_results",   # JSON 数组 [{"kind","value","verdict"}]（逐条 PASS/FAIL）
    "chain_status",        # CHAIN_PASS|CHAIN_FAIL|NAV_FAIL|STEPS_FAIL|ANR_BLOCKED|UNRESOLVED_PAGE_REF
    "note", "evidence_dir",
]

CHAIN_STEP_ACTIONS = ("tap", "input", "back")
CHAIN_ASSERTION_KINDS = ("text_visible", "text_gone", "persist_after_restart")
# 受阻（非行为矛盾）的链状态：reconcile 侧一律记 GAP 而非 CONFLICT。
# 收敛式重构批次1（#81/#83）新增三态：
#   INVALID_CONTRACT     RUNTIME 链无 result_assertions（契约不完整，链不执行）
#   UNSUPPORTED_ORACLE   全部断言 kind 未知（无可用 oracle，绝不能 PASS）
#   PRECONDITION_FAILED  pre_state 校验失败且重试一次仍失败（#83，非功能 FAIL）
# Gate 2 对 INVALID_CONTRACT/UNSUPPORTED_ORACLE 记 error（不是 GAP 宽容）。
CHAIN_BLOCKED_STATUS = ("NAV_FAIL", "STEPS_FAIL", "ANR_BLOCKED", "UNRESOLVED_PAGE_REF",
                        "INVALID_CONTRACT", "UNSUPPORTED_ORACLE", "PRECONDITION_FAILED")


def parse_json_col(raw: str) -> List[Dict[str, str]]:
    """CSV 单元格里的 JSON 数组 -> list[dict]；空/坏 JSON/非数组 -> []。"""
    v = (raw or "").strip()
    if not v:
        return []
    try:
        data = json.loads(v)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [d for d in data if isinstance(d, dict)]


def json_col_broken(raw: str) -> bool:
    """列非空但无法解析为 JSON 数组（格式错误需显式暴露，不静默降级）。"""
    v = (raw or "").strip()
    if not v:
        return False
    try:
        data = json.loads(v)
    except Exception:
        return True
    return not isinstance(data, list)


def parse_chain_steps(bc: Dict[str, str]) -> List[Dict[str, str]]:
    """BC.operation_steps（JSON-in-CSV，人工/LLM 填充）-> 操作序列。"""
    return parse_json_col(bc.get("operation_steps", ""))


def parse_chain_assertions(bc: Dict[str, str]) -> List[Dict[str, str]]:
    """BC.result_assertions（JSON-in-CSV）-> 结果断言序列。"""
    return parse_json_col(bc.get("result_assertions", ""))


def parse_prepare_steps(bc: Dict[str, str]) -> List[Dict[str, str]]:
    """BC.prepare_steps（JSON-in-CSV，可选列，接口预留）-> 前置准备步骤。

    收敛式重构批次1（#83）：与 operation_steps 同 schema（action/target/
    value）；BC 骨架不生成该列（表头不变），LLM/人工按需追加；为空时
    prepare 走"链前冷启动复位"最小实现。
    """
    return parse_json_col(bc.get("prepare_steps", ""))


# pre_state 机器可校验 token 提取（保守口径，避免自然语言误伤）：
# 仅取 `=`/`：`/`:` 右侧值与「」『』“”'' 引号内文本，长度 1..24。
_PRE_STATE_SPLIT_RE = re.compile(r"[=:：]")
_PRE_STATE_QUOTE_RE = re.compile(r"[「『“\"']([^」』”\"']{1,24})[」』”\"']")


def parse_pre_state_tokens(pre_state: str) -> List[str]:
    """从 pre_state 自然语言描述中提取机器可校验 token（保守，纯函数）。

    例：「语言=中文」-> ["中文"]；「主题为『深色』模式」-> ["深色"]；
    「当前处于设置页」（无分隔符/引号）-> []（verify 走仅记录口径——
    整句自然语言不可能逐字出现在 UI 上，不作为校验 token 误伤链）。"""
    v = (pre_state or "").strip()
    if not v:
        return []
    tokens: List[str] = []
    parts = _PRE_STATE_SPLIT_RE.split(v)
    if len(parts) > 1:  # 存在 =/：/: 分隔：首段是左侧标签，取右侧值段
        for part in parts[1:]:
            part = part.strip()
            if 1 <= len(part) <= 24 and \
                    not re.fullmatch(r"[\s,，;；.。/\\()（）\-]+", part):
                tokens.append(part)
    for m in _PRE_STATE_QUOTE_RE.finditer(v):
        q = m.group(1).strip()
        if q:
            tokens.append(q)
    # 去重保序
    seen: set = set()
    out: List[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def verify_precondition(pre_state: str, xml: str) -> tuple:
    """pre_state 记录校验（最小实现，纯函数）。返回 (ok, note)。

    - 提取出 token：全部在当前 UI 可见 -> ok（token 逐项记录在 note）；
      任一不可见 -> not ok（note 列缺失项）；
    - 提取不出 token：ok=True（仅记录口径——自然语言 pre_state 无法机械
      校验时不阻塞链，note 记录原文供人审）。"""
    tokens = parse_pre_state_tokens(pre_state)
    if not tokens:
        return True, f"pre_state recorded (no machine-checkable tokens): " \
                     f"{(pre_state or '(empty)')[:60]}"
    missing = [t for t in tokens if not _xml_shows(xml, t)]
    if missing:
        return False, "precondition unverified, missing on page: " + \
            ";".join(missing[:4]) + f" (tokens: {';'.join(tokens[:4])})"
    return True, "precondition verified: " + ";".join(tokens[:4])


def _xml_shows(xml: str, value: str) -> bool:
    """文本可见判定（与 find_click 同构：label 大小写不敏感子串 + raw xml 兜底）。"""
    if not value:
        return False
    vl = value.lower()
    for n in ui_nodes(xml or ""):
        if vl in n["label"].lower():
            return True
    return vl in (xml or "").lower()


def assertion_is_optional(a: Dict[str, Any]) -> bool:
    """断言是否显式声明 optional:true（收紧性修复 #88）。

    仅豁免 UNSUPPORTED（无 oracle 时可跳过）；绝不豁免 FAIL（optional
    断言判 FAIL 仍是行为矛盾）。接受 JSON 布尔 true 或字符串 "true"
    （大小写不敏感）；缺省/其余取值一律视为 required（默认全部必验）。"""
    v = a.get("optional", False)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() == "true"


def evaluate_chain_assertions(assertions: List[Dict[str, str]],
                              after_xml: str, restart_xml: str
                              ) -> List[Dict[str, str]]:
    """结果断言判定（纯函数；结果导向）：
    - text_visible: value 在操作后 UI 可见；
    - text_gone:    value 在操作后 UI 消失；
    - persist_after_restart: value 在 force-stop 重启后 UI 仍可见（第 6 步
      行为链的持久化断言；restart_xml 为空=未证实 -> FAIL，fail-closed）；
    - 未知 kind -> UNSUPPORTED（不判 FAIL，由 chain_status 归 GAP 判定）；
    - optional 标记透传到结果（#88：classify 按显式 optional 豁免）。"""
    out: List[Dict[str, str]] = []
    for a in assertions:
        kind = (a.get("kind") or "").strip()
        value = (a.get("value") or "").strip()
        if kind == "text_visible":
            verdict = "PASS" if value and _xml_shows(after_xml, value) else "FAIL"
        elif kind == "text_gone":
            verdict = "PASS" if value and not _xml_shows(after_xml, value) else "FAIL"
        elif kind == "persist_after_restart":
            verdict = "PASS" if value and _xml_shows(restart_xml, value) else "FAIL"
        else:
            verdict = "UNSUPPORTED"
        out.append({"kind": kind, "value": value, "verdict": verdict,
                    "optional": "true" if assertion_is_optional(a) else "false"})
    return out


def classify_chain_status(nav_reached: bool, nav_note: str,
                          has_steps: bool, steps_ok: int, steps_total: int,
                          assertion_results: List[Dict[str, str]],
                          restart_ok: bool, needs_restart: bool
                          ) -> tuple:
    """链状态分类（blocked 优先于断言判定：采集链路受损不构成行为矛盾）。
    返回 (chain_status, note)。

    收敛式重构批次1（#81）：degraded CHAIN_PASS 路径彻底删除——
    - 无断言（assertion_results 为空）→ INVALID_CONTRACT：RUNTIME 契约缺
      result_assertions，绝不能以"仅导航+快照"冒充 PASS；
    - 全部断言 UNSUPPORTED → UNSUPPORTED_ORACLE：无可用 oracle，归 GAP，
      绝不能 PASS。
    收紧性修复（#88）：混合断言收紧——required 断言（默认全部）任一
    UNSUPPORTED → 整链 UNSUPPORTED_ORACLE（归 GAP），绝不能以"文字变化
    验证了但持久化/副作用验证不了"冒充成功；仅断言 JSON 显式带
    "optional": true 的才允许 UNSUPPORTED 跳过（optional 只豁免
    UNSUPPORTED，不豁免 FAIL）。判定顺序：
      fails（含 optional 的 FAIL）→ CHAIN_FAIL；
      全部 UNSUPPORTED → UNSUPPORTED_ORACLE；
      required 的 UNSUPPORTED 数 > 0 → UNSUPPORTED_ORACLE；
      全部 required PASS（optional 可 UNSUPPORTED）→ CHAIN_PASS + note
      列出 skipped optional。"""
    if not nav_reached:
        status = "ANR_BLOCKED" if "ANR" in (nav_note or "") else "NAV_FAIL"
        return status, nav_note or "page not reached"
    if has_steps and steps_ok < steps_total:
        return "STEPS_FAIL", f"steps interrupted at {steps_ok}/{steps_total}"
    if needs_restart and not restart_ok:
        return "ANR_BLOCKED", "restart phase failed; persistence unverified"
    if not assertion_results:
        return "INVALID_CONTRACT", \
            "no result_assertions declared (RUNTIME contract incomplete)"
    fails = [a for a in assertion_results if a["verdict"] == "FAIL"]
    if fails:
        return "CHAIN_FAIL", "assertions failed: " + "; ".join(
            f"{a['kind']}={a['value']}" for a in fails[:4])
    unsup = [a for a in assertion_results if a["verdict"] == "UNSUPPORTED"]
    if unsup:
        if len(unsup) == len(assertion_results):
            return "UNSUPPORTED_ORACLE", "all assertions unsupported: " + \
                ";".join(a["kind"] for a in unsup[:4]) + \
                f" (supported kinds: {'|'.join(CHAIN_ASSERTION_KINDS)})"
        # #88 收紧：required 断言（未显式 optional:true）任一 UNSUPPORTED
        # -> 整链 UNSUPPORTED_ORACLE（归 GAP），部分验证不构成成功。
        required_unsup = [a for a in unsup if not assertion_is_optional(a)]
        if required_unsup:
            return "UNSUPPORTED_ORACLE", "required assertions unsupported: " + \
                ";".join(a["kind"] for a in required_unsup[:4]) + \
                f" (supported kinds: {'|'.join(CHAIN_ASSERTION_KINDS)})"
        # 仅显式 optional 的断言 UNSUPPORTED：豁免跳过，note 可诊断。
        return "CHAIN_PASS", "ok (skipped optional: " + \
            ";".join(a["kind"] for a in unsup) + ")"
    return "CHAIN_PASS", "ok"


def all_assertions_unsupported(assertions: List[Dict[str, str]]) -> bool:
    """预扫描：断言非空且全部 kind 不在支持集（无可用 oracle）。

    用于链执行前 fail-fast：这种链跑真机也只会得到全 UNSUPPORTED，
    直接标记 UNSUPPORTED_ORACLE 不执行（省采集，语义与执行后判定一致）。
    """
    if not assertions:
        return False
    supported = set(CHAIN_ASSERTION_KINDS)
    return all((a.get("kind") or "").strip() not in supported
               for a in assertions)


def load_feature_map(ws: Path) -> Dict[str, Any]:
    """读 feature-map.json（#38 改造A 产物；接口 2026-08-30 对齐）。

    权威 schema：features[]: {feature_id, verify_mode(RUNTIME|SOURCE_CONFIRM),
    surfaces[]: {id: 正式 PAGE-ID, kind, is_container}, ...}
    容错：surfaces 项为字符串 / 顶层即 list / {feature_id: {...}} 映射。
    返回 {"runtime_features": set, "source_confirm_features": set,
          "pages_by_feature": {fid: set(pid)}, "missing": bool}"""
    result: Dict[str, Any] = {"runtime_features": set(),
                              "source_confirm_features": set(),
                              "pages_by_feature": {}, "missing": True}
    for p in (ws / "feature-map.json", ws / "candidates" / "feature-map.json"):
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            break
        feats = data.get("features") if isinstance(data, dict) else data
        if isinstance(feats, dict):  # {feature_id: {...}} 映射形态
            feats = [{"feature_id": k, **(v if isinstance(v, dict) else {})}
                     for k, v in feats.items()]
        if not isinstance(feats, list):
            feats = []
        for f in feats:
            if not isinstance(f, dict):
                continue
            fid = str(f.get("feature_id") or f.get("id") or "").strip()
            if not fid:
                continue
            vm = str(f.get("verify_mode") or "").strip().upper().replace("-", "_")
            pages: set = set()
            for s in f.get("surfaces") or []:
                if isinstance(s, dict):
                    sid = str(s.get("id") or s.get("page_id") or "").strip()
                else:
                    sid = str(s).strip()
                if sid:
                    pages.add(sid)
            result["pages_by_feature"][fid] = pages
            if vm == "RUNTIME":
                result["runtime_features"].add(fid)
            elif vm in ("SOURCE_CONFIRM", "SOURCECONFIRM"):
                result["source_confirm_features"].add(fid)
        result["missing"] = False
        break
    return result


def select_chain_bcs(bc_rows: List[Dict[str, str]],
                     fmap: Dict[str, Any]) -> Dict[str, Any]:
    """行为链选择（第 6 步范式：SOURCE_CONFIRM 完全不跑）。
    - feature-map 在：verify_mode=RUNTIME 的 feature 下的 BC 选中；
      SOURCE_CONFIRM feature 的 BC 全部排除（含容器页）；feature_id 不在
      map -> unmapped（fail-closed，绝不静默当作排除）。
    - feature-map 缺失：降级 evidence_class=RUNTIME_REQUIRED（legacy 兼容）。"""
    selected: List[Dict[str, str]] = []
    excluded: List[Dict[str, str]] = []
    unmapped: List[Dict[str, str]] = []
    if fmap.get("missing"):
        for r in bc_rows:
            ec = (r.get("evidence_class") or "").strip().upper()
            if ec == "RUNTIME_REQUIRED":
                selected.append(r)
            else:
                excluded.append({"bc_id": r.get("bc_id", ""),
                                 "feature_id": r.get("feature_id", ""),
                                 "reason": f"evidence_class={ec or '(empty)'} (fallback)"})
        return {"selected": selected, "excluded": excluded, "unmapped": unmapped,
                "fallback": True}
    rt = fmap["runtime_features"]
    sc = fmap["source_confirm_features"]
    for r in bc_rows:
        fid = (r.get("feature_id") or "").strip()
        if fid in rt:
            selected.append(r)
        elif fid in sc:
            excluded.append({"bc_id": r.get("bc_id", ""), "feature_id": fid,
                             "reason": "verify_mode=SOURCE_CONFIRM (not run by design)"})
        else:
            unmapped.append({"bc_id": r.get("bc_id", ""), "feature_id": fid})
    return {"selected": selected, "excluded": excluded, "unmapped": unmapped,
            "fallback": False}


def chain_evidence_relpath(bc_id: str) -> str:
    """行为链证据目录（按 bc_id 组织，不再按 page_id）。"""
    return f"runtime-evidence/evidence/chains/{bc_id}"


# ---- 以下为 adb 副作用执行器（单测不覆盖，与现有采集器测试策略一致） ----

def _fg_in_pkg_now(serial: str, pkg: str) -> bool:
    """foreground∈pkg 防假访问铁律（链执行每步后校验）。"""
    fg = run(["adb", "-s", serial, "shell", "dumpsys", "activity",
              "activities"], timeout=20)
    m = re.search(r"topResumedActivity=.*?u0 (\S+)", fg)
    return bool(m) and pkg in m.group(1)


def _exec_chain_step(serial: str, pkg: str, act: str, step: Dict[str, str],
                     cur_xml: str, stay: float, budget: List[int],
                     ctx: str) -> Dict[str, Any]:
    """执行单个操作步骤；返回 {"ok", "xml", "note"}（xml=步骤后最新 UI dump）。
    步骤失败即中止后续（链式操作依赖前序状态），断言照常评估（结果导向）。"""
    action = (step.get("action") or "").strip().lower()
    target = (step.get("target") or "").strip()
    value = (step.get("value") or "").strip()
    if action == "tap":
        tgt = find_click(cur_xml, target)
        if not tgt:
            return {"ok": False, "xml": cur_xml,
                    "note": f"tap target not found: '{target}'"}
        adb(serial, "shell", "input", "tap", str(tgt["cx"]), str(tgt["cy"]))
        time.sleep(stay + _TAP_SETTLE)
        probe = _dump_stable(serial, pkg, act, f"step:{ctx}", anr_budget=budget)
        if not probe:
            return {"ok": False, "xml": cur_xml,
                    "note": "ANR_BLOCKED(collector-induced)"}
        if not _fg_in_pkg_now(serial, pkg):
            return {"ok": False, "xml": probe, "note": "foreground left pkg after tap"}
        return {"ok": True, "xml": probe,
                "note": f"tap '{target}' @({tgt['cx']},{tgt['cy']})"}
    if action == "input":
        if not target or not value:
            return {"ok": False, "xml": cur_xml,
                    "note": "input step missing target/value"}
        if not fill_field(serial, cur_xml, target, value):
            return {"ok": False, "xml": cur_xml,
                    "note": f"input field not found: '{target}'"}
        time.sleep(1.0)
        probe = _dump_stable(serial, pkg, act, f"step:{ctx}", anr_budget=budget)
        if not probe:
            return {"ok": False, "xml": cur_xml,
                    "note": "ANR_BLOCKED(collector-induced)"}
        return {"ok": True, "xml": probe, "note": f"input '{target}' <- '{value[:24]}'"}
    if action == "back":
        adb(serial, "shell", "input", "keyevent", "4")
        time.sleep(_BACK_SETTLE)
        probe = _dump_stable(serial, pkg, act, f"step:{ctx}", anr_budget=budget)
        if not probe:
            return {"ok": False, "xml": cur_xml,
                    "note": "ANR_BLOCKED(collector-induced)"}
        return {"ok": True, "xml": probe, "note": "back"}
    return {"ok": False, "xml": cur_xml, "note": f"unsupported action: '{action}'"}


def _cold_restart(serial: str, pkg: str, act: str) -> bool:
    """#83 prepare 最小实现：force-stop + 冷启动复位到干净态。

    供两处使用：run_chain_mode 每条链执行前（链前冷启动复位，保证每条
    行为链从干净态起步——持久化链的"新增→杀进程→还在"范式起点一致）；
    execute_behavior_chain precondition 校验失败后的重试。"""
    adb(serial, "shell", "am", "force-stop", pkg)
    time.sleep(2.0)
    adb(serial, "shell", "am", "start", "-n", f"{pkg}/.{act}")
    ok = _wait_app_ready(serial, pkg)
    if ok:
        time.sleep(2.0)  # 首帧稳定
    return ok


def _write_chain_artifacts(ev_dir: Path, ops_log: List[str], bc_id: str,
                           status: str, note: str,
                           results: List[Dict[str, str]]) -> None:
    (ev_dir / "operations.log").write_text("\n".join(ops_log) + "\n",
                                           encoding="utf-8")
    (ev_dir / "assertions.json").write_text(
        json.dumps({"bc_id": bc_id, "status": status, "note": note,
                    "results": results}, ensure_ascii=False, indent=1),
        encoding="utf-8")


def execute_behavior_chain(serial: str, pkg: str, act: str, bc: Dict[str, str],
                           out_dir: Path, page_id_map: Dict[str, str],
                           pid_sym: Dict[str, str], pf_labels: Dict[str, List[str]],
                           strings: Dict[str, str], launch_texts: set,
                           stay: float, anr_budget: List[int],
                           verified: List[Dict[str, Any]]) -> Dict[str, Any]:
    """执行一条 BC 行为链：prepare → verify precondition → execute → assert
    （#83：prepare = 链前冷启动复位（run_chain_mode 每链前）+ 可选
    prepare_steps 列；verify = pre_state 记录校验，失败冷复位重试一次，
    仍失败 → PRECONDITION_FAILED）→ 导航 -> before 快照 -> 操作序列 ->
    after 快照 -> persist 断言重启 -> restart 快照 -> 断言判定。
    无 result_assertions / 全断言无 oracle 的链不执行（#81：INVALID_CONTRACT
    / UNSUPPORTED_ORACLE 预拦截，绝无 degraded PASS）。
    证据瘦身：before/after/restart 三点关键快照 + operations.log +
    assertions.json（按 bc_id 组织）。返回 runtime-chains.csv 行。"""
    bc_id = (bc.get("bc_id") or "").strip() or "BC-?"
    fid = (bc.get("feature_id") or "").strip()
    page_ref = (bc.get("page_ref") or "").strip()
    steps = parse_chain_steps(bc)
    assertions = parse_chain_assertions(bc)
    ev_dir = out_dir / "evidence" / "chains" / bc_id
    ev_dir.mkdir(parents=True, exist_ok=True)
    ops_log: List[str] = []
    row: Dict[str, Any] = dict.fromkeys(CHAIN_CSV_FIELDS, "")
    row.update({"bc_id": bc_id, "feature_id": fid, "page_ref": page_ref,
                "steps_total": len(steps), "assertions_total": len(assertions),
                "evidence_dir": chain_evidence_relpath(bc_id)})
    if json_col_broken(bc.get("operation_steps", "")):
        ops_log.append("operation_steps column present but unparseable JSON "
                       "-> steps empty")
    if json_col_broken(bc.get("result_assertions", "")):
        ops_log.append("result_assertions column present but unparseable JSON "
                       "-> assertions empty")
    # 收敛式重构批次1（#81）：无断言/全断言无 oracle 的链不执行（fail-fast，
    # 绝不能以"仅导航+快照"冒充 PASS——degraded 路径已删除）。
    if not assertions:
        row.update({"chain_status": "INVALID_CONTRACT",
                    "note": "RUNTIME_REQUIRED contract has no result_assertions; "
                            "chain not executed (fill result_assertions and rerun)"})
        ops_log.append("INVALID_CONTRACT: no result_assertions; chain not executed")
        _write_chain_artifacts(ev_dir, ops_log, bc_id, row["chain_status"],
                               row["note"], [])
        return row
    if all_assertions_unsupported(assertions):
        kinds = ";".join((a.get("kind") or "(empty)") for a in assertions[:4])
        row.update({"chain_status": "UNSUPPORTED_ORACLE",
                    "note": f"all assertion kinds unsupported: {kinds} "
                            f"(supported: {'|'.join(CHAIN_ASSERTION_KINDS)}); "
                            "chain not executed"})
        ops_log.append("UNSUPPORTED_ORACLE: no supported assertion kind; "
                       "chain not executed")
        _write_chain_artifacts(ev_dir, ops_log, bc_id, row["chain_status"],
                               row["note"], [])
        return row
    pid = resolve_page_ref(page_ref, page_id_map)
    if not pid:
        row.update({"nav_status": "UNRESOLVED", "chain_status": "UNRESOLVED_PAGE_REF",
                    "note": f"page_ref '{page_ref}' not in candidate Page-ID map"})
        _write_chain_artifacts(ev_dir, ops_log, bc_id, row["chain_status"],
                               row["note"], [])
        return row
    sym = pid_sym.get(pid, "")
    # Home/host surfaces are reached by construction: the cold launch lands
    # on them. anchor_for word-root noise (e.g. 'Main' matching unrelated
    # string keys) makes the generic feature delta permanently false-negative
    # on container hosts, so probe the current dump and accept directly.
    HOME_SURFACE_SYMBOLS = {"MainScreen", "MainActivity"}

    def _nav_to_chain_page() -> tuple:
        """1) 导航到链所在页（跳板级联 + 长文本/图标兜底 + min_new_hits 从严，
        全保留；home 宿主面直接探测接受）。返回 (nav, feats)。"""
        if sym in HOME_SURFACE_SYMBOLS:
            home_xml = _dump_stable(serial, pkg, act, f"home:{bc_id}")
            if home_xml and _fg_in_pkg_now(serial, pkg):
                return ({"reached": True, "anchor": "(home-surface:launch)",
                         "fallback": False, "xml": home_xml}, [])
            return ({"reached": False, "note": "ANR_BLOCKED(collector-induced)",
                     "anchor": "", "fallback": False, "xml": ""}, [])
        page_feats = page_audit_features(sym, strings, pf_labels)
        nav = _nav_attempt(serial, pkg, act, out_dir, pid, sym, page_feats,
                           launch_texts, stay, jumps=verified, depth=3,
                           anr_budget=anr_budget)
        return nav, page_feats

    nav, feats = _nav_to_chain_page()
    row["nav_status"] = "REACHED" if nav.get("reached") else "NOT_REACHED"
    row["entry_anchor"] = (nav.get("anchor") or "")[:48]
    if not nav.get("reached"):
        status = "ANR_BLOCKED" if "ANR" in (nav.get("note") or "") else "NAV_FAIL"
        row.update({"chain_status": status, "note": nav.get("note", "")})
        _write_chain_artifacts(ev_dir, ops_log, bc_id, status,
                               row["note"], [])
        return row
    if nav.get("anchor"):  # 注册跳板（跨链复用）
        verified.append({"pid": pid, "sym": sym, "feats": feats,
                         "anchor": nav["anchor"],
                         "fallback": bool(nav.get("fallback"))})
    # 2) prepare → verify precondition → execute → assert（#83 最小实现）：
    #    - 链前冷启动复位由 run_chain_mode 每链前执行（干净态起点）；
    #    - prepare_steps 为 BC 可选列接口（非空则逐条执行，失败按 precondition
    #      失败处理重试）；
    #    - pre_state 记录校验（verify_precondition）失败 → 冷复位重试一次，
    #      仍失败 → PRECONDITION_FAILED（不算功能 FAIL，reconcile 归 GAP）。
    pre_state = (bc.get("pre_state") or "").strip()
    prep_steps = parse_prepare_steps(bc)
    if prep_steps:
        ops_log.append(f"prepare_steps declared: {len(prep_steps)} step(s)")
    cur_xml = nav.get("xml") or ""
    last_fail = "precondition not established"
    pre_established = False
    for attempt in (1, 2):
        if attempt == 2:  # 重试一次：冷启动复位 + 重新导航
            ops_log.append("precondition retry #1: cold restart + renavigate")
            _cold_restart(serial, pkg, act)
            nav, feats = _nav_to_chain_page()
            if not nav.get("reached"):
                last_fail = "retry navigation failed: " + (nav.get("note") or "")
                break
            cur_xml = nav.get("xml") or ""
        prep_ok = True
        for j, st in enumerate(prep_steps, 1):
            pr = _exec_chain_step(serial, pkg, act, st, cur_xml, stay,
                                  anr_budget, f"{bc_id}:prep{j}")
            ops_log.append(f"[{time.strftime('%H:%M:%S')}] prep{j}/{len(prep_steps)} "
                           f"action={st.get('action', '')} target={st.get('target', '')} "
                           f"ok={int(bool(pr['ok']))} {pr['note']}")
            if not pr["ok"]:
                prep_ok = False
                last_fail = f"prepare_steps interrupted at {j}/{len(prep_steps)}: " \
                            + pr["note"][:60]
                break
            cur_xml = pr["xml"]
        if not prep_ok:
            continue
        # before 关键快照（三点之一；prepare 之后采集，反映前置满足后的状态）
        before_ev = _full_probe(serial, ev_dir / "before", pkg, act,
                                ctx=f"before:{bc_id}")
        before_xml = (before_ev or {}).get("xml") or ""
        pre_ok, pre_note = verify_precondition(pre_state, before_xml)
        ops_log.append(pre_note)
        if pre_ok:
            pre_established = True
            break
        last_fail = pre_note
    if not pre_established:
        row.update({"chain_status": "PRECONDITION_FAILED",
                    "note": last_fail[:120]})
        _write_chain_artifacts(ev_dir, ops_log, bc_id, "PRECONDITION_FAILED",
                               row["note"], [])
        return row
    # 3) 操作序列（按 BC operation_steps 驱动）
    steps_ok = 0
    for i, st in enumerate(steps, 1):
        r = _exec_chain_step(serial, pkg, act, st, cur_xml, stay, anr_budget,
                             f"{bc_id}:{i}")
        ops_log.append(f"[{time.strftime('%H:%M:%S')}] step{i}/{len(steps)} "
                       f"action={st.get('action', '')} target={st.get('target', '')} "
                       f"ok={int(bool(r['ok']))} {r['note']}")
        print(f"[chain]   step{i}/{len(steps)} {st.get('action', '')} "
              f"'{str(st.get('target', ''))[:20]}' -> "
              f"{'ok' if r['ok'] else 'ABORT: ' + r['note'][:48]}")
        if not r["ok"]:
            break
        steps_ok = i
        cur_xml = r["xml"]
    # 4) after 关键快照（三点之二）
    _full_probe(serial, ev_dir / "after", pkg, act, ctx=f"after:{bc_id}")
    after_xml = ""
    if (ev_dir / "after" / "ui.xml").exists():
        after_xml = (ev_dir / "after" / "ui.xml").read_text(
            encoding="utf-8", errors="replace")
    if not after_xml:
        after_xml = cur_xml  # 快照失败（ANR 等）用最后一次 dump 兜底，note 已记录
        ops_log.append("after-snapshot unavailable; fell back to last step dump")
    # 5) persist 断言：一次重启 + 重导航 + restart 快照（三点之三）
    needs_restart = any((a.get("kind") or "").strip() == "persist_after_restart"
                        for a in assertions)
    restart_xml, restart_ok = "", True
    if needs_restart:
        adb(serial, "shell", "am", "force-stop", pkg)
        time.sleep(2.0)
        adb(serial, "shell", "am", "start", "-n", f"{pkg}/.{act}")
        restart_ok = _wait_app_ready(serial, pkg)
        reenter = "restart-failed"
        if restart_ok:
            time.sleep(2.5)  # 首帧稳定
            re_nav = _nav_attempt(serial, pkg, act, out_dir, pid, sym, feats,
                                  launch_texts, stay, jumps=verified, depth=3,
                                  anr_budget=anr_budget)
            reenter = "reentered" if re_nav.get("reached") else \
                "reenter-failed(home evidence retained)"
            _full_probe(serial, ev_dir / "restart", pkg, act,
                        ctx=f"restart:{bc_id}")
        else:
            ops_log.append("restart failed (app not ready after force-stop)")
        if (ev_dir / "restart" / "ui.xml").exists():
            restart_xml = (ev_dir / "restart" / "ui.xml").read_text(
                encoding="utf-8", errors="replace")
        ops_log.append(f"restart: {reenter}")
    # 6) 断言判定（结果导向）
    results = evaluate_chain_assertions(assertions, after_xml, restart_xml)
    status, note = classify_chain_status(
        True, "", bool(steps), steps_ok, len(steps), results,
        restart_ok, needs_restart)
    row.update({"steps_ok": steps_ok,
                "assertions_passed": sum(1 for a in results if a["verdict"] == "PASS"),
                "assertion_results": json.dumps(results, ensure_ascii=False),
                "chain_status": status, "note": note})
    _write_chain_artifacts(ev_dir, ops_log, bc_id, status, note, results)
    return row


def run_chain_mode(args: argparse.Namespace, ws: Path, out_dir: Path) -> int:
    """--mode chain 主流程（v5.0 新范式默认）。"""
    pkg, serial, act = args.package, args.serial, args.activity
    project = Path(args.project)
    cands = ws / "candidates"
    page_id_map = build_page_id_map(cands)
    bc_rows = load_behavior_contracts(ws)
    if not bc_rows:
        raise SystemExit("[chain] behavior-contracts.csv 缺失：fail-closed 拒绝执行；"
                         "先跑 scripts/build_behavior_contracts.py")
    fmap = load_feature_map(ws)
    sel = select_chain_bcs(bc_rows, fmap)
    if sel["unmapped"]:
        detail = "; ".join(f"{u['bc_id']}:feature_id={u['feature_id'] or '(empty)'}"
                           for u in sel["unmapped"][:10])
        raise SystemExit(
            "[chain] UNMAPPED_FEATURE: 以下 BC 的 feature_id 不在 feature-map.json 中\n"
            f"  {detail}\n"
            "  fail-closed：不静默跳过；对齐 feature-map.json 与 BC.feature_id 后重跑")
    if not sel["selected"]:
        raise SystemExit("[chain] RUNTIME 行为链集为空（feature-map 无 verify_mode="
                         "RUNTIME 功能且无降级集）：fail-closed 拒绝执行（同旧模式空集语义）")
    print(f"[chain] feature-map={'missing(evidence_class 降级)' if sel['fallback'] else 'ok'} "
          f"bc_rows={len(bc_rows)} selected={len(sel['selected'])} "
          f"excluded={len(sel['excluded'])} (SOURCE_CONFIRM 不跑，死锁根治)")
    if sel["fallback"]:
        print("[chain] WARNING: feature-map.json 缺失，按 evidence_class="
              "RUNTIME_REQUIRED 降级选择（legacy 兼容）")
    for e in sel["excluded"][:12]:
        print(f"[chain]   skip {e['bc_id']:14} {e['reason']}")
    if args.grant_perms:
        n = grant_permissions(serial, project, pkg)
        print(f"[perms] granted {n} permissions for {pkg}")
    # 屏幕元数据（复现实验元数据，仅记录，不作质量判据）
    cur_size = adb(serial, "shell", "wm", "size")
    cur_den = adb(serial, "shell", "wm", "density")
    print(f"[screen] metadata (reproducibility only): "
          f"{'' if cur_size.startswith('__ERR__') else cur_size.strip().replace(chr(10), ' ')} / "
          f"{'' if cur_den.startswith('__ERR__') else cur_den.strip().replace(chr(10), ' ')}")
    # 基准净化：force-stop + 冷启动（与 capture_behavior_evidence 同构：am start
    # 不清栈，任务栈残留会把主页基准采歪）
    adb(serial, "shell", "am", "force-stop", pkg)
    time.sleep(2.0)
    adb(serial, "shell", "am", "start", "-n", f"{pkg}/.{act}")
    _wait_app_ready(serial, pkg)
    time.sleep(2.5)
    base_xml = ""
    for _ in range(6):
        base_xml = _dump_stable(serial, pkg, act, "home-base")
        if base_xml and len(ui_nodes(base_xml)) >= 3:
            break
        time.sleep(2.5)
    if not base_xml:
        raise SystemExit("[chain] 主页基准 dump 不可用（uiautomator 故障），"
                         "fail-closed 拒绝采集")
    launch_texts = ui_text_set(base_xml)
    strings = load_strings(project)
    pf_labels = load_pf_label_map(ws, strings)
    pid_sym = build_pid_symbol_map(cands)
    verified: List[Dict[str, Any]] = []  # 跳板注册表（跨链复用）
    rows: List[Dict[str, Any]] = []
    for bc in sel["selected"]:
        # #83 prepare：链前冷启动复位——每条行为链从干净态起步（force-stop
        # + 冷启动；precondition 校验失败时 execute_behavior_chain 内还会
        # 再复位重试一次）。复杂 prepare 走 BC.prepare_steps 可选列（接口）。
        _cold_restart(serial, pkg, act)
        row = execute_behavior_chain(
            serial, pkg, act, bc, out_dir, page_id_map, pid_sym,
            pf_labels, strings, launch_texts, args.stay, [2], verified)
        rows.append(row)
        print(f"[chain] {row['chain_status']:22} {row['bc_id']:14} "
              f"steps={row['steps_ok']}/{row['steps_total']} "
              f"asserts={row['assertions_passed']}/{row['assertions_total']} "
              f"{(row['note'] or '')[:60]}")
        _back_to_home(serial, pkg, act, out_dir, launch_texts)
    write_csv(out_dir / "runtime-chains.csv", CHAIN_CSV_FIELDS, rows)
    # ANR 事件落盘（采集器诱发伪 ANR，定性同 v4.2，不作 app 缺陷）
    if _ANR_EVENTS:
        header = ("# classification: collector-induced pseudo-ANR "
                  "(uiautomator dump exports the Compose semantics tree on the "
                  "app main thread; arm-translated emulator amplifies latency; "
                  "system misjudges input unresponsive). NOT an app defect.\n")
        (out_dir / "anr-events.log").write_text(
            header + "\n".join(_ANR_EVENTS) + "\n", encoding="utf-8")
        print(f"[chain] ANR events={len(_ANR_EVENTS)} -> {out_dir / 'anr-events.log'}")
    bad = [r for r in rows if r["chain_status"] != "CHAIN_PASS"]
    print(f"[chain] done: rows={len(rows)} pass={len(rows) - len(bad)} "
          f"fail/blocked={len(bad)} -> {out_dir / 'runtime-chains.csv'}")
    if bad:
        for r in bad:
            print(f"[chain]   {r['chain_status']:18} {r['bc_id']:14} "
                  f"{(r['note'] or '')[:70]}")
        print("[chain] FAIL: 存在未全 PASS 的行为链（结果导向 fail-closed），退出非零；"
              "行为矛盾归 reconcile.py 判 CONFLICT")
        return 1
    return 0


FEATURE_COVERAGE_FIELDS = ["feature", "status", "evidence_hits"]


def build_feature_coverage_rows(gate_rows: List[Dict[str, Any]],
                                page_id_map: Dict[str, str],
                                feat_by_pid: Dict[str, str]) -> List[Dict[str, str]]:
    """从 runtime-gate 行派生 feature 口径覆盖表（gmi_phase3_adapter 消费）。

    表头：feature,status,evidence_hits（adapter 解析 evidence_hits 第一段 ":" 前
    的目录名作为 feature 级证据，要求该目录真实存在）。
    feature 归属：gate 行 symbol -> 正式 Page-ID（page_id_map 精确映射）
    -> 候选表 feature_id（feat_by_pid）；无法映射的行不计入。
    feature 状态口径：任一 VISITED -> VISITED；否则任一 EXITED -> EXITED；
    否则 NOT_ENTERED。仅 VISITED 行产出 evidence_hits（"<证据目录>:<符号>"，
    "|" 分隔），NOT_ENTERED/EXITED 行无证据目录。
    """
    status_by_feat: Dict[str, str] = {}
    hits_by_feat: Dict[str, List[str]] = {}
    for g in gate_rows:
        sym = (g.get("symbol") or "").strip()
        st = (g.get("status") or "").strip()
        if st not in ("VISITED", "EXITED", "NOT_ENTERED"):
            continue
        pid = resolve_page_ref(sym, page_id_map) if sym else ""
        feat = feat_by_pid.get(pid, "") if pid else ""
        if not feat:
            continue
        if st == "VISITED":
            status_by_feat[feat] = "VISITED"
            ev_dir = (g.get("page_id") or "").strip()
            if ev_dir:
                hits_by_feat.setdefault(feat, []).append(f"{ev_dir}:{sym}")
        elif st == "EXITED":
            if status_by_feat.get(feat) != "VISITED":
                status_by_feat[feat] = "EXITED"
        else:  # NOT_ENTERED
            if feat not in status_by_feat:
                status_by_feat[feat] = "NOT_ENTERED"
    return [{"feature": feat, "status": status_by_feat[feat],
             "evidence_hits": "|".join(hits_by_feat.get(feat, []))}
            for feat in sorted(status_by_feat)]


def ui_nodes(xml: str) -> List[Dict[str, Any]]:
    out = []
    for m in re.finditer(r"<node[^>]*?>", xml):
        node = m.group(0)
        text = re.search(r'text="([^"]*)"', node)
        desc = re.search(r'content-desc="([^"]*)"', node)
        bounds = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
        cls = re.search(r'class="([^"]+)"', node)
        tval = (text.group(1) if text else "") or (desc.group(1) if desc else "")
        if not tval or not bounds:
            continue
        x1, y1, x2, y2 = map(int, bounds.groups())
        out.append({"label": tval.strip(), "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2,
                    "cls": cls.group(1).split(".")[-1] if cls else ""})
    return out


def find_click(xml: str, want: str) -> Optional[Dict[str, Any]]:
    for n in ui_nodes(xml):
        if want.lower() in n["label"].lower():
            return n
    return None


# --- 权限弹窗识别（system dialog: 允许/仅限此应用时可用/不允许）---
PERM_BUTTONS = ("仅在使用该应用时允许", "使用应用时允许", "仅限该应用", "允许", "Allow",
                "仅限此应用", "使用期间允许")
PERM_DENY = "不允许"


def handle_permission_dialog(xml: str, serial: str) -> bool:
    """若当前 UI 是权限弹窗，点击允许类按钮，返回是否处理了。"""
    all_labels = [n["label"].strip() for n in ui_nodes(xml)]
    is_dialog = any(("允许" in l or "Allow" in l or "权限" in l or "permission" in l.lower()) for l in all_labels) and \
                any(("不允许" in l or "Don" in l or "Deny" in l) for l in all_labels)
    if not is_dialog:
        return False
    for btn in PERM_BUTTONS:
        tgt = find_click(xml, btn)
        if tgt:
            adb(serial, "shell", "input", "tap", str(tgt["cx"]), str(tgt["cy"]))
            time.sleep(1.5)
            return True
    return False


# --- 表单填充（缺口1）：find EditText/TextInput -> tap -> input text -> enter ---
def input_nodes(xml: str) -> List[Dict[str, Any]]:
    """可输入节点：class 含 EditText/TextInput 或 hint 非空且可聚焦。"""
    out = []
    for m in re.finditer(r"<node[^>]*?>", xml):
        node = m.group(0)
        cls = re.search(r'class="([^"]+)"', node)
        hint = re.search(r'hint="([^"]*)"', node)
        text = re.search(r'text="([^"]*)"', node)
        c = (cls.group(1) if cls else "")
        if c.split(".")[-1] not in ("EditText", "TextInput"):
            if not (hint and hint.group(1)) and not (text and text.group(1)):
                continue
            if "EditText" not in c and "TextInput" not in c:
                continue
        bounds = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
        if not bounds:
            continue
        x1, y1, x2, y2 = map(int, bounds.groups())
        out.append({"cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2,
                    "hint": hint.group(1) if hint else "",
                    "text": text.group(1) if text else ""})
    return out


def fill_field(serial: str, xml: str, want_hint: str, value: str) -> bool:
    """在当前 UI 找到 hint 匹配的输入框 -> tap -> input text -> enter。"""
    for n in input_nodes(xml):
        if want_hint and want_hint.lower() not in (n["hint"] or "").lower() and \
           want_hint.lower() not in (n["text"] or "").lower():
            continue
        adb(serial, "shell", "input", "tap", str(n["cx"]), str(n["cy"]))
        time.sleep(1.2)
        esc = value.replace(" ", "%s")
        adb(serial, "shell", "input", "text", esc)
        time.sleep(0.8)
        adb(serial, "shell", "input", "keyevent", "66")  # Enter
        time.sleep(1.2)
        return True
    return False


# --- 无文本可点节点（缺口3）：clickable 且无 label 的节点候补 ---
def tap_targets(xml: str) -> List[Dict[str, Any]]:
    """所有 clickable 节点（含无文本的图标按钮）。"""
    out = []
    for m in re.finditer(r"<node[^>]*?>", xml):
        node = m.group(0)
        cls = re.search(r'class="([^"]+)"', node)
        click = re.search(r'clickable="(\w+)"', node)
        bounds = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
        if not click or click.group(1) != "true" or not bounds:
            continue
        text = re.search(r'text="([^"]*)"', node)
        desc = re.search(r'content-desc="([^"]*)"', node)
        x1, y1, x2, y2 = map(int, bounds.groups())
        lab = (text.group(1) if text else "") or (desc.group(1) if desc else "")
        out.append({"cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2,
                    "label": lab.strip(),
                    "cls": cls.group(1).split(".")[-1] if cls else ""})
    return out


def pm_clear_and_relaunch(serial: str, pkg: str, act: str) -> None:
    """缺口2：清数据并重启，抓首启流程页。"""
    adb(serial, "shell", "pm", "clear", pkg)
    time.sleep(1.0)
    adb(serial, "shell", "am", "start", "-n", f"{pkg}/.{act}")
    time.sleep(6.0)


def snapshot(serial: str, tag: str, out_dir: Path, page_id: str,
             pkg: str = "", png: bool = True) -> Dict[str, Any]:
    d = out_dir / page_id
    d.mkdir(parents=True, exist_ok=True)
    adb(serial, "shell", "uiautomator", "dump", "/sdcard/ui.xml")
    (d / "ui.xml").write_text("", encoding="utf-8")
    adb(serial, "pull", "/sdcard/ui.xml", str(d / "ui.xml"))
    if not (d / "ui.xml").exists() or (d / "ui.xml").stat().st_size < 100:
        d.joinpath("ui.xml").write_text("<?xml version='1.0'?><hierarchy/><!--- empty --->", encoding="utf-8")
    ui_xml = (d / "ui.xml").read_text(encoding="utf-8", errors="replace") if (d / "ui.xml").exists() else ""
    # 处理权限弹窗：循环直到无(允许/不允许)对
    for _ in range(4):
        if not handle_permission_dialog(ui_xml, serial):
            break
        adb(serial, "shell", "uiautomator", "dump", "/sdcard/ui.xml")
        adb(serial, "pull", "/sdcard/ui.xml", str(d / "ui.xml"))
        ui_xml = (d / "ui.xml").read_text(encoding="utf-8", errors="replace")
        time.sleep(0.8)
    if png:
        adb(serial, "shell", "screencap", "-p", "/sdcard/sc.png")
        adb(serial, "pull", "/sdcard/sc.png", str(d / "screenshot.png"))
    fg = adb(serial, "shell", "dumpsys", "activity", "activities")
    m = re.search(r"topResumedActivity=.*?u0 (\S+)", fg)
    fg_comp = m.group(1) if m else ""
    # 固定屏幕参数（分辨率/密度），记录到证据，供 P4 对齐校验
    screen_size = ""
    screen_density = ""
    if pkg:
        size_out = adb(serial, "shell", "wm", "size")
        dm = re.search(r"(\d+x\d+)", size_out)
        screen_size = dm.group(1) if dm else ""
        dens_out = adb(serial, "shell", "wm", "density")
        dm2 = re.search(r"(\d+)", dens_out)
        screen_density = dm2.group(1) if dm2 else ""
    in_pkg = (pkg in fg_comp) if pkg else True
    return {
        "page_id": page_id, "tag": tag,
        "ui_sha256": sha256f(d / "ui.xml") if (d / "ui.xml").exists() else "",
        "png_sha256": sha256f(d / "screenshot.png") if (d / "screenshot.png").exists() else "",
        "foreground": fg_comp, "in_pkg": in_pkg,
        "screen_resolution": screen_size, "screen_density": screen_density,
        "xml": ui_xml or "",
    }


def bring_to_front(serial: str, pkg: str, act: str) -> str:
    """am start（不 force-stop）把 app 带回前台；返回当前 foreground。"""
    adb(serial, "shell", "am", "start", "-n", f"{pkg}/.{act}")
    time.sleep(3.0)
    fg = adb(serial, "shell", "dumpsys", "activity", "activities")
    m = re.search(r"topResumedActivity=.*?u0 (\S+)", fg)
    return m.group(1) if m else ""


def load_strings(project: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    targets = []
    res_dir = project / "app" / "src" / "main" / "res"
    if not res_dir.exists():
        res_dir = project / "res"
    if res_dir.exists():
        for sub in ("values", "values-zh", "values-zh-rCN"):
            targets.append(res_dir / sub / "strings.xml")
    for xml in targets:
        if not xml.exists():
            continue
        t = xml.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'<string name="([^"]+)"[^>]*>([^<]+)</string>', t):
            out[m.group(1)] = m.group(2).strip()
    return out


def anchor_for(page_symbol: str, strings: Dict[str, str]) -> List[str]:
    words = re.findall(r"[A-Z][a-z0-9]+", page_symbol)
    words = [w for w in words if len(w) >= 3 and w.lower() not in (
        "screen", "page", "dialog", "view", "activity", "route", "sheet", "fragment")]
    if not words:
        words = re.findall(r"[A-Za-z0-9]{3,}", page_symbol)
    anchors: List[str] = []
    for key, val in strings.items():
        kl = key.lower().lstrip("_")
        for w in words:
            if w.lower() in kl or kl in w.lower():
                if len(val) <= 40 and "%" not in val[:1]:
                    anchors.append(val)
                break
    return list(dict.fromkeys(anchors))


def ui_text_set(xml: str) -> set:
    return {n["label"] for n in ui_nodes(xml)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a | b) else 0.0


def pixel_diff(a_png: Path, b_png: Path) -> Optional[float]:
    try:
        from PIL import Image
        import numpy as np
        ia = Image.open(a_png).convert("L").resize((64, 64))
        ib = Image.open(b_png).convert("L").resize((64, 64))
        a = np.asarray(ia, dtype=np.float32)
        b = np.asarray(ib, dtype=np.float32)
        return float(np.abs(a - b).mean())
    except Exception:
        return None


def grant_permissions(serial: str, project: Path, pkg: str) -> int:
    """从 AndroidManifest 抓 uses-permission 并 pm grant；返回成功条数。"""
    perms = set()
    for mf in (project / "app" / "src" / "main" / "AndroidManifest.xml",):
        if not mf.exists():
            continue
        t = mf.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'android:name="([^"]+permission[^"]*)"', t):
            perms.add(m.group(1))
    granted = 0
    for perm in sorted(perms):
        r = adb(serial, "shell", "pm", "grant", pkg, perm)
        if "Exception" not in r and "Error" not in r and r.strip():
            granted += 1
    return granted


def sprintf_pid(sym: str, pid: str, hops: int) -> str:
    return f"STEP-{hops:02d}-{sym[:36]}"


def main() -> int:
    ap = argparse.ArgumentParser(description="gmi runtime bridge v4.1 (high-impact trimmed)")
    ap.add_argument("--project", required=True)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--package", required=True)
    ap.add_argument("--activity", default="MainActivity")
    ap.add_argument("--serial", default="emulator-5554")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--visits", default=None)
    ap.add_argument("--high-impact-only", action=argparse.BooleanOptionalAction, default=True,
                    help="只执行 behavior-contracts.csv 中 evidence_class=RUNTIME_REQUIRED 的集合"
                         "（默认开启；--no-high-impact-only 关闭回退全页行为）")
    ap.add_argument("--entry-labels", default=None,
                    help="主页入口（tab）标签，';' 或 ',' 分隔；缺省从"
                         " candidates/navigation-relations.candidates.csv 读取")
    ap.add_argument("--full-bfs", action="store_true",
                    help="可选：全页 BFS 级联探索（默认关闭，2.1 裁剪）")
    ap.add_argument("--all-screenshots", action="store_true",
                    help="可选：非高影响页也保存 screenshot.png（默认仅 ui.xml）")
    ap.add_argument("--max-hops", type=int, default=80)
    ap.add_argument("--stay", type=float, default=2.0)
    ap.add_argument("--back-after", action="store_true")
    ap.add_argument("--grant-perms", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--fill", default=None,
                    help="表单填充：hint:值;hint2:值2（进入页面后自动填）")
    ap.add_argument("--pm-clear", action="store_true",
                    help="先 pm clear 再启动（抓首启流程页 Guide/Welcome）")
    ap.add_argument("--explore", action="store_true",
                    help="探索模式：对无文本可点节点逐级点击（图标按钮），指纹去重防死循环")
    ap.add_argument("--screen-size", default="",
                    help="可选：设置模拟器分辨率（如 1080x2400）；缺省不再强制，仅采集当前值")
    ap.add_argument("--screen-density", default="",
                    help="可选：设置模拟器密度 dpi（如 440）；缺省不再强制，仅采集当前值")
    ap.add_argument("--mode", choices=("chain", "pages"), default="chain",
                    help="chain=行为链模式（v5.0 默认：BC operation_steps 驱动 + "
                         "result_assertions 结果断言，证据按 bc_id 组织）；"
                         "pages=旧页面模式（v4.2 VISITED 采集，保留兼容，不再是默认）")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    ws = Path(args.workspace)
    out_dir = ws / "runtime-evidence"
    pkg, serial, act = args.package, args.serial, args.activity
    cands = ws / "candidates"

    # ---- v5.0 行为链模式分叉（新范式默认；pages=旧页面模式保留兼容）----
    if args.mode == "chain":
        legacy_flags = [f for f, on in (("--auto", args.auto),
                                        ("--visits", args.visits),
                                        ("--full-bfs", args.full_bfs),
                                        ("--explore", args.explore),
                                        ("--fill", args.fill),
                                        ("--pm-clear", args.pm_clear)) if on]
        if legacy_flags:
            print(f"[chain] NOTE: {'/'.join(legacy_flags)} 属旧页面模式参数，"
                  "chain 模式忽略（页面导航由 BC page_ref 驱动；如需旧行为用 --mode pages）")
        return run_chain_mode(args, ws, out_dir)

    # ---- 2.1.1 高影响过滤：Page-ID 精确集合匹配（替代字符串归一化）----
    page_id_map = build_page_id_map(cands)
    bc_rows = load_behavior_contracts(ws)
    hi_scope: Optional[Dict[str, Any]] = None
    if bc_rows:
        scope = resolve_required_scope(bc_rows, page_id_map)
        if scope["unresolved"]:
            detail = "; ".join(f"{u['bc_id'] or '?'}:page_ref={u['page_ref'] or '(empty)'}"
                               for u in scope["unresolved"][:10])
            raise SystemExit(
                "[runtime] UNRESOLVED_PAGE_REF: 以下 RUNTIME_REQUIRED BC 无法映射到候选表正式 Page-ID\n"
                f"  {detail}\n"
                "  要求：behavior-contracts.csv.page_ref 必须直接使用 GMI 候选表正式 Page-ID，\n"
                "  或候选 manifest（candidates/inventory.candidates.csv）必须含对应映射；\n"
                "  fail-closed：不静默切换全页模式，退出非零")
        if not scope["pages"]:
            raise SystemExit("[runtime] RUNTIME_REQUIRED 集为空（无高影响过滤集）：正式路径拒绝执行；"
                             "调试可用 --no-high-impact-only")
        if bool(args.high_impact_only):
            hi_scope = scope
            print(f"[high-impact] behavior-contracts rows={len(bc_rows)}"
                  f" required_pages(Page-ID 精确集)={len(scope['pages'])}: 只实跑 RUNTIME_REQUIRED 集")
        else:
            print("[high-impact] --no-high-impact-only（调试开关）：全页采集；"
                  "正式高影响过滤仍以 Page-ID 精确集为准，不因本开关豁免")
    else:
        if args.high_impact_only:
            print("[high-impact] WARNING: behavior-contracts.csv 缺失，回退旧行为（全页）；"
                  "建议先跑 scripts/build_behavior_contracts.py")
    is_high_impact = make_hi_predicate(hi_scope, page_id_map)

    def want_png(name: str) -> bool:
        # 非高影响页面不再保存 screenshot.png（仅 ui.xml），除非显式开启 --all-screenshots
        return args.all_screenshots or hi_scope is None or is_high_impact(name)

    if args.grant_perms:
        n = grant_permissions(serial, Path(args.project), pkg)
        print(f"[perms] granted {n} permissions for {pkg}")

    # 屏幕元数据（2.1：仅复现实验元数据，不再强制设置；失败不阻塞，只记录）
    if args.screen_size:
        r = adb(serial, "shell", "wm", "size", args.screen_size)
        print(f"[screen] optional set size={args.screen_size} rc={'ERR' if r.startswith('__ERR__') else 'ok'}")
        time.sleep(0.8)
    if args.screen_density:
        r = adb(serial, "shell", "wm", "density", args.screen_density)
        print(f"[screen] optional set density={args.screen_density} rc={'ERR' if r.startswith('__ERR__') else 'ok'}")
        time.sleep(1.5)
    cur_size = adb(serial, "shell", "wm", "size")
    cur_den = adb(serial, "shell", "wm", "density")
    cur_size = "" if cur_size.startswith("__ERR__") else cur_size.strip().replace("\n", " ")
    cur_den = "" if cur_den.startswith("__ERR__") else cur_den.strip().replace("\n", " ")
    print(f"[screen] metadata (reproducibility only): {cur_size or 'unavailable'} / {cur_den or 'unavailable'}")

    if args.pm_clear:
        pm_clear_and_relaunch(serial, pkg, act)
    else:
        adb(serial, "shell", "am", "start", "-n", f"{pkg}/.{act}")
        time.sleep(6)

    ev: List[Dict[str, Any]] = []
    gate_rows: List[Dict[str, Any]] = []
    visited: set = set()

    if args.auto:
        project = Path(args.project)
        strings = load_strings(project)

        seen_pages: Dict[str, str] = {}
        for r in read_csv(cands / "phase-2-completeness.csv"):
            pym = r.get("page_symbol", "")
            if pym and pym not in ("", "MainActivity"):
                seen_pages[pym] = pym
        for r in read_csv(cands / "inventory.candidates.csv"):
            pid = r.get("page_id", "")
            if not pid:
                continue
            m = re.match(r"PAGE-([A-Za-z0-9]+(?:Screen|Page|Activity|Dialog|View|Sheet)?)", pid)
            sym = "".join(w.capitalize() for w in re.findall(r"[A-Za-z]+", m.group(1) if m else "")[:3])
            if not sym:
                sym = m.group(1) if m else pid
            if sym and sym not in seen_pages and sym != "MainActivity":
                seen_pages[sym] = sym
        for r in read_csv(cands / "page-fields.candidates.csv"):
            pym = r.get("page_symbol", "")
            if pym and pym not in ("", "MainActivity"):
                seen_pages.setdefault(pym, pym)
        pages = list(seen_pages.keys())
        if hi_scope is not None:
            before = len(pages)
            pages = [p for p in pages if is_high_impact(p)]
            print(f"[high-impact] candidate pages {before} -> {len(pages)}"
                  f"（Page-ID 精确集，仅 RUNTIME_REQUIRED）")
            if not pages:
                raise SystemExit(
                    "[runtime] 高影响过滤恒 0 命中：无候选页可解析到 RUNTIME_REQUIRED Page-ID 精确集；"
                    "正式路径拒绝静默全页回退。检查 candidates/inventory.candidates.csv 映射与"
                    "behavior-contracts.csv.page_ref；调试可用 --no-high-impact-only")
        print(f"[auto] candidate pages={len(pages)} (strings={len(strings)})")

        home_xml = snapshot(serial, "main0", out_dir, "PAGE-LAUNCH", pkg)["xml"]
        prio = []
        for p in pages:
            for a in anchor_for(p, strings):
                if find_click(home_xml, a):
                    prio.append(p)
                    break
        rest = [p for p in pages if p not in prio]
        pages = prio + rest
        print(f"[auto] priority-anchored={len(prio)}")

        home = snapshot(serial, "main", out_dir, "PAGE-LAUNCH", pkg)
        ev.append({k: v for k, v in home.items() if k != "xml"})
        gate_rows.append({"page_id": "PAGE-LAUNCH", "symbol": act, "status": "VISITED",
                          "evidence": "PAGE-LAUNCH/ui.xml"})
        visited.add(act)
        cur_xml = home["xml"]

        # 主页可点旅程（抓证据兜底；tab 间切换不需 BACK，back 会退出 app）
        # 2.1：入口标签来自 --entry-labels 或 navigation-relations 候选表，不再写死。
        entry_labels: List[str] = []
        if args.entry_labels:
            entry_labels = [l.strip() for l in re.split(r"[;,]", args.entry_labels) if l.strip()]
        if not entry_labels:
            for r in read_csv(cands / "navigation-relations.candidates.csv"):
                trig = (r.get("trigger") or "").strip()
                rel = f"{r.get('relation_type', '')} {r.get('action', '')}".upper()
                if trig and ("TAB" in rel or "BOTTOM" in rel or "NAV" in rel):
                    entry_labels.append(trig)
            entry_labels = list(dict.fromkeys(entry_labels))
        # 2.1.1：入口标签是导航手段（非页面），不按 Page-ID 集裁剪；
        # 高影响过滤在候选页面层精确生效。
        if not entry_labels:
            raise SystemExit("[runtime] 无主页入口标签：请用 --entry-labels \"标签;标签2\" 显式指定，"
                             "或确认 candidates/navigation-relations.candidates.csv 含 tab/nav 触发；"
                             "2.1 已移除硬编码标签列表")
        for lab in entry_labels:
            tgt = find_click(home_xml, lab)
            if tgt:
                adb(serial, "shell", "input", "tap", str(tgt["cx"]), str(tgt["cy"]))
                time.sleep(args.stay + 1.5)
                pid = f"TAB-{re.sub(r'[^A-Za-z0-9]', '', lab)[:20]}"
                snap = snapshot(serial, lab, out_dir, pid, pkg, png=want_png(lab))
                if snap["in_pkg"]:
                    ev.append({k: v for k, v in snap.items() if k != "xml"})
                    gate_rows.append({"page_id": pid, "symbol": lab, "status": "VISITED",
                                      "evidence": f"{pid}/ui.xml"})
                    visited.add(lab)
                else:
                    ev.append({k: v for k, v in snap.items() if k != "xml"})
                    gate_rows.append({"page_id": pid, "symbol": lab, "status": "EXITED",
                                      "evidence": f"{pid}/ui.xml"})
                    bring_to_front(serial, pkg, act)
                cur_xml = snapshot(serial, "root", out_dir, "PAGE-ROOT", pkg)["xml"]

        # 级联 BFS：每步把「当前 UI 里存在的锚点文本」作为跳转机会（2.1：--full-bfs 才启用）
        if args.full_bfs:
            pending = [p for p in pages if p not in visited]
        else:
            pending = []
            print("[auto] --full-bfs 关闭：跳过全页 BFS 级联（高影响裁剪；需要时显式开启）")
        hops = 0
        while pending and hops < args.max_hops:
            hops += 1
            clicked = False
            for sym in list(pending):
                if sym in visited:
                    continue
                for a in anchor_for(sym, strings):
                    tgt = find_click(cur_xml, a)
                    if tgt:
                        adb(serial, "shell", "input", "tap", str(tgt["cx"]), str(tgt["cy"]))
                        time.sleep(args.stay + 1.5)
                        pid = f"STEP-{hops:02d}-{re.sub(r'[^A-Za-z0-9]', '', sym)[:30]}"
                        snap = snapshot(serial, sym, out_dir, pid, pkg, png=want_png(sym))
                        if snap["in_pkg"]:
                            gate_rows.append({"page_id": pid, "symbol": sym, "status": "VISITED",
                                              "evidence": f"{pid}/ui.xml"})
                            visited.add(sym)
                        else:
                            # 掉出 app（点到了别处/退出）：标 EXITED，绝不当作到达
                            gate_rows.append({"page_id": pid, "symbol": sym, "status": "EXITED",
                                              "evidence": f"{pid}/ui.xml"})
                            bring_to_front(serial, pkg, act)
                            cur_xml = snapshot(serial, "root", out_dir, "PAGE-ROOT", pkg)["xml"]
                            break
                        ev.append({k: v for k, v in snap.items() if k != "xml"})
                        cur_xml = snap["xml"]
                        adb(serial, "shell", "input", "keyevent", "4")
                        time.sleep(2.0)
                        back_snap = snapshot(serial, "back", out_dir, "PAGE-BACK", pkg)
                        ev.append({k: v for k, v in back_snap.items() if k != "xml"})
                        if not back_snap["in_pkg"]:
                            # BACK 把 app 退到桌面了：拉回来
                            fg = bring_to_front(serial, pkg, act)
                        back2 = snapshot(serial, "root2", out_dir, "PAGE-ROOT", pkg)
                        if back2["in_pkg"]:
                            cur_xml = back2["xml"]
                        else:
                            cur_xml = back_snap["xml"]
                        print(f"[auto] {hops}. {sym} -> visited")
                        clicked = True
                        break
                if clicked:
                    break
            if not clicked:
                break

        unreach = [p for p in pending if p not in visited]
        print(f"[auto] finished. visited={len(visited)} not_entered={len(unreach)}")
        for p in unreach:
            gate_rows.append({"page_id": "", "symbol": p, "status": "NOT_ENTERED",
                              "evidence": "(route hints below)"})
        # 路由提示单
        hint_rows = []
        for p in unreach:
            anchors = anchor_for(p, strings)
            hint_rows.append({"symbol": p,
                              "anchors": " / ".join(anchors[:4]) if anchors else "(no anchor; try from screenshots)",
                              "hint": "需人工：从主页逐层点入（锚点文字见下）"})
        write_csv(out_dir / "route-hints.csv", ["symbol", "anchors", "hint"], hint_rows)

        # ---- 表单填充（缺口1）：对当前页填 --fill 指定字段（造数据以便打开详情）----
        if args.fill:
            for item in args.fill.split(";"):
                parts = item.strip().split(":")
                if len(parts) >= 2:
                    hint, val = parts[0].strip(), ":".join(parts[1:]).strip()
                    if fill_field(serial, cur_xml, hint, val):
                        print(f"[fill] '{hint}' <- '{val[:20]}'")
                    else:
                        print(f"[fill] MISS hint='{hint}'")
            time.sleep(1.5)
            cur_xml = snapshot(serial, "afterfill", out_dir, "PAGE-AFTERFILL", pkg)["xml"]

        # ---- 探索模式（缺口3）：对无文本可点节点逐级点击，指纹去重 ----
        if args.explore:
            seen_fp = {hashlib.sha256(cur_xml.encode()).hexdigest()}
            hop = 0
            while hop < args.max_hops:
                hop += 1
                targets = [t for t in tap_targets(cur_xml) if t["cx"] > 0]
                if not targets:
                    break
                acted = False
                for t in targets:
                    adb(serial, "shell", "input", "tap", str(t["cx"]), str(t["cy"]))
                    time.sleep(args.stay + 1.2)
                    snapx = snapshot(serial, f"explore{hop}", out_dir, f"EXPLORE-{hop:02d}-{t['cls']}", pkg)
                    fp = snapx["xml"]
                    fp_hash = hashlib.sha256(fp.encode()).hexdigest()
                    if fp_hash in seen_fp:
                        adb(serial, "shell", "input", "keyevent", "4")
                        time.sleep(1.2)
                        continue
                    seen_fp.add(fp_hash)
                    ev.append({k: v for k, v in snapx.items() if k != "xml"})
                    gate_rows.append({"page_id": snapx["page_id"], "symbol": t["label"] or t["cls"],
                                      "status": "VISITED" if snapx["in_pkg"] else "EXITED",
                                      "evidence": f"{snapx['page_id']}/ui.xml"})
                    print(f"[explore] {hop}. tap {t['label'][:12] or t['cls']} -> {snapx['page_id']} "
                          f"{'VISITED' if snapx['in_pkg'] else 'EXITED'}")
                    acted = True
                    adb(serial, "shell", "input", "keyevent", "4")
                    time.sleep(1.2)
                if not acted:
                    break
                cur_xml = snapshot(serial, "root", out_dir, "PAGE-ROOT", pkg)["xml"]
                print(f"[explore] round {hop} done, targets={len(targets)}")
    else:
        visits = []
        if args.visits:
            for item in args.visits.split(";"):
                parts = item.strip().split(":")
                if len(parts) >= 2:
                    visits.append((parts[0].strip(), float(parts[1]) if parts[1].strip().replace(".", "").isdigit() else 2.0))
        if hi_scope is not None and visits:
            kept = [(l, s) for (l, s) in visits if is_high_impact(l)]
            skipped = [l for (l, s) in visits if (l, s) not in kept]
            if skipped:
                print(f"[high-impact] visits 过滤掉 {len(skipped)} 个非 RUNTIME_REQUIRED 标签："
                      f"{', '.join(skipped[:8])}")
            if not kept:
                raise SystemExit(
                    "[runtime] --visits 全部未命中 RUNTIME_REQUIRED Page-ID 精确集（过滤恒 0 命中）："
                    "正式路径拒绝静默执行；请修正 --visits 标签为候选表页面符号，"
                    "或调试用 --no-high-impact-only")
            visits = kept
        cap = snapshot(serial, "main", out_dir, "PAGE-LAUNCH", pkg)
        ev.append({k: v for k, v in cap.items() if k != "xml"})
        gate_rows.append({"page_id": "PAGE-LAUNCH", "symbol": act, "status": "VISITED",
                          "evidence": "PAGE-LAUNCH/ui.xml"})
        cur_xml = cap["xml"]
        for i, (label, stay) in enumerate(visits, start=1):
            tgt = find_click(cur_xml, label)
            if not tgt:
                print(f"[visit] MISS '{label}'")
                continue
            adb(serial, "shell", "input", "tap", str(tgt["cx"]), str(tgt["cy"]))
            time.sleep(stay + 2.0)
            pid = f"STEP-{i:02d}-{re.sub(r'[^A-Za-z0-9]', '-', label)[:24]}"
            snap = snapshot(serial, label, out_dir, pid, png=want_png(label))
            ev.append({k: v for k, v in snap.items() if k != "xml"})
            gate_rows.append({"page_id": pid, "symbol": label, "status": "VISITED",
                              "evidence": f"{pid}/ui.xml"})
            cur_xml = snap["xml"]

    # ---- 2.1.2 RUNTIME_REQUIRED 页面级 behavior-evidence 采集（--auto + 高影响过滤激活）----
    if args.auto and hi_scope is not None and bc_rows:
        stats = capture_behavior_evidence(
            serial, pkg, act, out_dir, ws, Path(args.project),
            hi_scope, page_id_map, bc_rows, ev, gate_rows, args.stay,
            verbose=args.verbose)
        print(f"[behavior-capture] visited={stats['visited']} "
              f"not_entered={stats['not_entered']} (RUNTIME_REQUIRED Page-ID 精确集)")

    write_csv(out_dir / "evidence-index.csv",
              ["page_id", "tag", "foreground", "ui_sha256", "png_sha256", "screen_resolution", "screen_density"], ev)
    write_csv(out_dir / "runtime-gate.csv",
              ["page_id", "symbol", "status", "evidence"], gate_rows)

    # ---- feature 口径覆盖表（gmi_phase3_adapter 消费，14d：从 gate 行派生）----
    feat_by_pid: Dict[str, str] = {}
    for r in read_csv(cands / "inventory.candidates.csv"):
        _pid = (r.get("page_id") or "").strip()
        _feat = (r.get("feature_id") or "").strip()
        if _pid and _feat:
            feat_by_pid.setdefault(_pid, _feat)
    write_csv(out_dir / "runtime-feature-coverage.csv",
              FEATURE_COVERAGE_FIELDS,
              build_feature_coverage_rows(gate_rows, page_id_map, feat_by_pid))

    if args.compare:
        comp = []
        prev_ui: Dict[str, set] = {}
        for e in ev:
            pid = e["page_id"]
            d = out_dir / pid
            ui_p = d / "ui.xml"
            png_p = d / "screenshot.png"
            tset = set()
            if ui_p.exists():
                tset = ui_text_set(ui_p.read_text(encoding="utf-8", errors="replace"))
            for opid, oset in prev_ui.items():
                j = jaccard(tset, oset)
                pd = pixel_diff(png_p, out_dir / opid / "screenshot.png") if png_p.exists() else None
                if j < 0.97 or (pd is not None and pd > 12):
                    comp.append({"page_id": pid, "vs": opid,
                                 "text_jaccard": f"{j:.2f}",
                                 "pixel_diff": f"{pd:.1f}" if pd is not None else ""})
            prev_ui[pid] = tset
        write_csv(out_dir / "compare.csv",
                  ["page_id", "vs", "text_jaccard", "pixel_diff"], comp)
        print(f"[compare] distinct-diff rows={len(comp)}")

    v = sum(1 for g in gate_rows if g["status"] == "VISITED")
    ne = sum(1 for g in gate_rows if g["status"] == "NOT_ENTERED")
    print(f"[runtime] visited={v} not_entered={ne} evidence={len(ev)} out={out_dir}")

    # ---- 2.1.1 行为证据索引：每个 RUNTIME_REQUIRED BC 一行，证据不齐->非零 ----
    if bc_rows:
        if build_behavior_evidence_index(ws, out_dir, bc_rows, page_id_map, gate_rows) != 0:
            print("[runtime] FAIL: RUNTIME_REQUIRED BC 证据不齐（见 behavior-evidence-index.csv，"
                  "status 非 COMPLETE），退出非零")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
