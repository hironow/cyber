# スキル依存ツールの整備（計画）

対象リポジトリ: `/Users/nino/cyber`（スキル配布リポジトリ、`.agents/skills/` に 789 スキル）
作成日: 2026-10-12 / 状態: **独立レビュー反映済み・実装完了**（§14 に対応表）

## 1. 目的と完了条件

`tools/scan_missing_cli.py` が示す「スキルが参照するが環境に無いツール」を、**再現可能な形でリポジトリに整備し、このマシンにも適用**する。

完了条件:
1. 未導入ツールの分類が `tools/skill-deps.json` に記録されている（無償・CLI・macOS 対応のものは機械可読な導入定義、それ以外は理由つき）。
2. `tools/install_skill_deps.sh --apply` で未導入分が冪等に導入できる（既定は dry-run）。
3. `tools/report_skill_deps.py --check` が「auto 区分の未導入残」を検出して非 0 終了する。
4. `python3 -m unittest discover -s tools -p 'test_skill_deps.py'` が通る。
5. 実適用後、`report_skill_deps.py` と `scan_missing_cli.py` の before/after 数値をレポートし、`docs/skill-deps.md` が実測と一致する。

## 2. スコープ（ユーザー回答の反映）

| 決定 | 内容 |
|---|---|
| 成果物 | リポジトリ整備 **＋** このマシンへの実行 |
| 対象カテゴリ | ネットワーク深部 / モバイル・RE / DFIR 追加 / ステガノ / クラウド・検証AB / スマートコントラクト / Linux 専用の代替手順文書化 |
| 除外方針 | 有償・アカウント必須・巨大・Windows 専用は**除外して理由を明記** |

非スコープ（今回やらない）:
- **言語パッケージ 60 件**（`requests` / `boto3` / `scapy` / `impacket` 等のライブラリ）。ユーザーがカテゴリとして選んでいないため、`out_of_scope` として記録し、`docs/skill-deps.md` に「スキル内 venv で導入する想定」と明記する。
- 上流スキルの更新（`tools/update-skills.sh` の領分）。
- スキル本体（`.agents/skills/**`）の改変。
- Linux 専用ツールの実導入（代替手順の文書化まで）。

## 3. 現状の証拠（before）

```
$ python3 tools/scan_missing_cli.py
skills dir : /Users/nino/cyber/.agents/skills
candidates : 965  (missing 835, installed 130)
```

- 宣言ベース（D 列＝高精度）の未導入ツール: **173**
- 未導入の宣言ツールを持つスキル: **166 / 789**（残り 623 はそのまま使える）
- 候補の再構成（`scan_missing_cli.scan()` を再利用）: 宣言 173 ＋ 「フェンス内でフラグ/パス引数を伴う呼び出し」形状の invoked-only 79 → **252 件**を分類対象とした。

## 4. 成果物

| ファイル | 役割 |
|---|---|
| `tools/skill-deps.json` | 分類の source of truth。252 エントリ。`{category, status, method, package, provides, note, skills[], evidence}` |
| `tools/report_skill_deps.py` | マニフェスト × `shutil.which(provides)` で現状を報告。`--json` / `--markdown` / `--check`（auto 未導入があれば exit 1） |
| `tools/install_skill_deps.sh` | `status=auto` を method 単位で冪等導入。既定 dry-run、`--apply` で実行、`--category` で絞り込み |
| `tools/test_skill_deps.py` | オフライン契約テスト（schema 検証、mock した brew/pipx/npm/gem/cargo/go で導入コマンド列を検証、`docs` 鮮度チェック） |
| `docs/skill-deps.md` | 生成物。カテゴリ別カバレッジ＋ auto / manual / unsupported / out_of_scope の表（理由つき） |
| `README.md` | 使い方・更新手順の追記 |

既存規約に合わせる点: ツールは `tools/`、POSIX `sh`、`python3.10+` 標準ライブラリのみ、オフラインテスト、README からの導線。

## 5. マニフェスト仕様

`category`: `net` / `mobile_re` / `dfir` / `stego` / `cloud_ab` / `web3` / `devsec` / `pylib` / `linux` / `windows` / `noise`
（`devsec`（サプライチェーン・CI 系）と `pylib`・`noise` は、対象カテゴリで拾えない候補を落とさないために追加。`noise` はツール名でない prose。）

`status`:
- `auto` … 無償・CLI・macOS 対応。導入対象（**63 件**）
- `manual` … 無償だが手動（GUI 主体・巨大・配布が GitHub ソース/リリース・PyPI/brew 未登録等）（**29 件**）
- `unsupported` … そのプラットフォームでは不可（Linux 専用 36 / Windows 専用 14 / macOS 代替あり）（**52 件**）
- `alias` … 別ツールが既に提供（`vol`→volatility3、`nxc`→crackmapexec 等）（**35 件**）
- `out_of_scope` … 今回対象外（言語パッケージ）（**60 件**）
- `noise` … ツール名でない（**13 件**）

`package` の存在検証: `formulae.brew.sh/api/formula|/cask`（HTTP 200）、`pypi.org/pypi/<name>/json`、`registry.npmjs.org`、`rubygems.org/api/v1/gems` で機械確認済み。tap 提供（`hashicorp/tap/{vault,boundary}`）は `brew search` 出力で確認。`go`/`cargo` は形式のみ（リポジトリ存在で確認）。

## 6. 導入対象（auto 61 / link 6）

確定した一覧（method・package・check・version・license・既定/opt-in）は
`docs/skill-deps.md` に**マニフェストから生成**して掲載している（重複記載による drift を避けるため、計画書には転記しない）。

method 内訳: brew 30 / pipx 22 / npm 2 / gem 1 / cargo 1（`link` 6 はシムのみ、`go` は該当なし）。

## 7. manual（31 件・理由つきで記録）

`autopsy`（GUI＋巨大）, `analyzeheadless`（Ghidra 同梱・約500MB）, `diec`（GitHub リリース・GUI 主体）, `aleapp`/`ileapp`（PyPI 未登録・GitHub リリース）, `pdf-parser.py`（DidierStevensSuite 単体スクリプト）, `libevtx-utils`（brew 未提供・python-evtx/plaso で代替）, `steghide`/`stegsnow`（brew 未提供・ソースビルド）, `scalpel`/`arpwatch`（brew 未提供・Linux 前提）, `whatweb`（brew/gem 未提供・Ruby ソース）, `graphql-cop`/`frida-ios-dump`（PyPI 未登録・GitHub ソース）, `gophish`/`gvm`/`rita`/`networkminer`（コンテナ or GUI 前提）, `msfconsole`（cask・大容量）, `kubesec`（brew 未提供・go install）, `wazuh-agent`/`falcon-sensor…rpm`/`zpa-connector`（契約・Linux/Windows 配布）, `arcjet`/`snyk`/`nextdns`/`tailscale`（アカウント必須）, `dredd`/`wappalyzer`（メンテナンス停滞・npm 版廃止）

## 8. インストール方針（`tools/install_skill_deps.sh`）

- 既定は **dry-run**（実行コマンドを列挙）。`--apply` でのみ実際に導入。
- `--category net,dfir` などで部分適用。`--only <tool,...>` も用意。
- 冪等性: 各エントリの **`check`（スキルが実際に呼ぶ canonical バイナリ）を全て** `command -v` で確認できたときだけ skip（`provides` は説明用に降格。M2 対応）。
- method ごとの実行: `brew install <pkg>` / `brew install --cask <pkg>` / `pipx install <pkg>` / `npm install -g <pkg>` / `gem install <pkg>` / `cargo install <pkg>` / `go install <pkg>@latest`。
- tap が必要な package（`hashicorp/tap/vault` 等）は `brew install` に完全名を渡し、`brew tap` を事前実行しない（`brew install user/tap/formula` が解決する）。
- **失敗は fail-closed**: 1 件でも失敗したらそこで停止し非 0 終了（既存 `update-skills.sh` と同じ挙動）。`--keep-going` で継続可。
- `sudo` は使わない。`HOMEBREW_NO_AUTO_UPDATE=1` を設定し、既存環境の意図しない更新を避ける。
- **preflight**: 1 件も変更する前に、プラン中の全 method runner（`brew`/`pipx`/`npm`/`gem`/`cargo`/`go`）の存在を検査し、欠ければ exit 3 で即終了（半端な適用を防ぐ）。
- `link` 区分（impacket の CLI 名）と gem/go の PATH 乖離は、`~/.local/bin` へのシムで解消（`--no-links` で無効化）。`go install` は `GOBIN=$HOME/.local/bin`。
- `HOMEBREW_NO_AUTO_UPDATE=1` / `HOMEBREW_NO_INSTALL_CLEANUP=1` を設定し、既存環境の意図しない更新を行わない。
- ネットワーク失敗（curl 検証・brew fetch）時のリトライは行わない（既定 1 回、`--retry N` で指定）。

## 9. 検証計画

1. `python3 -m unittest discover -s tools -p 'test_skill_deps.py'`（オフライン）
2. `python3 tools/report_skill_deps.py` で before/after の auto カバレッジを取得
3. `sh tools/install_skill_deps.sh` で dry-run 出力を確認 → `--apply` 実行
4. `python3 tools/report_skill_deps.py --check`（残 0 を確認）
5. `python3 tools/scan_missing_cli.py` を再実行し、宣言ベース未導入が 173 → 減少したことを確認（invoked-only の prose ノイズは残る）
6. `python3 -m unittest discover -s tools -p 'test_update_skills.py'`（既存テストの非破壊確認）
7. `git status` / `git diff --check`

## 10. リスクと対処

| リスク | 対処 |
|---|---|
| ディスク（残 12Gi） | 巨大カテゴリを auto から外済み。plaso/mythril/atomic-operator 等は導入前にサイズを確認し、失敗時は `manual` へ降格 |
| brew の自動更新・既存環境への副作用 | `HOMEBREW_NO_AUTO_UPDATE=1`、`brew upgrade` は実行しない、cask は 1 件のみ |
| 上流での name 変更（例: libevtx が brew から消えた） | 存在検証を実装時に再実行し、`packageVerified` を付与。不一致は manual 落ち |
| PATH（pipx/uv の `~/.local/bin`） | 導入後に `command -v` で確認。PATH 外ならその旨を報告（自動でシェル設定は書き換えない） |
| `gem`/`cargo`/`go` 未導入 | 事前チェックで失敗扱い（誤魔化さない） |
| 一部だけ入って半端な状態 | `report_skill_deps.py --check` が残を列挙。導入は method 単位で再実行可能（冪等） |
| マニフェストの誤分類 | レビューで `auto` 63 件の package 名を検証。`skills` 証跡列で出典スキルを追える |

## 11. ロールバック

- リポジトリ: `git checkout -- tools/ README.md docs/`（作業ブランチ `feat/skill-deps-provisioning` を作成して実施）
- 環境: docs に記載した逆操作（`brew uninstall <pkg>` / `pipx uninstall <pkg>` / `npm uninstall -g <pkg>` / `gem uninstall <pkg>` / `cargo uninstall <pkg>` / `rm ~/.local/bin/<shim>`）を手動実行。`--uninstall` は実装しない（誤操作防止のため意図的に手動）

## 12. レビュー観点（依頼）

1. `auto` 63 件について、**package 名・method・provides の対応が正しいか**（特に `tshark`←wireshark、`plaso`←log2timeline.py/psort.py、`analyzeMFT`←analyzeMFT.py、`sigma-cli`←sigma、`freeradius-server`←radiusd、`osquery` は cask、`hashicorp/tap/*`）。
2. `manual`/`unsupported` への落とし方が妥当か（実は brew/pipx で入るのに manual に落ちていないか、その逆）。
3. 対象カテゴリの選択（ユーザー回答）に対する**過不足**。追加した `devsec` カテゴリの是非。
4. `install_skill_deps.sh` の安全性（既定 dry-run、fail-closed、sudo 不使用、冪等性の担保方法）。
5. 検証計画が「整備された」ことの証明として十分か。抜けている検証は何か。
6. 非スコープ（言語パッケージ 60 件）の扱いは妥当か。

## 13. 実行順序

1. 本計画のレビュー（独立レビュー）→ 指摘反映
2. `tools/skill-deps.json` 生成（レビュー済み分類＋再検証）
3. `tools/report_skill_deps.py` / `tools/install_skill_deps.sh` / `tools/test_skill_deps.py` 実装
4. dry-run → `--apply` → `--check`
5. `docs/skill-deps.md` 生成、README 追記、既存テスト＋新規テスト
6. before/after レポート、`git diff --check`


## 14. 独立レビューへの対応（reviewer / APPROVE_WITH_FIXES）

| 指摘 | 実測による確認 | 対応 |
|---|---|---|
| **M1** `osquery` を cask で auto は不可（PATH に出ない） | cask の artifacts は `pkg` 配布（`osquery-5.23.1.pkg`）で brew link 対象外。スキル本文も `brew install osquery`（formula 前提） | `manual` へ降格（理由を note に記載）。auto から除外 |
| **M2** 「provides のどれか 1 つが在れば skip」は不健全 | `pwntools` の `checksec`、`freeradius` の `radtest` 等で偽 skip/偽合格が起こり得る | マニフェストに **`check`（canonical バイナリ、all 判定）** を追加。install と report が同じ `check` を共有。`provides` は説明用に降格 |
| **M3** `gem` が sudo を要求しうる | brew Ruby（`/opt/homebrew/opt/ruby`）の gem dir は **nino 所有で sudo 不要**（`/opt/homebrew/lib/ruby/gems/4.0.0`）。真の問題は `EXECUTABLE DIRECTORY` が PATH 外 | `gem install`（sudo なし）＋ `~/.local/bin/zsteg` へのシム。実測で PATH 非掲載を確認済み |
| **M4** `devsec` は対象カテゴリ外なのに auto | ユーザー選択は 7 カテゴリ（devsec を含まない） | `categories.optIn` に分離し `defaultApply=false`。既定導入から除外し、`--category devsec` で明示指定時のみ導入 |
| **M5** PATH 反映が「報告のみ」 | 非対話 PATH に `~/.local/bin` `/opt/homebrew/sbin` `.cargo/bin` は有り、`~/go/bin` と gem bin は無い | gem/go はシム／GOBIN で解消。検証は `report --check`（`command -v` ベース）で実施し、非対話シェルでも解決することを確認 |
| SHOULD: impacket CLI 名の欠落 | `impacket-psexec` 等は**存在せず**、実体は `psexec.py` 等（pipx bin） | `status=link`（6 件）＋シム定義で解消 |
| SHOULD: バージョン非固定 | — | `version`/`license` を生成時に記録（brew/PyPI/npm/gem API）。導入は最新取得である旨と `--verify-upstream` を docs に明記（pin は今回スコープ外と明示） |
| SHOULD: runner preflight 欠如 | — | 実装（exit 3、変更前に検査） |
| SHOULD: 残存数の期待値が弱い | — | report が `declared-evidence` の区分別カウント（resolved/pending/excluded/alias-*）を出力。検証は pending=0 を要求 |
| SHOULD: Linux 代替手順の実体が無い | — | 52 件の unsupported に `alternative` を付与（49 件は具体手順、3 件はバケット既定文）。`docs/skill-deps.md` に表で掲載 |
| SHOULD: フラグ仕様の不整合 | — | `--list-installed` は削除（report が代替）。実在フラグは `tools/README.md` に列挙。`--uninstall` は意図的に未実装 |
| SHOULD: ライセンス記録なし | — | brew/PyPI/npm/gem から取得し `license` に記録 |
| NICE: method 内訳の誤り | — | 表から再計算（brew 30 / pipx 22 / npm 2 / gem 1 / cargo 1） |
| NICE: `__pycache__` が untracked | — | `.gitignore` に `__pycache__/` `*.pyc` `.DS_Store` を追加 |
| NICE: evidence/skills の健全性テスト | — | `test_skill_deps.py` が skills 実在・alias の `via` 実在・check 非空を検査 |
| NICE: `nosqli` / `bgpalerter` | PyPI `nosqli` は 404（スキル記載の pip 経路とも不一致）。`bgpalerter` の npm bin は `bgpalerter` で一致 | `nosqli` は manual 化、`bgpalerter` は auto を維持（対応確認済み） |
| （実行中に発見）read ループの stdin 枯渇 | `brew` がプランを飲み込み 8 件で停止（exit 1 をラッパーの `echo` が隠していた） | `done 3< "$PLAN"` ＋ 子プロセス `< /dev/null`。回帰テストを追加し、**修正前コードで実際に失敗する**ことを確認 |
| （実行中に発見）cp314 ホイール未提供 | `yara-python` / `coincurve` は macos-arm64 のホイールが cp313 まで（PyPI API で確認） | `python` フィールドを追加し該当 4 件を `pipx --python python3.13` で導入 |
| （実行中に発見）check 名のズレ | 実測: `analyzemft` / `beacon-dump` / `opencanaryd` / `hindsight.py` / `evtx_dump` / `slither` / `ROPgadget` / `myth`（マニフェストの想定名と不一致） | すべて実測名へ修正し、スキル呼び出し名が異なるものはシム（`analyzeMFT.py`, `hindsight`, `impacket-*`） |
| （実行中に発見）ディスク 100% | 空き 2.8 GiB、`~/.cache/uv` 32 G / brew cache 7.5 G / `~/.npm/_npx` 5.1 G | キャッシュのみ削除し空き 54.4 GiB に回復（`uv cache clean` 等）。docs に容量節を追加 |
| （実行中に改善）最終検証の honesty | インストール直後の WARN を unresolved として数え、リンク後に解決しても残っていた | リンク後の再検証で unresolved を算出。`~/.local/bin` が PATH 外なら警告 |
| （実行中に発見）pipx 1.17.12 の制約パース | `Requires-Python` が空の `theHarvester` で「Cannot read the Python constraint '3.13.16'」→ venv を削除 | `uv tool install` 経路（method: uv、`UV_TOOL_BIN_DIR=~/.local/bin`）をサポート |
| （実行中に発見）C 拡張ビルドが SDK を見つけられない | `ckzg==1.0.2` が `'stdlib.h' file not found`（PATH の clang は Swift 版） | インストーラで `SDKROOT=$(xcrun --show-sdk-path)` をエクスポート。手元検証で ckzg のビルド・import 成功を確認 |
| （実行中に発見）plaso の実バイナリ名 | `.py` なし（`log2timeline` / `psort`）。スキルは `.py` 付き名を呼ぶ | check を実名に修正し、`log2timeline.py`/`psort.py` のシムを追加 |
| （実行中に発見）`pymalleablec2` は CLI なし | スキルは `import`（ライブラリ）として参照 | `pylib`/`out_of_scope` へ移動（venv/pip で導入する想定） |
| 反証不能だった点（全 252 件の直接照合） | — | `tools/skill-deps.json` を生成し全件を機械可読で提示。`reviewer` の想定外だった `alias` 検証も `check`/`via` で可能にした |
