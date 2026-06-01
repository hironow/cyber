#!/usr/bin/env python3
"""Scan the skills collection for referenced CLI commands and report which are
missing from the current environment.

The skills under ``.agents/skills`` invoke many external CLI tools. This tool
extracts two high-signal sources from every ``SKILL.md`` and ``references/*.md``:

1. Declared install targets  -- lines like ``apt install X`` / ``pip install X``
   / ``brew install X`` / ``go install ...`` (what a skill says it needs).
2. Command invocations        -- the leading command token inside fenced
   ``bash``/``sh`` code blocks (what a skill actually runs).

Each candidate is then checked against ``$PATH`` with ``shutil.which`` and
reported as installed or missing.

Usage::

    python3 tools/scan_missing_cli.py                 # human-readable report
    python3 tools/scan_missing_cli.py --json          # machine-readable
    python3 tools/scan_missing_cli.py --skills DIR     # custom skills path
    python3 tools/scan_missing_cli.py --min-skills 2   # drop single-skill noise

Zero third-party dependencies; runs on any Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

# --- repo layout -----------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKILLS = REPO_ROOT / ".agents" / "skills"

# --- noise filters ---------------------------------------------------------
# English prose / pseudo-output words that slip into fenced blocks, plus shell
# builtins and ubiquitous coreutils we never want to flag as "missing".
STOPWORDS: frozenset[str] = frozenset(
    """
or and then from on with to the a an of in for is are be this that these those
y x z v v2 v3 install installed download build binary built library compiler
benchmark checks cis kali linux android ios windows macos requirements package
packages tool tools module modules dependencies deps medallion github gitlab com
http https www true false none null name value data file files dir acquisition
automated analysis detection report card key user host target output input
example note step steps total risk critical high medium low suspicious incident
evidence threat attack process logs log rule alert assessment timestamp unique
recommended compliance remediation hunt import eof pyeof phase post pull clone
new no active extracted access scan network cloud vulnerability credential
authentication lateral initial end event avg average containment client except
server email policy description where first affected action start mitre memory
account extract developer domain deployment failed review priority capture
computer ransomware vendor filter document fields compose findings recovery
timeline order interface results query content actions iocs beacon microsoft
writer match image week persistence role iam classification service password
full session admin mfa search result deny parse normal block sla connection
quality firewall common show use credentials estimated investigation next tier
known allow registry application root device reg get run def all base before
business check conditional current identity encryption unauthorized class
return print self async await lambda yield raise assert global
""".split()
)

# Helper scripts bundled inside every skill -- not external CLI tools.
SELF_SCRIPTS: frozenset[str] = frozenset({"agent.py", "process.py"})

SHELL_BUILTINS: frozenset[str] = frozenset(
    """
cd echo for if fi then else elif do done while case esac function return exit set
unset export local read shift eval exec source trap true false test let declare
readonly printf break continue in select until time command sudo env nohup xargs
watch sleep wait kill ls cat grep egrep fgrep awk sed cut sort uniq head tail tr
wc tee find xxd od cp mv rm mkdir rmdir touch chmod chown ln pwd basename dirname
realpath which type man ps top df du free uname whoami id date tar gzip gunzip zip
unzip bzip2 cmp diff more less vi vim nano tput clear yes seq expr bc mktemp stat
file strings hexdump
""".split()
)

# Command wrappers: when a line starts with one of these, the real command is
# the following token (skipping flags).
WRAPPERS: frozenset[str] = frozenset(
    """
sudo env time nohup command uv python python3 bun bunx npx pnpm pip pip3 poetry go
cargo docker git brew nice stdbuf
""".split()
)

_FENCE_RE = re.compile(r"```([^\n]*)\n(.*?)```", re.DOTALL)
_ALLOWED_INFO = {"", "bash", "sh", "shell", "console", "zsh", "shellsession", "bash-session"}
_INSTALL_HEAD = re.compile(
    r"^(?:sudo\s+)?(?:apt-get|apt|yum|dnf|zypper|pacman|apk|brew|snap|port)\b"
    r"|^(?:sudo\s+)?pip3?\s+install"
    r"|^(?:sudo\s+)?uv\s+(?:pip|tool)\s+install"
    r"|^(?:sudo\s+)?gem\s+install"
    r"|^(?:sudo\s+)?go\s+install"
    r"|^(?:sudo\s+)?cargo\s+install"
    r"|^(?:sudo\s+)?npm\s+install\s+-g"
    r"|^(?:sudo\s+)?(?:bun|pnpm)\s+(?:add|install)"
)
_CMD_RE = re.compile(r"^[a-z][a-z0-9_.+-]*$")
_CONNECTORS = {"or", "and", "from", "then", "to", "with", "&&", "||", "|", ";", ">", "2>", "#"}


def _norm_pkg(token: str) -> str:
    token = token.strip("\"'`")
    if "/" in token:  # go install path -> last segment before @version
        token = token.split("@")[0].rstrip("/").split("/")[-1]
    return re.split(r"[<>=~\[@]", token)[0].lower()


def _parse_install(line: str, skill: str, declared: dict[str, set[str]]) -> None:
    parts = re.sub(r"^sudo\s+", "", line).split()
    try:
        kw = next(i for i, p in enumerate(parts) if p in ("install", "add", "-S"))
    except StopIteration:
        return
    for p in parts[kw + 1:]:
        if p in _CONNECTORS:
            break
        if p.startswith("-") or "=" in p or "$" in p:
            continue
        pkg = _norm_pkg(p)
        if len(pkg) >= 2 and pkg not in STOPWORDS and _CMD_RE.match(pkg):
            declared[pkg].add(skill)


def _parse_invocations(content: str, skill: str, invoked: dict[str, set[str]]) -> None:
    for match in _FENCE_RE.finditer(content):
        if match.group(1).strip().lower() not in _ALLOWED_INFO:
            continue
        for raw in match.group(2).splitlines():
            line = re.sub(r"^[$>]\s+", "", raw.strip())
            if not line or line.startswith("#"):
                continue
            tokens = line.split()
            idx = 0
            while idx < len(tokens):
                tok = tokens[idx]
                if "=" in tok and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
                    idx += 1
                    continue
                if tok in WRAPPERS:
                    idx += 1
                    while idx < len(tokens) and tokens[idx].startswith("-"):
                        idx += 1
                    continue
                break
            if idx >= len(tokens):
                continue
            cmd = tokens[idx].lower()
            if (
                _CMD_RE.match(cmd)
                and cmd not in SHELL_BUILTINS
                and cmd not in STOPWORDS
                and cmd not in SELF_SCRIPTS
            ):
                invoked[cmd].add(skill)


def scan(skills_dir: Path) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return (declared, invoked) maps of command -> set of skill names."""
    declared: dict[str, set[str]] = defaultdict(set)
    invoked: dict[str, set[str]] = defaultdict(set)
    files = list(skills_dir.glob("*/SKILL.md")) + list(skills_dir.glob("*/references/*.md"))
    for path in files:
        skill = path.parent.name if path.name == "SKILL.md" else path.parent.parent.name
        content = path.read_text(errors="replace")
        _parse_invocations(content, skill, invoked)
        for raw in content.splitlines():
            line = raw.strip().lstrip("$> ").strip()
            if _INSTALL_HEAD.search(line):
                _parse_install(line, skill, declared)
    return declared, invoked


def build_report(
    declared: dict[str, set[str]], invoked: dict[str, set[str]], min_skills: int
) -> dict[str, object]:
    tools = set(declared) | set(invoked)
    installed: list[dict[str, object]] = []
    missing: list[dict[str, object]] = []
    for tool in sorted(tools):
        skills = declared.get(tool, set()) | invoked.get(tool, set())
        is_declared = tool in declared
        # confidence: declared install target, or invoked across several skills
        if not (is_declared or len(skills) >= min_skills):
            continue
        rec = {
            "tool": tool,
            "skills": len(skills),
            "declared": is_declared,
            "invoked": tool in invoked,
        }
        (installed if shutil.which(tool) else missing).append(rec)
    installed.sort(key=lambda r: (-r["skills"], r["tool"]))  # type: ignore[index,operator]
    missing.sort(key=lambda r: (-r["skills"], r["tool"]))  # type: ignore[index,operator]
    return {"installed": installed, "missing": missing}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skills", type=Path, default=DEFAULT_SKILLS, help="skills directory")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--min-skills", type=int, default=2, help="min skill count for invoked-only tools")
    parser.add_argument("--installed", action="store_true", help="also list installed tools")
    args = parser.parse_args(argv)

    if not args.skills.is_dir():
        print(f"error: skills dir not found: {args.skills}", file=sys.stderr)
        return 2

    declared, invoked = scan(args.skills)
    report = build_report(declared, invoked, args.min_skills)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    missing = report["missing"]
    installed = report["installed"]
    print(f"skills dir : {args.skills}")
    print(f"candidates : {len(missing) + len(installed)}  "  # type: ignore[arg-type]
          f"(missing {len(missing)}, installed {len(installed)})\n")  # type: ignore[arg-type]
    print("MISSING (referenced by skills, not on PATH)")
    print(f"{'tool':32} {'skills':>6}  src")
    for rec in missing:  # type: ignore[union-attr]
        src = ("D" if rec["declared"] else "-") + ("I" if rec["invoked"] else "-")
        print(f"{rec['tool']:32} {rec['skills']:>6}  {src}")
    if args.installed:
        print("\nINSTALLED")
        for rec in installed:  # type: ignore[union-attr]
            print(f"  {rec['tool']:32} {rec['skills']:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
