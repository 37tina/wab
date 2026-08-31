# -*- coding: utf-8 -*-
"""visual_memory -- Phase 2 视觉记忆：per-surface 基准截图引用 + ui-tree 摘要 + 色板。

参考 legacy（phase-02-android-inventory.legacy）写法：每页 screenshot.png +
ui.xml（完整组件树 bounds/text/resource-id）+ candidates/color-palette.candidates.csv
色板。v3 chain 范式不再逐页采集，本脚本从**既有产物聚合**（不新增采集流程）：

  - 基准截图 / ui dump 引用 <- runtime-evidence/evidence/chains/<bc_id>/{before,after}/
    （链式三点快照；防篡改由 closure 的 runtime_evidence_dir_sha256 覆盖）
  - ui-tree 摘要（组件类型序列 / 可见文本集 / 关键 bounds）<- 快照内 ui.xml
  - 色板 <- candidates/color-palette.candidates.csv（无 per-surface 色值列 ->
    全局色板 + 备注）

产出 <workspace>/visual-memory.json（供 Phase 3 主题层消费；gmi_closure.py 将其
sha256 记入 artifact_hashes 哈希链）。

surface -> 快照映射（透明规则，见产物 basis.surface_to_snapshot_mapping）：
  - feature 的 page/container surface（入口）挂其链 before 快照（入口态）
  - feature 的 sheet/dialog/reusable-component/menu/view surface 挂 after 快照
    （该 BC 操作后的代表态；同 feature 多组件 surface 共享同一 after，
    细粒度锚点见 ui_tree_summary.key_bounds / visible_texts）

用法：
  python visual_memory.py --workspace <phase-02 dir> [--validate]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"
ENTRY_KINDS = {"page", "container"}
# 其余 kind（sheet/dialog/menu/reusable-component/view 等）视为操作目标 surface
MAX_CLASS_SEQUENCE = 120
MAX_VISIBLE_TEXTS = 60
MAX_KEY_BOUNDS = 24
BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def png_size(p: Path) -> Optional[List[int]]:
    """读 PNG IHDR 宽高（IHDR 固定在前 24 字节内）。失败返回 None。"""
    try:
        head = p.read_bytes()[:24]
        if len(head) >= 24 and head[12:16] == b"IHDR":
            return [int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")]
    except OSError:
        pass
    return None


def read_rows(p: Path) -> List[Dict[str, str]]:
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def parse_ui_xml(p: Path) -> Dict[str, Any]:
    """从 ui.xml 提取 ui-tree 摘要。ET 解析失败时用 regex 兜底抽 <node .../>。"""
    text = p.read_text(encoding="utf-8", errors="replace")
    nodes: List[Dict[str, str]] = []

    def _walk(el: ET.Element, depth: int) -> None:
        attrs = dict(el.attrib)
        if el.tag == "node" or "class" in attrs:
            attrs["_depth"] = str(depth)
            nodes.append(attrs)
        for child in el:
            _walk(child, depth + 1)

    parse_error: Optional[str] = None
    try:
        root = ET.fromstring(text)
        _walk(root, 0)
    except ET.ParseError as exc:
        parse_error = str(exc)
        for m in re.finditer(r"<node\b([^>]*)/?>", text):
            attrs: Dict[str, str] = {}
            for kv in re.finditer(r'(\w[\w-]*)="([^"]*)"', m.group(1)):
                attrs[kv.group(1)] = kv.group(2)
            if attrs:
                nodes.append(attrs)

    class_seq: List[str] = []
    class_hist: Dict[str, int] = {}
    visible_texts: List[str] = []
    content_descs: List[str] = []
    resource_ids: List[str] = []
    key_bounds: List[Dict[str, Any]] = []
    attr_names: set = set()
    depth_max = 0
    for a in nodes:
        attr_names.update(a.keys())
        cls = (a.get("class") or "").strip()
        if cls:
            short = cls.rsplit(".", 1)[-1]
            class_seq.append(short)
            class_hist[short] = class_hist.get(short, 0) + 1
        depth = int(a.get("_depth", "0") or 0)
        depth_max = max(depth_max, depth)
        t = (a.get("text") or "").strip()
        if t and t not in visible_texts:
            visible_texts.append(t)
        d = (a.get("content-desc") or "").strip()
        if d and d not in content_descs:
            content_descs.append(d)
        rid = (a.get("resource-id") or "").strip()
        if rid and rid not in resource_ids:
            resource_ids.append(rid)
        if (t or rid) and len(key_bounds) < MAX_KEY_BOUNDS:
            bm = BOUNDS_RE.match(a.get("bounds") or "")
            entry: Dict[str, Any] = {"class": cls or None,
                                     "resource_id": rid or None,
                                     "text": t or None,
                                     "content_desc": d or None,
                                     "bounds": a.get("bounds") or None}
            if bm:
                x1, y1, x2, y2 = (int(g) for g in bm.groups())
                entry["size"] = {"w": x2 - x1, "h": y2 - y1}
            key_bounds.append({k: v for k, v in entry.items() if v is not None})
    return {
        "node_count": len(nodes),
        "depth_max": depth_max,
        "class_sequence(document_order)": class_seq[:MAX_CLASS_SEQUENCE],
        "class_histogram": dict(sorted(class_hist.items(), key=lambda kv: -kv[1])),
        "visible_texts": visible_texts[:MAX_VISIBLE_TEXTS],
        "content_descs": content_descs[:MAX_VISIBLE_TEXTS],
        "resource_ids": resource_ids[:MAX_VISIBLE_TEXTS],
        "key_bounds": key_bounds,
        "attribute_names": sorted(n for n in attr_names if not n.startswith("_")),
    }, parse_error


def snapshot_ref(ws: Path, chain_dir: Path, phase: str) -> Dict[str, Any]:
    """组装 before/after 快照引用（路径相对 workspace + sha256 + 尺寸）。"""
    ref: Dict[str, Any] = {"dir": chain_dir.relative_to(ws).as_posix(), "phase": phase}
    for key, name in (("screenshot", "screenshot.png"), ("ui_dump", "ui.xml")):
        p = chain_dir / name
        if p.exists():
            entry: Dict[str, Any] = {"path": p.relative_to(ws).as_posix(),
                                     "sha256": sha256_file(p),
                                     "bytes": p.stat().st_size}
            if key == "screenshot":
                size = png_size(p)
                if size:
                    entry["resolution"] = size
            ref[key] = entry
        else:
            ref[key] = None
    return ref


def load_palette(cands_dir: Path) -> Dict[str, Any]:
    """聚合 candidates/color-palette.candidates.csv（静态扫描、无 per-surface 列）。"""
    rows = read_rows(cands_dir / "color-palette.candidates.csv")
    swatches: List[Dict[str, Any]] = []
    backgrounds: List[Dict[str, Any]] = []
    theme: List[Dict[str, Any]] = []
    gradients: List[Dict[str, Any]] = []
    for r in rows:
        name = (r.get("color_name") or "").strip()
        hexv = (r.get("hex") or "").strip()
        kind = (r.get("kind") or "").strip()
        origin = {"file": r.get("file", ""), "line": r.get("line", "")}
        tokens = [t.strip().replace("token:", "") for t in kind.split("|")
                  if t.strip().startswith("token:")]
        tokens += [t.strip().replace("token:", "") for t in hexv.split(">") if "token:" in t]
        sw = {"candidate_id": r.get("candidate_id", ""), "name": name,
              "hex": hexv or None, "alpha": r.get("alpha", "") or None,
              "kind": kind or None, "tokens": tokens or None, "origin": origin}
        for k in ("hex", "alpha", "kind", "tokens"):
            if sw[k] is None:
                del sw[k]
        swatches.append(sw)
        low = name.lower()
        if "background" in low and sw.get("hex"):
            backgrounds.append({"name": name, "hex": sw["hex"]})
        if any(k in low for k in ("primary", "surface", "accent", "theme")) and sw.get("hex"):
            theme.append({"name": name, "hex": sw["hex"]})
        if "GRADIENT" in kind.upper():
            gradients.append({"name": name,
                              "stops": [t for t in (tokens or
                                          [s.strip() for s in hexv.split(">")])],
                              "origin": origin})
    return {
        "source": "candidates/color-palette.candidates.csv",
        "basis": "global",
        "note": ("候选表无 per-surface 色值列（源码静态扫描产物）：色值来自 theme/"
                 "palette 源码定义，Phase 3 主题层结合 surface 的 ui_tree_summary"
                 ".visible_texts / key_bounds 语义就近映射"),
        "swatch_count": len(swatches),
        "background_colors": backgrounds,
        "theme_colors": theme,
        "gradients": gradients,
        "swatches": swatches,
    }


def build(ws: Path) -> Dict[str, Any]:
    fmap = json.loads((ws / "feature-map.json").read_text(encoding="utf-8"))
    features = fmap.get("features", [])
    bc_rows = read_rows(next((p for p in (ws / "behavior-contracts.csv",
                                          ws / "candidates" / "behavior-contracts.csv")
                              if p.exists()), Path("-")))
    chain_rows = read_rows(ws / "runtime-evidence" / "runtime-chains.csv")
    chain_status = {r.get("bc_id", ""): r.get("chain_status", "") for r in chain_rows}

    # feature -> 有证据目录的链（CHAIN_PASS 优先，bc_id 字典序保证确定性）
    bcs_by_feature: Dict[str, List[str]] = {}
    for r in bc_rows:
        fid, bc = r.get("feature_id", ""), r.get("bc_id", "")
        if fid and bc:
            bcs_by_feature.setdefault(fid, []).append(bc)
    chain_of_feature: Dict[str, str] = {}
    for fid, bcs in bcs_by_feature.items():
        with_dir = sorted(bc for bc in bcs
                          if (ws / "runtime-evidence" / "evidence" / "chains" / bc).is_dir())
        if not with_dir:
            continue
        passed = [bc for bc in with_dir if chain_status.get(bc) == "CHAIN_PASS"]
        chain_of_feature[fid] = (passed or with_dir)[0]

    # surface 聚合（surface_id 去重；features 记全部引用方）
    surfaces: Dict[str, Dict[str, Any]] = {}
    for f in features:
        fid = f.get("feature_id", "")
        for s in f.get("surfaces", []):
            sid, kind = s.get("id", ""), s.get("kind", "")
            rec = surfaces.setdefault(sid, {"surface_id": sid, "kind": kind,
                                            "features": [], "_entry": False,
                                            "_target": False})
            rec["features"].append(fid)
            rec["_entry"] = rec["_entry"] or kind in ENTRY_KINDS
            rec["_target"] = rec["_target"] or kind not in ENTRY_KINDS

    chains_root = ws / "runtime-evidence" / "evidence" / "chains"
    ui_summary_cache: Dict[str, Any] = {}
    runtime_entry_symbols = sorted({r.get("page_ref", "") for r in bc_rows
                                    if r.get("page_ref")})
    for rec in surfaces.values():
        chosen: Optional[tuple] = None  # (bc_id, phase_kind) phase_kind: before|after
        want_before, want_after = rec.pop("_entry"), rec.pop("_target")
        for fid in rec["features"]:
            bc = chain_of_feature.get(fid)
            if not bc:
                continue
            phase = "before" if want_before else ("after" if want_after else None)
            if phase and (chains_root / bc / phase).is_dir():
                chosen = (bc, phase)
                break
        if chosen is None:
            # 入口/目标都未直接命中（如共享 surface 无所属链）→ 尝试任一引用链 after
            for fid in rec["features"]:
                bc = chain_of_feature.get(fid)
                if bc and (chains_root / bc / "after").is_dir():
                    chosen = (bc, "after")
                    break
        if chosen is None:
            rec["runtime_evidence"] = None
            rec["ui_tree_summary"] = None
            rec["note"] = ("no runtime chain snapshot for owning features "
                           "(SOURCE_CONFIRM / not captured); see basis")
            continue
        bc, phase = chosen
        rec["runtime_evidence"] = {"bc_id": bc, "snapshot": phase,
                                   **snapshot_ref(ws, chains_root / bc / phase, phase)}
        ui_path = chains_root / bc / phase / "ui.xml"
        if ui_path.exists():
            cache_key = str(ui_path)
            if cache_key not in ui_summary_cache:
                ui_summary_cache[cache_key] = parse_ui_xml(ui_path)
            summary, parse_error = ui_summary_cache[cache_key]
            rec["ui_tree_summary"] = dict(summary)
            rec["ui_tree_summary"]["source"] = f"{bc}/{phase}/ui.xml"
            if parse_error:
                rec["ui_tree_summary"]["parse_fallback"] = f"regex ({parse_error})"
        else:
            rec["ui_tree_summary"] = None

    feats_with_snapshot = {fid for fid, bc in chain_of_feature.items()
                           if (chains_root / bc).is_dir()}
    per_feature = []
    for f in features:
        fid = f.get("feature_id", "")
        sids = [s.get("id", "") for s in f.get("surfaces", [])]
        got = sum(1 for sid in sids if surfaces.get(sid, {}).get("runtime_evidence"))
        per_feature.append({"feature_id": fid, "surfaces": len(sids),
                            "with_snapshot": got,
                            "direct_chain": fid in feats_with_snapshot or None})
    surfaces_list = sorted(surfaces.values(), key=lambda r: r["surface_id"])
    for rec in surfaces_list:
        rec["features"] = sorted(set(rec["features"]))
    with_snapshot = sum(1 for r in surfaces_list if r.get("runtime_evidence"))
    total = len(surfaces_list)

    doc = {
        "schema_version": SCHEMA_VERSION,
        "generator": "visual_memory",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "workspace": str(ws),
        "basis": {
            "paradigm": "aggregate-from-existing-artifacts (no new capture)",
            "legacy_reference": ("legacy phase-02 per-page screenshot.png + ui.xml + "
                                 "candidates/color-palette.candidates.csv"),
            "snapshot_root": "runtime-evidence/evidence/chains",
            "runtime_entry_symbols": runtime_entry_symbols,
            "surface_to_snapshot_mapping": (
                "feature page/container surface -> its chain before snapshot (entry "
                "state); sheet/dialog/reusable-component surface -> after snapshot "
                "(post-operation representative state); component surfaces of one "
                "feature share the same after snapshot — fine-grained anchors are "
                "ui_tree_summary.visible_texts / key_bounds"),
            "chain_pick_rule": "CHAIN_PASS first, then bc_id lexicographic",
        },
        "surfaces": surfaces_list,
        "global_palette": load_palette(ws / "candidates"),
        "text_sizes": {
            "available": False,
            "note": ("uiautomator dump carries no font-size attribute (Compose nodes "
                     "expose no textSize); Phase 3 theme layer should derive sizes "
                     "from design tokens / Phase 4 visual walkthrough"),
            "ui_attribute_names_probe": sorted(
                {n for r in surfaces_list if r.get("ui_tree_summary")
                 for n in r["ui_tree_summary"].get("attribute_names", [])})[:40],
        },
        "coverage": {
            "features_total": len(features),
            "features_with_runtime_snapshot": sorted(feats_with_snapshot),
            "features_without_runtime_snapshot": sorted(
                f.get("feature_id", "") for f in features
                if f.get("feature_id") not in feats_with_snapshot),
            "surfaces_total": total,
            "surfaces_with_snapshot": with_snapshot,
            "surface_coverage_pct": round(with_snapshot / total * 100, 1) if total else 0.0,
            "per_feature": per_feature,
        },
    }
    return doc


def validate(ws: Path) -> List[str]:
    """fail-closed 自检：快照引用存在且哈希匹配 / 摘要非空 / coverage 与实算一致。"""
    errors: List[str] = []
    doc_path = ws / "visual-memory.json"
    if not doc_path.exists():
        return [f"visual-memory.json missing: {doc_path}"]
    try:
        doc = json.loads(doc_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"visual-memory.json unreadable: {exc}"]

    for rec in doc.get("surfaces", []):
        sid = rec.get("surface_id", "?")
        ev = rec.get("runtime_evidence")
        if not ev:
            continue
        for key in ("screenshot", "ui_dump"):
            ref = ev.get(key)
            if not ref:
                errors.append(f"{sid}: {key} reference missing (snapshot dir incomplete)")
                continue
            p = ws / ref.get("path", "")
            if not p.is_file():
                errors.append(f"{sid}: {key} path missing: {ref.get('path')}")
            elif sha256_file(p) != ref.get("sha256"):
                errors.append(f"{sid}: {key} sha256 mismatch: {ref.get('path')}")
        summary = rec.get("ui_tree_summary") or {}
        if not summary.get("node_count"):
            errors.append(f"{sid}: ui_tree_summary empty (node_count=0)")
        elif not (summary.get("visible_texts") or summary.get("key_bounds")):
            errors.append(f"{sid}: ui_tree_summary lacks visible_texts/key_bounds")

    cov = doc.get("coverage", {})
    actual_with = sum(1 for r in doc.get("surfaces", []) if r.get("runtime_evidence"))
    if cov.get("surfaces_with_snapshot") != actual_with:
        errors.append(f"coverage mismatch: declared {cov.get('surfaces_with_snapshot')}"
                      f" != actual {actual_with}")
    if cov.get("surfaces_total") != len(doc.get("surfaces", [])):
        errors.append("coverage surfaces_total != len(surfaces)")
    if not doc.get("global_palette", {}).get("swatches"):
        errors.append("global_palette empty (color-palette candidates not aggregated)")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="phase-2 visual memory (aggregate)")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--validate", action="store_true",
                    help="只校验已生成的 visual-memory.json（不重写）")
    args = ap.parse_args()
    ws = Path(args.workspace)

    if args.validate:
        errors = validate(ws)
        if errors:
            print("VISUAL MEMORY INVALID:")
            for e in errors:
                print("  -", e)
            return 1
        print("VISUAL MEMORY OK")
        return 0

    if not (ws / "feature-map.json").exists():
        print(f"feature-map.json missing under {ws}", file=sys.stderr)
        return 1
    doc = build(ws)
    out = ws / "visual-memory.json"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    cov = doc["coverage"]
    print(f"VISUAL MEMORY: surfaces={cov['surfaces_with_snapshot']}/"
          f"{cov['surfaces_total']} ({cov['surface_coverage_pct']}%) "
          f"features(chain)={len(cov['features_with_runtime_snapshot'])}/"
          f"{cov['features_total']} palette={doc['global_palette']['swatch_count']}")
    print("->", out)
    errors = validate(ws)
    if errors:
        print("SELF-VALIDATE FAILED:")
        for e in errors:
            print("  -", e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())