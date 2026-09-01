#!/usr/bin/env python3
"""Android 批次3收尾：BC-0019 主题（Display & Appearance）+ BC-0020 排序 + BC-0017 终复核 + BC-0021。subprocess timeout=30。"""
import subprocess, time, re, os, json

ADB = "/Users/rainyday/Library/Android/sdk/platform-tools/adb"
PKG = "com.capyreader.app.debug"
ACT = f"{PKG}/com.capyreader.app.MainActivity"
OUT = os.path.dirname(os.path.abspath(__file__))
PREFS = f"shared_prefs/com.capyreader.app.debug_preferences.xml"
HAMBURGER = (77, 231)
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
    raise RuntimeError(f"dump failed {name}")

def prefs(tag):
    rc, out, err = sh(f"run-as {PKG} cat /data/data/{PKG}/{PREFS}")
    with open(os.path.join(OUT, f"prefs-{tag}.xml"), "w") as f:
        f.write(out if rc == 0 else f"RC={rc} ERR={err}\n{out}")
    d = dict(re.findall(r'name="([\w_]+)"[^>]*>([^<]*)<', out or ""))
    print(f"[prefs:{tag}]", {k: d.get(k) for k in ["account_id","app_theme","theme_mode","article_list_sort_order","article_font_size"]})
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

sh(f"am force-stop {PKG}"); wait(1)
sh(f"am start -n {ACT}"); wait(5)

def open_settings():
    x = dump("tmp-main.xml")
    sh(f"input tap {HAMBURGER[0]} {HAMBURGER[1]}"); wait(2)
    x = dump("tmp-drawer.xml")
    c = bounds(x, "Open settings", "content-desc") or bounds(x, "Settings")
    sh(f"input tap {c[0]} {c[1]}"); wait(3)
    return dump("tmp-settings.xml")

# ============ BC-0019 ============
print("=== BC-0019 ===")
xs = open_settings()
ok_disp = tap_text(xs, "Display &amp; Appearance", label="Display & Appearance section") or tap_text(xs, "Appearance")
wait(2)
x19 = dump("bc0019-1-display.xml")
disp_texts = [t for t in re.findall(r'text="([^"]{1,30})"', x19) if t]
print("[display panel]", disp_texts[:20])
c19 = {"display_panel_opened": ok_disp, "panel_snapshot": disp_texts[:20]}
# Theme 行：找含 Theme 的行与当前值
tap_target = None
if "Theme" in x19:
    tap_target = tap_text(x19, "Theme", label="Theme row")
if not tap_target:
    for v in ["Default", "Newsprint", "Light", "Dark"]:
        if tap_text(x19, v, label=f"current theme {v}"): break
wait(1.5)
x19m = dump("bc0019-2-theme-menu.xml")
menu_texts = [t for t in re.findall(r'text="([^"]{1,30})"', x19m) if t]
c19["theme_menu_snapshot"] = menu_texts[:15]
c19["newsprint_option"] = "Newsprint" in x19m
tap_text(x19m, "Newsprint")
wait(2)
p19 = prefs("bc0019-after")
c19["prefs_app_theme"] = p19.get("app_theme")
x19a = dump("bc0019-android-after-newsprint.xml")
c19["ui_after_snapshot"] = [t for t in re.findall(r'text="([^"]{1,30})"', x19a) if t][:10]
print("[BC-0019]", c19)
LOG.append(["BC-0019", "theme-switch", c19])

# ============ BC-0020 ============
print("=== BC-0020 ===")
back(); wait(1)
x20 = dump("bc0020-1-settings.xml")
if "General" not in x20:
    back(); wait(1); x20 = dump("bc0020-1b-settings.xml")
c20 = {"settings_root_has_general": "General" in x20}
tap_text(x20, "General"); wait(2)
x20g = dump("bc0020-android-general-before.xml")
gen_texts = [t for t in re.findall(r'text="([^"]{1,32})"', x20g) if t]
c20["general_snapshot"] = gen_texts[:22]
# 排序行
sort_hit = tap_text(x20g, "Newest first", label="current sort Newest first")
if not sort_hit:
    tap_text(x20g, "Sort order", label="Sort order row")
wait(1.5)
x20m = dump("bc0020-2-sort-menu.xml")
c20["sort_menu_snapshot"] = [t for t in re.findall(r'text="([^"]{1,26})"', x20m) if t][:12]
c20["oldest_option"] = "Oldest first" in x20m
tap_text(x20m, "Oldest first"); wait(1)
p20 = prefs("bc0020-after")
c20["prefs_sort"] = p20.get("article_list_sort_order")
# 返回文章列表验证重排
back(); wait(1); back(); wait(2)
x20l = dump("bc0020-android-list-oldest.xml")
titles20 = [t for t in re.findall(r'text="([^"]{25,})"', x20l)]
c20["list_first_titles"] = [t[:42] for t in titles20[:2]]
print("[BC-0020]", c20)
LOG.append(["BC-0020", "sort-switch", c20])

# ============ BC-0017 终复核（主题+排序持久） ============
print("=== BC-0017 final ===")
sh(f"am force-stop {PKG}"); wait(2)
sh(f"am start -n {ACT}"); wait(5)
x17 = dump("bc0017-android-coldstart-final.xml")
t17 = re.findall(r'text="([^"]{25,})"', x17)
p17 = prefs("bc0017-final")
c17 = {"no_add_account": "Add Account" not in x17,
       "ars_feed_listed": "Ars Technica" in x17,
       "article_rows": len(t17),
       "first_titles": [t[:42] for t in t17[:2]],
       "prefs_account_id_present": bool(p17.get("account_id")),
       "prefs_app_theme_kept": p17.get("app_theme"),
       "prefs_sort_kept": p17.get("article_list_sort_order")}
print("[BC-0017]", c17)
LOG.append(["BC-0017", "cold-restart-persistence-final", c17])

# ============ BC-0021 ============
print("=== BC-0021 ===")
c21 = {"reader_opened": False, "style_entry": None, "panel": None}
if t17:
    c = bounds(x17, t17[0])
    if c:
        sh(f"input tap {c[0]} {c[1]}"); wait(4)
        x21 = dump("bc0021-android-reader.xml")
        c21["reader_opened"] = len(re.findall(r'text="[^"]{10,}"', x21)) > 2
        se = bounds(x21, "Aa") or bounds(x21, "Aa", "content-desc")
        c21["style_entry"] = bool(se)
        if se:
            sh(f"input tap {se[0]} {se[1]}"); wait(2)
            x21p = dump("bc0021-android-style-panel.xml")
            c21["panel"] = {"font": any(k in x21p for k in ["Small", "Medium", "Large"]),
                            "align": any(k in x21p for k in ["Left", "Center", "Justify"]),
                            "texts": [t for t in re.findall(r'text="([^"]{1,24})"', x21p) if t][:16]}
            p21 = prefs("bc0021")
            c21["prefs_article_font_size"] = p21.get("article_font_size")
            back(); wait(1)
print("[BC-0021]", c21)
LOG.append(["BC-0021", "style-shell", c21])

back(); wait(1); back(); wait(1)
sh(f"am force-stop {PKG}")
print("[reset] android force-stopped")
# 合并此前的 BC-0018 结果
prev = os.path.join(OUT, "android-manual-checks.json")
merged = {"device": "emulator-5554", "package": PKG,
          "log": [["BC-0018", "settings-page",
                   {"drawer_has_settings_entry": True, "display_section": True, "general_section": True,
                    "sections_snapshot": ["General", "Display & Appearance", "Gestures", "Account", "About", "Settings"],
                    "drawer_descs": ["Close navigation menu", "Open settings", "Refresh all", "Add Feed"]}]] + LOG}
with open(prev, "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=1)
print("DONE")