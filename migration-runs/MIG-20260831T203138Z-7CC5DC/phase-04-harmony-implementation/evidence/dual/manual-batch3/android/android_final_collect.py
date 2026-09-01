#!/usr/bin/env python3
"""Android 批次3终采：BC-0018 设置页 / BC-0019 主题 / BC-0020 排序 / BC-0017 持久复核 / BC-0021 样式壳。subprocess timeout=30。"""
import subprocess, time, re, os, json

ADB = "/Users/rainyday/Library/Android/sdk/platform-tools/adb"
PKG = "com.capyreader.app.debug"
ACT = f"{PKG}/com.capyreader.app.MainActivity"
OUT = os.path.dirname(os.path.abspath(__file__))
PREFS_FILE = f"shared_prefs/com.capyreader.app.debug_preferences.xml"
LOG = []

def adb(*a, t=30):
    r = subprocess.run([ADB, "-s", "emulator-5554"] + list(a), capture_output=True, text=True, timeout=t)
    return r.returncode, r.stdout, r.stderr

def sh(cmd, t=30):
    return adb("shell", cmd, t=t)

def dump(name):
    for _ in range(3):
        rc, out, err = sh("uiautomator dump /sdcard/ui.xml")
        if "dumped to" in (out or ""):
            adb("pull", "/sdcard/ui.xml", os.path.join(OUT, name))
            with open(os.path.join(OUT, name), encoding="utf-8") as f:
                return f.read()
        time.sleep(1.5)
    raise RuntimeError(f"dump failed: {name}")

def prefs(tag):
    rc, out, err = sh(f"run-as {PKG} cat /data/data/{PKG}/{PREFS_FILE}")
    with open(os.path.join(OUT, f"prefs-{tag}.xml"), "w") as f:
        f.write(out if rc == 0 else f"RC={rc} ERR={err}\n{out}")
    d = dict(re.findall(r'name="([\w_]+)"[^>]*>([^<]*)<', out or ""))
    keys = ["account_id", "app_theme", "theme_mode", "article_list_sort_order", "article_font_size"]
    print(f"[prefs:{tag}]", {k: d.get(k) for k in keys})
    return d

def bounds(xml, text, attr="text"):
    for nm in re.finditer(r"<node[^>]*>", xml):
        n = nm.group(0)
        if f'{attr}="{text}"' in n:
            b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', n)
            if b:
                x1, y1, x2, y2 = map(int, b.groups())
                return (x1 + x2) // 2, (y1 + y2) // 2
    return None

def tap_text(xml, text, attr="text", label=""):
    c = bounds(xml, text, attr)
    if c:
        sh(f"input tap {c[0]} {c[1]}"); print(f"[tap] {label or text} @ {c}")
        return True
    print(f"[MISS] {label or text} ({attr})")
    return False

def back(): sh("input keyevent 4")
def wait(s=2): time.sleep(s)

# 冷启动确保干净起点
sh(f"am force-stop {PKG}"); wait(1)
sh(f"am start -n {ACT}"); wait(5)

# ============ BC-0018：设置页 ============
print("=== BC-0018 ===")
x = dump("bc0018-1-main.xml")
HAMBURGER = (77, 231)
sh(f"input tap {HAMBURGER[0]} {HAMBURGER[1]}"); wait(2)
x = dump("bc0018-2-drawer.xml")
drawer_texts = [t for t in re.findall(r'text="([^"]+)"', x) if t]
drawer_descs = [d for d in re.findall(r'content-desc="([^"]+)"', x) if d]
print("[drawer]", drawer_texts[:15], drawer_descs[:8])
c = bounds(x, "Open settings", "content-desc") or bounds(x, "Settings") or bounds(x, "Settings", "content-desc")
ok18 = False
if c:
    sh(f"input tap {c[0]} {c[1]}"); wait(3)
    x18 = dump("bc0018-android-settings.xml")
    c18 = {"drawer_has_settings_entry": True,
           "display_section": "Display" in x18, "general_section": "General" in x18,
           "theme_row": "Theme" in x18,
           "sections_snapshot": [t for t in re.findall(r'text="([^"]{3,28})"', x18) if t][:18]}
    ok18 = c18["display_section"] and c18["general_section"]
else:
    x18 = x
    c18 = {"drawer_has_settings_entry": False, "drawer_texts": drawer_texts, "drawer_descs": drawer_descs}
print("[BC-0018]", c18)
LOG.append(["BC-0018", "settings-page", c18])

# ============ BC-0019：主题 Newsprint ============
print("=== BC-0019 ===")
c19 = {}
if ok18:
    tap_text(x18, "Display"); wait(2)
    x19 = dump("bc0019-1-display.xml")
    c19["display_panel"] = "Theme" in x19
    # Theme 行当前值 Default（契约 steps: tap Default -> tap Newsprint）
    if not tap_text(x19, "Default", label="current theme Default"):
        tap_text(x19, "Theme", label="Theme row")
    wait(1.5)
    x19m = dump("bc0019-2-theme-menu.xml")
    c19["menu_options"] = [t for t in ["Default", "Light", "Dark", "Newsprint"] if t in x19m]
    ok19 = tap_text(x19m, "Newsprint")
    wait(2)
    p19 = prefs("bc0019-after")
    c19["prefs_app_theme"] = p19.get("app_theme")
    x19a = dump("bc0019-android-after.xml")
    c19["ui_after_switch"] = ok19
print("[BC-0019]", c19)
LOG.append(["BC-0019", "theme-switch", c19])

# ============ BC-0020：排序 Oldest first ============
print("=== BC-0020 ===")
c20 = {}
if ok18:
    back(); wait(1)
    x20 = dump("bc0020-1-settings.xml")
    if "General" not in x20:
        back(); wait(1); x20 = dump("bc0020-1b-settings.xml")
    if tap_text(x20, "General"):
        wait(2)
        x20g = dump("bc0020-android-general-before.xml")
        c20["sort_row"] = "Newest first" in x20g or "Sort order" in x20g
        if not tap_text(x20g, "Newest first", label="current sort"):
            tap_text(x20g, "Sort order")
        wait(1.5)
        x20m = dump("bc0020-2-sort-menu.xml")
        c20["menu_options"] = [t for t in ["Newest first", "Oldest first"] if t in x20m]
        tap_text(x20m, "Oldest first"); wait(1)
        p20 = prefs("bc0020-after")
        c20["prefs_sort"] = p20.get("article_list_sort_order")
        back(); wait(1); back(); wait(2)
        x20l = dump("bc0020-android-list-oldest.xml")
        c20["list_first_titles"] = [t[:42] for t in re.findall(r'text="([^"]{25,})"', x20l)[:2]]
print("[BC-0020]", c20)
LOG.append(["BC-0020", "sort-switch", c20])

# ============ BC-0017 持久复核（主题+排序切换+杀进程后） ============
print("=== BC-0017 recheck ===")
sh(f"am force-stop {PKG}"); wait(2)
sh(f"am start -n {ACT}"); wait(5)
x17 = dump("bc0017-android-coldstart-recheck.xml")
t17 = re.findall(r'text="([^"]{25,})"', x17)
p17 = prefs("bc0017-recheck")
c17 = {"no_add_account": "Add Account" not in x17,
       "ars_feed_listed": "Ars Technica" in x17,
       "article_rows": len(t17),
       "first_titles": [t[:42] for t in t17[:2]],
       "prefs_account_id_present": bool(p17.get("account_id")),
       "prefs_app_theme_kept": p17.get("app_theme"),
       "prefs_sort_kept": p17.get("article_list_sort_order")}
print("[BC-0017]", c17)
LOG.append(["BC-0017", "cold-restart-persistence-recheck", c17])

# ============ BC-0021：阅读样式壳 ============
print("=== BC-0021 ===")
c21 = {"reader_opened": False, "style_entry": None, "panel": None}
tgt = bounds(x17, t17[0]) if t17 else None
if tgt:
    sh(f"input tap {tgt[0]} {tgt[1]}"); wait(4)
    x21 = dump("bc0021-android-reader.xml")
    c21["reader_opened"] = len(re.findall(r'text="[^"]{10,}"', x21)) > 2
    se = bounds(x21, "Aa") or bounds(x21, "Aa", "content-desc")
    c21["style_entry"] = bool(se)
    if se:
        sh(f"input tap {se[0]} {se[1]}"); wait(2)
        x21p = dump("bc0021-android-style-panel.xml")
        c21["panel"] = {"font": any(k in x21p for k in ["Small", "Medium", "Large"]),
                        "align": any(k in x21p for k in ["Left", "Center", "Justify"]),
                        "texts": [t for t in re.findall(r'text="([^"]{1,24})"', x21p) if t][:14]}
        p21 = prefs("bc0021")
        c21["prefs_article_font_size"] = p21.get("article_font_size")
        back(); wait(1)
print("[BC-0021]", c21)
LOG.append(["BC-0021", "style-shell", c21])

# 复位冷态
back(); wait(1); back(); wait(1)
sh(f"am force-stop {PKG}")
print("[reset] android force-stopped")
with open(os.path.join(OUT, "android-manual-checks.json"), "w", encoding="utf-8") as f:
    json.dump({"device": "emulator-5554", "package": PKG, "log": LOG}, f, ensure_ascii=False, indent=1)
print("DONE")