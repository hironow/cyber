#!/bin/sh
# Update project skills, including the three google/skills names duplicated upstream.
set -eu

repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo"

check_lock() {
    python3 - "$repo" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
lock = json.loads((root / "skills-lock.json").read_text())
for name in ("gcloud", "google-cloud-recipe-auth", "google-cloud-recipe-onboarding"):
    entry = lock["skills"].get(name, {})
    expected_path = f"skills/cloud/{name}/SKILL.md"
    if entry.get("source") != "google/skills" or entry.get("skillPath") != expected_path:
        sys.exit(f"Unexpected lock entry for {name}; refusing to update from another source")
    if not (root / ".agents" / "skills" / name / "SKILL.md").is_file():
        sys.exit(f"Missing installed skill: {name}")
PY
}

check_lock
bunx skills update -p -y

# skills CLI 1.7.1 skips these even when the locked path still exists:
# google/skills also publishes copies under plugins/cloud/google-cloud-developer/skills/.
# An explicit directory URL selects the recorded source path without ambiguity.
for name in gcloud google-cloud-recipe-auth google-cloud-recipe-onboarding; do
    bunx skills add "google/skills/skills/cloud/$name" --skill "$name" -y
    printf 'Updated project skill: %s\n' "$name"
done
check_lock
