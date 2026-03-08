# amplifier-bundle-symphony Design

## Goal

Create an Amplifier bundle that integrates with OpenAI's Symphony service — giving Amplifier users visibility into Symphony's operations, management capabilities, and workflow bridging between interactive Amplifier sessions and Symphony's autonomous agent fleet.

## Background

Symphony is a long-running Elixir daemon that polls Linear for issues, creates per-issue workspaces, and dispatches Codex agents. It operates autonomously but lacks a convenient interface for humans working inside Amplifier to monitor what it's doing, hand off work to it, or review what its agents produced.

The integration direction is one-way: **Amplifier calls Symphony** (not the reverse). Symphony already exposes an HTTP REST API that we wrap.

## Approach

**Pure Tool Bundle** (with a growth path toward adding Linear direct access later).

A single tool module wraps Symphony's HTTP API. Two agents provide a knowledge/action split. Recipes encode operational patterns. Context follows the thin-awareness + heavy-expert pattern.

No SDK, no Symphony modifications, no subprocess management. The tool talks to Symphony's existing REST endpoints.

## Architecture

```
amplifier-bundle-symphony/
├── bundle.md                              # Thin: foundation + behavior + awareness pointer
├── behaviors/
│   └── symphony.yaml                      # Wires tool (scoped to operator), agents, thin context
├── context/
│   └── symphony-awareness.md              # ~30 lines: "Symphony exists, delegate here"
├── agents/
│   ├── symphony-expert.md                 # Context sink: spec, lifecycle, harness engineering
│   └── symphony-operator.md               # Action agent: calls tool-symphony, manages work
├── docs/
│   ├── SYMPHONY_GUIDE.md                  # Full API + operational reference
│   ├── ISSUE_LIFECYCLE.md                 # State machine: unclaimed → claimed → running → ...
│   ├── HARNESS_ENGINEERING.md             # Distilled principles from OpenAI blog
│   └── HTTP_API.md                        # /api/v1/* endpoint reference
├── recipes/
│   ├── symphony-status-report.yaml        # Delegate to operator → format report
│   ├── issue-handoff.yaml                 # Verify → dispatch → monitor → report
│   └── workspace-review.yaml              # Operator fetches output → expert evaluates
└── modules/
    └── tool-symphony/
        ├── pyproject.toml
        └── amplifier_module_tool_symphony/
            ├── __init__.py                # mount() + SymphonyTool
            └── client.py                  # HTTP client with retry logic
```

Key structural decisions:

- `context/` has ONE thin file (~30 lines). Heavy docs load only when agents spawn (context sink pattern).
- Heavy documentation lives in `docs/`, @-mentioned by symphony-expert only, never by root sessions.
- Tool is scoped to the operator only via inline agent pattern in behavior YAML. Expert has no HTTP tool access.
- Harness engineering stays in-bundle per the Two-Implementation Rule — extract to standalone skill later when a second consumer appears.
- No `skills/` directory inside the bundle (not a standard convention).

## Components

### symphony-expert — Context Sink

| Aspect | Detail |
|---|---|
| Role | Knowledge source — answers "why" and "how does it work" |
| Model role | `[reasoning, general]` |
| Tools | Read-only: filesystem + search only. No write, no bash, no HTTP |
| @-mentions | `docs/SYMPHONY_GUIDE.md`, `docs/ISSUE_LIFECYCLE.md`, `docs/HARNESS_ENGINEERING.md`, `docs/HTTP_API.md` |
| Modes | RESEARCH (explain mechanisms), GUIDE (prescriptive config advice), VALIDATE (diagnose against spec) |

Trigger phrases: "How does Symphony...", "Why isn't my issue...", "What should WORKFLOW.md look like...", "How does the retry state machine..."

Description must include: MUST be consulted, authoritative-on taxonomy, 3+ example blocks covering debugging/config/architecture triggers.

### symphony-operator — Action Agent

| Aspect | Detail |
|---|---|
| Role | Executes operations — monitoring, refresh, status reports |
| Model role | `critical-ops` |
| Tools | `tool-symphony` (scoped via inline agent pattern in behavior YAML) |
| @-mentions | Light — knows the API operations, not the full spec |
| Consults | Delegates to symphony-expert when it needs deep knowledge |

Trigger phrases: "What's Symphony doing right now?", "Refresh Symphony", "Show me running issues", "Check issue MT-649"

**The relationship**: Operator does, expert knows. Operator can consult expert mid-task (same pattern as modular-builder consulting zen-architect). Expert never calls the API.

### tool-symphony — HTTP Tool Module

Wraps Symphony's HTTP REST API. Three operations:

| Operation | HTTP Call | Purpose |
|---|---|---|
| `status` | `GET /api/v1/state` | Full system snapshot — running sessions, retry queue, token totals, rate limits |
| `issue` | `GET /api/v1/<identifier>` | Deep detail on one issue — workspace, attempts, session, recent events, logs |
| `refresh` | `POST /api/v1/refresh` | Force immediate poll + reconciliation cycle |

**Input schema** (what the LLM sees):

```json
{
  "operation": "status | issue | refresh",
  "identifier": "MT-649 (required for 'issue' operation)"
}
```

**Config** (via behavior YAML, env var fallback):

- `symphony_url` — default `${SYMPHONY_URL:-http://localhost:4000}`
- `timeout_seconds` — default `30`
- `connect_timeout_seconds` — default `5`

**Client resilience**: Retry with exponential backoff (3 attempts) since Symphony is an Elixir daemon that may be restarting. Surface actual error messages cleanly — the operator agent needs to read them to make decisions.

Intentionally minimal — three operations. Future growth adds operations to the same tool rather than new tools.

## Data Flow

### Root Session → Agent Delegation

1. User asks a Symphony-related question or gives a command
2. Root session loads `context/symphony-awareness.md` (~30 lines), which tells it to delegate
3. Knowledge questions → `symphony-expert` (spawns with heavy docs @-mentioned)
4. Action requests → `symphony-operator` (spawns with tool-symphony scoped in)

### Operator → Symphony API

1. Operator receives task (e.g., "check status")
2. Calls `tool-symphony` with appropriate operation
3. Tool's `client.py` makes HTTP request to Symphony daemon with retry logic
4. Response parsed and returned to operator for formatting/decision-making

### Operator ↔ Expert Consultation

1. Operator encounters a decision requiring deep knowledge mid-task
2. Delegates to `symphony-expert` for analysis
3. Expert consults docs, returns findings
4. Operator incorporates findings into its action

### Recipe Flows

- **Status report**: Operator collects → formats → presents
- **Issue handoff**: Validate → Operator triggers refresh → Operator monitors → reports
- **Workspace review**: Operator fetches state → Expert evaluates against criteria → report with verdict

## Recipes

### symphony-status-report.yaml

"What's Symphony doing right now?"

- Step 1: `symphony-operator` → collect full status snapshot (running sessions, retry queue, token burn, stalled issues)
- Step 2: Format as a human-readable standup-style report
- Single flat recipe, no approval gates. Quick operational pulse.

### issue-handoff.yaml

"File this work for Symphony to handle"

- Step 1: Verify the issue is well-formed and ready for handoff (acceptance criteria, required fields)
- Step 2: `symphony-operator` → trigger refresh, monitor until Symphony acknowledges the issue
- Step 3: Report back — workspace created? Agent dispatched? Any errors?
- Bridge from interactive Amplifier work to autonomous Symphony execution.

### workspace-review.yaml

"Review what a Symphony agent produced"

- Step 1: `symphony-operator` → fetch workspace state, recent events, session output for a given issue
- Step 2: `symphony-expert` → evaluate the output against the issue's acceptance criteria and harness engineering principles
- Step 3: Report with verdict — pass/fail/needs-rework + specific findings
- Feedback loop — Amplifier as quality gate for Symphony's autonomous work.

All recipes delegate to agents, never call the tool directly.

## Context & Documentation Files

### context/symphony-awareness.md (~30 lines)

The only always-loaded file. Tells root sessions:

- Symphony exists and what it is (one paragraph)
- Delegate to `symphony-expert` for knowledge questions
- Delegate to `symphony-operator` for monitoring/actions
- Trigger words: Symphony, Linear polling, issue orchestration, workspace harness

### docs/SYMPHONY_GUIDE.md

Full operational reference. Covers the API endpoints, WORKFLOW.md format, config options, common operations. @-mentioned by symphony-expert only.

### docs/ISSUE_LIFECYCLE.md

The state machine in detail: `Unclaimed → Claimed → Running → RetryQueued → Released`. Transition triggers, eligibility predicates, blocker rules, retry backoff formula. @-mentioned by symphony-expert only.

### docs/HARNESS_ENGINEERING.md

Distilled principles from the OpenAI blog post: progressive disclosure, agent legibility, mechanical enforcement, entropy management, repo-as-system-of-record. Stays in-bundle per the Two-Implementation Rule — extract to standalone skill later if a second consumer appears. @-mentioned by symphony-expert only.

### docs/HTTP_API.md

Endpoint reference for `/api/v1/state`, `/api/v1/<issue>`, `/api/v1/refresh`. Response shapes, error codes, what each field means. @-mentioned by symphony-expert, also referenced by symphony-operator's instructions.

**The split**: Root sessions get a 30-line pointer. Expert carries ~4 doc files totaling maybe 3-4K tokens. Operator gets light instructions referencing the API. Nobody pays for docs they don't need.

## Error Handling

- **Connection refused / timeout**: Tool retries with exponential backoff (3 attempts). If all fail, surfaces the error clearly to the operator agent with the actual error message so it can report to the user or decide to retry later.
- **Symphony returning 503 (restarting)**: Handled by retry logic — common case for Elixir daemon restarts.
- **Invalid issue identifier**: Tool returns a clear error; operator reports it. No retry needed.
- **Network errors**: Separate connect timeout (5s) from read timeout (30s) to distinguish "can't reach Symphony" from "Symphony is slow to respond."
- **Recipe failures**: Each recipe step can fail independently. Operator reports what succeeded and what failed rather than silently swallowing errors.

## Testing Strategy

- **Tool module unit tests**: Mocked HTTP responses for all 3 operations + error cases + retry behavior
- **Client resilience tests**: Timeout, connection refused, 503 retry scenarios
- **Bundle composition tests**: Load bundle, verify agents available, verify tool registered
- **Recipe validation**: Validate YAML structure parses correctly
- **Integration tests** (optional): Against a running Symphony instance — requires Symphony to be up

## Open Questions

1. **Auth** — Symphony's HTTP API may not have auth today. If it adds auth later, tool config needs an `api_key` field.
2. **Linear direct access** — When to add a second tool for filing issues directly? Deferred to a future iteration.
3. **Workspace filesystem access** — Should the operator be able to read files from Symphony workspaces? Requires understanding Symphony's workspace path layout. Deferred.