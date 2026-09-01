#!/usr/bin/env python3
"""Harmony r1 自测（FEAT-ONLINE-ACCOUNT-UI R6 修复复验）：
冷启动 AddAccount -> Feedbin 登录页 -> 假凭证 Log In -> 错误反馈 -> 返回 -> FreshRSS 表单差异。
hdc subprocess timeout=30。dump: uitest dumpLayout + uiInput click/inputText。"""
import subprocess, time, re, os, json

HDC = "/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc"
DEV = "127.0.0.1:5557"
BUNDLE = "com.capyreader.app.debug"
OUT = os.path.dirname(os.path.abspath(__file__))
DEV_DUMP = "/data/local/tmp/r1dump.json"

def hdc(*a, t=30):
    r = subprocess.run([HDC, "-t", DEV] + list(a), capture_output=True, text=True, timeout=t)
    return r.returncode, r.stdout, r.stderr

def sh(cmd, t=30):
    return hdc("shell", cmd, t=t)

def dump(name):
    for _ in range(3):
        rc, out, err = sh(f"uitest dumpLayout -p {DEV_DUMP}")
        if rc == 0:
            hdc("file", "recv", DEV_DUMP, os.path.join(OUT, name))
            sh(f"rm -f {DEV_DUMP}")
            if os.path.exists(os.path.join(OUT, name)):
                with open(os.path.join(OUT, name), encoding="utf-8") as fh:
                    return fh.read()
        time.sleep(1.5)
    raise RuntimeError(f"dumpLayout failed {name}")

def texts(x):
    return [t for t in re.findall(r'"text"\s*:\s*"([^"]+)"', x) if t]

def hints(x):
    return [t for t in re.findall(r'"hint"\s*:\s*"([^"]+)"', x) if t]

def bounds_of(x, key, attr="text"):
    """节点平铺属性；bounds '[l,t][r,b]' -> 中心坐标"""
    for m in re.finditer(r'\{[^{}]*"' + attr + r'"\s*:\s*"' + re.escape(key) + r'"[^{}]*\}', x):
        b = re.search(r'"bounds"\s*:\s*"\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', m.group(0))
        if b:
            l, t, r, bo = map(int, b.groups())
            return (l + r) // 2, (t + bo) // 2
    return None

def click(c): sh(f"uitest uiInput click {c[0]} {c[1]}")
def input_text(c, s): sh(f"uitest uiInput inputText {c[0]} {c[1]} {s}")
def back(): sh("uitest uiInput keyEvent Back")
def wait(s=2): time.sleep(s)

res = {}

# 1) 清数据冷启动 -> Add Account 五选项
sh(f"bm clean -n {BUNDLE} -d"); wait(1)
sh(f"aa force-stop {BUNDLE}"); wait(1)
sh(f"aa start -b {BUNDLE} -a EntryAbility"); wait(6)
x = dump("r1-01-addaccount-coldstart.json")
res["addaccount_options_visible"] = {k: (k in x) for k in ["Feedbin", "FreshRSS", "Miniflux", "Reader", "Local"]}
print("[r1-01 coldstart]", texts(x)[:12])

# 2) tap Feedbin -> 登录页表单
c = bounds_of(x, "Feedbin")
res["feedbin_tappable"] = bool(c)
if not c:
    raise RuntimeError("Feedbin row not found")
click(c); wait(3)
x2 = dump("r1-02-feedbin-login.json")
t2 = texts(x2)
print("[r1-02 feedbin-login]", t2[:16])
res["feedbin_login_texts"] = t2[:16]
res["login_form_gate1"] = {k: (k in x2) for k in ["Username", "Password", "Log In", "Advanced options"]}
res["feedbin_no_url_field"] = ("Server URL" not in x2 and "API URL" not in x2)

# 3) 假凭证输入 -> 收键盘 -> Log In -> 错误反馈
u = bounds_of(x2, "Email", attr="hint")
p = bounds_of(x2, "Password", attr="hint")
res["fields_locatable"] = bool(u) and bool(p)
print("[fields]", u, p)
if u and p:
    click(u); wait(0.8)
    input_text(u, "capy@example.com"); wait(0.8)
    click(p); wait(0.8)
    input_text(p, "wrong-password"); wait(0.8)
    back(); wait(1.2)  # 收起软键盘（否则 dump 只剩 IME 焦点窗口）
    xmid = dump("r1-03a-login-filled.json")
    res["username_echo_in_dump"] = "capy@example.com" in xmid
    res["password_masked"] = "wrong-password" not in xmid
    b = bounds_of(xmid, "Log In")
    print("[login-btn]", b)
    if b:
        click(b); wait(20)  # 网络尝试最长 ~20s
        x3 = dump("r1-03b-login-error.json")
        t3 = texts(x3)
        print("[r1-03b after LogIn]", t3[:16])
        res["after_login_texts"] = t3[:16]
        res["error_feedback"] = {k: (k in x3) for k in
            ["Incorrect username or password", "Connection failed", "Logging in"]}

# 4) 返回 -> Add Account（首击可能仅收键盘，循环直到回到 Add Account）
for _ in range(3):
    back(); wait(1.6)
    x4 = dump("r1-04-back-addaccount.json")
    if "Add Account" in x4:
        break
res["back_to_addaccount"] = {k: (k in x4) for k in ["Add Account", "Feedbin", "Local"]}
print("[r1-04 back]", texts(x4)[:10])

# 5) FreshRSS 表单差异（BC-0003 hasCustomURL -> Server URL 可见，Advanced 展开）
c2 = bounds_of(x4, "FreshRSS")
if c2:
    click(c2); wait(3)
    x5 = dump("r1-05-freshrss-login.json")
    t5 = texts(x5)
    print("[r1-05 freshrss-login]", t5[:16])
    res["freshrss_form"] = {k: (k in x5) for k in ["FreshRSS", "Username", "Password", "Log In", "Server URL"]}
    res["freshrss_apiurl_hint"] = "API URL" in hints(x5)

sh(f"aa force-stop {BUNDLE}")
with open(os.path.join(OUT, "r1-probe.json"), "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print("RESULT:", json.dumps(res, ensure_ascii=False))
