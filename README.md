# cyber

セキュリティとクラウド関連のエージェント用スキルを集めたリポジトリです。スキルの本体は `.agents/skills/` にあり、`.pi/skills/` と `.claude/skills/` から参照します。参照元と更新管理の情報は `skills-lock.json` に記録されています。

## 使い方

リポジトリをクローンし、対応するエージェントでスキルを利用してください。スキルは外部 OSS 由来のため、実行前に内容と要求される権限を確認してください。

## 依存 CLI ツールの整備

スキルが参照する外部 CLI ツールのうち、この環境に無かったものを分類した一覧が `tools/skill-deps.json` です。
現在の充足状況は次のコマンドで確認できます。

```sh
python3 tools/report_skill_deps.py            # サマリ（auto 区分の resolved / pending）
python3 tools/report_skill_deps.py --check    # auto 区分に未導入があれば exit 1
sh tools/install_skill_deps.sh                # dry-run（既定。何も変更しない）
sh tools/install_skill_deps.sh --apply        # 実際に導入（既定カテゴリのみ）
```

- 導入対象は無償・CLI・macOS 対応のもの（`status=auto`）と、既存ツールに CLI 名のシムを張るもの（`status=link`）だけです。
- 有償・アカウント必須・巨大・Windows 専用、Linux 専用は自動導入せず、理由と代替手順を `docs/skill-deps.md` に記載しています。
- 言語パッケージ（`requests` 等）はスキル手順内で venv/pip により導入する想定のため、環境への常設導入は行いません。
- `devsec`（サプライチェーン/CI 系）は opt-in です。入れる場合は `sh tools/install_skill_deps.sh --apply --category devsec`。

分類・理由・代替手順の全体は [docs/skill-deps.md](docs/skill-deps.md)、ツールの仕様は [tools/README.md](tools/README.md) を参照してください。

## 更新

[Bun](https://bun.sh/) と Python 3 を用意し、このリポジトリのルートで実行します。

```sh
sh tools/update-skills.sh
```

このコマンドは **このリポジトリ内のスキルだけ**を更新します。内部で `bunx skills update -p -y` を実行し、上流に同名の複製があるため CLI がスキップする Google の3スキルを、記録済みのディレクトリから個別に取り込みます。CLI の警告は表示されますが、3スキルの取り込みが失敗した場合はコマンドも失敗します。グローバルスキルは更新しません。

更新後は差分を確認してからコミットしてください。

```sh
git diff --stat
git diff --check
python3 -m unittest discover -s tools -p 'test_update_skills.py'
```

ツールの詳細と CLI の制約は [tools/README.md](tools/README.md) を参照してください。
