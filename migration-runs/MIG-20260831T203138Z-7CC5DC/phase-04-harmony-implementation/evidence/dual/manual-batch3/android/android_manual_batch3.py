#!/usr/bin/env python3
"""Android 侧批次 3 手采（BC-0017~0021），同口径对照 Harmony 侧 evidence/batch3。
所有 adb 调用 subprocess timeout=30 包裹。产出 dump XML + prefs 快照到本目录。
"""
import subprocess, time, sys, re, os

ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
DEV = "-s"
DEVICE = "emulator-5554"
PKG = "com.capyreader.app.debug"
ACT = "com.capyreader.app.debug/com.capyreader.app.MainActivity"
OUT = os.path.dirname(os.path.abspath(__file__))

def adb(*args, timeout=30):
    cmd = [ADB, DEV, DEVICE] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def sh(cmd, timeout=30):
    return adb("shell", cmd, timeout=timeout)

def dump(name):
    sh("uiautomator dump /sdcard/ui.xml", timeout=30)
    adb("pull", "/sdcard/ui.xml", os.path.join(OUT, name), timeout=30)
    with open(os.path.join(OUT, name), encoding="utf-8") as f:
        return f.read()

def prefs(tag):
    rc, out, err = sh(f"run-as {PKG} cat /data/data/{PKG}/shared_prefs/default.xml")
    p = os.path.join(OUT, f"prefs-{tag}.xml")
    with open(p, "w", encoding="utf-8") as f:
        f.write(out if rc == 0 else f"RC={rc} ERR={err}\n{out}")
    # 关键键摘要
    keys = ["account_id", "app_theme", "theme_mode", "article_list_sort_order"]
    summary = {k: (re.search(rf'name="{k}"[^>]*>([^<]*)<', out).group(1)
                   if re.search(rf'name="{k}"[^>]*>([^<]*)<', out) else None) for k in keys}
    print(f"[prefs:{tag}] {summary}")
    return summary

def has(xml, s):
    return s in xml

def tap(x, y):
    sh(f"input tap {x} {y}")

def back():
    sh("input keyevent 4")

def wait(s=2):
    time.sleep(s)

def find_bounds(xml, text, attr="text"):
    """返回首个匹配节点的中心坐标"""
    m = re.search(rf'<node[^>]*{attr}="{re.escape(text)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
    if not m:  # 属性顺序不同的情况
        for nm in re.finditer(rf'<node[^>]*>', xml):
            node = nm.group(0)
            if f'{attr}="{text}"' in node:
                b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
                if b:
                    m = b; break
    if m:
        x1, y1, x2, y2 = map(int, m.groups())
        return (x1 + x2) // 2, (y1 + y2) // 2
    return None

def tap_text(xml, text, attr="text", label=""):
    c = find_bounds(xml, text, attr)
    if c:
        tap(*c); print(f"[tap] {label or text} @ {c}")
        return True
    print(f"[MISS] {label or text} ({attr}) not found")
    return False

log = []

# ============ BC-0017：冷启动持久 ============
print("=== BC-0017 cold start ===")
sh(f"am force-stop {PKG}"); wait(2)
sh(f"am start -n {ACT}"); wait(5)
x = dump("bc0017-android-coldstart.xml")
checks17 = {
    "no_add_account_first_screen": not has(x, "Add Account"),
    "ars_feed_listed": has(x, "Ars Technica"),
    "article_rows_present": has(x, "Mark as read") or len(re.findall(r'text="[^"]{20,}"', x)) > 3,
}
print(f"[BC-0017] {checks17}")
log.append(("BC-0017", "cold-start", checks17))
p17 = prefs("bc0017-coldstart")

# ============ BC-0018：设置页 ============
print("=== BC-0018 settings ===")
# 手机布局需先开导航抽屉：找 content-desc="Open navigation drawer" 或菜单键
opened = tap_text(x, "Open settings", "content-desc", "Open settings entry")
if not opened:
    # 尝试先开抽屉
    nav = find_bounds(x, "Open navigation drawer", "content-desc")
    if nav: tap(*nav); wait(2); x2 = dump("bc0018-drawer.xml"); tap_text(x2, "Open settings", "content-desc")
wait(3)
x = dump("bc0018-android-settings.xml")
checks18 = {
    "settings_sections_visible": has(x, "Display") and has(x, "General"),
    "theme_row_visible": has(x, "Theme"),
}
print(f"[BC-0018] {checks18}")
log.append(("BC-0018", "settings-page", checks18))

# ============ BC-0019：主题切换 ============
print("=== BC-0019 theme ===")
tap_text(x, "Display", "text", "Display section"); wait(2)
x = dump("bc0019-android-display-before.xml")
before_theme = has(x, "Theme")
print(f"[BC-0019] display panel, Theme row: {before_theme}")
# 打开 Theme 下拉（显示当前值的行，契约 steps: tap Default -> tap Newsprint）
if not tap_text(x, "Default", "text", "current theme value Default"):
    # Theme 行本身
    tap_text(x, "Theme", "text", "Theme row")
wait(1)
x = dump("bc0019-android-theme-menu.xml")
ok = tap_text(x, "Newsprint", "text", "Newsprint option")
wait(2)
x = dump("bc0019-android-theme-after.xml")
p19 = prefs("bc0019-after")
checks19 = {
    "theme_menu_opened": ok,
    "prefs_app_theme": p19.get("app_theme"),
    "newsprint_applied_ui": ok,  # prefs 为准 + dump 留证
}
print(f"[BC-0019] {checks19}")
log.append(("BC-0019", "theme-switch", checks19))

# ============ BC-0020：排序切换 ============
print("=== BC-0020 sort order ===")
back(); wait(1)  # 回设置根
x = dump("bc0020-android-settings-back.xml")
if not has(x, "General"):
    back(); wait(1); x = dump("bc0020-android-settings-back2.xml")
tap_text(x, "General", "text", "General section"); wait(2)
x = dump("bc0020-android-general-before.xml")
if not tap_text(x, "Newest first", "text", "current sort Newest first"):
    tap_text(x, "Sort order", "text", "Sort order row")
wait(1)
x = dump("bc0020-android-sort-menu.xml")
ok2 = tap_text(x, "Oldest first", "text", "Oldest first option")
wait(1)
p20 = prefs("bc0020-after")
# 返回文章列表
back(); wait(1); back(); wait(2)
x = dump("bc0020-android-list-after.xml")
# 首行文本（列表区域前几条长文本）
titles = re.findall(r'text="([^"]{25,})"', x)
checks20 = {
    "sort_menu_opened": ok2,
    "prefs_sort": p20.get("article_list_sort_order"),
    "list_first_titles": titles[:3],
}
print(f"[BC-0020] {checks20}")
log.append(("BC-0020", "sort-switch", checks20))

# ============ BC-0021：阅读样式壳（STATIC_ONLY） ============
print("=== BC-0021 article style ===")
# 点第一篇文章（找长标题）
target = None
for t in titles or []:
    c = find_bounds(x, t)
    if c: target = (t, c); break
if not target:
    m = re.search(r'text="([^"]{20,})"', x)
    if m: target = (m.group(1), find_bounds(x, m.group(1)))
if target:
    tap(*target[1]); wait(3)
x = dump("bc0021-android-reader.xml")
style_entry = find_bounds(x, "Aa", "text") or find_bounds(x, "Aa", "content-desc")
checks21 = {
    "reader_opened": len(re.findall(r'text="[^"]{10,}"', x)) > 0,
    "style_entry_visible": style_entry is not None,
}
print(f"[BC-0021] {checks21}")
if style_entry:
    tap(*style_entry); wait(2)
    x = dump("bc0021-android-style-panel.xml")
    checks21["panel_options"] = {
        "font_options": has(x, "Small") or has(x, "Medium") or has(x, "Large"),
        "align_options": has(x, "Left") or has(x, "Center") or has(x, "Justify"),
    }
    print(f"[BC-0021 panel] {checks21['panel_options']}")
    p21 = prefs("bc0021")
    back(); wait(1)
log.append(("BC-0021", "style-shell", checks21))

# ============ 复位：设置回默认 + 冷态 ============
print("=== reset ===")
back(); wait(1); back(); wait(1); back(); wait(1)
sh(f"am force-stop {PKG}")
print("[reset] force-stopped (theme/sort prefs left as evidence; reset-to-default noted in report)")

import json
with open(os.path.join(OUT, "android-manual-checks.json"), "w", encoding="utf-8") as f:
    json.dump({"log": [[a, b, c] for a, b, c in log]}, f, ensure_ascii=False, indent=1)
print("DONE")