"""Minimal static cases for validate_gate.verify_skill_freeze.

Covers only the freeze gate: missing manifest -> skipped, drifted file -> error.
No functional gate execution or historical run regression is attempted here.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

from validate_gate import verify_skill_freeze  # noqa: E402


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VerifySkillFreezeTest(unittest.TestCase):
    def make_skills_tree(self, root: Path) -> tuple[Path, dict[str, Path]]:
        skill = root / "skills" / "android-harmony-migration-controller"
        (skill / "scripts").mkdir(parents=True)
        files = {
            "android-harmony-migration-controller/scripts/validate_gate.py": skill / "scripts" / "validate_gate.py",
            "android-harmony-migration-controller/SKILL.md": skill / "SKILL.md",
            "android-harmony-migration-controller/manifest.json": skill / "manifest.json",
        }
        files["android-harmony-migration-controller/scripts/validate_gate.py"].write_text(
            "print('frozen')\n", encoding="utf-8"
        )
        files["android-harmony-migration-controller/SKILL.md"].write_text("# skill\n", encoding="utf-8")
        files["android-harmony-migration-controller/manifest.json"].write_text(
            '{"version": "2.1.0"}\n', encoding="utf-8"
        )
        return root / "skills", files

    def write_manifest(self, run_dir: Path, files: dict[str, Path]) -> None:
        (run_dir / "controller").mkdir(parents=True, exist_ok=True)
        lines = "".join(
            f"{sha256_of(path)}  {relative}\n" for relative, path in sorted(files.items())
        )
        (run_dir / "controller" / "skill-freeze-manifest.sha256").write_text(lines, encoding="utf-8")

    def test_missing_manifest_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "LEGACY-RUN"
            (run_dir / "controller").mkdir(parents=True)
            self.assertEqual(verify_skill_freeze(run_dir), [])

    def test_drifted_file_reports_violation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills_root, files = self.make_skills_tree(root)
            run_dir = root / "RUN-1"
            self.write_manifest(run_dir, files)
            # Tamper with a frozen skill file after the manifest was written.
            files["android-harmony-migration-controller/scripts/validate_gate.py"].write_text(
                "print('tampered')\n", encoding="utf-8"
            )
            errors = verify_skill_freeze(run_dir, skills_root=skills_root)
            self.assertTrue(errors)
            self.assertTrue(
                any(
                    "skill freeze violated" in item
                    and "android-harmony-migration-controller/scripts/validate_gate.py" in item
                    for item in errors
                )
            )
            self.assertTrue(any("skill-bug-ledger" in item for item in errors))

    def test_clean_tree_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills_root, files = self.make_skills_tree(root)
            run_dir = root / "RUN-2"
            self.write_manifest(run_dir, files)
            self.assertEqual(verify_skill_freeze(run_dir, skills_root=skills_root), [])


if __name__ == "__main__":
    unittest.main()
