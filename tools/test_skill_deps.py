"""Offline contract tests for the skill dependency manifest/tooling.

Run: python3 -m unittest discover -s tools -p 'test_skill_deps.py'
No network access and no host mutation: the installer is exercised against mock
runners inside a temporary HOME and temporary PATH.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import report_skill_deps as report  # noqa: E402

SCRIPT = TOOLS / "install_skill_deps.sh"
MANIFEST = TOOLS / "skill-deps.json"
DOC = REPO / "docs" / "skill-deps.md"

MOCK_RUNNERS = ("brew", "pipx", "npm", "gem", "cargo", "go", "uv")


def write_mock_runner(directory: Path, name: str) -> None:
    """A runner that logs its invocation and materialises the mapped binary."""
    path = directory / name
    path.write_text(
        "#!/bin/sh\n"
        'if [ -n "$MOCK_EAT_STDIN" ]; then cat > /dev/null; fi\n'
        'printf "%s %s sdkroot=%s toolbin=%s\\n" "$0" "$*" "${SDKROOT:-}" "${UV_TOOL_BIN_DIR:-}" >> "$MOCK_LOG"\n'
        'if [ -n "$MOCK_FAIL_ON" ]; then\n'
        '  case "$*" in\n'
        '    *"$MOCK_FAIL_ON"*) echo "mock failure for: $*" >&2; exit 4 ;;\n'
        "  esac\n"
        "fi\n"
        'pkg=""\n'
        'for arg in "$@"; do case "$arg" in -*) ;; *) pkg="$arg" ;; esac; done\n'
        'if [ -f "$MOCK_MAP" ]; then\n'
        '  while read -r p b; do\n'
        '    if [ "$p" = "$pkg" ]; then : > "$MOCK_BIN/$b"; chmod +x "$MOCK_BIN/$b"; fi\n'
        "  done < \"$MOCK_MAP\"\n"
        "fi\n"
        "exit 0\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.doc = report.load_manifest(MANIFEST)

    def test_manifest_is_valid(self):
        self.assertEqual(report.validate(self.doc), [])

    def test_statuses_and_categories_are_known(self):
        for name, entry in self.doc["entries"].items():
            with self.subTest(entry=name):
                self.assertIn(entry["status"], report.VALID_STATUS)
                self.assertIn(entry["category"], report.VALID_CATEGORIES)

    def test_installable_entries_have_canonical_checks(self):
        for name, entry in self.doc["entries"].items():
            if entry["status"] in report.INSTALL_STATUS:
                with self.subTest(entry=name):
                    self.assertTrue(entry["check"], "installable entry needs check binaries")
                    self.assertTrue(all(isinstance(c, str) and c for c in entry["check"]))
                    if entry["status"] == "auto":
                        self.assertIsNotNone(entry["method"])
                        self.assertIsNotNone(entry["package"])

    def test_link_entries_define_shims(self):
        for name, entry in self.doc["entries"].items():
            if entry["status"] == "link":
                with self.subTest(entry=name):
                    self.assertTrue(entry["links"])
                    for link in entry["links"]:
                        self.assertTrue(link["name"])
                        self.assertTrue(link["fromGlob"])

    def test_alias_targets_exist(self):
        entries = self.doc["entries"]
        for name, entry in entries.items():
            if entry["status"] == "alias":
                with self.subTest(entry=name):
                    if entry["via"]:
                        self.assertIn(entry["via"], entries)
                    else:
                        self.assertTrue(entry["check"], "alias without via must be verifiable")

    def test_referenced_skills_exist(self):
        for name, entry in self.doc["entries"].items():
            for skill in entry["skills"]:
                with self.subTest(entry=name, skill=skill):
                    self.assertTrue((REPO / ".agents" / "skills" / skill / "SKILL.md").is_file())

    def test_opt_in_categories_are_not_default(self):
        opt_in = set(self.doc["categories"]["optIn"])
        for name, entry in self.doc["entries"].items():
            if entry["category"] in opt_in:
                with self.subTest(entry=name):
                    self.assertFalse(entry["defaultApply"])


class DocsTest(unittest.TestCase):
    def test_generated_doc_is_up_to_date(self):
        doc = report.load_manifest(MANIFEST)
        generated = report.markdown(doc)
        self.assertTrue(DOC.is_file(), "docs/skill-deps.md is missing; run --markdown")
        self.assertEqual(DOC.read_text(encoding="utf-8"), generated,
                         "docs/skill-deps.md is stale; run: python3 tools/report_skill_deps.py --markdown")

    def test_generated_doc_is_environment_independent(self):
        doc = report.load_manifest(MANIFEST)
        self.assertEqual(report.markdown(doc), report.markdown(doc))


class ReportCheckTest(unittest.TestCase):
    def _fixture(self, tmp: Path, checks: list[str]) -> Path:
        doc = {
            "version": 1,
            "categories": {"userSelected": ["net"], "optIn": [], "unsupported": [], "notATool": [], "notProvisioned": []},
            "entries": {
                "alpha": {"category": "net", "status": "auto", "method": "brew", "package": "alphapkg",
                          "check": checks, "links": [], "via": None, "defaultApply": True, "version": None,
                          "license": None, "packageVerified": True, "note": None,
                          "skills": sorted(p.name for p in (REPO / ".agents" / "skills").glob("*"))[:1],
                          "evidence": "declared"},
            },
        }
        path = tmp / "fixture.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def _run(self, argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return report.main(argv)

    def test_check_fails_while_entry_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = self._fixture(Path(d), ["definitely-not-installed-bin"])
            self.assertEqual(self._run(["--manifest", str(manifest), "--check"]), 1)

    def test_check_passes_when_present(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = self._fixture(Path(d), ["sh"])
            self.assertEqual(self._run(["--manifest", str(manifest), "--check"]), 0)

    def test_invalid_manifest_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.json"
            path.write_text(json.dumps({"version": 1, "entries": {"x": {"status": "nonsense"}}}), encoding="utf-8")
            self.assertEqual(self._run(["--manifest", str(path)]), 2)


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        (self.repo / "tools").mkdir(parents=True)
        shutil.copy(SCRIPT, self.repo / "tools" / SCRIPT.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        # base utilities the installer needs, without exposing host package managers
        self.base = self.root / "base"
        self.base.mkdir()
        for util in ("sh", "grep", "cut", "sort", "tr", "sed", "mktemp", "dirname",
                     "mkdir", "ln", "rm", "ls", "cat", "chmod", "env", "xcrun"):
            for candidate in (Path("/bin") / util, Path("/usr/bin") / util):
                if candidate.exists():
                    (self.base / util).symlink_to(candidate)
                    break
        (self.base / "python3").symlink_to(sys.executable)
        for runner in MOCK_RUNNERS:
            write_mock_runner(self.bin, runner)
        self.home = self.root / "home"
        (self.home / ".local" / "bin").mkdir(parents=True)
        self.log = self.root / "invocations.log"
        self.map = self.root / "map"
        self.map.write_text("alphapkg alpha-bin\nbetapkg beta-bin\ndeltapkg delta-bin\nzetapkg zeta-bin\n"
                            "iotapkg iota-bin\nuvpkg uv-bin\n", encoding="utf-8")
        # beta-bin already installed -> installer must skip it
        present = self.bin / "beta-bin"
        present.write_text("#!/bin/sh\n")
        present.chmod(0o755)
        # gamma shim source (already installed tool, wrong name)
        real = self.home / ".local" / "bin" / "gammareal"
        real.write_text("#!/bin/sh\n")
        real.chmod(0o755)
        self.manifest = {
            "version": 1,
            "categories": {"userSelected": ["net"], "optIn": ["devsec"], "unsupported": [], "notATool": [], "notProvisioned": []},
            "entries": {
                "alpha": self._entry("alpha", "auto", "brew", "alphapkg", ["alpha-bin"], default=True),
                "beta": self._entry("beta", "auto", "brew", "betapkg", ["beta-bin"], default=True),
                "gamma": self._entry("gamma", "link", None, None, ["gamma-bin"], default=True,
                                     links=[{"name": "gamma-bin", "fromGlob": "$HOME/.local/bin/gammareal",
                                             "reason": "test shim"}]),
                "delta": self._entry("delta", "auto", "brew", "deltapkg", ["delta-bin"], default=False,
                                     category="devsec"),
                "epsilon": self._entry("epsilon", "manual", None, None, [], default=False),
                "iota": self._entry("iota", "auto", "pipx", "iotapkg", ["iota-bin"], default=True,
                                    interpreter=sys.executable),
                "lambda": self._entry("lambda", "auto", "uv", "uvpkg", ["uv-bin"], default=True,
                                      interpreter=sys.executable),
            },
        }
        self.write_manifest()

    def _entry(self, name, status, method, package, checks, default, links=None, category="net",
               interpreter=None):
        return {
            "category": category, "status": status, "method": method, "package": package,
            "python": interpreter,
            "check": checks, "links": links or [], "via": None, "defaultApply": default,
            "version": None, "license": None, "packageVerified": True,
            "note": None, "evidence": "declared", "skills": [],
        }

    def write_manifest(self):
        (self.repo / "tools" / "skill-deps.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def run_script(self, *args, extra_env=None):
        env = dict(os.environ)
        env.update({
            # isolated PATH: mocks + the interpreter dir + base utilities only, so a
            # missing runner cannot be masked by a real one on the host PATH
            # ~/.local/bin is where shims land and is expected to be on PATH (as on the host)
            "PATH": f"{self.bin}:{self.home / '.local' / 'bin'}:{self.base}",
            "HOME": str(self.home),
            "MOCK_LOG": str(self.log),
            "MOCK_BIN": str(self.bin),
            "MOCK_MAP": str(self.map),
            "MOCK_FAIL_ON": (extra_env or {}).get("MOCK_FAIL_ON", ""),
            "MOCK_EAT_STDIN": (extra_env or {}).get("MOCK_EAT_STDIN", ""),
        })
        import subprocess
        return subprocess.run(["sh", str(self.repo / "tools" / SCRIPT.name), *args],
                              capture_output=True, text=True, env=env, cwd=str(self.repo))

    def invocations(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_dry_run_installs_nothing(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry-run", result.stdout)
        self.assertIn("WOULD", result.stdout)
        self.assertEqual(self.invocations(), [])

    def test_apply_installs_only_missing_and_creates_shim(self):
        result = self.run_script("--apply")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        log = " ".join(self.invocations())
        self.assertIn("alphapkg", log)
        self.assertNotIn("betapkg", log)          # already present -> skipped
        self.assertNotIn("deltapkg", log)          # opt-in category excluded by default
        self.assertTrue((self.bin / "alpha-bin").exists())
        shim = self.home / ".local" / "bin" / "gamma-bin"
        self.assertTrue(shim.is_symlink())
        self.assertEqual(os.readlink(shim), str(self.home / ".local" / "bin" / "gammareal"))

    def test_apply_is_idempotent(self):
        self.assertEqual(self.run_script("--apply").returncode, 0)
        first = len(self.invocations())
        self.assertEqual(self.run_script("--apply").returncode, 0)
        self.assertEqual(len(self.invocations()), first, "second run must not reinstall")

    def test_category_selection_controls_opt_in(self):
        result = self.run_script("--apply", "--category", "devsec")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        log = " ".join(self.invocations())
        self.assertIn("deltapkg", log)
        self.assertNotIn("alphapkg", log)

    def test_only_selection(self):
        result = self.run_script("--apply", "--only", "alpha")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        log = " ".join(self.invocations())
        self.assertIn("alphapkg", log)
        self.assertNotIn("betapkg", log)

    def test_failure_is_fail_closed(self):
        result = self.run_script("--apply", extra_env={"MOCK_FAIL_ON": "alphapkg"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stderr)
        self.assertIn("summary:", result.stdout)

    def test_keep_going_continues_after_failure(self):
        result = self.run_script("--apply", "--keep-going", extra_env={"MOCK_FAIL_ON": "alphapkg"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stderr)
        # it must continue past the failure and still create the shim
        self.assertTrue((self.home / ".local" / "bin" / "gamma-bin").is_symlink())

    def test_missing_runner_fails_before_mutation(self):
        for runner in ("gem", "cargo"):
            (self.bin / runner).unlink()
        self.manifest["entries"]["zeta"] = self._entry("zeta", "auto", "gem", "zetapkg", ["zeta-bin"], default=True)
        self.write_manifest()
        result = self.run_script("--apply")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("MISSING RUNNERS", result.stderr)
        self.assertEqual(self.invocations(), [], "no install may run when a runner is missing")

    def test_plan_is_not_consumed_by_installer_stdin(self):
        """Regression: a runner reading stdin must not swallow the remaining plan entries."""
        result = self.run_script("--apply", "--all", extra_env={"MOCK_EAT_STDIN": "1"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        log = " ".join(self.invocations())
        self.assertIn("alphapkg", log, "first entry processed")
        self.assertIn("deltapkg", log, "entry after the stdin-eating runner must still run")
        self.assertTrue((self.home / ".local" / "bin" / "gamma-bin").is_symlink(),
                        "link phase must still run after all installs")

    def test_pinned_interpreter_is_passed_to_pipx(self):
        result = self.run_script("--apply", "--only", "iota")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn(f"--python {sys.executable}", " ".join(self.invocations()))

    def test_uv_method_installs_into_local_bin(self):
        result = self.run_script("--apply", "--only", "lambda")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        log = " ".join(self.invocations())
        self.assertIn("tool install", log)
        self.assertIn(f"toolbin={self.home / '.local' / 'bin'}", log)
        self.assertTrue((self.bin / "uv-bin").exists())

    @unittest.skipUnless(shutil.which("xcrun"), "xcrun not available")
    def test_sdkroot_is_exported_for_builds(self):
        result = self.run_script("--apply", "--only", "alpha")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        line = next(l for l in self.invocations() if "alphapkg" in l)
        self.assertRegex(line, r"sdkroot=/\S+")

    def test_missing_interpreter_is_unresolved(self):
        self.manifest["entries"]["kappa"] = self._entry(
            "kappa", "auto", "pipx", "iotapkg", ["iota-bin"], default=True,
            interpreter="/nonexistent/python3.13")
        self.write_manifest()
        result = self.run_script("--apply", "--only", "kappa")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("python:/nonexistent/python3.13", result.stderr)

    def test_report_only_skips_installs(self):
        result = self.run_script("--report-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.invocations(), [])


if __name__ == "__main__":
    unittest.main()
