#!/usr/bin/env python3
"""surface_contract.py 单元测试（静态扫描规则、承载证据判定、薄表生成/
校验、Gate 4 消费面）。"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import surface_contract as sc  # noqa: E402

GOOD_HOME = """// native home: Tabs + Navigation
@Entry
@Component
struct Index {
  @State currentIndex: number = 0
  builder navDest() { NavPathStack() }
  build() {
    Navigation() {
      Tabs() {
        TabContent() { Text('home') }
        TabContent() { Text('done') }
      }
      .barPosition(BarPosition.End)
    }
  }
}
"""

# R1 手搓底栏：Row + currentIndex 切换 + 2 onClick，无 Tabs
BAD_BOTTOM_BAR = """
@Component
struct Home {
  @State currentIndex: number = 0
  build() {
    Column() {
      Text('content')
      Row() {
        Text('tab1').onClick(() => { this.currentIndex = 0 })
        Text('tab2').onClick(() => { this.currentIndex = 1 })
      }
    }
  }
}
"""

# R1 反证：同文件使用 Tabs
GOOD_BOTTOM_BAR = """
@Component
struct Home {
  @State currentIndex: number = 0
  build() {
    Tabs() {
      TabContent() { Text('a') }
      TabContent() { Text('b') }
    }.barPosition(BarPosition.End)
  }
}
"""

# R2 自绘导航栈：currentPage 状态 + if(this.) 条件切页
BAD_NAV_STACK = """
@Component
struct Shell {
  @State currentPage: string = 'home'
  build() {
    if (this.currentPage === 'home') { Text('home page') }
    if (this.currentPage === 'detail') { Text('detail page') }
  }
}
"""

# R3 自造弹层：sheetVisible + Stack + 半透明遮罩，无原生弹层 API
BAD_DIALOG = """
@Component
struct Sheet {
  @State sheetVisible: boolean = false
  build() {
    Stack() {
      Text('host')
      if (this.sheetVisible) {
        Column() { Text('panel') }.position({x: 0, y: 300})
          .backgroundColor('#66000000')
      }
    }
  }
}
"""

# R3 反证：bindSheet 原生挂载
GOOD_SHEET = """
@Component
struct Host {
  @State show: boolean = false
  build() {
    Column() { Text('host') }
      .bindSheet($$this.show, this.sheetBuilder())
  }
  builder sheetBuilder() { Text('sheet content') }
}
"""

# R4 自绘开关：isToggled + Circle + animateTo
BAD_SWITCH = """
@Component
struct MySwitch {
  @State isToggled: boolean = false
  build() {
    Row() {
      Circle().width(20)
      Text('toggle').onClick(() => {
        animateTo(() => { this.isToggled = !this.isToggled })
      })
    }
  }
}
"""

# R4 反证：原生 Toggle
GOOD_SWITCH = """
@Component
struct MySwitch {
  build() {
    Toggle({ type: ToggleType.Switch, isOn: false })
  }
}
"""

# R5 自造选择器
BAD_PICKER = """
@Component
struct Wheel {
  build() {
    List() { Text('opt1'); Text('opt2') }
  }
}
// customPicker wheelPicker scrollPicker pickerList markers
"""

# R6 自造返回手势
BAD_BACK = """
@Component
struct Page {
  build() {
    Column() { Text('p') }
      .gesture(PanGesture().onActionEnd(() => { this.edgeBack() }))
  }
}
"""

EXEMPT_FILE = """
// native-exception(R1): 业务要求磁贴式非等宽底栏，Tabs 均分栏宽无法表达
@Component
struct Exempt {
  @State currentIndex: number = 0
  build() {
    Row() {
      Text('a').onClick(() => { this.currentIndex = 0 })
      Text('b').onClick(() => { this.currentIndex = 1 })
    }
  }
}
"""


def src(name: str, content: str) -> dict:
    return {name: content}


class NativeScanTest(unittest.TestCase):
    def assert_rule(self, rule_id, sources, expect):
        scan = sc.scan_native_impl(sources)
        hits = [f for f in scan["findings"] if f["rule"] == rule_id]
        verdicts = {h["level"] for h in hits}
        if expect == "FAIL":
            self.assertIn("FAIL", verdicts,
                          f"{rule_id} expected FAIL, got {scan}")
        elif expect == "PASS":
            self.assertNotIn("FAIL", verdicts,
                             f"{rule_id} expected no FAIL, got {hits}")

    def test_r1_bottom_bar_diy(self):
        self.assert_rule("R1", src("Home.ets", BAD_BOTTOM_BAR), "FAIL")

    def test_r1_native_tabs_passes(self):
        self.assert_rule("R1", src("Home.ets", GOOD_BOTTOM_BAR), "PASS")

    def test_r1_needs_two_clicks(self):
        single = BAD_BOTTOM_BAR.replace(
            "Text('tab2').onClick(() => { this.currentIndex = 1 })",
            "Text('tab2')")
        self.assert_rule("R1", src("Home.ets", single), "PASS")

    def test_r2_nav_stack_diy(self):
        self.assert_rule("R2", src("Shell.ets", BAD_NAV_STACK), "FAIL")

    def test_r2_project_navigation_clears(self):
        self.assert_rule("R2", {"Shell.ets": BAD_NAV_STACK,
                                "Index.ets": GOOD_HOME}, "PASS")

    def test_r3_dialog_diy(self):
        self.assert_rule("R3", src("Sheet.ets", BAD_DIALOG), "FAIL")

    def test_r3_bind_sheet_passes(self):
        self.assert_rule("R3", src("Host.ets", GOOD_SHEET), "PASS")

    def test_r4_switch_diy(self):
        self.assert_rule("R4", src("MySwitch.ets", BAD_SWITCH), "FAIL")

    def test_r4_native_toggle_passes(self):
        self.assert_rule("R4", src("MySwitch.ets", GOOD_SWITCH), "PASS")

    def test_r5_picker_diy(self):
        self.assert_rule("R5", src("Wheel.ets", BAD_PICKER), "FAIL")

    def test_r6_back_diy_no_navigation(self):
        # 工程级无 Navigation → R6 升级 FAIL
        scan = sc.scan_native_impl(src("Page.ets", BAD_BACK))
        r6 = [f for f in scan["findings"] if f["rule"] == "R6"]
        self.assertTrue(any(f["level"] == "FAIL" for f in r6), scan)
        self.assertEqual(scan["verdict"], "FAIL")

    def test_r6_back_diy_with_navigation_warns(self):
        scan = sc.scan_native_impl({"Page.ets": BAD_BACK,
                                    "Index.ets": GOOD_HOME})
        self.assertEqual(scan["verdict"], "PASS")
        self.assertTrue(any(w["rule"] == "R6" for w in scan["warnings"]),
                        scan)

    def test_native_exception_exempted(self):
        scan = sc.scan_native_impl(src("Exempt.ets", EXEMPT_FILE))
        self.assertEqual(scan["verdict"], "PASS")
        self.assertIn("Exempt.ets", scan["exempted"])

    def test_clean_project_passes(self):
        scan = sc.scan_native_impl(src("Index.ets", GOOD_HOME))
        self.assertEqual(scan["verdict"], "PASS")
        self.assertEqual(scan["findings"], [])

    def test_notes_format(self):
        scan = sc.scan_native_impl(src("Home.ets", BAD_BOTTOM_BAR))
        notes = sc.native_notes(scan)
        self.assertIn("R1:Home.ets", notes)


class RegistrationEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.pages = ["pages/shells/ShellPage_TODO"]
        self.sources = {"pages/shells/ShellPage_TODO.ets":
                        "// .id('PAGE-TODO') marker"}

    def test_route_registered_passes(self):
        plan = {"routes": [{"surface_id": "PAGE-TODO", "kind": "page",
                            "shell_file":
                            "entry/src/main/ets/pages/shells/"
                            "ShellPage_TODO.ets"}],
                "modals": [], "passthrough": []}
        evidence = sc.surface_registration_evidence(
            "PAGE-TODO", "page", plan, self.pages, self.sources)
        self.assertEqual(evidence["verdict"], "PASS")
        self.assertIn("main_pages", evidence["detail"])

    def test_modal_mount_passes(self):
        plan = {"routes": [], "modals": [
            {"surface_id": "SHEET-ADD", "kind": "sheet",
             "host_surface_id": "PAGE-TODO"}], "passthrough": []}
        sources = {"pages/Index.ets": "bindSheet($$this.show, ...)"}
        evidence = sc.surface_registration_evidence(
            "SHEET-ADD", "sheet", plan, [], sources)
        self.assertEqual(evidence["verdict"], "PASS")

    def test_modal_unresolved_host_fails(self):
        plan = {"routes": [], "modals": [
            {"surface_id": "SHEET-ADD", "kind": "sheet",
             "host_surface_id": None}], "passthrough": []}
        evidence = sc.surface_registration_evidence(
            "SHEET-ADD", "sheet", plan, [], {"x.ets": "Text('x')"})
        self.assertEqual(evidence["verdict"], "FAIL")

    def test_container_transparent_passes(self):
        evidence = sc.surface_registration_evidence(
            "PAGE-SHELL", "container", None, [], {})
        self.assertEqual(evidence["verdict"], "PASS")
        self.assertEqual(evidence["detail"], "transparent-host")

    def test_no_evidence_fails_closed(self):
        evidence = sc.surface_registration_evidence(
            "PAGE-GHOST", "page", None, [], {"a.ets": "Text('x')"})
        self.assertEqual(evidence["verdict"], "FAIL")

    def test_source_marker_fallback(self):
        sources = {"a.ets": "Navigation() { }.id('PAGE-TODO')"}
        evidence = sc.surface_registration_evidence(
            "PAGE-TODO", "page", None, [], sources)
        self.assertEqual(evidence["verdict"], "PASS")


class NavPatternTest(unittest.TestCase):
    def test_pattern_with_tabs_navigation_evidence(self):
        surfaces = [{"id": "P1", "kind": "page"},
                    {"id": "S1", "kind": "sheet"}]
        pattern = sc.nav_pattern_of(surfaces,
                                    src("i.ets", GOOD_HOME))
        self.assertEqual(pattern, "page+sheet[tabs+navigation]")

    def test_container_no_token(self):
        surfaces = [{"id": "C1", "kind": "container"}]
        self.assertEqual(sc.nav_pattern_of(surfaces, {}), "none")


def make_feature_map(included, features=None):
    return {
        "schema_version": 1,
        "features": features if features is not None else [
            {"feature_id": fid,
             "verify_mode": "SOURCE_CONFIRM" if i == 0 else "RUNTIME",
             "surfaces": surfaces}
            for i, (fid, surfaces) in enumerate(included)
        ],
        "coverage_gate": {
            "included_features_covered": True,
            "included": [fid for fid, _ in included],
            "covered": [fid for fid, _ in included],
            "missing": [],
        },
    }


GOOD_FEATURES = [
    ("FEATURE-NAV-SHELL", [{"id": "PAGE-MAINSCREEN", "kind": "container"}]),
    ("FEATURE-TODO-CREATE", [{"id": "PAGE-MAINSCREEN", "kind": "container"},
                             {"id": "SHEET-ADDTODO", "kind": "sheet"}]),
]
BAD_FEATURES = [
    ("FEATURE-NAV-SHELL", [{"id": "PAGE-MAINSCREEN", "kind": "container"}]),
]


class GenerateCheckTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="surface-contract-")
        self.root = Path(self.temp.name)
        self.project = self.root / "harmony-project"
        ets = self.project / "entry/src/main/ets/pages"
        ets.mkdir(parents=True)
        (ets / "Index.ets").write_text(GOOD_HOME, encoding="utf-8")
        (ets / "modals.ets").write_text(GOOD_SHEET, encoding="utf-8")
        profile = (self.project / "entry/src/main/resources/base/profile")
        profile.mkdir(parents=True)
        (profile / "main_pages.json").write_text(
            json.dumps(["pages/Index"]), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _map(self, features):
        path = self.root / "feature-map.json"
        path.write_text(json.dumps(make_feature_map(features)),
                        encoding="utf-8")
        return path

    def test_generate_good_project(self):
        fmap = self._map(GOOD_FEATURES)
        out = self.root / "surface-contract.csv"
        result = sc.generate_contract(fmap, self.project, out)
        self.assertEqual(len(result["rows"]), 2)
        by_id = {r["feature_id"]: r for r in result["rows"]}
        self.assertEqual(by_id["FEATURE-NAV-SHELL"]["native_impl_check"],
                         "PASS")
        self.assertEqual(by_id["FEATURE-NAV-SHELL"]["entry_reachable"],
                         "PASS")  # container 透明宿主
        self.assertEqual(by_id["FEATURE-TODO-CREATE"]["nav_pattern"],
                         "sheet[tabs+navigation]")  # container 透明不产 token
        # check 子命令通过（Gate 4 消费面）
        self.assertEqual(sc.check_contract(out, fmap), [])
        # CSV 列契约
        with out.open("r", encoding="utf-8", newline="") as stream:
            self.assertEqual(csv.DictReader(stream).fieldnames,
                             sc.SURFACE_CONTRACT_FIELDS)

    def test_generate_bad_native_impl(self):
        ets = self.project / "entry/src/main/ets/pages"
        (ets / "Bad.ets").write_text(BAD_BOTTOM_BAR, encoding="utf-8")
        fmap = self._map(GOOD_FEATURES)
        out = self.root / "surface-contract.csv"
        result = sc.generate_contract(fmap, self.project, out)
        by_id = {r["feature_id"]: r for r in result["rows"]}
        self.assertEqual(by_id["FEATURE-NAV-SHELL"]["native_impl_check"],
                         "FAIL")
        self.assertIn("R1:", by_id["FEATURE-NAV-SHELL"]["notes"])
        errors = sc.check_contract(out, fmap)
        self.assertTrue(any("native_impl_check=FAIL" in e for e in errors))

    def test_generate_unregistered_surface_fails_entry(self):
        features = [("FEATURE-GHOST", [{"id": "PAGE-GHOST",
                                        "kind": "page"}])]
        fmap = self._map(features)
        out = self.root / "surface-contract.csv"
        result = sc.generate_contract(fmap, self.project, out)
        by_id = {r["feature_id"]: r for r in result["rows"]}
        self.assertEqual(by_id["FEATURE-GHOST"]["entry_reachable"], "FAIL")
        errors = sc.check_contract(out, fmap)
        self.assertTrue(any("entry_reachable=FAIL" in e for e in errors))

    def test_check_detects_missing_and_extra_rows(self):
        fmap = self._map(GOOD_FEATURES)
        out = self.root / "surface-contract.csv"
        sc.generate_contract(fmap, self.project, out)
        # 只留一行 → 另一 included feature 缺行
        rows = sc.read_csv(out)
        sc.write_csv(out, sc.SURFACE_CONTRACT_FIELDS, rows[:1])
        errors = sc.check_contract(out, fmap)
        self.assertTrue(any("missing row" in e for e in errors))

    def test_check_bad_enum(self):
        fmap = self._map(GOOD_FEATURES)
        out = self.root / "surface-contract.csv"
        sc.generate_contract(fmap, self.project, out)
        rows = sc.read_csv(out)
        rows[0]["native_impl_check"] = "MAYBE"
        sc.write_csv(out, sc.SURFACE_CONTRACT_FIELDS, rows)
        errors = sc.check_contract(out, fmap)
        self.assertTrue(any("bad native_impl_check" in e for e in errors))

    def test_cli_generate_and_check(self):
        fmap = self._map(GOOD_FEATURES)
        out = self.root / "surface-contract.csv"
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "surface_contract.py"),
             "generate", "--feature-map", str(fmap),
             "--project", str(self.project), "--out", str(out)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["native_impl_check"], "PASS")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "surface_contract.py"),
             "check", "--contract", str(out), "--feature-map", str(fmap)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()