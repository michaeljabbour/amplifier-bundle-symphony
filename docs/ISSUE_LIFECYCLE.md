# Issue Lifecycle: Orchestration State Machine

This document describes Symphony's **internal orchestration states** — the claim and dispatch
lifecycle tracked by the orchestrator in memory. These are distinct from the issue tracker states
(`Todo`, `In Progress`, `Human Review`, etc.) that live in Linear. Understanding the difference is
essential: the orchestrator's states drive dispatch and retry logic; the tracker states drive
eligibility and workspace cleanup.

---

## The 5 Orchestration States

| State | Description |
|---|---|
| **Unclaimed** | Issue is known to the orchestrator but has no active claim — not running, not queued for retry. Eligible for dispatch on the next tick if eligibility predicates pass. |
| **Claimed** | The orchestrator has reserved this issue to prevent duplicate dispatch. In practice, claimed issues are always in one of two sub-states: Running or RetryQueued. The claim persists until explicitly released. |
| **Running** | A worker task exists and the issue is tracked in the `running` map with live session metadata (session ID, turn count, token totals, last event timestamp). |
| **RetryQueued** | No worker is running, but a retry timer is scheduled in `retry_attempts`. The issue remains claimed so nothing else can dispatch it while it waits. |
| **Released** | Claim removed. This happens when the issue transitions to a terminal tracker state, moves to a non-active state, is not found in the tracker at retry time, or exhausts the retry path without re-dispatch. A released issue returns to Unclaimed for future dispatch eligibility. |

> **Important nuance:** A normal worker exit does **not** mean the issue is done. After the worker
> finishes its in-process turn loop, the orchestrator schedules a short continuation retry (1
> second, attempt 1). At retry time it re-checks whether the issue is still active and eligible —
> if so, it dispatches a new worker session on the same workspace.

---

## State Transition Diagram

```
                         ┌─────────────────────────────┐
                         │         UNCLAIMED             │
                         │  (not in running or retry)    │
                         └────────────┬────────────────-┘
                                      │ dispatch eligible on poll tick
                                      ▼
                         ┌─────────────────────────────┐
                    ┌───▶│          CLAIMED              │◀──────────────┐
                    │    └──────┬──────────────┬────────┘               │
                    │           │              │                         │
                    │    worker │ spawned   retry │ timer scheduled      │
                    │           ▼              ▼                         │
                    │    ┌────────────┐  ┌────────────┐                 │
                    │    │  RUNNING   │  │RETRYQUEUED │                 │
                    │    └──────┬─────┘  └─────┬──────┘                 │
                    │           │              │                         │
                    │  abnormal │ exit    timer│ fires                   │
                    │    ┌──────▼──────┐       │                         │
                    └────│ RETRYQUEUED │       │                         │
                         └─────────────┘       │                         │
                                               │ issue still active     │
                                               │ AND slots available    │
                                               └────────────────────────┘
                                               │ issue not found OR
                                               │ no longer active
                                               ▼
                         ┌─────────────────────────────┐
                         │          RELEASED             │
                         │  claim removed; returns to    │
                         │  Unclaimed on next eval       │
                         └─────────────────────────────┘

  Additional transitions to RELEASED:
    Running ──[tracker state = terminal]──▶ RELEASED (+ workspace cleanup)
    Running ──[tracker state = non-active]─▶ RELEASED (no workspace cleanup)
    Running ──[stall timeout]──────────────▶ RETRYQUEUED
    Running ──[reconciliation cancels]─────▶ RELEASED
```

---

## Transition Triggers

### Poll Tick
Fires every `polling.interval_ms` (default 30s). Sequence:
1. Reconcile running issues.
2. Validate dispatch config (skip dispatch if invalid; reconciliation still runs).
3. Fetch candidates from tracker.
4. Sort and dispatch until slots exhausted.

### Worker Exit (Normal)
- Remove from `running` map; update aggregate token/runtime totals.
- Schedule **continuation retry**: attempt `1`, fixed delay `1000 ms`.
- The issue stays Claimed (in RetryQueued) pending the continuation check.

### Worker Exit (Abnormal)
- Remove from `running` map; update totals.
- Schedule **failure retry** with exponential backoff (see formula below).
- Issue stays Claimed (in RetryQueued).

### Codex Update Event
- Update live session fields: `last_codex_event`, `last_codex_timestamp`, `last_codex_message`.
- Update per-session token counters and aggregate `codex_totals`.
- Update `codex_rate_limits` with the latest rate-limit payload.
- No state transition; purely a metadata update to the Running entry.

### Retry Timer Fired
- Pop the RetryEntry from `retry_attempts`.
- Fetch active candidate issues from the tracker.
- If the issue is not found → **Release** claim.
- If found and still eligible and slots available → **Dispatch** (transition to Running).
- If found but no longer active → **Release** claim.
- If found, eligible, but no slots → requeue with error `no available orchestrator slots`.

### Reconciliation State Refresh
Runs at the start of every tick:
- Fetch current tracker states for all `running` issue IDs.
- Terminal state → terminate worker + clean workspace → **Release**.
- Still active state → update in-memory issue snapshot; stay Running.
- Neither active nor terminal → terminate worker without cleanup → **Release**.
- If the state refresh API call fails → keep workers running; retry on next tick.

### Stall Timeout
- Orchestrator tracks elapsed time since `last_codex_timestamp` (or `started_at` if no events yet).
- If `elapsed_ms > codex.stall_timeout_ms` (and stall detection is enabled) → terminate worker.
- Transitions: Running → RetryQueued (exponential backoff retry scheduled).
- Disable stall detection by setting `codex.stall_timeout_ms <= 0`.

---

## Dispatch Eligibility Predicates

An issue is eligible for dispatch only if **all** of the following hold:

1. Issue has non-empty `id`, `identifier`, `title`, and `state` fields.
2. `state` is in `active_states` (case-insensitive after trim).
3. `state` is **not** in `terminal_states`.
4. Issue `id` is **not** in the `running` map.
5. Issue `id` is **not** in the `claimed` set.
6. Global concurrency slots are available: `running_count < max_concurrent_agents`.
7. Per-state concurrency slots are available (if `max_concurrent_agents_by_state[state]` is set).
8. **Blocker rule for `Todo` state**: if the issue's tracker state is `Todo`, at least one
   blocker exists, and any blocker's state is **not** in `terminal_states` → **not eligible**.
   An issue with no blockers, or all blockers in terminal states, passes this check.

### Dispatch Sort Order

Issues that pass all predicates are sorted before dispatching:

1. `priority` ascending — values 1–4 preferred; `null` / unknown sorts last.
2. `created_at` oldest first — stable tie-breaker across priority groups.
3. `identifier` lexicographic — final tie-breaker.

---

## Retry Backoff Formula

**Continuation retries** (after normal worker exit):
```
delay_ms = 1000   (fixed, ~1 second)
attempt  = 1
```

**Failure retries** (abnormal exit, stall, slot exhaustion):
```
delay_ms = min(10000 × 2^(attempt - 1), agent.max_retry_backoff_ms)
```

| Attempt | Formula | Delay (default 5-min cap) |
|---------|---------|---------------------------|
| 1 | 10000 × 2^0 | 10s |
| 2 | 10000 × 2^1 | 20s |
| 3 | 10000 × 2^2 | 40s |
| 4 | 10000 × 2^3 | 80s |
| 5 | 10000 × 2^4 | 160s |
| 6 | 10000 × 2^5 | 300s (capped) |
| 7+ | — | 300s (capped) |

`agent.max_retry_backoff_ms` defaults to `300000` (5 minutes). Any previous retry timer for the
same issue is cancelled before the new one is registered.

---

## Reconciliation Details

Reconciliation runs **before** dispatch on every tick — it is never skipped, even when config
validation fails.

**Part A — Stall Detection:**
For each entry in `running`, compute elapsed time:
- Use `last_codex_timestamp` if any agent event has been received.
- Fall back to `started_at` if no events yet.
- If `elapsed_ms > codex.stall_timeout_ms` → terminate worker and queue failure retry.

**Part B — Tracker State Refresh:**
- Batch-fetch current states for all running issue IDs.
- On fetch failure → log warning, keep all workers running, skip Part B for this tick.
- For each refreshed issue:
  - **Terminal** (`terminal_states`) → terminate worker, delete workspace directory.
  - **Active** (`active_states`) → update in-memory issue snapshot; session continues.
  - **Other** → terminate worker; no workspace cleanup (issue may become active again).

---

## Run Attempt Sub-States

Within a single Running entry, the worker itself progresses through these phases:

```
PreparingWorkspace → BuildingPrompt → LaunchingAgentProcess
  → InitializingSession → StreamingTurn → Finishing
  → Succeeded | Failed | TimedOut | Stalled | CanceledByReconciliation
```

These terminal reasons affect retry scheduling and log output but do not change the orchestration
state machine directly — all non-Succeeded outcomes route to the failure retry path.
