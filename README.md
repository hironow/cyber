# cyber

セキュリティとクラウド関連のエージェント用スキルを集めたリポジトリです。スキルの本体は `.agents/skills/` にあり、`.pi/skills/` と `.claude/skills/` から参照します。参照元と更新管理の情報は `skills-lock.json` に記録されています。

## 使い方

リポジトリをクローンし、対応するエージェントでスキルを利用してください。スキルは外部 OSS 由来のため、実行前に内容と要求される権限を確認してください。

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
