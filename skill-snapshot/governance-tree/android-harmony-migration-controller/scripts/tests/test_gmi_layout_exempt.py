"""v4 retirement guards for the gmi-native layout exempt-set machinery.

任务 #59（v4 重写）：本文件原为旧范式豁免集守护（GMI_EXEMPT_INPUT_KEYS
三方文本级一致 + gmi_native_layout_of 探针行为 + 消费循环豁免守卫）。
v4 蓝图下豁免集、gmi_native_layout 探测与 intent_pass_rate 已被整体
删除（v4 唯一路径原则，删旧不留双路径），本文件改为守护 v4 语义：

1. 旧机制不存在（fail-closed 退役断言）——在 issue_phase4_work_order.py、
   validate_gate.py 与 harmonyos-feature-implementation/scripts/
   init_implementation.py 三个历史消费方中：
   - GMI_EXEMPT_INPUT_KEYS / gmi_exempt_input_keys 集合字面量不存在；
   - gmi_native_layout_of / gmi_native_layout 探测函数与旗标不存在；
   - validate_gate.py 报告面不再有 intent_pass_rate（v4 由
     runtime_bc_pass_rate 承载同单位 BC 通过率）。
2. v4 新锚点防漂移——7 类核心产物输入面 STAGE4_INPUT_RELATIVES 在
   issue_phase4_work_order.py（签发侧）与 init_implementation.py
   （初始化侧）必须字典级一致；BC 七段结构列 BC_SEMANTIC_COLUMNS
   同样双侧一致（替代旧豁免集三方一致守护的防漂移职责）。
3. v4 工单按功能签发——issue_phase4_work_order.py 含 feature_manifest
   构建路径且不再出现任何豁免分支（"GMI_EXEMPT" 字样全文不存在）。
"""

from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
SKILL_ROOT = SCRIPTS.parent
SKILLS_ROOT = SKILL_ROOT.parent
sys.path.insert(0, str(SCRIPTS))

import issue_phase4_work_order  # noqa: E402
import validate_gate  # noqa: E402


INIT_PATH = (
    SKILLS_ROOT / "harmonyos-feature-implementation" / "scripts" / "init_implementation.py"
)
ISSUE_PATH = SCRIPTS / "issue_phase4_work_order.py"
GATE_PATH = SCRIPTS / "validate_gate.py"

RETIRED_INPUT_KEY_NAMES = {"GMI_EXEMPT_INPUT_KEYS", "gmi_exempt_input_keys"}
RETIRED_PROBE_NAMES = {"gmi_native_layout_of", "gmi_native_layout"}


def parse_tree(source: str, filename: str) -> ast.Module:
    return ast.parse(source, filename=filename)


def assigned_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def function_names(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def dict_literal(tree: ast.Module, name: str) -> dict[str, str]:
    match = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
            and isinstance(node.value, ast.Dict)
        ),
        None,
    )
    if match is None:
        raise AssertionError(f"dict literal {name!r} not found")
    result: dict[str, str] = {}
    for key, value in zip(match.value.keys, match.value.values):
        if not (isinstance(key, ast.Constant) and isinstance(value, ast.Constant)):
            raise AssertionError(f"{name} must map string literals to string literals")
        result[key.value] = value.value
    return result


class RetiredMechanismAbsenceTest(unittest.TestCase):
    """旧豁免机制必须不存在（v4 删旧不留双路径）。"""

    def test_exempt_sets_and_probe_are_gone_from_all_three_scripts(self) -> None:
        for path in (ISSUE_PATH, GATE_PATH, INIT_PATH):
            with self.subTest(script=path.name):
                source = path.read_text(encoding="utf-8")
                tree = parse_tree(source, path.name)
                self.assertEqual(
                    set(), assigned_names(tree) & RETIRED_INPUT_KEY_NAMES,
                    f"{path.name} still assigns a retired exempt-set literal",
                )
                self.assertEqual(
                    set(), function_names(tree) & RETIRED_PROBE_NAMES,
                    f"{path.name} still defines a retired gmi layout probe",
                )

    def test_issue_phase4_has_no_exempt_branch_text(self) -> None:
        """签发脚本不得以任何标识符形式引用退役机制（注释/docstring 中的
        退役历史说明不构成活机制，AST 标识符级断言不受其影响）。"""
        source = ISSUE_PATH.read_text(encoding="utf-8")
        tree = parse_tree(source, "issue_phase4_work_order.py")
        referenced = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
        }
        self.assertNotIn("GMI_EXEMPT_INPUT_KEYS", referenced)
        self.assertNotIn("gmi_native_layout", referenced)

    def test_validate_gate_reports_runtime_bc_rate_not_intent_pass_rate(self) -> None:
        source = GATE_PATH.read_text(encoding="utf-8")
        tree = parse_tree(source, "validate_gate.py")
        self.assertNotIn(
            "intent_pass_rate",
            assigned_names(tree) | function_names(tree),
            "validate_gate must not compute the retired intent_pass_rate",
        )
        self.assertNotIn('"intent_pass_rate"', source)
        self.assertIn("runtime_bc_pass_rate", source,
                      "v4 report facts must carry runtime_bc_pass_rate")


class V4InputFaceDriftGuardTest(unittest.TestCase):
    """v4 新锚点：7 类输入面与 BC 七段列在签发侧/初始化侧双侧一致。"""

    def test_stage4_input_relatives_identical_between_issue_and_init(self) -> None:
        issue_map = dict_literal(
            parse_tree(ISSUE_PATH.read_text(encoding="utf-8"), "issue_phase4_work_order.py"),
            "STAGE4_INPUT_RELATIVES",
        )
        init_map = dict_literal(
            parse_tree(INIT_PATH.read_text(encoding="utf-8"), "init_implementation.py"),
            "STAGE4_INPUT_RELATIVES",
        )
        # 16 个输入键（①–⑥ 各产物 + Phase 3 骨架；⑦ H4ENV 走 phase3_henvs，
        # 不入本表）。17 是 BC 列数（BC_SEMANTIC_COLUMNS），勿混淆。
        self.assertEqual(16, len(issue_map), sorted(issue_map))
        self.assertEqual(issue_map, init_map,
                         "STAGE4_INPUT_RELATIVES drifted between issue and init sides")

    def test_bc_semantic_columns_identical_between_issue_and_init(self) -> None:
        issue_columns = issue_phase4_work_order.BC_SEMANTIC_COLUMNS
        init_source = INIT_PATH.read_text(encoding="utf-8")
        init_tree = parse_tree(init_source, "init_implementation.py")
        match = next(
            (
                node
                for node in ast.walk(init_tree)
                if isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "BC_SEMANTIC_COLUMNS"
                and isinstance(node.value, (ast.Tuple, ast.List))
            ),
            None,
        )
        self.assertIsNotNone(match, "init_implementation.py lacks BC_SEMANTIC_COLUMNS")
        init_columns = tuple(
            item.value for item in match.value.elts if isinstance(item, ast.Constant)
        )
        self.assertEqual(issue_columns, init_columns)

    def test_work_order_uses_feature_manifest_single_path(self) -> None:
        source = ISSUE_PATH.read_text(encoding="utf-8")
        self.assertIn("def build_feature_manifest", source)
        self.assertIn('"feature_manifest"', source)
        self.assertIn("v4：7 类产物输入面", source)


if __name__ == "__main__":
    unittest.main()
