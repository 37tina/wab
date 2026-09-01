#!/usr/bin/env python3
"""Harmony 侧批次4四门槛采集：AddAccountScreen 五选项 + Feedbin 登录页。hdc subprocess timeout=30。"""
import subprocess, time, re, os, json

HDC = "/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc"
DEV = "127.0.0.1:5557"
BUNDLE = "com.capyreader.app.debug"
OUT = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT, exist_ok=True)

def hdc(*a, t=30):
    r = subprocess.run([HDC, "-t", DEV] + list(a), capture_output=True, text=True, timeout=t)
    return r.returncode, r.stdout, r.stderr

def sh(cmd, t=30):
    return hdc("shell", cmd, t=t)

def dump(name):
    """uitest dumpLayout -p；从输出解析随机文件名并拉回"""
    for _ in range(3):
        rc, out, err = sh("uitest dumpLayout -p /data/local/tmp")
        m = re.search(r"/data/local/tmp/[\w./-]+\.json", (out or "") + (err or ""))
        if m:
            f = m.group(0)
            rc2, o2, _ = hdc("file", "recv", f, os.path.join(OUT, name))
            sh(f"rm -f {f}")
            if os.path.exists(os.path.join(OUT, name)):
                with open(os.path.join(OUT, name), encoding="utf-8") as fh:
                    return fh.read()
        time.sleep(1.5)
    raise RuntimeError(f"dumpLayout failed {name}")

def texts(x):
    return [t for t in re.findall(r'"text"\s*:\s*"([^"]+)"', x) if t]

def bounds_of(x, text):
    # 属性型 json：找 text 的 center
    for m in re.finditer(r'\{[^{}]*"text"\s*:\s*"' + re.escape(text) + r'"[^{}]*\}', x):
        seg = m.group(0)
        b = re.search(r'"center"\s*:\s*\{"x"\s*:\s*(\d+),"y"\s*:\s*(\d+)\}', seg) or \
            re.search(r'\[\s*(\d+),\s*(\d+)\s*\]', seg)
        if b:
            return int(b.group(1)), int(b.group(2))
        rct = re.search(r'"rect"\s*:\s*\{[^}]*"left"\s*:\s*(\d+)[^}]*"top"\s*:\s*(\d+)[^}]*"width"\s*:\s*(\d+)[^}]*"height"\s*:\s*(\d+)', seg)
        if rct:
            l, tp, w, h = map(int, rct.groups())
            return l + w // 2, tp + h // 2
    return None

def tap(c): sh(f"uinput -T -m {c[0]} {c[1]}")
def back(): sh("uinput -K -d 2 -u 2")
def wait(s=2): time.sleep(s)

res = {}
# 冷启动首屏
sh(f"aa force-stop {BUNDLE}"); wait(1)
sh(f"aa start -a Ability -b {BUNDLE}"); wait(5)
x = dump("b4-harmony-addaccount-coldstart.json")
t0 = texts(x)
print("[coldstart]", t0[:20])
res["addaccount_options_visible"] = {k: (k in x) for k in ["Feedbin", "FreshRSS", "Miniflux", "Reader", "Local"]}
res["coldstart_texts"] = t0[:20]

# 点 Feedbin → 登录页
c = bounds_of(x, "Feedbin")
res["feedbin_tappable"] = bool(c)
if c:
    tap(c); wait(3)
    x2 = dump("b4-harmony-feedbin-login.json")
    t2 = texts(x2)
    print("[feedbin-login]", t2[:20])
    res["feedbin_login_texts"] = t2[:20]
    res["login_fields"] = {k: (k.lower() in x2.lower()) for k in ["Server", "Username", "Password", "Email", "API"]}
    # 无 no-op：确认有输入框（TextField）
    res["textfields_present"] = ("TextField" in x2) or len(t2) > 3
    back(); wait(1.5)
sh(f"aa force-stop {BUNDLE}")
print("[reset] harmony force-stopped")
with open(os.path.join(OUT, "harmony-b4-probe.json"), "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print("RESULT:", json.dumps(res, ensure_ascii=False)[:800])