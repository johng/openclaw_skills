# OpenClaw Skills

Custom skills for [OpenClaw](https://openclaw.ai).

## Setup

Add this repo to your openclaw config at `~/.openclaw/openclaw.json`:

```json
{
  "skills": {
    "load": {
      "extraDirs": [
        "~/repos/openclaw_skills"
      ]
    }
  }
}
```

Skills are picked up automatically via the file watcher.

## Structure

Each skill lives in its own directory with a `SKILL.md` file:

```
openclaw_skills/
  my-skill/
    SKILL.md
```

## Creating a Skill

Create a directory and add a `SKILL.md` with YAML frontmatter:

```markdown
---
name: my-skill
description: What the skill does
---

Skill prompt content here.
```

### Frontmatter Options

| Field | Description |
|-------|-------------|
| `name` | Skill identifier |
| `description` | What the skill does |
| `user-invocable` | Expose as slash command (default: true) |
| `disable-model-invocation` | Exclude from model prompts |
| `metadata` | JSON for gating/config (requires, os, etc.) |
