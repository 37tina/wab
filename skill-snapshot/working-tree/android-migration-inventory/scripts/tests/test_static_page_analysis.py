#!/usr/bin/env python3
"""Offline tests for deterministic Android static page discovery."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1]


class StaticPageAnalysisTest(unittest.TestCase):
    def _run_analyzer(self, workspace: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            sys.executable, str(SKILL / "scripts" / "analyze_static_pages.py"),
            "--workspace", str(workspace), "--analyzed-by", "code-map-agent-1",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def _run_validator(self, workspace: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            sys.executable, str(SKILL / "scripts" / "validate_static_analysis.py"),
            "--workspace", str(workspace),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def test_xml_activity_event_state_and_transition_are_discovered(self) -> None:
        with tempfile.TemporaryDirectory(prefix="android-static-analysis-") as temp_name:
            root = Path(temp_name)
            project = root / "project"
            workspace = root / "phase-02-android-inventory"
            layout = project / "app" / "src" / "main" / "res" / "layout"
            values = project / "app" / "src" / "main" / "res" / "values"
            source = project / "app" / "src" / "main" / "java" / "demo"
            layout.mkdir(parents=True)
            values.mkdir(parents=True)
            source.mkdir(parents=True)
            workspace.mkdir()
            (project / "app" / "src" / "main" / "AndroidManifest.xml").write_text(
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="demo">'
                '<uses-permission android:name="android.permission.CAMERA"/>'
                '<application><activity android:name=".LoginActivity"><intent-filter>'
                '<action android:name="android.intent.action.MAIN"/>'
                '<category android:name="android.intent.category.LAUNCHER"/>'
                '</intent-filter></activity></application></manifest>', encoding="utf-8",
            )
            (values / "strings.xml").write_text(
                '<resources><string name="login">登录</string></resources>', encoding="utf-8",
            )
            (layout / "activity_login.xml").write_text(
                '<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android" '
                'android:layout_width="match_parent" android:layout_height="match_parent">'
                '<Button android:id="@+id/loginButton" android:layout_width="match_parent" '
                'android:layout_height="48dp" android:text="@string/login"/>'
                '</LinearLayout>', encoding="utf-8",
            )
            (source / "LoginActivity.kt").write_text(
                'class LoginActivity : AppCompatActivity() {\n'
                ' fun show() { setContentView(R.layout.activity_login)\n'
                ' loginButton.setOnClickListener { if (ready) startActivity(Intent(this, HomeActivity::class.java)) }\n'
                ' fun hidden() { Class.forName("demo.Plugin"); WebView(this).loadUrl("https://example.test") }\n'
                ' fun effects(p: SharedPreferences, c: ClipboardManager) { p.edit(); c.setPrimaryClip(clip); '
                'WorkManager.getInstance(this); requestPermissions(arrayOf("CAMERA"), 1); OkHttpClient() }\n'
                '}\n', encoding="utf-8",
            )
            (workspace / "phase-manifest.json").write_text(json.dumps({
                "phase": 2, "status": "IN_PROGRESS", "android_project_root": str(project),
                "source_revision": "abc123", "included_features": ["FEATURE-AUTH"],
                "ownership": {"code_map_agent_id": "code-map-agent-1"},
            }), encoding="utf-8")
            analyzer = subprocess.run([
                sys.executable, str(SKILL / "scripts" / "analyze_static_pages.py"),
                "--workspace", str(workspace), "--analyzed-by", "code-map-agent-1",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(analyzer.returncode, 0, analyzer.stderr)
            pages = json.loads((workspace / "static-analysis" / "pages.json").read_text(encoding="utf-8"))["pages"]
            components = json.loads((workspace / "static-analysis" / "components.json").read_text(encoding="utf-8"))["components"]
            events = json.loads((workspace / "static-analysis" / "events.json").read_text(encoding="utf-8"))["events"]
            transitions = json.loads((workspace / "static-analysis" / "transitions.json").read_text(encoding="utf-8"))["transitions"]
            states = json.loads((workspace / "static-analysis" / "state-candidates.json").read_text(encoding="utf-8"))["states"]
            advanced = json.loads((workspace / "static-analysis" / "advanced-analysis.json").read_text(encoding="utf-8"))
            self.assertEqual([page["symbol"] for page in pages], ["LoginActivity"])
            self.assertTrue(any(row["resource_id"] == "loginButton" and row["text"] == "登录" for row in components))
            self.assertTrue(any(row["component_symbol"] == "loginButton" for row in events))
            self.assertTrue(any(row["target_symbol"] == "HomeActivity" for row in transitions))
            self.assertTrue(any(row["expression"] == "ready" for row in states))
            self.assertTrue({"REFLECTION", "WEBVIEW"}.issubset(
                {row["risk_type"] for row in advanced["dynamic_risks"]}
            ))
            self.assertTrue({"PREFERENCES", "CLIPBOARD", "BACKGROUND", "PERMISSION", "NETWORK"}.issubset(
                {row["effect_type"] for row in advanced["side_effects"]}
            ))
            self.assertTrue({"REMOTE_ERROR", "PERMISSION_DENIED", "NETWORK_OFFLINE"}.issubset(
                {row["scenario_type"] for row in advanced["scenarios"]}
            ))
            validator = subprocess.run([
                sys.executable, str(SKILL / "scripts" / "validate_static_analysis.py"),
                "--workspace", str(workspace),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(validator.returncode, 0, validator.stdout + validator.stderr)

    def test_discovery_gaps_are_accounted_for_and_cannot_silently_pass(self) -> None:
        with tempfile.TemporaryDirectory(prefix="android-static-gap-") as temp_name:
            root = Path(temp_name)
            project = root / "project"
            workspace = root / "phase-02-android-inventory"
            layout = project / "app" / "src" / "main" / "res" / "layout"
            source = project / "app" / "src" / "main" / "java" / "demo"
            layout.mkdir(parents=True)
            source.mkdir(parents=True)
            workspace.mkdir()
            (project / "app" / "src" / "main" / "AndroidManifest.xml").write_text(
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="demo">'
                '<application><activity android:name=".MainActivity"/></application></manifest>',
                encoding="utf-8",
            )
            (layout / "activity_main.xml").write_text(
                '<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android" '
                'android:layout_width="match_parent" android:layout_height="match_parent"/>',
                encoding="utf-8",
            )
            (layout / "broken.xml").write_text("<LinearLayout>", encoding="utf-8")
            (source / "MainActivity.kt").write_text(
                'class MainActivity : Activity() { fun show() { setContentView(R.layout.activity_main) } }',
                encoding="utf-8",
            )
            (source / "HugeScreen.kt").write_text("x" * (2 * 1024 * 1024 + 1), encoding="utf-8")
            (workspace / "phase-manifest.json").write_text(json.dumps({
                "phase": 2, "status": "IN_PROGRESS", "android_project_root": str(project),
                "source_revision": "abc123", "included_features": ["FEATURE-A"],
                "ownership": {"code_map_agent_id": "code-map-agent-1"},
            }), encoding="utf-8")

            analyzer = self._run_analyzer(workspace)
            self.assertEqual(analyzer.returncode, 0, analyzer.stderr)
            index = json.loads(
                (workspace / "static-analysis" / "project-index.json").read_text(encoding="utf-8")
            )
            ledger = index["source_scan"]
            self.assertEqual(ledger["discovered_count"], 2)
            self.assertEqual(ledger["parsed_count"], 1)
            self.assertEqual(ledger["skipped_count"], 1)
            self.assertEqual(ledger["skipped"][0]["reason"], "FILE_TOO_LARGE")
            tasks = json.loads(
                (workspace / "static-analysis" / "runtime-tasks.json").read_text(encoding="utf-8")
            )["tasks"]
            blocking = [row for row in tasks if row.get("blocking_discovery_gap")]
            self.assertEqual({row["task_type"] for row in blocking}, {"XML_PARSE_ERROR", "SOURCE_SCAN_SKIPPED"})
            self.assertTrue(all(row.get("subject_id") for row in blocking))

            validator = self._run_validator(workspace)
            self.assertNotEqual(validator.returncode, 0, validator.stdout + validator.stderr)
            self.assertIn("blocking discovery gap", validator.stdout)

    def test_fidelity_attrs_three_states(self) -> None:
        """fix #5 fidelity 三态：显式值 / INHERITED / 未采集。

        - 显式声明 fidelity 属性的组件必须记录真值（不接受 INHERITED 冒充）；
        - 未显式声明（吃 theme/default style 的普通 XML 控件）记录
          {"style_source": "INHERITED"} 占位，validator 放行；
        - 完全缺失字段（既无值也无 INHERITED，篡改产物模拟漏采集）→ FAIL。
        """
        with tempfile.TemporaryDirectory(prefix="android-fidelity-") as temp_name:
            root = Path(temp_name)
            project = root / "project"
            workspace = root / "phase-02-android-inventory"
            layout = project / "app" / "src" / "main" / "res" / "layout"
            source = project / "app" / "src" / "main" / "java" / "demo"
            layout.mkdir(parents=True)
            source.mkdir(parents=True)
            workspace.mkdir()
            (project / "app" / "src" / "main" / "AndroidManifest.xml").write_text(
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="demo">'
                '<application><activity android:name=".LoginActivity"/></application></manifest>',
                encoding="utf-8",
            )
            (layout / "activity_login.xml").write_text(
                '<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android" '
                'android:layout_width="match_parent" android:layout_height="match_parent">'
                '<Button android:id="@+id/plainButton" android:layout_width="match_parent" '
                'android:layout_height="48dp" android:text="plain"/>'
                '<Button android:id="@+id/styledButton" android:layout_width="match_parent" '
                'android:layout_height="48dp" android:text="styled" '
                'android:textColor="#FF0000" android:background="@drawable/bg"/>'
                '</LinearLayout>', encoding="utf-8",
            )
            (source / "LoginActivity.kt").write_text(
                'class LoginActivity : Activity() { fun show() { setContentView(R.layout.activity_login) } }',
                encoding="utf-8",
            )
            (workspace / "phase-manifest.json").write_text(json.dumps({
                "phase": 2, "status": "IN_PROGRESS", "android_project_root": str(project),
                "source_revision": "abc123", "included_features": ["FEATURE-AUTH"],
                "ownership": {"code_map_agent_id": "code-map-agent-1"},
            }), encoding="utf-8")

            analyzer = self._run_analyzer(workspace)
            self.assertEqual(analyzer.returncode, 0, analyzer.stderr)
            package = workspace / "static-analysis"
            components = json.loads(
                (package / "components.json").read_text(encoding="utf-8")
            )["components"]
            by_id = {row["resource_id"]: row for row in components}
            # 1) 显式声明 -> 记录真值（不是 INHERITED 冒充）
            styled = by_id["styledButton"]["fidelity_attrs"]
            self.assertEqual(styled.get("background"), "@drawable/bg")
            self.assertNotIn("style_source", styled)
            # 2) 未显式声明 -> INHERITED 占位（三态第二态）
            self.assertEqual(
                by_id["plainButton"]["fidelity_attrs"], {"style_source": "INHERITED"}
            )
            # 3) INHERITED 占位可过 validator（含未声明控件的包不卡死）
            validator = self._run_validator(workspace)
            self.assertEqual(validator.returncode, 0, validator.stdout + validator.stderr)

            # 4) 完全缺失字段（既无值也无 INHERITED）-> 仍 FAIL
            for row in components:
                row["fidelity_attrs"] = {}
            (package / "components.json").write_text(
                json.dumps({"schema_version": 1, "components": components}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            sys.path.insert(0, str(SKILL / "scripts"))
            try:
                from _common import manifest_lines, sha256_file  # noqa: PLC0415
                names = sorted(
                    p.name for p in package.iterdir()
                    if p.is_file() and p.name not in {"manifest.sha256", "COMMITTED"}
                )
                manifest_path = package / "manifest.sha256"
                manifest_path.chmod(0o644)
                manifest_path.write_text(manifest_lines(package, names), encoding="utf-8")
                committed = package / "COMMITTED"
                committed.chmod(0o644)
                committed.write_text(sha256_file(manifest_path) + "\n", encoding="utf-8")
            finally:
                sys.path.pop(0)
            validator = self._run_validator(workspace)
            self.assertNotEqual(validator.returncode, 0, validator.stdout + validator.stderr)
            self.assertIn("lack fidelity_attrs", validator.stdout)

    def test_nonstandard_compose_page_name_is_not_silently_ignored(self) -> None:
        with tempfile.TemporaryDirectory(prefix="android-static-compose-") as temp_name:
            root = Path(temp_name)
            project = root / "project"
            workspace = root / "phase-02-android-inventory"
            source = project / "app" / "src" / "main" / "java" / "demo"
            source.mkdir(parents=True)
            workspace.mkdir()
            (project / "app" / "src" / "main" / "AndroidManifest.xml").write_text(
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="demo">'
                '<application/></manifest>', encoding="utf-8",
            )
            (source / "Settings.kt").write_text(
                '@Composable\nfun SettingsContent() { Column { Text("Settings") } }\n',
                encoding="utf-8",
            )
            (workspace / "phase-manifest.json").write_text(json.dumps({
                "phase": 2, "status": "IN_PROGRESS", "android_project_root": str(project),
                "source_revision": "abc123", "included_features": ["FEATURE-SETTINGS"],
                "ownership": {"code_map_agent_id": "code-map-agent-1"},
            }), encoding="utf-8")

            analyzer = self._run_analyzer(workspace)
            self.assertEqual(analyzer.returncode, 0, analyzer.stderr)
            # Feature-centric paradigm: suffix-less composable functions are
            # classified as reusable components in the surface index instead of
            # standalone pages -- but they are still DISCOVERED, never silently
            # dropped.
            import csv as _csv
            with open(workspace / "static-analysis" / "surface-index.csv", encoding="utf-8") as handle:
                surfaces = list(_csv.DictReader(handle))
            row = next(item for item in surfaces if item["symbol"] == "SettingsContent")
            self.assertEqual(row["kind"], "reusable-component")


if __name__ == "__main__":
    unittest.main()
