#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""android_data_probe -- Android Oracle 数据探针：真实读取应用持久化状态。

目的（收敛式重构批次 1，任务 #82）：
  gmi_runtime 的行为链断言目前只有 text_visible/text_gone/persist_after_restart
  （纯 UI 文本判定），缺少"数据真的写进去了"的 Oracle 证据。本探针对目标包
  做两类真实数据读取，产出机器可判定的语义状态 JSON（Oracle data 段）：

  1) Preferences 类
     - SharedPreferences XML（shared_prefs/*.xml）——全量键值解析；
     - MMKV（files/mmkv/*，二进制协议）——本地解析 varint KV 流 + 覆盖语义
       + 值启发式（bool/int/str/hex），解析失败降级 strings 提取，再失败标
       TOOL_GAP（绝不伪造）；
     - DataStore（files/datastore/*.preferences_pb）——第一版不解析，
       一律 TOOL_GAP 登记（不硬造数据）。
  2) SQLite/Room 类（databases/*，自动伴随 -wal/-shm 三件套）
     - 经 run-as（debuggable 包）或已 root 的 adbd 拉取到本地临时目录，
       用本地 sqlite3 CLI 只读查询（-readonly -json，WAL 数据可读）；
     - 设备端无 sqlite3 依赖（不在设备上执行任何写操作，探针全程只读）。

访问模式探测（按优先级，均不产生设备写副作用）：
  1. run-as：`run-as <pkg> true` 成功（包 DEBUGGABLE 才可行）；
  2. root：当前 adbd 已是 uid=0（本探针绝不主动执行 `adb root`）；
  3. 两者皆不可用 -> access_mode=DENIED，所有存储标 TOOL_GAP。

二进制安全：所有文件拉取统一走 `adb exec-out`（原始字节通道，无 pty 的
\\n->\\r\\n 转义风险；已与设备端 toybox md5sum 交叉验证）。

============================================================================
集成契约（gmi_runtime 消费方必读；本文件不修改 gmi_runtime.py，
由并行代理在 gmi_runtime 侧接线）：
============================================================================
调用时点：gmi_runtime.execute_behavior_chain 在现有三个快照时点各调用一次
本探针（subprocess，只读、幂等、可重复）：

    python android_data_probe.py --package <pkg> --device <serial> \\
        --objects <bc 声明的数据对象> --out <ev_dir>/data-before.json   # before 快照时点
    ...（操作序列执行后）
        --out <ev_dir>/data-after.json                                  # after 快照时点
    ...（force-stop 重启后）
        --out <ev_dir>/data-restart.json                                # restart 快照时点

其中 ev_dir = runtime-evidence/evidence/chains/<bc_id>/（与现有
operations.log / assertions.json 同目录）。三份 JSON 即该链的 data 段证据。

断言判定：BC.result_assertions 新增 data 类 kind，判定输入为上述三份
probe JSON。判定用本模块纯函数 evaluate_data_assertions()（可直接 import，
也可复制语义）：

    from android_data_probe import evaluate_data_assertions
    results = evaluate_data_assertions(
        [{"kind": "data_equals", "key": "prefs.sort_order", "value": "true"}],
        data_before=load(before.json), data_after=load(after.json),
        data_restart=load(restart.json))

kind 语义（fail-closed 分层）：
  - data_equals   : key 在 data_after 中解析成功且 == value -> PASS；
                    解析成功但值不等 -> FAIL（行为矛盾）；
                    after 文件缺失/该存储 TOOL_GAP/DENIED -> UNSUPPORTED
                    （采集受阻 != 行为矛盾，对齐 CHAIN_BLOCKED 路由理念，
                    由 chain_status 降级标注，不计入 FAIL）。
  - data_persists : 同上，但对 data_restart 判定（持久化 Oracle）。
  - data_changed  : key 在 before/after 均解析成功且值不同 -> PASS；
                    相同 -> FAIL；任一侧不可解析 -> UNSUPPORTED。
  - 未知 kind -> UNSUPPORTED（与 gmi_runtime 现有惯例一致）。

key 寻址语法（value 大小写敏感、精确匹配）：
  - prefs.<name>                      preferences 扁平段中的键
  - count:<table>                     tables.<table> 的行数
  - row:<table>[<col>=<v>].<col2>     表中首条 col==v 行的 col2 列值
  - exists:<table>[<col>=<v>]         表中是否存在 col==v 的行
值比较语义：同类型直接比较；str vs number 宽松数值比较（"1"==1）；
bool(true/false) 与 1/0 语义相等；其余不匹配即不等。

输出 JSON schema（android-data-probe/1）：
  {
    "schema": "android-data-probe/1",
    "package": "...", "device": "...", "captured_at": "UTC ISO8601",
    "access_mode": "run-as" | "root" | "DENIED",
    "preferences": {"<key>": <bool|int|float|str|list>},   # 多来源扁平合并
    "tables": {"<table>": [ {col: val, ...}, ... ]},       # 行对象数组
    "stores": [  # 每个发现的存储一条，审计用
      {"store": "shared_prefs:foo.xml", "path": "shared_prefs/foo.xml",
       "status": "READ|TOOL_GAP|ABSENT", "keys"?: N, "rows"?: N,
       "reason"?: "..."},
    ],
    "tool_gaps": [ {"store": "...", "reason": "..."} ]
  }

CLI：
  python android_data_probe.py --package com.nevoit.cresto \\
      --device emulator-5554 [--objects todo_items,todo_groups] \\
      --out probe.json [--adb adb] [--sqlite3 sqlite3] \\
      [--max-rows 200] [--timeout 30] [--verbose] [--no-prefs]

  --objects 逗号分隔：表名（在 db 表清单内则读取，否则记
  MISSING_IN_DB，不伪造）；留空默认读全部业务表（排除 sqlite_% /
  android_metadata 系统表）。preferences 不受 --objects 控制
  （默认全读，--no-prefs 关闭）。

退出码：0 = 探测完成（可含 TOOL_GAP，TOOL_GAP 是显式结果不是失败）；
        2 = 参数错误；3 = adb/设备不可达（此时也应产出 DENIED 报告文件
        而不是无输出崩溃——由调用方决定重试或降级）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "android-data-probe/1"

# 合法存储组件名校验（防路径注入：文件名/表名来自设备输出，白名单收紧）
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 系统表（不作为业务数据对象读取）
_SYSTEM_TABLES = {"android_metadata", "room_master_table"}

# MMKV 解析防御参数（实测 mmkv.default 预分配 16KB；键值均为小体量）
_MMKV_HEADER_BYTES = 8          # 前 8 字节 = actualSize(4) + crc(4)，实测不可靠，跳过
_MMKV_MAX_KEY_LEN = 512
_MMKV_MAX_VAL_LEN = 65536
_MMKV_MAX_PAIRS = 100000

# DataStore 第一版不解析（TOOL_GAP 登记即可）
_DATASTORE_GLOB = "*.preferences_pb"


# ============================================================================
# adb 封装（二进制安全：统一 exec-out）
# ============================================================================

def _run(argv: List[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, timeout=timeout)


def _adb_execout(adb: str, serial: str, shell_args: List[str],
                 timeout: int) -> Optional[bytes]:
    """`adb -s <serial> exec-out <shell_args...>` -> 原始 stdout 字节。

    exec-out 是二进制安全通道（无 pty 转义）。非零退出/超时 -> None。
    """
    argv = [adb, "-s", serial, "exec-out"] + shell_args
    try:
        cp = _run(argv, timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if cp.returncode != 0:
        return None
    return cp.stdout


def _adb_text(adb: str, serial: str, shell_args: List[str],
              timeout: int) -> Optional[str]:
    """exec-out -> UTF-8 文本（设备端 ls / id 等小输出）。"""
    raw = _adb_execout(adb, serial, shell_args, timeout)
    if raw is None:
        return None
    return raw.decode("utf-8", errors="replace")


def detect_access_mode(adb: str, serial: str, package: str,
                       timeout: int) -> str:
    """探测数据目录访问能力：run-as（debuggable）优先，其次已是 root 的 adbd。

    绝不主动 `adb root`（会重启 adbd，产生设备副作用）。
    返回 'run-as' | 'root' | 'DENIED'。
    """
    probe = _adb_execout(adb, serial, ["run-as", package, "true"], timeout)
    if probe is not None:
        return "run-as"
    who = _adb_text(adb, serial, ["id"], timeout)
    if who is not None and "uid=0" in who:
        # adbd 已是 root：直接绝对路径读取
        listing = _adb_text(adb, serial,
                            ["ls", f"/data/data/{package}"], timeout)
        if listing is not None:
            return "root"
    return "DENIED"


def _shell_prefix(mode: str, package: str) -> List[str]:
    """数据目录内相对路径的 exec-out 参数前缀。"""
    if mode == "run-as":
        return ["run-as", package]
    return ["cat", f"/data/data/{package}"]  # root 模式（无前缀 cat）


def list_data_dir(adb: str, serial: str, mode: str, package: str,
                  rel_dir: str, timeout: int) -> List[str]:
    """列出 <dataDir>/<rel_dir> 下条目名（目录不存在返回 []）。

    exec-out 非交互环境下 toybox ls 可能输出同行多列（实测两空格分隔），
    故强制 `ls -1` 且解析时收集行内全部 token（双保险）。
    """
    if mode == "DENIED":
        return []
    if mode == "run-as":
        args = ["run-as", package, "ls", "-1", rel_dir]
    else:
        args = ["ls", "-1", f"/data/data/{package}/{rel_dir}"]
    text = _adb_text(adb, serial, args, timeout)
    if text is None or "No such file" in text or "Not a directory" in text:
        return []
    names: List[str] = []
    for line in text.splitlines():
        for token in line.strip().split():
            if _SAFE_NAME_RE.match(token):
                names.append(token)
    return names


def pull_data_file(adb: str, serial: str, mode: str, package: str,
                   rel_path: str, timeout: int) -> Optional[bytes]:
    """拉取 <dataDir>/<rel_path> 原始字节；不存在/失败 -> None。"""
    if mode == "DENIED":
        return None
    if mode == "run-as":
        args = ["run-as", package, "cat", rel_path]
    else:
        args = ["cat", f"/data/data/{package}/{rel_path}"]
    return _adb_execout(adb, serial, args, timeout)


# ============================================================================
# SharedPreferences XML 解析（纯函数）
# ============================================================================

def parse_shared_prefs_xml(xml_text: str) -> Dict[str, Any]:
    """标准 SharedPreferences XML -> 扁平 {key: value}。

    支持节点：int / long / boolean / float / string / set（内含若干
    <string>）。解析失败抛 ET.ParseError（调用方按坏文件处理，不伪造）。
    """
    root = ET.fromstring(xml_text)
    out: Dict[str, Any] = {}
    for node in root:
        name = node.get("name")
        if not name:
            continue
        tag = node.tag.lower()
        if tag in ("int", "long"):
            out[name] = int(node.get("value", "0"))
        elif tag == "boolean":
            out[name] = node.get("value", "false").strip().lower() == "true"
        elif tag == "float":
            out[name] = float(node.get("value", "0"))
        elif tag == "string":
            out[name] = node.text if node.text is not None else ""
        elif tag == "set" or tag == "string-set":
            vals = [c.text if c.text is not None else ""
                    for c in node if c.tag.lower() == "string"]
            out[name] = vals
        else:
            # 未知节点：保留原始 value 便于审计，不丢弃不猜测
            out[name] = {"_raw_type": node.tag, "value": node.get("value")}
    return out


# ============================================================================
# MMKV 二进制解析（纯函数 + 防御）
# ============================================================================

def _read_varint(buf: bytes, pos: int) -> Tuple[int, int]:
    """protobuf base-128 varint -> (value, next_pos)。越界/超长抛 ValueError。"""
    result = 0
    shift = 0
    while pos < len(buf):
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")
    raise ValueError("varint truncated")


def decode_mmkv_value(raw: bytes) -> Any:
    """MMKV value 字节 -> 语义值（启发式，注释不确定性来源）。

    MMKV 不存类型元数据：putBool/putInt/putLong 均为 varint 编码，
    putString 为 UTF-8 原始字节，putFloat/putDouble 为 fixed32/64。
    启发式顺序（与实测 Cresto mmkv.default 一致）：
      1) varint 全量解码成功 -> 0/1 且字节长<=2 -> bool，否则 int；
      2) 全部为可打印 ASCII/合法 UTF-8（无控制字符）-> str；
      3) 兜底 -> "hex:<...>"（保留原始证据，不猜测语义）。
    """
    if not raw:
        return ""
    try:
        num, end = _read_varint(raw, 0)
        if end == len(raw):
            if num in (0, 1) and len(raw) <= 2:
                return bool(num)
            return num
    except ValueError:
        pass
    try:
        text = raw.decode("utf-8")
        if all(ch >= " " or ch in "\t\n\r" for ch in text):
            return text
    except UnicodeDecodeError:
        pass
    return "hex:" + raw.hex()


def parse_mmkv_binary(data: bytes) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """MMKV 主文件 -> (最终键值 dict, 原始 KV 序列)。

    文件布局（实测验证）：[0..7] 头（actualSize+crc，full-write 后可能为
    0 不可靠，跳过）；[8..] 连续 KV 流：varint key_len + key + varint
    val_len + val。MMKV 是 append-delta：同 key 后写覆盖先写。
    防御（解析 16KB 预分配区的脏区）：key 必须 1..512 字节可打印 ASCII、
    val_len <= 64KB、总对数 <= 100000；任一校验失败即停止（返回已解析
    部分），调用方据 KV 数决定 READ / 降级 strings / TOOL_GAP。
    """
    raw_pairs: List[Dict[str, Any]] = []
    pos = _MMKV_HEADER_BYTES
    end = len(data)
    while pos < end and len(raw_pairs) < _MMKV_MAX_PAIRS:
        try:
            klen, p = _read_varint(data, pos)
            if not (1 <= klen <= _MMKV_MAX_KEY_LEN):
                break
            key_bytes = data[p:p + klen]
            if len(key_bytes) != klen:
                break
            if not all(32 <= b < 127 for b in key_bytes):
                break  # 键名应可打印（MMKV 不限制，但业务键均如此；脏区防御）
            vlen, p2 = _read_varint(data, p + klen)
            if vlen > _MMKV_MAX_VAL_LEN:
                break
            val_bytes = data[p2:p2 + vlen]
            if len(val_bytes) != vlen:
                break
            key = key_bytes.decode("ascii")
            raw_pairs.append({"key": key, "value": decode_mmkv_value(val_bytes)})
            pos = p2 + vlen
        except ValueError:
            break
    final: Dict[str, Any] = {}
    for pair in raw_pairs:      # 顺序应用 -> 后写覆盖先写
        final[pair["key"]] = pair["value"]
    return final, raw_pairs


def extract_strings_fallback(data: bytes, min_len: int = 4) -> List[str]:
    """MMKV 解析失败的降级：strings 式提取可打印片段（标注 degraded）。"""
    return [m.group(0).decode("ascii")
            for m in re.finditer(rb"[ -~]{%d,}" % min_len, data)]


# ============================================================================
# SQLite/Room 读取（本地 sqlite3 CLI，只读）
# ============================================================================

def resolve_sqlite3(explicit: Optional[str]) -> Optional[str]:
    """定位本地 sqlite3 CLI（--sqlite3 显式优先，否则 PATH）。"""
    import shutil
    cand = explicit or shutil.which("sqlite3")
    if not cand:
        return None
    try:
        cp = _run([cand, "--version"], 10)
        if cp.returncode == 0:
            return cand
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def list_sqlite_tables(sqlite3_bin: str, db_path: Path, timeout: int
                       ) -> Optional[List[str]]:
    """列出库中业务表（排除 sqlite_% / android_metadata）。失败 -> None。"""
    sql = ("SELECT name FROM sqlite_master WHERE type='table' "
           "AND name NOT LIKE 'sqlite_%' AND name != 'android_metadata' "
           "ORDER BY name")
    cp = _run([sqlite3_bin, "-batch", "-readonly", str(db_path), sql], timeout)
    if cp.returncode != 0:
        return None
    names = [ln.strip() for ln in cp.stdout.decode("utf-8", errors="replace")
             .splitlines() if ln.strip()]
    return [n for n in names if _SAFE_TABLE_RE.match(n)]


def dump_sqlite_table(sqlite3_bin: str, db_path: Path, table: str,
                      max_rows: int, timeout: int
                      ) -> Optional[Dict[str, Any]]:
    """只读导出单表 -> {"rows": [...], "truncated": bool}。

    sqlite3 -json 输出 JSON 数组（空表输出空文本）。行对象内 blob 由 CLI
    转 base64 字符串、NULL 为 null，均为 JSON 安全类型。
    """
    if not _SAFE_TABLE_RE.match(table):
        return {"rows": [], "truncated": False, "error": "unsafe table name"}
    sql = f'SELECT * FROM "{table}" LIMIT {int(max_rows) + 1}'
    cp = _run([sqlite3_bin, "-batch", "-readonly", "-json",
               str(db_path), sql], timeout)
    if cp.returncode != 0:
        err = cp.stderr.decode("utf-8", errors="replace").strip()
        return {"rows": [], "truncated": False, "error": err[:200]}
    text = cp.stdout.decode("utf-8", errors="replace").strip()
    rows: List[Any] = []
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                rows = [r for r in parsed if isinstance(r, dict)]
        except json.JSONDecodeError:
            return {"rows": [], "truncated": False,
                    "error": "unparseable -json output"}
    truncated = len(rows) > max_rows
    if truncated:
        rows = rows[:max_rows]
    return {"rows": rows, "truncated": truncated}


# ============================================================================
# data 断言判定（纯函数；集成契约核心，供 gmi_runtime 消费）
# ============================================================================

def _norm_scalar(value: Any) -> Any:
    """值归一：bool -> 'true'/'false'；其余原样（保 JSON 类型）。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _values_equal(actual: Any, expected: Any) -> bool:
    """Oracle 值比较：宽松数值 + bool/0/1 语义，其余严格。"""
    a, e = _norm_scalar(actual), _norm_scalar(expected)
    if type(a) is type(e):
        return a == e
    # str vs number：宽松数值比较（SQLite INTEGER 1 vs 断言写 "1"）
    for x, y in ((a, e), (e, a)):
        if isinstance(x, str) and isinstance(y, (int, float)) and not isinstance(y, bool):
            try:
                return float(x) == float(y)
            except ValueError:
                return False
    # bool 语义串（expected 常写 "true"/"false"）与 bool 实值
    if isinstance(a, str) and isinstance(e, str):
        return a == e
    return False


def resolve_data_key(key: str, state: Optional[Dict[str, Any]]
                     ) -> Tuple[bool, Any, str]:
    """key 寻址语法解析 -> (found, value, note)。state = probe 输出 dict。

    语法：
      prefs.<name> | count:<table> | row:<t>[<col>=<v>].<col2> | exists:<t>[<col>=<v>]
    """
    if not state:
        return False, None, "probe state missing (file absent or DENIED)"
    key = (key or "").strip()
    m = re.match(r"^prefs\.(.+)$", key)
    if m:
        name = m.group(1)
        prefs = state.get("preferences") or {}
        if name in prefs:
            return True, prefs[name], ""
        return False, None, f"pref key not found: {name}"
    m = re.match(r"^count:([A-Za-z_][A-Za-z0-9_]*)$", key)
    if m:
        table = m.group(1)
        tables = state.get("tables") or {}
        if table not in tables:
            return False, None, f"table not probed: {table}"
        return True, len(tables[table]), ""
    m = re.match(r"^row:([A-Za-z_][A-Za-z0-9_]*)\[([A-Za-z_][A-Za-z0-9_]*)=(.*?)\]\.([A-Za-z_][A-Za-z0-9_]*)$",
                 key)
    if m:
        table, mcol, mval, col = m.group(1), m.group(2), m.group(3), m.group(4)
        tables = state.get("tables") or {}
        if table not in tables:
            return False, None, f"table not probed: {table}"
        for row in tables[table]:
            if isinstance(row, dict) and mcol in row and \
                    _values_equal(row[mcol], mval):
                if col in row:
                    return True, row[col], ""
                return False, None, f"column '{col}' missing in matched row"
        return False, None, f"no row with {mcol}={mval}"
    m = re.match(r"^exists:([A-Za-z_][A-Za-z0-9_]*)\[([A-Za-z_][A-Za-z0-9_]*)=(.*?)\]$",
                 key)
    if m:
        table, mcol, mval = m.group(1), m.group(2), m.group(3)
        tables = state.get("tables") or {}
        if table not in tables:
            return False, None, f"table not probed: {table}"
        hit = any(isinstance(r, dict) and mcol in r and _values_equal(r[mcol], mval)
                  for r in tables[table])
        return True, hit, ""
    return False, None, f"unparseable data key: {key!r}"


def evaluate_data_assertions(assertions: List[Dict[str, str]],
                             data_before: Optional[Dict[str, Any]],
                             data_after: Optional[Dict[str, Any]],
                             data_restart: Optional[Dict[str, Any]]
                             ) -> List[Dict[str, str]]:
    """data 类断言判定（纯函数；fail-closed 分层见模块 docstring 契约）。

    返回 [{"kind","key","value","verdict","note"}]，
    verdict ∈ PASS | FAIL | UNSUPPORTED。
    """
    out: List[Dict[str, str]] = []
    for a in assertions or []:
        kind = (a.get("kind") or "").strip()
        key = (a.get("key") or "").strip()
        expected = a.get("value")
        if kind == "data_equals":
            found, actual, note = resolve_data_key(key, data_after)
            if not found:
                out.append({"kind": kind, "key": key, "value": expected,
                            "verdict": "UNSUPPORTED",
                            "note": f"after-state unreadable: {note}"})
            else:
                ok = _values_equal(actual, expected)
                out.append({"kind": kind, "key": key, "value": expected,
                            "verdict": "PASS" if ok else "FAIL",
                            "note": "" if ok else f"actual={actual!r}"})
        elif kind == "data_persists":
            found, actual, note = resolve_data_key(key, data_restart)
            if not found:
                out.append({"kind": kind, "key": key, "value": expected,
                            "verdict": "UNSUPPORTED",
                            "note": f"restart-state unreadable: {note}"})
            else:
                ok = _values_equal(actual, expected)
                out.append({"kind": kind, "key": key, "value": expected,
                            "verdict": "PASS" if ok else "FAIL",
                            "note": "" if ok else f"actual={actual!r}"})
        elif kind == "data_changed":
            f_b, v_b, n_b = resolve_data_key(key, data_before)
            f_a, v_a, n_a = resolve_data_key(key, data_after)
            if not (f_b and f_a):
                out.append({"kind": kind, "key": key, "value": expected,
                            "verdict": "UNSUPPORTED",
                            "note": f"before={f_b}({n_b}) after={f_a}({n_a})"})
            else:
                changed = not _values_equal(v_b, v_a)
                out.append({"kind": kind, "key": key, "value": expected,
                            "verdict": "PASS" if changed else "FAIL",
                            "note": "" if changed
                            else f"unchanged: {v_b!r}"})
        else:
            out.append({"kind": kind, "key": key, "value": expected,
                        "verdict": "UNSUPPORTED",
                        "note": "unknown data assertion kind"})
    return out


# ============================================================================
# 探针主流程（设备侧；单测不覆盖，与现有采集器测试策略一致）
# ============================================================================

def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def probe_preferences(adb: str, serial: str, mode: str, package: str,
                      timeout: int, stores: List[Dict[str, Any]],
                      gaps: List[Dict[str, Any]],
                      verbose: bool = False) -> Dict[str, Any]:
    """读全部 Preferences 类存储 -> 扁平 preferences dict（多来源合并）。"""
    merged: Dict[str, Any] = {}

    # --- SharedPreferences XML ---
    for name in list_data_dir(adb, serial, mode, package, "shared_prefs", timeout):
        if not name.endswith(".xml"):
            continue
        rel = f"shared_prefs/{name}"
        raw = pull_data_file(adb, serial, mode, package, rel, timeout)
        if raw is None:
            stores.append({"store": f"shared_prefs:{name}", "path": rel,
                           "status": "TOOL_GAP", "reason": "pull failed"})
            gaps.append({"store": f"shared_prefs:{name}",
                         "reason": "file listed but unreadable"})
            continue
        try:
            kv = parse_shared_prefs_xml(raw.decode("utf-8", errors="strict"))
        except (ET.ParseError, UnicodeDecodeError) as exc:
            stores.append({"store": f"shared_prefs:{name}", "path": rel,
                           "status": "TOOL_GAP",
                           "reason": f"xml parse failed: {exc}"})
            gaps.append({"store": f"shared_prefs:{name}",
                         "reason": f"unparseable XML: {exc}"})
            continue
        for k, v in sorted(kv.items()):
            merged[k] = v
        stores.append({"store": f"shared_prefs:{name}", "path": rel,
                       "status": "READ", "keys": len(kv)})
        if verbose:
            print(f"  [prefs] shared_prefs/{name}: {len(kv)} keys")

    # --- MMKV（files/mmkv/ 主文件；.crc 跳过）---
    for name in list_data_dir(adb, serial, mode, package, "files/mmkv", timeout):
        if name.endswith(".crc"):
            continue
        rel = f"files/mmkv/{name}"
        raw = pull_data_file(adb, serial, mode, package, rel, timeout)
        if raw is None:
            stores.append({"store": f"mmkv:{name}", "path": rel,
                           "status": "TOOL_GAP", "reason": "pull failed"})
            gaps.append({"store": f"mmkv:{name}",
                         "reason": "file listed but unreadable"})
            continue
        final, pairs = parse_mmkv_binary(raw)
        if pairs:
            for k, v in sorted(final.items()):
                merged[k] = v
            stores.append({"store": f"mmkv:{name}", "path": rel,
                           "status": "READ", "keys": len(final),
                           "raw_pairs": len(pairs)})
            if verbose:
                print(f"  [prefs] mmkv/{name}: {len(final)} keys "
                      f"(raw {len(pairs)} pairs, override semantics applied)")
        else:
            # 降级：strings 提取（标注 degraded，键值可能不完整）
            frags = extract_strings_fallback(raw)
            if frags:
                stores.append({"store": f"mmkv:{name}", "path": rel,
                               "status": "READ",
                               "degraded": "strings-extraction",
                               "keys": 0, "fragments": len(frags)})
                merged[f"_mmkv_fragments:{name}"] = frags
                if verbose:
                    print(f"  [prefs] mmkv/{name}: KV parse failed, "
                          f"{len(frags)} strings fragments (degraded)")
            else:
                stores.append({"store": f"mmkv:{name}", "path": rel,
                               "status": "TOOL_GAP",
                               "reason": "binary KV stream unparseable"})
                gaps.append({"store": f"mmkv:{name}",
                             "reason": "MMKV stream unparseable, no strings"})

    # --- DataStore（第一版 TOOL_GAP，显式登记不伪造）---
    for name in list_data_dir(adb, serial, mode, package, "files/datastore",
                              timeout):
        if not _SAFE_NAME_RE.match(name):
            continue
        rel = f"files/datastore/{name}"
        kind = "datastore" if name.endswith(".preferences_pb") else "datastore-file"
        stores.append({"store": f"{kind}:{name}", "path": rel,
                       "status": "TOOL_GAP",
                       "reason": "DataStore protobuf not parsed in v1 "
                                 "(.preferences_pb schema-dependent)"})
        gaps.append({"store": f"{kind}:{name}",
                     "reason": "DataStore parsing is TOOL_GAP in v1"})
    return merged


def probe_database(adb: str, serial: str, mode: str, package: str,
                   objects: List[str], sqlite3_bin: str, max_rows: int,
                   timeout: int, stores: List[Dict[str, Any]],
                   gaps: List[Dict[str, Any]],
                   verbose: bool = False) -> Dict[str, Any]:
    """读全部 SQLite/Room 库 -> {table: [rows]}（--objects 过滤表级对象）。"""
    tables_out: Dict[str, Any] = {}
    if mode == "DENIED":
        return tables_out
    db_names = [n for n in list_data_dir(adb, serial, mode, package,
                                         "databases", timeout)
                if not n.endswith("-wal") and not n.endswith("-shm")
                and not n.endswith("-journal")]
    if not db_names:
        stores.append({"store": "databases", "path": "databases",
                       "status": "ABSENT", "reason": "no database files"})
        return tables_out
    if sqlite3_bin is None:
        for n in db_names:
            stores.append({"store": f"sqlite:{n}", "path": f"databases/{n}",
                           "status": "TOOL_GAP",
                           "reason": "local sqlite3 CLI unavailable"})
            gaps.append({"store": f"sqlite:{n}",
                         "reason": "sqlite3 CLI not found on host"})
        return tables_out
    with tempfile.TemporaryDirectory(prefix="data_probe_db_") as tmp:
        tmp_dir = Path(tmp)
        for db in db_names:
            if not _SAFE_NAME_RE.match(db):
                continue
            # 三件套：主库 + -wal + -shm（WAL 数据必需，实测 ro 打开可读）
            local_main = tmp_dir / db
            raw = pull_data_file(adb, serial, mode, package,
                                 f"databases/{db}", timeout)
            if raw is None:
                stores.append({"store": f"sqlite:{db}",
                               "path": f"databases/{db}",
                               "status": "TOOL_GAP", "reason": "pull failed"})
                gaps.append({"store": f"sqlite:{db}",
                             "reason": "db file listed but unreadable"})
                continue
            local_main.write_bytes(raw)
            for suffix in ("-wal", "-shm"):
                side = pull_data_file(adb, serial, mode, package,
                                      f"databases/{db}{suffix}", timeout)
                if side is not None:
                    (tmp_dir / f"{db}{suffix}").write_bytes(side)
            all_tables = list_sqlite_tables(sqlite3_bin, local_main, timeout)
            if all_tables is None:
                stores.append({"store": f"sqlite:{db}",
                               "path": f"databases/{db}",
                               "status": "TOOL_GAP",
                               "reason": "sqlite3 open/list failed "
                                         "(db corrupt or locked)"})
                gaps.append({"store": f"sqlite:{db}",
                             "reason": "unreadable db (not a valid sqlite file)"})
                continue
            wanted = objects if objects else all_tables
            db_tables: Dict[str, Any] = {}
            missing: List[str] = []
            for t in wanted:
                if t in _SYSTEM_TABLES:
                    continue
                if t not in all_tables:
                    missing.append(t)
                    continue
                dumped = dump_sqlite_table(sqlite3_bin, local_main, t,
                                           max_rows, timeout)
                if dumped is None or dumped.get("error"):
                    # 单表读失败不拖垮整库：登记后继续
                    stores.append({"store": f"sqlite:{db}#{t}",
                                   "path": f"databases/{db}",
                                   "status": "TOOL_GAP",
                                   "reason": dumped.get("error") or "dump failed"})
                    gaps.append({"store": f"sqlite:{db}#{t}",
                                 "reason": dumped.get("error") or "dump failed"})
                    continue
                db_tables[t] = dumped["rows"]
                tables_out[t] = dumped["rows"]
                if verbose:
                    extra = " (truncated)" if dumped["truncated"] else ""
                    print(f"  [db] {db}#{t}: {len(dumped['rows'])} rows{extra}")
            entry = {"store": f"sqlite:{db}", "path": f"databases/{db}",
                     "status": "READ", "tables": len(db_tables)}
            if missing:
                entry["missing_objects"] = missing
            stores.append(entry)
            if missing:
                # --objects 声明了但库里没有：显式登记（MISSING_IN_DB，
                # 不伪造空表；可能是对象名非本库表或库未创建）
                for t in missing:
                    gaps.append({"store": f"sqlite:{db}#{t}",
                                 "reason": "MISSING_IN_DB: object declared in "
                                           "--objects but table absent"})
    return tables_out


def run_probe(args: argparse.Namespace) -> int:
    """主入口：产出语义状态 JSON（TOOL_GAP 是显式结果，不算失败）。"""
    adb = args.adb
    serial = args.device
    sqlite3_bin = resolve_sqlite3(args.sqlite3)
    if args.verbose:
        print(f"probe: package={args.package} device={serial} "
              f"objects={args.objects or '<all tables>'} "
              f"sqlite3={sqlite3_bin or 'MISSING'}")

    # 设备可达性（adb 本身不可用 -> 退出码 3 + DENIED 报告）
    hello = _adb_text(adb, serial, ["echo", "probe-hello"], args.timeout)
    if hello is None or "probe-hello" not in hello:
        mode = "DENIED"
        reason = "adb or device unreachable"
    else:
        mode = detect_access_mode(adb, serial, args.package, args.timeout)
        reason = "run-as and root both unavailable (package not debuggable?)"

    stores: List[Dict[str, Any]] = []
    gaps: List[Dict[str, Any]] = []
    preferences: Dict[str, Any] = {}
    tables: Dict[str, Any] = {}

    if mode == "DENIED":
        gaps.append({"store": "*", "reason": reason})
        stores.append({"store": "*", "status": "TOOL_GAP", "reason": reason})
    else:
        if not args.no_prefs:
            preferences = probe_preferences(adb, serial, mode, args.package,
                                            args.timeout, stores, gaps,
                                            args.verbose)
        objects = [o.strip() for o in args.objects.split(",") if o.strip()] \
            if args.objects else []
        tables = probe_database(adb, serial, mode, args.package, objects,
                                sqlite3_bin, args.max_rows, args.timeout,
                                stores, gaps, args.verbose)

    report = {
        "schema": SCHEMA_VERSION,
        "package": args.package,
        "device": serial,
        "captured_at": _utc_now(),
        "access_mode": mode,
        "preferences": preferences,
        "tables": tables,
        "stores": stores,
        "tool_gaps": gaps,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    read_n = sum(1 for s in stores if s.get("status") == "READ")
    gap_n = len(gaps)
    print(f"probe done: access={mode} stores_read={read_n} "
          f"tool_gaps={gap_n} prefs={len(preferences)} "
          f"tables={len(tables)} -> {out_path}")
    return 0 if mode != "DENIED" or args.allow_denied else 3


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Android Oracle 数据探针：Preferences + SQLite/Room 真实读取")
    parser.add_argument("--package", required=True,
                        help="目标应用包名（如 com.nevoit.cresto）")
    parser.add_argument("--device", default="emulator-5554",
                        help="adb 设备序列号（默认 emulator-5554）")
    parser.add_argument("--objects", default="",
                        help="逗号分隔数据对象（表名）；空=全部业务表。"
                             "preferences 由 --no-prefs 单独控制")
    parser.add_argument("--out", required=True, help="输出 JSON 路径")
    parser.add_argument("--adb", default="adb", help="adb 可执行文件路径")
    parser.add_argument("--sqlite3", default=None,
                        help="本地 sqlite3 CLI 路径（默认搜 PATH）")
    parser.add_argument("--max-rows", type=int, default=200,
                        help="每表最大行数（默认 200，超出标 truncated）")
    parser.add_argument("--timeout", type=int, default=30,
                        help="单条 adb/sqlite3 命令超时秒数")
    parser.add_argument("--no-prefs", action="store_true",
                        help="跳过 Preferences 类存储")
    parser.add_argument("--allow-denied", action="store_true",
                        help="访问被拒时也退出 0（DENIED 作为显式结果）")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if not re.match(r"^[A-Za-z][A-Za-z0-9._]*$", args.package):
        parser.error(f"invalid package name: {args.package!r}")
        return 2
    try:
        return run_probe(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())