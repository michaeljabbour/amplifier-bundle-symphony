# Symphony Awareness

Symphony is an autonomous agent orchestration service built by OpenAI. It is a long-running Elixir daemon that polls Linear for issues, creates per-issue filesystem workspaces, and dispatches Codex agents to work on each issue independently.

This bundle provides monitoring, management, and workflow bridging between Amplifier sessions and Symphony's autonomous agent fleet.

## When to Delegate

| Need | Delegate To |
|------|-------------|
| Understanding Symphony architecture, lifecycle, configuration | `symphony:symphony-expert` |
| Understanding harness engineering principles | `symphony:symphony-expert` |
| Monitoring Symphony status, running issues, token usage | `symphony:symphony-operator` |
| Forcing a refresh or checking specific issue status | `symphony:symphony-operator` |
| Reviewing what a Symphony agent produced | `symphony:symphony-operator` (fetches) + `symphony:symphony-expert` (evaluates) |

## Trigger Words

Symphony, Linear polling, issue orchestration, Codex dispatch, workspace harness, retry queue, WORKFLOW.md, harness engineering, agent fleet
