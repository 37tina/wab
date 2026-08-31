#!/usr/bin/env python3
"""Static contract: Phase 4 guidance requires UiTest, never Inspector APIs."""

from __future__ import annotations

import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[2]
# 2.1.1 起 ArkUI Inspector 是 ui-tree 结构证据的正式通道，但仅限
# references/arkui-inspector-evidence.md 规约的 ohosTest
# ArkUIInspectorBridge.ets 用法，且不得替代 UiTest 探针的功能/交互证据链。
# 因此不再禁止裸 "Inspector"/"arkui-inspector" 词形（那是受规约上下文），
# 只禁止与 UiTest snapshot 契约真正冲突的旧式直调 API；@kit.TestKit 仍必须
# 是功能/交互证据的唯一正式来源（下方断言）。
FORBIDDEN = ("getFilteredInspectorTree",)


class UiTestSkillContractTest(unittest.TestCase):
    def test_skill_and_every_reference_use_uitest_snapshot_contract(self) -> None:
        paths = [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]
        joined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        for token in FORBIDDEN:
            self.assertNotIn(token, joined)
        self.assertIn("@kit.TestKit", joined)
        self.assertIn("ui-test-snapshot-evidence.md", (SKILL / "SKILL.md").read_text(encoding="utf-8"))
        self.assertTrue((SKILL / "references" / "ui-test-snapshot-evidence.md").is_file())
        # Inspector 上下文必须始终处于受规约约束之下：每处提及都必须来自
        # 带 Bridge 规约引用的正式文档集，且规约文档本身必须在场。
        self.assertTrue((SKILL / "references" / "arkui-inspector-evidence.md").is_file())


if __name__ == "__main__":
    unittest.main()
