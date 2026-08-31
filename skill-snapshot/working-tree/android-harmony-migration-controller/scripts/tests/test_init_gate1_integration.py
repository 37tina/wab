#!/usr/bin/env python3
"""Real init_migration -> Gate 1 integration test plus freeze-enumeration units.

Integration part (subprocess, no mocks):
    1. build a fake Android project (clean git HEAD), a minimal-but-valid APK
       container, and an executable apkanalyzer stub;
    2. run scripts/init_migration.py for real against the REAL skills tree
       (which currently contains __pycache__ bytecode caches, so the "pyc
       exists" scenario is covered naturally);
    3. fill scope.json programmatically and update task-ledger.csv ONLY via
       scripts/update_task_ledger.py (integration-covers the new tool);
    4. run scripts/validate_gate.py --phase 1 --write for real and require
       exit 0, verdict PASS, zero errors, no "skill freeze violated" anywhere,
       and a correctly rewritten task-ledger row.

Unit part (regression for SKILLBUG-01):
    - enumerate_frozen_skill_files must skip __pycache__/, loose *.pyc, and
      symlinks, and build_manifest_text / current_hashes must expose exactly
      the same key set (generator == verifier);
    - verify_skill_freeze must report zero errors for a tree whose manifest
      was produced by the shared enumeration even when pyc files exist.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

from _skill_freeze_common import (  # noqa: E402
    build_manifest_text,
    current_hashes,
    enumerate_frozen_skill_files,
)
from validate_gate import verify_skill_freeze  # noqa: E402


RUN_ID = "TEST-RUN-INT"
CONTROLLER_ID = "ctrl-agent-01"
INVENTORY_LEAD_ID = "inv-lead-01"
APPLICATION_ID = "com.example.fakeapp"
APP_VERSION = "1.2.3"
APP_BUILD = "42"


def build_fake_android_project(root: Path) -> Path:
    project = root / "fake-android"
    (project / "app" / "src" / "main").mkdir(parents=True)
    (project / "settings.gradle.kts").write_text(
        'rootProject.name = "FakeApp"\ninclude(":app")\n', encoding="utf-8"
    )
    (project / "build.gradle.kts").write_text(
        'plugins { id("com.android.application") version "8.0.0" }\n'
        'android {\n    namespace = "com.example.fakeapp"\n}\n',
        encoding="utf-8",
    )
    (project / "app" / "src" / "main" / "AndroidManifest.xml").write_text(
        f'<manifest package="{APPLICATION_ID}"/>\n', encoding="utf-8"
    )
    subprocess.run(
        ["git", "init", "-q"], cwd=project, check=True, stdout=subprocess.DEVNULL
    )
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=project,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return project


def build_fake_apk(root: Path) -> Path:
    apk_path = root / "fake-app.apk"
    with zipfile.ZipFile(apk_path, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00")
        archive.writestr("classes.dex", b"dex\n035\x00" + b"\x00" * 32)
        archive.writestr("resources.arsc", b"\x02\x00\x0c\x00")
    return apk_path


def build_apkanalyzer_stub(root: Path) -> Path:
    stub = root / "apkanalyzer-stub.sh"
    stub.write_text(
        "#!/bin/sh\n"
        'case "$2" in\n'
        f'  application-id) echo "{APPLICATION_ID}" ;;\n'
        f'  version-name) echo "{APP_VERSION}" ;;\n'
        f'  version-code) echo "{APP_BUILD}" ;;\n'
        '  *) echo "unexpected analyzer command: $2" >&2; exit 1 ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def fill_scope(run_dir: Path, project: Path, apk_path: Path, stub: Path) -> None:
    scope_path = run_dir / "controller" / "scope.json"
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    head = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    scope["android"].update(
        {
            "source_revision": head,
            "apk_path": str(apk_path),
            "apk_sha256": hashlib.sha256(apk_path.read_bytes()).hexdigest(),
            "application_id": APPLICATION_ID,
            "app_version": APP_VERSION,
            "app_build": APP_BUILD,
            "build_variant": "debug",
        }
    )
    scope["target"]["sdk_or_api_target"] = "HarmonyOS NEXT API 12"
    migration_scope = scope["migration_scope"]
    migration_scope["included_features"] = ["FEA-LOGIN"]
    migration_scope["key_business_capabilities"] = ["CAP-PAYMENT"]
    migration_scope["allowed_platform_substitutions"] = [
        {
            "capability": "push-notification",
            "reason": "HarmonyOS Push Kit provides the native equivalence",
            "native_equivalence_allowed": True,
        }
    ]
    scope["ownership"].update(
        {
            "migration_controller_id": CONTROLLER_ID,
            "inventory_lead_id": INVENTORY_LEAD_ID,
            "code_map_agent_id": "code-map-01",
            "runtime_state_agent_ids": ["runtime-state-01"],
            "business_rule_agent_id": "rule-agent-01",
            "data_dependency_agent_id": "data-dep-01",
            "evidence_administrator_id": "evidence-admin-01",
            "coverage_checker_id": "coverage-01",
        }
    )
    scope["environments"][0].update(
        {
            "account_id": "acct-001",
            "account_role": "owner",
            "seed_data_id": "seed-001",
            "seed_reset_ref": "reset-001",
            "network_conditions_ref": "netcond-001",
            "network_toggle_available": True,
            "emulator_model": "Pixel-8-API-34",
            "device_serial": "emulator-5554",
            "resolution": "1080x2400",
            "density_dpi": 420,
            "android_api_level": 34,
        }
    )
    scope["tool_policy"]["apk_analyzer_bin"] = str(stub)
    scope_path.write_text(json.dumps(scope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class InitGate1IntegrationTest(unittest.TestCase):
    """End-to-end: real init, real ledger tool, real Gate 1 --write PASS."""

    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("git") is None:
            raise unittest.SkipTest("git is not available")
        cls._temp = tempfile.TemporaryDirectory(prefix="gate1-int-")
        cls.tmp = Path(cls._temp.name)
        cls.project = build_fake_android_project(cls.tmp)
        cls.apk = build_fake_apk(cls.tmp)
        cls.stub = build_apkanalyzer_stub(cls.tmp)
        cls.run_dir = cls.tmp / "runs" / RUN_ID

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp.cleanup()

    def test_init_ledger_tool_and_gate1_write_pass(self) -> None:
        # Step 1: real init against the real skills tree (contains __pycache__).
        init = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "init_migration.py"),
                "--output",
                str(self.tmp / "runs"),
                "--project-root",
                str(self.project),
                "--project-name",
                "FakeApp",
                "--run-id",
                RUN_ID,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        self.assertEqual(init.returncode, 0, msg=f"init failed:\n{init.stderr}")
        self.assertTrue(self.run_dir.is_dir(), msg=init.stdout)
        # The frozen manifest must not contain any bytecode cache entry even
        # though the real skills tree ships __pycache__ directories right now.
        freeze_text = (self.run_dir / "controller" / "skill-freeze-manifest.sha256").read_text(
            encoding="utf-8"
        )
        self.assertFalse(
            any("__pycache__" in line or line.endswith(".pyc") for line in freeze_text.splitlines()),
            msg="freeze manifest must exclude __pycache__/*.pyc entries",
        )

        # Step 2: fill scope.json programmatically.
        fill_scope(self.run_dir, self.project, self.apk, self.stub)

        # Step 3: task-ledger updates MUST go through the new CSV tool.
        for phase, owner in ((1, CONTROLLER_ID), (2, INVENTORY_LEAD_ID)):
            ledger = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "update_task_ledger.py"),
                    "--run-dir",
                    str(self.run_dir),
                    "--phase",
                    str(phase),
                    "--set",
                    f"owner={owner}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )
            self.assertEqual(ledger.returncode, 0, msg=f"ledger tool failed:\n{ledger.stderr}")
        listed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "update_task_ledger.py"),
                "--run-dir",
                str(self.run_dir),
                "--phase",
                "1",
                "--list",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        self.assertEqual(listed.returncode, 0, msg=listed.stderr)
        self.assertIn(f"owner={CONTROLLER_ID}", listed.stdout)
        self.assertIn("status=IN_PROGRESS", listed.stdout)

        # Step 4: real Gate 1 with --write; default skills root (the real tree).
        gate = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "validate_gate.py"),
                "--run-dir",
                str(self.run_dir),
                "--phase",
                "1",
                "--write",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,
        )
        combined = gate.stdout + gate.stderr
        self.assertEqual(gate.returncode, 0, msg=f"gate failed:\n{combined}")
        self.assertNotIn("skill freeze violated", combined)

        report = json.loads((self.run_dir / "controller" / "gate-report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "PASS", msg=json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["errors"], [], msg=json.dumps(report, ensure_ascii=False, indent=2))
        self.assertNotIn("skill freeze violated", json.dumps(report, ensure_ascii=False))

        # Step 5: --write must have rewritten the phase 1 ledger row.
        import csv as _csv

        with (self.run_dir / "controller" / "task-ledger.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            rows = [row for row in _csv.DictReader(handle) if row.get("phase") == "1"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "PASS", msg=str(rows[0]))
        self.assertEqual(rows[0]["owner"], CONTROLLER_ID, msg=str(rows[0]))
        self.assertTrue(rows[0]["updated_at"], msg="updated_at must be stamped")


class FreezeEnumerationUnitTest(unittest.TestCase):
    """SKILLBUG-01 regression: shared enumeration excludes interpreter artifacts."""

    def make_tree(self, root: Path) -> Path:
        skill = root / "skills" / "android-migration-inventory"
        (skill / "scripts" / "__pycache__").mkdir(parents=True)
        (skill / "references").mkdir()
        (skill / "scripts" / "a.py").write_text("print('a')\n", encoding="utf-8")
        (skill / "scripts" / "__pycache__" / "x.pyc").write_bytes(b"\x00pyc")
        (skill / "scripts" / "loose.pyc").write_bytes(b"\x00pyc")
        (skill / "references" / "r.md").write_text("# r\n", encoding="utf-8")
        (skill / "SKILL.md").write_text("# skill\n", encoding="utf-8")
        (skill / "manifest.json").write_text('{"version": "2.1.2"}\n', encoding="utf-8")
        try:
            os.symlink(skill / "scripts" / "a.py", skill / "scripts" / "link.py")
        except OSError:
            self.skipTest("symlink creation is not available on this platform")
        return root / "skills"

    def test_enumeration_excludes_pycache_pyc_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = self.make_tree(Path(tmp))
            files = enumerate_frozen_skill_files(skills_root)
            expected = {
                "android-migration-inventory/scripts/a.py",
                "android-migration-inventory/references/r.md",
                "android-migration-inventory/SKILL.md",
                "android-migration-inventory/manifest.json",
            }
            self.assertEqual(set(files), expected, msg=str(sorted(files)))

    def test_generator_and_verifier_share_the_same_key_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = self.make_tree(Path(tmp))
            manifest_text, _ = build_manifest_text(skills_root)
            generated = {line.split("  ", 1)[1] for line in manifest_text.splitlines() if line}
            self.assertEqual(generated, set(current_hashes(skills_root)))
            # And neither side ever admits a bytecode artifact.
            self.assertFalse(any("__pycache__" in key or key.endswith(".pyc") for key in generated))

    def test_verify_skill_freeze_clean_for_pyc_bearing_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills_root = self.make_tree(root)
            manifest_text, _ = build_manifest_text(skills_root)
            run_dir = root / "RUN-PYC"
            (run_dir / "controller").mkdir(parents=True)
            (run_dir / "controller" / "skill-freeze-manifest.sha256").write_text(
                manifest_text, encoding="utf-8"
            )
            self.assertEqual(verify_skill_freeze(run_dir, skills_root=skills_root), [])


if __name__ == "__main__":
    unittest.main()