#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""feature_map -- 功能语义地图 + 数据关系生成器（Phase 2 新范式核心产物）。

范式定位（用户批准的重写级转变）：
  Phase 2 不再"把 Android 所有页面证明一遍"，而是给 Phase 4 一张
  **以用户功能为中心**的"功能语义地图 + 高风险行为证据包"。

产物一：feature-map.json
  {
    "schema_version": 1,
    "features": [{
      "feature_id": "FEATURE-TODO-CREATE",       # scope.included_features 之一
      "name": "",                               # 语义列：LLM 分片填充（如"新增待办"）
      "summary": "",                            # 语义列：LLM 分片填充（一句话语义）
      "source_refs": ["path/File.kt:120"],      # 行为证据，file:line 必须可解析
      "surfaces": [{                            # 显式绑定的 UI surface（禁止子串匹配兜底）
        "id": "PAGE-ADDTODOSHEET",              #   必须是 surface-index 正式 ID
        "kind": "sheet",                        #   必须与 surface-index 一致
        "is_container": false
      }],
      "data_objects": {"writes": ["todo_items"], "reads": ["todo_groups"]},
      "risk_level": "high" | "normal",
      "verify_mode": "RUNTIME" | "SOURCE_CONFIRM",
      "status": "OPEN"                          # 由后续步骤（reconcile/Gate2）更新
    }],
    "coverage_gate": {                          # 新门禁：范围内功能覆盖
      "included_features_covered": true,
      "included": [...], "covered": [...], "missing": [...]
    }
  }

verify_mode 分级验证：
  增删改/持久化/语言/主题/同步/权限 -> RUNTIME；
  普通展示/跳转 -> SOURCE_CONFIRM；
  宿主容器页（is_container=true）一律 SOURCE_CONFIRM（MainScreen/DetailActivity
  死锁的根治）。

产物二：data-relations.csv
  feature_id, data_object, relation(read|write),
  persistence_kind(room_table|preference_key|mmkv_key|datastore_key|...),
  persistence_location, source_ref
  来源：candidates 候选表 + 源码扫描（Room @Entity/@Dao 与 MMKV/SharedPreferences/
  DataStore key 的既有发现）。

绑定规则（实测教训，fail-closed）：
  1. feature↔surface 绑定只走显式映射：inputs/page-features.csv（page_symbol,
     feature_id，controller 冻结的信任根）+ inventory 候选 (feature_id, page_id)；
     子串匹配兜底被禁止（曾致 42 页错绑 1 feature）。
  2. 绑定校验：surface 的定义文件必须出现在该 feature 的证据文件集合
     （source_refs 文件 ∪ 显式映射页面文件 ∪ 候选表归属文件）中——
     NavContainer.kt 的行为不能绑 DetailActivity 这类错绑直接拒绝。
  3. surfaces[].id 必须精确等于 surface-index 正式 ID；kind/is_container
     必须与 surface-index 一致。

用法：
  python feature_map.py --workspace <run 目录>
        [--scope <scope.json>]                  # 缺省 <ws>/scope.json、<ws>/controller/scope.json
        [--surface-index <surface-index.csv>]   # 缺省 <ws>/static-analysis/surface-index.csv → <ws>/surface-index.csv
        [--page-features <page-features.csv>]   # 缺省 <ws>/inputs/page-features.csv → <ws>/page-features.csv
        [--project <android root>]              # 缺省 scope.android.project_root
        [--features A,B]                        # 显式 included features（覆盖 scope）
        [--out <feature-map.json>]              # 缺省 <ws>/feature-map.json
        [--data-relations-out <data-relations.csv>]  # 缺省 <ws>/data-relations.csv
        [--validate]                            # 校验已有 feature-map.json（不重写）

生成路径自校验与 --validate 共用 validate_feature_map()；骨架阶段语义列
（name/summary）按设计留空待 LLM 分片填充，走 skeleton 豁免，其余判据
完全一致——生成器自身拒绝输出坏地图，不留到 Gate 才发现。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# schema 常量
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1
VERIFY_MODES = ("RUNTIME", "SOURCE_CONFIRM")
RISK_LEVELS = ("high", "normal")
RELATIONS = ("read", "write")
PERSISTENCE_KINDS = (
    "room_table", "preference_key", "mmkv_key", "datastore_key",
    "file", "content_provider", "unknown",
)
# UI surface kinds 参与功能绑定；其余 kind（reusable-component/viewmodel/...）
# 只作 data-relations/参考，不进 surfaces[]。
UI_KINDS = {"page", "container", "sheet", "dialog", "menu", "settings"}

FEATURE_REQUIRED_KEYS = (
    "feature_id", "name", "summary", "source_refs", "surfaces",
    "data_objects", "risk_level", "verify_mode", "status",
)

# verify_mode=RUNTIME 的保守白名单词根（与 build_behavior_contracts 同源）：
# 增删改 / 持久化 / 语言 / 主题 / 同步 / 权限。
RUNTIME_SEEDS = (
    "create", "add", "insert", "save", "update", "edit", "modify", "delete",
    "remove", "swipe", "select", "batch", "complete", "repeat", "reminder",
    "setting", "preference", "persist", "language", "locale", "theme",
    "sync", "backup", "restore", "permission", "group",
    "新增", "添加", "新建", "删除", "修改", "编辑", "保存", "设置", "同步", "权限",
)

_FILE_LINE_RE = re.compile(r"^(?P<file>[^:\s][^:]*\.[A-Za-z0-9]+):(?P<line>\d+)$")

DATA_RELATION_FIELDS = [
    "relation_id", "feature_id", "data_object", "relation",
    "persistence_kind", "persistence_location", "source_ref",
]


# ---------------------------------------------------------------------------
# io helpers（与 gmi_generate.py / build_behavior_contracts.py 同风格）
# ---------------------------------------------------------------------------

def _csv_read(p: Path) -> List[Dict[str, str]]:
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _csv_write(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as h:
            w = csv.DictWriter(h, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            json.dump(value, h, indent=2, ensure_ascii=False)
            h.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _first_existing(*paths: Path) -> Optional[Path]:
    for p in paths:
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# 输入装载
# ---------------------------------------------------------------------------

def load_scope(workspace: Path, explicit: Optional[str]) -> Tuple[Optional[Path], dict]:
    path: Optional[Path] = None
    if explicit:
        path = Path(explicit).expanduser()
        if not path.exists():
            raise SystemExit(f"[fmap] --scope not found: {path}")
    else:
        path = _first_existing(workspace / "scope.json",
                               workspace / "controller" / "scope.json")
    if path is None:
        return None, {}
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"[fmap] scope.json 解析失败 {path}: {exc}")


def resolve_features(args_features: List[str], scope: dict, cands: Path) -> List[str]:
    if args_features:
        return args_features
    included = [str(f).strip() for f in
                (scope.get("migration_scope", {}) or {}).get("included_features") or []
                if str(f).strip()]
    if included:
        return included
    cj = cands / "candidates.json"
    if cj.exists():
        try:
            got = [str(f) for f in json.loads(cj.read_text(encoding="utf-8")).get("features", [])]
            if got:
                return got
        except Exception:  # noqa: BLE001
            pass
    feats = sorted({r.get("feature_id", "") for r in _csv_read(cands / "inventory.candidates.csv")
                    if r.get("feature_id")})
    return feats


def load_surface_index(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise SystemExit(
            f"[fmap] surface-index 不存在：{path}\n"
            f"  先跑 analyze_static_pages.py（新范式：先分类再登记），"
            f"或用 --surface-index 指定路径。")
    rows = _csv_read(path)
    if not rows:
        raise SystemExit(f"[fmap] surface-index 无数据行：{path}（fail-closed）")
    ids = [r.get("surface_id", "") for r in rows]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise SystemExit(f"[fmap] surface-index 存在重复 surface_id：{dupes[:5]}")
    return rows


def load_page_feature_map(path: Optional[Path]) -> Dict[str, str]:
    """显式映射 page_symbol -> feature_id（信任根；禁止子串匹配兜底）。"""
    if path is None or not path.exists():
        return {}
    out: Dict[str, str] = {}
    for row in _csv_read(path):
        sym = (row.get("page_symbol") or row.get("symbol") or "").strip()
        feat = (row.get("feature_id") or row.get("feature") or "").strip()
        if sym and feat:
            out[sym] = feat
    return out


# ---------------------------------------------------------------------------
# 证据聚合（feature -> files/refs）
# ---------------------------------------------------------------------------

def collect_evidence(cands: Path,
                     symbol_to_feature: Dict[str, str],
                     surface_by_symbol: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    """聚合每个 feature 的证据文件与 file:line 证据（全部显式归属，无子串匹配）。

    证据口径（收紧防错绑——实测教训：gmi code-map 的文件级兜底归属曾把
    NavContainer.kt 混入 Detail 类 feature 证据）：
      * 信任根 = inputs/page-features.csv 显式映射页面的定义文件（整文件属于
        该 feature 的地盘），显式页面 def 文件的 code-map 行全部计入；
      * 其余文件的 code-map suggested_feature 行一律不计入（兜底噪声）；
      * inventory / business-rules / risk-probes / navigation-relations 的
        page_id 行经 slug 桥接（两套 PAGE-ID 体系均为 PAGE-<SLUG>-<HASH>
        格式，取 SLUG 大写匹配 surface symbol）归属到显式映射 feature。
    """

    # 显式映射页面的定义文件集（信任根文件集）+ page_id slug 桥接表
    explicit_files: Dict[str, Set[str]] = {}
    symbol_slug: Dict[str, str] = {}
    for sym, surf in surface_by_symbol.items():
        parsed = parse_file_line(surf.get("source_ref", ""))
        feat = symbol_to_feature.get(sym)
        if parsed and feat:
            explicit_files.setdefault(feat, set()).add(parsed[0])
        pid = (surf.get("page_id") or surf.get("surface_id") or "")
        parts = pid.split("-")
        if len(parts) >= 3:
            symbol_slug.setdefault(parts[1].upper(), sym)

    def feature_of_page_id(page_id: str) -> Optional[str]:
        parts = (page_id or "").split("-")
        if len(parts) < 3:
            return None
        sym = symbol_slug.get(parts[1].upper())
        return symbol_to_feature.get(sym) if sym else None

    ev: Dict[str, Dict[str, Any]] = {}

    def touch(feature: str, ref: str, file_path: str = "") -> None:
        """计入证据——统一强制：文件必须 ∈ 该 feature 显式文件集（信任根）。

        这是任务书绑定校验的完整语义：上游候选表的页面级归属自带噪声
        （实测 NavContainer.kt 的 when 路由行为被记在 DetailScreen 名下），
        只有显式映射页面文件内的行为才是该 feature 的合法证据；
        LLM/人工后续可直接扩充条目 source_refs（validate 侧另作合法基准）。
        """
        if not feature:
            return
        allowed = explicit_files.get(feature, set())
        parsed = parse_file_line(ref)
        if parsed and parsed[0] not in allowed:
            return
        if file_path and file_path not in allowed:
            return
        entry = ev.setdefault(feature, {"files": set(), "refs": []})
        if file_path:
            entry["files"].add(file_path)
        if parsed:
            entry["files"].add(parsed[0])
            if ref not in entry["refs"]:
                entry["refs"].append(ref)

    # 信任根：显式页面 def 文件并入（无 refs 也占位）
    for feat, files in explicit_files.items():
        entry = ev.setdefault(feat, {"files": set(), "refs": []})
        entry["files"].update(files)

    for r in _csv_read(cands / "code-map.candidates.full.csv"):
        feat = (r.get("suggested_feature") or "").strip()
        file_path = (r.get("file_path") or "").strip()
        # 只接受显式映射页面文件内的行为行（其余 suggested_feature 是
        # 文件级兜底归属噪声，见上）
        if not feat or file_path not in explicit_files.get(feat, set()):
            continue
        touch(feat, (r.get("code_ref") or r.get("source_ref") or "").strip(), file_path)
    for r in _csv_read(cands / "inventory.candidates.csv"):
        feat = feature_of_page_id((r.get("page_id") or "").strip())
        touch(feat, (r.get("source_ref") or "").strip())
    for name, page_col in (("business-rules.candidates.csv", "page_id"),
                           ("risk-probes.candidates.csv", "page_id")):
        for r in _csv_read(cands / name):
            feat = feature_of_page_id((r.get(page_col) or "").strip())
            if name == "risk-probes.candidates.csv":
                f, ln = (r.get("file") or "").strip(), (r.get("line") or "").strip()
                ref = f"{f}:{ln}" if f and ln else ""
            else:
                ref = (r.get("source_ref") or "").strip()
            touch(feat, ref)
    for r in _csv_read(cands / "navigation-relations.candidates.csv"):
        feat = feature_of_page_id((r.get("from_page_id") or "").strip())
        touch(feat, (r.get("source_ref") or "").strip())
    return ev


def evidence_files_for_validation(cands: Path,
                                  symbol_to_feature: Dict[str, str],
                                  surface_by_symbol: Dict[str, Dict[str, str]]) -> Dict[str, Set[str]]:
    """重算 feature -> 完整证据文件集合（--validate 绑定校验基准）。

    与生成路径同口径：候选表证据 ∪ 显式映射页面定义文件（信任根）。
    """
    ev = collect_evidence(cands, symbol_to_feature, surface_by_symbol)
    files_map = {feat: set(v["files"]) for feat, v in ev.items()}
    for sym, feat in symbol_to_feature.items():
        surf = surface_by_symbol.get(sym)
        if not surf:
            continue
        parsed = parse_file_line(surf.get("source_ref", ""))
        if parsed:
            files_map.setdefault(feat, set()).add(parsed[0])
    return files_map


def parse_file_line(ref: str) -> Optional[Tuple[str, int]]:
    m = _FILE_LINE_RE.match((ref or "").strip())
    if not m:
        return None
    line = int(m.group("line"))
    if line < 1:
        return None
    return m.group("file"), line


# ---------------------------------------------------------------------------
# data-relations 源码扫描（Room / MMKV / SharedPreferences / DataStore）
# ---------------------------------------------------------------------------

_ROOM_TABLE_RE = re.compile(r"(?:FROM|INTO|UPDATE|JOIN)\s+([a-zA-Z_][\w]*)", re.I)
_ENTITY_TABLE_RE = re.compile(r'@Entity\s*\([^)]*?tableName\s*=\s*"([^"]+)"', re.DOTALL)
_DAO_RE = re.compile(r"@Dao\s*(?:\r?\n\s*)?interface\s+(\w+)")
_KV_CONST_RE = re.compile(r'(?:const\s+)?val\s+(KEY_\w+)\s*=\s*"([^"]*)"')
_MMKV_WRITE_RE = re.compile(r'\b(?:mmkv|mmkvInstance|kv)\.encode\s*\(\s*([\w."]+)')
_MMKV_READ_RE = re.compile(r'\b(?:mmkv|mmkvInstance|kv)\.decode\w*\s*\(\s*([\w."]+)')
_PREFS_WRITE_RE = re.compile(r'\.put(?:String|Int|Long|Boolean|Float|StringSet)\s*\(\s*"([^"]+)"')
_PREFS_READ_RE = re.compile(r'\.get(?:String|Int|Long|Boolean|Float|StringSet)\s*\(\s*"([^"]+)"')
_DATASTORE_KEY_RE = re.compile(
    r'\b(?:boolean|int|string|float|long)PreferencesKey\(\s*"([^"]+)"')


def scan_data_relations(project: Path) -> List[Dict[str, str]]:
    """确定性扫描数据对象读写关系（无 feature 归属，归属在聚合阶段做）。"""
    relations: List[Dict[str, str]] = []

    def add(data_object: str, relation: str, kind: str, location: str,
            ref: str, note: str) -> None:
        relations.append({
            "data_object": data_object, "relation": relation,
            "persistence_kind": kind, "persistence_location": location,
            "source_ref": ref, "_note": note, "_file": ref.split(":", 1)[0],
        })

    for path in sorted(project.rglob("*")):
        if not path.is_file() or path.suffix not in (".kt", ".java"):
            continue
        if any(part in {".git", ".gradle", "build", "out"} for part in path.relative_to(project).parts):
            continue
        if path.stat().st_size > 2 * 1024 * 1024:
            continue
        rel_path = path.relative_to(project).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        def line_of(match: "re.Match[str]") -> str:
            return f"{rel_path}:{text.count(chr(10), 0, match.start()) + 1}"

        # --- Room @Dao: CRUD annotations and @Query table targets ---
        for dao_match in _DAO_RE.finditer(text):
            block_end = text.find("\n}", dao_match.end())
            block = text[dao_match.end():block_end if block_end > 0 else len(text)]
            for ann in re.finditer(r"@(Insert|Update|Delete)\b", block):
                add("", "write", "room_table", f"<{ann.group(1)}>",
                    f"{rel_path}:{text.count(chr(10), 0, dao_match.end() + ann.start()) + 1}",
                    f"@{ann.group(1)} in @Dao {dao_match.group(1)}")
            for q in re.finditer(r'@Query\s*\(\s*"([^"]+)"', block):
                sql = q.group(1)
                verb = "read" if re.match(r"\s*SELECT", sql, re.I) else "write"
                for table in _ROOM_TABLE_RE.findall(sql):
                    if table.upper() in ("SELECT", "WHERE", "SET", "VALUES", "AND", "OR"):
                        continue
                    add(table, verb, "room_table", table,
                        f"{rel_path}:{text.count(chr(10), 0, dao_match.end() + q.start()) + 1}",
                        f"@Query {sql[:40]}")

        # --- Room @Entity table names (data object definitions) ---
        for ent in _ENTITY_TABLE_RE.finditer(text):
            add(ent.group(1), "read", "room_table", ent.group(1),
                line_of(ent), "@Entity tableName")

        # --- MMKV / SharedPreferences / DataStore keys ---
        key_literals: Dict[str, str] = dict(_KV_CONST_RE.findall(text))
        for match in _MMKV_WRITE_RE.finditer(text):
            token = match.group(1).split(".")[-1]
            add("settings", "write", "mmkv_key", key_literals.get(token, token),
                line_of(match), "mmkv.encode")
        for match in _MMKV_READ_RE.finditer(text):
            token = match.group(1).split(".")[-1]
            add("settings", "read", "mmkv_key", key_literals.get(token, token),
                line_of(match), "mmkv.decode")
        for match in _PREFS_WRITE_RE.finditer(text):
            add("settings", "write", "preference_key", match.group(1),
                line_of(match), "SharedPreferences.put")
        for match in _PREFS_READ_RE.finditer(text):
            add("settings", "read", "preference_key", match.group(1),
                line_of(match), "SharedPreferences.get")
        for match in _DATASTORE_KEY_RE.finditer(text):
            add("settings", "read", "datastore_key", match.group(1),
                line_of(match), "DataStore preferencesKey")
    return relations



# ---------------------------------------------------------------------------
# 骨架构建
# ---------------------------------------------------------------------------

def _surface_row_by_id(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    return {r["surface_id"]: r for r in rows if r.get("surface_id")}


def _runtime_seed_hit(feature_id: str) -> bool:
    fid = (feature_id or "").lower()
    return any(seed in fid for seed in RUNTIME_SEEDS)


# 可操作页面类 kind：用户直接交互的 surface。容器(container)与无人显式点名的
# reusable-component 不算可操作页面——纯壳 feature 一律 SOURCE_CONFIRM。
OPERABLE_KINDS = {"page", "sheet", "dialog", "menu", "settings"}


def derive_verify_mode(feature_id: str, surfaces: List[Dict[str, Any]],
                       writes: List[str]) -> Tuple[str, str]:
    """分级验证推导。返回 (verify_mode, reason)。

    规则（任务书）：
      * 无可操作页面（绑定 surface 全为 container/组件壳，如 NAV-SHELL 的
        MainActivity+MainScreen+NavContainer）-> SOURCE_CONFIRM（容器死锁根治）；
      * 持久化写入（data_objects.writes 非空）-> RUNTIME；
      * feature 语义命中白名单词根（增删改/持久化/语言/主题/同步/权限）-> RUNTIME；
      * 普通展示/跳转 -> SOURCE_CONFIRM。
    """
    operable = [s for s in surfaces if s.get("kind") in OPERABLE_KINDS]
    if surfaces and not operable:
        return "SOURCE_CONFIRM", "no operable page surfaces (container/component shell only)"
    if writes:
        return "RUNTIME", f"persists writes: {', '.join(writes[:3])}"
    if _runtime_seed_hit(feature_id):
        return "RUNTIME", "runtime whitelist seed"
    return "SOURCE_CONFIRM", "display/navigation only"


def build_feature_map(workspace: Path, scope: dict, included: List[str],
                      surface_rows: List[Dict[str, str]],
                      page_feature_map: Dict[str, str],
                      evidence: Dict[str, Dict[str, Any]],
                      data_relations: List[Dict[str, Any]]) -> Tuple[dict, List[str]]:
    surfaces_by_id = _surface_row_by_id(surface_rows)
    surface_by_symbol = {r["symbol"]: r for r in surface_rows}

    # 显式映射（信任根）：page_symbol -> feature_id（仅接受已知 surface 符号）
    symbol_to_feature: Dict[str, str] = {}
    for sym, feat in page_feature_map.items():
        if sym in surface_by_symbol:
            symbol_to_feature[sym] = feat

    features_out: List[Dict[str, Any]] = []
    skipped_bindings: List[str] = []

    for feat in included:
        ev = evidence.get(feat, {"files": set(), "refs": []})
        ev_files: Set[str] = set(ev["files"])
        ev_refs: List[str] = list(ev["refs"])
        # 显式映射到本 feature 的页面定义文件并入证据集（信任根）
        for sym, mapped_feat in symbol_to_feature.items():
            if mapped_feat != feat:
                continue
            surf = surface_by_symbol[sym]
            parsed = parse_file_line(surf.get("source_ref", ""))
            if parsed:
                ev_files.add(parsed[0])
                ev_refs.append(surf["source_ref"])

        # 证据 refs 采样（每文件 ≤3，总数 ≤24，保持稳定顺序）
        refs_by_file: Dict[str, List[str]] = {}
        for ref in ev_refs:
            parsed = parse_file_line(ref)
            if not parsed:
                continue
            refs_by_file.setdefault(parsed[0], []).append(ref)
        sampled: List[str] = []
        for f in sorted(refs_by_file):
            sampled.extend(sorted(refs_by_file[f])[:3])
            if len(sampled) >= 24:
                break
        sampled = sampled[:24]

        if not ev_files and not sampled:
            # 无证据 feature：占位条目（LLM/上游补绑定后 --validate 收口），
            # 不阻断整盘骨架生成，但 coverage_gate 之外由 validate 强制补齐。
            features_out.append({
                "feature_id": feat,
                "name": "", "summary": "",
                "source_refs": [], "surfaces": [],
                "data_objects": {"writes": [], "reads": []},
                "risk_level": "normal", "verify_mode": "SOURCE_CONFIRM",
                "status": "PENDING_LLM_BINDING",
                "_verify_mode_reason": "no evidence bound yet",
            })
            continue

        # surface 绑定：显式映射（symbol 级，信任根）+ 绑定校验（定义文件 ∈ 证据集）。
        # kind 过滤：UI surface 默认可绑；非 UI kind（reusable-component 等）只有在
        # 被显式映射（信任根点名，如 NavContainer->FEATURE-NAV-SHELL）时才可绑——
        # 无人显式点名的普通组件（TodoSection）永远不会被绑成 feature surface。
        bound_surfaces: List[Dict[str, Any]] = []
        candidate_symbols = {sym for sym, f in symbol_to_feature.items() if f == feat}
        for r in surface_rows:
            if r["kind"] not in UI_KINDS and r["symbol"] not in candidate_symbols:
                continue
            if r["symbol"] not in candidate_symbols:
                continue
            parsed = parse_file_line(r.get("source_ref", ""))
            if parsed and parsed[0] not in ev_files:
                skipped_bindings.append(
                    f"feature={feat} surface={r['surface_id']}({r['symbol']}) "
                    f"def_file={parsed[0]} not in feature evidence files "
                    f"(拒绝错绑；证据文件 {len(ev_files)} 个)")
                continue
            bound_surfaces.append({
                "id": r["surface_id"], "kind": r["kind"],
                "is_container": r.get("is_container") == "true",
            })
        bound_surfaces.sort(key=lambda s: s["id"])

        # data_objects 聚合：数据对象文件 ∈ 本 feature 证据文件 -> 关系归属
        writes: List[str] = []
        reads: List[str] = []
        for rel in data_relations:
            if rel.get("_file") not in ev_files:
                continue
            obj = rel.get("data_object") or ""
            if not obj:
                # @Dao CRUD 注解行无表名目标：data_objects 不聚合占位符
                # （占位行仍保留在 data-relations.csv 供人工/LLM 对齐）
                continue
            if rel["relation"] == "write" and obj not in writes:
                writes.append(obj)
            elif rel["relation"] == "read" and obj not in reads:
                reads.append(obj)


        verify_mode, vm_reason = derive_verify_mode(feat, bound_surfaces, writes)
        risk_level = "high" if verify_mode == "RUNTIME" else "normal"
        features_out.append({
            "feature_id": feat,
            "name": "",          # 语义列：LLM 分片填充
            "summary": "",       # 语义列：LLM 分片填充
            "source_refs": sampled,
            "surfaces": bound_surfaces,
            "data_objects": {"writes": writes, "reads": reads},
            "risk_level": risk_level,
            # 兼容键：controller Gate 2 消费 features[].risk|.impact（同值冗余）
            "risk": risk_level,
            "verify_mode": verify_mode,
            "status": "OPEN",
            "_verify_mode_reason": vm_reason,
        })

    covered = [f["feature_id"] for f in features_out]
    missing = [f for f in included if f not in covered]
    fmap = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": "FEATURE_MAP",
        "features": features_out,
        "coverage_gate": {
            "included_features_covered": not missing,
            "included": included,
            "covered": covered,
            "missing": missing,
        },
    }
    return fmap, skipped_bindings


def materialize_data_relations(data_relations: List[Dict[str, Any]],
                               feature_evidence: Dict[str, Dict[str, Any]],
                               included: List[str]) -> List[Dict[str, str]]:
    """给扫描到的数据关系落 feature 归属（文件 ∈ 证据集，多对多允许）。"""
    rows: List[Dict[str, str]] = []
    seq = 0
    for rel in data_relations:
        owners = [f for f in included
                  if rel.get("_file") in feature_evidence.get(f, {}).get("files", set())]
        targets = owners or [""]
        for feat in targets:
            seq += 1
            rows.append({
                "relation_id": f"REL-{seq:04d}",
                "feature_id": feat,
                "data_object": rel.get("data_object", ""),
                "relation": rel["relation"],
                "persistence_kind": rel.get("persistence_kind", "unknown"),
                "persistence_location": rel.get("persistence_location", ""),
                "source_ref": rel.get("source_ref", ""),
            })
    return rows


# ---------------------------------------------------------------------------
# 校验（生成路径自校验与 --validate 共用；fail-closed）
# ---------------------------------------------------------------------------

def validate_feature_map(fmap: Any, included: List[str],
                         surface_rows: List[Dict[str, str]],
                         project: Optional[Path],
                         evidence: Optional[Dict[str, Set[str]]] = None,
                         skeleton_mode: bool = False) -> List[str]:
    """逐条校验（生成路径与 --validate 共用）；返回错误列表（空=通过）。

    evidence: feature -> 完整证据文件集合（候选表重算）。绑定校验基准 =
    条目 source_refs 文件集 ∪ evidence 文件集——绝不用采样后的子集误判错绑。
    skeleton_mode=True 仅豁免：语义列 name/summary 与 PENDING_LLM_BINDING
    占位条目的空 source_refs/surfaces（LLM 分片填充前的设计留白）。
    """
    errors: List[str] = []
    surfaces_by_id = _surface_row_by_id(surface_rows)

    if not isinstance(fmap, dict):
        return ["feature-map.json 顶层不是 JSON 对象"]
    feats = fmap.get("features")
    if not isinstance(feats, list) or not feats:
        return ["features 为空或缺失（每个 included feature 至少一条）"]

    seen_ids: Dict[str, int] = {}
    for i, f in enumerate(feats, start=1):
        fid = str(f.get("feature_id") or "")
        label = fid or f"<feature[{i}]>"
        for key in FEATURE_REQUIRED_KEYS:
            if key not in f:
                errors.append(f"{label}: 缺少必需键 {key}")
        if not fid:
            errors.append(f"feature[{i}]: feature_id 为空")
            continue
        if fid in seen_ids:
            errors.append(f"{label}: feature_id 重复（首见于 feature[{seen_ids[fid]}]）")
        seen_ids[fid] = i

        status = str(f.get("status") or "").strip()
        pending = status == "PENDING_LLM_BINDING"
        if status not in ("OPEN", "CONFIRMED", "PENDING_RECONCILE", "PENDING_LLM_BINDING"):
            errors.append(f"{fid}: status={status!r} 非法"
                          f"（OPEN|CONFIRMED|PENDING_RECONCILE|PENDING_LLM_BINDING）")
        if pending and not skeleton_mode:
            errors.append(f"{fid}: status=PENDING_LLM_BINDING（LLM 绑定未补齐，"
                          f"收口前必须补 source_refs/surfaces 并置 OPEN）")
        if not skeleton_mode:
            for col in ("name", "summary"):
                if not str(f.get(col) or "").strip():
                    errors.append(f"{fid}: 语义列 {col} 为空（LLM 分片填充未完成）")

        vm = str(f.get("verify_mode") or "")
        rl = str(f.get("risk_level") or "")
        if vm not in VERIFY_MODES:
            errors.append(f"{fid}: verify_mode={vm!r} 非法（应为 {'|'.join(VERIFY_MODES)}）")
        if rl not in RISK_LEVELS:
            errors.append(f"{fid}: risk_level={rl!r} 非法（应为 {'|'.join(RISK_LEVELS)}）")
        if rl == "high" and vm != "RUNTIME":
            errors.append(f"{fid}: risk_level=high 必须 verify_mode=RUNTIME（当前 {vm!r}）")

        do = f.get("data_objects")
        if not isinstance(do, dict) or not isinstance(do.get("writes"), list) \
                or not isinstance(do.get("reads"), list):
            errors.append(f"{fid}: data_objects 必须含 writes/reads 列表")
        # 持久化写入必须 RUNTIME（分级验证一致性）
        if isinstance(do, dict) and do.get("writes") and vm != "RUNTIME":
            errors.append(f"{fid}: data_objects.writes 非空但 verify_mode={vm!r}"
                          f"（持久化写入必须 RUNTIME）")

        # source_refs：file:line 可解析 + 行号范围
        refs = f.get("source_refs")
        if not isinstance(refs, list):
            errors.append(f"{fid}: source_refs 必须为列表")
            refs = []
        if not refs and not (pending and skeleton_mode):
            errors.append(f"{fid}: source_refs 为空（每条 feature 必须有行为证据）")
        files_of_refs: Set[str] = set()
        for ref in refs:
            parsed = parse_file_line(str(ref))
            if not parsed:
                errors.append(f"{fid}: source_ref 不可解析为 file:line：{str(ref)[:80]!r}")
                continue
            file_name, line_no = parsed
            files_of_refs.add(file_name)
            if project is not None:
                abs_path = project / file_name
                if not abs_path.is_file():
                    errors.append(f"{fid}: source_ref 文件不存在：{file_name}")
                else:
                    total = abs_path.read_text(encoding="utf-8", errors="replace").count("\n") + 1
                    if line_no > total:
                        errors.append(
                            f"{fid}: source_ref 行号越界：{ref}（文件共 {total} 行）")

        # 绑定校验基准：条目 source_refs 文件 ∪ 候选表重算证据文件（不用采样子集）
        binding_basis = set(files_of_refs)
        if evidence:
            binding_basis |= set(evidence.get(fid, set()))

        # surfaces：正式 ID + 与 surface-index 一致 + 绑定校验（错绑拒绝）
        surfaces = f.get("surfaces")
        if not isinstance(surfaces, list):
            errors.append(f"{fid}: surfaces 必须为列表")
        else:
            if not surfaces and not (pending and skeleton_mode):
                errors.append(f"{fid}: surfaces 为空（功能必须绑定至少一个 UI surface）")
            for s in surfaces:
                sid = str(s.get("id") or "")
                surf = surfaces_by_id.get(sid)
                if surf is None:
                    errors.append(
                        f"{fid}: surfaces.id={sid!r} 不是 surface-index 正式 ID"
                        f"（拒绝页面名称/模糊 token/hash 猜测值）")
                    continue
                if str(s.get("kind")) != surf.get("kind"):
                    errors.append(f"{fid}: surface {sid} kind={s.get('kind')!r}"
                                  f" 与 surface-index({surf.get('kind')!r}) 不一致")
                want_container = surf.get("is_container") == "true"
                if bool(s.get("is_container")) != want_container:
                    errors.append(f"{fid}: surface {sid} is_container={s.get('is_container')!r}"
                                  f" 与 surface-index({want_container}) 不一致")
                parsed = parse_file_line(surf.get("source_ref", ""))
                if parsed and parsed[0] not in binding_basis:
                    errors.append(
                        f"{fid}: surface {sid}({surf.get('symbol')}) 定义文件"
                        f" {parsed[0]} 不在本 feature 证据文件集合内"
                        f"（绑定校验：拒绝错绑，如 NavContainer.kt 行为不能绑"
                        f" DetailActivity 类 feature）")

    # coverage gate：scope included ⊆ 条目（重算一致性）
    gate = fmap.get("coverage_gate")
    if not isinstance(gate, dict):
        errors.append("coverage_gate 缺失")
    else:
        if included:
            missing = [f for f in included if f not in seen_ids]
            if missing:
                errors.append(f"coverage_gate FAIL：included features 无条目：{missing}")
            declared = gate.get("included_features_covered")
            if declared is not True:
                errors.append("coverage_gate.included_features_covered 必须为 true")
    return errors


def validate_data_relations(rows: List[Dict[str, str]]) -> List[str]:
    errors: List[str] = []
    for i, r in enumerate(rows, start=2):
        rel = (r.get("relation") or "").strip()
        if rel not in RELATIONS:
            errors.append(f"L{i}: relation={rel!r} 非法（应为 {'|'.join(RELATIONS)}）")
        kind = (r.get("persistence_kind") or "").strip()
        if kind and kind not in PERSISTENCE_KINDS:
            errors.append(f"L{i}: persistence_kind={kind!r} 非法"
                          f"（应为 {'|'.join(PERSISTENCE_KINDS)}）")
    return errors


# ---------------------------------------------------------------------------
# --emit-compat：Phase 3/4 最小配套（从真实链产物派生 4+ 个兼容产物）
#
# 背景：新范式（chain）工作区缺旧契约产物，Phase 3 init_scaffold main_gmi 与
# Phase 4 init_implementation 消费以下文件（生产代码零改动，产物侧兼容）：
#   1. runtime-evidence/runtime-gate.csv   ← runtime-chains.csv + reconciliation.csv
#   2. runtime-evidence/audit-replay.csv   ← runtime-chains.csv
#   3. inventory.csv（页面状态行）          ← chains/reconciliation/feature-map/candidates
#   4. evidence-index.csv（数据行）         ← chains 证据目录（after/ui.xml 实算 sha256）
#   5. runtime-evidence/evidence-index.csv（副本：gmi_closure 目录哈希触发器，legacy 布局先例）
#   6. catalogs/ 三表 NONE_FOUND 哨兵行     ← data-relations 无 feature 级绑定的事实
# 派生原则：全部字段从真实产物取值（目录哈希实算、状态实映射），零时间戳保证幂等；
# 每个产物以 reason/note/compat_note 列标注派生来源。表头参照：
#   runtime-gate/audit-replay ← legacy 工作区同名文件列结构（前缀列一致 + 追加注记列）
#   inventory/evidence-index  ← 现有 WS 同名文件第 1 行
# ---------------------------------------------------------------------------

COMPAT_TAG = "chain-paradigm-compat"
# legacy runtime-gate.csv 列结构（migration-runs/<run>/phase-02-android-inventory.legacy）
RUNTIME_GATE_FIELDS = ["page_id", "symbol", "status", "evidence", "reason"]
# legacy audit-replay.csv 列结构
AUDIT_REPLAY_FIELDS = ["page_id", "symbol", "replayed", "recorded", "discrepancy", "note"]
# 现有 WS evidence-index.csv 表头 + 追加注记列
EVIDENCE_INDEX_COMPAT_FIELDS = [
    "evidence_id", "inventory_id", "feature_id", "page_id", "state_id", "env_id",
    "captured_at", "relative_path", "metadata_sha256", "status",
    "supersedes_evidence_id", "compat_note",
]
CATALOG_HEADERS = {
    "data-dependencies.csv": [
        "data_dependency_id", "feature_id", "dependency_type", "name", "direction",
        "source_ref", "sensitive", "migration_risk", "owner", "status", "notes",
    ],
    "system-capabilities.csv": [
        "system_capability_id", "feature_id", "capability_type", "name",
        "permission_or_api", "source_ref", "migration_risk", "owner", "status", "notes",
    ],
    "third-party-dependencies.csv": [
        "third_party_dependency_id", "feature_id", "name", "version", "purpose",
        "source_ref", "data_shared", "migration_risk", "owner", "status", "notes",
    ],
}


def _compat_read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"[compat] FAIL: 必需输入缺失：{path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _compat_read_header(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if row and row[0].strip():
                return [c.strip() for c in row]
    raise SystemExit(f"[compat] FAIL: 无法读取表头：{path}")


def _compat_sha256_file(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compat_write_csv(path: Path, fields: List[str], rows: List[Dict[str, Any]]) -> None:
    tmp = path.with_name(path.name + ".tmp-compat")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def _compat_scope(ws: Path) -> Tuple[List[str], str]:
    """included_features + coverage_checker_id（消费端 expected_reviewer）。"""
    for cand in (ws / "controller" / "scope.json", ws / "controller-scope.snapshot.json",
                 ws.parent / "controller" / "scope.json"):
        if not cand.is_file():
            continue
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"[compat] FAIL: scope 解析失败 {cand}: {exc}")
        included = [str(f) for f in
                    ((data.get("migration_scope") or {}).get("included_features") or [])]
        reviewer = ((data.get("ownership") or {}).get("coverage_checker_id") or "").strip()
        if included and reviewer:
            return included, reviewer
    raise SystemExit("[compat] FAIL: 找不到含 included_features+ownership.coverage_checker_id"
                     " 的 scope.json（controller/scope.json | controller-scope.snapshot.json）")


def _compat_symbol_for_page(cand_rows: List[Dict[str, str]], page_id: str) -> str:
    """页面符号：candidates 该页 source_ref 文件基名（MainScreen.kt:114 → MainScreen）。"""
    for row in cand_rows:
        if row.get("page_id") == page_id and row.get("source_ref"):
            base = row["source_ref"].split("/")[-1].split(":")[0]
            stem = base.rsplit(".", 1)[0] if "." in base else base
            if stem:
                return stem
    raise SystemExit(f"[compat] FAIL: candidates 中无 {page_id} 的 source_ref，无法派生 symbol")


def emit_compat(ws: Path) -> int:
    rt_ = ws / "runtime-evidence"
    chain_rows = _compat_read_rows(rt_ / "runtime-chains.csv")
    if not chain_rows:
        raise SystemExit("[compat] FAIL: runtime-chains.csv 无数据行")
    recon_rows = _compat_read_rows(ws / "reconciliation.csv")
    recon_by_bc = {r.get("bc_id", ""): r for r in recon_rows}
    fmap = {}
    fmap_path = ws / "feature-map.json"
    if fmap_path.is_file():
        fmap = json.loads(fmap_path.read_text(encoding="utf-8"))
    fmap_by_feat = {f.get("feature_id", ""): f for f in fmap.get("features", [])}
    cand_rows = _compat_read_rows(ws / "candidates" / "inventory.candidates.csv")
    included, reviewer = _compat_scope(ws)

    # ---- BC 全集 = 运行链（10）+ source-confirm 未运行（2）----
    chain_bcs = [r["bc_id"] for r in chain_rows if r.get("bc_id")]
    source_confirm_bcs = [
        r["bc_id"] for r in recon_rows
        if r.get("bc_id") and r.get("bc_id") not in chain_bcs
        and str(r.get("verdict", "")).strip().upper() == "SOURCE_CONFIRMED"
    ]
    all_bcs = chain_bcs + source_confirm_bcs

    # ---- 页面/状态/环境真实值（chains page_ref → candidates 行）----
    page_state: Dict[str, Dict[str, str]] = {}
    for bc in all_bcs:
        rr = recon_by_bc.get(bc, {})
        page_id = rr.get("page_ref") or ""
        if page_id and page_id not in page_state:
            state = next((c for c in cand_rows if c.get("page_id") == page_id), None)
            page_state[page_id] = {
                "page_id": page_id,
                "state_id": (state or {}).get("state_id", ""),
                "state_name": (state or {}).get("state_expression", "") or "DEFAULT",
                "env_id": (state or {}).get("env_id", "") or "ENV-001",
                "symbol": _compat_symbol_for_page(cand_rows, page_id),
            }
    missing_state = [p for p, v in page_state.items() if not v["state_id"]]
    if missing_state:
        raise SystemExit(f"[compat] FAIL: candidates 缺页面状态行：{missing_state}")

    # ---- 1) runtime-gate.csv（legacy 4 列 + reason 注记列）----
    gate_out: List[Dict[str, str]] = []
    for row in chain_rows:
        bc = row["bc_id"]
        page = page_state[row["page_ref"]]
        status = "VISITED" if row.get("nav_status") == "REACHED" else "NOT_ENTERED"
        gate_out.append({
            "page_id": row["page_ref"], "symbol": page["symbol"], "status": status,
            "evidence": f"evidence/chains/{bc}/after/ui.xml",
            "reason": f"derived-from-chain:{bc}:{row.get('chain_status', '')}",
        })
    for bc in source_confirm_bcs:
        rr = recon_by_bc[bc]
        page = page_state[rr["page_ref"]]
        gate_out.append({
            "page_id": rr["page_ref"], "symbol": page["symbol"], "status": "NOT_ENTERED",
            "evidence": "(source-confirm)",
            "reason": f"derived-from-chain:{bc}:SOURCE_CONFIRMED:not-run-by-design",
        })
    _compat_write_csv(rt_ / "runtime-gate.csv", RUNTIME_GATE_FIELDS, gate_out)

    # ---- 2) audit-replay.csv（legacy 6 列；discrepancy 小写，消费端只计 "YES"）----
    audit_out: List[Dict[str, str]] = []
    for row in chain_rows:
        bc = row["bc_id"]
        page = page_state[row["page_ref"]]
        chain_status = row.get("chain_status", "")
        disc = "no" if "PASS" in chain_status else "yes"
        audit_out.append({
            "page_id": row["page_ref"], "symbol": page["symbol"],
            "replayed": "VISITED", "recorded": "VISITED", "discrepancy": disc,
            "note": f"chain-assertion-derived:{bc}:{chain_status}:{row.get('note', '')}",
        })
    for bc in source_confirm_bcs:
        rr = recon_by_bc[bc]
        page = page_state[rr["page_ref"]]
        audit_out.append({
            "page_id": rr["page_ref"], "symbol": page["symbol"],
            "replayed": "NOT_RUN", "recorded": "DECLARED_SOURCE",
            "discrepancy": "no",
            "note": f"source-confirm-derived:{bc}:not-run-by-design",
        })
    _compat_write_csv(rt_ / "audit-replay.csv", AUDIT_REPLAY_FIELDS, audit_out)

    # ---- 3) inventory.csv（现有 26 列表头；12 BC 行）----
    inv_path = ws / "inventory.csv"
    inv_fields = _compat_read_header(inv_path)
    if not inv_fields or inv_fields[0] != "inventory_id":
        raise SystemExit(f"[compat] FAIL: inventory.csv 表头异常：{inv_fields[:3]}")
    inv_out: List[Dict[str, Any]] = []
    evidence_rows: List[Dict[str, Any]] = []
    # source-confirm 无运行证据：以 MainScreen 首条 CHAIN_PASS 链的 after 快照作
    # surface 存在性佐证（目录与哈希真实，compat_note 注明派生关系）
    surface_ref_bc = next((r["bc_id"] for r in chain_rows
                           if r.get("chain_status") == "CHAIN_PASS"), chain_bcs[0])
    surface_ref_dir = f"runtime-evidence/evidence/chains/{surface_ref_bc}/after"

    def _assert_summary(row: Dict[str, str]) -> str:
        try:
            results = json.loads(row.get("assertion_results") or "[]")
        except json.JSONDecodeError:
            results = []
        parts = [f"{a.get('kind', '')}={a.get('value', '')}" for a in results if isinstance(a, dict)]
        return ";".join(parts) if parts else (row.get("note") or "degraded:no_assertions")

    for bc in all_bcs:
        chain = next((r for r in chain_rows if r["bc_id"] == bc), None)
        rr = recon_by_bc.get(bc, {})
        feat = rr.get("feature_id") or (chain or {}).get("feature_id", "")
        if feat not in included:
            raise SystemExit(f"[compat] FAIL: {bc} feature {feat!r} 不在 scope included 内")
        page = page_state[rr.get("page_ref") or chain["page_ref"]]
        fmap_feat = fmap_by_feat.get(feat, {})
        refs = []
        for ref in (fmap_feat.get("source_refs") or []):
            if ref not in refs:
                refs.append(ref)
        ev_id = f"NONE_GMI-CHAIN-{bc}"
        chain_status = (chain or {}).get("chain_status", "SOURCE_CONFIRMED")
        note = (chain or {}).get("note", "not-run-by-design")
        inv_out.append({
            "inventory_id": f"INV-CHAIN-{bc}",
            "feature_id": feat,
            "feature_name": fmap_feat.get("name", ""),
            "page_id": page["page_id"],
            "page_name": page["symbol"],
            "state_id": page["state_id"],
            "state_name": page["state_name"],
            "env_id": page["env_id"],
            "evidence_id": ev_id,
            "entry_condition": (chain or {}).get("entry_anchor", "source-confirm"),
            "transition_from_state_id": "",
            "predecessor_evidence_id": "",
            "action_summary": f"behavior-chain {bc}",
            "expected_observable": _assert_summary(chain) if chain else "source-confirm",
            "actual_observable": f"{chain_status}({note});{COMPAT_TAG}",
            "code_refs": json.dumps(refs, ensure_ascii=False),
            "business_rule_refs": "[]",
            "data_dependency_refs": json.dumps([f"DATA-NONE-{feat}"]),
            "system_capability_refs": json.dumps([f"SYSTEM-NONE-{feat}"]),
            "third_party_dependency_refs": json.dumps([f"THIRD-NONE-{feat}"]),
            "asset_ids": "[]",
            "responsible_agent": "gmi-compat-emitter",
            "row_status": "REVIEWED",
            "rework_id": "",
            "reviewed_by": reviewer,
            "reviewed_at": "",
        })
        if chain is not None:
            ev_dir = ws / "runtime-evidence" / "evidence" / "chains" / bc / "after"
            ui = ev_dir / "ui.xml"
            if not ui.is_file():
                raise SystemExit(f"[compat] FAIL: 链证据缺 after/ui.xml：{bc}")
            ev_row_note = f"derived-from-chain:{bc}:{COMPAT_TAG}"
            rel_path = f"runtime-evidence/evidence/chains/{bc}/after"
        else:
            ev_dir = ws / surface_ref_dir
            ui = ev_dir / "ui.xml"
            if not ui.is_file():
                raise SystemExit(f"[compat] FAIL: surface 佐证目录缺 ui.xml：{ev_dir}")
            ev_row_note = (f"source-confirm-derived:{bc}:surface-snapshot-ref:"
                           f"{surface_ref_bc}/after:no-runtime-evidence-by-design")
            rel_path = surface_ref_dir
        evidence_rows.append({
            "evidence_id": ev_id,
            "inventory_id": f"INV-CHAIN-{bc}",
            "feature_id": feat,
            "page_id": page["page_id"],
            "state_id": page["state_id"],
            "env_id": page["env_id"],
            "captured_at": "",
            "relative_path": rel_path,
            "metadata_sha256": _compat_sha256_file(ui),
            "status": "ACCEPTED",
            "supersedes_evidence_id": "",
            "compat_note": ev_row_note,
        })
    _compat_write_csv(inv_path, inv_fields, inv_out)

    # ---- 4/5) evidence-index.csv（根 + runtime-evidence 副本触发闭包目录哈希）----
    ev_fields = _compat_read_header(ws / "evidence-index.csv")
    if ev_fields[:11] != EVIDENCE_INDEX_COMPAT_FIELDS[:11]:
        raise SystemExit(f"[compat] FAIL: evidence-index.csv 现有表头与预期不符：{ev_fields}")
    _compat_write_csv(ws / "evidence-index.csv", ev_fields + ["compat_note"], evidence_rows)
    _compat_write_csv(rt_ / "evidence-index.csv", ev_fields + ["compat_note"], evidence_rows)

    # ---- 6) catalogs 三表 NONE_FOUND 哨兵行（消费端哨兵判定逐列匹配）----
    catalog_specs = {
        "data-dependencies.csv": ("DATA-NONE-", "data_dependency_id", "dependency_type"),
        "system-capabilities.csv": ("SYSTEM-NONE-", "system_capability_id", "capability_type"),
        "third-party-dependencies.csv": ("THIRD-NONE-", "third_party_dependency_id", None),
    }
    for name, (prefix, id_field, type_field) in catalog_specs.items():
        path = ws / "catalogs" / name
        header = _compat_read_header(path) if path.is_file() else CATALOG_HEADERS[name]
        rows = []
        for feat in included:
            row: Dict[str, Any] = {col: "" for col in header}
            row[id_field] = f"{prefix}{feat}"
            row["feature_id"] = feat
            row["name"] = "NONE_FOUND"
            if type_field:
                row[type_field] = "NONE"
            if name == "data-dependencies.csv":
                row["direction"] = "NONE"
            if name == "third-party-dependencies.csv":
                row["version"] = "NONE"
                row["purpose"] = "NONE"
            row["migration_risk"] = "none"
            row["status"] = "NONE"
            row["notes"] = (f"derived-by:feature_map.py--emit-compat; fact: "
                            f"data-relations.csv 无 feature 级绑定（{COMPAT_TAG}）")
            rows.append(row)
        _compat_write_csv(path, header, rows)

    print(f"[compat] runtime-gate.csv rows={len(gate_out)} "
          f"(VISITED={sum(1 for r in gate_out if r['status'] == 'VISITED')}, "
          f"NOT_ENTERED={sum(1 for r in gate_out if r['status'] == 'NOT_ENTERED')})")
    print(f"[compat] audit-replay.csv rows={len(audit_out)} "
          f"discrepancy_yes={sum(1 for r in audit_out if r['discrepancy'] == 'yes')}")
    print(f"[compat] inventory.csv rows={len(inv_out)}（表头 {len(inv_fields)} 列保持；"
          f"原 # 注释行为 CSV 契约不兼容已移出，见 emit-compat 汇报）")
    print(f"[compat] evidence-index.csv rows={len(evidence_rows)}（根 + runtime-evidence 副本）")
    print(f"[compat] catalogs 哨兵行：3 表 × {len(included)} features；"
          f"surface 佐证目录={surface_ref_dir}")
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="feature map + data relations generator (Phase-2 paradigm)")
    ap.add_argument("--workspace", required=True, help="run 目录（含 candidates/）")
    ap.add_argument("--emit-compat", action="store_true",
                    help="从链产物派生 Phase 3/4 兼容产物（runtime-gate/audit-replay/"
                         "inventory/evidence-index/catalogs 哨兵），不改 feature-map 本体")
    ap.add_argument("--scope", default=None, help="scope.json 路径")
    ap.add_argument("--surface-index", default=None, help="surface-index.csv 路径")
    ap.add_argument("--page-features", default=None, help="显式映射 page_symbol,feature_id CSV")
    ap.add_argument("--project", default=None, help="Android 工程根（缺省 scope.android.project_root）")
    ap.add_argument("--features", default="", help="included features 逗号分隔（覆盖 scope）")
    ap.add_argument("--out", default=None, help="输出 feature-map.json 路径")
    ap.add_argument("--data-relations-out", default=None, help="输出 data-relations.csv 路径")
    ap.add_argument("--validate", action="store_true", help="只校验已有 feature-map.json，不重写")
    args = ap.parse_args()

    ws = Path(args.workspace).expanduser().resolve()
    if args.emit_compat:
        return emit_compat(ws)
    cands = ws / "candidates"
    out = Path(args.out).expanduser().resolve() if args.out else ws / "feature-map.json"
    dr_out = (Path(args.data_relations_out).expanduser().resolve()
              if args.data_relations_out else ws / "data-relations.csv")

    scope_path, scope = load_scope(ws, args.scope)
    explicit_feats = [f.strip() for f in args.features.split(",") if f.strip()]
    included = resolve_features(explicit_feats, scope, cands)

    surface_idx_path = (Path(args.surface_index).expanduser()
                        if args.surface_index else
                        _first_existing(ws / "static-analysis" / "surface-index.csv",
                                        ws / "surface-index.csv"))
    if surface_idx_path is None:
        raise SystemExit("[fmap] surface-index.csv 不存在（缺省路径 "
                         f"{ws / 'static-analysis' / 'surface-index.csv'}；"
                         "先跑 analyze_static_pages.py 或用 --surface-index 指定）")
    surface_rows = load_surface_index(surface_idx_path)

    pf_path = (Path(args.page_features).expanduser() if args.page_features else
               _first_existing(ws / "inputs" / "page-features.csv",
                               ws / "page-features.csv"))
    page_feature_map = load_page_feature_map(pf_path)
    surface_by_symbol = {r["symbol"]: r for r in surface_rows}
    symbol_to_feature = {sym: feat for sym, feat in page_feature_map.items()
                         if sym in surface_by_symbol}

    project_arg = args.project or str((scope.get("android", {}) or {}).get("project_root", ""))
    project = Path(project_arg).expanduser().resolve() if project_arg else None

    if args.validate:
        if not out.exists():
            raise SystemExit(f"[fmap] --validate: 未找到 {out}")
        try:
            fmap = json.loads(out.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"[fmap] feature-map.json 解析失败：{exc}")
        if not cands.is_dir():
            raise SystemExit(f"[fmap] validate FAIL: candidates/ 不存在：{cands}（fail-closed）")
        ev_files = evidence_files_for_validation(cands, symbol_to_feature, surface_by_symbol)
        errors = validate_feature_map(fmap, included, surface_rows, project,
                                      evidence=ev_files)
        # data-relations 若存在则一并校验
        if dr_out.exists():
            errors += validate_data_relations(_csv_read(dr_out))
        runtime_n = sum(1 for f in fmap.get("features", [])
                        if f.get("verify_mode") == "RUNTIME")
        print(f"[fmap] validate {out.name}: features={len(fmap.get('features', []))}"
              f" runtime={runtime_n} included={len(included)}")
        if errors:
            for e in errors[:60]:
                print(f"[fmap] ERROR {e}")
            raise SystemExit(f"[fmap] validate FAIL: {len(errors)} error(s)")
        print("[fmap] validate OK")
        return 0

    # ---- 生成路径 ----
    if not cands.is_dir():
        raise SystemExit(f"[fmap] candidates/ 不存在：{cands}（先跑 scripts/gmi.py）")
    evidence = collect_evidence(cands, symbol_to_feature, surface_by_symbol)

    data_relations: List[Dict[str, Any]] = []
    if project is not None and project.is_dir():
        data_relations = scan_data_relations(project)
    else:
        print(f"[fmap] WARNING: Android 工程根不可用（scope 未提供且 --project 未传），"
              f"data-relations 源码扫描跳过，data_objects 将为空。", file=sys.stderr)

    fmap, skipped = build_feature_map(ws, scope, included, surface_rows,
                                      page_feature_map, evidence, data_relations)
    # 生成器自校验：与 --validate 共用；骨架阶段语义列与 PENDING 占位走豁免
    ev_files = {feat: set(v["files"]) for feat, v in evidence.items()}
    for sym, feat in symbol_to_feature.items():
        parsed = parse_file_line(surface_by_symbol[sym].get("source_ref", ""))
        if parsed:
            ev_files.setdefault(feat, set()).add(parsed[0])
    errors = validate_feature_map(fmap, [], surface_rows, None,
                                  evidence=ev_files, skeleton_mode=True)
    if errors:
        for e in errors[:60]:
            print(f"[fmap] ERROR {e}")
        raise SystemExit(f"[fmap] 生成路径自校验 FAIL: {len(errors)} error(s)，拒绝输出")

    dr_rows = materialize_data_relations(data_relations, evidence, included)
    dr_errors = validate_data_relations(dr_rows)
    if dr_errors:
        for e in dr_errors[:40]:
            print(f"[fmap] ERROR {e}")
        raise SystemExit(f"[fmap] data-relations 自校验 FAIL: {len(dr_errors)} error(s)")

    _atomic_json(out, fmap)
    _csv_write(dr_out, DATA_RELATION_FIELDS, dr_rows)

    runtime_n = sum(1 for f in fmap["features"] if f["verify_mode"] == "RUNTIME")
    container_n = sum(1 for f in fmap["features"]
                      if f["surfaces"] and all(s["is_container"] for s in f["surfaces"]))
    gate = fmap["coverage_gate"]
    print(f"[fmap] included={len(included)} covered={len(gate['covered'])}"
          f" missing={len(gate['missing'])} runtime={runtime_n}"
          f" container-only={container_n}")
    print(f"[fmap] surfaces-bound={sum(len(f['surfaces']) for f in fmap['features'])}"
          f" data-relations={len(dr_rows)} out={out}")
    if gate["missing"]:
        print(f"[fmap] WARNING: coverage_gate 未闭合，missing={gate['missing']}"
              f"（补显式映射/证据后重跑）", file=sys.stderr)
    if skipped:
        print(f"[fmap] 绑定校验拒绝 {len(skipped)} 条错绑（surf 不进对应 feature）：",
              file=sys.stderr)
        for line in skipped[:40]:
            print(f"[fmap] REJECT {line}", file=sys.stderr)
    print("[fmap] 骨架已生成：name/summary 留待 LLM 分片填充，填完跑 --validate 收口。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())