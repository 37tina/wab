#!/usr/bin/env python3
# 4B-R3 批次2 差分收口工具：带超时的设备操作 + 嵌套树解析
import subprocess, sys, json, time, os

HDC = '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc'
ADB = os.path.expanduser('~/Library/Android/sdk/platform-tools/adb')
HTARGET = '127.0.0.1:5557'
ATARGET = 'emulator-5554'
EV = '/Users/rainyday/Desktop/finale/migration-runs/MIG-20260831T203138Z-7CC5DC/phase-04-harmony-implementation/evidence/batch2-4b'

def hdc_run(*args, timeout=30):
    r = subprocess.run([HDC, '-t', HTARGET, *args], capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr

def adb_run(*args, timeout=30):
    r = subprocess.run([ADB, '-s', ATARGET, *args], capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr

def h_click(x, y):
    return hdc_run('shell', 'uitest', 'uiInput', 'click', str(x), str(y))

def h_back():
    return hdc_run('shell', 'uitest', 'uiInput', 'keyEvent', 'Back')

def h_dump(name):
    """dump Harmony 布局到 EV/name.json，返回解析后的文本节点列表。
    注意：dumpLayout 输出到随机文件名 layout_<num>.json，必须从输出解析真实路径"""
    out = hdc_run('shell', 'uitest', 'dumpLayout')
    import re
    m = re.search(r'saved to:\s*(\S+)', out)
    if not m:
        print(f'[dump fail] {out[:200]}')
        return []
    path = m.group(1)
    js = hdc_run('shell', 'cat', path)
    hdc_run('shell', 'rm', '-f', path)  # 清理随机文件避免堆积
    with open(f'{EV}/{name}.json', 'w') as f:
        f.write(js)
    try:
        d = json.loads(js)
    except Exception as e:
        print(f'[dump parse fail: {e}] raw head: {js[:200]}')
        return []
    nodes = []
    def walk(n):
        a = n.get('attributes', {})
        t = a.get('text', '')
        if t or a.get('description'):
            nodes.append({'text': t, 'desc': a.get('description',''), 'bounds': a.get('bounds',''), 'id': a.get('id',''), 'key': a.get('key','')})
        for c in n.get('children', []) or []:
            walk(c)
    walk(d)
    return nodes

def find_center(bounds):
    # "[x1,y1][x2,y2]" -> (cx, cy)
    import re
    m = re.findall(r'(\d+),(\d+)', bounds)
    if len(m) >= 2:
        x1, y1 = int(m[0][0]), int(m[0][1]); x2, y2 = int(m[1][0]), int(m[1][1])
        return (x1+x2)//2, (y1+y2)//2
    return None

def h_find_tap(nodes, keyword, name=''):
    """按关键字找节点并点击，返回坐标或 None"""
    for n in nodes:
        if keyword.lower() in n['text'].lower() or keyword.lower() in n['desc'].lower():
            c = find_center(n['bounds'])
            if c:
                print(f'  tap {name or keyword} @ {c} (text={n["text"]!r})')
                h_click(*c)
                return c
    print(f'  !! not found: {keyword}')
    return None

def pull_probe(tag):
    """拉取语义探针，尝试多个路径"""
    paths = [
        '/data/app/el2/100/base/com.capyreader.app.debug/haps/entry/files/semantic-probe.json',
        '/data/app/el2/100/base/com.capyreader.app.debug/files/semantic-probe.json',
        '/data/storage/el2/base/files/semantic-probe.json',
    ]
    dst = f'{EV}/probe_{tag}.json'
    for p in paths:
        r = subprocess.run([HDC, '-t', HTARGET, 'file', 'recv', p, dst], capture_output=True, text=True, timeout=30)
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            try:
                return json.load(open(dst))
            except Exception:
                pass
    # 退路：shell cat
    for p in paths:
        out = hdc_run('shell', 'cat', p)
        if out.strip().startswith('{'):
            with open(dst, 'w') as f: f.write(out)
            try:
                return json.loads(out)
            except Exception:
                pass
    print(f'  !! probe not found: {tag}')
    return None

if __name__ == '__main__':
    pass