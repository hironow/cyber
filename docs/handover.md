# Handover

**Last updated:** 2026-06-10 (JST)
**Updated by:** claude (AI draft from git history — review before trusting)

## Current State

A vendored agent-skills collection: 786 skills live under `.agents/skills/`,
with `.claude/skills/` and `.pi/skills/` as symlink mirrors into it. Per-skill
provenance (source repo, path, content hash) is pinned in `skills-lock.json`;
sources are mukul975/Anthropic-Cybersecurity-Skills (754), google/skills (30),
arcjet/skills (1), and GoogleChrome/modern-web-guidance (1).
`tools/scan_missing_cli.py` reports which external CLIs the skills reference
but are not installed in the current environment. The root README.md is empty.
Last meaningful commit: `11bf5f4 add skills` (2026-06-08).

## In Progress

不明 (git 履歴からは判別できず)

## Next Actions

1. requester による docs/intent.md ドラフトのレビューと確定
2. Fill in the empty root README.md (purpose, sync workflow)

## Known Risks / Blockers

- No sync script is committed; how `skills-lock.json` and the symlink mirrors
  are regenerated is undocumented
- Skill content is vendored from third-party repos; correctness and updates
  depend on those upstreams

## Context the Next Actor Needs

- `.claude/skills/` and `.pi/skills/` are symlinks into `.agents/skills/` —
  edit skills only under `.agents/skills/`
- `skills-lock.json` records `source`, `sourceType`, `skillPath`, and a
  `computedHash` per skill
- There is no justfile, test suite, or CI in this repo

## Relevant Files and Commands

- `.agents/skills/` — canonical skill directories (SKILL.md + references/)
- `skills-lock.json` — provenance and content-hash pin per skill
- `tools/scan_missing_cli.py` — `python3 tools/scan_missing_cli.py`
  (flags: `--min-skills`, `--installed`, `--json`, `--skills`)
- `tools/README.md` — usage and caveats for the scanner
