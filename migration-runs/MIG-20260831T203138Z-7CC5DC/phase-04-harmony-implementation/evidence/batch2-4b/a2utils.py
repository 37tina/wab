#!/usr/bin/env python3
# 4B-R3 Android 同口径走查工具
import subprocess, os, re, time

ADB = os.path.expanduser('~/Library/Android/sdk/platform-tools/adb')
EV = '/Users/rainyday/Desktop/finale/migration-runs/MIG-20260831T203138Z-7CC5DC/phase-04-harmony-implementation/evidence/batch2-4b'

def sh(*args, timeout=30):
    r = subprocess.run([ADB, '-s', 'emulator-5554', *args], capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr

def a_tap(x, y):
    return sh('shell', 'input', 'tap', str(x), str(y))

def a_text(s):
    return sh('shell', 'input', 'text', s)

def a_back():
    return sh('shell', 'input', 'keyevent', '4')

def a_dump(name):
    """uiautomator dump -> 解析 XML 取 text/content-desc/bounds"""
    out = sh('shell', 'uiautomator', 'dump', '/sdcard/a2_dump.xml')
    xml = sh('shell', 'cat', '/sdcard/a2_dump.xml')
    with open(f'{EV}/{name}.xml', 'w') as f:
        f.write(xml)
    nodes = []
    for m in re.finditer(r'<node[^>]*?/?>', xml):
        tag = m.group(0)
        def attr(a):
            mm = re.search(rf'{a}="([^"]*)"', tag)
            return mm.group(1) if mm else ''
        t, d, b = attr('text'), attr('content-desc'), attr('bounds')
        if t or d:
            nodes.append({'text': t, 'desc': d, 'bounds': b, 'click': attr('clickable')})
    return nodes

def center(bounds):
    m = re.findall(r'(\d+),(\d+)', bounds)
    if len(m) >= 2:
        return (int(m[0][0])+int(m[1][0]))//2, (int(m[0][1])+int(m[1][1]))//2
    return None

def a_find_tap(nodes, keyword, field='both'):
    for n in nodes:
        hay = n['text'] + ' ' + n['desc']
        if keyword.lower() in hay.lower():
            c = center(n['bounds'])
            if c:
                print(f'  tap {keyword!r} @ {c}')
                a_tap(*c)
                return c
    print(f'  !! not found: {keyword}')
    return None

def start_app():
    return sh('shell', 'monkey', '-p', 'com.capyreader.app.debug', '-c', 'android.intent.category.LAUNCHER', '1')