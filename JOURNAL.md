# Development Journal

A running log of every task/PR: *why* it was done and the *design decisions* made.
Newest entries at the top. This is the durable record of intent that keeps the
maintainer in control of the codebase's direction — see the
[Task & Design Summaries](AGENTS.md#task--design-summaries) policy in `AGENTS.md`.

Entry template:

```markdown
## YYYY-MM-DD — <title> (#PR)

**Why** — the motivation and the problem this solves.

**What** — high-level description of the change.

**Design decisions**
- <decision> — alternatives considered, why this was chosen.

**Follow-ups** — anything deferred, known limitations.
```

---

## 2026-07-09 — Add collaboration rules and development journal (#17)

**Why** — The maintainer wants to retain ownership of the codebase — understanding
every change well enough to explain and modify it independently — rather than being
outpaced by the agent. Needed explicit rules of engagement and a durable record of
intent per change.

**What** — Added a *Collaboration & Ownership* section (plan-first-with-approval,
small diffs, explain-it-back gate, justify trade-offs, learnable idioms) and a
*Task & Design Summaries* section to `AGENTS.md`, wired both into the Workflow, and
introduced this `JOURNAL.md`. Also noted in `AGENTS.md` that the `examples` extra
must be installed for `ty` to pass (it type-checks `examples/`, which imports pandas).

**Design decisions**
- Single append-only `JOURNAL.md` at the repo root — chosen over per-task files in
  `docs/tasks/`. One file is lower-friction to maintain, reads top-to-bottom as a
  history, and avoids proliferating small files. Trade-off: it will grow over time,
  but old entries can be archived if it ever gets unwieldy.

**Follow-ups** — None.
