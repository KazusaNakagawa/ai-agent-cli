# Skills

Source-of-truth backup of Claude Code custom skills used in this project.

These skill files are not auto-discovered from this location. Claude Code looks under `~/.claude/skills/`, so install via symlink or copy.

## Available Skills

| Skill | Description |
|---|---|
| [notion-import](./notion-import/SKILL.md) | Save the previous research/answer to a local markdown file under `output/`, then append it to today's Notion briefing page. |

## Install

Symlink (recommended — edits stay in sync with the repo):

```bash
ln -s "$(pwd)/skills/notion-import" ~/.claude/skills/notion-import
```

Or copy (one-shot snapshot — repo and `~/.claude/skills/` will drift):

```bash
cp -r skills/notion-import ~/.claude/skills/
```

After installation, the skill is invocable via `/notion-import <topic-slug>` in Claude Code.

## Updating a Skill

Edit the file under `skills/<name>/SKILL.md`, commit the change, and (if you used `cp`) re-copy to `~/.claude/skills/`. Symlinked installs pick up edits automatically.
