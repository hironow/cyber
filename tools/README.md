# tools/

Utility tools for this skills collection.

## update-skills.sh

From this repository, run `sh tools/update-skills.sh` to update **project** skills.
It runs `bunx skills update -p -y`, then reinstalls `gcloud`,
`google-cloud-recipe-auth`, and `google-cloud-recipe-onboarding` from their
explicit `google/skills/skills/cloud/` directories. In skills CLI 1.7.1,
`update` skips these names because upstream also publishes same-named copies
under `plugins/cloud/google-cloud-developer/skills/`, even though the recorded
paths still exist. The CLI warning remains, but this wrapper closes the update
gap without changing global skills or manually editing lock hashes. It stops if
the lock's source/path changes or an install fails. Review and commit the
resulting diff after each update.

Offline wrapper checks: `python3 -m unittest discover -s tools -p 'test_update_skills.py'`.
The lasting fix belongs in the CLI: prefer a still-existing locked path when
the installer can target that exact path, while preserving fail-closed behavior
for sources that cannot (tracked upstream in
[vercel-labs/skills#2231](https://github.com/vercel-labs/skills/pull/2231)).

## scan_missing_cli.py

Scans every `SKILL.md` and `references/*.md` under `.agents/skills/`, extracts the
external CLI commands the skills reference, and reports which ones are **not
installed** in the current environment.

Two signals are extracted and merged:

- **Declared install targets** — `apt/brew/pip/go/gem/cargo/npm install …` lines
  (marked `D` in the `src` column). High precision.
- **Command invocations** — the leading command token inside fenced
  `bash`/`sh` blocks (marked `I`). Higher recall, more prose noise.

Availability is decided with `shutil.which` against the current `$PATH`.

### Usage

```bash
# Human-readable report (invoked-only tools need >= 2 skills to show)
python3 tools/scan_missing_cli.py

# Stricter signal: only tools referenced by >= 3 skills
python3 tools/scan_missing_cli.py --min-skills 3

# Also list what IS installed
python3 tools/scan_missing_cli.py --installed

# Machine-readable
python3 tools/scan_missing_cli.py --json

# Point at a different skills directory
python3 tools/scan_missing_cli.py --skills /path/to/skills
```

Zero third-party dependencies; requires Python 3.10+.

### Caveats

Extraction is heuristic. The `D` (declared) column is the trustworthy signal;
`I`-only rows with low skill counts can include prose that looks like a command.
Python/Node *libraries* installed via `pip`/`npm` (e.g. `impacket`, `scapy`,
`pymisp`, `stix2`) also appear — these are packages, not standalone binaries.
OS-specific commands (`systemctl`, `iptables`, PowerShell cmdlets) show as
missing on macOS by design.
