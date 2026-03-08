# Symphony Operational Guide

## What Is Symphony

Symphony is a long-running automation service that continuously polls an issue tracker (Linear),
creates an isolated workspace for each issue, and drives a coding agent session against that
workspace. It converts issue-based project work into a repeatable daemon workflow: one issue, one
workspace, one agent session — with bounded concurrency, exponential retry, and live reconciliation
against the tracker. The authoritative workflow policy — the agent prompt, runtime settings, and
workspace hooks — lives in a `WORKFLOW.md` file in the target repository, so teams version their
agent behaviour alongside their code. A successful run typically ends at a workflow-defined handoff
state (e.g. `Human Review`), not necessarily a tracker-terminal state like `Done`.

---

## Architecture

Symphony is built from six core components:

| Component | Responsibility |
|---|---|
| **Workflow Loader** | Reads `WORKFLOW.md`, splits YAML front matter from the Markdown prompt body, returns `{config, prompt_template}` |
| **Config Layer** | Typed getters over parsed front matter; applies defaults, resolves `$VAR` env references, validates at startup and before each dispatch cycle |
| **Issue Tracker Client** | Fetches candidate issues in active states, refreshes live issue states by ID (reconciliation), fetches terminal-state issues at startup for cleanup; normalises tracker payloads into a stable issue model |
| **Orchestrator** | Owns the poll tick and the single authoritative in-memory runtime state; decides which issues to dispatch, retry, stop, or release; tracks session metrics and aggregate token totals |
| **Workspace Manager** | Maps issue identifiers to isolated workspace directories; enforces path safety invariants; runs workspace lifecycle hooks; removes workspaces for terminal issues |
| **Agent Runner** | Creates or reuses the workspace, builds the per-issue prompt from the workflow template, launches the coding-agent app-server subprocess over stdio, and streams events back to the orchestrator |

Two additional optional components: a **Status Surface** (human-readable terminal/dashboard) and a
**Logging** subsystem (structured logs to one or more sinks).

---

## WORKFLOW.md Format

`WORKFLOW.md` is a Markdown file with optional YAML front matter. The front matter configures the
runtime; the body is a Liquid-compatible prompt template rendered once per issue dispatch.

```
---
tracker:
  kind: linear
  api_key: $LINEAR_API_KEY
  project_slug: my-project
polling:
  interval_ms: 30000
workspace:
  root: ~/symphony_workspaces
agent:
  max_concurrent_agents: 5
codex:
  approval_policy: auto
---

You are working on {{ issue.identifier }}: {{ issue.title }}.

{% if attempt %}This is retry attempt {{ attempt }}.{% endif %}

## Description
{{ issue.description }}
```

Parsing rules:
- File starting with `---` → parse lines until next `---` as YAML front matter.
- Remaining lines → prompt body (trimmed).
- Front matter absent → entire file is prompt body; config is empty map.
- Front matter must be a YAML map; non-map values are errors.
- Unknown top-level keys are ignored for forward compatibility.

Template variables available at render time: `{{ issue }}` (full normalised issue object including
`id`, `identifier`, `title`, `description`, `state`, `priority`, `labels`, `blocked_by`, etc.) and
`{{ attempt }}` (null on first run, integer on retry or continuation). Unknown variables and unknown
filters are hard errors — the run attempt fails rather than silently continuing.

### Front Matter Sections

#### `tracker`

Configures the issue tracker connection.

| Key | Default | Notes |
|---|---|---|
| `kind` | — | **Required.** Currently only `linear` is supported. |
| `endpoint` | `https://api.linear.app/graphql` | GraphQL endpoint |
| `api_key` | — | **Required.** Literal token or `$VAR_NAME`. Canonical env var: `LINEAR_API_KEY`. |
| `project_slug` | — | **Required for Linear.** Maps to Linear project `slugId`. |
| `active_states` | `Todo, In Progress` | List or comma-separated string. Issues in these states are eligible for dispatch. |
| `terminal_states` | `Closed, Cancelled, Canceled, Duplicate, Done` | Issues in these states trigger workspace cleanup and session termination. |

#### `polling`

| Key | Default | Notes |
|---|---|---|
| `interval_ms` | `30000` | Milliseconds between poll ticks. Re-applied dynamically; no restart required. |

#### `workspace`

| Key | Default | Notes |
|---|---|---|
| `root` | `<system-temp>/symphony_workspaces` | Root directory for all per-issue workspaces. Supports `~` and `$VAR` expansion. |

Each issue gets its own subdirectory: `<workspace.root>/<sanitized_identifier>`. Workspaces persist
across retries and continuation runs. They are only removed when an issue enters a terminal state.

#### `hooks`

Shell scripts executed at workspace lifecycle events. All hooks run with the workspace directory as
`cwd` via `bash -lc <script>` (or host equivalent). The `hooks.timeout_ms` limit (default 60s)
applies to every hook.

| Hook | Trigger | On Failure |
|---|---|---|
| `after_create` | New workspace directory just created | **Fatal** — aborts workspace creation |
| `before_run` | Before each agent attempt, after workspace prepared | **Fatal** — aborts the current attempt |
| `after_run` | After each agent attempt (any outcome) | Logged and ignored |
| `before_remove` | Before workspace directory deletion | Logged and ignored |

```yaml
hooks:
  after_create: |
    git clone git@github.com:org/repo.git .
  before_run: |
    git fetch origin && git reset --hard origin/main
  after_run: |
    echo "run finished"
  timeout_ms: 120000
```

#### `agent`

Controls concurrency and retry behaviour.

| Key | Default | Notes |
|---|---|---|
| `max_concurrent_agents` | `10` | Global concurrency cap. Applied dynamically. |
| `max_retry_backoff_ms` | `300000` (5 min) | Upper bound for exponential backoff delay |
| `max_concurrent_agents_by_state` | `{}` | Per-state slot overrides. State names normalised (trim + lowercase). |

#### `codex`

Controls the coding-agent subprocess.

| Key | Default | Notes |
|---|---|---|
| `command` | `codex app-server` | Shell command, launched via `bash -lc`. Must speak app-server JSON-RPC protocol over stdio. |
| `approval_policy` | Implementation-defined | Codex `AskForApproval` value |
| `thread_sandbox` | Implementation-defined | Codex `SandboxMode` value |
| `turn_sandbox_policy` | Implementation-defined | Codex `SandboxPolicy` value |
| `turn_timeout_ms` | `3600000` (1 hour) | Per-turn hard timeout |
| `read_timeout_ms` | `5000` | Startup handshake request/response timeout |
| `stall_timeout_ms` | `300000` (5 min) | Inactivity window before orchestrator kills the session. Set `<= 0` to disable. |

To inspect the full set of supported Codex values, run:
```bash
codex app-server generate-json-schema --out /tmp/schema
```

#### Extension: `server`

Enables the optional HTTP observability API (not part of the core schema).

| Key | Notes |
|---|---|
| `server.port` | Integer. Positive = bind that port. `0` = ephemeral (useful for tests). CLI `--port` overrides. |

---

## Common Operations

### Starting Symphony

```bash
# Uses ./WORKFLOW.md in the current directory
symphony

# Explicit workflow file path
symphony path/to/WORKFLOW.md

# With HTTP observability API enabled
symphony --port 8080
symphony path/to/WORKFLOW.md --port 8080
```

Symphony validates config at startup. If `WORKFLOW.md` is missing, unparseable, or required fields
(`tracker.api_key`, `tracker.project_slug`, `codex.command`) are absent, it fails cleanly before
entering the polling loop.

### Configuring for a New Repository

1. Create `WORKFLOW.md` at the repository root (or any path you'll pass to the CLI).
2. Add YAML front matter: set `tracker.kind: linear`, `tracker.api_key`, `tracker.project_slug`.
3. Write the Markdown prompt body using `{{ issue }}` and `{{ attempt }}` variables.
4. Add `hooks.after_create` to clone/bootstrap the workspace and `hooks.before_run` to sync it.
5. Launch: `symphony path/to/WORKFLOW.md`.

### Operator Controls

- **Edit `WORKFLOW.md`** — most settings (poll interval, concurrency, prompt, hooks) apply
  automatically on the next tick without restart.
- **Change issue state in the tracker** — moving a running issue to a terminal state causes
  Symphony to stop the agent and clean the workspace at next reconciliation; moving to a non-active
  state stops the agent without workspace cleanup.
- **Restart the service** — in-memory retry timers are cleared; Symphony recovers by re-polling
  active issues and re-dispatching eligible work.

---

## Key Concepts

### Workspace Isolation

Every issue gets its own directory:

```
<workspace.root>/
  MT-123/    ← sanitized from issue identifier
  MT-456/
  ABC-789/
```

Workspace names are sanitized: any character outside `[A-Za-z0-9._-]` becomes `_`. The coding
agent subprocess is always launched with `cwd` pointing to that directory. Symphony validates that
the workspace path stays inside `workspace.root` before every agent launch — paths escaping the
root are rejected.

### Per-Issue Sessions

Each dispatch creates one `Run Attempt` — one agent subprocess in one workspace. The agent may
complete multiple coding turns within a single attempt (up to `agent.max_turns`). After a normal
exit, Symphony schedules a short continuation retry (1 second) to re-check whether the issue is
still active and needs another session. On failure, it schedules an exponential backoff retry
instead. Workspaces are intentionally preserved across all these attempts.

### The Poll-Dispatch-Reconcile Loop

Every tick (default every 30 seconds):

1. **Reconcile** — check all running sessions against current tracker state; terminate any whose
   issue has gone terminal (clean workspace) or non-active (no cleanup); run stall detection
   (kill + retry if `stall_timeout_ms` exceeded).
2. **Validate** — confirm dispatch config is still valid; skip dispatch (not reconciliation) if
   not.
3. **Fetch** — retrieve all candidate issues from the tracker in `active_states`.
4. **Sort** — by priority ascending (1–4 preferred; null sorts last), then oldest `created_at`,
   then identifier lexicographically.
5. **Dispatch** — launch workers for eligible issues until global and per-state concurrency slots
   are exhausted.

---

## How Amplifier Integrates

The `symphony` bundle wraps Symphony's optional HTTP API so Amplifier agents can monitor and manage
a running Symphony instance without leaving their context. The `symphony_tool` Python module exposes
`get_state()`, `get_issue(identifier)`, and `refresh()` methods that call the REST endpoints. The
`symphony-expert` behavior wires the tool into the agent's toolchain and provides the context
needed to interpret running sessions, retry queues, and token totals.

See [`HTTP_API.md`](HTTP_API.md) for the full endpoint reference.
See [`ISSUE_LIFECYCLE.md`](ISSUE_LIFECYCLE.md) for the orchestration state machine.
