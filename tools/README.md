# tools/

Utility tools for this skills collection.

## report_skill_deps.py / install_skill_deps.sh / skill-deps.json

`skill-deps.json` is the manifest of every tool the skills reference but that was not
installed when the manifest was built. Each entry records:

| field | meaning |
|---|---|
| `category` | `net` / `mobile_re` / `dfir` / `stego` / `cloud_ab` / `web3` (default) / `devsec` (opt-in) / `pylib` / `linux` / `windows` / `noise` |
| `status` | `auto` (installable) / `link` (PATH shim) / `alias` (another entry provides it) / `manual` / `unsupported` / `out_of_scope` / `noise` |
| `method` + `package` | install route: brew, brew-cask, pipx, uv, npm, gem, cargo, go |
| `check` | **canonical binaries the skills actually invoke**; all of them must resolve for the entry to count as satisfied |
| `links` | PATH shims created in `~/.local/bin` (e.g. `impacket-psexec` -> `psexec.py`, `zsteg` from the gem dir) |
| `python` | optional interpreter for `pipx install --python` — used when upstream has no wheel for the default 3.14 (`plaso`/`mythril`/`pymalleablec2`/`theHarvester` pin `/opt/homebrew/bin/python3.13`) |
| `via` | for aliases: the canonical entry that provides the same binaries |
| `defaultApply` | `false` for opt-in categories (currently `devsec`) |
| `version` / `license` | upstream values captured when the manifest was generated |
| `skills` | the skills that reference the tool (evidence) |

The manifest was generated from `scan_missing_cli.py` (declared install targets plus
command-shaped invocations) and each package was verified against the upstream
registries (formulae.brew.sh, PyPI, npm, RubyGems) at generation time.

```bash
python3 tools/report_skill_deps.py                 # summary (resolved / pending per category)
python3 tools/report_skill_deps.py --json          # machine readable
python3 tools/report_skill_deps.py --check         # exit 1 while a default entry is missing
python3 tools/report_skill_deps.py --check --all   # include opt-in categories
python3 tools/report_skill_deps.py --markdown      # regenerate docs/skill-deps.md
python3 tools/report_skill_deps.py --verify-upstream  # network: re-check packages + versions

sh tools/install_skill_deps.sh                     # dry-run (default; installs nothing)
sh tools/install_skill_deps.sh --apply             # install default categories
sh tools/install_skill_deps.sh --apply --all       # include devsec
sh tools/install_skill_deps.sh --category net,dfir # subset by category
sh tools/install_skill_deps.sh --only tshark,zeek  # subset by entry
sh tools/install_skill_deps.sh --no-links          # skip PATH shims
sh tools/install_skill_deps.sh --keep-going        # continue after a failure
sh tools/install_skill_deps.sh --report-only       # runner preflight only
```

Behavior notes:

- Dry-run is the default; nothing is mutated without `--apply`.
- Idempotency uses `check` (all binaries), never "the package looks installed".
- Fail-closed: the first failing install stops the run (`--keep-going` overrides).
- No `sudo` is used. `gem` installs go to the Homebrew Ruby gem dir (user-owned) and
  are shimmed into `~/.local/bin`; `go install` uses `GOBIN=$HOME/.local/bin`;
  `uv` uses `UV_TOOL_BIN_DIR=$HOME/.local/bin`.
- `SDKROOT` is exported from `xcrun --show-sdk-path` before builds: without it, C
  extensions such as `ckzg` fail with `'stdlib.h' file not found` on macOS.
- `pipx` 1.17.12 removes the venv for packages whose `Requires-Python` is empty
  (`theHarvester`) or that expose no console script; `uv tool install` is the documented
  alternative route (`method: uv`).
- All method runners are preflighted before the first mutation; a missing runner aborts
  with exit code 3.
- Versions are recorded for reference but installs are not pinned (upstream moves);
  use `--verify-upstream` to detect drift.
- Offline contract tests: `python3 -m unittest discover -s tools -p 'test_skill_deps.py'`

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
