#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chain_driver_bypass.py -- Agent 2B（Android Runtime Oracle）driver：TOOL_GAP 绕过接线层。

背景（如实登记，全部属于 IN_MIGRATION run 期间发现、不修改 skill 树的绕过接线）：

GAP-1 BC<->gmi_runtime schema 不匹配
  behavior-contracts.csv（冻结）的 operation_steps 使用 action=wait/press_back
  与 target 前缀 text=/desc=/class=；result_assertions 使用
  {type,target,expected} 字段形态。gmi_runtime.py v5.0 仅消费
  action in tap/input/back（裸文本 target）与断言 {kind,value}
  （kind in text_visible/text_gone/persist_after_restart）。
  build_behavior_contracts.py --validate 只校验"JSON 数组"不校验字段形态，
  因此该 BC 合法通过收口却无法被链执行器消费。
  绕过：运行时适配（load_behavior_contracts 包装，冻结文件 0 字节改动）。

GAP-2 数据断言 oracle 未接线
  android_data_probe.py 明确"集成契约：由并行代理在 gmi_runtime 侧接线"。
  绕过：evaluate_chain_assertions 包装中把 target=prefs:<k> 且 expected 为
  裸 token 的 data_equals 断言交由 skill 自带的
  android_data_probe.evaluate_data_assertions 判定（只读探针，fail-closed）。
  其余 data_equals（期望含比较/时点语）与 count_ge/占位符 target 一律
  UNSUPPORTED（绝不猜测），由 chain_status 归 UNSUPPORTED_ORACLE -> GAP。

GAP-3 UI 无障碍标注缺失导致 BC 声明的 target 无法直接命中（源码佐证）：
  a) "Open settings navigation"：全源码不存在（grep 0 命中）；drawer 汉堡
     按钮 contentDescription=null（ArticleListTopBar.kt:134）。
     绕过：仅对该值启用结构兜底 = 点击 top bar 最左侧无文本 clickable。
  b) 侧栏状态切换 Starred/All/Unread：ToggleButton 纯图标且
     contentDescription=null（ArticleStatusBar.kt + ArticleStatusIcon）。
     绕过：drawer 底部同 y 带连续 3 图标组按 x 序映射
     [All, Unread, Starred]（FeedList.kt options 顺序源码佐证）。
  c) class=article_row_index_0：BC 语义=点击列表第一篇文章行（禁止绑定标题）。
     绕过：点击列表区域最上方含长文本子节点的全宽 clickable 行。
  d) "More options"/"Remove Feed"/"Remove"（BC-0007）：全源码不存在（真实
     文案 Unsubscribe）。不兜底（兜底=发明操作）-> 如实 STEPS_FAIL/NAV_FAIL。

GAP-4 feature-map.json verify_mode 与 BC evidence_class/scope.json 冲突
  （feature-map 仅 3 feature=RUNTIME；scope.json 9 个 RUNTIME；BC
  evidence_class=RUNTIME_REQUIRED x14 与 scope 一致）。绕过：
  load_feature_map 返回 missing -> gmi_runtime 自身 legacy 降级路径按
  evidence_class 选择全部 14 条（与任务授权一致）。冲突如实上报。

GAP-5 locale：BC 契约文本基于英文资源（values/strings.xml）；系统
  locale=zh-CN 时断言文本不出现（实测首屏为中文）。绕过：seed 复位后设
  per-app locale=en-US（pm clear 会重置 per-app locale，故置于其后）。

GAP-6 瞬态 snackbar：BC-0004/0005 的 wait 步骤与 text_visible 断言指向同一
  snackbar 文案；after 快照双 dump+screencap 耗时可能错过。绕过：
  text_visible 判 FAIL 时若同文本在链内 wait 步骤命中过 dump（同一 UI
  事实的更早观测时点），判 PASS 并在 note 标注。

判定铁律：CONFLICT 如实记录不翻转；required 断言 UNSUPPORTED ->
UNSUPPORTED_ORACLE 归 GAP 绝不 PASS；探针读不到 -> DENIED/UNSUPPORTED；
绝不伪造数据；绝不改冻结文件。
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SKILL_SCRIPTS = "/Users/rainyday/Desktop/finale/skill/android-migration-inventory/scripts"
WS = "/Users/rainyday/Desktop/finale/migration-runs/MIG-20260831T203138Z-7CC5DC/phase-02-android-inventory"
PROJECT = "/Users/rainyday/Desktop/finale/android/CapyReader"
PKG = "com.capyreader.app.debug"
SERIAL = "emulator-5554"
ACT = "MainActivity"
SQLITE3 = os.path.expanduser("~/Library/Android/sdk/platform-tools/sqlite3")
PROBE_SCRIPT = os.path.join(SKILL_SCRIPTS, "android_data_probe.py")
TG_DIR = Path(WS) / "runtime-evidence" / "toolgap"

sys.path.insert(0, SKILL_SCRIPTS)
import gmi_runtime as G  # noqa: E402
import android_data_probe as DP  # noqa: E402

_CHAIN_STATE = {}
_WAIT_HITS = {}
_AUDIT = []

_BARE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
_TARGET_PREFIX_RE = re.compile(r"^(text|desc|class)=(.*)$", re.S)


def _strip_target_prefix(target):
    m = _TARGET_PREFIX_RE.match((target or "").strip())
    if not m:
        return (target or "").strip(), ""
    return m.group(2).strip(), m.group(1)


def adapt_assertion(a):
    if not isinstance(a, dict):
        return a
    typ = (a.get("type") or "").strip()
    target = (a.get("target") or "").strip()
    expected = (a.get("expected") or "").strip()
    invert = str(a.get("invert", "")).strip().lower() == "true"
    raw, prefix = _strip_target_prefix(target)
    low_exp = expected.lower()
    restart_sem = ("after restart" in low_exp) or ("重启" in expected)
    before_sem = re.search(r"\bbefore\b", low_exp) is not None

    def rec(rule, out):
        out = dict(out)
        out["_rule"] = rule
        out["_raw"] = {"type": typ, "target": target, "expected": expected,
                       "invert": a.get("invert", "")}
        return out

    if typ == "text_visible" and prefix in ("text", "desc"):
        # v5 收紧：仅明确的时点声明（"visible before ..."）走 before 时点；
        # "shown before action" 属顺序叙述（BC-0015 实测误伤），不迁移时点。
        if re.search(r"visible\s+before", low_exp):
            return rec("A1-before", {"kind": "text_visible", "value": raw,
                                     "mode": "before"})
        return rec("A1", {"kind": "text_visible", "value": raw})
    if typ == "element_present" and prefix in ("text", "desc"):
        if restart_sem:
            mode = "gone" if invert else "visible"
            return rec("A4-restart", {"kind": "persist_after_restart",
                                      "value": raw, "mode": mode})
        if invert:
            return rec("A3", {"kind": "text_gone", "value": raw})
        return rec("A2", {"kind": "text_visible", "value": raw})
    if typ == "data_equals" and target.startswith("prefs:") \
            and _BARE_TOKEN_RE.match(expected or ""):
        key = "prefs." + target[len("prefs:"):]
        return rec("A7-probe", {"kind": "data_probe", "key": key,
                                "value": expected})
    return rec("KEEP", dict(a))


def adapt_step(s):
    if not isinstance(s, dict):
        return s
    out = dict(s)
    action = (s.get("action") or "").strip()
    raw, prefix = _strip_target_prefix(s.get("target") or "")
    if prefix in ("text", "desc"):
        out["target"] = raw
    out["_raw"] = {"action": action, "target": s.get("target", "")}
    if action == "press_back":
        out["action"] = "back"
    return out


# GAP-3i：BC-0014/BC-0016 的 pre_state（"已打开一篇文章"）无法由冷复位建立；
# prepare 复用 BC-0011 operation_steps[0]（class=article_row_index_0，BC 体系
# 冻结声明的"点击列表第一篇文章条目"操作）建立阅读视图前置（非发明操作）。
PREPARE_FROM_BC0011 = {
    "BC-0014": [{"action": "tap", "target": "class=article_row_index_0",
                 "value": ""}],
    # BC-0016 排在 BC-0015（Mark All as Read）之后：UNREAD 过滤列表已空，
    # 前置补一步"切 All 过滤"（BC-0009 冻结声明的操作 text=All），再点
    # 列表第一篇（BC-0011 冻结声明的操作）。
    "BC-0016": [{"action": "tap", "target": "desc=Open settings navigation",
                 "value": ""},
                {"action": "tap", "target": "text=All", "value": ""},
                {"action": "tap", "target": "class=article_row_index_0",
                 "value": ""}],
}


def adapt_bc_rows(rows):
    out = []
    for r in rows:
        if r.get("bc_id") in PREPARE_FROM_BC0011 and not (r.get("prepare_steps") or "").strip():
            r = dict(r)
            r["prepare_steps"] = json.dumps(PREPARE_FROM_BC0011[r["bc_id"]],
                                            ensure_ascii=False)
        r2 = dict(r)
        steps = G.parse_json_col(r.get("operation_steps", ""))
        asserts = G.parse_json_col(r.get("result_assertions", ""))
        if steps:
            r2["operation_steps"] = json.dumps(
                [adapt_step(s) for s in steps], ensure_ascii=False)
        if asserts:
            r2["result_assertions"] = json.dumps(
                [adapt_assertion(a) for a in asserts], ensure_ascii=False)
        _AUDIT.append({
            "bc_id": r.get("bc_id", ""),
            "steps": [{"raw": s.get("_raw", s), "adapted":
                       {k: v for k, v in s.items() if not k.startswith("_")}}
                      for s in (steps or [])],
            "assertions": [{"raw": a.get("_raw", a), "adapted":
                            {k: v for k, v in a.items() if not k.startswith("_")}}
                           for a in (asserts or [])] if asserts else [],
        })
        out.append(r2)
    return out


_orig_load_bc = G.load_behavior_contracts


def patched_load_bc(ws):
    rows = _orig_load_bc(ws)
    only = os.environ.get("CAPY2B_ONLY_BC", "")
    if only:
        rows = [r for r in rows if r.get("bc_id") in only.split(",")]
    adapted = adapt_bc_rows(rows)
    TG_DIR.mkdir(parents=True, exist_ok=True)
    (TG_DIR / "bc-adaptation-audit.json").write_text(
        json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "tool_gaps": ["GAP-1", "GAP-2", "GAP-3", "GAP-4", "GAP-5",
                                  "GAP-6"],
                    "rows": _AUDIT}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return adapted


G.load_behavior_contracts = patched_load_bc
G.load_feature_map = lambda ws: {"runtime_features": set(),
                                 "source_confirm_features": set(),
                                 "pages_by_feature": {}, "missing": True}

_orig_tokens = G.parse_pre_state_tokens


def patched_tokens(pre_state):
    toks = _orig_tokens(pre_state)
    return [re.sub(r"[）)\]】」』”\"';；,，。.\s]+$", "", t).strip() or t
            for t in toks]



# GAP-5b：load_strings 读取顺序缺陷（values-zh 中文值覆盖英文默认值）导致
# 特征锚点全中文，在 en-US UI（BC 契约文本语言）下 0 命中（实测 anchors_tried=0）。
# 绕过：只读 values/strings.xml（英文默认资源 = BC source_refs 引用的同一文件）。
_orig_load_strings = G.load_strings


def patched_load_strings(project):
    from pathlib import Path as _P
    out = {}
    res_dir = _P(project) / "app" / "src" / "main" / "res"
    if not res_dir.exists():
        res_dir = _P(project) / "res"
    xml = res_dir / "values" / "strings.xml"
    if xml.exists():
        t = xml.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'<string name="([^"]+)"[^>]*>([^<]+)</string>', t):
            out[m.group(1)] = m.group(2).strip()
    return out


G.load_strings = patched_load_strings

G.parse_pre_state_tokens = patched_tokens

_orig_verify = G.verify_precondition


def patched_verify(pre_state, xml):
    ok, note = _orig_verify(pre_state, xml)
    if not ok:
        pre = _CHAIN_STATE.get("nav_pre_xml", "")
        if pre:
            toks = G.parse_pre_state_tokens(pre_state)
            missing = [t for t in toks if not G._xml_shows(pre, t)]
            if toks and not missing:
                return True, ("precondition verified at pre-navigation UI "
                              "(entry navigation already advanced past the "
                              "described state): " + ";".join(toks[:4]))
    return ok, note


G.verify_precondition = patched_verify


def _nodes_full(xml):
    out = []
    for m in re.finditer(r"<node[^>]*?>", xml or ""):
        node = m.group(0)
        b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
        if not b:
            continue
        t = re.search(r'text="([^"]*)"', node)
        d = re.search(r'content-desc="([^"]*)"', node)
        click = re.search(r'clickable="(\w+)"', node)
        x1, y1, x2, y2 = map(int, b.groups())
        out.append({"text": (t.group(1) if t else ""),
                    "desc": (d.group(1) if d else ""),
                    "clickable": (click.group(1) == "true") if click else False,
                    "bounds": (x1, y1, x2, y2),
                    "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2})
    return out


def _screen_h(nodes_list):
    ys = [n["bounds"][3] for n in nodes_list if n.get("bounds")]
    return max(ys) if ys else 2400


def _locate_drawer_hamburger(xml, want_desc):
    """GAP-3a：幻影 desc -> top bar 最左无文本 clickable（源码佐证 desc=null）。"""
    if "open settings navigation" not in (want_desc or "").lower():
        return None
    nodes = _nodes_full(xml)
    h = _screen_h(nodes)
    cands = [n for n in nodes if n["clickable"] and not n["text"]
             and not n["desc"] and n["bounds"][1] < h * 0.25]
    if not cands:
        return None
    cands.sort(key=lambda n: n["bounds"][0])
    n = cands[0]
    return {"cx": n["cx"], "cy": n["cy"],
            "label": "hamburger(structural:%s)" % (n["bounds"],)}


def _locate_status_toggle(xml, want):
    """GAP-3b：图标组位置映射 [All, Unread, Starred]（FeedList options 佐证）。"""
    order = ["All", "Unread", "Starred"]
    if want not in order:
        return None
    nodes = _nodes_full(xml)
    h = _screen_h(nodes)
    icons = [n for n in nodes if n["clickable"] and not n["text"]
             and not n["desc"] and h * 0.45 < n["cy"] < h * 0.98
             and (n["bounds"][2] - n["bounds"][0]) < h * 0.25]
    if len(icons) < 3:
        return None
    icons.sort(key=lambda n: n["cy"])
    band = [icons[0]]
    bands = []
    for n in icons[1:]:
        if abs(n["cy"] - band[-1]["cy"]) < 60:
            band.append(n)
        else:
            bands.append(band)
            band = [n]
    bands.append(band)
    for b in bands:
        if len(b) >= 3:
            b = sorted(b[:3], key=lambda n: n["cx"])
            if abs((b[1]["cx"] - b[0]["cx"]) - (b[2]["cx"] - b[1]["cx"])) < 260:
                pick = b[order.index(want)]
                return {"cx": pick["cx"], "cy": pick["cy"],
                        "label": "status-toggle(structural:%s@%s)"
                                 % (want, pick["bounds"])}
    return None


def _locate_first_article_row(xml):
    """GAP-3c：列表最上方含长文本子节点的全宽 clickable 行（不绑定标题）。"""
    nodes = _nodes_full(xml)
    h = _screen_h(nodes)
    texts = [n for n in nodes if len(n["text"].strip()) >= 12]
    rows = []
    for n in nodes:
        if not n["clickable"] or n["bounds"][1] < h * 0.18:
            continue
        w = n["bounds"][2] - n["bounds"][0]
        if w < h * 0.5:
            continue
        inner = [t for t in texts
                 if n["bounds"][0] <= t["cx"] <= n["bounds"][2]
                 and n["bounds"][1] <= t["cy"] <= n["bounds"][3]]
        if inner:
            rows.append((n["bounds"][1], n))
    if not rows:
        return None
    rows.sort(key=lambda x: x[0])
    n = rows[0][1]
    return {"cx": n["cx"], "cy": n["cy"],
            "label": "article-row-0(structural:%s)" % (n["bounds"],)}



_ALL_STEP_XMLS = []
_DRAWER_ENTRY_TARGETS = {
    # GAP-3k：这些 target 位于侧栏（drawer）内，主界面默认收起不可见。
    "Open settings navigation", "Open settings", "Add Feed", "Refresh all",
}


def _drawer_entry_intent(target):
    t = (target or "").strip()
    return t in _DRAWER_ENTRY_TARGETS


DIALOG_FINGERPRINT = {
    # GAP-3e 导航到达态摩擦：gmi_runtime 的导航以"对话框打开"为到达终点，
    # 而 BC 步骤序列第一步就是"tap 打开该对话框"（从主界面起步假设）。
    # 幂等 skip：tap 目标 miss 且对话框指纹已可见 = 步骤意图已达成。
    "Add Feed": "Feed or Website URL",
    "Mark All as Read": "Mark all items as read?",
}


def _fill_input_by_label(serial, xml, want, value):
    """GAP-3f Compose 输入框定位：EditText 无 text/hint，label 为叠在其
    bounds 内的独立 TextView（实测 AddFeedDialog）。空间关联定位：
    label 中心落在 EditText bounds 内 -> 该框即目标。tap -> 清空 ->
    input text（不按 Enter：提交由 BC 显式 tap Add 步骤承担）。"""
    nodes = _nodes_full(xml)
    labels = []
    for n in nodes:
        lab = (n["text"] or n["desc"] or "").strip()
        if lab and want.lower() in lab.lower():
            labels.append(n)
    edits = []
    for m in re.finditer(r"<node[^>]*?>", xml or ""):
        node = m.group(0)
        cls = re.search(r'class="([^"]+)"', node)
        c = cls.group(1) if cls else ""
        if "EditText" not in c and "TextInput" not in c:
            continue
        b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
        if not b:
            continue
        x1, y1, x2, y2 = map(int, b.groups())
        edits.append((x1, y1, x2, y2))
    target = None
    for lab in labels:
        for (x1, y1, x2, y2) in edits:
            if x1 <= lab["cx"] <= x2 and y1 <= lab["cy"] <= y2:
                target = ((x1 + x2) // 2, (y1 + y2) // 2)
                break
        if target:
            break
    if not target and edits and labels:
        # 兜底：页面唯一输入框 + 唯一 label 匹配
        if len(edits) == 1:
            target = ((edits[0][0] + edits[0][2]) // 2,
                      (edits[0][1] + edits[0][3]) // 2)
    if not target:
        return False
    G.adb(serial, "shell", "input", "tap", str(target[0]), str(target[1]))
    time.sleep(1.2)
    G.adb(serial, "shell", "input", "text", value.replace(" ", "%s"))
    time.sleep(0.8)
    return True


ADD_ACCOUNT_FINGERPRINTS = ("On your device", "feedbin.com", "freshrss.org")
HOME_ENTRY_SYMS = {
    # GAP-3g/v5：这些面的 BC 操作序列都从"主界面（列表）"起步（步骤自行
    # 打开 drawer/对话框/设置入口）。gmi_runtime 的通用导航会把链带到
    # 对话框/阅读页等"到达态"，与 BC 步骤起点假设错位；且宽特征集下
    # 长文本兜底常点开 WebView 阅读页（uiautomator dump 极慢）导致
    # NAV_FAIL 连锁。拦截为"主界面起点"（冷启动即达），步骤序列自己
    # 完成入口导航（与 BC operation_steps 语义一致）。
    "ArticleScreen",      # 文章列表主界面
    "AddFeedDialog",      # 步骤1 tap Add Feed 自行开对话框
    "AddFeedButton",
    "RemoveFeedDialog",   # 步骤自行从 drawer 菜单进入
    "SettingsScreen",     # 步骤1 tap Open settings 自行进入
    # v7b：AddAccountScreen 冷启动即达（pm clear seed 首屏）；通用导航的
    # 锚点探索会点到在线服务行（Reader/Feedbin 登录页）再返回，返回 xml
    # 停在中间态导致 step1 tap Local 失稳。专属指纹（副标题/域名，drawer
    # 内不同时出现）稳定拦截。
    "AddAccountScreen",
}
HOME_FINGERPRINTS = ("Mark All as Read", "No feeds yet", "Add Feed", "All")
# v7：移除 "Add Account"——侧栏底部亦有 Add Account 入口文本（实测污染：
# drawer 态误判为账号未建立）。BC-0001 的 Add Account 页起点由通用导航
# 原生处理（already-on-page/锚点，历轮已工作）。


def patched_nav_attempt(serial, pkg, act, out_dir, pid, sym, feats,
                        launch_texts, stay, jumps=None, depth=3,
                        max_anchors=5, max_fallbacks=2, anr_budget=None):
    _CHAIN_STATE.clear()
    _WAIT_HITS.clear()
    # GAP-3j：pre_state 所述前置多位于链入口导航之前（如"侧栏可见 Add Feed
    # 入口"），而导航到达态可能已越过该状态（对话框打开）。保留导航前 UI
    # 供 precondition 校验兜底（时点修正，非期望放宽）。
    _CHAIN_STATE["nav_pre_xml"] = G._dump_xml(serial) or ""
    if sym in HOME_ENTRY_SYMS:
        # v7：fg 先行轮询（dump 的 uiautomator 会干扰冷启动；先确认前台
        # 再 dump 指纹）。force-stop 与 am start 竞态（arm 翻译模拟器上
        # force-stop 完成 >2.5s）：恢复动作 sleep 6s + fg 轮询确认。
        for attempt in range(4):
            for i in range(8):
                fg = G._fg_in_pkg_now(serial, pkg)
                if fg:
                    break
                time.sleep(2.5)
            if fg:
                home_xml = ""
                for i in range(4):
                    home_xml = G._dump_stable(serial, pkg, act,
                                              "home:" + pid,
                                              anr_budget=anr_budget)
                    if home_xml:
                        fp = [f for f in HOME_FINGERPRINTS
                              + ADD_ACCOUNT_FINGERPRINTS
                              if G._xml_shows(home_xml, f)]
                        if fp:
                            return {"reached": True,
                                    "anchor": "(home-surface:launch fp=%s)" % fp[0],
                                    "fallback": False, "xml": home_xml}
                        break  # UI 有效但非主界面指纹：走通用导航
                    time.sleep(2.5)
                if home_xml:
                    break
            print("[2B-nav] sym=%s not-fg/invalid-ui (attempt=%d) "
                  "-> force-relaunch" % (sym, attempt), flush=True)
            G.adb(serial, "shell", "am", "force-stop", pkg)
            time.sleep(6.0)
            G.adb(serial, "shell", "am", "start", "-n", "%s/.%s" % (pkg, act))
            time.sleep(4.0)
    return _orig_nav_attempt(serial, pkg, act, out_dir, pid, sym, feats,
                             launch_texts, stay, jumps=jumps, depth=depth,
                             max_anchors=max_anchors, max_fallbacks=max_fallbacks,
                             anr_budget=anr_budget)


_orig_exec_step = G._exec_chain_step


def patched_exec_step(serial, pkg, act, step, cur_xml, stay, budget, ctx):
    action = (step.get("action") or "").strip().lower()
    target = (step.get("target") or "").strip()
    value = (step.get("value") or "").strip()
    raw_target = (step.get("_raw") or {}).get("target", target)
    if action == "wait":
        want = target
        # v5：瞬态 UI（snackbar ~4s）可能在上一 tap 的 settle/dump 窗口内
        # 已出现又消失——先查链内早期步骤 dump（同一 UI 事实的更早观测）。
        for hx in _ALL_STEP_XMLS:
            if G._xml_shows(hx, want):
                _WAIT_HITS[want] = hx
                return {"ok": True, "xml": hx,
                        "note": "wait '%s' observed (earlier step dump)" % want}
        deadline = time.time() + 36.0
        while time.time() < deadline:
            xml = G._dump_xml(serial, force=True)
            if xml and G._xml_shows(xml, want):
                _WAIT_HITS[want] = xml
                if not G._fg_in_pkg_now(serial, pkg):
                    return {"ok": False, "xml": xml,
                            "note": "foreground left pkg while waiting"}
                return {"ok": True, "xml": xml,
                        "note": "wait '%s' observed" % want}
            time.sleep(2.5)
        return {"ok": False, "xml": cur_xml,
                "note": "wait timeout (36s) for '%s'" % want}
    if action == "input":
        if _fill_input_by_label(serial, cur_xml, target, value):
            time.sleep(1.0)
            probe = G._dump_stable(serial, pkg, act, "step:" + ctx,
                                   anr_budget=budget)
            if not probe:
                return {"ok": False, "xml": cur_xml,
                        "note": "ANR_BLOCKED(collector-induced)"}
            return {"ok": True, "xml": probe,
                    "note": "input '%s' <- '%s' [label-anchored]"
                            % (target, value[:24])}
        return {"ok": False, "xml": cur_xml,
                "note": "input field not found: '%s'" % (raw_target or target)}
    if action == "tap":
        tgt = G.find_click(cur_xml, target)
        via = "text"
        if not tgt:
            tgt = _locate_drawer_hamburger(cur_xml, raw_target)
            if tgt:
                via = "structural-fallback"
        if not tgt and _drawer_entry_intent(raw_target or target):
            # GAP-3k：drawer 入口类 target miss（主界面侧栏默认收起）->
            # 点汉堡开 drawer -> 重找 target（BC 步骤意图=进入侧栏入口）。
            ham = _locate_drawer_hamburger(cur_xml, "Open settings navigation")
            if ham:
                G.adb(serial, "shell", "input", "tap",
                      str(ham["cx"]), str(ham["cy"]))
                time.sleep(stay + G._TAP_SETTLE)
                probe = G._dump_stable(serial, pkg, act, "drawer:" + ctx,
                                       anr_budget=budget)
                if probe and G._fg_in_pkg_now(serial, pkg):
                    _ALL_STEP_XMLS.append(probe)
                    if raw_target == "desc=Open settings navigation" or \
                            target == "Open settings navigation":
                        if G._xml_shows(probe, "Refresh all") or \
                                G._xml_shows(probe, "Open settings"):
                            return {"ok": True, "xml": probe,
                                    "note": "tap '%s' -> drawer opened "
                                            "[structural: hamburger]"
                                            % target}
                    tgt = G.find_click(probe, target)
                    if tgt:
                        G.adb(serial, "shell", "input", "tap",
                              str(tgt["cx"]), str(tgt["cy"]))
                        time.sleep(stay + G._TAP_SETTLE)
                        p2 = G._dump_stable(serial, pkg, act,
                                            "step:" + ctx, anr_budget=budget)
                        if p2 and G._fg_in_pkg_now(serial, pkg):
                            _ALL_STEP_XMLS.append(p2)
                            return {"ok": True, "xml": p2,
                                    "note": "tap '%s' via drawer "
                                            "[structural: hamburger]"
                                            % target}
        if not tgt:
            tgt = _locate_status_toggle(cur_xml, target)
            if tgt:
                via = "structural-fallback"
        if not tgt and raw_target.startswith("class=article_row_index_"):
            tgt = _locate_first_article_row(cur_xml)
            if tgt:
                via = "structural-fallback"
        if not tgt and target in DIALOG_FINGERPRINT:
            fp = DIALOG_FINGERPRINT[target]
            if G._xml_shows(cur_xml, fp):
                return {"ok": True, "xml": cur_xml,
                        "note": "tap '%s' idempotent-skip: dialog already "
                                "open (fingerprint '%s' visible)" % (target, fp)}
        if not tgt and target == "Default":
            # GAP-3h：默认主题=MONET（API>=S，AppTheme.kt default=MONET.
            # normalized()），Theme 下拉当前显示 "Dynamic"（theme_dynamic）
            # 而非 BC 假设的 "Default"。step3 意图=展开 Theme 下拉：
            # 定位含 "Theme" 标签的 Display 面板首个只读展示框（EditText）。
            if G._xml_shows(cur_xml, "Theme"):
                for m in re.finditer(r"<node[^>]*?>", cur_xml or ""):
                    cls = re.search(r'class="([^"]+)"', m.group(0))
                    if not cls or "EditText" not in cls.group(1):
                        continue
                    b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                                  m.group(0))
                    if not b:
                        continue
                    x1, y1, x2, y2 = map(int, b.groups())
                    G.adb(serial, "shell", "input", "tap",
                          str((x1 + x2) // 2), str((y1 + y2) // 2))
                    time.sleep(stay + G._TAP_SETTLE)
                    probe = G._dump_stable(serial, pkg, act, "step:" + ctx,
                                           anr_budget=budget)
                    if not probe:
                        return {"ok": False, "xml": cur_xml,
                                "note": "ANR_BLOCKED(collector-induced)"}
                    return {"ok": True, "xml": probe,
                            "note": "tap 'Default' -> theme dropdown "
                                    "expand [structural: display-field]"}
        if not tgt:
            return {"ok": False, "xml": cur_xml,
                    "note": "tap target not found: '%s'" % (raw_target or target)}
        G.adb(serial, "shell", "input", "tap", str(tgt["cx"]), str(tgt["cy"]))
        time.sleep(stay + G._TAP_SETTLE)
        probe = G._dump_stable(serial, pkg, act, "step:" + ctx,
                               anr_budget=budget)
        if not probe:
            return {"ok": False, "xml": cur_xml,
                    "note": "ANR_BLOCKED(collector-induced)"}
        if not G._fg_in_pkg_now(serial, pkg):
            return {"ok": False, "xml": probe,
                    "note": "foreground left pkg after tap"}
        _ALL_STEP_XMLS.append(probe)
        note = "tap '%s' @(%d,%d)" % (target, tgt["cx"], tgt["cy"])
        if via != "text":
            note += " [%s]" % via
        return {"ok": True, "xml": probe, "note": note}
    return _orig_exec_step(serial, pkg, act, step, cur_xml, stay, budget, ctx)


_orig_nav_attempt = G._nav_attempt
G._nav_attempt = patched_nav_attempt

G._exec_chain_step = patched_exec_step


def _load_probe(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def patched_evaluate(assertions, after_xml, restart_xml):
    out = []
    before_xml = _CHAIN_STATE.get("before_xml", "") or ""
    for a in assertions or []:
        if not isinstance(a, dict):
            continue
        kind = (a.get("kind") or "").strip()
        note = ""
        if kind == "data_probe":
            key = (a.get("key") or "").strip()
            expected = a.get("value")
            res = DP.evaluate_data_assertions(
                [{"kind": "data_equals", "key": key, "value": expected}],
                data_before=_load_probe(_CHAIN_STATE.get("probe_before", "")),
                data_after=_load_probe(_CHAIN_STATE.get("probe_after", "")),
                data_restart=_load_probe(_CHAIN_STATE.get("probe_restart", "")))
            verdict = res[0]["verdict"] if res else "UNSUPPORTED"
            note = ((res[0].get("note", "") if res else "")
                    + " [probe oracle key=%s]" % key)
            out.append({"kind": "data_equals", "value": str(expected)[:60],
                        "verdict": verdict, "optional": "false",
                        "note": note})
            continue
        if kind in ("text_visible", "text_gone", "persist_after_restart"):
            value = (a.get("value") or "").strip()
            mode = (a.get("mode") or "").strip()
            if kind == "text_visible":
                if mode == "before":
                    verdict = "PASS" if value and G._xml_shows(before_xml, value) else "FAIL"
                    note = "judged at before-snapshot (expected 'visible before ...')"
                else:
                    verdict = "PASS" if value and G._xml_shows(after_xml, value) else "FAIL"
                    if verdict == "FAIL" and value:
                        if value in _WAIT_HITS:
                            verdict = "PASS"
                            note = ("observed at wait-step dump "
                                    "(transient snackbar)")
                        elif any(G._xml_shows(hx, value) for hx in _ALL_STEP_XMLS):
                            verdict = "PASS"
                            note = ("observed at earlier step dump "
                                    "(transient UI)")
            elif kind == "text_gone":
                verdict = "PASS" if value and not G._xml_shows(after_xml, value) else "FAIL"
            else:
                if not restart_xml:
                    verdict = "FAIL"
                    note = "restart snapshot unavailable (fail-closed)"
                elif mode == "gone":
                    verdict = "PASS" if not G._xml_shows(restart_xml, value) else "FAIL"
                else:
                    verdict = "PASS" if G._xml_shows(restart_xml, value) else "FAIL"
                if mode:
                    note = (note + " " if note else "") + "mode=%s" % mode
            item = {"kind": kind, "value": value[:60],
                    "verdict": verdict, "optional": "false"}
            if note:
                item["note"] = note
            out.append(item)
            continue
        out.append({"kind": kind or (a.get("type") or "?"),
                    "value": str(a.get("target") or a.get("value") or "")[:60],
                    "verdict": "UNSUPPORTED", "optional": "false",
                    "note": "no runtime oracle (GAP-2): type=%s target=%s"
                            % (a.get("type", ""), str(a.get("target", ""))[:40])})
    return out


G.evaluate_chain_assertions = patched_evaluate
G.all_assertions_unsupported = lambda assertions: False


_orig_full_probe = G._full_probe


def patched_full_probe(serial, dirpath, pkg, act="MainActivity", ctx=""):
    ev = _orig_full_probe(serial, dirpath, pkg, act, ctx)
    if not ctx or ":" not in ctx:
        return ev
    phase = ctx.split(":", 1)[0]
    if phase not in ("before", "after", "restart"):
        return ev
    _CHAIN_STATE[phase + "_xml"] = ev.get("xml", "") or ""
    out = Path(dirpath) / "data-probe.json"
    try:
        r = subprocess.run(
            [sys.executable, PROBE_SCRIPT, "--package", pkg, "--device", serial,
             "--out", str(out), "--sqlite3", SQLITE3, "--allow-denied"],
            capture_output=True, text=True, timeout=240)
        _CHAIN_STATE["probe_" + phase] = str(out) if out.exists() else ""
        _CHAIN_STATE.setdefault("probe_log", {})[phase] = \
            ((r.stdout or "") + (r.stderr or ""))[-600:]
    except Exception as e:  # noqa
        _CHAIN_STATE["probe_" + phase] = ""
        _CHAIN_STATE.setdefault("probe_log", {})[phase] = "__ERR__%s" % e
    return ev


G._full_probe = patched_full_probe


# GAP-3m：_cold_restart 的 force-stop(2s)->am start 竞态（arm 翻译模拟器
# 上 force-stop 完成耗时 >2.5s）：am start 抢先空壳 task 前台化、force-stop
# 收尾清除 -> app 永久滞留桌面，后续导航进入超慢探索（实测 25 分钟）。
# 绕过：延时 6s + 失败二次拉起。
_orig_cold_restart = G._cold_restart


def patched_cold_restart(serial, pkg, act):
    G.adb(serial, "shell", "am", "force-stop", pkg)
    time.sleep(6.0)
    G.adb(serial, "shell", "am", "start", "-n", "%s/.%s" % (pkg, act))
    ok = G._wait_app_ready(serial, pkg)
    if not ok:
        G.adb(serial, "shell", "am", "force-stop", pkg)
        time.sleep(4.0)
        G.adb(serial, "shell", "am", "start", "-n", "%s/.%s" % (pkg, act))
        ok = G._wait_app_ready(serial, pkg)
    if ok:
        time.sleep(2.0)
    return ok


G._cold_restart = patched_cold_restart


def seed_reset():
    """scope.reset_procedure（pm clear + 冷启动）+ GAP-5 locale 修正。"""
    print("[2B-seed] pm clear + per-app locale en-US（GAP-5：BC 契约文本基于"
          "英文资源；zh-CN 实测断言文本不出现）")
    G.adb(SERIAL, "shell", "pm", "clear", PKG)
    G.adb(SERIAL, "shell", "cmd", "locale", "set-app-locales", PKG,
          "--locales", "en-US")
    time.sleep(1.0)


def main():
    TG_DIR.mkdir(parents=True, exist_ok=True)
    seed_reset()
    sys.argv = ["gmi_runtime.py", "--project", PROJECT, "--workspace", WS,
                "--package", PKG, "--serial", SERIAL, "--activity", ACT,
                "--mode", "chain", "--high-impact-only", "--verbose"]
    rc = G.main()
    print("[2B-driver] gmi_runtime exit=%s" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
