# Intent

**Last updated:** 2026-06-10
**Requester:** hironow
**Status:** DRAFT — AI が README / git 履歴から起草。requester 未確認
**Work unit:** cyber — vendored agent-skills collection (cybersecurity-focused)

## Goal

Maintain a local collection of 786 agent skills — mostly cybersecurity skills —
vendored under `.agents/skills/`, exposed to multiple agent runtimes via symlink
mirrors (`.claude/skills/`, `.pi/skills/`), with per-skill provenance and content
hashes pinned in `skills-lock.json`.

## Success Criteria

- 未定義 — Open Questions 参照

## Scope

### In scope

- Vendoring skills from upstream repos, per `skills-lock.json`:
  mukul975/Anthropic-Cybersecurity-Skills (754), google/skills (30),
  arcjet/skills (1), GoogleChrome/modern-web-guidance (1)
- Symlink mirrors so `.claude/skills/` and `.pi/skills/` resolve the same
  canonical skill set under `.agents/skills/`
- `tools/scan_missing_cli.py` — reporting external CLIs that the skills
  reference but that are not installed locally

### Out of scope (Non-goals)

- 未確認 (ルート README.md が空のため、明示的な non-goals は不明)

## Constraints

- `tools/scan_missing_cli.py` is zero-dependency and requires Python 3.10+
  (per `tools/README.md`)

## Open Questions

- [ ] requester による本ドラフトのレビュー
- [ ] リポジトリの正式な目的・ゴール (ルート README.md が空のため未確認)
- [ ] 成功基準 (テスト / CI / 完了条件がリポジトリに存在しない)
- [ ] skills の同期ポリシー (どの上流をいつ同期するか。履歴上は 2026-05-08 /
      06-02 / 06-08 に同期コミットあり)
- [ ] `skills-lock.json` と symlink ミラーを生成・検証するツールの所在
      (リポジトリ内に同期スクリプトは見当たらない)
- [ ] `.pi/skills/` が対象とするエージェントランタイムの正体
