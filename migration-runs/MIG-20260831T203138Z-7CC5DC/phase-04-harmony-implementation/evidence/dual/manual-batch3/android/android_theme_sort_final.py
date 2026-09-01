#!/usr/bin/env python3
"""Android 批次3最终轮：reader 样式壳 + Theme Dark + Article Sort 切换 + 持久终复核。subprocess timeout=30。"""
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

# ---------- BC-0021：reader 样式入口（点文章标题而非 feed 名） ----------
print("=== BC-0021 reader ===")
xl = dump("f0-list.xml")
art = None
for t in re.findall(r'text="([^"]{25,})"', xl):
    if t.startswith("Ars Technica"): continue
    c = bounds(xl, t)
    if c: art = (t, c); break
c21 = {"style_entry": None, "panel": None}
if art:
    print("[article]", art[0][:40], art[1])
    sh(f"input tap {art[1][0]} {art[1][1]}"); wait(4)
    x21 = dump("bc0021-android-reader.xml")
    rd_texts = [t for t in re.findall(r'text="([^"]{1,40})"', x21) if t]
    rd_descs = [d for d in re.findall(r'content-desc="([^"]{1,40})"', x21) if d]
    print("[reader] texts:", rd_texts[:12], "descs:", rd_descs[:12])
    c21["reader_dump_ref"] = "bc0021-android-reader.xml"
    se = None
    for cand in ["Aa"]:
        se = bounds(x21, cand) or bounds(x21, cand, "content-desc")
    if not se:  # 动态找含 Aa/font/style/display 的 desc
        for d in rd_descs:
            if any(k in d.lower() for k in ["aa", "font", "style", "display", "text"]):
                se = bounds(x21, d, "content-desc"); break
    c21["style_entry"] = bool(se)
    if se:
        sh(f"input tap {se[0]} {se[1]}"); wait(2)
        x21p = dump("bc0021-android-style-panel.xml")
        c21["panel"] = {"font": any(k in x21p for k in ["Small", "Medium", "Large", "Font"]),
                        "align": any(k in x21p for k in ["Left", "Center", "Justify", "Align"]),
                        "texts": [t for t in re.findall(r'text="([^"]{1,26})"', x21p) if t][:16]}
        p21 = prefs("bc0021")
        c21["prefs_article_font_size"] = p21.get("article_font_size")
        back(); wait(1)
    back(); wait(2)
else:
    back(); wait(1)
print("[BC-0021]", c21)
LOG.append(["BC-0021", "style-shell", c21])

# ---------- BC-0019：Theme Dark（与 Harmony 走查同口径） ----------
print("=== BC-0019 theme dark ===")
xl = dump("f1-list.xml")
sh(f"input tap {HAMBURGER[0]} {HAMBURGER[1]}"); wait(2)
xd = dump("f1-drawer.xml")
c = bounds(xd, "Open settings", "content-desc") or bounds(xd, "Settings")
sh(f"input tap {c[0]} {c[1]}"); wait(3)
xs = dump("f1-settings.xml")
tap_text(xs, "Display &amp; Appearance", label="Display & Appearance"); wait(2)
x19 = dump("bc0019-android-display-panel.xml")
c19 = {"panel_snapshot": [t for t in re.findall(r'text="([^"]{1,28})"', x19) if t][:16]}
ok_dark = tap_text(x19, "Dark", label="Theme Dark segment")
wait(2)
p19 = prefs("bc0019-dark")
c19.update({"dark_tapped": ok_dark, "prefs_app_theme": p19.get("app_theme"),
            "prefs_theme_mode": p19.get("theme_mode")})
x19a = dump("bc0019-android-after-dark.xml")
print("[BC-0019]", c19)
LOG.append(["BC-0019", "theme-switch-dark", c19])

# ---------- BC-0020：Article Sort 切换 ----------
print("=== BC-0020 article sort ===")
back(); wait(1)
x20 = dump("f2-settings.xml")
if "General" not in x20: back(); wait(1); x20 = dump("f2b-settings.xml")
tap_text(x20, "General"); wait(2)
x20g = dump("bc0020-android-general.xml")
c20 = {"general_snapshot": [t for t in re.findall(r'text="([^"]{1,30})"', x20g) if t][:18]}
tap_text(x20g, "Newest First", label="Article Sort current value"); wait(1.5)
x20m = dump("bc0020-android-sort-menu.xml")
menu = [t for t in re.findall(r'text="([^"]{1,30})"', x20m) if t]
c20["sort_menu_snapshot"] = menu[:14]
picked = None
for opt in ["Oldest First", "Oldest first", "Newest First", "Last Updated"]:
    if opt in x20m and opt != "Newest First":
        tap_text(x20m, opt, label=f"sort -> {opt}"); picked = opt; break
if not picked and "Last Updated" in x20m:
    tap_text(x20m, "Last Updated", label="sort -> Last Updated"); picked = "Last Updated"
wait(1)
p20 = prefs("bc0020-after")
c20.update({"picked": picked, "prefs_sort": p20.get("article_list_sort_order")})
back(); wait(1); back(); wait(2)
x20l = dump("bc0020-android-list-after-sort.xml")
c20["list_first_titles"] = [t[:42] for t in re.findall(r'text="([^"]{25,})"', x20l)[:2]]
print("[BC-0020]", c20)
LOG.append(["BC-0020", "article-sort-switch", c20])

# ---------- BC-0017 持久终复核 ----------
print("=== BC-0017 final persistence ===")
sh(f"am force-stop {PKG}"); wait(2)
sh(f"am start -n {ACT}"); wait(5)
x17 = dump("bc0017-android-coldstart-final2.xml")
p17 = prefs("bc0017-final")
c17 = {"no_add_account": "Add Account" not in x17,
       "ars_feed_listed": "Ars Technica" in x17,
       "article_rows": len(re.findall(r'text="([^"]{25,})"', x17)),
       "prefs_account_id_present": bool(p17.get("account_id")),
       "prefs_app_theme_kept": p17.get("app_theme"),
       "prefs_theme_mode_kept": p17.get("theme_mode"),
       "prefs_sort_kept": p17.get("article_list_sort_order")}
print("[BC-0017]", c17)
LOG.append(["BC-0017", "cold-restart-persistence-final", c17])

# ---------- 复位 ----------
sh(f"am force-stop {PKG}")
print("[reset] android force-stopped")

prev = json.load(open(os.path.join(OUT, "android-manual-checks.json"), encoding="utf-8"))
seen = set()
for row in prev["log"]: seen.add(row[0])
for row in LOG:
    if row[0] in seen:
        prev["log"] = [r for r in prev["log"] if r[0] != row[0]]
    prev["log"].append(row)
with open(os.path.join(OUT, "android-manual-checks.json"), "w", encoding="utf-8") as f:
    json.dump(prev, f, ensure_ascii=False, indent=1)
print("DONE")