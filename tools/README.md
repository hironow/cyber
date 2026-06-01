# tools/

Utility tools for this skills collection.

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
