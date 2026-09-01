#!/usr/bin/env python3
"""Android 侧批次 3：先按 BC-0017 前置构造状态（Local 账户/Ars 订阅/已读/星标/主题），再跑 BC-0017~0021 手采。
所有 adb 调用 subprocess timeout=30 包裹。"""
import subprocess, time, re, os, json

ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
DEVICE = "emulator-5554"
PKG = "com.capyreader.app.debug"
ACT = f"{PKG}/com.capyreader.app.MainActivity"
OUT = os.path.dirname(os.path.abspath(__file__))

def adb(*args, timeout=30):
    r = subprocess.run([ADB, "-s", DEVICE] + list(args), capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr

def sh(cmd, timeout=30):
    return adb("shell", cmd, timeout=timeout)

def dump(name):
    sh("uiautomator dump /sdcard/ui.xml")
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
    pat = re.compile(rf'<node[^>]*?{attr}="{re.escape(text)}"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"')
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

# ---------- SEED：前置构造 ----------
print("=== SEED: local account + feed ===")
sh(f"am force-stop {PKG}"); wait(1)
sh(f"am start -n {ACT}"); wait(4)
x = dump("seed-00-addaccount-firstscreen.xml")  # 留证：五选项首屏（PART B Android 参照）
tap_text(x, "Local"); wait(3)
x = dump("seed-01-after-local.xml")
print("[seed] texts:", [t for t in re.findall(r'text="([^"]+)"', x) if t][:25])
# 若弹确认/Add Feed 对话框
if "Add Feed" in x or "Add feed" in x or "feed URL" in x.lower() or "URL" in x:
    pass  # 下面统一处理
# 主界面空态：找 Add feed 入口（FAB 或按钮）
entry = bounds(x, "Add Feed") or bounds(x, "Add feed") or bounds(x, "Add Feed", "content-desc") or bounds(x, "Add feed", "content-desc")
if not entry:
    # 尝试导航抽屉 FAB：Content-desc "Add Feed"
    for desc in re.findall(r'content-desc="([^"]+)"', x):
        if "add" in desc.lower():
            entry = bounds(x, desc, "content-desc"); break
if not entry:
    print("[seed] cannot find add-feed entry; texts above"); 
else:
    tap(entry); wait(2)
x = dump("seed-02-addfeed-dialog.xml")
print("[seed-dialog]", [t for t in re.findall(r'text="([^"]+)"', x) if t][:15])
# 输入 URL（input text：: 和 / 需转义 → 用逐段方式不可靠，直接试整串，失败则 %s 替换）
url = "https://feeds.arstechnica.com/arstechnica/index"
et = bounds(x, "", ) # 占位
# 找 EditText 节点坐标
m = re.search(r'<node[^>]*class="android.widget.EditText"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', x)
if m:
    ex, ey = (int(m.group(1)) + int(m.group(3))) // 2, (int(m.group(2)) + int(m.group(4))) // 2
    tap((ex, ey)); wait(1)
    sh(f"input text {url.replace(':', '\\:').replace('/', '\\/')}")  # adb input 对 : / 可直接传，转义保险
    wait(1)
    back()  # 收 IME
    wait(1)
    x = dump("seed-03-url-filled.xml")
    print("[seed-url]", "arstechnica" in x and "URL" in x or "arstechnica" in x)
    tap_text(x, "Add") or tap_text(x, "ADD")
wait(15)  # 等刷新
x = dump("seed-04-article-list.xml")
titles = [t for t in re.findall(r'text="([^"]{25,})"', x)]
print(f"[seed] article rows: {len(titles)}, first3: {titles[:3]}")

# 标记已读 + 星标：打开第一篇
if titles:
    c = bounds(x, titles[0])
    tap(c); wait(4)
    xr = dump("seed-05-reader.xml")
    acts = re.findall(r'content-desc="([^"]+)"', xr) + re.findall(r'text="([^"]+)"', xr)
    print("[seed-reader] actions:", [a for a in acts][:20])
    # Mark as read（阅读界面顶栏 icon desc）
    for key in ["Mark as read", "Mark as unread", "Star", "Starred"]:
        cc = bounds(xr, key, "content-desc") or bounds(xr, key)
        if cc: tap(cc); wait(1)
    back(); wait(2)

# 主题切换（前置要求"切换过主题"）：Settings → Display → Theme → Dark
x = dump("seed-06-main.xml")
nav = bounds(x, "Open navigation drawer", "content-desc")
if nav: tap(nav); wait(2); x = dump("seed-07-drawer.xml")
if tap_text(x, "Open settings", "content-desc", "settings entry") or tap_text(x, "Settings"):
    wait(2)
    x = dump("seed-08-settings.xml")
    if tap_text(x, "Display"):
        wait(2); x = dump("seed-09-display.xml")
        tap_text(x, "Theme") or tap_text(x, "Default")
        wait(1); x = dump("seed-10-theme-menu.xml")
        tap_text(x, "Newsprint")  # 与契约 steps 同口径（oracle 断言 NEWSPRINT）
        wait(2)
pseed = prefs("seed")
back(); wait(1); back(); wait(1)
sh(f"am force-stop {PKG}")
print("=== SEED DONE ===")

# ---------- BC-0017：冷启动持久验证 ----------
print("=== BC-0017 cold restart ===")
wait(2)
sh(f"am start -n {ACT}"); wait(5)
x = dump("bc0017-android-coldstart.xml")
c17 = {
    "no_add_account_first_screen": "Add Account" not in x,
    "ars_feed_listed_or_articles": ("Ars Technica" in x) or len(re.findall(r'text="([^"]{25,})"', x)) > 0,
    "first_titles": re.findall(r'text="([^"]{25,})"', x)[:3],
}
p17 = prefs("bc0017-coldstart")
c17["prefs_account_id_present"] = bool(p17.get("account_id"))
c17["prefs_app_theme"] = p17.get("app_theme")
print("[BC-0017]", c17)
LOG.append(["BC-0017", "cold-restart-persistence", c17])

# ---------- BC-0018：设置页 ----------
print("=== BC-0018 settings ===")
x18 = x
nav = bounds(x18, "Open navigation drawer", "content-desc")
if nav: tap(nav); wait(2); x18 = dump("bc0018-0-drawer.xml")
ok = tap_text(x18, "Open settings", "content-desc", "Open settings") or tap_text(x18, "Settings")
wait(3)
x18 = dump("bc0018-android-settings.xml")
c18 = {
    "settings_opened": ok,
    "display_section": "Display" in x18,
    "general_section": "General" in x18,
    "theme_row": "Theme" in x18,
}
print("[BC-0018]", c18)
LOG.append(["BC-0018", "settings-page", c18])

# ---------- BC-0019：主题（Newsprint 已在 seed 切过 → 复核 prefs+UI；再切回验证即时生效） ----------
print("=== BC-0019 theme ===")
tap_text(x18, "Display"); wait(2)
x19 = dump("bc0019-android-display.xml")
c19 = {"display_panel": "Theme" in x19 and ("Newsprint" in x19 or "Default" in x19)}
# 打开 Theme 选择器并切回 Default（验证第二次切换即时生效 + prefs 变化）
tap_text(x19, "Newsprint") or tap_text(x19, "Theme") or tap_text(x19, "Default")
wait(1)
x19m = dump("bc0019-android-theme-menu.xml")
c19["theme_menu_options"] = [t for t in ["Default", "Newsprint", "Dark"] if t in x19m]
tap_text(x19m, "Default"); wait(2)
p19 = prefs("bc0019-after")
c19["prefs_app_theme_after_switch_back"] = p19.get("app_theme")
x19a = dump("bc0019-android-after-default.xml")
c19["ui_after"] = "Display" in x19a
print("[BC-0019]", c19)
LOG.append(["BC-0019", "theme-switch", c19])

# ---------- BC-0020：排序 ----------
print("=== BC-0020 sort ===")
back(); wait(1)
x20 = dump("bc0020-0-settings.xml")
if "General" not in x20: back(); wait(1); x20 = dump("bc0020-0b-settings.xml")
tap_text(x20, "General"); wait(2)
x20 = dump("bc0020-android-general-before.xml")
c20 = {"sort_row_visible": "Newest first" in x20 or "Sort order" in x20}
tap_text(x20, "Newest first") or tap_text(x20, "Sort order")
wait(1)
x20m = dump("bc0020-android-sort-menu.xml")
c20["sort_menu_options"] = [t for t in ["Newest first", "Oldest first"] if t in x20m]
ok20 = tap_text(x20m, "Oldest first"); wait(1)
p20 = prefs("bc0020-after")
c20["prefs_sort"] = p20.get("article_list_sort_order")
# 返回文章列表看首行
back(); wait(1); back(); wait(2)
x20l = dump("bc0020-android-list-oldest.xml")
c20["list_first_titles"] = re.findall(r'text="([^"]{25,})"', x20l)[:3]
print("[BC-0020]", c20)
LOG.append(["BC-0020", "sort-switch", c20])

# ---------- BC-0021：阅读样式壳 ----------
print("=== BC-0021 style ===")
tgt = None
for t in c20["list_first_titles"] or re.findall(r'text="([^"]{25,})"', x20l):
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
        c21["panel"] = {
            "font": any(k in x21p for k in ["Small", "Medium", "Large"]),
            "align": any(k in x21p for k in ["Left", "Center", "Justify"]),
            "panel_texts": [t for t in re.findall(r'text="([^"]{1,20})"', x21p) if t][:15],
        }
        p21 = prefs("bc0021")
        back(); wait(1)
print("[BC-0021]", c21)
LOG.append(["BC-0021", "style-shell", c21])

# ---------- 复位冷态 ----------
back(); wait(1); back(); wait(1)
sh(f"am force-stop {PKG}")
print("[reset] android force-stopped")

with open(os.path.join(OUT, "android-manual-checks.json"), "w", encoding="utf-8") as f:
    json.dump({"device": DEVICE, "log": LOG}, f, ensure_ascii=False, indent=1)
print("DONE")