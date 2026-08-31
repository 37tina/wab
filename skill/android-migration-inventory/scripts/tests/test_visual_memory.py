# -*- coding: utf-8 -*-
"""test_visual_memory -- P2 视觉记忆（#75）最小回归。

覆盖：快照引用存在且 sha256 匹配 / ui-tree 摘要非空 / 无链 feature surface
如实降级 / coverage 实算一致 / --validate 对篡改 fail-closed /
gmi_closure 将 visual-memory.json 纳入 artifact_hashes 哈希链。
"""
from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
VISUAL_MEMORY = SCRIPTS / "visual_memory.py"
GMI_CLOSURE = SCRIPTS / "gmi_closure.py"

PNG_MIN = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" +
           struct.pack(">II", 1080, 2400) + b"\x08\x06\x00\x00\x00")


def _write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def _run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, timeout=120)


UI_XML = (
    "<?xml version='1.0'?><hierarchy><node index='0' text='' resource-id='' "
    "class='android.widget.FrameLayout' bounds='[0,0][1080,2400]'"
    "><node index='0' text='全部待办' resource-id='com.example:id/title' "
    "class='android.widget.TextView' bounds='[0,100][540,200]'/>"
    "<node index='1' text='添加' resource-id='' class='android.view.View' "
    "bounds='[0,2200][1080,2400]'/></node></hierarchy>"
)


def make_vm_workspace(root: Path) -> Path:
    """2 feature（1 RUNTIME 有链 + 1 SOURCE_CONFIRM 无链）最小工作区。"""
    ws = root / "vm-ws"
    _write(ws / "feature-map.json", json.dumps({
        "features": [
            {"feature_id": "FEATURE-TODO-CREATE", "name": "新建",
             "surfaces": [
                 {"id": "PAGE-HOME-AAAA", "kind": "page"},
                 {"id": "PAGE-ADDSHEET-BBBB", "kind": "sheet"}]},
            {"feature_id": "FEATURE-NAV-SHELL", "name": "壳",
             "surfaces": [{"id": "PAGE-MAIN-CCCC", "kind": "container"}]},
        ],
        "coverage_gate": {"included": ["FEATURE-TODO-CREATE", "FEATURE-NAV-SHELL"],
                          "included_features_covered": True}},
        ensure_ascii=False))
    _write(ws / "behavior-contracts.csv",
           "bc_id,feature_id,page_ref\n"
           "BC-CREATE-01,FEATURE-TODO-CREATE,PAGE-HOME-RUNTIME\n"
           "BC-NAV-01,FEATURE-NAV-SHELL,PAGE-HOME-RUNTIME\n")
    _write(ws / "runtime-evidence" / "runtime-chains.csv",
           "bc_id,feature_id,chain_status\nBC-CREATE-01,FEATURE-TODO-CREATE,CHAIN_PASS\n")
    chain = ws / "runtime-evidence" / "evidence" / "chains" / "BC-CREATE-01"
    _write(chain / "before" / "screenshot.png", PNG_MIN)
    _write(chain / "before" / "ui.xml", UI_XML)
    _write(chain / "after" / "screenshot.png", PNG_MIN)
    _write(chain / "after" / "ui.xml", UI_XML)
    _write(ws / "candidates" / "color-palette.candidates.csv",
           "candidate_id,color_name,hex,alpha,kind,file,line\n"
           "CAND-COLOR-0001,LightPalette.background,#FFFFFF,1.0,PALETTE,ui/theme/Color.kt,3\n"
           "CAND-COLOR-0002,gradient(listOf),token:Blue500 > token:Purple500,,GRADIENT,ui/theme/Grad.kt,7\n")
    return ws


class VisualMemoryTest(unittest.TestCase):

    def test_generate_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = make_vm_workspace(Path(td))
            r = _run(VISUAL_MEMORY, "--workspace", str(ws))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            doc = json.loads((ws / "visual-memory.json").read_text(encoding="utf-8"))
            by_sid = {s["surface_id"]: s for s in doc["surfaces"]}

            # 有链 feature：page surface 挂 before、sheet surface 挂 after
            home = by_sid["PAGE-HOME-AAAA"]
            self.assertEqual(home["runtime_evidence"]["snapshot"], "before")
            sheet = by_sid["PAGE-ADDSHEET-BBBB"]
            self.assertEqual(sheet["runtime_evidence"]["snapshot"], "after")
            for s in (home, sheet):
                shot = s["runtime_evidence"]["screenshot"]
                self.assertTrue(shot["path"].startswith("runtime-evidence/evidence/chains/"))
                self.assertEqual(shot["resolution"], [1080, 2400])
                self.assertEqual(
                    shot["sha256"],
                    hashlib.sha256((ws / shot["path"]).read_bytes()).hexdigest())
                self.assertIn("全部待办", s["ui_tree_summary"]["visible_texts"])
                self.assertTrue(s["ui_tree_summary"]["key_bounds"])
                self.assertEqual(s["ui_tree_summary"]["node_count"], 3)

            # 无链 feature（SOURCE_CONFIRM）如实降级
            main = by_sid["PAGE-MAIN-CCCC"]
            self.assertIsNone(main["runtime_evidence"])
            self.assertIsNone(main["ui_tree_summary"])

            # coverage 实算 + 色板聚合（含 token 渐变提取）
            cov = doc["coverage"]
            self.assertEqual(cov["surfaces_total"], 3)
            self.assertEqual(cov["surfaces_with_snapshot"], 2)
            self.assertEqual(cov["features_without_runtime_snapshot"],
                             ["FEATURE-NAV-SHELL"])
            palette = doc["global_palette"]
            self.assertEqual(palette["swatch_count"], 2)
            self.assertEqual(palette["background_colors"][0]["hex"], "#FFFFFF")
            self.assertEqual(palette["gradients"][0]["stops"],
                             ["Blue500", "Purple500"])
            self.assertFalse(doc["text_sizes"]["available"])

            # --validate 独立通过
            self.assertEqual(_run(VISUAL_MEMORY, "--workspace", str(ws),
                                  "--validate").returncode, 0)

    def test_validate_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = make_vm_workspace(Path(td))
            self.assertEqual(_run(VISUAL_MEMORY, "--workspace", str(ws)).returncode, 0)
            (ws / "runtime-evidence" / "evidence" / "chains" / "BC-CREATE-01"
             / "before" / "ui.xml").write_text(UI_XML + "<tamper/>", encoding="utf-8")
            r = _run(VISUAL_MEMORY, "--workspace", str(ws), "--validate")
            self.assertEqual(r.returncode, 1)
            self.assertIn("sha256 mismatch", r.stdout)

    def test_closure_chains_visual_memory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = make_vm_workspace(Path(td))
            # closure 最小门禁输入
            _write(ws / "candidates" / "manifest.sha256", "0" * 64 + "  x.csv\n")
            _write(ws / "coverage" / "coverage-ledger.csv",
                   "file,category,disposition,status,covering_candidates\n"
                   "a.kt,source,IN_SCOPE,OK,C1\n")
            _write(ws / "phase-2-report.md", "# report\n")
            self.assertEqual(_run(VISUAL_MEMORY, "--workspace", str(ws)).returncode, 0)
            r = _run(GMI_CLOSURE, "--workspace", str(ws))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            closure = json.loads((ws / "phase-2-closure.json").read_text(encoding="utf-8"))
            digest = closure["artifact_hashes"]["visual_memory_sha256"]
            self.assertEqual(digest, hashlib.sha256(
                (ws / "visual-memory.json").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()