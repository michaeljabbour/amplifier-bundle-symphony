# Harness Engineering Principles

Agent orchestration systems like Symphony do not succeed or fail based on the coding agent alone.
They succeed or fail based on the harness around the agent — the structure of context, the
enforcement of invariants, the management of entropy at scale. These principles, distilled from
OpenAI's production harness engineering experience, apply to any system where AI agents generate
high volumes of code changes against a shared codebase. Symphony embodies many of them by design:
`WORKFLOW.md` is Progressive Disclosure made concrete; workspace isolation is Mechanical
Enforcement at the filesystem level; the poll-dispatch-reconcile loop is Entropy Management applied
to scheduling.

---

## 1. Progressive Disclosure

**Give agents a map, not a 1,000-page manual.**

Agents have bounded context windows. Everything they need must be reachable through a small,
stable entry point — not dumped wholesale into the prompt.

The pattern: create an `AGENTS.md` (or equivalent) that is roughly 100 lines, structured as a
table of contents pointing to deeper `docs/` sources. The entry point covers the 20% of knowledge
that applies to 80% of tasks. Agents that need more follow the pointers.

Structured `docs/` directories serve as the system of record. Documents are scoped by domain
(`ISSUE_LIFECYCLE.md`, `HTTP_API.md`, `HARNESS_ENGINEERING.md`) and are stable enough to
`@`-mention reliably from prompts or behaviors. Agents start with a small, trustworthy context
and learn where to look next rather than being overwhelmed upfront.

**In Symphony:** `WORKFLOW.md` is the entry point for the coding agent. It provides the immediate
task context (the issue prompt) without embedding the entire project history. The agent discovers
architectural context through the repository it operates in.

---

## 2. Agent Legibility

**Optimize everything for agent readability. What agents can't access in-context doesn't exist.**

Agents operate only on what is in their context window. If decisions live in Slack threads, Google
Docs, or team members' heads, they are invisible to agents. The discipline is: **if it matters,
it must be in the repo.**

Practical implications:
- Push meeting decisions, architecture notes, and design rationale into versioned documents.
- Favour boring, composable technologies. Agents are trained on common stacks — niche frameworks
  introduce surface area that training data doesn't cover well.
- Use formats that are well-represented in training data: Markdown, YAML, JSON, standard REST.
  Avoid proprietary DSLs or underdocumented internal formats for anything agents must produce.
- Avoid encoding important context only in commit messages or PR descriptions — these are often
  outside the agent's active context.

**In Symphony:** the entire runtime contract is `WORKFLOW.md` — a Markdown file checked into the
repo. No out-of-band service configuration. The agent gets the policy and the issue; everything
required to act is in those two sources.

---

## 3. Mechanical Enforcement

**Encode invariants as custom linters, structural tests, and CI checks. Enforce architecture
through code, not documentation.**

Documentation-only conventions drift. Agents (and humans) forget or deviate. Mechanical
enforcement makes deviation impossible to land undetected.

Key patterns:
- Custom linters catch architectural violations and emit **remediation instructions in the error
  message itself** — so the agent's next context window includes both the problem and the fix.
- Structural tests verify invariants that are hard to lint (e.g. "every public module has a
  corresponding test file").
- CI gates enforce boundaries centrally. Individual contributors (human or agent) get local
  autonomy within those boundaries.
- Fail loudly with actionable messages. A lint error that says "import not allowed from this
  layer" with a pointer to the architecture doc is far more useful than a cryptic import error.

**In Symphony:** workspace path safety is mechanically enforced — the orchestrator rejects any
workspace path not inside `workspace.root` before the agent launches. No documentation warning
could be as reliable.

---

## 4. Entropy Management

**Code drift is inevitable at high agent throughput. Encode golden principles and run recurring
cleanup agents.**

When agents generate dozens of PRs a day, entropy accumulates faster than humans can review it.
Naming conventions diverge. Abstraction layers blur. Duplicate utilities multiply. Left
unmanaged, this compounds into a codebase that is increasingly hard for agents — and humans — to
navigate.

The discipline:
- Encode "golden principles" explicitly: naming conventions, module structure rules, preferred
  patterns. Make them machine-checkable where possible.
- Treat technical debt as high-interest debt — pay it continuously in small increments rather than
  letting it compound. A 30-line refactor PR is far cheaper than a 3,000-line structural overhaul.
- Run dedicated background cleanup agents on a schedule. These agents scan for drift against golden
  principles and open targeted, narrow refactoring PRs. Each PR addresses one specific deviation.
- Track entropy metrics: file length distributions, import depth, test coverage deltas. Treat a
  rising metric as a signal to dispatch a cleanup cycle.

**In Symphony:** the stall detection and reconciliation loop is entropy management for the
scheduling state — it continuously corrects drift between orchestrator state and tracker reality.
The same principle applies to codebases.

---

## 5. Repository as System of Record

**Knowledge that lives outside the repo is invisible to agents. Make the repo the single source of
truth for everything that shapes agent behaviour.**

Design documents, execution plans, quality grades, technical decision logs, and architectural
diagrams should all be versioned and co-located with the code they describe. This is not just good
documentation hygiene — it is a functional requirement for agent-assisted development.

Corollaries:
- Post-mortems and incident notes belong in `docs/` (or equivalent), not just in incident
  trackers.
- Architecture decision records (ADRs) enable agents to understand *why* a constraint exists, not
  just that it does.
- Quality grades (e.g. "this module is stable", "this module is experimental") should be explicit
  and machine-readable.
- Enable progressive disclosure: structure documents so agents can navigate from high-level summary
  to detailed spec without loading everything at once.

**In Symphony:** the spec itself (`SPEC.md`) is the system of record. This bundle's `docs/`
directory is the distilled, agent-readable form of that spec — structured for `@`-mention access
rather than linear reading.

---

## 6. Increasing Application Legibility

**Make the running application itself inspectable by agents.**

Agents need to verify that their code changes actually work. Giving them only static analysis tools
(linters, type checkers) is insufficient. They need to observe the running system.

Patterns:
- **Boot per git worktree.** Agents working in isolation can start a fresh instance of the
  application against their own workspace without interfering with other running instances.
- **Wire Chrome DevTools Protocol (CDP).** Give agents DOM access and screenshot capability for
  front-end verification. Agents that can see what a page looks like can verify their UI changes.
- **Expose logs, metrics, and traces via a local observability stack.** Run a lightweight instance
  of log aggregation and metrics collection in the development environment.
- **Enable direct query access.** Agents should be able to run `LogQL` and `PromQL` queries (or
  equivalent) against local observability data to verify behaviour.

**In Symphony:** the HTTP API (`/api/v1/state`, `/api/v1/<identifier>`) is Symphony's legibility
surface. An Amplifier agent monitoring a Symphony run can query live session state, token
consumption, and retry queue depth — it doesn't have to infer orchestrator state from logs alone.

---

## 7. Throughput Changes Merge Philosophy

**When agent throughput exceeds human attention, the cost of waiting exceeds the cost of fixing.**

At low PR volume, blocking merges on thorough review is sensible. At high agent throughput — tens
of PRs per day — the bottleneck shifts. Strict blocking gates become the constraint, not code
quality. The philosophy inverts: merge fast, fix fast.

Principles:
- **Minimal blocking merge gates.** Only block on hard failures (broken builds, failing tests).
  Advisory concerns are non-blocking.
- **Short-lived PRs.** Agent PRs should be reviewed and merged or closed within hours, not days.
  Long-lived PRs accumulate merge conflicts and become expensive to integrate.
- **Test flakes are addressed with follow-up runs**, not PR blocks. If a test flakes on an agent
  PR, re-run before blocking.
- **Corrections are cheap.** When agents generate code at high throughput, a wrong change can be
  corrected by another agent in the next cycle. The risk model is different from human-authored
  changes where a mistake might take weeks to fix.

**In Symphony:** the service is designed for continuous operation — issues cycle through
continuously, and corrections (retrying a failed session, adjusting a prompt) happen on the next
tick. The same fast-feedback philosophy applies to the PRs agents produce.

---

## Applicability Beyond Symphony

These principles are not specific to Symphony or to Linear-based workflows. They apply to any
system where AI agents interact with a codebase at scale:

- **Progressive Disclosure** scales to any documentation system, not just `WORKFLOW.md`.
- **Agent Legibility** applies to any team that wants agents to operate reliably — the more
  knowledge is in the repo, the better.
- **Mechanical Enforcement** is universally applicable; the tools differ (eslint, ruff, custom
  scripts) but the principle is constant.
- **Entropy Management** becomes critical at any throughput where agents contribute more changes
  per day than human reviewers can deeply inspect.
- **Repository as System of Record** is sound engineering practice regardless of whether agents
  are involved — agents simply make the cost of violating it more immediate and visible.
- **Application Legibility** matters for any automated testing or verification workflow.
- **Merge Philosophy** depends on team risk tolerance, but the directional principle — that high
  throughput changes the cost calculus — is broadly true.

The harness is not scaffolding to be discarded once the agent is "good enough." It is a permanent,
load-bearing part of the system. Invest in it proportionally to how much you rely on agent output.
