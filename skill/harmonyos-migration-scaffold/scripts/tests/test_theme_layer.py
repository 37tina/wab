#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""emit_theme_layer（#77 主题层）最小单测。

覆盖：
1. token 派生真伪：背景/前景色来自色板 swatch（来源全名保真）、
   primary 无 swatch 时退化为平台默认并注明、typography 走平台标准阶梯
   （visual-memory text_sizes.available=false）；
2. 渐变 stops 顺序保真：token 引用未解析 hex 时 resolved=false 且顺序
   不变；palette 含 token hex 时可解析为 hex 数组；
3. dark 派生三态：palette-dark-swatch（真实 run 形态）/
   inverted-from-light（色板无 Dark swatch 时明色 HSL 亮度反演）/
   platform-default（无 visual-memory 整体退化）；
4. emit_theme_layer 端到端：三产物文件 + surface-plan.json theme_tokens
   摘要（幂等可重放）；
5. HOME-FULL-RUN1 真实 visual-memory 集成断言（存在时运行，否则 skip）。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
REPO_ROOT = SCRIPTS.parents[3]
# migration-runs 位于工作流根（android-harmony-skills 之上），存在时跑真实集成
REAL_RUN = REPO_ROOT.parent / "migration-runs" / "HOME-FULL-RUN1"
REAL_VISUAL_MEMORY = REAL_RUN / "phase-02-android-inventory" / "visual-memory.json"

sys.path.insert(0, str(SCRIPTS))

import init_scaffold  # noqa: E402


def _swatch(name: str, hex_value: str) -> dict:
    return {
        "candidate_id": f"CAND-{name}", "name": name, "hex": hex_value,
        "kind": "PALETTE", "origin": {"file": "theme/Colors.kt", "line": "1"},
    }


def _fixture_visual_memory(with_dark: bool = True, with_hex_stops: bool = False) -> dict:
    light = [
        _swatch("MockLightPalette.background", "#FFFFFF"),
        _swatch("MockLightPalette.pageBackground", "#F2F2F2"),
        _swatch("MockLightPalette.cardBackground", "#FFFFFF"),
        _swatch("MockLightPalette.elevatedCardBackground", "#FAFAFA"),
        _swatch("MockLightPalette.content", "#111111"),
        _swatch("MockLightPalette.contentVariant", "#666666"),
        _swatch("MockLightPalette.onPrimary", "#FFFFFF"),
        _swatch("MockLightPalette.scrimNormal", "#66000000"),
    ]
    dark = [
        _swatch("MockDarkPalette.background", "#0A0A0A"),
        _swatch("MockDarkPalette.pageBackground", "#000000"),
        _swatch("MockDarkPalette.cardBackground", "#1C1C1E"),
        _swatch("MockDarkPalette.elevatedCardBackground", "#2C2C2E"),
        _swatch("MockDarkPalette.content", "#EEEEEE"),
        _swatch("MockDarkPalette.contentVariant", "#999999"),
        _swatch("MockDarkPalette.onPrimary", "#FFFFFF"),
        _swatch("MockDarkPalette.scrimNormal", "#99000000"),
    ]
    swatches = light + dark
    if with_hex_stops:
        swatches += [
            _swatch("Blue500", "#3B82F6"),
            _swatch("Purple500", "#A855F7"),
        ]
    gradient_stops = (
        ["Blue500", "Purple500"] if with_hex_stops
        else ["Rose500", "Red500", "Amber500"]
    )
    swatches.append({
        "candidate_id": "CAND-GRAD-1", "name": "gradient(listOf)",
        "hex": " > ".join(f"token:{s}" for s in gradient_stops),
        "kind": "GRADIENT", "tokens": gradient_stops,
        "origin": {"file": "theme/Gradient.kt", "line": "42"},
    })
    return {
        "schema_version": 1.0,
        "generator": "visual_memory",
        "workspace": "/fixture/phase-02",
        "global_palette": {
            "source": "candidates/color-palette.candidates.csv",
            "basis": "global",
            "swatch_count": len(swatches),
            "swatches": swatches,
            "background_colors": [
                {"name": "MockLightPalette.background", "hex": "#FFFFFF"},
            ],
            "theme_colors": [
                {"name": "MockLightPalette.onPrimary", "hex": "#FFFFFF"},
            ],
            "gradients": [],
        },
        "text_sizes": {"available": False, "note": "fixture: no font-size data"},
    }


class ThemeDerivationTest(unittest.TestCase):
    def test_tokens_derive_from_palette_with_source_names(self) -> None:
        tokens = init_scaffold._derive_theme_tokens(_fixture_visual_memory())
        self.assertEqual(tokens["mode"], "palette-derived")
        self.assertEqual(tokens["dark_mode"], "palette-dark-swatch")
        # 背景色来自色板 swatch（值 + 来源全名保真）
        self.assertEqual(tokens["light"]["background"], "#FFFFFF")
        self.assertEqual(tokens["source_map"]["background"], "MockLightPalette.background")
        self.assertEqual(tokens["light"]["surface"], "#FFFFFF")
        self.assertEqual(tokens["source_map"]["surface"], "MockLightPalette.cardBackground")
        self.assertEqual(tokens["light"]["onBackground"], "#111111")
        self.assertEqual(tokens["source_map"]["onBackground"], "MockLightPalette.content")
        # dark 来自 Dark swatch
        self.assertEqual(tokens["dark"]["background"], "#0A0A0A")
        self.assertEqual(tokens["dark"]["surface"], "#1C1C1E")
        self.assertEqual(tokens["dark_source_map"]["background"], "MockDarkPalette.background")
        # primary 无 swatch → 平台默认并注明
        self.assertEqual(tokens["light"]["primary"], "#007DFF")
        self.assertEqual(tokens["source_map"]["primary"], "platform-default")
        # typography 无字号数据 → 平台标准阶梯
        self.assertEqual(tokens["typography_source"], "platform-standard-ladder")
        self.assertEqual(tokens["typography"]["title"], 24)
        self.assertEqual(tokens["typography"]["body"], 16)
        self.assertFalse(tokens["text_sizes_available"])

    def test_gradient_stop_order_preserved_unresolved(self) -> None:
        tokens = init_scaffold._derive_theme_tokens(_fixture_visual_memory())
        gradient = tokens["gradient"]
        self.assertIsNotNone(gradient)
        self.assertEqual(gradient["stops"], ["Rose500", "Red500", "Amber500"])
        self.assertFalse(gradient["resolved_to_hex"])
        self.assertIsNone(gradient["hexes"])
        self.assertEqual(gradient["source_swatch"], "CAND-GRAD-1")

    def test_gradient_resolves_when_palette_has_token_hex(self) -> None:
        tokens = init_scaffold._derive_theme_tokens(
            _fixture_visual_memory(with_hex_stops=True)
        )
        gradient = tokens["gradient"]
        self.assertTrue(gradient["resolved_to_hex"])
        self.assertEqual(gradient["hexes"], ["#3B82F6", "#A855F7"])
        self.assertEqual(gradient["stops"], ["Blue500", "Purple500"])

    def test_dark_inverted_when_palette_lacks_dark_swatches(self) -> None:
        fixture = _fixture_visual_memory()
        fixture["global_palette"]["swatches"] = [
            s for s in fixture["global_palette"]["swatches"]
            if "Dark" not in s["name"]
        ]
        tokens = init_scaffold._derive_theme_tokens(fixture)
        self.assertEqual(tokens["dark_mode"], "inverted-from-light")
        expected = init_scaffold._invert_hex("#FFFFFF")
        self.assertEqual(tokens["dark"]["background"], expected)
        self.assertTrue(tokens["dark_source_map"]["background"].startswith("inverted:"))

    def test_platform_default_fallback_without_visual_memory(self) -> None:
        tokens = init_scaffold._derive_theme_tokens(None)
        self.assertEqual(tokens["mode"], "platform-default")
        self.assertEqual(tokens["dark_mode"], "platform-default")
        self.assertEqual(
            tokens["light"]["background"], init_scaffold.THEME_PLATFORM_DEFAULTS["background"]
        )
        self.assertEqual(tokens["source_map"]["background"], "platform-default")
        self.assertIsNone(tokens["gradient"])
        self.assertEqual(tokens["typography_source"], "platform-standard-ladder")

    def test_typography_prefers_text_sizes_when_available(self) -> None:
        fixture = _fixture_visual_memory()
        fixture["text_sizes"] = {
            "available": True,
            "sizes": {"title": 22, "body": 15},
        }
        tokens = init_scaffold._derive_theme_tokens(fixture)
        self.assertEqual(tokens["typography_source"], "visual-memory-text-sizes")
        self.assertEqual(tokens["typography"]["title"], 22)
        self.assertEqual(tokens["typography"]["body"], 15)
        # sizes 缺档回退标准阶梯
        self.assertEqual(tokens["typography"]["caption"], 12)

    def test_hex_helpers(self) -> None:
        self.assertEqual(init_scaffold._norm_hex("#ffffff"), "#FFFFFF")
        self.assertEqual(init_scaffold._norm_hex("FFF"), "#FFFFFF")
        self.assertIsNone(init_scaffold._norm_hex("not-a-color"))
        # 反演对称性与 alpha 保留
        self.assertEqual(init_scaffold._invert_hex("#FFFFFF"), "#000000")
        self.assertEqual(init_scaffold._invert_hex("#66000000"), "#66FFFFFF")


class EmitThemeLayerE2ETest(unittest.TestCase):
    def _workspace(self, root: Path, visual_memory: dict | None) -> Path:
        phase2 = root / "phase-02-android-inventory"
        phase2.mkdir(parents=True, exist_ok=True)
        if visual_memory is not None:
            (phase2 / "visual-memory.json").write_text(
                json.dumps(visual_memory, ensure_ascii=False), encoding="utf-8"
            )
        workspace = root / "phase-03-harmony-scaffold"
        project = workspace / "harmony-project" / "entry" / "src" / "main"
        (project / "ets").mkdir(parents=True, exist_ok=True)
        (workspace / "surface-plan.json").write_text(
            json.dumps({"schema_version": 1, "routes": []}), encoding="utf-8"
        )
        return workspace

    def test_emit_writes_artifacts_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self._workspace(root, _fixture_visual_memory())
            input_lock = {"inputs": {}}
            summary = init_scaffold.emit_theme_layer(workspace, input_lock)
            theme_file = (
                workspace / "harmony-project" / "entry/src/main/ets/foundation/AppTheme.ets"
            )
            base_file = (
                workspace / "harmony-project" / "entry/src/main/resources/base/element/color.json"
            )
            dark_file = (
                workspace / "harmony-project" / "entry/src/main/resources/dark/element/color.json"
            )
            for artifact in (theme_file, base_file, dark_file):
                self.assertTrue(artifact.is_file(), artifact)
            theme_text = theme_file.read_text(encoding="utf-8")
            self.assertIn("export class AppTheme", theme_text)
            self.assertIn("background: '#FFFFFF'", theme_text)
            self.assertIn("// MockLightPalette.background", theme_text)
            self.assertIn("accentTokens: ['Rose500', 'Red500', 'Amber500']", theme_text)
            self.assertIn("title: 24", theme_text)
            base_colors = json.loads(base_file.read_text(encoding="utf-8"))["color"]
            dark_colors = json.loads(dark_file.read_text(encoding="utf-8"))["color"]
            base_map = {entry["name"]: entry["value"] for entry in base_colors}
            dark_map = {entry["name"]: entry["value"] for entry in dark_colors}
            self.assertEqual(base_map["app_background"], "#FFFFFF")
            self.assertEqual(dark_map["app_background"], "#0A0A0A")
            self.assertEqual(len(base_colors), summary["resource_color_count"])
            # surface-plan.json 摘要追加 + 幂等重放
            plan = json.loads((workspace / "surface-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["theme_tokens"]["mode"], "palette-derived")
            self.assertEqual(plan["theme_tokens"]["dark_mode"], "palette-dark-swatch")
            self.assertEqual(plan["theme_tokens"]["source_map"]["background"], "MockLightPalette.background")
            replay = init_scaffold.emit_theme_layer(workspace, input_lock)
            self.assertEqual(replay["mode"], summary["mode"])
            self.assertEqual(replay["color_token_count"], summary["color_token_count"])

    def test_emit_falls_back_without_visual_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self._workspace(root, None)
            summary = init_scaffold.emit_theme_layer(workspace, {"inputs": {}})
            self.assertEqual(summary["mode"], "platform-default")
            self.assertFalse(summary["visual_memory"]["available"])
            theme_text = (
                workspace / "harmony-project" / "entry/src/main/ets/foundation/AppTheme.ets"
            ).read_text(encoding="utf-8")
            self.assertIn("platform-default", theme_text)
            self.assertIn(
                f"background: '{init_scaffold.THEME_PLATFORM_DEFAULTS['background']}'",
                theme_text,
            )
            plan = json.loads((workspace / "surface-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["theme_tokens"]["mode"], "platform-default")


class RealRunIntegrationTest(unittest.TestCase):
    """HOME-FULL-RUN1 真实 visual-memory 集成（存在时运行）。"""

    def test_real_visual_memory_derivation(self) -> None:
        if not REAL_VISUAL_MEMORY.is_file():
            self.skipTest(f"real visual-memory not present: {REAL_VISUAL_MEMORY}")
        visual_memory = json.loads(REAL_VISUAL_MEMORY.read_text(encoding="utf-8"))
        tokens = init_scaffold._derive_theme_tokens(visual_memory)
        self.assertEqual(tokens["mode"], "palette-derived")
        self.assertEqual(tokens["dark_mode"], "palette-dark-swatch")
        self.assertEqual(tokens["light"]["background"], "#FFFFFF")
        self.assertEqual(tokens["source_map"]["background"], "GlasenseLightPalette.background")
        self.assertEqual(tokens["dark"]["background"], "#000000")
        self.assertEqual(tokens["dark_source_map"]["background"], "GlasenseDarkPalette.background")
        self.assertEqual(tokens["light"]["surface"], "#FFFFFF")
        self.assertEqual(tokens["dark"]["surface"], "#1B1C1D")
        # 真实 run：渐变 stops 为源码 token 引用（无 hex 解析），顺序保真
        self.assertEqual(
            tokens["gradient"]["stops"],
            ["Blue500", "Purple500", "Pink500", "Indigo500", "Blue500"],
        )
        self.assertFalse(tokens["gradient"]["resolved_to_hex"])
        # 真实 run：text_sizes.available=false → 平台标准阶梯
        self.assertFalse(tokens["text_sizes_available"])
        self.assertEqual(tokens["typography"]["title"], 24)
        self.assertEqual(tokens["swatch_count"], 68)


if __name__ == "__main__":
    unittest.main()