# abysshub

Pre-release: the Abyss API opens soon.

The official libraries for the [Abyss](https://abysshub.com) API, and an agent skill for making Abyss Widgets.

| Folder | What it is |
|---|---|
| [`js/`](js/README.md) | `abysshub` on npm, for JavaScript and TypeScript |
| [`python/`](python/README.md) | `abysshub` on PyPI, for Python 3.9+ |
| [`n8n/`](n8n/README.md) | `n8n-nodes-abysshub`, the Abyss node for n8n (not published yet) |
| [`skills/abyss-widget/`](skills/abyss-widget/SKILL.md) | the `abyss-widget` agent skill |

## The `abyss-widget` skill

It teaches a coding agent (Claude Code, Codex, Cursor and others) to make an Abyss Widget in one of two ways: **build** one from scratch, or **port** a tool you already have (an n8n flow, a Python script, a notebook, a Streamlit or Gradio app) and check the Port on your own real uses of the original.

Install it with [Vercel's skills CLI](https://github.com/vercel-labs/skills), which needs Node 22.20 or newer:

```bash
npx skills add Abysshub/abysshub-sdk --skill abyss-widget -a claude-code
```

- `-a` names your agent: `claude-code`, `codex`, `cursor`, or several. Without `-a`, the CLI asks, or with `-y` installs for every agent it knows.
- `-g` installs it for all your projects instead of this one.
- `--list` shows the skill without installing it.

Or copy the folder yourself: `skills/abyss-widget/` into `.claude/skills/` for Claude Code, or `.agents/skills/` for Codex and Cursor.

Then ask your agent, for example, *"Port my n8n invoice flow to Abyss"* or *"Make an Abyss Widget that turns a CSV into a chart"*. Until the Abyss API opens, the skill checks a Widget on your machine and stops before the upload.

## License

MIT
