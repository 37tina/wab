#!/usr/bin/env python3
"""Android 批次3手采集续跑：seed URL 输入（修复版）+ BC-0017~0021。subprocess timeout=30。"""
import subprocess, time, re, os, json

ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
DEVICE = "emulator-5554"
PKG = "com.capyreader.app.debug"
ACT = f"{PKG}/com.capyreader.app.MainActivity"
OUT = os.path.dirname(os.path.abspath(__file__))
URL = "https://feeds.arstechnica.com/arstechnica/index"

def adb(*args, timeout=30):
    r = subprocess.run([ADB, "-s", DEVICE] + list(args), capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr

def sh(cmd, timeout=30):
    return adb("shell", cmd, timeout=timeout)

def dump(name, retries=3):
    for i in range(retries):
        rc, out, err = sh("uiautomator dump /sdcard/ui.xml")
        if "dumped to" in (out or ""):
            adb("pull", "/sdcard/ui.xml", os.path.join(OUT, name))
            with open(os.path.join(OUT, name), encoding="utf-8") as f:
                x = f.read()
            if len(x) > 500:
                return x
        time.sleep(1.5)
    print(f"[dump-warn] {name} degraded")
    adb("pull", "/sdcard/ui.xml", os.path.join(OUT, name))
    with open(os.path.join(OUT, name), encoding="utf-8") as f:
        return f.read()

def prefs(tag):
    rc, out, err = sh(f"run-as {PKG} cat /data/data/{PKG}/shared_prefs/default.xml")
    with open(os.path.join(OUT, f"prefs-{tag}.xml"), "w") as f:
        f.write(out if rc == 0 else f"RC={rc} ERR={err}\n{out}")
    d = dict(re.findall(r'name="([\w_]+)"[^>]*>([^<]*)<', out or ""))
    keys = ["account_id", "app_theme", "theme_mode", "article_list_sort_order"]
    print(f"[prefs:{tag}]", {k: d.get(k) for k in keys})
    return d

def bounds(xml, text, attr="text"):
    for nm in re.finditer(r"<node[^>]*>", xml):
        node = nm.group(0)
        if f'{attr}="{text}"' in node:
            b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
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

def tap(c): sh(f"input tap {c[0]} {c[1]}")
def back(): sh("input keyevent 4")
def wait(s=2): time.sleep(s)
LOG = []

print("=== SEED2: add feed URL ===")
sh(f"am force-stop {PKG}"); wait(1)
sh(f"am start -n {ACT}"); wait(5)
x = dump("seed2-00-main.xml")
print("[main]", [t for t in re.findall(r'text="([^"]+)"', x) if t][:12])
# 若在 Add Account 首屏（无账户兜底）
if "Add Account" in x:
    tap_text(x, "Local"); wait(3); x = dump("seed2-01-after-local.xml")
af = bounds(x, "Add Feed") or bounds(x, "Add Feed", "content-desc") or bounds(x, "Add feed")
if not af:
    print("[FATAL] no Add Feed entry"); raise SystemExit(1)
tap(af); wait(2)
x = dump("seed2-02-dialog.xml")
print("[dialog]", [t for t in re.findall(r'text="([^"]+)"', x) if t][:12])
m = re.search(r'<node[^>]*EditText[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', x)
if not m:
    print("[FATAL] no EditText"); raise SystemExit(1)
ex, ey = (int(m.group(1)) + int(m.group(3))) // 2, (int(m.group(2)) + int(m.group(4))) // 2
tap((ex, ey)); wait(1.5)
# URL 直接传（无空格，不需转义；adb shell input text 原样支持 : / . -）
sh(f'input text "{URL}"'); wait(1.5)
back(); wait(1.5)  # 收 IME
x = dump("seed2-03-url-filled.xml")
filled = URL in x or "arstechnica" in x
print(f"[url-filled] {filled}")
if not filled:  # 再试一次焦点+输入
    tap((ex, ey)); wait(1); sh(f'input text "{URL}"'); wait(1); back(); wait(1)
    x = dump("seed2-03b-url-filled.xml"); filled = "arstechnica" in x
    print(f"[url-filled-retry] {filled}")
ok_add = tap_text(x, "Add", label="Add feed confirm")
wait(18)  # 等抓取
x = dump("seed2-04-article-list.xml")
titles = [t for t in re.findall(r'text="([^"]{25,})"', x)]
print(f"[seed2] articles={len(titles)} first3={[t[:40] for t in titles[:3]]}")

# 标记已读 + 星标（第一篇）
if titles:
    c = bounds(x, titles[0]); tap(c); wait(4)
    xr = dump("seed2-05-reader.xml")
    for key in ["Mark as unread", "Mark as read", "Starred", "Star"]:
        cc = bounds(xr, key, "content-desc") or bounds(xr, key)
        if cc: tap(cc); wait(1.2)
    back(); wait(2)

# 主题（前置：切换过主题；用 Dark 与 Harmony 走查同口径，再回 Default 留 NEWSPRINT 断言给 BC-0019 复测）
x = dump("seed2-06-main.xml")
nav = bounds(x, "Open navigation drawer", "content-desc")
if nav: tap(nav); wait(2); x = dump("seed2-07-drawer.xml")
if tap_text(x, "Open settings", "content-desc", "settings entry"):
    wait(2); x = dump("seed2-08-settings.xml")
    if tap_text(x, "Display"):
        wait(2); x = dump("seed2-09-display.xml")
        tap_text(x, "Theme") or tap_text(x, "Default") or tap_text(x, "Newsprint")
        wait(1); xm = dump("seed2-10-theme-menu.xml")
        print("[theme-menu]", [t for t in ["Default", "Newsprint"] if t in xm])
        tap_text(xm, "Newsprint"); wait(2)
prefs("seed2")
back(); wait(1); back(); wait(1)
sh(f"am force-stop {PKG}")
print("=== SEED2 DONE ===")

# ---------- BC-0017 ----------
print("=== BC-0017 ===")
wait(2); sh(f"am start -n {ACT}"); wait(5)
x = dump("bc0017-android-coldstart.xml")
t17 = re.findall(r'text="([^"]{25,})"', x)
c17 = {
    "no_add_account_first_screen": "Add Account" not in x,
    "ars_feed_listed": "Ars Technica" in x,
    "article_rows": len(t17),
    "first_titles": [t[:45] for t in t17[:3]],
}
p17 = prefs("bc0017-coldstart")
c17["prefs_account_id_present"] = bool(p17.get("account_id"))
c17["prefs_app_theme"] = p17.get("app_theme")
print("[BC-0017]", c17)
LOG.append(["BC-0017", "cold-restart-persistence", c17])

# ---------- BC-0018 ----------
x18 = x
nav = bounds(x18, "Open navigation drawer", "content-desc")
if nav: tap(nav); wait(2); x18 = dump("bc0018-0-drawer.xml")
ok = tap_text(x18, "Open settings", "content-desc", "Open settings")
wait(3)
x18 = dump("bc0018-android-settings.xml")
c18 = {"settings_opened": ok, "display": "Display" in x18, "general": "General" in x18,
       "theme_row": "Theme" in x18, "sections": [t for t in re.findall(r'text="([^"]{3,25})"', x18) if t][:15]}
print("[BC-0018]", c18)
LOG.append(["BC-0018", "settings-page", c18])

# ---------- BC-0019（seed 已切 Newsprint → 验证 prefs 保持 + 再切回 Default 验证即时生效） ----------
tap_text(x18, "Display"); wait(2)
x19 = dump("bc0019-android-display.xml")
c19 = {"display_panel": "Theme" in x19}
tap_text(x19, "Newsprint") or tap_text(x19, "Theme") or tap_text(x19, "Default")
wait(1)
x19m = dump("bc0019-android-theme-menu.xml")
c19["menu_options"] = [t for t in ["Default", "Newsprint"] if t in x19m]
tap_text(x19m, "Default"); wait(2)
p19 = prefs("bc0019-after")
c19["prefs_app_theme"] = p19.get("app_theme")
x19a = dump("bc0019-android-after-default.xml")
c19["ui_still_display"] = "Theme" in x19a
print("[BC-0019]", c19)
LOG.append(["BC-0019", "theme-switch", c19])

# ---------- BC-0020 ----------
back(); wait(1)
x20 = dump("bc0020-0-settings.xml")
if "General" not in x20: back(); wait(1); x20 = dump("bc0020-0b-settings.xml")
tap_text(x20, "General"); wait(2)
x20 = dump("bc0020-android-general-before.xml")
c20 = {"sort_row": "Newest first" in x20 or "Sort order" in x20}
tap_text(x20, "Newest first") or tap_text(x20, "Sort order")
wait(1)
x20m = dump("bc0020-android-sort-menu.xml")
c20["menu_options"] = [t for t in ["Newest first", "Oldest first"] if t in x20m]
tap_text(x20m, "Oldest first"); wait(1)
p20 = prefs("bc0020-after")
c20["prefs_sort"] = p20.get("article_list_sort_order")
back(); wait(1); back(); wait(2)
x20l = dump("bc0020-android-list-oldest.xml")
c20["list_first_titles"] = [t[:45] for t in re.findall(r'text="([^"]{25,})"', x20l)[:3]]
print("[BC-0020]", c20)
LOG.append(["BC-0020", "sort-switch", c20])

# ---------- BC-0021 ----------
tgt = None
for t in re.findall(r'text="([^"]{25,})"', x20l):
    cc = bounds(x20l, t)
    if cc: tgt = (t, cc); break
c21 = {"reader_opened": False, "style_entry": None, "panel": None}
if tgt:
    tap(tgt[1]); wait(4)
    x21 = dump("bc0021-android-reader.xml")
    c21["reader_opened"] = len(re.findall(r'text="[^"]{10,}"', x21)) > 2
    se = bounds(x21, "Aa") or bounds(x21, "Aa", "content-desc")
    c21["style_entry"] = bool(se)
    if se:
        tap(se); wait(2)
        x21p = dump("bc0021-android-style-panel.xml")
        c21["panel"] = {"font": any(k in x21p for k in ["Small", "Medium", "Large"]),
                        "align": any(k in x21p for k in ["Left", "Center", "Justify"]),
                        "texts": [t for t in re.findall(r'text="([^"]{1,22})"', x21p) if t][:14]}
        prefs("bc0021")
        back(); wait(1)
print("[BC-0021]", c21)
LOG.append(["BC-0021", "style-shell", c21])

back(); wait(1); back(); wait(1)
sh(f"am force-stop {PKG}")
print("[reset] android force-stopped")
with open(os.path.join(OUT, "android-manual-checks.json"), "w", encoding="utf-8") as f:
    json.dump({"device": DEVICE, "package": PKG, "log": LOG}, f, ensure_ascii=False, indent=1)
print("DONE")