# Symphony HTTP API Reference

Symphony exposes an optional JSON REST API under `/api/v1/*` when started with `--port` or with
`server.port` set in `WORKFLOW.md` front matter. The server binds loopback (`127.0.0.1`) by
default. The API is read-only except for the `/refresh` operational trigger.

Enable the server:
```bash
symphony --port 8080
symphony path/to/WORKFLOW.md --port 8080
```

Or in `WORKFLOW.md` front matter:
```yaml
server:
  port: 8080
```

CLI `--port` takes precedence over `server.port` when both are present.

---

## Endpoints

### `GET /api/v1/state`

Returns a summary snapshot of the current orchestrator state: all running sessions, the retry
queue, aggregate token/runtime totals, and the latest rate-limit data.

**Response — 200 OK**

```json
{
  "generated_at": "2026-02-24T20:15:30Z",
  "counts": {
    "running": 2,
    "retrying": 1
  },
  "running": [
    {
      "issue_id": "abc123",
      "issue_identifier": "MT-649",
      "state": "In Progress",
      "session_id": "thread-1-turn-1",
      "turn_count": 7,
      "last_event": "turn_completed",
      "last_message": "",
      "started_at": "2026-02-24T20:10:12Z",
      "last_event_at": "2026-02-24T20:14:59Z",
      "tokens": {
        "input_tokens": 1200,
        "output_tokens": 800,
        "total_tokens": 2000
      }
    }
  ],
  "retrying": [
    {
      "issue_id": "def456",
      "issue_identifier": "MT-650",
      "attempt": 3,
      "due_at": "2026-02-24T20:16:00Z",
      "error": "no available orchestrator slots"
    }
  ],
  "codex_totals": {
    "input_tokens": 5000,
    "output_tokens": 2400,
    "total_tokens": 7400,
    "seconds_running": 1834.2
  },
  "rate_limits": null
}
```

**Field notes:**
- `generated_at` — UTC timestamp when the snapshot was produced.
- `counts` — summary counts for quick status checks.
- `running[].session_id` — format `<thread_id>-<turn_id>`.
- `running[].turn_count` — number of coding-agent turns started within the current worker lifetime.
- `running[].last_event` — most recent event type from the agent (e.g. `notification`,
  `turn_completed`, `approval_auto_approved`).
- `retrying[].attempt` — retry attempt number (1-based for the retry queue).
- `retrying[].due_at` — UTC timestamp when the retry will fire.
- `codex_totals.seconds_running` — aggregate wall-clock seconds across all sessions including
  currently active ones.
- `rate_limits` — latest rate-limit payload from the coding agent, or `null` if none received.

---

### `GET /api/v1/<issue_identifier>`

Returns runtime and debug details for a single issue by its identifier (e.g. `MT-649`).

**Response — 200 OK**

```json
{
  "issue_identifier": "MT-649",
  "issue_id": "abc123",
  "status": "running",
  "workspace": {
    "path": "/tmp/symphony_workspaces/MT-649"
  },
  "attempts": {
    "restart_count": 1,
    "current_retry_attempt": 2
  },
  "running": {
    "session_id": "thread-1-turn-1",
    "turn_count": 7,
    "state": "In Progress",
    "started_at": "2026-02-24T20:10:12Z",
    "last_event": "notification",
    "last_message": "Working on tests",
    "last_event_at": "2026-02-24T20:14:59Z",
    "tokens": {
      "input_tokens": 1200,
      "output_tokens": 800,
      "total_tokens": 2000
    }
  },
  "retry": null,
  "logs": {
    "codex_session_logs": [
      {
        "label": "latest",
        "path": "/var/log/symphony/codex/MT-649/latest.log",
        "url": null
      }
    ]
  },
  "recent_events": [
    {
      "at": "2026-02-24T20:14:59Z",
      "event": "notification",
      "message": "Working on tests"
    }
  ],
  "last_error": null
}
```

**Field notes:**
- `status` — high-level status string: `running`, `retrying`, `claimed`, or similar.
- `workspace.path` — absolute path to the per-issue workspace directory.
- `attempts.restart_count` — number of separate worker sessions started for this issue.
- `attempts.current_retry_attempt` — current retry attempt number from the retry queue.
- `running` — present when a worker is active; `null` when the issue is queued or idle.
- `retry` — present when a retry is pending; `null` when running or released.
- `logs.codex_session_logs` — log file references for the coding-agent session; implementation-
  defined. `url` may be a remote log link or `null`.
- `recent_events` — tail of recent agent events for quick inspection without log access.
- `last_error` — last error message from a failed attempt, or `null`.

**Response — 404 Not Found**

Returned when the issue identifier is unknown to the current in-memory orchestrator state.

```json
{
  "error": {
    "code": "issue_not_found",
    "message": "No session found for identifier MT-999"
  }
}
```

---

### `POST /api/v1/refresh`

Queues an immediate tracker poll and reconciliation cycle. Useful for triggering a check without
waiting for the next scheduled tick. Implementations may coalesce repeated rapid calls.

**Request body:** empty body or `{}`

**Response — 202 Accepted**

```json
{
  "queued": true,
  "coalesced": false,
  "requested_at": "2026-02-24T20:15:30Z",
  "operations": ["poll", "reconcile"]
}
```

**Field notes:**
- `queued` — `true` if the refresh was scheduled.
- `coalesced` — `true` if a refresh was already pending and this request was merged into it.
- `operations` — the operations that will run (`poll` and/or `reconcile`).

---

## Error Responses

All API errors use a consistent JSON envelope:

```json
{
  "error": {
    "code": "error_code_string",
    "message": "Human-readable description"
  }
}
```

| Status | Condition |
|--------|-----------|
| `404 Not Found` | Issue identifier not in current orchestrator state (`GET /api/v1/<id>`) |
| `405 Method Not Allowed` | Wrong HTTP method used on a defined route |

Implementations may add additional error codes but should preserve this envelope shape for
compatibility with tooling built against the API.

---

## Design Notes

- All endpoints are read-only except `/refresh` (which triggers an operational action but does not
  modify persistent state directly).
- The API reflects in-memory orchestrator state only — it does not query the tracker or filesystem.
- Implementations may add fields to responses but should not remove or rename existing fields
  within a version.
- If Symphony's optional dashboard is a client-side app, it consumes this API rather than
  duplicating orchestrator logic.
- The Amplifier `symphony_tool` calls these endpoints to give agents visibility into running
  sessions, retry queues, and aggregate token consumption.
