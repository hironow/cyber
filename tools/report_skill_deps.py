#!/usr/bin/env python3
"""Report and verify skill dependency coverage for this repository.

Reads tools/skill-deps.json (manifest of every tool the skills reference but that
was not installed when the manifest was built) and compares it against the current
environment via shutil.which().

Usage:
    python3 tools/report_skill_deps.py                  # human readable summary
    python3 tools/report_skill_deps.py --check          # exit 1 while a default auto entry is missing
    python3 tools/report_skill_deps.py --check --all    # include opt-in categories (devsec)
    python3 tools/report_skill_deps.py --json
    python3 tools/report_skill_deps.py --markdown       # regenerate docs/skill-deps.md
    python3 tools/report_skill_deps.py --verify-upstream  # network: re-verify package existence/version

Exit codes: 0 = ok, 1 = --check failure, 2 = manifest invalid.
"""

from __future__ import annotations

import argparse

import json

import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO / "tools" / "skill-deps.json"
DEFAULT_DOC = REPO / "docs" / "skill-deps.md"
SKILLS_DIR = REPO / ".agents" / "skills"

VALID_STATUS = {"auto", "link", "alias", "manual", "unsupported", "out_of_scope", "noise"}
VALID_CATEGORIES = {"net", "mobile_re", "dfir", "stego", "cloud_ab", "web3", "devsec", "pylib", "linux", "windows", "noise"}
VALID_METHODS = {"brew", "brew-cask", "pipx", "uv", "npm", "gem", "cargo", "go", "docker", "none", None}
INSTALL_STATUS = {"auto", "link"}


# --------------------------------------------------------------------------- io
def load_manifest(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def validate(doc: dict) -> list[str]:
    problems: list[str] = []
    entries = doc.get("entries")
    if not isinstance(entries, dict) or not entries:
        return ["manifest carries no entries"]
    names = set(entries)
    for name, e in sorted(entries.items()):
        where = f"entries[{name}]"
        if e.get("status") not in VALID_STATUS:
            problems.append(f"{where}: bad status {e.get('status')!r}")
        if e.get("category") not in VALID_CATEGORIES:
            problems.append(f"{where}: bad category {e.get('category')!r}")
        if e.get("method") not in VALID_METHODS:
            problems.append(f"{where}: bad method {e.get('method')!r}")
        if e.get("status") in INSTALL_STATUS:
            if not e.get("check"):
                problems.append(f"{where}: installable entry without a check binary")
            if e["status"] == "auto" and not e.get("package"):
                problems.append(f"{where}: auto entry without a package")
            if e["status"] == "link" and not e.get("links"):
                problems.append(f"{where}: link entry without a link definition")
        if e["status"] == "alias" and not e.get("via") and not e.get("check"):
            problems.append(f"{where}: alias without via and without check binary")
        if e.get("via") and e["via"] not in names:
            problems.append(f"{where}: via target {e['via']!r} is not an entry")
        for link in e.get("links") or []:
            if not link.get("name") or not link.get("fromGlob"):
                problems.append(f"{where}: link entry needs name and fromGlob")
        for skill in e.get("skills") or []:
            if not (SKILLS_DIR / skill / "SKILL.md").is_file():
                problems.append(f"{where}: skill {skill!r} does not exist")
        if e.get("evidence") not in ("declared", "invoked"):
            problems.append(f"{where}: bad evidence {e.get('evidence')!r}")
    return problems


# ------------------------------------------------------------------- resolution
def resolve(entry: dict) -> dict:
    """Resolve the canonical check binaries of an entry against the current PATH."""
    found = {}
    for binary in entry.get("check") or []:
        found[binary] = shutil.which(binary)
    interpreter = entry.get("python")
    if interpreter and not Path(interpreter).is_file():
        found[f"python:{interpreter}"] = None
    return {
        "check": found,
        "ok": bool(found) and all(found.values()),
        "missing": sorted(b for b, p in found.items() if not p),
    }


def evaluate(doc: dict, include_opt_in: bool) -> dict:
    entries = doc["entries"]
    resolved: dict[str, dict] = {}
    for name, e in entries.items():
        if e["status"] in INSTALL_STATUS and (e.get("defaultApply") or include_opt_in):
            resolved[name] = resolve(e)
    # alias entries inherit the state of their canonical entry; alias entries without
    # a canonical entry are verified against their own check binaries (already-installed tools)
    for name, e in entries.items():
        if e["status"] != "alias":
            continue
        if e.get("via") in entries:
            target = entries[e["via"]]
            if target["status"] in INSTALL_STATUS:
                resolved[name] = resolve(target)
        elif e.get("check"):
            resolved[name] = resolve(e)

    def bucket(entry: dict, name: str) -> str:
        if entry["status"] in INSTALL_STATUS:
            return "resolved" if resolved.get(name, {}).get("ok") else (
                "pending" if (entry.get("defaultApply") or include_opt_in) else "opt-in")
        if entry["status"] == "alias":
            state = resolved.get(name)
            if state is None:
                return "alias-n/a"
            return "alias-resolved" if state["ok"] else "alias-pending"
        return "excluded"

    declared = {n: e for n, e in entries.items() if e["evidence"] == "declared"}
    counts: dict[str, int] = {}
    for name, e in entries.items():
        counts[bucket(e, name)] = counts.get(bucket(e, name), 0) + 1
    declared_counts: dict[str, int] = {}
    for name, e in declared.items():
        declared_counts[bucket(e, name)] = declared_counts.get(bucket(e, name), 0) + 1

    per_category: dict[str, dict[str, int]] = {}
    for name, e in entries.items():
        if e["status"] not in INSTALL_STATUS:
            continue
        row = per_category.setdefault(e["category"], {"resolved": 0, "pending": 0, "opt-in": 0, "total": 0})
        row["total"] += 1
        state = bucket(e, name)
        row[{"resolved": "resolved", "pending": "pending", "opt-in": "opt-in"}.get(state, "pending")] += 1

    return {
        "resolved": resolved,
        "bucket_of": {n: bucket(e, n) for n, e in entries.items()},
        "counts": counts,
        "declared_counts": declared_counts,
        "declared_total": len(declared),
        "per_category": per_category,
    }


# --------------------------------------------------------------------- upstream
def _http_json(url: str):
    try:
        with urllib.request.urlopen(url, timeout=30) as fh:  # noqa: S310 - fixed https hosts
            return json.load(fh)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def verify_upstream(doc: dict) -> list[str]:
    problems = []
    for name, e in sorted(doc["entries"].items()):
        method, package = e.get("method"), e.get("package")
        if not package:
            continue
        if method == "brew":
            data = _http_json(f"https://formulae.brew.sh/api/formula/{package.split('/')[-1]}.json")
        elif method == "brew-cask":
            data = _http_json(f"https://formulae.brew.sh/api/cask/{package}.json")
        elif method == "pipx":
            data = _http_json(f"https://pypi.org/pypi/{package}/json")
        elif method == "npm":
            data = _http_json(f"https://registry.npmjs.org/{package.replace('/', '%2F')}")
        elif method == "gem":
            data = _http_json(f"https://rubygems.org/api/v1/gems/{package}.json")
        else:
            continue
        if data is None:
            problems.append(f"{name}: {method}:{package} not resolvable upstream")
            continue
        latest = None
        if method == "brew":
            latest = data.get("versions", {}).get("stable")
        elif method == "brew-cask":
            latest = data.get("version")
        elif method == "pipx":
            latest = data.get("info", {}).get("version")
        elif method == "npm":
            latest = data.get("dist-tags", {}).get("latest")
        elif method == "gem":
            latest = data.get("version")
        if latest and e.get("version") and latest != e["version"]:
            problems.append(f"{name}: version drift (manifest {e['version']} -> upstream {latest})")
    return problems


# ---------------------------------------------------------------------- output
def human(doc: dict, ev: dict) -> str:
    entries = doc["entries"]
    lines = []
    pending = sorted(n for n, b in ev["bucket_of"].items() if b == "pending")
    auto_total = sum(1 for e in entries.values() if e["status"] in INSTALL_STATUS)
    lines.append(f"manifest     : {len(entries)} entries ({auto_total} installable)")
    lines.append(f"resolved     : {ev['counts'].get('resolved', 0)}")
    lines.append(f"pending      : {len(pending)}")
    lines.append(f"opt-in       : {ev['counts'].get('opt-in', 0)} (devsec: apply with --category devsec)")
    lines.append(f"excluded     : {ev['counts'].get('excluded', 0)} (manual / unsupported / out_of_scope / noise)")
    lines.append(f"alias        : resolved={ev['counts'].get('alias-resolved', 0)} "
                 f"pending={ev['counts'].get('alias-pending', 0)} n/a={ev['counts'].get('alias-n/a', 0)}")
    lines.append("")
    lines.append(f"declared-evidence entries: {ev['declared_total']} "
                 f"({', '.join(f'{k}={v}' for k, v in sorted(ev['declared_counts'].items()))})")
    lines.append("")
    lines.append("category      resolved / total   (opt-in)")
    for cat in sorted(ev["per_category"]):
        r = ev["per_category"][cat]
        lines.append(f"  {cat:<12} {r['resolved']:>2} / {r['total']:<3}  opt-in={r['opt-in']}")
    if pending:
        lines.append("")
        lines.append("PENDING INSTALL")
        for name in pending:
            e = entries[name]
            how = "link-shim" if e["status"] == "link" else f"{e['method']}:{e['package']}"
            lines.append(f"  {name:<24} {how}  "
                         f"missing={','.join(ev['resolved'].get(name, {}).get('missing', []))}")
    return "\n".join(lines) + "\n"


def markdown(doc: dict) -> str:
    entries = doc["entries"]
    cats = doc.get("categories", {})
    out = []
    out.append("<!-- generated by tools/report_skill_deps.py --markdown ; do not edit by hand -->")
    out.append("")
    out.append("# スキル依存ツールの整備状況")
    out.append("")
    out.append("このファイルは `tools/skill-deps.json`（スキルが参照する未導入ツールの分類）と、")
    out.append("実行環境の `PATH` を突き合わせた結果から生成されます。")
    out.append("")
    out.append("```sh")
    out.append("python3 tools/report_skill_deps.py              # 現状サマリ")
    out.append("python3 tools/report_skill_deps.py --check      # auto 区分の未導入があれば exit 1")
    out.append("sh tools/install_skill_deps.sh                  # dry-run（既定）")
    out.append("sh tools/install_skill_deps.sh --apply          # 実際に導入")
    out.append("```")
    out.append("")
    out.append("## サマリ")
    out.append("")
    out.append("| 区分 | 件数 | 意味 |")
    out.append("|---|---|---|")
    out.append(f"| auto | {sum(1 for e in entries.values() if e['status'] == 'auto')} | 無償・CLI・macOS 対応。導入対象 |")
    out.append(f"| link | {sum(1 for e in entries.values() if e['status'] == 'link')} | 既存ツールに CLI 名のシムを張って満たす |")
    out.append(f"| alias | {sum(1 for e in entries.values() if e['status'] == 'alias')} | 別エントリが同一実体を提供 |")
    out.append(f"| manual | {sum(1 for e in entries.values() if e['status'] == 'manual')} | 無償だが手動（理由は下表） |")
    out.append(f"| unsupported | {sum(1 for e in entries.values() if e['status'] == 'unsupported')} | その OS では不可。代替手順を記載 |")
    out.append(f"| out_of_scope | {sum(1 for e in entries.values() if e['status'] == 'out_of_scope')} | 言語パッケージ（スキル内 venv で導入する想定） |")
    out.append(f"| noise | {sum(1 for e in entries.values() if e['status'] == 'noise')} | ツール名ではない抽出ノイズ |")
    out.append("")
    out.append("> 実行環境での現在の解決状況（resolved / pending）は `python3 tools/report_skill_deps.py` または")
    out.append("> `--check` で確認します。この文書は環境に依存しない内容だけを記載します。")
    out.append("")
    out.append("既定の導入カテゴリ: " + ", ".join(f"`{c}`" for c in cats.get("userSelected", [])) +
               "。opt-in: " + ", ".join(f"`{c}`" for c in cats.get("optIn", [])) + "（`--category devsec` で明示指定）")
    out.append("")
    out.append("## カテゴリ別の導入対象件数")
    out.append("")
    out.append("| category | installable | うち既定導入 | opt-in | 備考 |")
    out.append("|---|---|---|---|---|")
    for cat in sorted({e["category"] for e in entries.values()}):
        rows = [e for e in entries.values() if e["category"] == cat]
        inst = [e for e in rows if e["status"] in INSTALL_STATUS]
        dflt = [e for e in inst if e.get("defaultApply")]
        note = ""
        if cat in cats.get("optIn", []):
            note = "opt-in（--category devsec）"
        elif cat in cats.get("unsupported", []):
            note = "代替手順を記載"
        elif cat in cats.get("notProvisioned", []):
            note = "常設導入しない"
        out.append(f"| {cat} | {len(inst)} | {len(dflt)} | {len(inst) - len(dflt)} | {note} |")
    out.append("")

    def table(names, cols, row):
        out.append("| " + " | ".join(cols) + " |")
        out.append("|" + "---|" * len(cols))
        for name in names:
            out.append("| " + " | ".join(row(name)) + " |")
        out.append("")

    installable = sorted((n for n, e in entries.items() if e["status"] in INSTALL_STATUS),
                         key=lambda n: (entries[n]["category"], n))
    out.append("## 導入対象（auto / link）")
    out.append("")
    table(installable,
          ["tool", "category", "method", "install target", "check", "interpreter", "status", "既定", "version", "license", "skills"],
          lambda n: [
              f"`{n}`", entries[n]["category"], entries[n]["method"] or "-",
              f"`{entries[n]['package']}`", ", ".join(f"`{c}`" for c in entries[n]["check"]),
              f"`{entries[n]['python']}`" if entries[n].get("python") else "-",
              "auto" if entries[n]["status"] == "auto" else "link",
              "yes" if entries[n].get("defaultApply") else "opt-in",
              entries[n].get("version") or "-", entries[n].get("license") or "-",
              str(len(entries[n]["skills"])),
          ])
    links = sorted(n for n, e in entries.items() if e.get("links"))
    if links:
        out.append("### PATH シム（link / `links` を持つエントリ）")
        out.append("")
        table(links, ["tool", "link name", "実体", "理由"],
              lambda n: [f"`{n}`", ", ".join(f"`{l['name']}`" for l in entries[n]["links"]),
                         ", ".join(f"`{l['fromGlob']}`" for l in entries[n]["links"]),
                         entries[n]["links"][0].get("reason", "-")])
    manual = sorted((n for n, e in entries.items() if e["status"] == "manual"), key=lambda n: (entries[n]["category"], n))
    out.append("## 手動導入（manual・自動導入の対象外）")
    out.append("")
    table(manual, ["tool", "category", "理由 / 手段"], lambda n: [f"`{n}`", entries[n]["category"], entries[n].get("note") or "-"])
    unsupported = sorted((n for n, e in entries.items() if e["status"] == "unsupported"), key=lambda n: (entries[n]["category"], n))
    out.append("## macOS では不可（unsupported）と代替手順")
    out.append("")
    table(unsupported, ["tool", "platform", "代替手順"],
          lambda n: [f"`{n}`", entries[n]["category"], entries[n].get("alternative") or entries[n].get("note") or "-"])
    aliases = sorted((n for n, e in entries.items() if e["status"] == "alias"), key=lambda n: (entries[n]["category"], n))
    out.append("## 別ツールが提供（alias）")
    out.append("")
    table(aliases, ["参照名", "提供元エントリ", "理由"],
          lambda n: [f"`{n}`", f"`{entries[n].get('via') or '-'}`", entries[n].get("note") or "-"])
    pylib = sorted(n for n, e in entries.items() if e["status"] == "out_of_scope")
    out.append("## 対象外: 言語パッケージ（out_of_scope）")
    out.append("")
    out.append("スキル本文の手順の中で venv / pip により導入される想定のため、環境への常設導入は行いません。")
    out.append("")
    out.append(", ".join(f"`{n}`" for n in pylib))
    out.append("")
    noise = sorted(n for n, e in entries.items() if e["status"] == "noise")
    out.append("## 抽出ノイズ（noise）")
    out.append("")
    out.append(", ".join(f"`{n}`" for n in noise))
    out.append("")
    out.append("## 運用")
    out.append("")
    out.append("- 冪等判定は `check`（スキルが実際に呼ぶ canonical バイナリ）で行います。`provides` は説明用です。")
    out.append("- `--check` は既定カテゴリの auto/link が未解決なら exit 1。`--all` で opt-in も検査します。")
    out.append("- 導入は `status=auto|link` かつ `defaultApply=true`（既定カテゴリ）が対象。`--all` または `--category devsec` で opt-in を追加。")
    out.append("- バージョンは生成時点の上流最新を記録（`version`）。導入は最新を取得するため、`--verify-upstream` で差分を確認してください。")
    out.append("- ロールバック: `brew uninstall <pkg>` / `pipx uninstall <pkg>` / `npm uninstall -g <pkg>` / "
               "`gem uninstall <pkg>` / `cargo uninstall <pkg>` / `rm ~/.local/bin/<shim>`")
    out.append("- 再生成: `python3 tools/report_skill_deps.py --markdown`（`tools/test_skill_deps.py` が一致を検査）")
    out.append("")
    out.append("### 容量（導入時に増えるキャッシュ）")
    out.append("")
    out.append("この整備で導入すると、次のキャッシュが数 GB〜数十 GB まで膨らむことがあります。")
    out.append("いずれも再取得可能で、削除しても導入手順の再実行で復旧します（実測例: 合計 51 GiB を回収）。")
    out.append("")
    out.append("| キャッシュ | 削除コマンド |")
    out.append("|---|---|")
    out.append("| uv（pipx の入背後。最大） | `uv cache clean` |")
    out.append("| Homebrew のダウンロード/旧版 | `brew cleanup -s --prune=all` |")
    out.append("| npx の一時パッケージ | `rm -rf ~/.npm/_npx ~/.npm/_cacache` |")
    out.append("| cargo のレジストリ展開 | `rm -rf ~/.cargo/registry/{cache,src}` |")
    out.append("")
    out.append("導入済みの実体（`~/.local/pipx/venvs`、brew の Cellar）は削除しないでください。")
    out.append("")
    return "\n".join(out)


# ------------------------------------------------------------------------ main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--markdown", nargs="?", const=str(DEFAULT_DOC), default=None,
                        help="write the generated doc (default docs/skill-deps.md)")
    parser.add_argument("--check", action="store_true", help="exit 1 when a default auto entry is unresolved")
    parser.add_argument("--all", action="store_true", help="include opt-in categories (devsec)")
    parser.add_argument("--verify-upstream", action="store_true", help="network: re-verify packages and versions")
    args = parser.parse_args(argv)

    doc = load_manifest(args.manifest)
    problems = validate(doc)
    if problems:
        for p in problems:
            print(f"manifest error: {p}", file=sys.stderr)
        return 2
    ev = evaluate(doc, args.all)

    if args.markdown is not None:
        Path(args.markdown).write_text(markdown(doc), encoding="utf-8")
        print(f"wrote {args.markdown}")
    if args.json:
        print(json.dumps({
            "counts": ev["counts"],
            "declared": {"total": ev["declared_total"], "counts": ev["declared_counts"]},
            "perCategory": ev["per_category"],
            "pending": sorted(n for n, b in ev["bucket_of"].items() if b == "pending"),
            "resolved": {n: e["ok"] for n, e in ev["resolved"].items()},
        }, indent=2, sort_keys=True))
    elif args.markdown is None:
        sys.stdout.write(human(doc, ev))

    if args.verify_upstream:
        drift = verify_upstream(doc)
        if drift:
            print("upstream drift:", file=sys.stderr)
            for d in drift:
                print(f"  {d}", file=sys.stderr)
        else:
            print("upstream: all recorded packages resolve (versions match)")

    if args.check:
        pending = sorted(n for n, b in ev["bucket_of"].items() if b == "pending")
        if pending:
            print(f"UNRESOLVED ({len(pending)}): {', '.join(pending)}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
