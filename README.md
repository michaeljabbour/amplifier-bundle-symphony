# amplifier-bundle-symphony

Amplifier integration with [Symphony](https://github.com/openai/symphony) — OpenAI's autonomous agent orchestration service.

Symphony is a long-running Elixir daemon that polls Linear for issues, creates per-issue workspaces, and dispatches Codex agents. This bundle gives Amplifier users visibility into Symphony's operations, management capabilities, and workflow bridging between interactive Amplifier sessions and Symphony's autonomous agent fleet.

## Installation

```bash
amplifier bundle add --app git+https://github.com/michaeljabbour/amplifier-bundle-symphony@main
```

This composes Symphony alongside your existing bundles. No replacement — just composition.

## What's Included

### Tool: `symphony`

Wraps Symphony's HTTP REST API with 3 operations:

| Operation | What It Does |
|-----------|-------------|
| `symphony(operation="status")` | Full system snapshot — running sessions, retry queue, token totals |
| `symphony(operation="issue", identifier="MT-649")` | Deep detail on one issue — workspace, attempts, session, events |
| `symphony(operation="refresh")` | Force immediate poll + reconciliation cycle |

### Agents

| Agent | Role |
|-------|------|
| `symphony:symphony-expert` | Knowledge source — architecture, WORKFLOW.md config, issue lifecycle, harness engineering principles |
| `symphony:symphony-operator` | Action agent — monitors status, inspects issues, triggers refreshes |

### Recipes

| Recipe | Purpose |
|--------|---------|
| `symphony-status-report` | Collect and format a standup-style status report |
| `issue-handoff` | Verify an issue, hand it off to Symphony, monitor until acknowledged |
| `workspace-review` | Fetch what a Symphony agent produced and evaluate it |

### Documentation

The `symphony-expert` agent carries deep reference docs:

- **SYMPHONY_GUIDE.md** — Full operational reference
- **ISSUE_LIFECYCLE.md** — Orchestration state machine (Unclaimed → Claimed → Running → RetryQueued → Released)
- **HTTP_API.md** — Endpoint reference with response shapes
- **HARNESS_ENGINEERING.md** — Distilled principles from [OpenAI's harness engineering post](https://openai.com/index/harness-engineering/)

## Configuration

Set the `SYMPHONY_URL` environment variable to point to your Symphony instance:

```bash
export SYMPHONY_URL=http://localhost:4000
```

Or configure via bundle behavior:

```yaml
tools:
  - module: tool-symphony
    config:
      symphony_url: http://your-symphony-host:4000
      timeout_seconds: 30
      connect_timeout_seconds: 5
```

## Usage

Once installed, just ask naturally:

- "What's Symphony doing right now?" → routes to `symphony-operator`
- "How does the retry state machine work?" → routes to `symphony-expert`
- "Check issue MT-649" → routes to `symphony-operator`
- "How should I configure WORKFLOW.md for this repo?" → routes to `symphony-expert`

Or run recipes:

```
Run the symphony-status-report recipe
```

## Development

```bash
# Install dev dependencies
cd modules/tool-symphony
pip install -e ".[dev]"

# Run tests
cd ~/dev/amplifier-bundle-symphony
python -m pytest tests/tool-symphony/ -v
```

## Architecture

```
amplifier-bundle-symphony/
├── bundle.md                     # Thin entry point
├── behaviors/symphony.yaml       # Wires tool, agents, context
├── context/symphony-awareness.md # 19-line delegation pointer
├── agents/
│   ├── symphony-expert.md        # Context sink (4 @-mentioned docs)
│   └── symphony-operator.md      # Action agent (tool-scoped)
├── docs/                         # Heavy docs (@-mentioned by expert only)
├── recipes/                      # 3 workflow recipes
└── modules/tool-symphony/        # Python HTTP client + Amplifier tool
```

## License

MIT
