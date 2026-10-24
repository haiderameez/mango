# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Backend exists: FastAPI + SQLAlchemy 2 + PostgreSQL, layered router → service → repository.
Console surface: a single static HTML file with vanilla JS and CSS, served by FastAPI at
`/console`. No build step, no npm, no framework — decided by the user to keep the project
runnable with one `uvicorn` command.

## Users

Two audiences, weighted equally by the user's decision:

- **An on-call engineer or SRE mid-incident.** Wants to scan many incidents fast, see
  severity and status without reading, open one, read its history, and find out what the AI
  investigation concluded. Often at night, often on a second monitor beside logs and a
  terminal.
- **A technical reviewer** (recruiter, hiring engineer) looking at the project for about a
  minute. The AI investigation is the part of this product nothing else in the category has,
  so it must be visible and legible immediately, not buried behind navigation.

## Product Purpose

Mango manages software incidents and then investigates them with a multi-agent AI workflow
that reads the failing application's real logs. Success is an engineer going from "the app is
broken" to "here is the likely cause, the evidence behind it, and what to check" without
reading raw logs themselves.

## Positioning

The investigation is **evidence-bound and auditable**, which is the thing a generic
"AI explains your error" tool cannot truthfully copy:

- Log retrieval is ordinary tested Python, not a model with system access. The model only
  ever sees a bounded, credential-scrubbed set of records.
- The report separates **collected facts** from **model conclusions**, carries a confidence
  level, and lists the evidence that is *missing or contradicting*.
- Every agent's run is persisted as an `AgentExecution` with its output, its duration, and
  its own reasoning, so a conclusion can be traced back to what produced it.
- Confidence tracks evidence quality, demonstrably: the same agents report `low` on a single
  log line and `medium` when given a correlated failure sequence.

## Operating Context

- Incidents arrive from a companion app (DummyCommerce) that fails on demand, writes JSONL
  logs, and calls Mango's API; or are created by hand.
- An investigation is queued, not instant. One runs at a time, each takes roughly 30–60
  seconds across five agents, and a run can be `PENDING`, `RUNNING`, `COMPLETED` or `FAILED`.
- The LLM runs on a free-tier Gemini key with a hard daily request budget. Remaining budget
  and queue depth are operationally meaningful and already exposed at
  `GET /investigations/quota`.
- Engineers collaborate on an incident through comments; the system records a separate,
  append-only activity timeline.

## Capabilities and Constraints

- Entities: User, Incident, Comment, Activity, WorkflowRun, AgentExecution.
- Incident severity: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. Status: `OPEN` → `INVESTIGATING` →
  `RESOLVED`, one-way, no skipping.
- Permissions are per-incident, not role-based: only the creator assigns, only the creator or
  assignee changes status, only the author edits or deletes a comment.
- The five agents, always in this order: `planner`, `evidence_collector`, `root_cause`,
  `fix_recommendation`, `report`. Two of them (`evidence_collector`, `report`) are plain
  Python and have no reasoning to show.
- Incident list supports filtering by status, severity, assignee, creator and title search,
  with limit/offset pagination, newest first.
- Console authentication is implemented: the console signs in through the same `/auth`
  endpoints as any other client and holds a bearer token in `localStorage`. It has no
  privileged path into the API.
- There is no incident-delete endpoint and no role system. The console must not imply either.

## Brand Commitments

- The name **Mango** is fixed. The user explicitly left the visual identity free and declined
  a literal fruit reading, so the name is not a palette instruction.
- No logo, typeface or colour has been supplied. Note: orange and red are already spoken for
  by `HIGH` and `CRITICAL` severity, so they are not free as brand colours.

## Evidence on Hand

Real, working, already verified end to end — nothing here needs inventing:

- Live investigation reports produced by Gemini against real DummyCommerce logs, including
  one `medium`-confidence diagnosis naming an upstream service and its circuit-breaker
  cascade.
- Real agent reasoning text captured per execution.
- Real activity timelines, comments, severity and status transitions.
- Real quota figures (`requests_used_today`, `requests_remaining_today`, `queue_depth`).
- 214 passing tests across backend and DummyCommerce (199 + 15).
- A 50-scenario synthetic evaluation harness; full live accuracy and manual judge validation
  remain pending and must not be represented as measured product claims.

## Accessibility

No formal target stated. Treat WCAG AA contrast and full keyboard operation as the floor,
since the stated scene includes night-time use on a secondary monitor.
