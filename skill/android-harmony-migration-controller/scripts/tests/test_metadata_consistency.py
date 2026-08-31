from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SKILL_ROOT = ROOT / ".codeartsdoer" / "skills"
SKILLS = (
    "android-harmony-migration-controller",
    "android-migration-inventory",
    "harmonyos-migration-scaffold",
    "harmonyos-feature-implementation",
)
MOJIBAKE = ("\ufffd", "閳", "閿", "閵", "娴ｈ", "闂冭")


def frontmatter_description(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
    if not match:
        raise AssertionError(f"Missing frontmatter description: {path}")
    return match.group(1).strip()


def yaml_quoted_value(path: Path, key: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf'^\s*{re.escape(key)}:\s*"([^"]*)"\s*$', text, re.MULTILINE)
    if not match:
        raise AssertionError(f"Missing quoted {key}: {path}")
    return match.group(1)


class MetadataConsistencyTest(unittest.TestCase):
    def test_skill_ir_is_valid_and_matches_frontmatter_and_real_resources(self) -> None:
        for name in SKILLS:
            with self.subTest(skill=name):
                root = SKILL_ROOT / name
                ir = json.loads((root / "reports" / "skill-ir.json").read_text(encoding="utf-8"))
                description = frontmatter_description(root / "SKILL.md")
                self.assertEqual(name, ir["name"])
                self.assertEqual(description, ir["job_to_be_done"])
                self.assertEqual(description, ir["trigger_surface"]["description"])
                for group in ("references", "scripts", "assets", "reports"):
                    for relative in ir["resources"][group]:
                        self.assertTrue((root / Path(relative.replace("\\", "/"))).is_file(), relative)

    def test_agent_prompts_are_readable_and_match_current_gate_contract(self) -> None:
        required = {
            "android-harmony-migration-controller": ("WAITING_HUMAN_REVIEW",),
            "android-migration-inventory": ("WAITING_HUMAN_REVIEW",),
            "harmonyos-migration-scaffold": ("WAITING_HUMAN_REVIEW",),
            "harmonyos-feature-implementation": (
                "PAGE_WORK_ORDER",
                "CAPABILITY_WORK_ORDER",
                "UI_UNDERSTANDING_AND_CONVERSION_AGENT",
                "UiTest",
            ),
        }
        for name, tokens in required.items():
            root = SKILL_ROOT / name
            for adapter in ("interface.yaml", "openai.yaml"):
                path = root / "agents" / adapter
                text = path.read_text(encoding="utf-8")
                with self.subTest(skill=name, adapter=adapter):
                    self.assertFalse(any(marker in text for marker in MOJIBAKE), text)
                    prompt = yaml_quoted_value(path, "default_prompt")
                    for token in tokens:
                        self.assertIn(token, prompt)

    def test_controller_metadata_is_human_gated_and_excludes_phase56_claims(self) -> None:
        root = SKILL_ROOT / "android-harmony-migration-controller"
        ir = json.loads((root / "reports" / "skill-ir.json").read_text(encoding="utf-8"))
        combined = json.dumps(ir, ensure_ascii=False)
        self.assertNotIn("continuously execute", combined)
        self.assertNotRegex(combined, r"issue_phase[56]|_phase56|Phase [56]")
        flattened = {item.replace("\\", "/") for values in ir["resources"].values() for item in values}
        for required in (
            "references/human-review-gates.md",
            "scripts/_human_gate.py",
            "scripts/generate_review_summary.py",
            "scripts/record_human_review.py",
            "scripts/tests/test_human_gate.py",
            "scripts/tests/test_human_gate_wiring.py",
        ):
            self.assertIn(required, flattened)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("phases-1-4-human-gated", manifest["capability_scope"])

    def test_phase4_metadata_keeps_v4_core_scripts_and_retires_page_orders(self) -> None:
        """v4（任务 #59）：Phase 4 按功能组织实施（feature-dispatch），旧页面/
        能力工单签发链（issue_page/capability_work_order + stage4_work_orders +
        page_acceptance_contract）整体退役——元数据不得再引用已删脚本，
        v4 核心初始化/校验脚本必须在场。"""
        root = SKILL_ROOT / "harmonyos-feature-implementation"
        ir = json.loads((root / "reports" / "skill-ir.json").read_text(encoding="utf-8"))
        combined = json.dumps(ir, ensure_ascii=False)
        self.assertNotIn("Inspector", combined)
        self.assertNotIn("arkui_inspector", combined)
        self.assertIn("UI_UNDERSTANDING_AND_CONVERSION_AGENT", combined)
        self.assertIn("UiTest", combined)
        scripts = {item.replace("\\", "/") for item in ir["resources"]["scripts"]}
        for retired in (
            "scripts/issue_page_work_order.py",
            "scripts/issue_capability_work_order.py",
            "scripts/stage4_work_orders.py",
            "scripts/page_acceptance_contract.py",
            "scripts/tests/test_stage4_work_orders.py",
            "scripts/tests/test_page_acceptance_contract.py",
        ):
            self.assertNotIn(retired, scripts)
        for required in (
            "scripts/init_implementation.py",
            "scripts/validate_stage4.py",
            "scripts/manage_stage4_rework.py",
            "scripts/tests/test_stage4_workflow.py",
        ):
            self.assertIn(required, scripts)


if __name__ == "__main__":
    unittest.main()
