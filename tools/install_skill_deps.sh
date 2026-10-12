#!/bin/sh
# Install the skill dependencies recorded in tools/skill-deps.json.
#
# Defaults to DRY-RUN: nothing is installed unless --apply is given.
# Idempotency is decided per entry by its canonical `check` binaries (all of them),
# never by "any binary of the package exists". Fail-closed: the first failing
# command stops the run unless --keep-going is given. No sudo is used.
#
# Usage:
#   sh tools/install_skill_deps.sh                     # dry-run, default categories
#   sh tools/install_skill_deps.sh --apply             # install (default categories)
#   sh tools/install_skill_deps.sh --apply --all       # include opt-in (devsec)
#   sh tools/install_skill_deps.sh --category net,dfir # only these categories
#   sh tools/install_skill_deps.sh --only tshark,zeek  # only these entries
#   sh tools/install_skill_deps.sh --no-links          # skip PATH shims
#   sh tools/install_skill_deps.sh --keep-going        # continue after a failure
#   sh tools/install_skill_deps.sh --report-only       # dependency runner preflight only
#   sh tools/install_skill_deps.sh --retry 2           # retry each failing command

set -eu

# Keep the host stable: never auto-update existing formulae, never clean up mid-run.
export HOMEBREW_NO_AUTO_UPDATE=1
export HOMEBREW_NO_INSTALL_CLEANUP=1
export PIP_DISABLE_PIP_VERSION_CHECK=1
# macOS: C 拡張のビルドは SDK ヘッダを必要とする（未設定だと 'stdlib.h not found'）
if command -v xcrun >/dev/null 2>&1; then
  _sdkroot=$(xcrun --show-sdk-path 2>/dev/null || true)
  if [ -n "${_sdkroot:-}" ] && [ -d "$_sdkroot" ]; then export SDKROOT="$_sdkroot"; fi
fi

APPLY=0
ALL=0
LINKS=1
KEEP_GOING=0
REPORT_ONLY=0
RETRY=0
CATEGORIES=""
ONLY=""

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --all) ALL=1 ;;
    --no-links) LINKS=0 ;;
    --keep-going) KEEP_GOING=1 ;;
    --report-only) REPORT_ONLY=1 ;;
    --category) shift; CATEGORIES="${1:-}" ;;
    --category=*) CATEGORIES="${1#--category=}" ;;
    --only) shift; ONLY="${1:-}" ;;
    --only=*) ONLY="${1#--only=}" ;;
    --retry) shift; RETRY="${1:-0}" ;;
    --retry=*) RETRY="${1#--retry=}" ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(dirname -- "$SCRIPT_DIR")
MANIFEST="$SCRIPT_DIR/skill-deps.json"
BIN_DIR="${HOME}/.local/bin"

if [ ! -f "$MANIFEST" ]; then
  echo "manifest not found: $MANIFEST" >&2
  exit 2
fi
command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 2; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT INT TERM
PLAN="$WORK/plan.tsv"
LINKS_PLAN="$WORK/links.tsv"

# ---------------------------------------------------------------------------
# Plan: python3 decides what is applicable, sh decides what is already present.
# ---------------------------------------------------------------------------
python3 - "$MANIFEST" "$CATEGORIES" "$ONLY" "$ALL" > "$PLAN" <<'PY'
import json, sys
manifest, categories_arg, only_arg, all_arg = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
doc = json.load(open(manifest, encoding="utf-8"))
entries = doc["entries"]
user_cats = doc.get("categories", {}).get("userSelected", [])
cats = set(c for c in categories_arg.split(",") if c) if categories_arg else set(user_cats)
if all_arg == "1" and not categories_arg:
    cats = set(user_cats) | set(doc.get("categories", {}).get("optIn", []))
only = set(t for t in only_arg.split(",") if t)
for name, e in sorted(entries.items()):
    if e["status"] not in ("auto", "link"):
        continue
    if only and name not in only:
        continue
    if not only and e["category"] not in cats:
        continue
    if e["status"] == "auto":
        checks = ",".join(e.get("check") or [])
        print("INSTALL\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (
            name, e.get("method") or "none", e.get("package") or "-", checks,
            "1" if e.get("defaultApply") else "0", e["category"], e.get("python") or "-"))
    for link in e.get("links") or []:
        print("LINK\t%s\t%s\t%s\t%s" % (name, link["name"], link["fromGlob"], link.get("altGlob") or "-"))
PY

if [ ! -s "$PLAN" ]; then
  echo "no entries selected (check --category / --only)" >&2
  exit 0
fi

grep '^LINK' "$PLAN" > "$LINKS_PLAN" || true

# ---------------------------------------------------------------------------
# Preflight: every runner needed by the plan must exist (fail before mutating).
# ---------------------------------------------------------------------------
MISSING_RUNNERS=""
NEEDED=""
while IFS="$(printf '\t')" read -r kind name method package checks default category interpreter <&3; do
  [ "$kind" = "INSTALL" ] || continue
  case "$method" in
    brew|brew-cask) NEEDED="$NEEDED brew" ;;
    pipx) NEEDED="$NEEDED pipx" ;;
    npm) NEEDED="$NEEDED npm" ;;
    gem) NEEDED="$NEEDED gem" ;;
    cargo) NEEDED="$NEEDED cargo" ;;
    uv) NEEDED="$NEEDED uv" ;;
    go) NEEDED="$NEEDED go" ;;
    none|-) ;;
    *) echo "unsupported method in manifest: $method ($name)" >&2; exit 2 ;;
  esac
done 3< "$PLAN"
for runner in $(printf '%s\n' $NEEDED | sort -u); do
  command -v "$runner" >/dev/null 2>&1 || MISSING_RUNNERS="$MISSING_RUNNERS $runner"
done

echo "manifest   : $MANIFEST"
echo "mode       : $([ "$APPLY" = 1 ] && echo APPLY || echo 'dry-run (use --apply)')"
echo "categories : ${CATEGORIES:-$(python3 -c "import json,sys;print(','.join(json.load(open(sys.argv[1]))['categories']['userSelected']))" "$MANIFEST")}"
echo "runners    :$(printf '%s\n' $NEEDED | sort -u | tr '\n' ' ')"
if [ -n "$MISSING_RUNNERS" ]; then
  echo "MISSING RUNNERS:$MISSING_RUNNERS" >&2
  exit 3
fi
[ "$REPORT_ONLY" = 1 ] && exit 0

# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------
HOOK=0
SKIPPED=0
INSTALLED=0
FAILED=0
UNRESOLVED=0

all_checks_present() {
  # $1 = comma separated check list; returns 0 when every binary resolves
  _ok=1
  for _b in $(printf '%s' "$1" | tr ',' ' '); do
    command -v "$_b" >/dev/null 2>&1 || _ok=0
  done
  [ "$_ok" = 1 ]
}

run_cmd() {
  # $1 = description, rest = command
  # stdin is /dev/null: installers must never consume the plan that the caller reads.
  _desc=$1; shift
  _n=0
  while :; do
    if "$@" < /dev/null; then return 0; fi
    _n=$((_n + 1))
    [ "$_n" -gt "$RETRY" ] && return 1
    echo "  retry $_n/$RETRY: $_desc"
  done
}

while IFS="$(printf '\t')" read -r kind name method package checks default category interpreter <&3; do
  [ "$kind" = "INSTALL" ] || continue
  if all_checks_present "$checks"; then
    echo "SKIP    $name ($category) already present: $checks"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi
  case "$method" in
    brew)      CMD="brew install $package" ;;
    brew-cask) CMD="brew install --cask $package" ;;
    pipx)      if [ "$interpreter" != "-" ]; then CMD="pipx install --python $interpreter $package"; else CMD="pipx install $package"; fi ;;
    npm)       CMD="npm install -g $package" ;;
    gem)       CMD="gem install $package" ;;
    cargo)     CMD="cargo install $package" ;;
    uv)        if [ "$interpreter" != "-" ]; then CMD="env UV_TOOL_BIN_DIR=$BIN_DIR uv tool install --python $interpreter $package"; else CMD="env UV_TOOL_BIN_DIR=$BIN_DIR uv tool install $package"; fi ;;
    go)        CMD="env GOBIN=$BIN_DIR go install $package@latest" ;;
    *)         CMD="" ;;
  esac
  if [ "$APPLY" != 1 ]; then
    echo "WOULD   $name ($category): $CMD   [needs: $checks]"
    continue
  fi
  echo "INSTALL $name ($category): $CMD"
  set -- $CMD
  if run_cmd "$CMD" "$@"; then
    if all_checks_present "$checks"; then
      INSTALLED=$((INSTALLED + 1))
    else
      echo "  WARN: $name installed but checks still missing: $checks (re-checked after the link phase)" >&2
    fi
  else
    FAILED=$((FAILED + 1))
    echo "  FAILED: $CMD" >&2
    [ "$KEEP_GOING" = 1 ] || break
  fi
done 3< "$PLAN"

# ---------------------------------------------------------------------------
# PATH shims: create the names the skills actually call in ~/.local/bin.
# ---------------------------------------------------------------------------
if [ -s "$LINKS_PLAN" ]; then
  case ":${PATH}:" in
    *":$BIN_DIR:"*) ;;
    *) echo "WARN    $BIN_DIR is not on PATH: created shims will not resolve in this shell" >&2 ;;
  esac
  while IFS="$(printf '\t')" read -r kind tool linkname fromglob altglob <&3; do
    [ "$kind" = "LINK" ] || continue
    if command -v "$linkname" >/dev/null 2>&1; then
      echo "SKIP    link $linkname (already resolvable)"
      continue
    fi
    src=""
    for pattern in $fromglob $altglob; do
      [ "$pattern" = "-" ] && continue
      pattern=$(printf '%s' "$pattern" | sed "s|\\\$HOME|$HOME|g")
      for candidate in $pattern; do
        if [ -x "$candidate" ]; then src=$candidate; break; fi
      done
      [ -n "$src" ] && break
    done
    if [ -z "$src" ]; then
      echo "WARN    link $linkname: source not found ($fromglob)" >&2
      continue
    fi
    if [ "$APPLY" != 1 ]; then
      echo "WOULD   link $linkname -> $src"
      continue
    fi
    mkdir -p "$BIN_DIR"
    ln -sf "$src" "$BIN_DIR/$linkname"
    echo "LINK    $linkname -> $src"
  done 3< "$LINKS_PLAN"
fi

# ---------------------------------------------------------------------------
# Final verification, after installs AND shims: an entry counts as resolved only
# when every canonical check binary (and any shim name) actually resolves.
# ---------------------------------------------------------------------------
if [ "$APPLY" = 1 ]; then
  UNRESOLVED=0
  while IFS="$(printf '\t')" read -r kind name method package checks default category interpreter <&3; do
    [ "$kind" = "INSTALL" ] || continue
    _bad=""
    all_checks_present "$checks" || _bad="$checks"
    if [ "$interpreter" != "-" ] && [ ! -x "$interpreter" ]; then
      _bad="$_bad python:$interpreter"
    fi
    if [ -n "$_bad" ]; then
      echo "  UNRESOLVED $name (needs:$_bad)" >&2
      UNRESOLVED=$((UNRESOLVED + 1))
    fi
  done 3< "$PLAN"
  while IFS="$(printf '\t')" read -r kind tool linkname fromglob altglob <&3; do
    [ "$kind" = "LINK" ] || continue
    if ! command -v "$linkname" >/dev/null 2>&1; then
      echo "  UNRESOLVED shim $linkname" >&2
      UNRESOLVED=$((UNRESOLVED + 1))
    fi
  done 3< "$LINKS_PLAN"
fi

echo
echo "summary: installed=$INSTALLED skipped=$SKIPPED failed=$FAILED unresolved=$UNRESOLVED"
if [ "$APPLY" != 1 ]; then
  echo "(dry-run) re-run with --apply to install"
  exit 0
fi
if [ "$FAILED" -gt 0 ] || [ "$UNRESOLVED" -gt 0 ]; then
  echo "verification: python3 tools/report_skill_deps.py --check" >&2
  exit 1
fi
exit 0
