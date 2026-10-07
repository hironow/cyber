"""Offline contract tests for the project-only skills update wrapper."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("update-skills.sh")
NAMES = ("gcloud", "google-cloud-recipe-auth", "google-cloud-recipe-onboarding")


class UpdateSkillsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        tools = self.root / "tools"
        tools.mkdir()
        (tools / SCRIPT.name).write_bytes(SCRIPT.read_bytes())
        self.log = self.root / "invocations"
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        mock = bin_dir / "bunx"
        mock.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$MOCK_LOG"\n'
            'if [ "${FAIL_ADD:-}" = 1 ] && [ "$2" = add ]; then exit 4; fi\n'
        )
        mock.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", MOCK_LOG=str(self.log))
        for name in NAMES:
            skill = self.root / ".agents" / "skills" / name / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(f"---\nname: {name}\n---\n")
        self.lock = {
            "version": 1,
            "skills": {
                name: {
                    "source": "google/skills",
                    "skillPath": f"skills/cloud/{name}/SKILL.md",
                    "computedHash": "dummy",
                }
                for name in NAMES
            },
        }
        self.write_lock()

    def write_lock(self):
        (self.root / "skills-lock.json").write_text(json.dumps(self.lock))

    def run_script(self, **env):
        return subprocess.run(
            ["sh", str(self.root / "tools" / SCRIPT.name)],
            cwd="/",
            env=dict(self.env, **env),
            capture_output=True,
            text=True,
        )

    def test_updates_only_project_and_three_explicit_paths(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.log.read_text().splitlines(),
            ["skills update -p -y"] + [
                f"skills add google/skills/skills/cloud/{name} --skill {name} -y"
                for name in NAMES
            ],
        )

    def test_refuses_changed_source_before_running_cli(self):
        self.lock["skills"]["gcloud"]["source"] = "someone/else"
        self.write_lock()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected lock entry", result.stderr)
        self.assertFalse(self.log.exists())

    def test_add_failure_stops_before_other_skills(self):
        result = self.run_script(FAIL_ADD="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.log.read_text().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
