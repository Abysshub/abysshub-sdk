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

In Claude Code, you can install it as a plugin instead, so it is there in every session of yours, in every project. This repo is a plugin marketplace, `abysshub`; add it, then install the plugin:

```
/plugin marketplace add Abysshub/abysshub-sdk
/plugin install abyss-widget@abysshub
```

The plugin holds the same `skills/abyss-widget/` files.

Then ask your agent, for example, *"Share my invoice script with my client on Abyss"*, *"Port my n8n invoice flow to Abyss"* or *"Make an Abyss Widget that turns a CSV into a chart"*. When your Abyss API key has **Manage Widgets**, the agent publishes the Widget itself, privately, and ends with its link; without one, it walks you through the website's upload. When the Abyss API can't be reached, it checks the Widget on your machine and hands you the folder.

## Publish a Widget folder

The Python package ships the `abysshub` command, which publishes a Widget folder as the website's Publish page does: it uploads the folder, makes the Test Run from `test_inputs.json`, saves the listing from `abyss.json` and prints the Widget's link. It needs a key with Manage Widgets.

```bash
export ABYSS_API_KEY=abyss_sk_...   # a key with Manage Widgets, from your Cave
uvx abysshub publish my-widget      # or: pip install abysshub && abysshub publish my-widget
```

Run it again in the same folder to publish a new version. `abysshub status my-widget` shows the Widget on Abyss beside the folder, and `abysshub pull my-widget` takes a listing changed on the website into the folder.

## License

MIT
