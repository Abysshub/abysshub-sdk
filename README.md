# abysshub

Share a script with a client or a colleague, or port an n8n flow, a notebook, or a Streamlit or Gradio app: on [Abyss](https://abysshub.com), it becomes a Widget, a hosted tool that anyone runs from its page or from their own code. This repo holds the `abyss-widget` agent skill, which makes the Widget with your coding agent, and the official JavaScript and Python libraries for the Abyss API, which run a Widget from your code and get its result and files.

- **Docs:** [abysshub.com/docs](https://abysshub.com/docs)
- **For coding agents:** [abysshub.com/llms.txt](https://abysshub.com/llms.txt)
- **To make a Widget:** the [`abyss-widget` agent skill](skills/abyss-widget/SKILL.md)

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

Then ask your agent, for example, *"Share my invoice script with my client on Abyss"*, *"Port my n8n invoice flow to Abyss"* or *"Make an Abyss Widget that turns a CSV into a chart"*. Until the Abyss API opens, the skill checks a Widget on your machine and stops before the upload.

## License

MIT
