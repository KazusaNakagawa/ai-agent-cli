# Skills

Source-of-truth backup of Claude Code custom skills used in this project.

このディレクトリ（`<project>/.claude/skills/`）は Claude Code がこの repo で作業中に**自動検出**します。本 repo 内で使う分にはインストール不要です。`~/.claude/skills/` にグローバル配置したい場合のみ、下記の Install 手順を使ってください。

## Available Skills

| Skill | Description |
|---|---|
| [notion-import](./notion-import/SKILL.md) | Save the previous research/answer to a local markdown file under `output/`, then append it to today's Notion briefing page. |
| [tech-architect](./tech-architect/SKILL.md) | Walk through a fixed sequence of multiple-choice questions (target user, distribution, stack, code layout, UI structure, credentials, auth) and produce a design doc draft. Specialization of `superpowers:brainstorming`. |
| [architecting-defaults](./architecting-defaults/SKILL.md) | Recurring decision-time behaviors during technical brainstorming: respond decisively to "ベストプラクティスは?", lead with comparison tables for "種類は?", inspect referenced projects before answering, default to terse UI labels, accept flexible multi-select answers. |

## Install (optional — グローバル配置したい場合のみ)

repo 内で完結させる場合は不要。他のプロジェクトからも呼びたい時だけ実行する。

Symlink（推奨 — repo の編集と同期される）:

```bash
for s in notion-import tech-architect architecting-defaults; do
  ln -s "$(pwd)/.claude/skills/$s" "$HOME/.claude/skills/$s"
done
```

Or copy（スナップショット — repo と `~/.claude/skills/` が drift する）:

```bash
cp -r .claude/skills/notion-import .claude/skills/tech-architect .claude/skills/architecting-defaults ~/.claude/skills/
```

呼び出しは `/notion-import <topic-slug>`、`/tech-architect <feature-brief>` など。`architecting-defaults` は brainstorming 中に description マッチで自動起動する。

## Updating a Skill

`.claude/skills/<name>/SKILL.md` を編集してコミットする。`cp` で global インストールしている場合は `~/.claude/skills/` へ再コピーが必要。symlink インストールなら自動反映。

## Writing Conventions

- **コードブロックには必ず言語を指定する。** 言語が不明な場合は `bash`、`text`、`json` など適切なものを設定すること。言語なしの ` ``` ` は禁止。
  - シェルコマンド → ` ```bash `
  - 設定ファイル / 構造化データ → ` ```json `、` ```yaml `、` ```toml `
  - ディレクトリツリーやプレーンテキスト → ` ```text `
  - Markdown 自体を示す場合 → ` ```markdown `
