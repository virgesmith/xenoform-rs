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

## 2026-07-10 — Fold the Python ABI into the module checksum (issue #13)

**Why** — A compiled extension is specific to the interpreter that built it: a
free-threaded (`3.14t`) binary is version-specific, and a GIL `abi3` binary loaded
under a free-threaded interpreter silently re-enables the GIL. Previously the
checksum only covered the generated sources, so switching interpreters left users
with a stale binary and the "delete the `ext` folder" failure mode — or worse, a
binary that imported but degraded free-threading without any signal.

**What** — `ModuleSpec.make_source` now emits the interpreter's ABI tag as a
`// Built for Python ABI: …` comment at the top of the generated `lib.rs`. Because
the checksum embedded in the module (`__checksum__`) is a hash of the generated
sources, the comment automatically becomes part of it: running under a different
Python version, GIL mode, or platform changes the source, so the freshness check
in `compile.py` mismatches and triggers the normal automatic rebuild.

**Design decisions**
- ABI tag source is `sysconfig.get_config_var("EXT_SUFFIX")` (e.g.
  `.cpython-314t-x86_64-linux-gnu.so`) — a single value that captures Python
  version, free-threaded flag, and platform on all OSes in the CI matrix.
  `SOABI` was rejected (historically undefined on Windows);
  `sys.implementation.cache_tag` was rejected (omits the free-threaded `t` flag,
  which lives in the ABI tag, not the bytecode cache tag).
- Embedded as a source comment rather than mixed into the hash bytes directly.
  Both make the checksum ABI-sensitive, but the comment also leaves the ABI
  human-readable in `lib.rs`, so when a stale binary is suspected the value that
  drove (or didn't drive) a rebuild can be read straight from the generated
  source instead of being an invisible input to a hash. rustfmt preserves the
  leading comment, so it survives formatting unchanged.
- Deliberately conservative: hashing the full tag forces a rebuild on any minor
  version bump even though GIL builds use `abi3-py312` and would remain
  ABI-compatible. A rebuild costs one compile; distinguishing "abi3-safe" from
  "version-specific" (free-threaded) builds would complicate the hash for a rare
  saving and risk missing the silent-GIL-re-enable case.
- No change to the comparison logic in `compile.py` — the ABI is treated as just
  another build input to the existing hash, so the rebuild path stays single.

**Follow-ups** — The remaining robustness items in issue #13 (shared cargo target
dir, sidecar checksum file, AOT build command) are untouched; the sidecar-file
idea would pair well with this since the ABI-sensitive checksum makes the sidecar
equally trustworthy.

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
